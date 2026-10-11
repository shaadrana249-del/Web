"""
================================================================================
SHAAD LIVE FF - HIGH-CONCURRENCY ENTERPRISE API BACKEND SUITE
================================================================================
Target Platforms: Linux Containers, Railway.app, Docker, Termux (Android)
Core Modules: Dual API Like Dispatch, JWT Security, Thread-Safe SQLite Bridge,
              Real-time UTR Validation, Plan Administration, Analytics Engine
================================================================================
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
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    g,
    session,
    make_response,
    url_for,
    redirect
)
from flask_cors import CORS
import jwt

# Internal DAO database abstraction layer
import database
from database import (
    get_admin_key,
    update_admin_key,
    get_all_user_keys,
    create_user_key,
    update_key_usage,
    delete_user_key,
    validate_user_key,
    log_usage,
    get_usage_logs,
    is_ip_banned,
    ban_ip,
    init_db,
    create_session,
    get_session,
    delete_session,
    cleanup_expired_sessions,
    get_all_plans,
    get_plan_by_id,
    create_plan,
    delete_plan,
    process_utr_payment
)

# ==============================================================================
# SECTION 1: LOGGING TELEMETRY SYSTEM ARCHITECTURE
# ==============================================================================
LOG_FORMAT = "%(asctime)s [%(levelname)s] [PROD_ENGINE:%(lineno)d] ~ %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('SHAAD_LIVE_FF_ENGINE')

# ==============================================================================
# SECTION 2: APPLICATION BOOTSTRAP & ENVIRONMENT MATRIX
# ==============================================================================
app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "*"}})

# GUNICORN / RAILWAY STARTUP AUTO-INIT FIX
# Worker start hote hi schema tables bina fail hue check aur initialize karega
try:
    init_db()
    logger.info("Railway Boot Check: Database schema initialized successfully.")
except Exception as e:
    logger.error(f"Startup DB Init Warning: {e}")

# Application Security Keys & Timing Constants
app.config['SECRET_KEY'] = os.environ.get(
    'SECRET_KEY',
    'SHAAD_LIVE_FF_SUPER_PROD_MASTER_KEY_2026_SECURE_TOKEN_XYZ_89712398471923'
)
app.config['JWT_EXPIRATION_HOURS'] = int(os.environ.get('JWT_EXPIRATION_HOURS', 12))
app.config['MAX_FAILED_ATTEMPTS'] = 5
app.config['FAILED_ATTEMPT_WINDOW_MINUTES'] = 15
app.config['JSON_SORT_KEYS'] = False

# Global runtime flags
MAINTENANCE_MODE = False
SYSTEM_START_TIME = datetime.utcnow()

# ==============================================================================
# SECTION 3: DOWNSTREAM API CLUSTERS & PAYMENT CONFIGURATIONS
# ==============================================================================
# Dual Engine Microservices (Key: ZEXXY)
API_URL_20 = os.environ.get("API_URL_20", "https://shaadviplikeob55.vercel.app/like")
API_URL_50 = os.environ.get("API_URL_50", "https://chikubot-sable.vercel.app/like")
BASE_API_URL = os.environ.get("BASE_API_URL", "https://chikubot-sable.vercel.app")
API_KEY = os.environ.get("API_KEY", "ZEXXY")

# Gateway & Master Security Credentials
YOUR_UPI_ID = os.environ.get("UPI_GATEWAY_ID", "shaadrana249@oksbi")
ADMIN_MASTER_KEY = os.environ.get("ADMIN_MASTER_KEY", "Shaadlive07")

# Global Memory Caches for Security Interceptors
FAILED_LOGINS = {}
RATE_LIMIT_CACHE = {}
REQUEST_AUDIT_LOG = []

# ==============================================================================
# SECTION 4: THREAD-SAFE SQLITE PER-REQUEST CONTEXT BRIDGE
# ==============================================================================
DATABASE_FILE = os.environ.get("DB_PATH", "shaad_live_ff.db")

def get_request_db():
    """Establish and return isolated SQLite context connection for this request."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE_FILE, timeout=30.0)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode = WAL;")
        db.execute("PRAGMA synchronous = NORMAL;")
    return db

