#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder - Notification System
===============================

Provides utilities for sending notifications and alerts through various channels.
==========================
License: MIT
=========================

This file is part of the ON1Builder project, which is licensed under the MIT License.
see https://opensource.org/licenses/MIT or https://github.com/John0n1/ON1Builder/blob/master/LICENSE
"""

import asyncio
import json
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import aiohttp
from dotenv import load_dotenv

from on1builder.utils.logger import get_logger
logger = get_logger(__name__)

# Load environment variables from .env file
load_dotenv()


class NotificationManager:
    """Manages sending notifications through various channels.

    Supported channels:
    - Slack
    - Email
    - Telegram
    - Discord
    - Console logging
    """

    def __init__(self, config=None, main_core=None):
        """Initialize the notification manager.

        Args:
            config: Configuration object containing notification settings
            main_core: Optional reference to MainCore for shared resources
        """
        # Always load .env from project root if config is not provided or missing values
        root_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
        if os.path.exists(root_env_path):
            load_dotenv(dotenv_path=root_env_path, override=False)

        self.config = config
        self.main_core = main_core
        self._channels: List[Tuple[str, Any]] = []
        self._min_notification_level = "INFO"  # Default level
        self._client_session = None
        self._supported_levels = {
            "DEBUG": 10,
            "INFO": 20,
            "WARNING": 30,
            "ERROR": 40, 
            "CRITICAL": 50
        }
        self._initialize_channels()


    def _initialize_channels(self):
        """Initialize notification channels based on configuration."""
        # Get minimum notification level
        if self.config and hasattr(self.config, "MIN_NOTIFICATION_LEVEL"):
            self._min_notification_level = self.config.MIN_NOTIFICATION_LEVEL

        # Initialize only channels specified in config
        notification_channels = []
        if self.config and hasattr(self.config, "NOTIFICATION_CHANNELS"):
            notification_channels = self.config.NOTIFICATION_CHANNELS

        # Initialize Slack if webhook URL is available and channel is enabled
        if "slack" in notification_channels or not notification_channels:
            slack_webhook = os.environ.get("SLACK_WEBHOOK_URL") or (
                getattr(self.config, "SLACK_WEBHOOK_URL", None) if self.config else None
            )
            if slack_webhook:
                self._channels.append(("slack", slack_webhook))
                logger.info("Slack notifications enabled")

        # Initialize Email if SMTP settings are available and channel is enabled
        if "email" in notification_channels or not notification_channels:
            smtp_server = os.environ.get("SMTP_SERVER") or (
                getattr(self.config, "EMAIL_SMTP_SERVER", None) if self.config else None
            )
            smtp_port = os.environ.get("SMTP_PORT") or (
                getattr(self.config, "EMAIL_SMTP_PORT", None) if self.config else None
            )
            smtp_username = os.environ.get("SMTP_USERNAME") or (
                getattr(self.config, "EMAIL_USERNAME", None) if self.config else None
            )
            smtp_password = os.environ.get("SMTP_PASSWORD") or (
                getattr(self.config, "EMAIL_PASSWORD", None) if self.config else None
            )
            alert_email = os.environ.get("ALERT_EMAIL") or (
                getattr(self.config, "EMAIL_TO", None) if self.config else None
            )

            if all([smtp_server, smtp_port, smtp_username, smtp_password, alert_email]):
                self._channels.append(
                    (
                        "email", 
                        {
                            "server": smtp_server,
                            "port": int(smtp_port),
                            "username": smtp_username,
                            "password": smtp_password,
                            "to_email": alert_email,
                            "from_email": smtp_username,
                        }
                    )
                )
                logger.info("Email notifications enabled")

        # Initialize Telegram if bot token and chat ID are available and channel is enabled
        if "telegram" in notification_channels or not notification_channels:
            telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN") or (
                getattr(self.config, "TELEGRAM_BOT_TOKEN", None) if self.config else None
            )
            telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID") or (
                getattr(self.config, "TELEGRAM_CHAT_ID", None) if self.config else None
            )
            
            if telegram_token and telegram_chat_id:
                self._channels.append(
                    (
                        "telegram", 
                        {
                            "bot_token": telegram_token,
                            "chat_id": telegram_chat_id,
                        }
                    )
                )
                logger.info("Telegram notifications enabled")

        # Initialize Discord if webhook URL is available and channel is enabled
        if "discord" in notification_channels or not notification_channels:
            discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL") or (
                getattr(self.config, "DISCORD_WEBHOOK_URL", None) if self.config else None
            )
            
            if discord_webhook:
                self._channels.append(("discord", discord_webhook))
                logger.info("Discord notifications enabled")

        # Always enable console logging
        self._channels.append(("console", None))
        
        # Try to get aiohttp session from main_core if available
        if self.main_core and hasattr(self.main_core, "components"):
            api_config = self.main_core.components.get("api_config")
            if api_config and hasattr(api_config, "session"):
                self._client_session = api_config.session
                logger.debug("Using shared aiohttp session from API Config")

    def _should_send(self, level: str) -> bool:
        """Check if notification should be sent based on level."""
        if level not in self._supported_levels:
            return True  # Send if level is unknown
            
        min_level_value = self._supported_levels.get(
            self._min_notification_level.upper(), 0
        )
        current_level_value = self._supported_levels.get(level.upper(), 0)
        return current_level_value >= min_level_value

    async def send_notification(
        self, message: str, level: str = "INFO", details: Dict[str, Any] = None
    ) -> bool:
        """Send a notification through all available channels.

        Args:
            message: The notification message
            level: Notification level (INFO, WARN, ERROR)
            details: Additional details to include in the notification

        Returns:
            True if notification was sent successfully through at least one channel
        """
        # Skip if level is below minimum notification level
        if not self._should_send(level):
            return False
            
        # Normalize level
        level = level.upper()
        
        # Always log to console
        if level == "ERROR" or level == "CRITICAL":
            logger.error(message, extra=details or {})
        elif level == "WARNING" or level == "WARN":
            logger.warning(message, extra=details or {})
        else:
            logger.info(message, extra=details or {})
            
        # Return immediately if only console logging is enabled
        if len(self._channels) <= 1:
            return True
            
        # Send through all other channels
        success = False
        
        for channel, config in self._channels:
            if channel == "console":
                success = True
                continue
                
            try:
                if channel == "slack":
                    await self._send_slack(message, level, details, config)
                    success = True
                elif channel == "email":
                    await self._send_email(message, level, details, config)
                    success = True
                elif channel == "telegram":
                    await self._send_telegram(message, level, details, config)
                    success = True
                elif channel == "discord":
                    await self._send_discord(message, level, details, config)
                    success = True
            except Exception as e:
                logger.error(f"Failed to send {level} notification via {channel}: {e}")
                
        return success

    async def send_alert(
        self, message: str, level: str = "ERROR", details: Dict[str, Any] = None
    ) -> bool:
        """Send an alert (alias for send_notification with ERROR level by default).

        Args:
            message: The alert message
            level: Alert level (defaults to ERROR)
            details: Additional details to include in the alert

        Returns:
            True if alert was sent successfully
        """
        return await self.send_notification(message, level, details)
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp ClientSession for API calls."""
        if not self._client_session:
            self._client_session = aiohttp.ClientSession()
            logger.debug("Created new aiohttp ClientSession for notifications")
        return self._client_session
    
    async def _send_slack(
        self, message: str, level: str, details: Dict[str, Any], webhook_url: str
    ) -> bool:
        """Send notification to Slack using webhook URL.
        
        Args:
            message: The notification message
            level: Notification level
            details: Additional details to include
            webhook_url: Slack webhook URL
            
        Returns:
            True if successful
        """
        if not webhook_url:
            return False
            
        # Determine color based on level
        color = "#000000"  # Default
        if level == "ERROR" or level == "CRITICAL":
            color = "#FF0000"  # Red
        elif level == "WARNING" or level == "WARN":
            color = "#FFA500"  # Orange
        elif level == "INFO":
            color = "#0000FF"  # Blue
            
        # Format details as attachment field
        attachment_fields = []
        if details:
            for key, value in details.items():
                try:
                    if isinstance(value, (dict, list)):
                        value = json.dumps(value, default=str)
                    attachment_fields.append({
                        "title": key,
                        "value": str(value),
                        "short": len(str(value)) < 20
                    })
                except Exception:
                    attachment_fields.append({
                        "title": key,
                        "value": f"[Error formatting value: {type(value).__name__}]",
                        "short": True
                    })
                    
        payload = {
            "text": f"*{level}*: {message}",
            "attachments": [
                {
                    "color": color,
                    "fields": attachment_fields,
                    "footer": "ON1Builder Notification System"
                }
            ]
        }
        
        try:
            session = await self._get_session()
            async with session.post(webhook_url, json=payload) as response:
                if response.status >= 400:
                    logger.error(f"Slack notification failed: {response.status} - {await response.text()}")
                    return False
            return True
        except Exception as e:
            logger.error(f"Error sending Slack notification: {e}")
            return False

    async def _send_email(
        self, message: str, level: str, details: Dict[str, Any], config: Dict[str, Any]
    ) -> bool:
        """Send notification via email.
        
        Args:
            message: The notification message
            level: Notification level
            details: Additional details to include
            config: Email configuration parameters
            
        Returns:
            True if successful
        """
        if not config:
            return False
            
        try:
            # Create email
            msg = MIMEMultipart()
            msg["From"] = config["from_email"]
            msg["To"] = config["to_email"]
            msg["Subject"] = f"ON1Builder {level}: {message[:50]}..."
            
            # Format message with details
            body = f"{message}\n\n"
            if details:
                body += "Details:\n"
                for key, value in details.items():
                    try:
                        if isinstance(value, (dict, list)):
                            value = json.dumps(value, default=str)
                        body += f"- {key}: {value}\n"
                    except Exception:
                        body += f"- {key}: [Error formatting value]\n"
            
            msg.attach(MIMEText(body, "plain"))
            
            # Connect to SMTP server and send
            server = smtplib.SMTP(config["server"], config["port"])
            server.starttls()
            server.login(config["username"], config["password"])
            server.send_message(msg)
            server.quit()
            return True
        except Exception as e:
            logger.error(f"Error sending email notification: {e}")
            return False
            
    async def _send_telegram(
        self, message: str, level: str, details: Dict[str, Any], config: Dict[str, Any]
    ) -> bool:
        """Send notification via Telegram.
        
        Args:
            message: The notification message
            level: Notification level
            details: Additional details to include
            config: Telegram configuration parameters
            
        Returns:
            True if successful
        """
        if not config or not config.get("bot_token") or not config.get("chat_id"):
            return False
            
        # Format message with details
        formatted_msg = f"*ON1Builder {level}*\n{message}\n\n"
        if details:
            formatted_msg += "*Details:*\n"
            for key, value in details.items():
                try:
                    if isinstance(value, (dict, list)):
                        value = json.dumps(value, default=str)
                    formatted_msg += f"• `{key}`: `{value}`\n"
                except Exception:
                    formatted_msg += f"• `{key}`: [Error formatting value]\n"
                    
        # URL for Telegram Bot API
        url = f"https://api.telegram.org/bot{config['bot_token']}/sendMessage"
        payload = {
            "chat_id": config["chat_id"],
            "text": formatted_msg,
            "parse_mode": "Markdown"
        }
        
        try:
            session = await self._get_session()
            async with session.post(url, json=payload) as response:
                if response.status >= 400:
                    logger.error(f"Telegram notification failed: {response.status} - {await response.text()}")
                    return False
            return True
        except Exception as e:
            logger.error(f"Error sending Telegram notification: {e}")
            return False
            
    async def _send_discord(
        self, message: str, level: str, details: Dict[str, Any], webhook_url: str
    ) -> bool:
        """Send notification to Discord using webhook URL.
        
        Args:
            message: The notification message
            level: Notification level
            details: Additional details to include
            webhook_url: Discord webhook URL
            
        Returns:
            True if successful
        """
        if not webhook_url:
            return False
            
        # Determine color based on level
        color = 0  # Default
        if level == "ERROR" or level == "CRITICAL":
            color = 0xFF0000  # Red
        elif level == "WARNING" or level == "WARN":
            color = 0xFFA500  # Orange
        elif level == "INFO":
            color = 0x0000FF  # Blue
            
        # Format fields
        fields = []
        if details:
            for key, value in details.items():
                try:
                    if isinstance(value, (dict, list)):
                        value = json.dumps(value, default=str)
                    fields.append({
                        "name": key,
                        "value": str(value),
                        "inline": len(str(value)) < 20
                    })
                except Exception:
                    fields.append({
                        "name": key,
                        "value": f"[Error formatting value: {type(value).__name__}]",
                        "inline": True
                    })
                    
        payload = {
            "embeds": [
                {
                    "title": f"{level}: {message}",
                    "color": color,
                    "fields": fields,
                    "footer": {"text": "ON1Builder Notification System"}
                }
            ]
        }
        
        try:
            session = await self._get_session()
            async with session.post(webhook_url, json=payload) as response:
                if response.status >= 400:
                    logger.error(f"Discord notification failed: {response.status} - {await response.text()}")
                    return False
            return True
        except Exception as e:
            logger.error(f"Error sending Discord notification: {e}")
            return False
            
    async def stop(self) -> None:
        """Clean up resources when shutting down."""
        # Only close the session if we created it
        if self._client_session and self.main_core is None:
            try:
                await self._client_session.close()
                logger.debug("Closed aiohttp ClientSession for notifications")
            except Exception as e:
                logger.error(f"Error closing notification ClientSession: {e}")
                
        self._client_session = None


# Helper for accessing time (used for timestamps)
def import_time():
    """Import time module dynamically to avoid circular imports."""
    import time

    return time


# Global singleton notification manager
_notification_manager: Optional[NotificationManager] = None

def get_notification_manager(config=None, main_core=None) -> NotificationManager:
    """Get or create the global NotificationManager instance.
    
    Args:
        config: Configuration object (optional)
        main_core: Reference to MainCore (optional)
        
    Returns:
        NotificationManager instance
    """
    global _notification_manager
    
    if _notification_manager is None or (config is not None and _notification_manager.config != config):
        _notification_manager = NotificationManager(config, main_core)
        logger.debug("Created new NotificationManager instance")
        
    return _notification_manager


async def send_alert(message: str, level: str = "ERROR", details: Dict[str, Any] = None, config=None) -> bool:
    """Send an alert through the global notification manager.
    
    Args:
        message: The alert message
        level: Alert level
        details: Additional details to include
        config: Optional configuration to use
        
    Returns:
        True if alert was sent successfully
    """
    manager = get_notification_manager(config)
    return await manager.send_alert(message, level, details)
