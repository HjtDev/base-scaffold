"""`config.checks.check_production_settings` — BASE-DESIGN.md §4.3: "a misconfigured
production deploy that boots and *then* misbehaves costs far more than one that refuses
to boot." Asserts on check IDs, never on message text — the ID is the stable contract.
"""

import os
from unittest.mock import patch

from django.test import override_settings

from config.checks import EXAMPLE_SECRET_KEY, check_production_settings


def _error_ids() -> set[str]:
    return {str(msg.id) for msg in check_production_settings(app_configs=None)}


def test_no_errors_when_debug_is_on_even_with_bad_settings() -> None:
    with override_settings(DEBUG=True, SECRET_KEY=EXAMPLE_SECRET_KEY, ALLOWED_HOSTS=[]):
        assert _error_ids() == set()


def test_e001_when_secret_key_is_still_the_placeholder() -> None:
    with override_settings(
        DEBUG=False, SECRET_KEY=EXAMPLE_SECRET_KEY, ALLOWED_HOSTS=["example.com"]
    ):
        assert "config.E001" in _error_ids()


def test_no_e001_with_a_real_secret_key() -> None:
    with override_settings(
        DEBUG=False, SECRET_KEY="a-real-generated-key", ALLOWED_HOSTS=["example.com"]
    ):
        assert "config.E001" not in _error_ids()


def test_e002_when_allowed_hosts_is_empty() -> None:
    with override_settings(DEBUG=False, SECRET_KEY="a-real-generated-key", ALLOWED_HOSTS=[]):
        assert "config.E002" in _error_ids()


def test_e002_when_allowed_hosts_is_wildcard() -> None:
    with override_settings(
        DEBUG=False, SECRET_KEY="a-real-generated-key", ALLOWED_HOSTS=["*"]
    ):
        assert "config.E002" in _error_ids()


def test_no_e002_with_real_allowed_hosts() -> None:
    with override_settings(
        DEBUG=False, SECRET_KEY="a-real-generated-key", ALLOWED_HOSTS=["example.com"]
    ):
        assert "config.E002" not in _error_ids()


def test_no_errors_on_a_correctly_configured_prod_shaped_env() -> None:
    with override_settings(
        DEBUG=False, SECRET_KEY="a-real-generated-key", ALLOWED_HOSTS=["example.com"]
    ):
        assert _error_ids() == set()


def test_e003_when_an_app_declared_required_env_key_is_missing() -> None:
    with (
        override_settings(
            DEBUG=False, SECRET_KEY="a-real-generated-key", ALLOWED_HOSTS=["example.com"]
        ),
        patch("config.checks.REQUIRED_ENV_KEYS", ["SOME_MISSING_KEY_XYZ"]),
    ):
        os.environ.pop("SOME_MISSING_KEY_XYZ", None)
        assert "config.E003" in _error_ids()


def test_no_e003_when_the_required_env_key_is_present() -> None:
    with (
        override_settings(
            DEBUG=False, SECRET_KEY="a-real-generated-key", ALLOWED_HOSTS=["example.com"]
        ),
        patch("config.checks.REQUIRED_ENV_KEYS", ["SOME_PRESENT_KEY_XYZ"]),
        patch.dict(os.environ, {"SOME_PRESENT_KEY_XYZ": "value"}),
    ):
        assert "config.E003" not in _error_ids()
