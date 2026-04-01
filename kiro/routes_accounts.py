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
Account management API routes for Kiro Gateway.

Provides endpoints for adding, removing, and managing multiple Kiro accounts.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import secrets

from fastapi import APIRouter, Depends, Request, HTTPException
from loguru import logger

from kiro.routes_openai import verify_api_key

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])


class AddAccountManualRequest(BaseModel):
    """Request to add an account manually with refresh token."""
    refresh_token: str = Field(..., description="Kiro refresh token")
    profile_arn: Optional[str] = Field(None, description="AWS profile ARN (optional)")
    region: str = Field("us-east-1", description="AWS region")
    email: Optional[str] = Field(None, description="Email identifier (optional)")


class AddAccountCliRequest(BaseModel):
    """Request to add an account from kiro-cli database."""
    db_path: str = Field(..., description="Path to kiro-cli SQLite database")


class RemoveAccountRequest(BaseModel):
    """Request to remove an account."""
    email: str = Field(..., description="Email of account to remove")


@router.post("/add/oauth")
async def add_account_oauth(
    request: Request,
    _: bool = Depends(verify_api_key)
) -> Dict[str, Any]:
    """
    Add an account via Kiro Portal OAuth (Google/GitHub).

    Opens https://app.kiro.dev/signin in the browser and captures the callback.

    Args:
        request: FastAPI request object

    Returns:
        Dict with success status and account info

    Raises:
        HTTPException: 400 if OAuth fails, 503 if multi-account disabled
    """
    # Check if multi-account mode is enabled
    account_manager = getattr(request.app.state, 'account_manager', None)

    if not account_manager:
        raise HTTPException(
            status_code=503,
            detail="Multi-account mode is not enabled. Set MULTI_ACCOUNT_ENABLED=true in your configuration."
        )

    try:
        # Start OAuth flow
        from kiro.portal_oauth import start_oauth_flow

        logger.info("Starting Kiro Portal OAuth flow")
        tokens = await start_oauth_flow()

        if not tokens or not tokens.get('refresh_token'):
            raise Exception("OAuth flow failed or was cancelled")

        # Add to account manager
        from kiro.account_storage import Account, AccountTokens

        account = Account(
            email=f"{tokens.get('provider', 'kiro')}-{secrets.token_hex(4)}@oauth",
            tokens=AccountTokens(
                access=tokens.get('access_token', ''),
                refresh=tokens.get('refresh_token', ''),
                expires_at=int(tokens.get('expires_at', 0)) if tokens.get('expires_at') else 0
            ),
            enabled=True,
            is_invalid=False,
            model_rate_limits={},
            last_used=None,
            health_score=1.0,
            metadata={
                "auth_type": "social",
                "provider": tokens.get('provider', 'Unknown'),
                "profile_arn": tokens.get('profile_arn'),
                "added_via": "oauth"
            }
        )

        await account_manager.storage.add_account(account)
        logger.info(f"Added account via OAuth: {account.email} (provider: {tokens.get('provider')})")

        return {
            "success": True,
            "message": f"Account added successfully via {tokens.get('provider')} OAuth",
            "account": {
                "email": account.email,
                "provider": tokens.get('provider'),
                "auth_type": "social",
                "validated": True
            }
        }

    except Exception as e:
        logger.error(f"Failed to add account via OAuth: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"OAuth authentication failed: {str(e)}"
        )


@router.post("/add/manual")
async def add_account_manual(
    request: Request,
    body: AddAccountManualRequest,
    _: bool = Depends(verify_api_key)
) -> Dict[str, Any]:
    """
    Add an account manually using a refresh token.

    Args:
        request: FastAPI request object
        body: Account details including refresh token

    Returns:
        Dict with success status and account info

    Raises:
        HTTPException: 400 if validation fails, 503 if multi-account disabled
    """
    # Check if multi-account mode is enabled
    account_manager = getattr(request.app.state, 'account_manager', None)

    if not account_manager:
        raise HTTPException(
            status_code=503,
            detail="Multi-account mode is not enabled. Set MULTI_ACCOUNT_ENABLED=true in your configuration."
        )

    # Get OAuth manager
    oauth_manager = getattr(request.app.state, 'oauth_manager', None)
    if not oauth_manager:
        raise HTTPException(
            status_code=503,
            detail="OAuth manager not initialized"
        )

    try:
        # Validate and add account
        account_info = await oauth_manager.add_account_manual(
            refresh_token=body.refresh_token,
            profile_arn=body.profile_arn,
            region=body.region,
            email=body.email
        )

        # Add to account manager
        from kiro.account_storage import Account, AccountTokens

        account = Account(
            email=account_info["email"],
            tokens=AccountTokens(
                access="",  # Will be refreshed on first use
                refresh=body.refresh_token,
                expires_at=0
            ),
            enabled=True,
            is_invalid=False,
            model_rate_limits={},
            last_used=None,
            health_score=1.0,
            metadata={
                "auth_type": account_info["auth_type"],
                "profile_arn": body.profile_arn,
                "region": body.region,
                "added_via": "manual"
            }
        )

        await account_manager.storage.add_account(account)
        logger.info(f"Added account manually: {account_info['email']}")

        return {
            "success": True,
            "message": "Account added successfully",
            "account": {
                "email": account_info["email"],
                "auth_type": account_info["auth_type"],
                "validated": True
            }
        }

    except Exception as e:
        logger.error(f"Failed to add account manually: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to add account: {str(e)}"
        )


