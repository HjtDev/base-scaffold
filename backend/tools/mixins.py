"""Shared DRF mixins and the standard error envelope, for project-owned code
(`config/`, `core/`) — see BASE-DESIGN.md §3. Not for installed app packages: see
`tools/crypto.py`'s docstring for why, and APP-DESIGN.md §4 for the internal equivalent
an app bundles instead.

`standard_exception_handler` is wired via `REST_FRAMEWORK["EXCEPTION_HANDLER"]` in
`config/settings.py` rather than left as an opt-in mixin, specifically so the envelope
applies to every DRF-raised error (401/403/404/405/429) and not only to views that
remember to inherit something. Every error response takes this shape:

    {"error": {"code": "validation_error", "message": "...", "details": {}, "request_id": "..."}}

`details` is always present (`{}` when there's nothing field-level) so a client never
needs to branch on whether the key exists. `code` is a stable, machine-readable string —
adding one is a minor change, renaming one is breaking. The full set this handler emits:
`validation_error`, `parse_error`, `not_authenticated`, `authentication_failed`,
`permission_denied`, `not_found`, `method_not_allowed`, `throttled`, `server_error`
(also documented in BASE-DESIGN.md §3).
"""

import logging
from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from config.logging import request_id_var
from tools.cache import build_cache_key, cached_call

__all__ = ["CachedListMixin", "standard_exception_handler"]

logger = logging.getLogger(__name__)

# Ordered most-specific-first: several of these subclass one another (e.g.
# NotAuthenticated and AuthenticationFailed both subclass APIException independently,
# but ValidationError has its own subclasses in some apps), so isinstance order matters.
_CODE_BY_EXCEPTION: list[tuple[type[Exception], str]] = [
    (drf_exceptions.ValidationError, "validation_error"),
    (drf_exceptions.ParseError, "parse_error"),
    (drf_exceptions.NotAuthenticated, "not_authenticated"),
    (drf_exceptions.AuthenticationFailed, "authentication_failed"),
    (drf_exceptions.PermissionDenied, "permission_denied"),
    (drf_exceptions.NotFound, "not_found"),
    (drf_exceptions.MethodNotAllowed, "method_not_allowed"),
    (drf_exceptions.Throttled, "throttled"),
]


def _code_for(exc: Exception) -> str:
    for exc_type, code in _CODE_BY_EXCEPTION:
        if isinstance(exc, exc_type):
            return code
    return "error"  # some other APIException DRF already turned into a response


def _message_and_details(data: Any, *, code: str) -> tuple[str, dict[str, Any]]:
    """Splits DRF's raw `response.data` into a flat message plus a details dict."""
    if isinstance(data, dict) and set(data) == {"detail"}:
        return str(data["detail"]), {}
    if isinstance(data, list):
        return "; ".join(str(item) for item in data), {"non_field_errors": data}
    if isinstance(data, dict):
        message = "Validation failed." if code == "validation_error" else "Request failed."
        return message, data
    return str(data), {}


def standard_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """DRF `EXCEPTION_HANDLER` producing the envelope described in this module's docstring.

    Delegates to DRF's own `exception_handler` first and rewrites only `response.data` —
    never rebuilds the `Response` from scratch — so headers DRF already set (`Retry-After`
    on a throttled response, `WWW-Authenticate` on a 401) survive untouched.
    """
    # DRF's own exception_handler converts a plain Django Http404/PermissionDenied into
    # its DRF equivalent internally, on a *new* exception object it builds and discards —
    # it never hands that conversion back to us. Without redoing it here, _code_for(exc)
    # below would see the original Http404/PermissionDenied, match nothing, and every 404
    # raised the normal Django way (get_object_or_404, DoesNotExist) would fall through to
    # the generic "error" code instead of "not_found"/"permission_denied".
    if isinstance(exc, Http404):
        exc = drf_exceptions.NotFound(*exc.args)
    elif isinstance(exc, DjangoPermissionDenied):
        exc = drf_exceptions.PermissionDenied(*exc.args)

    response = drf_exception_handler(exc, context)

    if response is None:
        # DRF returns None for anything that isn't an APIException/Http404/PermissionDenied
        # — i.e. a genuinely unhandled exception. Normally that propagates to Django's own
        # error handling, which is what triggers `django.request` logging and Sentry
        # capture. Returning a 500 envelope here instead swallows that unless we log
        # explicitly first.
        logger.exception("Unhandled exception in view", exc_info=exc)
        message = str(exc) if settings.DEBUG else "Internal server error."
        return Response(
            {
                "error": {
                    "code": "server_error",
                    "message": message,
                    "details": {},
                    "request_id": request_id_var.get(),
                }
            },
            status=500,
        )

    code = _code_for(exc)
    message, details = _message_and_details(response.data, code=code)
    response.data = {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": request_id_var.get(),
        }
    }
    return response


class CachedListMixin:
    """Caches a `ListAPIView`'s serialized data per user and querystring.

    Set `cache_timeout` (seconds) on the view — matches the convention APP-DESIGN.md §4
    tells app packages to bundle their own equivalent of. Caches `response.data`, not the
    `Response` object itself: a DRF `Response` carries renderer/request state that isn't
    meant to be pickled into a cache backend, where a plain list of serialized dicts is.

    Usage: `class MyListView(CachedListMixin, generics.ListAPIView): ...` — the mixin
    must precede the generic view in the MRO so it wraps `list()`.
    """

    cache_timeout: int = 60
    cache_namespace: str = ""  # falls back to the view class name

    def _cache_namespace(self) -> str:
        return self.cache_namespace or type(self).__name__

    def _cache_key(self, request: Any) -> str:
        user_part = getattr(request.user, "pk", None) or "anon"
        return build_cache_key(self._cache_namespace(), user_part, request.get_full_path())

    def list(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        def build() -> Any:
            # This mixin is only ever combined with generics.ListAPIView (see the class
            # docstring), which is where `list()` actually comes from — mypy can't see
            # that from this class's own bases, since a plain mixin has none.
            return super(CachedListMixin, self).list(request, *args, **kwargs).data  # type: ignore[misc]

        data = cached_call(self._cache_key(request), self.cache_timeout, build)
        return Response(data)
