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
Shared metrics collector for dashboard.

This module provides a singleton metrics collector that is shared across
all middleware instances and can be accessed by dashboard routes.
"""

import asyncio
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List

from loguru import logger


class MetricsCollector:
    """
    Shared metrics collector for dashboard.

    This class stores metrics data that is shared across all middleware
    instances and can be accessed by dashboard routes.
    """

    def __init__(self):
        """Initialize metrics collector."""
        # In-memory counters for fast access
        self.counters: Dict[str, int] = defaultdict(int)
        self.response_times: Dict[str, List[float]] = defaultdict(list)
        self.active_requests: int = 0

        # Batch persistence control
        self.last_persist_time: float = time.time()
        self.persist_interval: int = 60  # Persist every 60 seconds
        self.persist_lock: asyncio.Lock = asyncio.Lock()

        # Storage reference (set externally)
        self.storage = None

        logger.debug("MetricsCollector initialized")

    def increment_active_requests(self):
        """Increment active request counter."""
        self.active_requests += 1

    def decrement_active_requests(self):
        """Decrement active request counter."""
        self.active_requests -= 1

    def record_request(self, method: str, path: str, model: str = None):
        """
        Record a request.

        Args:
            method: HTTP method
            path: Request path
            model: Model name (optional)
        """
        hour_key = datetime.now().strftime("%Y-%m-%d-%H")

        self.counters["requests_total"] += 1
        self.counters[f"requests_{hour_key}"] += 1
        self.counters[f"requests_{method}_{path}"] += 1

        if model:
            self.counters[f"model_{model}"] += 1
            self.counters[f"model_{model}_{hour_key}"] += 1

    def record_response(self, status_code: int, duration_ms: float):
        """
        Record a response.

        Args:
            status_code: HTTP status code
            duration_ms: Response duration in milliseconds
        """
        hour_key = datetime.now().strftime("%Y-%m-%d-%H")

        self.response_times[hour_key].append(duration_ms)
        self.counters[f"status_{status_code}"] += 1
        self.counters[f"status_{status_code}_{hour_key}"] += 1

        if status_code == 429:
            self.counters["rate_limited"] += 1
            self.counters[f"rate_limited_{hour_key}"] += 1

    def get_active_requests(self) -> int:
        """Get current number of active requests."""
        return self.active_requests

    def get_counter(self, key: str) -> int:
        """Get value of a specific counter."""
        return self.counters.get(key, 0)

    def get_all_counters(self) -> Dict[str, int]:
        """Get all counters as a dictionary."""
        return dict(self.counters)

    async def persist_if_needed(self):
        """Persist metrics if enough time has passed."""
        current_time = time.time()
        if current_time - self.last_persist_time >= self.persist_interval:
            await self._persist_metrics()

    async def _persist_metrics(self):
        """Persist in-memory metrics to SQLite database."""
        async with self.persist_lock:
            try:
                self.last_persist_time = time.time()

                if not self.storage:
                    logger.warning("Metrics storage not available, skipping persistence")
                    return

                # Prepare metrics snapshot
                metrics_snapshot = dict(self.counters)
                response_times_snapshot = dict(self.response_times)

                # Persist to database (run in thread pool to avoid blocking)
                await asyncio.to_thread(
                    self.storage.persist_metrics,
                    metrics_snapshot,
                    response_times_snapshot
                )

                logger.debug(f"Persisted {len(metrics_snapshot)} metrics to database")

            except Exception as e:
                logger.error(f"Failed to persist metrics: {e}")
