"""
================================================================================
SHAAD LIVE FF - ENTERPRISE SQLITE DATABASE LAYER & TRANSACTION ENGINE
================================================================================
Architecture: Thread-Safe SQLite Bridge, Schema Migrations & Auto-Recovery
Platform Compatibility: Local Termux (Android), Railway Container, Docker, Linux
File: database.py
================================================================================
"""

import os
import sys
import time
import sqlite3
import logging
from datetime import datetime, timedelta
from contextlib import contextmanager

# ==============================================================================
# SECTION 1: LOGGING TELEMETRY CONFIGURATION
# ==============================================================================
logger = logging.getLogger("SHAAD_LIVE_DB_ENGINE")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [DB_ENGINE:%(lineno)d] ~ %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# ==============================================================================
# SECTION 2: ENVIRONMENT CONFIGURATIONS & MASTER CONSTANTS
# ==============================================================================
DB_PATH = os.environ.get("DB_PATH", "shaad_live_ff.db")
DEFAULT_ADMIN_KEY = os.environ.get("ADMIN_MASTER_KEY", "Shaadlive07")
CONNECTION_TIMEOUT = float(os.environ.get("DB_TIMEOUT", 30.0))
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 0.5

# ==============================================================================
# SECTION 3: THREAD-SAFE CONTEXT MANAGERS & CONNECTION HANDLERS
# ==============================================================================
def get_db():
    """
    Establish and return a single connection instance with Row factory enabled.
    Sets timeout and busy handlers to prevent SQLite database lock errors.
    """
    try:
        conn = sqlite3.connect(
            DB_PATH,
            timeout=CONNECTION_TIMEOUT,
            isolation_level=None,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Critical error establishing connection to SQLite at {DB_PATH}: {str(e)}")
        raise e

@contextmanager
def get_db_cursor(commit=True):
    """
    Thread-safe context manager for executing transactional queries safely.
    Handles rollback on exceptions and automatic cursor/connection cleanup.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        if commit:
            cursor.execute("BEGIN IMMEDIATE;")
        yield cursor
        if commit:
            conn.commit()
    except sqlite3.Error as e:
        if commit:
            try:
                conn.rollback()
                logger.warning(f"Transaction rolled back due to error: {str(e)}")
            except sqlite3.Error:
                pass
        logger.error(f"Database operation failed: {str(e)}")
        raise e
    finally:
        cursor.close()
        conn.close()

# ==============================================================================
# SECTION 4: DATABASE INITIALIZATION & SCHEMA DDL DEFINITIONS
# ==============================================================================
def init_db():
    """
    Initialize and upgrade full relational schema structures.
    Creates necessary tables, indexes, and seeds master security keys.
    """
    logger.info(f"Initializing SHAAD LIVE Database schema at target: {DB_PATH}")
    
    with get_db_cursor(commit=True) as cur:
        # 1. User Keys & Licenses Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_name TEXT UNIQUE NOT NULL,
                validity_days INTEGER DEFAULT 30,
                use_limit INTEGER DEFAULT 1,
                used_count INTEGER DEFAULT 0,
                created_by TEXT DEFAULT 'system',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            );
        """)

        # 2. Master Administrative Meta Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_meta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                master_key TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 3. Commercial Likes & VIP Plans Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS commercial_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                likes_count INTEGER NOT NULL,
                price REAL NOT NULL,
                validity_days INTEGER DEFAULT 30,
                boost_limit INTEGER DEFAULT 1,
                description TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            );
        """)

        # 4. Verified Payment UTR Ledger
        cur.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                utr_number TEXT UNIQUE NOT NULL,
                plan_id INTEGER,
                amount REAL,
                generated_key TEXT,
                status TEXT DEFAULT 'APPROVED',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 5. Session State Store Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                session_id TEXT PRIMARY KEY,
                user_key TEXT NOT NULL,
                user_type TEXT NOT NULL,
                ip_address TEXT,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 6. Granular Operational Telemetry & Usage Logs
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_key TEXT NOT NULL,
                action TEXT NOT NULL,
                target_uid TEXT,
                target_region TEXT,
                status TEXT NOT NULL,
                client_ip TEXT,
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 7. Banned Blacklist Registry Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS banned_ips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT UNIQUE NOT NULL,
                reason TEXT,
                banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Indexing for high-speed queries on large datasets
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_keys_name ON user_keys(key_name);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_payments_utr ON payments(utr_number);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_id ON user_sessions(session_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_usage_logs_key ON usage_logs(user_key);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_banned_ips_addr ON banned_ips(ip_address);")

        # Seed master admin key if empty
        cur.execute("SELECT COUNT(*) FROM admin_meta;")
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO admin_meta (master_key) VALUES (?);", (DEFAULT_ADMIN_KEY,))
            logger.info("Master Admin key seeded into database.")

        # Seed initial commercial plans if empty
        cur.execute("SELECT COUNT(*) FROM commercial_plans;")
        if cur.fetchone()[0] == 0:
            default_plans = [
                ("20 Likes Starter", 20, 10.0, 30, 1, "Instant Delivery, 100% Safe (OB55 Server)"),
                ("50 Likes Pro", 50, 25.0, 30, 1, "Fast Auto Delivery, Chikubot Engine"),
                ("100 Likes Ultimate", 100, 49.0, 30, 1, "Ultra Fast Boost, Priority Server"),
                ("200 Likes Mega Pack", 200, 95.0, 30, 1, "Admin Supervised Delivery, Dedicated Node"),
                ("500 Likes Ultra Pack", 500, 230.0, 30, 1, "Max Speed Boost, Guaranteed Delivery"),
                ("1000 Likes VIP Legend", 1000, 450.0, 30, 1, "VIP Dedicated Node, Rank Boost")
            ]
            cur.executemany("""
                INSERT INTO commercial_plans (name, likes_count, price, validity_days, boost_limit, description)
                VALUES (?, ?, ?, ?, ?, ?);
            """, default_plans)
            logger.info("Default commercial likes packages seeded into database.")

    logger.info("Database initialized and verified successfully.")

# ==============================================================================
# SECTION 5: ADMINISTRATIVE MASTER DATA ACCESS
# ==============================================================================
def get_admin_key():
    """Retrieve the current active administrative master key."""
    try:
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT master_key FROM admin_meta ORDER BY id DESC LIMIT 1;")
            row = cur.fetchone()
            if row:
                return row["master_key"]
    except Exception as e:
        logger.error(f"Error fetching admin master key: {e}")
    return DEFAULT_ADMIN_KEY

def update_admin_key(old_key, new_key):
    """Rotate the master administrative key after verifying previous key."""
    if not old_key or not new_key:
        return False
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("SELECT id, master_key FROM admin_meta ORDER BY id DESC LIMIT 1;")
            row = cur.fetchone()
            if row and row["master_key"] == old_key:
                cur.execute(
                    "UPDATE admin_meta SET master_key = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?;",
                    (new_key, row["id"])
                )
                logger.info("Admin master key successfully rotated.")
                return True
    except Exception as e:
        logger.error(f"Exception updating admin key: {e}")
    return False

# ==============================================================================
# SECTION 6: COMMERCIAL PLANS DATA OPERATIONS
# ==============================================================================
def get_all_plans():
    """Fetch all active commercial likes plans ordered by price."""
    try:
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT * FROM commercial_plans WHERE is_active = 1 ORDER BY price ASC;")
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching commercial plans: {e}")
        return []

def get_plan_by_id(plan_id):
    """Retrieve single commercial plan by its unique primary ID."""
    if not plan_id:
        return None
    try:
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT * FROM commercial_plans WHERE id = ?;", (plan_id,))
            row = cur.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error fetching plan by ID {plan_id}: {e}")
        return None

def create_plan(name, likes, price, days=30, limit=1, desc=""):
    """Create a new commercial plan offering."""
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                INSERT INTO commercial_plans (name, likes_count, price, validity_days, boost_limit, description)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (name, likes, price, days, limit, desc))
            return cur.lastrowid
    except Exception as e:
        logger.error(f"Error creating new plan: {e}")
        return None

def delete_plan(plan_id):
    """Soft-delete a commercial plan by deactivating its status."""
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("UPDATE commercial_plans SET is_active = 0 WHERE id = ?;", (plan_id,))
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Error deleting plan {plan_id}: {e}")
        return False

# ==============================================================================
# SECTION 7: USER KEYS & LICENSES DATA OPERATIONS
# ==============================================================================
def get_all_user_keys():
    """Retrieve complete list of user keys and licenses."""
    try:
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT * FROM user_keys ORDER BY created_at DESC;")
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching all user keys: {e}")
        return []

def create_user_key(key, validity_days=30, use_limit=1, created_by="system"):
    """Insert a newly generated license key with its assigned quotas."""
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                INSERT INTO user_keys (key_name, validity_days, use_limit, created_by)
                VALUES (?, ?, ?, ?);
            """, (key, validity_days, use_limit, created_by))
            return True
    except sqlite3.IntegrityError:
        logger.warning(f"Key collision: {key} already exists.")
        return False
    except Exception as e:
        logger.error(f"Error creating user key {key}: {e}")
        return False

