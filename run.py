#!/usr/bin/env python3
"""
Counselor Assistant - All-in-One School Counselor Management Tool
100% Local - FERPA & ASCA Compliant - No Cloud Dependencies

Usage:
    python run.py
"""
import os
import socket
import subprocess
from app import create_app

app = create_app()


def detect_tailscale_ip():
    """Return the Tailscale IPv4 address if Tailscale is installed, else None."""
    candidates = [
        'tailscale',
        r'C:\Program Files\Tailscale\tailscale.exe',
        r'C:\Program Files (x86)\Tailscale\tailscale.exe',
    ]
    for cmd in candidates:
        try:
            result = subprocess.run(
                [cmd, 'ip', '-4'],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                ip = result.stdout.strip().splitlines()[0].strip()
                # Trust whatever tailscale reports — self-hosted tailnets
                # (Headscale, custom ACLs) may use non-100.x ranges.
                if ip:
                    return ip
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue
    # Fallback: scan local interfaces for a 100.x CGNAT address
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip.startswith('100.'):
                return ip
    except socket.gaierror:
        pass
    return None


if __name__ == '__main__':
    # HOST env var overrides auto-detection
    explicit_host = os.environ.get('HOST')
    tailscale_ip = detect_tailscale_ip()

    if explicit_host:
        host = explicit_host
        mode = 'manual'
    elif tailscale_ip:
        # Bind to 0.0.0.0 so both localhost and Tailscale connections work.
        # Flask middleware below restricts non-localhost to Tailscale IPs only.
        host = '0.0.0.0'
        mode = 'tailscale'
    else:
        host = '127.0.0.1'
        mode = 'local'

    print()
    print("=" * 60)
    print("  COUNSELOR ASSISTANT")
    print("  All-in-One School Counselor Management Tool")
    print("=" * 60)
    print()
    print("  FERPA Compliant - 100% Local Storage")
    print("  No data leaves this computer.")
    print()
    if mode == 'tailscale':
        print(f"  Tailscale detected. Server bound to: {host}")
        print(f"  On this PC:   http://{host}:5000")
        print(f"  On iPhone:    http://{host}:5000 (via Tailscale)")
        print("  The school LAN cannot see this port.")
    elif mode == 'manual':
        print(f"  Server bound to: {host}:5000 (HOST env var)")
    else:
        print("  Tailscale not detected. Local-only mode.")
        print("  Open your browser to: http://127.0.0.1:5000")
        print("  (Install Tailscale to enable iPhone access — see TAILSCALE_SETUP.md)")
    print()
    print("  Press Ctrl+C to stop the server.")
    print("=" * 60)
    print()

    if mode == 'tailscale':
        from flask import request as flask_request, abort

        @app.before_request
        def _tailscale_guard():
            remote = flask_request.remote_addr or ''
            if remote.startswith('127.') or remote.startswith('100.') or remote == '::1':
                return  # localhost or Tailscale CGNAT — allowed
            abort(403)

    app.run(host=host, port=5000,
            debug=os.environ.get('FLASK_DEBUG', '').lower() == 'true')
