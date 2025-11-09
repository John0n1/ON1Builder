from types import SimpleNamespace

import pytest

from on1builder.config.settings import DatabaseSettings
from on1builder.persistence import db_interface as db_module
from on1builder.persistence.db_interface import DatabaseInterface


@pytest.mark.asyncio
async def test_database_interface_roundtrip(monkeypatch, tmp_path):
    DatabaseInterface.reset_instance()

    db_path = tmp_path / "test.db"
    stub_settings = SimpleNamespace(
        database=DatabaseSettings(url=f"sqlite+aiosqlite:///{db_path}"),
        debug=False,
    )

    monkeypatch.setattr(db_module, "settings", stub_settings)

    interface = DatabaseInterface()
    await interface.initialize_db()

    tx_hash = "0x" + "1" * 64
    tx_payload = {
        "tx_hash": tx_hash,
        "chain_id": 1,
        "from_address": "0x" + "2" * 40,
        "to_address": "0x" + "3" * 40,
        "value": 123456789,
        "gas_used": 21000,
        "gas_price": 1000000000,
        "gas_cost_eth": 0.000021,
        "status": True,
        "strategy": "arbitrage",
    }

    saved_tx = await interface.save_transaction(tx_payload)
    assert saved_tx is not None

    fetched = await interface.get_transaction_by_hash(tx_hash)
    assert fetched is not None
    assert fetched.tx_hash == tx_hash

    recent = await interface.get_recent_transactions(chain_id=1, limit=5)
    assert recent and recent[0].tx_hash == tx_hash

    profit_payload = {
        "tx_hash": tx_hash,
        "chain_id": 1,
        "profit_amount_eth": 0.5,
        "profit_amount_usd": 1000.0,
        "gas_cost_eth": 0.1,
        "net_profit_eth": 0.4,
        "roi_percentage": 10.0,
        "strategy": "arbitrage",
    }

    saved_profit = await interface.save_profit_record(profit_payload)
    assert saved_profit is not None

    summary = await interface.get_profit_summary()
    assert summary["trade_count"] >= 1
    assert summary["total_profit_eth"] >= 0.5

    await interface.close()
    DatabaseInterface.reset_instance()
