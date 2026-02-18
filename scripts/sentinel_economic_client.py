#!/usr/bin/env python3
"""
Sentinel Economic Client SDK
Use this to integrate any service with Sentinel Economic
"""

import requests
from functools import wraps
from flask import request, jsonify, Response
from typing import Optional, Dict
from dataclasses import dataclass


@dataclass
class SentinelEconomicConfig:
    base_url: str = "http://localhost:8100"
    service_id: str = "my_service"
    timeout: int = 30


class SentinelEconomicClient:
    """Client to interact with Sentinel Economic API"""
    
    def __init__(self, config: SentinelEconomicConfig = None):
        self.config = config or SentinelEconomicConfig()
        self.base_url = self.config.base_url.rstrip('/')
    
    def get_price(self, endpoint: str, use_dynamic: bool = True) -> float:
        """Get price for an endpoint"""
        try:
            resp = requests.post(
                f"{self.base_url}/api/pricing/calculate",
                json={
                    "service_id": self.config.service_id,
                    "endpoint": endpoint,
                    "use_dynamic": use_dynamic
                },
                timeout=self.config.timeout
            )
            if resp.status_code == 200:
                return resp.json().get("price", 0.01)
        except Exception as e:
            print(f"[SentinelEconomic] Price fetch error: {e}")
        return 0.01  # Default fallback
    
    def get_payment_requirements(self, endpoint: str, method: str = "GET") -> Dict:
        """Get 402 payment requirements"""
        try:
            resp = requests.post(
                f"{self.base_url}/api/payment/requirements",
                json={
                    "service_id": self.config.service_id,
                    "endpoint": endpoint,
                    "method": method
                },
                timeout=self.config.timeout
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            print(f"[SentinelEconomic] Payment requirements error: {e}")
        return {}
    
    def verify_payment(self, endpoint: str, payment_header: str) -> Dict:
        """Verify x402 payment"""
        try:
            resp = requests.post(
                f"{self.base_url}/api/payment/verify",
                json={
                    "service_id": self.config.service_id,
                    "endpoint": endpoint,
                    "payment": payment_header
                },
                timeout=self.config.timeout
            )
            return resp.json()
        except Exception as e:
            print(f"[SentinelEconomic] Payment verify error: {e}")
        return {"success": False, "message": str(e)}
    
    def verify_token_holder(self, wallet_address: str) -> Dict:
        """Verify token holder for free access"""
        try:
            resp = requests.post(
                f"{self.base_url}/api/payment/verify-token",
                json={
                    "service_id": self.config.service_id,
                    "wallet_address": wallet_address
                },
                timeout=self.config.timeout
            )
            return resp.json()
        except Exception as e:
            print(f"[SentinelEconomic] Token verify error: {e}")
        return {"success": False, "message": str(e)}
    
    def record_transaction(self, service_type: str, buyer_id: str, 
                          price: float, tx_hash: str = None) -> bool:
        """Manually record a transaction"""
        try:
            resp = requests.post(
                f"{self.base_url}/api/market/transaction",
                json={
                    "service_type": service_type,
                    "seller_id": self.config.service_id,
                    "buyer_id": buyer_id,
                    "price": price,
                    "tx_hash": tx_hash,
                    "source": "sdk"
                },
                timeout=self.config.timeout
            )
            return resp.status_code == 200
        except Exception as e:
            print(f"[SentinelEconomic] Record transaction error: {e}")
        return False
    
    def start_negotiation(self, endpoint: str, buyer_id: str, 
                         offered_price: float, quantity: int = 1) -> Dict:
        """Start price negotiation"""
        try:
            resp = requests.post(
                f"{self.base_url}/api/negotiate/start",
                json={
                    "service_id": self.config.service_id,
                    "endpoint": endpoint,
                    "buyer_id": buyer_id,
                    "offered_price": offered_price,
                    "quantity": quantity
                },
                timeout=self.config.timeout
            )
            return resp.json()
        except Exception as e:
            print(f"[SentinelEconomic] Negotiation error: {e}")
        return {"status": "error", "message": str(e)}


def sentinel_economic_protected(service_id: str, 
                                 economic_url: str = "http://localhost:8100"):
    """
    Decorator to protect Flask endpoints with Sentinel Economic
    
    Usage:
        @app.route("/api/v1/signal/<slug>")
        @sentinel_economic_protected("oracle_sentinel")
        def get_signal(slug):
            return jsonify({"signal": "BUY_YES"})
    """
    
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            client = SentinelEconomicClient(SentinelEconomicConfig(
                base_url=economic_url,
                service_id=service_id
            ))
            
            endpoint = request.path
            method = request.method
            
            # Check 1: Token holder (FREE access)
            wallet = request.headers.get('X-Wallet-Address')
            if wallet:
                token_result = client.verify_token_holder(wallet)
                if token_result.get("success"):
                    response = f(*args, **kwargs)
                    if isinstance(response, Response):
                        response.headers['X-Access-Method'] = 'token_holder'
                    return response
            
            # Check 2: x402 Payment
            payment_header = request.headers.get('X-Payment') or request.headers.get('X-PAYMENT')
            if payment_header:
                verify_result = client.verify_payment(endpoint, payment_header)
                if verify_result.get("success"):
                    response = f(*args, **kwargs)
                    if isinstance(response, Response):
                        response.headers['X-Access-Method'] = 'x402_payment'
                        response.headers['X-Payment-Status'] = 'settled'
                    return response
                else:
                    return jsonify({
                        "error": "Payment verification failed",
                        "details": verify_result.get("message")
                    }), 402
            
            # Check 3: Negotiation token (if negotiated price)
            neg_token = request.headers.get('X-Negotiation-Token')
            if neg_token:
                # TODO: Verify negotiation was accepted and paid
                pass
            
            # No valid payment - return 402
            payment_req = client.get_payment_requirements(endpoint, method)
            
            response = jsonify({
                "error": "Payment required",
                "price": payment_req.get("price"),
                "currency": payment_req.get("currency", "USDC"),
                "payment_methods": payment_req.get("payment_methods", []),
                "negotiate_url": f"{economic_url}/api/negotiate/start",
                "expires_at": payment_req.get("expires_at")
            })
            response.status_code = 402
            response.headers['WWW-Authenticate'] = 'X402'
            return response
        
        return decorated_function
    return decorator


# ═══════════════════════════════════════════════════════════════
# EXAMPLE USAGE
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Example: How to use the client
    
    print("\n=== Sentinel Economic Client SDK Demo ===\n")
    
    # Initialize client
    client = SentinelEconomicClient(SentinelEconomicConfig(
        base_url="http://localhost:8100",
        service_id="oracle_sentinel"
    ))
    
    # Get dynamic price
    price = client.get_price("/api/v1/signal")
    print(f"1. Dynamic price for /api/v1/signal: ${price}")
    
    # Get payment requirements
    req = client.get_payment_requirements("/api/v1/signal")
    print(f"2. Payment methods: {len(req.get('payment_methods', []))}")
    
    # Start negotiation
    neg = client.start_negotiation("/api/v1/signal", "demo_buyer", 0.02)
    print(f"3. Negotiation: {neg.get('status')} - {neg.get('message')}")
    
    # Record transaction (manual)
    success = client.record_transaction("prediction_signal", "demo_buyer", 0.025, "demo_tx_123")
    print(f"4. Transaction recorded: {success}")
    
    print("\n" + "="*50)
    print("To protect your Flask endpoint, use:")
    print("="*50)
    print("""
from sentinel_economic_client import sentinel_economic_protected

@app.route("/api/v1/signal/<slug>")
@sentinel_economic_protected("your_service_id")
def get_signal(slug):
    return jsonify({"signal": "BUY_YES"})
""")
