from __future__ import annotations

import sys
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from on1builder.utils.profit_calculator import ProfitCalculator


class Topic:
    def __init__(self, value: str):
        self._value = value

    def hex(self):
        return self._value


class TxHash:
    def __init__(self, value: str = "0xhash"):
        self._value = value

    def hex(self):
        return self._value


class Log:
    def __init__(
        self,
        *,
        topics,
        address="0xToken",
        data="0x0",
        block_number=1,
        log_index=0,
        tx_hash="0xhash",
    ):
        self.topics = topics
        self.address = address
        self.data = data
        self.blockNumber = block_number
        self.logIndex = log_index
        self.transactionHash = TxHash(tx_hash)


class Receipt(dict):
    def __getattr__(self, item):
        return self[item]


@pytest.fixture
def calculator(monkeypatch):
    web3 = MagicMock()
    web3.eth = MagicMock()
    web3.eth.get_transaction_receipt = AsyncMock()
    web3.eth.get_transaction = AsyncMock()
    web3.eth.contract = MagicMock()
    web3.eth.chain_id = AsyncMock(return_value=1)
    web3.to_checksum_address = lambda address: address.upper()
    calc = ProfitCalculator(
        web3,
        settings=SimpleNamespace(
            wallet_address="0xwallet", wallet_addresses={1: "0xwallet"}
        ),
    )
    calc._abi_registry = MagicMock()
    calc._api_manager = MagicMock()
    return calc


@pytest.mark.asyncio
async def test_calculate_transaction_profit_success_and_error(calculator):
    receipt = Receipt(logs=[1], gasUsed=21_000)
    transaction = {"gasPrice": 100}
    calculator._web3.eth.get_transaction_receipt.return_value = receipt
    calculator._web3.eth.get_transaction.return_value = transaction
    calculator._parse_token_movements = AsyncMock(return_value=[{"type": "transfer"}])
    calculator._analyze_profit_by_strategy = AsyncMock(
        return_value={"net_profit_usd": 3}
    )
    calculator._convert_eth_to_usd = AsyncMock(return_value=Decimal("2"))

    result = await calculator.calculate_transaction_profit("0xabc", "arb")
    assert result["tx_hash"] == "0xabc"
    assert result["gas_cost_eth"] > 0
    assert result["gas_cost_usd"] == 2.0
    assert result["profit_analysis"]["net_profit_usd"] == 3

    calculator._web3.eth.get_transaction_receipt.side_effect = RuntimeError("boom")
    assert "error" in await calculator.calculate_transaction_profit("0xabc", "arb")


def test_calculate_gas_cost_prefers_effective_gas_price(calculator):
    receipt = Receipt(gasUsed=10, effectiveGasPrice=50)
    tx = {"gasPrice": 100}
    assert calculator._calculate_gas_cost(receipt, tx) == Decimal(500) / Decimal(10**18)


@pytest.mark.asyncio
async def test_parse_token_movements_dispatches_known_log_types(calculator):
    transfer_log = Log(topics=[Topic(calculator._event_signatures["Transfer"])])
    swap_log = Log(topics=[Topic(calculator._event_signatures["Swap"])])
    flash_log = Log(topics=[Topic(calculator._event_signatures["FlashLoan"])])
    unknown_log = Log(topics=[Topic("0xdead")])
    calculator._parse_transfer_log = AsyncMock(return_value={"type": "transfer"})
    calculator._parse_swap_log = AsyncMock(return_value={"type": "swap"})
    calculator._parse_flash_loan_log = AsyncMock(return_value={"type": "flash_loan"})

    result = await calculator._parse_token_movements(
        [transfer_log, swap_log, flash_log, unknown_log]
    )
    assert [entry["type"] for entry in result] == ["transfer", "swap", "flash_loan"]


@pytest.mark.asyncio
async def test_parse_transfer_log_success_and_invalid_topics(calculator):
    calculator._get_token_decimals = AsyncMock(return_value=6)
    calculator._convert_token_to_usd = AsyncMock(return_value=Decimal("12.5"))
    calculator._abi_registry.get_token_symbol_by_address.return_value = "USDC"
    log = Log(
        address="0xabc",
        topics=[
            Topic(calculator._event_signatures["Transfer"]),
            Topic("0x" + "0" * 24 + "a" * 40),
            Topic("0x" + "0" * 24 + "b" * 40),
        ],
        data=hex(12_500_000),
    )

    movement = await calculator._parse_transfer_log(log)
    assert movement == {
        "type": "transfer",
        "token_address": "0xabc",
        "token_symbol": "USDC",
        "from_address": "0x" + "a" * 40,
        "to_address": "0x" + "b" * 40,
        "amount": 12.5,
        "amount_usd": 12.5,
    }
    assert await calculator._parse_transfer_log(Log(topics=[Topic("0x1")])) is None


