"""The three wiring smoke tests BASE-DESIGN.md §5.4 / INTEGRATION-GUIDE.md §4 ask the host
to carry, plus a jazzmin-ordering regression test (§4.3 — jazzmin must precede
django.contrib.admin in INSTALLED_APPS). These pass vacuously in a fresh scaffold with no
apps installed — they're tripwires for the first app install, not assertions about today's
(empty) state.
"""

import re
from pathlib import Path
from typing import cast

import pytest
from django.conf import settings
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver

_THROTTLE_SCOPE_SOURCE_RE = re.compile(r'throttle_scope\s*=\s*"([^"]+)"')
_SCANNED_SOURCE_DIRS = ("core", "config", "tools")


def _iter_view_classes() -> list[type]:
    """Walks the resolved `ROOT_URLCONF`, including every installed app's own urls.py,
    yielding each view class. This is what catches an *installed app's* throttle scope —
    that code lives in site-packages, so no grep over `backend/` would ever see it.
    """
    classes: list[type] = []

    def walk(patterns: list[URLPattern | URLResolver]) -> None:
        for entry in patterns:
            if isinstance(entry, URLResolver):
                walk(entry.url_patterns)
            elif isinstance(entry, URLPattern):
                view_class = getattr(entry.callback, "cls", None)
                if view_class is not None:
                    classes.append(view_class)

    walk(get_resolver().url_patterns)
    return classes


def _throttle_scopes_from_urlconf() -> set[str]:
    scopes: set[str] = set()
    for view_class in _iter_view_classes():
        scope = getattr(view_class, "throttle_scope", None)
        if scope:
            scopes.add(scope)
    return scopes


def _throttle_scopes_from_source() -> set[str]:
    """Regex-scans host *production* source under core/, config/, tools/ — belt-and-
    suspenders next to the URLconf walk above, for a `throttle_scope` set on a view that
    never got mounted. Test directories are excluded: a throwaway `throttle_scope` inside
    a test fixture (e.g. this module's own throttling test) isn't a real wiring gap.
    """
    scopes: set[str] = set()
    backend_dir = Path(settings.BASE_DIR)
    for sub in _SCANNED_SOURCE_DIRS:
        for path in (backend_dir / sub).rglob("*.py"):
            if "tests" in path.relative_to(backend_dir).parts:
                continue
            scopes.update(_THROTTLE_SCOPE_SOURCE_RE.findall(path.read_text()))
    return scopes


def test_every_throttle_scope_exists_in_default_throttle_rates() -> None:
    scopes = _throttle_scopes_from_urlconf() | _throttle_scopes_from_source()
    # django-stubs infers REST_FRAMEWORK's value type from the literal dict in settings.py,
    # which is now legitimately heterogeneous (appkit's own NUM_PROXIES entry is an int
    # alongside the string/list/dict values here) — that union isn't uniformly Iterable[str],
    # so set(...) can't resolve an overload against it without this explicit narrowing.
    rates = cast("dict[str, str]", settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {}))
    configured = set(rates)
    missing = scopes - configured
    assert missing == set(), f"throttle_scope(s) with no DEFAULT_THROTTLE_RATES entry: {missing}"


@pytest.mark.django_db
def test_schema_endpoint_returns_200_and_valid_openapi() -> None:
    response = Client().get("/api/schema/", HTTP_ACCEPT="application/json")
    assert response.status_code == 200
    schema = response.json()
    assert schema.get("openapi", "").startswith("3.")


@pytest.mark.django_db
def test_every_schema_operation_carries_a_tag() -> None:
    schema = Client().get("/api/schema/", HTTP_ACCEPT="application/json").json()
    http_methods = {"get", "post", "put", "patch", "delete"}
    untagged = [
        f"{method.upper()} {path}"
        for path, operations in schema.get("paths", {}).items()
        for method, operation in operations.items()
        if method in http_methods and not operation.get("tags")
    ]
    assert untagged == [], f"schema operations missing a tag: {untagged}"


def test_jazzmin_precedes_django_admin_in_installed_apps() -> None:
    # jazzmin overrides the admin's templates via Django's app-directories loader, which
    # resolves to the FIRST match in INSTALLED_APPS. Reversed, the admin still renders,
    # just silently unthemed.
    apps = settings.INSTALLED_APPS
    assert apps.index("jazzmin") < apps.index("django.contrib.admin")
