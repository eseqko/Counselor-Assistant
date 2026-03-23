#!/usr/bin/env python3
"""
Course Catalog Wiki - Standalone Mode
A detachable tool from the Counselor Assistant suite.

No login required. No FERPA protections. Safe to demo and share.
Serves the same catalog files used by the main Counselor Assistant app.

Usage:
    python run_catalog.py

Then open http://127.0.0.1:5001 in your browser.
"""
from flask import Flask, send_from_directory, send_file
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
CATALOG_DIR = os.path.join(BASE_DIR, 'app', 'static', 'course_catalog')

app = Flask(__name__, static_folder=os.path.join(BASE_DIR, 'app', 'static'))


@app.route('/')
def index():
    return send_from_directory(CATALOG_DIR, 'index.html')


@app.route('/editor')
def editor():
    return send_from_directory(CATALOG_DIR, 'editor.html')


@app.route('/setup')
def setup():
    return send_from_directory(CATALOG_DIR, 'setup.html')


# Serve any other static files the catalog pages reference
@app.route('/<path:filename>')
def catalog_files(filename):
    # First check the catalog directory
    catalog_path = os.path.join(CATALOG_DIR, filename)
    if os.path.isfile(catalog_path):
        return send_from_directory(CATALOG_DIR, filename)
    # Fall back to the main static directory (for shared assets)
    return send_from_directory(app.static_folder, filename)


if __name__ == '__main__':
    print()
    print("=" * 60)
    print("  COURSE CATALOG WIKI")
    print("  Standalone Mode")
    print("=" * 60)
    print()
    print("  Part of the Counselor Assistant suite of tools.")
    print("  Running independently - no login required.")
    print()
    print("  Open your browser to: http://127.0.0.1:5001")
    print()
    print("  Pages:")
    print("    Catalog:  http://127.0.0.1:5001/")
    print("    Editor:   http://127.0.0.1:5001/editor")
    print("    Setup:    http://127.0.0.1:5001/setup")
    print()
    print("  Press Ctrl+C to stop the server.")
    print("=" * 60)
    print()
    app.run(host='127.0.0.1', port=5001, debug=True)
