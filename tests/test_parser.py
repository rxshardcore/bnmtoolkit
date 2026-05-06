"""Test the HostingIndustries HTML parser against the real table structure."""

from app.clients.hostingindustries import HostingIndustriesClient

SAMPLE_HTML = """
<html><body>
<div id="topbar">Domainpanel</div>
<div id="contentpanel">
<div class="domains"><table class="table"><thead><tr>
<th>Domeinnaam</th><th>Extensie</th><th>Status</th><th>Houder</th>
<th>Begindatum</th><th>Einddatum</th><th>Acties</th>
</tr></thead><tbody>
<tr><td>mediahertz</td><td>it</td><td>Quarantaine</td><td>Blauwe Monsters B.V.</td><td>31-01-2024</td><td>31-01-2026</td><td></td></tr>
<tr><td>hellocoolstuff</td><td>com</td><td>Expiry</td><td>Blauwe Monsters B.V.</td><td>09-04-2024</td><td>09-04-2026</td><td></td></tr>
<tr><td>eensuccesvolbedrijf</td><td>nl</td><td>Active</td><td>Blauwe Monsters B.V.</td><td>10-02-2022</td><td>01-05-2026</td><td></td></tr>
</tbody></table></div>
</div>
</body></html>
"""


def test_parse_returns_correct_count():
    client = HostingIndustriesClient("", "", "test")
    result = client.parse_domains(SAMPLE_HTML)
    assert len(result) == 3


def test_parse_full_domain():
    client = HostingIndustriesClient("", "", "test")
    result = client.parse_domains(SAMPLE_HTML)
    domains = {r.full_domain for r in result}
    assert "mediahertz.it" in domains
    assert "hellocoolstuff.com" in domains
    assert "eensuccesvolbedrijf.nl" in domains


def test_parse_statuses():
    client = HostingIndustriesClient("", "", "test")
    result = client.parse_domains(SAMPLE_HTML)
    statuses = {r.full_domain: r.status for r in result}
    assert statuses["mediahertz.it"] == "Quarantaine"
    assert statuses["hellocoolstuff.com"] == "Expiry"
    assert statuses["eensuccesvolbedrijf.nl"] == "Active"


def test_parse_dates():
    client = HostingIndustriesClient("", "", "test")
    result = client.parse_domains(SAMPLE_HTML)
    m = next(r for r in result if r.full_domain == "mediahertz.it")
    assert m.start_date == "31-01-2024"
    assert m.end_date == "31-01-2026"


def test_parse_account_name():
    client = HostingIndustriesClient("", "", "myaccount")
    result = client.parse_domains(SAMPLE_HTML)
    assert all(r.account_name == "myaccount" for r in result)


def test_is_login_page_true():
    login_html = '<html><body><div class="login-panel"><form action="login.php"></form></div></body></html>'
    assert HostingIndustriesClient._is_login_page(login_html) is True


def test_is_login_page_false():
    assert HostingIndustriesClient._is_login_page(SAMPLE_HTML) is False
