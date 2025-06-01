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

import json
import time
import traceback
from typing import Any, Dict, Optional

class StrategyExecutionError(Exception):
    """Custom exception for strategy execution failures with detailed context."""

    def __init__(
        self, 
        message: str = "Strategy execution failed", 
        strategy_name: Optional[str] = None,
        chain_id: Optional[int] = None,
        tx_hash: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None
    ) -> None:
        self.message: str = message
        self.strategy_name: Optional[str] = strategy_name
        self.chain_id: Optional[int] = chain_id
        self.tx_hash: Optional[str] = tx_hash
        self.details: Dict[str, Any] = details or {}
        self.timestamp: float = time.time()
        self.original_exception: Optional[Exception] = original_exception
        self.traceback: Optional[str] = None
        
        if original_exception:
            self.traceback = traceback.format_exception(
                type(original_exception),
                original_exception,
                original_exception.__traceback__
            )
            
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the error to a dictionary representation."""
        return {
            "message": self.message,
            "strategy_name": self.strategy_name,
            "chain_id": self.chain_id,
            "tx_hash": self.tx_hash,
            "details": self.details,
            "timestamp": self.timestamp,
            "original_exception": str(self.original_exception) if self.original_exception else None,
            "traceback": self.traceback
        }
    
    def to_json(self) -> str:
        """Convert the error to a JSON string."""
        return json.dumps(self.to_dict(), default=str)
    
    def __str__(self) -> str:
        """Human-readable error message."""
        parts = [self.message]
        
        if self.strategy_name:
            parts.append(f"Strategy: {self.strategy_name}")
        if self.chain_id:
            parts.append(f"Chain ID: {self.chain_id}")
        if self.tx_hash:
            parts.append(f"TX Hash: {self.tx_hash}")
        if self.details:
            parts.append(f"Details: {self.details}")
        if self.original_exception:
            parts.append(f"Caused by: {self.original_exception}")
            
        return " | ".join(parts)
