"""Intent-focused tests for MainOrchestrator health checks without full startup."""
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from on1builder.core.main_orchestrator import MainOrchestrator


class DummyWorker:
    def __init__(self, chain_id, last_heartbeat=None):
        self.chain_id = chain_id
        self.last_heartbeat = last_heartbeat or datetime.now() - timedelta(minutes=10)

    async def stop(self):
        return None


class DummyBalanceManager:
    def __init__(self, eth_balance):
        self.eth_balance = eth_balance

    async def get_balance(self, token):
        return self.eth_balance if token == "ETH" else Decimal("0")


@pytest.mark.asyncio
async def test_check_system_health_flags_unhealthy_and_low_balance(monkeypatch):
    orch = MainOrchestrator.__new__(MainOrchestrator)
    orch._workers = [DummyWorker(1)]
    orch._balance_managers = {1: DummyBalanceManager(Decimal("0.005"))}
    orch._startup_time = datetime.now()
    orch._notification_service = SimpleNamespace()
    orch._send_alert = AsyncMock()

    await orch._check_system_health()

    # Expect at least one alert (unresponsive worker or low ETH)
    assert orch._send_alert.await_count >= 1
