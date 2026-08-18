"""Regression guard for CORRECTIONS.md #12: `RequestIDMiddleware` broke every real request
because it never marked itself coroutine-visible to the sync-style middleware wrapping it,
and neither `manage.py check` nor a unit-level middleware test dispatches a real request
through the actual `MIDDLEWARE` chain, so the bug shipped a full phase undetected.

`django.test.AsyncClient` builds the same `settings.MIDDLEWARE` chain in async mode
(`load_middleware(is_async=True)`) that `config.asgi.application` — what `uvicorn` actually
serves — runs in production. Driving it end-to-end here is what a unit test of
`RequestIDMiddleware` in isolation, or a sync `django.test.Client` request, cannot catch:
either one sidesteps exactly the async-adjacency failure that broke every endpoint.

No async test plugin (`pytest-asyncio`/`anyio`) is configured for this project, so the
coroutine is driven explicitly via `asyncio.run()` rather than an `async def` test function.
"""

import asyncio

import pytest
from django.test import AsyncClient


@pytest.mark.django_db
def test_healthz_200_through_the_real_async_middleware_chain() -> None:
    response = asyncio.run(AsyncClient().get("/healthz/"))

    assert response.status_code == 200
    # Proves RequestIDMiddleware actually ran (and its response mutation actually reached
    # the client) rather than being silently dropped by a broken async adjacency upstream.
    assert response["X-Request-ID"]
    assert len(response["X-Request-ID"]) == 32  # uuid4().hex, minted since no header was sent
