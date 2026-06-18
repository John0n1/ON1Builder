"""Logic-level tests for TransactionManager profit and safety handling."""

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pytest import approx

from on1builder.core.transaction_manager import TransactionManager
from on1builder.utils.custom_exceptions import (
    InsufficientFundsError,
    StrategyExecutionError,
    TransactionError,
)


class StubWeb3:
    def __init__(self):
        self.eth = SimpleNamespace()

    def to_checksum_address(self, addr):
        return addr

    def to_wei(self, value, unit):
        if unit == "gwei":
            return int(value) * 10**9
        if unit == "ether":
            return int(Decimal(value) * Decimal(10**18))
        return int(value)

    def from_wei(self, value, unit):
        if unit == "ether":
            return Decimal(value) / Decimal(10**18)
        return value


class StubWeb3ForBuild(StubWeb3):
    def __init__(self, gas_price, estimate_gas=None):
        super().__init__()
        future = asyncio.Future()
        future.set_result(gas_price)
        self.eth.gas_price = future
        if estimate_gas is None:
            self.eth.estimate_gas = AsyncMock(return_value=21000)
        else:
            self.eth.estimate_gas = estimate_gas


def build_manager(override_sign_send: bool = True):
    tm = TransactionManager.__new__(TransactionManager)
    tm._web3 = StubWeb3()  # type: ignore[assignment]
    tm._chain_id = 1
    tm._address = "0xabc"  # type: ignore[assignment]
    tm._balance_manager = SimpleNamespace(  # type: ignore[assignment]
        update_balance=AsyncMock(side_effect=[Decimal("1.0"), Decimal("1.3")]),
        record_profit=AsyncMock(return_value=None),
    )
    tm._safety_guard = SimpleNamespace(  # type: ignore[assignment]
        check_transaction=AsyncMock(return_value=(True, ""))
    )
    tm._account = SimpleNamespace(  # type: ignore[assignment]
        sign_transaction=lambda params: SimpleNamespace(rawTransaction=b"0x")
    )
    tm._nonce_manager = SimpleNamespace(  # type: ignore[assignment]
        get_next_nonce=AsyncMock(return_value=1), resync_nonce=AsyncMock()
    )
    tm._db_interface = SimpleNamespace(  # type: ignore[assignment]
        save_transaction=AsyncMock(return_value=None),
        save_profit_record=AsyncMock(return_value=None),
    )
    tm._notification_service = SimpleNamespace(  # type: ignore[assignment]
        send_alert=AsyncMock(return_value=None)
    )
    tm._execution_stats = {
        "total_transactions": 0,
        "successful_transactions": 0,
        "total_profit_eth": 0.0,
        "total_gas_spent_eth": 0.0,
    }
    # override network calls when desired
    if override_sign_send:
        tm._sign_and_send = AsyncMock(return_value="0xtxhash")  # type: ignore[method-assign]
    tm.wait_for_receipt = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "gasUsed": 100000,
            "effectiveGasPrice": 10 * 10**9,
            "status": 1,
            "blockNumber": 1,
        }
    )
    return tm


def test_format_raw_tx_prefixes_0x():
    tm = TransactionManager.__new__(TransactionManager)
    raw_tx = b"\xde\xad\xbe\xef"
    assert tm._format_raw_tx(raw_tx) == "0xdeadbeef"


def test_encode_uniswap_v3_path():
    tm = TransactionManager.__new__(TransactionManager)
    tokens = [
        "0x" + "11" * 20,
        "0x" + "22" * 20,
    ]
    fees = [3000]
    encoded = tm._encode_uniswap_v3_path(tokens, fees)
    assert len(encoded) == 43
    assert encoded[:20].hex() == tokens[0][2:]
    assert encoded[20:23] == (3000).to_bytes(3, "big")
    assert encoded[23:].hex() == tokens[1][2:]


