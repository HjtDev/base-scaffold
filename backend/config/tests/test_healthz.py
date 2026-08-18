"""`/healthz/` proves the DB and cache are actually reachable, not just that Python is
running — so the down-path (503) is the whole point of testing it, not an afterthought.
"""

from unittest.mock import patch

import pytest
from django.db import DatabaseError
from django.test import Client

from config.views import _check_cache, _check_database


@pytest.mark.django_db
def test_check_database_true_against_the_real_test_db() -> None:
    assert _check_database() == (True, "ok")


@pytest.mark.django_db
def test_check_database_false_when_the_connection_raises() -> None:
    with patch("config.views.connections") as mock_connections:
        mock_connections.__getitem__.return_value.cursor.side_effect = DatabaseError("boom")
        ok, detail = _check_database()

    assert ok is False
    assert detail == "boom"


def test_check_cache_true_against_the_real_test_cache() -> None:
    assert _check_cache() == (True, "ok")


def test_check_cache_false_when_the_backend_raises() -> None:
    with patch("config.views.cache") as mock_cache:
        mock_cache.set.side_effect = Exception("redis down")
        ok, detail = _check_cache()

    assert ok is False
    assert detail == "redis down"


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
