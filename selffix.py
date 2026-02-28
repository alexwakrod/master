import discord
import logging
from config import VERIFY_CATEGORY, VERIFY_CHANNEL, LOG_CHANNEL, PATCH_CHANNEL, SOLUTION_LOG_CHANNEL

logger = logging.getLogger(__name__)

async def ensure_verification_setup(bot, guild: discord.Guild):
    """Create or retrieve the verification category and all four channels."""
    if not guild:
        return None, None, None, None, None

    # ---------- Category ----------
    category = discord.utils.get(guild.categories, name=VERIFY_CATEGORY)
    if not category:
        if not guild.me.guild_permissions.manage_channels:
            logger.error(f"Missing MANAGE_CHANNELS permission in {guild.name}")
            return None, None, None, None, None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        category = await guild.create_category(VERIFY_CATEGORY, overwrites=overwrites)
        logger.info(f"✅ Created category '{VERIFY_CATEGORY}' in {guild.name}")

    # ---------- Verification channel (bot-verify) ----------
    verify_channel = discord.utils.get(category.channels, name=VERIFY_CHANNEL)
    if not verify_channel:
        verify_channel = await category.create_text_channel(
            VERIFY_CHANNEL,
            overwrites=category.overwrites
        )
        logger.info(f"✅ Created channel #{VERIFY_CHANNEL} in {guild.name}")

    # ---------- Log channel (bot-logs) ----------
    log_channel = discord.utils.get(category.channels, name=LOG_CHANNEL)
    if not log_channel:
        log_channel = await category.create_text_channel(
            LOG_CHANNEL,
            overwrites=category.overwrites
        )
        logger.info(f"✅ Created channel #{LOG_CHANNEL} in {guild.name}")

    # ---------- Patch channel (bot-patches) ----------
    patch_channel = discord.utils.get(category.channels, name=PATCH_CHANNEL)
    if not patch_channel:
        patch_channel = await category.create_text_channel(
            PATCH_CHANNEL,
            overwrites=category.overwrites
        )
        logger.info(f"✅ Created channel #{PATCH_CHANNEL} in {guild.name}")

    # ---------- Solution logs channel (solution-logs) ----------
    solution_channel = discord.utils.get(category.channels, name=SOLUTION_LOG_CHANNEL)
    if not solution_channel:
        solution_channel = await category.create_text_channel(
            SOLUTION_LOG_CHANNEL,
            overwrites=category.overwrites
        )
        logger.info(f"✅ Created channel #{SOLUTION_LOG_CHANNEL} in {guild.name}")

    return category, verify_channel, log_channel, patch_channel, solution_channel

async def self_fix_all(bot):
    """Run ensure_verification_setup for all guilds the bot is in."""
    logger.info("🛠️ Running verification self‑fix for all guilds...")
    for guild in bot.guilds:
        await ensure_verification_setup(bot, guild)
    logger.info("✅ Verification self‑fix completed.")
