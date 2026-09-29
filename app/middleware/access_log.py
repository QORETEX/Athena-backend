from __future__ import annotations

import logging
import re
import secrets
import time
from urllib.parse import parse_qs, urlencode

from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import get_settings

_log = logging.getLogger("access")

_SENSITIVE_KEYS = frozenset({
    "token", "access_token", "refresh_token", "id_token",
    "password", "code", "key", "api_key", "secret",
})

_RID_RE = re.compile(r"^[A-Za-z0-9\-]{1,64}$")

# ANSI colour codes — dev only, matching Django runserver palette
_RESET = "\033[0m"
_STATUS_COLOURS = {2: "\033[32m", 3: "\033[36m", 4: "\033[33m", 5: "\033[31m"}

# WS close codes that warrant a WARNING instead of INFO
_WARN_WS_CODES = frozenset({1008, 1009, 1011})


def _redact_query(qs: str) -> str:
    if not qs:
        return qs
    params = parse_qs(qs, keep_blank_values=True)
    out: dict[str, list[str]] = {}
    for k, vs in params.items():
        out[k] = ["***"] * len(vs) if k.lower() in _SENSITIVE_KEYS else vs
    return urlencode(out, doseq=True)


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    return f"{n / 1024:.1f}KB"


def _client_ip(scope: Scope) -> str:
    settings = get_settings()
    if settings.trust_proxy:
        for k, v in scope.get("headers", []):
            if k.lower() == b"x-forwarded-for":
                return v.decode("latin-1", errors="replace").split(",")[-1].strip()
    client = scope.get("client")
    return client[0] if client else "127.0.0.1"


def _request_id(scope: Scope) -> str:
    for k, v in scope.get("headers", []):
        if k.lower() == b"x-request-id":
            rid = v.decode("latin-1", errors="replace")
            if _RID_RE.match(rid):
                return rid
    return secrets.token_hex(4)


def _colour(status: int, is_dev: bool) -> str:
    s = str(status)
    if not is_dev:
        return s
    c = _STATUS_COLOURS.get(status // 100, "")
    return f"{c}{s}{_RESET}" if c else s


# Starlette 1.x stores scope["state"] as a plain dict; Request.state is a
# thin attribute-accessor wrapper around that same dict.
def _state(scope: Scope) -> dict:
    return scope.setdefault("state", {})


class AccessLogMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            await self._http(scope, receive, send)
        elif scope["type"] == "websocket":
            await self._ws(scope, receive, send)
        else:
            await self.app(scope, receive, send)

    # ── HTTP ──────────────────────────────────────────────────────────────────

    async def _http(self, scope: Scope, receive: Receive, send: Send) -> None:
        settings = get_settings()
        path = scope.get("path", "/")

        exclude = [p.strip() for p in settings.access_log_exclude.split(",") if p.strip()]
        if not settings.access_log or any(path.startswith(p) for p in exclude):
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        method = scope.get("method", "")
        qs_raw = scope.get("query_string", b"").decode("latin-1", errors="replace")
        qs = _redact_query(qs_raw)
        http_ver = scope.get("http_version", "1.1")
        ip = _client_ip(scope)
        rid = _request_id(scope)
        is_dev = settings.environment != "production"

        # Expose rid so downstream handlers can include it in their own logs.
        _state(scope)["request_id"] = rid

        status: int | None = None
        body_bytes = 0

        async def wrapped_send(message: dict) -> None:
            nonlocal status, body_bytes
            if message["type"] == "http.response.start":
                status = message["status"]
                hdrs = list(message.get("headers", []))
                hdrs.append((b"x-request-id", rid.encode()))
                message = {**message, "headers": hdrs}
            elif message["type"] == "http.response.body":
                body_bytes += len(message.get("body", b""))
            await send(message)

        exc_to_raise: BaseException | None = None
        try:
            await self.app(scope, receive, wrapped_send)
        except Exception as exc:
            exc_to_raise = exc
            if status is None:
                status = 500

        duration_ms = (time.perf_counter() - start) * 1000

        st = status if status is not None else 500
        # user_id is written into scope["state"] by get_current_user after auth
        user_id = scope.get("state", {}).get("user_id")
        user_str = str(user_id) if user_id is not None else "-"

        path_qs = f"{path}?{qs}" if qs else path
        size_str = _fmt_size(body_bytes) if status is not None else "-"

        msg = (
            f'"{method} {path_qs} HTTP/{http_ver}" '
            f'{_colour(st, is_dev)} {size_str} {duration_ms:.1f}ms '
            f'user={user_str} ip={ip} rid={rid}'
        )

        if st >= 500:
            _log.error(msg)
        elif st >= 400:
            _log.warning(msg)
        else:
            _log.info(msg)

        if exc_to_raise is not None:
            raise exc_to_raise

    # ── WebSocket ─────────────────────────────────────────────────────────────

    async def _ws(self, scope: Scope, receive: Receive, send: Send) -> None:
        settings = get_settings()

        if not settings.access_log:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "/")
        ip = _client_ip(scope)
        rid = _request_id(scope)
        _state(scope)["request_id"] = rid

        start = time.perf_counter()

        # Shared mutable cell so both closures can read/write the same state.
        cell: dict = {"connected": False, "close_code": None}

        async def wrapped_send(message: dict) -> None:
            if message["type"] == "websocket.accept":
                cell["connected"] = True
                _log.info("WS CONNECT %s ip=%s rid=%s", path, ip, rid)
            elif message["type"] == "websocket.close" and cell["close_code"] is None:
                # Server-initiated close — prefer client disconnect code if it
                # arrives later (overwritten in wrapped_receive).
                cell["close_code"] = message.get("code", 1000)
            await send(message)

        async def wrapped_receive() -> dict:
            message = await receive()
            if message["type"] == "websocket.disconnect":
                cell["close_code"] = message.get("code", 1000)
            return message

        await self.app(scope, wrapped_receive, wrapped_send)

        if cell["connected"]:
            duration_s = time.perf_counter() - start
            user_id = scope.get("state", {}).get("user_id")
            user_str = str(user_id) if user_id is not None else "-"
            code = cell["close_code"] if cell["close_code"] is not None else 1000

            msg = (
                f"WS CLOSE {path} code={code} duration={duration_s:.1f}s "
                f"user={user_str} ip={ip} rid={rid}"
            )
            _log.log(logging.WARNING if code in _WARN_WS_CODES else logging.INFO, msg)
