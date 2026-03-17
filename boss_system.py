import discord
from discord.ext import commands
from datetime import datetime, timezone, timedelta
import random

BOSS_CHANNEL_ID = 1483370802760908993


class BossSystem(commands.Cog):
    def __init__(self, bot, boss_col, users_col, ensure_user, change_credit, get_user):
        self.bot = bot
        self.boss_col = boss_col
        self.users_col = users_col
        self.ensure_user = ensure_user
        self.change_credit = change_credit
        self.get_user = get_user
        self.MAX_MANA = 100
        self.MANA_GAIN_ATTACK = (5, 15)
        self.MANA_GAIN_HIT = (3, 10)
        self.SKILL_COST = 40

        self.COOLDOWN = 30
        self.DEATH_COOLDOWN = 7200  # 2h

    # ================= HELPER =================

    def get_boss(self):
        return self.boss_col.find_one({"active": True})

    def check_channel(self, ctx):
        return ctx.channel.id == BOSS_CHANNEL_ID

    def get_player(self, boss, user_id):
        return boss["players"].get(str(user_id))

    def update_boss(self, boss):
        self.boss_col.update_one({"_id": boss["_id"]}, {"$set": boss})

    # ================= COMMAND GROUP =================

    @commands.group(name="bb", invoke_without_command=True)
    async def bb(self, ctx):
        if not self.check_channel(ctx):
            return

        await ctx.send(
            "🐉 **BOSS BATTLE**\n"
            "`!bb create <name> <hp>`\n"
            "`!bb join`\n"
            "`!bb attack`\n"
            "`!bb skill`\n"
            "`!bb info`"
        )

    # ================= CREATE =================

    @bb.command(name="create")
    async def create(self, ctx, name: str, hp: int, reward: int):
        if not self.check_channel(ctx):
            return

        if self.get_boss():
            await ctx.send("⚠️ Đã có boss rồi!")
            return

        img = None
        if ctx.message.attachments:
            img = ctx.message.attachments[0].url

        boss = {
            "name": name,
            "hp": hp,
            "max_hp": hp,
            "reward": reward,  # 👈 THÊM
            "image": img,
            "players": {},
            "active": True,
            "created_at": datetime.now(timezone.utc)
        }

        self.boss_col.insert_one(boss)

        embed = discord.Embed(
            title=f"🐉 {name} xuất hiện!",
            description=f"HP: `{hp}`\n💰 Reward: `{reward}` SC",
            color=0xff0000
        )
        if img:
            embed.set_image(url=img)

        await ctx.send(embed=embed)

    # ================= JOIN =================

    @bb.command(name="join")
    async def join(self, ctx):
        if not self.check_channel(ctx):
            return

        boss = self.get_boss()
        if not boss:
            await ctx.send("❌ Không có boss.")
            return

        user_id = str(ctx.author.id)

        if user_id in boss["players"]:
            await ctx.send("⚠️ Bạn đã tham gia.")
            return

        now = datetime.now(timezone.utc)

        # check chết
        user_data = self.get_user(ctx.author.id) or {}
        death_time = user_data.get("boss_death")

        if death_time:
            if now < death_time:
                remain = int((death_time - now).total_seconds() / 60)
                await ctx.send(f"💀 Bạn đang chết. Chờ {remain} phút.")
                return

        boss["players"][user_id] = {
            "hp": 100,
            "mana": 0,  # 👈 THÊM
            "last_attack": None
        }

        self.update_boss(boss)

        await ctx.send(f"⚔️ {ctx.author.mention} đã tham gia!")

    # ================= ATTACK =================

    @bb.command(name="attack")
    async def attack(self, ctx):
        if not self.check_channel(ctx):
            return

        boss = self.get_boss()
        if not boss:
            return

        player = self.get_player(boss, ctx.author.id)
        if not player:
            await ctx.send("❌ Bạn chưa join.")
            return

        now = datetime.now(timezone.utc)

        if player["last_attack"]:
            elapsed = (now - player["last_attack"]).total_seconds()
            if elapsed < self.COOLDOWN:
                await ctx.send(f"⏳ Chờ {int(self.COOLDOWN - elapsed)}s")
                return

        dmg = random.randint(20, 50)
        boss["hp"] -= dmg

        # gain mana khi attack
        mana_gain = random.randint(*self.MANA_GAIN_ATTACK)
        player["mana"] = min(self.MAX_MANA, player.get("mana", 0) + mana_gain)
        # boss phản damage
        boss_dmg = random.randint(10, 30)
        player["hp"] -= boss_dmg

        # gain mana khi bị đánh
        mana_gain_hit = random.randint(*self.MANA_GAIN_HIT)
        player["mana"] = min(self.MAX_MANA, player["mana"] + mana_gain_hit)

        player["last_attack"] = now

        # chết
        if player["hp"] <= 0:
            self.users_col.update_one(
                {"user_id": ctx.author.id},
                {"$set": {"boss_death": now + timedelta(seconds=self.DEATH_COOLDOWN)}}
            )
            del boss["players"][str(ctx.author.id)]
            await ctx.send(f"💀 {ctx.author.display_name} đã chết!")
        else:
            boss["players"][str(ctx.author.id)] = player

        # boss chết
        if boss["hp"] <= 0:
            reward = boss.get("reward", 200)
            for uid in boss["players"]:
                member = ctx.guild.get_member(int(uid))
                if member:
                    self.change_credit(member, reward, "Boss reward")

            await ctx.send(f"🏆 Boss bị tiêu diệt! Mỗi người +{reward} SC")
            self.boss_col.delete_many({})
            return

        self.update_boss(boss)

        await ctx.send(
            f"⚔️ {ctx.author.display_name} gây `{dmg}` dmg\n"
            f"🐉 Boss còn `{boss['hp']}` HP\n"
            f"❤️ HP: `{player['hp']}` | 🔮 Mana: `{player['mana']}`"
        )

    # ================= SKILL =================

    @bb.command(name="skill")
    async def skill(self, ctx):
        if not self.check_channel(ctx):
            return

        boss = self.get_boss()
        if not boss:
            await ctx.send("❌ Không có boss.")
            return

        player = self.get_player(boss, ctx.author.id)
        if not player:
            await ctx.send("❌ Bạn chưa join.")
            return

        now = datetime.now(timezone.utc)

        # ================= COOLDOWN =================
        if player.get("last_attack"):
            elapsed = (now - player["last_attack"]).total_seconds()
            if elapsed < self.COOLDOWN:
                await ctx.send(f"⏳ Chờ {int(self.COOLDOWN - elapsed)}s")
                return

        # ================= MANA CHECK =================
        if player.get("mana", 0) < self.SKILL_COST:
            await ctx.send(
                f"❌ Không đủ mana!\n"
                f"🔮 Hiện tại: `{player.get('mana', 0)}` / `{self.SKILL_COST}`"
            )
            return

        # ================= TRỪ MANA =================
        player["mana"] -= self.SKILL_COST

        # ================= DAMAGE =================
        dmg = random.randint(50, 120)
        boss["hp"] -= dmg

        # ================= BOSS PHẢN DAMAGE =================
        boss_dmg = random.randint(15, 35)
        player["hp"] -= boss_dmg

        # ================= GAIN MANA NHẸ =================
        mana_gain = random.randint(2, 6)
        player["mana"] = min(self.MAX_MANA, player["mana"] + mana_gain)

        # ================= UPDATE TIME =================
        player["last_attack"] = now

        # ================= PLAYER CHẾT =================
        if player["hp"] <= 0:
            self.users_col.update_one(
                {"user_id": ctx.author.id},
                {"$set": {"boss_death": now + timedelta(seconds=self.DEATH_COOLDOWN)}}
            )

            del boss["players"][str(ctx.author.id)]

            self.update_boss(boss)

            await ctx.send(
                f"🔥 {ctx.author.display_name} dùng SKILL gây `{dmg}` dmg\n"
                f"💀 Nhưng đã bị boss phản damage `{boss_dmg}` và chết!"
            )
            return

        # ================= BOSS CHẾT =================
        if boss["hp"] <= 0:
            reward = boss.get("reward", 200)

            for uid in boss["players"]:
                member = ctx.guild.get_member(int(uid))
                if member:
                    self.change_credit(member, reward, "Boss reward")

            await ctx.send(
                f"🔥 {ctx.author.display_name} tung SKILL `{dmg}` dmg\n"
                f"🏆 Boss bị tiêu diệt!\n"
                f"💰 Mỗi người nhận `{reward}` SC"
            )

            self.boss_col.delete_many({})
            return

        # ================= SAVE =================
        boss["players"][str(ctx.author.id)] = player
        self.update_boss(boss)

        # ================= RESPONSE =================
        await ctx.send(
            f"🔥 {ctx.author.display_name} dùng SKILL!\n"
            f"💥 Damage: `{dmg}`\n"
            f"🐉 Boss HP: `{boss['hp']}`\n"
            f"❤️ HP: `{player['hp']}`\n"
            f"🔮 Mana: `{player['mana']}`"
        )


    # ================= INFO =================

    @bb.command(name="info")
    async def info(self, ctx):
        if not self.check_channel(ctx):
            return

        boss = self.get_boss()
        if not boss:
            await ctx.send("❌ Không có boss.")
            return

        embed = discord.Embed(
            title=f"🐉 {boss['name']}",
            description=f"HP: `{boss['hp']}/{boss['max_hp']}`\n💰 Reward: `{boss.get('reward', 0)}`",
            color=0xff0000
        )

        if boss["image"]:
            embed.set_image(url=boss["image"])

        embed.add_field(
            name="👥 Người chơi",
            value=f"{len(boss['players'])}",
            inline=False
        )

        await ctx.send(embed=embed)

