import discord
from discord.ext import commands
import logging
import sys
from datetime import datetime

from config import BOT_TOKEN, COLORS, FOOTER_TEXT
import database as db
import selffix

# ----- Logging setup (colours) -----
class ColourFormatter(logging.Formatter):
    grey = "\x1b[38;21m"
    blue = "\x1b[38;5;39m"
    yellow = "\x1b[38;5;226m"
    red = "\x1b[38;5;196m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    FORMATS = {
        logging.DEBUG: grey + "%(asctime)s [%(levelname)s] %(name)s: %(message)s" + reset,
        logging.INFO: blue + "%(asctime)s [%(levelname)s] %(name)s: %(message)s" + reset,
        logging.WARNING: yellow + "%(asctime)s [%(levelname)s] %(name)s: %(message)s" + reset,
        logging.ERROR: red + "%(asctime)s [%(levelname)s] %(name)s: %(message)s" + reset,
        logging.CRITICAL: bold_red + "%(asctime)s [%(levelname)s] %(name)s: %(message)s" + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)

root_logger = logging.getLogger()
root_logger.handlers.clear()
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(ColourFormatter())
root_logger.addHandler(handler)
root_logger.setLevel(logging.INFO)
logger = logging.getLogger(__name__)

def print_banner():
    banner = f"""
    ╔══════════════════════════════════════════╗
    ║         MASTER BOT – License Authority   ║
    ║              By AW (Alex Wakrod)         ║
    ╠══════════════════════════════════════════╣
    ║  • Version: 1.0.0                       ║
    ║  • Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}   ║
    ╚══════════════════════════════════════════╝
    """
    print(banner)

class MasterBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True   # needed to read DMs
        intents.guilds = True
        super().__init__(command_prefix="!", intents=intents)
        self.initial_extensions = [
            "commands", 
            "listener", 
            "utility", 
            "bot_manager", 
            "giveaway",
            "solutions_manager",   # fixed
            "error_monitor",
            "patch_tracker",
            "duplicate",
            "t_perm"
        ]
    async def setup_hook(self):
        # Init DB
        try:
            db.init_db()
            logger.info("✅ Database ready.")
        except Exception as e:
            logger.critical(f"❌ Database init failed: {e}")
            sys.exit(1)

        # Load cogs
        for ext in self.initial_extensions:
            try:
                await self.load_extension(ext)
                logger.info(f"✅ Loaded {ext}")
            except Exception as e:
                logger.error(f"❌ Failed to load {ext}: {e}")

        await self.tree.sync()
        logger.info("✅ Commands synced.")

    async def on_ready(self):
        logger.info(f"✅ Logged in as {self.user}")
        # Self‑fix for verification channels (now includes solution-logs)
        for guild in self.guilds:
            await selffix.ensure_verification_setup(self, guild)
        logger.info("🚀 Master Bot ready.")

bot = MasterBot()

if __name__ == "__main__":
    print_banner()
    if not BOT_TOKEN:
        logger.critical("❌ No BOT_TOKEN")
        sys.exit(1)
    bot.run(BOT_TOKEN)