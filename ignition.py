# ignition.py
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.syntax import Syntax
    import questionary
    from questionary import ValidationError, Validator
except ImportError:
    print("Error: Required packages 'rich' and 'questionary' are not installed.")
    print("Please install them by running: pip install rich questionary")
    sys.exit(1)

console = Console()

class PathValidator(Validator):
    def validate(self, document):
        path = Path(document.text)
        if not path.exists():
            raise ValidationError(
                message="Please enter a valid path to your .env file",
                cursor_position=len(document.text),
            )

class Ignition:
    def __init__(self):
        self.env_file_path: Optional[Path] = self._find_env_file()

    def _find_env_file(self) -> Optional[Path]:
        """Searches for a .env file in the current and parent directories."""
        current_dir = Path.cwd()
        for _ in range(3):
            env_path = current_dir / ".env"
            if env_path.exists():
                return env_path
            current_dir = current_dir.parent
        return None

    def display_header(self):
        """Displays the application header."""
        console.clear()
        header = Panel(
            "[bold yellow]ON1Builder Ignition[/]\n[dim]Interactive TUI Launcher[/]",
            title="[bold]v2.1.4[/]",
            border_style="yellow",
            expand=False
        )
        console.print(header)
        console.print()

    def display_status(self):
        """Displays the current configuration status."""
        status_table = Table(show_header=False, box=None, padding=(0, 2))
        status_table.add_column(style="cyan")
        status_table.add_column(style="green")
        
        env_status = f"[green]{self.env_file_path}[/]" if self.env_file_path else "[red]Not Found[/]"
        status_table.add_row("Env File:", env_status)
        
        console.print(Panel(status_table, title="[bold]Current Settings[/]", border_style="blue"))
        console.print()

    def run(self):
        """The main loop for the interactive menu."""
        while True:
            self.display_header()
            self.display_status()
            
            if not self.env_file_path:
                console.print("[bold yellow]⚠️  .env file not found.[/] Please specify the path.")
                self.configure_env_path()
                continue

            choice = questionary.select(
                "Select an action:",
                choices=[
                    questionary.Choice("🚀 Launch ON1Builder", value="launch"),
                    questionary.Choice("🔎 Check System Status", value="status"),
                    questionary.Choice("⚙️  Configure .env Path", value="config"),
                    questionary.Choice("📄 View Logs", value="logs"),
                    questionary.Separator(),
                    questionary.Choice("❌ Exit", value="exit"),
                ],
                use_indicator=True
            ).ask()

            if choice == "launch":
                self.launch_bot()
            elif choice == "status":
                self.check_status()
            elif choice == "config":
                self.configure_env_path()
            elif choice == "logs":
                self.view_logs()
            elif choice == "exit" or choice is None:
                console.print("[bold yellow]Goodbye![/]")
                break

    def configure_env_path(self):
        """Prompts the user to set the path to the .env file."""
        path_str = questionary.path(
            "Enter the full path to your .env file:",
            only_files=True,
            validate=PathValidator
        ).ask()
        if path_str:
            self.env_file_path = Path(path_str)
            console.print(f"[green]✅ .env path set to: {self.env_file_path}[/]")
        time.sleep(1.5)

    def launch_bot(self):
        """Constructs and runs the 'run start' command."""
        self.display_header()
        console.print("[bold green]🚀 Launching ON1Builder...[/]")
        console.print("[dim]Press Ctrl+C to stop the bot at any time.[/]\n")
        
        command = [sys.executable, "-m", "on1builder", "run", "start"]
        try:
            # We use Popen to run it as a managed subprocess
            process = subprocess.Popen(command, env={**os.environ, "DOTENV_PATH": str(self.env_file_path)})
            process.wait() # Wait for the process to complete
        except KeyboardInterrupt:
            console.print("\n[bold yellow]Interruption detected. Sending stop signal to bot...[/]")
            process.terminate()
            process.wait()
        except Exception as e:
            console.print(f"[bold red]An error occurred while launching the bot:[/] {e}")
            
        console.print("\n[bold blue]ON1Builder has stopped. Press Enter to return to the menu.[/]")
        input()

    def check_status(self):
        """Runs the 'status check' command."""
        self.display_header()
        command = [sys.executable, "-m", "on1builder", "status", "check"]
        subprocess.run(command, env={**os.environ, "DOTENV_PATH": str(self.env_file_path)})
        console.print("\n[bold blue]Status check complete. Press Enter to return to the menu.[/]")
        input()

    def view_logs(self):
        """Displays the tail end of the main log file."""
        self.display_header()
        log_file = Path("logs/on1builder.log")
        if not log_file.exists():
            console.print("[bold red]Log file not found at 'logs/on1builder.log'[/]")
        else:
            console.print(Panel(f"[bold]Showing last 50 lines of {log_file}[/]", border_style="blue"))
            log_content = ""
            try:
                with open(log_file, "r") as f:
                    lines = f.readlines()
                    log_content = "".join(lines[-50:])
                
                syntax = Syntax(log_content, "log", theme="monokai", line_numbers=True)
                console.print(syntax)
            except Exception as e:
                console.print(f"[bold red]Error reading log file:[/] {e}")

        console.print("\n[bold blue]Press Enter to return to the menu.[/]")
        input()

def main():
    try:
        ignition = Ignition()
        ignition.run()
    except (KeyboardInterrupt, TypeError):
        # TypeError can be raised by questionary on Ctrl+C in some terminals
        console.print("\n[bold yellow]Ignition launcher exited.[/]")

if __name__ == "__main__":
    main()