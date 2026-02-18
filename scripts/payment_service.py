#!/usr/bin/env python3
"""
Sentinel Economic — Unified Payment Service
Handles x402 (PayAI) payments for all services
"""

import json
import os
import yaml
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("payment_service")

CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', 'config')


@dataclass
class PaymentRequirement:
    service_id: str
    endpoint: str
    price: float
    currency: str
    payment_methods: list
    expires_at: str
    metadata: Dict


@dataclass 
class PaymentResult:
    success: bool
    method: str  # "x402", "token_gating"
    amount: float
    tx_hash: Optional[str]
    buyer_id: Optional[str]
    message: str


class PaymentService:
    def __init__(self):
        self.services = self._load_services()
        self.global_config = self._load_global_config()
        
    def _load_services(self) -> Dict:
        """Load service registry from YAML"""
        path = os.path.join(CONFIG_DIR, 'services.yaml')
        with open(path, 'r') as f:
            config = yaml.safe_load(f)
        return config.get('services', {})
    
    def _load_global_config(self) -> Dict:
        """Load global payment config"""
        path = os.path.join(CONFIG_DIR, 'services.yaml')
        with open(path, 'r') as f:
            config = yaml.safe_load(f)
        return config.get('global', {})
    
    def get_service(self, service_id: str) -> Optional[Dict]:
        """Get service configuration"""
        return self.services.get(service_id)
    
    def get_endpoint_price(self, service_id: str, endpoint: str, 
                           use_dynamic: bool = True) -> float:
        """
        Get price for an endpoint.
        If use_dynamic=True, applies dynamic pricing factors.
        """
        service = self.get_service(service_id)
        if not service:
            return 0.01  # Default
        
        endpoints = service.get('endpoints', {})
        
        # Exact match first
        if endpoint in endpoints:
            base_price = endpoints[endpoint].get('price', 0.01)
        else:
            # Partial match (for parameterized routes like /api/v1/signal/<slug>)
            base_price = 0.01
            for ep, config in endpoints.items():
                if endpoint.startswith(ep.split('<')[0].rstrip('/')):
                    base_price = config.get('price', 0.01)
                    break
        
        if use_dynamic:
            # Import here to avoid circular dependency
            from dynamic_pricing import DynamicPricingAI
            from market_intelligence import MarketIntelligence
            
            mi = MarketIntelligence(service_id)
            pricing = DynamicPricingAI(service_id, mi)
            
            # Map endpoint to service_type
            service_type = self._endpoint_to_service_type(service_id, endpoint)
            rec = pricing.calculate_price(service_type)
            
            # Use dynamic price if available, else base
            if rec.optimal_price > 0:
                return rec.optimal_price
        
        return base_price
    
    def _endpoint_to_service_type(self, service_id: str, endpoint: str) -> str:
        """Map endpoint to service_type for market intelligence"""
        # Simple mapping - can be enhanced
        if "signal" in endpoint:
            return "prediction_signal"
        elif "analysis" in endpoint or "analyze" in endpoint:
            return "prediction_analysis"
        elif "whale" in endpoint:
            return "whale_data"
        elif "scan" in endpoint:
            return "code_scan"
        elif "report" in endpoint:
            return "security_report"
        return f"{service_id}_default"
    
    def create_payment_requirements(self, service_id: str, endpoint: str,
                                     method: str = "GET") -> PaymentRequirement:
        """Create 402 payment requirements for an endpoint"""
        service = self.get_service(service_id)
        if not service:
            raise ValueError(f"Unknown service: {service_id}")
        
        price = self.get_endpoint_price(service_id, endpoint)
        price_micro = int(price * 1_000_000)  # Convert to micro-USDC
        
        # Build payment methods
        payment_methods = []
        
        # x402 method
        payment_methods.append({
            "type": "x402",
            "scheme": "exact",
            "network": self.global_config["network_string"],
            "maxAmountRequired": str(price_micro),
            "asset": self.global_config["usdc_mint"],
            "payTo": service["treasury_wallet"],
            "extra": {
                "facilitator": self.global_config["facilitator_url"],
                "description": f"{service['name']}: {method} {endpoint}",
                "mimeType": "application/json"
            }
        })
        
        # Token gating (if enabled)
        if service.get('token_gating', {}).get('enabled'):
            payment_methods.append({
                "type": "token_gating",
                "token_mint": service['token_gating']['mint'],
                "min_balance": service['token_gating']['min_balance'],
                "benefit": "Free unlimited API access"
            })
        
        
        return PaymentRequirement(
            service_id=service_id,
            endpoint=endpoint,
            price=price,
            currency="USDC",
            payment_methods=payment_methods,
            expires_at=(datetime.utcnow() + timedelta(minutes=5)).isoformat(),
            metadata={
                "service_name": service["name"],
                "method": method
            }
        )
    
    def verify_x402_payment(self, service_id: str, endpoint: str,
                            payment_header: str) -> PaymentResult:
        """Verify and settle x402 payment"""
        service = self.get_service(service_id)
        if not service:
            return PaymentResult(False, "x402", 0, None, None, "Unknown service")
        
        price = self.get_endpoint_price(service_id, endpoint)
        price_micro = int(price * 1_000_000)
        
        try:
            # Verify with facilitator
            verify_response = requests.post(
                f"{self.global_config['facilitator_url']}/verify",
                json={
                    "x402Version": 2,
                    "payment": payment_header,
                    "paymentRequirements": {
                        "scheme": "exact",
                        "network": self.global_config["network_string"],
                        "maxAmountRequired": str(price_micro),
                        "asset": self.global_config["usdc_mint"],
                        "payTo": service["treasury_wallet"]
                    }
                },
                timeout=30
            )
            
            if verify_response.status_code == 200:
                result = verify_response.json()
                if result.get("valid") or result.get("isValid"):
                    # Settle payment
                    settle_response = requests.post(
                        f"{self.global_config['facilitator_url']}/settle",
                        json={"x402Version": 2, "payment": payment_header},
                        timeout=30
                    )
                    
                    tx_hash = result.get("txHash") or result.get("signature")
                    buyer = result.get("payer") or result.get("from")
                    
                    # Record transaction
                    self._record_transaction(service_id, endpoint, price, 
                                            "x402", tx_hash, buyer)
                    
                    return PaymentResult(True, "x402", price, tx_hash, buyer, "settled")
                
                return PaymentResult(False, "x402", 0, None, None, 
                                    result.get("error", "Invalid payment"))
            
            return PaymentResult(False, "x402", 0, None, None,
                               f"Facilitator error: {verify_response.status_code}")
            
        except Exception as e:
            logger.error(f"x402 verification error: {e}")
            return PaymentResult(False, "x402", 0, None, None, str(e))
    
    def verify_token_gating(self, service_id: str, wallet_address: str,
                            signature: str = None) -> PaymentResult:
        """Verify token holder status"""
        service = self.get_service(service_id)
        if not service:
            return PaymentResult(False, "token_gating", 0, None, None, "Unknown service")
        
        token_config = service.get('token_gating', {})
        if not token_config.get('enabled'):
            return PaymentResult(False, "token_gating", 0, None, None, "Token gating disabled")
        
        try:
            from token_gating import check_token_balance
            
            balance = check_token_balance(wallet_address, token_config['mint'])
            
            if balance >= token_config['min_balance']:
                # Record as free transaction
                self._record_transaction(service_id, "token_gating", 0,
                                        "token_gating", None, wallet_address)
                
                return PaymentResult(True, "token_gating", 0, None, wallet_address,
                                    f"Token holder: {balance} tokens")
            
            return PaymentResult(False, "token_gating", 0, None, wallet_address,
                               f"Insufficient balance: {balance} < {token_config['min_balance']}")
            
        except Exception as e:
            logger.error(f"Token gating error: {e}")
            return PaymentResult(False, "token_gating", 0, None, None, str(e))
    
    def _record_transaction(self, service_id: str, endpoint: str, price: float,
                           method: str, tx_hash: str, buyer_id: str):
        """Record transaction to market intelligence"""
        try:
            from market_intelligence import MarketIntelligence
            
            mi = MarketIntelligence(service_id)
            service_type = self._endpoint_to_service_type(service_id, endpoint)
            
            mi.record_transaction(
                service_type=service_type,
                seller_id=service_id,
                buyer_id=buyer_id or "unknown",
                price=price,
                currency="USDC",
                tx_hash=tx_hash,
                source=method,
                metadata={"endpoint": endpoint}
            )
            
            logger.info(f"Recorded transaction: {service_id} | {endpoint} | ${price} | {method}")
            
        except Exception as e:
            logger.error(f"Failed to record transaction: {e}")


# Singleton instance
_payment_service = None

def get_payment_service() -> PaymentService:
    global _payment_service
    if _payment_service is None:
        _payment_service = PaymentService()
    return _payment_service


if __name__ == "__main__":
    # Test
    ps = PaymentService()
    
    print("\n=== Payment Service Test ===\n")
    
    # Test get price
    price = ps.get_endpoint_price("oracle_sentinel", "/api/v1/signal", use_dynamic=False)
    print(f"Static price for /api/v1/signal: ${price}")
    
    # Test payment requirements
    req = ps.create_payment_requirements("oracle_sentinel", "/api/v1/signal")
    print(f"\nPayment Requirements:")
    print(f"  Price: ${req.price}")
    print(f"  Methods: {len(req.payment_methods)}")
    for m in req.payment_methods:
        print(f"    - {m['type']}")
