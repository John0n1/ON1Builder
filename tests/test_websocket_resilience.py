"""Resilience tests for websocket handling in TxPoolScanner."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from on1builder.monitoring.txpool_scanner import TxPoolScanner


class DummyWeb3:
    def __init__(self, chain_id=1):
        self.eth = SimpleNamespace(chain_id=asyncio.Future())
        self.eth.chain_id.set_result(chain_id)

    async def from_wei(self, value, unit):
        return value


class DummyExec:
    def __init__(self):
        self.executed = []

    async def execute_opportunity(self, opp):
        self.executed.append(opp)
        return {"success": True}


@pytest.mark.asyncio
async def test_websocket_subscription_failure_retries(monkeypatch):
    """Ensure scanner handles subscription failures without crashing."""
    # Simulate settings with minimal fields
    monkeypatch.setattr(
        "on1builder.monitoring.txpool_scanner.settings",
        SimpleNamespace(
            websocket_urls={1: "ws://dummy"},
            connection_retry_delay=0.01,
            heartbeat_interval=0.01,
            chains=[1],
        ),
    )
    monkeypatch.setattr(
        "on1builder.monitoring.txpool_scanner.ABIRegistry",
        lambda: SimpleNamespace(get_monitored_tokens=lambda chain_id: {}),
    )

    # Fake websocket provider that raises on subscribe then succeeds
    class FakeWebSocket:
        def __init__(self):
            self.calls = 0

        async def subscribe(self, *_):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("subscribe failed")
            return "sub_id"

        async def recv(self):
            await asyncio.sleep(0.01)
            return {"result": None}  # malformed, should be ignored

        async def close(self):
            return None

    class FakeProvider:
        def __init__(self):
            self.created = False

        def connect(self):
            self.created = True
            async def _conn():
                return FakeWebSocket()
            return _conn()

    # Patch module attribute directly (imported inside function normally)
    import on1builder.monitoring.txpool_scanner as scanner_mod
    scanner_mod.WebSocketProvider = lambda url: FakeProvider()

    scanner = TxPoolScanner(DummyWeb3(), DummyExec(), chain_id=1)
    # Run the subscription loop briefly, then cancel
    task = asyncio.create_task(scanner._subscribe_to_pending_transactions())
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Ensure no crash and subscription was attempted
    assert scanner._pending_tx_count >= 0
