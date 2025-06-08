# tests/config_cmd_test.py

import pytest
from pathlib import Path
import yaml
from typer.testing import CliRunner
from typer import Exit

# Adjust this import path if your package structure differs.
from on1builder.cli.config_cmd import app, _load_yaml


runner = CliRunner()


# ----------------------------
# Fixtures
# ----------------------------

@pytest.fixture
def tmp_yaml_file(tmp_path: Path):
    """
    Create a simple valid YAML file and return its path.
    """
    content = {
        "chain_id": 1,
        "rpc_url": "https://example.org"
    }
    file_path = tmp_path / "valid.yaml"
    file_path.write_text(yaml.dump(content))
    return file_path


@pytest.fixture
def tmp_invalid_yaml_file(tmp_path: Path):
    """
    Create a file with malformed YAML.
    """
    file_path = tmp_path / "invalid.yaml"
    file_path.write_text("::: not valid yaml :::")
    return file_path


@pytest.fixture
def tmp_multichain_yaml(tmp_path: Path):
    """
    Create a valid multi‐chain YAML file.
    """
    content = {
        "chains": [
            {"chain_id": 1, "rpc_url": "https://chain1.example"},
            {"chain_id": 2, "rpc_url": "https://chain2.example"},
        ]
    }
    file_path = tmp_path / "multichain.yaml"
    file_path.write_text(yaml.dump(content))
    return file_path


@pytest.fixture
def tmp_missing_fields_yaml(tmp_path: Path):
    """
    Create a YAML missing required fields.
    """
    content = {
        "some_key": "some_value"
    }
    file_path = tmp_path / "missing.yaml"
    file_path.write_text(yaml.dump(content))
    return file_path


@pytest.fixture
def tmp_chain_config_valid(tmp_path: Path):
    """
    Create a valid chain‐specific YAML file.
    """
    content = {"chain_id": 42, "rpc_url": "https://chain42.example"}
    file_path = tmp_path / "chain_valid.yaml"
    file_path.write_text(yaml.dump(content))
    return file_path


@pytest.fixture
def tmp_chain_config_missing(tmp_path: Path):
    """
    Create a chain‐specific YAML missing required fields.
    """
    content = {"rpc_url": "https://chain-missing.example"}
    file_path = tmp_path / "chain_missing.yaml"
    file_path.write_text(yaml.dump(content))
    return file_path


# ----------------------------
# Tests for _load_yaml
# ----------------------------

def test_load_yaml_valid(tmp_yaml_file):
    data = _load_yaml(tmp_yaml_file)
    assert isinstance(data, dict)
    assert data["chain_id"] == 1
    assert data["rpc_url"].startswith("https://")


def test_load_yaml_empty(tmp_path: Path):
    # Create an empty file: safe_load should return {} 
    empty_file = tmp_path / "empty.yaml"
    empty_file.write_text("")
    data = _load_yaml(empty_file)
    assert data == {}


def test_load_yaml_invalid_raises(tmp_invalid_yaml_file):
    # _load_yaml should call safe_load, catch YAMLError, print an error, and raise typer.Exit
    with pytest.raises(Exit) as excinfo:
        _load_yaml(tmp_invalid_yaml_file)
    assert excinfo.value.exit_code == 1


# ----------------------------
# Tests for validate_command (single‐chain)
# ----------------------------

def test_validate_single_chain_success(tmp_yaml_file):
    """Single‐chain without --chain, fields present, should succeed."""
    result = runner.invoke(app, ["validate", str(tmp_yaml_file)])
    assert result.exit_code == 0
    assert "✅ Configuration is valid." in result.stdout


def test_validate_single_chain_missing_fields(tmp_missing_fields_yaml):
    """Single‐chain missing required fields should fail with appropriate message."""
    result = runner.invoke(app, ["validate", str(tmp_missing_fields_yaml)])
    assert result.exit_code == 1
    # Should report missing 'chain_id' and 'rpc_url'
    assert "❌ Main config: missing required field 'chain_id'" in result.stdout
    assert "❌ Main config: missing required field 'rpc_url'" in result.stdout


def test_validate_single_chain_with_chain_option_success(tmp_yaml_file, tmp_chain_config_valid):
    """
    Using --chain option: main config only needs to exist (it can be empty),
    but chain_config must have required fields.
    """
    # main config can be an otherwise empty dict, but to satisfy exists/readable constraint, reuse tmp_yaml_file
    result = runner.invoke(
        app,
        ["validate", str(tmp_yaml_file), "--chain", str(tmp_chain_config_valid)]
    )
    assert result.exit_code == 0
    assert "✅ Configuration is valid." in result.stdout


def test_validate_single_chain_with_chain_option_missing_fields(tmp_yaml_file, tmp_chain_config_missing):
    """Chain config missing required fields should produce an error."""
    result = runner.invoke(
        app,
        ["validate", str(tmp_yaml_file), "--chain", str(tmp_chain_config_missing)]
    )
    assert result.exit_code == 1
    assert "❌ Chain config: missing required field 'chain_id'" in result.stdout


def test_validate_single_chain_with_invalid_chain_yaml(tmp_yaml_file, tmp_invalid_yaml_file):
    """If the chain_config file is invalid YAML, it should error out."""
    result = runner.invoke(
        app,
        ["validate", str(tmp_yaml_file), "--chain", str(tmp_invalid_yaml_file)]
    )
    # It will fail inside _load_yaml for chain_config
    assert result.exit_code == 1
    assert "❌ YAML parsing error:" in result.stderr or "Validation failed:" in result.stderr


