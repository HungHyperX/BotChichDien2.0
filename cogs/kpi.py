import discord
from discord.ext import commands, tasks
import requests
import json
from datetime import datetime, timezone, timedelta, time
import config

class KPI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_manual_data = None
        # Khởi động task tự động
        self.daily_check_circle.start()

    def cog_unload(self):
        self.daily_check_circle.cancel()

    @tasks.loop(time=time(7, 0, tzinfo=timezone(timedelta(hours=7))))
    async def daily_check_circle(self):
        channel = self.bot.get_channel(config.CHANNEL_ID_TO_SEND)
        if not channel: return
        await channel.send("Đang tự động kiểm tra KPI Circle lúc **7h sáng**...")
        await self.run_check_and_send(config.CIRCLE_ID_TO_CHECK, channel)
        await self.check_kpi_day_week_month(config.CIRCLE_ID_TO_CHECK, channel)

    @commands.command(name="usejson")
    async def use_json_data(self, ctx):
        if not ctx.message.attachments:
            return await ctx.send("❌ Kèm file JSON đi.")
        attachment = ctx.message.attachments[0]
        try:
            file_content = await attachment.read()
            self.last_manual_data = json.loads(file_content)
            await ctx.send(f"✅ Đã lưu dữ liệu từ **{attachment.filename}**.")
        except Exception as e:
            await ctx.send(f"❌ Lỗi: {e}")

    @commands.command(name="cf")
    async def check_from_cache(self, ctx):
        if self.last_manual_data is None:
            return await ctx.send("❌ Chưa có dữ liệu! Dùng `!usejson` trước.")
        await ctx.send("📂 **Sử dụng lại dữ liệu cũ...**")
        await self.run_check_and_send(config.CIRCLE_ID_TO_CHECK, ctx.channel, manual_data=self.last_manual_data)

    @commands.command(name="checkcircle", aliases=["cc", "circle"])
    async def checkcircle(self, ctx, circle_id: int = None):
        cid = circle_id or config.CIRCLE_ID_TO_CHECK
        await ctx.send(f"Đang kiểm tra Circle `{cid}`...")
        await self.run_check_and_send(cid, ctx.channel)

    @commands.command(name="kpiChichDien", aliases=["checkkpi"])
    async def kpi(self, ctx):
        await ctx.send("⏳ **Đang kiểm tra KPI (thủ công)...**")
        await self.check_kpi_day_week_month_manual(config.CIRCLE_ID_TO_CHECK, ctx.channel)

    # --- HELPER FUNCTIONS (Logic KPI) ---
    async def run_check_and_send(self, circle_id, destination, manual_data=None):
        try:
            data = manual_data
            if not data:
                res = requests.get(config.API_URL.format(circle_id), timeout=15)
                if res.status_code != 200: return await destination.send(f"Lỗi API: {res.status_code}")
                data = res.json()

            circle = data.get("circle")
            members = data.get("members")
            if not circle or not members: return await destination.send("Không có dữ liệu circle.")

            circle_updated_str = circle["last_updated"]
            circle_date_prefix = circle_updated_str[:10]
            circle_updated_dt = datetime.fromisoformat(circle_updated_str.replace("Z", "+00:00"))
            today = circle_updated_dt.date()
            yesterday = today - timedelta(days=1)

            results = []
            for mem in members:
                raw_name = mem.get("trainer_name") or mem.get("name")
                name = str(raw_name).strip() if raw_name else "Unknown"
                if not name: continue

                updated_str = mem.get("last_updated", "")
                if not updated_str: continue
                if updated_str[:10] not in (circle_date_prefix, yesterday.strftime("%Y-%m-%d")):
                    continue

                daily = mem.get("daily_fans", [])
                if len(daily) < today.day: continue
                
                idx_today = mem_date_day = datetime.fromisoformat(updated_str.replace("Z", "+00:00")).date().day - 1
                idx_yesterday = idx_today - 1
                if idx_today >= len(daily) or idx_yesterday < 0: continue

                diff = daily[idx_today] - daily[idx_yesterday]
                signal = "✅" if diff >= 999_000 else "⚡"
                status = f"đã thoát với `{diff:,}` fans" if diff >= 999_000 else f"Chỉ cày `{diff:,}` fans -> chích điện"
                results.append({"signal": signal, "name": name, "diff": diff, "status": status})

            if not results: return await destination.send("Không có dữ liệu hợp lệ hôm nay.")
            
            results.sort(key=lambda x: x["diff"], reverse=True)
            msg = f"**Club {circle['name']}** - Báo cáo KPI {yesterday.day}/{yesterday.month} -> {today.day}/{today.month}\n\n"
            for i, r in enumerate(results, 1):
                msg += f"`{i:2}.` **{r['signal']} {r['name']}**: {r['status']}\n"
            
            if len(msg) > 1900:
                for part in [msg[i:i+1900] for i in range(0, len(msg), 1900)]:
                    await destination.send(part)
            else:
                await destination.send(msg)
        except Exception as e:
            print(f"Check error: {e}")
            await destination.send(f"Lỗi: {e}")

    async def check_kpi_day_week_month(self, circle_id, channel, manual_data=None):
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
            response = requests.get((config.API_URL).format(circle_id), HEADERS, timeout=15)
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
        #pass 

    async def check_kpi_day_week_month_manual(self, circle_id, channel):
        HEADERS = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }
        response = requests.get((config.API_URL).format(circle_id), HEADERS, timeout=15)
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
        #pass

async def setup(bot):
    await bot.add_cog(KPI(bot))