import discord
from discord.ext import commands, tasks
import requests
from datetime import datetime, timezone, timedelta, time
from threading import Thread
import asyncio
import random
import json  # <--- THÊM DÒNG NÀY
import io    # <--- THÊM DÒNG NÀY
import re
import os
import aiohttp
from config import *
from database import *
from rob_system import RobSystem
from bet_system import BetSystem
from shop_system import ShopSystem

# ================== CẤU HÌNH CỦA BẠN ==================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

last_message_time = {}  # {user_id: datetime}

LEFT_REGEX = re.compile(r"User\s+<?@?(\d+)>?\s+left", re.IGNORECASE)
ID_REGEX = re.compile(r"\b(\d{17,20})\b")

saved_cm_message = None

def remove_mentions(text: str) -> str:
    # User mention <@123> hoặc <@!123>
    text = re.sub(r'<@!?\d+>', '', text)

    # Role mention <@&123>
    text = re.sub(r'<@&\d+>', '', text)

    # Channel mention <#123>
    text = re.sub(r'<#\d+>', '', text)

    return text

spouse_interaction_cooldown = {} 

@bot.event
async def on_message(message):

    # ================= WELCOME LOG CHANNEL =================
    if message.channel.id == WELCOME_LOG_CHANNEL_ID:
        # Bỏ qua nếu là bot của mình
        if message.author.id == bot.user.id:
            return

        # Chỉ xử lý nếu là bot khác
        if message.author.bot:

            # Nếu bot có mention user
            if message.mentions:
                for member in message.mentions:
                    await message.channel.send(
                        f"🎉 WELCUM {member.mention} đến **STRATEGIST**.\n"
                        f"Hãy gõ `!registerDB` để đăng kí tài khoản bắt đầu tại đây :>"
                    )

            return

    # ================= CHECK BOT LOG CHANNEL =================
    if message.channel.id == LEAVE_LOG_CHANNEL_ID or message.channel.id == LEAVE_LOG_CHANNEL_ID_2 or message.channel.id == LEAVE_LOG_CHANNEL_ID_3:

        # ❌ Nếu là bot mình thì bỏ
        if message.author.id == bot.user.id:
            return

        # Chỉ xử lý nếu là bot KHÁC
        if message.author.bot and message.author.id != bot.user.id:

            match = ID_REGEX.search(message.content)
            if match:
                user_id = int(match.group(1))

                try:
                    user = await bot.fetch_user(user_id)
                except:
                    await message.channel.send(f"❌ Không fetch được user `{user_id}`")
                    return

                embed = discord.Embed(
                    title="🔍 USER PROFILE DETECTED",
                    color=0x2f3136,
                    timestamp=datetime.now(timezone.utc)
                )

                embed.add_field(name="👤 Username", value=f"{user}", inline=False)
                embed.add_field(name="🆔 User ID", value=user.id, inline=False)
                embed.add_field(name="🤖 Bot?", value=user.bot, inline=True)
                embed.add_field(name="📅 Account Created",
                                value=user.created_at.strftime("%d/%m/%Y %H:%M:%S"),
                                inline=True)

                embed.set_thumbnail(url=user.display_avatar.url)

                await message.channel.send(embed=embed)

    if message.author.bot: # Ngăn cho nó k bắt bot
        return

    await bot.process_commands(message)

# ====================================================
@bot.event
async def on_ready():
    print(f"Bot đã online: {bot.user}")

    # Đảm bảo task 7h sáng chạy đúng giờ dù bot khởi động lúc nào
    #daily_check_circle.start()

    await bot.add_cog(
        RobSystem(
            bot,
            users_col,
            rob_col,
            ensure_user,
            get_user,
            change_credit,
            SPOUSE_USER_ID
        )
    )
    print("Rob system loaded.")

    await bot.add_cog(
        BetSystem(
            bot,
            ensure_user,
            change_credit,
            BET_ADMIN_ID,
            BET_ADMIN_ID_2,
            SPOUSE_USER_ID
        )
    )
    print("Bet system loaded.")

    await bot.add_cog(ShopSystem(bot))
    print("Shop system loaded.")
    # Auto check fans
    #if not auto_cc_2230.is_running():
    auto_cc_2230.start()


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

