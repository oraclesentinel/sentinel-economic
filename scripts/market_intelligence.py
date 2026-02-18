#!/usr/bin/env python3
"""
Sentinel Economic — Market Intelligence Module
"""

import json
import sqlite3
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("market_intelligence")

DB_PATH = os.path.expanduser("~/sentinel-economic/data/sentinel_economic.db")


@dataclass
class MarketRate:
    service_type: str
    median_price: float
    min_price: float
    max_price: float
    avg_price: float
    sample_size: int
    demand_factor: float
    trend: str
    last_updated: str


class MarketIntelligence:
    def __init__(self, agent_id: Optional[str] = None):
        self.agent_id = agent_id
        self.db_path = DB_PATH
        self._ensure_db()
        
    def _ensure_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_hash TEXT UNIQUE,
                service_type TEXT NOT NULL,
                seller_id TEXT NOT NULL,
                buyer_id TEXT NOT NULL,
                price REAL NOT NULL,
                currency TEXT DEFAULT 'USDC',
                status TEXT DEFAULT 'completed',
                timestamp TEXT NOT NULL,
                source TEXT DEFAULT 'internal',
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT UNIQUE NOT NULL,
                service_types TEXT,
                total_transactions INTEGER DEFAULT 0,
                total_volume REAL DEFAULT 0,
                success_rate REAL DEFAULT 1.0,
                avg_rating REAL DEFAULT 5.0,
                trust_score REAL,
                last_active TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_type TEXT NOT NULL,
                price REAL NOT NULL,
                timestamp TEXT NOT NULL,
                source TEXT
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {self.db_path}")
    
    def _get_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def record_transaction(self, service_type: str, seller_id: str, buyer_id: str, 
                          price: float, currency: str = "USDC", tx_hash: str = None,
                          source: str = "internal", metadata: Dict = None) -> int:
        conn = self._get_db()
        cursor = conn.cursor()
        tx_hash = tx_hash or f"internal_{datetime.utcnow().timestamp()}"
        timestamp = datetime.utcnow().isoformat()
        
        try:
            cursor.execute("""
                INSERT INTO transactions 
                (tx_hash, service_type, seller_id, buyer_id, price, currency, timestamp, source, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (tx_hash, service_type, seller_id, buyer_id, price, currency, 
                  timestamp, source, json.dumps(metadata) if metadata else None))
            
            cursor.execute("""
                INSERT INTO price_history (service_type, price, timestamp, source)
                VALUES (?, ?, ?, ?)
            """, (service_type, price, timestamp, source))
            
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return -1
        finally:
            conn.close()
    
    def get_market_rate(self, service_type: str, lookback_hours: int = 168) -> MarketRate:
        conn = self._get_db()
        cursor = conn.cursor()
        cutoff = (datetime.utcnow() - timedelta(hours=lookback_hours)).isoformat()
        
        cursor.execute("""
            SELECT COUNT(*) as count, AVG(price) as avg_price,
                   MIN(price) as min_price, MAX(price) as max_price
            FROM transactions WHERE service_type = ? AND timestamp > ?
        """, (service_type, cutoff))
        
        stats = cursor.fetchone()
        
        if not stats or stats["count"] == 0:
            conn.close()
            return MarketRate(service_type, 0.01, 0.01, 0.01, 0.01, 0, 1.0, "unknown", 
                            datetime.utcnow().isoformat())
        
        cursor.execute("""
            SELECT price FROM transactions
            WHERE service_type = ? AND timestamp > ? ORDER BY price
        """, (service_type, cutoff))
        prices = [r["price"] for r in cursor.fetchall()]
        median = prices[len(prices)//2] if prices else 0.01
        
        cursor.execute("""
            SELECT COUNT(*) as c FROM transactions
            WHERE service_type = ? AND timestamp > ?
        """, (service_type, (datetime.utcnow() - timedelta(hours=24)).isoformat()))
        recent = cursor.fetchone()["c"] or 0
        demand = min(2.0, max(0.5, recent / 5.0))
        
        trend = self._calc_trend(cursor, service_type)
        conn.close()
        
        return MarketRate(service_type, median, stats["min_price"] or 0.01,
                         stats["max_price"] or 0.01, stats["avg_price"] or 0.01,
                         stats["count"], demand, trend, datetime.utcnow().isoformat())
    
    def _calc_trend(self, cursor, service_type: str) -> str:
        now = datetime.utcnow()
        w1 = (now - timedelta(days=7)).isoformat()
        w2 = (now - timedelta(days=14)).isoformat()
        
        cursor.execute("SELECT AVG(price) as a FROM transactions WHERE service_type=? AND timestamp>?", 
                      (service_type, w1))
        r1 = cursor.fetchone()
        cursor.execute("SELECT AVG(price) as a FROM transactions WHERE service_type=? AND timestamp>? AND timestamp<=?",
                      (service_type, w2, w1))
        r2 = cursor.fetchone()
        
        if not r1["a"] or not r2["a"]: return "unknown"
        chg = (r1["a"] - r2["a"]) / r2["a"] * 100
        if chg > 5: return "rising"
        if chg < -5: return "falling"
        return "stable"
    
    def get_all_services(self) -> List[Dict]:
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT service_type FROM transactions")
        services = [r["service_type"] for r in cursor.fetchall()]
        conn.close()
        return [{"service": s, **self.get_market_rate(s).__dict__} for s in services]


if __name__ == "__main__":
    mi = MarketIntelligence("sentinel_predict")
    mi.record_transaction("prediction_signal", "sentinel_predict", "trader_1", 0.05)
    mi.record_transaction("prediction_signal", "sentinel_predict", "trader_2", 0.045)
    mi.record_transaction("data_feed", "sentinel_data", "sentinel_predict", 0.001)
    
    rate = mi.get_market_rate("prediction_signal")
    print(f"\nMarket Rate: ${rate.avg_price:.4f} | Trend: {rate.trend} | Demand: {rate.demand_factor:.1f}x")
