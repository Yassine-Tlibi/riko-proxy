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
OAuth Manager for Kiro Gateway.

Handles OAuth flows for adding accounts via AWS SSO OIDC.
Provides a web-based flow similar to antigravity-claude-proxy.
"""

import asyncio
import secrets
import time
from typing import Dict, Optional, Any
from dataclasses import dataclass
from loguru import logger

from kiro.auth import KiroAuthManager, AuthType


@dataclass
class OAuthSession:
    """Represents an active OAuth session."""
    session_id: str
    state: str
    created_at: float
    auth_manager: Optional[KiroAuthManager] = None
    email: Optional[str] = None

    def is_expired(self, timeout_seconds: int = 300) -> bool:
        """Check if session has expired (default 5 minutes)."""
        return (time.time() - self.created_at) > timeout_seconds


class OAuthManager:
    """
    Manages OAuth flows for adding Kiro accounts.

    Supports:
    - Manual token entry (paste refresh token)
    - AWS SSO OIDC flow
    - Import from kiro-cli database
    """

    def __init__(self):
        self.sessions: Dict[str, OAuthSession] = {}
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the OAuth manager and cleanup task."""
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_sessions())
        logger.info("OAuth manager started")

    async def stop(self):
        """Stop the OAuth manager and cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("OAuth manager stopped")

    async def _cleanup_expired_sessions(self):
        """Periodically clean up expired OAuth sessions."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute

                expired_sessions = [
                    session_id
                    for session_id, session in self.sessions.items()
                    if session.is_expired()
                ]

                for session_id in expired_sessions:
                    del self.sessions[session_id]
                    logger.debug(f"Cleaned up expired OAuth session: {session_id}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in OAuth session cleanup: {e}")

    def create_session(self) -> OAuthSession:
        """
        Create a new OAuth session.

        Returns:
            OAuthSession with unique session_id and state
        """
        session_id = secrets.token_urlsafe(32)
        state = secrets.token_urlsafe(32)

        session = OAuthSession(
            session_id=session_id,
            state=state,
            created_at=time.time()
        )

        self.sessions[session_id] = session
        logger.info(f"Created OAuth session: {session_id}")

        return session

    def get_session(self, session_id: str) -> Optional[OAuthSession]:
        """Get an OAuth session by ID."""
        session = self.sessions.get(session_id)

        if session and session.is_expired():
            del self.sessions[session_id]
            return None

        return session

    def delete_session(self, session_id: str):
        """Delete an OAuth session."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Deleted OAuth session: {session_id}")

    async def add_account_manual(
        self,
        refresh_token: str,
        profile_arn: Optional[str] = None,
        region: str = "us-east-1",
        email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Add an account manually using a refresh token.

        Args:
            refresh_token: Kiro refresh token
            profile_arn: Optional AWS profile ARN
            region: AWS region (default: us-east-1)
            email: Optional email identifier

        Returns:
            Dict with account information

        Raises:
            Exception: If token validation fails
        """
        # Create auth manager to validate token
        auth_manager = KiroAuthManager(
            refresh_token=refresh_token,
            profile_arn=profile_arn,
            region=region
        )

        # Validate token by attempting to get access token
        try:
            access_token = await auth_manager.get_access_token()

            # Determine email if not provided
            if not email:
                # Try to extract from token or use a placeholder
                email = f"kiro-account-{secrets.token_hex(4)}@local"

            logger.info(f"Successfully validated account: {email}")

            return {
                "email": email,
                "refresh_token": refresh_token,
                "profile_arn": profile_arn,
                "region": region,
                "auth_type": auth_manager.auth_type.value,
                "validated": True
            }

        except Exception as e:
            logger.error(f"Failed to validate account: {e}")
            raise Exception(f"Invalid refresh token: {str(e)}")

    async def add_account_from_cli_db(
        self,
        db_path: str
    ) -> Dict[str, Any]:
        """
        Add an account by importing from kiro-cli database.

        Args:
            db_path: Path to kiro-cli SQLite database

        Returns:
            Dict with account information

        Raises:
            Exception: If import fails
        """
        # Create auth manager with SQLite DB
        auth_manager = KiroAuthManager(
            sqlite_db=db_path
        )

        # Validate by attempting to get access token
        try:
            access_token = await auth_manager.get_access_token()

            # Extract email or identifier from database
            email = f"kiro-cli-{secrets.token_hex(4)}@local"

            logger.info(f"Successfully imported account from kiro-cli: {email}")

            return {
                "email": email,
                "sqlite_db": db_path,
                "auth_type": AuthType.AWS_SSO_OIDC.value,
                "validated": True
            }

        except Exception as e:
            logger.error(f"Failed to import from kiro-cli: {e}")
            raise Exception(f"Failed to import from kiro-cli database: {str(e)}")

    async def scan_kiro_ide_accounts(self) -> list[Dict[str, Any]]:
        """
        Scan ~/.aws/sso/cache/ for Kiro IDE credential files.

        Returns:
            List of found accounts with their information

        Each account dict contains:
        - file_path: Path to the credential file
        - email: Email from authMethod/provider or placeholder
        - refresh_token: Refresh token
        - profile_arn: Profile ARN (if available)
        - region: AWS region
        - expires_at: Token expiration time
        - auth_method: Authentication method (social, etc.)
        - provider: OAuth provider (Google, GitHub, etc.)
        - is_expired: Whether the token is expired
        """
        import json
        from pathlib import Path
        from datetime import datetime, timezone

        found_accounts = []
        cache_dir = Path.home() / ".aws" / "sso" / "cache"

        if not cache_dir.exists():
            logger.warning(f"AWS SSO cache directory not found: {cache_dir}")
            return found_accounts

        logger.info(f"Scanning for Kiro IDE accounts in: {cache_dir}")

        # Scan all JSON files in cache directory
        for json_file in cache_dir.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Check if this is a Kiro credential file
                # Kiro files have: refreshToken, accessToken, profileArn
                if 'refreshToken' not in data:
                    continue

                # Extract account information
                refresh_token = data.get('refreshToken')
                profile_arn = data.get('profileArn')
                region = data.get('region', 'us-east-1')
                expires_at_str = data.get('expiresAt')
                auth_method = data.get('authMethod', 'unknown')
                provider = data.get('provider', 'unknown')

                # Parse expiration time
                is_expired = False
                expires_at = None
                if expires_at_str:
                    try:
                        if expires_at_str.endswith('Z'):
                            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                        else:
                            expires_at = datetime.fromisoformat(expires_at_str)

                        # Check if expired
                        is_expired = datetime.now(timezone.utc) >= expires_at
                    except Exception as e:
                        logger.warning(f"Failed to parse expiresAt in {json_file.name}: {e}")

                # Generate email identifier
                if provider and provider != 'unknown':
                    email = f"{provider.lower()}-account@kiro.local"
                elif auth_method and auth_method != 'unknown':
                    email = f"{auth_method.lower()}-account@kiro.local"
                else:
                    email = f"kiro-{json_file.stem}@local"

                account_info = {
                    "file_path": str(json_file),
                    "file_name": json_file.name,
                    "email": email,
                    "refresh_token": refresh_token,
                    "profile_arn": profile_arn,
                    "region": region,
                    "expires_at": expires_at.isoformat() if expires_at else None,
                    "auth_method": auth_method,
                    "provider": provider,
                    "is_expired": is_expired
                }

                found_accounts.append(account_info)
                logger.debug(f"Found Kiro account in {json_file.name}: {email} (expired: {is_expired})")

            except json.JSONDecodeError as e:
                logger.debug(f"Skipping non-JSON file {json_file.name}: {e}")
            except Exception as e:
                logger.warning(f"Error reading {json_file.name}: {e}")

        logger.info(f"Found {len(found_accounts)} Kiro IDE account(s)")
        return found_accounts
