from app.services.wordpress_remediation_service import classify_label_preflight


def test_label_76_is_skipped_before_wordpress_login():
    assert classify_label_preflight({12, 76}, jg_label_id=76, expired_label_id=79) == "skipped_jg_label"


def test_label_79_uses_delete_route():
    assert classify_label_preflight({79}, jg_label_id=76, expired_label_id=79) == "deleted_label79"


def test_other_labels_continue_to_wordpress_remediation():
    assert classify_label_preflight({12, 34}, jg_label_id=76, expired_label_id=79) is None
