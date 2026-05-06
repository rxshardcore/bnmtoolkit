"""Test configuration loading and CSV parsing."""

import os
import pytest
from app.config import Settings


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Prevent the real .env from leaking into tests."""
    for key in list(os.environ):
        if key.startswith(("HI_", "SOURCE_DB", "AUDIT_DB", "MAILGUN", "ENABLE_", "N8N_")):
            monkeypatch.delenv(key, raising=False)


def test_default_dry_run():
    s = Settings(_env_file=None)
    assert s.dry_run is True


def test_csv_statuses():
    s = Settings(_env_file=None, unusable_domain_statuses="Quarantaine,Expiry,Custom")
    assert s.unusable_statuses_list == ["Quarantaine", "Expiry", "Custom"]


def test_hi_accounts_single():
    s = Settings(_env_file=None, hi_account1_username="user1", hi_account1_password="pass1")
    assert len(s.hi_accounts) == 1
    assert s.hi_accounts[0]["name"] == "primary"


def test_hi_accounts_dual():
    s = Settings(
        _env_file=None,
        hi_account1_username="u1", hi_account1_password="p1",
        hi_account2_username="u2", hi_account2_password="p2",
    )
    assert len(s.hi_accounts) == 2


def test_source_db_urls():
    s = Settings(
        _env_file=None,
        source_db1_host="host1", source_db1_name="db1",
        source_db1_user="u", source_db1_password="p",
        source_db2_host="host2", source_db2_name="db2",
        source_db2_user="u2", source_db2_password="p2",
    )
    assert len(s.source_db_urls) == 2
    assert "db1" in s.source_db_urls[0]["url"]
    assert "db2" in s.source_db_urls[1]["url"]


def test_source_db_single():
    s = Settings(
        _env_file=None,
        source_db1_host="host1", source_db1_name="db1",
        source_db1_user="u", source_db1_password="p",
    )
    assert len(s.source_db_urls) == 1


def test_wordpress_remediation_defaults():
    s = Settings(_env_file=None)
    assert s.jg_label_id == 76
    assert s.expired_label_id == 79
    assert s.wp_failed_statuses_list == ["failed_domain", "failed_domain_category"]
    assert s.wp_plugin_name == "Google Analytics Insertion"
