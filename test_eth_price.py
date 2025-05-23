import asyncio
import logging
from decimal import Decimal
from on1builder.config.config import Configuration, APIConfig, setup_logging

async def test_eth_price():
    # Setup logging
    setup_logging(level=logging.DEBUG)
    logger = logging.getLogger("eth_price_test")
    
    # Initialize configuration
    config = Configuration()
    api_config = APIConfig(config)
    
    try:
        # Initialize the APIConfig
        await api_config.initialize()
        
        # Test fetching ETH price
        eth_price = await api_config.get_real_time_price("ETH", "USD")
        logger.info(f"ETH/USD Price: {eth_price}")
        
        # Test fetching ETH price from each provider
        for provider_name, provider in api_config.providers.items():
            price = await api_config._price_from_provider(provider, "ETH", "USD")
            logger.info(f"ETH/USD from {provider_name}: {price}")
        
        # Test the fallback mechanism
        fallback_price = api_config._get_fallback_price("ETH", "USD")
        logger.info(f"ETH/USD Fallback Price: {fallback_price}")
        
        # Test other common tokens
        for token in ["BTC", "USDT", "USDC", "WETH", "WBTC"]:
            price = await api_config.get_real_time_price(token, "USD")
            logger.info(f"{token}/USD Price: {price}")
        
    finally:
        # Clean up
        await api_config.close()

if __name__ == "__main__":
    asyncio.run(test_eth_price())
