from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from on1builder.core import transaction_manager as tm_module
from on1builder.core.transaction_manager import TransactionManager
from on1builder.utils.custom_exceptions import (
    InitializationError,
    TransactionError,
)


class AwaitableValue:
    def __init__(self, value=None, exc=None):
        self.value = value
        self.exc = exc

    def __await__(self):
        async def _coro():
            if self.exc:
                raise self.exc
            return self.value

        return _coro().__await__()


class Resp:
    def __init__(self, data, status=200):
        self.data = data
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return self.data


class Session:
    def __init__(self, responses):
        self.responses = list(responses)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def post(self, *args, **kwargs):
        return self.responses.pop(0)


@pytest.fixture
def stub_settings(monkeypatch, tmp_path):
    settings = SimpleNamespace(
        dynamic_gas_pricing=False,
        max_gas_price_gwei=200,
        default_gas_limit=500000,
        allow_insufficient_funds_tests=False,
        transaction_retry_count=2,
        transaction_retry_delay=0,
        submission_mode="public",
        private_rpc_url="https://private",
        simulation_backend="eth_call",
        slippage_tolerance=0.5,
        allow_unsimulated_trades=False,
        contracts=SimpleNamespace(
            uniswap_router={"1": "0xrouter"}, uniswap_addresses={}, uniswap={}
        ),
    )
    monkeypatch.setattr(tm_module, "settings", settings)
    return settings


def build_manager(base_path: Path | None = None):
    tm = TransactionManager.__new__(TransactionManager)
    tm._web3 = MagicMock()
    tm._web3.eth = SimpleNamespace(
        chain_id=AwaitableValue(1),
        gas_price=AwaitableValue(10**9),
        estimate_gas=AsyncMock(return_value=21000),
        send_raw_transaction=AsyncMock(
            return_value=SimpleNamespace(hex=lambda: "0xtx")
        ),
        get_transaction_receipt=AsyncMock(return_value={"status": 1}),
        get_transaction=AsyncMock(return_value={}),
        call=AsyncMock(),
        block_number=AwaitableValue(10),
        contract=lambda **kwargs: MagicMock(),
    )
    tm._web3.to_checksum_address = lambda address: address.upper()
    tm._web3.to_wei = lambda value, unit: int(
        Decimal(str(value)) * (10**9 if unit == "gwei" else 10**18)
    )
    tm._web3.from_wei = lambda value, unit: Decimal(value) / Decimal(10**18)
    tm._address = "0xabc"  # type: ignore[assignment]
    tm._chain_id = 1
    tm._account = SimpleNamespace(  # type: ignore[assignment]
        sign_transaction=lambda params: SimpleNamespace(
            rawTransaction=b"raw", hash=SimpleNamespace(hex=lambda: "0xhash")
        )
    )
    tm._nonce_manager = SimpleNamespace(  # type: ignore[assignment]
        get_next_nonce=AsyncMock(return_value=1), resync_nonce=AsyncMock()
    )
    tm._balance_manager = SimpleNamespace(  # type: ignore[assignment]
        update_balance=AsyncMock(return_value=Decimal("2")),
        calculate_optimal_gas_price=AsyncMock(return_value=(50, True)),
        record_profit=AsyncMock(),
    )
    tm._safety_guard = SimpleNamespace(  # type: ignore[assignment]
        check_transaction=AsyncMock(return_value=(True, "ok"))
    )
    tm._db_interface = SimpleNamespace(  # type: ignore[assignment]
        save_transaction=AsyncMock(), save_profit_record=AsyncMock()
    )
    tm._notification_service = SimpleNamespace(send_alert=AsyncMock())  # type: ignore[assignment]
    tm._gas_optimizer = SimpleNamespace(initialize=AsyncMock())  # type: ignore[assignment]
    tm._abi_registry = SimpleNamespace(  # type: ignore[assignment]
        get_abi=lambda name: [{"name": name}],
        get_token_address=lambda symbol, chain_id: "0xtoken",
        _abis={"erc20_abi": []},
    )
    tm._profit_calculator = SimpleNamespace(  # type: ignore[assignment]
        calculate_transaction_profit=AsyncMock(return_value={"profit": 1})
    )
    tm._execution_stats = {
        "total_transactions": 0,
        "successful_transactions": 0,
        "total_profit_eth": 0.0,
        "total_gas_spent_eth": 0.0,
    }
    tm._private_rpc_url = "https://private"
    tm._tenderly_account = "acct"
    tm._tenderly_project = "proj"
    tm._tenderly_token = "token"
    tm._tenderly_base_url = "https://tenderly"
    tm._bundle_relay_url = "https://relay"
    tm._bundle_relay_auth = "auth"
    tm._bundle_target_block_offset = 1
    tm._bundle_timeout_seconds = 30
    tm._bundle_signer_key = None
    tm._bundle_signer_key_path = (base_path or Path(".")) / "bundle.key"
    tm._bundle_signer_account = None
    return tm


@pytest.mark.asyncio
async def test_initialize_build_transaction_and_wait_for_receipt(
    monkeypatch, stub_settings, tmp_path
):
    tm = build_manager(tmp_path)
    await tm.initialize()
    tm._gas_optimizer.initialize.assert_awaited_once()

    tm._web3.eth.chain_id = AwaitableValue(2)
    with pytest.raises(InitializationError):
        await tm.initialize()
    tm._web3.eth.chain_id = AwaitableValue(1)

    tx = await tm._build_transaction("0xdef", value=1)
    assert tx["to"] == "0XDEF"
    assert tx["gas"] > 0

    tm._web3.eth.get_transaction_receipt = AsyncMock(return_value={"status": 1})
    assert (await tm.wait_for_receipt("0xtx", timeout=5))["status"] == 1


