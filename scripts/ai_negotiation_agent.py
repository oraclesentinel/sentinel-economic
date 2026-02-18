#!/usr/bin/env python3
"""
Sentinel Economic — AI Negotiation Agent
LLM-powered intelligent negotiation with learning capabilities
"""

import json
import os
import sqlite3
import requests
from datetime import datetime, UTC, timedelta
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass, asdict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_negotiation_agent")

DB_PATH = os.path.expanduser("~/sentinel-economic/data/sentinel_economic.db")

# Load API key
from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/oracle-sentinel/config/.env"))
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")


@dataclass
class BuyerProfile:
    buyer_id: str
    total_transactions: int
    total_spent: float
    avg_offer_ratio: float  # avg(offer / asking_price)
    acceptance_rate: float
    counter_acceptance_rate: float
    negotiation_rounds_avg: float
    last_active: str
    tags: List[str]  # ["high_value", "price_sensitive", "quick_decider", etc.]


@dataclass
class NegotiationContext:
    negotiation_id: str
    service_id: str
    endpoint: str
    buyer_id: str
    buyer_profile: BuyerProfile
    our_price: float
    min_acceptable: float
    offered_price: float
    quantity: int
    round_number: int
    history: List[Dict]
    market_conditions: Dict


@dataclass
class AIDecision:
    action: str  # "accept", "counter", "reject"
    counter_price: Optional[float]
    confidence: float
    reasoning: str
    strategy: str
    predicted_acceptance: float
    suggested_message: str


