"""Host-owned helpers for `config/` and `core/` — never importable by an installed app
package (see INTEGRATION-GUIDE.md §6, machine-enforced by the `banned-api` ruff config in
`pyproject.toml`).

As of the appkit v1.0.0 integration, this package holds only what genuinely depends on host
configuration — a host `.env` key, a host setting, a host policy decision. Everything that
was pure logic over Django's own APIs (caching, the DRF error envelope, request-ID
correlation) moved to `appkit`; see BASE-DESIGN.md §3 for the boundary rule and the full
before/after table.

Currently: `crypto.py`, wrapping `appkit.crypto.Cipher` with this host's own `FERNET_KEY`
env var — appkit's `Cipher` takes its key as a constructor argument and reads no setting or
env var of its own, so *something* has to own that reading, permanently. A future
host-specific helper belongs here on the same test: needs this host's own configuration to
behave correctly, not just Django/DRF's own APIs.
"""
