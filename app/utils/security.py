"""Security helpers: SSRF URL validation, CSV formula-injection neutralization,
and safe static-file responses.

This app is FERPA-scoped and promises "local-only, no external connections."
These helpers enforce that promise on the few surfaces that take user-supplied
URLs or echo user-supplied data into spreadsheets / served files.
"""
import ipaddress
import socket
from urllib.parse import urlparse

from flask import send_file

# Tailscale CGNAT range — a legitimate place a counselor would run Ollama on
# another of their own devices. Allowed alongside loopback + RFC-1918.
_TAILSCALE_CGNAT = ipaddress.ip_network('100.64.0.0/10')


def validate_local_url(url, allow_schemes=('http', 'https')):
    """Validate that a user-supplied URL points at a local/private host.

    Returns (True, normalized_url) when safe, else (False, error_message).

    Blocks SSRF to public hosts and to cloud metadata endpoints
    (169.254.169.254 etc.) while still allowing localhost, private LANs, and
    the Tailscale CGNAT range — the only places the AI server should ever be.
    """
    if not url or not url.strip():
        return False, 'A URL is required.'
    parsed = urlparse(url.strip())
    if parsed.scheme not in allow_schemes:
        return False, 'URL must start with http:// or https://.'
    if parsed.username or parsed.password:
        return False, 'Credentials embedded in the URL are not allowed.'
    host = parsed.hostname
    if not host:
        return False, 'URL has no host.'

    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False, f'Could not resolve host "{host}".'
    addrs = {info[4][0] for info in infos}
    if not addrs:
        return False, f'Could not resolve host "{host}".'

    for addr in addrs:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False, 'Invalid host address.'
        # Reject link-local first: 169.254.0.0/16 covers the cloud-metadata IP.
        if ip.is_link_local:
            return False, 'Link-local addresses (including cloud metadata) are not allowed.'
        is_tailscale = ip.version == 4 and ip in _TAILSCALE_CGNAT
        if not (ip.is_loopback or ip.is_private or is_tailscale):
            return False, (
                'For FERPA safety the AI server must be a local or private-network '
                'address (e.g. localhost, 10.x, 172.16-31.x, 192.168.x, or your '
                'Tailscale IP). Public hosts are not allowed.'
            )
    return True, url.strip().rstrip('/')


def validate_external_url(url, allow_schemes=('http', 'https')):
    """SSRF guard for a URL the SERVER will fetch from the public internet.

    The inverse of validate_local_url: an external calendar feed is *supposed*
    to live on a public host (calendar.google.com), so the local/private
    allowlist would reject every legitimate URL. What must be blocked here is
    the server being pointed at something only it can reach — the cloud
    metadata endpoint, localhost, or the LAN/tailnet — and having the response
    handed back through the parser.

    Call this immediately before each fetch, not only when the URL is saved:
    validating at save time alone leaves DNS rebinding wide open, since the
    name can resolve to a public IP then and an internal one later.

    Returns (ok, url_or_error_message).
    """
    if not url or not url.strip():
        return False, 'A URL is required.'
    parsed = urlparse(url.strip())
    if parsed.scheme not in allow_schemes:
        return False, 'URL must start with http:// or https://.'
    if parsed.username or parsed.password:
        return False, 'Credentials embedded in the URL are not allowed.'
    host = parsed.hostname
    if not host:
        return False, 'URL has no host.'

    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False, f'Could not resolve host "{host}".'
    addrs = {info[4][0] for info in infos}
    if not addrs:
        return False, f'Could not resolve host "{host}".'

    # EVERY resolved address must be public — a name resolving to both a public
    # and an internal address must not slip through on the public one.
    for addr in addrs:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False, 'Invalid host address.'
        is_tailscale = ip.version == 4 and ip in _TAILSCALE_CGNAT
        if (ip.is_loopback or ip.is_private or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or is_tailscale):
            return False, (
                'That address is on this machine or your private network. An '
                'external calendar URL must point at a public host (for example '
                'the "Secret address in iCal format" from Google Calendar).'
            )
    return True, url.strip()


# Characters that trigger formula evaluation when a cell is opened in Excel /
# Google Sheets / LibreOffice.
_CSV_DANGEROUS_PREFIXES = ('=', '+', '-', '@', '\t', '\r')


def csv_safe(value):
    """Neutralize spreadsheet formula injection for a single CSV/Excel cell.

    Prefixes a leading formula trigger with an apostrophe so the spreadsheet
    treats the cell as text. Returns '' for None.
    """
    if value is None:
        return ''
    s = str(value)
    if s and s[0] in _CSV_DANGEROUS_PREFIXES:
        return "'" + s
    return s


def xlsx_safe(value):
    """csv_safe for a spreadsheet cell, preserving non-text cell types.

    csv_safe() str()s everything, which would turn grade_level 10 into the
    text "10" and break sorting/filtering in the exported workbook. Only
    strings can carry a formula trigger, so only strings need neutralizing —
    ints, floats, dates and None pass through as native cell values.
    """
    return csv_safe(value) if isinstance(value, str) else value


def safe_logo_response(path):
    """Serve an uploaded logo with headers that neutralize SVG-borne XSS.

    School logos may be SVG (scalable crest). An SVG served inline can run
    embedded <script> when navigated to directly. The `sandbox` CSP directive
    disables script execution while still rendering the image inside an <img>,
    so legitimate logos keep working.
    """
    resp = send_file(path)
    resp.headers['Content-Security-Policy'] = (
        "sandbox; default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'"
    )
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp
