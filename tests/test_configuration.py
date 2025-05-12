# LICENSE: MIT // github.com/John0n1/ON1Builder

import pytest
from unittest.mock import AsyncMock, patch
from scripts.python.configuration import Configuration

@pytest.fixture
def configuration():
    config = Configuration()
    config.WALLET_KEY = "test_wallet_key"
    config.BASE_PATH = "test_base_path"
    config.HTTP_ENDPOINT = "http://localhost:8545"
    config.WEBSOCKET_ENDPOINT = "ws://localhost:8546"
    config.IPC_ENDPOINT = "/path/to/geth.ipc"
    return config

@pytest.fixture
def configuration_instance(configuration):
    return Configuration(configuration)

@pytest.mark.asyncio
async def test_load_env(configuration_instance):
    with patch('scripts.python.configuration.dotenv.load_dotenv') as mock_load_dotenv:
        configuration_instance._load_env()
        mock_load_dotenv.assert_called_once_with(dotenv_path=configuration_instance.env_path)

@pytest.mark.asyncio
async def test_validate_ethereum_address(configuration_instance):
    valid_address = "0x0000000000000000000000000000000000000000"
    invalid_address = "0xInvalidAddress"
    with pytest.raises(ValueError):
        configuration_instance._validate_ethereum_address(invalid_address, "TEST_VAR")
    assert configuration_instance._validate_ethereum_address(valid_address, "TEST_VAR") == valid_address

@pytest.mark.asyncio
async def test_get_env_str(configuration_instance):
    with patch('python.configuration.os.getenv', return_value="test_value") as mock_getenv:
        value = configuration_instance._get_env_str("TEST_VAR", "default_value", "Test Description")
        assert value == "test_value"
        mock_getenv.assert_called_once_with("TEST_VAR", "default_value")

@pytest.mark.asyncio
async def test_get_env_int(configuration_instance):
    with patch('python.configuration.os.getenv', return_value="123") as mock_getenv:
        value = configuration_instance._get_env_int("TEST_VAR", 456, "Test Description")
        assert value == 123
        mock_getenv.assert_called_once_with("TEST_VAR")

@pytest.mark.asyncio
async def test_get_env_float(configuration_instance):
    with patch('python.configuration.os.getenv', return_value="123.45") as mock_getenv:
        value = configuration_instance._get_env_float("TEST_VAR", 456.78, "Test Description")
        assert value == 123.45
        mock_getenv.assert_called_once_with("TEST_VAR")

@pytest.mark.asyncio
async def test_resolve_path(configuration_instance):
    with patch('python.configuration.os.getenv', return_value="test_path") as mock_getenv, \
         patch('python.configuration.Path.exists', return_value=True) as mock_exists:
        path = configuration_instance._resolve_path("TEST_PATH_VAR", "Test Description")
        assert path == configuration_instance.BASE_PATH / "test_path"
        mock_getenv.assert_called_once_with("TEST_PATH_VAR", None)
        mock_exists.assert_called_once()

@pytest.mark.asyncio
async def test_load_json_safe(configuration_instance):
    test_path = configuration_instance.BASE_PATH / "test.json"
    test_data = {"key": "value"}
    with patch('python.configuration.aiofiles.open', new_callable=AsyncMock) as mock_open, \
         patch('python.configuration.json.loads', return_value=test_data) as mock_json_loads:
        mock_open.return_value.__aenter__.return_value.read.return_value = '{"key": "value"}'
        data = await configuration_instance._load_json_safe(test_path, "Test Description")
        assert data == test_data
        mock_open.assert_called_once_with(test_path, 'r')
        mock_json_loads.assert_called_once_with('{"key": "value"}')

@pytest.mark.asyncio
async def test_get_token_addresses(configuration_instance):
    test_data = {"0xTokenAddress": "TokenSymbol"}
    with patch.object(configuration_instance, '_load_json_safe', return_value=test_data) as mock_load_json_safe:
        addresses = await configuration_instance.get_token_addresses()
        assert addresses == ["0xTokenAddress"]
        mock_load_json_safe.assert_called_once_with(configuration_instance.TOKEN_ADDRESSES, "monitored tokens")

