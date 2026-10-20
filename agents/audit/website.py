"""Bounded, evidence-based HTML audit for publicly accessible business websites."""
from __future__ import annotations

import ipaddress
import http.client
import socket
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any


MAX_HTML_BYTES = 1_000_000
USER_AGENT = "GrowthEngineWebsiteAudit/1.0 (+https://github.com/notbryan4real-blip/ai-business-growth-engine)"


class WebsiteAuditError(RuntimeError):
    """A safe, user-presentable website audit failure."""


def _validate_public_url(url: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise WebsiteAuditError("Enter a valid public http:// or https:// website URL.")
    if parsed.username or parsed.password:
        raise WebsiteAuditError("URLs containing credentials are not allowed.")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise WebsiteAuditError("Local and private network hosts are not allowed.")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    except (socket.gaierror, OSError) as exc:
        raise WebsiteAuditError("The website hostname could not be resolved.") from exc
    if not addresses:
        raise WebsiteAuditError("The website hostname did not resolve to a public address.")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise WebsiteAuditError("The hostname returned an invalid IP address.") from exc
        if not ip.is_global:
            raise WebsiteAuditError("Private, loopback, link-local, and reserved IP addresses are blocked.")
    return parsed


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    max_redirections = 3
    max_repeats = 2

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _connect_public(address, timeout=8, source_address=None, **kwargs):
    """Resolve once, validate every answer, then connect to a literal public IP.

    HTTPSConnection still uses the original hostname for TLS SNI/certificate
    validation. Disabling proxy handlers prevents environment proxy bypasses.
    """
    host, port = address
    answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    ips = list(dict.fromkeys(item[4][0] for item in answers))
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise WebsiteAuditError("Private, loopback, link-local, and reserved IP addresses are blocked.")
    error = None
    for ip in ips:
        try:
            return socket.create_connection((ip, port), timeout, source_address)
        except OSError as exc:
            error = exc
    raise error


class _PublicHTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _connect_public


class _PublicHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _connect_public


class _PublicHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_PublicHTTPConnection, req)


class _PublicHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_PublicHTTPSConnection, req, context=self._context)


