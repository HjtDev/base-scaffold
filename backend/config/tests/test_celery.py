"""`config.celery` — the app must be named "config" (that's what `celery -A config` resolves)
and re-exported from `config/__init__.py` for autodiscovery to work at all.
"""

from django.conf import settings

import config
from config.celery import app as celery_app


def test_app_is_named_config() -> None:
    # `celery -A config worker` resolves the app by this name — BASE-DESIGN.md §8.2.
    assert celery_app.main == "config"


def test_reexported_from_config_init_for_autodiscovery() -> None:
    assert config.celery_app is celery_app


def test_config_from_object_applied_the_django_settings() -> None:
    assert celery_app.conf.broker_url == settings.CELERY_BROKER_URL
    assert celery_app.conf.result_backend == settings.CELERY_RESULT_BACKEND
    assert celery_app.conf.task_serializer == "json"


def test_beat_scheduler_is_the_database_scheduler() -> None:
    assert celery_app.conf.beat_scheduler == "django_celery_beat.schedulers:DatabaseScheduler"
