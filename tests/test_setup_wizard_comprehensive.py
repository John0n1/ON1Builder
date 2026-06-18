from __future__ import annotations

from pathlib import Path

import pytest
import typer

from on1builder.cli import setup_wizard


class Prompt:
    def __init__(self, value):
        self.value = value

    def ask(self):
        return self.value


def test_load_env_values_format_apply_and_redaction(tmp_path):
    env1 = tmp_path / ".env.example"
    env2 = tmp_path / ".env"
    env1.write_text("A=1\nB='two words'\n# comment\n", encoding="utf-8")
    env2.write_text("C=3\n", encoding="utf-8")

    values = setup_wizard._load_env_values([env1, env2])
    assert values == {"A": "1", "B": "two words", "C": "3"}
    assert setup_wizard._format_env_value("two words", quoted=False) == '"two words"'
    assert (
        setup_wizard._format_env_value("comma,value", quoted=False) == '"comma,value"'
    )
    assert (
        setup_wizard._apply_updates(
            ["A=1", "B='x'", "OTHER=ok"], {"A": "2", "B": "two words", "NEW": "n"}
        )
        == 'A=2\nB="two words"\nOTHER=ok\nNEW=n\n'
    )
    assert setup_wizard._redact_secret("123456789") == "1234...6789"
    assert setup_wizard._bool_to_env(True) == "1"
    assert setup_wizard._redact_summary(
        {"API_KEY": "123456789", "CONFIG_PATH": "/a/b", "NAME": "ok"}
    ) == {"API_KEY": "1234...6789", "CONFIG_PATH": "/a/b", "NAME": "ok"}
    assert setup_wizard._bool_from_env("yes", False) is True
    assert setup_wizard._bool_from_env("off", True) is False
    assert (
        setup_wizard._normalize_choice(
            "TENDERLY", ["eth_call", "anvil", "tenderly"], "eth_call"
        )
        == "tenderly"
    )


@pytest.mark.parametrize(
    ("func", "value", "expected"),
    [
        (setup_wizard._validate_private_key, "", "Private key is required."),
        (setup_wizard._validate_private_key, "0x" + "1" * 64, True),
        (setup_wizard._validate_optional_private_key, "", True),
        (setup_wizard._validate_wallet_address, "0x" + "1" * 40, True),
        (
            setup_wizard._validate_wallet_address,
            "bad",
            "Invalid address format (0x...).",
        ),
        (setup_wizard._validate_chain_ids, "1,137", True),
        (setup_wizard._validate_int, "2", True),
        (setup_wizard._validate_int, "x", "Must be an integer."),
        (setup_wizard._validate_float, "2.5", True),
        (setup_wizard._validate_float, "x", "Must be a number."),
        (setup_wizard._validate_http_url, "https://rpc", True),
        (
            setup_wizard._validate_http_url,
            "ftp://rpc",
            "RPC URL must start with http:// or https://",
        ),
        (setup_wizard._validate_ws_url, "wss://rpc", True),
        (
            setup_wizard._validate_ws_url,
            "http://rpc",
            "WebSocket URL must start with ws:// or wss://",
        ),
    ],
)
def test_validation_helpers(func, value, expected):
    assert func(value) == expected
    assert setup_wizard._parse_chain_ids("1, 137") == [1, 137]


def test_prompt_helpers_raise_exit_on_cancel(monkeypatch):
    monkeypatch.setattr(
        setup_wizard.questionary, "text", lambda *args, **kwargs: Prompt(None)
    )
    monkeypatch.setattr(
        setup_wizard.questionary, "password", lambda *args, **kwargs: Prompt(None)
    )
    monkeypatch.setattr(
        setup_wizard.questionary, "confirm", lambda *args, **kwargs: Prompt(None)
    )
    monkeypatch.setattr(
        setup_wizard.questionary, "select", lambda *args, **kwargs: Prompt(None)
    )

    with pytest.raises(typer.Exit):
        setup_wizard._ask_required("label", validate=None)
    with pytest.raises(typer.Exit):
        setup_wizard._ask_password("label", validate=None)
    with pytest.raises(typer.Exit):
        setup_wizard._ask_confirm("label")
    with pytest.raises(typer.Exit):
        setup_wizard._ask_select("label", ["a"])


