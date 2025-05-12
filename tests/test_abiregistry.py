# LICENSE: MIT // github.com/John0n1/ON1Builder

import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from scripts.python.abi_registry import ABIRegistry

@pytest.fixture
def abi_registry():
    return ABIRegistry()

@pytest.mark.asyncio
async def test_initialize(abi_registry):
    with patch('scripts.python.abi_registry.ABIRegistry._load_all_abis', new_callable=AsyncMock) as mock_load_all_abis:
        await abi_registry.initialize()
        mock_load_all_abis.assert_called_once()
        assert abi_registry._initialized is True

@pytest.mark.asyncio
async def test_load_and_validate_abi(abi_registry):
    abi_type = 'erc20'
    abi_path = Path('tests/abi/erc20_abi.json')
    critical_abis = {'erc20'}

    with patch('scripts.python.abi_registry.ABIRegistry._load_abi_from_path', new_callable=AsyncMock) as mock_load_abi_from_path:
        mock_load_abi_from_path.return_value = [{'name': 'transfer', 'type': 'function', 'inputs': []}]
        await abi_registry._load_and_validate_abi(abi_type, abi_path, critical_abis)
        assert abi_type in abi_registry.abis
        assert abi_registry.abis[abi_type] == [{'name': 'transfer', 'type': 'function', 'inputs': []}]

@pytest.mark.asyncio
async def test_load_abi_from_path(abi_registry):
    abi_path = Path('tests/abi/erc20_abi.json')
    abi_type = 'erc20'

    with patch('aiofiles.open', new_callable=AsyncMock) as mock_open:
        mock_open.return_value.__aenter__.return_value.read.return_value = '[{"name": "transfer", "type": "function", "inputs": []}]'
        abi = await abi_registry._load_abi_from_path(abi_path, abi_type)
        assert abi == [{'name': 'transfer', 'type': 'function', 'inputs': []}]

def test_validate_abi(abi_registry):
    abi = [{'name': 'transfer', 'type': 'function', 'inputs': []}]
    abi_type = 'erc20'
    assert abi_registry._validate_abi(abi, abi_type) is True

def test_extract_signatures(abi_registry):
    abi = [{'name': 'transfer', 'type': 'function', 'inputs': []}]
    abi_type = 'erc20'
    abi_registry._extract_signatures(abi, abi_type)
    assert abi_registry.signatures[abi_type] == {'transfer': 'transfer()'}
    assert 'a9059cbb' in abi_registry.method_selectors[abi_type]

def test_get_abi(abi_registry):
    abi_registry.abis['erc20'] = [{'name': 'transfer', 'type': 'function', 'inputs': []}]
    assert abi_registry.get_abi('erc20') == [{'name': 'transfer', 'type': 'function', 'inputs': []}]

def test_get_method_selector(abi_registry):
    abi_registry.method_selectors['erc20'] = {'a9059cbb': 'transfer'}
    assert abi_registry.get_method_selector('a9059cbb') == 'transfer'

def test_get_function_signature(abi_registry):
    abi_registry.signatures['erc20'] = {'transfer': 'transfer()'}
    assert abi_registry.get_function_signature('erc20', 'transfer') == 'transfer()'

@pytest.mark.asyncio
async def test_update_abi(abi_registry):
    abi_type = 'erc20'
    new_abi = [{'name': 'transfer', 'type': 'function', 'inputs': []}]
    await abi_registry.update_abi(abi_type, new_abi)
    assert abi_registry.abis[abi_type] == new_abi
    assert abi_registry.signatures[abi_type] == {'transfer': 'transfer()'}
    assert 'a9059cbb' in abi_registry.method_selectors[abi_type]
