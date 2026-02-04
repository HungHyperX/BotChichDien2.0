import discord
from discord.ext import commands
import asyncio
import config

# Cấu hình Bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

@bot.event
async def on_ready():
    print(f"Bot đã online: {bot.user}")
    print("Đang load extensions...")

async def main():
    async with bot:
        # Load các file trong folder cogs
        await bot.load_extension("cogs.events")
        await bot.load_extension("cogs.betting")
        await bot.load_extension("cogs.social")
        await bot.load_extension("cogs.kpi")
        print("Đã load toàn bộ cogs!")
        # Bạn cần thêm token vào đây hoặc để trong biến môi trường
        # await bot.start("YOUR_TOKEN_HERE") 

if __name__ == "__main__":
    # Thay vì để token cứng, hãy dùng input hoặc biến môi trường
    import os
    token = os.getenv("DISCORD_BOT_TOKEN") 
    if not token:
        print("⚠️ Chưa set DISCORD_BOT_TOKEN!")
    else:
        asyncio.run(main())