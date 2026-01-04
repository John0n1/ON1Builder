"""Live integration checks for ExternalAPIManager (skipped unless opted in)."""
import os
import pytest

from on1builder.integrations.external_apis import ExternalAPIManager


requires_live = pytest.mark.skipif(
    os.getenv("RUN_LIVE_API_TESTS") != "1",
    reason="Set RUN_LIVE_API_TESTS=1 to run live API integration tests.",
)


@requires_live
@pytest.mark.asyncio
async def test_live_eth_price_and_summary(monkeypatch):
    # Ensure config validation passes by providing a public RPC endpoint
    monkeypatch.setenv("RPC_URL_1", "https://ethereum-rpc.publicnode.com")

    mgr = ExternalAPIManager()
    try:
        price = await mgr.get_price("ETH")
        assert price is not None and price > 0

        summary = await mgr.get_comprehensive_market_data("ETH")
        assert summary["symbol"] == "ETH"
        assert summary["price_usd"] is not None
        # Volume and sentiment may be None if providers are unavailable, but should not raise
        assert "timestamp" in summary
    finally:
        await mgr.close()
