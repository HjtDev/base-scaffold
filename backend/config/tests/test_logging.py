"""`config.logging` — the request-ID contextvar/middleware/filter and the environment-split
logging config. The contextvar-reset test is the important one: under ASGI concurrency, a
set-without-reset leaks one request's ID into whatever runs next on the same task, and only
a test — not a code read — catches that.
"""

import asyncio
import logging

from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory

from config.logging import (
    RequestIDFilter,
    RequestIDMiddleware,
    build_logging_config,
    request_id_var,
)

factory = RequestFactory()


async def _stub_get_response(request: HttpRequest) -> HttpResponse:
    return HttpResponse("ok")


def _run_middleware(request: HttpRequest) -> HttpResponse:
    middleware = RequestIDMiddleware(_stub_get_response)
    return asyncio.run(middleware(request))


def test_mints_an_id_when_no_header_is_present() -> None:
    response = _run_middleware(factory.get("/"))
    assert len(response["X-Request-ID"]) == 32  # uuid4().hex


def test_propagates_a_valid_inbound_request_id() -> None:
    response = _run_middleware(factory.get("/", HTTP_X_REQUEST_ID="abc-123"))
    assert response["X-Request-ID"] == "abc-123"


def test_replaces_a_malformed_inbound_request_id() -> None:
    response = _run_middleware(factory.get("/", HTTP_X_REQUEST_ID="bad id; with spaces"))
    assert response["X-Request-ID"] != "bad id; with spaces"
    assert len(response["X-Request-ID"]) == 32


def test_replaces_an_over_length_inbound_request_id() -> None:
    too_long = "a" * 65
    response = _run_middleware(factory.get("/", HTTP_X_REQUEST_ID=too_long))
    assert response["X-Request-ID"] != too_long
    assert len(response["X-Request-ID"]) == 32


def test_resets_the_contextvar_after_the_request() -> None:
    _run_middleware(factory.get("/", HTTP_X_REQUEST_ID="reset-check"))
    assert request_id_var.get() == "-"


def test_request_id_filter_defaults_to_dash_outside_a_request_cycle() -> None:
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
    assert RequestIDFilter().filter(record) is True
    assert record.request_id == "-"  # type: ignore[attr-defined]


def test_build_logging_config_uses_console_renderer_when_debug() -> None:
    config = build_logging_config(debug=True)
    processors = config["formatters"]["default"]["processors"]
    assert any(type(p).__name__ == "ConsoleRenderer" for p in processors)
    assert "request_id" in config["filters"]


def test_build_logging_config_uses_json_renderer_when_not_debug() -> None:
    config = build_logging_config(debug=False)
    processors = config["formatters"]["default"]["processors"]
    assert any(type(p).__name__ == "JSONRenderer" for p in processors)
    assert "request_id" in config["filters"]
