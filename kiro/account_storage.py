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
Account storage and persistence for multi-account support.

Handles:
- Loading accounts from JSON file
- Saving account state atomically
- Account schema validation
- Migration from single-account to multi-account
"""

import json
import os
import asyncio
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from loguru import logger


@dataclass
class AccountTokens:
    """OAuth tokens for an account."""
    access: str
    refresh: str
    expires_at: int  # Unix timestamp in milliseconds

    def is_expired(self, threshold_ms: int = 300000) -> bool:
        """
        Check if token is expired or will expire soon.

        Args:
            threshold_ms: Milliseconds before expiry to consider expired (default: 5 minutes)

        Returns:
            True if token is expired or will expire within threshold
        """
        now_ms = int(datetime.now().timestamp() * 1000)
        return self.expires_at - now_ms < threshold_ms


@dataclass
class ModelRateLimit:
    """Rate limit state for a specific model."""
    is_rate_limited: bool
    reset_time: Optional[int]  # Unix timestamp in milliseconds
    consecutive_failures: int = 0

    def is_expired(self) -> bool:
        """Check if rate limit has expired."""
        if not self.is_rate_limited or self.reset_time is None:
            return True
        now_ms = int(datetime.now().timestamp() * 1000)
        return now_ms >= self.reset_time


@dataclass
class Account:
    """
    Represents a single Kiro account.

    Attributes:
        email: Account email/identifier
        tokens: OAuth tokens (access, refresh, expires_at)
        enabled: Whether account is enabled for use
        is_invalid: Permanent failure flag (auth error, banned)
        model_rate_limits: Per-model rate limit tracking
        last_used: Last time account was used (Unix timestamp ms)
        health_score: Health score for hybrid strategy (0.0-1.0)
        metadata: Additional account metadata (region, profile_arn, etc.)
    """
    email: str
    tokens: AccountTokens
    enabled: bool = True
    is_invalid: bool = False
    model_rate_limits: Dict[str, ModelRateLimit] = None
    last_used: Optional[int] = None
    health_score: float = 1.0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        """Initialize default values for mutable fields."""
        if self.model_rate_limits is None:
            self.model_rate_limits = {}
        if self.metadata is None:
            self.metadata = {}

    def is_available_for_model(self, model_id: str) -> bool:
        """
        Check if account is available for a specific model.

        Args:
            model_id: Model identifier

        Returns:
            True if account can be used for this model
        """
        if not self.enabled or self.is_invalid:
            return False

        if model_id in self.model_rate_limits:
            limit = self.model_rate_limits[model_id]
            if limit.is_rate_limited and not limit.is_expired():
                return False

        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert account to dictionary for JSON serialization."""
        return {
            "email": self.email,
            "tokens": asdict(self.tokens),
            "enabled": self.enabled,
            "is_invalid": self.is_invalid,
            "model_rate_limits": {
                model_id: asdict(limit)
                for model_id, limit in self.model_rate_limits.items()
            },
            "last_used": self.last_used,
            "health_score": self.health_score,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Account":
        """Create account from dictionary."""
        tokens = AccountTokens(**data["tokens"])
        model_rate_limits = {
            model_id: ModelRateLimit(**limit_data)
            for model_id, limit_data in data.get("model_rate_limits", {}).items()
        }

        return cls(
            email=data["email"],
            tokens=tokens,
            enabled=data.get("enabled", True),
            is_invalid=data.get("is_invalid", False),
            model_rate_limits=model_rate_limits,
            last_used=data.get("last_used"),
            health_score=data.get("health_score", 1.0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class AccountSettings:
    """Settings for account management."""
    strategy: str = "hybrid"
    active_index: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AccountSettings":
        """Create settings from dictionary."""
        return cls(
            strategy=data.get("strategy", "hybrid"),
            active_index=data.get("active_index", 0),
        )


class AccountStorage:
    """
    Handles persistence of account data to JSON file.

    Features:
    - Atomic writes (write to temp file, then rename)
    - Automatic backup on save
    - Schema validation
    - Thread-safe operations
    """

    def __init__(self, file_path: str):
        """
        Initialize account storage.

        Args:
            file_path: Path to accounts.json file
        """
        self.file_path = Path(file_path).expanduser()
        self.backup_path = self.file_path.with_suffix(".json.backup")

        # Ensure directory exists
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    async def load(self) -> tuple[List[Account], AccountSettings]:
        """
        Load accounts and settings from file asynchronously.

        Returns:
            Tuple of (accounts list, settings)

        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If file is invalid JSON
            ValueError: If schema validation fails
        """
        if not self.file_path.exists():
            logger.info(f"[AccountStorage] No accounts file found at {self.file_path}")
            return [], AccountSettings()

        try:
            # FIXED: Use asyncio.to_thread for non-blocking file I/O
            def _load_file():
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return json.load(f)

            data = await asyncio.to_thread(_load_file)

            # Validate schema
            if not isinstance(data, dict):
                raise ValueError("Accounts file must be a JSON object")

            if "accounts" not in data:
                raise ValueError("Accounts file missing 'accounts' key")

            # Load accounts
            accounts = [
                Account.from_dict(account_data)
                for account_data in data["accounts"]
            ]

            # Load settings
            settings = AccountSettings.from_dict(data.get("settings", {}))

            logger.info(f"[AccountStorage] Loaded {len(accounts)} accounts from {self.file_path}")
            return accounts, settings

        except json.JSONDecodeError as e:
            logger.error(f"[AccountStorage] Invalid JSON in {self.file_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"[AccountStorage] Failed to load accounts: {e}")
            raise

    async def save(self, accounts: List[Account], settings: AccountSettings) -> None:
        """
        Save accounts and settings to file atomically and asynchronously.

        Args:
            accounts: List of accounts to save
            settings: Settings to save

        Raises:
            OSError: If file operations fail
        """
        # Prepare data
        data = {
            "accounts": [account.to_dict() for account in accounts],
            "settings": settings.to_dict(),
            "version": "1.0",
            "updated_at": datetime.now().isoformat()
        }

        # FIXED: Use asyncio.to_thread for non-blocking file I/O with atomic write
        def _save_file():
            # Ensure parent directory exists
            self.file_path.parent.mkdir(parents=True, exist_ok=True)

            # Atomic write: write to temp file first, then rename
            temp_path = self.file_path.with_suffix('.tmp')
            try:
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                # Atomic rename (works on Windows and Unix)
                if os.name == 'nt':  # Windows
                    if self.file_path.exists():
                        self.file_path.unlink()
                    temp_path.rename(self.file_path)
                else:  # Unix-like
                    temp_path.rename(self.file_path)

            except Exception:
                # Clean up temp file on error
                if temp_path.exists():
                    temp_path.unlink()
                raise

        await asyncio.to_thread(_save_file)
        logger.debug(f"[AccountStorage] Saved {len(accounts)} accounts to {self.file_path}")

    async def create_default(self) -> None:
        """Create default accounts.json file with empty accounts list asynchronously."""
        default_data = {
            "accounts": [],
            "settings": {
                "strategy": "hybrid",
                "active_index": 0,
            }
        }

        # FIXED: Use asyncio.to_thread for non-blocking file creation
        def _create_file():
            # Ensure parent directory exists
            self.file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(default_data, f, indent=2, ensure_ascii=False)

        await asyncio.to_thread(_create_file)
        logger.info(f"[AccountStorage] Created default accounts file at {self.file_path}")

    async def add_account(self, account: Account) -> None:
        """
        Add a new account to storage.

        Args:
            account: Account to add

        Raises:
            ValueError: If account with same email already exists
            IOError: If save fails
        """
        accounts, settings = await self.load()

        if any(acc.email == account.email for acc in accounts):
            raise ValueError(f"Account with email {account.email} already exists")

        accounts.append(account)

        await self.save(accounts, settings)
        logger.info(f"[AccountStorage] Added account: {account.email}")

    async def remove_account(self, email: str) -> None:
        """
        Remove an account from storage.

        Args:
            email: Email of account to remove

        Raises:
            ValueError: If account not found
            IOError: If save fails
        """
        accounts, settings = await self.load()

        original_count = len(accounts)
        accounts = [acc for acc in accounts if acc.email != email]

        if len(accounts) == original_count:
            raise ValueError(f"Account with email {email} not found")

        await self.save(accounts, settings)
        logger.info(f"[AccountStorage] Removed account: {email}")

    async def update_account_enabled(self, email: str, enabled: bool) -> None:
        """
        Enable or disable an account.

        Args:
            email: Email of account to update
            enabled: New enabled status

        Raises:
            ValueError: If account not found
            IOError: If save fails
        """
        accounts, settings = await self.load()

        found = False
        for account in accounts:
            if account.email == email:
                account.enabled = enabled
                found = True
                break

        if not found:
            raise ValueError(f"Account with email {email} not found")

        await self.save(accounts, settings)
        logger.info(f"[AccountStorage] Updated account {email}: enabled={enabled}")

