# -*- coding: utf-8 -*-

"""
Unit tests for account storage module.

Tests:
- Account dataclass serialization/deserialization
- AccountStorage load/save operations
- Atomic writes and backup creation
- Schema validation
- Rate limit expiration logic
"""

import json
import pytest
from pathlib import Path
from datetime import datetime, timedelta

from kiro.account_storage import (
    Account,
    AccountTokens,
    ModelRateLimit,
    AccountSettings,
    AccountStorage,
)


@pytest.fixture
def temp_accounts_file(tmp_path):
    """Create temporary accounts file path."""
    return tmp_path / "accounts.json"


@pytest.fixture
def sample_tokens():
    """Create sample tokens."""
    expires_at = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)
    return AccountTokens(
        access="access_token_123",
        refresh="refresh_token_456",
        expires_at=expires_at
    )


@pytest.fixture
def sample_account(sample_tokens):
    """Create sample account."""
    return Account(
        email="test@example.com",
        tokens=sample_tokens,
        enabled=True,
        is_invalid=False,
        model_rate_limits={},
        last_used=int(datetime.now().timestamp() * 1000),
        health_score=1.0,
        metadata={"region": "us-east-1"}
    )


class TestAccountTokens:
    """Test AccountTokens dataclass."""

    def test_is_expired_not_expired(self):
        """Test token not expired."""
        expires_at = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)
        tokens = AccountTokens(
            access="access",
            refresh="refresh",
            expires_at=expires_at
        )
        assert not tokens.is_expired()

    def test_is_expired_within_threshold(self):
        """Test token expires within threshold."""
        # Expires in 4 minutes (threshold is 5 minutes)
        expires_at = int((datetime.now() + timedelta(minutes=4)).timestamp() * 1000)
        tokens = AccountTokens(
            access="access",
            refresh="refresh",
            expires_at=expires_at
        )
        assert tokens.is_expired(threshold_ms=300000)  # 5 minutes

    def test_is_expired_already_expired(self):
        """Test token already expired."""
        expires_at = int((datetime.now() - timedelta(hours=1)).timestamp() * 1000)
        tokens = AccountTokens(
            access="access",
            refresh="refresh",
            expires_at=expires_at
        )
        assert tokens.is_expired()


class TestModelRateLimit:
    """Test ModelRateLimit dataclass."""

    def test_is_expired_not_limited(self):
        """Test rate limit not active."""
        limit = ModelRateLimit(
            is_rate_limited=False,
            reset_time=None,
            consecutive_failures=0
        )
        assert limit.is_expired()

    def test_is_expired_reset_time_passed(self):
        """Test rate limit expired."""
        reset_time = int((datetime.now() - timedelta(minutes=1)).timestamp() * 1000)
        limit = ModelRateLimit(
            is_rate_limited=True,
            reset_time=reset_time,
            consecutive_failures=1
        )
        assert limit.is_expired()

    def test_is_expired_not_yet(self):
        """Test rate limit still active."""
        reset_time = int((datetime.now() + timedelta(minutes=5)).timestamp() * 1000)
        limit = ModelRateLimit(
            is_rate_limited=True,
            reset_time=reset_time,
            consecutive_failures=1
        )
        assert not limit.is_expired()


class TestAccount:
    """Test Account dataclass."""

    def test_is_available_for_model_enabled(self, sample_account):
        """Test account available when enabled."""
        assert sample_account.is_available_for_model("claude-sonnet-4-5")

    def test_is_available_for_model_disabled(self, sample_account):
        """Test account unavailable when disabled."""
        sample_account.enabled = False
        assert not sample_account.is_available_for_model("claude-sonnet-4-5")

    def test_is_available_for_model_invalid(self, sample_account):
        """Test account unavailable when invalid."""
        sample_account.is_invalid = True
        assert not sample_account.is_available_for_model("claude-sonnet-4-5")

    def test_is_available_for_model_rate_limited(self, sample_account):
        """Test account unavailable when rate limited."""
        reset_time = int((datetime.now() + timedelta(minutes=5)).timestamp() * 1000)
        sample_account.model_rate_limits["claude-sonnet-4-5"] = ModelRateLimit(
            is_rate_limited=True,
            reset_time=reset_time,
            consecutive_failures=1
        )
        assert not sample_account.is_available_for_model("claude-sonnet-4-5")

    def test_is_available_for_model_rate_limit_expired(self, sample_account):
        """Test account available when rate limit expired."""
        reset_time = int((datetime.now() - timedelta(minutes=1)).timestamp() * 1000)
        sample_account.model_rate_limits["claude-sonnet-4-5"] = ModelRateLimit(
            is_rate_limited=True,
            reset_time=reset_time,
            consecutive_failures=1
        )
        assert sample_account.is_available_for_model("claude-sonnet-4-5")

    def test_to_dict_serialization(self, sample_account):
        """Test account serialization to dict."""
        data = sample_account.to_dict()

        assert data["email"] == "test@example.com"
        assert data["enabled"] is True
        assert data["is_invalid"] is False
        assert "tokens" in data
        assert data["tokens"]["access"] == "access_token_123"
        assert data["health_score"] == 1.0
        assert data["metadata"]["region"] == "us-east-1"

    def test_from_dict_deserialization(self, sample_account):
        """Test account deserialization from dict."""
        data = sample_account.to_dict()
        restored = Account.from_dict(data)

        assert restored.email == sample_account.email
        assert restored.enabled == sample_account.enabled
        assert restored.is_invalid == sample_account.is_invalid
        assert restored.tokens.access == sample_account.tokens.access
        assert restored.health_score == sample_account.health_score


