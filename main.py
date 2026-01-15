import discord
from discord.ext import commands, tasks
import requests
from datetime import datetime, timezone, timedelta, time
from threading import Thread
import asyncio
import random
import re
import os
from pymongo import MongoClient
# ================== CẤU HÌNH CỦA BẠN ==================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
API_URL = "https://uma.moe/api/v4/circles?circle_id={}"
# THAY 2 DÒNG NÀY BẰNG CỦA BẠN
CIRCLE_ID_TO_CHECK = 230947009  # ← ID Circle chính (Strategist)
CHANNEL_ID_TO_SEND = 1442395967369511054  # ← ID kênh nhận báo cáo tự động 7h sáng

TARGET_USER_ID = 1036115986467790918  # ID người bạn muốn bot phản ứng

SPOUSE_USER_ID = 872024401095294986
last_message_time = {}  # {user_id: datetime}

BET_ADMIN_ID = 708552026539163723  # người được phép tạo & chốt kèo

SOURCE_BOT_ID = 1400050839544008804  # 🔁 thay bằng ID bot bạn cung cấp

active_bet = None

GAY_KEYWORDS = [
    "gay", "đồng tính", "bê đê", "lgbt", "les", "bisexual", "queer", "femb"
]

GAY_IMAGE_PATH = "gay.jpg"  # hoặc .png / .gif
gay_cooldown = {}  # {user_id: timestamp lần cuối bị detect}

GAY_WHITELIST_IDS = {
    1085788407864770560, 1434883205344792597, 872024401095294986, 1239908958123331664
    # thêm ID khác nếu muốn
}

# ================== MONGODB ==================
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "BET_BUNG")

mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client[DB_NAME]

users_col = mongo_db["users"]  # collection users

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

def remove_mentions(text: str) -> str:
    # User mention <@123> hoặc <@!123>
    text = re.sub(r'<@!?\d+>', '', text)

    # Role mention <@&123>
    text = re.sub(r'<@&\d+>', '', text)

    # Channel mention <#123>
    text = re.sub(r'<#\d+>', '', text)

    return text

spouse_interaction_cooldown = {} 

CORRECT_REGEX = re.compile(
    r"Correct\s+(?:<@!?(\d+)>|@(.+?))!"
    r".*?\(\+(\d+)\s+points\)"
    r".*?Current Streak:\s*\**(\d+)\**",
    re.IGNORECASE | re.DOTALL
)

@bot.event
async def on_message(message):

    if message.author.id == 1400050839544008804:
        match = CORRECT_REGEX.search(message.content)
        if match:
            # Lấy thông tin từ regex
            user_id_str = match.group(1) # Nếu là mention <@ID>
            user_name_str = match.group(2) # Nếu là text @Name
            base_points = 0# int(match.group(3))
            streak = int(match.group(4))

            guild = message.guild
            if not guild: return

            member = None
            
            # Trường hợp 1: Bot tag trực tiếp (Có ID)
            if user_id_str:
                member = guild.get_member(int(user_id_str))
            
            # Trường hợp 2: Bot chỉ ghi tên (Tìm theo tên hiển thị)
            elif user_name_str:
                member = discord.utils.get(guild.members, display_name=user_name_str)

            if not member:
                # Nếu không tìm thấy member, có thể return hoặc log ra
                print(f"Không tìm thấy member: {user_id_str or user_name_str}")
                await message.channel.send(
                    f"**Mở tài khoản đi ku!!!** Gõ !registerDB"
                )
                return

            # 🎁 TÍNH BONUS STREAK
            streak_bonus = (streak - 1) // 30 + 1
            total_reward = base_points + streak_bonus

            # Cộng điểm (Giả sử hàm change_credit của bạn đã hoạt động tốt)
            change_credit(
                member,
                total_reward,
                reason=f"Correct answer (+{base_points}) + streak bonus (+{streak_bonus})"
            )

            await message.channel.send(
                #f"🔥 **{member.display_name}** đúng câu trả lời!\n"
                #f"➕ Điểm gốc: `{base_points}`\n"
                #f"🔥 Streak `{streak}` → thưởng `{streak_bonus}` SC\n"
                f"🏆 **Thưởng:** `{total_reward}` Social Credit"
            )
            
            # QUAN TRỌNG: Return ngay để không bị dính vào logic "if message.author.bot" ở dưới
            return

    if message.author.bot: # Ngăn cho nó k bắt bot
        return

    # Lấy thời điểm hiện tại dưới dạng UTC (Timezone-aware)
    # Thay thế cho datetime.utcnow() và datetime.now()
    now_utc = datetime.now(timezone.utc)

    raw_text = message.content
    no_mention_text = remove_mentions(raw_text)
    no_emoji_text = re.sub(r'<a?:[a-zA-Z0-9_]+:\d+>', '', no_mention_text)
    no_emoji_text = re.sub(r':[^:\s]+:', '', no_emoji_text)
    content_lower = no_emoji_text.lower().strip()

    # ====== GAY DETECT ======
    if (message.author.id not in GAY_WHITELIST_IDS and any(word in content_lower for word in GAY_KEYWORDS)):
        user_id = message.author.id
        last_time = gay_cooldown.get(user_id)
        
        # Sửa: Đảm bảo so sánh hai datetime cùng loại (aware)
        if last_time is None or (now_utc - last_time).total_seconds() >= 3600:
            gay_cooldown[user_id] = now_utc
            try:
                with open(GAY_IMAGE_PATH, "rb") as f:
                    img = discord.File(f, filename="gay.jpg")
                    await message.reply(
                        f"🚨 **GAY DETECTED** 🚨\n"
                        f"👤 **{message.author.display_name}** đã bị trừ **2000 điểm tấn công** 💀\n",
                        file=img
                    )
                    penalty_msg = change_credit(message.author, -10, "Gay detected")
                    await message.channel.send(penalty_msg)
            except FileNotFoundError:
                await message.reply("❌ File gay.jpg chưa có trong thư mục bot!")
            except Exception as e:
                print("Gay detect error:", e)

    # ====== PHẢN ỨNG USER ĐẶC BIỆT (Giữ nguyên) ======
    if message.author.id == TARGET_USER_ID:
        try:
            await message.reply("NÍN CMM !!!🤫🤫🤫")
        except Exception as e:
            print("Reply failed:", e)
    
    # ================== THEO DÕI TIN NHẮN CỦA SPOUSE ==================
    if message.author.id == SPOUSE_USER_ID:
        last_message_time[SPOUSE_USER_ID] = datetime.utcnow()

    # ====== LOGIC XỬ LÝ SPOUSE (ĐÃ THÊM COOLDOWN 1 NGÀY) ======
    
    # ================== THEO DÕI TIN NHẮN CỦA SPOUSE ==================
    if message.author.id == SPOUSE_USER_ID:
        last_message_time[SPOUSE_USER_ID] = now_utc

    # ====== LOGIC XỬ LÝ SPOUSE (COOLDOWN 1 NGÀY & NO WARNING) ======
    
    def check_spouse_cooldown(user_id):
        last_trigger = spouse_interaction_cooldown.get(user_id)
        if last_trigger:
            # So sánh thời gian hiện tại với thời gian lưu (cả 2 đều là UTC aware)
            if (datetime.now(timezone.utc) - last_trigger).total_seconds() < 86400:
                return True 
        return False

    # 1️⃣ MENTION SPOUSE
    if SPOUSE_USER_ID in [m.id for m in message.mentions]:
        if not check_spouse_cooldown(message.author.id):
            try:
                await message.reply("Gọi gì chồng bà 😡💢😏")
                spouse_interaction_cooldown[message.author.id] = datetime.now(timezone.utc)
            except Exception as e:
                print("Mention reply error:", e)

    # 2️⃣ REPLY SPOUSE
    if message.reference:
        try:
            replied_msg = await message.channel.fetch_message(message.reference.message_id)
            if replied_msg.author.id == SPOUSE_USER_ID:
                if not check_spouse_cooldown(message.author.id):
                    
                    async def delayed_reply():
                        await asyncio.sleep(60)
                        last_time_active = last_message_time.get(SPOUSE_USER_ID)
                        if not last_time_active: return

                        # Sửa lỗi Warning tại đây
                        if (datetime.now(timezone.utc) - last_time_active).total_seconds() >= 60:
                            if not check_spouse_cooldown(message.author.id):
                                try:
                                    await message.reply("Chờ chồng bà chút ⏳💤 chồng đang bận 😌")
                                    spouse_interaction_cooldown[message.author.id] = datetime.now(timezone.utc)
                                except Exception as e:
                                    print("Delayed reply error:", e)

                    asyncio.create_task(delayed_reply())
        except:
            pass

    await bot.process_commands(message)

