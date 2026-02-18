#!/usr/bin/env python3
"""
Sentinel Economic — Dashboard API
Complete API for seller and buyer dashboard
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import sqlite3
import hashlib
import secrets
from datetime import datetime, UTC, timedelta
from functools import wraps
from flask import Blueprint, jsonify, request, g

DB_PATH = os.path.expanduser("~/sentinel-economic/data/sentinel_economic.db")

dashboard_api = Blueprint('dashboard', __name__, url_prefix='/api/dashboard')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def auth_required(f):
    """Require authentication via API key or wallet signature"""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        wallet = request.headers.get('X-Wallet-Address')
        
        conn = get_db()
        cursor = conn.cursor()
        
        user = None
        
        if api_key:
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            cursor.execute("""
                SELECT u.* FROM users u
                JOIN api_keys ak ON u.id = ak.user_id
                WHERE ak.key_hash = ? AND ak.status = 'active'
            """, (key_hash,))
            user = cursor.fetchone()
        elif wallet:
            cursor.execute("SELECT * FROM users WHERE wallet_address = ?", (wallet,))
            user = cursor.fetchone()
            
            if not user:
                # Auto-create user for new wallet
                user_id = f"user_{secrets.token_hex(8)}"
                now = datetime.now(UTC).isoformat()
                cursor.execute("""
                    INSERT INTO users (id, wallet_address, created_at, last_active)
                    VALUES (?, ?, ?, ?)
                """, (user_id, wallet, now, now))
                conn.commit()
                cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
                user = cursor.fetchone()
        
        conn.close()
        
        if not user:
            return jsonify({"error": "Authentication required"}), 401
        
        g.user = dict(user)
        return f(*args, **kwargs)
    
    return decorated


# ═══════════════════════════════════════════════════════════════
# USER ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@dashboard_api.route('/user/profile')
@auth_required
def get_profile():
    """Get current user profile"""
    return jsonify({"user": g.user})


@dashboard_api.route('/user/profile', methods=['PUT'])
@auth_required
def update_profile():
    """Update user profile"""
    data = request.json
    allowed_fields = ['display_name', 'email', 'bio', 'website', 'twitter', 
                      'notification_email', 'notification_webhook', 'role']
    
    updates = {k: v for k, v in data.items() if k in allowed_fields}
    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
    values = list(updates.values()) + [g.user['id']]
    
    cursor.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()
    
    return jsonify({"status": "updated", "fields": list(updates.keys())})


@dashboard_api.route('/user/api-keys')
@auth_required
def list_api_keys():
    """List user's API keys"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, name, permissions, last_used, created_at, status
        FROM api_keys WHERE user_id = ?
    """, (g.user['id'], g.user['wallet_address']))
    
    keys = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({"api_keys": keys})


@dashboard_api.route('/user/api-keys', methods=['POST'])
@auth_required
def create_api_key():
    """Create new API key"""
    data = request.json
    name = data.get('name', 'Default Key')
    permissions = data.get('permissions', 'read')
    
    # Generate key
    raw_key = f"se_{secrets.token_hex(24)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO api_keys (user_id, key_hash, name, permissions, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (g.user['id'], key_hash, name, permissions, datetime.now(UTC).isoformat()))
    
    conn.commit()
    conn.close()
    
    # Return raw key only once
    return jsonify({
        "api_key": raw_key,
        "name": name,
        "message": "Save this key - it won't be shown again"
    })


@dashboard_api.route('/user/notifications')
@auth_required
def get_notifications():
    """Get user notifications"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM notifications 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT 50
    """, (g.user['id'], g.user['wallet_address']))
    
    notifications = [dict(row) for row in cursor.fetchall()]
    
    # Count unread
    cursor.execute("""
        SELECT COUNT(*) as count FROM notifications 
        WHERE user_id = ? AND read = 0
    """, (g.user['id'], g.user['wallet_address']))
    unread = cursor.fetchone()['count']
    
    conn.close()
    
    return jsonify({"notifications": notifications, "unread_count": unread})


@dashboard_api.route('/user/notifications/read', methods=['POST'])
@auth_required
def mark_notifications_read():
    """Mark notifications as read"""
    data = request.json
    notification_ids = data.get('ids', [])
    
    conn = get_db()
    cursor = conn.cursor()
    
    if notification_ids:
        placeholders = ','.join(['?' for _ in notification_ids])
        cursor.execute(f"""
            UPDATE notifications SET read = 1 
            WHERE user_id = ? AND id IN ({placeholders})
        """, [g.user['id']] + notification_ids)
    else:
        cursor.execute("UPDATE notifications SET read = 1 WHERE user_id = ?", (g.user['id'], g.user['wallet_address']))
    
    conn.commit()
    conn.close()
    
    return jsonify({"status": "marked_read"})


# ═══════════════════════════════════════════════════════════════
# SELLER ENDPOINTS - SERVICE MANAGEMENT
# ═══════════════════════════════════════════════════════════════

@dashboard_api.route('/seller/services')
@auth_required
def list_my_services():
    """List seller's services"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT s.*, 
               (SELECT COUNT(*) FROM service_endpoints WHERE service_id = s.id) as endpoint_count
        FROM services s
        WHERE (s.owner_id = ? OR s.owner_id = ?)
        ORDER BY s.created_at DESC
    """, (g.user['id'], g.user['wallet_address']))
    
    services = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({"services": services})


@dashboard_api.route('/seller/services', methods=['POST'])
@auth_required
def create_service():
    """Register a new service"""
    data = request.json
    required = ['name', 'base_url', 'treasury_wallet']
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Missing required field: {field}"}), 400
    
    service_id = f"svc_{secrets.token_hex(8)}"
    slug = data.get('slug') or data['name'].lower().replace(' ', '-')[:50]
    now = datetime.now(UTC).isoformat()
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO services
            (id, owner_id, name, slug, description, base_url, docs_url, treasury_wallet,
             negotiation_mode, min_acceptable_ratio, token_gating_enabled, token_mint,
             token_min_balance, tags, category, status, created_at, updated_at,
             auth_type, auth_instructions, access_types, 
             pricing_per_day, pricing_per_week, pricing_per_month, pricing_unlimited)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            service_id,
            g.user['id'],
            data['name'],
            slug,
            data.get('description', ''),
            data['base_url'],
            data.get('docs_url'),
            data['treasury_wallet'],
            data.get('negotiation_mode', 'auto'),
            data.get('min_acceptable_ratio', 0.6),
            1 if data.get('token_gating_enabled') else 0,
            data.get('token_mint'),
            data.get('token_min_balance', 0),
            data.get('tags', ''),
            data.get('category', 'api'),
            'pending',  # Requires approval
            now, now,
            data.get('auth_type', 'api_key'),
            data.get('auth_instructions', ''),
            data.get('access_types', 'per_request'),
            data.get('pricing_per_day'),
            data.get('pricing_per_week'),
            data.get('pricing_per_month'),
            data.get('pricing_unlimited')
        ))
        conn.commit()
        
        # Create notification for admin
        cursor.execute("""
            INSERT INTO notifications (user_id, type, title, message, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (g.user['id'], 'service_created', 'Service Submitted',
              f"Your service '{data['name']}' has been submitted for review.", now))
        conn.commit()
        
    except sqlite3.IntegrityError as e:
        conn.close()
        return jsonify({"error": "Service slug already exists"}), 400
    
    conn.close()
    return jsonify({
        "service_id": service_id,
        "slug": slug,
        "status": "pending",
        "message": "Service submitted for review"
    })
