from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from on1builder.core import chain_worker as worker_module
from on1builder.core.chain_worker import ChainWorker
from on1builder.utils.custom_exceptions import InitializationError


class AwaitableValue:
    def __init__(self, value):
        self.value = value

    def __await__(self):
        async def _coro():
            return self.value

        return _coro().__await__()


@pytest.fixture
def stub_settings(monkeypatch):
    settings = SimpleNamespace(
        wallet_keys={1: "key1"},
        wallet_key="key1",
        wallet_addresses={1: "0xabc"},
        wallet_address="0xabc",
        emergency_balance_threshold=0.01,
        heartbeat_interval=1,
        startup_test_transaction=True,
        allow_insufficient_funds_tests=True,
        max_gas_price_gwei=100,
    )
    monkeypatch.setattr(worker_module, "settings", settings)
    return settings


@pytest.mark.asyncio
async def test_initialize_success_and_failure(monkeypatch, stub_settings):
    worker = ChainWorker(1)
    web3 = MagicMock()
    web3.eth.gas_price = AwaitableValue(50)
    web3.to_wei = lambda value, unit: value * 10**9
    monkeypatch.setattr(
        worker_module.Web3ConnectionFactory,
        "create_connection",
        AsyncMock(return_value=web3),
    )
    monkeypatch.setattr(
        "eth_account.Account.from_key", lambda key: SimpleNamespace(address="0xabc")
    )

    balance_manager = MagicMock(
        update_balance=AsyncMock(),
        get_balance_summary=AsyncMock(
            return_value={
                "balance": 1.0,
                "balance_tier": "normal",
                "max_investment": 0.5,
            }
        ),
    )
    tx_manager = MagicMock(initialize=AsyncMock())
    monkeypatch.setattr(
        worker_module, "BalanceManager", lambda *_args, **_kwargs: balance_manager
    )
    monkeypatch.setattr(worker_module, "MarketDataFeed", lambda web3: MagicMock())
    monkeypatch.setattr(worker_module, "SafetyGuard", lambda web3: MagicMock())
    monkeypatch.setattr(
        worker_module, "NonceManager", lambda web3, address: MagicMock()
    )
    monkeypatch.setattr(
        worker_module, "TransactionManager", lambda **kwargs: tx_manager
    )
    monkeypatch.setattr(worker_module, "StrategyExecutor", lambda **kwargs: MagicMock())
    monkeypatch.setattr(worker_module, "TxPoolScanner", lambda **kwargs: MagicMock())
    worker._memory_optimizer = MagicMock(register_cleanup_callback=MagicMock())

    await worker.initialize()
    assert worker.web3 is web3
    tx_manager.initialize.assert_awaited_once()

    monkeypatch.setattr(
        "eth_account.Account.from_key", lambda key: SimpleNamespace(address="0xdef")
    )
    with pytest.raises(InitializationError):
        await ChainWorker(1).initialize()