@bot.command(name="grant")
async def grant_social_credit(ctx, target, amount: int, *, reason: str = "Special grant"):
    # 🔒 CHỈ SPOUSE ĐƯỢC DÙNG
    if ctx.author.id != SPOUSE_USER_ID:
        await ctx.send("⛔ Mày không có quyền dùng lệnh này.")
        return

    # ===== TRAO CHO TẤT CẢ =====
    if target.lower() == "all":
        users = list(users_col.find({}))
        affected = 0

        for user in users:
            user_id = user["user_id"]

            change_credit_by_id(user_id, amount, reason)
            affected += 1

        sign = "+" if amount > 0 else ""
        await ctx.send(
            f"👑 **SPOUSE COMMAND** 👑\n"
            f"🌍 Đã áp dụng `{sign}{amount}` Social Credit cho **{affected} user trong DB**\n"
            f"📝 Lý do: *{reason}*"
        )
        return

    # ===== TRAO CHO 1 NGƯỜI =====
    if not ctx.message.mentions:
        await ctx.send("❌ Phải tag người dùng hoặc dùng `all`.")
        return

    member = ctx.message.mentions[0]

    ensure_user(member)
    change_credit(member, amount, reason)

    sign = "+" if amount > 0 else ""
    await ctx.send(
        f"👑 **SPOUSE COMMAND** 👑\n"
        f"👤 **{member.display_name}** nhận `{sign}{amount}` Social Credit\n"
        f"📝 Lý do: *{reason}*"
    )

def get_random_user_from_db():
    users = list(users_col.find({}))
    if not users:
        return None
    return random.choice(users)

def transfer_credit(from_user, to_user, amount: int, reason: str):
    # Trừ người gửi
    change_credit(from_user, -amount, f"Transfer to {to_user.id}: {reason}")
    # Cộng người nhận
    change_credit(to_user, amount, f"Transfer from {from_user.id}: {reason}")

MAX_TRANSFER_AMOUNT = 500