@router.post("/add/cli")
async def add_account_cli(
    request: Request,
    body: AddAccountCliRequest,
    _: bool = Depends(verify_api_key)
) -> Dict[str, Any]:
    """
    Add an account by importing from kiro-cli database.

    Args:
        request: FastAPI request object
        body: Database path

    Returns:
        Dict with success status and account info

    Raises:
        HTTPException: 400 if import fails, 503 if multi-account disabled
    """
    # Check if multi-account mode is enabled
    account_manager = getattr(request.app.state, 'account_manager', None)

    if not account_manager:
        raise HTTPException(
            status_code=503,
            detail="Multi-account mode is not enabled. Set MULTI_ACCOUNT_ENABLED=true in your configuration."
        )

    # Get OAuth manager
    oauth_manager = getattr(request.app.state, 'oauth_manager', None)
    if not oauth_manager:
        raise HTTPException(
            status_code=503,
            detail="OAuth manager not initialized"
        )

    try:
        # Import from kiro-cli
        account_info = await oauth_manager.add_account_from_cli_db(body.db_path)

        # Add to account manager
        from kiro.account_storage import Account, AccountTokens

        account = Account(
            email=account_info["email"],
            tokens=AccountTokens(
                access="",  # Will be refreshed on first use
                refresh="",  # Stored in SQLite DB
                expires_at=0
            ),
            enabled=True,
            is_invalid=False,
            model_rate_limits={},
            last_used=None,
            health_score=1.0,
            metadata={
                "auth_type": account_info["auth_type"],
                "sqlite_db": body.db_path,
                "added_via": "cli"
            }
        )

        await account_manager.storage.add_account(account)
        logger.info(f"Added account from kiro-cli: {account_info['email']}")

        return {
            "success": True,
            "message": "Account imported successfully from kiro-cli",
            "account": {
                "email": account_info["email"],
                "auth_type": account_info["auth_type"],
                "validated": True
            }
        }

    except Exception as e:
        logger.error(f"Failed to import account from kiro-cli: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to import account: {str(e)}"
        )


@router.get("/scan")
async def scan_kiro_ide_accounts(
    request: Request,
    _: bool = Depends(verify_api_key)
) -> Dict[str, Any]:
    """
    Scan ~/.aws/sso/cache/ for Kiro IDE credential files.

    Returns:
        Dict with list of found accounts

    Raises:
        HTTPException: 503 if OAuth manager not initialized
    """
    # Get OAuth manager
    oauth_manager = getattr(request.app.state, 'oauth_manager', None)
    if not oauth_manager:
        raise HTTPException(
            status_code=503,
            detail="OAuth manager not initialized"
        )

    try:
        # Scan for accounts
        found_accounts = await oauth_manager.scan_kiro_ide_accounts()

        logger.info(f"Scanned and found {len(found_accounts)} Kiro IDE account(s)")

        return {
            "success": True,
            "accounts": found_accounts,
            "count": len(found_accounts)
        }

    except Exception as e:
        logger.error(f"Failed to scan for Kiro IDE accounts: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to scan for accounts: {str(e)}"
        )


class AddScannedAccountsRequest(BaseModel):
    """Request to bulk-import accounts discovered via auto-scan."""
    accounts: list = Field(..., description="List of scanned account dicts from /scan endpoint")


