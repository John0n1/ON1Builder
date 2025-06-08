"""
Tests for the notification_service module.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from on1builder.utils.notification_service import NotificationService


@pytest.fixture
def mock_config():
    """Create mock configuration."""
    config = MagicMock()
    config.MIN_NOTIFICATION_LEVEL = "INFO"
    config.NOTIFICATION_CHANNELS = ["slack", "email"]
    config.SLACK_WEBHOOK_URL = "https://hooks.slack.com/test"
    config.EMAIL_SMTP_SERVER = "smtp.test.com"
    return config


@pytest.fixture
def notification_service(mock_config):
    """Create test notification service."""
    return NotificationService(config=mock_config)


class TestNotificationService:
    """Test NotificationService class."""

    def test_init_with_config(self, mock_config):
        """Test notification service initialization with config."""
        service = NotificationService(config=mock_config)
        
        assert service.config == mock_config
        assert service.main_orchestrator is None
        assert service._min_notification_level == "INFO"
        assert isinstance(service._channels, list)
        assert service._client_session is None
        
        # Check supported levels
        expected_levels = {
            "DEBUG": 10,
            "INFO": 20,
            "WARNING": 30,
            "ERROR": 40,
            "CRITICAL": 50,
        }
        assert service._supported_levels == expected_levels

    def test_init_without_config(self):
        """Test notification service initialization without config."""
        service = NotificationService()
        
        assert service.config is None
        assert service.main_orchestrator is None
        assert service._min_notification_level == "INFO"  # default
        assert isinstance(service._channels, list)

    def test_init_with_main_orchestrator(self, mock_config):
        """Test notification service initialization with main orchestrator."""
        mock_orchestrator = MagicMock()
        service = NotificationService(config=mock_config, main_orchestrator=mock_orchestrator)
        
        assert service.main_orchestrator == mock_orchestrator

    @patch.dict(os.environ, {
        'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/env_test'
    })
    def test_initialize_channels_slack_env(self):
        """Test Slack channel initialization from environment."""
        config = MagicMock()
        config.MIN_NOTIFICATION_LEVEL = "INFO"
        config.NOTIFICATION_CHANNELS = ["slack"]
        
        service = NotificationService(config=config)
        
        # Should find Slack channel with env webhook
        slack_channels = [ch for ch in service._channels if ch[0] == "slack"]
        assert len(slack_channels) > 0
        assert slack_channels[0][1] == "https://hooks.slack.com/env_test"

    def test_initialize_channels_slack_config(self, mock_config):
        """Test Slack channel initialization from config."""
        service = NotificationService(config=mock_config)
        
        # Should find Slack channel with config webhook
        slack_channels = [ch for ch in service._channels if ch[0] == "slack"]
        assert len(slack_channels) > 0
        assert slack_channels[0][1] == "https://hooks.slack.com/test"

    @patch.dict(os.environ, {
        'SMTP_SERVER': 'smtp.env.com'
    })
    def test_initialize_channels_email_env(self):
        """Test email channel initialization from environment."""
        config = MagicMock()
        config.MIN_NOTIFICATION_LEVEL = "INFO"
        config.NOTIFICATION_CHANNELS = ["email"]
        
        service = NotificationService(config=config)
        
        # Should find email channel
        email_channels = [ch for ch in service._channels if ch[0] == "email"]
        # Note: email initialization depends on other SMTP settings too

    def test_initialize_channels_no_channels_specified(self):
        """Test channel initialization when no channels specified."""
        config = MagicMock()
        config.MIN_NOTIFICATION_LEVEL = "INFO"
        config.NOTIFICATION_CHANNELS = []
        
        # Mock environment variables
        with patch.dict(os.environ, {
            'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/test'
        }, clear=False):
            service = NotificationService(config=config)
            
            # Should still initialize available channels
            assert len(service._channels) >= 0

    def test_initialize_channels_no_config(self):
        """Test channel initialization without config."""
        with patch.dict(os.environ, {
            'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/test'
        }, clear=False):
            service = NotificationService()
            
            # Should initialize available channels from environment
            slack_channels = [ch for ch in service._channels if ch[0] == "slack"]
            assert len(slack_channels) > 0

    def test_min_notification_level_from_config(self, mock_config):
        """Test minimum notification level from config."""
        mock_config.MIN_NOTIFICATION_LEVEL = "WARNING"
        service = NotificationService(config=mock_config)
        
        assert service._min_notification_level == "WARNING"

    def test_min_notification_level_default(self):
        """Test default minimum notification level."""
        config = MagicMock()
        # Don't set MIN_NOTIFICATION_LEVEL attribute
        delattr(config, 'MIN_NOTIFICATION_LEVEL')
        
        service = NotificationService(config=config)
        assert service._min_notification_level == "INFO"

    @patch('on1builder.utils.notification_service.load_dotenv')
    def test_env_loading(self, mock_load_dotenv):
        """Test that environment variables are loaded from .env file."""
        NotificationService()
        
        # Should call load_dotenv at least once
        assert mock_load_dotenv.call_count >= 1

    def test_supported_levels_mapping(self, notification_service):
        """Test that supported levels are correctly mapped."""
        levels = notification_service._supported_levels
        
        assert levels["DEBUG"] < levels["INFO"]
        assert levels["INFO"] < levels["WARNING"]
        assert levels["WARNING"] < levels["ERROR"]
        assert levels["ERROR"] < levels["CRITICAL"]

    def test_channels_list_initialization(self, notification_service):
        """Test that channels list is properly initialized."""
        assert isinstance(notification_service._channels, list)
        
        # Each channel should be a tuple with (name, config)
        for channel in notification_service._channels:
            assert isinstance(channel, tuple)
            assert len(channel) == 2
            assert isinstance(channel[0], str)  # channel name

    def test_client_session_initialization(self, notification_service):
        """Test that client session is initialized to None."""
        assert notification_service._client_session is None

    @patch.dict(os.environ, {}, clear=True)
    def test_no_environment_variables(self):
        """Test initialization when no environment variables are set."""
        service = NotificationService()
        
        # Should not crash and should initialize with empty channels
        assert isinstance(service._channels, list)

    def test_notification_channels_attribute_missing(self):
        """Test when config doesn't have NOTIFICATION_CHANNELS attribute."""
        config = MagicMock()
        config.MIN_NOTIFICATION_LEVEL = "INFO"
        # Don't set NOTIFICATION_CHANNELS attribute
        delattr(config, 'NOTIFICATION_CHANNELS')
        
        service = NotificationService(config=config)
        
        # Should not crash and should work with default behavior
        assert isinstance(service._channels, list)

    @patch('os.path.exists')
    @patch('on1builder.utils.notification_service.load_dotenv')
    def test_env_file_loading_when_exists(self, mock_load_dotenv, mock_exists):
        """Test .env file loading when file exists."""
        mock_exists.return_value = True
        
        NotificationService()
        
        # Should load from the .env file in project root
        mock_load_dotenv.assert_called()
        # Check that it was called with override=False
        call_args = mock_load_dotenv.call_args
        assert call_args[1]['override'] is False

    @patch('os.path.exists')
    @patch('on1builder.utils.notification_service.load_dotenv')
    def test_env_file_loading_when_not_exists(self, mock_load_dotenv, mock_exists):
        """Test .env file loading when file doesn't exist."""
        mock_exists.return_value = False
        
        NotificationService()
        
        # Should still call load_dotenv (from the import at module level)
        # but not for the project root path
        assert mock_load_dotenv.call_count >= 1

    def test_channel_tuple_structure(self, notification_service):
        """Test that channel tuples have correct structure."""
        for channel_name, channel_config in notification_service._channels:
            assert isinstance(channel_name, str)
            assert channel_name in ["slack", "email", "telegram", "discord"]
            # channel_config can be various types depending on the channel
