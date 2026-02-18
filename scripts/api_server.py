#!/usr/bin/env python3
"""
Sentinel Economic — API Server
Unified infrastructure for AI agent economy
Port: 8101
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, UTC
from flask import Flask, jsonify, request
from flask_cors import CORS
from dataclasses import asdict

from market_intelligence import MarketIntelligence
from dynamic_pricing import DynamicPricingAI
from decision_engine import EconomicDecisionEngine, JobRequest
from payment_service import get_payment_service, PaymentRequirement
from negotiation_engine_ai import get_ai_negotiation_engine as get_negotiation_engine
from dashboard_api import dashboard_api

app = Flask(__name__)
CORS(app)

# Register Dashboard Blueprint
app.register_blueprint(dashboard_api)

# Initialize services
market_intel = MarketIntelligence("sentinel_economic")
pricing = DynamicPricingAI("sentinel_economic", market_intel)
engine = EconomicDecisionEngine("sentinel_economic")
payment_service = get_payment_service()
negotiation_engine = get_negotiation_engine()


@app.route("/")
def index():
    return jsonify({
        "name": "Sentinel Economic",
        "version": "1.1.0",
        "description": "Infrastructure for AI agent economy",
        "endpoints": {
            "health": "/api/health",
            "pricing": "/api/pricing/*",
            "payment": "/api/payment/*",
            "negotiate": "/api/negotiate/*",
            "market": "/api/market/*",
            "analytics": "/api/analytics/*",
            "dashboard": "/api/dashboard/*"
        }
    })


@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "sentinel-economic",
        "version": "1.1.0",
        "time": datetime.now(UTC).isoformat()
    })


@app.route("/api/pricing/calculate", methods=["POST"])
def calc_price():
    d = request.json
    service_id = d.get("service_id", "oracle_sentinel")
    endpoint = d.get("endpoint", "/api/v1/signal")
    use_dynamic = d.get("use_dynamic", True)
    price = payment_service.get_endpoint_price(service_id, endpoint, use_dynamic)
    rec = pricing.calculate_price(
        d.get("service_type", "prediction_signal"),
        d.get("complexity", "medium"),
        d.get("urgency", "normal"),
        d.get("buyer_trust")
    )
    return jsonify({"service_id": service_id, "endpoint": endpoint, "price": price, "breakdown": asdict(rec)})


@app.route("/api/pricing/services")
def list_services():
    services = payment_service.services
    result = []
    for service_id, config in services.items():
        endpoints = []
        for ep, ep_config in config.get("endpoints", {}).items():
            endpoints.append({
                "endpoint": ep,
                "base_price": ep_config.get("price", 0.01),
                "dynamic_price": payment_service.get_endpoint_price(service_id, ep, True),
                "description": ep_config.get("description", "")
            })
        result.append({
            "service_id": service_id,
            "name": config.get("name", service_id),
            "base_url": config.get("base_url", ""),
            "endpoints": endpoints
        })
    return jsonify({"services": result})


@app.route("/api/payment/requirements", methods=["POST"])
def get_payment_requirements():
    d = request.json
    service_id = d.get("service_id", "oracle_sentinel")
    endpoint = d.get("endpoint", "/api/v1/signal")
    method = d.get("method", "GET")
    try:
        req = payment_service.create_payment_requirements(service_id, endpoint, method)
        return jsonify(asdict(req))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/payment/verify", methods=["POST"])
def verify_payment():
    d = request.json
    service_id = d.get("service_id", "oracle_sentinel")
    endpoint = d.get("endpoint", "/api/v1/signal")
    payment_header = d.get("payment")
    if not payment_header:
        return jsonify({"error": "Missing payment header"}), 400
    result = payment_service.verify_x402_payment(service_id, endpoint, payment_header)
    return jsonify(asdict(result))


@app.route("/api/payment/verify-token", methods=["POST"])
def verify_token_gating():
    d = request.json
    service_id = d.get("service_id", "oracle_sentinel")
    wallet_address = d.get("wallet_address")
    if not wallet_address:
        return jsonify({"error": "Missing wallet_address"}), 400
    result = payment_service.verify_token_gating(service_id, wallet_address)
    return jsonify(asdict(result))


@app.route("/api/negotiate/start", methods=["POST"])
def start_negotiation():
    d = request.json
    required = ["service_id", "endpoint", "buyer_id", "offered_price"]
    for field in required:
        if field not in d:
            return jsonify({"error": f"Missing required field: {field}"}), 400
    try:
        resp = negotiation_engine.start_negotiation(
            service_id=d["service_id"],
            endpoint=d["endpoint"],
            buyer_id=d["buyer_id"],
            offered_price=float(d["offered_price"]),
            quantity=int(d.get("quantity", 1))
        )
        return jsonify(asdict(resp))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/negotiate/<negotiation_id>/respond", methods=["POST"])
def respond_negotiation(negotiation_id):
    d = request.json
    action = d.get("action")
    if action not in ["accept", "counter", "reject"]:
        return jsonify({"error": "Invalid action. Use: accept, counter, reject"}), 400
    try:
        resp = negotiation_engine.respond_to_counter(
            negotiation_id=negotiation_id,
            action=action,
            new_offer=float(d["new_offer"]) if d.get("new_offer") else None
        )
        return jsonify(asdict(resp))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/negotiate/<negotiation_id>")
def get_negotiation(negotiation_id):
    neg = negotiation_engine.get_negotiation(negotiation_id)
    if not neg:
        return jsonify({"error": "Negotiation not found"}), 404
    return jsonify(neg)


@app.route("/api/market/services")
def get_services():
    return jsonify({"services": market_intel.get_all_services()})


@app.route("/api/market/rate/<service_type>")
def get_rate(service_type):
    return jsonify(asdict(market_intel.get_market_rate(service_type)))


@app.route("/api/market/transaction", methods=["POST"])
def record_tx():
    d = request.json
    required = ["service_type", "seller_id", "buyer_id", "price"]
    for field in required:
        if field not in d:
            return jsonify({"error": f"Missing: {field}"}), 400
    tx_id = market_intel.record_transaction(
        d["service_type"], d["seller_id"], d["buyer_id"],
        float(d["price"]), d.get("currency", "USDC"),
        d.get("tx_hash"), d.get("source", "api")
    )
    return jsonify({"tx_id": tx_id, "status": "recorded"})


@app.route("/api/decision/evaluate", methods=["POST"])
def evaluate():
    d = request.json
    job = JobRequest(
        d.get("job_id", "job_1"), d["service_type"], d["buyer_id"],
        float(d["offered_price"]), d.get("complexity", "medium"), d.get("urgency", "normal")
    )
    decision = engine.evaluate(job, d.get("buyer_trust", 60))
    return jsonify(asdict(decision))


@app.route("/api/decision/quick", methods=["POST"])
def quick():
    d = request.json
    return jsonify(engine.quick_evaluate(d["service_type"], float(d["offered_price"]), d.get("buyer_trust", 60)))


@app.route("/api/analytics/summary")
def analytics_summary():
    conn = market_intel._get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count, SUM(price) as volume FROM transactions")
    txn_stats = cursor.fetchone()
    cursor.execute("""
        SELECT service_type, COUNT(*) as count, SUM(price) as volume, AVG(price) as avg_price
        FROM transactions GROUP BY service_type ORDER BY volume DESC
    """)
    by_service = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM transactions ORDER BY timestamp DESC LIMIT 10")
    recent = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT status, COUNT(*) as count FROM negotiations GROUP BY status")
    neg_stats = {r["status"]: r["count"] for r in cursor.fetchall()}
    conn.close()
    return jsonify({
        "transactions": {"total": txn_stats["count"] or 0, "volume": round(txn_stats["volume"] or 0, 4)},
        "by_service": by_service, "recent_transactions": recent, "negotiations": neg_stats
    })


@app.route("/api/analytics/service/<service_id>")
def analytics_service(service_id):
    conn = market_intel._get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) as count, SUM(price) as volume, AVG(price) as avg_price,
               MIN(price) as min_price, MAX(price) as max_price
        FROM transactions WHERE seller_id = ?
    """, (service_id,))
    stats = cursor.fetchone()
    cursor.execute("""
        SELECT DATE(timestamp) as date, COUNT(*) as count, SUM(price) as volume
        FROM transactions WHERE seller_id = ?
        GROUP BY DATE(timestamp) ORDER BY date DESC LIMIT 30
    """, (service_id,))
    daily = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({
        "service_id": service_id,
        "stats": {
            "total_transactions": stats["count"] or 0,
            "total_volume": round(stats["volume"] or 0, 4),
            "avg_price": round(stats["avg_price"] or 0, 4),
            "min_price": round(stats["min_price"] or 0, 4),
            "max_price": round(stats["max_price"] or 0, 4)
        },
        "daily": daily
    })


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  SENTINEL ECONOMIC — Infrastructure API v1.1")
    print("  http://localhost:8101")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=8101, debug=False)
