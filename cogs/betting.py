from discord.ext import commands
import config
from database import ensure_user, change_credit

class Betting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_bet = None

    @commands.group(name="bet", invoke_without_command=True)
    async def bet(self, ctx):
        await ctx.send(
            "📌 **LỆNH BET**\n"
            "`!bet create <title> | <opt1> | <opt2> ...`\n"
            "`!bet join <số_option> <credit>`\n"
            "`!bet stop`\n"
            "`!bet end <số_option_thắng>`\n"
            "`!bet info`\n"
            "`!bet refund`\n"
        )

    @bet.command(name="create")
    async def bet_create(self, ctx, *, raw: str):
        if ctx.author.id != config.BET_ADMIN_ID and ctx.author.id != config.SPOUSE_USER_ID:
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

    @bet.command(name="join")
    async def bet_join(self, ctx, option: int, amount: int):
        if not self.active_bet or not self.active_bet["open"]:
            await ctx.send("❌ Hiện không có kèo nào.")
            return

        if option not in self.active_bet["options"]:
            await ctx.send("❌ Lựa chọn không tồn tại.")
            return

        if amount < 10 or amount > 360:
            await ctx.send("❌ Chỉ được bet từ **10 đến 360** Social Credit.")
            return

        user_data = ensure_user(ctx.author)
        if user_data["social_credit"] < amount:
            await ctx.send("❌ Không đủ Social Credit.")
            return

        for opt in self.active_bet["options"].values():
            if ctx.author.id in opt["bets"]:
                await ctx.send("⚠️ Mỗi người chỉ được bet **1 cửa**.")
                return

        change_credit(ctx.author, -amount, "Bet tham gia")
        opt = self.active_bet["options"][option]
        opt["total"] += amount
        opt["bets"][ctx.author.id] = amount
        self.active_bet["total_pool"] += amount

        await ctx.send(f"✅ **{ctx.author.display_name}** đã bet `{amount}` SC vào **{opt['text']}**")

    @bet.command(name="stop")
    async def bet_stop(self, ctx):
        if ctx.author.id != config.BET_ADMIN_ID and ctx.author.id != config.SPOUSE_USER_ID:
            await ctx.send("⛔ Không có quyền.")
            return
        if not self.active_bet:
            return await ctx.send("❌ Không có kèo nào.")
        self.active_bet["open"] = False
        await ctx.send("🛑 **KÈO ĐÃ BỊ DỪNG**")

    @bet.command(name="info")
    async def bet_info(self, ctx):
        if not self.active_bet:
            return await ctx.send("❌ Không có kèo nào.")
        
        status = "🔓 Đang mở bet" if self.active_bet["open"] else "🔒 Đã khóa bet"
        if self.active_bet["ended"]: status = "🏁 Đã kết thúc"
        
        msg = f"🎲 **{self.active_bet['title']}**\n📊 {status} | 💰 Pool: `{self.active_bet['total_pool']}` SC\n\n"
        for i, opt in self.active_bet["options"].items():
            msg += f"`{i}`️⃣ **{opt['text']}**: `{opt['total']}` SC ({len(opt['bets'])} người)\n"
        await ctx.send(msg)

    @bet.command(name="end")
    async def bet_end(self, ctx, winning_option: int):
        if ctx.author.id != config.BET_ADMIN_ID and ctx.author.id != config.SPOUSE_USER_ID:
            return await ctx.send("⛔ Không có quyền.")
        
        if not self.active_bet or self.active_bet["open"] or self.active_bet["ended"]:
            return await ctx.send("⚠️ Phải stop kèo trước hoặc kèo đã end.")

        if winning_option not in self.active_bet["options"]:
            return await ctx.send("❌ Lựa chọn không tồn tại.")

        self.active_bet["ended"] = True
        win_opt = self.active_bet["options"][winning_option]
        
        msg = f"🏁 **KẾT QUẢ: {win_opt['text']}**\n"
        if win_opt["total"] == 0:
            msg += "💀 Không ai bet cửa thắng."
            await ctx.send(msg)
            self.active_bet = None
            return

        WIN_RATE = 1.5
        for uid, bet_amt in win_opt["bets"].items():
            user = ctx.guild.get_member(uid)
            if user:
                win_amount = int(bet_amt * WIN_RATE)
                change_credit(user, win_amount, "Bet thắng")
                msg += f"🎉 **{user.display_name}** thắng `{win_amount}` SC\n"
        
        await ctx.send(msg)
        self.active_bet = None

    @bet.command(name="refund")
    async def bet_refund(self, ctx):
        if ctx.author.id != config.BET_ADMIN_ID and ctx.author.id != config.SPOUSE_USER_ID:
            return
        if not self.active_bet or self.active_bet["ended"]:
            return await ctx.send("❌ Không thể refund.")

        msg = "🔄 **REFUND KÈO**\n"
        for opt in self.active_bet["options"].values():
            for uid, amt in opt["bets"].items():
                member = ctx.guild.get_member(uid)
                if member:
                    change_credit(member, amt, "Refund bet")
                    msg += f"💸 **{member.display_name}** nhận lại `{amt}` SC\n"
        
        await ctx.send(msg)
        self.active_bet = None

async def setup(bot):
    await bot.add_cog(Betting(bot))