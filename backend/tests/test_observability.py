"""Observability: request ids, access logging, and the error contract.

WHY THIS EXISTS
---------------
Monitoring is the one part of a system that fails silently by construction: if
the access log stops, nothing logs the fact that nothing is logging. The whole
value of the module under test is that a deployed failure reaches somebody, so
the assertions here are about the things that would quietly stop being true --
that an id is present and echoed, that a failing request is still recorded,
that the safe message and the real one stay on opposite sides of the boundary.
"""
from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app import observability
from backend.app.main import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# --------------------------------------------------------------------------
# Request identity
# --------------------------------------------------------------------------

def test_every_response_carries_a_request_id(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.headers["X-Request-ID"]


def test_ids_are_unique_per_request(client):
    seen = {client.get("/api/health").headers["X-Request-ID"] for _ in range(5)}
    assert len(seen) == 5


def test_a_proxys_request_id_is_adopted_rather_than_replaced(client):
    """A trace has to survive the hop, or it is not a trace."""
    response = client.get("/api/health", headers={"X-Request-ID": "edge-abc123"})
    assert response.headers["X-Request-ID"] == "edge-abc123"


@pytest.mark.parametrize(
    "hostile",
    [
        "a" * 500,                      # unbounded length
        "abc\nINFO forged log line",    # log injection
        "abc\r\nX-Evil: 1",             # header injection
        "id with spaces",
        "../../etc/passwd",
        "<script>alert(1)</script>",
    ],
)
def test_a_hostile_request_id_is_replaced_not_sanitised(client, hostile):
    """This header is attacker-controlled and lands in a log and a header.

    Replaced rather than stripped on purpose: a sanitiser that removes the
    newline from `abc\\nINFO ...` still writes the attacker's text into the
    log, just on one line. Minting a fresh id discards the input entirely.
    """
    returned = client.get("/api/health", headers={"X-Request-ID": hostile}).headers["X-Request-ID"]
    assert returned != hostile
    assert returned.isalnum()
    assert len(returned) == 16


def test_a_wellformed_id_at_the_length_limit_is_still_accepted(client):
    ok = "a" * 64
    assert client.get("/api/health", headers={"X-Request-ID": ok}).headers["X-Request-ID"] == ok
    too_long = "a" * 65
    assert client.get("/api/health", headers={"X-Request-ID": too_long}).headers["X-Request-ID"] != too_long


# --------------------------------------------------------------------------
# The access log
# --------------------------------------------------------------------------

def test_a_successful_request_is_logged_once_with_route_and_duration(client, caplog):
    with caplog.at_level(logging.INFO, logger="f1.access"):
        client.get("/api/health")

    lines = [r for r in caplog.records if r.name == "f1.access"]
    assert len(lines) == 1
    fields = lines[0].fields
    assert fields["method"] == "GET"
    assert fields["route"] == "/api/health"
    assert fields["status"] == 200
    assert fields["duration_ms"] >= 0


def test_the_log_records_the_route_template_not_the_concrete_path(client, caplog):
    """129 driver paths are one endpoint. A percentile over 129 buckets is not
    a percentile."""
    with caplog.at_level(logging.INFO, logger="f1.access"):
        client.get("/api/drivers/1")

    fields = [r for r in caplog.records if r.name == "f1.access"][0].fields
    assert fields["route"] == "/api/drivers/{driver_id}"


def test_the_template_keeps_the_router_prefix(client, caplog):
    """One naming scheme in the `route` field, not two.

    `scope["route"].path` reports `/drivers/{driver_id}` for a router included
    with `prefix="/api"`, while an app-level route reports `/api/health`.
    Grouping a dashboard by a field that names one service two ways splits it
    in half, so the template is rebuilt from the served path instead.
    """
    with caplog.at_level(logging.INFO, logger="f1.access"):
        client.get("/api/drivers/1")
        client.get("/api/health")

    routes = [r.fields["route"] for r in caplog.records if r.name == "f1.access"]
    assert all(route.startswith("/api/") for route in routes), routes


def test_a_parameter_value_is_substituted_per_segment_not_per_substring(client, caplog):
    """A driver id of `1` must not rewrite `2011` into `20{driver_id}1`."""
    with caplog.at_level(logging.INFO, logger="f1.access"):
        client.get("/api/seasons/2011")

    route = [r for r in caplog.records if r.name == "f1.access"][0].fields["route"]
    assert route.count("{") <= 1
    assert "20{" not in route


def test_a_client_error_logs_at_warning_and_keeps_the_concrete_path(client, caplog):
    with caplog.at_level(logging.INFO, logger="f1.access"):
        client.get("/api/drivers/99999999")

    line = [r for r in caplog.records if r.name == "f1.access"][0]
    assert line.levelno == logging.WARNING
    # The specific value is the whole point of a 4xx.
    assert line.fields["path"] == "/api/drivers/99999999"


def test_a_failing_request_is_still_logged(caplog):
    """Emitted from a `finally`. An unhandled exception is the case you most
    want a log line for, and the case a naive implementation drops."""
    tiny = FastAPI()
    tiny.add_middleware(observability.AccessLogMiddleware)

    @tiny.get("/boom")
    def boom():
        raise RuntimeError("deliberate")

    with caplog.at_level(logging.INFO, logger="f1.access"):
        TestClient(tiny, raise_server_exceptions=False).get("/boom")

    line = [r for r in caplog.records if r.name == "f1.access"][0]
    assert line.levelno == logging.ERROR
    assert line.fields["status"] == 500


def test_log_records_carry_the_request_id_of_the_request_that_emitted_them():
    """The filter is what ties an exception line to the access line beside it.

    Under concurrency, "beside it" is not a relationship you can rely on.
    """
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
    token = observability.current_request_id.set("req-under-test")
    try:
        assert observability.RequestIdFilter().filter(record)
        assert record.request_id == "req-under-test"
    finally:
        observability.current_request_id.reset(token)


def test_the_request_id_does_not_leak_between_requests(client):
    """The ContextVar is reset in the same `finally` that logs."""
    client.get("/api/health")
    assert observability.current_request_id.get() == "-"


# --------------------------------------------------------------------------
# JSON formatting
# --------------------------------------------------------------------------

def test_json_lines_are_one_object_per_line_and_carry_the_structured_fields():
    import json

    record = logging.LogRecord("f1.access", logging.INFO, __file__, 1, "GET /x", None, None)
    record.request_id = "abc"
    record.fields = {"status": 200, "duration_ms": 12.3, "route": "/x"}

    line = observability.JsonFormatter().format(record)
    assert "\n" not in line
    parsed = json.loads(line)
    assert parsed["request_id"] == "abc"
    assert parsed["status"] == 200
    assert parsed["duration_ms"] == 12.3


def test_a_newline_in_a_message_cannot_forge_a_second_log_entry():
    """The reason JSON is offered at all: a text log is forgeable by anything
    that reaches a message."""
    import json

    record = logging.LogRecord(
        "f1.access", logging.INFO, __file__, 1,
        "innocent\nERROR everything is fine", None, None,
    )
    line = observability.JsonFormatter().format(record)
    assert "\n" not in line
    assert json.loads(line)["message"] == "innocent\nERROR everything is fine"


# --------------------------------------------------------------------------
# Error reporting configuration
# --------------------------------------------------------------------------

def test_no_dsn_means_reporting_is_off_and_says_so(monkeypatch):
    monkeypatch.delenv("F1_SENTRY_DSN", raising=False)
    assert "disabled" in observability.configure_error_reporting()


def test_a_dsn_without_the_sdk_is_loud_rather_than_silent(monkeypatch):
    """The failure mode that makes people trust an alerting system that is off.

    Reported as MISCONFIGURED rather than as "enabled", because a deployment
    that believes it has error reporting and does not is worse than one that
    knows it has none.
    """
    monkeypatch.setenv("F1_SENTRY_DSN", "https://example@example.ingest.sentry.io/1")

    import builtins

    real_import = builtins.__import__

    def no_sentry(name, *args, **kwargs):
        if name == "sentry_sdk":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_sentry)
    assert observability.configure_error_reporting() == "MISCONFIGURED (DSN set, SDK missing)"


# --------------------------------------------------------------------------
# The error contract
# --------------------------------------------------------------------------

def test_an_unhandled_exception_returns_the_documented_json_body(client, monkeypatch):
    """The gap the three named handlers left open.

    Before the catch-all, this returned Starlette's plain-text `Internal
    Server Error` with no `detail` key -- and `services/api.ts` reads `detail`
    to decide what to show a reader.
    """
    from backend.app import main as main_module

    def explode(*_args, **_kwargs):
        # Deliberately NOT sqlite3.Error or SupabaseError: those have their own
        # handlers, and this test exists to cover everything that does not.
        raise TypeError("deliberate: a row shape that changed")

    monkeypatch.setattr(main_module, "connect", explode)
    monkeypatch.setenv("F1_BACKEND", "sqlite")

    response = client.get("/api/health")

    assert response.status_code == 500
    body = response.json()
    assert set(body) == {"detail", "request_id"}
    # The safe message, and nothing from the real one.
    assert "deliberate" not in body["detail"]
    assert "TypeError" not in body["detail"]
    assert body["request_id"] == response.headers["X-Request-ID"]
