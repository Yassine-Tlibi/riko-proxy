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
Sticky selection strategy.

Keeps using the same account until it becomes unavailable.
Best for prompt caching as it maintains cache continuity.
"""

from datetime import datetime
from typing import List, Optional

from loguru import logger

from kiro.strategies.base_strategy import BaseStrategy, SelectionResult
from kiro.account_storage import Account


class StickyStrategy(BaseStrategy):
    """
    Sticky account selection strategy.

    Behavior:
    - Keeps using the same account until unavailable
    - Only switches when current account is rate-limited >2min or invalid
    - Waits for current account if rate limit is short (<2min)
    - Maximizes cache hits at the cost of potential underutilization

    Best for:
    - Conversational AI
    - Claude Code sessions
    - Context-heavy workloads
    - Prompt caching optimization
    """

    # Maximum wait time before switching accounts (2 minutes)
    MAX_STICKY_WAIT_MS = 120000

    def __init__(self, config: dict = None):
        """
        Initialize Sticky strategy.

        Args:
            config: Strategy configuration
                - max_sticky_wait_ms: Max wait time before switching (default: 120000)
        """
        super().__init__(config)
        self.max_sticky_wait_ms = config.get(
            "max_sticky_wait_ms",
            self.MAX_STICKY_WAIT_MS
        ) if config else self.MAX_STICKY_WAIT_MS

    def select_account(
        self,
        accounts: List[Account],
        model_id: str,
        options: dict = None
    ) -> SelectionResult:
        """
        Select account with sticky preference.

        Prefers the current account for cache continuity, only switches when:
        - Current account is rate-limited for > max_sticky_wait_ms
        - Current account is invalid
        - Current account is disabled

        Args:
            accounts: List of available accounts
            model_id: Model ID for the request
            options: Additional options (current_index, on_save callback)

        Returns:
            SelectionResult with selected account, index, and optional wait time
        """
        options = options or {}
        current_index = options.get("current_index", 0)
        on_save = options.get("on_save")

        if not accounts:
            return SelectionResult(account=None, index=0, wait_ms=0)

        # Clamp index to valid range
        index = min(current_index, len(accounts) - 1)
        current_account = accounts[index]

        # Check if current account is usable
        if current_account.is_available_for_model(model_id):
            current_account.last_used = int(datetime.now().timestamp() * 1000)
            if on_save:
                on_save()

            logger.debug(
                f"[StickyStrategy] Continuing with sticky account: "
                f"{current_account.email}"
            )
            return SelectionResult(account=current_account, index=index, wait_ms=0)

        # Current account not usable - check if others are available
        usable_accounts = self.get_usable_accounts(accounts, model_id)

        if usable_accounts:
            # Found a free account - switch immediately
            next_idx, next_account = self._pick_next_account(
                accounts, index, model_id
            )
            if next_account:
                next_account.last_used = int(datetime.now().timestamp() * 1000)
                if on_save:
                    on_save()

                logger.info(
                    f"[StickyStrategy] Switched to new account (failover): "
                    f"{next_account.email}"
                )
                return SelectionResult(
                    account=next_account,
                    index=next_idx,
                    wait_ms=0
                )

        # No other accounts available - check if we should wait for current
        wait_info = self._should_wait_for_account(current_account, model_id)
        if wait_info["should_wait"]:
            wait_ms = wait_info["wait_ms"]
            logger.info(
                f"[StickyStrategy] Waiting {wait_ms}ms for sticky account: "
                f"{current_account.email}"
            )
            return SelectionResult(account=None, index=index, wait_ms=wait_ms)

        # Current account unavailable for too long, try to find any other
        next_idx, next_account = self._pick_next_account(accounts, index, model_id)
        if next_account:
            next_account.last_used = int(datetime.now().timestamp() * 1000)
            if on_save:
                on_save()

            logger.info(
                f"[StickyStrategy] Switched to account after long wait: "
                f"{next_account.email}"
            )
            return SelectionResult(account=next_account, index=next_idx, wait_ms=0)

        # No accounts available at all
        wait_ms = self.calculate_min_wait_time(accounts, model_id)
        logger.warning(
            f"[StickyStrategy] No available accounts for model {model_id}. "
            f"Wait time: {wait_ms}ms"
        )
        return SelectionResult(account=None, index=index, wait_ms=wait_ms)

    def _should_wait_for_account(
        self,
        account: Account,
        model_id: str
    ) -> dict:
        """
        Determine if we should wait for the current account.

        Args:
            account: Account to check
            model_id: Model ID

        Returns:
            Dict with should_wait (bool) and wait_ms (int)
        """
        if account.is_invalid or not account.enabled:
            return {"should_wait": False, "wait_ms": 0}

        if model_id not in account.model_rate_limits:
            return {"should_wait": False, "wait_ms": 0}

        limit = account.model_rate_limits[model_id]
        if not limit.is_rate_limited or not limit.reset_time:
            return {"should_wait": False, "wait_ms": 0}

        now_ms = int(datetime.now().timestamp() * 1000)
        wait_ms = max(0, limit.reset_time - now_ms)

        # Only wait if wait time is reasonable
        should_wait = wait_ms > 0 and wait_ms <= self.max_sticky_wait_ms

        return {"should_wait": should_wait, "wait_ms": wait_ms}

    def _pick_next_account(
        self,
        accounts: List[Account],
        current_index: int,
        model_id: str
    ) -> tuple[int, Optional[Account]]:
        """
        Pick the next available account after current_index.

        Args:
            accounts: List of accounts
            current_index: Current account index
            model_id: Model ID

        Returns:
            Tuple of (index, account) or (current_index, None) if none found
        """
        # Try accounts after current_index first
        for i in range(len(accounts)):
            idx = (current_index + 1 + i) % len(accounts)
            account = accounts[idx]

            if account.is_available_for_model(model_id):
                return idx, account

        return current_index, None
