from app.services.wordpress_remediation_service import classify_label_preflight, group_orders_by_website


def test_label_76_is_skipped_before_wordpress_login():
    assert classify_label_preflight({12, 76}, jg_label_id=76, expired_label_id=79) == "skipped_jg_label"


def test_label_79_uses_delete_route():
    assert classify_label_preflight({79}, jg_label_id=76, expired_label_id=79) == "deleted_label79"


def test_other_labels_continue_to_wordpress_remediation():
    assert classify_label_preflight({12, 34}, jg_label_id=76, expired_label_id=79) is None


def test_group_orders_by_website_collapses_duplicate_domains():
    grouped = group_orders_by_website([
        {
            "order_id": 1,
            "domainId": 10,
            "wp_domain": "https://www.example.nl/",
            "status": "failed_domain",
            "label_ids": {1},
        },
        {
            "order_id": 2,
            "domainId": 10,
            "wp_domain": "http://example.nl",
            "status": "failed_domain_category",
            "label_ids": {2},
        },
    ])

    assert len(grouped) == 1
    assert grouped[0]["order_ids"] == [1, 2]
    assert grouped[0]["order_count"] == 2
    assert grouped[0]["label_ids"] == {1, 2}
    assert grouped[0]["status"] == "failed_domain, failed_domain_category"
