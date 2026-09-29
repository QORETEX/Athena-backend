"""Tests for the AccessLogMiddleware (app/middleware/access_log.py)."""
from __future__ import annotations

import logging
import re

import pytest
from fastapi import WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from main import app

# ── Module-level test routes (registered once, persist for the test session) ──

@app.get("/api/_test_access_log_ok")
async def _test_ok():
    return {"status": "ok"}


@app.get("/api/_test_access_log_500")
async def _test_500():
    raise RuntimeError("deliberate 500 for access-log test")


@app.websocket("/ws/_test_access_log")
async def _test_ws(ws: WebSocket):
    await ws.accept()
    ws.state.user_id = 99
    try:
        await ws.receive_text()
    except WebSocketDisconnect:
        pass


# ── Helpers ────────────────────────────────────────────────────────────────────

def _access_records(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "access"]


def _strip_ansi(s: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", s)


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_200_logs_method_path_status_size_duration(client: TestClient, caplog):
    with caplog.at_level(logging.INFO, logger="access"):
        resp = client.get("/api/_test_access_log_ok")

    assert resp.status_code == 200
    records = _access_records(caplog)
    assert records, "Expected at least one access log record"
    msg = _strip_ansi(records[-1].getMessage())
    assert "GET" in msg
    assert "/api/_test_access_log_ok" in msg
    assert "200" in msg
    # Size: ends with B or KB
    assert re.search(r"\d+(\.\d+)?(B|KB)", msg), f"No size token in: {msg}"
    # Duration: ends with ms
    assert re.search(r"\d+\.\d+ms", msg), f"No duration token in: {msg}"


def test_authenticated_request_logs_user_id(authenticated_client: TestClient, caplog):
    # /api/notes is protected by get_current_user which sets request.state.user_id
    with caplog.at_level(logging.INFO, logger="access"):
        resp = authenticated_client.get("/api/notes")

    assert resp.status_code == 200
    records = _access_records(caplog)
    assert records
    msg = _strip_ansi(records[-1].getMessage())
    # user= must be a numeric id, not "-"
    m = re.search(r"user=(\S+)", msg)
    assert m and m.group(1) != "-", f"Expected numeric user id in: {msg}"


def test_unauthenticated_401_logs_user_dash_at_warning(client: TestClient, caplog):
    with caplog.at_level(logging.INFO, logger="access"):
        resp = client.get("/api/notes")  # protected; no token

    assert resp.status_code == 401
    records = _access_records(caplog)
    assert records
    record = records[-1]
    msg = _strip_ansi(record.getMessage())
    assert "401" in msg
    assert "user=-" in msg
    assert record.levelno == logging.WARNING


def test_5xx_logs_at_error_and_reraises(caplog):
    # RuntimeError propagates through ExceptionMiddleware → our middleware
    # catches it, logs 500 ERROR, re-raises → ServerErrorMiddleware returns 500.
    tc = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.INFO, logger="access"):
        resp = tc.get("/api/_test_access_log_500")

    assert resp.status_code == 500
    records = _access_records(caplog)
    assert records
    record = records[-1]
    msg = _strip_ansi(record.getMessage())
    assert "500" in msg
    assert record.levelno == logging.ERROR


def test_query_redaction(client: TestClient, caplog):
    with caplog.at_level(logging.INFO, logger="access"):
        client.get("/api/_test_access_log_ok?token=abc123&q=hello")

    records = _access_records(caplog)
    assert records
    msg = records[-1].getMessage()
    assert "abc123" not in msg, "Token value must not appear in log"
    assert "token=%2A%2A%2A" in msg or "token=***" in msg, f"Redacted token not found: {msg}"
    assert "q=hello" in msg or "q=" in msg  # non-sensitive key is kept


def test_request_id_incoming_valid_is_echoed(client: TestClient, caplog):
    with caplog.at_level(logging.INFO, logger="access"):
        resp = client.get(
            "/api/_test_access_log_ok",
            headers={"X-Request-ID": "test-rid-1234"},
        )

    assert resp.headers.get("x-request-id") == "test-rid-1234"
    records = _access_records(caplog)
    assert records
    assert "test-rid-1234" in records[-1].getMessage()


def test_request_id_invalid_is_replaced(client: TestClient, caplog):
    with caplog.at_level(logging.INFO, logger="access"):
        resp = client.get(
            "/api/_test_access_log_ok",
            headers={"X-Request-ID": "has spaces! invalid"},
        )

    rid_in_response = resp.headers.get("x-request-id", "")
    assert rid_in_response != "has spaces! invalid"
    # Generated rid is 8 hex chars
    assert re.match(r"^[0-9a-f]{8}$", rid_in_response), f"Unexpected rid: {rid_in_response}"
    records = _access_records(caplog)
    assert records
    assert rid_in_response in records[-1].getMessage()


def test_health_excluded_by_default(client: TestClient, caplog):
    with caplog.at_level(logging.INFO, logger="access"):
        resp = client.get("/health")

    assert resp.status_code == 200
    # No access log entry should be emitted for /health
    records = _access_records(caplog)
    health_records = [r for r in records if "/health" in r.getMessage()]
    assert not health_records, f"Health endpoint must be excluded; got: {[r.getMessage() for r in health_records]}"


def test_ws_connect_and_close_logged_with_close_code(client: TestClient, caplog):
    with caplog.at_level(logging.INFO, logger="access"):
        with client.websocket_connect("/ws/_test_access_log"):
            pass  # connect, then immediately disconnect (close code 1000)

    records = _access_records(caplog)
    msgs = [r.getMessage() for r in records]

    connect_msgs = [m for m in msgs if "WS CONNECT" in m]
    close_msgs = [m for m in msgs if "WS CLOSE" in m]

    assert connect_msgs, f"Expected WS CONNECT log; got: {msgs}"
    assert close_msgs, f"Expected WS CLOSE log; got: {msgs}"

    close_msg = close_msgs[-1]
    # Close code must be present
    assert re.search(r"code=\d+", close_msg), f"No close code in: {close_msg}"
    # User id set by the test handler
    assert "user=99" in close_msg, f"Expected user=99 in: {close_msg}"
