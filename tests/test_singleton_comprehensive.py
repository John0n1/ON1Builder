from __future__ import annotations

import threading
from unittest.mock import AsyncMock, MagicMock

import pytest

from on1builder.utils import singleton as singleton_module
from on1builder.utils.singleton import (
    SingletonMeta,
    SingletonRegistry,
    get_singleton_registry,
)


@pytest.fixture(autouse=True)
def reset_singleton_state():
    SingletonMeta._instances.clear()
    SingletonRegistry._instances.clear()
    SingletonRegistry._factories.clear()
    Refreshable.init_count = 0
    singleton_module._registry = SingletonRegistry()
    yield
    Refreshable.init_count = 0
    SingletonMeta._instances.clear()
    SingletonRegistry._instances.clear()
    SingletonRegistry._factories.clear()


class Refreshable(metaclass=SingletonMeta):
    init_count = 0

    def __init__(self, value=0):
        type(self).init_count += 1
        self.value = value
        self.refresh_calls: list[tuple[int]] = []

    def _singleton_refresh(self, value=0):
        self.refresh_calls.append((value,))


def test_singleton_meta_returns_same_instance_and_resets():
    first = Refreshable(1)
    second = Refreshable(2)

    assert first is second
    assert Refreshable.init_count == 1
    assert second.refresh_calls[-1] == (2,)

    Refreshable.reset_instance()
    third = Refreshable(3)
    assert third is not first
    assert Refreshable.init_count == 2


def test_singleton_meta_is_thread_safe():
    created = []
    barrier = threading.Barrier(5)

    def build_instance():
        barrier.wait()
        created.append(Refreshable(10))

    threads = [threading.Thread(target=build_instance) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len({id(instance) for instance in created}) == 1
    assert Refreshable.init_count == 1


def test_singleton_registry_registers_gets_has_and_resets():
    registry = SingletonRegistry()
    factory = MagicMock(side_effect=lambda prefix: {"value": prefix})
    registry.register_factory("alpha", factory)

    assert registry.has("alpha") is True
    first = registry.get("alpha", "one")
    second = registry.get("alpha", "two")
    assert first is second
    assert first == {"value": "one"}
    assert factory.call_count == 1

    registry.reset("alpha")
    third = registry.get("alpha", "three")
    assert third == {"value": "three"}

    registry.reset()
    assert registry._instances == {}

    with pytest.raises(KeyError):
        registry.get("missing")


@pytest.mark.asyncio
async def test_singleton_registry_shutdown_all_handles_async_sync_and_errors():
    registry = SingletonRegistry()
    async_instance = MagicMock()
    async_instance.stop = AsyncMock()

    sync_calls: list[str] = []
    broken_calls: list[str] = []

    class SyncInstance:
        def close(self):
            sync_calls.append("closed")

    class BrokenInstance:
        def close(self):
            broken_calls.append("broken")
            raise RuntimeError("boom")

    registry._instances = {
        "async": async_instance,
        "sync": SyncInstance(),
        "broken": BrokenInstance(),
        "plain": object(),
    }

    await registry.shutdown_all()

    async_instance.stop.assert_awaited_once()
    assert sync_calls == ["closed"]
    assert broken_calls == ["broken"]


def test_get_singleton_registry_returns_global_registry():
    registry = get_singleton_registry()
    assert registry is singleton_module._registry
    assert isinstance(registry, SingletonRegistry)
