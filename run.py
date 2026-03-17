#!/usr/bin/env python3
"""
Counselor Assistant - All-in-One School Counselor Management Tool
100% Local - FERPA & ASCA Compliant - No Cloud Dependencies

Usage:
    python run.py

Default login:
    Username: counselor
    Password: changeme
    (Change your password immediately after first login)
"""
from app import create_app

app = create_app()

if __name__ == '__main__':
    print()
    print("=" * 60)
    print("  COUNSELOR ASSISTANT")
    print("  All-in-One School Counselor Management Tool")
    print("=" * 60)
    print()
    print("  FERPA Compliant - Local Network Only")
    print()
    print("  Open your browser to: http://127.0.0.1:5000")
    print()
    # Show local network IP for device linking
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
        print(f"  From other devices: http://{local_ip}:5000")
        print()
    except Exception:
        pass
    print("  Default Login:")
    print("    Username: counselor")
    print("    Password: changeme")
    print()
    print("  Press Ctrl+C to stop the server.")
    print("=" * 60)
    print()
    app.run(host='0.0.0.0', port=5000, debug=True)
