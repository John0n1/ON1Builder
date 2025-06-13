# src/on1builder/cli/status_cmd.py
from __future__ import annotations

import asyncio
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from on1builder.config.loaders import settings
from on1builder.utils.web3_factory import Web3ConnectionFactory
from on1builder.persistence.db_interface import DatabaseInterface
from on1builder.core.balance_manager import BalanceManager

app = typer.Typer(help="Commands to check comprehensive system status and performance.")
console = Console()

async def check_comprehensive_status():
    """Enhanced async helper to perform comprehensive status checks."""
    
    # Create main status table
    table = Table(title="ON1Builder Enhanced System Status")
    table.add_column("Component", justify="right", style="cyan", no_wrap=True)
    table.add_column("Status", style="green")
    table.add_column("Details", justify="left", style="magenta")
    table.add_column("Performance", justify="right", style="yellow")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Checking system status...", total=None)
        
        # Check Database Connection
        try:
            progress.update(task, description="Checking database...")
            db = DatabaseInterface()
            await db.initialize_db()
            
            # Get some basic stats
            try:
                recent_transactions = await db.get_recent_transactions(limit=10)
                tx_count = len(recent_transactions)
            except:
                tx_count = "N/A"
            
            table.add_row(
                "Database", 
                "✅ Connected", 
                f"URL: {settings.database.url}",
                f"Recent TXs: {tx_count}"
            )
            await db.close()
        except Exception as e:
            table.add_row("Database", "❌ Failed", f"Error: {str(e)}", "N/A")

        # Check RPC and WebSocket Connections for each chain
        for chain_id in settings.chains:
            progress.update(task, description=f"Checking chain {chain_id}...")
            
            # Test RPC connection
            try:
                web3 = await Web3ConnectionFactory.create_connection(chain_id)
                latest_block = await web3.eth.block_number
                
                # Test balance check
                balance_manager = BalanceManager(web3, settings.wallet_address)
                balance_summary = await balance_manager.get_balance_summary()
                
                table.add_row(
                    f"Chain {chain_id} RPC",
                    "✅ Connected",
                    f"Block: {latest_block}",
                    f"Balance: {balance_summary['balance']:.6f} ETH"
                )
                
                # Test WebSocket if available
                ws_url = settings.websocket_urls.get(chain_id)
                if ws_url:
                    table.add_row(
                        f"Chain {chain_id} WS",
                        "🔗 Available",
                        f"URL: {ws_url}",
                        f"Tier: {balance_summary['balance_tier']}"
                    )
                
            except Exception as e:
                table.add_row(f"Chain {chain_id}", "❌ Failed", f"Error: {str(e)[:50]}...", "N/A")

        # Check API integrations
        progress.update(task, description="Checking API integrations...")
        api_statuses = []
        
        if settings.api.etherscan_api_key:
            api_statuses.append("Etherscan ✅")
        if settings.api.coingecko_api_key:
            api_statuses.append("CoinGecko ✅")
        if settings.api.coinmarketcap_api_key:
            api_statuses.append("CoinMarketCap ✅")
        if settings.api.infura_project_id:
            api_statuses.append("Infura ✅")
        
        table.add_row(
            "API Services",
            "🔧 Configured" if api_statuses else "⚠️ Limited",
            ", ".join(api_statuses) if api_statuses else "No APIs configured",
            f"{len(api_statuses)} active"
        )

        # Check notification services
        progress.update(task, description="Checking notification services...")
        notification_channels = settings.notifications.channels
        if notification_channels:
            table.add_row(
                "Notifications",
                "📢 Enabled",
                f"Channels: {', '.join(notification_channels)}",
                f"Level: {settings.notifications.min_level}"
            )
        else:
            table.add_row(
                "Notifications",
                "⚠️ Disabled",
                "No channels configured",
                "Silent mode"
            )

        # Configuration summary
        progress.update(task, description="Analyzing configuration...")
        config_summary = []
        
        if settings.flashloan_enabled:
            config_summary.append("Flashloan ✅")
        if settings.ml_enabled:
            config_summary.append("ML ✅")
        if settings.dynamic_profit_scaling:
            config_summary.append("Dynamic Profit ✅")
        if settings.dynamic_gas_pricing:
            config_summary.append("Dynamic Gas ✅")
        
        table.add_row(
            "Configuration",
            "⚙️ Active",
            ", ".join(config_summary),
            f"Debug: {'ON' if settings.debug else 'OFF'}"
        )

    console.print(table)
    
    # Additional information panels
    await _show_balance_analysis()
    await _show_strategy_configuration()

