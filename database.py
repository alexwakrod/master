import pyodbc
import logging
import random
import string
import os
import re
from config import DATABASE, USER_LICENSE_PREFIX, USER_LICENSE_FORMAT, BOTS_BASE_PATH

logger = logging.getLogger(__name__)

def get_connection():
    try:
        conn = pyodbc.connect(
            driver=DATABASE['driver'],
            server=DATABASE['server'],
            database=DATABASE['database'],
            uid=DATABASE['uid'],
            pwd=DATABASE['pwd'],
            autocommit=False
        )
        return conn
    except pyodbc.Error as e:
        logger.error(f"Database connection failed: {e}")
        raise

def column_exists(cursor, table, column):
    """Check if a column exists in a table."""
    cursor.execute("""
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_NAME = ? AND COLUMN_NAME = ?
    """, (table, column))
    return cursor.fetchone() is not None

def migrate_bot_licenses():
    """Add bot_path column to bot_licenses if missing, preserving data."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Check if table exists
        cursor.execute("SELECT 1 FROM sysobjects WHERE name='bot_licenses' AND xtype='U'")
        if not cursor.fetchone():
            # Table doesn't exist yet, will be created by init_db
            return

        # Check if bot_path column exists
        if not column_exists(cursor, 'bot_licenses', 'bot_path'):
            logger.info("Migrating bot_licenses table to add bot_path column...")
            
            # Create new table with updated schema
            cursor.execute("""
                CREATE TABLE bot_licenses_new (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    license_code NVARCHAR(50) UNIQUE NOT NULL,
                    bot_name NVARCHAR(100) NOT NULL,
                    is_active BIT DEFAULT 1,
                    created_at DATETIME DEFAULT GETDATE(),
                    last_verified DATETIME,
                    owner_id BIGINT,
                    bot_path NVARCHAR(500) NULL
                )
            """)
            
            # Copy data from old table
            cursor.execute("""
                INSERT INTO bot_licenses_new (license_code, bot_name, is_active, created_at, last_verified, owner_id)
                SELECT license_code, bot_name, is_active, created_at, last_verified, owner_id
                FROM bot_licenses
            """)
            
            # Drop old table
            cursor.execute("DROP TABLE bot_licenses")
            
            # Rename new table
            cursor.execute("EXEC sp_rename 'bot_licenses_new', 'bot_licenses'")
            
            conn.commit()
            logger.info("Migration complete: added bot_path column.")
    except pyodbc.Error as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def sync_bot_paths():
    """Scan all bot directories and update bot_path for matching licenses."""
    logger.info("Syncing bot paths with licenses...")
    updated = 0
    for path in get_bot_directories():
        config_path = os.path.join(path, "config.py")
        license_code = extract_license_from_config(config_path)
        if license_code:
            # Update the license with this path
            conn = get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("UPDATE bot_licenses SET bot_path = ? WHERE license_code = ?", (path, license_code))
                if cursor.rowcount > 0:
                    updated += 1
                conn.commit()
            except pyodbc.Error as e:
                logger.error(f"Failed to set path for {license_code}: {e}")
            finally:
                cursor.close()
                conn.close()
    logger.info(f"Synced {updated} bot paths.")

def get_bot_directories():
    """Helper to get list of bot directories (copied from bot_manager)."""
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

def init_db():
    """Create all master‑bot related tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # ----- Bot Licenses (handshake bot authentication) -----
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='bot_licenses' AND xtype='U')
            CREATE TABLE bot_licenses (
                id INT IDENTITY(1,1) PRIMARY KEY,
                license_code NVARCHAR(50) UNIQUE NOT NULL,
                bot_name NVARCHAR(100) NOT NULL,
                is_active BIT DEFAULT 1,
                created_at DATETIME DEFAULT GETDATE(),
                last_verified DATETIME,
                owner_id BIGINT,
                bot_path NVARCHAR(500) NULL
            )
        """)
        conn.commit()

        # ----- Error Logs -----
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='error_logs' AND xtype='U')
            CREATE TABLE error_logs (
                id INT IDENTITY(1,1) PRIMARY KEY,
                bot_license NVARCHAR(50) NOT NULL,
                error_message NVARCHAR(MAX) NOT NULL,
                timestamp DATETIME DEFAULT GETDATE(),
                forwarded BIT DEFAULT 0
            )
        """)
        conn.commit()

        # ----- Patch History -----
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='patches' AND xtype='U')
            CREATE TABLE patches (
                id INT IDENTITY(1,1) PRIMARY KEY,
                bot_license NVARCHAR(50) NOT NULL,
                filename NVARCHAR(255) NOT NULL,
                applied_at DATETIME DEFAULT GETDATE()
            )
        """)
        conn.commit()

        # ----- User Licenses -----
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='user_licenses' AND xtype='U')
            CREATE TABLE user_licenses (
                id INT IDENTITY(1,1) PRIMARY KEY,
                license_code NVARCHAR(50) UNIQUE NOT NULL,
                product_name NVARCHAR(100) NOT NULL,
                is_active BIT DEFAULT 1,
                expiration_date DATE,
                assigned_to BIGINT,
                giveaway_id INT,
                created_at DATETIME DEFAULT GETDATE()
            )
        """)
        conn.commit()

        # ----- Solution Logs -----
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='solution_logs' AND xtype='U')
            CREATE TABLE solution_logs (
                id INT IDENTITY(1,1) PRIMARY KEY,
                bot_license NVARCHAR(50),
                bot_name NVARCHAR(100),
                error_type NVARCHAR(255),
                solution_file NVARCHAR(255),
                applied_at DATETIME DEFAULT GETDATE(),
                success BIT DEFAULT 1,
                details NVARCHAR(MAX)
            )
        """)
        conn.commit()

        # ----- Error Events -----
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='error_events' AND xtype='U')
            CREATE TABLE error_events (
                id INT IDENTITY(1,1) PRIMARY KEY,
                bot_license NVARCHAR(50),
                bot_name NVARCHAR(100),
                error_text NVARCHAR(MAX),
                matched_solution NVARCHAR(255),
                notified_admin BIT DEFAULT 0,
                occurred_at DATETIME DEFAULT GETDATE()
            )
        """)
        conn.commit()

        # ----- Patch Tracking -----
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='patch_tracking' AND xtype='U')
            CREATE TABLE patch_tracking (
                id INT IDENTITY(1,1) PRIMARY KEY,
                bot_license NVARCHAR(50),
                bot_name NVARCHAR(100),
                patch_filename NVARCHAR(255),
                downloaded_at DATETIME DEFAULT GETDATE(),
                dm_sent BIT DEFAULT 0
            )
        """)
        conn.commit()

        # ----- Bot Duplications Log -----
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='bot_duplications' AND xtype='U')
            CREATE TABLE bot_duplications (
                id INT IDENTITY(1,1) PRIMARY KEY,
                user_id BIGINT NOT NULL,
                folder_name NVARCHAR(255) NOT NULL,
                bot_token NVARCHAR(100) NOT NULL,
                license_code NVARCHAR(50),
                created_at DATETIME DEFAULT GETDATE()
            )
        """)
        conn.commit()

        logger.info("✅ Master Bot database tables initialised.")
    except pyodbc.Error as e:
        logger.error(f"Error creating master tables: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

    # After tables exist, run migration if needed (for older installs)
    migrate_bot_licenses()
    # Then sync paths
    sync_bot_paths()

# ---------- Bot License Management ----------
def generate_bot_license() -> str:
    chars = string.ascii_uppercase + string.digits
    license = "BOT-"
    for _ in range(4):
        license += random.choice(chars)
    license += "-"
    for _ in range(4):
        license += random.choice(chars)
    license += "-"
    for _ in range(3):
        license += random.choice(chars)
    license += "-"
    for _ in range(3):
        license += random.choice(chars)
    return license

def generate_unique_bot_license():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        while True:
            license = generate_bot_license()
            cursor.execute("SELECT 1 FROM bot_licenses WHERE license_code = ?", (license,))
            if not cursor.fetchone():
                return license
    finally:
        cursor.close()
        conn.close()

def register_bot_license(bot_name: str, owner_id: int = None) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        license_code = generate_unique_bot_license()
        cursor.execute("""
            INSERT INTO bot_licenses (license_code, bot_name, owner_id)
            VALUES (?, ?, ?)
        """, (license_code, bot_name, owner_id))
        conn.commit()
        logger.info(f"✅ Registered new bot license: {license_code} for '{bot_name}'")
        return license_code
    except pyodbc.Error as e:
        logger.error(f"Failed to register bot license: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def verify_bot_license(license_code: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 1 FROM bot_licenses
            WHERE license_code = ? AND is_active = 1
        """, (license_code,))
        exists = cursor.fetchone() is not None
        if exists:
            cursor.execute("""
                UPDATE bot_licenses
                SET last_verified = GETDATE()
                WHERE license_code = ?
            """, (license_code,))
            conn.commit()
        return exists
    except pyodbc.Error as e:
        logger.error(f"Error verifying bot license {license_code}: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def deactivate_bot_license(license_code: str):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE bot_licenses SET is_active = 0 WHERE license_code = ?", (license_code,))
        conn.commit()
        logger.info(f"✅ Deactivated bot license: {license_code}")
    except pyodbc.Error as e:
        logger.error(f"Error deactivating bot license {license_code}: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def get_bot_name_by_license(license_code: str):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT bot_name FROM bot_licenses WHERE license_code = ?", (license_code,))
        row = cursor.fetchone()
        return row.bot_name if row else None
    except pyodbc.Error as e:
        logger.error(f"Error fetching bot name: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def get_all_active_bots():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT license_code, bot_name, last_verified
            FROM bot_licenses
            WHERE is_active = 1
            ORDER BY bot_name
        """)
        rows = cursor.fetchall()
        return [(row.license_code, row.bot_name, row.last_verified) for row in rows]
    except pyodbc.Error as e:
        logger.error(f"Failed to fetch active bots: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def get_license_by_path(bot_path: str):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT license_code FROM bot_licenses WHERE bot_path = ?", (bot_path,))
        row = cursor.fetchone()
        return row.license_code if row else None
    except pyodbc.Error as e:
        logger.error(f"Error fetching license by path: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def set_license_path(license_code: str, bot_path: str):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE bot_licenses SET bot_path = ? WHERE license_code = ?", (bot_path, license_code))
        conn.commit()
    except pyodbc.Error as e:
        logger.error(f"Error setting license path: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

# ---------- Error Logging ----------
def log_bot_error(license_code: str, error_message: str):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO error_logs (bot_license, error_message) VALUES (?, ?)", (license_code, error_message))
        conn.commit()
        logger.info(f"📝 Logged error from bot license: {license_code}")
    except pyodbc.Error as e:
        logger.error(f"Failed to log error for {license_code}: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

# ---------- User Licenses (for giveaways) ----------
def generate_user_license(product_name: str = "Giveaway", assigned_to: int = None, giveaway_id: int = None) -> str:
    chars = string.ascii_uppercase + string.digits
    license = USER_LICENSE_PREFIX
    for ch in USER_LICENSE_FORMAT:
        if ch == '#':
            license += random.choice(chars)
        else:
            license += ch
    conn = get_connection()
    cursor = conn.cursor()
    try:
        while True:
            cursor.execute("SELECT 1 FROM user_licenses WHERE license_code = ?", (license,))
            if not cursor.fetchone():
                break
            license = USER_LICENSE_PREFIX
            for ch in USER_LICENSE_FORMAT:
                if ch == '#':
                    license += random.choice(chars)
                else:
                    license += ch
        cursor.execute("""
            INSERT INTO user_licenses (license_code, product_name, assigned_to, giveaway_id)
            VALUES (?, ?, ?, ?)
        """, (license, product_name, assigned_to, giveaway_id))
        conn.commit()
        return license
    except Exception as e:
        logger.error(f"Error generating user license: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def generate_multiple_user_licenses(count: int, product_name: str = "Giveaway", giveaway_id: int = None) -> list:
    codes = []
    for _ in range(count):
        codes.append(generate_user_license(product_name, None, giveaway_id))
    return codes

def assign_license_to_user(license_code: str, user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE user_licenses SET assigned_to = ? WHERE license_code = ?", (user_id, license_code))
        conn.commit()
    except pyodbc.Error as e:
        logger.error(f"Failed to assign license: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

# ---------- Solution Logs ----------
def log_solution(bot_license, bot_name, error_type, solution_file, success=True, details=""):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO solution_logs (bot_license, bot_name, error_type, solution_file, success, details)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (bot_license, bot_name, error_type, solution_file, success, details))
        conn.commit()
    except pyodbc.Error as e:
        logger.error(f"Failed to log solution: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

# ---------- Error Events ----------
def log_error_event(bot_license, bot_name, error_text, matched_solution=None):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO error_events (bot_license, bot_name, error_text, matched_solution)
            VALUES (?, ?, ?, ?)
        """, (bot_license, bot_name, error_text, matched_solution))
        conn.commit()
    except pyodbc.Error as e:
        logger.error(f"Failed to log error event: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

# ---------- Patch Tracking ----------
def log_patch_download(bot_license, bot_name, patch_filename):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO patch_tracking (bot_license, bot_name, patch_filename)
            VALUES (?, ?, ?)
        """, (bot_license, bot_name, patch_filename))
        conn.commit()
    except pyodbc.Error as e:
        logger.error(f"Failed to log patch download: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

# ---------- Bot Duplications Log ----------
def log_duplication(user_id: int, folder_name: str, bot_token: str, license_code: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO bot_duplications (user_id, folder_name, bot_token, license_code)
            VALUES (?, ?, ?, ?)
        """, (user_id, folder_name, bot_token, license_code))
        conn.commit()
    except pyodbc.Error as e:
        logger.error(f"Failed to log duplication: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
