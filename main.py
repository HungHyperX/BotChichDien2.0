import discord
from discord.ext import commands, tasks
import requests
from datetime import datetime, timezone, timedelta, time
from threading import Thread
import asyncio

# ================== CẤU HÌNH CỦA BẠN ==================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
API_URL = "https://uma.moe/api/circles?circle_id={}"

# THAY 2 DÒNG NÀY BẰNG CỦA BẠN
CIRCLE_ID_TO_CHECK = 230947009  # ← ID Circle chính (Strategist)
CHANNEL_ID_TO_SEND = 1442395967369511054  # ← ID kênh nhận báo cáo tự động 7h sáng
# ====================================================

@bot.event
async def on_ready():
    print(f"Bot đã online: {bot.user}")
    auto_keep_awake.start()
    
    # Đảm bảo task 7h sáng chạy đúng giờ dù bot khởi động lúc nào
    daily_check_circle.start()
    
    print("Bot đã sẵn sàng! Task 7h sáng đã được kích hoạt.")


# Task 1: Giữ Replit awake mỗi 12 phút
@tasks.loop(minutes=5)
async def auto_keep_awake():
    try:
        requests.get("https://uma.moe/api/circles?circle_id=1", timeout=10)
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] Auto ping – Replit awake!"
        )
    except:
        pass


# Task 2: Tự động check + gửi kênh lúc 7h sáng giờ Việt Nam
# Chạy đúng 7h00 sáng giờ Việt Nam mỗi ngày
@tasks.loop(time=time(7, 0, tzinfo=timezone(timedelta(hours=7))))
async def daily_check_circle():
    channel = bot.get_channel(CHANNEL_ID_TO_SEND)
    if not channel:
        print("[7h sáng] Không tìm thấy kênh tự động!")
        return

    await channel.send("Đang tự động kiểm tra + lưu KPI Circle lúc **7h sáng**...")

    # Lưu KPI hôm qua trước
    await save_yesterday_kpi_for_circle(CIRCLE_ID_TO_CHECK)

    # Sau đó gửi báo cáo chích điện
    await run_check_and_send(CIRCLE_ID_TO_CHECK, channel)

    print(f"[7h sáng] Đã gửi báo cáo tự động thành công – {datetime.now(timezone(timedelta(hours=7))).strftime('%d/%m/%Y %H:%M')}")


# Hàm chung để xử lý check circle (dùng cho cả lệnh thủ công và tự động)
async def run_check_and_send(circle_id: int, destination):
    try:
        response = requests.get(API_URL.format(circle_id), timeout=15)
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
        circle_date_prefix = circle_updated_str[:10]  # ví dụ: "2025-12-08"

        # Lấy ngày hôm nay từ circle (đã chuẩn)
        circle_updated_dt = datetime.fromisoformat(circle_updated_str.replace("Z", "+00:00"))
        today = circle_updated_dt.date()
        yesterday = today - timedelta(days=1)

        # Gọi lưu KPI hôm qua trước (giữ nguyên logic cũ)
        await save_yesterday_kpi_for_circle(circle_id)

        results = []
        for mem in members:
            name = mem.get("trainer_name", "Unknown").strip()
            if not name:
                continue

            updated_str = mem.get("last_updated", "")
            if not updated_str:
                continue

            # CHỈ LẤY NHỮNG THÀNH VIÊN CÓ CÙNG NGÀY CẬP NHẬT VỚI CIRCLE
            if not updated_str.startswith(circle_date_prefix):
                continue  # Bỏ qua nếu không cùng ngày (ví dụ: còn sót từ hôm qua)

            daily = mem.get("daily_fans", [])
            if len(daily) < today.day:  # Chưa đủ dữ liệu đến hôm nay
                continue

            # Tính fans kiếm được hôm qua (ngày today.day - 1)
            idx_today = today.day - 1      # index của hôm nay trong mảng (0-based)
            idx_yesterday = idx_today - 1  # index của hôm qua

            if idx_today >= len(daily) or idx_yesterday < 0:
                continue

            fans_today = daily[idx_today]
            fans_yesterday = daily[idx_yesterday] if idx_yesterday >= 0 else 0
            diff = fans_today - fans_yesterday

            signal = "✅" if diff >= 800_000 else "⚡"
            status = f"đã thoát được hôm nay với `{diff:,}` fans" if diff >= 800_000 else f"Chỉ cày được `{diff:,}` fans nên sẽ bị chích điện"

            results.append({
                "signal": signal,
                "name": name,
                "diff": diff,
                "status": status
            })

        if not results:
            await destination.send("Không có thành viên nào được cập nhật hôm nay hoặc dữ liệu chưa đầy đủ.")
            return

        # Sắp xếp theo số fan kiếm được giảm dần
        results.sort(key=lambda x: x["diff"], reverse=True)

        msg = f"**Club {circle['name']} ({circle_id})**\n"
        msg += f"**Báo cáo KPI ngày {yesterday.day}/{yesterday.month} → {today.day}/{today.month}** (**KPI**: 800_000 fans)\n\n"

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


