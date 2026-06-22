"""Tests for the launcher's tailnet/localhost ACL predicate (app.utils.networking).

The guard runs at every request when Tailscale is detected at startup, blocking
non-tailnet traffic with 403. Until this file, the predicate had no coverage —
and the predicate it replaced silently admitted any 100.x.x.x address, including
public IPs outside the actual Tailscale CGNAT (100.64.0.0/10).
"""
from app.utils.networking import is_tailnet_or_localhost


def test_allows_ipv4_loopback():
    assert is_tailnet_or_localhost('127.0.0.1') is True
    assert is_tailnet_or_localhost('127.1.2.3') is True


def test_allows_ipv6_loopback():
    assert is_tailnet_or_localhost('::1') is True


def test_allows_tailscale_cgnat_range():
    # Boundaries + the user's reported PC tailnet IP.
    assert is_tailnet_or_localhost('100.64.0.0') is True
    assert is_tailnet_or_localhost('100.64.0.1') is True
    assert is_tailnet_or_localhost('100.106.193.90') is True
    assert is_tailnet_or_localhost('100.127.255.255') is True


def test_rejects_100_dot_outside_cgnat():
    """The previous startswith('100.') check would have admitted these — they're
    PUBLIC, not tailnet, so they MUST be rejected on a 0.0.0.0-bound server."""
    assert is_tailnet_or_localhost('100.0.0.0') is False
    assert is_tailnet_or_localhost('100.1.2.3') is False
    assert is_tailnet_or_localhost('100.63.255.255') is False   # one below CGNAT
    assert is_tailnet_or_localhost('100.128.0.0') is False      # one above CGNAT
    assert is_tailnet_or_localhost('100.255.255.255') is False


def test_rejects_private_lan_ranges():
    # The exact source IP from the user's screenshot — phone on Wi-Fi, not VPN.
    assert is_tailnet_or_localhost('10.14.0.61') is False
    assert is_tailnet_or_localhost('192.168.1.1') is False
    assert is_tailnet_or_localhost('172.16.0.1') is False


def test_rejects_public():
    assert is_tailnet_or_localhost('8.8.8.8') is False
    assert is_tailnet_or_localhost('1.1.1.1') is False


def test_tolerates_garbage():
    assert is_tailnet_or_localhost('') is False
    assert is_tailnet_or_localhost(None) is False
    assert is_tailnet_or_localhost('not-an-ip') is False
    assert is_tailnet_or_localhost('999.999.999.999') is False


def test_handles_ipv6_mapped_ipv4():
    """Some proxies/Werkzeug versions report IPv4 sources as ::ffff:127.0.0.1.
    The guard must treat those the same as their IPv4 form."""
    assert is_tailnet_or_localhost('::ffff:127.0.0.1') is True
    assert is_tailnet_or_localhost('::ffff:100.106.193.90') is True
    assert is_tailnet_or_localhost('::ffff:10.14.0.61') is False
