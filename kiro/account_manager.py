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
Multi-account manager for Kiro Gateway.

Manages multiple Kiro accounts with automatic rotation, rate limit handling,
and intelligent failover.
"""

import asyncio
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from loguru import logger

from kiro.account_storage import (
    Account,
    AccountSettings,
    AccountStorage,
    AccountTokens,
    ModelRateLimit,
)
from kiro.strategies import (
    BaseStrategy,
    StickyStrategy,
    RoundRobinStrategy,
    HybridStrategy,
)


class AccountManager:
    """
    Manages multiple Kiro accounts with automatic rotation and failover.

    Features:
    - Pluggable selection strategies (sticky, round-robin, hybrid)
    - Per-model rate limit tracking
    - Automatic token refresh integration
    - Thread-safe operations with asyncio.Lock
    - State persistence to JSON file
    - Invalid account detection and isolation

    Usage:
        manager = AccountManager("~/.config/kiro-gateway/accounts.json")
        await manager.initialize()

        # Select account for request
        result = await manager.select_account("claude-sonnet-4-5")
        if result.account:
            # Use account for request
            await manager.notify_success(result.account, "claude-sonnet-4-5")
        else:
            # Wait or return error
            await asyncio.sleep(result.wait_ms / 1000)
    """

    def __init__(
        self,
        accounts_file: str,
        strategy_name: str = "hybrid",
        config: dict = None
    ):
        """
        Initialize AccountManager.

        Args:
            accounts_file: Path to accounts.json file
            strategy_name: Selection strategy (sticky, round-robin, hybrid)
            config: Additional configuration
        """
        self.storage = AccountStorage(accounts_file)
        self.strategy_name = strategy_name.lower()
        self.config = config or {}

        self.accounts: List[Account] = []
        self.settings: AccountSettings = AccountSettings()
        self.strategy: Optional[BaseStrategy] = None

        # Thread safety
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize the account manager.

        Loads accounts from storage and creates strategy instance.

        Raises:
            FileNotFoundError: If accounts file doesn't exist
            ValueError: If invalid strategy name
        """
        async with self._lock:
            if self._initialized:
                return

            # Load accounts from storage
            self.accounts, self.settings = await self.storage.load()
            
            # Create default file if it doesn't exist
            if not self.storage.file_path.exists():
                logger.warning(
                    "[AccountManager] No accounts file found. "
                    "Creating default file."
                )
                await self.storage.create_default()
                self.accounts = []
                self.settings = AccountSettings()

            # Override strategy from settings if not explicitly set
            if self.strategy_name == "hybrid" and self.settings.strategy:
                self.strategy_name = self.settings.strategy

            # Create strategy instance
            self.strategy = self._create_strategy(self.strategy_name)

            # Clear expired rate limits
            self._clear_expired_limits()

            logger.info(
                f"[AccountManager] Initialized with {len(self.accounts)} accounts "
                f"using {self.strategy_name} strategy"
            )

            self._initialized = True

    async def select_account(
        self,
        model_id: str,
        session_id: Optional[str] = None
    ) -> "SelectionResult":
        """
        Select an account for a request.

        Args:
            model_id: Model ID for the request
            session_id: Optional session ID for cache continuity

        Returns:
            SelectionResult with account, index, and optional wait time

        Raises:
            RuntimeError: If not initialized
        """
        if not self._initialized:
            raise RuntimeError("AccountManager not initialized. Call initialize() first.")

        async with self._lock:
            # Clear expired rate limits before selection
            self._clear_expired_limits()

            # Select account using strategy
            result = self.strategy.select_account(
                self.accounts,
                model_id,
                options={
                    "current_index": self.settings.active_index,
                    "session_id": session_id,
                    "on_save": self._save_state,
                }
            )

            # Update active index
            self.settings.active_index = result.index

            return result

    async def notify_success(self, account: Account, model_id: str) -> None:
        """
        Notify manager of successful request.

        Args:
            account: Account that was used
            model_id: Model ID that was used
        """
        async with self._lock:
            # Reset consecutive failures
            if model_id in account.model_rate_limits:
                account.model_rate_limits[model_id].consecutive_failures = 0

            # Notify strategy
            self.strategy.notify_success(account, model_id)

            # Save state
            self._save_state()

    async def notify_failure(
        self,
        account: Account,
        model_id: str,
        error_type: str,
        retry_after_ms: Optional[int] = None
    ) -> None:
        """
        Notify manager of failed request.

        Args:
            account: Account that was used
            model_id: Model ID that was used
            error_type: Type of error (rate_limit, auth_error, network_error)
            retry_after_ms: Optional retry-after time from API
        """
        async with self._lock:
            if error_type == "rate_limit":
                self._mark_rate_limited(account, model_id, retry_after_ms)
            elif error_type == "auth_error":
                self._mark_invalid(account)

            # Notify strategy
            self.strategy.notify_failure(account, model_id, error_type)

            # Save state
            self._save_state()

    async def mark_account_invalid(self, email: str) -> None:
        """
        Mark an account as invalid (permanent failure).

        Args:
            email: Email of account to mark invalid
        """
        async with self._lock:
            for account in self.accounts:
                if account.email == email:
                    account.is_invalid = True
                    logger.warning(
                        f"[AccountManager] Marked account as invalid: {email}"
                    )
                    self._save_state()
                    return

    async def clear_account_invalid(self, email: str) -> None:
        """
        Clear invalid flag for an account.

        Args:
            email: Email of account to clear
        """
        async with self._lock:
            for account in self.accounts:
                if account.email == email:
                    account.is_invalid = False
                    logger.info(
                        f"[AccountManager] Cleared invalid flag for: {email}"
                    )
                    self._save_state()
                    return

    async def get_account_status(self) -> dict:
        """
        Get status of all accounts.

        Returns:
            Dict with account statistics and status
        """
        async with self._lock:
            total = len(self.accounts)
            enabled = sum(1 for a in self.accounts if a.enabled)
            invalid = sum(1 for a in self.accounts if a.is_invalid)
            available = sum(
                1 for a in self.accounts
                if a.enabled and not a.is_invalid
            )

            return {
                "total": total,
                "enabled": enabled,
                "invalid": invalid,
                "available": available,
                "strategy": self.strategy_name,
                "accounts": [
                    {
                        "email": a.email,
                        "enabled": a.enabled,
                        "is_invalid": a.is_invalid,
                        "health_score": a.health_score,
                        "last_used": a.last_used,
                        "rate_limits": {
                            model_id: {
                                "is_limited": limit.is_rate_limited,
                                "reset_time": limit.reset_time,
                                "failures": limit.consecutive_failures,
                            }
                            for model_id, limit in a.model_rate_limits.items()
                        }
                    }
                    for a in self.accounts
                ]
            }

    async def reload(self) -> None:
        """Reload accounts from storage."""
        # Clear initialized flag and call initialize (which acquires the lock)
        # We do not acquire the lock here as asyncio.Lock is not reentrant.
        self._initialized = False
        await self.initialize()
        logger.info("[AccountManager] Accounts reloaded from storage")

    def _create_strategy(self, strategy_name: str) -> BaseStrategy:
        """
        Create strategy instance.

        Args:
            strategy_name: Strategy name (sticky, round-robin, hybrid)

        Returns:
            Strategy instance

        Raises:
            ValueError: If invalid strategy name
        """
        strategy_config = self.config.get("strategy_config", {})

        if strategy_name == "sticky":
            return StickyStrategy(strategy_config)
        elif strategy_name in ("round-robin", "roundrobin"):
            return RoundRobinStrategy(strategy_config)
        elif strategy_name == "hybrid":
            return HybridStrategy(strategy_config)
        else:
            logger.warning(
                f"[AccountManager] Unknown strategy '{strategy_name}', "
                f"falling back to hybrid"
            )
            return HybridStrategy(strategy_config)

    def _mark_rate_limited(
        self,
        account: Account,
        model_id: str,
        retry_after_ms: Optional[int] = None
    ) -> None:
        """
        Mark account as rate-limited for a model.

        Args:
            account: Account to mark
            model_id: Model ID
            retry_after_ms: Optional retry-after time from API
        """
        if model_id not in account.model_rate_limits:
            account.model_rate_limits[model_id] = ModelRateLimit(
                is_rate_limited=False,
                reset_time=None,
                consecutive_failures=0
            )

        limit = account.model_rate_limits[model_id]
        limit.is_rate_limited = True
        limit.consecutive_failures += 1

        # Calculate reset time with exponential backoff
        if retry_after_ms:
            reset_time = int(datetime.now().timestamp() * 1000) + retry_after_ms
        else:
            # Exponential backoff: 60s, 120s, 240s (max 5min)
            base_cooldown_ms = 60000
            max_cooldown_ms = 300000
            cooldown = min(
                base_cooldown_ms * (2 ** limit.consecutive_failures),
                max_cooldown_ms
            )
            reset_time = int(datetime.now().timestamp() * 1000) + cooldown

        limit.reset_time = reset_time

        logger.warning(
            f"[AccountManager] Rate limited: {account.email} "
            f"(model: {model_id}, reset: {reset_time})"
        )

    def _mark_invalid(self, account: Account) -> None:
        """
        Mark account as invalid (permanent failure).

        Args:
            account: Account to mark
        """
        account.is_invalid = True
        logger.error(
            f"[AccountManager] Marked account as invalid: {account.email}"
        )

    def _clear_expired_limits(self) -> None:
        """Clear expired rate limits for all accounts."""
        now_ms = int(datetime.now().timestamp() * 1000)
        cleared = 0

        for account in self.accounts:
            for model_id, limit in list(account.model_rate_limits.items()):
                if limit.is_rate_limited and limit.reset_time:
                    if now_ms >= limit.reset_time:
                        limit.is_rate_limited = False
                        limit.reset_time = None
                        cleared += 1
                        logger.success(
                            f"[AccountManager] Rate limit expired: "
                            f"{account.email} (model: {model_id})"
                        )

        if cleared > 0:
            self._save_state()

    def _save_state(self) -> None:
        """Save current state to storage asynchronously."""
        try:
            # Create a background task for the async save operation
            task = asyncio.create_task(self.storage.save(self.accounts, self.settings))
            
            # Simple wrapper to log any exceptions from the background task
            def handle_exception(t):
                if not t.cancelled() and t.exception():
                    logger.error(f"[AccountManager] Delayed save failed: {t.exception()}")
                    
            task.add_done_callback(handle_exception)
        except Exception as e:
            logger.error(f"[AccountManager] Failed to schedule state save: {e}")


# Re-export SelectionResult for convenience
from kiro.strategies.base_strategy import SelectionResult

__all__ = ["AccountManager", "SelectionResult"]
