#!/usr/bin/env python3
"""
Sentinel Economic — Negotiation Engine
Handles multi-round bargaining between agents
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, UTC
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("negotiation_engine")

DB_PATH = os.path.expanduser("~/sentinel-economic/data/sentinel_economic.db")


class NegotiationStatus(Enum):
    PENDING = "pending"
    COUNTERED = "countered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class NegotiationOffer:
    negotiation_id: str
    service_id: str
    endpoint: str
    buyer_id: str
    offered_price: float
    quantity: int
    round_number: int
    status: str
    counter_price: Optional[float]
    message: str
    expires_at: str
    created_at: str


@dataclass
class NegotiationResponse:
    negotiation_id: str
    status: str
    your_offer: float
    our_price: float
    counter_price: Optional[float]
    message: str
    round_number: int
    max_rounds: int
    expires_at: str
    payment_url: Optional[str]


class NegotiationEngine:
    MAX_ROUNDS = 3
    
    def __init__(self):
        self._ensure_db()
    
    def _ensure_db(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS negotiations (
                id TEXT PRIMARY KEY,
                service_id TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                buyer_id TEXT NOT NULL,
                quantity INTEGER DEFAULT 1,
                initial_offer REAL NOT NULL,
                current_offer REAL NOT NULL,
                our_price REAL NOT NULL,
                counter_price REAL,
                status TEXT DEFAULT 'pending',
                round_number INTEGER DEFAULT 1,
                final_price REAL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS negotiation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                negotiation_id TEXT NOT NULL,
                round_number INTEGER NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                price REAL,
                message TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (negotiation_id) REFERENCES negotiations(id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def _get_db(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _get_buyer_trust(self, buyer_id: str) -> float:
        """Get buyer trust score from transaction history"""
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) as total_txns,
                   SUM(price) as total_spent
            FROM transactions
            WHERE buyer_id = ?
        """, (buyer_id,))
        
        stats = cursor.fetchone()
        conn.close()
        
        if not stats or not stats["total_txns"]:
            return 0.5  # New buyer
        
        # Trust based on history
        txn_score = min(stats["total_txns"] / 100, 1) * 0.5
        spend_score = min((stats["total_spent"] or 0) / 50, 1) * 0.5
        
        return txn_score + spend_score
    
    def _get_our_price(self, service_id: str, endpoint: str, quantity: int = 1) -> float:
        """Get our optimal price for this request"""
        from payment_service import get_payment_service
        
        ps = get_payment_service()
        unit_price = ps.get_endpoint_price(service_id, endpoint, use_dynamic=True)
        
        # Bulk discount
        if quantity >= 100:
            unit_price *= 0.7  # 30% discount
        elif quantity >= 50:
            unit_price *= 0.8  # 20% discount
        elif quantity >= 20:
            unit_price *= 0.9  # 10% discount
        
        return round(unit_price * quantity, 4)
    
    def start_negotiation(self, service_id: str, endpoint: str, buyer_id: str,
                          offered_price: float, quantity: int = 1) -> NegotiationResponse:
        """Start a new negotiation"""
        
        negotiation_id = f"neg_{uuid.uuid4().hex[:12]}"
        our_price = self._get_our_price(service_id, endpoint, quantity)
        buyer_trust = self._get_buyer_trust(buyer_id)
        
        # Decision logic
        min_acceptable = our_price * 0.6  # Floor: 40% below our price
        
        now = datetime.now(UTC)
        expires_at = (now + timedelta(minutes=30)).isoformat()
        
        if offered_price >= our_price:
            # Great offer, accept immediately
            status = NegotiationStatus.ACCEPTED.value
            counter_price = None
            message = "Offer accepted! Proceed to payment."
            final_price = offered_price
        
        elif offered_price >= our_price * 0.85:
            # Close enough, accept
            status = NegotiationStatus.ACCEPTED.value
            counter_price = None
            message = "Offer accepted."
            final_price = offered_price
        
        elif offered_price >= min_acceptable:
            # Negotiate
            status = NegotiationStatus.COUNTERED.value
            # Counter at midpoint, slightly in our favor
            counter_price = round((offered_price + our_price) / 2 * 1.05, 4)
            message = f"Counter offer: ${counter_price:.4f}"
            if quantity > 1:
                message += f" for {quantity} requests (${counter_price/quantity:.4f}/each)"
            final_price = None
        
        else:
            # Too low
            if buyer_trust >= 0.7:
                # Good buyer, give them a chance
                status = NegotiationStatus.COUNTERED.value
                counter_price = round(min_acceptable * 1.1, 4)
                message = f"Your offer is quite low. Best we can do: ${counter_price:.4f}"
                final_price = None
            else:
                status = NegotiationStatus.REJECTED.value
                counter_price = our_price
                message = f"Offer too low. Minimum: ${min_acceptable:.4f}"
                final_price = None
        
        # Save negotiation
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO negotiations 
            (id, service_id, endpoint, buyer_id, quantity, initial_offer, current_offer,
             our_price, counter_price, status, round_number, final_price, expires_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (negotiation_id, service_id, endpoint, buyer_id, quantity, offered_price,
              offered_price, our_price, counter_price, status, 1, final_price,
              expires_at, now.isoformat(), now.isoformat()))
        
        # Log history
        cursor.execute("""
            INSERT INTO negotiation_history (negotiation_id, round_number, actor, action, price, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (negotiation_id, 1, "buyer", "offer", offered_price, f"Initial offer: ${offered_price}", now.isoformat()))
        
        cursor.execute("""
            INSERT INTO negotiation_history (negotiation_id, round_number, actor, action, price, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (negotiation_id, 1, "seller", status, counter_price or final_price, message, now.isoformat()))
        
        conn.commit()
        conn.close()
        
        return NegotiationResponse(
            negotiation_id=negotiation_id,
            status=status,
            your_offer=offered_price,
            our_price=our_price,
            counter_price=counter_price,
            message=message,
            round_number=1,
            max_rounds=self.MAX_ROUNDS,
            expires_at=expires_at,
            payment_url=f"/api/payment/pay/{negotiation_id}" if status == NegotiationStatus.ACCEPTED.value else None
        )
    
    def respond_to_counter(self, negotiation_id: str, action: str, 
                           new_offer: float = None) -> NegotiationResponse:
        """Handle buyer's response to counter offer"""
        
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM negotiations WHERE id = ?", (negotiation_id,))
        neg = cursor.fetchone()
        
        if not neg:
            conn.close()
            raise ValueError("Negotiation not found")
        
        if neg["status"] in [NegotiationStatus.ACCEPTED.value, 
                             NegotiationStatus.REJECTED.value,
                             NegotiationStatus.EXPIRED.value]:
            conn.close()
            raise ValueError(f"Negotiation already {neg['status']}")
        
        # Check expiry
        if datetime.fromisoformat(neg["expires_at"].replace('Z', '+00:00')) < datetime.now(UTC):
            cursor.execute("UPDATE negotiations SET status = 'expired' WHERE id = ?", (negotiation_id,))
            conn.commit()
            conn.close()
            raise ValueError("Negotiation expired")
        
        if neg["round_number"] >= self.MAX_ROUNDS:
            conn.close()
            raise ValueError("Maximum negotiation rounds reached")
        
        now = datetime.now(UTC)
        new_round = neg["round_number"] + 1
        
        if action == "accept":
            # Buyer accepts our counter
            final_price = neg["counter_price"]
            status = NegotiationStatus.ACCEPTED.value
            message = "Deal accepted! Proceed to payment."
            counter_price = None
            
        elif action == "counter" and new_offer is not None:
            # Buyer counters
            min_acceptable = neg["our_price"] * 0.6
            
            if new_offer >= neg["counter_price"]:
                # Buyer met or exceeded our counter
                status = NegotiationStatus.ACCEPTED.value
                final_price = new_offer
                counter_price = None
                message = "Offer accepted!"
                
            elif new_offer >= min_acceptable:
                # Still negotiating
                status = NegotiationStatus.COUNTERED.value
                # New counter - closer to their offer since they're engaging
                counter_price = round((new_offer + neg["counter_price"]) / 2, 4)
                final_price = None
                message = f"Counter: ${counter_price:.4f}"
                
            else:
                status = NegotiationStatus.REJECTED.value
                final_price = None
                counter_price = None
                message = f"Cannot go that low. Minimum: ${min_acceptable:.4f}"
        
        elif action == "reject":
            status = NegotiationStatus.REJECTED.value
            final_price = None
            counter_price = None
            message = "Negotiation ended by buyer."
        
        else:
            conn.close()
            raise ValueError("Invalid action. Use: accept, counter, reject")
        
        # Update negotiation
        expires_at = (now + timedelta(minutes=30)).isoformat()
        
        cursor.execute("""
            UPDATE negotiations 
            SET status = ?, round_number = ?, current_offer = ?, counter_price = ?,
                final_price = ?, expires_at = ?, updated_at = ?
            WHERE id = ?
        """, (status, new_round, new_offer or neg["current_offer"], counter_price,
              final_price, expires_at, now.isoformat(), negotiation_id))
        
        # Log history
        cursor.execute("""
            INSERT INTO negotiation_history (negotiation_id, round_number, actor, action, price, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (negotiation_id, new_round, "buyer", action, new_offer, f"Buyer {action}", now.isoformat()))
        
        cursor.execute("""
            INSERT INTO negotiation_history (negotiation_id, round_number, actor, action, price, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (negotiation_id, new_round, "seller", status, counter_price or final_price, message, now.isoformat()))
        
        conn.commit()
        conn.close()
        
        return NegotiationResponse(
            negotiation_id=negotiation_id,
            status=status,
            your_offer=new_offer or neg["current_offer"],
            our_price=neg["our_price"],
            counter_price=counter_price,
            message=message,
            round_number=new_round,
            max_rounds=self.MAX_ROUNDS,
            expires_at=expires_at,
            payment_url=f"/api/payment/pay/{negotiation_id}" if status == NegotiationStatus.ACCEPTED.value else None
        )
    
    def get_negotiation(self, negotiation_id: str) -> Optional[Dict]:
        """Get negotiation details"""
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM negotiations WHERE id = ?", (negotiation_id,))
        neg = cursor.fetchone()
        
        if not neg:
            conn.close()
            return None
        
        cursor.execute("""
            SELECT * FROM negotiation_history 
            WHERE negotiation_id = ? 
            ORDER BY created_at ASC
        """, (negotiation_id,))
        history = [dict(h) for h in cursor.fetchall()]
        
        conn.close()
        
        return {
            **dict(neg),
            "history": history
        }


_negotiation_engine = None

def get_negotiation_engine() -> NegotiationEngine:
    global _negotiation_engine
    if _negotiation_engine is None:
        _negotiation_engine = NegotiationEngine()
    return _negotiation_engine


if __name__ == "__main__":
    engine = NegotiationEngine()
    
    print("\n=== Negotiation Engine Test ===\n")
    
    # Test 1: Low offer
    print("Test 1: Low offer ($0.005 for $0.01 service)")
    resp = engine.start_negotiation("oracle_sentinel", "/api/v1/signal", "buyer_001", 0.005, 1)
    print(f"  Status: {resp.status}")
    print(f"  Our price: ${resp.our_price}")
    print(f"  Counter: ${resp.counter_price}")
    print(f"  Message: {resp.message}")
    
    # Test 2: Good offer
    print("\nTest 2: Good offer ($0.025 for $0.0268 service)")
    resp2 = engine.start_negotiation("oracle_sentinel", "/api/v1/signal", "buyer_002", 0.025, 1)
    print(f"  Status: {resp2.status}")
    print(f"  Message: {resp2.message}")
    
    # Test 3: Bulk negotiation
    print("\nTest 3: Bulk offer (100 requests at $0.50)")
    resp3 = engine.start_negotiation("oracle_sentinel", "/api/v1/signal", "buyer_003", 0.50, 100)
    print(f"  Status: {resp3.status}")
    print(f"  Our price (bulk): ${resp3.our_price}")
    print(f"  Counter: ${resp3.counter_price}")
    print(f"  Message: {resp3.message}")
