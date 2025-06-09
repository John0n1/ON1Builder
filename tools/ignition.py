#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – Interactive Console Ignition
==========================================

A terminal-based interactive launcher for the ON1Builder application.
Provides menus, configuration options, and monitoring capabilities
through a user-friendly TUI (Terminal User Interface).

License: MIT
"""

from __future__ import annotations

import asyncio
import os
import random
import re
import subprocess
import sys
import threading
import time
from pathlib import Path


# Check for required packages with enhanced error handling
def check_required_packages():
    """Check for required packages and provide installation instructions."""
    required_packages = ["questionary", "rich", "typer"]
    missing_packages = []

    # Check each package individually
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)

    if missing_packages:
        print(f"Missing required packages: {', '.join(missing_packages)}")
        print("Please install them using:")
        print(f"  pip install {' '.join(missing_packages)}")
        print("  or")
        print("  pip install -e .[dev]  # for development dependencies")
        print("")
        print("Make sure you're in your virtual environment and try again.")
        sys.exit(1)


# Check for required packages
check_required_packages()

# Now import the packages (they should be available)
RICH_AVAILABLE = False
QUESTIONARY_AVAILABLE = False

try:
    import questionary
    from questionary import ValidationError, Validator

    QUESTIONARY_AVAILABLE = True
except ImportError:
    print("⚠️  Questionary not available - using basic input mode")

try:
    from rich import print as rprint
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.prompt import Confirm, Prompt
    from rich.table import Table

    RICH_AVAILABLE = True
except ImportError:
    print("⚠️  Rich not available - using basic output mode")

# If neither package is available, provide instructions
if not RICH_AVAILABLE and not QUESTIONARY_AVAILABLE:
    print("❌ Error: Required packages not available after installation attempt")
    print("ON1Builder Ignition requires the following packages:")
    print("  - questionary (for interactive menus)")
    print("  - rich (for beautiful terminal output)")
    print("")
    print("Please install them manually:")
    print("  pip install questionary rich typer")
    sys.exit(1)

# Import ON1Builder modules if they're available
try:
    from on1builder import __version__
    from on1builder.config.loaders import ConfigLoader
    from on1builder.config.settings import GlobalSettings
    from on1builder.core.main_orchestrator import MainOrchestrator
    from on1builder.core.multi_chain_orchestrator import MultiChainOrchestrator
    from on1builder.utils.logging_config import get_logger, setup_logging

    ON1BUILDER_AVAILABLE = True
except ImportError:
    print("Warning: ON1Builder package not found in path.")
    print("Limited functionality available.")
    __version__ = "2.1.3"  # Fallback version
    ON1BUILDER_AVAILABLE = False

# Set up console for rich output (with fallback)
if RICH_AVAILABLE:
    console = Console()
else:
    # Create a simple console fallback
    class SimpleConsole:
        def print(self, *args, **kwargs):
            # Remove rich markup for basic printing
            text = " ".join(str(arg) for arg in args)
            # Basic cleanup of rich markup
            import re

            text = re.sub(r"\[/?\w+[^\]]*\]", "", text)
            print(text)

        def print_json(self, data=None, **kwargs):
            # Simple JSON printing without rich formatting
            import json

            if data is not None:
                print(json.dumps(data, indent=2))

        def input(self, prompt=""):
            return input(prompt)

        def status(self, *args, **kwargs):
            # Simple context manager that does nothing
            class NoOpStatus:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

            return NoOpStatus()

    console = SimpleConsole()

# Initialize logger
logger = setup_logging("Ignition", level="INFO") if ON1BUILDER_AVAILABLE else None

# Constants
CONFIG_DIR = Path("configs/chains")
DEFAULT_CONFIG_PATH = CONFIG_DIR / "ethereum_mainnet.yaml"
DEFAULT_ENV_PATH = Path(".env")
DEFAULT_LOG_DIR = Path("logs")


class ConfigValidator(Validator):
    def validate(self, document):
        if not document.text:
            raise ValidationError(
                message="Config path cannot be empty",
                cursor_position=len(document.text),
            )
        path = Path(document.text)
        if not (path.exists() or path.parent.exists()):
            raise ValidationError(
                message=f"Path {path} does not exist and parent directory doesn't exist either",
                cursor_position=len(document.text),
            )


class Ignition:
    """Main class for the interactive ignition interface."""

    def __init__(self):
        """Initialize the ignition interface."""
        # Use the global console instance instead of creating a new one
        self.config_path = DEFAULT_CONFIG_PATH
        self.env_file = DEFAULT_ENV_PATH
        self.multi_chain = False
        self.log_level = "INFO"
        self.metrics_enabled = True
        self.monitoring_enabled = True
        self.notifications_enabled = True
        self.strategy_validation = True
        self.json_logs = False
        self.run_process = None
        self.core = None
        self.config = None

    def display_header(self):
        """Display the application header."""
        console.print()
        if RICH_AVAILABLE:
            console.print(
                Panel.fit(
                    "[bold yellow]ON1Builder Ignition[/bold yellow]\n"
                    "[dim]Interactive console launcher for ON1Builder[/dim]",
                    title=f"v{__version__}",
                    border_style="yellow",
                )
            )
        else:
            print("=" * 50)
            print(f"     ON1Builder Ignition v{__version__}")
            print("Interactive console launcher for ON1Builder")
            print("=" * 50)
        console.print()

    def display_menu(self):
        """Display the main menu and handle user input."""
        while True:
            self.display_header()

            # Status indicators for current configuration
            status_table = Table(show_header=False, box=None)
            status_table.add_column("Setting", style="cyan")
            status_table.add_column("Value", style="green")

            status_table.add_row("Config Path", str(self.config_path))
            status_table.add_row("Environment File", str(self.env_file))
            status_table.add_row(
                "Mode", "Multi-Chain" if self.multi_chain else "Single-Chain"
            )
            status_table.add_row("Log Level", self.log_level)
            status_table.add_row("Metrics", "✅" if self.metrics_enabled else "❌")
            status_table.add_row(
                "Monitoring", "✅" if self.monitoring_enabled else "❌"
            )
            status_table.add_row(
                "Notifications", "✅" if self.notifications_enabled else "❌"
            )
            status_table.add_row(
                "Strategy Validation", "✅" if self.strategy_validation else "❌"
            )
            status_table.add_row("JSON Logs", "✅" if self.json_logs else "❌")

            console.print(
                Panel(status_table, title="Current Settings", border_style="blue")
            )
            console.print()

            # Main menu options
            if QUESTIONARY_AVAILABLE:
                choice = questionary.select(
                    "Select an option:",
                    choices=[
                        " Launch ON1Builder",
                        "⚙️  Configure Settings",
                        "📊 View System Status",
                        "📁 Manage Configuration Files",
                        "🔎 View Logs",
                        "❓ Help & Documentation",
                        "❌ Exit",
                    ],
                    use_indicator=True,
                    style=questionary.Style(
                        [
                            ("selected", "bg:#0000ff #ffffff"),
                            ("pointer", "fg:#00ff00 bold"),
                            ("highlighted", "fg:#00ffff bold"),
                            ("answer", "fg:#00ff00 bold"),
                        ]
                    ),
                ).ask()
            else:
                choice = self._simple_select(
                    "Select an option:",
                    [
                        " Launch ON1Builder",
                        "⚙️  Configure Settings",
                        "📊 View System Status",
                        "📁 Manage Configuration Files",
                        "🔎 View Logs",
                        "❓ Help & Documentation",
                        "❌ Exit",
                    ],
                )

            if choice == " Launch ON1Builder":
                self.launch_on1builder()
            elif choice == "⚙️  Configure Settings":
                self.configure_settings()
            elif choice == "📊 View System Status":
                self.view_system_status()
            elif choice == "📁 Manage Configuration Files":
                self.manage_config_files()
            elif choice == "🔎 View Logs":
                self.view_logs()
            elif choice == "❓ Help & Documentation":
                self.show_help()
            elif choice == "❌ Exit":
                console.print("[yellow]Exiting ON1Builder Ignition...[/yellow]")
                sys.exit(0)

    def configure_settings(self):
        """Configure the application settings."""
        self.display_header()
        console.print("[bold blue]Configure Settings[/bold blue]\n")

        # Options for configuration
        # Select multiple settings via checkboxes
        selected = questionary.checkbox(
            "Select options to enable:",
            choices=[
                {"name": "Multi-Chain Mode", "checked": self.multi_chain},
                {"name": "Metrics Collection", "checked": self.metrics_enabled},
                {"name": "Monitoring Components", "checked": self.monitoring_enabled},
                {"name": "Notifications", "checked": self.notifications_enabled},
                {"name": "Strategy Validation", "checked": self.strategy_validation},
                {"name": "JSON Log Format", "checked": self.json_logs},
            ],
        ).ask()
        if selected:
            self.multi_chain = "Multi-Chain Mode" in selected
            self.metrics_enabled = "Metrics Collection" in selected
            self.monitoring_enabled = "Monitoring Components" in selected
            self.notifications_enabled = "Notifications" in selected
            self.strategy_validation = "Strategy Validation" in selected
            self.json_logs = "JSON Log Format" in selected

        # Configuration paths
        self.config_path = Path(
            questionary.text(
                "Config path:",
                default=str(self.config_path),
                validate=ConfigValidator,
            ).ask()
        )

        self.env_file = Path(
            questionary.text(
                "Environment file path:",
                default=str(self.env_file),
            ).ask()
        )

        # Log level selection
        self.log_level = questionary.select(
            "Select log level:",
            choices=[
                "DEBUG",
                "INFO",
                "WARNING",
                "ERROR",
            ],
            default=self.log_level,
        ).ask()

        console.print("[green]Settings updated![/green]")
        time.sleep(1)

    def launch_on1builder(self):
        """Launch the ON1Builder application with the current settings."""
        if not ON1BUILDER_AVAILABLE:
            console.print(
                "[bold red]Error:[/bold red] ON1Builder package not available."
            )
            console.print("Make sure ON1Builder is correctly installed.")
            input("\nPress Enter to continue...")
            return

        self.display_header()
        console.print("[bold green]Launching ON1Builder...[/bold green]\n")

        # Confirm before launching
        confirm = questionary.confirm(
            "Are you sure you want to launch ON1Builder with these settings?",
            default=True,
        ).ask()

        if not confirm:
            return

        try:
            # Create the run command with available options
            cmd = [
                sys.executable,
                "-m",
                "on1builder",
                "run",
                "run",
                "--config",
                str(self.config_path),
            ]

            # Add debug flag if log level is DEBUG
            if self.log_level.upper() == "DEBUG":
                cmd.append("--debug")

            # Display the command that will be run
            console.print("[dim]Running command:[/dim]")
            console.print(" ".join(cmd))
            console.print()

            # Run ON1Builder in a subprocess with live output
            console.print("[bold]ON1Builder Output:[/bold]")
            console.print("[yellow]Press Ctrl+C to stop...[/yellow]")

            # Run the process and capture output
            import subprocess

            with subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                universal_newlines=True,
            ) as proc:
                self.run_process = proc
                try:
                    if proc.stdout:
                        for line in proc.stdout:
                            console.print(line.rstrip())
                except KeyboardInterrupt:
                    console.print("[yellow]Stopping ON1Builder...[/yellow]")
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()

            self.run_process = None

        except Exception as e:
            console.print(f"[bold red]Error launching ON1Builder:[/bold red] {e}")

        console.print()
        input("Press Enter to return to menu...")

    def view_system_status(self):
        """Display system status information."""
        if not ON1BUILDER_AVAILABLE:
            console.print(
                "[bold red]Error:[/bold red] ON1Builder package not available."
            )
            console.print("Make sure ON1Builder is correctly installed.")
            input("\nPress Enter to continue...")
            return

        self.display_header()
        console.print("[bold blue]System Status[/bold blue]\n")

        with console.status("[bold green]Checking system status...[/bold green]"):
            # Run system checks
            time.sleep(1)

            # Check config file
            config_status = (
                "[green]✓[/green]"
                if Path(self.config_path).exists()
                else "[red]✗[/red]"
            )

            # Check env file
            env_status = (
                "[green]✓[/green]" if Path(self.env_file).exists() else "[red]✗[/red]"
            )

            # Check if python environment is set up correctly
            import importlib

            required_packages = ["web3", "eth_account", "aiohttp", "typer"]
            packages_status = {}
            for pkg in required_packages:
                try:
                    importlib.import_module(pkg)
                    packages_status[pkg] = "[green]✓[/green]"
                except ImportError:
                    packages_status[pkg] = "[red]✗[/red]"

        # Create status table
        table = Table(title="System Status")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Details", style="yellow")

        table.add_row("Config File", config_status, str(self.config_path))
        table.add_row("Environment File", env_status, str(self.env_file))

        for pkg, status in packages_status.items():
            table.add_row(f"Package: {pkg}", status, "")

        console.print(table)

        # Run additional status checks if ON1Builder is available
        try:
            # Create minimal config to check connections
            if Path(self.config_path).exists() and ON1BUILDER_AVAILABLE:
                loader = ConfigLoader()
                config = loader.load_global_config(str(self.config_path))

                console.print("\n[bold]Connection Status:[/bold]")

                # Check chain configurations
                try:
                    if hasattr(config, "chains") and isinstance(config.chains, dict):
                        console.print(
                            f"Configured chains: [green]{', '.join(config.chains.keys())}[/green]"
                        )
                        for chain_name, chain_config in config.chains.items():
                            if hasattr(chain_config, "http_endpoint"):
                                console.print(
                                    f"  {chain_name} RPC: [dim]{chain_config.http_endpoint}[/dim]"
                                )
                            if hasattr(chain_config, "chain_id"):
                                console.print(
                                    f"  {chain_name} Chain ID: [green]{chain_config.chain_id}[/green]"
                                )
                    else:
                        console.print("[yellow]No chain configurations found[/yellow]")
                except Exception as e:
                    console.print(f"Error reading chain configurations: {e}")
        except Exception as e:
            console.print(f"[red]Error checking connections: {e}[/red]")

        input("\nPress Enter to continue...")

    def manage_config_files(self):
        """Manage configuration files."""
        self.display_header()
        console.print("[bold blue]Manage Configuration Files[/bold blue]\n")

        if QUESTIONARY_AVAILABLE:
            choice = questionary.select(
                "Select an option:",
                choices=[
                    "View Current Config",
                    "Edit Config File",
                    "Create New Config",
                    "Back to Main Menu",
                ],
            ).ask()
        else:
            choice = self._simple_select(
                "Select an option:",
                choices=[
                    "View Current Config",
                    "Edit Config File",
                    "Create New Config",
                    "Back to Main Menu",
                ],
            )

        if choice == "View Current Config":
            self._view_config_file()
        elif choice == "Edit Config File":
            self._edit_config_file()
        elif choice == "Create New Config":
            self._create_new_config()
        else:
            return

    def _view_config_file(self):
        """View the current configuration file."""
        config_path = Path(self.config_path)

        if not config_path.exists():
            console.print(f"[red]Config file not found: {config_path}[/red]")
            input("\nPress Enter to continue...")
            return

        console.print(f"[bold]Contents of {config_path}:[/bold]\n")

        try:
            with open(config_path, "r") as f:
                content = f.read()

            # Try to parse as YAML for better display
            try:
                import yaml

                parsed = yaml.safe_load(content)
                console.print_json(data=parsed)
            except Exception:
                # Fallback to plain text display
                console.print(content)
        except Exception as e:
            console.print(f"[red]Error reading config file: {e}[/red]")

        input("\nPress Enter to continue...")

    def _edit_config_file(self):
        """Edit the configuration file using the default editor."""
        config_path = Path(self.config_path)

        if not config_path.exists():
            console.print(f"[red]Config file not found: {config_path}[/red]")
            create_new = questionary.confirm("Create a new config file?").ask()
            if create_new:
                self._create_new_config()
            return

        # Try to use the user's preferred editor
        editor = os.environ.get("EDITOR", "vi")

        try:
            import subprocess

            console.print(f"[green]Opening {config_path} with {editor}...[/green]")
            subprocess.call([editor, str(config_path)])
            console.print(f"[green]Finished editing {config_path}[/green]")
        except Exception as e:
            console.print(f"[red]Error editing config file: {e}[/red]")

        input("\nPress Enter to continue...")

    def _create_new_config(self):
        """Create a new configuration file."""
        self.display_header()
        console.print("[bold blue]Create New Configuration[/bold blue]\n")

        # Get new config path
        new_config_path = questionary.text(
            "New config file path:",
            default=str(CONFIG_DIR / "new_config.yaml"),
        ).ask()

        new_config_path = Path(new_config_path)

        # Make sure directory exists
        os.makedirs(new_config_path.parent, exist_ok=True)

        # Configuration options
        is_multi_chain = questionary.confirm("Create multi-chain configuration?").ask()

        # Template selection
        template_choices = ["empty", "minimal", "complete", "custom"]
        template_type = questionary.select(
            "Select template type:",
            choices=template_choices,
        ).ask()

        # Generate config content based on template
        content = self._generate_config_template(template_type, is_multi_chain)

        try:
            with open(new_config_path, "w") as f:
                f.write(content)

            console.print(f"[green]Configuration created at {new_config_path}[/green]")

            # Ask if user wants to use this config
            use_new_config = questionary.confirm(
                "Use this configuration as current config?", default=True
            ).ask()

            if use_new_config:
                self.config_path = new_config_path
                self.multi_chain = is_multi_chain
        except Exception as e:
            console.print(f"[red]Error creating config file: {e}[/red]")

        input("\nPress Enter to continue...")

    def _generate_config_template(self, template_type, is_multi_chain):
        """Generate a configuration template based on type."""
        if template_type == "empty":
            if is_multi_chain:
                return "# Multi-chain Configuration\nchains: {}\n"
            else:
                return "# Single-chain Configuration\n"
        elif template_type == "minimal":
            if is_multi_chain:
                return """# Multi-chain Configuration
