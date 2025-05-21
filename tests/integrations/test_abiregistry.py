# LICENSE: MIT // github.com/John0n1/ON1Builder

import pytest
import hashlib
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from on1builder.integrations.abi_registry import ABIRegistry

@pytest.fixture
def test_base_path():
    return Path(__file__).parent.parent

@pytest.fixture
def abi_registry():
    # Reset shared state to avoid test interference
    ABIRegistry._GLOBAL_ABIS = {}
    ABIRegistry._GLOBAL_SIG_MAP = {}
    ABIRegistry._GLOBAL_SELECTOR_MAP = {}
    ABIRegistry._FILE_HASH = {}
    ABIRegistry._initialized = False
    return ABIRegistry()

@pytest.mark.asyncio
async def test_initialize(abi_registry, test_base_path):
    with patch('on1builder.integrations.abi_registry.ABIRegistry._load_all', new_callable=AsyncMock) as mock_load_all:
        await abi_registry.initialize(test_base_path)
        mock_load_all.assert_called_once()
        assert abi_registry._initialized is True

@pytest.mark.asyncio
async def test_load_single(abi_registry):
    abi_type = 'erc20'
    abi_path = Path('tests/abi/erc20_abi.json')
    
    # Create a mock file
    mock_file_content = '[{"name": "transfer", "type": "function", "inputs": []}]'
    
    # We need to patch file_path.exists() directly rather than replacing Path itself
    with patch.object(Path, 'exists', return_value=True):
        with patch.object(Path, 'read_text', return_value=mock_file_content):
            with patch.object(Path, 'read_bytes', return_value=mock_file_content.encode()):
                with patch('on1builder.integrations.abi_registry.ABIRegistry._validate_schema') as mock_validate:
                    with patch('on1builder.integrations.abi_registry.ABIRegistry._extract_maps') as mock_extract:
                        mock_extract.return_value = ({"transfer": "transfer()"}, {"a9059cbb": "transfer"})
                        
                        # Simulate file hash
                        file_hash = hashlib.md5(mock_file_content.encode()).hexdigest()
                        
                        result = await abi_registry._load_single(abi_type, abi_path)
                        
                        assert result is True
                        mock_validate.assert_called_once()
                        mock_extract.assert_called_once()
                        assert ABIRegistry._GLOBAL_ABIS.get(abi_type) == [{'name': 'transfer', 'type': 'function', 'inputs': []}]
                        assert ABIRegistry._FILE_HASH.get(abi_type) == file_hash

def test_validate_schema(abi_registry):
    # Valid ABI
    valid_abi = [{'type': 'function', 'name': 'transfer', 'inputs': []}]
    abi_type = 'erc20'
    # Should not raise an exception
    ABIRegistry._validate_schema(valid_abi, abi_type)
    
    # Invalid ABI (not a list)
    import pytest
    from on1builder.integrations.abi_registry import ABIValidationError
    invalid_abi = {'type': 'function', 'name': 'transfer'}
    with pytest.raises(ABIValidationError):
        ABIRegistry._validate_schema(invalid_abi, abi_type)
    
    # Invalid ABI (entry missing type)
    invalid_abi = [{'name': 'transfer'}]
    with pytest.raises(ABIValidationError):
        ABIRegistry._validate_schema(invalid_abi, abi_type)

def test_extract_maps(abi_registry):
    abi = [{'name': 'transfer', 'type': 'function', 'inputs': [{'type': 'address'}]}]
    
    with patch('web3.Web3.keccak', return_value=bytes.fromhex('a9059cbb0000')):
        sig_map, selector_map = ABIRegistry._extract_maps(abi)
        assert sig_map == {'transfer': 'transfer(address)'}
        assert selector_map == {'a9059cbb': 'transfer'}

def test_get_abi(abi_registry):
    # Setup
    ABIRegistry._GLOBAL_ABIS['erc20'] = [{'name': 'transfer', 'type': 'function', 'inputs': []}]
    
    # Test with mocked _maybe_reload_if_changed to avoid file system interactions
    with patch.object(abi_registry, '_maybe_reload_if_changed'):
        assert abi_registry.get_abi('erc20') == [{'name': 'transfer', 'type': 'function', 'inputs': []}]