# LỆNH KIỂM TRA KPI: !checkkpi
@bot.command(name="kpiChichDien")
async def kpi_chich_dien(ctx, circle_id: int = None):
    if circle_id is None:
        circle_id = CIRCLE_ID_TO_CHECK

    await ctx.send(f"Đang kiểm tra KPI Chích Điện của Circle `{circle_id}`...")

    try:
        response = requests.get(API_URL.format(circle_id), timeout=15)
        if response.status_code != 200:
            await ctx.send(f"Lỗi API: {response.status_code}")
            return

        data = response.json()
        if not data or "circle" not in data or not data.get("members"):
            await ctx.send("Không tìm thấy dữ liệu circle.")
            return

        circle = data["circle"]
        members = data["members"]

        # Lấy ngày hôm nay từ last_updated của circle
        circle_updated_str = data["circle"]["last_updated"]
        circle_updated_dt = datetime.fromisoformat(
            circle_updated_str.replace("Z", "+00:00"))
        today = circle_updated_dt.date()

        msg = f"**📌 KPI Chích Điện – Club {circle['name']} ({circle_id})**\n"
        msg += "Chỉ tiêu: **10 ngày khác nhau hoặc 5 ngày liên tiếp không đủ KPI (< 500k)**\n"
        msg += f"Phân tích từ ngày **15** đến **{today.day - 1}**/{today.month} \n\n"

        bad_members = []

        for mem in members:
            name = mem.get("trainer_name", "Unknown")
            daily = mem.get("daily_fans", [])

            # Không đủ dữ liệu
            if len(daily) < today.day:
                continue

            # Đếm số ngày không đạt KPI
            fail_days = 0
            consecutive = 0
            max_consecutive = 0

            # I bắt đầu từ hôm qua → lùi về 1
            for i in range(today.day - 1, 15, -1):
                diff = daily[i] - daily[i - 1]

                if diff < 500_000:
                    fail_days += 1
                    consecutive += 1
                else:
                    consecutive = 0

                max_consecutive = max(max_consecutive, consecutive)

            # Kiểm tra điều kiện
            if fail_days >= 10 or max_consecutive >= 5:
                bad_members.append({
                    "name": name,
                    "fail": fail_days,
                    "consec": max_consecutive
                })

        if not bad_members:
            await ctx.send("🎉 Không có ai vi phạm KPI chích điện!")
            return

        # Sort theo số lần fail
        bad_members.sort(key=lambda x: (x["fail"], x["consec"]), reverse=True)

        for m in bad_members:
            msg += f"⚡ **{m['name']}** bị cảnh cáo – vì {m['fail']} ngày không đủ KPI, {m['consec']} ngày liên tiếp\n"

        # Gửi kết quả
        if len(msg) > 1900:
            for part in [msg[i:i + 1900] for i in range(0, len(msg), 1900)]:
                await ctx.send(part)
        else:
            await ctx.send(msg)

    except Exception as e:
        await ctx.send(f"Lỗi: {e}")
        print(e)


# Keep alive dự phòng


import json
from pathlib import Path


# ================== LƯU KPI THEO CIRCLE_ID ==================
def get_kpi_file(circle_id: int) -> Path:
    """Trả về đường dẫn file JSON riêng cho từng circle"""
    return Path(f"daily_kpi_circle_{circle_id}.json")


def load_kpi_history(circle_id: int) -> dict:
    """Đọc lịch sử KPI của circle cụ thể"""
    file = get_kpi_file(circle_id)
    if not file.exists():
        return {}  # Trả về dict rỗng nếu chưa có file
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
        # Chuyển key ngày từ string → date (nếu cần xử lý date sau này)
        return {
            datetime.strptime(k, "%Y-%m-%d").date(): v
            for k, v in data.items()
        }
    except Exception as e:
        print(f"[Lưu KPI] Lỗi đọc file {file.name}: {e}")
        return {}


