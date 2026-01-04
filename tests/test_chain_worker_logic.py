"""Logic-focused tests for ChainWorker status without starting network tasks."""
import pytest

from on1builder.core.chain_worker import ChainWorker


@pytest.mark.asyncio
async def test_status_stopped_without_init():
    worker = ChainWorker.__new__(ChainWorker)
    worker.chain_id = 1
    worker.is_running = False
    status = await worker.get_status()
    assert status["status"] == "stopped"
    assert status["chain_id"] == 1


@pytest.mark.asyncio
async def test_status_running_reports_components(monkeypatch):
    worker = ChainWorker.__new__(ChainWorker)
    worker.chain_id = 1
    worker.is_running = True
    worker._performance_stats = {"uptime_seconds": 5}
    worker.tx_scanner = type("TS", (), {"get_pending_tx_count": lambda self: 2})()
    async def bm_summary():
        return {"balance": 1.0, "balance_tier": "medium"}

    async def tx_stats():
        return {
            "total_transactions": 1,
            "successful_transactions": 1,
            "total_profit_eth": 0.1,
            "total_gas_spent_eth": 0.01,
            "net_profit_eth": 0.09,
            "success_rate_percentage": 100.0,
        }

    async def strat_report():
        return {
            "execution_count": 1,
            "recent_performance": 0.5,
            "ml_parameters": {},
            "strategy_performance": {},
        }

    worker.balance_manager = type("BM", (), {"get_balance_summary": lambda self: bm_summary()})()
    worker.tx_manager = type("TM", (), {"get_performance_stats": lambda self: tx_stats()})()
    worker.strategy_executor = type("SE", (), {"get_strategy_report": lambda self: strat_report()})()

    status = await worker.get_status()
    assert status["status"] == "running"
    assert status["balance_summary"]["balance"] == 1.0
    assert status["pending_transactions"] == 2