@pytest.mark.asyncio
async def test_start_stop_and_startup_test_transaction(monkeypatch, stub_settings):
    worker = ChainWorker.__new__(ChainWorker)
    worker.chain_id = 1
    worker.is_running = False
    worker._tasks = []
    worker.web3 = MagicMock(to_wei=lambda value, unit: value * 10**9)
    worker.web3.eth = SimpleNamespace(gas_price=AwaitableValue(200 * 10**9))
    worker.account = SimpleNamespace(address="0xabc")
    worker.market_feed = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
    worker.tx_scanner = SimpleNamespace(
        start=AsyncMock(),
        stop=AsyncMock(),
        get_cache_stats=lambda: {"tx_analysis_cache_size": 0},
    )
    worker.balance_manager = MagicMock()
    worker.tx_manager = SimpleNamespace(
        _simulate_transaction=AsyncMock(),
        execute_and_confirm=AsyncMock(return_value={"success": False}),
        get_performance_stats=AsyncMock(
            return_value={"success_rate_percentage": 100, "net_profit_eth": 1}
        ),
    )
    worker.strategy_executor = SimpleNamespace(
        get_strategy_report=AsyncMock(return_value={"strategy_performance": {}})
    )
    worker.nonce_manager = SimpleNamespace(
        get_next_nonce=AsyncMock(return_value=3), resync_nonce=AsyncMock()
    )
    worker._memory_optimizer = MagicMock(
        get_current_metrics=lambda: SimpleNamespace(process_memory_mb=10)
    )
    worker._performance_stats = {
        "uptime_seconds": 0,
        "last_heartbeat": 0,
        "opportunities_detected": 0,
        "memory_cleanups": 0,
        "balance_updates": 0,
        "error_count": 0,
        "opportunities_executed": 0,
    }
    worker._start_time = 0
    worker._generate_final_report = AsyncMock()

    class FakeTask:
        def __init__(self, coro):
            self.coro = coro

        def cancel(self):
            self.coro.close()

        def done(self):
            return False

        def __await__(self):
            self.coro.close()
            if False:
                yield None
            return None

    monkeypatch.setattr(
        worker_module.asyncio, "create_task", lambda coro: FakeTask(coro)
    )
    monkeypatch.setattr(worker_module.asyncio, "gather", AsyncMock(return_value=[]))
    await ChainWorker.start(worker)
    assert worker.is_running is True
    assert len(worker._tasks) == 6

    await ChainWorker._run_startup_test_transaction(worker)
    worker.nonce_manager.resync_nonce.assert_awaited_once()

    await ChainWorker.stop(worker)
    worker.market_feed.stop.assert_awaited_once()
    worker.tx_scanner.stop.assert_awaited_once()
    worker._generate_final_report.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_loops_cleanup_reports_and_status(monkeypatch, stub_settings):
    worker = ChainWorker.__new__(ChainWorker)
    worker.chain_id = 1
    worker.is_running = True
    worker._start_time = 0
    worker._performance_stats = {
        "uptime_seconds": 0,
        "last_heartbeat": 0,
        "opportunities_detected": 2,
        "memory_cleanups": 0,
        "balance_updates": 0,
        "error_count": 0,
        "opportunities_executed": 1,
    }
    worker.balance_manager = MagicMock(
        get_balance_summary=AsyncMock(
            side_effect=[
                {"balance": 1.0, "balance_tier": "normal", "emergency_mode": False},
                {"balance": 1.2, "balance_tier": "normal", "emergency_mode": False},
                {"balance": 1.2, "balance_tier": "normal"},
            ]
        ),
        update_balance=AsyncMock(),
        get_balance=AsyncMock(return_value=Decimal("1")),
    )
    worker.tx_manager = SimpleNamespace(
        get_performance_stats=AsyncMock(
            return_value={
                "success_rate_percentage": 99.0,
                "net_profit_eth": 1.0,
                "total_gas_spent_eth": 0.1,
                "total_transactions": 2,
                "successful_transactions": 2,
                "total_profit_eth": 1.1,
            }
        )
    )
    worker.strategy_executor = SimpleNamespace(
        get_strategy_report=AsyncMock(
            return_value={
                "strategy_performance": {},
                "execution_count": 1,
                "recent_performance": 0.5,
                "ml_parameters": {},
            }
        )
    )
    worker.tx_scanner = SimpleNamespace(
        get_pending_tx_count=lambda: 1,
        get_cache_stats=lambda: {"tx_analysis_cache_size": 600},
        _manage_cache_size=MagicMock(),
    )
    worker._memory_optimizer = MagicMock(
        get_current_metrics=lambda: SimpleNamespace(process_memory_mb=12)
    )

    async def stop_sleep(_seconds):
        worker.is_running = False

    monkeypatch.setattr(worker_module.asyncio, "sleep", stop_sleep)
    monkeypatch.setattr(
        worker_module.asyncio,
        "get_event_loop",
        lambda: SimpleNamespace(time=lambda: 10),
    )

    await ChainWorker._ON1Builder_heartbeat(worker)
    worker.is_running = True
    await ChainWorker._balance_monitoring_loop(worker)
    worker.is_running = True
    await ChainWorker._performance_reporting_loop(worker)
    ChainWorker._cleanup_worker_caches(worker)
    assert worker._performance_stats["memory_cleanups"] == 1

    worker.is_running = True
    worker.balance_manager.get_balance_summary = AsyncMock(
        return_value={"balance": 1.2, "balance_tier": "normal", "emergency_mode": False}
    )
    await ChainWorker._generate_final_report(worker)
    status = await ChainWorker.get_status(worker)
    assert status["status"] == "running"
