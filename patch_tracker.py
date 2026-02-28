import discord
from discord.ext import commands
import logging
from datetime import datetime, timezone

from config import ADMIN_USER_ID, PATCH_CHANNEL
import database as db

logger = logging.getLogger(__name__)

class PatchTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.patch_channel = None

    @commands.Cog.listener()
    async def on_ready(self):
        # Find the patch channel
        for guild in self.bot.guilds:
            channel = discord.utils.get(guild.channels, name=PATCH_CHANNEL)
            if channel:
                self.patch_channel = channel
                break
        if self.patch_channel:
            logger.info(f"✅ Patch tracker monitoring #{PATCH_CHANNEL}")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if not self.patch_channel:
            return
        if payload.channel_id != self.patch_channel.id:
            return
        if payload.user_id == self.bot.user.id:
            return

        channel = self.bot.get_channel(payload.channel_id)
        if not channel:
            return
        message = await channel.fetch_message(payload.message_id)
        if not message:
            return

        # Check if this message is a patch (sent by master bot)
        if message.author.id != self.bot.user.id:
            return
        if not message.content.startswith("PATCH "):
            return

        # Parse the patch message: "PATCH <license> <filename>"
        parts = message.content.split(maxsplit=2)
        if len(parts) < 3:
            return
        _, license_code, filename = parts

        # Get bot name
        bot_name = db.get_bot_name_by_license(license_code) or "Unknown"

        # Log the download
        db.log_patch_download(license_code, bot_name, filename)

        # Optionally notify admin
        admin = self.bot.get_user(ADMIN_USER_ID)
        if admin:
            embed = discord.Embed(
                title="📥 Patch Downloaded",
                description=f"**Bot:** {bot_name}\n**License:** `{license_code}`\n**File:** `{filename}`",
                color=0x00ff00,
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Downloaded by", value=f"<@{payload.user_id}>")
            try:
                await admin.send(embed=embed)
            except:
                pass

async def setup(bot):
    await bot.add_cog(PatchTracker(bot))