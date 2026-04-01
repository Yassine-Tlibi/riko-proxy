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
Dashboard API routes for Kiro Gateway.

Provides endpoints for dashboard metrics, health, and statistics.
"""

import time
import psutil
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from loguru import logger

from kiro.routes_openai import verify_api_key
from kiro.dashboard_models import (
    DashboardMetrics,
    HealthResponse,
    ModelUsageResponse,
    QuotaResponse,
    RequestVolumePoint,
)

router = APIRouter(prefix="/api", tags=["dashboard"])

# Server start time for uptime calculation
SERVER_START_TIME = time.time()


@router.get("/metrics", response_model=DashboardMetrics)
async def get_metrics(
    request: Request,
    hours: int = Query(24, ge=1, le=168, description="Number of hours to retrieve"),
    _: bool = Depends(verify_api_key)
):
    """
    Get aggregated metrics for dashboard.

    Args:
        request: FastAPI request object
        hours: Number of hours of data to retrieve (1-168)

    Returns:
        DashboardMetrics with current statistics
    """
    storage = request.app.state.metrics_storage
    collector = request.app.state.metrics_collector

    # Get metrics from storage
    total_requests = storage.get_total_requests()
    rate_limited = storage.get_rate_limited_count()
    request_volume_data = storage.get_request_volume(hours)
    model_usage = storage.get_model_usage()
    status_codes = storage.get_status_code_distribution()

    # Get active requests from collector
    active_requests = collector.get_active_requests()

    # Convert request volume to response format
    request_volume = [
        RequestVolumePoint(
            timestamp=point["timestamp"],
            hour=point["hour"],
            count=point["count"]
        )
        for point in request_volume_data
    ]

    return DashboardMetrics(
        total_requests=total_requests,
        active_requests=active_requests,
        rate_limited=rate_limited,
        quota_used_percent=0.0,  # Unknown without Kiro API integration
        request_volume=request_volume,
        model_usage=model_usage,
        status_codes=status_codes,
    )


@router.get("/health", response_model=HealthResponse)
async def get_health(
    request: Request,
    _: bool = Depends(verify_api_key)
):
    """
    Get system health and statistics.

    Args:
        request: FastAPI request object

    Returns:
        HealthResponse with system stats
    """
    storage = request.app.state.metrics_storage
    collector = request.app.state.metrics_collector

    # Calculate uptime
    uptime_seconds = time.time() - SERVER_START_TIME

    # Get memory usage
    process = psutil.Process()
    memory_info = process.memory_info()
    memory_usage_mb = memory_info.rss / (1024 * 1024)

    # Get active connections (approximate)
    active_connections = collector.get_active_requests()

    # Get database stats
    database_stats = storage.get_database_stats()

    # Determine health status
    status = "ok"
    if memory_usage_mb > 1000:  # Over 1GB
        status = "degraded"

    return HealthResponse(
        status=status,
        uptime_seconds=round(uptime_seconds, 2),
        memory_usage_mb=round(memory_usage_mb, 2),
        active_connections=active_connections,
        database_stats=database_stats,
    )


@router.get("/models/usage", response_model=ModelUsageResponse)
async def get_model_usage(
    request: Request,
    _: bool = Depends(verify_api_key)
):
    """
    Get model usage statistics.

    Args:
        request: FastAPI request object

    Returns:
        ModelUsageResponse with model usage breakdown
    """
    storage = request.app.state.metrics_storage

    # Get model usage from storage
    models = storage.get_model_usage()
    total_requests = sum(models.values())

    # Find most used model
    most_used_model = max(models.items(), key=lambda x: x[1])[0] if models else None

    return ModelUsageResponse(
        models=models,
        total_requests=total_requests,
        most_used_model=most_used_model,
    )


@router.get("/quota", response_model=QuotaResponse)
async def get_quota(
    request: Request,
    _: bool = Depends(verify_api_key)
):
    """
    Get quota usage information.

    Args:
        request: FastAPI request object

    Returns:
        QuotaResponse with quota statistics
    """
    storage = request.app.state.metrics_storage

    # Get total requests
    total_requests = storage.get_total_requests()

    return QuotaResponse(
        used_percent=0.0,  # Unknown without Kiro API integration
        total_requests=total_requests,
        estimated_limit=None,  # Unknown without Kiro API integration
        reset_time=None,  # Unknown without Kiro API integration
    )


@router.get("/v1/accounts/status")
async def get_account_status(
    request: Request,
    _: bool = Depends(verify_api_key)
) -> Dict[str, Any]:
    """
    Get multi-account status and health information.

    Args:
        request: FastAPI request object

    Returns:
        Dict with account status including:
        - total: Total number of accounts
        - enabled: Number of enabled accounts
        - invalid: Number of invalid accounts
        - available: Number of currently available accounts
        - strategy: Current selection strategy
        - accounts: List of account details with health scores and rate limits

    Raises:
        HTTPException: 404 if multi-account mode is not enabled
    """
    # Check if multi-account mode is enabled
    account_manager = getattr(request.app.state, 'account_manager', None)

    if not account_manager:
        logger.debug("Multi-account status requested but multi-account mode is disabled")
        raise HTTPException(
            status_code=404,
            detail="Multi-account mode is not enabled. Set MULTI_ACCOUNT_ENABLED=true in your configuration."
        )

    try:
        # Get account status from AccountManager
        status = await account_manager.get_account_status()
        logger.debug(f"Account status retrieved: {status['available']}/{status['total']} accounts available")
        return status
    except Exception as e:
        logger.error(f"Failed to get account status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve account status: {str(e)}"
        )

