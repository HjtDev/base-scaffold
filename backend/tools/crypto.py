"""Field-level encryption for project-owned models, wrapping `FERNET_KEY` — for `config/`
and `core/` code only. See BASE-DESIGN.md §3 and INTEGRATION-GUIDE.md §6: an installed app
package must never import this module — it can't assume a host's `tools/` exists at a
stable path. An app that needs encryption bundles its own equivalent with its own
documented `.env` key.

    from tools.crypto import encrypt, decrypt

    token = encrypt("some secret")
    plaintext = decrypt(token)
"""

from functools import lru_cache

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

__all__ = ["decrypt", "encrypt"]


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    """Builds the `Fernet` cipher from `settings.FERNET_KEY`, lazily.

    Lazy and cached rather than built at import time: `settings.FERNET_KEY` is read at
    settings import, so an eager `Fernet(...)` here would make an invalid key break every
    management command, including ones that never touch encryption. Building it on first
    use means only code paths that actually encrypt/decrypt pay for a bad key — with a
    clear error instead of a cryptic one from deep inside the `cryptography` library.
    """
    try:
        return Fernet(settings.FERNET_KEY)
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(
            "FERNET_KEY is not a valid Fernet key. Generate one with: "
            'python3 -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        ) from exc


def encrypt(value: str) -> str:
    """Encrypts `value`, returning a URL-safe token string."""
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypts a token produced by `encrypt`.

    Raises `cryptography.fernet.InvalidToken` for a tampered, expired, or wrong-key
    token — never silently returns garbage.
    """
    return _fernet().decrypt(token.encode()).decode()
