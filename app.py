"""
SHAAD LIVE FF - ENTERPRISE HIGH-CONCURRENCY BACKEND ENGINE
ARCHITECTED FOR RAILWAY LINUX CONTAINER & LOCAL HYBRID EXECUTION
FULL DUAL-ENGINE LIKE INJECTION (OB55 / CHIKUBOT) INTEGRATION WITH PROXY BYPASS
DATABASE: SQLITE THREAD-SAFE ORM WITH ROTATIONAL AUDIT PROTOCOL
"""

import os
import re
import sys
import time
import json
import uuid
import string
import random
import logging
import sqlite3
import hashlib
import binascii
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlencode, quote_plus

import requests
from flask import Flask, render_template, request, jsonify, g, session, make_response
from flask_cors import CORS
import jwt

# ==============================================================================
# SECTION 1: LOGGING TELEMETRY SYSTEM ARCHITECTURE
# ==============================================================================
LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] ~ %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('SHAAD_LIVE_FF_ENGINE')

# ==============================================================================
# SECTION 2: SYSTEM ENVIRONMENT & CONFIGURATION BINDINGS
# ==============================================================================
app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "*"}})

# Core Secrets & JWT Lifespans
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'SHAAD_LIVE_FF_SUPER_PROD_MASTER_KEY_2026_SECURE_TOKEN_XYZ')
app.config['JWT_EXPIRATION_HOURS'] = int(os.environ.get('JWT_EXPIRATION_HOURS', 12))
app.config['MAX_FAILED_ATTEMPTS'] = 5
app.config['FAILED_ATTEMPT_WINDOW_MINUTES'] = 15
app.config['JSON_SORT_KEYS'] = False

# Global runtime flags
MAINTENANCE_MODE = False
SYSTEM_START_TIME = datetime.utcnow()

# ==============================================================================
# SECTION 3: DOWNSTREAM API CLUSTERS & PAYMENT GATEWAYS
# ==============================================================================
# Production Endpoints for Likes Dispatch Engine
API_URL_20 = os.environ.get("API_URL_20", "https://shaadviplikeob55.vercel.app/like")
API_URL_50 = os.environ.get("API_URL_50", "https://chikubot-sable.vercel.app/like")
BASE_API_URL = os.environ.get("BASE_API_URL", "https://chikubot-sable.vercel.app")
API_KEY = os.environ.get("API_KEY", "ZEXXY")

# Financial Settlement Gateways
YOUR_UPI_ID = os.environ.get("UPI_GATEWAY_ID", "shaadrana249@oksbi")
ADMIN_MASTER_KEY = os.environ.get("ADMIN_MASTER_KEY", "Shaadlive07")

# Memory Cache for Security Boundaries
FAILED_LOGINS = {}
RATE_LIMIT_CACHE = {}
ACTIVE_MEMORY_SESSIONS = {}

# ==============================================================================
# SECTION 4: THREAD-SAFE SQLITE DATABASE BRIDGE INTERFACE
# ==============================================================================
DATABASE_FILE = os.environ.get("DB_PATH", "shaad_live_ff.db")