@bot.command(name="pay", aliases=["transfer", "send"])
async def pay_social_credit(ctx, member: discord.Member, amount: int, *, reason: str = "User transfer"):
    sender = ctx.author
    receiver = member

    if sender.id == receiver.id:
        await ctx.send("❌ Tự chuyển cho chính mình là sao mày?")
        return

    if amount <= 0:
        await ctx.send("❌ Amount phải là số dương.")
        return

    if amount > MAX_TRANSFER_AMOUNT:
        await ctx.send(
            f"❌ Mỗi lần chỉ được chuyển tối đa `{MAX_TRANSFER_AMOUNT}` Social Credit."
        )
        return

    sender_data = ensure_user(sender)
    ensure_user(receiver)

    if sender_data["social_credit"] < amount:
        await ctx.send("❌ Mày không đủ Social Credit.")
        return

    transfer_credit(sender, receiver, amount, reason)

    await ctx.send(
        f"💸 **CHUYỂN SOCIAL CREDIT** 💸\n"
        f"👤 Người gửi: **{sender.display_name}**\n"
        f"🎯 Người nhận: **{receiver.display_name}**\n"
        f"💰 Số tiền: `{amount}` SC\n"
        f"📝 Lý do: *{reason}*"
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

@tasks.loop(time=time(22, 30, tzinfo=timezone(timedelta(hours=7))))
async def auto_cc_2230():
    print("Running auto cc 22:30...")

    channel1 = bot.get_channel(1445650304031785052)
    channel2 = bot.get_channel(1445419568238694400)

    if channel1:
        await channel1.send("📊 Auto check circle 716455843 (22:30)")
        await run_check_and_send(716455843, channel1)

    if channel2:
        await channel2.send("📊 Auto check circle 147613035 (22:30)")
        await run_check_and_send(147613035, channel2)

@tasks.loop(time=time(14, 45, tzinfo=timezone(timedelta(hours=7))))
async def auto_cc_1445():
    print("Running auto cc 22:30...")

    channel1 = bot.get_channel(1445650304031785052)
    channel2 = bot.get_channel(1445419568238694400)

    if channel1:
        await channel1.send("📊 Auto check circle 716455843 (22:30)")
        await run_check_and_send(716455843, channel1)

    if channel2:
        await channel2.send("📊 Auto check circle 147613035 (22:30)")
        await run_check_and_send(147613035, channel2)

# Hàm chung để xử lý check circle (dùng cho cả lệnh thủ công và tự động)
async def run_check_and_send(circle_id: int, destination, manual_data=None):

    manual_flag = ''
    try:
        data = None
        
        # NẾU CÓ DỮ LIỆU THỦ CÔNG THÌ DÙNG LUÔN, KHỎI GỌI API
        if manual_data:
            data = manual_data
            manual_flag = 'tay'
        else:
            manual_flag = 'api'
            # Logic cũ: Gọi API
            HEADERS = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(API_URL.format(circle_id), headers=HEADERS, timeout=15) as response:
                    if response.status != 200:
                        await destination.send(f"Lỗi API: {response.status}")
                        return
                    data = await response.json()
                    from database import save_circle_snapshot
                    save_circle_snapshot(circle_id, data)

        # --- BẮT ĐẦU XỬ LÝ DỮ LIỆU (PHẦN NÀY GIỮ NGUYÊN) ---
        if not data or "circle" not in data or not data.get("members"):
            await destination.send("Không tìm thấy dữ liệu circle.")
            return
            
        circle = data["circle"]
        members = data["members"]
        
        # Lấy thời gian cập nhật của circle
        circle_updated_str = circle["last_updated"]
        circle_date_prefix = circle_updated_str[:10] 
        circle_updated_dt = datetime.fromisoformat(circle_updated_str.replace("Z", "+00:00"))
        today = circle_updated_dt.date()
        yesterday = today - timedelta(days=1)
        
        print(f"[DEBUG] Processing date: {today}")

        results = []
        skipped_count = 0
        
        for mem in members:
            #name = mem.get("trainer_name", "Unknown").strip()
            # --- [QUAN TRỌNG] LOGIC LẤY TÊN ĐƯỢC SỬA LẠI TẠI ĐÂY ---
            raw_name = mem.get("trainer_name") # Ưu tiên lấy trainer_name
            
            # Nếu trainer_name không có hoặc là None, lấy "name"
            if not raw_name:
                raw_name = mem.get("name")
            
            # Nếu vẫn không có, đặt là Unknown
            if not raw_name:
                name = "Unknown"
            else:
                name = str(raw_name).strip() # Chuyển thành chuỗi và xóa khoảng trắng thừa

            if not name: continue
            
            updated_str = mem.get("last_updated", "")
            if not updated_str: continue

            # Check ngày update
            mem_date_prefix = updated_str[:10]
            if mem_date_prefix not in (circle_date_prefix, yesterday.strftime("%Y-%m-%d")):
                skipped_count += 1
                continue 

            daily = mem.get("daily_fans", [])
            if len(daily) < today.day:
                continue

            try:
                updated_dt = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                mem_date = updated_dt.date()
                idx_today = mem_date.day - 1 
                idx_yesterday = idx_today - 1
                
                if idx_today >= len(daily) or idx_yesterday < 0:
                    continue
                    
                fans_today = daily[idx_today]
                fans_yesterday = daily[idx_yesterday] if idx_yesterday >= 0 else 0
                diff = fans_today - fans_yesterday
            except Exception as e:
                print(f"[DEBUG] Skip {name}: parse error {e}")
                continue

            signal = "✅" if diff >= 999_000 else "⚡"
            status = f"đã thoát được hôm nay với `{diff:,}` fans" if diff >= 999_000 else f"Chỉ cày được `{diff:,}` fans nên sẽ bị chích điện"
            results.append({
                "signal": signal,
                "name": name,
                "diff": diff,
                "status": status
            })

        if not results:
            await destination.send(f"Không có dữ liệu hợp lệ để báo cáo hôm nay (Skipped: {skipped_count})")
            return

        results.sort(key=lambda x: x["diff"], reverse=True)
        msg = f"**Club {circle['name']} ({circle['circle_id']})**\n"
        msg += f"**Báo cáo KPI ngày {yesterday.day}/{yesterday.month} → {today.day}/{today.month}** (Check {manual_flag})\n\n"
        
        for i, r in enumerate(results, 1):
            msg += f"`{i:2}.` **{r['signal']} {r['name']}**: {r['status']}\n"
            
        if len(msg) > 1950:
            for part in [msg[i:i + 1950] for i in range(0, len(msg), 1950)]:
                await destination.send(part)
        else:
            await destination.send(msg)

    except Exception as e:
        await destination.send(f"Lỗi nghiêm trọng: {e}")
        print(f"[run_check_and_send] Exception: {e}")

# Biến này sẽ lưu nội dung file JSON gần nhất bạn gửi
last_manual_data = None

@bot.command(name="usejson")
async def use_json_data(ctx):
    global last_manual_data  # <--- Khai báo dùng biến toàn cục

    # Kiểm tra xem có file đính kèm không
    if not ctx.message.attachments:
        await ctx.send("❌ Vui lòng đính kèm file JSON vào lệnh này!")
        return

    attachment = ctx.message.attachments[0]
    
    if not attachment.filename.endswith('.json') and not attachment.filename.endswith('.txt'):
        await ctx.send("❌ File phải có đuôi .json hoặc .txt")
        return

    try:
        # Đọc nội dung file
        file_content = await attachment.read()
        json_data = json.loads(file_content)
        
        # --- LƯU VÀO BỘ NHỚ ---
        last_manual_data = json_data 
        
        await ctx.send(f"✅ Đã đọc và **lưu** dữ liệu từ file **{attachment.filename}**.")
        
        # Chạy báo cáo ngay lập tức
        #await run_check_and_send(CIRCLE_ID_TO_CHECK, ctx.channel, manual_data=json_data)
        #await check_kpi_day_week_month(CIRCLE_ID_TO_CHECK, ctx.channel, manual_data=json_data)

    except json.JSONDecodeError:
        await ctx.send("❌ Nội dung file không phải JSON hợp lệ.")
    except Exception as e:
        await ctx.send(f"❌ Lỗi khi xử lý: {e}")
        print(e)

@bot.command(name="cf")
async def check_from_cache(ctx):
    global last_manual_data # Lấy dữ liệu đã lưu

    if last_manual_data is None:
        await ctx.send("❌ Chưa có dữ liệu lưu trữ! Hãy dùng lệnh `!usejson` kèm file JSON trước một lần.")
        return

    await ctx.send("📂 **Sử dụng lại dữ liệu từ file JSON gần nhất...**")

    # Gọi hàm xử lý với dữ liệu cũ
    await run_check_and_send(CIRCLE_ID_TO_CHECK, ctx.channel, manual_data=last_manual_data)
    #await check_kpi_day_week_month(CIRCLE_ID_TO_CHECK, ctx.channel, manual_data=last_manual_data)
    
    await ctx.send("🏁 **Hoàn tất báo cáo (dữ liệu cũ).**")

# LỆNH THỦ CÔNG: !cc hoặc !circle (có thể bỏ trống ID → dùng ID mặc định)
@bot.command(name="checkcircle", aliases=["cc", "circle"])
async def checkcircle(ctx, circle_id: int = None):

    # Nếu có nhập ID → check 1 cái như cũ
    if circle_id:
        await ctx.send(f"Đang kiểm tra Circle `{circle_id}`...")
        await run_check_and_send(circle_id, ctx)
        return

    # Nếu KHÔNG nhập ID → check cả 2
    await ctx.send("📊 Đang kiểm tra cả 2 Club...")

    await run_check_and_send(716455843, ctx)
    await run_check_and_send(147613035, ctx)

def safe_segment_gain(daily, start_idx, end_idx):
    """
    Tính gain từ start_idx → end_idx.
    Nếu daily[end_idx] < daily[start_idx]
    thì lùi end_idx xuống cho tới khi >= start.
    """

    if end_idx >= len(daily):
        end_idx = len(daily) - 1

    start_value = daily[start_idx]

    for i in range(end_idx, start_idx, -1):
        if daily[i] >= start_value:
            return daily[i] - start_value

    return 0

@bot.command(name="weeklyfans", aliases=["wfans"])
async def weekly_fans(ctx, circle_id: int = None):

    if not circle_id:
        await ctx.send("❌ Dùng: `!weeklyfans <circle_id>`")
        return

    HEADERS = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }

    response = requests.get(API_URL.format(circle_id), headers=HEADERS, timeout=15)
    if response.status_code != 200:
        await ctx.send(f"❌ API lỗi: {response.status_code}")
        return

    data = response.json()

    if "members" not in data:
        await ctx.send("❌ Không có dữ liệu members.")
        return

    members = data["members"]
    circle_name = data["circle"]["name"]

    msg = f"📊 **Weekly Fans Breakdown – {circle_name} ({circle_id})**\n\n"

    for mem in members:
        name = mem.get("trainer_name") or mem.get("name") or "Unknown"
        daily = mem.get("daily_fans", [])

        if len(daily) < 2:
            continue

        last_index = len(daily) - 1

        seg1 = safe_segment_gain(daily, 0, 7) if last_index >= 1 else 0
        seg2 = safe_segment_gain(daily, 7, 14) if last_index >= 8 else 0
        seg3 = safe_segment_gain(daily, 14, 21) if last_index >= 16 else 0
        seg4 = safe_segment_gain(daily, 21, 28) if last_index >= 24 else 0

        full = safe_segment_gain(daily, 0, last_index)

        msg += (
            f"**{name}**\n"
            f"Tuần 1: `{seg1:,}`\n"
            f"Tuần 2: `{seg2:,}`\n"
            f"Tuần 3: `{seg3:,}`\n"         
            f"📈 Tổng tháng: `{full:,}`\n\n"
        )

    if len(msg) > 1900:
        for part in [msg[i:i + 1900] for i in range(0, len(msg), 1900)]:
            await ctx.send(part)
    else:
        await ctx.send(msg)


