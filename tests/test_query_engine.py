"""Unit tests for Azure query engine (fully mocked — no Azure credentials needed)."""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from azure_slo_guardian.config import QueryType, SLIConfig, SLIType, Operator
from azure_slo_guardian.query_engine import AzureQueryEngine, QueryResult


# ---------------------------------------------------------------------------
# QueryResult
# ---------------------------------------------------------------------------


class TestQueryResult:
    """Test QueryResult helper."""

    def test_success_with_value(self):
        r = QueryResult(value=42.0)
        assert r.success
        assert r.get_scalar_value() == 42.0

    def test_success_with_rows(self):
        r = QueryResult(rows=[{"Count": 100}])
        assert r.success
        assert r.get_scalar_value() == 100.0

    def test_error(self):
        r = QueryResult(error="boom")
        assert not r.success
        assert r.get_scalar_value() is None

    def test_empty_rows_returns_none(self):
        r = QueryResult(rows=[])
        assert r.get_scalar_value() is None

    def test_non_numeric_value_returns_none(self):
        r = QueryResult(rows=[{"name": "hello"}])
        assert r.get_scalar_value() is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _availability_sli() -> SLIConfig:
    return SLIConfig(
        type=SLIType.AVAILABILITY,
        query_type=QueryType.APPLICATION_INSIGHTS,
        workspace_id="test-ws",
        good_query="requests | where success == true | count",
        total_query="requests | count",
    )


def _latency_sli() -> SLIConfig:
    return SLIConfig(
        type=SLIType.LATENCY,
        query_type=QueryType.APPLICATION_INSIGHTS,
        workspace_id="test-ws",
        query="requests | summarize percentile(duration, 95)",
        threshold=500,
        operator=Operator.LTE,
    )


def _metrics_sli() -> SLIConfig:
    return SLIConfig(
        type=SLIType.AVAILABILITY,
        query_type=QueryType.AZURE_MONITOR,
        workspace_id="/subscriptions/xxx/resourceGroups/rg/providers/Microsoft.Web/sites/myapp",
        good_query="SuccessfulRequests",
        total_query="TotalRequests",
    )


def _mock_logs_response(tables):
    """Build a mock Azure LogsQueryResult."""
    resp = MagicMock()
    resp.status = "Success"  # LogsQueryStatus.SUCCESS
    resp.tables = tables
    return resp


def _mock_table(columns, rows):
    table = MagicMock()
    cols = []
    for c in columns:
        col = MagicMock()
        col.name = c
        cols.append(col)
    table.columns = cols
    table.rows = rows
    return table


# ---------------------------------------------------------------------------
# AzureQueryEngine — Logs
# ---------------------------------------------------------------------------


class TestAzureQueryEngineLogs:
    """Test log-based queries via mocked LogsQueryClient."""

    def test_execute_logs_query_success(self):
        engine = AzureQueryEngine(credential=MagicMock())
        mock_client = MagicMock()
        engine._logs_client = mock_client

        table = _mock_table(["Count"], [[42]])
        mock_client.query_workspace.return_value = _mock_logs_response([table])

        sli = _availability_sli()
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        result = engine.execute_query(sli, sli.good_query, start, end)
        assert result.success
        assert result.get_scalar_value() == 42.0

    def test_execute_logs_query_failure(self):
        engine = AzureQueryEngine(credential=MagicMock())
        mock_client = MagicMock()
        engine._logs_client = mock_client

        resp = MagicMock()
        resp.status = "PartialError"
        mock_client.query_workspace.return_value = resp

        sli = _availability_sli()
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        result = engine.execute_query(sli, sli.good_query, start, end)
        assert not result.success

    def test_execute_logs_query_exception(self):
        engine = AzureQueryEngine(credential=MagicMock())
        mock_client = MagicMock()
        engine._logs_client = mock_client
        mock_client.query_workspace.side_effect = Exception("auth error")

        sli = _availability_sli()
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        result = engine.execute_query(sli, sli.good_query, start, end)
        assert not result.success
        assert "auth error" in result.error

    def test_workspace_id_strips_resource_path(self):
        engine = AzureQueryEngine(credential=MagicMock())
        mock_client = MagicMock()
        engine._logs_client = mock_client

        table = _mock_table(["Count"], [[1]])
        mock_client.query_workspace.return_value = _mock_logs_response([table])

        sli = SLIConfig(
            type=SLIType.AVAILABILITY,
            query_type=QueryType.LOG_ANALYTICS,
            workspace_id="/subscriptions/x/resourceGroups/rg/providers/Microsoft.OperationalInsights/workspaces/myws",
            good_query="test",
            total_query="test",
        )
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        engine.execute_query(sli, sli.good_query, start, end)
        call_args = mock_client.query_workspace.call_args
        assert call_args.kwargs["workspace_id"] == "myws"


# ---------------------------------------------------------------------------
# AzureQueryEngine — Ratio queries
# ---------------------------------------------------------------------------


class TestExecuteRatioQueries:
    def test_success(self):
        engine = AzureQueryEngine(credential=MagicMock())
        mock_client = MagicMock()
        engine._logs_client = mock_client

        good_table = _mock_table(["Count"], [[950]])
        total_table = _mock_table(["Count"], [[1000]])

        mock_client.query_workspace.side_effect = [
            _mock_logs_response([good_table]),
            _mock_logs_response([total_table]),
        ]

        sli = _availability_sli()
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        good, total, err = engine.execute_ratio_queries(sli, start, end)
        assert err is None
        assert good == 950.0
        assert total == 1000.0

    def test_missing_queries(self):
        engine = AzureQueryEngine(credential=MagicMock())
        sli = SLIConfig(
            type=SLIType.AVAILABILITY,
            query_type=QueryType.APPLICATION_INSIGHTS,
            workspace_id="ws",
            good_query="test",
            total_query="test",
        )
        sli.good_query = None
        good, total, err = engine.execute_ratio_queries(
            sli,
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 2, tzinfo=timezone.utc),
        )
        assert err is not None
        assert "Missing" in err


