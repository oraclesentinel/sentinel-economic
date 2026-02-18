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
- **Buyer Mode**: Browse services, negotiate prices, manage API keys
- **Seller Mode**: List services, set pricing, monitor analytics
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

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+ (for frontend)
- SQLite3
- Solana wallet (Phantom recommended)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/sentinel-economic.git
cd sentinel-economic
```

2. **Install Python dependencies**
```bash
pip install -r requirements.txt
```

3. **Initialize the database**
```bash
python scripts/setup_database.py
```

4. **Start the API server**
```bash
python scripts/dashboard_api.py
```

The API will be available at `http://localhost:8101`

### Frontend Setup

The frontend is located in the main Oracle Sentinel dashboard. See [oracle-sentinel](https://github.com/anthropics/oracle-sentinel) for frontend setup.

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

## Using Your API Key

After purchasing access from Sentinel Economic, you'll receive an API key. Here's how to use it:

### Authentication

Include your API key in the request header:
```bash
curl -X GET "https://api.oraclesentinel.xyz/api/v1/signal" \
  -H "X-API-Key: your_api_key_here"
```

### Example: Python
```python
import requests

API_KEY = "your_api_key_here"
BASE_URL = "https://api.oraclesentinel.xyz"

headers = {
    "X-API-Key": API_KEY
}

# Get prediction signal
response = requests.get(f"{BASE_URL}/api/v1/signal", headers=headers)
data = response.json()
print(data)
```

### Example: JavaScript
```javascript
const API_KEY = "your_api_key_here";
const BASE_URL = "https://api.oraclesentinel.xyz";

const response = await fetch(`${BASE_URL}/api/v1/signal`, {
  headers: {
    "X-API-Key": API_KEY
  }
});

const data = await response.json();
console.log(data);
```

### Error Handling

| Status Code | Description |
|-------------|-------------|
| 200 | Success |
| 401 | Invalid or missing API key |
| 402 | Insufficient balance (for per-request) |
| 500 | Server error |

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

## Security Considerations

1. **Never commit sensitive data**: API keys, private keys, database files
2. **Use environment variables** for production secrets
3. **Validate all wallet addresses** before processing

## Contributing

Contributions are welcome! Please read our contributing guidelines before submitting PRs.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Links

- **Sentinel Economic**: [economic.oraclesentinel.xyz](https://economic.oraclesentinel.xyz)
- **Sentinel Predict**: [predict.oraclesentinel.xyz](https://predict.oraclesentinel.xyz)
- **Sentinel Code**: [code.oraclesentinel.xyz](https://code.oraclesentinel.xyz)
- **Website**: [oraclesentinel.xyz](https://oraclesentinel.xyz)
- **X**: [@oracle_sentinel](https://x.com/oracle_sentinel)

## Support

For support, please open an issue on GitHub or reach out on X.
