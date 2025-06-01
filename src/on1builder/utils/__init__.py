#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder - Utilities Module
===========================
Utilities for ON1Builder including logging, notifications, dependency injection,
and error handling components.

==========================
License: MIT
=========================

This file is part of the ON1Builder project, which is licensed under the MIT License.
see https://opensource.org/licenses/MIT or https://github.com/John0n1/ON1Builder/blob/master/LICENSE
"""
from on1builder.utils.logger import setup_logging, get_logger, bind_logger_context
from on1builder.utils.notifications import NotificationManager, get_notification_manager, send_alert
from on1builder.utils.strategyexecutionerror import StrategyExecutionError
from on1builder.utils.container import Container, get_container

__all__ = [
    "setup_logging",
    "get_logger",
    "bind_logger_context",
    "NotificationManager",
    "get_notification_manager",
    "send_alert",
    "StrategyExecutionError",
    "Container",
    "get_container",
]