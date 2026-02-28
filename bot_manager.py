import discord
from discord import app_commands
from discord.ext import commands
import logging
import os
import subprocess
import signal
import re
import asyncio
from datetime import datetime, timezone, timedelta

from config import (
    EMOJIS, COLORS, FOOTER_TEXT,
    BOTS_BASE_PATH, ADMIN_USER_ID, MASTER_BOT_PATH
)
import database as db

logger = logging.getLogger(__name__)

# Try to import psutil for better process detection
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil not installed. Install with: pip install psutil")

# ---------- Helper functions ----------
def get_bot_directories():
    dirs = []
    try:
        for item in os.listdir(BOTS_BASE_PATH):
            full = os.path.join(BOTS_BASE_PATH, item)
            config_path = os.path.join(full, "config.py")
            if os.path.isdir(full) and os.path.isfile(config_path):
                dirs.append(full)
    except Exception as e:
        logger.error(f"Error scanning bot directories: {e}")
    return dirs

def extract_license_from_config(config_path):
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        match = re.search(r'LICENSE_CODE\s*=\s*["\']([^"\']+)["\']', content)
        return match.group(1) if match else None
    except Exception as e:
        logger.error(f"Error reading {config_path}: {e}")
        return None

def extract_token_from_config(config_path):
    """Extract bot token from config.py (used for presence check)."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        match = re.search(r'BOT_TOKEN\s*=\s*os\.getenv\(\'BOT_TOKEN\',\s*[\'"]?([^\'"]+)[\'"]?\)', content)
        if not match:
            match = re.search(r'BOT_TOKEN\s*=\s*[\'"]([^\'"]+)[\'"]', content)
        return match.group(1) if match else None
    except Exception as e:
        logger.error(f"Error extracting token from {config_path}: {e}")
        return None

def get_pid_file(bot_path):
    return os.path.join(bot_path, "bot.pid")

def is_process_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, OSError):
        return False

def find_processes_by_path(bot_path):
    """Return list of PIDs of processes whose cwd or cmdline contains bot_path."""
    if not PSUTIL_AVAILABLE:
        return []
    pids = []
    try:
        for proc in psutil.process_iter(['pid', 'cwd', 'cmdline']):
            try:
                if proc.info['cwd'] == bot_path:
                    pids.append(proc.info['pid'])
                elif proc.info['cmdline'] and bot_path in ' '.join(proc.info['cmdline']):
                    pids.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        logger.error(f"Error scanning processes: {e}")
    return pids

async def kill_process(pid):
    """Terminate a process by PID asynchronously."""
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(5):
            if not is_process_alive(pid):
                return True
            await asyncio.sleep(0.5)
        os.kill(pid, signal.SIGKILL)
        return not is_process_alive(pid)
    except Exception as e:
        logger.error(f"Failed to kill PID {pid}: {e}")
        return False

async def check_discord_presence(bot_path):
    """
    Attempt to fetch the bot's user info using its token.
    If successful, the bot is online (its token is valid and Discord accepts it).
    """
    token = extract_token_from_config(os.path.join(bot_path, "config.py"))
    if not token:
        return False
    headers = {"Authorization": f"Bot {token}"}
    url = "https://discord.com/api/v10/users/@me"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    return True
                else:
                    return False
    except Exception as e:
        logger.error(f"Presence check failed for {bot_path}: {e}")
        return False

def is_bot_running(bot_path, license_code=None):
    """
    Determine if a bot is online using multiple layers:
    1. Process-based detection (psutil + PID file)
    2. last_verified timestamp (within 5 minutes)
    """
    # Layer 1: Process detection
    pids = find_processes_by_path(bot_path)
    if pids:
        return True

    pid_file = get_pid_file(bot_path)
    if os.path.isfile(pid_file):
        try:
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            if is_process_alive(pid):
                return True
            else:
                os.remove(pid_file)
        except (ValueError, OSError):
            try:
                os.remove(pid_file)
            except:
                pass

    # Layer 2: last_verified
    if license_code:
        conn = db.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT last_verified FROM bot_licenses WHERE license_code = ?", (license_code,))
            row = cursor.fetchone()
            if row and row.last_verified:
                last_verified = row.last_verified.replace(tzinfo=timezone.utc) if row.last_verified.tzinfo is None else row.last_verified
                if datetime.now(timezone.utc) - last_verified < timedelta(minutes=5):
                    return True
        except Exception as e:
            logger.error(f"Error checking last_verified: {e}")
        finally:
            cursor.close()
            conn.close()

    return False

async def start_bot(bot_path, license_code, bot_name, force=False):
    """
    Start a bot. If force=True, ignore running status and kill any existing processes.
    """
    if not force and is_bot_running(bot_path, license_code):
        return False, "Already running", None

    # Kill any existing process from this path
    pids = find_processes_by_path(bot_path)
    for pid in pids:
        await kill_process(pid)

    pid_file = get_pid_file(bot_path)
    if os.path.exists(pid_file):
        try:
            os.remove(pid_file)
        except:
            pass

    try:
        proc = await asyncio.create_subprocess_exec(
            'python3', 'main.py',
            cwd=bot_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True
        )
        for _ in range(10):
            await asyncio.sleep(0.5)
            if proc.returncode is not None:
                return False, f"Process exited with code {proc.returncode}", None
            if os.path.exists(pid_file):
                db.set_license_path(license_code, bot_path)
                return True, proc.pid, proc
        if proc.returncode is None:
            with open(pid_file, 'w') as f:
                f.write(str(proc.pid))
            db.set_license_path(license_code, bot_path)
            return True, proc.pid, proc
        return False, "Start timeout", None
    except Exception as e:
        logger.error(f"Failed to start bot in {bot_path}: {e}")
        return False, str(e), None

async def stop_bot(bot_path, license_code):
    """Stop a bot and clear its license path."""
    pids = find_processes_by_path(bot_path)
    killed = False
    for pid in pids:
        if await kill_process(pid):
            killed = True

    pid_file = get_pid_file(bot_path)
    if os.path.isfile(pid_file) and not killed:
        try:
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
            for _ in range(10):
                await asyncio.sleep(0.5)
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    os.remove(pid_file)
                    killed = True
                    break
            if not killed:
                os.kill(pid, signal.SIGKILL)
                os.remove(pid_file)
                killed = True
        except ProcessLookupError:
            if os.path.exists(pid_file):
                os.remove(pid_file)
            killed = True
        except Exception as e:
            logger.error(f"Error stopping bot via PID file: {e}")

    if license_code:
        db.set_license_path(license_code, None)

    if killed:
        return True, "Stopped"
    return False, "No running process found"

# ---------- Views ----------
class BotSelect(discord.ui.Select):
    def __init__(self, bot_data):
        self.bot_data = bot_data
        options = []
        for i, bot in enumerate(bot_data):
            options.append(discord.SelectOption(
                label=bot['name'],
                value=str(i),
                description=f"License: {bot['license'] or 'None'}"
            ))
        super().__init__(placeholder="Choose bots to manage...", min_values=1, max_values=len(options), options=options)

    async def callback(self, interaction):
        await interaction.response.defer()
        self.view.selected_indices = [int(val) for val in self.values]
        self.view.current_phase = 3
        await self.view.update_embed(interaction)

class ActionView(discord.ui.View):
    def __init__(self, parent_view):
        super().__init__(timeout=60)
        self.parent_view = parent_view

    @discord.ui.button(label="Start Selected", style=discord.ButtonStyle.success)
    async def start_button(self, interaction, button):
        await interaction.response.defer()
        self.parent_view.action = "start"
        self.parent_view.current_phase = 6
        await self.parent_view.execute_action(interaction, force=False)

    @discord.ui.button(label="Force Start", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def force_start_button(self, interaction, button):
        await interaction.response.defer()
        self.parent_view.action = "start"
        self.parent_view.current_phase = 6
        await self.parent_view.execute_action(interaction, force=True)

    @discord.ui.button(label="Stop Selected", style=discord.ButtonStyle.danger)
    async def stop_button(self, interaction, button):
        await interaction.response.defer()
        self.parent_view.action = "stop"
        self.parent_view.current_phase = 6
        await self.parent_view.execute_action(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction, button):
        await interaction.response.defer()
        self.parent_view.current_phase = 5
        await self.parent_view.update_embed(interaction)

class BotManagerView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=300)
        self.bot = bot
        self.directories = get_bot_directories()
        self.bot_data = []
        self.selected_indices = []
        self.current_phase = 1
        self.message = None
        self.action = None
        self.load_bots()

    def load_bots(self):
        self.bot_data = []
        for path in self.directories:
            name = os.path.basename(path)
            license_code = extract_license_from_config(os.path.join(path, "config.py"))
            verified = db.verify_bot_license(license_code) if license_code else False
            running = is_bot_running(path, license_code)
            self.bot_data.append({
                "path": path,
                "name": name,
                "license": license_code,
                "verified": verified,
                "running": running
            })

    async def update_embed(self, interaction):
        phase_colors = {
            1: COLORS['info'],
            2: COLORS['primary'],
            3: COLORS['warning'],
            4: COLORS['role'],
            5: COLORS['warning'],
            6: COLORS['success']
        }
        color = phase_colors.get(self.current_phase, COLORS['primary'])

        embed = discord.Embed(
            title=f"🤖 Bot Manager – Phase {self.current_phase}/6",
            color=color,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=FOOTER_TEXT)

        progress = "█" * self.current_phase + "░" * (6 - self.current_phase)
        embed.add_field(name="Progress", value=progress, inline=False)

        self.clear_items()

        if self.current_phase == 1:
            embed.description = "**Detected bots:**"
            for i, bot in enumerate(self.bot_data):
                status = "✅" if bot['running'] else "⏹️"
                verified = "🔐" if bot['verified'] else "❌"
                embed.add_field(
                    name=f"{i+1}. {bot['name']}",
                    value=f"{verified} License: `{bot['license'] or 'N/A'}` {status}",
                    inline=False
                )
            embed.add_field(name="Next", value="Press **Next** to select bots to manage.", inline=False)
            self.add_item(self.refresh_button)

        elif self.current_phase == 2:
            embed.description = "**Select bots to manage** (use the dropdown below)."
            select = BotSelect(self.bot_data)
            self.add_item(select)

        elif self.current_phase == 3:
            embed.description = "**License verification results:**"
            for i in self.selected_indices:
                bot = self.bot_data[i]
                status = "✅ Verified" if bot['verified'] else "❌ Not registered"
                embed.add_field(name=bot['name'], value=status, inline=False)

        elif self.current_phase == 4:
            embed.description = "**Current running status:**"
            for i in self.selected_indices:
                bot = self.bot_data[i]
                status = "🟢 Running" if bot['running'] else "🔴 Stopped"
                embed.add_field(name=bot['name'], value=status, inline=False)

        elif self.current_phase == 5:
            embed.description = "**Choose action:** Start or stop the selected bots?"
            selected_names = [self.bot_data[i]['name'] for i in self.selected_indices]
            embed.add_field(name="Selected bots", value="\n".join(selected_names), inline=False)
            action_view = ActionView(self)
            for child in action_view.children:
                self.add_item(child)

        elif self.current_phase == 6:
            embed.description = "**Action executed.** Results will appear here."

        if self.current_phase > 1 and self.current_phase != 6:
            self.add_item(self.prev_button)
        if self.current_phase < 5 and self.current_phase != 2:
            self.add_item(self.next_button)
        if self.current_phase not in (2, 5, 6):
            self.add_item(self.cancel_button)
        if self.current_phase == 6:
            self.add_item(self.finish_button)

        await interaction.edit_original_response(embed=embed, view=self)

    async def execute_action(self, interaction, force=False):
        results = []
        for i in self.selected_indices:
            bot = self.bot_data[i]
            if self.action == "start":
                success, msg, proc = await start_bot(bot['path'], bot['license'], bot['name'], force=force)
                if success:
                    results.append(f"{bot['name']}: ✅ Started (PID {msg})")
                    error_monitor = self.bot.get_cog('ErrorMonitor')
                    if error_monitor:
                        error_monitor.register_bot(bot['path'], proc, bot['name'], bot['license'])
                else:
                    results.append(f"{bot['name']}: ❌ {msg}")
            else:  # stop
                if bot['running']:
                    success, msg = await stop_bot(bot['path'], bot['license'])
                    if success:
                        results.append(f"{bot['name']}: ✅ {msg}")
                        error_monitor = self.bot.get_cog('ErrorMonitor')
                        if error_monitor:
                            error_monitor.unregister_bot(bot['path'])
                    else:
                        results.append(f"{bot['name']}: ❌ {msg}")
                else:
                    results.append(f"{bot['name']}: ⏹️ Already stopped")

        self.load_bots()

        embed = discord.Embed(
            title=f"🤖 Bot Manager – Phase 6/6",
            color=COLORS['success'],
            timestamp=datetime.now(timezone.utc)
        )
        embed.description = "\n".join(results)
        embed.set_footer(text=FOOTER_TEXT)

        self.clear_items()
        self.add_item(self.finish_button)

        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Refresh Status", style=discord.ButtonStyle.primary, emoji="🔄")
    async def refresh_button(self, interaction, button):
        await interaction.response.defer()
        self.load_bots()
        await self.update_embed(interaction)

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction, button):
        await interaction.response.defer()
        if self.current_phase > 1:
            self.current_phase -= 1
            await self.update_embed(interaction)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction, button):
        await interaction.response.defer()
        if self.current_phase < 5:
            self.current_phase += 1
            await self.update_embed(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction, button):
        await interaction.response.defer()
        await interaction.edit_original_response(content="Cancelled.", embed=None, view=None)

    @discord.ui.button(label="Finish", style=discord.ButtonStyle.success)
    async def finish_button(self, interaction, button):
        await interaction.response.defer()
        await interaction.edit_original_response(content="Done.", embed=None, view=None)

# ---------- Cog ----------
class BotManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.monitored_paths = set()

    async def restart_bot_by_path(self, bot_path):
        name = os.path.basename(bot_path)
        license_code = extract_license_from_config(os.path.join(bot_path, "config.py"))
        if not license_code:
            logger.error(f"No license found for {bot_path}")
            return False

        success_stop, msg = await stop_bot(bot_path, license_code)
        if not success_stop:
            logger.error(f"Stop failed for {bot_path}: {msg}")
            return False

        await asyncio.sleep(2)
        success_start, pid, proc = await start_bot(bot_path, license_code, name, force=True)
        if success_start:
            error_monitor = self.bot.get_cog('ErrorMonitor')
            if error_monitor:
                error_monitor.register_bot(bot_path, proc, name, license_code)
                self.monitored_paths.add(bot_path)
            logger.info(f"✅ Restarted {name} (PID {pid})")
            return True
        else:
            logger.error(f"Start failed for {bot_path}: {pid}")
            return False

    @app_commands.command(name="runbots", description="Interactive wizard to manage all handshake bots")
    @app_commands.default_permissions(administrator=True)
    async def runbots(self, interaction):
        view = BotManagerView(self.bot)
        await interaction.response.send_message("Loading bot directories...", view=view, ephemeral=True)

    @app_commands.command(name="botstatus", description="Show status of all handshake bots")
    @app_commands.default_permissions(administrator=True)
    async def botstatus(self, interaction):
        dirs = get_bot_directories()
        embed = discord.Embed(
            title="🤖 Handshake Bot Status",
            color=COLORS['info'],
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=FOOTER_TEXT)

        for path in dirs:
            name = os.path.basename(path)
            license_code = extract_license_from_config(os.path.join(path, "config.py"))
            verified = db.verify_bot_license(license_code) if license_code else False
            running = is_bot_running(path, license_code)
            status = "🟢 Online" if running else "🔴 Offline"
            verified_emoji = "✅" if verified else "❌"
            embed.add_field(
                name=f"{name}",
                value=f"{verified_emoji} License: `{license_code}`\n{status}",
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="forcekill", description="Force kill a bot by its folder path (admin only)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(folder_name="Name of the bot folder (e.g., Giveaway)")
    async def forcekill(self, interaction: discord.Interaction, folder_name: str):
        await interaction.response.defer(ephemeral=True)
        target_path = os.path.join(BOTS_BASE_PATH, folder_name)
        if not os.path.isdir(target_path):
            await interaction.followup.send(f"❌ Folder `{folder_name}` not found.", ephemeral=True)
            return

        pids = find_processes_by_path(target_path)
        if not pids:
            await interaction.followup.send(f"No processes found for `{folder_name}`.", ephemeral=True)
            return

        killed = []
        for pid in pids:
            if await kill_process(pid):
                killed.append(str(pid))
        if killed:
            await interaction.followup.send(f"✅ Killed processes: {', '.join(killed)}", ephemeral=True)
        else:
            await interaction.followup.send("❌ Failed to kill processes.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(BotManager(bot))
