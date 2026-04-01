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
SQLite-based metrics storage for Kiro Gateway dashboard.

Stores metrics with hourly aggregation for efficient querying and visualization.
Implements automatic cleanup of old data based on retention policy.
"""

import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger


class MetricsStorage:
    """
    SQLite storage for dashboard metrics.

    Stores time-series metrics data with hourly aggregation.
    Provides efficient queries for dashboard visualization.
    """

    def __init__(self, db_path: str = "metrics.db"):
        """
        Initialize metrics storage.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_schema()
        logger.info(f"MetricsStorage initialized at {db_path}")

    def _init_schema(self):
        """Create database schema if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    metric_type TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    value REAL NOT NULL,
                    metadata TEXT,
                    created_at INTEGER DEFAULT (strftime('%s', 'now'))
                )
            """)

            # Indexes for efficient queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON metrics(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_metric_type ON metrics(metric_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_metric_name ON metrics(metric_name)")

            conn.commit()
            logger.debug("Database schema initialized")

    def persist_metrics(self, counters: Dict[str, int], response_times: Dict[str, List[float]]):
        """
        Persist in-memory metrics to database.

        Args:
            counters: Dictionary of counter metrics
            response_times: Dictionary of response time lists by hour
        """
        timestamp = int(time.time())

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Insert counter metrics
            for key, value in counters.items():
                # Parse metric type and name
                if key.startswith("requests_"):
                    metric_type = "request_count"
                    metric_name = key
                elif key.startswith("model_"):
                    metric_type = "model_usage"
                    metric_name = key
                elif key.startswith("status_"):
                    metric_type = "status_code"
                    metric_name = key
                elif key.startswith("rate_limited"):
                    metric_type = "rate_limit"
                    metric_name = key
                else:
                    metric_type = "counter"
                    metric_name = key

                cursor.execute("""
                    INSERT INTO metrics (timestamp, metric_type, metric_name, value)
                    VALUES (?, ?, ?, ?)
                """, (timestamp, metric_type, metric_name, value))

            # Insert response time metrics (calculate percentiles)
            for hour_key, times in response_times.items():
                if times:
                    times_sorted = sorted(times)
                    count = len(times_sorted)

                    # Calculate percentiles
                    avg = sum(times_sorted) / count
                    p50 = times_sorted[int(count * 0.50)]
                    p95 = times_sorted[int(count * 0.95)]
                    p99 = times_sorted[int(count * 0.99)]

                    # Insert aggregated response time metrics
                    for metric_name, value in [
                        (f"response_time_avg_{hour_key}", avg),
                        (f"response_time_p50_{hour_key}", p50),
                        (f"response_time_p95_{hour_key}", p95),
                        (f"response_time_p99_{hour_key}", p99),
                    ]:
                        cursor.execute("""
                            INSERT INTO metrics (timestamp, metric_type, metric_name, value)
                            VALUES (?, ?, ?, ?)
                        """, (timestamp, "response_time", metric_name, value))

            conn.commit()

    def get_total_requests(self) -> int:
        """
        Get total number of requests.

        Returns:
            Total request count
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT MAX(value) FROM metrics
                WHERE metric_name = 'requests_total'
            """)
            result = cursor.fetchone()
            return int(result[0]) if result and result[0] else 0

    def get_rate_limited_count(self) -> int:
        """
        Get total number of rate-limited requests.

        Returns:
            Rate limited request count
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT MAX(value) FROM metrics
                WHERE metric_name = 'rate_limited'
            """)
            result = cursor.fetchone()
            return int(result[0]) if result and result[0] else 0

    def get_request_volume(self, hours: int = 24) -> List[Dict]:
        """
        Get request volume time-series data.

        Args:
            hours: Number of hours to retrieve

        Returns:
            List of {timestamp, count} dictionaries
        """
        cutoff_time = int(time.time()) - (hours * 3600)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, metric_name, value
                FROM metrics
                WHERE metric_type = 'request_count'
                  AND metric_name LIKE 'requests_____-__-__-__'
                  AND timestamp >= ?
                ORDER BY timestamp ASC
            """, (cutoff_time,))

            # Group by hour
            hourly_data: Dict[str, int] = {}
            for row in cursor.fetchall():
                timestamp, metric_name, value = row
                # Extract hour from metric_name (format: requests_YYYY-MM-DD-HH)
                hour_key = metric_name.replace("requests_", "")
                if hour_key not in hourly_data or value > hourly_data[hour_key]:
                    hourly_data[hour_key] = int(value)

            # Convert to list format
            result = []
            for hour_key, count in sorted(hourly_data.items()):
                # Parse hour_key to timestamp
                dt = datetime.strptime(hour_key, "%Y-%m-%d-%H")
                result.append({
                    "timestamp": int(dt.timestamp()),
                    "hour": hour_key,
                    "count": count
                })

            return result

    def get_model_usage(self) -> Dict[str, int]:
        """
        Get model usage statistics.

        Returns:
            Dictionary mapping model names to request counts
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT metric_name, MAX(value) as count
                FROM metrics
                WHERE metric_type = 'model_usage'
                  AND metric_name LIKE 'model_%'
                  AND metric_name NOT LIKE 'model_%____-__-__-__'
                GROUP BY metric_name
                ORDER BY count DESC
            """)

            result = {}
            for row in cursor.fetchall():
                metric_name, count = row
                # Extract model name (format: model_<model-name>)
                model_name = metric_name.replace("model_", "")
                result[model_name] = int(count)

            return result

    def get_status_code_distribution(self) -> Dict[str, int]:
        """
        Get distribution of HTTP status codes.

        Returns:
            Dictionary mapping status codes to counts
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT metric_name, MAX(value) as count
                FROM metrics
                WHERE metric_type = 'status_code'
                  AND metric_name LIKE 'status_%'
                  AND metric_name NOT LIKE 'status_%____-__-__-__'
                GROUP BY metric_name
                ORDER BY count DESC
            """)

            result = {}
            for row in cursor.fetchall():
                metric_name, count = row
                # Extract status code (format: status_<code>)
                status_code = metric_name.replace("status_", "")
                result[status_code] = int(count)

            return result

    def cleanup_old_metrics(self, retention_days: int = 30):
        """
        Remove metrics older than retention period.

        Args:
            retention_days: Number of days to retain metrics
        """
        cutoff_time = int(time.time()) - (retention_days * 86400)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM metrics WHERE timestamp < ?
            """, (cutoff_time,))

            deleted_count = cursor.rowcount
            conn.commit()

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old metrics (older than {retention_days} days)")

    def get_database_stats(self) -> Dict:
        """
        Get database statistics.

        Returns:
            Dictionary with database stats (size, row count, etc.)
        """
        db_path = Path(self.db_path)
        db_size = db_path.stat().st_size if db_path.exists() else 0

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM metrics")
            row_count = cursor.fetchone()[0]

            cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM metrics")
            min_ts, max_ts = cursor.fetchone()

        return {
            "db_size_bytes": db_size,
            "db_size_mb": round(db_size / (1024 * 1024), 2),
            "total_rows": row_count,
            "oldest_metric": datetime.fromtimestamp(min_ts).isoformat() if min_ts else None,
            "newest_metric": datetime.fromtimestamp(max_ts).isoformat() if max_ts else None,
        }
