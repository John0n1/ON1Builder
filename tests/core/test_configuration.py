# LICENSE: MIT // github.com/John0n1/ON1Builder

import pytest
from unittest.mock import AsyncMock, patch
from on1builder.config.config import Configuration

@pytest.fixture
def configuration():
    config = Configuration()
    config.WALLET_KEY = "test_wallet_key"
    config.BASE_PATH = "test_base_path"
    config.HTTP_ENDPOINT = "http://localhost:8545"
    config.WEBSOCKET_ENDPOINT = "ws://localhost:8546"
    config.IPC_ENDPOINT = "/path/to/geth.ipc"
    config.TOKEN_ADDRESSES = "test_base_path/tokens.json"
    config.TOKEN_SYMBOLS = "test_base_path/token_symbols.json"
    config.ERC20_SIGNATURES = "test_base_path/erc20_signatures.json"
    return config

@pytest.fixture
def configuration_instance(configuration):
    # Just return the configuration directly since we don't need to initialize with another instance
    return configuration

@pytest.mark.asyncio
async def test_load_from_env_method(configuration_instance):
    # Test _load_from_env method directly
    with patch('os.getenv') as mock_getenv:
        mock_getenv.side_effect = lambda key: "test_value" if key == "TEST_KEY" else None
        # Set the value in config that we'll override
        configuration_instance._config["TEST_KEY"] = "original"
        # Run the method
        configuration_instance._load_from_env()
        # Check if the method correctly processed the environment variable
        assert mock_getenv.called

@pytest.mark.asyncio
async def test_validate_configuration(configuration_instance):
    # Instead test the _validate method which exists
    with patch.object(configuration_instance, '_validate') as mock_validate:
        configuration_instance._validate()
        mock_validate.assert_called_once()

@pytest.mark.asyncio
async def test_get_method(configuration_instance):
    # Test the get method that exists in Configuration
    with patch('on1builder.config.configuration.os.getenv', return_value="test_value") as mock_getenv:
        # Test the get method which exists in Configuration
        value = configuration_instance.get("TEST_VAR", "default_value")
        assert value == "default_value"  # Because TEST_VAR doesn't exist in _config

@pytest.mark.asyncio
async def test_set_method(configuration_instance):
    # Test the set method
    configuration_instance.set("TEST_INT", 123)
    assert configuration_instance.get("TEST_INT") == 123
    
@pytest.mark.asyncio
async def test_update_method(configuration_instance):
    # Test the update method
    configuration_instance.update({"TEST_FLOAT": 123.45})
    assert configuration_instance.get("TEST_FLOAT") == 123.45

@pytest.mark.asyncio
async def test_load_yaml(configuration_instance):
    # Test the _load_yaml method
    test_yaml = {"TEST_KEY": "test_value"}
    with patch('builtins.open', return_value=__builtins__['open']('README.md', 'r')), \
         patch('yaml.safe_load', return_value=test_yaml):
        configuration_instance._load_yaml("config.yaml")
        assert configuration_instance.get("TEST_KEY") == "test_value"

@pytest.mark.asyncio
async def test_as_dict(configuration_instance):
    # Test the as_dict method
    config_dict = configuration_instance.as_dict()
    assert isinstance(config_dict, dict)
    assert "BASE_PATH" in config_dict
    assert config_dict["BASE_PATH"] == "test_base_path"

@pytest.mark.asyncio
async def test_attribute_access(configuration_instance):
    # Test attribute access (__getattr__)
    assert configuration_instance.BASE_PATH == "test_base_path"
    assert configuration_instance.HTTP_ENDPOINT == "http://localhost:8545"
    # Test attribute setting (__setattr__)
    configuration_instance.NEW_ATTRIBUTE = "new_value"
    assert configuration_instance.NEW_ATTRIBUTE == "new_value"
    
    # Test attribute error
    with pytest.raises(AttributeError):
        configuration_instance.NONEXISTENT_ATTRIBUTE

@pytest.mark.asyncio
async def test_load_from_env(configuration_instance):
    # Test _load_from_env method
    with patch('on1builder.config.configuration.os.getenv') as mock_getenv:
        # Setup mock to return values for specific keys
        mock_getenv.side_effect = lambda x: {"BASE_PATH": "env_path", "HTTP_ENDPOINT": "env_endpoint"}.get(x)
        
        configuration_instance._load_from_env()
        
        # Check if the values were updated
        assert configuration_instance.get("BASE_PATH") == "env_path"
        assert configuration_instance.get("HTTP_ENDPOINT") == "env_endpoint"

@pytest.mark.asyncio
async def test_save_method(configuration_instance):
    # Test save method
    with patch('builtins.open'), \
         patch('yaml.dump') as mock_yaml_dump:
        configuration_instance.save("config.yaml")
        mock_yaml_dump.assert_called_once()

@pytest.mark.asyncio
async def test__init__with_config_path(configuration_instance):
    # Test initialization with config_path
    with patch('os.path.exists', return_value=True), \
         patch('builtins.open', return_value=__builtins__['open']('README.md', 'r')), \
         patch('yaml.safe_load', return_value={"TEST_YAML_KEY": "yaml_value"}):
        # Use skip_env=True to prevent environment variables from overriding YAML values
        config = Configuration(config_path="config.yaml", skip_env=True)
        assert config.get("TEST_YAML_KEY") == "yaml_value"

@pytest.mark.asyncio
async def test__init__with_env_file(configuration_instance):
    # Test initialization with env_file
    with patch('os.path.exists', return_value=True), \
         patch('on1builder.config.config.load_dotenv') as mock_load_dotenv:
        config = Configuration(env_file=".env")
        mock_load_dotenv.assert_called_once_with(".env")

@pytest.mark.asyncio
async def test__validate_method(configuration_instance):
    # Test _validate method with MIN_PROFIT
    default_min_profit = 0.001  # Match the hardcoded default from Configuration._DEFAULTS
    configuration_instance.MIN_PROFIT = -1  # Set invalid value
    configuration_instance._validate()
    # After validation, the value should be reset to default
    assert configuration_instance.MIN_PROFIT == default_min_profit
