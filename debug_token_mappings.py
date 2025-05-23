#!/usr/bin/env python3
import asyncio
import json
import os
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from on1builder.config.config import Configuration, APIConfig

async def main():
    # Initialize configuration
    config = Configuration()
    await config.load()
    
    # Initialize API config
    api_config = APIConfig(config)
    await api_config.initialize()
    
    # Print token mapping paths
    print(f"TOKEN_ADDRESSES path: {config.TOKEN_ADDRESSES}")
    print(f"TOKEN_SYMBOLS path: {config.TOKEN_SYMBOLS}")
    print(f"ADDRESS_TO_SYMBOL path: {config.ADDRESS_TO_SYMBOL if hasattr(config, 'ADDRESS_TO_SYMBOL') else 'Not set'}")
    
    # Check if files exist
    print(f"TOKEN_ADDRESSES exists: {os.path.exists(config.TOKEN_ADDRESSES)}")
    print(f"TOKEN_SYMBOLS exists: {os.path.exists(config.TOKEN_SYMBOLS)}")
    if hasattr(config, 'ADDRESS_TO_SYMBOL'):
        print(f"ADDRESS_TO_SYMBOL exists: {os.path.exists(config.ADDRESS_TO_SYMBOL)}")
    
    # Print a sample of token mappings
    print("\nToken address to symbol mappings (sample):")
    items = list(api_config.token_address_to_symbol.items())[:5]
    for addr, sym in items:
        print(f"  {addr} -> {sym}")
    
    print("\nToken symbol to address mappings (sample):")
    items = list(api_config.token_symbol_to_address.items())[:5]
    for sym, addr in items:
        print(f"  {sym} -> {addr}")
    
    # Count of mappings
    print(f"\nTotal token_address_to_symbol mappings: {len(api_config.token_address_to_symbol)}")
    print(f"Total token_symbol_to_address mappings: {len(api_config.token_symbol_to_address)}")
    
    # Check a few common tokens
    common_tokens = ["ETH", "WETH", "BTC", "USDT", "USDC"]
    print("\nLookup common tokens:")
    for token in common_tokens:
        addr = api_config.get_token_address(token)
        print(f"  {token} -> {addr}")
    
    await api_config.close()

if __name__ == "__main__":
    asyncio.run(main())
