"""Tests `standard_exception_handler` through a real DRF view dispatch — not by calling
the handler function directly — so each branch is exercised the way it actually runs in
production, including the headers DRF itself attaches (`WWW-Authenticate`, `Retry-After`).
Throwaway `APIView` subclasses are dispatched straight off `APIRequestFactory`, with no
`ROOT_URLCONF` involved: URL resolution plays no part in exception handling.
"""

import uuid
from unittest.mock import patch

from django.http import Http404
from django.test import override_settings
from rest_framework import exceptions
from rest_framework.authentication import BasicAuthentication
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

factory = APIRequestFactory()


def _dispatch(view_class: type[APIView], method: str = "get", **extra: object) -> Response:
    request = getattr(factory, method)("/", **extra)
    return view_class.as_view()(request)


def test_validation_error() -> None:
    class View(APIView):
        def get(self, request: object) -> Response:
            raise exceptions.ValidationError({"name": ["This field is required."]})

    response = _dispatch(View)

    assert response.status_code == 400
    assert response.data == {
        "error": {
            "code": "validation_error",
            "message": "Validation failed.",
            "details": {"name": ["This field is required."]},
            "request_id": "-",
        }
    }


def test_parse_error() -> None:
    class View(APIView):
        def get(self, request: object) -> Response:
            raise exceptions.ParseError("malformed body")

    response = _dispatch(View)

    assert response.status_code == 400
    assert response.data["error"]["code"] == "parse_error"
    assert response.data["error"]["message"] == "malformed body"
    assert response.data["error"]["details"] == {}


def test_not_authenticated_carries_www_authenticate_header() -> None:
    class View(APIView):
        # Plain class attribute, DRF's own convention — ClassVar would conflict with how
        # APIView itself declares this (mypy: "cannot override instance variable ... with
        # class variable"), and RUF012 doesn't know DRF views never instance-assign these.
        authentication_classes = [BasicAuthentication]  # noqa: RUF012

        def get(self, request: object) -> Response:
            raise exceptions.NotAuthenticated()

    response = _dispatch(View)

    assert response.status_code == 401
    assert response.data["error"]["code"] == "not_authenticated"
    assert response["WWW-Authenticate"].startswith("Basic")


def test_authentication_failed_carries_www_authenticate_header() -> None:
    class View(APIView):
        authentication_classes = [BasicAuthentication]  # noqa: RUF012 — see comment above

        def get(self, request: object) -> Response:
            raise exceptions.AuthenticationFailed("bad credentials")

    response = _dispatch(View)

    assert response.status_code == 401
    assert response.data["error"]["code"] == "authentication_failed"
    assert response.data["error"]["message"] == "bad credentials"
    assert "WWW-Authenticate" in response


def test_permission_denied() -> None:
    class View(APIView):
        def get(self, request: object) -> Response:
            raise exceptions.PermissionDenied("no")

    response = _dispatch(View)

    assert response.status_code == 403
    assert response.data["error"]["code"] == "permission_denied"
    assert response.data["error"]["message"] == "no"


def test_not_found_converts_django_http404() -> None:
    class View(APIView):
        def get(self, request: object) -> Response:
            raise Http404("missing")

    response = _dispatch(View)

    assert response.status_code == 404
    assert response.data["error"]["code"] == "not_found"


def test_method_not_allowed() -> None:
    class View(APIView):
        def get(self, request: object) -> Response:
            return Response({"ok": True})

    response = _dispatch(View, method="delete")

    assert response.status_code == 405
    assert response.data["error"]["code"] == "method_not_allowed"


def test_throttled_preserves_retry_after_header() -> None:
    class View(APIView):
        throttle_classes = [ScopedRateThrottle]  # noqa: RUF012 — see comment above
        throttle_scope = "mixins_test_scope"

        def get(self, request: object) -> Response:
            return Response({"ok": True})

    # A fresh ident per run: ScopedRateThrottle's cache entry lives in the real cache
    # backend and outlives this test process, so a fixed REMOTE_ADDR would carry a
    # counter over between repeated runs against the same (non-ephemeral) cache.
    ident = uuid.uuid4().hex

    # ScopedRateThrottle.THROTTLE_RATES is a plain class attribute, snapshotted from
    # api_settings.DEFAULT_THROTTLE_RATES once at import time (rest_framework/throttling.py)
    # — override_settings(REST_FRAMEWORK=...) fires DRF's setting_changed reload for
    # api_settings itself, but that reload never reaches this already-bound class
    # attribute. Patching the class attribute directly is the only thing that actually
    # takes effect.
    with patch.object(ScopedRateThrottle, "THROTTLE_RATES", {"mixins_test_scope": "1/day"}):
        first = _dispatch(View, REMOTE_ADDR=ident)
        assert first.status_code == 200

        second = _dispatch(View, REMOTE_ADDR=ident)

    assert second.status_code == 429
    assert second.data["error"]["code"] == "throttled"
    assert "Retry-After" in second


def test_unhandled_exception_hides_internals_with_debug_off() -> None:
    class View(APIView):
        def get(self, request: object) -> Response:
            raise RuntimeError("boom - internal detail")

    with override_settings(DEBUG=False):
        response = _dispatch(View)

    assert response.status_code == 500
    assert response.data["error"]["code"] == "server_error"
    assert "boom" not in response.data["error"]["message"]


def test_unhandled_exception_shows_internals_with_debug_on() -> None:
    class View(APIView):
        def get(self, request: object) -> Response:
            raise RuntimeError("boom - internal detail")

    with override_settings(DEBUG=True):
        response = _dispatch(View)

    assert response.status_code == 500
    assert response.data["error"]["code"] == "server_error"
    assert "boom - internal detail" in response.data["error"]["message"]