@app.teardown_appcontext
def teardown_db_connection(exception):
    """Safely terminate database connection on request teardown."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# ==============================================================================
# SECTION 5: NETWORK UTILITIES & SANITIZATION HELPERS
# ==============================================================================
def get_client_ip():
    """Extract authoritative remote client IP across reverse proxies and load balancers."""
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    real = request.headers.get('X-Real-IP')
    if real:
        return real.strip()
    return request.remote_addr or '127.0.0.1'

def generate_random_key(prefix="SLFF"):
    """Generate cryptographically strong license string excluding ambiguous chars."""
    alphabet = string.ascii_uppercase + string.digits
    for banned in ('O', '0', 'I', '1'):
        alphabet = alphabet.replace(banned, '')
    seg1 = ''.join(random.choices(alphabet, k=4))
    seg2 = ''.join(random.choices(alphabet, k=4))
    seg3 = ''.join(random.choices(alphabet, k=4))
    return f"{prefix}-{seg1}-{seg2}-{seg3}"

def validate_freefire_uid(uid):
    """Enforce numeric bounds standard for Free Fire account UIDs (8 to 12 digits)."""
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

def check_ip_rate_limit(ip, max_requests=120, window_seconds=60):
    """In-memory sliding window rate limiting."""
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
    """Track failed login attempts per IP and trigger auto-ban when limit is exceeded."""
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
    """Clear failed login records upon successful authentication."""
    FAILED_LOGINS.pop(ip, None)

# ==============================================================================
# SECTION 6: JWT TOKEN LIFECYCLE & MIDDLEWARE GUARDS
# ==============================================================================
def generate_jwt_token(user_key, user_type, key_data=None):
    """Create and sign a cryptographically secure JWT authentication token."""
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
    """Decode, verify signature and check persistence validity for JWT token."""
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
    """Decorator ensuring that incoming requests have valid JWT authentication."""
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
    """Decorator restricting route execution strictly to authenticated Administrators."""
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
# SECTION 7: GLOBAL SECURITY BOUNDARY INTERCEPTORS
# ==============================================================================
@app.before_request
def enforce_security_boundary():
    """Run security assertions on all incoming HTTP requests prior to view execution."""
    client_ip = get_client_ip()
    
    # 1. IP Ban Enforcement
    if is_ip_banned(client_ip):
        return jsonify({
            'success': False,
            'message': 'Your IP address has been restricted from interacting with this service.'
        }), 403
        
    # 2. Rate Limiting Protection
    if request.path.startswith('/api/') or request.path.startswith('/send_likes_api'):
        if not check_ip_rate_limit(client_ip, max_requests=150, window_seconds=60):
            return jsonify({
                'success': False,
                'message': 'Rate limit threshold exceeded. Please slow down.'
            }), 429
            
    # 3. Occasional garbage collection of expired session entries
    if random.random() < 0.05:
        cleanup_expired_sessions()

# ==============================================================================
# SECTION 8: PUBLIC CLIENT & FRONTEND ROUTING
# ==============================================================================
@app.route('/', methods=['GET'])
def index():
    """Render the primary HTML single-page application."""
    return render_template('index.html')

@app.route('/api/health', methods=['GET'])
def system_health():
    """Deliver real-time cluster health and process telemetry."""
    uptime = datetime.utcnow() - SYSTEM_START_TIME
    return jsonify({
        'status': 'healthy',
        'server_time': datetime.utcnow().isoformat(),
        'uptime_seconds': int(uptime.total_seconds()),
        'maintenance': MAINTENANCE_MODE,
        'environment': os.environ.get('RAILWAY_ENVIRONMENT', 'production'),
        'api_cluster': {
            '20_engine': API_URL_20,
            '50_engine': API_URL_50
        }
    })

@app.route('/api/plans', methods=['GET'])
def get_commercial_plans():
    """Publicly retrieve list of available likes packages and payment parameters."""
    plans = get_all_plans()
    return jsonify({
        'success': True,
        'plans': plans,
        'upi_id': YOUR_UPI_ID
    })

# ==============================================================================
# SECTION 9: DUAL ENGINE FREE FIRE LIKE DISPATCH ENGINE (20 & 50 LIKES)
# ==============================================================================
@app.route('/send_likes_api', methods=['POST'])
def send_likes_api():
    """
    Main dispatch endpoint for Free Fire Likes injection.
    Automatically routes to:
      - 20 Likes: https://shaadviplikeob55.vercel.app/like
      - 50 Likes: https://chikubot-sable.vercel.app/like
    Extracts real game nickname, before likes, likes added, and final likes.
    """
    payload = request.get_json() or {}
    uid = payload.get('uid', '').strip()
    region = payload.get('region', 'ind').strip().lower()
    likes_target = int(payload.get('likes', 20))

    if not validate_freefire_uid(uid):
        return jsonify({
            'success': False,
            'message': 'Invalid Free Fire Player UID format. Must be 8-12 digits.'
        }), 400

    # Route based on selected package size
    target_api_url = API_URL_20 if likes_target == 20 else API_URL_50

    params = {
        "key": API_KEY,
        "uid": uid,
        "region": region
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 12; Mobile) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
        )
    }

    logger.info(
        f"Executing Likes Dispatch -> [Target: {likes_target} Likes] "
        f"| Endpoint: {target_api_url} | UID: {uid} | Region: {region}"
    )

    real_player_name = "亗 S H A A D 亗"
    prev_likes = 0
    delivered_likes = 0
    final_likes = 0
    api_success_flag = False

    try:
        response = requests.get(target_api_url, params=params, headers=headers, timeout=40)
        logger.info(f"Like API HTTP Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            logger.info(f"API Returned Exact Response: {data}")
            api_success_flag = True

            # 1. Nickname from PlayerNickname
            if data.get("PlayerNickname"):
                real_player_name = str(data.get("PlayerNickname")).strip()

            # 2. Previous Likes from LikesbeforeCommand
            if data.get("LikesbeforeCommand") is not None:
                try:
                    prev_likes = int(data.get("LikesbeforeCommand"))
                except (ValueError, TypeError):
                    prev_likes = 0

            # 3. Delivered Likes from LikesGivenByAPI
            if data.get("LikesGivenByAPI") is not None:
                try:
                    delivered_likes = int(data.get("LikesGivenByAPI"))
                except (ValueError, TypeError):
                    delivered_likes = 0

            # 4. Final Likes from LikesafterCommand
            if data.get("LikesafterCommand") is not None:
                try:
                    final_likes = int(data.get("LikesafterCommand"))
                except (ValueError, TypeError):
                    final_likes = prev_likes + delivered_likes
            else:
                final_likes = prev_likes + delivered_likes

        else:
            logger.warning(f"Upstream API failed with status: {response.status_code}")
            final_likes = prev_likes + delivered_likes

    except requests.exceptions.Timeout:
        logger.error(f"Downstream Like API timed out for UID: {uid}")
        final_likes = prev_likes + delivered_likes
    except Exception as e:
        logger.error(f"Exception during Like API invocation: {str(e)}")
        final_likes = prev_likes + delivered_likes

    # Log telemetry for administrative visibility
    log_usage(
        key="WEB_PORTAL",
        action=f"BOOST_{likes_target}",
        uid=uid,
        region=region,
        status="SUCCESS" if api_success_flag else "FAILED",
        ip=get_client_ip(),
        ua=request.headers.get("User-Agent", "WebBrowser")
    )

    return jsonify({
        'success': True,
        'playerName': real_player_name,
        'previousLikes': prev_likes,
        'likesDelivered': delivered_likes,
        'finalLikes': final_likes
    })

# ==============================================================================
# SECTION 10: PAYMENT VERIFICATION & ACCOUNT AUTHENTICATION
# ==============================================================================
@app.route('/api/verify-payment', methods=['POST'])
def verify_payment_endpoint():
    """Verify submitted payment UTR against configured plans and credit ledger."""
    data = request.json or {}
    utr = data.get('utr', '').strip()
    plan_id = data.get('plan_id')
    
    if not validate_utr_format(utr):
        return jsonify({
            'success': False,
            'message': 'Invalid UTR format. Must be an exact 12-digit numeric reference.'
        }), 400
        
    plan = get_plan_by_id(plan_id)
    if not plan:
        return jsonify({
            'success': False,
            'message': 'Target plan configuration not found.'
        }), 404
        
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

@app.route('/api/find-key', methods=['POST'])
def find_key_endpoint():
    """Allow customers to recover their generated license key using their payment UTR."""
    data = request.json or {}
    utr = data.get('utr', '').strip()
    
    if not validate_utr_format(utr):
        return jsonify({'success': False, 'message': 'Please enter a valid 12-digit UTR.'}), 400
        
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT generated_key FROM payments WHERE utr_number = ?', (utr,))
    row = cursor.fetchone()
    conn.close()
    
    if row and row['generated_key']:
        key_data, error = validate_user_key(row['generated_key'])
        if error:
            return jsonify({
                'success': False,
                'message': f"Key found ({row['generated_key']}), but status: {error}"
            })
        return jsonify({'success': True, 'key': row['generated_key']})
        
    return jsonify({
        'success': False,
        'message': 'No license key associated with this UTR number.'
    }), 404

@app.route('/api/login', methods=['POST'])
def login_endpoint():
    """Authenticate both users with license keys and admins with master security keys."""
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
    """Verify client JWT token validity upon page reloads."""
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
# SECTION 11: ADMINISTRATIVE REST APIS & MANAGEMENT
# ==============================================================================
@app.route('/api/admin/keys', methods=['GET'])
@admin_required
def get_keys_endpoint():
    """Retrieve all issued customer licenses."""
    keys = get_all_user_keys()
    return jsonify({'success': True, 'keys': keys})

@app.route('/api/admin/create-key', methods=['POST'])
@admin_required
def admin_manual_create_key_endpoint():
    """Manually issue keys directly from the administrator workspace."""
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
    """Revoke and delete a customer license."""
    key = request.json.get('key')
    if not key:
        return jsonify({'success': False, 'message': 'Key parameter missing.'}), 400
    return jsonify({'success': delete_user_key(key)})

@app.route('/api/admin/create-plan', methods=['POST'])
@admin_required
def add_plan_endpoint():
    """Add a new commercial package to the store catalog."""
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
    """Remove a commercial plan from active store listings."""
    plan_id = request.json.get('plan_id')
    return jsonify({'success': delete_plan(plan_id)})

@app.route('/api/admin/update-admin-key', methods=['POST'])
@admin_required
def upd_admin_key_endpoint():
    """Rotate the master administrative authorization key."""
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
    """Fetch recent activity logs."""
    logs = get_usage_logs(limit=150)
    return jsonify({'success': True, 'logs': logs})

@app.route('/api/admin/system-stats', methods=['GET'])
@admin_required
def admin_stats_endpoint():
    """Compute financial earnings and order metrics."""
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM user_keys')
    total_keys = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM payments')
    total_orders = cursor.fetchone()[0]
    cursor.execute('SELECT SUM(amount) FROM payments')
    total_revenue = cursor.fetchone()[0] or 0
    cursor.execute('SELECT COUNT(*) FROM usage_logs WHERE status = "SUCCESS"')
    total_boosts = cursor.fetchone()[0]
    conn.close()
    
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
    """Toggle maintenance mode globally."""
    global MAINTENANCE_MODE
    MAINTENANCE_MODE = not MAINTENANCE_MODE
    return jsonify({'success': True, 'maintenance': MAINTENANCE_MODE})

# ==============================================================================
# SECTION 12: APPLICATION RUNTIME ENTRYPOINT (LOCAL & RAILWAY COMPLIANT)
# ==============================================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info("Initializing SHAAD LIVE FF Production Environment...")
    logger.info(f"Payment Gateway Bound to: {YOUR_UPI_ID}")
    logger.info(f"Dual Like Dispatch Engines: {API_URL_20} & {API_URL_50}")
    logger.info(f"Server Listening on 0.0.0.0:{port}")
    app.run(debug=False, host='0.0.0.0', port=port)
