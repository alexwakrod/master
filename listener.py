import discord
from discord.ext import commands
import logging
import hashlib
import hmac
from datetime import datetime, timezone

from config import (
    MASTER_SECRET, EMOJIS, COLORS, FOOTER_TEXT,
    VERIFY_CHANNEL, LOG_CHANNEL
)
import database as db
import selffix

logger = logging.getLogger(__name__)

class MasterListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.log_channel = None

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            _, _, log_ch, _, _ = await selffix.ensure_verification_setup(self.bot, guild)
            if log_ch:
                self.log_channel = log_ch
                break

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Process verification requests and error reports in #bot-verify."""
        # Ignore messages from MYSELF only – other bots are allowed
        if message.author.id == self.bot.user.id:
            return

        # Only process messages in #bot-verify (case‑insensitive)
        if not isinstance(message.channel, discord.TextChannel):
            return
        if message.channel.name.lower() != VERIFY_CHANNEL.lower():
            return

        # Must have an embed
        if not message.embeds:
            return

        embed = message.embeds[0]

        # ----- VERIFICATION REQUEST: look for field named "License" -----
        license_field = None
        for field in embed.fields:
            if field.name.lower() == "license":
                license_field = field
                break

        if license_field:
            license_code = license_field.value.strip('` ')
            await self.handle_verification(message, license_code)
            return

        # ----- ERROR REPORT: description starts with "ERROR" + License field -----
        if embed.description and embed.description.startswith("ERROR"):
            error_license_field = None
            for field in embed.fields:
                if field.name.lower() == "license":
                    error_license_field = field
                    break
            if error_license_field:
                license_code = error_license_field.value.strip('` ')
                # Extract error message from description (remove "ERROR <code> ")
                error_msg = embed.description.split(maxsplit=2)[-1] if len(embed.description.split()) > 2 else "Unknown error"
                await self.handle_error_report(message, license_code, error_msg)
                return

    async def handle_verification(self, message: discord.Message, license_code: str):
        """Process a verification request, reply with signed embed."""
        is_valid = db.verify_bot_license(license_code)

        if is_valid:
            timestamp = str(int(datetime.now(timezone.utc).timestamp()))
            signature = hmac.new(
                MASTER_SECRET.encode(),
                f"{license_code}:{timestamp}".encode(),
                hashlib.sha256
            ).hexdigest()

            reply_embed = discord.Embed(
                title=f"{EMOJIS['verified']} License Verified",
                color=COLORS['success'],
                timestamp=datetime.now(timezone.utc)
            )
            reply_embed.add_field(name="License", value=f"`{license_code}`", inline=True)
            reply_embed.add_field(name="Timestamp", value=f"`{timestamp}`", inline=True)
            reply_embed.add_field(name="Signature", value=f"`{signature}`", inline=False)
            reply_embed.add_field(
                name="Instructions",
                value="Your bot is now authorized. Use `/fetch_patches` to get updates.",
                inline=False
            )
            reply_embed.set_footer(text=FOOTER_TEXT)

            await message.reply(embed=reply_embed, mention_author=False)
            logger.info(f"✅ Verified bot license: {license_code}")
        else:
            reply_embed = discord.Embed(
                title=f"{EMOJIS['error']} License Invalid",
                description=f"License `{license_code}` is not active or does not exist.",
                color=COLORS['error'],
                timestamp=datetime.now(timezone.utc)
            )
            reply_embed.set_footer(text=FOOTER_TEXT)
            await message.reply(embed=reply_embed, mention_author=False)
            logger.warning(f"❌ Invalid bot license attempt: {license_code}")

    async def handle_error_report(self, message: discord.Message, license_code: str, error_msg: str):
        """Log an error report, acknowledge, and forward to #bot-logs."""
        db.log_bot_error(license_code, error_msg)

        # Acknowledge receipt
        ack_embed = discord.Embed(
            title=f"{EMOJIS['info']} Error Logged",
            description=f"Error from license `{license_code}` has been recorded.",
            color=COLORS['info'],
            timestamp=datetime.now(timezone.utc)
        )
        ack_embed.set_footer(text=FOOTER_TEXT)
        await message.reply(embed=ack_embed, mention_author=False)

        # Forward to dedicated log channel if available
        if self.log_channel:
            log_embed = discord.Embed(
                title=f"{EMOJIS['error']} Bot Error Report",
                description=f"**Error:** {error_msg}",
                color=COLORS['error'],
                timestamp=datetime.now(timezone.utc)
            )
            log_embed.add_field(name="License", value=f"`{license_code}`", inline=True)
            log_embed.add_field(
                name="Reporter",
                value=f"{message.author.mention} (`{message.author.id}`)",
                inline=True
            )
            log_embed.set_footer(text=FOOTER_TEXT)
            await self.log_channel.send(embed=log_embed)

async def setup(bot):
    await bot.add_cog(MasterListener(bot))