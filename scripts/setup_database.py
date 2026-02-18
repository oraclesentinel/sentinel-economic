#!/usr/bin/env python3
"""
Sentinel Economic — Database Setup
Multi-tenant schema for sellers and buyers
"""

import sqlite3
import os
from datetime import datetime, UTC

DB_PATH = os.path.expanduser("~/sentinel-economic/data/sentinel_economic.db")


def setup_database():
    """Create all tables for Sentinel Economic"""
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # ═══════════════════════════════════════════════════════════════
    # USERS TABLE
    # ═══════════════════════════════════════════════════════════════
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            wallet_address TEXT UNIQUE NOT NULL,
            display_name TEXT,
            email TEXT,
            role TEXT DEFAULT 'buyer',
            api_key TEXT UNIQUE,
            avatar_url TEXT,
            bio TEXT,
            website TEXT,
            twitter TEXT,
            notification_email INTEGER DEFAULT 1,
            notification_webhook TEXT,
            created_at TEXT NOT NULL,
            last_active TEXT,
            status TEXT DEFAULT 'active'
        )
    """)
    
    # ═══════════════════════════════════════════════════════════════
    # SERVICES TABLE (Sellers register services here)
    # ═══════════════════════════════════════════════════════════════
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT,
            logo_url TEXT,
            base_url TEXT NOT NULL,
            docs_url TEXT,
            treasury_wallet TEXT NOT NULL,
            negotiation_mode TEXT DEFAULT 'auto',
            min_acceptable_ratio REAL DEFAULT 0.6,
            max_negotiation_rounds INTEGER DEFAULT 3,
            token_gating_enabled INTEGER DEFAULT 0,
            token_mint TEXT,
            token_min_balance INTEGER DEFAULT 0,
            tags TEXT,
            category TEXT DEFAULT 'api',
            status TEXT DEFAULT 'pending',
            featured INTEGER DEFAULT 0,
            total_transactions INTEGER DEFAULT 0,
            total_revenue REAL DEFAULT 0,
            avg_rating REAL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY (owner_id) REFERENCES users(id)
        )
    """)
    
    # ═══════════════════════════════════════════════════════════════
    # SERVICE ENDPOINTS (Pricing per endpoint)
    # ═══════════════════════════════════════════════════════════════
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS service_endpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id TEXT NOT NULL,
            method TEXT DEFAULT 'GET',
            endpoint TEXT NOT NULL,
            description TEXT,
            base_price REAL NOT NULL,
            dynamic_pricing_enabled INTEGER DEFAULT 1,
            rate_limit INTEGER DEFAULT 100,
            example_request TEXT,
            example_response TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (service_id) REFERENCES services(id),
            UNIQUE(service_id, method, endpoint)
        )
    """)
    
    # ═══════════════════════════════════════════════════════════════
    # API KEYS (For programmatic access)
    # ═══════════════════════════════════════════════════════════════
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            key_hash TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            permissions TEXT DEFAULT 'read',
            last_used TEXT,
            expires_at TEXT,
            created_at TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    # ═══════════════════════════════════════════════════════════════
    # NOTIFICATIONS
    # ═══════════════════════════════════════════════════════════════
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT,
            data TEXT,
            read INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    # ═══════════════════════════════════════════════════════════════
    # SERVICE REVIEWS
    # ═══════════════════════════════════════════════════════════════
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS service_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            rating INTEGER NOT NULL,
            review TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (service_id) REFERENCES services(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(service_id, user_id)
        )
    """)
    
    # ═══════════════════════════════════════════════════════════════
    # SELLER OVERRIDES (Manual intervention on AI decisions)
    # ═══════════════════════════════════════════════════════════════
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS negotiation_overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            negotiation_id TEXT NOT NULL,
            seller_id TEXT NOT NULL,
            original_action TEXT NOT NULL,
            override_action TEXT NOT NULL,
            override_price REAL,
            reason TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (negotiation_id) REFERENCES negotiations(id),
            FOREIGN KEY (seller_id) REFERENCES users(id)
        )
    """)
    
    # ═══════════════════════════════════════════════════════════════
    # INDEXES FOR PERFORMANCE
    # ═══════════════════════════════════════════════════════════════
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_services_owner ON services(owner_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_services_status ON services(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_services_category ON services(category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_endpoints_service ON service_endpoints(service_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, read)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_seller ON transactions(seller_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_buyer ON transactions(buyer_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_negotiations_buyer ON negotiations(buyer_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_negotiations_service ON negotiations(service_id)")
    
    conn.commit()
    conn.close()
    
    print("✅ Database schema created successfully")


def seed_demo_data():
    """Add demo data for testing"""
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now(UTC).isoformat()
    
    # Demo users
    demo_users = [
        ("user_edu", "LXzWaDDkSkDQSAvRfArcYwRSq2pjgrVFidGbbnWbiD9", "Edu (Oracle Sentinel)", "seller", now),
        ("user_alice", "A1iceBuyerWa11etAddress1234567890abcdefgh", "Alice (Trader Bot)", "buyer", now),
        ("user_bob", "B0bBuyerWa11etAddress1234567890abcdefghij", "Bob (Research Agent)", "buyer", now),
    ]
    
    for user in demo_users:
        try:
            cursor.execute("""
                INSERT INTO users (id, wallet_address, display_name, role, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, user)
        except sqlite3.IntegrityError:
            pass
    
    # Demo service
    try:
        cursor.execute("""
            INSERT INTO services 
            (id, owner_id, name, slug, description, base_url, treasury_wallet, 
             negotiation_mode, tags, category, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "svc_oracle_sentinel",
            "user_edu",
            "Oracle Sentinel Predict",
            "oracle-sentinel",
            "AI-powered prediction market intelligence with 57% accuracy. Get real-time signals, probability estimates, and trading recommendations.",
            "https://api.oraclesentinel.xyz",
            "LXzWaDDkSkDQSAvRfArcYwRSq2pjgrVFidGbbnWbiD9",
            "auto",
            "prediction,oracle,trading,ai",
            "api",
            "active",
            now
        ))
    except sqlite3.IntegrityError:
        pass
    
    # Demo endpoints
    demo_endpoints = [
        ("svc_oracle_sentinel", "GET", "/api/v1/signal/<slug>", "Get trading signal for a market", 0.01),
        ("svc_oracle_sentinel", "GET", "/api/v1/analysis/<slug>", "Full AI analysis for a market", 0.03),
        ("svc_oracle_sentinel", "GET", "/api/v1/whale/<slug>", "Whale trade data", 0.02),
        ("svc_oracle_sentinel", "GET", "/api/v1/bulk", "Bulk signals", 0.08),
        ("svc_oracle_sentinel", "POST", "/api/v1/analyze", "Custom market analysis", 0.05),
    ]
    
    for ep in demo_endpoints:
        try:
            cursor.execute("""
                INSERT INTO service_endpoints 
                (service_id, method, endpoint, description, base_price, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (*ep, now))
        except sqlite3.IntegrityError:
            pass
    
    conn.commit()
    conn.close()
    
    print("✅ Demo data seeded successfully")


if __name__ == "__main__":
    setup_database()
    seed_demo_data()