# ---------------------------------------------------------------------------
# AzureQueryEngine — Threshold queries
# ---------------------------------------------------------------------------


class TestExecuteThresholdQuery:
    def test_success(self):
        engine = AzureQueryEngine(credential=MagicMock())
        mock_client = MagicMock()
        engine._logs_client = mock_client

        table = _mock_table(["p95"], [[320.5]])
        mock_client.query_workspace.return_value = _mock_logs_response([table])

        sli = _latency_sli()
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        value, err = engine.execute_threshold_query(sli, start, end)
        assert err is None
        assert value == 320.5

    def test_missing_query(self):
        engine = AzureQueryEngine(credential=MagicMock())
        sli = _latency_sli()
        sli.query = None
        value, err = engine.execute_threshold_query(
            sli,
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 2, tzinfo=timezone.utc),
        )
        assert err is not None
        assert "Missing" in err


# ---------------------------------------------------------------------------
# AzureQueryEngine — Metrics
# ---------------------------------------------------------------------------


class TestAzureQueryEngineMetrics:
    def test_execute_metrics_query_success(self):
        engine = AzureQueryEngine(credential=MagicMock())
        mock_client = MagicMock()

        data_point = MagicMock()
        data_point.average = 99.5
        data_point.total = None
        data_point.count = None

        ts_element = MagicMock()
        ts_element.data = [data_point]

        metric = MagicMock()
        metric.timeseries = [ts_element]

        response = MagicMock()
        response.metrics = [metric]

        mock_client.query_resource.return_value = response

        sli = _metrics_sli()
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        with patch.object(type(engine), "metrics_client", new_callable=PropertyMock, return_value=mock_client):
            result = engine._execute_metrics_query(sli.workspace_id, "SuccessfulRequests", start, end)
        assert result.success
        assert result.value == 99.5

    def test_execute_metrics_query_no_data(self):
        engine = AzureQueryEngine(credential=MagicMock())
        mock_client = MagicMock()

        metric = MagicMock()
        metric.timeseries = []

        response = MagicMock()
        response.metrics = [metric]

        mock_client.query_resource.return_value = response

        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        with patch.object(type(engine), "metrics_client", new_callable=PropertyMock, return_value=mock_client):
            result = engine._execute_metrics_query("/sub/rg/resource", "Metric", start, end)
        assert not result.success
        assert "No metric data" in result.error

    def test_execute_metrics_query_exception(self):
        engine = AzureQueryEngine(credential=MagicMock())
        mock_client = MagicMock()
        mock_client.query_resource.side_effect = Exception("forbidden")

        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        with patch.object(type(engine), "metrics_client", new_callable=PropertyMock, return_value=mock_client):
            result = engine._execute_metrics_query("/sub/rg/resource", "Metric", start, end)
        assert not result.success
        assert "forbidden" in result.error

    def test_execute_metrics_query_unavailable(self):
        """When MetricsQueryClient is not installed, return a clear error."""
        engine = AzureQueryEngine(credential=MagicMock())

        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        with patch.object(
            type(engine), "metrics_client", new_callable=PropertyMock,
            side_effect=ImportError("MetricsQueryClient is not available"),
        ):
            result = engine._execute_metrics_query("/sub/rg/resource", "Metric", start, end)
        assert not result.success
        assert "not available" in result.error


class TestQueryTimeout:
    """Test that query timeout is passed to Azure SDK."""

    def test_default_timeout(self):
        from azure_slo_guardian.query_engine import DEFAULT_QUERY_TIMEOUT_SECONDS
        engine = AzureQueryEngine(credential=MagicMock())
        assert engine.query_timeout == DEFAULT_QUERY_TIMEOUT_SECONDS

    def test_custom_timeout(self):
        engine = AzureQueryEngine(credential=MagicMock(), query_timeout=60)
        assert engine.query_timeout == 60

    def test_timeout_passed_to_query(self):
        engine = AzureQueryEngine(credential=MagicMock(), query_timeout=45)
        mock_client = MagicMock()
        engine._logs_client = mock_client

        table = _mock_table(["Count"], [[42]])
        mock_client.query_workspace.return_value = _mock_logs_response([table])

        sli = _availability_sli()
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        engine.execute_query(sli, sli.good_query, start, end)
        call_kwargs = mock_client.query_workspace.call_args.kwargs
        assert call_kwargs["server_timeout"] == 45


class TestQueryRetry:
    """Test that transient Azure failures are retried."""

    def test_retries_on_transient_exception(self):
        from azure.core.exceptions import HttpResponseError
        engine = AzureQueryEngine(credential=MagicMock())
        mock_client = MagicMock()
        engine._logs_client = mock_client

        table = _mock_table(["Count"], [[42]])
        ok_resp = _mock_logs_response([table])

        # First call fails, second succeeds
        mock_client.query_workspace.side_effect = [
            HttpResponseError("transient"),
            ok_resp,
        ]

        sli = _availability_sli()
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        result = engine.execute_query(sli, sli.good_query, start, end)
        assert result.success
        assert mock_client.query_workspace.call_count == 2

    def test_non_retryable_exception_fails_immediately(self):
        engine = AzureQueryEngine(credential=MagicMock())
        mock_client = MagicMock()
        engine._logs_client = mock_client

        # ValueError is not retryable
        mock_client.query_workspace.side_effect = ValueError("bad query")

        sli = _availability_sli()
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        result = engine.execute_query(sli, sli.good_query, start, end)
        assert not result.success
        mock_client.query_workspace.assert_called_once()
