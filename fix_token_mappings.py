#!/usr/bin/env python3
import asyncio
import json
import os
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

async def main():
    # Get paths to token files from environment
    address_to_symbol_path = os.environ.get("ADDRESS_TO_SYMBOL")
    symbol_to_address_path = os.environ.get("TOKEN_SYMBOLS")
    
    print(f"Loading address to symbol from: {address_to_symbol_path}")
    print(f"Loading symbol to address from: {symbol_to_address_path}")
    
    # Load existing mappings
    with open(address_to_symbol_path, 'r') as f:
        address_to_symbol = json.load(f)
    with open(symbol_to_address_path, 'r') as f:
        symbol_to_address = json.load(f)
        
    # Check if important tokens are present
    important_tokens = {
        "ETH": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",  # ETH pseudo-address used by some protocols
        "BTC": "0xbBbBBBBbbBBBbbbBbbBbbbbBBbBbbbbBbBbbBBbB"   # BTC pseudo-address
    }
    
    additions = 0
    
    # Add missing tokens
    for symbol, address in important_tokens.items():
        if symbol not in symbol_to_address:
            print(f"Adding missing token: {symbol} -> {address}")
            symbol_to_address[symbol] = address
            additions += 1
            
        if address.lower() not in address_to_symbol:
            print(f"Adding missing address mapping: {address} -> {symbol}")
            address_to_symbol[address.lower()] = symbol
            additions += 1
            
    if additions > 0:
        # Save the updated mappings
        with open(address_to_symbol_path, 'w') as f:
            json.dump(address_to_symbol, f, indent=2)
        with open(symbol_to_address_path, 'w') as f:
            json.dump(symbol_to_address, f, indent=2)
            
        print(f"Added {additions} missing token mappings")
    else:
        print("No missing tokens needed to be added")

if __name__ == "__main__":
    asyncio.run(main())