@pytest.mark.asyncio
async def test_sign_and_send_modes_and_retry_paths(
    monkeypatch, stub_settings, tmp_path
):
    tm = build_manager(tmp_path)
    tx_params = {
        "nonce": 1,
        "gas": 21000,
        "gasPrice": 10**9,
        "value": 0,
        "to": "0xdef",
        "chainId": 1,
    }
    assert await tm._sign_and_send(dict(tx_params)) == "0xtx"

    stub_settings.submission_mode = "private"
    tm._send_private_transaction = AsyncMock(return_value="0xprivate")
    assert await tm._sign_and_send(dict(tx_params)) == "0xprivate"

    stub_settings.submission_mode = "bundle"
    tm._send_bundle = AsyncMock(return_value="0xbundle")
    assert await tm._sign_and_send(dict(tx_params)) == "0xhash"

    stub_settings.submission_mode = "unknown"
    with pytest.raises(TransactionError):
        await tm._sign_and_send(dict(tx_params))

    stub_settings.submission_mode = "public"
    tm._web3.eth.send_raw_transaction = AsyncMock(
        side_effect=[
            RuntimeError("nonce too low"),
            RuntimeError("replacement transaction underpriced"),
            SimpleNamespace(hex=lambda: "0xok"),
        ]
    )
    stub_settings.transaction_retry_count = 3
    assert await tm._sign_and_send(dict(tx_params)) == "0xok"
    assert tm._nonce_manager.resync_nonce.await_count == 1


@pytest.mark.asyncio
async def test_private_bundle_signer_and_simulation_helpers(
    monkeypatch, stub_settings, tmp_path
):
    tm = build_manager(tmp_path)
    sessions = iter(
        [
            Session([Resp({"error": {"message": "nope"}}, 400)]),
            Session([Resp({"result": "0xraw"})]),
        ]
    )
    monkeypatch.setattr(tm_module.aiohttp, "ClientSession", lambda: next(sessions))
    assert await tm._send_private_transaction(b"raw") == "0xraw"

    monkeypatch.setattr(
        tm_module.aiohttp,
        "ClientSession",
        lambda: Session([Resp({"result": {"bundleHash": "0xbh"}})]),
    )
    original_getter = TransactionManager._get_bundle_signer_account
    monkeypatch.setattr(
        TransactionManager,
        "_get_bundle_signer_account",
        lambda self: SimpleNamespace(
            address="0xsigner",
            sign_message=lambda message: SimpleNamespace(
                signature=SimpleNamespace(hex=lambda: "0xsig")
            ),
        ),
    )
    assert await tm._send_bundle([b"raw"]) == "0xbh"
    monkeypatch.setattr(
        TransactionManager, "_get_bundle_signer_account", original_getter
    )

    monkeypatch.setattr(tm_module.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(
        tm_module.Account,
        "create",
        lambda: SimpleNamespace(key=bytes.fromhex("11" * 32)),
    )
    monkeypatch.setattr(
        tm_module.Account, "from_key", lambda key: SimpleNamespace(address="0xsigner")
    )
    account = tm._get_bundle_signer_account()
    assert account.address == "0xsigner"
    assert Path(tm._bundle_signer_key_path).exists()

    await tm._simulate_transaction({"from": "0xabc", "to": "0xdef", "nonce": 1})
    stub_settings.simulation_backend = "anvil"
    monkeypatch.setattr(
        tm_module.aiohttp, "ClientSession", lambda: Session([Resp({"result": "ok"})])
    )
    await tm._simulate_transaction({"from": "0xabc", "to": "0xdef", "nonce": 1})
    stub_settings.simulation_backend = "tenderly"
    monkeypatch.setattr(
        tm_module.aiohttp,
        "ClientSession",
        lambda: Session([Resp({"simulation": True})]),
    )
    await tm._simulate_transaction({"from": "0xabc", "to": "0xdef", "nonce": 1})


@pytest.mark.asyncio
async def test_dex_path_and_swap_helpers(stub_settings, tmp_path):
    tm = build_manager(tmp_path)
    dex_contract = MagicMock()
    dex_contract.functions.getAmountsOut.return_value.call = AsyncMock(
        return_value=[1, 2]
    )
    tm._web3.eth.contract = lambda **kwargs: dex_contract
    assert await tm._get_dex_contract("uniswap") is dex_contract
    assert await tm._get_swap_path({"path": ["ETH", "0xabc"]}) == ["0xtoken", "0XABC"]
    assert await tm._calculate_amounts_with_slippage(
        {"amount_in": 1.0, "expected_amount_out": 2.0}
    ) == (10**18, int(2 * 10**18 * 0.995))
    assert await tm._quote_expected_output(dex_contract, 1, ["a", "b"]) == 2
    assert tm._get_wrapped_native_address() == "0xtoken"

    stub_settings.allow_unsimulated_trades = False
    result = await tm.execute_swap(
        {"dex": "uniswap", "path": ["ETH", "USDC"], "amount_in": 1}, "strategy"
    )
    assert result["success"] is False
