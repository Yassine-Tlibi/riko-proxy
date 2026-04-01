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
Multi-account failover mechanism.

Handles automatic account rotation on rate limits and auth errors.
Integrates with AccountManager for intelligent account selection.
"""

import asyncio
from typing import Callable, Any, Optional
from datetime import datetime

from loguru import logger
import httpx

from kiro.account_manager import AccountManager
from kiro.account_storage import Account
from kiro.config import MAX_ACCOUNT_RETRIES, RETRY_BACKOFF_BASE_MS


class FailoverHandler:
    """
    Handles automatic failover across multiple accounts.

    Features:
    - Automatic retry with different accounts on rate limits
    - Exponential backoff between retries
    - Auth error detection and account invalidation
    - Integration with AccountManager for selection
    - Detailed logging of failover attempts

    Usage:
        handler = FailoverHandler(account_manager)
        result = await handler.execute_with_failover(
            model_id="claude-sonnet-4-5",
            request_func=lambda account: make_api_call(account),
            session_id="optional-session-id"
        )
    """

    def __init__(self, account_manager: AccountManager):
        """
        Initialize failover handler.

        Args:
            account_manager: AccountManager instance
        """
        self.account_manager = account_manager

    async def execute_with_failover(
        self,
        model_id: str,
        request_func: Callable[[Account], Any],
        session_id: Optional[str] = None,
        max_retries: int = MAX_ACCOUNT_RETRIES
    ) -> Any:
        """
        Execute a request with automatic failover.

        Args:
            model_id: Model ID for the request
            request_func: Async function that takes an Account and makes the API call
            session_id: Optional session ID for cache continuity
            max_retries: Maximum number of retry attempts

        Returns:
            Result from request_func

        Raises:
            HTTPException: If all accounts exhausted or other error
        """
        last_error = None
        retry_count = 0

        while retry_count < max_retries:
            # Select account
            selection = await self.account_manager.select_account(
                model_id=model_id,
                session_id=session_id
            )

            # Check if we need to wait
            if selection.wait_ms > 0:
                logger.info(
                    f"[Failover] All accounts rate-limited. "
                    f"Waiting {selection.wait_ms}ms before retry."
                )
                await asyncio.sleep(selection.wait_ms / 1000)
                continue

            # Check if account available
            if not selection.account:
                logger.error(
                    f"[Failover] No available accounts for model {model_id} "
                    f"after {retry_count} retries"
                )
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=503,
                    detail=f"All accounts unavailable for model {model_id}. Please try again later."
                )

            account = selection.account

            try:
                # Execute request with selected account
                logger.debug(
                    f"[Failover] Attempt {retry_count + 1}/{max_retries} "
                    f"with account: {account.email}"
                )

                result = await request_func(account)

                # Success - notify manager
                await self.account_manager.notify_success(account, model_id)

                logger.success(
                    f"[Failover] Request succeeded with account: {account.email}"
                )

                return result

            except httpx.HTTPStatusError as e:
                last_error = e
                error_type = self._classify_error(e)

                logger.warning(
                    f"[Failover] Request failed with account {account.email}: "
                    f"{e.response.status_code} - {error_type}"
                )

                # Extract retry-after if available
                retry_after_ms = self._extract_retry_after(e.response)

                # Notify manager of failure
                await self.account_manager.notify_failure(
                    account=account,
                    model_id=model_id,
                    error_type=error_type,
                    retry_after_ms=retry_after_ms
                )

                # Decide whether to retry
                if error_type in ("rate_limit", "server_error"):
                    retry_count += 1

                    # Exponential backoff
                    if retry_count < max_retries:
                        backoff_ms = RETRY_BACKOFF_BASE_MS * (2 ** (retry_count - 1))
                        logger.info(
                            f"[Failover] Retrying in {backoff_ms}ms "
                            f"(attempt {retry_count + 1}/{max_retries})"
                        )
                        await asyncio.sleep(backoff_ms / 1000)
                    continue

                elif error_type == "auth_error":
                    # Auth error - try next account immediately
                    retry_count += 1
                    continue

                else:
                    # Client error - don't retry
                    logger.error(
                        f"[Failover] Non-retryable error: {e.response.status_code}"
                    )
                    raise

            except Exception as e:
                last_error = e
                logger.error(
                    f"[Failover] Unexpected error with account {account.email}: {e}"
                )

                # Notify manager of failure
                await self.account_manager.notify_failure(
                    account=account,
                    model_id=model_id,
                    error_type="network_error"
                )

                retry_count += 1

                if retry_count < max_retries:
                    backoff_ms = RETRY_BACKOFF_BASE_MS * (2 ** (retry_count - 1))
                    await asyncio.sleep(backoff_ms / 1000)
                    continue
                else:
                    raise

        # All retries exhausted
        logger.error(
            f"[Failover] All {max_retries} retry attempts exhausted for model {model_id}"
        )

        from fastapi import HTTPException
        if last_error:
            if isinstance(last_error, httpx.HTTPStatusError):
                raise HTTPException(
                    status_code=last_error.response.status_code,
                    detail=f"Request failed after {max_retries} attempts: {last_error.response.text}"
                )
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"Request failed after {max_retries} attempts: {str(last_error)}"
                )
        else:
            raise HTTPException(
                status_code=503,
                detail=f"All accounts unavailable after {max_retries} attempts"
            )

    def _classify_error(self, error: httpx.HTTPStatusError) -> str:
        """
        Classify HTTP error for failover decision.

        Args:
            error: HTTP status error

        Returns:
            Error type: rate_limit, auth_error, server_error, client_error
        """
        status_code = error.response.status_code

        if status_code == 429:
            return "rate_limit"
        elif status_code in (401, 403):
            return "auth_error"
        elif status_code >= 500:
            return "server_error"
        else:
            return "client_error"

    def _extract_retry_after(self, response: httpx.Response) -> Optional[int]:
        """
        Extract Retry-After header from response.

        Args:
            response: HTTP response

        Returns:
            Retry-after time in milliseconds, or None
        """
        retry_after = response.headers.get("Retry-After")
        if not retry_after:
            return None

        try:
            # Try parsing as seconds
            seconds = int(retry_after)
            return seconds * 1000
        except ValueError:
            # Try parsing as HTTP date
            try:
                from email.utils import parsedate_to_datetime
                retry_date = parsedate_to_datetime(retry_after)
                now = datetime.now(retry_date.tzinfo)
                delta = retry_date - now
                return max(0, int(delta.total_seconds() * 1000))
            except Exception:
                return None


__all__ = ["FailoverHandler"]