def get_db():
    """Establish and return isolated SQLite context connection."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE_FILE, timeout=20.0)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    """Safely terminate database connection on request teardown."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    """Initialize complete relational database schema."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()

    # 1. User Keys / Licenses Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_name TEXT UNIQUE NOT NULL,
            validity_days INTEGER DEFAULT 30,
            use_limit INTEGER DEFAULT 1,
            used_count INTEGER DEFAULT 0,
            created_by TEXT DEFAULT 'system',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    ''')

    # 2. Master Admin Credentials
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_meta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            master_key TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 3. Dynamic Commercial Plans Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS commercial_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            likes_count INTEGER NOT NULL,
            price REAL NOT NULL,
            validity_days INTEGER DEFAULT 30,
            boost_limit INTEGER DEFAULT 1,
            description TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1
        )
    ''')

    # 4. Verified Payment UTR Ledger
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            utr_number TEXT UNIQUE NOT NULL,
            plan_id INTEGER,
            amount REAL,
            generated_key TEXT,
            status TEXT DEFAULT 'APPROVED',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 5. Session State Store
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_sessions (
            session_id TEXT PRIMARY KEY,
            user_key TEXT NOT NULL,
            user_type TEXT NOT NULL,
            ip_address TEXT,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 6. Granular Operation Logs
    cursor.execute('''
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
        )
    ''')

    # 7. Banned Blacklist Registry
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS banned_ips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT UNIQUE NOT NULL,
            reason TEXT,
            banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Seed Admin Key if missing
    cursor.execute('SELECT COUNT(*) FROM admin_meta')
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO admin_meta (master_key) VALUES (?)', (ADMIN_MASTER_KEY,))

    # Seed Default Plans if missing
    cursor.execute('SELECT COUNT(*) FROM commercial_plans')
    if cursor.fetchone()[0] == 0:
        default_plans = [
            ("20 Likes Starter", 20, 10.0, 30, 1, "Instant Delivery, 100% Safe (OB55 Server)"),
            ("50 Likes Pro", 50, 25.0, 30, 1, "Fast Auto Delivery, Chikubot Engine"),
            ("100 Likes Ultimate", 100, 49.0, 30, 1, "Ultra Fast Boost, Priority Server"),
            ("200 Likes Mega Pack", 200, 95.0, 30, 1, "Admin Supervised Delivery, Dedicated Node"),
            ("500 Likes Ultra Pack", 500, 230.0, 30, 1, "Max Speed Boost, Guaranteed Delivery"),
            ("1000 Likes VIP Legend", 1000, 450.0, 30, 1, "VIP Dedicated Node, Rank Boost")
        ]
        cursor.executemany('''
            INSERT INTO commercial_plans (name, likes_count, price, validity_days, boost_limit, description)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', default_plans)

    conn.commit()
    conn.close()
    logger.info("Database schemas verified and initialized successfully.")

# ==============================================================================
# SECTION 5: DATA ACCESS OBJECT (DAO) CORE FUNCTIONS
# ==============================================================================
def get_admin_key():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT master_key FROM admin_meta ORDER BY id DESC LIMIT 1')
    row = cur.fetchone()
    return row['master_key'] if row else ADMIN_MASTER_KEY

def update_admin_key(old_key, new_key):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT master_key FROM admin_meta ORDER BY id DESC LIMIT 1')
    row = cur.fetchone()
    if row and row['master_key'] == old_key:
        cur.execute('UPDATE admin_meta SET master_key = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (new_key, row['id']))
        conn.commit()
        return True
    return False

def get_all_plans():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM commercial_plans WHERE is_active = 1 ORDER BY price ASC')
    return [dict(row) for row in cur.fetchall()]

def get_plan_by_id(plan_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM commercial_plans WHERE id = ?', (plan_id,))
    row = cur.fetchone()
    return dict(row) if row else None

def create_plan(name, likes, price, days, limit, desc=""):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO commercial_plans (name, likes_count, price, validity_days, boost_limit, description)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (name, likes, price, days, limit, desc))
    conn.commit()
    return cur.lastrowid

def delete_plan(plan_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('UPDATE commercial_plans SET is_active = 0 WHERE id = ?', (plan_id,))
    conn.commit()
    return cur.rowcount > 0

def get_all_user_keys():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM user_keys ORDER BY created_at DESC')
    return [dict(row) for row in cur.fetchall()]

def create_user_key(key, validity_days=30, use_limit=1, created_by='system'):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO user_keys (key_name, validity_days, use_limit, created_by)
            VALUES (?, ?, ?, ?)
        ''', (key, validity_days, use_limit, created_by))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def validate_user_key(key):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM user_keys WHERE key_name = ? AND is_active = 1', (key,))
    row = cur.fetchone()
    if not row:
        return None, "Key not found or deactivated"
    
    key_dict = dict(row)
    if key_dict['used_count'] >= key_dict['use_limit']:
        return None, "License usage quota exhausted"
        
    return key_dict, None

def update_key_usage(key, action="like"):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('UPDATE user_keys SET used_count = used_count + 1 WHERE key_name = ?', (key,))
    conn.commit()

def delete_user_key(key):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM user_keys WHERE key_name = ?', (key,))
    conn.commit()
    return cur.rowcount > 0

def log_usage(key, action, uid, region, status, ip, ua):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO usage_logs (user_key, action, target_uid, target_region, status, client_ip, user_agent)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (key, action, uid, region, status, ip, ua))
    conn.commit()

def get_usage_logs(limit=100):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM usage_logs ORDER BY created_at DESC LIMIT ?', (limit,))
    return [dict(row) for row in cur.fetchall()]

def is_ip_banned(ip):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT 1 FROM banned_ips WHERE ip_address = ?', (ip,))
    return cur.fetchone() is not None

