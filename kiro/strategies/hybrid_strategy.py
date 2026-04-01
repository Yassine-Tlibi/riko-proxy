# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Hybrid selection strategy.

Combines sticky and round-robin approaches with intelligent weighted scoring.
Considers account health, quota usage, failure rate, and response time.
"""

from datetime import datetime
from typing import List, Optional

from loguru import logger

from kiro.strategies.base_strategy import BaseStrategy, SelectionResult
from kiro.account_storage import Account


class HybridStrategy(BaseStrategy):
    """
    Hybrid account selection strategy.

    Behavior:
    - Weighted scoring based on multiple factors
    - Prefers healthy accounts with low failure rates
    - Balances between cache continuity and load distribution
    - Adapts to account performance over time

    Scoring factors:
    - Health score (0.0-1.0): Overall account health
    - Consecutive failures: Penalizes unreliable accounts
    - Last used time: Slight preference for recently used (cache)
    - Availability: Binary check (available vs rate-limited)

    Best for:
    - General-purpose usage
    - Production workloads
    - Mixed usage patterns
    - Unknown workload characteristics
    """

    # Default weights for scoring
    DEFAULT_WEIGHTS = {
        "health": 0.4,          # 40% weight on health score
        "failures": 0.3,        # 30% weight on failure rate
        "recency": 0.2,         # 20% weight on cache continuity
        "availability": 0.1,    # 10% weight on availability
    }

    # Maximum consecutive failures before heavy penalty
    MAX_FAILURES_THRESHOLD = 5

    # Recency window (prefer accounts used within last 5 minutes)
    RECENCY_WINDOW_MS = 300000

    def __init__(self, config: dict = None):
        """
        Initialize Hybrid strategy.

        Args:
            config: Strategy configuration
                - weights: Custom weights for scoring factors
                - max_failures_threshold: Max failures before penalty
                - recency_window_ms: Time window for recency bonus
        """
        super().__init__(config)

        self.weights = config.get("weights", self.DEFAULT_WEIGHTS) if config else self.DEFAULT_WEIGHTS
        self.max_failures_threshold = config.get(
            "max_failures_threshold",
            self.MAX_FAILURES_THRESHOLD
        ) if config else self.MAX_FAILURES_THRESHOLD
        self.recency_window_ms = config.get(
            "recency_window_ms",
            self.RECENCY_WINDOW_MS
        ) if config else self.RECENCY_WINDOW_MS

    def select_account(
        self,
        accounts: List[Account],
        model_id: str,
        options: dict = None
    ) -> SelectionResult:
        """
        Select account using weighted scoring.

        Args:
            accounts: List of available accounts
            model_id: Model ID for the request
            options: Additional options (current_index, on_save callback)

        Returns:
            SelectionResult with highest-scoring account
        """
        options = options or {}
        current_index = options.get("current_index", 0)
        on_save = options.get("on_save")

        if not accounts:
            return SelectionResult(account=None, index=0, wait_ms=0)

        # Get usable accounts
        usable_accounts = self.get_usable_accounts(accounts, model_id)

        if not usable_accounts:
            # No accounts available - calculate wait time
            wait_ms = self.calculate_min_wait_time(accounts, model_id)
            logger.warning(
                f"[HybridStrategy] No available accounts for model {model_id}. "
                f"Wait time: {wait_ms}ms"
            )
            return SelectionResult(
                account=None,
                index=min(current_index, len(accounts) - 1),
                wait_ms=wait_ms
            )

        # Score all usable accounts
        scored_accounts = [
            (idx, account, self._calculate_score(account, model_id))
            for idx, account in usable_accounts
        ]

        # Sort by score (descending)
        scored_accounts.sort(key=lambda x: x[2], reverse=True)

        # Select highest-scoring account
        best_idx, best_account, best_score = scored_accounts[0]

        # Update account state
        best_account.last_used = int(datetime.now().timestamp() * 1000)

        if on_save:
            on_save()

        logger.info(
            f"[HybridStrategy] Selected account: {best_account.email} "
            f"(score: {best_score:.3f})"
        )

        return SelectionResult(account=best_account, index=best_idx, wait_ms=0)

    def _calculate_score(self, account: Account, model_id: str) -> float:
        """
        Calculate weighted score for an account.

        Args:
            account: Account to score
            model_id: Model ID

        Returns:
            Score between 0.0 and 1.0 (higher is better)
        """
        # Health score (0.0-1.0)
        health_score = account.health_score

        # Failure score (0.0-1.0, lower failures = higher score)
        failures = 0
        if model_id in account.model_rate_limits:
            failures = account.model_rate_limits[model_id].consecutive_failures

        failure_score = max(0.0, 1.0 - (failures / self.max_failures_threshold))

        # Recency score (0.0-1.0, recently used = higher score)
        recency_score = self._calculate_recency_score(account)

        # Availability score (1.0 if available, 0.0 if not)
        availability_score = 1.0 if account.is_available_for_model(model_id) else 0.0

        # Weighted sum
        total_score = (
            self.weights["health"] * health_score +
            self.weights["failures"] * failure_score +
            self.weights["recency"] * recency_score +
            self.weights["availability"] * availability_score
        )

        return total_score

    def _calculate_recency_score(self, account: Account) -> float:
        """
        Calculate recency score based on last used time.

        Args:
            account: Account to score

        Returns:
            Score between 0.0 and 1.0 (recently used = higher score)
        """
        if account.last_used is None:
            return 0.5  # Neutral score for never-used accounts

        now_ms = int(datetime.now().timestamp() * 1000)
        time_since_use = now_ms - account.last_used

        if time_since_use <= 0:
            return 1.0

        # Linear decay within recency window
        if time_since_use < self.recency_window_ms:
            return 1.0 - (time_since_use / self.recency_window_ms)

        return 0.0

    def notify_success(self, account: Account, model_id: str) -> None:
        """
        Update account health on successful request.

        Args:
            account: Account that was used
            model_id: Model ID that was used
        """
        super().notify_success(account, model_id)

        # Gradually improve health score on success
        account.health_score = min(1.0, account.health_score + 0.01)

    def notify_failure(
        self,
        account: Account,
        model_id: str,
        error_type: str
    ) -> None:
        """
        Update account health on failed request.

        Args:
            account: Account that was used
            model_id: Model ID that was used
            error_type: Type of error
        """
        super().notify_failure(account, model_id, error_type)

        # Degrade health score on failure
        penalty = 0.05 if error_type == "rate_limit" else 0.1
        account.health_score = max(0.0, account.health_score - penalty)