@bot.command(name="kpiChichDien", aliases=["checkkpi"])
async def kpi(ctx):
    await ctx.send("⏳ **Đang kiểm tra KPI (thủ công)...**")
    await check_kpi_day_week_month_manual(CIRCLE_ID_TO_CHECK, ctx.channel)

async def check_kpi_day_week_month(circle_id: int, channel, manual_data=None):
    data = None
    manual_flag = ''

    # Ưu tiên dùng dữ liệu thủ công
    if manual_data:
        manual_flag = 'tay'
        data = manual_data
    else:
        manual_flag = 'api'
        HEADERS = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }
        response = requests.get(API_URL.format(circle_id), HEADERS, timeout=15)
        if response.status_code != 200:
            await channel.send(f"❌ KPI API lỗi: {response.status_code}")
            return
        data = response.json()

    # --- PHẦN XỬ LÝ (GIỮ NGUYÊN) ---
    circle = data["circle"]
    members = data["members"]

    circle_updated_dt = datetime.fromisoformat(circle["last_updated"].replace("Z", "+00:00"))
    today = circle_updated_dt.date()
    day_index = today.day - 1 

    report_week = []
    report_month = []

    for mem in members:
        name = mem.get("trainer_name", "Unknown")
        daily = mem.get("daily_fans", [])

        if len(daily) <= day_index:
            continue

        # KPI TUẦN (chủ nhật)
        if today.weekday() == 6 and day_index >= 6:
            week_fans = daily[day_index] - daily[day_index - 6]
            report_week.append(f"{'✅' if week_fans >= 6_000_000 else '⚡'} **{name}**: `{week_fans:,}`")

        # KPI THÁNG (ngày cuối tháng)
        next_day = today + timedelta(days=1)
        if next_day.month != today.month:
            month_fans = daily[day_index] - daily[0]
            report_month.append(f"{'✅' if month_fans >= 30_000_000 else '⚡'} **{name}**: `{month_fans:,}`")

    if report_week:
        await channel.send(f"📍 **KPI TUẦN – 6M fan/người**\n" + "\n".join(report_week))

    if report_month:
        await channel.send(f"📍 **KPI THÁNG ({today.month}) – 30M fan/người**\n" + "\n".join(report_month))

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

