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
Base strategy interface for account selection.

All selection strategies must inherit from BaseStrategy and implement
the select_account method.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Callable

from kiro.account_storage import Account


@dataclass
class SelectionResult:
    """
    Result of account selection.

    Attributes:
        account: Selected account (None if no account available)
        index: Index of selected account in accounts list
        wait_ms: Milliseconds to wait before retrying (0 if account available)
    """
    account: Optional[Account]
    index: int
    wait_ms: int = 0


class BaseStrategy(ABC):
    """
    Base class for account selection strategies.

    Subclasses must implement:
    - select_account: Choose an account for a request
    - notify_success: Handle successful request
    - notify_failure: Handle failed request
    """

    def __init__(self, config: dict = None):
        """
        Initialize strategy with configuration.

        Args:
            config: Strategy-specific configuration
        """
        self.config = config or {}

    @abstractmethod
    def select_account(
        self,
        accounts: List[Account],
        model_id: str,
        options: dict = None
    ) -> SelectionResult:
        """
        Select an account for a request.

        Args:
            accounts: List of available accounts
            model_id: Model ID for the request
            options: Additional options (current_index, on_save callback, etc.)

        Returns:
            SelectionResult with account, index, and optional wait time
        """
        pass

    def notify_success(self, account: Account, model_id: str) -> None:
        """
        Notify strategy of successful request.

        Args:
            account: Account that was used
            model_id: Model ID that was used
        """
        # Default implementation: reset consecutive failures
        if model_id in account.model_rate_limits:
            account.model_rate_limits[model_id].consecutive_failures = 0

    def notify_failure(
        self,
        account: Account,
        model_id: str,
        error_type: str
    ) -> None:
        """
        Notify strategy of failed request.

        Args:
            account: Account that was used
            model_id: Model ID that was used
            error_type: Type of error (rate_limit, auth_error, etc.)
        """
        # Base implementation does nothing as AccountManager handles state updates
        pass

    def get_usable_accounts(
        self,
        accounts: List[Account],
        model_id: str
    ) -> List[tuple[int, Account]]:
        """
        Get list of usable accounts with their indices.

        Args:
            accounts: List of all accounts
            model_id: Model ID to check availability for

        Returns:
            List of (index, account) tuples for usable accounts
        """
        return [
            (idx, account)
            for idx, account in enumerate(accounts)
            if account.is_available_for_model(model_id)
        ]

    def calculate_min_wait_time(
        self,
        accounts: List[Account],
        model_id: str
    ) -> int:
        """
        Calculate minimum wait time across all rate-limited accounts.

        Args:
            accounts: List of accounts
            model_id: Model ID to check

        Returns:
            Minimum wait time in milliseconds (0 if any account available)
        """
        from datetime import datetime

        now_ms = int(datetime.now().timestamp() * 1000)
        min_wait = float('inf')

        for account in accounts:
            if not account.enabled or account.is_invalid:
                continue

            if model_id in account.model_rate_limits:
                limit = account.model_rate_limits[model_id]
                if limit.is_rate_limited and limit.reset_time:
                    wait_ms = max(0, limit.reset_time - now_ms)
                    min_wait = min(min_wait, wait_ms)

        return int(min_wait) if min_wait != float('inf') else 0