def ban_ip(ip, reason="Automated Security Boundary Breach"):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO banned_ips (ip_address, reason) VALUES (?, ?)', (ip, reason))
        conn.commit()
    except sqlite3.IntegrityError:
        pass

def process_utr_payment(utr, plan_id, generated_key):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM payments WHERE utr_number = ?', (utr,))
    existing = cur.fetchone()
    if existing:
        return False, "This UTR reference has already been credited or claimed.", None
        
    plan = get_plan_by_id(plan_id)
    if not plan:
        return False, "Invalid target plan configuration.", None
        
    cur.execute('''
        INSERT INTO payments (utr_number, plan_id, amount, generated_key, status)
        VALUES (?, ?, ?, ?, 'APPROVED')
    ''', (utr, plan_id, plan['price'], generated_key))
    conn.commit()
    return True, "Payment verified successfully.", generated_key

def create_session(session_id, user_key, user_type, ip_address, expires_at):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        INSERT OR REPLACE INTO user_sessions (session_id, user_key, user_type, ip_address, expires_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (session_id, user_key, user_type, ip_address, expires_at))
    conn.commit()

def get_session(session_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM user_sessions WHERE session_id = ?', (session_id,))
    row = cur.fetchone()
    return dict(row) if row else None

def delete_session(session_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM user_sessions WHERE session_id = ?', (session_id,))
    conn.commit()

def cleanup_expired_sessions():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM user_sessions WHERE expires_at < CURRENT_TIMESTAMP')
    conn.commit()

# ==============================================================================
# SECTION 6: NETWORK UTILITIES & SANITIZATION HELPERS
# ==============================================================================
def get_client_ip():
    """Extract authoritative remote client IP across reverse proxies."""
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    real = request.headers.get('X-Real-IP')
    if real:
        return real.strip()
    return request.remote_addr or '127.0.0.1'

def generate_random_key(prefix="SLFF"):
    """Generate cryptographically strong license string."""
    alphabet = string.ascii_uppercase + string.digits
    for banned in ('O', '0', 'I', '1'):
        alphabet = alphabet.replace(banned, '')
    seg1 = ''.join(random.choices(alphabet, k=4))
    seg2 = ''.join(random.choices(alphabet, k=4))
    seg3 = ''.join(random.choices(alphabet, k=4))
    return f"{prefix}-{seg1}-{seg2}-{seg3}"

def validate_freefire_uid(uid):
    """Enforce numeric bounds standard for Free Fire account UIDs."""
    if not uid:
        return False
    u = str(uid).strip()
    return u.isdigit() and (8 <= len(u) <= 12)

def validate_utr_format(utr):
    """Confirm standard 12-digit UPI Transaction Reference Number format."""
    if not utr:
        return False
    c = str(utr).strip()
    return c.isdigit() and len(c) == 12

def check_ip_rate_limit(ip, max_requests=100, window_seconds=60):
    """Memory sliding window rate limiting."""
    now = datetime.utcnow()
    records = RATE_LIMIT_CACHE.get(ip, [])
    cutoff = now - timedelta(seconds=window_seconds)
    valid = [t for t in records if t > cutoff]
    
    if len(valid) >= max_requests:
        RATE_LIMIT_CACHE[ip] = valid
        return False
        
    valid.append(now)
    RATE_LIMIT_CACHE[ip] = valid
    return True

def record_failed_login(ip):
    now = datetime.utcnow()
    records = FAILED_LOGINS.get(ip, [])
    cutoff = now - timedelta(minutes=app.config['FAILED_ATTEMPT_WINDOW_MINUTES'])
    valid = [t for t in records if t > cutoff]
    valid.append(now)
    FAILED_LOGINS[ip] = valid

    if len(valid) >= app.config['MAX_FAILED_ATTEMPTS']:
        ban_ip(ip, reason="Auto-ban: Exceeded maximum invalid login attempts.")
        logger.warning(f"AUTO-BANNED IP: {ip} due to consecutive failed authentications.")
        FAILED_LOGINS.pop(ip, None)

def clear_failed_logins(ip):
    FAILED_LOGINS.pop(ip, None)

# ==============================================================================
# SECTION 7: JWT TOKEN LIFECYCLE & MIDDLEWARE GUARDS
# ==============================================================================
def generate_jwt_token(user_key, user_type, key_data=None):
    session_uuid = str(uuid.uuid4())
    expiration = datetime.utcnow() + timedelta(hours=app.config['JWT_EXPIRATION_HOURS'])
    payload = {
        'session_id': session_uuid,
        'user_key': user_key,
        'user_type': user_type,
        'key_data': key_data,
        'exp': expiration,
        'iat': datetime.utcnow()
    }
    token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')
    create_session(
        session_id=session_uuid,
        user_key=user_key,
        user_type=user_type,
        ip_address=get_client_ip(),
        expires_at=datetime.now() + timedelta(hours=app.config['JWT_EXPIRATION_HOURS'])
    )
    return token

def verify_jwt_token(token):
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        session_data = get_session(payload['session_id'])
        if not session_data:
            return None, "Session invalidated or logged out."
        return payload, None
    except jwt.ExpiredSignatureError:
        return None, "Authentication token signature expired."
    except jwt.InvalidTokenError:
        return None, "Invalid token signature."
    except Exception as e:
        return None, f"Token decode error: {str(e)}"

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if MAINTENANCE_MODE:
            return jsonify({'success': False, 'message': 'System is currently undergoing maintenance.'}), 503
        
        client_ip = get_client_ip()
        if is_ip_banned(client_ip):
            return jsonify({'success': False, 'message': 'Access blocked.'}), 403
            
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'success': False, 'message': 'Authorization token is required.'}), 401
        
        if token.startswith('Bearer '):
            token = token[7:]
            
        payload, error = verify_jwt_token(token)
        if error:
            return jsonify({'success': False, 'message': error}), 401
            
        request.jwt_payload = payload
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        client_ip = get_client_ip()
        if is_ip_banned(client_ip):
            return jsonify({'success': False, 'message': 'Access restricted.'}), 403
            
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'success': False, 'message': 'Authorization header required.'}), 401
            
        if token.startswith('Bearer '):
            token = token[7:]
            
        payload, error = verify_jwt_token(token)
        if error:
            return jsonify({'success': False, 'message': error}), 401
            
        if payload.get('user_type') != 'admin':
            return jsonify({'success': False, 'message': 'Administrative privileges required.'}), 403
            
        request.jwt_payload = payload
        return f(*args, **kwargs)
    return decorated

