#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – StrategyExecutionError
======================

Custom exception for strategy execution failures.
==========================
License: MIT
=========================

This file is part of the ON1Builder project, which is licensed under the MIT License.
see https://opensource.org/licenses/MIT or https://github.com/John0n1/ON1Builder/blob/master/LICENSE
"""

class StrategyExecutionError(Exception):
    """Custom exception for strategy execution failures."""

    def __init__(self, message: str = "Strategy execution failed") -> None:
        self.message: str = message
        super().__init__(self.message)
