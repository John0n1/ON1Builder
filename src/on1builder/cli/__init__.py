#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – CLI Tools
=====================

Helper tools and utilities for the ON1Builder command-line interface.
Provides command handlers, configuration validation, and interactive tools
for managing the application from the terminal.

The main command-line interface is implemented using Typer in src/on1builder/__main__.py.

==========================
License: MIT
=========================

This file is part of the ON1Builder project, which is licensed under the MIT License.
see https://opensource.org/licenses/MIT or https://github.com/John0n1/ON1Builder/blob/master/LICENSE
"""

from .config import app, validate_command

__all__ = [
    "app",
    "validate_command",
]