@bot.group(name="bet", invoke_without_command=True)
async def bet(ctx):
    await ctx.send(
        "📌 **LỆNH BET**\n"
        "`**Tạo bet:** !bet create <title> | <opt1> | <opt2> ...`\n"
        "`**Đặt bet:**!bet join <số_option> <credit>`\n"
        "`**Dừng bet:** !bet stop\n`"
        "`**Kết thúc bet:** !bet end <số_option_thắng>\n`"
        "`**Xem bet:** !bet info\n`"
        "`**Bể bet:** !bet refund\n`"
    )


@bet.command(name="create")
async def bet_create(ctx, *, raw: str):
    global active_bet

    if ctx.author.id != BET_ADMIN_ID:
        await ctx.send("⛔ Mày không có quyền tạo kèo.")
        return

    if active_bet and active_bet["open"]:
        await ctx.send("⚠️ Đang có kèo khác rồi!")
        return

    parts = [p.strip() for p in raw.split("|")]
    if len(parts) < 3:
        await ctx.send("❌ Cần ít nhất 2 lựa chọn.")
        return

    title = parts[0]
    options = {}

    for i, opt in enumerate(parts[1:], start=1):
        options[i] = {"text": opt, "total": 0, "bets": {}}

    active_bet = {
        "creator_id": ctx.author.id,
        "title": title,
        "options": options,
        "total_pool": 0,
        "open": True,
        "ended": False     # 🏁 đã end hay chưa
    }

    msg = f"🎲 **KÈO BET MỚI** 🎲\n📌 {title}\n\n"
    for i, o in options.items():
        msg += f"`{i}`️⃣ {o['text']}\n"
    msg += "\n👉 Tham gia: `!bet join <số> <credit>`"

    await ctx.send(msg)

@bet.command(name="join")
async def bet_join(ctx, option: int, amount: int):
    global active_bet

    if not active_bet or not active_bet["open"]:
        await ctx.send("❌ Hiện không có kèo nào.")
        return

    if option not in active_bet["options"]:
        await ctx.send("❌ Lựa chọn không tồn tại.")
        return

    # 🔒 GIỚI HẠN BET
    if amount < 10 or amount > 200:
        await ctx.send("❌ Chỉ được bet từ **10 đến 200** Social Credit.")
        return

    user_data = ensure_user(ctx.author)
    if user_data["social_credit"] < amount:
        await ctx.send("❌ Không đủ Social Credit.")
        return

    # ❌ Không cho bet nhiều cửa
    for opt in active_bet["options"].values():
        if ctx.author.id in opt["bets"]:
            await ctx.send("⚠️ Mỗi người chỉ được bet **1 cửa**.")
            return

    # Trừ tiền
    change_credit(ctx.author, -amount, "Bet tham gia")

    opt = active_bet["options"][option]
    opt["total"] += amount
    opt["bets"][ctx.author.id] = amount
    active_bet["total_pool"] += amount

    await ctx.send(
        f"✅ **{ctx.author.display_name}** đã bet `{amount}` SC vào **{opt['text']}**"
    )

