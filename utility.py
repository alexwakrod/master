import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime

from config import EMOJIS, COLORS, FOOTER_TEXT

logger = logging.getLogger(__name__)

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = datetime.utcnow()

    @app_commands.command(name="help", description="Show available commands and information")
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"{EMOJIS['info']} Master Bot - Help & Commands",
            description="I am the central authority for all handshake bots. Below are my commands:",
            color=COLORS['primary'],
            timestamp=datetime.utcnow()
        )

        # Admin Commands
        embed.add_field(
            name=f"{EMOJIS['bot']} `/runbots`",
            value="Show all registered handshake bots and their online status.",
            inline=False
        )
        embed.add_field(
            name=f"{EMOJIS['error']} `/clearlicense <license_code>`",
            value="Deactivate a bot license. (Admin only)",
            inline=False
        )
        embed.add_field(
            name=f"{EMOJIS['patch']} `/patchbot <license_code> <filename> <file>`",
            value="Post a patch file to `#bot-patches` for a specific bot.",
            inline=False
        )
        embed.add_field(
            name=f"{EMOJIS['info']} `/help`",
            value="Show this help message.",
            inline=False
        )

        # System Info
        embed.add_field(
            name="📊 System Information",
            value=(
                f"**Uptime:** <t:{int(self.start_time.timestamp())}:R>\n"
                f"**Latency:** `{round(self.bot.latency * 1000)}ms`\n"
                f"**Servers:** `{len(self.bot.guilds)}`"
            ),
            inline=False
        )

        # Handshake Bot Setup
        embed.add_field(
            name="🤝 Handshake Bot Setup",
            value=(
                "1. Obtain a valid license code from the database.\n"
                "2. Configure your handshake bot with the license and Master Bot ID.\n"
                "3. Run the bot – it will automatically verify in `#bot-verify`.\n"
                "4. Use `/fetch_patches` on the handshake bot to receive updates."
            ),
            inline=False
        )

        embed.set_footer(text=FOOTER_TEXT)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="ping", description="Check the bot's latency")
    async def ping(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"{EMOJIS['info']} Pong!",
            description=f"**Latency:** `{round(self.bot.latency * 1000)}ms`",
            color=COLORS['success'],
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=FOOTER_TEXT)
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Utility(bot))
