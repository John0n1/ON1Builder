"""Logical tests for NonceManager ensuring reliable nonce handling."""
import pytest

from on1builder.core.nonce_manager import NonceManager


class StubEth:
    def __init__(self, nonce_sequence):
        self._nonce_sequence = list(nonce_sequence)
        self.calls = 0

    async def get_transaction_count(self, address, state):
        self.calls += 1
        idx = min(self.calls - 1, len(self._nonce_sequence) - 1)
        return self._nonce_sequence[idx]


class StubWeb3:
    def __init__(self, nonce_sequence):
        self.eth = StubEth(nonce_sequence)


@pytest.fixture(autouse=True)
def reset_singleton():
    NonceManager.reset_instance()
    yield
    NonceManager.reset_instance()


@pytest.mark.asyncio
async def test_nonce_initialization_and_increment():
    web3 = StubWeb3([5])
    manager = NonceManager(web3, "0xabc")

    first = await manager.get_next_nonce()
    second = await manager.get_next_nonce()

    assert (first, second) == (5, 6)
    assert web3.eth.calls == 1  # only one chain call for initial fetch


@pytest.mark.asyncio
async def test_resync_refreshes_nonce_from_chain():
    web3 = StubWeb3([3, 10])
    manager = NonceManager(web3, "0xabc")

    await manager.get_next_nonce()  # initializes to 3
    await manager.resync_nonce()    # forces refresh to next value (10)
    refreshed = await manager.get_next_nonce()

    assert refreshed == 10
    assert web3.eth.calls == 2


@pytest.mark.asyncio
async def test_singleton_refresh_resets_cached_nonce_on_reuse():
    web3_first = StubWeb3([7])
    manager = NonceManager(web3_first, "0xabc")
    await manager.get_next_nonce()  # consumes initial

    # Re-create with same address but new provider; refresh should reset cache
    web3_new = StubWeb3([15])
    manager_again = NonceManager(web3_new, "0xabc")
    next_nonce = await manager_again.get_next_nonce()

    assert next_nonce == 15
    assert web3_new.eth.calls == 1