# ----------------------------
# Tests for validate_command (multi‐chain)
# ----------------------------

def test_validate_multi_chain_success(tmp_multichain_yaml):
    """Valid multi-chain config (with 'chains' list) should pass."""
    result = runner.invoke(app, ["validate", str(tmp_multichain_yaml), "--multi-chain"])
    assert result.exit_code == 0
    assert "✅ Configuration is valid." in result.stdout


def test_validate_multi_chain_missing_chains_section(tmp_missing_fields_yaml):
    """Multi-chain flag but no 'chains' key should produce an error."""
    result = runner.invoke(app, ["validate", str(tmp_missing_fields_yaml), "--multi-chain"])
    assert result.exit_code == 1
    assert "❌ Multi-chain config must have 'chains' section" in result.stdout


def test_validate_multi_chain_chain_item_not_dict(tmp_path: Path):
    """If one of the entries under 'chains' is not a dict, we should catch that."""
    bad_content = {"chains": ["not_a_dict", 123]}
    bad_file = tmp_path / "bad_multichain.yaml"
    bad_file.write_text(yaml.dump(bad_content))

    result = runner.invoke(app, ["validate", str(bad_file), "--multi-chain"])
    assert result.exit_code == 1
    # The first chain is not a dict, so we expect an error referencing "Chain #0: must be a dictionary"
    assert "❌ Chain #0: must be a dictionary" in result.stdout


def test_validate_multi_chain_chain_missing_fields(tmp_path: Path):
    """If a chain dict is missing 'rpc_url' or 'chain_id', we should report it."""
    content = {"chains": [{"chain_id": 7}, {"rpc_url": "https://noid.example"}]}
    file_path = tmp_path / "incomplete_multichain.yaml"
    file_path.write_text(yaml.dump(content))

    result = runner.invoke(app, ["validate", str(file_path), "--multi-chain"])
    assert result.exit_code == 1
    # Expect two errors: one for the first chain missing 'rpc_url', one for the second missing 'chain_id'
    assert "❌ Chain #0: missing required field 'rpc_url'" in result.stdout
    assert "❌ Chain #1: missing required field 'chain_id'" in result.stdout


def test_validate_multi_chain_invalid_yaml(tmp_invalid_yaml_file):
    """If main config is invalid YAML when using --multi-chain, it should exit early."""
    result = runner.invoke(app, ["validate", str(tmp_invalid_yaml_file), "--multi-chain"])
    assert result.exit_code == 1
    assert "❌ YAML parsing error:" in result.stderr or "Validation failed:" in result.stderr


# ----------------------------
# Tests for show_command
# ----------------------------

def test_show_command_success(tmp_yaml_file):
    """show_command should print out the YAML contents in dumped form."""
    # Load the file’s contents with safe_load and then compare with dumped output
    loaded = yaml.safe_load(tmp_yaml_file.read_text())

    result = runner.invoke(app, ["show", str(tmp_yaml_file)])
    assert result.exit_code == 0

    # The output should be a YAML‐dumped version of `loaded`
    dumped = yaml.dump(loaded, default_flow_style=False, indent=2)
    assert dumped.strip() in result.stdout.strip()


def test_show_command_invalid_yaml(tmp_invalid_yaml_file):
    """If YAML is invalid, show_command should report an error and exit with code 1."""
    result = runner.invoke(app, ["show", str(tmp_invalid_yaml_file)])
    assert result.exit_code == 1
    assert "❌ Failed to show config:" in result.stderr or "❌ YAML parsing error:" in result.stderr


def test_show_command_nonexistent_file(tmp_path: Path):
    """If the file does not exist, Typer’s built-in check should catch it before our code runs."""
    fake = tmp_path / "does_not_exist.yaml"
    result = runner.invoke(app, ["show", str(fake)])
    # Typer’s error for non‐existent file usually starts with “Error:” and exit code != 0
    assert result.exit_code != 0
    assert ("Error" in result.stderr) or ("No such file or directory" in result.stderr)


# ----------------------------
# Direct tests of _load_yaml for hierarchy checks
# ----------------------------

def test_load_yaml_returns_empty_dict_for_blank_file(tmp_path: Path):
    """If the YAML file is blank, safe_load returns None, so our wrapper returns {}."""
    blank = tmp_path / "blank.yaml"
    blank.write_text("")
    data = _load_yaml(blank)
    assert data == {}


def test_load_yaml_non_mapping_root(tmp_path: Path):
    """
    If the root of the YAML is a list or scalar, validate_command should catch it.
    Here we call _load_yaml directly to demonstrate it returns a non‐dict without error.
    But validate_command will flag it.
    """
    # Create a YAML whose root is a list
    list_root = tmp_path / "listroot.yaml"
    list_root.write_text("- item1\n- item2\n")

    data = _load_yaml(list_root)
    assert isinstance(data, list)

    # Now run validate_command so it prints "Configuration root must be a mapping" and exits
    result = runner.invoke(app, ["validate", str(list_root)])
    assert result.exit_code == 1
    assert "❌ Configuration root must be a mapping (dictionary)." in result.stdout


# ----------------------------
# End of tests
# ----------------------------
