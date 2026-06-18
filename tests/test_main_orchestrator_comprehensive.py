from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from on1builder.core.main_orchestrator import MainOrchestrator
from on1builder.utils.custom_exceptions import InitializationError


class Worker:
    def __init__(self, chain_id):
        self.chain_id = chain_id
        self.tx_manager = SimpleNamespace(successful_trades=2, failed_trades=1)
        self.last_heartbeat = datetime.now()
        self.initialize = AsyncMock()
        self.start = AsyncMock()
        self.stop = AsyncMock()


@pytest.mark.asyncio
async def test_initialize_database_and_workers(monkeypatch):
    orch = MainOrchestrator.__new__(MainOrchestrator)
    orch._config = SimpleNamespace(chains=[1, 2], wallet_address="0xabc")
    orch._workers = []
    orch._balance_managers = {}
    orch._send_alert = AsyncMock()
    orch._db_interface = SimpleNamespace(initialize_db=AsyncMock())

    await MainOrchestrator._initialize_database(orch)
    orch._db_interface.initialize_db.assert_awaited_once()

    orch._initialize_chain_worker = AsyncMock(
        side_effect=[None, RuntimeError("bad chain")]
    )
    await MainOrchestrator._initialize_workers(orch)
    orch._send_alert.assert_awaited_once()

    orch._config = SimpleNamespace(chains=[])
    with pytest.raises(InitializationError):
        await MainOrchestrator._initialize_workers(orch)


@pytest.mark.asyncio
async def test_initialize_chain_worker_and_startup_details(monkeypatch):
    orch = MainOrchestrator.__new__(MainOrchestrator)
    orch._config = SimpleNamespace(wallet_address="0xabc", chains=[1])
    orch._workers = []
    orch._balance_managers = {}
    worker = Worker(1)
    balance_manager = MagicMock(update_balance=AsyncMock())

    monkeypatch.setattr(
        "on1builder.core.main_orchestrator.ChainWorker", lambda chain_id: worker
    )
    monkeypatch.setattr(
        "on1builder.core.main_orchestrator.create_web3_instance",
        AsyncMock(return_value="web3"),
    )
    monkeypatch.setattr(
        "on1builder.core.main_orchestrator.BalanceManager",
        lambda web3, address: balance_manager,
    )

    await MainOrchestrator._initialize_chain_worker(orch, 1)
    assert orch._workers == [worker]
    assert orch._balance_managers[1] is balance_manager

    orch._startup_time = datetime.now()
    orch._multi_chain_orchestrator = None
    assert MainOrchestrator._get_startup_details(orch)["active_chains"] == [1]


