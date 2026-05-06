"""Azure query engine for executing KQL queries."""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from azure.core.credentials import TokenCredential
from azure.core.exceptions import HttpResponseError, ServiceRequestError
from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient, LogsQueryStatus
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

try:
    from azure.monitor.query import MetricsQueryClient  # azure-monitor-query < 2.0
except ImportError:
    MetricsQueryClient = None  # type: ignore[assignment,misc]

from azure_slo_guardian.config import QueryType, SLIConfig

logger = logging.getLogger(__name__)

# Transient Azure exceptions that should trigger a retry
_RETRYABLE_EXCEPTIONS = (HttpResponseError, ServiceRequestError, ConnectionError, TimeoutError)

# Default server-side timeout for KQL queries (seconds)
DEFAULT_QUERY_TIMEOUT_SECONDS = 120


class QueryResult:
    """Result from a query execution."""

    def __init__(
        self,
        value: Optional[float] = None,
        rows: Optional[List[Dict[str, Any]]] = None,
        error: Optional[str] = None,
    ):
        self.value = value
        self.rows = rows or []
        self.error = error
        self.success = error is None

    def get_scalar_value(self) -> Optional[float]:
        """Extract scalar value from query result."""
        if self.value is not None:
            return self.value

        # Try to extract from first row, first column
        if self.rows and len(self.rows) > 0:
            first_row = self.rows[0]
            if isinstance(first_row, dict):
                # Get first value
                values = list(first_row.values())
                if values:
                    try:
                        return float(values[0])
                    except (ValueError, TypeError):
                        return None
        return None


