# -*- coding: utf-8 -*-

"""
Unit tests for AccountManager.

Tests:
- Initialization and account loading
- Account selection with different strategies
- Success/failure notifications
- Rate limit management
- Invalid account handling
- State persistence
- Thread safety
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from kiro.account_manager import AccountManager
from kiro.account_storage import Account, AccountTokens, ModelRateLimit


@pytest.fixture
def temp_accounts_file(tmp_path):
    """Create temporary accounts file."""
    return str(tmp_path / "accounts.json")


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
def create_test_accounts_file(temp_accounts_file, sample_tokens):
    """Create accounts file with test data."""
    import json

    accounts_data = {
        "accounts": [
            {
                "email": f"test{i}@example.com",
                "tokens": {
                    "access": f"access_{i}",
                    "refresh": f"refresh_{i}",
                    "expires_at": sample_tokens.expires_at
                },
                "enabled": True,
                "is_invalid": False,
                "model_rate_limits": {},
                "last_used": None,
                "health_score": 1.0,
                "metadata": {}
            }
            for i in range(3)
        ],
        "settings": {
            "strategy": "hybrid",
            "active_index": 0
        }
    }

    Path(temp_accounts_file).parent.mkdir(parents=True, exist_ok=True)
    with open(temp_accounts_file, "w") as f:
        json.dump(accounts_data, f)

    return temp_accounts_file


@pytest.mark.asyncio
class TestAccountManager:
    """Test AccountManager class."""

    async def test_initialize_creates_default_file(self, temp_accounts_file):
        """Test initialization creates default file if missing."""
        manager = AccountManager(temp_accounts_file)
        await manager.initialize()

        assert Path(temp_accounts_file).exists()
        assert len(manager.accounts) == 0

    async def test_initialize_loads_existing_accounts(self, create_test_accounts_file):
        """Test initialization loads existing accounts."""
        manager = AccountManager(create_test_accounts_file)
        await manager.initialize()

        assert len(manager.accounts) == 3
        assert manager.accounts[0].email == "test0@example.com"
        assert manager.settings.strategy == "hybrid"

    async def test_initialize_only_once(self, create_test_accounts_file):
        """Test initialization only happens once."""
        manager = AccountManager(create_test_accounts_file)

        await manager.initialize()
        initial_accounts = len(manager.accounts)

        await manager.initialize()
        assert len(manager.accounts) == initial_accounts

    async def test_select_account_returns_available(self, create_test_accounts_file):
        """Test selecting available account."""
        manager = AccountManager(create_test_accounts_file, strategy_name="round-robin")
        await manager.initialize()

        result = await manager.select_account("claude-sonnet-4-5")

        assert result.account is not None
        assert result.account.email in ["test0@example.com", "test1@example.com", "test2@example.com"]
        assert result.wait_ms == 0

    async def test_select_account_not_initialized_raises(self, temp_accounts_file):
        """Test selecting account before initialization raises error."""
        manager = AccountManager(temp_accounts_file)

        with pytest.raises(RuntimeError, match="not initialized"):
            await manager.select_account("claude-sonnet-4-5")

    async def test_notify_success_resets_failures(self, create_test_accounts_file):
        """Test notifying success resets consecutive failures."""
        manager = AccountManager(create_test_accounts_file)
        await manager.initialize()

        account = manager.accounts[0]

        # Add failures
        account.model_rate_limits["claude-sonnet-4-5"] = ModelRateLimit(
            is_rate_limited=False,
            reset_time=None,
            consecutive_failures=3
        )

        await manager.notify_success(account, "claude-sonnet-4-5")

        assert account.model_rate_limits["claude-sonnet-4-5"].consecutive_failures == 0

    async def test_notify_failure_marks_rate_limited(self, create_test_accounts_file):
        """Test notifying failure marks account as rate limited."""
        manager = AccountManager(create_test_accounts_file)
        await manager.initialize()

        account = manager.accounts[0]

        await manager.notify_failure(
            account,
            "claude-sonnet-4-5",
            "rate_limit",
            retry_after_ms=60000
        )

        assert "claude-sonnet-4-5" in account.model_rate_limits
        limit = account.model_rate_limits["claude-sonnet-4-5"]
        assert limit.is_rate_limited is True
        assert limit.reset_time is not None
        assert limit.consecutive_failures == 1

    async def test_notify_failure_marks_invalid_on_auth_error(self, create_test_accounts_file):
        """Test notifying auth error marks account as invalid."""
        manager = AccountManager(create_test_accounts_file)
        await manager.initialize()

        account = manager.accounts[0]

        await manager.notify_failure(account, "claude-sonnet-4-5", "auth_error")

        assert account.is_invalid is True

    async def test_mark_account_invalid(self, create_test_accounts_file):
        """Test marking account as invalid by email."""
        manager = AccountManager(create_test_accounts_file)
        await manager.initialize()

        await manager.mark_account_invalid("test1@example.com")

        account = next(a for a in manager.accounts if a.email == "test1@example.com")
        assert account.is_invalid is True

    async def test_clear_account_invalid(self, create_test_accounts_file):
        """Test clearing invalid flag."""
        manager = AccountManager(create_test_accounts_file)
        await manager.initialize()

        # Mark invalid
        await manager.mark_account_invalid("test1@example.com")

        # Clear invalid
        await manager.clear_account_invalid("test1@example.com")

        account = next(a for a in manager.accounts if a.email == "test1@example.com")
        assert account.is_invalid is False

    async def test_get_account_status(self, create_test_accounts_file):
        """Test getting account status."""
        manager = AccountManager(create_test_accounts_file)
        await manager.initialize()

        # Mark one account invalid
        manager.accounts[1].is_invalid = True

        status = await manager.get_account_status()

        assert status["total"] == 3
        assert status["enabled"] == 3
        assert status["invalid"] == 1
        assert status["available"] == 2
        assert status["strategy"] == "hybrid"
        assert len(status["accounts"]) == 3

    async def test_reload_accounts(self, create_test_accounts_file):
        """Test reloading accounts from storage."""
        manager = AccountManager(create_test_accounts_file)
        await manager.initialize()

        # Modify file externally
        import json
        with open(create_test_accounts_file, "r") as f:
            data = json.load(f)

        data["accounts"].append({
            "email": "test3@example.com",
            "tokens": {
                "access": "access_3",
                "refresh": "refresh_3",
                "expires_at": int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)
            },
            "enabled": True,
            "is_invalid": False,
            "model_rate_limits": {},
            "last_used": None,
            "health_score": 1.0,
            "metadata": {}
        })

        with open(create_test_accounts_file, "w") as f:
            json.dump(data, f)

        # Reload
        await manager.reload()

        assert len(manager.accounts) == 4

    async def test_clear_expired_limits(self, create_test_accounts_file):
        """Test clearing expired rate limits."""
        manager = AccountManager(create_test_accounts_file)
        await manager.initialize()

        account = manager.accounts[0]

        # Add expired rate limit
        reset_time = int((datetime.now() - timedelta(minutes=1)).timestamp() * 1000)
        account.model_rate_limits["claude-sonnet-4-5"] = ModelRateLimit(
            is_rate_limited=True,
            reset_time=reset_time,
            consecutive_failures=1
        )

        # Select account (triggers cleanup)
        await manager.select_account("claude-sonnet-4-5")

        # Rate limit should be cleared
        limit = account.model_rate_limits["claude-sonnet-4-5"]
        assert limit.is_rate_limited is False

    async def test_exponential_backoff_on_failures(self, create_test_accounts_file):
        """Test exponential backoff on consecutive failures."""
        manager = AccountManager(create_test_accounts_file)
        await manager.initialize()

        account = manager.accounts[0]

        # First failure
        await manager.notify_failure(account, "claude-sonnet-4-5", "rate_limit")
        limit1 = account.model_rate_limits["claude-sonnet-4-5"]
        reset1 = limit1.reset_time

        # Second failure
        await manager.notify_failure(account, "claude-sonnet-4-5", "rate_limit")
        limit2 = account.model_rate_limits["claude-sonnet-4-5"]
        reset2 = limit2.reset_time

        # Reset time should increase (exponential backoff)
        assert reset2 > reset1
        assert limit2.consecutive_failures == 2

    async def test_strategy_selection(self, create_test_accounts_file):
        """Test different strategy selection."""
        # Test sticky
        manager_sticky = AccountManager(create_test_accounts_file, strategy_name="sticky")
        await manager_sticky.initialize()
        assert manager_sticky.strategy_name == "sticky"

        # Test round-robin
        manager_rr = AccountManager(create_test_accounts_file, strategy_name="round-robin")
        await manager_rr.initialize()
        assert manager_rr.strategy_name == "round-robin"

        # Test hybrid
        manager_hybrid = AccountManager(create_test_accounts_file, strategy_name="hybrid")
        await manager_hybrid.initialize()
        assert manager_hybrid.strategy_name == "hybrid"

    async def test_concurrent_access(self, create_test_accounts_file):
        """Test thread-safe concurrent access."""
        manager = AccountManager(create_test_accounts_file, strategy_name="round-robin")
        await manager.initialize()

        # Simulate concurrent requests
        async def make_request():
            result = await manager.select_account("claude-sonnet-4-5")
            if result.account:
                await manager.notify_success(result.account, "claude-sonnet-4-5")

        # Run 10 concurrent requests
        await asyncio.gather(*[make_request() for _ in range(10)])

        # All accounts should have been used
        assert any(a.last_used is not None for a in manager.accounts)

    async def test_all_accounts_rate_limited(self, create_test_accounts_file):
        """Test behavior when all accounts rate limited."""
        manager = AccountManager(create_test_accounts_file)
        await manager.initialize()

        # Rate limit all accounts
        reset_time = int((datetime.now() + timedelta(minutes=5)).timestamp() * 1000)
        for account in manager.accounts:
            account.model_rate_limits["claude-sonnet-4-5"] = ModelRateLimit(
                is_rate_limited=True,
                reset_time=reset_time,
                consecutive_failures=1
            )

        result = await manager.select_account("claude-sonnet-4-5")

        # Should return no account with wait time
        assert result.account is None
        assert result.wait_ms > 0