class TestAccountStorage:
    """Test AccountStorage class with async methods."""

    @pytest.mark.asyncio
    async def test_create_default(self, temp_accounts_file):
        """Test creating default accounts file."""
        storage = AccountStorage(str(temp_accounts_file))
        await storage.create_default()

        assert temp_accounts_file.exists()

        with open(temp_accounts_file, "r") as f:
            data = json.load(f)

        assert "accounts" in data
        assert "settings" in data
        assert data["accounts"] == []
        assert data["settings"]["strategy"] == "hybrid"

    @pytest.mark.asyncio
    async def test_save_and_load(self, temp_accounts_file, sample_account):
        """Test saving and loading accounts."""
        storage = AccountStorage(str(temp_accounts_file))
        settings = AccountSettings(strategy="sticky", active_index=0)

        # Save
        await storage.save([sample_account], settings)

        # Load
        loaded_accounts, loaded_settings = await storage.load()

        assert len(loaded_accounts) == 1
        assert loaded_accounts[0].email == sample_account.email
        assert loaded_settings.strategy == "sticky"

    @pytest.mark.asyncio
    async def test_save_overwrites_existing(self, temp_accounts_file, sample_account):
        """Test that save overwrites existing file with updated data."""
        storage = AccountStorage(str(temp_accounts_file))
        settings = AccountSettings()

        # First save
        await storage.save([sample_account], settings)

        # Modify and save again
        sample_account.health_score = 0.5
        await storage.save([sample_account], settings)

        # Load and verify updated data
        loaded_accounts, _ = await storage.load()
        assert len(loaded_accounts) == 1
        assert loaded_accounts[0].health_score == 0.5

    @pytest.mark.asyncio
    async def test_load_nonexistent_file(self, temp_accounts_file):
        """Test loading from nonexistent file returns empty defaults."""
        storage = AccountStorage(str(temp_accounts_file))

        accounts, settings = await storage.load()

        assert accounts == []
        assert settings.strategy == "hybrid"

    @pytest.mark.asyncio
    async def test_save_atomic_write(self, temp_accounts_file, sample_account):
        """Test atomic write (temp file then rename)."""
        storage = AccountStorage(str(temp_accounts_file))
        settings = AccountSettings()

        await storage.save([sample_account], settings)

        # Temp file should not exist after save
        temp_path = temp_accounts_file.with_suffix(".tmp")
        assert not temp_path.exists()

        # Actual file should exist
        assert temp_accounts_file.exists()

    @pytest.mark.asyncio
    async def test_save_multiple_accounts(self, temp_accounts_file, sample_tokens):
        """Test saving multiple accounts."""
        storage = AccountStorage(str(temp_accounts_file))

        accounts = [
            Account(
                email=f"test{i}@example.com",
                tokens=sample_tokens,
                enabled=True,
                health_score=1.0 - (i * 0.1)
            )
            for i in range(5)
        ]

        settings = AccountSettings()
        await storage.save(accounts, settings)

        loaded_accounts, _ = await storage.load()

        assert len(loaded_accounts) == 5
        assert loaded_accounts[0].email == "test0@example.com"
        assert loaded_accounts[4].email == "test4@example.com"
        assert loaded_accounts[4].health_score == 0.6

    @pytest.mark.asyncio
    async def test_load_invalid_json(self, temp_accounts_file):
        """Test loading invalid JSON raises JSONDecodeError."""
        storage = AccountStorage(str(temp_accounts_file))

        # Write invalid JSON
        with open(temp_accounts_file, "w") as f:
            f.write("{ invalid json")

        with pytest.raises(json.JSONDecodeError):
            await storage.load()

    @pytest.mark.asyncio
    async def test_load_missing_accounts_key(self, temp_accounts_file):
        """Test loading file without accounts key raises ValueError."""
        storage = AccountStorage(str(temp_accounts_file))

        # Write valid JSON but missing accounts key
        with open(temp_accounts_file, "w") as f:
            json.dump({"settings": {}}, f)

        with pytest.raises(ValueError, match="missing 'accounts' key"):
            await storage.load()