def validate_user_key(key):
    """Validate license key existence, activation, and usage limits."""
    if not key:
        return None, "Key cannot be empty."
    try:
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT * FROM user_keys WHERE key_name = ? AND is_active = 1;", (key,))
            row = cur.fetchone()
            if not row:
                return None, "License key not found or has been deactivated."
            
            k = dict(row)
            if k["used_count"] >= k["use_limit"]:
                return None, "License usage quota exhausted."
            
            return k, None
    except Exception as e:
        logger.error(f"Error validating key {key}: {e}")
        return None, "Internal database error during key validation."

def update_key_usage(key, action="like"):
    """Increment key usage counter and touch timestamp."""
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                UPDATE user_keys 
                SET used_count = used_count + 1, updated_at = CURRENT_TIMESTAMP 
                WHERE key_name = ?;
            """, (key,))
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Error updating key usage for {key}: {e}")
        return False

def delete_user_key(key):
    """Permanently revoke and delete a user license key."""
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("DELETE FROM user_keys WHERE key_name = ?;", (key,))
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Error deleting key {key}: {e}")
        return False

# ==============================================================================
# SECTION 8: PAYMENTS & FINANCIAL SETTLEMENT DATA OPERATIONS
# ==============================================================================
def process_utr_payment(utr, plan_id, generated_key):
    """Verify and record a payment UTR, preventing duplicate claims."""
    clean_utr = str(utr).strip()
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("SELECT id FROM payments WHERE utr_number = ?;", (clean_utr,))
            if cur.fetchone():
                return False, "This UTR number has already been claimed or approved.", None
            
            cur.execute("SELECT * FROM commercial_plans WHERE id = ?;", (plan_id,))
            plan_row = cur.fetchone()
            if not plan_row:
                return False, "Target plan configuration not found.", None
            
            plan = dict(plan_row)
            cur.execute("""
                INSERT INTO payments (utr_number, plan_id, amount, generated_key, status)
                VALUES (?, ?, ?, ?, 'APPROVED');
            """, (clean_utr, plan_id, plan["price"], generated_key))
            
            return True, "Payment verified and recorded successfully.", generated_key
    except Exception as e:
        logger.error(f"Error processing UTR payment {clean_utr}: {e}")
        return False, f"Database transaction failed: {str(e)}", None

# ==============================================================================
# SECTION 9: SESSION LIFECYCLE & SECURITY DATA OPERATIONS
# ==============================================================================
def create_session(session_id, user_key, user_type, ip_address, expires_at):
    """Store or refresh an active JWT session record."""
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                INSERT OR REPLACE INTO user_sessions (session_id, user_key, user_type, ip_address, expires_at)
                VALUES (?, ?, ?, ?, ?);
            """, (session_id, user_key, user_type, ip_address, expires_at))
            return True
    except Exception as e:
        logger.error(f"Error creating session {session_id}: {e}")
        return False

