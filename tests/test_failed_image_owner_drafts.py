from app.services.failed_image_owner_draft_service import build_failed_image_owner_drafts


def test_failed_image_drafts_route_default_supplier_to_stefan():
    drafts = build_failed_image_owner_drafts([
        {
            "added_by": 1,
            "order_id": 10,
            "wp_domain": "https://example.nl/",
            "customer_name": "Klant A",
            "status": "failed_image",
            "added_on": "2026-01-01",
            "delivery_date": "2026-01-02",
            "anchor1": "anchor",
            "link1": "https://target.nl/",
            "db": "linkstatus_blauwemonsters",
            "label_names": "",
        },
        {
            "added_by": 1,
            "order_id": 11,
            "wp_domain": "https://example2.nl/",
            "customer_name": "Klant B",
            "status": "failed_image",
            "added_on": "2026-01-03",
            "delivery_date": "2026-01-04",
            "anchor1": "anchor2",
            "link1": "https://target2.nl/",
            "db": "linkstatus_blauwemonsters",
            "label_names": "",
        },
    ])

    assert len(drafts) == 1
    assert drafts[0].recipient_email == "stefan@hostingindustries.nl"
    assert drafts[0].order_count == 2
    assert "failed_image" in drafts[0].body_html
    assert "example.nl" in drafts[0].body_html


def test_failed_image_drafts_route_jg_labels_to_hugo():
    drafts = build_failed_image_owner_drafts([
        {
            "added_by": 1,
            "order_id": 10,
            "wp_domain": "https://example.nl/",
            "label_names": "JG Webmarketing",
        }
    ])

    assert len(drafts) == 1
    assert drafts[0].recipient_email == "hugo@jgwebmarketing.nl"
