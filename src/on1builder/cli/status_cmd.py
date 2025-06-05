"""
Status command for ON1Builder CLI.
"""

from typing import Optional

import typer

from ..config.loaders import load_configuration
from ..persistence.db_interface import DatabaseInterface
from ..utils.logging_config import get_logger

logger = get_logger(__name__)

# Remove the app wrapper - this will be imported as a direct command
def status_command(
    config: Optional[str] = typer.Option(
        None, "--config", "-c", help="Configuration file path"
    ),
    chain: Optional[str] = typer.Option(
        None, "--chain", help="Chain to check status for"
    ),
):
    """Check the status of ON1Builder components."""
    logger.info(f"Checking status with config: {config}, chain: {chain}")

    try:
        # Load configuration using the proper loader
        from ..config.loaders import get_config_loader
        
        loader = get_config_loader()
        if config:
            config_obj = loader.load_global_config(config)
        else:
            config_obj = loader.load_global_config()

        typer.echo("=== ON1Builder Status ===")

        # Check database connectivity
        try:
            db = DatabaseInterface(config_obj)
            is_connected = db.check_connection()
            if is_connected:
                typer.echo("✓ Database: Connected")
            else:
                typer.echo("✗ Database: Not connected")
        except Exception as e:
            typer.echo(f"✗ Database: Failed ({e})")

        # Check RPC endpoints from chain configs if available
        chains_found = False
        if chain:
            try:
                chain_config = loader.load_chain_config(chain)
                rpc_url = chain_config.http_endpoint
                chains_found = True
            except Exception:
                rpc_url = None
        else:
            # Try to load default chain configs
            try:
                multi_config = loader.load_multi_chain_config()
                if multi_config.chains:
                    first_chain = next(iter(multi_config.chains.values()))
                    rpc_url = first_chain.http_endpoint
                    chains_found = True
                else:
                    rpc_url = None
            except Exception:
                rpc_url = None
        
        if rpc_url:
            try:
                # Test the RPC connection
                import asyncio
                from web3 import AsyncWeb3, AsyncHTTPProvider
                
                web3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))
                
                # Run the connection test in an async context
                async def test_connection():
                    try:
                        connected = await web3.is_connected()
                        if connected:
                            # Try to get the latest block number as a deeper test
                            block_number = await web3.eth.block_number
                            return True, block_number
                        return False, None
                    except Exception as e:
                        return False, str(e)
                
                connected, result = asyncio.run(test_connection())
                if connected:
                    typer.echo(f"✓ RPC URL: {rpc_url} (Block: {result})")
                else:
                    typer.echo(f"✗ RPC URL: {rpc_url} (Connection failed: {result})")
                    
            except Exception as e:
                typer.echo(f"✗ RPC URL: {rpc_url} (Test failed: {e})")
        else:
            typer.echo("✗ RPC URL: Not configured")

        # Show chain info
        if chains_found:
            if chain:
                try:
                    chain_config = loader.load_chain_config(chain)
                    typer.echo(f"✓ Chain ID: {chain_config.chain_id} ({chain_config.name})")
                except Exception:
                    typer.echo("✗ Chain ID: Failed to load chain config")
            else:
                try:
                    multi_config = loader.load_multi_chain_config()
                    chain_count = len(multi_config.chains)
                    typer.echo(f"✓ Chains configured: {chain_count}")
                except Exception:
                    typer.echo("✗ Chain ID: Not configured")

        typer.echo("Status check completed")

    except Exception as e:
        logger.error(f"Failed to check status: {e}")
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
