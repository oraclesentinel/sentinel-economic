#!/usr/bin/env python3
"""
Token Gating - Check $OSAI balance for free API access
"""

import json
import os
from solana.rpc.api import Client
from solana.rpc.types import TokenAccountOpts
from solders.pubkey import Pubkey
import time

# Simple cache for token balances (wallet -> (balance, timestamp))
_balance_cache = {}
CACHE_TTL = 60  # Cache for 60 seconds

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'x402_config.json')

def load_config() -> dict:
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

# Solana RPC
SOLANA_RPC = "https://api.mainnet-beta.solana.com"

def get_token_balance(wallet_address: str, mint_address: str) -> int:
    """
    Get SPL token balance for a wallet.
    Returns balance in human-readable units.
    Uses caching to avoid RPC rate limits.
    """
    # Check cache first
    cache_key = f"{wallet_address}:{mint_address}"
    if cache_key in _balance_cache:
        cached_balance, cached_time = _balance_cache[cache_key]
        if time.time() - cached_time < CACHE_TTL:
            return cached_balance
    
    try:
        client = Client(SOLANA_RPC)
        
        wallet_pubkey = Pubkey.from_string(wallet_address)
        mint_pubkey = Pubkey.from_string(mint_address)
        
        # Use TokenAccountOpts object instead of dict
        opts = TokenAccountOpts(mint=mint_pubkey)
        
        response = client.get_token_accounts_by_owner_json_parsed(
            wallet_pubkey,
            opts
        )
        
        if response.value and len(response.value) > 0:
            token_account = response.value[0]
            account_data = token_account.account.data
            
            # Handle different response formats
            if hasattr(account_data, 'parsed'):
                parsed = account_data.parsed
            elif isinstance(account_data, dict) and 'parsed' in account_data:
                parsed = account_data['parsed']
            else:
                print(f"[TokenGating] Unexpected data format: {type(account_data)}")
                return 0
            
            # Get token amount info
            if isinstance(parsed, dict) and 'info' in parsed:
                info = parsed['info']
                token_amount = info.get('tokenAmount', {})
                balance = int(token_amount.get('amount', 0))
                decimals = int(token_amount.get('decimals', 6))
                
                # Return human-readable balance
                human_balance = balance // (10 ** decimals)
                # Cache the result
                _balance_cache[cache_key] = (human_balance, time.time())
                return human_balance
        
        # Cache zero balance
        _balance_cache[cache_key] = (0, time.time())
        return 0
        
    except Exception as e:
        print(f"[TokenGating] Error checking balance: {e}")
        return 0


def check_osai_holder(wallet_address: str) -> dict:
    """
    Check if wallet is an $OSAI holder with sufficient balance.
    """
    config = load_config()
    
    if not config.get("token_gating", {}).get("enabled", False):
        return {
            "is_holder": False,
            "balance": 0,
            "min_required": 0,
            "tier": "free",
            "message": "Token gating disabled"
        }
    
    osai_mint = config.get("osai_mint")
    min_balance = config.get("token_gating", {}).get("min_balance", 1000)
    
    if not wallet_address:
        return {
            "is_holder": False,
            "balance": 0,
            "min_required": min_balance,
            "tier": "free",
            "message": "No wallet provided"
        }
    
    # Validate wallet address format
    try:
        Pubkey.from_string(wallet_address)
    except Exception:
        return {
            "is_holder": False,
            "balance": 0,
            "min_required": min_balance,
            "tier": "free",
            "message": "Invalid wallet address"
        }
    
    # Get balance
    balance = get_token_balance(wallet_address, osai_mint)
    
    # Determine tier
    if balance >= 100000:
        tier = "vip"
    elif balance >= 10000:
        tier = "premium"
    elif balance >= min_balance:
        tier = "holder"
    else:
        tier = "free"
    
    is_holder = balance >= min_balance
    
    return {
        "is_holder": is_holder,
        "balance": balance,
        "min_required": min_balance,
        "tier": tier,
        "message": f"Balance: {balance:,} $OSAI" if is_holder else f"Need {min_balance:,}+ $OSAI for free access"
    }


# Test function
if __name__ == "__main__":
    print("=== Token Gating Test ===")
    
    # Test with treasury wallet
    test_wallet = "LXzWaDDkSkDQSAvRfArcYwRSq2pjgrVFidGbbnWbiD9"
    
    print(f"\nChecking wallet: {test_wallet}")
    result = check_osai_holder(test_wallet)
    print(f"Result: {json.dumps(result, indent=2)}")
