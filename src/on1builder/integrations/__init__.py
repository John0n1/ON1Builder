#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ON1Builder – Integrations Module
===============================

This module provides integrations with external systems, blockchain APIs,
smart contract ABIs, and third-party services. It contains tools for 
interacting with various blockchain protocols and external data sources.

==========================
License: MIT
=========================

This file is part of the ON1Builder project, which is licensed under the MIT License.
see https://opensource.org/licenses/MIT or https://github.com/John0n1/ON1Builder/blob/master/LICENSE
"""

from .abi_registry import ABIRegistry, get_registry

__all__ = [
    "ABIRegistry",
    "get_registry"
]