@pytest.mark.asyncio
async def test_get_token_symbols(configuration_instance):
    test_data = {"0xTokenAddress": "TokenSymbol"}
    with patch.object(configuration_instance, '_load_json_safe', return_value=test_data) as mock_load_json_safe:
        symbols = await configuration_instance.get_token_symbols()
        assert symbols == test_data
        mock_load_json_safe.assert_called_once_with(configuration_instance.TOKEN_SYMBOLS, "token symbols")

@pytest.mark.asyncio
async def test_get_erc20_signatures(configuration_instance):
    test_data = {"function_name": "selector"}
    with patch.object(configuration_instance, '_load_json_safe', return_value=test_data) as mock_load_json_safe:
        signatures = await configuration_instance.get_erc20_signatures()
        assert signatures == test_data
        mock_load_json_safe.assert_called_once_with(configuration_instance.ERC20_SIGNATURES, "ERC20 function signatures")

@pytest.mark.asyncio
async def test_get_config_value(configuration_instance):
    configuration_instance.TEST_VAR = "test_value"
    value = configuration_instance.get_config_value("TEST_VAR", "default_value")
    assert value == "test_value"

@pytest.mark.asyncio
async def test_get_all_config_values(configuration_instance):
    config_values = configuration_instance.get_all_config_values()
    assert isinstance(config_values, dict)
    assert "WALLET_KEY" in config_values

@pytest.mark.asyncio
async def test_load_abi_from_path(configuration_instance):
    test_path = configuration_instance.BASE_PATH / "test_abi.json"
    test_data = [{"name": "function", "type": "function"}]
    with patch('python.configuration.aiofiles.open', new_callable=AsyncMock) as mock_open, \
         patch('python.configuration.json.loads', return_value=test_data) as mock_json_loads:
        mock_open.return_value.__aenter__.return_value.read.return_value = '[{"name": "function", "type": "function"}]'
        abi = await configuration_instance.load_abi_from_path(test_path)
        assert abi == test_data
        mock_open.assert_called_once_with(test_path, 'r')
        mock_json_loads.assert_called_once_with('[{"name": "function", "type": "function"}]')

@pytest.mark.asyncio
async def test_load(configuration_instance):
    with patch.object(configuration_instance, '_create_required_directories', new_callable=AsyncMock) as mock_create_dirs, \
         patch.object(configuration_instance, '_load_critical_abis', new_callable=AsyncMock) as mock_load_abis, \
         patch.object(configuration_instance, '_validate_api_keys', new_callable=AsyncMock) as mock_validate_keys, \
         patch.object(configuration_instance, '_validate_addresses', new_callable=AsyncMock) as mock_validate_addresses:
        await configuration_instance.load()
        mock_create_dirs.assert_called_once()
        mock_load_abis.assert_called_once()
        mock_validate_keys.assert_called_once()
        mock_validate_addresses.assert_called_once()

@pytest.mark.asyncio
async def test_create_required_directories(configuration_instance):
    with patch('python.configuration.os.makedirs') as mock_makedirs:
        configuration_instance._create_required_directories()
        assert mock_makedirs.call_count == 3

@pytest.mark.asyncio
async def test_load_critical_abis(configuration_instance):
    with patch.object(configuration_instance, '_resolve_path', return_value="test_path") as mock_resolve_path:
        await configuration_instance._load_critical_abis()
        assert mock_resolve_path.call_count == 6

@pytest.mark.asyncio
async def test_validate_api_keys(configuration_instance):
    with patch('python.configuration.aiohttp.ClientSession') as mock_session:
        mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value.json.return_value = {"result": "success"}
        await configuration_instance._validate_api_keys()
        assert mock_session.called

@pytest.mark.asyncio
async def test_validate_addresses(configuration_instance):
    with patch.object(configuration_instance, '_validate_ethereum_address', return_value="0xValidAddress") as mock_validate_address:
        configuration_instance.WALLET_ADDRESS = "0xValidAddress"
        configuration_instance._validate_addresses()
        mock_validate_address.assert_called_once_with("0xValidAddress", "WALLET_ADDRESS")