def get_session(session_id):
    """Fetch active session record by its unique session UUID."""
    if not session_id:
        return None
    try:
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT * FROM user_sessions WHERE session_id = ?;", (session_id,))
            row = cur.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error fetching session {session_id}: {e}")
        return None

def delete_session(session_id):
    """Delete a session on logout or invalidation."""
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("DELETE FROM user_sessions WHERE session_id = ?;", (session_id,))
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {e}")
        return False

def cleanup_expired_sessions():
    """Housekeeping job: delete expired sessions from the store."""
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("DELETE FROM user_sessions WHERE expires_at < CURRENT_TIMESTAMP;")
            count = cur.rowcount
            if count > 0:
                logger.info(f"Cleaned up {count} expired user sessions.")
            return count
    except Exception as e:
        logger.error(f"Error cleaning up expired sessions: {e}")
        return 0

# ==============================================================================
# SECTION 10: AUDIT TELEMETRY & BAN REPOSITORIES
# ==============================================================================
def log_usage(key, action, uid, region, status, ip, ua):
    """Write an audit entry for actions executed across the system."""
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                INSERT INTO usage_logs (user_key, action, target_uid, target_region, status, client_ip, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (key, action, uid, region, status, ip, ua))
            return True
    except Exception as e:
        logger.error(f"Failed to record usage log: {e}")
        return False

def get_usage_logs(limit=100):
    """Retrieve operational log entries in reverse chronological order."""
    try:
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT * FROM usage_logs ORDER BY created_at DESC LIMIT ?;", (limit,))
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error retrieving usage logs: {e}")
        return []

def is_ip_banned(ip):
    """Check if a remote client IP is in the blacklist."""
    if not ip:
        return False
    try:
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT 1 FROM banned_ips WHERE ip_address = ?;", (ip,))
            return cur.fetchone() is not None
    except Exception as e:
        logger.error(f"Error checking IP ban status for {ip}: {e}")
        return False

def ban_ip(ip, reason="Automated Security Boundary Violation"):
    """Add a client IP address to the blacklist."""
    if not ip:
        return False
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("INSERT OR IGNORE INTO banned_ips (ip_address, reason) VALUES (?, ?);", (ip, reason))
            logger.warning(f"IP {ip} has been added to the blacklist. Reason: {reason}")
            return True
    except Exception as e:
        logger.error(f"Error banning IP {ip}: {e}")
        return False

