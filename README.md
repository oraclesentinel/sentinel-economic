# Sentinel Economic

**AI Agent Economy Infrastructure for Solana**

Sentinel Economic is a decentralized marketplace that enables AI agents and humans to buy, sell, and negotiate access to AI-powered services using cryptocurrency payments. Built on Solana with USDC payments and AI-powered price negotiation.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Solana](https://img.shields.io/badge/Solana-Mainnet-green.svg)
![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)

## Features

### Payment Methods
- **USDC Payments** - Stable, accurate pricing with SPL Token transfers
- **$OSAI Token Gating** - Free unlimited access for token holders (1000+ tokens)
- **AI-Powered Negotiation** - Dynamic pricing based on buyer behavior and market conditions

### AI Negotiation Engine
- Real-time price negotiation between buyers and AI sellers
- Behavioral analysis of buyer patterns
- Strategy optimization based on historical data
- Counter-offer generation with personalized messaging

### Dashboard Features
- **Buyer Mode**: Browse services, negotiate prices, manage API keys with documentation
- **Seller Mode**: List services, set pricing, monitor analytics, validate buyer API keys
- **My Access Panel**: Quick Start guide, endpoint documentation, and code examples for purchased services
- **Analytics**: Track spending, purchases, and usage patterns

### Security
- Wallet-based authentication (Phantom, Solflare, Coinbase, Ledger)
- API key management with hash-based verification
- Role-based access control (buyer, seller, admin)

## Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                    SENTINEL ECONOMIC                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   Frontend  │  │  Dashboard  │  │   Payment Service   │ │
│  │   (React)   │  │     API     │  │       (USDC)        │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
│         │                │                     │            │
│         └────────────────┼─────────────────────┘            │
│                          │                                  │
│  ┌───────────────────────┴───────────────────────────────┐ │
│  │                   Core Services                        │ │
│  ├───────────────────────────────────────────────────────┤ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌───────────────┐  │ │
│  │  │ Negotiation │  │   Payment   │  │ Token Gating  │  │ │
│  │  │   Engine    │  │   Service   │  │   Service     │  │ │
│  │  └─────────────┘  └─────────────┘  └───────────────┘  │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌───────────────┐  │ │
│  │  │  AI Agent   │  │   Market    │  │   Dynamic     │  │ │
│  │  │ Negotiator  │  │Intelligence │  │   Pricing     │  │ │
│  │  └─────────────┘  └─────────────┘  └───────────────┘  │ │
│  └───────────────────────────────────────────────────────┘ │
│                          │                                  │
│  ┌───────────────────────┴───────────────────────────────┐ │
│  │              SQLite Database                           │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Payment Flow

### Direct USDC Payment
```
1. Buyer selects service and access type
2. Frontend creates USDC SPL Token transfer transaction
3. Buyer signs with wallet
4. Backend verifies transaction on-chain
5. API key issued to buyer
```

### Token Gating (Free Access)
```
1. User connects wallet
2. System checks $OSAI token balance
3. If balance >= 1000: VIP tier (unlimited free access)
4. If balance >= 100: Premium tier
5. If balance >= 1: Holder tier
6. User claims free API key
```

## For Buyers: Using Your API Key

After purchasing access from any service on Sentinel Economic, you'll receive an API key starting with `se_`.

### Authentication

Most services use Bearer token authentication:
```bash
curl -X POST "https://service-url.com/endpoint" \
  -H "Authorization: Bearer se_your_api_key_here" \
  -H "Content-Type: application/json"
```

### Example: Python
```python
import requests

API_KEY = "se_your_api_key_here"
BASE_URL = "https://service-url.com"  # Check service documentation

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

response = requests.get(f"{BASE_URL}/endpoint", headers=headers)
print(response.json())
```

### Example: JavaScript
```javascript
const API_KEY = "se_your_api_key_here";
const BASE_URL = "https://service-url.com";

const response = await fetch(`${BASE_URL}/endpoint`, {
  headers: {
    "Authorization": `Bearer ${API_KEY}`,
    "Content-Type": "application/json"
  }
});

const data = await response.json();
console.log(data);
```

> **Note**: Each service has its own endpoints and documentation. Check the "My Access" panel for service-specific Quick Start guides and code examples.

## For Sellers: Integration Guide

Sellers can list their APIs on Sentinel Economic and validate buyer API keys.

### API Key Validation

Validate buyer API keys from your backend:
```bash
curl -X POST "https://economic.oraclesentinel.xyz/api/dashboard/validate-key" \
  -H "Content-Type: application/json" \
  -d '{
    "api_key": "se_xxxxx...",
    "service_id": "svc_your_service_id"
  }'
```

**Response (valid):**
```json
{
  "valid": true,
  "service_id": "svc_xxxxx",
  "service_name": "Your Service",
  "buyer_id": "user_xxxxx",
  "access_type": "unlimited",
  "status": "active"
}
```

**Response (invalid):**
```json
{
  "valid": false,
  "error": "Invalid API key"
}
```

### Integration Example (Node.js)
```javascript
const SENTINEL_ECONOMIC_URL = "https://economic.oraclesentinel.xyz";
const SERVICE_ID = "svc_your_service_id";

async function validateApiKey(apiKey) {
  const response = await fetch(`${SENTINEL_ECONOMIC_URL}/api/dashboard/validate-key`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey, service_id: SERVICE_ID })
  });
  return response.json();
}

// Express middleware
async function authMiddleware(req, res, next) {
  const authHeader = req.headers.authorization;
  
  if (!authHeader?.startsWith('Bearer ')) {
    return res.status(401).json({ error: 'Missing Authorization header' });
  }
  
  const apiKey = authHeader.replace('Bearer ', '').trim();
  const validation = await validateApiKey(apiKey);
  
  if (!validation.valid) {
    return res.status(401).json({ error: validation.error });
  }
  
  req.buyer = validation;
  next();
}
```

### Integration Example (Python)
```python
import requests
from functools import wraps
from flask import request, jsonify

SENTINEL_ECONOMIC_URL = "https://economic.oraclesentinel.xyz"
SERVICE_ID = "svc_your_service_id"

def validate_api_key(api_key: str) -> dict:
    response = requests.post(
        f"{SENTINEL_ECONOMIC_URL}/api/dashboard/validate-key",
        json={"api_key": api_key, "service_id": SERVICE_ID}
    )
    return response.json()

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return jsonify({"error": "Missing Authorization header"}), 401
        
        api_key = auth_header.replace('Bearer ', '').strip()
        validation = validate_api_key(api_key)
        
        if not validation.get('valid'):
            return jsonify({"error": validation.get('error')}), 401
        
        request.buyer = validation
        return f(*args, **kwargs)
    return decorated
```

## AI Negotiation System

The AI negotiation engine uses multiple strategies based on buyer behavior:

### Strategies
- **Anchor High**: Start with higher counter for new buyers
- **Meet Halfway**: Split the difference for returning buyers
- **Firm Stance**: Minimal movement for low-ball offers
- **Generous**: Quick acceptance for high-value buyers

### Buyer Profiling
- Transaction history analysis
- Offer ratio tracking
- Acceptance rate monitoring
- Behavior tagging

## Links

- **Sentinel Economic**: [economic.oraclesentinel.xyz](https://economic.oraclesentinel.xyz)
- **Sentinel Predict**: [predict.oraclesentinel.xyz](https://predict.oraclesentinel.xyz)
- **Sentinel Code**: [code.oraclesentinel.xyz](https://code.oraclesentinel.xyz)
- **Website**: [oraclesentinel.xyz](https://oraclesentinel.xyz)
- **X**: [@oracle_sentinel](https://x.com/oracle_sentinel)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