chains:
  1:  # Ethereum Mainnet
    RPC_URL: "https://eth-mainnet.alchemyapi.io/v2/your-api-key"
    CHAIN_ID: 1
    LOG_LEVEL: "INFO"
  137:  # Polygon
    RPC_URL: "https://polygon-mainnet.alchemyapi.io/v2/your-api-key"
    CHAIN_ID: 137
    LOG_LEVEL: "INFO"
"""
            else:
                return """# Single-chain Configuration
RPC_URL: "https://eth-mainnet.alchemyapi.io/v2/your-api-key"
CHAIN_ID: 1
LOG_LEVEL: "INFO"
"""
        elif template_type == "complete":
            if is_multi_chain:
                return """# Multi-chain Configuration
chains:
  1:  # Ethereum Mainnet
    RPC_URL: "https://eth-mainnet.alchemyapi.io/v2/your-api-key"
    CHAIN_ID: 1
    LOG_LEVEL: "INFO"
    WALLET_KEY: "${PRIVATE_KEY}"  # From .env file
    GAS_MULTIPLIER: 1.1
    MAX_GAS_PRICE_GWEI: 100
  137:  # Polygon
    RPC_URL: "https://polygon-mainnet.alchemyapi.io/v2/your-api-key"
    CHAIN_ID: 137
    LOG_LEVEL: "INFO"
    WALLET_KEY: "${PRIVATE_KEY}"  # From .env file
    GAS_MULTIPLIER: 1.1
    MAX_GAS_PRICE_GWEI: 500