@router.post("/add/scan")
async def add_scanned_accounts(
    request: Request,
    body: AddScannedAccountsRequest,
    _: bool = Depends(verify_api_key)
) -> Dict[str, Any]:
    """
    Bulk-import accounts discovered by the scan endpoint.

    Accepts the account objects returned from GET /scan and creates
    Account entries in the account manager for each one.

    Args:
        request: FastAPI request object
        body: List of scanned account objects

    Returns:
        Dict with imported count, failed count, and error details

    Raises:
        HTTPException: 400 if no accounts provided, 503 if multi-account disabled
    """
    account_manager = getattr(request.app.state, 'account_manager', None)

    if not account_manager:
        raise HTTPException(
            status_code=503,
            detail="Multi-account mode is not enabled. Set MULTI_ACCOUNT_ENABLED=true in your configuration."
        )

    if not body.accounts:
        raise HTTPException(
            status_code=400,
            detail="No accounts provided for import"
        )

    from kiro.account_storage import Account, AccountTokens

    imported = 0
    failed = 0
    errors = []

    for scanned in body.accounts:
        try:
            refresh_token = scanned.get("refresh_token", "")
            if not refresh_token:
                errors.append(f"Account {scanned.get('email', 'unknown')}: missing refresh token")
                failed += 1
                continue

            account = Account(
                email=scanned.get("email", f"scanned-{secrets.token_hex(4)}@local"),
                tokens=AccountTokens(
                    access="",  # Will be refreshed on first use
                    refresh=refresh_token,
                    expires_at=0
                ),
                enabled=True,
                is_invalid=False,
                model_rate_limits={},
                last_used=None,
                health_score=1.0,
                metadata={
                    "auth_type": "kiro_desktop",
                    "profile_arn": scanned.get("profile_arn"),
                    "region": scanned.get("region", "us-east-1"),
                    "provider": scanned.get("provider", "unknown"),
                    "file_path": scanned.get("file_path"),
                    "added_via": "auto_scan"
                }
            )

            await account_manager.storage.add_account(account)
            imported += 1
            logger.info(f"Imported scanned account: {account.email}")

        except Exception as e:
            email = scanned.get("email", "unknown")
            logger.warning(f"Failed to import scanned account {email}: {e}")
            errors.append(f"Account {email}: {str(e)}")
            failed += 1

    logger.info(f"Bulk scan import complete: {imported} imported, {failed} failed")

    return {
        "success": imported > 0,
        "imported": imported,
        "failed": failed,
        "errors": errors if errors else None,
        "message": f"Imported {imported} account(s)" + (f", {failed} failed" if failed else "")
    }


@router.post("/remove")
async def remove_account(
    request: Request,
    body: RemoveAccountRequest,
    _: bool = Depends(verify_api_key)
) -> Dict[str, Any]:
    """
    Remove an account from the account manager.

    Args:
        request: FastAPI request object
        body: Email of account to remove

    Returns:
        Dict with success status

    Raises:
        HTTPException: 404 if account not found, 503 if multi-account disabled
    """
    # Check if multi-account mode is enabled
    account_manager = getattr(request.app.state, 'account_manager', None)

    if not account_manager:
        raise HTTPException(
            status_code=503,
            detail="Multi-account mode is not enabled. Set MULTI_ACCOUNT_ENABLED=true in your configuration."
        )

    try:
        # Remove account
        await account_manager.storage.remove_account(body.email)
        logger.info(f"Removed account: {body.email}")

        return {
            "success": True,
            "message": f"Account {body.email} removed successfully"
        }

    except Exception as e:
        logger.error(f"Failed to remove account: {e}")
        raise HTTPException(
            status_code=404,
            detail=f"Failed to remove account: {str(e)}"
        )


@router.post("/toggle")
async def toggle_account(
    request: Request,
    body: Dict[str, Any],
    _: bool = Depends(verify_api_key)
) -> Dict[str, Any]:
    """
    Enable or disable an account.

    Args:
        request: FastAPI request object
        body: Dict with email and enabled status

    Returns:
        Dict with success status

    Raises:
        HTTPException: 404 if account not found, 503 if multi-account disabled
    """
    # Check if multi-account mode is enabled
    account_manager = getattr(request.app.state, 'account_manager', None)

    if not account_manager:
        raise HTTPException(
            status_code=503,
            detail="Multi-account mode is not enabled. Set MULTI_ACCOUNT_ENABLED=true in your configuration."
        )

    email = body.get("email")
    enabled = body.get("enabled", True)

    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    try:
        # Toggle account
        await account_manager.storage.update_account_enabled(email, enabled)
        logger.info(f"Toggled account {email}: enabled={enabled}")

        return {
            "success": True,
            "message": f"Account {email} {'enabled' if enabled else 'disabled'} successfully"
        }

    except Exception as e:
        logger.error(f"Failed to toggle account: {e}")
        raise HTTPException(
            status_code=404,
            detail=f"Failed to toggle account: {str(e)}"
        )
