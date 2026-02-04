import random
from pymongo import MongoClient
import config

mongo_client = MongoClient(config.MONGO_URI)
mongo_db = mongo_client[config.DB_NAME]
users_col = mongo_db["users"]

def get_user(user_id: int):
    return users_col.find_one({"user_id": user_id})

def create_user(user):
    credit = random.randint(1000, 2000)
    doc = {
        "user_id": user.id,
        "username": str(user),
        "social_credit": credit
    }
    users_col.insert_one(doc)
    return credit

def ensure_user(user):
    data = get_user(user.id)
    if not data:
        credit = create_user(user)
        return {
            "user_id": user.id,
            "social_credit": credit
        }
    return data

def change_credit(user, amount: int, reason: str = ""):
    ensure_user(user)
    users_col.update_one(
        {"user_id": user.id},
        {"$inc": {"social_credit": amount}}
    )
    sign = "+" if amount > 0 else ""
    return f"💳 **Social Credit**: {sign}{amount} ({reason})"

def change_credit_by_id(user_id: int, amount: int, reason: str):
    users_col.update_one(
        {"user_id": user_id},
        {"$inc": {"social_credit": amount}},
        upsert=True
    )