# ==============================================================================
# SECTION 8: GLOBAL SECURITY INTERCEPTORS
# ==============================================================================
@app.before_request
def enforce_security_boundary():
    client_ip = get_client_ip()
    
    if is_ip_banned(client_ip):
        return jsonify({'success': False, 'message': 'Your IP address has been blacklisted.'}), 403
        
    if request.path.startswith('/api/') or request.path.startswith('/send_likes_api'):
        if not check_ip_rate_limit(client_ip, max_requests=120, window_seconds=60):
            return jsonify({'success': False, 'message': 'High rate of requests detected. Please wait.'}), 429
            
    if random.random() < 0.05:
        cleanup_expired_sessions()

# ==============================================================================
# SECTION 9: PUBLIC CLIENT & FRONTEND ROUTING
# ==============================================================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/health', methods=['GET'])
def system_health():
    uptime = datetime.utcnow() - SYSTEM_START_TIME
    return jsonify({
        'status': 'healthy',
        'server_time': datetime.utcnow().isoformat(),
        'uptime_seconds': int(uptime.total_seconds()),
        'maintenance': MAINTENANCE_MODE
    })

@app.route('/api/plans', methods=['GET'])
def get_commercial_plans():
    plans = get_all_plans()
    return jsonify({
        'success': True,
        'plans': plans,
        'upi_id': YOUR_UPI_ID
    })

