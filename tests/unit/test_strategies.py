# -*- coding: utf-8 -*-

"""
Unit tests for account selection strategies.

Tests:
- StickyStrategy: cache continuity, failover, wait logic
- RoundRobinStrategy: rotation, load distribution
- HybridStrategy: weighted scoring, health tracking
- BaseStrategy: common functionality
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock

from kiro.account_storage import Account, AccountTokens, ModelRateLimit
from kiro.strategies import (
    StickyStrategy,
    RoundRobinStrategy,
    HybridStrategy,
    SelectionResult,
)


@pytest.fixture
def sample_tokens():
    """Create sample tokens."""
    expires_at = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)
    return AccountTokens(
        access="access_token",
        refresh="refresh_token",
        expires_at=expires_at
    )


@pytest.fixture
def create_account(sample_tokens):
    """Factory for creating test accounts."""
    def _create(email: str, enabled: bool = True, is_invalid: bool = False):
        return Account(
            email=email,
            tokens=sample_tokens,
            enabled=enabled,
            is_invalid=is_invalid,
            model_rate_limits={},
            last_used=None,
            health_score=1.0,
            metadata={}
        )
    return _create


@pytest.fixture
def three_accounts(create_account):
    """Create three test accounts."""
    return [
        create_account("account1@example.com"),
        create_account("account2@example.com"),
        create_account("account3@example.com"),
    ]


class TestStickyStrategy:
    """Test StickyStrategy."""

    def test_select_first_account_initially(self, three_accounts):
        """Test selecting first account on initial request."""
        strategy = StickyStrategy()
        result = strategy.select_account(
            three_accounts,
            "claude-sonnet-4-5",
            {"current_index": 0}
        )

        assert result.account == three_accounts[0]
        assert result.index == 0
        assert result.wait_ms == 0

    def test_stick_to_current_account(self, three_accounts):
        """Test sticking to current account when available."""
        strategy = StickyStrategy()

        # First request
        result1 = strategy.select_account(
            three_accounts,
            "claude-sonnet-4-5",
            {"current_index": 1}
        )

        # Second request - should stick to same account
        result2 = strategy.select_account(
            three_accounts,
            "claude-sonnet-4-5",
            {"current_index": 1}
        )

        assert result1.account == three_accounts[1]
        assert result2.account == three_accounts[1]
        assert result1.index == result2.index == 1

    def test_switch_when_current_disabled(self, three_accounts):
        """Test switching when current account disabled."""
        strategy = StickyStrategy()

        # Disable current account
        three_accounts[0].enabled = False

        result = strategy.select_account(
            three_accounts,
            "claude-sonnet-4-5",
            {"current_index": 0}
        )

        # Should switch to next available
        assert result.account == three_accounts[1]
        assert result.index == 1

    def test_switch_when_current_invalid(self, three_accounts):
        """Test switching when current account invalid."""
        strategy = StickyStrategy()

        # Mark current account invalid
        three_accounts[0].is_invalid = True

        result = strategy.select_account(
            three_accounts,
            "claude-sonnet-4-5",
            {"current_index": 0}
        )

        # Should switch to next available
        assert result.account == three_accounts[1]
        assert result.index == 1

    def test_switch_when_current_rate_limited_long(self, three_accounts):
        """Test switching when current account rate limited for >2min."""
        strategy = StickyStrategy()

        # Rate limit current account for 5 minutes
        reset_time = int((datetime.now() + timedelta(minutes=5)).timestamp() * 1000)
        three_accounts[0].model_rate_limits["claude-sonnet-4-5"] = ModelRateLimit(
            is_rate_limited=True,
            reset_time=reset_time,
            consecutive_failures=1
        )

        result = strategy.select_account(
            three_accounts,
            "claude-sonnet-4-5",
            {"current_index": 0}
        )

        # Should switch to next available
        assert result.account == three_accounts[1]
        assert result.index == 1

    def test_wait_when_current_rate_limited_short(self, three_accounts):
        """Test waiting when current account rate limited for <2min."""
        strategy = StickyStrategy()

        # Rate limit current account for 1 minute
        reset_time = int((datetime.now() + timedelta(minutes=1)).timestamp() * 1000)
        three_accounts[0].model_rate_limits["claude-sonnet-4-5"] = ModelRateLimit(
            is_rate_limited=True,
            reset_time=reset_time,
            consecutive_failures=1
        )

        # Disable other accounts so we have to wait
        three_accounts[1].enabled = False
        three_accounts[2].enabled = False

        result = strategy.select_account(
            three_accounts,
            "claude-sonnet-4-5",
            {"current_index": 0}
        )

        # Should wait for current account
        assert result.account is None
        assert result.wait_ms > 0
        assert result.wait_ms <= 120000  # Max 2 minutes

    def test_empty_accounts_list(self):
        """Test with empty accounts list."""
        strategy = StickyStrategy()
        result = strategy.select_account([], "claude-sonnet-4-5")

        assert result.account is None
        assert result.index == 0
        assert result.wait_ms == 0


class TestRoundRobinStrategy:
    """Test RoundRobinStrategy."""

    def test_rotate_through_accounts(self, three_accounts):
        """Test rotating through all accounts."""
        strategy = RoundRobinStrategy()

        # First request (cursor starts at 0, selects cursor+1 = 1)
        result1 = strategy.select_account(three_accounts, "claude-sonnet-4-5")
        # Second request (cursor now 1, selects cursor+1 = 2)
        result2 = strategy.select_account(three_accounts, "claude-sonnet-4-5")
        # Third request (cursor now 2, selects cursor+1 = 0, wraps around)
        result3 = strategy.select_account(three_accounts, "claude-sonnet-4-5")

        # Should rotate through accounts starting from index 1
        assert result1.account == three_accounts[1]
        assert result2.account == three_accounts[2]
        assert result3.account == three_accounts[0]

    def test_wrap_around_after_last_account(self, three_accounts):
        """Test wrapping around after full rotation."""
        strategy = RoundRobinStrategy()

        # Rotate through all accounts (1, 2, 0)
        for _ in range(3):
            strategy.select_account(three_accounts, "claude-sonnet-4-5")

        # Next should continue rotation (cursor is 0, select 1)
        result = strategy.select_account(three_accounts, "claude-sonnet-4-5")
        assert result.account == three_accounts[1]

    def test_skip_disabled_accounts(self, three_accounts):
        """Test skipping disabled accounts."""
        strategy = RoundRobinStrategy()

        # Disable middle account
        three_accounts[1].enabled = False

        result1 = strategy.select_account(three_accounts, "claude-sonnet-4-5")
        result2 = strategy.select_account(three_accounts, "claude-sonnet-4-5")

        # Should skip disabled account (starts at 1, skips to 2, then wraps to 0)
        assert result1.account == three_accounts[2]
        assert result2.account == three_accounts[0]

    def test_skip_rate_limited_accounts(self, three_accounts):
        """Test skipping rate-limited accounts."""
        strategy = RoundRobinStrategy()

        # Rate limit first account
        reset_time = int((datetime.now() + timedelta(minutes=5)).timestamp() * 1000)
        three_accounts[0].model_rate_limits["claude-sonnet-4-5"] = ModelRateLimit(
            is_rate_limited=True,
            reset_time=reset_time,
            consecutive_failures=1
        )

        result = strategy.select_account(three_accounts, "claude-sonnet-4-5")

        # Should skip rate-limited account
        assert result.account == three_accounts[1]

    def test_reset_cursor(self, three_accounts):
        """Test resetting cursor."""
        strategy = RoundRobinStrategy()

        # Advance cursor
        strategy.select_account(three_accounts, "claude-sonnet-4-5")
        strategy.select_account(three_accounts, "claude-sonnet-4-5")

        # Reset
        strategy.reset_cursor()

        # Should start from beginning (cursor=0, selects cursor+1=1)
        result = strategy.select_account(three_accounts, "claude-sonnet-4-5")
        assert result.account == three_accounts[1]

    def test_all_accounts_unavailable(self, three_accounts):
        """Test when all accounts unavailable."""
        strategy = RoundRobinStrategy()

        # Disable all accounts
        for account in three_accounts:
            account.enabled = False

        result = strategy.select_account(three_accounts, "claude-sonnet-4-5")

        assert result.account is None
        assert result.wait_ms >= 0


class TestHybridStrategy:
    """Test HybridStrategy."""

    def test_select_highest_health_score(self, three_accounts):
        """Test selecting account with highest health score."""
        strategy = HybridStrategy()

        # Set different health scores
        three_accounts[0].health_score = 0.5
        three_accounts[1].health_score = 1.0
        three_accounts[2].health_score = 0.7

        result = strategy.select_account(three_accounts, "claude-sonnet-4-5")

        # Should select account with highest health
        assert result.account == three_accounts[1]

    def test_penalize_consecutive_failures(self, three_accounts):
        """Test penalizing accounts with failures."""
        strategy = HybridStrategy()

        # Add failures to first account
        three_accounts[0].model_rate_limits["claude-sonnet-4-5"] = ModelRateLimit(
            is_rate_limited=False,
            reset_time=None,
            consecutive_failures=3
        )

        result = strategy.select_account(three_accounts, "claude-sonnet-4-5")

        # Should prefer account without failures
        assert result.account in (three_accounts[1], three_accounts[2])

    def test_prefer_recently_used(self, three_accounts):
        """Test preferring recently used accounts."""
        strategy = HybridStrategy()

        # Set last used times
        now_ms = int(datetime.now().timestamp() * 1000)
        three_accounts[0].last_used = now_ms - 60000  # 1 minute ago
        three_accounts[1].last_used = now_ms - 600000  # 10 minutes ago
        three_accounts[2].last_used = None  # Never used

        result = strategy.select_account(three_accounts, "claude-sonnet-4-5")

        # Should prefer recently used (cache continuity)
        assert result.account == three_accounts[0]

    def test_notify_success_improves_health(self, three_accounts):
        """Test that success improves health score."""
        strategy = HybridStrategy()
        account = three_accounts[0]
        account.health_score = 0.5

        strategy.notify_success(account, "claude-sonnet-4-5")

        assert account.health_score > 0.5

    def test_notify_failure_degrades_health(self, three_accounts):
        """Test that failure degrades health score."""
        strategy = HybridStrategy()
        account = three_accounts[0]
        account.health_score = 1.0

        strategy.notify_failure(account, "claude-sonnet-4-5", "rate_limit")

        assert account.health_score < 1.0

    def test_custom_weights(self, three_accounts):
        """Test custom scoring weights."""
        custom_weights = {
            "health": 1.0,
            "failures": 0.0,
            "recency": 0.0,
            "availability": 0.0,
        }
        strategy = HybridStrategy({"weights": custom_weights})

        # Set different health scores
        three_accounts[0].health_score = 0.3
        three_accounts[1].health_score = 0.9
        three_accounts[2].health_score = 0.5

        result = strategy.select_account(three_accounts, "claude-sonnet-4-5")

        # Should select based purely on health
        assert result.account == three_accounts[1]

    def test_empty_accounts_list(self):
        """Test with empty accounts list."""
        strategy = HybridStrategy()
        result = strategy.select_account([], "claude-sonnet-4-5")

        assert result.account is None
        assert result.index == 0
        assert result.wait_ms == 0


class TestBaseStrategy:
    """Test BaseStrategy common functionality."""

    def test_get_usable_accounts(self, three_accounts):
        """Test getting usable accounts."""
        strategy = StickyStrategy()  # Use concrete implementation

        # Disable one account
        three_accounts[1].enabled = False

        usable = strategy.get_usable_accounts(three_accounts, "claude-sonnet-4-5")

        assert len(usable) == 2
        assert usable[0][1] == three_accounts[0]
        assert usable[1][1] == three_accounts[2]

    def test_calculate_min_wait_time(self, three_accounts):
        """Test calculating minimum wait time."""
        strategy = StickyStrategy()

        # Rate limit accounts with different reset times
        now_ms = int(datetime.now().timestamp() * 1000)
        three_accounts[0].model_rate_limits["claude-sonnet-4-5"] = ModelRateLimit(
            is_rate_limited=True,
            reset_time=now_ms + 60000,  # 1 minute
            consecutive_failures=1
        )
        three_accounts[1].model_rate_limits["claude-sonnet-4-5"] = ModelRateLimit(
            is_rate_limited=True,
            reset_time=now_ms + 120000,  # 2 minutes
            consecutive_failures=1
        )

        wait_ms = strategy.calculate_min_wait_time(three_accounts, "claude-sonnet-4-5")

        # Should return shortest wait time
        assert 55000 <= wait_ms <= 65000  # ~1 minute (with some tolerance)

    def test_notify_success_resets_failures(self, three_accounts):
        """Test that success resets consecutive failures."""
        strategy = StickyStrategy()
        account = three_accounts[0]

        # Add failures
        account.model_rate_limits["claude-sonnet-4-5"] = ModelRateLimit(
            is_rate_limited=False,
            reset_time=None,
            consecutive_failures=3
        )

        strategy.notify_success(account, "claude-sonnet-4-5")

        assert account.model_rate_limits["claude-sonnet-4-5"].consecutive_failures == 0

    # Removed test_notify_failure_increments_failures as BaseStrategy.notify_failure is now a no-op
