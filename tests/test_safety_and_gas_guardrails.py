"""Logic tests for safety guard and gas optimizer intent."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from on1builder.utils.custom_exceptions import StrategyExecutionError


class DummySafetyGuard:
    def __init__(self, allow=True):
        self.allow = allow

    async def check_transaction(self, params):
        return self.allow, "blocked" if not self.allow else ""


class DummyBalanceManager:
    async def calculate_optimal_gas_price(self, expected_profit):
        # Reject if expected profit is too low relative to gas
        if expected_profit < Decimal("0.0001"):
            return 0, False
        return 10, True


class DummyWeb3:
    def __init__(self):
        self.eth = SimpleNamespace(gas_price=50 * 10**9)

    def to_wei(self, value, unit):
        return int(value * 10**9) if unit == "gwei" else value


@pytest.mark.asyncio
async def test_safety_guard_blocks_unsafe_tx(monkeypatch):
    from on1builder.core.transaction_manager import TransactionManager

    tm = TransactionManager.__new__(TransactionManager)
    tm._web3 = DummyWeb3()
    tm._chain_id = 1
    tm._address = "0xabc"
    tm._balance_manager = DummyBalanceManager()
    tm._safety_guard = DummySafetyGuard(allow=False)
    tm._account = SimpleNamespace(sign_transaction=lambda p: SimpleNamespace(rawTransaction=b"0x"))
    tm._nonce_manager = SimpleNamespace(get_next_nonce=lambda: 1, resync_nonce=lambda: None)
    tm._db_interface = SimpleNamespace()  # unused in these paths
    tm._notification_service = SimpleNamespace()

    with pytest.raises(StrategyExecutionError):
        await tm._sign_and_send({"to": "0xdef", "value": 0, "gasPrice": 1, "gas": 21000, "nonce": 1, "chainId": 1})


@pytest.mark.asyncio
async def test_gas_price_rejects_when_profit_too_low(monkeypatch):
    from on1builder.core.transaction_manager import TransactionManager

    tm = TransactionManager.__new__(TransactionManager)
    tm._web3 = DummyWeb3()
    tm._chain_id = 1
    tm._address = "0xabc"
    tm._balance_manager = DummyBalanceManager()
    tm._safety_guard = DummySafetyGuard(allow=True)
    tm._account = SimpleNamespace(sign_transaction=lambda p: SimpleNamespace(rawTransaction=b"0x"))
    tm._nonce_manager = SimpleNamespace(get_next_nonce=lambda: 1, resync_nonce=lambda: None)
    tm._db_interface = SimpleNamespace()  # unused in these paths
    tm._notification_service = SimpleNamespace()

    with pytest.raises(Exception):
        await tm._build_transaction("0xdef", value=0, data="0x", gas_limit=21000, gas_price=None)
