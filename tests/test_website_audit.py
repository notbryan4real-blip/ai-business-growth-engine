from email.message import Message
from unittest.mock import patch

import pytest

from agents.audit.website import WebsiteAuditError, audit_website, _connect_public


class FakeResponse:
    def __init__(self, html, url="https://example.com/"):
        self.raw = html.encode("utf-8")
        self.url = url
        self.headers = Message()
        self.headers["Content-Type"] = "text/html; charset=utf-8"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return self.url

    def getcode(self):
        return 200

    def read(self, size=-1):
        return self.raw if size < 0 else self.raw[:size]


class FakeOpener:
    def __init__(self, response):
        self.response = response

    def open(self, request, timeout):
        return self.response


def _public_dns(*args, **kwargs):
    return [(None, None, None, None, ("8.8.8.8", 0))]


def test_audit_extracts_observable_html_signals_without_claiming_full_site_coverage():
    html = """<!doctype html><html><head><title>Example Plumbing</title>
    <meta name="description" content="Reliable local plumbing service for homes and businesses.">
    <meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body><h1>Plumbing help</h1><a href="/contact">Contact us</a>
    <img src="/hero.jpg"><form></form></body></html>"""
    response = FakeResponse(html)
    with patch("socket.getaddrinfo", side_effect=_public_dns), patch(
        "urllib.request.build_opener", return_value=FakeOpener(response)
    ):
        result = audit_website("https://example.com")

    assert result["status"] == "completed"
    assert result["signals"]["title"] == "Example Plumbing"
    assert result["signals"]["viewport"]
    assert result["signals"]["h1_count"] == 1
    assert result["signals"]["form_count"] == 1
    assert result["signals"]["images_missing_alt"] == 1
    assert any(item["signal"] == "image_alt" for item in result["findings"])
    assert "not a full browser" in result["limitations"][0]


def test_audit_blocks_loopback_before_fetching():
    with pytest.raises(WebsiteAuditError, match="Private, loopback"):
        audit_website("http://127.0.0.1/admin")


def test_audit_blocks_private_dns_results():
    private_dns = lambda *args, **kwargs: [(None, None, None, None, ("192.168.1.5", 0))]
    with patch("socket.getaddrinfo", side_effect=private_dns):
        with pytest.raises(WebsiteAuditError, match="Private"):
            audit_website("https://example.com")


def test_audit_rejects_non_html_responses():
    response = FakeResponse("not html")
    response.headers.replace_header("Content-Type", "application/json")
    with patch("socket.getaddrinfo", side_effect=_public_dns), patch(
        "urllib.request.build_opener", return_value=FakeOpener(response)
    ):
        with pytest.raises(WebsiteAuditError, match="did not return an HTML"):
            audit_website("https://example.com")


def test_dns_rebinding_cannot_connect_to_a_private_address():
    private_dns = [(None, None, None, None, ("127.0.0.1", 443))]
    with patch("socket.getaddrinfo", return_value=private_dns), patch("socket.create_connection") as connect:
        with pytest.raises(WebsiteAuditError, match="Private"):
            _connect_public(("example.com", 443))
        connect.assert_not_called()


def test_connection_uses_validated_ip_instead_of_resolving_hostname_again():
    with patch("socket.getaddrinfo", side_effect=_public_dns), patch("socket.create_connection") as connect:
        _connect_public(("example.com", 443), timeout=8)
        connect.assert_called_once_with(("8.8.8.8", 443), 8, None)