@bot.command(name="ott_emoji")
async def ott_emoji(ctx):
    choices = ["✊", "✋", "✌️"]
    bot_choice = random.choice(choices)

    msg = await ctx.send("🎮 **OẲN TÙ TÌ**\nRa tay đi: ✊ ✋ ✌️")

    # Bot thả reaction
    for e in choices:
        await msg.add_reaction(e)
        await asyncio.sleep(0.3)

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

@bot.command(name="checkuser")
async def checkuser(ctx, user_input: str = None):

    if user_input is None and ctx.message.reference is None:
        await ctx.send("❌ Dùng: `!checkuser @user` hoặc `!checkuser user_id` hoặc reply tin nhắn")
        return

    user = None

    try:
        # Reply
        if ctx.message.reference:
            replied_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            user = replied_msg.author

        # Mention
        elif ctx.message.mentions:
            user = ctx.message.mentions[0]

        # ID
        else:
            if not user_input.isdigit():
                await ctx.send("❌ ID không hợp lệ")
                return
            user = await bot.fetch_user(int(user_input))

    except:
        await ctx.send("❌ Không fetch được user này")
        return

    # Fetch full user (để có banner nếu có)
    try:
        user = await bot.fetch_user(user.id)
    except:
        pass

    member = ctx.guild.get_member(user.id)

    embed = discord.Embed(
        title="🔎 USER PROFILE",
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )

    embed.set_thumbnail(url=user.display_avatar.url)

    # ===== Thông tin cơ bản =====
    embed.add_field(name="👤 Tên", value=f"{user.name}", inline=True)
    embed.add_field(name="🌍 Global", value=user.global_name or "Không có", inline=True)
    embed.add_field(name="🆔 ID", value=user.id, inline=False)

    embed.add_field(
        name="📅 Tạo tài khoản",
        value=user.created_at.strftime("%d/%m/%Y %H:%M"),
        inline=True
    )

    embed.add_field(
        name="🤖 Bot",
        value="Có" if user.bot else "Không",
        inline=True
    )

    # ===== Nếu còn trong server =====
    if member:
        embed.add_field(
            name="📥 Vào server",
            value=member.joined_at.strftime("%d/%m/%Y %H:%M"),
            inline=True
        )

        embed.add_field(
            name="🚀 Boost",
            value="Có" if member.premium_since else "Không",
            inline=True
        )

        embed.add_field(
            name="🏷 Nickname",
            value=member.nick or "Không có",
            inline=True
        )

        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        embed.add_field(
            name=f"📜 Roles ({len(roles)})",
            value=" ".join(roles[:10]) + (" ..." if len(roles) > 10 else "") if roles else "Không có",
            inline=False
        )

    if user.banner:
        embed.set_image(url=user.banner.url)

    await ctx.send(embed=embed)

