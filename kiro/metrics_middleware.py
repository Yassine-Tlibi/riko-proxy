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
Metrics collection middleware for Kiro Gateway dashboard.

This middleware tracks request/response metrics with minimal overhead (<5ms target).
Uses a shared MetricsCollector for coordination with dashboard routes.
"""

import time
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from loguru import logger


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Lightweight metrics collection middleware.

    Tracks:
    - Total requests per hour
    - Requests by endpoint and method
    - Response times (for percentile calculations)
    - Status codes
    - Active (in-flight) requests
    - Model usage (extracted from request body)

    Performance target: <5ms overhead per request.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process request and collect metrics.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain

        Returns:
            HTTP response
        """
        # Skip metrics for dashboard endpoints to avoid recursion
        if request.url.path.startswith("/api/") or request.url.path.startswith("/static/"):
            return await call_next(request)

        # Get metrics collector from app state
        collector = request.app.state.metrics_collector
        if not collector:
            return await call_next(request)

        # Track active requests
        collector.increment_active_requests()

        # Start timing
        start_time = time.time()

        # Extract request metadata
        method = request.method
        path = request.url.path

        # Extract model from request body (for API endpoints)
        model_name: Optional[str] = None
        if path in ("/v1/chat/completions", "/v1/messages"):
            try:
                body = await request.body()
                # Re-create request with body for downstream handlers
                request = Request(request.scope, receive=self._make_receive(body))

                # Parse model from body
                import json
                body_json = json.loads(body.decode("utf-8"))
                model_name = body_json.get("model")
            except Exception as e:
                logger.debug(f"Failed to extract model from request: {e}")

        # Record request
        collector.record_request(method, path, model_name)

        # Process request
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            logger.error(f"Request failed: {e}")
            status_code = 500
            raise
        finally:
            # Track response time
            duration_ms = (time.time() - start_time) * 1000

            # Record response
            collector.record_response(status_code, duration_ms)

            # Decrement active requests
            collector.decrement_active_requests()

        # Periodic persistence (non-blocking)
        await collector.persist_if_needed()

        return response

    def _make_receive(self, body: bytes):
        """
        Create a receive callable that returns the request body.

        This is needed because we consume the request body to extract the model,
        but downstream handlers also need to read it.

        Args:
            body: Request body bytes

        Returns:
            Async callable that returns body
        """
        async def receive():
            return {"type": "http.request", "body": body}
        return receive
