import discord
from discord.ext import commands
from database import ensure_user, change_credit, add_item, get_inventory, get_user

class ShopSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Danh sách vật phẩm
        self.SHOP_ITEMS = {
            "finalshowdown_point": {
                "price": 250,
                "description": "1 điểm Final Showdown Qualifier.\nMua xong liên hệ <@!969465805555261480>"
            },
            "shopping_point": {
                "price": 200,
                "description": "1 điểm mua hàng.\nMua xong liên hệ <@!969465805555261480>"
            },
            "jail_break": {
                "price": 36000,
                "description": "Vé tự do ra tù. Có trong người ra vào nhà tù tự do trong 1 tháng"
            }
        }

    # ================= SHOP =================

    @commands.command(name="shop")
    async def shop(self, ctx):
        embed = discord.Embed(
            title="🏪 CỬA HÀNG SOCIAL CREDIT",
            color=discord.Color.green()
        )

        for name, data in self.SHOP_ITEMS.items():
            embed.add_field(
                name=f"{name.upper()} — {data['price']} SC",
                value=data["description"],
                inline=False
            )

        await ctx.send(embed=embed)

    # ================= BUY =================

    @commands.command(name="buy")
    async def buy(self, ctx, item_name: str, quantity: int = 1):
        user = ctx.author
        ensure_user(user)

        item_name = item_name.lower()

        if item_name not in self.SHOP_ITEMS:
            await ctx.send("❌ Vật phẩm không tồn tại.")
            return

        if quantity <= 0:
            await ctx.send("❌ Số lượng phải lớn hơn 0.")
            return

        item = self.SHOP_ITEMS[item_name]
        price = item["price"]

        total_price = price * quantity

        user_data = get_user(user.id)

        if user_data["social_credit"] < total_price:
            await ctx.send(
                f"❌ Không đủ Social Credit.\n"
                f"💰 Cần `{total_price}` SC"
            )
            return

        # Trừ tiền
        change_credit(user, -total_price, f"Mua {item_name} x{quantity}")

        # Cộng item
        add_item(user.id, item_name, quantity)

        await ctx.send(
            f"🛒 Mua thành công `{item_name} x{quantity}`\n"
            f"💸 Tổng: `{total_price}` SC"
        )

    # ================= INVENTORY =================

    @commands.command(name="inventory", aliases=["inv"])
    async def inventory(self, ctx):
        user = ctx.author
        inv = get_inventory(user.id)

        if not inv:
            await ctx.send("🎒 Túi đồ trống.")
            return

        text = ""
        for item, amount in inv.items():
            text += f"• **{item}** x{amount}\n"

        embed = discord.Embed(
            title=f"🎒 Inventory của {user.display_name}",
            description=text,
            color=discord.Color.blurple()
        )

        await ctx.send(embed=embed)