# Global settings
LOG_LEVEL: "INFO"
LOG_FORMAT: "detailed"
LOG_TO_FILE: true
LOG_DIR: "logs"

# Monitoring
ENABLE_PROMETHEUS: true
PROMETHEUS_PORT: 9090

# Notifications
NOTIFICATION_CHANNELS: ["slack", "email"]
MIN_NOTIFICATION_LEVEL: "WARNING"
SLACK_WEBHOOK_URL: "${SLACK_WEBHOOK_URL}"
"""
            else:
                return """# Single-chain Configuration
RPC_URL: "https://eth-mainnet.alchemyapi.io/v2/your-api-key"
CHAIN_ID: 1
WALLET_KEY: "${PRIVATE_KEY}"  # From .env file

# Gas settings
GAS_MULTIPLIER: 1.1
MAX_GAS_PRICE_GWEI: 100
PRIORITY_FEE_GWEI: 1.5

# Logging
LOG_LEVEL: "INFO"
LOG_FORMAT: "detailed"
LOG_TO_FILE: true
LOG_DIR: "logs"

# Monitoring
ENABLE_PROMETHEUS: true
PROMETHEUS_PORT: 9090

# Notifications
NOTIFICATION_CHANNELS: ["slack", "email"]
MIN_NOTIFICATION_LEVEL: "WARNING"
SLACK_WEBHOOK_URL: "${SLACK_WEBHOOK_URL}"
"""
        elif template_type == "custom":
            # For custom, let the user edit directly or provide more options
            if is_multi_chain:
                return """# Custom Multi-chain Configuration
