"""Field-level encryption for project-owned models, wrapping `FERNET_KEY` — for `config/`
and `core/` code only. See BASE-DESIGN.md §3 and INTEGRATION-GUIDE.md §6: an installed app
package must never import this module — it can't assume a host's `tools/` exists at a
stable path. An app that needs encryption bundles its own equivalent with its own
documented `.env` key — never this module. `appkit.crypto.Cipher` itself reads no Django
setting or env var of its own (appkit's README, "Required `.env` keys"); `FERNET_KEY` is a
scaffold-owned key this module is the one place that reads.

A thin host wrapper over `appkit.crypto.Cipher`: appkit owns the Fernet primitive (and the
`crypto` extra it requires — `backend/pyproject.toml`), this module owns reading
`FERNET_KEY` and naming it specifically in the error a bad key produces, since appkit's own
error deliberately knows nothing about this host's env var names.

    from tools.crypto import encrypt, decrypt

    token = encrypt("some secret")
    plaintext = decrypt(token)
"""

from functools import lru_cache

from appkit.crypto import Cipher
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

__all__ = ["decrypt", "encrypt"]


@lru_cache(maxsize=1)
def _cipher() -> Cipher:
    """Builds the `Cipher` from `settings.FERNET_KEY`, lazily.

    Lazy and cached rather than built at import time: `settings.FERNET_KEY` is read at
    settings import, so an eager `Cipher(...)` here would make an invalid key break every
    management command, including ones that never touch encryption. Building it on first
    use means only code paths that actually encrypt/decrypt pay for a bad key — with a
    clear error naming `FERNET_KEY` specifically, rather than appkit's own generic "a key
    that is not a valid Fernet key" wording, which has no way to know this host's env var
    name.
    """
    try:
        return Cipher(settings.FERNET_KEY)
    except ImproperlyConfigured as exc:
        raise ImproperlyConfigured(
            "FERNET_KEY is not a valid Fernet key. Generate one with: "
            'python3 -c "from appkit.crypto import generate_key; print(generate_key())"'
        ) from exc


def encrypt(value: str) -> str:
    """Encrypts `value`, returning a URL-safe token string."""
    return _cipher().encrypt(value)


def decrypt(token: str) -> str:
    """Decrypts a token produced by `encrypt`.

    Raises `cryptography.fernet.InvalidToken` for a tampered, expired, or wrong-key
    token — never silently returns garbage.
    """
    return _cipher().decrypt(token)
