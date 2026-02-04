import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timezone
import re
import config
from database import change_credit

class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.gay_cooldown = {}
        self.last_message_time = {}
        self.spouse_interaction_cooldown = {}

    def check_spouse_cooldown(self, user_id):
        last_trigger = self.spouse_interaction_cooldown.get(user_id)
        if last_trigger:
            if (datetime.now(timezone.utc) - last_trigger).total_seconds() < 86400:
                return True 
        return False

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return

        # 1. LOGIC BẮT BOT "CORRECT"
        if message.author.id == config.SOURCE_BOT_ID:
            match = config.CORRECT_REGEX.search(message.content)
            if match:
                user_id_str = match.group(1)
                user_name_str = match.group(2)
                base_points = 0
                streak = int(match.group(4))
                guild = message.guild
                if not guild: return
                
                member = None
                if user_id_str:
                    member = guild.get_member(int(user_id_str))
                elif user_name_str:
                    member = discord.utils.get(guild.members, display_name=user_name_str)

                if not member:
                    print(f"Không tìm thấy member: {user_id_str or user_name_str}")
                    await message.channel.send("**Mở tài khoản đi ku!!!** Gõ !registerDB")
                    return

                streak_bonus = (streak - 1) // 30 + 1
                total_reward = base_points + streak_bonus
                change_credit(member, total_reward, reason=f"Correct answer + streak bonus")
                await message.channel.send(f"🏆 **Thưởng:** `{total_reward}` Social Credit")
                return

        if message.author.bot:
            return

        now_utc = datetime.now(timezone.utc)
        content_lower = message.content.lower().strip()

        # 2. GAY DETECT
        if (message.author.id not in config.GAY_WHITELIST_IDS and any(word in content_lower for word in config.GAY_KEYWORDS)):
            user_id = message.author.id
            last_time = self.gay_cooldown.get(user_id)
            
            if last_time is None or (now_utc - last_time).total_seconds() >= 3600:
                self.gay_cooldown[user_id] = now_utc
                try:
                    with open(config.GAY_IMAGE_PATH, "rb") as f:
                        img = discord.File(f, filename="gay.jpg")
                        await message.reply(
                            f"🚨 **GAY DETECTED** 🚨\n"
                            f"👤 **{message.author.display_name}** đã bị trừ **2000 điểm tấn công** 💀\n",
                            file=img
                        )
                        penalty_msg = change_credit(message.author, -10, "Gay detected")
                        await message.channel.send(penalty_msg)
                except Exception as e:
                    print("Gay detect error:", e)

        # 3. TARGET USER
        if message.author.id == config.TARGET_USER_ID:
            try:
                await message.reply("NÍN CMM !!!🤫🤫🤫")
            except: pass

        # 4. SPOUSE LOGIC
        if message.author.id == config.SPOUSE_USER_ID:
            self.last_message_time[config.SPOUSE_USER_ID] = now_utc

        if message.reference:
            try:
                replied_msg = await message.channel.fetch_message(message.reference.message_id)
                if replied_msg.author.id == config.SPOUSE_USER_ID:
                    if not self.check_spouse_cooldown(message.author.id):
                        async def delayed_reply():
                            await asyncio.sleep(60)
                            last_time_active = self.last_message_time.get(config.SPOUSE_USER_ID)
                            if not last_time_active: return
                            if (datetime.now(timezone.utc) - last_time_active).total_seconds() >= 60:
                                if not self.check_spouse_cooldown(message.author.id):
                                    try:
                                        await message.reply("Chờ chồng bà chút ⏳💤 chồng đang bận 😌")
                                        self.spouse_interaction_cooldown[message.author.id] = datetime.now(timezone.utc)
                                    except Exception as e:
                                        print("Delayed reply error:", e)
                        asyncio.create_task(delayed_reply())
            except: pass

async def setup(bot):
    await bot.add_cog(Events(bot))