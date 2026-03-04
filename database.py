from pymongo import MongoClient
import random
from config import MONGO_URI, DB_NAME
from datetime import datetime, timezone

mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client[DB_NAME]

users_col = mongo_db["users"]
rob_col = mongo_db["rob_logs"]
circle_logs_col = mongo_db["circle_logs"]


def get_user(user_id: int):
    return users_col.find_one({"user_id": user_id})


def create_user(user):
    credit = random.randint(1000, 2000)
    doc = {
        "user_id": user.id,
        "username": str(user),
        "social_credit": credit,
        "inventory": {}   # 👈 THÊM DÒNG NÀY
    }
    users_col.insert_one(doc)
    return credit


def ensure_user(user):
    data = get_user(user.id)
    if not data:
        credit = create_user(user)
        return {"user_id": user.id, "social_credit": credit}
    return data


def change_credit(user, amount: int, reason: str = ""):
    ensure_user(user)
    users_col.update_one(
        {"user_id": user.id},
        {"$inc": {"social_credit": amount}}
    )
    sign = "+" if amount > 0 else ""
    return f"💳 **Social Credit**: {sign}{amount} ({reason})"


def change_credit_by_id(user_id: int, amount: int):
    users_col.update_one(
        {"user_id": user_id},
        {"$inc": {"social_credit": amount}},
        upsert=True
    )


def get_top_users(limit=10):
    return list(
        users_col.find({})
        .sort("social_credit", -1)
        .limit(limit)
    )

def add_item(user_id: int, item_name: str, amount: int = 1):
    users_col.update_one(
        {"user_id": user_id},
        {"$inc": {f"inventory.{item_name}": amount}}
    )

def get_inventory(user_id: int):
    user = users_col.find_one({"user_id": user_id})
    if not user:
        return {}
    return user.get("inventory", {})

def save_circle_snapshot(circle_id: int, data: dict):
    circle = data.get("circle", {})
    members = data.get("members", [])

    if not circle or not members:
        return

    try:
        updated_at = datetime.fromisoformat(
            circle["last_updated"].replace("Z", "+00:00")
        )
    except:
        updated_at = datetime.now(timezone.utc)

    circle_logs_col.update_one(
        {"circle_id": circle_id},  # tìm document theo circle_id
        {
            "$set": {
                "circle_name": circle.get("name"),
                "last_updated": updated_at,
                "members": members,
                "updated_at": datetime.now(timezone.utc)
            }
        },
        upsert=True  # nếu chưa có thì tạo mới
    )
