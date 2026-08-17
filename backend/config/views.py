"""Cross-cutting views. `healthz` is the /healthz/ endpoint BASE-DESIGN.md §8.2 wires into
every compose healthcheck and the deploy rollout's readiness poll.
"""

from django.core.cache import cache
from django.db import DatabaseError, connections
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

# A single request-scoped constant so the cache round-trip can tell "we wrote this and read
# it back" apart from "cache.get() returned someone else's stale key by coincidence".
_HEALTHZ_CACHE_KEY = "healthz-check"
_HEALTHZ_CACHE_VALUE = "ok"


def _check_database() -> tuple[bool, str]:
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError as exc:
        return False, str(exc)
    return True, "ok"


def _check_cache() -> tuple[bool, str]:
    try:
        cache.set(_HEALTHZ_CACHE_KEY, _HEALTHZ_CACHE_VALUE, timeout=5)
        if cache.get(_HEALTHZ_CACHE_KEY) != _HEALTHZ_CACHE_VALUE:
            return False, "round-trip mismatch"
    except Exception as exc:  # any backend failure here means "not healthy"
        return False, str(exc)
    return True, "ok"


@require_GET
@never_cache
def healthz(request: HttpRequest) -> JsonResponse:
    """Proves the things whose failure means "don't send traffic here": a real query against
    the database and a real round-trip against the cache (Redis). A healthcheck that only
    proves Python is running will happily report healthy while every request 500s.

    Deliberately a plain Django function view, not a DRF view — so ScopedRateThrottle
    structurally cannot apply, keeping this endpoint unauthenticated and unthrottled by
    construction rather than by a permission/throttle class someone could accidentally add.
    """
    db_ok, db_detail = _check_database()
    cache_ok, cache_detail = _check_cache()
    healthy = db_ok and cache_ok

    return JsonResponse(
        {
            "status": "ok" if healthy else "unavailable",
            "checks": {
                "database": {"ok": db_ok, "detail": db_detail},
                "cache": {"ok": cache_ok, "detail": cache_detail},
            },
        },
        status=200 if healthy else 503,
    )