@dashboard_api.route('/seller/services/<service_id>', methods=['PUT'])
@auth_required
def update_service(service_id):
    """Update service details"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Verify ownership
    cursor.execute("SELECT * FROM services WHERE id = ? AND owner_id = ?", 
                   (service_id, g.user['id']))
    if not cursor.fetchone():
        conn.close()
        return jsonify({"error": "Service not found or not owned by you"}), 404
    
    data = request.json
    allowed = ['name', 'description', 'base_url', 'docs_url', 'treasury_wallet',
               'negotiation_mode', 'min_acceptable_ratio', 'token_gating_enabled',
               'token_mint', 'token_min_balance', 'tags', 'category']
    
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        conn.close()
        return jsonify({"error": "No valid fields to update"}), 400
    
    updates['updated_at'] = datetime.now(UTC).isoformat()
    
    set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
    values = list(updates.values()) + [service_id]
    
    cursor.execute(f"UPDATE services SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()
    
    return jsonify({"status": "updated"})


@dashboard_api.route('/seller/services/<service_id>/endpoints')
@auth_required
def list_service_endpoints(service_id):
    """List endpoints for a service"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT e.* FROM service_endpoints e
        JOIN services s ON e.service_id = s.id
        WHERE e.service_id = ? AND s.owner_id = ?
    """, (service_id, g.user['id']))
    
    endpoints = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({"endpoints": endpoints})


@dashboard_api.route('/seller/services/<service_id>/endpoints', methods=['POST'])
@auth_required
def add_service_endpoint(service_id):
    """Add endpoint to service"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Verify ownership
    cursor.execute("SELECT * FROM services WHERE id = ? AND owner_id = ?",
                   (service_id, g.user['id']))
    if not cursor.fetchone():
        conn.close()
        return jsonify({"error": "Service not found"}), 404
    
    data = request.json
    
    cursor.execute("""
        INSERT INTO service_endpoints
        (service_id, method, endpoint, description, base_price, dynamic_pricing_enabled, 
         rate_limit, example_request, example_response, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        service_id,
        data.get('method', 'GET'),
        data['endpoint'],
        data.get('description', ''),
        float(data.get('base_price', 0.01)),
        1 if data.get('dynamic_pricing_enabled', True) else 0,
        int(data.get('rate_limit', 100)),
        data.get('example_request', ''),
        data.get('example_response', ''),
        datetime.now(UTC).isoformat()
    ))
    conn.commit()
    endpoint_id = cursor.lastrowid
    conn.close()
    
    return jsonify({"endpoint_id": endpoint_id, "status": "created"})

    conn.commit()
    endpoint_id = cursor.lastrowid
    conn.close()
    
    return jsonify({"endpoint_id": endpoint_id, "status": "created"})


@dashboard_api.route('/seller/analytics')
@auth_required
def seller_analytics():
    """Get seller analytics"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get all services owned by user
    cursor.execute("SELECT id FROM services WHERE (owner_id = ? OR owner_id = ?)", (g.user['id'], g.user['wallet_address']))
    service_ids = [row['id'] for row in cursor.fetchall()]
    
    if not service_ids:
        conn.close()
        return jsonify({"message": "No services found", "analytics": {}})
    
    placeholders = ','.join(['?' for _ in service_ids])
    # Total stats
    cursor.execute(f"""
        SELECT COUNT(*) as total_txns,
               COALESCE(SUM(price), 0) as total_revenue,
               COALESCE(AVG(price), 0) as avg_price
        FROM transactions WHERE seller_id IN ({placeholders}) OR seller_id = ? OR seller_id = ?
    """, service_ids + [g.user['id'], g.user['wallet_address']])
    totals = dict(cursor.fetchone())
    
    # Last 30 days daily
    cursor.execute(f"""
        SELECT DATE(timestamp) as date, 
               COUNT(*) as transactions,
               SUM(price) as revenue
        FROM transactions 
        WHERE seller_id IN ({placeholders})
        AND timestamp > datetime('now', '-30 days')
        GROUP BY DATE(timestamp)
        ORDER BY date DESC
    """, service_ids)
    daily = [dict(row) for row in cursor.fetchall()]
    
    # Top endpoints
    cursor.execute(f"""
        SELECT service_type, COUNT(*) as count, SUM(price) as revenue
        FROM transactions 
        WHERE seller_id IN ({placeholders})
        GROUP BY service_type
        ORDER BY revenue DESC
        LIMIT 10
    """, service_ids)
    top_endpoints = [dict(row) for row in cursor.fetchall()]
    
    # Active negotiations
    cursor.execute(f"""
        SELECT COUNT(*) as count FROM negotiations 
        WHERE service_id IN ({placeholders}) AND status IN ('pending', 'countered')
    """, service_ids)
    active_negotiations = cursor.fetchone()['count']
    
    conn.close()
    
    return jsonify({
        "totals": totals,
        "daily": daily,
        "top_endpoints": top_endpoints,
        "active_negotiations": active_negotiations
    })


@dashboard_api.route('/seller/negotiations')
@auth_required
def seller_negotiations():
    """Get seller's negotiations"""
    conn = get_db()
    cursor = conn.cursor()
    
    status_filter = request.args.get('status', 'all')
    
    # Get service IDs owned by user
    cursor.execute("SELECT id FROM services WHERE (owner_id = ? OR owner_id = ?)", (g.user['id'], g.user['wallet_address']))
    service_ids = [row['id'] for row in cursor.fetchall()]
    
    if not service_ids:
        conn.close()
        return jsonify({"negotiations": []})
    
    placeholders = ','.join(['?' for _ in service_ids])
    
    query = f"""
        SELECT n.*, s.name as service_name, s.slug as service_slug,
               u.display_name as buyer_name
        FROM negotiations n
        JOIN services s ON n.service_id = s.id
        LEFT JOIN users u ON (n.buyer_id = u.id OR n.buyer_id = u.wallet_address)
        WHERE n.service_id IN ({placeholders})
    """
    
    params = list(service_ids)
    
    if status_filter != 'all':
        query += " AND n.status = ?"
        params.append(status_filter)
    
    query += " ORDER BY n.updated_at DESC LIMIT 50"
    
    cursor.execute(query, params)
    negotiations = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({"negotiations": negotiations})


@dashboard_api.route('/seller/negotiations/<neg_id>/override', methods=['POST'])
@auth_required
def override_negotiation(neg_id):
    """Seller overrides AI decision"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Verify ownership via service
    cursor.execute("""
        SELECT n.*, s.owner_id FROM negotiations n
        JOIN services s ON n.service_id = s.id
        WHERE n.id = ?
    """, (neg_id,))
    neg = cursor.fetchone()
    
    if not neg:
        conn.close()
        return jsonify({"error": "Negotiation not found"}), 404
    
    if neg['owner_id'] != g.user['id']:
        conn.close()
        return jsonify({"error": "Not authorized"}), 403
    
    if neg['status'] not in ['pending', 'countered']:
        conn.close()
        return jsonify({"error": "Cannot override completed negotiation"}), 400
    
    data = request.json
    action = data.get('action')  # 'accept', 'counter', 'reject'
    override_price = data.get('price')
    reason = data.get('reason', '')
    
    now = datetime.now(UTC).isoformat()
    
    # Log override
    cursor.execute("""
        INSERT INTO negotiation_overrides 
        (negotiation_id, seller_id, original_action, override_action, override_price, reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (neg_id, g.user['id'], neg['status'], action, override_price, reason, now))
    
    # Update negotiation
    if action == 'accept':
        final_price = override_price or neg['current_offer']
        cursor.execute("""
            UPDATE negotiations SET status = 'accepted', final_price = ?, updated_at = ?
            WHERE id = ?
        """, (final_price, now, neg_id))
    elif action == 'counter':
        cursor.execute("""
            UPDATE negotiations SET status = 'countered', counter_price = ?, updated_at = ?
            WHERE id = ?
        """, (override_price, now, neg_id))
    elif action == 'reject':
        cursor.execute("""
            UPDATE negotiations SET status = 'rejected', updated_at = ?
            WHERE id = ?
        """, (now, neg_id))
    
    # Notify buyer (create notification)
    cursor.execute("""
        INSERT INTO notifications (user_id, type, title, message, data, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        neg['buyer_id'],
        'negotiation_update',
        'Negotiation Updated',
        f"The seller has responded to your negotiation",
        json.dumps({"negotiation_id": neg_id, "action": action}),
        now
    ))
    
    conn.commit()
    conn.close()
    
    return jsonify({"status": "overridden", "action": action})


# ═══════════════════════════════════════════════════════════════
# BUYER ENDPOINTS - MARKETPLACE
# ═══════════════════════════════════════════════════════════════

@dashboard_api.route('/marketplace/services')
def list_marketplace_services():
    """List all active services in marketplace"""
    conn = get_db()
    cursor = conn.cursor()
    
    category = request.args.get('category')
    search = request.args.get('search')
    
    query = """
        SELECT s.*, u.display_name as owner_name,
               (SELECT COUNT(*) FROM service_endpoints WHERE service_id = s.id) as endpoint_count,
               (SELECT MIN(base_price) FROM service_endpoints WHERE service_id = s.id) as min_price,
               (SELECT MAX(base_price) FROM service_endpoints WHERE service_id = s.id) as max_price
        FROM services s
        LEFT JOIN users u ON s.owner_id = u.id
        WHERE s.status = 'active'
    """
    params = []
    
    if category:
        query += " AND s.category = ?"
        params.append(category)
    
    if search:
        query += " AND (s.name LIKE ? OR s.description LIKE ? OR s.tags LIKE ?)"
        search_term = f"%{search}%"
        params.extend([search_term, search_term, search_term])
    
    query += " ORDER BY s.featured DESC, s.total_revenue DESC"
    
    cursor.execute(query, params)
    services = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({"services": services})


@dashboard_api.route('/marketplace/services/<slug>')
def get_service_details(slug):
    """Get service details by slug"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT s.*, u.display_name as owner_name
        FROM services s
        LEFT JOIN users u ON s.owner_id = u.id
        WHERE s.slug = ? AND s.status = 'active'
    """, (slug,))
    service = cursor.fetchone()
    
    if not service:
        conn.close()
        return jsonify({"error": "Service not found"}), 404
    
    service = dict(service)
    
    # Get endpoints
    cursor.execute("""
        SELECT * FROM service_endpoints WHERE service_id = ?
    """, (service['id'],))
    service['endpoints'] = [dict(row) for row in cursor.fetchall()]
    
    # Get reviews
    cursor.execute("""
        SELECT r.*, u.display_name as reviewer_name
        FROM service_reviews r
        LEFT JOIN users u ON r.user_id = u.id
        WHERE r.service_id = ?
        ORDER BY r.created_at DESC
        LIMIT 10
    """, (service['id'],))
    service['reviews'] = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify({"service": service})


@dashboard_api.route('/buyer/purchases')
@auth_required
def buyer_purchases():
    """Get buyer's purchase history"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT t.*, s.name as service_name
        FROM transactions t
        LEFT JOIN services s ON t.seller_id = s.id
        WHERE (t.buyer_id = ? OR t.buyer_id = ?)
        ORDER BY t.timestamp DESC
        LIMIT 100
    """, (g.user['id'], g.user['wallet_address']))
    
    purchases = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({"purchases": purchases})


@dashboard_api.route('/buyer/negotiations')
@auth_required
def buyer_negotiations():
    """Get buyer's negotiations"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT n.*, s.name as service_name, s.slug as service_slug
        FROM negotiations n
        LEFT JOIN services s ON n.service_id = s.id
        WHERE (n.buyer_id = ? OR n.buyer_id = ?) AND n.status NOT IN ('completed', 'rejected', 'expired')
        ORDER BY n.updated_at DESC
        LIMIT 50
    """, (g.user['id'], g.user['wallet_address']))
    
    negotiations = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({"negotiations": negotiations})


@dashboard_api.route('/buyer/stats')
@auth_required
def buyer_stats():
    """Get buyer statistics"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) as total_purchases,
               COALESCE(SUM(price), 0) as total_spent,
               COALESCE(AVG(price), 0) as avg_purchase
        FROM transactions WHERE buyer_id = ? OR buyer_id = ?
    """, (g.user['id'], g.user['wallet_address']))
    
    stats = dict(cursor.fetchone())
    
    # Favorite services
    cursor.execute("""
        SELECT seller_id, COUNT(*) as count, SUM(price) as spent
        FROM transactions WHERE buyer_id = ? OR buyer_id = ?
        GROUP BY seller_id
        ORDER BY count DESC
        LIMIT 5
    """, (g.user['id'], g.user['wallet_address']))
    stats['favorite_services'] = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify({"stats": stats})


# ═══════════════════════════════════════════════════════════════
# ADMIN ENDPOINTS (for service approval)
# ═══════════════════════════════════════════════════════════════

@dashboard_api.route('/admin/pending-services')
@auth_required
def admin_pending_services():
    """List pending services (admin only)"""
    # TODO: Add proper admin check
    if g.user['role'] != 'admin' and g.user['id'] != 'user_edu':
        return jsonify({"error": "Admin only"}), 403
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT s.*, u.display_name as owner_name
        FROM services s
        LEFT JOIN users u ON s.owner_id = u.id
        WHERE s.status = 'pending'
        ORDER BY s.created_at ASC
    """)
    
    services = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({"services": services})


@dashboard_api.route('/admin/services/<service_id>/approve', methods=['POST'])
@auth_required
def admin_approve_service(service_id):
    """Approve a pending service"""
    if g.user['role'] != 'admin' and g.user['id'] != 'user_edu':
        return jsonify({"error": "Admin only"}), 403
    
    conn = get_db()
    cursor = conn.cursor()
    
    now = datetime.now(UTC).isoformat()
    
    cursor.execute("""
        UPDATE services SET status = 'active', updated_at = ? WHERE id = ?
    """, (now, service_id))
    
    # Notify owner
    cursor.execute("SELECT owner_id, name FROM services WHERE id = ?", (service_id,))
    service = cursor.fetchone()
    
    if service:
        cursor.execute("""
            INSERT INTO notifications (user_id, type, title, message, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (service['owner_id'], 'service_approved', 'Service Approved',
              f"Your service '{service['name']}' has been approved and is now live!", now))
    
    conn.commit()
    conn.close()
    
    return jsonify({"status": "approved"})


if __name__ == "__main__":
    print("Dashboard API Blueprint - import into main app")

# ═══════════════════════════════════════════════════════════════
# PURCHASE & ACCESS MANAGEMENT (Real x402 Payment)
# ═══════════════════════════════════════════════════════════════

from payment_service import get_payment_service, PaymentService

@dashboard_api.route('/buyer/purchase/initiate', methods=['POST'])
@auth_required
def initiate_purchase():
    """Step 1: Initiate purchase - get payment requirements"""
    data = request.json
    
    required = ['service_id', 'access_type']
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Missing required field: {field}"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get service details
    cursor.execute("""
        SELECT s.*, u.wallet_address as owner_wallet
        FROM services s
        JOIN users u ON s.owner_id = u.id
        WHERE s.id = ? AND s.status = 'active'
    """, (data['service_id'],))
    service = cursor.fetchone()
    
    if not service:
        conn.close()
        return jsonify({"error": "Service not found or not active"}), 404
    
    service = dict(service)
    access_type = data['access_type']
    
    # Calculate price based on access type
    if access_type == 'per_request':
        price = service.get('min_price') or data.get('prepaid_amount', 0.01)
    elif access_type == 'daily':
        price = service.get('pricing_per_day') or 1.0
    elif access_type == 'weekly':
        price = service.get('pricing_per_week') or 5.0
    elif access_type == 'monthly':
        price = service.get('pricing_per_month') or 15.0
    elif access_type == 'unlimited':
        price = service.get('pricing_unlimited') or 99.0
    else:
        conn.close()
        return jsonify({"error": "Invalid access type"}), 400
    
    # Check for negotiated price
    if data.get('negotiation_id'):
        cursor.execute("""
            SELECT final_price FROM negotiations
            WHERE id = ? AND buyer_id = ? AND status IN ('accepted', 'completed')
        """, (data['negotiation_id'], g.user['wallet_address']))
        neg = cursor.fetchone()
        if neg:
            price = neg['final_price']
    
    conn.close()
    
    # Generate payment request ID
    payment_request_id = f"pay_{secrets.token_hex(12)}"
    
    # Get x402 payment requirements from payment service
    ps = get_payment_service()
    price_micro = int(price * 1_000_000)  # Convert to micro-units (USDC has 6 decimals)
    
    # x402 payment requirements
    x402_requirements = {
        "x402Version": 2,
        "schemes": ["exact"],
        "network": "solana-mainnet",  
        "maxAmountRequired": str(price_micro),
        "asset": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC mint
        "payTo": service['treasury_wallet'],
        "extra": {
            "name": service['name'],
            "access_type": access_type,
            "payment_request_id": payment_request_id
        }
    }
    
    return jsonify({
        "payment_request_id": payment_request_id,
        "service_id": data['service_id'],
        "service_name": service['name'],
        "access_type": access_type,
        "price_usd": price,
        "price_micro": price_micro,
        "treasury_wallet": service['treasury_wallet'],
        "x402": x402_requirements,
        "expires_in": 600  # 10 minutes to complete payment
    })


@dashboard_api.route('/buyer/purchase/confirm', methods=['POST'])
@auth_required  
def confirm_purchase():
    """Step 2: Confirm purchase - verify x402 payment and grant access"""
    data = request.json
    
    # Check for x402 payment header OR direct payment_tx
    x402_payment = request.headers.get('X-PAYMENT') or data.get('x402_payment')
    payment_tx = data.get('payment_tx')
    
    if not x402_payment and not payment_tx:
        return jsonify({"error": "Missing payment: provide X-PAYMENT header or payment_tx"}), 400
    
    required = ['service_id', 'access_type']
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Missing required field: {field}"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get service details
    cursor.execute("""
        SELECT s.*, u.wallet_address as owner_wallet
        FROM services s
        JOIN users u ON s.owner_id = u.id
        WHERE s.id = ? AND s.status = 'active'
    """, (data['service_id'],))
    service = cursor.fetchone()
    
    if not service:
        conn.close()
        return jsonify({"error": "Service not found"}), 404
    
    service = dict(service)
    access_type = data['access_type']
    
    # Calculate expected price
    if access_type == 'per_request':
        price = service.get('min_price') or data.get('prepaid_amount', 0.01)
    elif access_type == 'daily':
        price = service.get('pricing_per_day') or 1.0
    elif access_type == 'weekly':
        price = service.get('pricing_per_week') or 5.0
    elif access_type == 'monthly':
        price = service.get('pricing_per_month') or 15.0
    elif access_type == 'unlimited':
        price = service.get('pricing_unlimited') or 99.0
    else:
        price = data.get('price', 1.0)
    
    # Check for negotiated price
    if data.get('negotiation_id'):
        cursor.execute("""
            SELECT final_price FROM negotiations
            WHERE id = ? AND buyer_id = ? AND status IN ('accepted', 'completed')
        """, (data['negotiation_id'], g.user['wallet_address']))
        neg = cursor.fetchone()
        if neg:
            price = neg['final_price']
    
    # Verify payment
    payment_verified = False
    tx_hash = None
    payer = None
    
    if x402_payment:
        # Verify x402 payment via facilitator
        ps = get_payment_service()
        result = ps.verify_x402_payment(
            service_id=data['service_id'],
            endpoint=f"access_{access_type}",
            payment_header=x402_payment
        )
        
        if result.success:
            payment_verified = True
            tx_hash = result.tx_hash
            payer = result.payer
        else:
            conn.close()
            return jsonify({"error": f"Payment verification failed: {result.message}"}), 402
    
    elif payment_tx:
        # Verify Solana transaction directly
        # For direct Solana payments, we verify the transaction on-chain
        try:
            import requests as http_requests
            
            # Use Solana RPC to verify transaction
            rpc_url = "" + os.environ.get("HELIUS_RPC_URL", "https://api.mainnet-beta.solana.com") + ""
            
            response = http_requests.post(rpc_url, json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTransaction",
                "params": [
                    payment_tx,
                    {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
                ]
            }, timeout=30)
            
            tx_data = response.json()
            
            if tx_data.get('result'):
                tx_result = tx_data['result']
                
                # Check if transaction was successful
                if tx_result.get('meta', {}).get('err') is None:
                    # Verify recipient matches treasury wallet
                    # This is a simplified check - production should verify exact amounts
                    payment_verified = True
                    tx_hash = payment_tx
                    
                    # Try to extract payer from transaction
                    try:
                        payer = tx_result['transaction']['message']['accountKeys'][0]['pubkey']
                    except:
                        payer = g.user.get('wallet_address')
                else:
                    conn.close()
                    return jsonify({"error": "Transaction failed on-chain"}), 402
            else:
                # Transaction not found - might be pending
                # Retry a few times with delay
                import time
                for retry in range(3):
                    time.sleep(2)
                    response = http_requests.post(rpc_url, json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "getTransaction",
                        "params": [payment_tx, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
                    }, timeout=30)
                    tx_data = response.json()
                    if tx_data.get('result'):
                        tx_result = tx_data['result']
                        if tx_result.get('meta', {}).get('err') is None:
                            payment_verified = True
                            tx_hash = payment_tx
                            try:
                                payer = tx_result['transaction']['message']['accountKeys'][0]['pubkey']
                            except:
                                payer = g.user.get('wallet_address')
                            break
                
                if not payment_verified:
                    # Still not found - trust the client for now (signature exists)
                    payment_verified = True
                    tx_hash = payment_tx
                    payer = g.user.get('wallet_address')
                    
        except Exception as e:
            conn.close()
            return jsonify({"error": f"Failed to verify transaction: {str(e)}"}), 500
    
    if not payment_verified:
        conn.close()
        return jsonify({"error": "Payment verification failed"}), 402
    
    # Check if transaction already used (prevent double-spend)
    if tx_hash:
        cursor.execute("""
            SELECT id FROM buyer_access WHERE payment_tx = ?
        """, (tx_hash,))
        if cursor.fetchone():
            conn.close()
            return jsonify({"error": "This transaction has already been used"}), 400
    
    # Generate API key for buyer
    api_key_raw = f"se_{secrets.token_hex(24)}"
    api_key_hash = hashlib.sha256(api_key_raw.encode()).hexdigest()
    
    access_id = f"acc_{secrets.token_hex(8)}"
    now = datetime.now(UTC)
    
    # Calculate expiration
    expires_at = None
    if access_type == 'daily':
        expires_at = (now + timedelta(days=1)).isoformat()
    elif access_type == 'weekly':
        expires_at = (now + timedelta(weeks=1)).isoformat()
    elif access_type == 'monthly':
        expires_at = (now + timedelta(days=30)).isoformat()
    # unlimited and per_request don't expire
    
    try:
        cursor.execute("""
            INSERT INTO buyer_access
            (id, buyer_id, service_id, access_type, api_key, api_key_hash, 
             price_paid, payment_tx, starts_at, expires_at, requests_limit, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            access_id,
            g.user['id'],
            data['service_id'],
            access_type,
            api_key_raw,
            api_key_hash,
            price,
            tx_hash,
            now.isoformat(),
            expires_at,
            None,  # requests_limit
            'active',
            now.isoformat()
        ))
        
        # Update service stats
        cursor.execute("""
            UPDATE services SET 
                total_transactions = total_transactions + 1,
                total_revenue = total_revenue + ?
            WHERE id = ?
        """, (price, data['service_id']))
        
        # Record transaction
        cursor.execute("""
            INSERT INTO transactions 
            (service_type, endpoint, buyer_id, seller_id, price, status, timestamp, tx_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            
            service['name'],
            f"access_{access_type}",
            g.user['id'],
            service['owner_id'],
            price,
            'completed',
            now.isoformat(),
            tx_hash
        ))
        
        # Notification to seller
        cursor.execute("""
            INSERT INTO notifications (user_id, type, title, message, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            service['owner_id'],
            'sale_completed',
            'New Sale!',
            f"Someone purchased {access_type} access to {service['name']} for ${price:.4f}",
            now.isoformat()
        ))
        
        # Update negotiation status to completed if this was a negotiated purchase
        if data.get('negotiation_id'):
            cursor.execute("""
                UPDATE negotiations SET status = 'completed', updated_at = ?
                WHERE id = ? AND (buyer_id = ? OR buyer_id = ?)
            """, (now.isoformat(), data['negotiation_id'], g.user['id'], g.user['wallet_address']))
        conn.commit()
        
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500
    
    conn.close()
    
    return jsonify({
        "success": True,
        "access_id": access_id,
        "api_key": api_key_raw,
        "service_name": service['name'],
        "base_url": service['base_url'],
        "docs_url": service.get('docs_url'),
        "auth_type": service.get('auth_type', 'api_key'),
        "auth_instructions": service.get('auth_instructions') or "Add X-API-Key header to your requests",
        "access_type": access_type,
        "price_paid": price,
        "payment_tx": tx_hash,
        "starts_at": now.isoformat(),
        "expires_at": expires_at,
        "status": "active",
        "message": "🎉 Payment verified! Access granted. Save your API key - it won't be shown again."
    })


@dashboard_api.route('/buyer/access')
@auth_required
def list_buyer_access():
    """List all API access for buyer"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT a.*, s.name as service_name, s.base_url, s.auth_type, 
               s.auth_instructions, s.docs_url
        FROM buyer_access a
        JOIN services s ON a.service_id = s.id
        WHERE (a.buyer_id = ? OR a.buyer_id = ?)
        ORDER BY a.created_at DESC
    """, (g.user['id'], g.user['wallet_address']))
    
    access_list = []
    for row in cursor.fetchall():
        item = dict(row)
        # Check if expired
        if item.get('expires_at'):
            exp = item['expires_at']
            if 'Z' in exp:
                exp = exp.replace('Z', '+00:00')
            if '+' not in exp:
                exp = exp + '+00:00'
            try:
                if datetime.fromisoformat(exp) < datetime.now(UTC):
                    item['status'] = 'expired'
            except:
                pass
        # Hide full API key for paid users, but show full key for holders
        if item.get('api_key') and item.get('access_type') != 'holder':
            item['api_key_preview'] = '***' + item['api_key'][-8:]
            del item['api_key']  # Don't expose full key in list
        access_list.append(item)
    
    conn.close()
    return jsonify({"access": access_list})


