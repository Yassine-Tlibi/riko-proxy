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
Pydantic models for dashboard API responses.

Defines the data structures returned by dashboard API endpoints.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class RequestVolumePoint(BaseModel):
    """Single data point in request volume time series."""
    timestamp: int = Field(..., description="Unix timestamp")
    hour: str = Field(..., description="Hour key (YYYY-MM-DD-HH)")
    count: int = Field(..., description="Number of requests in this hour")


class DashboardMetrics(BaseModel):
    """Main dashboard metrics response."""
    total_requests: int = Field(..., description="Total number of requests processed")
    active_requests: int = Field(..., description="Currently in-flight requests")
    rate_limited: int = Field(..., description="Number of rate-limited requests")
    quota_used_percent: float = Field(..., description="Quota usage percentage (0-100)")
    request_volume: List[RequestVolumePoint] = Field(..., description="Request volume time series")
    model_usage: Dict[str, int] = Field(..., description="Request count by model")
    status_codes: Dict[str, int] = Field(..., description="Request count by status code")


class HealthResponse(BaseModel):
    """System health and stats response."""
    status: str = Field(..., description="Health status (ok, degraded, error)")
    uptime_seconds: float = Field(..., description="Server uptime in seconds")
    memory_usage_mb: float = Field(..., description="Memory usage in MB")
    active_connections: int = Field(..., description="Active HTTP connections")
    database_stats: Dict = Field(..., description="Database statistics")


class ModelUsageResponse(BaseModel):
    """Model usage statistics response."""
    models: Dict[str, int] = Field(..., description="Request count by model")
    total_requests: int = Field(..., description="Total requests across all models")
    most_used_model: Optional[str] = Field(None, description="Most frequently used model")


class QuotaResponse(BaseModel):
    """Quota usage response."""
    used_percent: float = Field(..., description="Quota usage percentage (0-100)")
    total_requests: int = Field(..., description="Total requests counted toward quota")
    estimated_limit: Optional[int] = Field(None, description="Estimated quota limit (if known)")
    reset_time: Optional[int] = Field(None, description="Unix timestamp when quota resets")
