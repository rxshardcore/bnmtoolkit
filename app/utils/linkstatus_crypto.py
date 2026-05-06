"""Decrypt Linkstatus WordPress passwords.

The legacy database stores encrypted WordPress passwords, but deployments have
used more than one lightweight encoding format over time. This helper keeps the
supported formats explicit and fails closed when a value cannot be decoded.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import string


class PasswordDecryptionError(ValueError):
    """Raised when an encrypted Linkstatus password cannot be decrypted."""


@dataclass(frozen=True)
class DecryptedPassword:
    value: str
    method: str


def _is_printable_secret(value: str) -> bool:
    if not value:
        return False
    allowed = set(string.printable)
    return all(ch in allowed for ch in value) and not any(ch in value for ch in "\r\n\t")


def _decode_base64(value: str) -> bytes | None:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return None


def _xor_with_key(data: bytes, key: str) -> bytes:
    key_bytes = key.encode("utf-8")
    return bytes(byte ^ key_bytes[idx % len(key_bytes)] for idx, byte in enumerate(data))


def decrypt_linkstatus_password(encrypted_value: str, key: str) -> DecryptedPassword:
    """Decrypt a WordPress password from Linkstatus.

    Supported formats:
    - `xor-base64`: base64 of bytes XORed with the configured key.
    - `base64`: plain base64 encoded password.
    - `plain`: accepted only for non-base64 values, mainly for legacy rows.
    """
    value = (encrypted_value or "").strip()
    if not value:
        raise PasswordDecryptionError("Encrypted password is empty")
    if not key:
        raise PasswordDecryptionError("LINKSTATUS_DECRYPTION_KEY is not configured")

    decoded = _decode_base64(value)
    if decoded is not None:
        xored = _xor_with_key(decoded, key)
        try:
            candidate = xored.decode("utf-8")
        except UnicodeDecodeError:
            candidate = ""
        if _is_printable_secret(candidate):
            return DecryptedPassword(candidate, "xor-base64")

        try:
            candidate = decoded.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PasswordDecryptionError("Unsupported encrypted password format") from exc
        if _is_printable_secret(candidate):
            return DecryptedPassword(candidate, "base64")

    if _is_printable_secret(value):
        return DecryptedPassword(value, "plain")

    raise PasswordDecryptionError("Unsupported encrypted password format")
