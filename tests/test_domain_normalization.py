from app.utils.domain_normalization import normalize_domain


def test_basic_domain():
    assert normalize_domain("example.com") == "example.com"


def test_https_www_trailing_slash():
    assert normalize_domain("https://www.anieuws.be/") == "anieuws.be"


def test_http_www():
    assert normalize_domain("http://www.example.com") == "example.com"


def test_uppercase():
    assert normalize_domain("EXAMPLE.COM/") == "example.com"


def test_www_only():
    assert normalize_domain("www.example.com") == "example.com"


def test_subdomain_preserved():
    assert normalize_domain("blog.example.com") == "blog.example.com"


def test_trailing_dot():
    assert normalize_domain("example.com.") == "example.com"


def test_empty_string():
    result = normalize_domain("")
    assert isinstance(result, str)
