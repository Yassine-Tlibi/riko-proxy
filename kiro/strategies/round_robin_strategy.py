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
Round-Robin selection strategy.

Rotates to the next account on every request for maximum throughput.
Does not maintain cache continuity but maximizes concurrent requests.
"""

from datetime import datetime
from typing import List

from loguru import logger

from kiro.strategies.base_strategy import BaseStrategy, SelectionResult
from kiro.account_storage import Account


class RoundRobinStrategy(BaseStrategy):
    """
    Round-Robin account selection strategy.

    Behavior:
    - Rotates to next account on every request
    - Distributes load evenly across all accounts
    - Skips rate-limited and invalid accounts
    - Maximizes throughput at the cost of cache continuity

    Best for:
    - High-volume batch processing
    - Parallel requests
    - Maximum RPS requirements
    - Stateless operations
    """

    def __init__(self, config: dict = None):
        """
        Initialize Round-Robin strategy.

        Args:
            config: Strategy configuration (unused for round-robin)
        """
        super().__init__(config)
        self.cursor = 0

    def select_account(
        self,
        accounts: List[Account],
        model_id: str,
        options: dict = None
    ) -> SelectionResult:
        """
        Select the next available account in rotation.

        Args:
            accounts: List of available accounts
            model_id: Model ID for the request
            options: Additional options (on_save callback)

        Returns:
            SelectionResult with selected account and index
        """
        options = options or {}
        on_save = options.get("on_save")

        if not accounts:
            return SelectionResult(account=None, index=0, wait_ms=0)

        # Clamp cursor to valid range
        if self.cursor >= len(accounts):
            self.cursor = 0

        # Start from the next position after cursor
        start_index = (self.cursor + 1) % len(accounts)

        # Try each account starting from start_index
        for i in range(len(accounts)):
            idx = (start_index + i) % len(accounts)
            account = accounts[idx]

            if account.is_available_for_model(model_id):
                # Update account state
                account.last_used = int(datetime.now().timestamp() * 1000)
                self.cursor = idx

                if on_save:
                    on_save()

                position = idx + 1
                total = len(accounts)
                logger.info(
                    f"[RoundRobinStrategy] Using account: {account.email} "
                    f"({position}/{total})"
                )

                return SelectionResult(account=account, index=idx, wait_ms=0)

        # No usable accounts found - calculate wait time
        wait_ms = self.calculate_min_wait_time(accounts, model_id)

        logger.warning(
            f"[RoundRobinStrategy] No available accounts for model {model_id}. "
            f"Wait time: {wait_ms}ms"
        )

        return SelectionResult(account=None, index=self.cursor, wait_ms=wait_ms)

    def reset_cursor(self) -> None:
        """Reset the cursor position to 0."""
        self.cursor = 0