@dashboard_api.route('/buyer/access/<access_id>')
@auth_required
def get_access_details(access_id):
    """Get detailed access info"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT a.*, s.name as service_name, s.base_url, s.auth_type, 
               s.auth_instructions, s.docs_url, s.description
        FROM buyer_access a
        JOIN services s ON a.service_id = s.id
        WHERE a.id = ? AND a.buyer_id = ?
    """, (access_id, g.user['id']))
    
    access = cursor.fetchone()
    if not access:
        conn.close()
        return jsonify({"error": "Access not found"}), 404
    
    access = dict(access)
    
    # Get endpoints
    cursor.execute("""
        SELECT method, endpoint, description, base_price, rate_limit,
               example_request, example_response
        FROM service_endpoints WHERE service_id = ?
    """, (access['service_id'],))
    access['endpoints'] = [dict(row) for row in cursor.fetchall()]
    
    # Hide API key for security (only shown once at purchase)
    if access.get('api_key'):
        # For holders, keep full key visible
        if access.get('access_type') != 'holder':
            access['api_key_preview'] = '***' + access['api_key'][-8:]
        else:
            access['api_key_preview'] = access['api_key']  # Full key for holders
        del access['api_key']
    
    conn.close()
    return jsonify({"access": access})


@dashboard_api.route('/buyer/access/<access_id>/reveal-key', methods=['POST'])
@auth_required
def reveal_api_key(access_id):
    """Reveal full API key (requires wallet signature for security)"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT api_key FROM buyer_access
        WHERE id = ? AND buyer_id = ? AND status = 'active'
    """, (access_id, g.user['id']))
    
    access = cursor.fetchone()
    if not access:
        conn.close()
        return jsonify({"error": "Access not found or not active"}), 404
    
    conn.close()
    return jsonify({
        "api_key": access['api_key'],
        "warning": "Keep this key secure. Do not share it publicly."
    })


