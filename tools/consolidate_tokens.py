#!/usr/bin/env python3
"""
Script to consolidate token data from multiple JSON files into a unified format.
"""

import json
from pathlib import Path
from typing import Dict, Any, List


def consolidate_token_data() -> None:
    """Consolidate token data from chainid-1 directory into unified format."""
    
    # Source directory
    source_dir = Path("/home/john0n1/ON1Builder-1/resources/tokens/chainid-1")
    target_dir = Path("/home/john0n1/ON1Builder-1/src/on1builder/resources/tokens")
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Load all the mapping files
    with open(source_dir / "symbol2address.json") as f:
        symbol_to_address = json.load(f)
        
    with open(source_dir / "token2symbol.json") as f:
        token_to_symbol = json.load(f)
        
    with open(source_dir / "address2token.json") as f:
        address_to_token = json.load(f)
    
    # Create unified token structure
    unified_tokens = []
    processed_symbols = set()
    
    for symbol, address in symbol_to_address.items():
        if symbol in processed_symbols:
            continue
            
        # Get the full token name
        token_name = address_to_token.get(address, symbol)
        
        token_data = {
            "symbol": symbol,
            "name": token_name,
            "addresses": {
                "1": address.lower()  # Ethereum mainnet
            },
            "decimals": 18  # Default, would need to be updated with real data
        }
        
        # Add special cases for known tokens with different decimals
        if symbol in ["USDT", "USDC"]:
            token_data["decimals"] = 6
        elif symbol in ["WBTC", "cbBTC"]:
            token_data["decimals"] = 8
            
        unified_tokens.append(token_data)
        processed_symbols.add(symbol)
    
    # Sort by symbol for consistency
    unified_tokens.sort(key=lambda x: x["symbol"])
    
    # Save the unified data
    output_file = target_dir / "all_chains_tokens.json"
    with open(output_file, 'w') as f:
        json.dump(unified_tokens, f, indent=2)
    
    print(f"Consolidated {len(unified_tokens)} tokens into {output_file}")
    print(f"Sample entry: {unified_tokens[0] if unified_tokens else 'None'}")


if __name__ == "__main__":
    consolidate_token_data()
