import os
import re

# ================== CẤU HÌNH ID & URL ==================
API_URL = "https://uma.moe/api/v4/circles?circle_id={}"
CIRCLE_ID_TO_CHECK = 230947009
CHANNEL_ID_TO_SEND = 1442395967369511054
TARGET_USER_ID = 1036115986467790918
SPOUSE_USER_ID = 872024401095294986
BET_ADMIN_ID = 708552026539163723
SOURCE_BOT_ID = 1400050839544008804

# ================== MONGODB ==================
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "BET_BUNG")

# ================== KEYWORDS & PATHS ==================
GAY_KEYWORDS = [
    "gay", "đồng tính", "bê đê", "lgbt", "les", "bisexual", "queer", "femb", "cong"
]
GAY_IMAGE_PATH = "gay.jpg"
GAY_WHITELIST_IDS = {
    1085788407864770560, 1434883205344792597, 872024401095294986, 1239908958123331664
}

# Regex bắt tin nhắn Correct
CORRECT_REGEX = re.compile(
    r"Correct\s+(?:<@!?(\d+)>|@(.+?))!"
    r".*?\(\+(\d+)\s+points\)"
    r".*?Current Streak:\s*\**(\d+)\**",
    re.IGNORECASE | re.DOTALL
)