"""
ON1Builder - Notification System
===============================

Provides utilities for sending notifications and alerts through various channels.
"""

import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import aiohttp
from typing import Dict, Any

logger = logging.getLogger("Notifications")


class NotificationManager:
    """Manages sending notifications through various channels.

    Supported channels:
    - Slack
    - Email
    - Console logging
    """

    def __init__(self, config=None):
        """Initialize the notification manager.

        Args:
            config: Configuration object containing notification settings
        """
        self.config = config
        self._channels = []
        self._initialize_channels()

    def _initialize_channels(self):
        """Initialize notification channels based on configuration."""
        # Initialize Slack if webhook URL is available
        slack_webhook = os.environ.get("SLACK_WEBHOOK_URL") or (
            self.config.get("SLACK_WEBHOOK_URL") if self.config else None
        )
        if slack_webhook:
            self._channels.append(("slack", slack_webhook))
            logger.info("Slack notifications enabled")

        # Initialize Email if SMTP settings are available
        smtp_server = os.environ.get("SMTP_SERVER") or (
            self.config.get("SMTP_SERVER") if self.config else None
        )
        smtp_port = os.environ.get("SMTP_PORT") or (
            self.config.get("SMTP_PORT") if self.config else None
        )
        smtp_username = os.environ.get("SMTP_USERNAME") or (
            self.config.get("SMTP_USERNAME") if self.config else None
        )
        smtp_password = os.environ.get("SMTP_PASSWORD") or (
            self.config.get("SMTP_PASSWORD") if self.config else None
        )
        alert_email = os.environ.get("ALERT_EMAIL") or (
            self.config.get("ALERT_EMAIL") if self.config else None
        )

        if all([smtp_server, smtp_port, smtp_username,
               smtp_password, alert_email]):
            self._channels.append(
                (
                    "email",
                    {
                        "server": smtp_server,
                        "port": int(smtp_port),
                        "username": smtp_username,
                        "password": smtp_password,
                        "recipient": alert_email,
                    },
                )
            )
            logger.info("Email notifications enabled")

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
        # Always log to console
        if level == "ERROR":
            logger.error(message, extra=details or {})
        elif level == "WARN":
            logger.warning(message, extra=details or {})
        else:
            logger.info(message, extra=details or {})

        # Format the environment info
        environment = os.environ.get("ENVIRONMENT") or (
            self.config.get("ENVIRONMENT") if self.config else "development"
        )

        # Create rich message with details
        rich_message = f"[{environment.upper()}] {level}: {message}"
        if details:
            formatted_details = "\n".join(
                [f"{k}: {v}" for k, v in details.items()])
            rich_message = f"{rich_message}\n\nDetails:\n{formatted_details}"

        # Send through all channels
        success = False

        for channel_type, channel_config in self._channels:
            try:
                if channel_type == "slack":
                    await self._send_slack(rich_message, level, channel_config)
                    success = True
                elif channel_type == "email":
                    await self._send_email(rich_message, level, channel_config)
                    success = True
            except Exception as e:
                logger.error(
                    f"Failed to send {channel_type} notification: {e}")

        return success

    async def _send_slack(self, message: str, level: str,
                          webhook_url: str) -> bool:
        """Send a notification to Slack.

        Args:
            message: The message to send
            level: Notification level
            webhook_url: Slack webhook URL

        Returns:
            True if successful
        """
        color = "#36a64f"  # Green for INFO
        if level == "WARN":
            color = "#ffcc00"  # Yellow for WARN
        elif level == "ERROR":
            color = "#ff0000"  # Red for ERROR

        payload = {
            "attachments": [
                {
                    "color": color,
                    "title": f"ON1Builder Alert - {level}",
                    "text": message,
                    "ts": int(import_time().time()),
                }
            ]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"Error sending Slack notification: {e}")
            return False

    async def _send_email(
        self, message: str, level: str, config: Dict[str, Any]
    ) -> bool:
        """Send a notification via email.

        Args:
            message: The message to send
            level: Notification level
            config: Email configuration

        Returns:
            True if successful
        """
        subject = f"ON1Builder Alert - {level}"

        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = config["username"]
        msg["To"] = config["recipient"]

        msg.attach(MIMEText(message, "plain"))

        try:
            server = smtplib.SMTP(config["server"], config["port"])
            server.starttls()
            server.login(config["username"], config["password"])
            server.send_message(msg)
            server.quit()
            return True
        except Exception as e:
            logger.error(f"Error sending email notification: {e}")
            return False


# Helper for accessing time (used for timestamps)
def import_time():
    """Import time module dynamically to avoid circular imports."""
    import time

    return time


# Create a singleton instance
_notification_manager = None


def get_notification_manager(config=None):
    """Get or create the singleton NotificationManager instance."""
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager(config)
    return _notification_manager


async def send_alert(
    message: str, level: str = "INFO", details: Dict[str, Any] = None, config=None
):
    """Send an alert through the notification system.

    Args:
        message: The alert message
        level: Alert level (INFO, WARN, ERROR)
        details: Additional details to include
        config: Configuration to use for notifications

    Returns:
        True if alert was sent successfully
    """
    manager = get_notification_manager(config)
    return await manager.send_notification(message, level, details)
