"""Startup validation — BASE-DESIGN.md §4.3: "a misconfigured production deploy that boots
and *then* misbehaves costs far more than one that refuses to boot."

Only active when DEBUG is off, since the values it guards against (the example SECRET_KEY,
an empty/wildcard ALLOWED_HOSTS) are exactly what local dev intentionally uses.
"""

import os
from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage, Error, Tags, register

# The literal placeholder value shipped in backend/.env.example — if this is still the live
# SECRET_KEY with DEBUG off, the deploy copied the example file instead of generating one.
# Not a real secret — ruff's bandit rule can't tell that from the variable name alone.
EXAMPLE_SECRET_KEY = "django-insecure-replace-me-see-env-example"  # noqa: S105

# Installed app packages append the keys their README declares required here — an empty
# list means "the currently-installed set of apps has no required keys of its own" (a fresh
# scaffold), not "nothing is required" (SECRET_KEY/FERNET_KEY are already enforced by
# `decouple.config(...)` raising at import time — see config/settings.py).
REQUIRED_ENV_KEYS: list[str] = []


@register(Tags.security)
def check_production_settings(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    errors: list[CheckMessage] = []

    if settings.DEBUG:
        return errors

    if settings.SECRET_KEY == EXAMPLE_SECRET_KEY:
        errors.append(
            Error(
                "SECRET_KEY is still the .env.example placeholder value.",
                hint='Generate a real key: python3 -c "import secrets; '
                'print(secrets.token_urlsafe(64))"',
                id="config.E001",
            )
        )

    if not settings.ALLOWED_HOSTS or settings.ALLOWED_HOSTS == ["*"]:
        errors.append(
            Error(
                "ALLOWED_HOSTS is empty or '*' with DEBUG off.",
                hint="Set ALLOWED_HOSTS to the real, comma-separated production host names.",
                id="config.E002",
            )
        )

    missing = [key for key in REQUIRED_ENV_KEYS if not os.environ.get(key)]
    if missing:
        errors.append(
            Error(
                f"Required .env keys are not set: {', '.join(missing)}.",
                hint="An installed app package declared these required in its README.",
                id="config.E003",
            )
        )

    return errors