@bet.command(name="refund")
async def bet_refund(ctx):
    global active_bet

    if ctx.author.id != BET_ADMIN_ID:
        await ctx.send("⛔ Mày không có quyền refund kèo.")
        return

    if not active_bet or active_bet["ended"]:
        await ctx.send("❌ Không có kèo nào để refund.")
        return

    refunded_users = {}
    total_refund = 0

    for opt in active_bet["options"].values():
        for user_id, amount in opt["bets"].items():
            refunded_users[user_id] = refunded_users.get(user_id, 0) + amount
            total_refund += amount

    if not refunded_users:
        await ctx.send("⚠️ Kèo chưa có ai bet → không cần refund.")
        active_bet = None
        return

    # Hoàn tiền
    msg = "🔄 **REFUND KÈO BET** 🔄\n\n"
    for uid, amt in refunded_users.items():
        member = ctx.guild.get_member(uid)
        if not member:
            continue
        change_credit(member, amt, "Refund bet")
        msg += f"💸 **{member.display_name}** được hoàn `{amt}` SC\n"

    msg += f"\n💰 **Tổng hoàn:** `{total_refund}` SC"
    msg += "\n🧹 Kèo đã bị hủy & reset."

    await ctx.send(msg)

    # ❌ Reset kèo
    active_bet = None


@bet.command(name="info")
async def bet_info(ctx):
    global active_bet

    if not active_bet:
        await ctx.send("❌ Hiện không có kèo nào.")
        return

    #status = "🟢 ĐANG MỞ" if active_bet["open"] else "🛑 ĐÃ DỪNG"
    status = "🔓 Đang mở bet" if active_bet["open"] else "🔒 Đã khóa bet"
    if active_bet["ended"]:
        status = "🏁 Đã kết thúc"
    msg = (
        f"🎲 **THÔNG TIN KÈO BET** 🎲\n"
        f"📌 **Kèo:** {active_bet['title']}\n"
        f"📊 **Trạng thái:** {status}\n"
        f"💰 **Tổng pool:** `{active_bet['total_pool']}` SC\n\n"
        f"📋 **LỰA CHỌN:**\n"
    )

    for i, opt in active_bet["options"].items():
        msg += (
            f"`{i}`️⃣ **{opt['text']}**\n"
            f"   └ 💸 Tổng bet: `{opt['total']}` SC\n"
            f"   └ 👥 Người chơi: `{len(opt['bets'])}`\n"
        )

    await ctx.send(msg)


@bet.command(name="stop")
async def bet_stop(ctx):
    global active_bet

    if ctx.author.id != BET_ADMIN_ID:
        await ctx.send("⛔ Mày không có quyền stop kèo.")
        return

    if not active_bet:
        await ctx.send("❌ Không có kèo nào.")
        return

    if not active_bet["open"]:
        await ctx.send("⚠️ Kèo đã bị stop rồi.")
        return

    active_bet["open"] = False

    await ctx.send(
        "🛑 **KÈO ĐÃ BỊ DỪNG**\n"
        "❌ Không thể `!bet join` nữa\n"
        "⏳ Chờ `!bet end` để chốt kết quả"
    )


@bet.command(name="end")
async def bet_end(ctx, winning_option: int):
    global active_bet

    if ctx.author.id != BET_ADMIN_ID:
        await ctx.send("⛔ Mày không có quyền chốt kèo.")
        return

    if not active_bet or not active_bet["ended"]:
        await ctx.send("❌ Không có kèo đang mở.")
        return

    if winning_option not in active_bet["options"]:
        await ctx.send("❌ Lựa chọn thắng không tồn tại.")
        return
    active_bet["ended"] = True
    #active_bet["open"] = False

    win_opt = active_bet["options"][winning_option]
    total_win = win_opt["total"]
    pool = active_bet["total_pool"]

    msg = f"🏁 **KẾT QUẢ BET** 🏁\n"
    msg += f"🎯 Kèo: {active_bet['title']}\n"
    msg += f"🏆 Kết quả: **{win_opt['text']}**\n\n"

    if total_win == 0:
        msg += "💀 Không ai bet cửa thắng."
        await ctx.send(msg)
        active_bet = None
        return

    WIN_RATE = 1.0

    for uid, bet_amt in win_opt["bets"].items():
        user = ctx.guild.get_member(uid)
        win_amount = int(bet_amt * WIN_RATE)
        change_credit(user, win_amount, "Bet thắng x1.5")
        msg += f"🎉 **{user.display_name}** thắng `{win_amount}` SC (x1.5)\n"


    await ctx.send(msg)
    active_bet = None


# ====================================================
@bot.event
async def on_ready():
    print(f"Bot đã online: {bot.user}")
    #auto_keep_awake.start()

    # Đảm bảo task 7h sáng chạy đúng giờ dù bot khởi động lúc nào
    daily_check_circle.start()

    print("Bot đã sẵn sàng! Task 7h sáng đã được kích hoạt.")

@bot.command(name="registerDB")
async def register_db(ctx):
    user = ctx.author

    existing = get_user(user.id)
    if existing:
        await ctx.send(
            f"⚠️ **{user.display_name}** đã có trong cơ sở dữ liệu rồi!\n"
            f"💳 Social Credit hiện tại: **{existing['social_credit']}**"
        )
        return

    credit = create_user(user)

    await ctx.send(
        f"✅ **Đăng ký thành công!**\n"
        f"👤 Người dùng: **{user.display_name}**\n"
        f"💳 Social Credit ban đầu: **{credit}**"
    )

