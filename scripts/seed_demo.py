#!/usr/bin/env python3
"""CLI: wipe and re-seed the demo dataset.

Useful during development of the seed JSON. Equivalent to clicking the
"Reset Demo" button in the UI, but doesn't require the server to be running.

Usage:
    COUNSELOR_DEMO=1 COUNSELOR_DATA_DIR=/tmp/ca-demo python scripts/seed_demo.py
"""
import os
import sys

# Make the parent (project root) importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Force demo flag so the app's create_app picks it up
os.environ['COUNSELOR_DEMO'] = '1'

from app import create_app  # noqa: E402
from app.utils.demo_seed import reset_and_reseed  # noqa: E402


def main():
    app = create_app()
    reset_and_reseed(app)
    print("Demo data reset and re-seeded.")
    print(f"  COUNSELOR_DATA_DIR = {os.environ.get('COUNSELOR_DATA_DIR') or '(default: ./data)'}")


if __name__ == '__main__':
    main()