@bot.command(name="top", aliases=["leaderboard", "rank", "bxh"])
async def top_social_credit(ctx, limit: int = 10):
    # Giới hạn tránh spam
    limit = max(1, min(limit, 50))

    top_users = get_top_users(limit)

    if not top_users:
        await ctx.send("❌ Database trống, chưa có ai đăng ký Social Credit.")
        return

    embed = discord.Embed(
        title="🏆 BẢNG XẾP HẠNG SOCIAL CREDIT",
        description=f"Top **{len(top_users)}** công dân gương mẫu nhất",
        color=discord.Color.gold()
    )

    embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else discord.Embed.Empty)
    embed.set_footer(
        text=f"Yêu cầu bởi {ctx.author.display_name}",
        icon_url=ctx.author.display_avatar.url
    )

    leaderboard_text = ""

    for i, u in enumerate(top_users, start=1):
        user_id = int(u["user_id"])
        credit = u.get("social_credit", 0)

        member = ctx.guild.get_member(user_id)
        name = member.display_name if member else u.get("username", f"User {user_id}")

        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, "🔹")

        leaderboard_text += (
            f"**{i}. {medal} {name}**\n"
            f"↳ 💳 `{credit}` Social Credit\n\n"
        )

    embed.add_field(
        name="📊 Xếp hạng",
        value=leaderboard_text,
        inline=False
    )

    await ctx.send(embed=embed)

@bot.command(name="setcm")
async def set_cm(ctx):
    global saved_cm_message

    # Bắt buộc phải reply
    if not ctx.message.reference:
        await ctx.send("❌ Hãy reply vào tin nhắn muốn copy rồi dùng `!setcm`")
        return

    try:
        msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
    except:
        await ctx.send("❌ Không fetch được tin nhắn.")
        return

    # Lưu nội dung cơ bản
    saved_cm_message = {
        "content": msg.content,
        "embeds": msg.embeds,
        "attachments": msg.attachments
    }

    await ctx.send("✅ Đã lưu tin nhắn làm CM.")

@bot.command(name="cm")
async def cm(ctx):
    global saved_cm_message

    if not saved_cm_message:
        await ctx.send("❌ Chưa có tin nhắn nào được lưu.")
        return

    files = []

    # Lấy lại file nếu có
    for att in saved_cm_message["attachments"]:
        file_bytes = await att.read()
        files.append(discord.File(io.BytesIO(file_bytes), filename=att.filename))

    await ctx.send(
        content=saved_cm_message["content"],
        embeds=saved_cm_message["embeds"],
        files=files if files else None
    )

import random
import asyncio
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
    #bot.run(os.getenv('DISCORD_TOKEN'))
    try:
        bot.run(DISCORD_TOKEN)
    except:
        os.system("kill 1")