@bot.command(name="credit", aliases=["sc"])
async def social_credit(ctx):
    user = ctx.author
    data = get_user(user.id)

    if not data:
        await ctx.send("❌ Bạn chưa đăng ký. Dùng `!registerDB` trước.")
        return

    await ctx.send(
        f"💳 **Social Credit của {user.display_name}:** `{data['social_credit']}`"
    )

@bot.command(name="supremacy")
async def supremacy(ctx):
    file_path = "daiwaifu.gif"  # File nằm cùng thư mục
    
    try:
        with open(file_path, "rb") as f:
            gif_file = discord.File(f, filename="supremacy.gif")
            await ctx.send("**DAISCA SUPREMACY**", file=gif_file)
    except FileNotFoundError:
        await ctx.send("❌ GIF supremacy.gif chưa có trong repo! Hãy commit và redeploy.")
    except Exception as e:
        await ctx.send(f"Lỗi: {e}")

@tasks.loop(time=time(7, 0, tzinfo=timezone(timedelta(hours=7))))
async def daily_check_circle():
    channel = bot.get_channel(CHANNEL_ID_TO_SEND)
    if not channel:
        print("[7h sáng] Không tìm thấy kênh tự động!")
        return
    await channel.send(
        "Đang tự động kiểm tra + lưu KPI Circle lúc **7h sáng**...")
    # Lưu KPI hôm qua trước
    #await save_yesterday_kpi_for_circle(CIRCLE_ID_TO_CHECK)
    # Sau đó gửi báo cáo chích điện
    await run_check_and_send(CIRCLE_ID_TO_CHECK, channel)
    print(
        f"[7h sáng] Đã gửi báo cáo tự động thành công – {datetime.now(timezone(timedelta(hours=7))).strftime('%d/%m/%Y %H:%M')}"
    )
    await check_kpi_day_week_month(CIRCLE_ID_TO_CHECK, channel)


# Hàm chung để xử lý check circle (dùng cho cả lệnh thủ công và tự động)
async def run_check_and_send(circle_id: int, destination):
    try:
        HEADERS = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }

        response = requests.get(
            API_URL.format(circle_id),
            headers=HEADERS,
            timeout=15
        )
        if response.status_code != 200:
            await destination.send(f"Lỗi API: {response.status_code}")
            return
        data = response.json()
        if not data or "circle" not in data or not data.get("members"):
            await destination.send("Không tìm thấy dữ liệu circle.")
            return
        circle = data["circle"]
        members = data["members"]
        # Lấy thời gian cập nhật của circle (10 ký tự đầu: YYYY-MM-DD)
        circle_updated_str = circle["last_updated"]
        circle_date_prefix = circle_updated_str[:10]  # ví dụ: "2025-12-11"
        # Lấy ngày hôm nay từ circle (đã chuẩn)
        circle_updated_dt = datetime.fromisoformat(
            circle_updated_str.replace("Z", "+00:00"))
        today = circle_updated_dt.date()
        yesterday = today - timedelta(days=1)
        print(
            f"[DEBUG] Circle date prefix: {circle_date_prefix}, today: {today}, yesterday: {yesterday}"
        )
        # Gọi lưu KPI hôm qua trước (giữ nguyên logic cũ)
        #await save_yesterday_kpi_for_circle(circle_id)
        results = []
        skipped_count = 0
        for mem in members:
            name = mem.get("trainer_name", "Unknown").strip()
            if not name:
                continue
            updated_str = mem.get("last_updated", "")
            if not updated_str:
                print(f"[DEBUG] Skip {name}: no last_updated")
                continue
            # SỬA: LẤY NHỮNG THÀNH VIÊN CÓ CÙNG NGÀY CẬP NHẬT VỚI CIRCLE HOẶC HÔM QUA (LINH HOẠT HƠN)
            mem_date_prefix = updated_str[:10]
            if mem_date_prefix not in (circle_date_prefix,
                                       yesterday.strftime("%Y-%m-%d")):
                print(
                    f"[DEBUG] Skip {name}: prefix '{mem_date_prefix}' != '{circle_date_prefix}' or yesterday"
                )
                skipped_count += 1
                continue  # Bỏ qua nếu không cùng ngày hoặc hôm qua
            daily = mem.get("daily_fans", [])
            if len(daily) < today.day:  # Chưa đủ dữ liệu đến hôm nay
                print(
                    f"[DEBUG] Skip {name}: daily_fans len {len(daily)} < {today.day}"
                )
                continue
            # SỬA: Tính index dựa trên ngày của member (chính xác hơn)
            try:
                updated_dt = datetime.fromisoformat(
                    updated_str.replace("Z", "+00:00"))
                mem_date = updated_dt.date()
                idx_today = mem_date.day - 1  # index của ngày cập nhật (0-based)
                idx_yesterday = idx_today - 1  # index của hôm trước
                if idx_today >= len(daily) or idx_yesterday < 0:
                    print(
                        f"[DEBUG] Skip {name}: invalid index {idx_today}/{idx_yesterday} for len {len(daily)}"
                    )
                    continue
                fans_today = daily[idx_today]
                fans_yesterday = daily[
                    idx_yesterday] if idx_yesterday >= 0 else 0
                diff = fans_today - fans_yesterday
                print(
                    f"[DEBUG] {name}: diff = {diff:,} (today {fans_today:,} - yest {fans_yesterday:,})"
                )
            except Exception as e:
                print(f"[DEBUG] Skip {name}: parse date error {e}")
                continue
            signal = "✅" if diff >= 999_000 else "⚡"
            status = f"đã thoát được hôm nay với `{diff:,}` fans" if diff >= 999_000 else f"Chỉ cày được `{diff:,}` fans nên sẽ bị chích điện"
            results.append({
                "signal": signal,
                "name": name,
                "diff": diff,
                "status": status
            })
        print(
            f"[DEBUG] Total results: {len(results)}, skipped: {skipped_count}/{len(members)}"
        )
        if not results:
            await destination.send(
                f"Không có thành viên nào được cập nhật hôm nay hoặc dữ liệu chưa đầy đủ. (Debug: {skipped_count}/{len(members)} skipped do date mismatch)"
            )
            return
        # Sắp xếp theo số fan kiếm được giảm dần
        results.sort(key=lambda x: x["diff"], reverse=True)
        msg = f"**Club {circle['name']} ({circle_id})**\n"
        msg += f"**Báo cáo KPI ngày {yesterday.day}/{yesterday.month} → {today.day}/{today.month}** (**KPI**: 1_000_000 fans)\n\n"
        for i, r in enumerate(results, 1):
            msg += f"`{i:2}.` **{r['signal']} {r['name']}**: {r['status']}\n"
        # Chia nhỏ tin nhắn nếu quá dài
        if len(msg) > 1950:
            for part in [msg[i:i + 1950] for i in range(0, len(msg), 1950)]:
                await destination.send(part)
        else:
            await destination.send(msg)
    except Exception as e:
        await destination.send(f"Lỗi nghiêm trọng: {e}")
        print(f"[run_check_and_send] Exception: {e}")


