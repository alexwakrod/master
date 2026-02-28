import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime

from config import EMOJIS, COLORS, FOOTER_TEXT
import database as db
import selffix

logger = logging.getLogger(__name__)

class MasterCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ---------- Admin Permission Check ----------
    def is_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator

    # ---------- /registerbot – Generate a new handshake bot license ----------
    @app_commands.command(name="registerbot", description="Generate a new bot license (admin only)")
    @app_commands.describe(
        bot_name="Name of the handshake bot",
        owner_id="(Optional) Discord user ID of the bot's owner"
    )
    async def registerbot(self, interaction: discord.Interaction, bot_name: str, owner_id: str = None):
        if not self.is_admin(interaction):
            embed = discord.Embed(
                title=f"{EMOJIS['error']} Permission Denied",
                description="This command is for administrators only.",
                color=COLORS['error']
            ).set_footer(text=FOOTER_TEXT)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Parse owner_id if provided
        owner_id_int = None
        if owner_id:
            try:
                owner_id_int = int(owner_id)
            except ValueError:
                embed = discord.Embed(
                    title=f"{EMOJIS['error']} Invalid Owner ID",
                    description="Owner ID must be a valid Discord user ID (numbers only).",
                    color=COLORS['error']
                ).set_footer(text=FOOTER_TEXT)
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

        try:
            license_code = db.register_bot_license(bot_name, owner_id_int)
        except Exception as e:
            logger.error(f"Failed to register bot license: {e}")
            embed = discord.Embed(
                title=f"{EMOJIS['error']} Registration Failed",
                description="An internal database error occurred. Check logs.",
                color=COLORS['error']
            ).set_footer(text=FOOTER_TEXT)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title=f"{EMOJIS['success']} Bot License Created",
            description=f"**Bot Name:** {bot_name}\n**License Code:** `{license_code}`",
            color=COLORS['success'],
            timestamp=datetime.utcnow()
        )
        if owner_id_int:
            embed.add_field(name="Owner ID", value=f"`{owner_id_int}`", inline=False)
        embed.add_field(
            name="📋 Instructions",
            value=(
                "1. Copy this license code into your handshake bot's `config.py`.\n"
                "2. Run the handshake bot – it will automatically verify in `#bot-verify`.\n"
                "3. The license is now active and ready for use."
            ),
            inline=False
        )
        embed.set_footer(text=FOOTER_TEXT)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ---------- /clearlicense – Deactivate a bot license ----------
    @app_commands.command(name="clearlicense", description="Deactivate a bot license (admin only)")
    @app_commands.describe(license_code="The license code to deactivate")
    async def clearlicense(self, interaction: discord.Interaction, license_code: str):
        if not self.is_admin(interaction):
            embed = discord.Embed(
                title=f"{EMOJIS['error']} Permission Denied",
                description="This command is for administrators only.",
                color=COLORS['error']
            ).set_footer(text=FOOTER_TEXT)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            db.deactivate_bot_license(license_code)
            embed = discord.Embed(
                title=f"{EMOJIS['success']} License Deactivated",
                description=f"License `{license_code}` has been deactivated.",
                color=COLORS['success'],
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text=FOOTER_TEXT)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to deactivate license {license_code}: {e}")
            embed = discord.Embed(
                title=f"{EMOJIS['error']} Deactivation Failed",
                description="An internal database error occurred.",
                color=COLORS['error']
            ).set_footer(text=FOOTER_TEXT)
            await interaction.followup.send(embed=embed, ephemeral=True)

    # ---------- /patchbot – Post a patch file to #bot-patches ----------
    @app_commands.command(name="patchbot", description="Post a patch file for a specific bot license (admin only)")
    @app_commands.describe(
        license_code="License code of the target bot",
        filename="Name to save the file as on the bot's side",
        file="The file to attach"
    )
    async def patchbot(self, interaction: discord.Interaction, license_code: str, filename: str, file: discord.Attachment):
        if not self.is_admin(interaction):
            embed = discord.Embed(
                title=f"{EMOJIS['error']} Permission Denied",
                description="This command is for administrators only.",
                color=COLORS['error']
            ).set_footer(text=FOOTER_TEXT)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Verify that the license exists (optional, but good practice)
        if not db.verify_bot_license(license_code):  # verify just checks existence, doesn't update timestamp
            embed = discord.Embed(
                title=f"{EMOJIS['error']} Invalid License",
                description=f"License `{license_code}` is not active or does not exist.",
                color=COLORS['error']
            ).set_footer(text=FOOTER_TEXT)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Ensure patch channel exists
        guild = interaction.guild
        _, _, _, patch_ch = await selffix.ensure_verification_setup(self.bot, guild)
        if not patch_ch:
            embed = discord.Embed(
                title=f"{EMOJIS['error']} Channel Error",
                description="Could not find or create the `#bot-patches` channel.",
                color=COLORS['error']
            ).set_footer(text=FOOTER_TEXT)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Post the file with clear label
        content = f"PATCH {license_code} {filename}"
        await patch_ch.send(content=content, file=await file.to_file())

        embed = discord.Embed(
            title=f"{EMOJIS['patch']} Patch Posted",
            description=f"Patch `{filename}` for license `{license_code}` has been posted in #{patch_ch.name}.",
            color=COLORS['success'],
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=FOOTER_TEXT)
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(MasterCommands(bot))