@pytest.mark.asyncio
async def test_build_transaction_rejects_gas_price_over_cap(monkeypatch):
    stub_settings = SimpleNamespace(
        dynamic_gas_pricing=False,
        max_gas_price_gwei=5,
        default_gas_limit=21000,
    )
    monkeypatch.setattr("on1builder.core.transaction_manager.settings", stub_settings)

    tm = TransactionManager.__new__(TransactionManager)
    tm._web3 = StubWeb3ForBuild(gas_price=10 * 10**9)
    tm._address = "0xabc"
    tm._chain_id = 1
    tm._nonce_manager = SimpleNamespace(get_next_nonce=AsyncMock(return_value=1))
    tm._balance_manager = SimpleNamespace()

    with pytest.raises(TransactionError):
        await tm._build_transaction(to="0xdef", value=0)


@pytest.mark.asyncio
async def test_build_transaction_blocks_when_gas_unprofitable(monkeypatch):
    stub_settings = SimpleNamespace(
        dynamic_gas_pricing=True,
        max_gas_price_gwei=200,
        default_gas_limit=21000,
    )
    monkeypatch.setattr("on1builder.core.transaction_manager.settings", stub_settings)

    tm = TransactionManager.__new__(TransactionManager)
    tm._web3 = StubWeb3ForBuild(gas_price=1 * 10**9)
    tm._address = "0xabc"
    tm._chain_id = 1
    tm._nonce_manager = SimpleNamespace(get_next_nonce=AsyncMock(return_value=1))
    tm._balance_manager = SimpleNamespace(
        calculate_optimal_gas_price=AsyncMock(return_value=(100, False))
    )

    with pytest.raises(InsufficientFundsError):
        await tm._build_transaction(to="0xdef", value=0)


@pytest.mark.asyncio
async def test_build_transaction_falls_back_to_default_gas(monkeypatch):
    stub_settings = SimpleNamespace(
        dynamic_gas_pricing=False,
        max_gas_price_gwei=200,
        default_gas_limit=500000,
    )
    monkeypatch.setattr("on1builder.core.transaction_manager.settings", stub_settings)

    tm = TransactionManager.__new__(TransactionManager)
    tm._web3 = StubWeb3ForBuild(
        gas_price=1 * 10**9, estimate_gas=AsyncMock(side_effect=Exception("boom"))
    )
    tm._address = "0xabc"
    tm._chain_id = 1
    tm._nonce_manager = SimpleNamespace(get_next_nonce=AsyncMock(return_value=1))
    tm._balance_manager = SimpleNamespace()

    tx_params = await tm._build_transaction(to="0xdef", value=0)
    assert tx_params["gas"] == stub_settings.default_gas_limit


@pytest.mark.asyncio
async def test_execute_and_confirm_tracks_profit_net_of_gas():
    tm = build_manager()
    tx_params = {"to": "0xdef", "value": 0, "gasPrice": 10 * 10**9, "gas": 100000}

    result = await tm.execute_and_confirm(tx_params, "test_strategy")

    assert result["success"] is True
    # Profit should be post - pre - gas_cost (gas cost = 0.001 ETH)
    assert tm._execution_stats["total_profit_eth"] == approx(0.299, rel=1e-3)
    tm._db_interface.save_transaction.assert_awaited_once()
    tm._db_interface.save_profit_record.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_and_confirm_adds_profit_analysis_when_enabled(monkeypatch):
    tm = build_manager()
    tm._profit_calculator = SimpleNamespace(
        calculate_transaction_profit=AsyncMock(return_value={"net_profit_usd": 1.23})
    )
    monkeypatch.setattr(
        "on1builder.core.transaction_manager.settings",
        SimpleNamespace(profit_analysis_enabled=True),
    )
    tx_params = {"to": "0xdef", "value": 0, "gasPrice": 10 * 10**9, "gas": 100000}

    result = await tm.execute_and_confirm(tx_params, "test_strategy")

    assert result["profit_analysis"] == {"net_profit_usd": 1.23}
    tm._profit_calculator.calculate_transaction_profit.assert_awaited_once_with(
        "0xtxhash", "test_strategy"
    )


@pytest.mark.asyncio
async def test_execute_and_confirm_passes_expected_profit_to_send():
    tm = build_manager()
    captured = {}

    async def _capture_send(params):
        captured.update(params)
        return "0xtxhash"

    tm._sign_and_send = AsyncMock(side_effect=_capture_send)
    tx_params = {"to": "0xdef", "value": 0, "gasPrice": 10 * 10**9, "gas": 100000}

    await tm.execute_and_confirm(tx_params, "test_strategy", Decimal("0.05"))

    assert captured.get("expected_profit_eth") == 0.05