def save_kpi_history(circle_id: int, history: dict):
    """Lưu lại lịch sử KPI (history đã có key là date object)"""
    file = get_kpi_file(circle_id)
    savable = {d.strftime("%Y-%m-%d"): v for d, v in history.items()}
    file.write_text(json.dumps(savable, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    print(f"[Lưu KPI] Đã lưu vào {file.name} – {len(history)} ngày")


# ============================================================


async def save_yesterday_kpi_for_circle(circle_id: int):
    """
    Lưu số fan kiếm được HÔM QUA của tất cả thành viên trong circle
    Gọi hàm này mỗi 7h sáng (hoặc khi cần)
    """
    try:
        response = requests.get(API_URL.format(circle_id), timeout=15)
        if response.status_code != 200:
            print(f"[Circle {circle_id}] Lỗi API khi lưu KPI:",
                  response.status_code)
            return

        data = response.json()
        if not data or "circle" not in data or not data.get("members"):
            print(f"[Circle {circle_id}] Không có dữ liệu circle khi lưu KPI")
            return

        members = data["members"]
        circle_updated_str = data["circle"]["last_updated"]
        circle_updated_dt = datetime.fromisoformat(
            circle_updated_str.replace("Z", "+00:00"))
        today = circle_updated_dt.date()
        yesterday = today - timedelta(days=1)  # Ngày cần lưu KPI

        history = load_kpi_history(circle_id)

        # Nếu ngày hôm qua đã được lưu rồi thì không ghi đè (tránh lỗi khi task chạy lại)
        if yesterday in history:
            print(
                f"[Circle {circle_id}] KPI ngày {yesterday} đã được lưu trước đó rồi."
            )
            return

        history[yesterday] = {}
        # Tạo dict mới cho ngày hôm qua
        saved_count = 0

        for mem in members:
            name = mem.get("trainer_name", "").strip()
            if not name:
                continue

            daily = mem.get("daily_fans", [])
            if len(daily) < 2:
                continue

            # Kiểm tra xem dữ liệu member có mới không
            updated_str = mem.get("last_updated", "")
            if not updated_str:
                continue
            try:
                updated_dt = datetime.fromisoformat(
                    updated_str.replace("Z", "+00:00"))
            except:
                continue

            if updated_dt.date() not in (today, yesterday):
                continue

            idx = updated_dt.day - 1
            if idx <= 0 or idx >= len(daily):
                continue

            fans_yesterday = daily[idx] - (daily[idx - 1] if idx > 0 else 0)

            history[yesterday][name] = fans_yesterday
            saved_count += 1

        # Chỉ lưu khi thực sự có dữ liệu mới
        if saved_count > 0:
            save_kpi_history(circle_id, history)
            print(
                f"[Circle {circle_id}] Đã lưu KPI ngày {yesterday.strftime('%d/%m/%Y')} cho {saved_count} thành viên"
            )
        else:
            print(
                f"[Circle {circle_id}] Không có thành viên nào cập nhật hôm qua → không lưu"
            )

    except Exception as e:
        print(f"[Circle {circle_id}] Lỗi nghiêm trọng khi lưu KPI: {e}")


# ================== HELP SIÊU LẦY LỘI ==================
@bot.command(name="help", aliases=["h", "commands", "lenh"])
async def custom_help(ctx):
    embed = discord.Embed(
        title="Bot Chích Điện bị ngu nên hay đi ngủ gật thông cảm",
        description="Dưới đây là danh sách lệnh tao có thể làm (khi tao tỉnh):",
        color=0xFF6B6B)

    embed.add_field(
        name="`!help` hoặc `!h`",
        value="→ Để kêu cứu khi mày lạc đường trong cái bot ngu này",
        inline=False)

    embed.add_field(name="`!cc` hoặc `!circle` hoặc `!checkcircle`",
                    value="→ Chích điện mấy con vợ không đủ KPI hôm qua\n"
                    "Ví dụ: `!cc` hoặc `!cc 123456` nếu muốn check club khác",
                    inline=False)

    embed.add_field(
        name="`!kpiChichDien`",
        value=
        "→ Check xem đứa nào lười quá trời, không đủ 500k nhiều ngày liền → chuẩn bị bị cảnh cáo + chích điện thật",
        inline=False)

    embed.add_field(
        name="`!beg + <số-ngày-beg>`",
        value=
        "→ Cầu xin mấy con giời thêm đền thờ cho Daiwa Scarlet a.k.a tội vơ :>",
        inline=False)

    embed.set_footer(
        text="Thức tỉnh mà nghiện uma đê. Không thì bị giật điện!!!")
    embed.set_thumbnail(
        url="https://ibb.co/LDZ91gVV")  # icon chích điện (có thể thay link)

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
    bot.run(os.getenv('DISCORD_TOKEN'))

#bot.run(os.getenv("DISCORD_TOKEN"))
