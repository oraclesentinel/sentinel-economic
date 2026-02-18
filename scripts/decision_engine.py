#!/usr/bin/env python3
"""
Sentinel Economic — Economic Decision Engine
"""

from datetime import datetime
from typing import Dict, Optional, List
from dataclasses import dataclass
from enum import Enum
import logging

from market_intelligence import MarketIntelligence
from dynamic_pricing import DynamicPricingAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("decision_engine")


class Action(Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    COUNTER = "counter"


@dataclass
class JobRequest:
    job_id: str
    service_type: str
    buyer_id: str
    offered_price: float
    complexity: str = "medium"
    urgency: str = "normal"


@dataclass
class Decision:
    job_id: str
    action: str
    confidence: float
    recommended_price: float
    reasoning: List[str]
    risks: List[str]
    profit_margin: float
    counter_offer: Optional[Dict]


class EconomicDecisionEngine:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.market_intel = MarketIntelligence(agent_id)
        self.pricing = DynamicPricingAI(agent_id, self.market_intel)
        self.config = {"min_trust": 30, "min_margin": 0.1, "max_workload": 0.8}
        self.workload = 0.3
    
    def evaluate(self, job: JobRequest, buyer_trust: float = 60) -> Decision:
        reasoning, risks = [], []
        
        price_rec = self.pricing.calculate_price(job.service_type, job.complexity, 
                                                  job.urgency, buyer_trust)
        
        cost = {"low": 0.001, "medium": 0.005, "high": 0.015}.get(job.complexity, 0.005)
        margin = (job.offered_price - cost) / job.offered_price if job.offered_price > 0 else 0
        
        # Evaluate
        trust_ok = buyer_trust >= self.config["min_trust"]
        price_ok = job.offered_price >= price_rec.min_price
        price_great = job.offered_price >= price_rec.optimal_price
        margin_ok = margin >= self.config["min_margin"]
        
        if buyer_trust >= 80: reasoning.append(f"High trust buyer ({buyer_trust})")
        elif trust_ok: reasoning.append(f"Acceptable trust ({buyer_trust})")
        else: reasoning.append(f"Low trust ({buyer_trust})"); risks.append("Low trust buyer")
        
        if price_great: reasoning.append(f"Price ${job.offered_price} exceeds optimal")
        elif price_ok: reasoning.append(f"Price ${job.offered_price} acceptable")
        else: reasoning.append(f"Price below minimum"); risks.append("Underpriced")
        
        # Decision
        if buyer_trust < 20:
            action, conf, counter = Action.REJECT, 0.95, None
        elif trust_ok and price_great and margin_ok:
            action, conf, counter = Action.ACCEPT, 0.9, None
        elif trust_ok and not price_ok:
            action, conf, counter = Action.COUNTER, 0.75, {"suggested": price_rec.optimal_price}
        elif trust_ok and price_ok:
            action, conf, counter = Action.ACCEPT, 0.7, None
        else:
            action, conf, counter = Action.REJECT, 0.6, None
        
        return Decision(job.job_id, action.value, conf, price_rec.optimal_price,
                       reasoning, risks, margin, counter)
    
    def quick_evaluate(self, service: str, price: float, trust: float = 60) -> Dict:
        rec = self.pricing.calculate_price(service, buyer_trust=trust)
        if trust < 20: return {"action": "reject", "reason": "Low trust"}
        if price >= rec.optimal_price: return {"action": "accept", "confidence": 0.85}
        if price >= rec.min_price: return {"action": "accept", "confidence": 0.65}
        return {"action": "counter", "suggested": rec.optimal_price}


if __name__ == "__main__":
    engine = EconomicDecisionEngine("sentinel_predict")
    
    job = JobRequest("job_001", "prediction_signal", "trader_1", 0.05)
    decision = engine.evaluate(job, 75)
    
    print(f"\nDecision: {decision.action.upper()} ({decision.confidence:.0%})")
    print(f"Recommended: ${decision.recommended_price:.4f}")
    print(f"Reasoning: {'; '.join(decision.reasoning)}")
