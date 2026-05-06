from app.services.failed_image_owner_draft_service import (
    build_failed_image_xlsx,
    build_failed_image_owner_drafts,
    summarize_orders_by_domain,
)


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
    assert drafts[0].domain_count == 2
    assert len(drafts[0].body_json["domains"]) == 2
    assert drafts[0].body_json["total_domains"] == 2
    assert "failed_image" in drafts[0].body_html
    assert "example.nl" in drafts[0].body_html
    assert "<th>Website</th><th>Foutmelding</th><th>Aantal orders</th>" in drafts[0].body_html
    assert "Afbeelding uploaden geblokkeerd" in drafts[0].body_html


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


def test_failed_image_drafts_preview_first_50_domains():
    orders = [
        {
            "added_by": 1,
            "order_id": idx,
            "wp_domain": f"https://example{idx}.nl/",
            "label_names": "JG Webmarketing",
        }
        for idx in range(101)
    ]

    drafts = build_failed_image_owner_drafts(orders)

    assert len(drafts) == 1
    assert len(drafts[0].body_json["domains"]) == 50
    assert drafts[0].body_json["total_domains"] == 101
    assert drafts[0].domain_count == 101
    assert drafts[0].subject == "Failed image: 101 domein(en)"


def test_failed_image_orders_summarize_by_domain():
    domains = summarize_orders_by_domain([
        {
            "order_id": 1,
            "wp_domain": "https://www.example.nl/",
            "customer_name": "Klant A",
            "anchor1": "anchor",
            "link1": "https://target.nl/",
            "db": "db1",
            "label_names": "JG Webmarketing",
        },
        {
            "order_id": 2,
            "wp_domain": "http://example.nl",
            "customer_name": "Klant A",
            "anchor1": "anchor2",
            "link1": "https://target2.nl/",
            "db": "db1",
            "label_names": "JG Webmarketing",
        },
    ])

    assert len(domains) == 1
    assert domains[0]["order_count"] == 2
    assert domains[0]["order_ids"] == [1, 2]


def test_failed_image_xlsx_contains_all_domains():
    data = build_failed_image_xlsx([
        {
            "wp_domain": "https://example.nl/",
            "order_count": 2,
            "customer_name": "Klant A",
            "db": "db1",
            "label_names": "JG Webmarketing",
            "order_ids": [1, 2],
        }
    ])

    assert data.startswith(b"PK")
