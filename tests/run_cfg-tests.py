# tests/test_run_cli.py

import sys
import asyncio
import pytest
from typer.testing import CliRunner
from typer import Exit

# Import the Typer app object from your run module.
# Adjust this if the path is different in your project.
from on1builder.cli.run_cmd import app as run_app

runner = CliRunner()


# ----------------------------
# Helpers to create dummy modules/classes
# ----------------------------

class DummyOrchestrator:
    def __init__(self, *, config):
        # store config for inspection if needed
        self.config = config
        self.ran = False

    async def run(self):
        # mark that run() was called
        self.ran = True


class FailingOrchestrator:
    def __init__(self, *, config):
        self.config = config

    async def run(self):
        raise RuntimeError("Orchestrator failure")


@pytest.fixture(autouse=True)
def stub_core_modules(monkeypatch):
    """
    Before each test, insert dummy modules into sys.modules so that
    `from on1builder.core.main_orchestrator import MainOrchestrator`
    and
    `from on1builder.core.multi_chain_orchestrator import MultiChainOrchestrator`
    resolve to our dummies.
    """
    # Create a dummy module for on1builder.core.main_orchestrator
    main_mod_name = "on1builder.core.main_orchestrator"
    multi_mod_name = "on1builder.core.multi_chain_orchestrator"

    # Dummy modules
    class MainModule:
        MainOrchestrator = DummyOrchestrator

    class MultiModule:
        MultiChainOrchestrator = DummyOrchestrator

    # Insert into sys.modules so that import inside run() finds these
    monkeypatch.setitem(sys.modules, main_mod_name, MainModule)
    monkeypatch.setitem(sys.modules, multi_mod_name, MultiModule)
    yield
    # After test, monkeypatch will undo


# ----------------------------
# Test: successful single‐chain run
# ----------------------------

def test_run_single_chain_success(monkeypatch, tmp_path):
    """
    If load_configuration returns a dict without 'multi_chain',
    run should instantiate MainOrchestrator and call its run() via asyncio.run,
    exiting with code 0 and no error printed.
    """
    # 1) Stub load_configuration to return a simple dict without 'multi_chain'
    dummy_config = {"some_key": "some_value"}
    def fake_load_configuration(*, config_path, chain):
        # verify that config_path and chain arguments propagate correctly
        assert config_path == str(tmp_path / "does_not_matter.yaml")
        assert chain == "mychain"
        return dummy_config

    monkeypatch.setattr(
        "on1builder.config.loaders.load_configuration",
        fake_load_configuration,
    )

    # 2) Stub asyncio.run so it simply awaits the coroutine and returns
    called = {"executed": False}
    original_asyncio_run = asyncio.run
    def fake_asyncio_run(coro):
        # The orchestrator instance should be our DummyOrchestrator
        # and its run() sets .ran = True
        result = original_asyncio_run(coro)
        called["executed"] = True
        return result

    monkeypatch.setattr(asyncio, "run", fake_asyncio_run)

    # 3) Invoke the CLI with --config and --chain flags
    result = runner.invoke(
        run_app,
        [
            "--config",
            str(tmp_path / "does_not_matter.yaml"),
            "--chain",
            "mychain",
        ],
    )

    assert result.exit_code == 0, f"Exit code: {result.exit_code}, stdout: {result.stdout}, stderr: {result.stderr}"
    # Since logger.info is used but not printed to stdout by default, we only check that
    # no "Error:" prefix is printed to stderr.
    assert result.stderr == ""
    # Confirm that asyncio.run was called, which implies orchestrator.run() ran
    assert called["executed"]


# ----------------------------
# Test: successful multi‐chain run
# ----------------------------

