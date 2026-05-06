"""Discover and fetch WordPress credentials from the first Linkstatus database."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.utils.domain_normalization import normalize_domain

logger = logging.getLogger(__name__)

_IDENT_RE = re.compile(r"^[A-Za-z0-9_]+$")

DOMAIN_HINTS = ("domain", "url", "website", "site")
USERNAME_HINTS = ("username", "user_name", "login", "wp_user", "wp_username")
PASSWORD_HINTS = ("password", "passwd", "pass", "wp_pass", "wp_password")


class CredentialSchemaError(RuntimeError):
    """Raised when WordPress credential columns cannot be discovered safely."""


@dataclass(frozen=True)
class CredentialSchema:
    table_name: str
    domain_column: str
    username_column: str
    password_column: str


@dataclass(frozen=True)
class WordPressCredentials:
    domain: str
    username: str
    encrypted_password: str
    schema: CredentialSchema
    decrypted_password: str | None = None


def _quote_identifier(identifier: str) -> str:
    if not _IDENT_RE.match(identifier):
        raise CredentialSchemaError(f"Unsafe database identifier discovered: {identifier!r}")
    return f"`{identifier}`"


def _score_column(name: str, hints: tuple[str, ...]) -> int:
    lower = name.lower()
    score = 0
    for hint in hints:
        if lower == hint:
            score += 10
        elif lower.endswith(hint) or lower.startswith(hint):
            score += 6
        elif hint in lower:
            score += 3
    if "wordpress" in lower or lower.startswith("wp_"):
        score += 2
    return score


def _best_column(columns: list[str], hints: tuple[str, ...]) -> tuple[str | None, int]:
    scored = sorted(
        ((col, _score_column(col, hints)) for col in columns),
        key=lambda item: item[1],
        reverse=True,
    )
    if not scored or scored[0][1] == 0:
        return None, 0
    return scored[0]


def discover_wordpress_credentials_schema(session: Session) -> CredentialSchema:
    """Find the most likely credentials table using information_schema only."""
    rows = session.execute(text("""
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND data_type IN ('char', 'varchar', 'text', 'mediumtext', 'longtext')
        ORDER BY table_name, ordinal_position
    """)).fetchall()

    columns_by_table: dict[str, list[str]] = {}
    for table_name, column_name in rows:
        columns_by_table.setdefault(str(table_name), []).append(str(column_name))

    candidates: list[tuple[int, CredentialSchema]] = []
    for table_name, columns in columns_by_table.items():
        domain_col, domain_score = _best_column(columns, DOMAIN_HINTS)
        username_col, username_score = _best_column(columns, USERNAME_HINTS)
        password_col, password_score = _best_column(columns, PASSWORD_HINTS)
        if not (domain_col and username_col and password_col):
            continue

        table_score = 0
        lower_table = table_name.lower()
        if "wordpress" in lower_table or lower_table.startswith("wp"):
            table_score += 8
        if "login" in lower_table or "credential" in lower_table or "account" in lower_table:
            table_score += 5
        if "domain" in lower_table:
            table_score += 2

        schema = CredentialSchema(
            table_name=table_name,
            domain_column=domain_col,
            username_column=username_col,
            password_column=password_col,
        )
        candidates.append((table_score + domain_score + username_score + password_score, schema))

    if not candidates:
        raise CredentialSchemaError("No WordPress credential table could be discovered in database 1")

    candidates.sort(key=lambda item: item[0], reverse=True)
    best_score, best_schema = candidates[0]
    tied = [schema for score, schema in candidates if score == best_score]
    if len(tied) > 1:
        names = ", ".join(f"{s.table_name}.{s.username_column}/{s.password_column}" for s in tied)
        raise CredentialSchemaError(f"Ambiguous WordPress credential schema candidates: {names}")

    logger.info(
        "Discovered WordPress credential schema: %s.%s/%s/%s",
        best_schema.table_name,
        best_schema.domain_column,
        best_schema.username_column,
        best_schema.password_column,
    )
    return best_schema


def _domain_variants(domain: str) -> list[str]:
    normalized = normalize_domain(domain)
    variants = {
        normalized,
        f"www.{normalized}",
        f"http://{normalized}",
        f"https://{normalized}",
        f"http://www.{normalized}",
        f"https://www.{normalized}",
        f"http://{normalized}/",
        f"https://{normalized}/",
        f"http://www.{normalized}/",
        f"https://www.{normalized}/",
    }
    return sorted(v for v in variants if v)


def _coerce_secret(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore").strip()
    return str(value).strip()


def get_wordpress_credentials(
    session: Session,
    domain: str,
    schema: CredentialSchema | None = None,
    decryption_key: str = "",
) -> WordPressCredentials | None:
    """Return encrypted WordPress credentials for a domain, if present."""
    schema = schema or discover_wordpress_credentials_schema(session)

    table = _quote_identifier(schema.table_name)
    domain_col = _quote_identifier(schema.domain_column)
    username_col = _quote_identifier(schema.username_column)
    password_col = _quote_identifier(schema.password_column)

    variants = _domain_variants(domain)
    decrypt_select = ""
    if decryption_key:
        decrypt_select = f""",
            CAST(AES_DECRYPT(FROM_BASE64({password_col}), :decryption_key) AS CHAR) AS decrypted_from_base64,
            CAST(AES_DECRYPT({password_col}, :decryption_key) AS CHAR) AS decrypted_raw
        """

    query = text(f"""
        SELECT {domain_col}, {username_col}, {password_col}
            {decrypt_select}
        FROM {table}
        WHERE {domain_col} IN :variants
           OR REPLACE(REPLACE(REPLACE(REPLACE({domain_col}, 'https://', ''), 'http://', ''), 'www.', ''), '/', '') = :normalized
        LIMIT 1
    """).bindparams(
        bindparam("variants", expanding=True, value=variants),
        bindparam("normalized", value=normalize_domain(domain)),
    )
    if decryption_key:
        query = query.bindparams(bindparam("decryption_key", value=decryption_key))

    row = session.execute(query).first()
    if not row:
        return None

    username = _coerce_secret(row[1])
    encrypted_password = _coerce_secret(row[2])
    if not username or not encrypted_password:
        return None

    decrypted_password = None
    if decryption_key and len(row) >= 5:
        decrypted_password = _coerce_secret(row[3]) or _coerce_secret(row[4]) or None

    return WordPressCredentials(
        domain=_coerce_secret(row[0]) or domain,
        username=username,
        encrypted_password=encrypted_password,
        schema=schema,
        decrypted_password=decrypted_password,
    )