@pytest.mark.asyncio
async def test_parse_swap_log_v2_v3_unknown_and_decode_error(calculator, monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "eth_abi",
        SimpleNamespace(
            decode_abi=lambda abi, data: (
                (1, 2, 3, 4, "0xTO") if abi[0] == "uint256" else (-1, 2, 3, 4, 5)
            )
        ),
    )

    v2_log = Log(
        topics=[Topic(calculator._event_signatures["Swap"])],
        data="0x1234",
        address="0xDex",
        tx_hash="0xv2",
    )
    v3_log = Log(
        topics=[Topic(calculator._event_signatures["SwapV3"])],
        data="0x1234",
        address="0xDex",
        tx_hash="0xv3",
    )
    assert (await calculator._parse_swap_log(v2_log))["dex_type"] == "uniswap_v2"
    assert (await calculator._parse_swap_log(v3_log))["dex_type"] == "uniswap_v3"
    assert await calculator._parse_swap_log(Log(topics=[])) is None
    assert await calculator._parse_swap_log(Log(topics=[Topic("0xdead")])) is None

    monkeypatch.setitem(
        sys.modules,
        "eth_abi",
        SimpleNamespace(
            decode_abi=lambda abi, data: (_ for _ in ()).throw(
                RuntimeError("bad decode")
            )
        ),
    )
    assert await calculator._parse_swap_log(v2_log) is None


@pytest.mark.asyncio
async def test_parse_flash_loan_log(calculator):
    log = Log(topics=[], address="0xflash", block_number=7, log_index=2)
    assert await calculator._parse_flash_loan_log(log) == {
        "type": "flash_loan",
        "protocol_address": "0xflash",
        "block_number": 7,
        "log_index": 2,
    }


@pytest.mark.asyncio
async def test_analyze_profit_by_strategy_uses_wallet_and_chain_specific_settings(
    calculator,
):
    calculator._convert_eth_to_usd = AsyncMock(return_value=Decimal("5"))
    calculator._get_strategy_specific_analysis = AsyncMock(return_value={"kind": "arb"})
    calculator._web3.eth.chain_id = AsyncMock(return_value=1)
    movements = [
        {
            "type": "transfer",
            "token_symbol": "ETH",
            "amount": 2,
            "amount_usd": 8,
            "to_address": "0xwallet",
        },
        {
            "type": "transfer",
            "token_symbol": "ETH",
            "amount": 1,
            "amount_usd": 3,
            "from_address": "0xwallet",
        },
        {"type": "swap"},
    ]

    analysis = await calculator._analyze_profit_by_strategy(
        movements, Decimal("0.1"), "arbitrage"
    )
    assert analysis["gross_profit_usd"] == 5.0
    assert analysis["net_profit_usd"] == 0.0
    assert analysis["net_token_changes"] == {"ETH": 1.0}
    assert analysis["strategy_analysis"] == {"kind": "arb"}

    calculator._get_strategy_specific_analysis = AsyncMock(
        side_effect=RuntimeError("bad strategy")
    )
    assert "error" in await calculator._analyze_profit_by_strategy(
        movements, Decimal("0.1"), "arbitrage"
    )


@pytest.mark.asyncio
async def test_strategy_specific_analysis_branches(calculator):
    net_positive = {"ETH": Decimal("1")}
    movements = [{"type": "swap"}, {"type": "flash_loan"}]
    assert (
        await calculator._get_strategy_specific_analysis(
            "arbitrage", movements, net_positive
        )
    )["arbitrage_success"] is True
    flash = await calculator._get_strategy_specific_analysis(
        "flash_loan", movements, {}
    )
    assert flash["flash_loan_detected"] is True and flash["flash_loan_count"] == 1
    mev = await calculator._get_strategy_specific_analysis(
        "sandwich", movements, net_positive
    )
    assert mev["mev_profit_extracted"] is True and mev["victim_transactions"] == 1
    assert (
        await calculator._get_strategy_specific_analysis(
            "liquidation", movements, net_positive
        )
    )["liquidation_bonus_estimated"] is True


