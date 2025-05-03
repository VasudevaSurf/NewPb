from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime, timedelta
import calendar
import os

# Get the absolute path to the frontend directory
# This assumes that frontend and backend are at the same level
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend')

app = Flask(__name__)
CORS(app)

# MongoDB connection
client = MongoClient('mongodb+srv://abbas:Abbas111@cluster0.c2lmxxc.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
db = client['order_management']

# Collections
users = db.users
branches = db.branches
delivery_boys = db.delivery_boys
configurations = db.configurations
plans = db.plans
pauses = db.pauses

# Helper functions
def calculate_end_date(start_date, delivery_type):
    """Calculate end date based on delivery type"""
    # Assuming plans are for 1 month
    if delivery_type == "Monday to Saturday":
        return start_date + timedelta(days=30)  # Approx 26 working days
    else:  # Monday to Friday
        return start_date + timedelta(days=30)  # Approx 22 working days

def is_delivery_day(date, delivery_type):
    """Check if the given date is a delivery day"""
    weekday = date.weekday()
    if delivery_type == "Monday to Saturday":
        return weekday < 6  # Monday to Saturday (0-5)
    else:  # Monday to Friday
        return weekday < 5  # Monday to Friday (0-4)

def get_delivery_dates(days_ahead=3):
    """Get dates for delivery calculations"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return [today + timedelta(days=i) for i in range(days_ahead)]

def format_date(date):
    """Format date for JSON response"""
    return date.strftime("%Y-%m-%d")

# Route to serve frontend files
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    if path == "":
        return send_from_directory(frontend_dir, 'index.html')
    else:
        if os.path.exists(os.path.join(frontend_dir, path)):
            return send_from_directory(frontend_dir, path)
        else:
            # If path doesn't exist, return index.html for client-side routing
            return send_from_directory(frontend_dir, 'index.html')

# API Routes
# Configuration routes
@app.route('/api/configurations', methods=['GET'])
def get_configurations():
    """Get all configuration values"""
    config_type = request.args.get('type', None)
    if config_type:
        config = configurations.find_one({"type": config_type})
        return jsonify({"values": config["values"] if config else []})
    else:
        result = {}
        for config in configurations.find():
            result[config["type"]] = config["values"]
        return jsonify(result)

@app.route('/api/configurations', methods=['POST'])
def add_configuration():
    """Add new configuration value"""
    data = request.get_json()
    config_type = data.get('type')
    value = data.get('value')
    
    if not config_type or not value:
        return jsonify({"error": "Type and value are required"}), 400
    
    # Check if config type exists
    config = configurations.find_one({"type": config_type})
    if config:
        # Add value if it doesn't exist
        if value not in config["values"]:
            configurations.update_one(
                {"type": config_type},
                {"$push": {"values": value}}
            )
    else:
        # Create new config type
        configurations.insert_one({
            "type": config_type,
            "values": [value],
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        })
    
    return jsonify({"success": True})

@app.route('/api/configurations/<config_type>/<value>', methods=['DELETE'])
def delete_configuration(config_type, value):
    """Delete configuration value"""
    result = configurations.update_one(
        {"type": config_type},
        {"$pull": {"values": value}}
    )
    
    if result.modified_count:
        return jsonify({"success": True})
    else:
        return jsonify({"error": "Value not found"}), 404

# User routes
@app.route('/api/users', methods=['GET'])
def get_users():
    """Get users with optional filtering"""
    branch = request.args.get('branch', None)
    
    query = {}
    if branch:
        query["branch"] = branch
    
    user_list = []
    for user in users.find(query):
        user["_id"] = str(user["_id"])
        user["start_date"] = format_date(user["start_date"])
        user["end_date"] = format_date(user["end_date"])
        
        if "current_pause" in user and user["current_pause"]:
            user["current_pause"]["start_date"] = format_date(user["current_pause"]["start_date"])
            user["current_pause"]["end_date"] = format_date(user["current_pause"]["end_date"])
        
        user_list.append(user)
    
    return jsonify(user_list)

@app.route('/api/users', methods=['POST'])
def add_user():
    """Add a new user"""
    data = request.get_json()
    
    # Validate required fields
    required_fields = ["name", "phone", "state", "city", "branch", "area", 
                      "pincode", "plan", "payment_status", "delivery_type"]
    
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400
    
    # Parse dates
    try:
        start_date = datetime.strptime(data["start_date"], "%Y-%m-%d")
    except (ValueError, KeyError):
        return jsonify({"error": "Invalid start date format"}), 400
    
    # Calculate end date
    end_date = calculate_end_date(start_date, data["delivery_type"])
    
    # Create user document
    user = {
        "name": data["name"],
        "phone": data["phone"],
        "state": data["state"],
        "city": data["city"],
        "branch": data["branch"],
        "area": data["area"],
        "pincode": data["pincode"],
        "plan": data["plan"],
        "payment_status": data["payment_status"],
        "amount_paid": float(data.get("amount_paid", 0)),
        "delivery_type": data["delivery_type"],
        "start_date": start_date,
        "end_date": end_date,
        "delivery_boy_code": data.get("delivery_boy_code", ""),
        "is_active": True,
        "current_pause": None,
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    }
    
    result = users.insert_one(user)
    
    return jsonify({
        "success": True,
        "id": str(result.inserted_id)
    })

@app.route('/api/users/<user_id>', methods=['PUT'])
def update_user(user_id):
    """Update user information"""
    data = request.get_json()
    
    # Ensure user exists
    user = users.find_one({"_id": ObjectId(user_id)})
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    update_data = {}
    
    # Update basic fields
    for field in ["name", "phone", "state", "city", "branch", "area", 
                 "pincode", "plan", "payment_status", "amount_paid", 
                 "delivery_type", "delivery_boy_code"]:
        if field in data:
            update_data[field] = data[field]
    
    # Handle date updates
    if "start_date" in data:
        try:
            start_date = datetime.strptime(data["start_date"], "%Y-%m-%d")
            update_data["start_date"] = start_date
            
            # Recalculate end date if delivery type is provided or use existing
            delivery_type = data.get("delivery_type", user["delivery_type"])
            update_data["end_date"] = calculate_end_date(start_date, delivery_type)
        except ValueError:
            return jsonify({"error": "Invalid date format"}), 400
    
    # Update active status if provided
    if "is_active" in data:
        update_data["is_active"] = data["is_active"]
    
    update_data["updated_at"] = datetime.now()
    
    users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": update_data}
    )
    
    return jsonify({"success": True})

@app.route('/api/users/<user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Delete a user"""
    result = users.delete_one({"_id": ObjectId(user_id)})
    
    if result.deleted_count:
        return jsonify({"success": True})
    else:
        return jsonify({"error": "User not found"}), 404

# User pause routes
@app.route('/api/users/pause', methods=['POST'])
def pause_user():
    """Pause a user's deliveries"""
    data = request.get_json()
    
    # Validate required fields
    required_fields = ["user_id", "start_date", "end_date"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400
    
    try:
        user_id = data["user_id"]
        start_date = datetime.strptime(data["start_date"], "%Y-%m-%d")
        end_date = datetime.strptime(data["end_date"], "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Invalid date format"}), 400
    
    # Ensure user exists
    user = users.find_one({"_id": ObjectId(user_id)})
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    # Calculate days paused
    days_paused = 0
    current_date = start_date
    while current_date <= end_date:
        if is_delivery_day(current_date, user["delivery_type"]):
            days_paused += 1
        current_date += timedelta(days=1)
    
    # Create pause record
    pause = {
        "user_id": ObjectId(user_id),
        "start_date": start_date,
        "end_date": end_date,
        "days_paused": days_paused,
        "created_at": datetime.now()
    }
    
    pauses.insert_one(pause)
    
    # Update user's end date and current pause info
    new_end_date = user["end_date"] + timedelta(days=days_paused)
    
    users.update_one(
        {"_id": ObjectId(user_id)},
        {
            "$set": {
                "end_date": new_end_date,
                "current_pause": {
                    "start_date": start_date,
                    "end_date": end_date
                },
                "updated_at": datetime.now()
            }
        }
    )
    
    return jsonify({
        "success": True,
        "days_paused": days_paused,
        "new_end_date": format_date(new_end_date)
    })

# Dashboard routes
@app.route('/api/dashboard', methods=['GET'])
def get_dashboard_data():
    """Get dashboard delivery data"""
    branch = request.args.get('branch', None)
    
    delivery_dates = get_delivery_dates(3)
    
    result = {}
    for i, date in enumerate(delivery_dates):
        day_key = ["today", "tomorrow", "day_after_tomorrow"][i]
        
        query = {
            "is_active": True,
            "start_date": {"$lte": date},
            "end_date": {"$gte": date}
        }
        
        # Add branch filter if provided
        if branch:
            query["branch"] = branch
        
        # Filter out users on pause
        query["$or"] = [
            {"current_pause": None},
            {"current_pause.start_date": {"$gt": date}},
            {"current_pause.end_date": {"$lt": date}}
        ]
        
        # Total deliveries for this day
        total_count = users.count_documents(query)
        
        # Deliveries by delivery type
        monday_to_friday = users.count_documents({
            **query,
            "delivery_type": "Monday to Friday"
        })
        
        monday_to_saturday = users.count_documents({
            **query,
            "delivery_type": "Monday to Saturday"
        })
        
        # Get all matching users for this day
        matching_users = list(users.find(query))
        
        # Deliveries by plan - get directly from users
        plan_breakdown = {}
        for user in matching_users:
            plan_name = user.get("plan")
            if plan_name:
                if plan_name not in plan_breakdown:
                    plan_breakdown[plan_name] = 0
                plan_breakdown[plan_name] += 1
        
        # Deliveries by delivery boy
        delivery_boy_breakdown = {}
        
        # Group by delivery boy code
        for user in matching_users:
            delivery_boy_code = user.get("delivery_boy_code")
            if delivery_boy_code:
                if delivery_boy_code not in delivery_boy_breakdown:
                    delivery_boy_breakdown[delivery_boy_code] = 0
                delivery_boy_breakdown[delivery_boy_code] += 1
        
        # Get delivery boy names
        delivery_boy_details = {}
        for code, count in delivery_boy_breakdown.items():
            # Find the delivery boy details
            boy = delivery_boys.find_one({"code": code})
            name = boy["name"] if boy else "Unknown"
            delivery_boy_details[code] = {
                "name": name,
                "count": count
            }
        
        result[day_key] = {
            "date": format_date(date),
            "total": total_count,
            "delivery_types": {
                "Monday to Friday": monday_to_friday,
                "Monday to Saturday": monday_to_saturday
            },
            "plans": plan_breakdown,
            "delivery_boys": delivery_boy_details
        }
    
    return jsonify(result)

# Branch routes
@app.route('/api/branches', methods=['GET'])
def get_branches():
    """Get all branches"""
    branch_list = []
    for branch in branches.find():
        branch["_id"] = str(branch["_id"])
        branch_list.append(branch)
    
    return jsonify(branch_list)

@app.route('/api/branches', methods=['POST'])
def add_branch():
    """Add a new branch"""
    data = request.get_json()
    
    # Validate required fields
    required_fields = ["name", "city", "state"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400
    
    branch = {
        "name": data["name"],
        "city": data["city"],
        "state": data["state"],
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    }
    
    result = branches.insert_one(branch)
    
    # Add to configuration for dropdown selection
    configurations.update_one(
        {"type": "branch"},
        {"$addToSet": {"values": data["name"]}},
        upsert=True
    )
    
    return jsonify({
        "success": True,
        "id": str(result.inserted_id)
    })

# Plans routes
@app.route('/api/plans', methods=['GET'])
def get_plans():
    """Get all plans"""
    plan_list = []
    for plan in plans.find():
        plan["_id"] = str(plan["_id"])
        plan_list.append(plan)
    
    return jsonify(plan_list)

@app.route('/api/test-db')
def test_db():
    try:
        # Test the database connection
        db_names = client.list_database_names()
        collection_names = db.list_collection_names()
        return jsonify({
            "status": "success", 
            "databases": db_names,
            "collections": collection_names
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/plans', methods=['POST'])
def add_plan():
    """Add a new plan"""
    data = request.get_json()
    
    # Validate required fields
    if "name" not in data:
        return jsonify({"error": "Plan name is required"}), 400
    
    plan = {
        "name": data["name"],
        "description": data.get("description", ""),
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    }
    
    result = plans.insert_one(plan)
    
    # Add to configuration for dropdown selection
    configurations.update_one(
        {"type": "plan"},
        {"$addToSet": {"values": data["name"]}},
        upsert=True
    )
    
    return jsonify({
        "success": True,
        "id": str(result.inserted_id)
    })

# Delivery Boys routes
@app.route('/api/delivery-boys', methods=['GET'])
def get_delivery_boys():
    """Get all delivery boys"""
    delivery_boy_list = []
    for boy in delivery_boys.find():
        boy["_id"] = str(boy["_id"])
        delivery_boy_list.append(boy)
    
    return jsonify(delivery_boy_list)

@app.route('/api/delivery-boys', methods=['POST'])
def add_delivery_boy():
    """Add a new delivery boy"""
    data = request.get_json()
    
    # Validate required fields
    required_fields = ["code", "name", "branch"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400
    
    delivery_boy = {
        "code": data["code"],
        "name": data["name"],
        "phone": data.get("phone", ""),
        "branch": data["branch"],
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    }
    
    result = delivery_boys.insert_one(delivery_boy)
    
    # Add to configuration for dropdown selection
    configurations.update_one(
        {"type": "delivery_boy_code"},
        {"$addToSet": {"values": data["code"]}},
        upsert=True
    )
    
    return jsonify({
        "success": True,
        "id": str(result.inserted_id)
    })

@app.route('/api/branches/pause', methods=['POST'])
def pause_branch():
    """Pause all users in a branch"""
    data = request.get_json()
    
    # Validate required fields
    required_fields = ["branch", "start_date", "end_date"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400
    
    try:
        branch_name = data["branch"]
        start_date = datetime.strptime(data["start_date"], "%Y-%m-%d")
        end_date = datetime.strptime(data["end_date"], "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Invalid date format"}), 400
    
    # Find all active users in this branch
    branch_users = list(users.find({"branch": branch_name, "is_active": True}))
    
    if not branch_users:
        return jsonify({"error": "No active users found in this branch"}), 404
    
    paused_users = 0
    
    # Process each user in the branch
    for user in branch_users:
        # Skip users who are already paused
        if user.get("current_pause"):
            continue
            
        # Calculate days paused based on delivery type
        days_paused = 0
        current_date = start_date
        while current_date <= end_date:
            if is_delivery_day(current_date, user["delivery_type"]):
                days_paused += 1
            current_date += timedelta(days=1)
        
        # Create pause record
        pause = {
            "user_id": user["_id"],
            "branch": branch_name,
            "start_date": start_date,
            "end_date": end_date,
            "days_paused": days_paused,
            "created_at": datetime.now()
        }
        
        pauses.insert_one(pause)
        
        # Update user's end date and current pause info
        new_end_date = user["end_date"] + timedelta(days=days_paused)
        
        users.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "end_date": new_end_date,
                    "current_pause": {
                        "start_date": start_date,
                        "end_date": end_date
                    },
                    "updated_at": datetime.now()
                }
            }
        )
        
        paused_users += 1
    
    return jsonify({
        "success": True,
        "paused_users": paused_users,
        "branch": branch_name,
        "start_date": format_date(start_date),
        "end_date": format_date(end_date)
    })

if __name__ == '__main__':
    # Initialize default configurations if not exists
    default_configs = [
        {"type": "state", "values": ["Telangana", "Karnataka"]},
        {"type": "city", "values": ["Hyderabad", "Bengaluru"]},
        {"type": "delivery_type", "values": ["Monday to Saturday", "Monday to Friday"]}
    ]
    
    for config in default_configs:
        configurations.update_one(
            {"type": config["type"]},
            {"$setOnInsert": {
                **config,
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }},
            upsert=True
        )
    
    # Ensure the plans are properly set up
    default_plans = ["Basic", "Premium", "Super"]
    
    # Add default plans to the plans collection if they don't exist
    for plan_name in default_plans:
        plan_exists = plans.find_one({"name": plan_name})
        if not plan_exists:
            plans.insert_one({
                "name": plan_name,
                "description": f"{plan_name} plan",
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            })
    
    # Also ensure plans are in the configurations collection
    plan_config = configurations.find_one({"type": "plan"})
    if not plan_config:
        configurations.insert_one({
            "type": "plan",
            "values": default_plans,
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        })
    else:
        # Update existing plan configuration to include any missing plans
        current_plans = plan_config.get("values", [])
        missing_plans = [p for p in default_plans if p not in current_plans]
        if missing_plans:
            configurations.update_one(
                {"type": "plan"},
                {"$push": {"values": {"$each": missing_plans}}}
            )
    
    print("Plans configuration checked and initialized.")
    
    app.run(debug=True, port=8000)