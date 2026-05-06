from app.services.wordpress_client import WordPressClient


def test_base_url_preserves_www_host():
    client = WordPressClient()
    assert client._base_url("https://www.hetgroeneerf.nl/") == "https://www.hetgroeneerf.nl/"


def test_base_url_adds_scheme_without_stripping_www():
    client = WordPressClient()
    assert client._base_url("www.example.nl") == "https://www.example.nl/"
