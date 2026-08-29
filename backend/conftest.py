"""Project-wide fixtures — BASE-DESIGN.md §5.2.

Empty by design as of the appkit v1.0.0 integration: this file used to define
`api_client`/`user`/`admin_user`/`auth_client` directly, but appkit's opt-in pytest plugin
(`-p appkit.testing`, `pyproject.toml`'s `addopts`) now provides the `appkit_`-prefixed
equivalents — `appkit_api_client`, `appkit_user`, `appkit_admin_user`, `appkit_auth_client`,
`appkit_admin_client` — built reflectively through `get_user_model().USERNAME_FIELD`, so they
work against a custom user model with no extra configuration. Use those instead.

The scaffold's own versions were dropped rather than kept as aliases: `admin_user` collides
with a fixture pytest-django ships natively, and (verified directly) pytest-django's version
wins that collision silently — the exact hazard appkit's `appkit_` prefix exists to prevent.
Keeping a same-named local fixture only recreates that ambiguity one file away.

Anything spanning more than one installed app belongs in `core/tests/conftest.py` instead, not
here.
"""
