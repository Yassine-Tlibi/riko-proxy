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
Logs API routes for Kiro Gateway.

Provides endpoints for retrieving system logs.
"""

import os
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from loguru import logger

from kiro.routes_openai import verify_api_key

router = APIRouter(prefix="/api", tags=["logs"])


class LogEntry(BaseModel):
    """Single log entry."""
    timestamp: str
    level: str
    message: str


@router.get("/logs", response_model=List[LogEntry])
async def get_logs(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of logs to retrieve"),
    level: Optional[str] = Query(None, description="Filter by log level"),
    _: bool = Depends(verify_api_key)
):
    """
    Get recent system logs.

    Args:
        limit: Maximum number of logs to retrieve (1-1000)
        level: Optional log level filter (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        List of log entries
    """
    # For now, return mock logs
    # In production, you would read from actual log files or a logging backend

    mock_logs = [
        LogEntry(
            timestamp=datetime.now().isoformat(),
            level="INFO",
            message="Kiro Gateway started successfully"
        ),
        LogEntry(
            timestamp=datetime.now().isoformat(),
            level="INFO",
            message="Authentication manager initialized"
        ),
        LogEntry(
            timestamp=datetime.now().isoformat(),
            level="DEBUG",
            message="Model resolver cache initialized"
        ),
        LogEntry(
            timestamp=datetime.now().isoformat(),
            level="INFO",
            message="HTTP client configured with retry logic"
        ),
        LogEntry(
            timestamp=datetime.now().isoformat(),
            level="WARNING",
            message="Token refresh threshold reached, refreshing..."
        ),
        LogEntry(
            timestamp=datetime.now().isoformat(),
            level="INFO",
            message="Token refreshed successfully"
        ),
        LogEntry(
            timestamp=datetime.now().isoformat(),
            level="DEBUG",
            message="Request received: POST /v1/chat/completions"
        ),
        LogEntry(
            timestamp=datetime.now().isoformat(),
            level="INFO",
            message="Request completed successfully (200 OK)"
        ),
    ]

    # Filter by level if specified
    if level:
        mock_logs = [log for log in mock_logs if log.level == level.upper()]

    # Apply limit
    return mock_logs[:limit]