class _PageSignals(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.in_title = False
        self.description = ""
        self.viewport = ""
        self.h1_count = 0
        self.form_count = 0
        self.image_count = 0
        self.images_missing_alt = 0
        self.cta_count = 0
        self.anchor_count = 0
        self.button_count = 0
        self._cta_tag: str | None = None
        self._cta_parts: list[str] = []
        self._cta_words = ("call", "quote", "contact", "book", "schedule", "request", "estimate", "get started", "service")

    def handle_starttag(self, tag: str, attrs):
        values = {key.lower(): value or "" for key, value in attrs}
        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            name = values.get("name", "").lower()
            if name == "description":
                self.description = values.get("content", "").strip()
            elif name == "viewport":
                self.viewport = values.get("content", "").strip()
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "form":
            self.form_count += 1
        elif tag == "img":
            self.image_count += 1
            if not values.get("alt", "").strip():
                self.images_missing_alt += 1
        elif tag == "a":
            self.anchor_count += 1
            self._cta_tag = "a"
            self._cta_parts = [values.get("aria-label", ""), values.get("title", "")]
        elif tag == "button":
            self.button_count += 1
            self._cta_tag = "button"
            self._cta_parts = [values.get("aria-label", ""), values.get("title", "")]

    def handle_endtag(self, tag: str):
        if tag == "title":
            self.in_title = False
        if self._cta_tag == tag:
            label = " ".join(self._cta_parts).lower()
            if any(word in label for word in self._cta_words):
                self.cta_count += 1
            self._cta_tag = None
            self._cta_parts = []

    def handle_data(self, data: str):
        if self.in_title:
            self.title_parts.append(data.strip())
        if self._cta_tag:
            self._cta_parts.append(data.strip())

    def result(self, final_url: str, status_code: int, html_bytes: int) -> dict[str, Any]:
        title = " ".join(part for part in self.title_parts if part).strip()[:1000]
        self.description = self.description[:1000]
        self.viewport = self.viewport[:200]
        findings: list[dict[str, str]] = []
        if urllib.parse.urlparse(final_url).scheme != "https":
            findings.append({"severity": "warning", "signal": "https", "detail": "The final page URL does not use HTTPS."})
        if not title:
            findings.append({"severity": "warning", "signal": "title", "detail": "No HTML title was detected."})
        elif len(title) > 60:
            findings.append({"severity": "info", "signal": "title_length", "detail": "The title exceeds 60 characters; review how it appears in search results."})
        if not self.description:
            findings.append({"severity": "warning", "signal": "meta_description", "detail": "No meta description was detected."})
        elif len(self.description) > 160:
            findings.append({"severity": "info", "signal": "meta_description_length", "detail": "The meta description exceeds 160 characters."})
        if not self.viewport:
            findings.append({"severity": "warning", "signal": "mobile_viewport", "detail": "No viewport meta tag was detected."})
        if self.h1_count == 0:
            findings.append({"severity": "warning", "signal": "h1", "detail": "No H1 heading was detected."})
        elif self.h1_count > 1:
            findings.append({"severity": "info", "signal": "multiple_h1", "detail": "Multiple H1 headings were detected; review heading hierarchy."})
        if self.form_count == 0 and self.cta_count == 0:
            findings.append({"severity": "warning", "signal": "conversion_path", "detail": "No form or clearly labeled call-to-action was detected in the downloaded HTML."})
        if self.images_missing_alt:
            findings.append({"severity": "warning", "signal": "image_alt", "detail": f"{self.images_missing_alt} of {self.image_count} image elements lack a non-empty alt attribute."})
        return {
            "status": "completed",
            "final_url": final_url,
            "http_status": status_code,
            "html_bytes_analyzed": html_bytes,
            "signals": {
                "title": title,
                "title_length": len(title),
                "meta_description": self.description,
                "meta_description_length": len(self.description),
                "viewport": self.viewport,
                "h1_count": self.h1_count,
                "form_count": self.form_count,
                "anchor_count": self.anchor_count,
                "button_count": self.button_count,
                "cta_label_count": self.cta_count,
                "image_count": self.image_count,
                "images_missing_alt": self.images_missing_alt,
            },
            "findings": findings,
            "limitations": [
                "This is a bounded static HTML inspection, not a full browser, Lighthouse, accessibility, or SEO certification.",
                "JavaScript-rendered content and authenticated pages may not be visible in the fetched HTML.",
                "A missing signal is a finding about the fetched response only, not proof that a feature is absent from the full website.",
            ],
        }


def audit_website(url: str, timeout: float = 8.0) -> dict[str, Any]:
    """Fetch a public HTML page with SSRF checks and analyze a bounded response."""
    _validate_public_url(url)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        _PublicHTTPHandler(), _PublicHTTPSHandler(), _SafeRedirectHandler())
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = response.geturl()
            _validate_public_url(final_url)
            status_code = response.getcode()
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise WebsiteAuditError("The URL did not return an HTML document.")
            raw = response.read(MAX_HTML_BYTES + 1)
    except WebsiteAuditError:
        raise
    except urllib.error.HTTPError as exc:
        raise WebsiteAuditError(f"The website returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise WebsiteAuditError("The website could not be fetched within the allowed time.") from exc
    if len(raw) > MAX_HTML_BYTES:
        raw = raw[:MAX_HTML_BYTES]
    charset = "utf-8"
    try:
        html = raw.decode(charset, errors="replace")
    except LookupError:
        html = raw.decode("utf-8", errors="replace")
    parser = _PageSignals()
    parser.feed(html)
    parser.close()
    return parser.result(final_url, status_code, len(raw))
