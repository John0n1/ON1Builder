#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 John Hauger Mitander

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path

import questionary
import typer
from rich.console import Console
from rich.syntax import Syntax

from on1builder.config.validation import ConfigValidator
from on1builder.utils.cli_helpers import (
    info_message,
    resolve_editor_command,
    success_message,
    warning_message,
)
from on1builder.utils.custom_exceptions import ConfigurationError

console = Console()


def _load_env_values(paths: Iterable[Path]) -> dict[str, str]:
    values: dict[str, str] = {}
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, raw_value = stripped.partition("=")
            value = raw_value.strip()
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            values[key.strip()] = value
    return values


def _format_env_value(value: str, quoted: bool) -> str:
    if quoted:
        return f'"{value}"'
    if any(ch.isspace() for ch in value):
        return f'"{value}"'
    if "," in value:
        return f'"{value}"'
    return value


def _apply_updates(lines: list[str], updates: dict[str, str]) -> str:
    updated_keys = set()
    rendered: list[str] = []
    for line in lines:
        match = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
        if not match:
            rendered.append(line)
            continue
        key, raw_value = match.group(1), match.group(2)
        if key not in updates:
            rendered.append(line)
            continue
        stripped = raw_value.strip()
        quoted = (stripped.startswith('"') and stripped.endswith('"')) or (
            stripped.startswith("'") and stripped.endswith("'")
        )
        rendered.append(f"{key}={_format_env_value(updates[key], quoted)}")
        updated_keys.add(key)

    for key, value in updates.items():
        if key in updated_keys:
            continue
        rendered.append(f"{key}={_format_env_value(value, quoted=False)}")

    return "\n".join(rendered).rstrip() + "\n"


def _ask_required(label: str, validate) -> str:
    value = questionary.text(label, validate=validate).ask()
    if value is None:
        raise typer.Exit(code=130)
    return value.strip()


def _ask_optional(label: str, default: str | None = None, validate=None) -> str:
    value = questionary.text(label, default=default or "", validate=validate).ask()
    if value is None:
        raise typer.Exit(code=130)
    return value.strip()


def _ask_password(label: str, validate) -> str:
    value = questionary.password(label, validate=validate).ask()
    if value is None:
        raise typer.Exit(code=130)
    return value.strip()


def _ask_optional_password(label: str, validate) -> str:
    value = questionary.password(label, validate=validate).ask()
    if value is None:
        raise typer.Exit(code=130)
    return value.strip()


def _ask_confirm(label: str, default: bool = True) -> bool:
    value = questionary.confirm(label, default=default).ask()
    if value is None:
        raise typer.Exit(code=130)
    return bool(value)


def _ask_select(label: str, choices: list[str], default: str | None = None) -> str:
    value = questionary.select(label, choices=choices, default=default).ask()
    if value is None:
        raise typer.Exit(code=130)
    return str(value)


def _validate_private_key(value: str) -> bool | str:
    if not value:
        return "Private key is required."
    if not ConfigValidator.PRIVATE_KEY_PATTERN.match(value):
        return "Invalid private key format (64 hex chars, optional 0x)."
    return True


def _validate_optional_private_key(value: str) -> bool | str:
    if not value:
        return True
    if not ConfigValidator.PRIVATE_KEY_PATTERN.match(value):
        return "Invalid private key format (64 hex chars, optional 0x)."
    return True


def _validate_wallet_address(value: str) -> bool | str:
    if not value:
        return "Wallet address is required."
    if not ConfigValidator.ADDRESS_PATTERN.match(value):
        return "Invalid address format (0x...)."
    return True


def _validate_chain_ids(value: str) -> bool | str:
    if not value.strip():
        return "At least one chain ID is required."
    try:
        chain_ids = _parse_chain_ids(value)
        ConfigValidator.validate_chain_ids(chain_ids)
    except Exception as exc:
        return str(exc)
    return True


def _validate_int(value: str) -> bool | str:
    if not value.strip():
        return "Value is required."
    try:
        int(value)
    except ValueError:
        return "Must be an integer."
    return True