@pytest.mark.asyncio
async def test_execute_and_confirm_reports_error_recovery(monkeypatch):
    tm = build_manager()
    tm._sign_and_send = AsyncMock(side_effect=StrategyExecutionError("boom"))
    recovery = SimpleNamespace(handle_error=AsyncMock(return_value=False))
    monkeypatch.setattr(
        "on1builder.core.transaction_manager.get_error_recovery_manager",
        lambda: recovery,
    )

    result = await tm.execute_and_confirm(
        {"to": "0xdef", "value": 0, "gasPrice": 1, "gas": 21000}, "test_strategy"
    )

    assert result["success"] is False
    recovery.handle_error.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_and_confirm_retries_after_recovery(monkeypatch):
    tm = build_manager()
    tm._sign_and_send = AsyncMock(
        side_effect=[StrategyExecutionError("boom"), "0xtxhash"]
    )
    tm._balance_manager.update_balance = AsyncMock(return_value=Decimal("1.0"))
    tm.wait_for_receipt = AsyncMock(
        return_value={
            "gasUsed": 100000,
            "effectiveGasPrice": 10 * 10**9,
            "status": 1,
            "blockNumber": 1,
        }
    )
    recovery = SimpleNamespace(
        handle_error=AsyncMock(
            side_effect=lambda *_: _[1].update({"retry": True}) or True
        )
    )
    monkeypatch.setattr(
        "on1builder.core.transaction_manager.get_error_recovery_manager",
        lambda: recovery,
    )

    result = await tm.execute_and_confirm(
        {"to": "0xdef", "value": 0, "gasPrice": 1, "gas": 21000}, "test_strategy"
    )

    assert result["success"] is True
    assert tm._sign_and_send.await_count == 2


@pytest.mark.asyncio
async def test_sign_and_send_raises_when_safety_fails():
    tm = build_manager(override_sign_send=False)
    tm._safety_guard.check_transaction = AsyncMock(return_value=(False, "blocked"))
    tm._balance_manager.update_balance = AsyncMock(return_value=Decimal("1.0"))
    tx_params = {
        "to": "0xdef",
        "value": 0,
        "gasPrice": 1,
        "gas": 21000,
        "nonce": 1,
        "chainId": 1,
    }

    with pytest.raises(StrategyExecutionError):
        await tm._sign_and_send(tx_params)


@pytest.mark.asyncio
async def test_sign_and_send_bypasses_balance_checks_when_flag(monkeypatch):
    stub_settings = SimpleNamespace(
        allow_insufficient_funds_tests=True,
        transaction_retry_count=1,
        transaction_retry_delay=0,
        submission_mode="public",
        max_gas_price_gwei=200,
    )
    monkeypatch.setattr("on1builder.core.transaction_manager.settings", stub_settings)

    tm = TransactionManager.__new__(TransactionManager)
    tm._web3 = StubWeb3()
    tm._web3.eth.send_raw_transaction = AsyncMock(return_value=b"\x12")
    tm._chain_id = 1
    tm._address = "0xabc"
    tm._balance_manager = SimpleNamespace(
        update_balance=AsyncMock(return_value=Decimal("0"))
    )
    tm._safety_guard = SimpleNamespace(
        check_transaction=AsyncMock(return_value=(True, ""))
    )
    tm._account = SimpleNamespace(
        sign_transaction=lambda params: SimpleNamespace(rawTransaction=b"0x")
    )
    tm._nonce_manager = SimpleNamespace(
        get_next_nonce=AsyncMock(return_value=1), resync_nonce=AsyncMock()
    )
    tm._db_interface = SimpleNamespace()
    tm._notification_service = SimpleNamespace()

    tx_params = {
        "to": "0xdef",
        "value": 0,
        "gasPrice": 1,
        "gas": 21000,
        "nonce": 1,
        "chainId": 1,
    }

    tx_hash = await tm._sign_and_send(tx_params)

    assert tx_hash == "12"
