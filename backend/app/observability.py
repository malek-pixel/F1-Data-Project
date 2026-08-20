"""Request logging, request ids, and an optional error-reporting hook.

WHY THIS EXISTS
---------------
Until this module, a deployed failure told nobody. Every *handled* failure was
already logged and already returned a correct status -- `main.py` has had
handlers for the store, the Supabase leg and a missing capability for some
time -- but the log lines were unstructured, carried no request identity, and
recorded nothing at all about requests that succeeded. There was no way to
answer "what is the 5xx rate" or "which endpoint is slow" from what the
process emitted, and no way to tie a reader's report of a broken screen to the
line in the log that explains it.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not aggregate, store, alert or draw. `docs/OPERATIONS.md` section 6
says to use the platform's monitoring rather than build any, and that
judgement stands: an in-process counter resets on every deploy and is per
worker, so a `/metrics` endpoint of our own would be a number that looks
authoritative and is not.

What this module does instead is make the process *legible* to whatever is
already watching it: one structured line per request, on stdout, which every
hosting platform already collects and can already aggregate into a 5xx rate
and a p95. The observability is real; the storage is someone else's job.

THE THREE PIECES
----------------
1. **A request id.** Taken from an inbound `X-Request-ID` when a proxy set one
   -- so a trace survives the hop -- and generated when not. Echoed on the
   response, attached to every log line emitted while the request runs, and
   available to the error handlers so a reader can quote it.

2. **One log line per request**, with method, route template, status and
   duration. The route *template* (`/api/drivers/{driver_id}`) rather than the
   raw path, because 129 distinct paths that are really one endpoint make a
   latency percentile meaningless. The raw path is included separately for
   4xx/5xx, where the specific value is usually the point.

3. **An optional reporting hook.** `F1_SENTRY_DSN` turns on Sentry *if* the
   SDK is installed. Both halves are optional on purpose: this project carries
   no dependency it does not need, so `sentry-sdk` is not in requirements.txt,
   and a deployment that wants reporting installs it. A DSN set with no SDK
   present warns loudly at startup rather than silently reporting nothing --
   the failure mode that makes people trust an alerting system that is off.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware

log = logging.getLogger("f1.access")

# The id of the request being served, readable from anywhere without threading
# it through every call. A ContextVar rather than a global because the API is
# async: two requests are routinely in flight in the same thread.
current_request_id: ContextVar[str] = ContextVar("current_request_id", default="-")

# Requests slower than this are logged at WARNING even when they succeed. The
# audit measured `dataset/summary` at 400-500 ms and `records` at ~340 ms as
# the slowest endpoints, so 1000 ms sits comfortably above known-good and is
# still low enough to catch a regression rather than only an outage.
SLOW_REQUEST_MS = float(os.getenv("F1_SLOW_REQUEST_MS", "1000"))

_ID_ALPHABET_EXTRA = "-_"
_MAX_ID_LENGTH = 64


class RequestIdFilter(logging.Filter):
    """Attach the current request id to every record, not just access lines.

    Without this, `log.exception("Database error on %s", path)` in main.py
    lands in the log with no way to tie it to the access line beside it -- and
    under any concurrency "beside it" is not a relationship you can rely on.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = current_request_id.get()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line.

    Chosen because log aggregators parse it without a custom rule, and because
    a message containing a newline cannot forge a second log entry. Text stays
    the default for local development, where JSON is simply harder to read.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        # Structured fields set by the access middleware travel as their own
        # keys rather than being interpolated into the message, which is the
        # entire point of emitting JSON.
        for key, value in getattr(record, "fields", {}).items():
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Install the formatter and the request-id filter on the root logger.

    Idempotent: uvicorn also configures logging, and this runs at application
    import, so it has to be safe arriving either side of that.
    """
    fmt = os.getenv("F1_LOG_FORMAT", "text").lower()
    level = os.getenv("F1_LOG_LEVEL", "INFO").upper()

    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter()
        if fmt == "json"
        else logging.Formatter(
            "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s"
        )
    )
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    # Replace our own handler rather than stacking a duplicate on a reload.
    for existing in list(root.handlers):
        if getattr(existing, "_f1_observability", False):
            root.removeHandler(existing)
    handler._f1_observability = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level)

    # uvicorn's own access log duplicates ours without the request id or the
    # route template. Silenced rather than left to double every line.
    logging.getLogger("uvicorn.access").disabled = True


def configure_error_reporting() -> str:
    """Initialise Sentry when both a DSN and the SDK are present.

    Returns a short description of what happened, so startup can say it out
    loud instead of leaving the operator to guess.
    """
    dsn = os.getenv("F1_SENTRY_DSN", "").strip()
    if not dsn:
        return "disabled (no F1_SENTRY_DSN)"

    try:
        import sentry_sdk
    except ImportError:
        # Loud, because the alternative is a deployment that believes it has
        # error reporting and does not.
        log.error(
            "F1_SENTRY_DSN is set but sentry-sdk is not installed: error "
            "reporting is OFF. Install it (pip install sentry-sdk) or unset "
            "the variable."
        )
        return "MISCONFIGURED (DSN set, SDK missing)"

    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("F1_ENVIRONMENT", "production"),
        traces_sample_rate=float(os.getenv("F1_SENTRY_TRACES_SAMPLE_RATE", "0")),
        # This API serves a public, read-only historical dataset and has no
        # users, sessions or auth. There is no PII to send, and saying so
        # explicitly is cheaper than someone later assuming there might be.
        send_default_pii=False,
    )
    return "enabled"


def _route_template(request) -> str:
    """`/api/drivers/{driver_id}`, not `/api/drivers/65`.

    Built by substituting the matched path parameters back into the real path,
    rather than by reading `scope["route"].path`. The obvious implementation
    is the one that reads the route, and it is wrong here: this FastAPI
    version keeps a router included with `prefix="/api"` as an internal
    `_IncludedRouter` whose child routes still carry their own un-prefixed
    paths, and it leaves `root_path` empty. Reading the route therefore logged
    `/drivers/{driver_id}` for a request to `/api/drivers/1`, while
    app-level routes logged `/api/health` -- two naming schemes in one field,
    which is worse than either, since grouping by it would split one service
    into two.

    Substituting into `request.url.path` starts from the path that was
    actually served, so the prefix is present by construction and cannot drift
    if the routers are ever re-mounted somewhere else.

    Matching is per **segment**, not by string replacement: a driver id of `1`
    appearing inside `/api/seasons/2011/...` must not turn into
    `/api/seasons/20{driver_id}1/...`.

    Falls back to the raw path when nothing matched -- a 404 has no template,
    and inventing one would hide the actual URL being probed.
    """
    path = request.url.path
    params = request.scope.get("path_params") or {}
    if not params:
        return path

    # Values first, names second: two parameters can legitimately hold the
    # same value (`/seasons/2020/races/2020`), so each name is consumed once
    # and in order rather than matched repeatedly.
    remaining = [(name, str(value)) for name, value in params.items()]
    segments = []
    for segment in path.split("/"):
        match = next((pair for pair in remaining if pair[1] == segment), None)
        if match is not None:
            remaining.remove(match)
            segments.append("{" + match[0] + "}")
        else:
            segments.append(segment)
    return "/".join(segments)


def _safe_request_id(incoming: str) -> str:
    """Accept a proxy's id, or mint one. Never trust it unvalidated.

    This value is attacker-controlled and ends up in a log line and in a
    response header. A 200 KB "id", or one carrying a newline or a control
    character, is a log-injection and header-injection primitive rather than
    an identifier -- so it is length-bounded and alphabet-restricted, and
    anything failing either test is replaced rather than sanitised.
    """
    candidate = incoming.strip()
    if (
        candidate
        and len(candidate) <= _MAX_ID_LENGTH
        and all(c.isalnum() or c in _ID_ALPHABET_EXTRA for c in candidate)
    ):
        return candidate
    return uuid.uuid4().hex[:16]


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Time every request, give it an id, and log exactly one line for it.

    The line is emitted from a `finally`, so a request that raises is still
    recorded -- an unhandled exception is precisely the case you most want a
    duration and a status for, and it is the case a naive implementation
    silently drops.
    """

    async def dispatch(self, request, call_next):
        request_id = _safe_request_id(request.headers.get("x-request-id", ""))
        token = current_request_id.set(request_id)
        request.state.request_id = request_id

        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            fields = {
                "method": request.method,
                "route": _route_template(request),
                "status": status,
                "duration_ms": duration_ms,
            }
            # The concrete path matters when something went wrong, and is
            # noise when it did not.
            if status >= 400:
                fields["path"] = request.url.path

            if status >= 500:
                level = logging.ERROR
            elif status >= 400 or duration_ms >= SLOW_REQUEST_MS:
                level = logging.WARNING
            else:
                level = logging.INFO

            log.log(
                level,
                "%s %s -> %s in %sms",
                fields["method"],
                fields["route"],
                status,
                duration_ms,
                extra={"fields": fields},
            )
            current_request_id.reset(token)