async def _show_balance_analysis():
    """Show detailed balance analysis."""
    try:
        # Get balance info for all chains
        balance_info = []
        total_balance = 0.0
        
        for chain_id in settings.chains:
            try:
                web3 = await Web3ConnectionFactory.create_connection(chain_id)
                balance_manager = BalanceManager(web3, settings.wallet_address)
                summary = await balance_manager.get_balance_summary()
                
                balance_info.append(f"Chain {chain_id}: {summary['balance']:.6f} ETH ({summary['balance_tier']})")
                total_balance += summary['balance']
                
            except Exception as e:
                balance_info.append(f"Chain {chain_id}: Error - {str(e)[:30]}...")
        
        balance_panel = Panel(
            "\n".join(balance_info) + f"\n\nTotal Portfolio: {total_balance:.6f} ETH",
            title="💰 Balance Analysis",
            style="cyan"
        )
        console.print(balance_panel)
        
    except Exception as e:
        console.print(f"[red]Failed to analyze balances: {e}[/red]")

async def _show_strategy_configuration():
    """Show strategy and ML configuration."""
    try:
        strategy_config = [
            f"Min Profit: {settings.min_profit_eth:.6f} ETH ({settings.min_profit_percentage}%)",
            f"Risk Ratio: {settings.balance_risk_ratio:.1%}",
            f"Slippage Tolerance: {settings.slippage_tolerance:.2f}%",
            f"Gas Price Limit: {settings.max_gas_price_gwei} Gwei",
            "",
            "🤖 ML Configuration:",
            f"Learning Rate: {settings.ml_learning_rate:.4f}",
            f"Exploration Rate: {settings.ml_exploration_rate:.2%}",
            f"Update Frequency: Every {settings.ml_update_frequency} transactions",
            "",
            "🎯 Balance Thresholds:",
            f"Emergency: {settings.emergency_balance_threshold:.4f} ETH",
            f"Low Balance: {settings.low_balance_threshold:.4f} ETH",
            f"High Balance: {settings.high_balance_threshold:.2f} ETH",
            "",
            "⚡ Flashloan Settings:",
            f"Enabled: {'✅' if settings.flashloan_enabled else '❌'}",
            f"Max Amount: {settings.flashloan_max_amount_eth:.0f} ETH",
            f"Min Profit Multiplier: {settings.flashloan_min_profit_multiplier:.1f}x"
        ]
        
        strategy_panel = Panel(
            "\n".join(strategy_config),
            title="🎯 Strategy & Configuration",
            style="green"
        )
        console.print(strategy_panel)
        
    except Exception as e:
        console.print(f"[red]Failed to show strategy config: {e}[/red]")

@app.command(name="check")
def status_command():
    """
    Comprehensive system status check with enhanced reporting.
    """
    console.print("[bold blue]🔍 Running comprehensive system diagnostics...[/bold blue]")
    try:
        asyncio.run(check_comprehensive_status())
    except Exception as e:
        console.print(f"[bold red]Status check failed:[/] {e}")
        raise typer.Exit(code=1)