@pytest.mark.asyncio
async def test_get_token_decimals_cache_registry_contract_and_fallback(calculator):
    calculator._token_decimals_cache["0xcached"] = 9
    assert await calculator._get_token_decimals("0xCached") == 9

    calculator._abi_registry.get_token_info_by_address.return_value = {"decimals": 6}
    assert await calculator._get_token_decimals("0xabc") == 6

    calculator._abi_registry.get_token_info_by_address.return_value = None
    contract = MagicMock()
    contract.functions.decimals.return_value.call.return_value = 8
    calculator._web3.eth.contract.return_value = contract
    assert await calculator._get_token_decimals("0xdef") == 8

    contract.functions.decimals.return_value.call.side_effect = RuntimeError("fail")
    assert await calculator._get_token_decimals("0xghi") == 18

    calculator._web3.eth.chain_id = AsyncMock(side_effect=RuntimeError("bad chain"))
    calculator._abi_registry.get_token_info_by_address.side_effect = RuntimeError(
        "bad registry"
    )
    assert await calculator._get_token_decimals("0xjkl") == 18


@pytest.mark.asyncio
async def test_convert_token_and_eth_to_usd_paths(calculator):
    calculator._get_token_price_usd = AsyncMock(
        side_effect=[2.5, 0, 0, 0, RuntimeError("bad"), 3000, 0, RuntimeError("no eth")]
    )
    assert await calculator._convert_token_to_usd(Decimal("2"), "ABC") == Decimal("5.0")
    assert await calculator._convert_token_to_usd(Decimal("2"), "ETH") == Decimal(
        "4000"
    )
    assert await calculator._convert_token_to_usd(Decimal("2"), "USDC") == Decimal("2")
    assert await calculator._convert_token_to_usd(Decimal("2"), "WBTC") == Decimal(
        "60000"
    )
    assert await calculator._convert_token_to_usd(Decimal("2"), "XYZ") == Decimal("0")
    assert await calculator._convert_eth_to_usd(Decimal("2")) == Decimal("6000")
    assert await calculator._convert_eth_to_usd(Decimal("1")) == Decimal("2000")
    assert await calculator._convert_eth_to_usd(Decimal("1")) == Decimal("0")
    assert await calculator._convert_token_to_usd(Decimal("0"), None) == Decimal("0")


@pytest.mark.asyncio
async def test_calculate_flash_loan_profit_and_summary(calculator):
    calculator.calculate_transaction_profit = AsyncMock(
        side_effect=[
            {"error": "bad"},
            {
                "token_movements": [
                    {"type": "flash_loan", "protocol_address": "0x1"},
                    {"type": "flash_loan", "protocol_address": "0x2"},
                    {"type": "transfer"},
                ]
            },
            {
                "profit_analysis": {"net_profit_usd": 5},
                "gas_cost_usd": 1,
                "strategy_type": "unknown",
            },
            {
                "profit_analysis": {"net_profit_usd": -2},
                "gas_cost_usd": 0.5,
                "strategy_type": "unknown",
            },
        ]
    )

    assert await calculator.calculate_flash_loan_profit("0x1") == {"error": "bad"}
    enriched = await calculator.calculate_flash_loan_profit("0x2")
    assert enriched["flash_loan_analysis"]["flash_loans_used"] == 2
    assert enriched["flash_loan_analysis"]["compound_strategy"] is True

    summary = await calculator.get_profit_summary(["a", "b"])
    assert summary["total_profit_usd"] == 3.0
    assert summary["total_gas_cost_usd"] == 1.5
    assert summary["successful_trades"] == 1
    assert summary["failed_trades"] == 1
    assert summary["strategy_breakdown"]["unknown"]["trade_count"] == 2


@pytest.mark.asyncio
async def test_get_profit_summary_handles_internal_errors_and_price_lookup(calculator):
    calculator.calculate_transaction_profit = AsyncMock(
        side_effect=RuntimeError("boom")
    )
    summary = await calculator.get_profit_summary(["a"])
    assert summary["failed_trades"] == 1
    assert summary["successful_trades"] == 0

    calculator._api_manager.get_price = AsyncMock(
        side_effect=[None, RuntimeError("bad api")]
    )
    assert await calculator._get_token_price_usd("ETH") == 0
    assert await calculator._get_token_price_usd("ETH") == 0
