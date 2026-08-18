from cryptography.fernet import Fernet, InvalidToken
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from tools import crypto


def test_round_trip() -> None:
    token = crypto.encrypt("hello world")
    assert crypto.decrypt(token) == "hello world"


def test_ciphertext_differs_from_plaintext() -> None:
    token = crypto.encrypt("hello world")
    assert token != "hello world"


def test_two_encryptions_of_same_input_differ() -> None:
    # Fernet embeds a random IV and a timestamp, so encrypting the same plaintext twice
    # must never produce the same token — a repeat would be a real cryptographic bug.
    first = crypto.encrypt("hello world")
    second = crypto.encrypt("hello world")
    assert first != second
    assert crypto.decrypt(first) == crypto.decrypt(second) == "hello world"


def test_round_trip_non_ascii() -> None:
    token = crypto.encrypt("héllo wörld — 你好")
    assert crypto.decrypt(token) == "héllo wörld — 你好"


def test_tampered_token_is_rejected() -> None:
    token = crypto.encrypt("hello world")
    tampered = token[:-4] + ("A" if token[-4] != "A" else "B") + token[-3:]
    try:
        crypto.decrypt(tampered)
    except InvalidToken:
        pass
    else:
        raise AssertionError("tampered token was accepted")


def test_token_from_a_different_key_is_rejected() -> None:
    foreign_token = Fernet(Fernet.generate_key()).encrypt(b"hello world").decode()
    try:
        crypto.decrypt(foreign_token)
    except InvalidToken:
        pass
    else:
        raise AssertionError("token encrypted under a different key was accepted")


def test_invalid_fernet_key_raises_improperly_configured() -> None:
    crypto._fernet.cache_clear()  # must bust the lru_cache so it re-reads settings
    try:
        with override_settings(FERNET_KEY="not-a-valid-fernet-key"):
            try:
                crypto.encrypt("hello world")
            except ImproperlyConfigured as exc:
                assert "FERNET_KEY" in str(exc)
            else:
                raise AssertionError("invalid FERNET_KEY did not raise ImproperlyConfigured")
    finally:
        crypto._fernet.cache_clear()  # restore, so tests that run after this one see a valid key
