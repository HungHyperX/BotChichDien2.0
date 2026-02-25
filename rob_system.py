import discord
from discord.ext import commands
from datetime import datetime, timezone, timedelta
import random


class RobSystem(commands.Cog):
    def __init__(self, bot, users_col, rob_col, ensure_user, get_user, change_credit, SPOUSE_USER_ID):
        self.bot = bot
        self.users_col = users_col
        self.rob_col = rob_col
        self.ensure_user = ensure_user
        self.get_user = get_user
        self.change_credit = change_credit
        self.SPOUSE_USER_ID = SPOUSE_USER_ID

        # CONFIG
        self.ROB_DAILY_COOLDOWN = 21600  # 8h
        self.ROB_BASE_SUCCESS = 0.5
        self.DEFEND_BASE_SUCCESS = 0.6
        self.ROB_MIN = 37
        self.ROB_MAX = 360
        self.DEFEND_TIME = 4 * 60 * 60  # 4h
        self.DEFEND_FOR_SUCCESS = 0.36  # thấp hơn defend thường (0.6)
        self.DEFEND_REWARD = 36


    # ================= DATABASE HELPERS =================

    def get_last_rob(self, user_id):
        return self.rob_col.find_one(
            {"robber_id": user_id},
            sort=[("created_at", -1)]
        )

    def get_active_rob_for_victim(self, victim_id):
        now = datetime.now(timezone.utc)
        return self.rob_col.find_one({
            "victim_id": victim_id,
            "success": True,
            "defended": False,
            "expires_at": {"$gt": now}
        })

    # ================= COMMANDS =================

    @commands.command(name="rob")
    async def rob(self, ctx, target: discord.Member):
        robber = ctx.author
        victim = target

        if robber.id == victim.id:
            await ctx.send("❌ Tự cướp bản thân là sao mày?")
            return

        if victim.bot:
            await ctx.send("🤖 Cướp bot làm gì?")
            return

        if victim.id == self.SPOUSE_USER_ID:
            success_chance = 0.036
        else:
            success_chance = self.ROB_BASE_SUCCESS

        self.ensure_user(robber)
        self.ensure_user(victim)

        now = datetime.now(timezone.utc)

        # Cooldown
        if victim.id != self.SPOUSE_USER_ID:
            last = self.get_last_rob(robber.id)
            if last:
                last_time = last["created_at"]
                if last_time.tzinfo is None:
                    last_time = last_time.replace(tzinfo=timezone.utc)

                elapsed = (now - last_time).total_seconds()
                if elapsed < self.ROB_DAILY_COOLDOWN:
                    remain = int(self.ROB_DAILY_COOLDOWN - elapsed)
                    hours = remain // 3600
                    minutes = (remain % 3600) // 60
                    await ctx.send(f"⏳ Còn `{hours}h {minutes}p` nữa.")
                    return

        victim_data = self.get_user(victim.id)
        if victim_data["social_credit"] <= 0:
            await ctx.send("💀 Nó nghèo rồi.")
            return

        amount = random.randint(self.ROB_MIN, self.ROB_MAX)
        amount = min(amount, victim_data["social_credit"])

        success = random.random() < success_chance

        rob_log = {
            "robber_id": robber.id,
            "victim_id": victim.id,
            "amount": amount,
            "success": success,
            "defended": False,
            "defenders": [],  # 👈 THÊM DÒNG NÀY
            "created_at": now,
            "expires_at": now + timedelta(seconds=self.DEFEND_TIME)
        }

        self.rob_col.insert_one(rob_log)

        if success:
            self.change_credit(victim, -amount, "Bị cướp")
            self.change_credit(robber, amount, "Cướp thành công")

            await ctx.send(
                f"🔪 Cướp thành công `{amount}` SC\n"
                f"⚠️ Nạn nhân có 4h để `!defend`"
            )
        else:
            await ctx.send("💥 Cướp thất bại!")

    @commands.command(name="defend")
    async def defend(self, ctx):
        defender = ctx.author

        rob = self.get_active_rob_for_victim(defender.id)
        if not rob:
            await ctx.send("❌ Không có vụ cướp nào.")
            return

        defend_success = random.random() < self.DEFEND_BASE_SUCCESS

        if not defend_success:
            self.rob_col.update_one(
                {"_id": rob["_id"]},
                {"$set": {"defended": True}}
            )
            await ctx.send("💥 Phòng thủ thất bại!")
            return

        steal_back = rob["amount"]
        robber_id = rob["robber_id"]
        robber = ctx.guild.get_member(robber_id)

        if robber:
            self.change_credit(robber, -steal_back, "Bị phản công")

        self.change_credit(defender, steal_back, "Phòng thủ thành công")

        self.rob_col.update_one(
            {"_id": rob["_id"]},
            {"$set": {"defended": True}}
        )

        await ctx.send(f"🛡️ Lấy lại `{steal_back}` SC!")

    @commands.command(name="defendfor")
    async def defend_for(self, ctx, target: discord.Member):
        helper = ctx.author
        victim = target

        if helper.id == victim.id:
            await ctx.send("❌ Muốn defend thì dùng !defend.")
            return

        if victim.bot:
            await ctx.send("🤖 Không defend cho bot.")
            return

        rob = self.get_active_rob_for_victim(victim.id)
        if not rob:
            await ctx.send("❌ Người này không có vụ cướp nào đang hoạt động.")
            return

        # ❌ Không cho robber đi defend hộ
        if helper.id == rob["robber_id"]:
            await ctx.send("💀 Mày là thằng đi cướp, defend cái gì?")
            return

        defenders = rob.get("defenders", [])

        # ❌ Mỗi người chỉ được defend 1 lần
        if helper.id in defenders:
            await ctx.send("❌ Mày đã defend hộ vụ này rồi.")
            return

        # ❌ Giới hạn 2 người defend
        if len(defenders) >= 2:
            await ctx.send("⚠️ Đã có đủ 2 người defend hộ rồi.")
            return

        defend_success = random.random() < self.DEFEND_FOR_SUCCESS

        if not defend_success:
            # Vẫn tính là đã dùng lượt
            self.rob_col.update_one(
                {"_id": rob["_id"]},
                {"$push": {"defenders": helper.id}}
            )

            await ctx.send("💥 Defend hộ thất bại!")
            return

        steal_back = rob["amount"]
        robber_id = rob["robber_id"]
        robber = ctx.guild.get_member(robber_id)

        reward = min(self.DEFEND_REWARD, steal_back)

        # Trừ robber
        if robber:
            self.change_credit(robber, -steal_back, "Bị phản công (defend hộ)")

        # Victim lấy lại phần còn lại
        self.change_credit(victim, steal_back - reward, "Được defend hộ")

        # Helper nhận thưởng
        self.change_credit(helper, reward, "Thưởng defend hộ")

        # Update DB
        self.rob_col.update_one(
            {"_id": rob["_id"]},
            {
                "$set": {"defended": True},
                "$push": {"defenders": helper.id}
            }
        )

        await ctx.send(
            f"🛡️ {helper.mention} defend thành công cho {victim.mention}!\n"
            f"💰 {victim.display_name} lấy lại `{steal_back - reward}` SC\n"
            f"🏆 {helper.display_name} nhận `{reward}` SC tiền thưởng!"
        )