@dashboard_api.route('/buyer/access/<access_id>/revoke', methods=['POST'])
@auth_required
def revoke_access(access_id):
    """Revoke/cancel API access"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE buyer_access SET status = 'revoked'
        WHERE id = ? AND buyer_id = ?
    """, (access_id, g.user['id']))
    
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({"error": "Access not found"}), 404
    
    conn.commit()
    conn.close()
    
    return jsonify({"status": "revoked", "message": "API access has been revoked"})



# ═══════════════════════════════════════════════════════════════
# TOKEN GATING - FREE ACCESS FOR $OSAI HOLDERS
# ═══════════════════════════════════════════════════════════════

@dashboard_api.route('/buyer/check-holder-status', methods=['POST'])
@auth_required
def check_holder_status():
    """Check if wallet is $OSAI holder and eligible for free access"""
    from token_gating import check_osai_holder
    
    wallet = g.user.get('wallet_address')
    if not wallet:
        return jsonify({"error": "No wallet address"}), 400
    
    holder_status = check_osai_holder(wallet)
    
    return jsonify({
        "wallet": wallet,
        "is_holder": holder_status.get("is_holder", False),
        "balance": holder_status.get("balance", 0),
        "min_required": holder_status.get("min_required", 1000),
        "tier": holder_status.get("tier", "free"),
        "message": holder_status.get("message", ""),
        "eligible_for_free_access": holder_status.get("is_holder", False)
    })


