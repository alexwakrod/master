import os
from dotenv import load_dotenv

load_dotenv()

# ---------- Database (SQL Server Authentication) ----------
DATABASE = {
    'driver': '{ODBC Driver 17 for SQL Server}',
    'server': 'localhost',               
    'database': 'DISCORDBOT',
    'uid': 'Databaseuser',                   
    'pwd': 'DATABASEPW'                  
}
# ---------- Discord ----------
BOT_TOKEN = os.getenv('MASTER_BOT_TOKEN', 'YOUR_BOT_TOKEN')
BOTS_BASE_PATH = "/Work"
TEMPLATE_FOLDER_NAME = "HandshakeBot_Template"
TEMPLATE_PATH = os.path.join(BOTS_BASE_PATH, TEMPLATE_FOLDER_NAME)
MASTER_BOT_PATH = os.path.dirname(os.path.abspath(__file__))

# ---------- Emojis & Colours ----------
EMOJIS = {
    'success': '✅',
    'error': '❌',
    'info': 'ℹ️',
    'warning': '⚠️',
    'verified': '🔐',
    'patch': '📦',
    'log': '📋',
    'bot': '🤖'
}
COLORS = {
    'primary': 0x3498db,
    'success': 0x2ecc71,
    'error': 0xe74c3c,
    'warning': 0xf39c12,
    'info': 0x5865f2,
    'role': 0xffd700,
    'style': 0xFFFF33
}
FOOTER_TEXT = "Master Bot – By AW (Alex Wakrod)"

# ---------- Master Secret (for signing) ----------
MASTER_SECRET = os.getenv('MASTER_SECRET', 'YOUR_BOT_SPECIALSIGN')

# ---------- Auto‑created channels ----------
VERIFY_CATEGORY = "Verification"
VERIFY_CHANNEL = "bot-verify"
LOG_CHANNEL = "bot-logs"          # where error logs are forwarded
PATCH_CHANNEL = "bot-patches"
SOLUTION_LOG_CHANNEL = "solution-logs"   # new channel for solution logs

# ---------- Giveaway Integration ----------
LICENSE_REQUEST_CHANNEL = "g-license"        # Channel where requests arrive
USER_LICENSE_PREFIX = "USER-"                 # Prefix for user licenses
USER_LICENSE_FORMAT = "####-####-####"        # Format after prefix

# ---------- Solutions Path ----------
SOLUTION_PATH = os.path.join(BOTS_BASE_PATH, "MasterBot", "Solutions") # /media/alexwakrod/Local Disk 11/Work/MasterBot/Solutions
ADMIN_USER_ID = 1399234194281861201  # Replace with your Discord user ID
MASTER_BOT_ID = 1471507680139939850

# ---------- T-PERM (Ticket Permissions) ---------------
TICKET_PERMISSION_CHANNEL = "t-permission" #Ticket Permissions
