#!/usr/bin/env python3
"""
Counselor Assistant - All-in-One School Counselor Management Tool
100% Local - FERPA & ASCA Compliant - No Cloud Dependencies

Usage:
    python run.py
"""
import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    print()
    print("=" * 60)
    print("  COUNSELOR ASSISTANT")
    print("  All-in-One School Counselor Management Tool")
    print("=" * 60)
    print()
    print("  FERPA Compliant - 100% Local Storage")
    print("  No data leaves this computer.")
    print()
    print("  Open your browser to: http://127.0.0.1:5000")
    print()
    print("  Press Ctrl+C to stop the server.")
    print("=" * 60)
    print()
    app.run(host='127.0.0.1', port=5000,
            debug=os.environ.get('FLASK_DEBUG', '').lower() == 'true')
