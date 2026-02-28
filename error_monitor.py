import discord
from discord.ext import commands, tasks
import logging
import os
import asyncio
import importlib.util
import sys
import re
from datetime import datetime, timezone
from collections import defaultdict

from config import SOLUTION_PATH, ADMIN_USER_ID
import database as db

logger = logging.getLogger(__name__)

class ErrorMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.monitored_processes = {}  # {bot_path: {'task': task, 'process': process, 'name': name, 'license': license, 'stderr_queue': asyncio.Queue}}
        self.solution_modules = {}      # {filename: {'module': module, 'pattern': re.compile(pattern)}}
        self.error_counts = defaultdict(lambda: defaultdict(int))  # {bot_path: {error_signature: count}}
        self.solution_channel = None
        self.load_solutions()
        self.monitor_errors.start()
        self.monitored_paths = set()

    def load_solutions(self):
        """Dynamically import all solution files and compile their patterns."""
        for file in os.listdir(SOLUTION_PATH):
            if file.endswith(".py") and not file.startswith("__"):
                module_name = file[:-3]
                spec = importlib.util.spec_from_file_location(module_name, os.path.join(SOLUTION_PATH, file))
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                # Extract pattern from module's docstring or attribute
                pattern = None
                if hasattr(module, 'pattern'):
                    pattern = module.pattern
                else:
                    # Fallback: use filename without extension as keyword
                    pattern = module_name.replace('_', ' ')
                self.solution_modules[file] = {
                    'module': module,
                    'pattern': re.compile(pattern, re.IGNORECASE) if not isinstance(pattern, re.Pattern) else pattern,
                    'name': module_name
                }
                logger.info(f"Loaded solution module: {file} with pattern: {pattern}")

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            channel = discord.utils.get(guild.channels, name="solution-logs")
            if channel:
                self.solution_channel = channel
                break

    def register_bot(self, bot_path, process, name, license_code):
        queue = asyncio.Queue()
        task = asyncio.create_task(self.monitor_bot_output(bot_path, process, name, license_code, queue))
        self.monitored_processes[bot_path] = {
            'task': task,
            'process': process,
            'name': name,
            'license': license_code,
            'queue': queue
        }
        self.monitored_paths.add(bot_path)

    def unregister_bot(self, bot_path):
        if bot_path in self.monitored_processes:
            self.monitored_processes[bot_path]['task'].cancel()
            del self.monitored_processes[bot_path]
            self.monitored_paths.discard(bot_path)
            self.error_counts.pop(bot_path, None)

    async def monitor_bot_output(self, bot_path, process, name, license_code, queue):
        """Read stderr line by line and put into queue for processing."""
        while True:
            line = await process.stderr.readline()
            if not line:
                break
            line = line.decode().strip()
            if line:
                logger.debug(f"[{name}] {line}")
                await queue.put(line)

    @tasks.loop(seconds=5)
    async def monitor_errors(self):
        """Process error lines from all bots."""
        for bot_path, info in list(self.monitored_processes.items()):
            queue = info['queue']
            name = info['name']
            license_code = info['license']
            try:
                while not queue.empty():
                    line = await queue.get()
                    await self.process_error(bot_path, name, license_code, line)
            except Exception as e:
                logger.error(f"Error processing queue for {name}: {e}")

    async def process_error(self, bot_path, bot_name, license_code, error_line):
        """Check error line, apply solutions, count occurrences, notify admin."""
        # Update error count for this error (simplified: use error line as key)
        self.error_counts[bot_path][error_line] += 1
        count = self.error_counts[bot_path][error_line]

        # Check if any solution pattern matches
        matched_solution = None
        for file, data in self.solution_modules.items():
            if data['pattern'].search(error_line):
                matched_solution = file
                break

        if matched_solution:
            # Apply solution
            module = data['module']
            try:
                # Pass bot_path to solution if needed
                if hasattr(module, 'apply'):
                    success, message = await module.apply(self.bot, error_line, bot_path)
                else:
                    success, message = False, "Solution module has no apply function"

                db.log_solution(license_code, bot_name, error_line, matched_solution, success, message)
                if self.solution_channel:
                    embed = discord.Embed(
                        title="🛠️ Solution Applied",
                        description=f"**Bot:** {bot_name}\n**License:** `{license_code}`\n**Error:** {error_line[:200]}...\n**Solution:** {matched_solution}\n**Result:** {'✅ Success' if success else '❌ Failed'}",
                        color=0x00ff00 if success else 0xff0000,
                        timestamp=datetime.now(timezone.utc)
                    )
                    embed.set_footer(text=message)
                    await self.solution_channel.send(embed=embed)

                # If solution succeeded and involved module install, we should restart the bot
                if success and matched_solution == 'module_not_found.py':
                    # Restart the bot
                    await self.restart_bot(bot_path)
                    # Reset error count after restart
                    self.error_counts[bot_path].clear()
            except Exception as e:
                logger.error(f"Failed to apply solution {matched_solution}: {e}")
                db.log_solution(license_code, bot_name, error_line, matched_solution, False, str(e))
        else:
            # No match – if error occurs 3 times in a row, notify admin
            if count >= 3:
                db.log_error_event(license_code, bot_name, error_line)
                await self.notify_admin(bot_name, license_code, error_line, bot_path)
                # Reset count to avoid spam
                self.error_counts[bot_path][error_line] = 0

    async def restart_bot(self, bot_path):
        """Restart a bot by stopping and starting it via bot_manager."""
        bot_manager = self.bot.get_cog('BotManager')
        if not bot_manager:
            logger.error("BotManager cog not found")
            return False
        try:
            # Call a public method of BotManager to restart by path
            success = await bot_manager.restart_bot_by_path(bot_path)
            if success:
                logger.info(f"✅ Restarted bot at {bot_path}")
                return True
            else:
                logger.error(f"❌ Failed to restart bot at {bot_path}")
                return False
        except Exception as e:
            logger.error(f"Error restarting bot: {e}")
            return False

    async def notify_admin(self, bot_name, license_code, error_line, bot_path):
        """DM the admin with error details."""
        admin = self.bot.get_user(ADMIN_USER_ID)
        if not admin:
            try:
                admin = await self.bot.fetch_user(ADMIN_USER_ID)
            except:
                return
        embed = discord.Embed(
            title="⚠️ Unhandled Error in Bot",
            description=f"**Bot:** {bot_name}\n**License:** `{license_code}`\n**Error:** {error_line[:500]}",
            color=0xffa500,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Path", value=bot_path, inline=False)
        try:
            await admin.send(embed=embed)
        except:
            pass

    def cog_unload(self):
        self.monitor_errors.cancel()

async def setup(bot):
    await bot.add_cog(ErrorMonitor(bot))