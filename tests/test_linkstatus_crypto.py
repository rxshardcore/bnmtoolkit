import base64

import pytest

from app.utils.linkstatus_crypto import PasswordDecryptionError, decrypt_linkstatus_password


def _linkstatus_encrypt(secret: str, key: str) -> str:
    encrypted = ""
    for idx, char in enumerate(secret):
        key_char = key[idx % len(key) - 1]
        encrypted += chr(ord(char) + ord(key_char))
    return base64.b64encode(encrypted.encode("latin-1")).decode("ascii")


def test_decrypt_linkstatus_shift_scheme():
    encrypted = _linkstatus_encrypt("wp-secret-123", "usmannnn")
    result = decrypt_linkstatus_password(encrypted, "usmannnn")
    assert result.value == "wp-secret-123"
    assert result.method == "linkstatus-shift"


def test_decrypt_uses_last_key_character_first():
    encrypted = _linkstatus_encrypt("a", "abc")
    result = decrypt_linkstatus_password(encrypted, "usmannnn")
    assert result.value != "a"

    result = decrypt_linkstatus_password(encrypted, "abc")
    assert result.value == "a"


def test_decrypt_requires_key():
    with pytest.raises(PasswordDecryptionError):
        decrypt_linkstatus_password("anything", "")
