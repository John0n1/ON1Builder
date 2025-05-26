"""
Implementation of Telegram notification functionality and tests for the notification system
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import aiohttp

from on1builder.utils.notifications import NotificationManager, get_notification_manager


class MockResponse:
    def __init__(self, status, json_data):
        self.status = status
        self._json_data = json_data

    async def json(self):
        return self._json_data

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def __aenter__(self):
        return self


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    config = MagicMock()
    config.DISCORD_WEBHOOK_URL = "https://discord.webhook/test"
    config.TELEGRAM_BOT_TOKEN = "telegram_token"
    config.TELEGRAM_CHAT_ID = "telegram_chat_id"
    config.SLACK_WEBHOOK_URL = "https://slack.webhook/test"
    config.EMAIL_FROM = "test@example.com"
    config.EMAIL_TO = "admin@example.com"
    config.EMAIL_SMTP_SERVER = "smtp.example.com"
    config.EMAIL_SMTP_PORT = 587
    config.EMAIL_USERNAME = "username"
    config.EMAIL_PASSWORD = "password"
    config.NOTIFICATION_CHANNELS = ["discord", "telegram", "slack", "email"]
    config.MIN_NOTIFICATION_LEVEL = "INFO"
    return config


@pytest.fixture
def notification_manager(mock_config):
    """Create a notification manager with the mock config."""
    with patch('on1builder.utils.notifications.aiohttp.ClientSession') as mock_session:
        manager = NotificationManager(mock_config)
        manager.session = mock_session()
        yield manager


@pytest.mark.asyncio
async def test_send_telegram_notification(notification_manager):
    """Test sending a Telegram notification."""
    # Create mock for Telegram API response
    mock_response = MockResponse(200, {"ok": True, "result": {"message_id": 123}})
    
    # Configure the mock session to return our mock response
    notification_manager.session.post = AsyncMock(return_value=mock_response)
    
    # Call the method under test
    message = "Test notification message"
    result = await notification_manager._send_telegram(message)
    
    # Check that the telegram API was called correctly
    notification_manager.session.post.assert_called_once()
    call_args = notification_manager.session.post.call_args[0][0]
    assert "telegram" in call_args
    assert notification_manager.config.TELEGRAM_BOT_TOKEN in call_args
    
    # Verify the result indicates success
    assert result is True


@pytest.mark.asyncio
async def test_send_telegram_notification_failure(notification_manager):
    """Test handling of failed Telegram notification."""
    # Create mock for Telegram API error response
    mock_response = MockResponse(400, {"ok": False, "description": "Bad Request"})
    
    # Configure the mock session to return our mock response
    notification_manager.session.post = AsyncMock(return_value=mock_response)
    
    # Call the method under test
    message = "Test notification message"
    result = await notification_manager._send_telegram(message)
    
    # Verify the result indicates failure
    assert result is False


@pytest.mark.asyncio
async def test_send_notification_all_channels(notification_manager):
    """Test sending notifications to all configured channels."""
    # Mock all notification methods
    with patch.object(notification_manager, '_send_discord', return_value=True) as mock_discord, \
         patch.object(notification_manager, '_send_slack', return_value=True) as mock_slack, \
         patch.object(notification_manager, '_send_telegram', return_value=True) as mock_telegram, \
         patch.object(notification_manager, '_send_email', return_value=True) as mock_email:
        
        # Call the send_notification method
        message = "Test notification to all channels"
        level = "INFO"
        result = await notification_manager.send_notification(message, level=level)
        
        # Verify all channels were used
        mock_discord.assert_called_once_with(message)
        mock_slack.assert_called_once_with(message)
        mock_telegram.assert_called_once_with(message)
        mock_email.assert_called_once_with(message, f"[{level}] ON1Builder Notification")
        
        # All channels succeeded so result should be True
        assert result is True


@pytest.mark.asyncio
async def test_send_notification_level_filtering(notification_manager):
    """Test that notifications are filtered by level."""
    # Set MIN_NOTIFICATION_LEVEL to WARNING
    notification_manager.config.MIN_NOTIFICATION_LEVEL = "WARNING"
    
    # Mock notification methods
    with patch.object(notification_manager, '_send_discord') as mock_discord, \
         patch.object(notification_manager, '_send_slack') as mock_slack, \
         patch.object(notification_manager, '_send_telegram') as mock_telegram, \
         patch.object(notification_manager, '_send_email') as mock_email:
        
        # Send INFO level message (should be ignored)
        message = "This is an info message"
        await notification_manager.send_notification(message, level="INFO")
        
        # None of the send methods should be called
        mock_discord.assert_not_called()
        mock_slack.assert_not_called()
        mock_telegram.assert_not_called()
        mock_email.assert_not_called()
        
        # Send WARNING level message (should be sent)
        message = "This is a warning message"
        await notification_manager.send_notification(message, level="WARNING")
        
        # All send methods should be called
        mock_discord.assert_called_once()
        mock_slack.assert_called_once()
        mock_telegram.assert_called_once()
        mock_email.assert_called_once()


@pytest.mark.asyncio
async def test_get_notification_manager_with_custom_config():
    """Test getting notification manager with custom config."""
    custom_config = MagicMock()
    custom_config.NOTIFICATION_CHANNELS = ["email"]
    
    with patch('on1builder.utils.notifications.NotificationManager') as mock_notification_class:
        manager = get_notification_manager(custom_config)
        
        # NotificationManager should be instantiated with our custom config
        mock_notification_class.assert_called_once_with(custom_config)
        assert manager == mock_notification_class.return_value