def test_get_method_selector(abi_registry):
    # Setup global state
    ABIRegistry._REGISTRY_HASH = "test_hash"
    selector = "a9059cbb"
    
    # Use patch to bypass the LRU cache function
    with patch('on1builder.integrations.abi_registry._selector_to_name_lru') as mock_cache:
        mock_cache.return_value = "transfer"
        
        # Call the method
        result = abi_registry.get_method_selector(selector)
        
        # Verify
        assert result == "transfer"
        assert abi_registry.lookup_count == 1
        assert abi_registry.cache_hit_count == 1
        mock_cache.assert_called_once_with((ABIRegistry._REGISTRY_HASH, selector))

def test_get_function_signature(abi_registry):
    # Setup
    ABIRegistry._GLOBAL_SIG_MAP['erc20'] = {'transfer': 'transfer()'}
    
    # Test with mocked _maybe_reload_if_changed
    with patch.object(abi_registry, '_maybe_reload_if_changed'):
        assert abi_registry.get_function_signature('erc20', 'transfer') == 'transfer()'

@pytest.mark.asyncio
async def test_is_healthy(abi_registry):
    # Test when erc20 ABI is not available
    ABIRegistry._GLOBAL_ABIS = {}
    assert await abi_registry.is_healthy() is False
    
    # Test when erc20 ABI is available
    ABIRegistry._GLOBAL_ABIS['erc20'] = [{'name': 'transfer', 'type': 'function', 'inputs': []}]
    assert await abi_registry.is_healthy() is True

@pytest.mark.asyncio
async def test_load_all(abi_registry):
    test_abi_dir = Path('test_abi_dir')
    mock_file_paths = [
        Path('test_abi_dir/erc20.json'),
        Path('test_abi_dir/uniswap.json')
    ]
    
    with patch('pathlib.Path.glob', return_value=mock_file_paths):
        with patch.object(abi_registry, '_load_single', new_callable=AsyncMock) as mock_load_single:
            # Setup mock returns
            mock_load_single.side_effect = [True, True]
            
            # Call the method
            await abi_registry._load_all(test_abi_dir)
            
            # Verify
            assert mock_load_single.call_count == 2
            mock_load_single.assert_any_call('erc20', mock_file_paths[0])
            mock_load_single.assert_any_call('uniswap', mock_file_paths[1])

@pytest.mark.asyncio
async def test_maybe_reload_if_changed(abi_registry):
    abi_type = 'erc20'
    
    # Setup
    ABIRegistry._GLOBAL_ABIS = {abi_type: []}
    ABIRegistry._FILE_HASH = {abi_type: 'old_hash'}
    
    with patch('pathlib.Path.exists', return_value=True):
        with patch('pathlib.Path.read_bytes') as mock_read_bytes:
            with patch('asyncio.create_task') as mock_create_task:
                # Setup mock to return different hash
                mock_read_bytes.return_value = b'new content'
                mock_hash = hashlib.md5(b'new content').hexdigest()
                
                # Test the method
                abi_registry._maybe_reload_if_changed(abi_type)
                
                # Verify task was created to reload
                assert mock_create_task.call_count == 1
                assert abi_registry.reload_count == 1

@pytest.mark.asyncio
async def test_get_registry():
    from on1builder.integrations.abi_registry import get_registry
    
    # Test with specified base_path
    test_path = Path('/test/path')
    with patch('on1builder.integrations.abi_registry.ABIRegistry.initialize', new_callable=AsyncMock) as mock_init:
        mock_init.return_value = None  # Ensure the coroutine returns None
        registry = await get_registry(test_path)
        mock_init.assert_called_once_with(test_path)
        assert registry is not None
        
    # Reset module variable
    import on1builder.integrations.abi_registry
    on1builder.integrations.abi_registry._default_registry = None
    
    # Test with default base_path
    with patch('on1builder.integrations.abi_registry.ABIRegistry.initialize', new_callable=AsyncMock) as mock_init:
        mock_init.return_value = None  # Ensure the coroutine returns None
        with patch('pathlib.Path.parent', return_value=Path('/default/path')):
            registry = await get_registry()
            mock_init.assert_called_once()
            assert registry is not None
