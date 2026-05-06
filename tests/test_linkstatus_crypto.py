import base64

import pytest

from app.utils.linkstatus_crypto import PasswordDecryptionError, decrypt_linkstatus_password


def _xor_base64(secret: str, key: str) -> str:
    data = secret.encode("utf-8")
    key_bytes = key.encode("utf-8")
    encrypted = bytes(byte ^ key_bytes[idx % len(key_bytes)] for idx, byte in enumerate(data))
    return base64.b64encode(encrypted).decode("ascii")


def test_decrypt_xor_base64():
    encrypted = _xor_base64("wp-secret-123", "usmannnn")
    result = decrypt_linkstatus_password(encrypted, "usmannnn")
    assert result.value == "wp-secret-123"
    assert result.method == "xor-base64"


def test_decrypt_base64_plain_text():
    encrypted = base64.b64encode(b"wp-secret").decode("ascii")
    result = decrypt_linkstatus_password(encrypted, "usmannnn")
    assert result.value == "wp-secret"
    assert result.method == "base64"


def test_decrypt_requires_key():
    with pytest.raises(PasswordDecryptionError):
        decrypt_linkstatus_password("anything", "")
