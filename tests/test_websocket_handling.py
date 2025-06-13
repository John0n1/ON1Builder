#!/usr/bin/env python3
"""Test WebSocket handling improvements in TxPoolScanner."""

import asyncio
import sys
import os
sys.path.append('src')

async def test_websocket_none_handling():
    """Test that TxPoolScanner properly handles None WebSocket connections."""
    try:
        from on1builder.monitoring.txpool_scanner import TxPoolScanner
        from unittest.mock import AsyncMock, MagicMock
        
        # Create mock objects
        mock_web3 = MagicMock()
        mock_web3.eth.chain_id = 1
        
        mock_strategy_executor = MagicMock()
        
        # Create TxPoolScanner
        scanner = TxPoolScanner(mock_web3, mock_strategy_executor)
        
        # Test _handle_websocket_subscription with None websocket
        print("Testing _handle_websocket_subscription with None...")
        await scanner._handle_websocket_subscription(None)
        print("✓ _handle_websocket_subscription handled None gracefully")
        
        # Test with mock websocket that has no subscribe method
        mock_websocket = MagicMock()
        mock_websocket.subscribe = None
        print("Testing _handle_websocket_subscription with invalid websocket...")
        await scanner._handle_websocket_subscription(mock_websocket)
        print("✓ _handle_websocket_subscription handled invalid websocket gracefully")
        
        print("All WebSocket handling tests passed!")
        
    except Exception as e:
        print(f"❌ Error testing WebSocket handling: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_websocket_none_handling())
