#!/usr/bin/env python3
"""
Sentinel Economic — Dynamic Pricing AI
"""

from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass
import logging

from market_intelligence import MarketIntelligence, MarketRate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dynamic_pricing")


@dataclass
class PriceRecommendation:
    service_type: str
    optimal_price: float
    min_price: float
    max_price: float
    breakdown: Dict[str, float]
    vs_market: str
    confidence: float
    reasoning: str


class DynamicPricingAI:
    def __init__(self, agent_id: str, market_intel: MarketIntelligence = None):
        self.agent_id = agent_id
        self.market_intel = market_intel or MarketIntelligence(agent_id)
        self.metrics = {"accuracy": 0.571, "reputation": 0.8, "success_rate": 0.95}
    
    def set_metrics(self, metrics: Dict):
        self.metrics.update(metrics)
    
    def calculate_price(self, service_type: str, complexity: str = "medium",
                       urgency: str = "normal", buyer_trust: float = None) -> PriceRecommendation:
        
        rate = self.market_intel.get_market_rate(service_type)
        base = rate.median_price if rate.sample_size > 0 else 0.01
        
        # Multipliers
        quality = 1.0 + (self.metrics.get("accuracy", 0.5) - 0.5)
        urg_map = {"low": 0.9, "normal": 1.0, "high": 1.3, "critical": 2.0}
        urgency_m = urg_map.get(urgency, 1.0)
        comp_map = {"low": 0.8, "medium": 1.0, "high": 1.5, "extreme": 2.5}
        complexity_m = comp_map.get(complexity, 1.0)
        demand_m = rate.demand_factor
        trust_d = 0.9 if buyer_trust and buyer_trust >= 80 else 1.0
        
        optimal = round(base * quality * urgency_m * complexity_m * demand_m * trust_d, 4)
        
        vs = "At market"
        if rate.avg_price > 0:
            pct = ((optimal - rate.avg_price) / rate.avg_price) * 100
            vs = f"+{pct:.0f}% above" if pct > 10 else f"{pct:.0f}% below" if pct < -10 else "At market"
        
        return PriceRecommendation(
            service_type=service_type,
            optimal_price=optimal,
            min_price=round(optimal * 0.8, 4),
            max_price=round(optimal * 1.2, 4),
            breakdown={"base": base, "quality": quality, "urgency": urgency_m, 
                      "complexity": complexity_m, "demand": demand_m, "trust": trust_d},
            vs_market=vs,
            confidence=0.7 + (0.2 if rate.sample_size > 20 else 0.1 if rate.sample_size > 5 else 0),
            reasoning=f"Base ${base:.4f} × quality {quality:.2f} × demand {demand_m:.1f}"
        )


if __name__ == "__main__":
    pricing = DynamicPricingAI("sentinel_predict")
    pricing.set_metrics({"accuracy": 0.571})
    
    rec = pricing.calculate_price("prediction_signal", "medium", "normal", 75)
    print(f"\nOptimal: ${rec.optimal_price:.4f} | Range: ${rec.min_price:.4f}-${rec.max_price:.4f}")
    print(f"vs Market: {rec.vs_market} | Confidence: {rec.confidence:.0%}")
