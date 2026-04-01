# -*- coding: utf-8 -*-

"""
Tests for OAuthManager - scan_kiro_ide_accounts and account management methods.

Covers:
- Scanning ~/.aws/sso/cache/ for Kiro IDE credential files
- Handling missing directories, corrupt JSON, non-Kiro files
- Manual account addition and validation
- CLI database import
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def oauth_manager():
    """Creates a fresh OAuthManager instance."""
    from kiro.oauth_manager import OAuthManager
    return OAuthManager()


@pytest.fixture
def mock_sso_cache_dir(tmp_path):
    """
    Creates a temporary ~/.aws/sso/cache/ directory structure
    with sample Kiro credential files and non-Kiro files.
    """
    cache_dir = tmp_path / ".aws" / "sso" / "cache"
    cache_dir.mkdir(parents=True)

    # Valid Kiro credential file (not expired)
    valid_kiro_file = {
        "accessToken": "eyJ_valid_access_token",
        "refreshToken": "eyJ_valid_refresh_token",
        "expiresAt": (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
        "profileArn": "arn:aws:codewhisperer:us-east-1:123456:profile/test",
        "region": "us-east-1",
        "authMethod": "social",
        "provider": "Google"
    }
    (cache_dir / "kiro-auth-token.json").write_text(json.dumps(valid_kiro_file))

    # Expired Kiro credential file
    expired_kiro_file = {
        "accessToken": "eyJ_expired_access_token",
        "refreshToken": "eyJ_expired_refresh_token",
        "expiresAt": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
        "profileArn": "arn:aws:codewhisperer:us-east-1:789:profile/old",
        "region": "eu-west-1",
        "authMethod": "social",
        "provider": "GitHub"
    }
    (cache_dir / "expired-token.json").write_text(json.dumps(expired_kiro_file))

    # Non-Kiro file (no refreshToken)
    aws_sso_file = {
        "accessToken": "some_aws_token",
        "expiresAt": "2099-01-01T00:00:00Z",
        "region": "us-east-1"
    }
    (cache_dir / "aws-sso-regular.json").write_text(json.dumps(aws_sso_file))

    # Corrupt JSON file
    (cache_dir / "corrupt.json").write_text("{invalid json content")

    # Non-JSON file
    (cache_dir / "notes.txt").write_text("This is not a JSON file")

    return cache_dir


@pytest.fixture
def mock_empty_sso_cache_dir(tmp_path):
    """Creates an empty ~/.aws/sso/cache/ directory."""
    cache_dir = tmp_path / ".aws" / "sso" / "cache"
    cache_dir.mkdir(parents=True)
    return cache_dir


# =============================================================================
# Test: scan_kiro_ide_accounts — Success Cases
# =============================================================================

class TestScanKiroIdeAccountsSuccess:
    """Tests for successful scanning of Kiro IDE credential files."""

    @pytest.mark.asyncio
    async def test_scan_finds_valid_kiro_files(self, oauth_manager, mock_sso_cache_dir):
        """
        What it does: Scans a directory with valid Kiro files and returns them.
        Purpose: Verify the scanner correctly identifies and parses Kiro credential files.
        """
        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = mock_sso_cache_dir.parent.parent.parent
            accounts = await oauth_manager.scan_kiro_ide_accounts()

        # Should find exactly 2 Kiro files (valid + expired), skip non-Kiro and corrupt
        assert len(accounts) == 2
        print(f"Found {len(accounts)} accounts as expected")

    @pytest.mark.asyncio
    async def test_scan_extracts_correct_fields(self, oauth_manager, mock_sso_cache_dir):
        """
        What it does: Verifies all expected fields are populated from scanned files.
        Purpose: Ensure email, refresh_token, region, provider are all extracted.
        """
        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = mock_sso_cache_dir.parent.parent.parent
            accounts = await oauth_manager.scan_kiro_ide_accounts()

        # Find the valid (non-expired) account
        valid_accounts = [a for a in accounts if not a["is_expired"]]
        assert len(valid_accounts) == 1

        account = valid_accounts[0]
        assert account["refresh_token"] == "eyJ_valid_refresh_token"
        assert account["region"] == "us-east-1"
        assert account["provider"] == "Google"
        assert account["profile_arn"] is not None
        assert account["file_path"] is not None
        assert "email" in account
        print(f"Valid account fields verified: {account['email']}")

    @pytest.mark.asyncio
    async def test_scan_identifies_expired_accounts(self, oauth_manager, mock_sso_cache_dir):
        """
        What it does: Marks expired token files as is_expired=True.
        Purpose: Frontend can display expired status and warn users.
        """
        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = mock_sso_cache_dir.parent.parent.parent
            accounts = await oauth_manager.scan_kiro_ide_accounts()

        expired = [a for a in accounts if a["is_expired"]]
        assert len(expired) == 1
        assert expired[0]["provider"] == "GitHub"
        assert expired[0]["region"] == "eu-west-1"
        print(f"Expired account detected: {expired[0]['email']}")

    @pytest.mark.asyncio
    async def test_scan_generates_email_from_provider(self, oauth_manager, mock_sso_cache_dir):
        """
        What it does: Generates a meaningful email identifier from the provider name.
        Purpose: Users see 'google-account@kiro.local' instead of a hash.
        """
        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = mock_sso_cache_dir.parent.parent.parent
            accounts = await oauth_manager.scan_kiro_ide_accounts()

        emails = [a["email"] for a in accounts]
        assert any("google" in e.lower() for e in emails), f"Expected Google-based email in {emails}"
        assert any("github" in e.lower() for e in emails), f"Expected GitHub-based email in {emails}"
        print(f"Generated emails: {emails}")


# =============================================================================
# Test: scan_kiro_ide_accounts — Edge Cases
# =============================================================================

class TestScanKiroIdeAccountsEdgeCases:
    """Tests for edge cases and error handling in the scanner."""

    @pytest.mark.asyncio
    async def test_scan_missing_cache_directory(self, oauth_manager, tmp_path):
        """
        What it does: Returns empty list when ~/.aws/sso/cache/ doesn't exist.
        Purpose: Graceful handling for machines without Kiro IDE installed.
        """
        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = tmp_path
            accounts = await oauth_manager.scan_kiro_ide_accounts()

        assert accounts == []
        print("Correctly returned empty list for missing cache dir")

    @pytest.mark.asyncio
    async def test_scan_empty_cache_directory(self, oauth_manager, mock_empty_sso_cache_dir):
        """
        What it does: Returns empty list when cache directory exists but has no files.
        Purpose: Handle freshly installed Kiro IDE with no logins.
        """
        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = mock_empty_sso_cache_dir.parent.parent.parent
            accounts = await oauth_manager.scan_kiro_ide_accounts()

        assert accounts == []
        print("Correctly returned empty list for empty cache dir")

    @pytest.mark.asyncio
    async def test_scan_skips_non_kiro_files(self, oauth_manager, mock_sso_cache_dir):
        """
        What it does: Ignores JSON files that don't have a refreshToken field.
        Purpose: Don't pick up regular AWS SSO cache files as Kiro accounts.
        """
        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = mock_sso_cache_dir.parent.parent.parent
            accounts = await oauth_manager.scan_kiro_ide_accounts()

        file_paths = [a["file_path"] for a in accounts]
        assert not any("aws-sso-regular" in fp for fp in file_paths), \
            "Should not include non-Kiro AWS SSO files"
        print("Correctly skipped non-Kiro files")

    @pytest.mark.asyncio
    async def test_scan_skips_corrupt_json(self, oauth_manager, mock_sso_cache_dir):
        """
        What it does: Gracefully handles corrupt JSON files without crashing.
        Purpose: One bad file shouldn't prevent scanning other valid files.
        """
        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = mock_sso_cache_dir.parent.parent.parent
            accounts = await oauth_manager.scan_kiro_ide_accounts()

        file_names = [Path(a["file_path"]).name for a in accounts]
        assert not any("corrupt" in fn for fn in file_names)
        # Should still find the 2 valid Kiro files
        assert len(accounts) == 2
        print("Correctly skipped corrupt JSON and still found valid files")

    @pytest.mark.asyncio
    async def test_scan_handles_missing_optional_fields(self, oauth_manager, tmp_path):
        """
        What it does: Handles Kiro files that have a refreshToken but lack optional fields.
        Purpose: Minimal Kiro credential files should still be detected.
        """
        cache_dir = tmp_path / ".aws" / "sso" / "cache"
        cache_dir.mkdir(parents=True)

        minimal_file = {
            "refreshToken": "minimal_refresh_token"
        }
        (cache_dir / "minimal.json").write_text(json.dumps(minimal_file))

        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = tmp_path
            accounts = await oauth_manager.scan_kiro_ide_accounts()

        assert len(accounts) == 1
        account = accounts[0]
        assert account["refresh_token"] == "minimal_refresh_token"
        assert account["region"] == "us-east-1"  # Default
        assert account["is_expired"] is False  # No expiry = not expired
        print(f"Minimal file handled correctly: {account['email']}")

    @pytest.mark.asyncio
    async def test_scan_handles_invalid_expires_at(self, oauth_manager, tmp_path):
        """
        What it does: Handles files with malformed expiresAt strings.
        Purpose: Don't crash on unparseable date formats.
        """
        cache_dir = tmp_path / ".aws" / "sso" / "cache"
        cache_dir.mkdir(parents=True)

        bad_date_file = {
            "refreshToken": "token_with_bad_date",
            "expiresAt": "not-a-valid-date"
        }
        (cache_dir / "bad-date.json").write_text(json.dumps(bad_date_file))

        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = tmp_path
            accounts = await oauth_manager.scan_kiro_ide_accounts()

        assert len(accounts) == 1
        # Should still be detected, just with is_expired=False since parsing failed
        assert accounts[0]["is_expired"] is False
        print("Handled invalid expiresAt gracefully")
