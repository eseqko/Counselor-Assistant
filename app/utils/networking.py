"""Network-source ACL helpers for the launcher (run.py).

Lives in app/utils/ rather than run.py itself so the predicate is importable
into the test suite without spinning up a second Flask app.
"""
import ipaddress

# Tailscale assigns node IPs from the CGNAT range RFC 6598 reserves for
# carrier-grade NAT — 100.64.0.0/10 (i.e. 100.64.0.0 through 100.127.255.255).
# Note: a naive ``startswith('100.')`` check matches addresses like 100.1.2.3
# which are PUBLIC (Google-owned at time of writing), not tailnet — the
# previous implementation would have admitted those over the LAN. Restrict to
# the actual CGNAT block.
_TAILSCALE_CGNAT = ipaddress.ip_network('100.64.0.0/10')


def is_tailnet_or_localhost(remote_addr):
    """Return True if ``remote_addr`` is loopback or in Tailscale's CGNAT range.

    Used by the launcher's @before_request guard to allow only tailnet + local
    traffic when the server is bound to 0.0.0.0 because Tailscale was detected.
    Tolerates empty/None and IPv6-mapped-IPv4 (``::ffff:127.0.0.1``).
    """
    if not remote_addr:
        return False
    try:
        ip = ipaddress.ip_address(remote_addr)
    except ValueError:
        return False
    # ::1 and 127.0.0.0/8 — also catches IPv6-mapped loopbacks.
    if ip.is_loopback:
        return True
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.version == 4 and ip in _TAILSCALE_CGNAT
