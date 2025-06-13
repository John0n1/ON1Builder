# src/on1builder/utils/notification_service.py
from __future__ import annotations

import asyncio
import json
import smtplib
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

import aiohttp

from on1builder.utils.logging_config import get_logger
from on1builder.utils.singleton import SingletonMeta

logger = get_logger(__name__)

class NotificationService(metaclass=SingletonMeta):
    """Manages sending notifications through various configured channels."""

    def __init__(self):
        from on1builder.config.loaders import get_settings
        settings = get_settings()
        self._session: Optional[aiohttp.ClientSession] = None
        self._config = settings.notifications
        self._min_level_value = self._level_to_int(self._config.min_level)
        logger.info(f"NotificationService initialized. Active channels: {self._config.channels or 'None'}")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Lazily creates and returns an aiohttp ClientSession."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session

    def _level_to_int(self, level: str) -> int:
        """Converts a log level string to an integer for comparison."""
        return {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}.get(level.upper(), 1)

    def _should_send(self, level: str) -> bool:
        """Determines if a message of a given level should be sent."""
        return self._level_to_int(level) >= self._min_level_value

    async def send_alert(
        self,
        title: str,
        message: str,
        level: str = "ERROR",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Sends a notification if its level is at or above the configured minimum.

        Args:
            title: The main title of the alert.
            message: The detailed message body.
            level: The severity level ('INFO', 'WARNING', 'ERROR', 'CRITICAL').
            details: An optional dictionary of key-value pairs to include.
        """
        if not self._should_send(level):
            return

        logger.info(f"Sending alert (Level: {level}): {title} - {message}")
        tasks = []
        for channel in self._config.channels:
            if channel == "slack" and self._config.slack_webhook_url:
                tasks.append(self._send_slack(title, message, level, details))
            elif channel == "discord" and self._config.discord_webhook_url:
                tasks.append(self._send_discord(title, message, level, details))
            elif channel == "telegram" and self._config.telegram_bot_token and self._config.telegram_chat_id:
                tasks.append(self._send_telegram(title, message, level, details))
            elif channel == "email" and self._config.smtp_server and self._config.alert_email:
                tasks.append(self._send_email(title, message, level, details))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _format_details(self, details: Optional[Dict[str, Any]]) -> str:
        """Formats the details dictionary into a string for message bodies."""
        if not details:
            return ""
        return "\n".join([f"**{key.replace('_', ' ').title()}:** `{value}`" for key, value in details.items()])

    async def _send_slack(self, title: str, message: str, level: str, details: Optional[Dict[str, Any]]):
        color_map = {"INFO": "#439FE0", "WARNING": "#FFA500", "ERROR": "#D00000", "CRITICAL": "#D00000"}
        payload = {
            "attachments": [{
                "color": color_map.get(level.upper(), "#808080"),
                "blocks": [
                    {"type": "header", "text": {"type": "plain_text", "text": f":{level.lower()}: {level.upper()}: {title}"}},
                    {"type": "section", "text": {"type": "mrkdwn", "text": message}},
                    {"type": "divider"},
                    {"type": "section", "text": {"type": "mrkdwn", "text": self._format_details(details)}} if details else None,
                ]
            }]
        }
        # Filter out None blocks
        payload["attachments"][0]["blocks"] = [b for b in payload["attachments"][0]["blocks"] if b is not None]
        try:
            session = await self._get_session()
            async with session.post(self._config.slack_webhook_url, json=payload) as response:
                if not response.ok:
                    logger.error(f"Slack notification failed: {response.status} {await response.text()}")
        except Exception as e:
            logger.error(f"Error sending Slack notification: {e}", exc_info=True)

    async def _send_discord(self, title: str, message: str, level: str, details: Optional[Dict[str, Any]]):
        color_map = {"INFO": 3447003, "WARNING": 16753920, "ERROR": 13632027, "CRITICAL": 13632027}
        fields = [{"name": key.replace('_', ' ').title(), "value": f"`{value}`", "inline": True} for key, value in details.items()] if details else []
        payload = {
            "embeds": [{
                "title": f"[{level.upper()}] {title}",
                "description": message,
                "color": color_map.get(level.upper(), 8421504),
                "fields": fields
            }]
        }
        try:
            session = await self._get_session()
            async with session.post(self._config.discord_webhook_url, json=payload) as response:
                if not response.ok:
                    logger.error(f"Discord notification failed: {response.status} {await response.text()}")
        except Exception as e:
            logger.error(f"Error sending Discord notification: {e}", exc_info=True)

    async def _send_telegram(self, title: str, message: str, level: str, details: Optional[Dict[str, Any]]):
        text = f"*{level.upper()}: {title}*\n\n{message}\n\n{self._format_details(details)}"
        url = f"https://api.telegram.org/bot{self._config.telegram_bot_token}/sendMessage"
        payload = {"chat_id": self._config.telegram_chat_id, "text": text, "parse_mode": "Markdown"}
        try:
            session = await self._get_session()
            async with session.post(url, json=payload) as response:
                if not response.ok:
                    logger.error(f"Telegram notification failed: {response.status} {await response.text()}")
        except Exception as e:
            logger.error(f"Error sending Telegram notification: {e}", exc_info=True)

    async def _send_email(self, title: str, message: str, level: str, details: Optional[Dict[str, Any]]):
        subject = f"[ON1Builder Alert - {level.upper()}] {title}"
        body = f"{message}\n\n--- Details ---\n{json.dumps(details, indent=2, default=str)}"
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = self._config.smtp_username
        msg["To"] = self._config.alert_email
        try:
            await asyncio.to_thread(self._send_smtp_email, msg)
        except Exception as e:
            logger.error(f"Error sending email notification: {e}", exc_info=True)
            
    def _send_smtp_email(self, msg):
        """Blocking helper for sending email."""
        with smtplib.SMTP(self._config.smtp_server, self._config.smtp_port) as server:
            server.starttls()
            server.login(self._config.smtp_username, self._config.smtp_password)
            server.send_message(msg)

    async def close(self) -> None:
        """Closes the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("NotificationService session closed.")