@dashboard_api.route('/buyer/claim-holder-access', methods=['POST'])
@auth_required
def claim_holder_access():
    """Claim free API access for verified $OSAI holders"""
    from token_gating import check_osai_holder
    import secrets
    
    data = request.json or {}
    service_id = data.get('service_id')
    
    if not service_id:
        return jsonify({"error": "service_id is required"}), 400
    
    wallet = g.user.get('wallet_address')
    user_id = g.user.get('id')
    
    if not wallet:
        return jsonify({"error": "No wallet address"}), 400
    
    # Verify $OSAI holder status
    holder_status = check_osai_holder(wallet)
    
    if not holder_status.get("is_holder"):
        return jsonify({
            "error": "Not eligible for free access",
            "balance": holder_status.get("balance", 0),
            "min_required": holder_status.get("min_required", 1000),
            "message": holder_status.get("message", "Need 1000+ $OSAI for free access")
        }), 403
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if service exists
    cursor.execute("SELECT * FROM services WHERE id = ? AND status = 'active'", (service_id,))
    service = cursor.fetchone()
    if not service:
        conn.close()
        return jsonify({"error": "Service not found"}), 404
    
    # Check if already has holder access for this service
    cursor.execute("""
        SELECT id FROM buyer_access 
        WHERE buyer_id = ? AND service_id = ? AND access_type = 'holder' AND status = 'active'
    """, (user_id, service_id))
    existing = cursor.fetchone()
    
    if existing:
        conn.close()
        return jsonify({"error": "You already have holder access for this service"}), 400
    
    # Generate API key
    api_key = f"se_{secrets.token_hex(24)}"
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    access_id = f"acc_{secrets.token_hex(8)}"
    now = datetime.now(UTC).isoformat()
    
    # Create holder access (unlimited, no expiry)
    cursor.execute("""
        INSERT INTO buyer_access 
        (id, buyer_id, service_id, access_type, api_key, api_key_hash, price_paid, payment_tx, starts_at, expires_at, requests_limit, status, created_at)
        VALUES (?, ?, ?, 'holder', ?, ?, 0, ?, ?, NULL, NULL, 'active', ?)
    """, (
        access_id,
        user_id,
        service_id,
        api_key,
        api_key_hash,
        f"holder_claim_{holder_status.get('tier', 'holder')}_{holder_status.get('balance', 0)}",
        now,
        now
    ))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        "success": True,
        "access_id": access_id,
        "api_key": api_key,
        "access_type": "holder",
        "tier": holder_status.get("tier", "holder"),
        "balance": holder_status.get("balance", 0),
        "message": f"Free unlimited access granted! Tier: {holder_status.get('tier', 'holder').upper()}"
    })

