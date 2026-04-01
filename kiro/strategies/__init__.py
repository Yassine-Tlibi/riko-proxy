# -*- coding: utf-8 -*-

"""
Account selection strategies for multi-account support.

Available strategies:
- StickyStrategy: Cache-optimized, maintains account continuity
- RoundRobinStrategy: Throughput-optimized, rotates on every request
- HybridStrategy: Intelligent weighted scoring
"""

from kiro.strategies.base_strategy import BaseStrategy, SelectionResult
from kiro.strategies.sticky_strategy import StickyStrategy
from kiro.strategies.round_robin_strategy import RoundRobinStrategy
from kiro.strategies.hybrid_strategy import HybridStrategy

__all__ = [
    "BaseStrategy",
    "SelectionResult",
    "StickyStrategy",
    "RoundRobinStrategy",
    "HybridStrategy",
]