class AINegotiationAgent:
    """LLM-powered negotiation agent with learning capabilities"""
    
    def __init__(self):
        self._ensure_tables()
    
    def _ensure_tables(self):
        """Create tables for AI learning"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Buyer profiles (learned from interactions)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS buyer_profiles (
                buyer_id TEXT PRIMARY KEY,
                total_transactions INTEGER DEFAULT 0,
                total_spent REAL DEFAULT 0,
                avg_offer_ratio REAL DEFAULT 1.0,
                acceptance_rate REAL DEFAULT 0.5,
                counter_acceptance_rate REAL DEFAULT 0.5,
                negotiation_rounds_avg REAL DEFAULT 1.0,
                preferred_services TEXT,
                behavior_tags TEXT,
                last_active TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        # AI decision log (for learning)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                negotiation_id TEXT,
                round_number INTEGER,
                context_json TEXT,
                decision_json TEXT,
                actual_outcome TEXT,
                outcome_correct INTEGER,
                created_at TEXT
            )
        """)
        
        # Strategy performance tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT,
                total_used INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                avg_final_price REAL,
                avg_rounds REAL,
                last_used TEXT,
                updated_at TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    
    def _get_db(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_buyer_profile(self, buyer_id: str) -> BuyerProfile:
        """Get or create buyer profile with learned behavior"""
        conn = self._get_db()
        cursor = conn.cursor()
        
        # Check existing profile
        cursor.execute("SELECT * FROM buyer_profiles WHERE buyer_id = ?", (buyer_id,))
        profile = cursor.fetchone()
        
        if profile:
            tags = json.loads(profile["behavior_tags"]) if profile["behavior_tags"] else []
            conn.close()
            return BuyerProfile(
                buyer_id=buyer_id,
                total_transactions=profile["total_transactions"],
                total_spent=profile["total_spent"],
                avg_offer_ratio=profile["avg_offer_ratio"],
                acceptance_rate=profile["acceptance_rate"],
                counter_acceptance_rate=profile["counter_acceptance_rate"],
                negotiation_rounds_avg=profile["negotiation_rounds_avg"],
                last_active=profile["last_active"] or "",
                tags=tags
            )
        
        # Analyze from transaction history
        cursor.execute("""
            SELECT COUNT(*) as count, SUM(price) as total, AVG(price) as avg
            FROM transactions WHERE buyer_id = ?
        """, (buyer_id,))
        txn_stats = cursor.fetchone()
        
        # Analyze from negotiation history
        cursor.execute("""
            SELECT 
                COUNT(*) as total_negs,
                AVG(CASE WHEN status = 'accepted' THEN 1.0 ELSE 0.0 END) as accept_rate,
                AVG(round_number) as avg_rounds,
                AVG(initial_offer / our_price) as avg_offer_ratio
            FROM negotiations WHERE buyer_id = ?
        """, (buyer_id,))
        neg_stats = cursor.fetchone()
        
        # Determine behavior tags
        tags = []
        if (txn_stats["total"] or 0) > 10:
            tags.append("high_value")
        if (neg_stats["avg_offer_ratio"] or 1.0) < 0.7:
            tags.append("price_sensitive")
        if (neg_stats["avg_rounds"] or 1.0) < 1.5:
            tags.append("quick_decider")
        if (neg_stats["accept_rate"] or 0.5) > 0.7:
            tags.append("easy_closer")
        
        # Create new profile
        now = datetime.now(UTC).isoformat()
        cursor.execute("""
            INSERT INTO buyer_profiles 
            (buyer_id, total_transactions, total_spent, avg_offer_ratio, 
             acceptance_rate, counter_acceptance_rate, negotiation_rounds_avg,
             behavior_tags, last_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            buyer_id,
            txn_stats["count"] or 0,
            txn_stats["total"] or 0,
            neg_stats["avg_offer_ratio"] or 1.0,
            neg_stats["accept_rate"] or 0.5,
            0.5,  # default counter acceptance
            neg_stats["avg_rounds"] or 1.0,
            json.dumps(tags),
            now, now, now
        ))
        conn.commit()
        conn.close()
        
        return BuyerProfile(
            buyer_id=buyer_id,
            total_transactions=txn_stats["count"] or 0,
            total_spent=txn_stats["total"] or 0,
            avg_offer_ratio=neg_stats["avg_offer_ratio"] or 1.0,
            acceptance_rate=neg_stats["accept_rate"] or 0.5,
            counter_acceptance_rate=0.5,
            negotiation_rounds_avg=neg_stats["avg_rounds"] or 1.0,
            last_active=now,
            tags=tags
        )
    
    def get_market_conditions(self) -> Dict:
        """Get current market conditions for context"""
        conn = self._get_db()
        cursor = conn.cursor()
        
        # Recent activity (24h)
        cursor.execute("""
            SELECT COUNT(*) as count, AVG(price) as avg_price
            FROM transactions
            WHERE timestamp > datetime('now', '-24 hours')
        """)
        recent = cursor.fetchone()
        
        # Negotiation success rate (7d)
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'accepted' THEN 1 ELSE 0 END) as accepted
            FROM negotiations
            WHERE created_at > datetime('now', '-7 days')
        """)
        neg_stats = cursor.fetchone()
        
        conn.close()
        
        success_rate = (neg_stats["accepted"] / neg_stats["total"] * 100) if neg_stats["total"] > 0 else 50
        
        return {
            "transactions_24h": recent["count"] or 0,
            "avg_price_24h": round(recent["avg_price"] or 0, 4),
            "demand_level": "high" if (recent["count"] or 0) > 10 else "medium" if (recent["count"] or 0) > 3 else "low",
            "negotiation_success_rate": round(success_rate, 1),
            "market_trend": "stable"  # TODO: calculate from price history
        }
    
    def get_strategy_performance(self) -> Dict:
        """Get performance of different negotiation strategies"""
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT strategy_name, total_used, success_count, 
                   CAST(success_count AS REAL) / NULLIF(total_used, 0) as success_rate
            FROM strategy_performance
            ORDER BY success_rate DESC
        """)
        
        strategies = {row["strategy_name"]: {
            "total_used": row["total_used"],
            "success_count": row["success_count"],
            "success_rate": round(row["success_rate"] or 0, 2)
        } for row in cursor.fetchall()}
        
        conn.close()
        return strategies
    
    def make_decision(self, context: NegotiationContext) -> AIDecision:
        """Use LLM to make intelligent negotiation decision"""
        
        # Build prompt with full context
        prompt = self._build_decision_prompt(context)
        
        # Call LLM
        try:
            response = self._call_llm(prompt)
            decision = self._parse_llm_response(response, context)
        except Exception as e:
            logger.error(f"LLM decision failed: {e}, falling back to rules")
            decision = self._fallback_decision(context)
        
        # Log decision for learning
        self._log_decision(context, decision)
        
        return decision
    
    def _build_decision_prompt(self, ctx: NegotiationContext) -> str:
        """Build comprehensive prompt for LLM decision"""
        
        strategy_perf = self.get_strategy_performance()
        
        prompt = f"""You are an AI negotiation agent for Sentinel Economic, a pricing infrastructure for AI agents.

## YOUR GOAL
Maximize successful deals while maintaining fair prices. Balance between:
- Closing deals (revenue)
- Maintaining price integrity (not underselling)
- Building long-term buyer relationships

## CURRENT NEGOTIATION

**Service**: {ctx.service_id}
**Endpoint**: {ctx.endpoint}
**Quantity**: {ctx.quantity}

**Pricing**:
- Our optimal price: ${ctx.our_price:.4f}
- Minimum acceptable: ${ctx.min_acceptable:.4f}
- Buyer's offer: ${ctx.offered_price:.4f}
- Offer ratio: {(ctx.offered_price / ctx.our_price * 100):.1f}% of our price

**Round**: {ctx.round_number} of 3

## BUYER PROFILE: {ctx.buyer_id}

- Total transactions: {ctx.buyer_profile.total_transactions}
- Total spent: ${ctx.buyer_profile.total_spent:.2f}
- Avg offer ratio: {ctx.buyer_profile.avg_offer_ratio:.1%} of asking price
- Acceptance rate: {ctx.buyer_profile.acceptance_rate:.1%}
- Counter acceptance rate: {ctx.buyer_profile.counter_acceptance_rate:.1%}
- Avg negotiation rounds: {ctx.buyer_profile.negotiation_rounds_avg:.1f}
- Behavior tags: {', '.join(ctx.buyer_profile.tags) or 'new_buyer'}

## MARKET CONDITIONS

- Demand level: {ctx.market_conditions.get('demand_level', 'medium')}
- Transactions (24h): {ctx.market_conditions.get('transactions_24h', 0)}
- Avg price (24h): ${ctx.market_conditions.get('avg_price_24h', 0):.4f}
- Negotiation success rate: {ctx.market_conditions.get('negotiation_success_rate', 50)}%

## NEGOTIATION HISTORY
{json.dumps(ctx.history[-5:], indent=2) if ctx.history else "First offer"}

## STRATEGY PERFORMANCE (what worked before)
{json.dumps(strategy_perf, indent=2) if strategy_perf else "No data yet"}

## YOUR TASK

Analyze this negotiation and decide:
1. **Action**: "accept", "counter", or "reject"
2. **Counter price** (if countering): specific dollar amount
3. **Strategy name**: e.g., "meet_in_middle", "firm_stance", "loyalty_discount", "volume_deal"
4. **Predicted acceptance probability**: 0-100%
5. **Suggested message**: professional message to buyer

Respond in this exact JSON format:
```json
{{
    "action": "accept|counter|reject",
    "counter_price": 0.0000,
    "confidence": 0.85,
    "reasoning": "Brief explanation of your decision",
    "strategy": "strategy_name",
    "predicted_acceptance": 75,
    "suggested_message": "Message to send to buyer"
}}
```

Think step by step:
1. Is this offer acceptable as-is?
2. If not, what counter would this buyer likely accept?
3. What's the risk of losing this deal vs. getting a better price?
"""
        return prompt
    
    def _call_llm(self, prompt: str) -> str:
        """Call OpenRouter LLM API"""
        
        if not OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY not set")
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "anthropic/claude-sonnet-4",
                "messages": [
                    {"role": "system", "content": "You are an expert AI negotiation agent. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 500,
                "temperature": 0.3
            },
            timeout=30
        )
        
        if response.status_code != 200:
            raise Exception(f"LLM API error: {response.status_code}")
        
        return response.json()["choices"][0]["message"]["content"]
    
    def _parse_llm_response(self, response: str, ctx: NegotiationContext) -> AIDecision:
        """Parse LLM response into AIDecision"""
        
        # Extract JSON from response
        try:
            # Find JSON block
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]
            else:
                json_str = response
            
            data = json.loads(json_str.strip())
            
            # Validate action
            action = data.get("action", "reject").lower()
            if action not in ["accept", "counter", "reject"]:
                action = "reject"
            
            # Validate counter price
            counter_price = None
            if action == "counter":
                counter_price = float(data.get("counter_price", ctx.our_price))
                # Ensure counter is within bounds
                counter_price = max(ctx.min_acceptable, min(counter_price, ctx.our_price * 1.2))
                counter_price = round(counter_price, 4)
            
            return AIDecision(
                action=action,
                counter_price=counter_price,
                confidence=float(data.get("confidence", 0.7)),
                reasoning=data.get("reasoning", "AI decision"),
                strategy=data.get("strategy", "adaptive"),
                predicted_acceptance=float(data.get("predicted_acceptance", 50)),
                suggested_message=data.get("suggested_message", f"Counter offer: ${counter_price}" if counter_price else "")
            )
            
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return self._fallback_decision(ctx)
    
    def _fallback_decision(self, ctx: NegotiationContext) -> AIDecision:
        """Rule-based fallback when LLM fails"""
        
        offer_ratio = ctx.offered_price / ctx.our_price
        
        if offer_ratio >= 1.0:
            return AIDecision(
                action="accept",
                counter_price=None,
                confidence=0.95,
                reasoning="Offer meets or exceeds our price",
                strategy="direct_accept",
                predicted_acceptance=100,
                suggested_message="Offer accepted! Proceed to payment."
            )
        
        elif offer_ratio >= 0.85:
            return AIDecision(
                action="accept",
                counter_price=None,
                confidence=0.8,
                reasoning="Offer is close enough to accept",
                strategy="close_enough",
                predicted_acceptance=100,
                suggested_message="Offer accepted."
            )
        
        elif offer_ratio >= 0.6:
            counter = round((ctx.offered_price + ctx.our_price) / 2, 4)
            return AIDecision(
                action="counter",
                counter_price=counter,
                confidence=0.7,
                reasoning="Offer in negotiable range, countering at midpoint",
                strategy="meet_in_middle",
                predicted_acceptance=60,
                suggested_message=f"Counter offer: ${counter:.4f}"
            )
        
        else:
            return AIDecision(
                action="reject",
                counter_price=None,
                confidence=0.9,
                reasoning="Offer too low",
                strategy="firm_stance",
                predicted_acceptance=0,
                suggested_message=f"Offer too low. Minimum acceptable: ${ctx.min_acceptable:.4f}"
            )
    
    def _log_decision(self, ctx: NegotiationContext, decision: AIDecision):
        """Log decision for learning"""
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO ai_decisions 
            (negotiation_id, round_number, context_json, decision_json, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            ctx.negotiation_id,
            ctx.round_number,
            json.dumps(asdict(ctx.buyer_profile)),
            json.dumps(asdict(decision)),
            datetime.now(UTC).isoformat()
        ))
        
        conn.commit()
        conn.close()
    
    def record_outcome(self, negotiation_id: str, outcome: str, final_price: float = None):
        """Record negotiation outcome for learning"""
        conn = self._get_db()
        cursor = conn.cursor()
        
        # Update AI decisions with outcome
        cursor.execute("""
            UPDATE ai_decisions 
            SET actual_outcome = ?,
                outcome_correct = CASE 
                    WHEN json_extract(decision_json, '$.action') = ? THEN 1 
                    ELSE 0 
                END
            WHERE negotiation_id = ?
        """, (outcome, outcome, negotiation_id))
        
        # Get the strategy used
        cursor.execute("""
            SELECT json_extract(decision_json, '$.strategy') as strategy
            FROM ai_decisions
            WHERE negotiation_id = ?
            ORDER BY round_number DESC LIMIT 1
        """, (negotiation_id,))
        row = cursor.fetchone()
        
        if row and row["strategy"]:
            strategy = row["strategy"]
            success = 1 if outcome == "accepted" else 0
            
            # Update strategy performance
            cursor.execute("""
                INSERT INTO strategy_performance (strategy_name, total_used, success_count, last_used, updated_at)
                VALUES (?, 1, ?, ?, ?)
                ON CONFLICT(strategy_name) DO UPDATE SET
                    total_used = total_used + 1,
                    success_count = success_count + ?,
                    last_used = ?,
                    updated_at = ?
            """, (strategy, success, datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat(),
                  success, datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat()))
        
        # Update buyer profile
        cursor.execute("""
            SELECT buyer_id FROM negotiations WHERE id = ?
        """, (negotiation_id,))
        neg = cursor.fetchone()
        
        if neg:
            self._update_buyer_profile(cursor, neg["buyer_id"], outcome, final_price)
        
        conn.commit()
        conn.close()
    
    def _update_buyer_profile(self, cursor, buyer_id: str, outcome: str, final_price: float):
        """Update buyer profile based on outcome"""
        now = datetime.now(UTC).isoformat()
        
        if outcome == "accepted":
            cursor.execute("""
                UPDATE buyer_profiles SET
                    total_transactions = total_transactions + 1,
                    total_spent = total_spent + ?,
                    acceptance_rate = (acceptance_rate * total_transactions + 1) / (total_transactions + 1),
                    last_active = ?,
                    updated_at = ?
                WHERE buyer_id = ?
            """, (final_price or 0, now, now, buyer_id))
        else:
            cursor.execute("""
                UPDATE buyer_profiles SET
                    acceptance_rate = (acceptance_rate * total_transactions) / (total_transactions + 1),
                    last_active = ?,
                    updated_at = ?
                WHERE buyer_id = ?
            """, (now, now, buyer_id))


# Singleton
_ai_agent = None

def get_ai_agent() -> AINegotiationAgent:
    global _ai_agent
    if _ai_agent is None:
        _ai_agent = AINegotiationAgent()
    return _ai_agent


if __name__ == "__main__":
    print("\n=== AI Negotiation Agent Test ===\n")
    
    agent = AINegotiationAgent()
    
    # Get buyer profile
    profile = agent.get_buyer_profile("test_buyer_001")
    print(f"Buyer Profile: {profile.buyer_id}")
    print(f"  Tags: {profile.tags}")
    print(f"  Acceptance Rate: {profile.acceptance_rate:.1%}")
    
    # Get market conditions
    market = agent.get_market_conditions()
    print(f"\nMarket Conditions:")
    print(f"  Demand: {market['demand_level']}")
    print(f"  Success Rate: {market['negotiation_success_rate']}%")
    
    # Test decision making
    context = NegotiationContext(
        negotiation_id="test_neg_001",
        service_id="oracle_sentinel",
        endpoint="/api/v1/signal",
        buyer_id="test_buyer_001",
        buyer_profile=profile,
        our_price=0.0268,
        min_acceptable=0.0161,
        offered_price=0.02,
        quantity=1,
        round_number=1,
        history=[],
        market_conditions=market
    )
    
    print(f"\nMaking AI Decision...")
    print(f"  Our price: ${context.our_price}")
    print(f"  Buyer offer: ${context.offered_price}")
    
    decision = agent.make_decision(context)
    
    print(f"\nAI Decision:")
    print(f"  Action: {decision.action}")
    print(f"  Counter: ${decision.counter_price}" if decision.counter_price else "  Counter: N/A")
    print(f"  Confidence: {decision.confidence:.0%}")
    print(f"  Strategy: {decision.strategy}")
    print(f"  Predicted Acceptance: {decision.predicted_acceptance:.0f}%")
    print(f"  Reasoning: {decision.reasoning}")
    print(f"  Message: {decision.suggested_message}")
