import discord
from discord.ext import commands
import config
from database import get_user, create_user, ensure_user, change_credit, change_credit_by_id, users_col

class SocialCredit(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="registerDB")
    async def register_db(self, ctx):
        existing = get_user(ctx.author.id)
        if existing:
            await ctx.send(f"⚠️ Đã có tài khoản! SC: **{existing['social_credit']}**")
        else:
            credit = create_user(ctx.author)
            await ctx.send(f"✅ Đăng ký thành công! SC: **{credit}**")

    @commands.command(name="credit", aliases=["sc"])
    async def social_credit(self, ctx):
        data = get_user(ctx.author.id)
        if not data:
            await ctx.send("❌ Dùng `!registerDB` trước.")
        else:
            await ctx.send(f"💳 **Social Credit:** `{data['social_credit']}`")

    @commands.command(name="grant")
    async def grant_social_credit(self, ctx, target, amount: int, *, reason: str = "Special grant"):
        if ctx.author.id != config.SPOUSE_USER_ID:
            return await ctx.send("⛔ Mày không có quyền.")

        if target.lower() == "all":
            users = list(users_col.find({}))
            for user in users:
                change_credit_by_id(user["user_id"], amount, reason)
            await ctx.send(f"👑 Đã áp dụng {amount} SC cho {len(users)} user.")
        elif ctx.message.mentions:
            member = ctx.message.mentions[0]
            ensure_user(member)
            change_credit(member, amount, reason)
            await ctx.send(f"👑 Đã cấp {amount} SC cho {member.display_name}.")
        else:
            await ctx.send("❌ Tag user hoặc dùng `all`.")

    @commands.command(name="supremacy")
    async def supremacy(self, ctx):
        try:
            with open("supremacy.gif", "rb") as f:
                await ctx.send("**DAISCA SUPREMACY**", file=discord.File(f))
        except:
            await ctx.send("❌ Thiếu file supremacy.gif")

async def setup(bot):
    await bot.add_cog(SocialCredit(bot))