def _validate_float(value: str) -> bool | str:
    if not value.strip():
        return "Value is required."
    try:
        float(value)
    except ValueError:
        return "Must be a number."
    return True


def _validate_http_url(value: str) -> bool | str:
    if not value.strip():
        return "RPC URL is required."
    if value.startswith("http://") or value.startswith("https://"):
        return True
    return "RPC URL must start with http:// or https://"


def _validate_ws_url(value: str) -> bool | str:
    if not value.strip():
        return True
    if value.startswith("ws://") or value.startswith("wss://"):
        return True
    return "WebSocket URL must start with ws:// or wss://"


def _parse_chain_ids(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _redact_secret(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _bool_to_env(value: bool) -> str:
    return "1" if value else "0"


def _redact_summary(values: dict[str, str]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for key, value in values.items():
        if not value:
            redacted[key] = value
            continue
        if key.endswith("_PATH"):
            redacted[key] = value
        elif any(token in key for token in ("KEY", "TOKEN", "PASSWORD")):
            redacted[key] = _redact_secret(value)
        else:
            redacted[key] = value
    return redacted


def _bool_from_env(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in ("1", "true", "yes", "y", "on"):
        return True
    if normalized in ("0", "false", "no", "n", "off"):
        return False
    return default


def _normalize_choice(value: str | None, choices: list[str], fallback: str) -> str:
    if not value:
        return fallback
    candidate = value.strip()
    if candidate in choices:
        return candidate
    candidate_lower = candidate.lower()
    if candidate_lower in choices:
        return candidate_lower
    return fallback


def run_setup_wizard() -> None:
    env_example = Path.cwd() / ".env.example"
    env_path = Path.cwd() / ".env"

    if not env_example.exists():
        raise ConfigurationError(
            "Could not find .env.example in the current directory."
        )

    defaults = _load_env_values([env_example, env_path])
    example_lines = env_example.read_text().splitlines()

    if env_path.exists():
        overwrite = _ask_confirm(
            ".env already exists. Overwrite it with new values?", default=False
        )
        if not overwrite:
            info_message("Setup cancelled; keeping existing .env.")
            return

    console.print("[bold]ON1Builder setup wizard[/]")
    console.print("Follow the prompts to generate a fresh .env file.\n")

    while True:
        updates: dict[str, str] = {}

        wallet_key = _ask_password(
            "Insert your private key", validate=_validate_private_key
        )
        updates["WALLET_KEY"] = wallet_key

        wallet_address = _ask_required(
            "Insert your wallet address", validate=_validate_wallet_address
        )
        updates["WALLET_ADDRESS"] = wallet_address

        use_wallet_profit = _ask_confirm(
            "Use wallet address as profit receiver?",
            default=_bool_from_env(defaults.get("USE_WALLET_AS_PROFIT_RECEIVER"), True),
        )
        if use_wallet_profit:
            updates["PROFIT_RECEIVER_ADDRESS"] = wallet_address
        else:
            profit_address = _ask_required(
                "Insert profit receiver address", validate=_validate_wallet_address
            )
            updates["PROFIT_RECEIVER_ADDRESS"] = profit_address

        chain_default = defaults.get("CHAINS", "1")
        chain_input = _ask_optional(
            "Chains (comma-separated IDs)",
            default=chain_default,
            validate=_validate_chain_ids,
        )
        chain_ids = _parse_chain_ids(chain_input)
        updates["CHAINS"] = ",".join(str(cid) for cid in chain_ids)

        poa_default = defaults.get("POA_CHAINS", "")
        poa_input = _ask_optional(
            "PoA chains (comma-separated IDs, optional)",
            default=poa_default,
            validate=lambda v: _validate_chain_ids(v) if v.strip() else True,
        )
        updates["POA_CHAINS"] = poa_input

        for chain_id in chain_ids:
            rpc_key = f"RPC_URL_{chain_id}"
            ws_key = f"WEBSOCKET_URL_{chain_id}"
            rpc_default = defaults.get(rpc_key, "")
            ws_default = defaults.get(ws_key, "")
            updates[rpc_key] = _ask_optional(
                f"RPC URL for chain {chain_id}",
                default=rpc_default,
                validate=_validate_http_url,
            )
            updates[ws_key] = _ask_optional(
                f"WebSocket URL for chain {chain_id} (optional)",
                default=ws_default,
                validate=_validate_ws_url,
            )
            if rpc_default and not updates[rpc_key]:
                updates[rpc_key] = rpc_default

        if _ask_confirm(
            "Use different wallet keys per chain?",
            default=_bool_from_env(defaults.get("USE_PER_CHAIN_KEYS"), False),
        ):
            try:
                from eth_account import Account
            except ImportError:
                warning_message(
                    "eth-account not available; per-chain keys cannot be derived."
                )
            else:
                for chain_id in chain_ids:
                    per_key = _ask_optional_password(
                        f"Private key for chain {chain_id} (leave blank to reuse default)",
                        validate=_validate_optional_private_key,
                    )
                    if not per_key:
                        continue
                    normalized = ConfigValidator.validate_private_key(per_key)
                    updates[f"WALLET_KEY_{chain_id}"] = normalized
                    try:
                        derived = Account.from_key(normalized).address
                        updates[f"WALLET_ADDRESS_{chain_id}"] = derived
                    except Exception as exc:
                        warning_message(
                            f"Could not derive address for chain {chain_id}: {exc}"
                        )

        if _ask_confirm("Configure API keys?", default=False):
            updates["ETHERSCAN_API_KEY"] = _ask_optional(
                "Etherscan API key",
                default=defaults.get("ETHERSCAN_API_KEY", ""),
            )
            updates["COINGECKO_API_KEY"] = _ask_optional(
                "Coingecko API key",
                default=defaults.get("COINGECKO_API_KEY", ""),
            )
            updates["COINMARKETCAP_API_KEY"] = _ask_optional(
                "CoinMarketCap API key",
                default=defaults.get("COINMARKETCAP_API_KEY", ""),
            )
            updates["CRYPTOCOMPARE_API_KEY"] = _ask_optional(
                "CryptoCompare API key",
                default=defaults.get("CRYPTOCOMPARE_API_KEY", ""),
            )
            updates["INFURA_PROJECT_ID"] = _ask_optional(
                "Infura project ID",
                default=defaults.get("INFURA_PROJECT_ID", ""),
            )

        if _ask_confirm("Configure simulation settings?", default=False):
            updates["ALLOW_UNSIMULATED_TRADES"] = _bool_to_env(
                _ask_confirm(
                    "Allow unsimulated trades?",
                    default=_bool_from_env(
                        defaults.get("ALLOW_UNSIMULATED_TRADES"), False
                    ),
                )
            )
            simulation_backend = _ask_select(
                "Simulation backend",
                choices=["eth_call", "anvil", "tenderly"],
                default=_normalize_choice(
                    defaults.get("SIMULATION_BACKEND"),
                    ["eth_call", "anvil", "tenderly"],
                    "eth_call",
                ),
            )
            updates["SIMULATION_BACKEND"] = simulation_backend
            updates["SIMULATION_CONCURRENCY"] = _ask_optional(
                "Simulation concurrency",
                default=defaults.get("SIMULATION_CONCURRENCY", "5"),
                validate=_validate_int,
            )
            if simulation_backend == "tenderly":
                updates["TENDERLY_BASE_URL"] = _ask_optional(
                    "Tenderly base URL",
                    default=defaults.get(
                        "TENDERLY_BASE_URL", "https://api.tenderly.co/api/v1"
                    ),
                    validate=_validate_http_url,
                )
                updates["TENDERLY_ACCOUNT_SLUG"] = _ask_required(
                    "Tenderly account slug", validate=lambda v: bool(v.strip())
                )
                updates["TENDERLY_PROJECT_SLUG"] = _ask_required(
                    "Tenderly project slug", validate=lambda v: bool(v.strip())
                )
                tenderly_token = _ask_password(
                    "Tenderly access token", validate=lambda v: bool(v.strip())
                )
                updates["TENDERLY_ACCESS_TOKEN"] = tenderly_token

        if _ask_confirm("Configure submission/Flashbots settings?", default=False):
            submission_mode = _ask_select(
                "Submission mode",
                choices=["public", "private", "bundle"],
                default=_normalize_choice(
                    defaults.get("SUBMISSION_MODE"),
                    ["public", "private", "bundle"],
                    "public",
                ),
            )
            updates["SUBMISSION_MODE"] = submission_mode
            if submission_mode == "private":
                updates["PRIVATE_RPC_URL"] = _ask_optional(
                    "Private RPC URL",
                    default=defaults.get(
                        "PRIVATE_RPC_URL", "https://rpc.flashbots.net/fast"
                    ),
                    validate=_validate_http_url,
                )
            elif submission_mode == "bundle":
                updates["BUNDLE_RELAY_URL"] = _ask_optional(
                    "Bundle relay URL",
                    default=defaults.get(
                        "BUNDLE_RELAY_URL", "https://relay.flashbots.net"
                    ),
                    validate=_validate_http_url,
                )
                updates["BUNDLE_RELAY_AUTH_TOKEN"] = _ask_optional(
                    "Bundle relay auth token (optional)",
                    default=defaults.get("BUNDLE_RELAY_AUTH_TOKEN", ""),
                )
                updates["BUNDLE_TARGET_BLOCK_OFFSET"] = _ask_optional(
                    "Bundle target block offset",
                    default=defaults.get("BUNDLE_TARGET_BLOCK_OFFSET", "1"),
                    validate=_validate_int,
                )
                updates["BUNDLE_TIMEOUT_SECONDS"] = _ask_optional(
                    "Bundle timeout (seconds)",
                    default=defaults.get("BUNDLE_TIMEOUT_SECONDS", "30"),
                    validate=_validate_int,
                )
                if _ask_confirm(
                    "Provide a bundle signer key? (auto-generated if blank)",
                    default=False,
                ):
                    bundle_key = _ask_password(
                        "Bundle signer private key", validate=_validate_private_key
                    )
                    updates["BUNDLE_SIGNER_KEY"] = ConfigValidator.validate_private_key(
                        bundle_key
                    )
                    updates["BUNDLE_SIGNER_KEY_PATH"] = _ask_optional(
                        "Bundle signer key path",
                        default=defaults.get(
                            "BUNDLE_SIGNER_KEY_PATH",
                            str(Path.home() / ".on1builder" / "bundle_signer.key"),
                        ),
                    )

        if _ask_confirm("Configure gas and transaction settings?", default=False):
            updates["MAX_GAS_PRICE_GWEI"] = _ask_optional(
                "Max gas price (gwei)",
                default=defaults.get("MAX_GAS_PRICE_GWEI", "200"),
                validate=_validate_int,
            )
            updates["GAS_PRICE_MULTIPLIER"] = _ask_optional(
                "Gas price multiplier",
                default=defaults.get("GAS_PRICE_MULTIPLIER", "1.1"),
                validate=_validate_float,
            )
            updates["DEFAULT_GAS_LIMIT"] = _ask_optional(
                "Default gas limit",
                default=defaults.get("DEFAULT_GAS_LIMIT", "500000"),
                validate=_validate_int,
            )
            updates["FALLBACK_GAS_PRICE_GWEI"] = _ask_optional(
                "Fallback gas price (gwei)",
                default=defaults.get("FALLBACK_GAS_PRICE_GWEI", "50"),
                validate=_validate_int,
            )
            updates["DYNAMIC_GAS_PRICING"] = _bool_to_env(
                _ask_confirm(
                    "Enable dynamic gas pricing?",
                    default=_bool_from_env(defaults.get("DYNAMIC_GAS_PRICING"), True),
                )
            )
            updates["GAS_PRICE_PERCENTILE"] = _ask_optional(
                "Gas price percentile",
                default=defaults.get("GAS_PRICE_PERCENTILE", "75"),
                validate=_validate_int,
            )
            updates["MAX_GAS_FEE_PERCENTAGE"] = _ask_optional(
                "Max gas fee percentage",
                default=defaults.get("MAX_GAS_FEE_PERCENTAGE", "10.0"),
                validate=_validate_float,
            )
            updates["TRANSACTION_RETRY_COUNT"] = _ask_optional(
                "Transaction retry count",
                default=defaults.get("TRANSACTION_RETRY_COUNT", "3"),
                validate=_validate_int,
            )
            updates["TRANSACTION_RETRY_DELAY"] = _ask_optional(
                "Transaction retry delay (seconds)",
                default=defaults.get("TRANSACTION_RETRY_DELAY", "2.0"),
                validate=_validate_float,
            )

        if _ask_confirm(
            "Configure profit, balance, and risk thresholds?", default=False
        ):
            updates["MIN_WALLET_BALANCE"] = _ask_optional(
                "Min wallet balance (ETH)",
                default=defaults.get("MIN_WALLET_BALANCE", "0.05"),
                validate=_validate_float,
            )
            updates["MIN_PROFIT_ETH"] = _ask_optional(
                "Min profit (ETH)",
                default=defaults.get("MIN_PROFIT_ETH", "0.005"),
                validate=_validate_float,
            )
            updates["MIN_PROFIT_PERCENTAGE"] = _ask_optional(
                "Min profit (% of investment)",
                default=defaults.get("MIN_PROFIT_PERCENTAGE", "0.1"),
                validate=_validate_float,
            )
            updates["DYNAMIC_PROFIT_SCALING"] = _bool_to_env(
                _ask_confirm(
                    "Enable dynamic profit scaling?",
                    default=_bool_from_env(
                        defaults.get("DYNAMIC_PROFIT_SCALING"), True
                    ),
                )
            )
            updates["BALANCE_RISK_RATIO"] = _ask_optional(
                "Balance risk ratio",
                default=defaults.get("BALANCE_RISK_RATIO", "0.3"),
                validate=_validate_float,
            )
            updates["SLIPPAGE_TOLERANCE"] = _ask_optional(
                "Slippage tolerance (%)",
                default=defaults.get("SLIPPAGE_TOLERANCE", "0.5"),
                validate=_validate_float,
            )
            updates["EMERGENCY_BALANCE_THRESHOLD"] = _ask_optional(
                "Emergency balance threshold (ETH)",
                default=defaults.get("EMERGENCY_BALANCE_THRESHOLD", "0.01"),
                validate=_validate_float,
            )
            updates["LOW_BALANCE_THRESHOLD"] = _ask_optional(
                "Low balance threshold (ETH)",
                default=defaults.get("LOW_BALANCE_THRESHOLD", "0.05"),
                validate=_validate_float,
            )
            updates["HIGH_BALANCE_THRESHOLD"] = _ask_optional(
                "High balance threshold (ETH)",
                default=defaults.get("HIGH_BALANCE_THRESHOLD", "1.0"),
                validate=_validate_float,
            )
            updates["PROFIT_REINVESTMENT_PERCENTAGE"] = _ask_optional(
                "Profit reinvestment (%)",
                default=defaults.get("PROFIT_REINVESTMENT_PERCENTAGE", "80.0"),
                validate=_validate_float,
            )
            updates["MAX_POSITION_SIZE_PERCENT"] = _ask_optional(
                "Max position size (%)",
                default=defaults.get("MAX_POSITION_SIZE_PERCENT", "20.0"),
                validate=_validate_float,
            )
            updates["DAILY_LOSS_LIMIT_PERCENT"] = _ask_optional(
                "Daily loss limit (%)",
                default=defaults.get("DAILY_LOSS_LIMIT_PERCENT", "5.0"),
                validate=_validate_float,
            )

        if _ask_confirm("Configure flashloan/MEV strategy settings?", default=False):
            updates["FLASHLOAN_ENABLED"] = _bool_to_env(
                _ask_confirm(
                    "Enable flashloans?",
                    default=_bool_from_env(defaults.get("FLASHLOAN_ENABLED"), True),
                )
            )
            updates["FLASHLOAN_MIN_PROFIT_MULTIPLIER"] = _ask_optional(
                "Flashloan min profit multiplier",
                default=defaults.get("FLASHLOAN_MIN_PROFIT_MULTIPLIER", "2.0"),
                validate=_validate_float,
            )
            updates["FLASHLOAN_MAX_AMOUNT_ETH"] = _ask_optional(
                "Flashloan max amount (ETH)",
                default=defaults.get("FLASHLOAN_MAX_AMOUNT_ETH", "1000.0"),
                validate=_validate_float,
            )
            updates["FLASHLOAN_BUFFER_PERCENTAGE"] = _ask_optional(
                "Flashloan buffer (%)",
                default=defaults.get("FLASHLOAN_BUFFER_PERCENTAGE", "0.1"),
                validate=_validate_float,
            )
            updates["MEV_STRATEGIES_ENABLED"] = _bool_to_env(
                _ask_confirm(
                    "Enable MEV strategies?",
                    default=_bool_from_env(
                        defaults.get("MEV_STRATEGIES_ENABLED"), True
                    ),
                )
            )
            updates["FRONT_RUNNING_ENABLED"] = _bool_to_env(
                _ask_confirm(
                    "Enable front-running?",
                    default=_bool_from_env(defaults.get("FRONT_RUNNING_ENABLED"), True),
                )
            )
            updates["BACK_RUNNING_ENABLED"] = _bool_to_env(
                _ask_confirm(
                    "Enable back-running?",
                    default=_bool_from_env(defaults.get("BACK_RUNNING_ENABLED"), True),
                )
            )
            updates["SANDWICH_ATTACKS_ENABLED"] = _bool_to_env(
                _ask_confirm(
                    "Enable sandwich attacks?",
                    default=_bool_from_env(
                        defaults.get("SANDWICH_ATTACKS_ENABLED"), False
                    ),
                )
            )

        if _ask_confirm("Configure cross-chain settings?", default=False):
            updates["CROSS_CHAIN_ENABLED"] = _bool_to_env(
                _ask_confirm(
                    "Enable cross-chain mode?",
                    default=_bool_from_env(defaults.get("CROSS_CHAIN_ENABLED"), True),
                )
            )
            updates["BRIDGE_MONITORING_ENABLED"] = _bool_to_env(
                _ask_confirm(
                    "Enable bridge monitoring?",
                    default=_bool_from_env(
                        defaults.get("BRIDGE_MONITORING_ENABLED"), True
                    ),
                )
            )
            updates["ARBITRAGE_SCAN_INTERVAL"] = _ask_optional(
                "Arbitrage scan interval (seconds)",
                default=defaults.get("ARBITRAGE_SCAN_INTERVAL", "15"),
                validate=_validate_int,
            )

        summary = _redact_summary(dict(updates))
        console.print("\n[bold]Proposed configuration[/]")
        console.print(Syntax(json.dumps(summary, indent=2), "json", theme="monokai"))

        if _ask_confirm("Change any values before writing?", default=False):
            continue

        if _ask_confirm("Write .env with these values?", default=True):
            rendered = _apply_updates(example_lines, updates)
            env_path.write_text(rendered)
            success_message("Saved .env.")

            if _ask_confirm("Open .env in an editor now?", default=True):
                command = resolve_editor_command(None)
                try:
                    import subprocess

                    subprocess.run([*command, str(env_path)], check=False)
                except FileNotFoundError:
                    warning_message(
                        f"Editor '{command[0]}' not found. Set $EDITOR or use --editor."
                    )
            break

        if not _ask_confirm("Restart setup wizard?", default=False):
            info_message("Setup cancelled.")
            break