@pytest.mark.asyncio
async def test_start_services_send_alert_stop_and_shutdown(monkeypatch):
    orch = MainOrchestrator.__new__(MainOrchestrator)
    orch._workers = [Worker(1), Worker(2)]
    orch._balance_managers = {}
    orch._shutdown_event = asyncio.Event()
    orch._notification_service = SimpleNamespace(
        send_alert=AsyncMock(), close=AsyncMock()
    )
    orch._db_interface = SimpleNamespace(close=AsyncMock())
    orch._performance_monitor_task = None
    orch._performance_monitor_loop = AsyncMock()
    orch._generate_final_report = AsyncMock()
    orch._is_running = False

    class FakeTask:
        def __init__(self, coro):
            self.coro = coro
            self.cancel = MagicMock()

        def __await__(self):
            self.coro.close()
            if False:
                yield None
            return None

    monkeypatch.setattr(
        "on1builder.core.main_orchestrator.asyncio.create_task",
        lambda coro: FakeTask(coro),
    )
    monkeypatch.setattr(
        "on1builder.core.main_orchestrator.MultiChainOrchestrator",
        lambda workers: SimpleNamespace(start=AsyncMock(), stop=AsyncMock()),
    )
    monkeypatch.setattr(
        "on1builder.core.main_orchestrator.initialize_memory_optimization", AsyncMock()
    )
    monkeypatch.setattr(
        "on1builder.core.main_orchestrator.ExternalAPIManager",
        lambda: SimpleNamespace(close=AsyncMock()),
    )
    monkeypatch.setattr(
        "on1builder.core.main_orchestrator.Web3ConnectionFactory.close_all_connections",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "on1builder.core.main_orchestrator.cleanup_memory_optimization", AsyncMock()
    )

    await MainOrchestrator._start_services(orch)
    assert orch._multi_chain_orchestrator is not None

    await MainOrchestrator._send_alert(
        orch, title="hello", message="world", level="INFO", details={"x": 1}
    )
    orch._notification_service.send_alert.assert_awaited_once()

    await MainOrchestrator.stop(orch)
    assert orch._shutdown_event.is_set() is True

    orch._is_running = False
    await MainOrchestrator._shutdown(orch)
    orch._generate_final_report.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_alert_failure_and_handle_critical_error(monkeypatch):
    orch = MainOrchestrator.__new__(MainOrchestrator)
    orch._notification_service = SimpleNamespace(
        send_alert=AsyncMock(side_effect=RuntimeError("bad notify"))
    )
    orch._startup_time = datetime.now() - timedelta(seconds=10)
    orch._error_count = 0
    orch._max_consecutive_errors = 1
    orch._send_alert = AsyncMock()

    await MainOrchestrator._send_alert(orch, title="x", message="y", level="INFO")
    await MainOrchestrator._handle_critical_error(orch, RuntimeError("boom"))
    orch._send_alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_performance_report_health_and_final_report(monkeypatch):
    orch = MainOrchestrator.__new__(MainOrchestrator)
    worker = Worker(1)
    worker.last_heartbeat = datetime.now() - timedelta(minutes=10)
    orch._workers = [worker]
    balance_manager = MagicMock()
    balance_manager.update_balance = AsyncMock()
    balance_manager.get_total_profit.return_value = Decimal("2")
    balance_manager.get_balance = AsyncMock(return_value=Decimal("0.5"))
    orch._balance_managers = {1: balance_manager}
    orch._multi_chain_orchestrator = None
    orch._send_alert = AsyncMock()
    orch._startup_time = datetime.now() - timedelta(hours=2)
    orch._performance_monitor_task = None
    orch._last_profit_report = datetime.now() - timedelta(hours=2)
    orch._is_running = True

    await MainOrchestrator._generate_performance_report(orch)
    orch._send_alert.assert_awaited_once()

    orch._send_alert.reset_mock()
    await MainOrchestrator._check_system_health(orch)
    orch._send_alert.assert_awaited_once()

    orch._generate_performance_report = AsyncMock()
    await MainOrchestrator._generate_final_report(orch)
    orch._generate_performance_report.assert_awaited_once()


@pytest.mark.asyncio
async def test_performance_monitor_loop_handles_success_cancel_and_error(monkeypatch):
    orch = MainOrchestrator.__new__(MainOrchestrator)
    orch._is_running = True
    orch._last_profit_report = datetime.now() - timedelta(hours=2)
    orch._generate_performance_report = AsyncMock(
        side_effect=lambda: setattr(orch, "_is_running", False)
    )
    orch._check_system_health = AsyncMock()
    monkeypatch.setattr("on1builder.core.main_orchestrator.asyncio.sleep", AsyncMock())
    await MainOrchestrator._performance_monitor_loop(orch)
    orch._generate_performance_report.assert_awaited_once()

    orch._is_running = True
    orch._generate_performance_report = AsyncMock(side_effect=RuntimeError("bad loop"))
    orch._check_system_health = AsyncMock()

    async def stop_after_error(_seconds):
        orch._is_running = False

    monkeypatch.setattr(
        "on1builder.core.main_orchestrator.asyncio.sleep", stop_after_error
    )
    await MainOrchestrator._performance_monitor_loop(orch)