class AzureQueryEngine:
    """Engine for executing KQL queries against Azure."""

    def __init__(
        self,
        credential: Optional[TokenCredential] = None,
        query_timeout: int = DEFAULT_QUERY_TIMEOUT_SECONDS,
    ):
        """Initialize query engine.

        Args:
            credential: Azure credential. If None, uses DefaultAzureCredential.
            query_timeout: Server-side timeout for KQL queries in seconds.
        """
        self.credential = credential or DefaultAzureCredential()
        self.query_timeout = query_timeout
        self._logs_client: Optional[LogsQueryClient] = None
        self._metrics_client: Optional[MetricsQueryClient] = None

    @property
    def logs_client(self) -> LogsQueryClient:
        """Get or create logs query client."""
        if self._logs_client is None:
            self._logs_client = LogsQueryClient(self.credential)
        return self._logs_client

    @property
    def metrics_client(self):
        """Get or create metrics query client."""
        if MetricsQueryClient is None:
            raise ImportError(
                "MetricsQueryClient is not available. "
                "Install azure-monitor-query<2.0.0 or upgrade to a version that includes it."
            )
        if self._metrics_client is None:
            self._metrics_client = MetricsQueryClient(self.credential)
        return self._metrics_client

    def execute_query(
        self,
        sli_config: SLIConfig,
        query: str,
        start_time: datetime,
        end_time: datetime,
    ) -> QueryResult:
        """Execute a KQL query.

        Args:
            sli_config: SLI configuration
            query: KQL query string
            start_time: Query start time
            end_time: Query end time

        Returns:
            QueryResult with the query results
        """
        query_start = time.monotonic()
        try:
            if sli_config.query_type in (
                QueryType.APPLICATION_INSIGHTS,
                QueryType.LOG_ANALYTICS,
            ):
                logger.debug(
                    "Executing logs query against workspace=%s, window=%s to %s",
                    sli_config.workspace_id,
                    start_time.isoformat(),
                    end_time.isoformat(),
                )
                result = self._execute_logs_query(
                    sli_config.workspace_id, query, start_time, end_time
                )
            elif sli_config.query_type == QueryType.AZURE_MONITOR:
                resource_id = sli_config.connection_id or sli_config.workspace_id
                logger.debug(
                    "Executing metrics query against resource=%s", resource_id
                )
                result = self._execute_metrics_query(
                    resource_id, query, start_time, end_time,
                )
            else:
                return QueryResult(error=f"Unsupported query type: {sli_config.query_type}")

            elapsed_ms = (time.monotonic() - query_start) * 1000
            if result.success:
                logger.info(
                    "Query completed in %.0fms, rows=%d, scalar=%s",
                    elapsed_ms,
                    len(result.rows),
                    result.value,
                )
            else:
                logger.warning(
                    "Query returned error after %.0fms: %s", elapsed_ms, result.error
                )
            return result

        except Exception as e:
            elapsed_ms = (time.monotonic() - query_start) * 1000
            logger.error("Query execution failed after %.0fms: %s", elapsed_ms, e)
            return QueryResult(error=str(e))

    def _execute_logs_query(
        self,
        workspace_id: str,
        query: str,
        start_time: datetime,
        end_time: datetime,
    ) -> QueryResult:
        """Execute KQL query against Log Analytics or Application Insights.

        Retries up to 3 times with exponential backoff on transient failures.
        """
        # Extract workspace ID from resource ID if needed
        if "/" in workspace_id:
            workspace_id = workspace_id.split("/")[-1]

        @retry(
            retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=15),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def _do_query() -> QueryResult:
            response = self.logs_client.query_workspace(
                workspace_id=workspace_id,
                query=query,
                timespan=(start_time, end_time),
                server_timeout=self.query_timeout,
            )

            if response.status == LogsQueryStatus.SUCCESS:
                rows = []
                for table in response.tables:
                    for row in table.rows:
                        row_dict = dict(zip([col.name for col in table.columns], row))
                        rows.append(row_dict)

                value = None
                if rows and len(rows) == 1:
                    first_row = rows[0]
                    if len(first_row) == 1:
                        try:
                            value = float(list(first_row.values())[0])
                        except (ValueError, TypeError):
                            pass

                return QueryResult(value=value, rows=rows)
            else:
                return QueryResult(error="Query returned partial results or failed")

        try:
            return _do_query()
        except Exception as e:
            logger.error("Logs query failed after retries: %s", e)
            return QueryResult(error=str(e))

    def _execute_metrics_query(
        self,
        resource_id: str,
        query: str,
        start_time: datetime,
        end_time: datetime,
    ) -> QueryResult:
        """Execute metrics query against Azure Monitor.

        The query string is interpreted as the metric name.
        Retries up to 3 times with exponential backoff on transient failures.
        """
        try:
            client = self.metrics_client
        except ImportError as e:
            return QueryResult(error=str(e))

        @retry(
            retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=15),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def _do_query() -> QueryResult:
            response = client.query_resource(
                resource_uri=resource_id,
                metric_names=[query.strip()],
                timespan=(start_time, end_time),
            )

            for metric in response.metrics:
                for ts_element in metric.timeseries:
                    for data_point in reversed(ts_element.data):
                        for attr in ("average", "total", "count"):
                            val = getattr(data_point, attr, None)
                            if val is not None:
                                return QueryResult(value=float(val))

            return QueryResult(error="No metric data returned for the specified time range")

        try:
            return _do_query()
        except Exception as e:
            logger.error("Metrics query failed after retries: %s", e)
            return QueryResult(error=str(e))

    def execute_ratio_queries(
        self,
        sli_config: SLIConfig,
        start_time: datetime,
        end_time: datetime,
    ) -> tuple[Optional[float], Optional[float], Optional[str]]:
        """Execute good and total queries for ratio-based SLI.

        Returns:
            Tuple of (good_count, total_count, error_message)
        """
        if not sli_config.good_query or not sli_config.total_query:
            return None, None, "Missing good_query or total_query"

        # Execute good query
        good_result = self.execute_query(
            sli_config, sli_config.good_query, start_time, end_time
        )
        if not good_result.success:
            return None, None, f"Good query failed: {good_result.error}"

        # Execute total query
        total_result = self.execute_query(
            sli_config, sli_config.total_query, start_time, end_time
        )
        if not total_result.success:
            return None, None, f"Total query failed: {total_result.error}"

        good_count = good_result.get_scalar_value()
        total_count = total_result.get_scalar_value()

        if good_count is None or total_count is None:
            return None, None, "Could not extract numeric values from query results"

        return good_count, total_count, None

    def execute_threshold_query(
        self,
        sli_config: SLIConfig,
        start_time: datetime,
        end_time: datetime,
    ) -> tuple[Optional[float], Optional[str]]:
        """Execute query for threshold-based SLI.

        Returns:
            Tuple of (measured_value, error_message)
        """
        if not sli_config.query:
            return None, "Missing query"

        result = self.execute_query(sli_config, sli_config.query, start_time, end_time)
        if not result.success:
            return None, f"Query failed: {result.error}"

        value = result.get_scalar_value()
        if value is None:
            return None, "Could not extract numeric value from query result"

        return value, None