def test_run_setup_wizard_full_flow(monkeypatch, tmp_path):
    env_example = tmp_path / ".env.example"
    env_example.write_text(
        "WALLET_KEY=old\nWALLET_ADDRESS=0xold\nCHAINS=1\n", encoding="utf-8"
    )
    env_path = tmp_path / ".env"

    monkeypatch.setattr(Path, "cwd", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(setup_wizard.console, "print", lambda *args, **kwargs: None)
    monkeypatch.setattr(setup_wizard, "success_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(setup_wizard, "warning_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(setup_wizard, "info_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(setup_wizard, "resolve_editor_command", lambda editor: ["echo"])
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: None)

    confirms = iter(
        [
            True,  # use wallet as profit receiver
            False,  # different wallet keys
            True,  # configure api keys
            True,  # configure simulation settings
            True,  # allow unsimulated trades
            True,  # configure submission bundle
            True,  # provide bundle signer key
            True,  # configure gas
            True,  # enable dynamic gas pricing
            True,  # configure profit/risk
            True,  # enable dynamic profit scaling
            True,  # configure flashloan
            True,  # enable flashloans
            True,  # enable mev strategies
            True,  # enable front-running
            True,  # enable back-running
            False,  # enable sandwich attacks
            True,  # configure cross-chain
            True,  # enable cross-chain mode
            True,  # enable bridge monitoring
            False,  # change values before writing
            True,  # write .env
            False,  # open editor
        ]
    )
    selects = iter(["tenderly", "bundle"])
    optional_values = iter(
        [
            "1,137",
            "",
            "https://rpc1",
            "wss://ws1",
            "https://rpc137",
            "",  # chain/rpc/ws
            "etherscan",
            "coingecko",
            "coinmarket",
            "cryptocompare",
            "infura",  # api
            "7",
            "https://api.tenderly.co/api/v1",  # simulation
            "https://relay.flashbots.net",
            "auth-token",
            "2",
            "30",
            "/keys/bundle.key",  # bundle
            "200",
            "1.2",
            "500000",
            "50",
            "75",
            "10.0",
            "3",
            "2.0",  # gas
            "0.05",
            "0.005",
            "0.1",
            "0.3",
            "0.5",
            "0.01",
            "0.05",
            "1.0",
            "80.0",
            "20.0",
            "5.0",  # profit
            "2.0",
            "1000.0",
            "0.1",  # flashloan
            "15",  # cross-chain
        ]
    )
    required_values = iter(
        [
            "0x" + "a" * 40,
            "tenderly-account",
            "tenderly-project",
        ]
    )
    password_values = iter(
        [
            "0x" + "1" * 64,
            "tenderly-token",
            "0x" + "2" * 64,
        ]
    )

    monkeypatch.setattr(
        setup_wizard, "_ask_confirm", lambda *args, **kwargs: next(confirms)
    )
    monkeypatch.setattr(
        setup_wizard, "_ask_select", lambda *args, **kwargs: next(selects)
    )
    monkeypatch.setattr(
        setup_wizard, "_ask_optional", lambda *args, **kwargs: next(optional_values)
    )
    monkeypatch.setattr(
        setup_wizard, "_ask_required", lambda *args, **kwargs: next(required_values)
    )
    monkeypatch.setattr(
        setup_wizard, "_ask_password", lambda *args, **kwargs: next(password_values)
    )
    monkeypatch.setattr(
        setup_wizard, "_ask_optional_password", lambda *args, **kwargs: ""
    )
    monkeypatch.setattr(
        setup_wizard.ConfigValidator,
        "validate_private_key",
        staticmethod(lambda value: value.replace("0x", "")),
    )

    setup_wizard.run_setup_wizard()

    written = env_path.read_text(encoding="utf-8")
    assert "WALLET_KEY=0x" + "1" * 64 in written
    assert "TENDERLY_ACCOUNT_SLUG=tenderly-account" in written
    assert "BUNDLE_SIGNER_KEY=" + "2" * 64 in written
    assert "CROSS_CHAIN_ENABLED=1" in written


def test_run_setup_wizard_handles_existing_file_and_missing_example(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(Path, "cwd", classmethod(lambda cls: tmp_path))

    with pytest.raises(setup_wizard.ConfigurationError):
        setup_wizard.run_setup_wizard()

    env_example = tmp_path / ".env.example"
    env_example.write_text("A=1\n", encoding="utf-8")
    (tmp_path / ".env").write_text("A=1\n", encoding="utf-8")
    messages = []
    monkeypatch.setattr(setup_wizard, "_ask_confirm", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        setup_wizard, "info_message", lambda message: messages.append(message)
    )
    monkeypatch.setattr(setup_wizard.console, "print", lambda *args, **kwargs: None)

    setup_wizard.run_setup_wizard()
    assert messages == ["Setup cancelled; keeping existing .env."]