# LỆNH THỦ CÔNG: !cc hoặc !circle (có thể bỏ trống ID → dùng ID mặc định)
@bot.command(name="checkcircle", aliases=["cc", "circle"])
async def checkcircle(ctx, circle_id: int = None):
    if circle_id is None:
        circle_id = CIRCLE_ID_TO_CHECK  # Dùng circle chính nếu không nhập ID
    await ctx.send(f"Đang kiểm tra Circle `{circle_id}`...")
    await run_check_and_send(circle_id, ctx)  # Dùng lại hàm chung

@bot.command(name="kpiChichDien", aliases=["checkkpi"])
async def kpi(ctx):
    await ctx.send("⏳ **Đang kiểm tra KPI (thủ công)...**")
    await check_kpi_day_week_month_manual(CIRCLE_ID_TO_CHECK, ctx.channel)

async def check_kpi_day_week_month(circle_id: int, channel):
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    response = requests.get(API_URL.format(circle_id), HEADERS, timeout=15)
    if response.status_code != 200:
        await channel.send(f"❌ KPI API lỗi: {response.status_code}")
        return

    data = response.json()
    circle = data["circle"]
    members = data["members"]

    circle_updated_dt = datetime.fromisoformat(
        circle["last_updated"].replace("Z", "+00:00")
    )
    today = circle_updated_dt.date()
    day_index = today.day - 1  # index hôm nay (0-based)

    report_day = []
    report_week = []
    report_month = []

    for mem in members:
        name = mem.get("trainer_name", "Unknown")
        daily = mem.get("daily_fans", [])

        if len(daily) <= day_index:
            continue

        # ===== KPI NGÀY =====
        today_fan = daily[day_index]
        yesterday_fan = daily[day_index - 1] if day_index > 0 else 0
        diff_day = today_fan - yesterday_fan

        report_day.append(
            f"{'✅' if diff_day >= 1_000_000 else '⚡'} **{name}**: `{diff_day:,}`"
        )

        # ===== KPI TUẦN (chủ nhật) =====
        if today.weekday() == 6 and day_index >= 6:
            week_fans = daily[day_index] - daily[day_index - 6]
            report_week.append(
                f"{'✅' if week_fans >= 6_000_000 else '⚡'} **{name}**: `{week_fans:,}`"
            )

        # ===== KPI THÁNG (ngày cuối tháng) =====
        next_day = today + timedelta(days=1)
        if next_day.month != today.month:
            month_fans = daily[day_index] - daily[0]
            report_month.append(
                f"{'✅' if month_fans >= 30_000_000 else '⚡'} **{name}**: `{month_fans:,}`"
            )

    # ===== GỬI BÁO CÁO =====
    #if report_day:
    #    await channel.send(
    #        f"📊 **KPI NGÀY ({today.strftime('%d/%m')}) – 1M fan/người**\n"
    #        + "\n".join(report_day)
    #    )

    if report_week:
        await channel.send(
            f"📍 **KPI TUẦN – 6M fan/người**\n"
            + "\n".join(report_week)
        )

    if report_month:
        await channel.send(
            f"📍 **KPI THÁNG ({today.month}) – 30M fan/người**\n"
            + "\n".join(report_month)
        )

