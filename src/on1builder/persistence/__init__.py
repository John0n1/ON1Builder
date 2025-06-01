#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder - Persistence Module
===========================

Manages database connections and operations for persisting transaction data,
monitoring information, strategy performance metrics, and system state.
Provides tools for data access, querying, and managing database connections.

==========================
License: MIT
=========================

This file is part of the ON1Builder project, which is licensed under the MIT License.
see https://opensource.org/licenses/MIT or https://github.com/John0n1/ON1Builder/blob/master/LICENSE
"""

from .db_manager import DatabaseManager, get_db_manager

__all__ = [
    "DatabaseManager", 
    "get_db_manager"
]