# Please fill in your configuration details
chains:
  1:  # Ethereum Mainnet
    RPC_URL: ""
    CHAIN_ID: 1
    WALLET_KEY: "${PRIVATE_KEY}"  # From .env file
  # Add more chains as needed
"""
            else:
                return """# Custom Single-chain Configuration
# Please fill in your configuration details
RPC_URL: ""
CHAIN_ID: 1
WALLET_KEY: "${PRIVATE_KEY}"  # From .env file
"""
        else:
            # Default fallback
            return "# Configuration file\n"

    def view_logs(self):
        """View application logs."""
        self.display_header()
        console.print("[bold blue]Log Viewer[/bold blue]\n")

        # Find log files
        log_dir = DEFAULT_LOG_DIR
        log_files = []

        try:
            for root, _, files in os.walk(log_dir):
                for file in files:
                    if file.endswith(".log"):
                        log_files.append(os.path.join(root, file))
        except Exception:
            pass

        if not log_files:
            console.print("[yellow]No log files found.[/yellow]")
            log_files = ["No logs available"]

        # Sort logs by modification time (newest first)
        log_files.sort(
            key=lambda f: os.path.getmtime(f) if os.path.exists(f) else 0, reverse=True
        )

        # Add back option
        log_files.append("Back to Main Menu")

        # Let the user select a log file
        selected = questionary.select(
            "Select a log file to view:",
            choices=log_files,
        ).ask()

        if selected == "Back to Main Menu" or selected == "No logs available":
            return

        # View the selected log file
        console.print(f"[bold]Contents of {selected}:[/bold]\n")

        try:
            # Read the last 50 lines for large files
            tail_cmd = ["tail", "-n", "50", selected]
            import subprocess

            result = subprocess.run(tail_cmd, capture_output=True, text=True)
            console.print(result.stdout)

            console.print("\n[dim]Note: Showing the last 50 lines only.[/dim]")
        except Exception as e:
            console.print(f"[red]Error reading log file: {e}[/red]")

        input("\nPress Enter to continue...")

    def show_help(self):
        """Show help and documentation."""
        self.display_header()
        console.print("[bold blue]Help & Documentation[/bold blue]\n")

        # Create a table for commands and descriptions
        table = Table(title="ON1Builder Commands & Options")
        table.add_column("Command", style="cyan")
        table.add_column("Description", style="green")

        table.add_row("run", "Start ON1Builder in single or multi-chain mode")
        table.add_row("status", "Check system status and components")
        table.add_row("--multi-chain", "Enable multi-chain operation")
        table.add_row("--log-level", "Set logging level (DEBUG, INFO, WARNING, ERROR)")
        table.add_row("--metrics/--no-metrics", "Enable/disable metrics collection")
        table.add_row("--json-logs", "Use JSON formatted logs")

        console.print(table)
        console.print()

        # Show documentation links
        console.print("[bold]Documentation Links:[/bold]")
        console.print(
            "- Local docs: [link]file:///home/john0n1/ON1Builder/docs/index.html[/link]"
        )
        console.print(
            "- GitHub repository: [link]https://github.com/john0n1/ON1Builder[/link]"
        )
        console.print()

        # Show quick start guide
        console.print(
            Panel(
                "\n".join(
                    [
                        "[bold]Quick Start:[/bold]",
                        "",
                        "1. Configure your settings with the '⚙️  Configure Settings' option",
                        "2. Choose your mode (single or multi-chain)",
                        "3. Launch ON1Builder with the '🚀 Launch ON1Builder' option",
                        "",
                        "[bold]Common Issues:[/bold]",
                        "",
                        "- RPC connection errors: Check your RPC URL in the configuration",
                        "- Missing ABI errors: Ensure ABI files exist in resources/abi/",
                        "- Gas price errors: Set appropriate MAX_GAS_PRICE_GWEI in config",
                    ]
                ),
                title="Quick Help",
                border_style="green",
            )
        )

        input("\nPress Enter to continue...")

    def _simple_select(self, question, choices):
        """Fallback menu selection when questionary is not available."""
        print(f"\n{question}")
        print("-" * len(question))

        for i, choice in enumerate(choices, 1):
            # Clean up emoji and rich formatting for display
            clean_choice = (
                choice.replace("🔧", "[Setup]")
                .replace("🚀", "[Launch]")
                .replace("⚙️", "[Config]")
            )
            clean_choice = (
                clean_choice.replace("📊", "[Status]")
                .replace("📁", "[Files]")
                .replace("🔎", "[Logs]")
            )
            clean_choice = clean_choice.replace("❓", "[Help]").replace("❌", "[Exit]")
            print(f"{i}. {clean_choice}")

        while True:
            try:
                choice_num = int(input(f"\nSelect option (1-{len(choices)}): ")) - 1
                if 0 <= choice_num < len(choices):
                    return choices[choice_num]
                else:
                    print(f"Please enter a number between 1 and {len(choices)}")
            except (ValueError, KeyboardInterrupt):
                print("Please enter a valid number or Ctrl+C to exit")

    def _simple_confirm(self, question, default=True):
        """Fallback confirmation when questionary is not available."""
        default_text = "Y/n" if default else "y/N"
        while True:
            try:
                response = input(f"{question} ({default_text}): ").strip().lower()
                if response == "":
                    return default
                elif response in ["y", "yes"]:
                    return True
                elif response in ["n", "no"]:
                    return False
                else:
                    print("Please enter 'y' for yes or 'n' for no")
            except KeyboardInterrupt:
                return False

    def _simple_text(self, question, default=""):
        """Fallback text input when questionary is not available."""
        prompt = f"{question}"
        if default:
            prompt += f" (default: {default})"
        prompt += ": "

        try:
            response = input(prompt).strip()
            return response if response else default
        except KeyboardInterrupt:
            return default

    # Matrix-style intro effects
    def clear_screen(self):
        """Clear the terminal screen"""
        os.system("clear" if os.name == "posix" else "cls")

    def matrix_rain_effect(self, duration=3):
        """Display falling green code effect"""
        if not sys.stdout.isatty():
            return

        # Matrix characters
        chars = "01アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンabcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()_+-=[]{}|;:,.<>?"

        try:
            # Get terminal size using shutil (cross-platform)
            try:
                import shutil

                size = shutil.get_terminal_size()
                rows, cols = size.lines, size.columns
            except (ImportError, OSError):
                # Fallback to reasonable defaults
                rows, cols = 24, 80

            # Initialize falling streams
            streams = [
                {"chars": [], "y": 0, "speed": random.randint(1, 3)}
                for _ in range(cols // 3)
            ]

            start_time = time.time()
            while time.time() - start_time < duration:
                # Clear screen
                print("\033[2J\033[H", end="")

                # Create matrix effect
                matrix = [[" " for _ in range(cols)] for _ in range(rows)]

                # Update streams
                for i, stream in enumerate(streams):
                    if random.random() < 0.1:  # Start new stream
                        stream["chars"] = [
                            random.choice(chars) for _ in range(random.randint(5, 15))
                        ]
                        stream["y"] = 0

                    # Draw stream
                    x = i * 3
                    if x < cols and stream["chars"]:
                        for j, char in enumerate(stream["chars"]):
                            y = stream["y"] - j
                            if 0 <= y < rows:
                                if j == 0:  # Head of stream (bright)
                                    print(
                                        f"\033[{y+1};{x+1}H\033[92m{char}\033[0m",
                                        end="",
                                    )
                                elif j < 3:  # Bright part
                                    print(
                                        f"\033[{y+1};{x+1}H\033[32m{char}\033[0m",
                                        end="",
                                    )
                                else:  # Dim part
                                    print(
                                        f"\033[{y+1};{x+1}H\033[90m{char}\033[0m",
                                        end="",
                                    )

                        stream["y"] += stream["speed"]
                        if stream["y"] > rows + len(stream["chars"]):
                            stream["chars"] = []

                sys.stdout.flush()
                time.sleep(0.1)

        except KeyboardInterrupt:
            pass

        self.clear_screen()

    def wake_up_neo_sequence(self):
        messages = [
            "Wake up, Developer...",
            "",
            "The Matrix has you...",
            "Follow the white rabbit.",
            "",
            "",
            "Knock, knock, Dev.",
            "",
            "",
            "It's time to build.",
            "",
            "",
            "Welcome to ON1Builder",
        ]

        for msg in messages:
            if msg:
                # Green text effect
                for char in msg:
                    print(f"\033[92m{char}\033[0m", end="", flush=True)
                    time.sleep(0.05)
                print()
            time.sleep(1)

    def white_rabbit_sequence(self):
        """Display ASCII white rabbit animation"""
        rabbit_frames = [
            """
                    (\\   /)
                   ( ._.)
                  o_(")(")
            """,
            """
                    (\\   /)
                   ( >.<)
                  o_(")(")
            """,
            """
                    (\\   /)
                   ( >.<)
                  o_(")(")
            """,
            """
                    (\\   /)
                   ( ._.)
                  o_(")(")
            """,
        ]

        time.sleep(1)

        for frame in rabbit_frames:
            self.clear_screen()
            print("\033[97m" + frame + "\033[0m")  # White rabbit
            time.sleep(1.2)

        time.sleep(2)
        self.clear_screen()

    def matrix_intro(self):
        """Run the complete Matrix-style intro sequence"""
        try:
            self.clear_screen()

            # Phase 1: Matrix rain
            print("\033[92m" + "=" * 50)
            print("ON1Builder Ignition")
            print("=" * 50 + "\033[0m")
            time.sleep(1)

            self.matrix_rain_effect(3)

            # Phase 2: Wake up Neo
            self.wake_up_neo_sequence()
            time.sleep(2)

            # Phase 3: White rabbit
            self.white_rabbit_sequence()

            # Phase 4: System ready
            print("\033[92m" + "=" * 50)
            print("SYSTEM ONLINE - REALITY LOADING...")
            print("=" * 50 + "\033[0m")
            time.sleep(2)
            self.clear_screen()

        except KeyboardInterrupt:
            self.clear_screen()
            print("Matrix sequence interrupted. Entering normal mode...")
            time.sleep(1)
            self.clear_screen()


# ...existing code...


def main():
    """Main entry point with Matrix-style intro."""
    try:
        # Create ignition instance first
        ignition = Ignition()

        # Run Matrix intro sequence
        ignition.matrix_intro()

        # Start the main application
        ignition.display_menu()
    except KeyboardInterrupt:
        console.print("\n[yellow]Exiting ON1Builder Ignition...[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
