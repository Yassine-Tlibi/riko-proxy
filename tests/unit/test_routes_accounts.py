# -*- coding: utf-8 -*-

"""
Tests for account management API routes (/api/v1/accounts/*).

Covers:
- GET /api/v1/accounts/scan — auto-detect Kiro IDE accounts
- POST /api/v1/accounts/add/scan — bulk import scanned accounts
- POST /api/v1/accounts/add/manual — add account with refresh token
- POST /api/v1/accounts/remove — remove an account
- POST /api/v1/accounts/toggle — enable/disable an account
- Authentication enforcement on all endpoints
- Error handling for multi-account disabled state
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from fastapi.testclient import TestClient


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_account_manager():
    """Creates a mock AccountManager with a mock storage."""
    manager = MagicMock()
    manager.storage = MagicMock()
    manager.storage.add_account = AsyncMock()
    manager.storage.remove_account = AsyncMock()
    manager.storage.update_account_enabled = AsyncMock()
    return manager


@pytest.fixture
def mock_oauth_manager_with_scan():
    """Creates a mock OAuthManager with scan_kiro_ide_accounts method."""
    manager = MagicMock()
    manager.scan_kiro_ide_accounts = AsyncMock(return_value=[
        {
            "file_path": "/home/user/.aws/sso/cache/kiro-auth-token.json",
            "file_name": "kiro-auth-token.json",
            "email": "google-account@kiro.local",
            "refresh_token": "eyJ_valid_refresh_token_1",
            "profile_arn": "arn:aws:codewhisperer:us-east-1:123:profile/test",
            "region": "us-east-1",
            "expires_at": "2026-12-31T23:59:59+00:00",
            "auth_method": "social",
            "provider": "Google",
            "is_expired": False
        },
        {
            "file_path": "/home/user/.aws/sso/cache/expired-token.json",
            "file_name": "expired-token.json",
            "email": "github-account@kiro.local",
            "refresh_token": "eyJ_expired_refresh_token",
            "profile_arn": None,
            "region": "eu-west-1",
            "expires_at": "2024-01-01T00:00:00+00:00",
            "auth_method": "social",
            "provider": "GitHub",
            "is_expired": True
        }
    ])
    manager.add_account_manual = AsyncMock(return_value={
        "email": "manual@example.com",
        "auth_type": "kiro_desktop",
        "validated": True
    })
    manager.add_account_from_cli_db = AsyncMock(return_value={
        "email": "cli-imported@kiro.local",
        "auth_type": "aws_sso_oidc",
        "validated": True
    })
    return manager


@pytest.fixture
def app_with_accounts(clean_app, mock_account_manager, mock_oauth_manager_with_scan):
    """Configures the app with mocked account and OAuth managers."""
    clean_app.state.account_manager = mock_account_manager
    clean_app.state.oauth_manager = mock_oauth_manager_with_scan
    return clean_app


@pytest.fixture
def client_with_accounts(app_with_accounts):
    """Test client with multi-account mode enabled."""
    with TestClient(app_with_accounts) as client:
        yield client


@pytest.fixture
def app_without_accounts(clean_app):
    """Configures the app without account manager (multi-account disabled)."""
    clean_app.state.account_manager = None
    clean_app.state.oauth_manager = None
    return clean_app


@pytest.fixture
def client_without_accounts(app_without_accounts):
    """Test client with multi-account mode disabled."""
    with TestClient(app_without_accounts) as client:
        yield client


# =============================================================================
# Test: GET /api/v1/accounts/scan — Success Cases
# =============================================================================

class TestScanEndpointSuccess:
    """Tests for the scan endpoint when everything works correctly."""

    def test_scan_returns_found_accounts(
        self, client_with_accounts, auth_headers, mock_oauth_manager_with_scan
    ):
        """
        What it does: Calls the scan endpoint and gets a list of found accounts.
        Purpose: Verify the endpoint correctly proxies to OAuthManager.scan_kiro_ide_accounts.
        """
        response = client_with_accounts.get(
            "/api/v1/accounts/scan",
            headers=auth_headers()
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 2
        assert len(data["accounts"]) == 2
        print(f"Scan returned {data['count']} accounts")

    def test_scan_returns_correct_account_data(
        self, client_with_accounts, auth_headers
    ):
        """
        What it does: Verifies the structure of returned account objects.
        Purpose: Frontend relies on specific fields being present.
        """
        response = client_with_accounts.get(
            "/api/v1/accounts/scan",
            headers=auth_headers()
        )

        data = response.json()
        account = data["accounts"][0]

        assert "email" in account
        assert "refresh_token" in account
        assert "region" in account
        assert "provider" in account
        assert "is_expired" in account
        assert "file_path" in account
        print(f"Account structure verified: {account['email']}")


# =============================================================================
# Test: GET /api/v1/accounts/scan — Error Cases
# =============================================================================

class TestScanEndpointErrors:
    """Tests for scan endpoint error handling."""

    def test_scan_requires_authentication(self, client_with_accounts):
        """
        What it does: Rejects unauthenticated requests.
        Purpose: Scan endpoint must be protected by API key.
        """
        response = client_with_accounts.get("/api/v1/accounts/scan")

        assert response.status_code in [401, 403, 422]
        print("Unauthenticated scan correctly rejected")

    def test_scan_rejects_invalid_api_key(self, client_with_accounts, auth_headers):
        """
        What it does: Rejects requests with wrong API key.
        Purpose: Only authorized users should scan for accounts.
        """
        response = client_with_accounts.get(
            "/api/v1/accounts/scan",
            headers=auth_headers(invalid=True)
        )

        assert response.status_code in [401, 403]
        print("Invalid API key correctly rejected")

    def test_scan_fails_when_oauth_manager_missing(
        self, client_with_accounts, auth_headers
    ):
        """
        What it does: Returns 503 when OAuth manager is not initialized.
        Purpose: Graceful error when the system isn't fully configured.
        """
        # Remove OAuth manager
        client_with_accounts.app.state.oauth_manager = None

        response = client_with_accounts.get(
            "/api/v1/accounts/scan",
            headers=auth_headers()
        )

        assert response.status_code == 503
        print("Missing OAuth manager correctly returns 503")


# =============================================================================
# Test: POST /api/v1/accounts/add/scan — Bulk Import
# =============================================================================

class TestBulkImportSuccess:
    """Tests for the bulk import endpoint."""

    def test_import_single_account(
        self, client_with_accounts, auth_headers, mock_account_manager
    ):
        """
        What it does: Imports a single scanned account successfully.
        Purpose: Basic happy path for importing a detected account.
        """
        response = client_with_accounts.post(
            "/api/v1/accounts/add/scan",
            headers=auth_headers(),
            json={
                "accounts": [{
                    "email": "google-account@kiro.local",
                    "refresh_token": "eyJ_valid_refresh_token",
                    "region": "us-east-1",
                    "provider": "Google",
                    "profile_arn": "arn:aws:test",
                    "file_path": "/path/to/file.json"
                }]
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["imported"] == 1
        assert data["failed"] == 0
        mock_account_manager.storage.add_account.assert_called_once()
        print(f"Successfully imported 1 account: {data['message']}")

    def test_import_multiple_accounts(
        self, client_with_accounts, auth_headers, mock_account_manager
    ):
        """
        What it does: Imports multiple scanned accounts in one request.
        Purpose: Verify batch import works for multiple selections.
        """
        response = client_with_accounts.post(
            "/api/v1/accounts/add/scan",
            headers=auth_headers(),
            json={
                "accounts": [
                    {
                        "email": "account1@kiro.local",
                        "refresh_token": "token_1",
                        "region": "us-east-1",
                        "provider": "Google"
                    },
                    {
                        "email": "account2@kiro.local",
                        "refresh_token": "token_2",
                        "region": "eu-west-1",
                        "provider": "GitHub"
                    }
                ]
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 2
        assert data["failed"] == 0
        assert mock_account_manager.storage.add_account.call_count == 2
        print(f"Imported {data['imported']} accounts successfully")


class TestBulkImportErrors:
    """Tests for bulk import error handling."""

    def test_import_empty_list_returns_400(
        self, client_with_accounts, auth_headers
    ):
        """
        What it does: Rejects import with empty accounts list.
        Purpose: Prevent no-op requests with clear error message.
        """
        response = client_with_accounts.post(
            "/api/v1/accounts/add/scan",
            headers=auth_headers(),
            json={"accounts": []}
        )

        assert response.status_code == 400
        assert "No accounts provided" in response.json()["detail"]
        print("Empty list correctly rejected with 400")

    def test_import_skips_accounts_without_refresh_token(
        self, client_with_accounts, auth_headers
    ):
        """
        What it does: Skips accounts that don't have a refresh_token.
        Purpose: Handle incomplete scan results gracefully.
        """
        response = client_with_accounts.post(
            "/api/v1/accounts/add/scan",
            headers=auth_headers(),
            json={
                "accounts": [
                    {"email": "no-token@kiro.local", "region": "us-east-1"},
                    {"email": "has-token@kiro.local", "refresh_token": "valid_token", "region": "us-east-1"}
                ]
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 1
        assert data["failed"] == 1
        assert len(data["errors"]) == 1
        assert "missing refresh token" in data["errors"][0]
        print(f"Partial import handled: {data['message']}")

    def test_import_handles_storage_failure(
        self, client_with_accounts, auth_headers, mock_account_manager
    ):
        """
        What it does: Handles storage.add_account raising an exception.
        Purpose: One failed import shouldn't crash the entire batch.
        """
        mock_account_manager.storage.add_account.side_effect = [
            None,  # First succeeds
            Exception("Duplicate email")  # Second fails
        ]

        response = client_with_accounts.post(
            "/api/v1/accounts/add/scan",
            headers=auth_headers(),
            json={
                "accounts": [
                    {"email": "ok@kiro.local", "refresh_token": "token1"},
                    {"email": "fail@kiro.local", "refresh_token": "token2"}
                ]
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 1
        assert data["failed"] == 1
        print(f"Storage failure handled gracefully: {data['message']}")

    def test_import_requires_multi_account_enabled(
        self, client_without_accounts, auth_headers
    ):
        """
        What it does: Returns 503 when multi-account mode is disabled.
        Purpose: Clear error when feature isn't enabled.
        """
        response = client_without_accounts.post(
            "/api/v1/accounts/add/scan",
            headers=auth_headers(),
            json={"accounts": [{"email": "test@local", "refresh_token": "token"}]}
        )

        assert response.status_code == 503
        assert "not enabled" in response.json()["detail"]
        print("Multi-account disabled correctly returns 503")


# =============================================================================
# Test: POST /api/v1/accounts/add/manual
# =============================================================================

class TestManualAddEndpoint:
    """Tests for the manual account addition endpoint."""

    def test_add_manual_success(
        self, client_with_accounts, auth_headers, mock_account_manager
    ):
        """
        What it does: Adds an account with a valid refresh token.
        Purpose: Verify the primary manual import flow works.
        """
        response = client_with_accounts.post(
            "/api/v1/accounts/add/manual",
            headers=auth_headers(),
            json={
                "refresh_token": "eyJ_test_refresh_token",
                "email": "user@example.com",
                "region": "us-east-1"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["account"]["validated"] is True
        mock_account_manager.storage.add_account.assert_called_once()
        print(f"Manual add successful: {data['account']['email']}")

    def test_add_manual_requires_refresh_token(
        self, client_with_accounts, auth_headers
    ):
        """
        What it does: Rejects requests missing the required refresh_token field.
        Purpose: Validate input before attempting to add.
        """
        response = client_with_accounts.post(
            "/api/v1/accounts/add/manual",
            headers=auth_headers(),
            json={"email": "user@example.com"}
        )

        assert response.status_code == 422
        print("Missing refresh_token correctly returns 422")

    def test_add_manual_requires_multi_account(
        self, client_without_accounts, auth_headers
    ):
        """
        What it does: Returns 503 when multi-account is disabled.
        Purpose: Route shouldn't work without the feature enabled.
        """
        response = client_without_accounts.post(
            "/api/v1/accounts/add/manual",
            headers=auth_headers(),
            json={"refresh_token": "test_token"}
        )

        assert response.status_code == 503
        print("Multi-account disabled correctly returns 503")


# =============================================================================
# Test: POST /api/v1/accounts/remove
# =============================================================================

class TestRemoveEndpoint:
    """Tests for the account removal endpoint."""

    def test_remove_account_success(
        self, client_with_accounts, auth_headers, mock_account_manager
    ):
        """
        What it does: Removes an account by email.
        Purpose: Basic happy path for account removal.
        """
        response = client_with_accounts.post(
            "/api/v1/accounts/remove",
            headers=auth_headers(),
            json={"email": "user@example.com"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        mock_account_manager.storage.remove_account.assert_called_once_with("user@example.com")
        print("Account removed successfully")

    def test_remove_nonexistent_account(
        self, client_with_accounts, auth_headers, mock_account_manager
    ):
        """
        What it does: Handles removal of an account that doesn't exist.
        Purpose: Storage should raise an error, endpoint returns 404.
        """
        mock_account_manager.storage.remove_account.side_effect = Exception("Account not found")

        response = client_with_accounts.post(
            "/api/v1/accounts/remove",
            headers=auth_headers(),
            json={"email": "ghost@example.com"}
        )

        assert response.status_code == 404
        print("Non-existent account removal returns 404")

    def test_remove_requires_email(self, client_with_accounts, auth_headers):
        """
        What it does: Rejects removal request without email field.
        Purpose: Validate input before attempting removal.
        """
        response = client_with_accounts.post(
            "/api/v1/accounts/remove",
            headers=auth_headers(),
            json={}
        )

        assert response.status_code == 422
        print("Missing email correctly returns 422")


# =============================================================================
# Test: POST /api/v1/accounts/toggle
# =============================================================================

class TestToggleEndpoint:
    """Tests for the account toggle (enable/disable) endpoint."""

    def test_toggle_account_disable(
        self, client_with_accounts, auth_headers, mock_account_manager
    ):
        """
        What it does: Disables an account.
        Purpose: Users should be able to temporarily disable accounts.
        """
        response = client_with_accounts.post(
            "/api/v1/accounts/toggle",
            headers=auth_headers(),
            json={"email": "user@example.com", "enabled": False}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "disabled" in data["message"]
        mock_account_manager.storage.update_account_enabled.assert_called_once_with(
            "user@example.com", False
        )
        print("Account disabled successfully")

    def test_toggle_account_enable(
        self, client_with_accounts, auth_headers, mock_account_manager
    ):
        """
        What it does: Enables a previously disabled account.
        Purpose: Verify re-enabling works correctly.
        """
        response = client_with_accounts.post(
            "/api/v1/accounts/toggle",
            headers=auth_headers(),
            json={"email": "user@example.com", "enabled": True}
        )

        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data["message"]
        print("Account enabled successfully")

    def test_toggle_requires_email(self, client_with_accounts, auth_headers):
        """
        What it does: Rejects toggle request without email.
        Purpose: Email is required to identify which account to toggle.
        """
        response = client_with_accounts.post(
            "/api/v1/accounts/toggle",
            headers=auth_headers(),
            json={"enabled": False}
        )

        assert response.status_code == 400
        assert "Email is required" in response.json()["detail"]
        print("Missing email correctly returns 400")


# =============================================================================
# Test: Authentication Enforcement
# =============================================================================

class TestAuthenticationEnforcement:
    """Tests that all endpoints require proper authentication."""

    @pytest.mark.parametrize("method,path,body", [
        ("GET", "/api/v1/accounts/scan", None),
        ("POST", "/api/v1/accounts/add/scan", {"accounts": []}),
        ("POST", "/api/v1/accounts/add/manual", {"refresh_token": "x"}),
        ("POST", "/api/v1/accounts/remove", {"email": "x@x.com"}),
        ("POST", "/api/v1/accounts/toggle", {"email": "x@x.com", "enabled": True}),
    ])
    def test_endpoints_reject_invalid_key(
        self, client_with_accounts, auth_headers, method, path, body
    ):
        """
        What it does: Sends requests with invalid API key to all endpoints.
        Purpose: Every account endpoint must enforce authentication.
        """
        kwargs = {"headers": auth_headers(invalid=True)}
        if body:
            kwargs["json"] = body

        if method == "GET":
            response = client_with_accounts.get(path, **kwargs)
        else:
            response = client_with_accounts.post(path, **kwargs)

        assert response.status_code in [401, 403], \
            f"{method} {path} should reject invalid key, got {response.status_code}"
        print(f"{method} {path}: auth enforced ✓")