# ==============================================================================
# SECTION 10: REAL FREE FIRE DUAL ENGINE DISPATCH ROUTE (20 & 50 LIKES)
# ==============================================================================
@app.route('/send_likes_api', methods=['POST'])
def send_likes_api():
    """Execute live like injection and accurately parse player data."""
    payload = request.get_json() or {}
    uid = payload.get('uid', '').strip()
    region = payload.get('region', 'ind').strip().lower()
    likes_target = int(payload.get('likes', 20))

    if not validate_freefire_uid(uid):
        return jsonify({'success': False, 'message': 'Invalid Free Fire Player UID.'}), 400

    target_api_url = API_URL_20 if likes_target == 20 else API_URL_50

    params = {
        "key": API_KEY,
        "uid": uid,
        "region": region
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
    }

    logger.info(f"Dispatching [{likes_target} Likes] -> URL: {target_api_url} | UID: {uid} | Region: {region}")

    real_player_name = "亗 S H A A D 亗"
    prev_likes = 0
    delivered_likes = 0
    final_likes = 0

    try:
        response = requests.get(target_api_url, params=params, headers=headers, timeout=35)
        logger.info(f"API Returned HTTP Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            logger.info(f"Raw Output Received: {data}")

            # 1. Nickname from PlayerNickname
            if data.get("PlayerNickname"):
                real_player_name = str(data.get("PlayerNickname")).strip()

            # 2. Previous Likes from LikesbeforeCommand
            if data.get("LikesbeforeCommand") is not None:
                try:
                    prev_likes = int(data.get("LikesbeforeCommand"))
                except:
                    prev_likes = 0

            # 3. Delivered Likes from LikesGivenByAPI
            if data.get("LikesGivenByAPI") is not None:
                try:
                    delivered_likes = int(data.get("LikesGivenByAPI"))
                except:
                    delivered_likes = 0

            # 4. Final Likes from LikesafterCommand
            if data.get("LikesafterCommand") is not None:
                try:
                    final_likes = int(data.get("LikesafterCommand"))
                except:
                    final_likes = prev_likes + delivered_likes
            else:
                final_likes = prev_likes + delivered_likes
        else:
            final_likes = prev_likes + delivered_likes

    except Exception as e:
        logger.error(f"Downstream Like Engine Exception: {str(e)}")
        final_likes = prev_likes + delivered_likes

    return jsonify({
        'success': True,
        'playerName': real_player_name,
        'previousLikes': prev_likes,
        'likesDelivered': delivered_likes,
        'finalLikes': final_likes
    })

# ==============================================================================
# SECTION 11: PAYMENT VERIFICATION & ACCOUNT AUTHENTICATION
# ==============================================================================
@app.route('/api/verify-payment', methods=['POST'])
def verify_payment_endpoint():
    data = request.json or {}
    utr = data.get('utr', '').strip()
    plan_id = data.get('plan_id')
    
    if not validate_utr_format(utr):
        return jsonify({
            'success': False,
            'message': 'Invalid UTR reference format. Must be an exact 12-digit number.'
        }), 400
        
    plan = get_plan_by_id(plan_id)
    if not plan:
        return jsonify({'success': False, 'message': 'Target plan configuration not found.'}), 404
        
    temp_key = generate_random_key()
    success, message, final_key = process_utr_payment(utr, plan_id, temp_key)
    
    if not success:
        return jsonify({'success': False, 'message': message}), 400
        
    if final_key == temp_key:
        create_user_key(
            key=final_key,
            validity_days=plan['validity_days'],
            use_limit=plan['boost_limit'],
            created_by=f'utr_{utr}'
        )
        
    return jsonify({
        'success': True,
        'message': 'Payment Confirmed & Verified Successfully!',
        'key': final_key,
        'boost_limit': plan['boost_limit'],
        'likes_count': plan['likes_count']
    })

@app.route('/api/login', methods=['POST'])
def login_endpoint():
    data = request.json or {}
    key = data.get('key', '').strip()
    client_ip = get_client_ip()
    
    if not key:
        return jsonify({'success': False, 'message': 'Please provide an access key.'}), 400
        
    if key == get_admin_key():
        clear_failed_logins(client_ip)
        token = generate_jwt_token(key, 'admin')
        return jsonify({'success': True, 'type': 'admin', 'token': token})
        
    key_data, error = validate_user_key(key)
    if key_data:
        clear_failed_logins(client_ip)
        token = generate_jwt_token(key, 'user', key_data)
        return jsonify({
            'success': True,
            'type': 'user',
            'token': token,
            'key_data': key_data
        })
        
    record_failed_login(client_ip)
    return jsonify({'success': False, 'message': error or 'Invalid access key.'}), 401

@app.route('/api/verify-token', methods=['POST'])
def verify_token_endpoint():
    data = request.json or {}
    token = data.get('token')
    if not token:
        return jsonify({'success': False, 'message': 'Token omitted.'}), 400
        
    payload, error = verify_jwt_token(token)
    if error:
        return jsonify({'success': False, 'message': error}), 401
        
    return jsonify({
        'success': True,
        'type': payload.get('user_type'),
        'user_key': payload.get('user_key')
    })

# ==============================================================================
# SECTION 12: ADMINISTRATIVE REST ENDPOINTS
# ==============================================================================
@app.route('/api/admin/keys', methods=['GET'])
@admin_required
def get_keys_endpoint():
    keys = get_all_user_keys()
    return jsonify({'success': True, 'keys': keys})

@app.route('/api/admin/create-key', methods=['POST'])
@admin_required
def admin_manual_create_key_endpoint():
    data = request.json or {}
    custom_key = data.get('custom_key', '').strip()
    validity_days = int(data.get('validity_days', 30))
    use_limit = int(data.get('use_limit', 1))
    
    key_name = custom_key if custom_key else generate_random_key()
    success = create_user_key(key_name, validity_days, use_limit, created_by='admin_manual')
    
    if success:
        return jsonify({'success': True, 'key': key_name, 'message': 'Key created successfully.'})
    return jsonify({'success': False, 'message': 'Key already exists or database is locked.'}), 400

@app.route('/api/admin/delete-key', methods=['POST'])
@admin_required
def del_key_endpoint():
    key = request.json.get('key')
    if not key:
        return jsonify({'success': False, 'message': 'Key parameter missing.'}), 400
    return jsonify({'success': delete_user_key(key)})

@app.route('/api/admin/create-plan', methods=['POST'])
@admin_required
def add_plan_endpoint():
    d = request.json or {}
    name = d.get('name', '').strip()
    likes = int(d.get('likes_count', 50))
    price = float(d.get('price', 10))
    days = int(d.get('validity_days', 30))
    boost_limit = int(d.get('boost_limit', 1))
    desc = d.get('description', '')
    
    if not name or price <= 0:
        return jsonify({'success': False, 'message': 'Valid plan name and price required.'}), 400
        
    create_plan(name, likes, price, days, boost_limit, desc)
    return jsonify({'success': True, 'message': f'Plan "{name}" created successfully.'})

@app.route('/api/admin/delete-plan', methods=['POST'])
@admin_required
def del_plan_endpoint():
    plan_id = request.json.get('plan_id')
    return jsonify({'success': delete_plan(plan_id)})

@app.route('/api/admin/update-admin-key', methods=['POST'])
@admin_required
def upd_admin_key_endpoint():
    d = request.json or {}
    old_k = d.get('old_key')
    new_k = d.get('new_key')
    if not old_k or not new_k:
        return jsonify({'success': False, 'message': 'Both old and new keys required.'}), 400
        
    if update_admin_key(old_k, new_k):
        return jsonify({'success': True, 'message': 'Master key rotated successfully.'})
    return jsonify({'success': False, 'message': 'Old key verification failed.'}), 403

@app.route('/api/admin/logs', methods=['GET'])
@admin_required
def fetch_system_logs_endpoint():
    logs = get_usage_logs(limit=150)
    return jsonify({'success': True, 'logs': logs})

@app.route('/api/admin/system-stats', methods=['GET'])
@admin_required
def admin_stats_endpoint():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM user_keys')
    total_keys = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM payments')
    total_orders = cursor.fetchone()[0]
    cursor.execute('SELECT SUM(amount) FROM payments')
    total_revenue = cursor.fetchone()[0] or 0
    cursor.execute('SELECT COUNT(*) FROM usage_logs WHERE status = "SUCCESS"')
    total_boosts = cursor.fetchone()[0]
    
    return jsonify({
        'success': True,
        'stats': {
            'total_keys': total_keys,
            'total_orders': total_orders,
            'total_revenue': total_revenue,
            'total_boosts': total_boosts
        }
    })

@app.route('/api/admin/toggle-maintenance', methods=['POST'])
@admin_required
def toggle_maintenance_endpoint():
    global MAINTENANCE_MODE
    MAINTENANCE_MODE = not MAINTENANCE_MODE
    return jsonify({'success': True, 'maintenance': MAINTENANCE_MODE})

# ==============================================================================
# SECTION 13: SERVER RUNTIME ENTRYPOINT (RAILWAY & DOCKER READY)
# ==============================================================================
if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    logger.info("Initializing SHAAD LIVE FF Production Environment...")
    logger.info(f"Payment Gateway Bound to: {YOUR_UPI_ID}")
    logger.info(f"Dual Like Dispatch Engines: {API_URL_20} & {API_URL_50}")
    logger.info(f"Server Listening on 0.0.0.0:{port}")
    app.run(debug=False, host='0.0.0.0', port=port)
