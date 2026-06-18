from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from on1builder.config import manager as manager_module
from on1builder.config.manager import (
    ConfigurationManager,
    get_config_manager,
    get_validated_config,
    initialize_global_config,
)
from on1builder.utils.custom_exceptions import ConfigurationError


@pytest.fixture(autouse=True)
def reset_global_manager():
    manager_module._config_manager = None
    yield
    manager_module._config_manager = None


class StubConfig:
    def __init__(self):
        self.wallet_address = "0x" + "1" * 40
        self.wallet_key = "0x" + "2" * 64
        self.chains = [1]
        self.rpc_urls = {1: "https://rpc.example"}
        self.websocket_urls = {1: "wss://ws.example"}
        self.api = SimpleNamespace(
            etherscan_api_key="etherscan",
            coingecko_api_key=None,
            coinmarketcap_api_key=None,
        )
        self.notifications = {"channels": ["slack"]}
        self.debug = True

    def model_dump(self):
        return {
            "wallet_address": self.wallet_address,
            "wallet_key": self.wallet_key,
            "chains": self.chains,
            "rpc_urls": self.rpc_urls,
            "websocket_urls": self.websocket_urls,
            "api": {
                "etherscan_api_key": "etherscan",
                "coingecko_api_key": None,
                "coinmarketcap_api_key": None,
            },
            "notifications": self.notifications,
            "debug": self.debug,
        }


def test_initialize_get_config_reload_and_runtime_checks(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DUMMY=1\n", encoding="utf-8")
    config = StubConfig()
    manager = ConfigurationManager()

    validate_complete = MagicMock(side_effect=lambda cfg: cfg)
    monkeypatch.setattr(manager_module, "load_settings", lambda env_path: config)
    monkeypatch.setattr(
        manager._validator, "validate_complete_config", validate_complete
    )
    monkeypatch.setattr(manager, "_find_config_file", lambda: env_file)

    manager.initialize()
    assert manager.get_config() is config
    assert manager._config_file_path == env_file
    assert manager._last_loaded is not None
    validate_complete.assert_called_once()

    first_loaded = manager._last_loaded
    manager.initialize()
    assert manager._last_loaded == first_loaded

    manager.reload_configuration()
    assert manager._last_loaded >= first_loaded

    runtime = manager.validate_runtime_requirements()
    assert runtime == {
        "initialized": True,
        "wallet_configured": True,
        "chains_configured": True,
        "rpc_connections": True,
        "api_access": True,
        "file_permissions": True,
    }


def test_find_config_file_validation_and_health(monkeypatch, tmp_path):
    current = tmp_path / "project"
    current.mkdir()
    parent_env = tmp_path / ".env"
    parent_env.write_text("x=1\n", encoding="utf-8")

    monkeypatch.setattr(Path, "cwd", classmethod(lambda cls: current))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))

    manager = ConfigurationManager()
    assert manager._find_config_file() == parent_env

    manager._config = StubConfig()
    manager._config_file_path = parent_env
    manager._validation_errors = ["warning"]
    monkeypatch.setattr(
        manager, "validate_runtime_requirements", lambda: {"initialized": True}
    )
    health = manager.get_health_status()
    assert health["status"] == "unhealthy"
    assert health["config_file"] == str(parent_env)


def test_validate_configuration_critical_and_runtime_failure_paths(monkeypatch):
    manager = ConfigurationManager()
    manager._config = StubConfig()
    manager._config.model_dump = lambda: {
        "wallet_key": None,
        "wallet_address": None,
        "chains": [],
    }
    monkeypatch.setattr(manager._validator, "validate_complete_config", lambda cfg: cfg)
    monkeypatch.setattr(
        manager, "validate_runtime_requirements", lambda: {"initialized": False}
    )

    with pytest.raises(
        ConfigurationError, match="Critical configuration requirements not met"
    ):
        manager._validate_configuration()

    assert any(
        "Wallet private key is required" in err for err in manager._validation_errors
    )
    assert manager.get_health_status()["runtime_checks"] == {"initialized": False}


def test_initialize_wraps_errors_and_get_config_requires_initialization(
    monkeypatch, tmp_path
):
    manager = ConfigurationManager()
    env_file = tmp_path / ".env"
    env_file.write_text("x=1\n", encoding="utf-8")
    monkeypatch.setattr(manager, "_find_config_file", lambda: env_file)
    monkeypatch.setattr(
        manager_module,
        "load_settings",
        lambda env_path: (_ for _ in ()).throw(RuntimeError("bad load")),
    )

    with pytest.raises(ConfigurationError, match="Configuration initialization failed"):
        manager.initialize()

    with pytest.raises(ConfigurationError, match="Configuration not initialized"):
        ConfigurationManager().get_config()


def test_validation_helpers_and_export_safe_config(monkeypatch, tmp_path):
    manager = ConfigurationManager()
    manager._config = StubConfig()
    manager._config_file_path = tmp_path / ".env"

    config_dict = manager._config.model_dump()
    manager._check_critical_requirements(config_dict)
    manager._validate_chain_configurations(
        {
            "chains": [1, 137],
            "rpc_urls": {"1": "https://rpc.example"},
            "websocket_urls": {},
        }
    )
    assert "Missing RPC URLs for chains: [137]" in manager._validation_errors

    manager._validation_errors.clear()
    manager._validate_api_configurations({"api": {}})
    assert manager._validation_errors == [
        "At least one price API key should be configured for better market data"
    ]

    monkeypatch.setattr(
        "on1builder.utils.config_redactor.ConfigRedactor.redact_config",
        lambda config, show_sensitive=False: {
            "redacted": True,
            "show_sensitive": show_sensitive,
        },
    )
    assert manager.export_safe_config() == {"redacted": True, "show_sensitive": False}


def test_global_config_helpers(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DUMMY=1\n", encoding="utf-8")
    config = StubConfig()
    manager = get_config_manager()

    monkeypatch.setattr(manager, "initialize", MagicMock())
    initialize_global_config(str(env_file), force_reload=True)
    manager.initialize.assert_called_once_with(str(env_file), True)

    manager_module._config_manager = ConfigurationManager()
    manager_module._config_manager._config = config
    assert get_validated_config() is config
    assert get_config_manager() is manager_module._config_manager