@app.command(name="balance")
def balance_command():
    """
    Show detailed balance information across all chains.
    """
    async def show_balance_details():
        for chain_id in settings.chains:
            try:
                console.print(f"\n[bold cyan]Chain {chain_id} Balance Analysis[/bold cyan]")
                
                web3 = await Web3ConnectionFactory.create_connection(chain_id)
                balance_manager = BalanceManager(web3, settings.wallet_address)
                summary = await balance_manager.get_balance_summary()
                
                # Create detailed balance table
                balance_table = Table()
                balance_table.add_column("Metric", style="cyan")
                balance_table.add_column("Value", style="green")
                
                balance_table.add_row("Current Balance", f"{summary['balance']:.6f} ETH")
                balance_table.add_row("Balance Tier", summary['balance_tier'])
                balance_table.add_row("Max Investment", f"{summary['max_investment']:.6f} ETH")
                balance_table.add_row("Profit Threshold", f"{summary['profit_threshold']:.6f} ETH")
                balance_table.add_row("Flashloan Recommended", "✅" if summary['flashloan_recommended'] else "❌")
                balance_table.add_row("Emergency Mode", "🚨" if summary['emergency_mode'] else "✅")
                
                console.print(balance_table)
                
            except Exception as e:
                console.print(f"[red]Error checking chain {chain_id}: {e}[/red]")
    
    try:
        asyncio.run(show_balance_details())
    except Exception as e:
        console.print(f"[bold red]Balance check failed:[/] {e}")
        raise typer.Exit(code=1)

@app.command(name="performance") 
def performance_command():
    """
    Show system performance metrics and optimization suggestions.
    """
    async def show_performance():
        try:
            console.print("[bold blue]📊 Performance Analysis[/bold blue]")
            
            # This would integrate with the actual running system
            # For now, show configuration-based analysis
            
            perf_table = Table()
            perf_table.add_column("Component", style="cyan")
            perf_table.add_column("Status", style="green")
            perf_table.add_column("Optimization", style="yellow")
            
            # Analyze gas settings
            if settings.dynamic_gas_pricing:
                perf_table.add_row("Gas Pricing", "✅ Dynamic", "Optimized for market conditions")
            else:
                perf_table.add_row("Gas Pricing", "⚠️ Static", "Consider enabling dynamic pricing")
            
            # Analyze profit settings
            if settings.dynamic_profit_scaling:
                perf_table.add_row("Profit Scaling", "✅ Dynamic", "Adapts to balance tier")
            else:
                perf_table.add_row("Profit Scaling", "⚠️ Static", "Enable dynamic scaling for better performance")
            
            # Analyze ML settings
            if settings.ml_enabled:
                if settings.ml_learning_rate > 0.05:
                    perf_table.add_row("ML Learning", "⚠️ High LR", "Consider reducing learning rate")
                else:
                    perf_table.add_row("ML Learning", "✅ Optimal", "Learning rate well tuned")
            else:
                perf_table.add_row("ML Learning", "❌ Disabled", "Enable ML for better strategy selection")
            
            # Analyze flashloan settings
            if settings.flashloan_enabled:
                if settings.flashloan_min_profit_multiplier < 1.5:
                    perf_table.add_row("Flashloan Risk", "⚠️ High", "Consider higher profit multiplier")
                else:
                    perf_table.add_row("Flashloan Risk", "✅ Conservative", "Good risk management")
            
            console.print(perf_table)
            
            # Show optimization recommendations
            recommendations = [
                "💡 Optimization Recommendations:",
                "",
                "1. Enable all dynamic features for best performance",
                "2. Monitor balance tiers and adjust strategies accordingly", 
                "3. Use flashloans for capital efficiency in low-balance scenarios",
                "4. Set conservative profit thresholds in high-gas environments",
                "5. Enable comprehensive logging and notifications",
                "6. Regularly update ML weights based on performance"
            ]
            
            rec_panel = Panel(
                "\n".join(recommendations),
                title="🚀 Performance Optimization",
                style="bright_green"
            )
            console.print(rec_panel)
            
        except Exception as e:
            console.print(f"[red]Performance analysis failed: {e}[/red]")
    
    try:
        asyncio.run(show_performance())
    except Exception as e:
        console.print(f"[bold red]Performance analysis failed:[/] {e}")
        raise typer.Exit(code=1)