async def check_kpi_day_week_month_manual(circle_id: int, channel):
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    response = requests.get(API_URL.format(circle_id), HEADERS, timeout=15)
    if response.status_code != 200:
        await channel.send(f"❌ KPI API lỗi: {response.status_code}")
        return

    data = response.json()
    circle = data["circle"]
    members = data["members"]

    circle_updated_dt = datetime.fromisoformat(
        circle["last_updated"].replace("Z", "+00:00")
    )
    today = circle_updated_dt.date()
    today_index = today.day - 1

    # ================== TÍNH CHỦ NHẬT GẦN NHẤT ==================
    days_since_sunday = (today.weekday() + 1) % 7
    last_sunday = today - timedelta(days=days_since_sunday)
    sunday_index = last_sunday.day - 1

    report_day = []
    report_week = []
    report_month = []

    for mem in members:
        name = mem.get("trainer_name", "Unknown")
        daily = mem.get("daily_fans", [])

        if len(daily) <= today_index:
            continue

        # ===== KPI NGÀY =====
        today_fan = daily[today_index]
        yesterday_fan = daily[today_index - 1] if today_index > 0 else 0
        diff_day = today_fan - yesterday_fan

        report_day.append(
            f"{'✅' if diff_day >= 1_000_000 else '⚡'} **{name}**: `{diff_day:,}`"
        )

        # ===== KPI TUẦN (CHỦ NHẬT GẦN NHẤT) =====
        if sunday_index >= 6 and len(daily) > sunday_index:
            week_fans = daily[sunday_index] - daily[sunday_index - 6]
            report_week.append(
                f"{'✅' if week_fans >= 6_000_000 else '⚡'} **{name}**: `{week_fans:,}`"
            )

        # ===== KPI THÁNG (GIỮ NGUYÊN) =====
        next_day = today + timedelta(days=1)
        if next_day.month != today.month:
            month_fans = daily[today_index] - daily[0]
            report_month.append(
                f"{'✅' if month_fans >= 30_000_000 else '⚡'} **{name}**: `{month_fans:,}`"
            )

    # ================== GỬI BÁO CÁO ==================
    #await channel.send(
    #    f"📊 **KPI NGÀY ({today.strftime('%d/%m')}) – 1M fan/người**\n"
    #    + "\n".join(report_day)
    #)

    if report_week:
        await channel.send(
            f"📍 **KPI TUẦN (chủ nhật gần nhất: {last_sunday.strftime('%d/%m')}) – 6M fan/người**\n"
            + "\n".join(report_week)
        )
    else:
        await channel.send("⚠️ Không đủ dữ liệu để check KPI tuần gần nhất.")

    if report_month:
        await channel.send(
            f"📍 **KPI THÁNG ({today.month}) – 30M fan/người**\n"
            + "\n".join(report_month)
        )



# ================== HELP SIÊU LẦY LỘI (ĐÃ CẬP NHẬT) ==================
@bot.command(name="help", aliases=["h", "commands", "lenh"])
async def custom_help(ctx):
    embed = discord.Embed(
        title="⚡ Bot Chích Điện – Danh sách lệnh (khi bot tỉnh)",
        description="Bot này hơi ngu hay ngủ gật, thông cảm nha 😴\nDưới đây là tất cả lệnh tao biết làm:",
        color=0xFF6B6B
    )

    embed.add_field(
        name="📋 **Lệnh cơ bản**",
        value=(
            "`!help` | `!h` | `!commands` | `!lenh`\n"
            "→ Xem cái danh sách này (đang xem nè)\n\n"
            "`!supremacy`\n"
            "→ **DAISCA SUPREMACY** – Thả GIF Daiwa Scarlet cực chất 🏆"
        ),
        inline=False
    )

# ===== DATABASE / CREDIT =====
    embed.add_field(
        name="💳 **Social Credit (Database)**",
        value=(
            "`!registerDB`\n"
            "→ Đăng ký vào hệ thống (chỉ cần 1 lần)\n\n"
            "`!credit` | `!sc`\n"
            "→ Xem Social Credit hiện tại\n\n"
            "📌 Credit bị trừ / cộng khi:\n"
            "• Bị detect gay\n"
            "• Chơi game thắng / thua\n"
            "• Một số hành vi đặc biệt khác"
        ),
        inline=False
    )

    embed.add_field(
        name="🎮 **Game vui vui**",
        value=(
            "`!ott_emoji`\n"
            "→ Chơi oẳn tù tì nhanh với bot (chỉ 1 lượt)\n\n"
            "`!rps`\n"
            "→ Chơi oẳn tù tì full luật phức tạp (thắng 3 điểm, có phạt, phá luật...)\n\n"
            "`!rpsrule` | `!rpsrules`\n"
            "→ Xem luật chi tiết của !rps (đọc trước khi chơi kẻo thua khóc)"
        ),
        inline=False
    )

    embed.add_field(
        name="🌸 **Lệnh cầu xin**",
        value=(
            "`!beg` | `!xin` | `!cầu` + <số ngày>\n"
            "→ Cầu xin đền thờ cho Daisca :>\n"
            "Ví dụ: `!beg 69` (có ngày đẹp sẽ được bonus đặc biệt)"
        ),
        inline=False
    )

    embed.add_field(
        name="⚡ **Lệnh KPI & Chích điện**",
        value=(
            "`!cc` | `!circle` | `!checkcircle` [circle_id]\n"
            "→ Báo cáo KPI hôm qua, xem ai đủ 1M fans, ai bị chích điện ⚡\n"
            "(Không nhập ID → check circle chính)\n\n"
            "`!kpiChichDien` [circle_id]\n"
            "→ Check ai lười quá trời, sắp bị cảnh cáo thật (không đủ 500k nhiều ngày)"
        ),
        inline=False
    )

    embed.add_field(
        name="🤫 **Tính năng tự động (không cần lệnh)**",
        value=(
            "• Gõ từ khóa **gay, đồng tính, bê đê, lgbt...** → Bot detect và phạt -2000 điểm tấn công 💀\n"
            "• User đặc biệt (đã set ID) gửi tin nhắn → Bot tự reply **NÍN**\n"
            "• Mỗi **7h sáng** → Bot tự động check KPI và báo cáo ở kênh chỉ định"
        ),
        inline=False
    )

    embed.set_footer(text="Thức tỉnh mà nghiện Uma đi, không thì bị giật điện thật đấy!!! ⚡")
    embed.set_thumbnail(url="https://i.ibb.co/LDZ91gVV/lightning-icon.png")  # Thay link thumbnail nếu muốn

    await ctx.send(embed=embed)


