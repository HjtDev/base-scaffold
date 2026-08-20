"""Environment-split logging config, plus the request-ID plumbing that correlates a single
request's log lines across both configs.

`build_logging_config(debug=DEBUG)` returns a colored, human-readable console config in dev
and a structlog-based JSON config otherwise — see BASE-DESIGN.md §3: JSON in dev is unreadable
to a person, colored text in prod is unparseable by any log aggregator, so a single config is
wrong in one environment no matter which is picked.

The `ContextVar`, `RequestIDMiddleware`, and `RequestIDFilter` all live here, alongside the
function they exist to serve, rather than in a separate `middleware.py`. No new dependency:
`contextvars` and `logging.Filter` are both stdlib.
"""

import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

import structlog
from asgiref.sync import markcoroutinefunction
from django.http import HttpRequest, HttpResponse

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# Caps how much of an inbound X-Request-ID we trust, and restricts it to characters that
# can't inject newlines or control sequences into a log line.
_MAX_REQUEST_ID_LEN = 64
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]+$")


def _clean_request_id(raw: str | None) -> str:
    """Accept an inbound X-Request-ID if it looks safe, else mint a new one."""
    if raw and len(raw) <= _MAX_REQUEST_ID_LEN and _VALID_REQUEST_ID.match(raw):
        return raw
    return uuid.uuid4().hex


class RequestIDMiddleware:
    """Assigns/propagates a request ID for log correlation, and echoes it on the response.

    Implemented as an async middleware (`async_capable = True`, `sync_capable = False`):
    a sync-only middleware would force Django to run the whole chain through a thread pool,
    quietly undoing the reason this scaffold is on ASGI in the first place. Belongs near the
    top of MIDDLEWARE — after SecurityMiddleware, before anything that logs.
    """

    sync_capable = False
    async_capable = True

    def __init__(self, get_response: Callable[[HttpRequest], Awaitable[HttpResponse]]) -> None:
        self.get_response = get_response
        # `sync_capable`/`async_capable` only tell Django's *own* `load_middleware` how to
        # build this middleware's wrapper — they say nothing to a generic
        # `inspect.iscoroutinefunction(instance)` check, which is what any middleware
        # WRAPPING this one (e.g. SecurityMiddleware, via django.utils.deprecation's
        # MiddlewareMixin) uses to decide whether to `await` it. Without this explicit
        # mark, an instance's `async def __call__` is invisible to that check — Django's
        # own `MiddlewareMixin` does this same marking internally; a raw, non-Mixin async
        # middleware has to do it itself, or every outer sync-style middleware calls this
        # one without awaiting it, crashing on the returned coroutine. Confirmed to break
        # every real request (ASGI and WSGI both) without this line.
        markcoroutinefunction(self)

    async def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = _clean_request_id(request.headers.get("X-Request-ID"))
        # Always reset in `finally` — under ASGI concurrency, a set-without-reset leaks
        # this request's ID into whatever runs next on the same task (most visibly, a
        # Celery task enqueued mid-request, or an unrelated request if something goes wrong).
        token = request_id_var.set(request_id)
        try:
            response = await self.get_response(request)
        finally:
            request_id_var.reset(token)
        response["X-Request-ID"] = request_id
        return response


class RequestIDFilter(logging.Filter):
    """Stamps `record.request_id` from the contextvar, for any handler/formatter that reads
    the raw `LogRecord` rather than the structlog event dict (e.g. a future file handler with
    a plain %-style formatter). Never raises — logging outside a request cycle (management
    commands, Celery tasks, startup) must still work, defaulting to "-".
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def _add_request_id(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor: stamps the contextvar's request ID into every event dict, so it
    ends up as a real field in the JSON renderer's output and a visible key in the console
    renderer's output — for both structlog-native calls and stdlib logging calls routed
    through structlog (Django's/Celery's own `logging.getLogger(...)` calls).
    """
    event_dict["request_id"] = request_id_var.get()
    return event_dict


def build_logging_config(*, debug: bool) -> dict[str, Any]:
    """Colored console config when `debug`, structlog JSON config otherwise. Both carry
    `request_id` so a single request's log lines can be correlated — see BASE-DESIGN.md §3.
    """
    shared_processors: list[Any] = [
        _add_request_id,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # Global, one-time structlog configuration — routes structlog-native log calls through
    # the same stdlib handlers/formatters as everything else, so `LOGGING` below is the one
    # source of truth for where logs actually go.
    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer = (
        structlog.dev.ConsoleRenderer(colors=True) if debug else structlog.processors.JSONRenderer()
    )

    formatter = {
        "()": structlog.stdlib.ProcessorFormatter,
        "processors": [structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
        "foreign_pre_chain": shared_processors,
    }

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_id": {"()": RequestIDFilter},
        },
        "formatters": {
            "default": formatter,
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "filters": ["request_id"],
            },
        },
        "root": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "loggers": {
            "django": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "django.request": {
                "handlers": ["console"],
                "level": "INFO" if debug else "WARNING",
                "propagate": False,
            },
            "celery": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
        },
    }
