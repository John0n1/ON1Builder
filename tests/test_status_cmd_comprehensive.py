from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import typer

from on1builder.cli import status_cmd


@pytest.fixture
def stub_settings(monkeypatch):
    settings = SimpleNamespace(
        api={
            "etherscan_api_key": "ekey",
            "coingecko_api_key": "gkey",
            "coinmarketcap_api_key": None,
            "infura_project_id": "infura",
        },
        notifications={"channels": ["slack"], "min_level": "WARNING"},
        database={"url": "sqlite:///db.sqlite"},
        chains=[1, 2],
        wallet_addresses={1: "0x1", 2: "0x2"},
        wallet_address="0x0",
        websocket_urls={1: "wss://one"},
        flashloan_enabled=True,
        ml_enabled=True,
        dynamic_profit_scaling=True,
        dynamic_gas_pricing=False,
        debug=True,
        min_profit_eth=0.01,
        min_profit_percentage=0.2,
        balance_risk_ratio=0.3,
        slippage_tolerance=0.5,
        max_gas_price_gwei=100,
        ml_learning_rate=0.01,
        ml_exploration_rate=0.1,
        ml_update_frequency=5,
        emergency_balance_threshold=0.01,
        low_balance_threshold=0.05,
        high_balance_threshold=1.0,
        flashloan_max_amount_eth=100,
        flashloan_min_profit_multiplier=2.0,
    )
    monkeypatch.setattr(status_cmd, "settings", settings)
    return settings


@pytest.mark.asyncio
async def test_check_comprehensive_status_builds_rows(monkeypatch, stub_settings):
    printed = []
    monkeypatch.setattr(status_cmd.console, "print", lambda obj: printed.append(obj))

    class DummyProgress:
        def __init__(self, *args, **kwargs):
            self.updated = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def add_task(self, *args, **kwargs):
            return 1

        def update(self, task, description=None):
            self.updated.append(description)

    monkeypatch.setattr(status_cmd, "Progress", DummyProgress)

    db = MagicMock()
    db.initialize_db = AsyncMock()
    db.get_recent_transactions = AsyncMock(return_value=[1, 2, 3])
    db.close = AsyncMock()
    monkeypatch.setattr(status_cmd, "DatabaseInterface", lambda: db)

    web3 = MagicMock()
    web3.eth.block_number = AsyncMock(return_value=12345)
    monkeypatch.setattr(
        status_cmd.Web3ConnectionFactory,
        "create_connection",
        AsyncMock(return_value=web3),
    )

    balance_manager = MagicMock()
    balance_manager.get_balance_summary = AsyncMock(
        return_value={
            "balance": 1.23,
            "balance_tier": "normal",
            "max_investment": 0.5,
            "profit_threshold": 0.1,
            "flashloan_recommended": True,
            "emergency_mode": False,
        }
    )
    monkeypatch.setattr(
        status_cmd, "BalanceManager", lambda *_args, **_kwargs: balance_manager
    )

    api_manager = MagicMock()
    api_manager.get_cache_stats.return_value = {
        "failed_tokens_count": 2,
        "provider_backoff": {"one": 1},
    }
    monkeypatch.setattr(status_cmd, "ExternalAPIManager", lambda: api_manager)
    monkeypatch.setattr(status_cmd, "_show_balance_analysis", AsyncMock())
    monkeypatch.setattr(status_cmd, "_show_strategy_configuration", AsyncMock())

    await status_cmd.check_comprehensive_status()

    assert printed
    status_cmd._show_balance_analysis.assert_awaited_once()
    status_cmd._show_strategy_configuration.assert_awaited_once()
    db.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_show_balance_analysis_and_strategy_configuration(
    monkeypatch, stub_settings
):
    printed = []
    monkeypatch.setattr(status_cmd.console, "print", lambda obj: printed.append(obj))
    web3 = MagicMock()
    monkeypatch.setattr(
        status_cmd.Web3ConnectionFactory,
        "create_connection",
        AsyncMock(return_value=web3),
    )
    balance_manager = MagicMock()
    balance_manager.get_balance_summary = AsyncMock(
        side_effect=[
            {"balance": 1.0, "balance_tier": "normal"},
            RuntimeError("offline"),
        ]
    )
    monkeypatch.setattr(
        status_cmd, "BalanceManager", lambda *_args, **_kwargs: balance_manager
    )

    await status_cmd._show_balance_analysis()
    await status_cmd._show_strategy_configuration()

    assert len(printed) >= 2


def test_status_balance_and_performance_commands(monkeypatch, stub_settings):
    printed = []
    monkeypatch.setattr(status_cmd.console, "print", lambda obj: printed.append(obj))
    monkeypatch.setattr(status_cmd.asyncio, "run", lambda coro: coro.close())

    status_cmd.status_command()
    status_cmd.balance_command()
    status_cmd.performance_command()
    assert printed

    def broken_run(coro):
        coro.close()
        raise RuntimeError("bad")

    monkeypatch.setattr(status_cmd.asyncio, "run", broken_run)
    with pytest.raises(typer.Exit):
        status_cmd.status_command()
    with pytest.raises(typer.Exit):
        status_cmd.balance_command()
    with pytest.raises(typer.Exit):
        status_cmd.performance_command()


def test_helper_accessors_support_mapping_and_object_shapes(stub_settings):
    assert status_cmd._api_value("etherscan_api_key") == "ekey"
    assert status_cmd._notifications_value("min_level") == "WARNING"
    assert status_cmd._database_value("url") == "sqlite:///db.sqlite"

    status_cmd.settings.api = SimpleNamespace(etherscan_api_key="x")
    status_cmd.settings.notifications = SimpleNamespace(min_level="INFO")
    status_cmd.settings.database = SimpleNamespace(url="sqlite:///other")
    assert status_cmd._api_value("etherscan_api_key") == "x"
    assert status_cmd._notifications_value("min_level") == "INFO"
    assert status_cmd._database_value("url") == "sqlite:///other"