# Nếu bạn đang dùng help_command=None thì giữ nguyên, cái này sẽ đè lên hoàn toàn
# Nếu chưa có dòng này thì thêm vào đầu file cùng chỗ help_command=None:
# bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
@bot.command(name="beg", aliases=["xin", "cầu", "begbeg"])
async def beg_command(ctx, day: int = None):
    if day is None:
        await ctx.send(
            "Mày quên điền ngày rồi con điên à? Dùng: `!beg 69` ví dụ")
        return
    if day < 1:
        await ctx.send("Ngày gì âm lịch vậy con chó? Đưa số dương đi!")
        return
    if day > 1000:
        await ctx.send(f"Day {day}? Mày định beg tới kiếp sau hả trời ơi ")
        return
    # Tin nhắn chính thức siêu cute
    await ctx.send(f"Day **{day}** asking for Daisca's Shrine :> ")
    # Bonus: nếu là ngày đẹp thì thả tim thêm
    if day in [69, 100, 200, 300, 420, 500, 696, 777, 999]:
        await ctx.message.add_reaction("")

@bot.command(name="ott_emoji")
async def ott_emoji(ctx):
    choices = ["✊", "✋", "✌️"]
    bot_choice = random.choice(choices)

    msg = await ctx.send("🎮 **OẲN TÙ TÌ**\nRa tay đi: ✊ ✋ ✌️")

    # Bot thả reaction
    for e in choices:
        await msg.add_reaction(e)

    def check(reaction, user):
        return (
            user == ctx.author and                 # đúng người chơi
            str(reaction.emoji) in choices and     # đúng emoji
            reaction.message.id == msg.id          # đúng message
        )

    try:
        # CHỈ NHẬN 1 reaction đầu tiên
        reaction, user = await bot.wait_for(
            "reaction_add",
            timeout=10.0,
            check=check
        )
    except asyncio.TimeoutError:
        #await msg.clear_reactions()
        await ctx.send("⏱️ Hết giờ! Tay run quá à?")
        return

    user_choice = str(reaction.emoji)

    win_map = {
        "✊": "✌️",
        "✋": "✊",
        "✌️": "✋"
    }

    if user_choice == bot_choice:
        result = "🤝 **HOÀ**"
    elif win_map[user_choice] == bot_choice:
        result = "🎉 **MÀY THẮNG**"
    else:
        result = "💀 **MÀY THUA**"

    #await msg.clear_reactions()

    await ctx.send(
        f"👤 Mày: {user_choice}\n"
        f"🤖 Bot: {bot_choice}\n\n"
        f"{result}"
    )

    if "THẮNG" in result:
        msg = change_credit(ctx.author, +5, "OTT win")
    elif "THUA" in result:
        msg = change_credit(ctx.author, -3, "OTT lose")
    else:
        msg = change_credit(ctx.author, +1, "OTT draw")

    await ctx.send(msg)

import random
import asyncio

@bot.command(name="rps")
async def rps(ctx):
    import random, asyncio

    # ========== KHÓA GAME ==========
    if getattr(bot, "rps_playing", False):
        await ctx.send("⛔ Đang có người chơi khác!")
        return
    bot.rps_playing = True

    # ========== CẤU HÌNH ==========
    EMOJIS = ["✌️", "✊", "✋"]
    PENALTY_ORDER = ["✌️", "✊", "✋"]

    def win(u, b):
        return (u == "✌️" and b == "✋") or \
               (u == "✊" and b == "✌️") or \
               (u == "✋" and b == "✊")

    # ========== TRẠNG THÁI ==========
    score_user = 0
    score_bot = 0
    round_count = 1

    penalty_target = None
    penalty_index = 0

    break_user_available = True
    break_bot_available = True

    first_penalty_decided = False   # ⭐ QUAN TRỌNG

    last_messages = []

    async def clear_round():
        for m in last_messages:
            try:
                await m.delete()
            except:
                pass
        last_messages.clear()

    await ctx.send("🎮 **BẮT ĐẦU OẲN TÙ TÌ – THẮNG 3 ĐIỂM**")

    # ========== GAME LOOP ==========
    while score_user < 3 and score_bot < 3:
        await clear_round()

        forced_user = forced_bot = None
        info = [
            f"🎮 **LƯỢT {round_count}**",
            f"👤 Bạn: {score_user} | 🤖 Bot: {score_bot}"
        ]

        if penalty_target == "user":
            forced_user = PENALTY_ORDER[penalty_index]
            info += ["⚠️ **BẠN ĐANG BỊ PHẠT**", f"👉 Bắt buộc ra: {forced_user}"]

        if penalty_target == "bot":
            forced_bot = PENALTY_ORDER[penalty_index]
            info += ["⚠️ **BOT ĐANG BỊ PHẠT**", f"👉 Bot phải ra: {forced_bot}"]

        info.append(f"🔓 Quyền phá luật bạn: {'✅' if break_user_available else '❌'}")
        info.append(f"🔓 Quyền phá luật bot: {'✅' if break_bot_available else '❌'}")

        msg = await ctx.send("\n".join(info))
        last_messages.append(msg)

        available = (
            [forced_user] if penalty_target == "user" and not break_user_available
            else EMOJIS
        )

        for e in available:
            await msg.add_reaction(e)

        def check(reaction, user):
            return user == ctx.author and reaction.message.id == msg.id and str(reaction.emoji) in available

        try:
            reaction, _ = await bot.wait_for("reaction_add", timeout=30, check=check)
        except asyncio.TimeoutError:
            await ctx.send("⌛ Hết thời gian!")
            bot.rps_playing = False
            return

        user_choice = str(reaction.emoji)

        # ---------- BOT ----------
        if penalty_target == "bot":
            if break_bot_available:
                bot_choice = random.choice(EMOJIS)
                if bot_choice != forced_bot:
                    break_bot_available = False
            else:
                bot_choice = forced_bot
        else:
            bot_choice = random.choice(EMOJIS)

        last_messages.append(await ctx.send(f"🤖 Bot ra: {bot_choice}"))

        # ---------- KẾT QUẢ ----------
        if user_choice == bot_choice:
            result = "draw"
            last_messages.append(await ctx.send("😐 **HÒA**"))
        elif win(user_choice, bot_choice):
            result = "user_win"
            last_messages.append(await ctx.send("🎉 **BẠN THẮNG**"))
        else:
            result = "bot_win"
            last_messages.append(await ctx.send("💀 **BẠN THUA**"))

        # ========== XỬ LÝ LUẬT ==========
        if not first_penalty_decided:
            if result == "user_win":
                penalty_target = "bot"
                penalty_index = 0
                first_penalty_decided = True
            elif result == "bot_win":
                penalty_target = "user"
                penalty_index = 0
                first_penalty_decided = True

        else:
            if penalty_target:
                punished = penalty_target

                if (punished == "user" and result == "user_win") or \
                   (punished == "bot" and result == "bot_win"):
                    if punished == "user":
                        score_user += 1
                        penalty_target = "bot"
                    else:
                        score_bot += 1
                        penalty_target = "user"
                    penalty_index = 0

                elif (punished == "user" and result == "bot_win") or \
                     (punished == "bot" and result == "user_win"):
                    if punished == "user" and not break_user_available:
                        penalty_index = 0
                    elif punished == "bot" and not break_bot_available:
                        penalty_index = 0
                    else:
                        penalty_index += 1

                if penalty_index >= 3:
                    penalty_index = 0
                    penalty_target = "bot" if punished == "user" else "user"

            else:
                if result == "user_win":
                    score_user += 1
                    penalty_target = "bot"
                elif result == "bot_win":
                    score_bot += 1
                    penalty_target = "user"
                penalty_index = 0

        round_count += 1
        await asyncio.sleep(1)

    await clear_round()
    await ctx.send(
        f"🏁 **KẾT THÚC GAME**\n"
        f"👤 {score_user} | 🤖 {score_bot}\n"
        f"{'🎉 BẠN THẮNG!' if score_user > score_bot else '🤖 BOT THẮNG!'}"
    )
    if score_user > score_bot:
        msg = change_credit(ctx.author, +20, "RPS victory")
    else:
        msg = change_credit(ctx.author, -15, "RPS defeat")

    await ctx.send(msg)

    bot.rps_playing = False

