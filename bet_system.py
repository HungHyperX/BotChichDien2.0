import discord
from discord.ext import commands

class BetSystem(commands.Cog):
    def __init__(self, bot, ensure_user, change_credit,
                 BET_ADMIN_ID, BET_ADMIN_ID_2, SPOUSE_USER_ID):
        self.bot = bot
        self.ensure_user = ensure_user
        self.change_credit = change_credit

        self.BET_ADMIN_ID = BET_ADMIN_ID
        self.BET_ADMIN_ID_2 = BET_ADMIN_ID_2
        self.SPOUSE_USER_ID = SPOUSE_USER_ID

        self.active_bet = None

    # ================= GROUP =================
    @commands.group(name="bet", invoke_without_command=True)
    async def bet(self, ctx):
        await ctx.send(
            "📌 **LỆNH BET**\n"
            "`!bet create <title> | <opt1> | <opt2>`\n"
            "`!bet join <số_option> <credit>`\n"
            "`!bet stop`\n"
            "`!bet end <số_option_thắng>`\n"
            "`!bet info`\n"
            "`!bet refund`\n"
        )

    # ================= CREATE =================
    @bet.command(name="create")
    async def bet_create(self, ctx, *, raw: str):

        if ctx.author.id not in [
            self.BET_ADMIN_ID,
            self.BET_ADMIN_ID_2,
            self.SPOUSE_USER_ID
        ]:
            await ctx.send("⛔ Mày không có quyền tạo kèo.")
            return

        if self.active_bet and self.active_bet["open"]:
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

        self.active_bet = {
            "creator_id": ctx.author.id,
            "title": title,
            "options": options,
            "total_pool": 0,
            "open": True,
            "ended": False
        }

        msg = f"🎲 **KÈO BET MỚI** 🎲\n📌 {title}\n\n"
        for i, o in options.items():
            msg += f"`{i}`️⃣ {o['text']}\n"

        msg += "\n👉 Tham gia: `!bet join <số> <credit>`"

        await ctx.send(msg)

    # ================= JOIN =================
    @bet.command(name="join")
    async def bet_join(self, ctx, option: int, amount: int):

        if not self.active_bet or not self.active_bet["open"]:
            await ctx.send("❌ Hiện không có kèo nào.")
            return

        if option not in self.active_bet["options"]:
            await ctx.send("❌ Lựa chọn không tồn tại.")
            return

        if amount < 10 or amount > 670:
            await ctx.send("❌ Chỉ được bet từ 10 đến 670 SC.")
            return

        user_data = self.ensure_user(ctx.author)

        if user_data["social_credit"] < amount:
            await ctx.send("❌ Không đủ Social Credit.")
            return

        # Không cho bet nhiều cửa
        for opt in self.active_bet["options"].values():
            if ctx.author.id in opt["bets"]:
                await ctx.send("⚠️ Mỗi người chỉ được bet 1 cửa.")
                return

        self.change_credit(ctx.author, -amount, "Bet tham gia")

        opt = self.active_bet["options"][option]
        opt["total"] += amount
        opt["bets"][ctx.author.id] = amount
        self.active_bet["total_pool"] += amount

        await ctx.send(
            f"✅ **{ctx.author.display_name}** đã bet `{amount}` SC vào **{opt['text']}**"
        )

    # ================= STOP =================
    @bet.command(name="stop")
    async def bet_stop(self, ctx):

        if ctx.author.id not in [
            self.BET_ADMIN_ID,
            self.BET_ADMIN_ID_2,
            self.SPOUSE_USER_ID
        ]:
            await ctx.send("⛔ Không có quyền stop.")
            return

        if not self.active_bet:
            await ctx.send("❌ Không có kèo.")
            return

        self.active_bet["open"] = False

        await ctx.send("🛑 Kèo đã dừng. Chờ `!bet end`.")

    # ================= END =================
    @bet.command(name="end")
    async def bet_end(self, ctx, winning_option: int):

        if ctx.author.id not in [
            self.BET_ADMIN_ID,
            self.BET_ADMIN_ID_2,
            self.SPOUSE_USER_ID
        ]:
            await ctx.send("⛔ Không có quyền end.")
            return

        if not self.active_bet or self.active_bet["open"]:
            await ctx.send("⚠️ Phải stop trước.")
            return

        if winning_option not in self.active_bet["options"]:
            await ctx.send("❌ Option không tồn tại.")
            return

        win_opt = self.active_bet["options"][winning_option]
        total_win = win_opt["total"]

        msg = f"🏁 **KẾT QUẢ BET** 🏁\n🏆 {win_opt['text']}\n\n"

        if total_win == 0:
            msg += "💀 Không ai bet cửa thắng."
            await ctx.send(msg)
            self.active_bet = None
            return

        WIN_RATE = 1.5

        for uid, bet_amt in win_opt["bets"].items():
            user = ctx.guild.get_member(uid)
            if not user:
                continue

            win_amount = int(bet_amt * WIN_RATE)
            self.change_credit(user, win_amount, "Bet thắng")
            msg += f"🎉 {user.display_name} thắng `{win_amount}` SC\n"

        await ctx.send(msg)
        self.active_bet = None

    # ================= INFO =================
    @bet.command(name="info")
    async def bet_info(self, ctx):

        if not self.active_bet:
            await ctx.send("❌ Không có kèo.")
            return

        status = "🔓 Đang mở" if self.active_bet["open"] else "🔒 Đã khóa"

        msg = (
            f"🎲 **THÔNG TIN KÈO**\n"
            f"📌 {self.active_bet['title']}\n"
            f"📊 {status}\n"
            f"💰 Pool: `{self.active_bet['total_pool']}` SC\n\n"
        )

        for i, opt in self.active_bet["options"].items():
            msg += (
                f"`{i}`️⃣ {opt['text']}\n"
                f"   └ 💸 `{opt['total']}` SC | 👥 `{len(opt['bets'])}` người\n"
            )

        await ctx.send(msg)

    # ================= REFUND =================
    @bet.command(name="refund")
    async def bet_refund(self, ctx):

        if ctx.author.id not in [
            self.BET_ADMIN_ID,
            self.BET_ADMIN_ID_2,
            self.SPOUSE_USER_ID
        ]:
            await ctx.send("⛔ Không có quyền refund.")
            return

        if not self.active_bet:
            await ctx.send("❌ Không có kèo.")
            return

        for opt in self.active_bet["options"].values():
            for uid, amount in opt["bets"].items():
                member = ctx.guild.get_member(uid)
                if member:
                    self.change_credit(member, amount, "Refund bet")

        await ctx.send("🔄 Đã refund toàn bộ.")
        self.active_bet = None

