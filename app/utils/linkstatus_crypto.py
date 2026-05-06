"""Decrypt Linkstatus WordPress passwords."""

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


def decrypt_linkstatus_password(encrypted_value: str, key: str) -> DecryptedPassword:
    """Decrypt a WordPress password from Linkstatus.

    Linkstatus stores the password as base64 text. After decoding, each
    latin-1 character is shifted back by the corresponding key character.
    The original scheme uses key[i % len(key) - 1], so the first character
    uses the final key character, then key character 0, 1, 2, and so on.
    """
    value = (encrypted_value or "").strip()
    if not value:
        raise PasswordDecryptionError("Encrypted password is empty")
    if not key:
        raise PasswordDecryptionError("LINKSTATUS_DECRYPTION_KEY is not configured")

    decoded = _decode_base64(value)
    if decoded is None:
        raise PasswordDecryptionError("Password is not valid base64")

    decoded_string = decoded.decode("latin-1")
    decrypted = ""
    for idx, char in enumerate(decoded_string):
        key_char = key[idx % len(key) - 1]
        decrypted += chr(ord(char) - ord(key_char))

    if _is_printable_secret(decrypted):
        return DecryptedPassword(decrypted, "linkstatus-shift")

    raise PasswordDecryptionError("Unsupported encrypted password format")