@bot.command(name="rpsrule", aliases=["rpsrules", "rps_rule", "rps_rules"])
async def rps_rule(ctx):
    msg = (
        "📜 **LUẬT OẲN TÙ TÌ – BẢN DỄ HIỂU**\n\n"

        "🎯 **MỤC TIÊU**\n"
        "- Ai đạt **3 điểm trước** là thắng ván chơi.\n\n"

        "🔰 **LƯỢT ĐẦU TIÊN**\n"
        "- Chơi bình thường cho đến khi có người thắng.\n"
        "- ❌ **KHÔNG tính điểm** ở lượt này.\n"
        "- 👉 Chỉ dùng để xác định **AI BỊ PHẠT**.\n\n"

        "⚠️ **HÌNH PHẠT (QUAN TRỌNG)**\n"
        "- Người bị phạt **BẮT BUỘC** phải ra theo thứ tự:\n"
        "  **✌️ Kéo → ✊ Búa → ✋ Bao** (3 lượt liên tiếp).\n\n"

        "🔓 **QUYỀN PHÁ LUẬT (MỖI NGƯỜI 1 LẦN / 1 VÁN)**\n"
        "- Mỗi người (bạn & bot) có **1 lần duy nhất** được ra khác thứ tự hình phạt.\n"
        "- Dùng rồi là **MẤT QUYỀN**.\n\n"

        "💥 **NẾU ĐANG BỊ PHẠT**\n"
        "- ❌ Thua → hình phạt **BẮT ĐẦU LẠI** từ ✌️ Kéo.\n"
        "- ⚠️ Nếu dùng quyền phá luật mà **VẪN THUA** → hình phạt cũng reset.\n"
        "- ⭕ Hòa → không tính gì, vẫn tiếp tục hình phạt.\n\n"

        "🎉 **THẮNG TRONG KHI BỊ PHẠT**\n"
        "- ✔️ Được **+1 điểm**.\n"
        "- ✔️ **CHUYỂN HÌNH PHẠT** sang đối phương.\n\n"

        "🔁 **HOÀN THÀNH HÌNH PHẠT (3 LƯỢT)**\n"
        "- Nếu hết 3 lượt mà **CHƯA THUA**:\n"
        "  👉 Hình phạt **CHUYỂN SANG ĐỐI PHƯƠNG**.\n\n"

        "😐 **HÒA**\n"
        "- Không ai được điểm.\n"
        "- Không đổi hình phạt.\n\n"

        "🏆 **CHIẾN THẮNG CUỐI CÙNG**\n"
        "- Ai đạt **3 điểm trước** → **THẮNG GAME** 🎉\n\n"

    )

    await ctx.send(msg)


from flask import Flask
import os
import threading
# Tạo Flask app giả để Render happy (chỉ cần endpoint /ping)
app = Flask(__name__)


@app.route('/ping', methods=['GET'])
def ping():
    return "Bot awake!", 200


# Chạy Flask trên port Render (env var PORT)
def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)


# Chạy Flask trong thread riêng, không block bot
if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    bot.run(os.getenv('DISCORD_TOKEN'))