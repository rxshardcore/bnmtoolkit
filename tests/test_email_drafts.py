"""Test email draft generation and grouping logic."""

from app.services.email_draft_service import build_drafts


def _make_orders():
    return [
        {
            "order_id": 1, "added_on": "2025-01-01", "delivery_date": "2025-02-01",
            "wp_domain": "example.nl", "customer_name": "Klant A", "order_status": "failed_domain",
            "added_by": 10, "addedby_name": "Jan", "addedby_email": "jan@test.nl",
            "anchor1": "a1", "anchor2": "", "anchor3": "", "link1": "http://a.nl",
            "link2": "", "link3": "",
        },
        {
            "order_id": 2, "added_on": "2025-01-05", "delivery_date": "2025-02-10",
            "wp_domain": "ander.nl", "customer_name": "Klant B", "order_status": "peding",
            "added_by": 10, "addedby_name": "Jan", "addedby_email": "jan@test.nl",
            "anchor1": "b1", "anchor2": "", "anchor3": "", "link1": "http://b.nl",
            "link2": "", "link3": "",
        },
        {
            "order_id": 3, "added_on": "2025-01-10", "delivery_date": "2025-03-01",
            "wp_domain": "derde.be", "customer_name": "Klant C", "order_status": "failed_image",
            "added_by": 20, "addedby_name": "Piet", "addedby_email": "piet@test.nl",
            "anchor1": "c1", "anchor2": "", "anchor3": "", "link1": "http://c.nl",
            "link2": "", "link3": "",
        },
    ]


def test_grouping_by_admin():
    drafts = build_drafts(_make_orders(), dry_run=True)
    assert len(drafts) == 2


def test_order_count():
    drafts = build_drafts(_make_orders(), dry_run=True)
    jan_draft = next(d for d in drafts if d.admin_email == "jan@test.nl")
    assert jan_draft.order_count == 2


def test_html_contains_domain():
    drafts = build_drafts(_make_orders(), dry_run=True)
    jan_draft = next(d for d in drafts if d.admin_email == "jan@test.nl")
    assert "example.nl" in jan_draft.body_html


def test_dry_run_notice():
    drafts = build_drafts(_make_orders(), dry_run=True)
    for d in drafts:
        assert "DRY-RUN" in d.body_html


def test_no_dry_run_notice():
    drafts = build_drafts(_make_orders(), dry_run=False)
    for d in drafts:
        assert "DRY-RUN" not in d.body_html


def test_dutch_copy():
    drafts = build_drafts(_make_orders(), dry_run=False)
    html = drafts[0].body_html
    assert "verlopen" in html
    assert "ander domein" in html
    assert "Zodra je vervangende domeinen" in html


def test_signature_present():
    drafts = build_drafts(_make_orders(), dry_run=False)
    assert "Ruben van Melsen" in drafts[0].body_html
    assert "blauwemonsters.nl" in drafts[0].body_html


def test_subject():
    drafts = build_drafts(_make_orders(), dry_run=True)
    jan_draft = next(d for d in drafts if d.admin_email == "jan@test.nl")
    assert "Actie nodig" in jan_draft.subject
    assert "2 order(s)" in jan_draft.subject