def test_run_multi_chain_success(monkeypatch, tmp_path):
    """
    If load_configuration returns {'multi_chain': True}, run() should import
    MultiChainOrchestrator and call its run() via asyncio.run, exit code 0.
    """
    # 1) Stub load_configuration to return a dict with multi_chain=True
    dummy_config = {"multi_chain": True, "chains": ["a", "b"]}
    def fake_load_configuration(*, config_path, chain):
        assert config_path is None  # since we won't pass --config
        assert chain is None
        return dummy_config

    monkeypatch.setattr(
        "on1builder.config.loaders.load_configuration",
        fake_load_configuration,
    )

    # 2) Stub asyncio.run again
    called = {"multi_executed": False}
    original_asyncio_run = asyncio.run

    def fake_asyncio_run(coro):
        result = original_asyncio_run(coro)
        called["multi_executed"] = True
        return result

    monkeypatch.setattr(asyncio, "run", fake_asyncio_run)

    # 3) Invoke without any flags: defaults to config=None, chain=None
    result = runner.invoke(run_app, [])
    assert result.exit_code == 0, f"Exit code: {result.exit_code}, stdout: {result.stdout}, stderr: {result.stderr}"
    assert result.stderr == ""
    assert called["multi_executed"]


# ----------------------------
# Test: load_configuration raises an exception
# ----------------------------

def test_run_load_config_failure(monkeypatch):
    """
    If load_configuration raises, run() should catch it, print an error to stderr,
    and exit with code 1.
    """
    def fake_load_configuration(*, config_path, chain):
        raise ValueError("bad config!")

    import sys
    import types
    run_cmd_module = sys.modules["on1builder.cli.run_cmd"]
    monkeypatch.setattr(run_cmd_module, "load_configuration", fake_load_configuration)

    # No need to stub asyncio.run or orchestrators, because load_configuration fails first
    result = runner.invoke(
        run_app,
        ["--config", "whatever.yaml", "--chain", "x"],
    )
    assert result.exit_code == 1
    # The stderr should contain the prefix "Error: bad config!"
    assert "Error: bad config!" in result.stderr


# ----------------------------
# Test: orchestrator.run() raises an exception
# ----------------------------

def test_run_orchestrator_failure(monkeypatch):
    """
    If orchestrator.run() raises, run() should print “Error: …” and exit code 1.
    We simulate this by having MainOrchestrator be FailingOrchestrator.
    """
    # 1) Stub load_configuration to return single‐chain config
    dummy_config = {"foo": "bar"}
    def fake_load_configuration(*, config_path, chain):
        return dummy_config

    monkeypatch.setattr(
        "on1builder.config.loaders.load_configuration",
        fake_load_configuration,
    )

    # 2) Replace the MainOrchestrator class in the module so that its run() fails
    main_mod = sys.modules["on1builder.core.main_orchestrator"]
    setattr(main_mod, "MainOrchestrator", FailingOrchestrator)

    # 3) Stub asyncio.run: it will propagate the exception raised by FailingOrchestrator.run()
    def fake_asyncio_run(coro):
        # Create a new event loop and run the coroutine, which should raise
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    monkeypatch.setattr(asyncio, "run", fake_asyncio_run)

    result = runner.invoke(
        run_app,
        ["--config", "some.yaml"],
    )
    assert result.exit_code == 1
    # The stderr should mention “Error: ” and the original exception text
    assert "Error: Orchestrator failure" in result.stderr


# ----------------------------
# Test: debug flag does not break anything
# ----------------------------

def test_run_with_debug_flag(monkeypatch, tmp_path):
    """
    Passing --debug should still follow the single‐chain code path and succeed.
    """
    # 1) Stub load_configuration
    dummy_config = {"x": "y"}
    def fake_load_configuration(*, config_path, chain):
        return dummy_config

    monkeypatch.setattr(
        "on1builder.config.loaders.load_configuration",
        fake_load_configuration,
    )

    # 2) Stub asyncio.run
    called = {"ran_debug": False}
    original_asyncio_run = asyncio.run

    def fake_asyncio_run(coro):
        called["ran_debug"] = True
        return original_asyncio_run(coro)

    monkeypatch.setattr(asyncio, "run", fake_asyncio_run)

    # 3) Invoke with --debug (no other flags)
    result = runner.invoke(run_app, ["--debug"])
    assert result.exit_code == 0, f"Exit code: {result.exit_code}, stdout: {result.stdout}, stderr: {result.stderr}"
    assert result.stderr == ""
    assert called["ran_debug"]
