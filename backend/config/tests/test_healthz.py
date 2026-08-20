"""`/healthz/` proves the DB and cache are actually reachable, not just that Python is
running — so the down-path (503) is the whole point of testing it, not an afterthought.
"""

from unittest.mock import patch

import pytest
from django.db import DatabaseError
from django.test import Client, override_settings

from config.views import _check_cache, _check_database


@pytest.mark.django_db
def test_check_database_true_against_the_real_test_db() -> None:
    assert _check_database() == (True, "ok")


@pytest.mark.django_db
def test_check_database_false_when_the_connection_raises() -> None:
    # Django's test runner forces DEBUG=False for the whole session (setup_test_environment),
    # so the raw-detail branch below needs an explicit override to exercise it at all —
    # otherwise this test would silently assert against the masked "unavailable" string
    # and never touch the DEBUG=True code path.
    with (
        override_settings(DEBUG=True),
        patch("config.views.connections") as mock_connections,
    ):
        mock_connections.__getitem__.return_value.cursor.side_effect = DatabaseError("boom")
        ok, detail = _check_database()

    assert ok is False
    assert detail == "boom"


def test_check_cache_true_against_the_real_test_cache() -> None:
    assert _check_cache() == (True, "ok")


def test_check_cache_false_when_the_backend_raises() -> None:
    with override_settings(DEBUG=True), patch("config.views.cache") as mock_cache:
        mock_cache.set.side_effect = Exception("redis down")
        ok, detail = _check_cache()

    assert ok is False
    assert detail == "redis down"


@pytest.mark.django_db
def test_check_database_detail_is_generic_with_debug_off() -> None:
    # /healthz/ is unauthenticated — a raw exception string routinely names the internal
    # host/port a service failed to reach, which must never reach an anonymous caller in
    # production.
    with (
        override_settings(DEBUG=False),
        patch("config.views.connections") as mock_connections,
    ):
        mock_connections.__getitem__.return_value.cursor.side_effect = DatabaseError(
            'connection to server at "db" (10.0.0.5), port 5432 failed'
        )
        ok, detail = _check_database()

    assert ok is False
    assert detail == "unavailable"


def test_check_cache_detail_is_generic_with_debug_off() -> None:
    with override_settings(DEBUG=False), patch("config.views.cache") as mock_cache:
        mock_cache.set.side_effect = Exception("Error -2 connecting to redis:6379.")
        ok, detail = _check_cache()

    assert ok is False
    assert detail == "unavailable"


def test_check_cache_false_on_round_trip_mismatch() -> None:
    with patch("config.views.cache") as mock_cache:
        mock_cache.get.return_value = "not-what-we-wrote"
        ok, detail = _check_cache()

    assert ok is False
    assert detail == "round-trip mismatch"


@pytest.mark.django_db
def test_healthz_200_when_db_and_cache_are_up() -> None:
    response = Client().get("/healthz/")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "ok",
        "checks": {
            "database": {"ok": True, "detail": "ok"},
            "cache": {"ok": True, "detail": "ok"},
        },
    }


@pytest.mark.django_db
def test_healthz_503_when_database_is_down() -> None:
    with patch("config.views._check_database", return_value=(False, "connection refused")):
        response = Client().get("/healthz/")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["database"] == {"ok": False, "detail": "connection refused"}
    assert body["checks"]["cache"]["ok"] is True


@pytest.mark.django_db
def test_healthz_503_when_cache_is_down() -> None:
    with patch("config.views._check_cache", return_value=(False, "connection refused")):
        response = Client().get("/healthz/")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["cache"] == {"ok": False, "detail": "connection refused"}
    assert body["checks"]["database"]["ok"] is True
