#!/usr/bin/env python3
"""
Sentinel Economic — AI-Powered Negotiation Engine
Replaces rule-based negotiation with AI agent
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, UTC
from typing import Dict, Optional
from dataclasses import dataclass, asdict
from enum import Enum
import logging

from ai_negotiation_agent import (
    get_ai_agent, 
    NegotiationContext, 
    BuyerProfile,
    AIDecision
)
from payment_service import get_payment_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("negotiation_engine_ai")

DB_PATH = os.path.expanduser("~/sentinel-economic/data/sentinel_economic.db")


class NegotiationStatus(Enum):
    PENDING = "pending"
    COUNTERED = "countered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


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
    ai_insights: Optional[Dict]  # NEW: AI reasoning


class AINegotiationEngine:
    """AI-powered negotiation engine"""
    
    MAX_ROUNDS = 3
    
    def __init__(self):
        self.ai_agent = get_ai_agent()
        self.payment_service = get_payment_service()
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
                ai_strategy TEXT,
                ai_confidence REAL,
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
                ai_reasoning TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        conn.commit()
        conn.close()
    
    def _get_db(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _get_our_price(self, service_id: str, endpoint: str, quantity: int = 1) -> float:
        """Get optimal price using payment service"""
        unit_price = self.payment_service.get_endpoint_price(service_id, endpoint, use_dynamic=True)
        
        # Bulk discount
        if quantity >= 100:
            unit_price *= 0.7
        elif quantity >= 50:
            unit_price *= 0.8
        elif quantity >= 20:
            unit_price *= 0.9
        
        return round(unit_price * quantity, 4)
    
    def _get_negotiation_history(self, negotiation_id: str) -> list:
        """Get negotiation history"""
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM negotiation_history 
            WHERE negotiation_id = ? 
            ORDER BY created_at ASC
        """, (negotiation_id,))
        
        history = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return history
    
    def start_negotiation(self, service_id: str, endpoint: str, buyer_id: str,
                          offered_price: float, quantity: int = 1) -> NegotiationResponse:
        """Start AI-powered negotiation"""
        
        negotiation_id = f"neg_{uuid.uuid4().hex[:12]}"
        our_price = self._get_our_price(service_id, endpoint, quantity)
        min_acceptable = our_price * 0.6
        
        # Get buyer profile
        buyer_profile = self.ai_agent.get_buyer_profile(buyer_id)
        
        # Get market conditions
        market_conditions = self.ai_agent.get_market_conditions()
        
        # Build context for AI
        context = NegotiationContext(
            negotiation_id=negotiation_id,
            service_id=service_id,
            endpoint=endpoint,
            buyer_id=buyer_id,
            buyer_profile=buyer_profile,
            our_price=our_price,
            min_acceptable=min_acceptable,
            offered_price=offered_price,
            quantity=quantity,
            round_number=1,
            history=[],
            market_conditions=market_conditions
        )
        
        # AI makes decision
        decision = self.ai_agent.make_decision(context)
        
        # Map AI decision to negotiation status
        now = datetime.now(UTC)
        expires_at = (now + timedelta(minutes=30)).isoformat()
        
        if decision.action == "accept":
            status = NegotiationStatus.ACCEPTED.value
            final_price = offered_price
        elif decision.action == "counter":
            status = NegotiationStatus.COUNTERED.value
            final_price = None
        else:
            status = NegotiationStatus.REJECTED.value
            final_price = None
        
        # Save to database
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO negotiations 
            (id, service_id, endpoint, buyer_id, quantity, initial_offer, current_offer,
             our_price, counter_price, status, round_number, final_price, ai_strategy,
             ai_confidence, expires_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            negotiation_id, service_id, endpoint, buyer_id, quantity,
            offered_price, offered_price, our_price, decision.counter_price,
            status, 1, final_price, decision.strategy, decision.confidence,
            expires_at, now.isoformat(), now.isoformat()
        ))
        
        # Log history
        cursor.execute("""
            INSERT INTO negotiation_history 
            (negotiation_id, round_number, actor, action, price, message, ai_reasoning, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (negotiation_id, 1, "buyer", "offer", offered_price, 
              f"Initial offer: ${offered_price}", None, now.isoformat()))
        
        cursor.execute("""
            INSERT INTO negotiation_history 
            (negotiation_id, round_number, actor, action, price, message, ai_reasoning, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (negotiation_id, 1, "seller", decision.action, 
              decision.counter_price or final_price, decision.suggested_message,
              decision.reasoning, now.isoformat()))
        
        conn.commit()
        conn.close()
        
        return NegotiationResponse(
            negotiation_id=negotiation_id,
            status=status,
            your_offer=offered_price,
            our_price=our_price,
            counter_price=decision.counter_price,
            message=decision.suggested_message,
            round_number=1,
            max_rounds=self.MAX_ROUNDS,
            expires_at=expires_at,
            payment_url=f"/api/payment/pay/{negotiation_id}" if status == NegotiationStatus.ACCEPTED.value else None,
            ai_insights={
                "strategy": decision.strategy,
                "confidence": decision.confidence,
                "predicted_acceptance": decision.predicted_acceptance,
                "reasoning": decision.reasoning
            }
        )
    
    def respond_to_counter(self, negotiation_id: str, action: str,
                           new_offer: float = None) -> NegotiationResponse:
        """Handle buyer's response with AI decision"""
        
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
        
        if neg["round_number"] >= self.MAX_ROUNDS:
            conn.close()
            raise ValueError("Maximum negotiation rounds reached")
        
        now = datetime.now(UTC)
        new_round = neg["round_number"] + 1
        
        if action == "accept":
            # Buyer accepts our counter
            status = NegotiationStatus.ACCEPTED.value
            final_price = neg["counter_price"]
            counter_price = None
            message = "Deal accepted! Proceed to payment."
            ai_insights = {"strategy": "buyer_accepted", "confidence": 1.0}
            
            # Record outcome for learning
            self.ai_agent.record_outcome(negotiation_id, "accepted", final_price)
            
        elif action == "counter" and new_offer is not None:
            # Buyer counters - AI decides again
            buyer_profile = self.ai_agent.get_buyer_profile(neg["buyer_id"])
            market_conditions = self.ai_agent.get_market_conditions()
            history = self._get_negotiation_history(negotiation_id)
            
            context = NegotiationContext(
                negotiation_id=negotiation_id,
                service_id=neg["service_id"],
                endpoint=neg["endpoint"],
                buyer_id=neg["buyer_id"],
                buyer_profile=buyer_profile,
                our_price=neg["our_price"],
                min_acceptable=neg["our_price"] * 0.6,
                offered_price=new_offer,
                quantity=neg["quantity"],
                round_number=new_round,
                history=history,
                market_conditions=market_conditions
            )
            
            decision = self.ai_agent.make_decision(context)
            
            if decision.action == "accept":
                status = NegotiationStatus.ACCEPTED.value
                final_price = new_offer
                counter_price = None
                self.ai_agent.record_outcome(negotiation_id, "accepted", final_price)
            elif decision.action == "counter":
                status = NegotiationStatus.COUNTERED.value
                final_price = None
                counter_price = decision.counter_price
            else:
                status = NegotiationStatus.REJECTED.value
                final_price = None
                counter_price = None
                self.ai_agent.record_outcome(negotiation_id, "rejected", None)
            
            message = decision.suggested_message
            ai_insights = {
                "strategy": decision.strategy,
                "confidence": decision.confidence,
                "predicted_acceptance": decision.predicted_acceptance,
                "reasoning": decision.reasoning
            }
            
        elif action == "reject":
            status = NegotiationStatus.REJECTED.value
            final_price = None
            counter_price = None
            message = "Negotiation ended by buyer."
            ai_insights = {"strategy": "buyer_rejected", "confidence": 1.0}
            
            self.ai_agent.record_outcome(negotiation_id, "rejected", None)
            
        else:
            conn.close()
            raise ValueError("Invalid action. Use: accept, counter, reject")
        
        # Update database
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
            INSERT INTO negotiation_history 
            (negotiation_id, round_number, actor, action, price, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (negotiation_id, new_round, "buyer", action, new_offer, 
              f"Buyer {action}", now.isoformat()))
        
        cursor.execute("""
            INSERT INTO negotiation_history 
            (negotiation_id, round_number, actor, action, price, message, ai_reasoning, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (negotiation_id, new_round, "seller", status, counter_price or final_price,
              message, ai_insights.get("reasoning"), now.isoformat()))
        
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
            payment_url=f"/api/payment/pay/{negotiation_id}" if status == NegotiationStatus.ACCEPTED.value else None,
            ai_insights=ai_insights
        )
    
    def get_negotiation(self, negotiation_id: str) -> Optional[Dict]:
        """Get negotiation with AI insights"""
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM negotiations WHERE id = ?", (negotiation_id,))
        neg = cursor.fetchone()
        
        if not neg:
            conn.close()
            return None
        
        history = self._get_negotiation_history(negotiation_id)
        conn.close()
        
        return {
            **dict(neg),
            "history": history
        }


# Singleton
_ai_engine = None

def get_ai_negotiation_engine() -> AINegotiationEngine:
    global _ai_engine
    if _ai_engine is None:
        _ai_engine = AINegotiationEngine()
    return _ai_engine


if __name__ == "__main__":
    print("\n=== AI Negotiation Engine Test ===\n")
    
    engine = AINegotiationEngine()
    
    # Test negotiation
    print("Starting AI-powered negotiation...")
    resp = engine.start_negotiation(
        service_id="oracle_sentinel",
        endpoint="/api/v1/signal",
        buyer_id="smart_buyer_001",
        offered_price=0.018,
        quantity=1
    )
    
    print(f"\nNegotiation ID: {resp.negotiation_id}")
    print(f"Status: {resp.status}")
    print(f"Your Offer: ${resp.your_offer}")
    print(f"Our Price: ${resp.our_price}")
    print(f"Counter: ${resp.counter_price}" if resp.counter_price else "Counter: N/A")
    print(f"Message: {resp.message}")
    print(f"\nAI Insights:")
    print(f"  Strategy: {resp.ai_insights['strategy']}")
    print(f"  Confidence: {resp.ai_insights['confidence']:.0%}")
    print(f"  Predicted Acceptance: {resp.ai_insights['predicted_acceptance']:.0f}%")
