#!/usr/bin/env python3
"""Build the USB-distributable Counselor Assistant demo bundle.

Produces a directory tree that drops onto an exFAT-formatted USB stick
and runs offline on Windows, Mac (Apple Silicon), and Linux x86_64 — no
pre-installed Python required.

Usage:
    python3 scripts/build_usb_bundle.py --output dist/usb-bundle
    python3 scripts/build_usb_bundle.py --output dist/usb-bundle --skip-runtimes
    python3 scripts/build_usb_bundle.py --output dist/usb-bundle --clean

The build runs on a single Linux developer box. python-build-standalone
ships per-platform tarballs and PyPI ships prebuilt wheels for every
package in requirements-demo.txt — so no cross-compilation, no build
matrix, no Docker.

Output layout:
    <output>/
        START_HERE_Windows.bat
        START_HERE_Mac.command
        START_HERE_Linux.sh
        README_FIRST.txt
        runtimes/{windows,macos,linux}/python/...
        runtimes/{windows,macos,linux}/site-packages/...
        Counselor-Assistant/run.py + app/ + data/demo-seed.json
"""
import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path


# Pin a known-good python-build-standalone release. Update by browsing
# https://github.com/astral-sh/python-build-standalone/releases — pick the
# tag, copy the tarball name pattern (the date suffix). Triples below.
PBS_RELEASE = '20260504'
PBS_PYTHON = '3.12.13'  # ship the 3.12.x line for ABI stability

PLATFORMS = {
    'windows': {
        'pbs_triple': 'x86_64-pc-windows-msvc',
        'pip_platform': 'win_amd64',
        'python_exe': 'python/python.exe',
        'launcher': 'START_HERE_Windows.bat',
    },
    'macos': {
        'pbs_triple': 'aarch64-apple-darwin',
        'pip_platform': 'macosx_11_0_arm64',
        'python_exe': 'python/bin/python3',
        'launcher': 'START_HERE_Mac.command',
    },
    'linux': {
        'pbs_triple': 'x86_64-unknown-linux-gnu',
        'pip_platform': 'manylinux2014_x86_64',
        'python_exe': 'python/bin/python3',
        'launcher': 'START_HERE_Linux.sh',
    },
}

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_ROOT = REPO_ROOT / '.bundle-cache'

# What to copy from the app directory. Everything else is excluded.
APP_INCLUDES = ['app', 'config.py', 'run.py']
APP_EXCLUDES_REL = {'__pycache__', 'venv', '.venv', 'instance', '.git'}


def log(stage, msg):
    print(f'[{stage}] {msg}', flush=True)


def download(url, dest, retries=4):
    """Download with exponential-backoff retry."""
    if dest.exists():
        log('cache', f'{dest.name} already cached')
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    delay = 2
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            log('download', f'{url}  →  {dest}')
            with urllib.request.urlopen(url, timeout=60) as resp:
                with open(dest, 'wb') as f:
                    shutil.copyfileobj(resp, f)
            return
        except Exception as e:
            last_err = e
            log('retry', f'attempt {attempt}/{retries} failed: {e}; sleeping {delay}s')
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f'download failed after {retries} attempts: {url} ({last_err})')


def fetch_pbs(platform):
    """Download the python-build-standalone tarball for one platform.

    Uses the install_only_stripped variant — drops debug symbols (saves
    ~600 MB on Linux, smaller savings on Windows/Mac). Functionality is
    identical to the full install_only variant for our use.
    """
    triple = PLATFORMS[platform]['pbs_triple']
    fname = f'cpython-{PBS_PYTHON}+{PBS_RELEASE}-{triple}-install_only_stripped.tar.gz'
    url = (
        f'https://github.com/astral-sh/python-build-standalone/releases/download/'
        f'{PBS_RELEASE}/{fname}'
    )
    cache = CACHE_ROOT / 'pbs' / fname
    download(url, cache)
    return cache


def extract_pbs(tarball, dest_dir):
    """Extract a PBS tarball to ``dest_dir/python``. Tarball top-level dir is 'python'."""
    if (dest_dir / 'python').exists():
        log('extract', f'{dest_dir}/python already extracted')
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    log('extract', f'{tarball.name} → {dest_dir}/python')
    with tarfile.open(tarball, 'r:gz') as tf:
        tf.extractall(dest_dir)


def fetch_wheels(platform, requirements_file):
    """Download platform-specific wheels for every dep in requirements-demo.txt."""
    cache = CACHE_ROOT / 'wheels' / platform
    cache.mkdir(parents=True, exist_ok=True)
    plat = PLATFORMS[platform]['pip_platform']
    log('wheels', f'fetching wheels for {platform} ({plat})')
    cmd = [
        sys.executable, '-m', 'pip', 'download',
        '-r', str(requirements_file),
        '--platform', plat,
        '--python-version', PBS_PYTHON.rsplit('.', 1)[0],  # e.g. "3.12"
        '--only-binary=:all:',
        '--implementation', 'cp',
        '-d', str(cache),
        '--quiet', '--disable-pip-version-check',
    ]
    subprocess.run(cmd, check=True)


def install_wheels(platform, runtime_dir, requirements_file):
    """Install wheels from the cache into runtime_dir/site-packages.

    The build host's Python differs from the target's, so we pass
    --platform/--python-version/--implementation to make pip resolve the
    cache wheels for the TARGET. --no-index forces resolution from the
    local cache only — transitive deps were already pulled by
    fetch_wheels().
    """
    site_packages = runtime_dir / 'site-packages'
    if site_packages.exists():
        shutil.rmtree(site_packages)
    site_packages.mkdir(parents=True)
    cache = CACHE_ROOT / 'wheels' / platform
    plat = PLATFORMS[platform]['pip_platform']
    log('install', f'installing into {site_packages}')
    cmd = [
        sys.executable, '-m', 'pip', 'install',
        '-r', str(requirements_file),
        '--target', str(site_packages),
        '--platform', plat,
        '--python-version', PBS_PYTHON.rsplit('.', 1)[0],
        '--implementation', 'cp',
        '--only-binary=:all:',
        '--no-index', '--find-links', str(cache),
        '--quiet', '--disable-pip-version-check',
    ]
    subprocess.run(cmd, check=True)


def copy_app(output):
    """Copy the app source into output/Counselor-Assistant/, excluding caches and runtime data."""
    dest = output / 'Counselor-Assistant'
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    log('copy', f'app source → {dest}')

    for name in APP_INCLUDES:
        src = REPO_ROOT / name
        target = dest / name
        if src.is_dir():
            shutil.copytree(
                src, target,
                ignore=shutil.ignore_patterns(*APP_EXCLUDES_REL, '*.pyc'),
            )
        else:
            shutil.copy2(src, target)

    # Bring along just the demo seed (the canonical fixture). Everything
    # else under data/ — counselor.db, uploads, backups — is excluded.
    seed_src = REPO_ROOT / 'data' / 'demo-seed.json'
    if not seed_src.exists():
        raise RuntimeError(
            'data/demo-seed.json is missing — did the demo seed get committed? '
            'Run from a clean checkout that includes the file.'
        )
    seed_dest_dir = dest / 'data'
    seed_dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(seed_src, seed_dest_dir / 'demo-seed.json')


WINDOWS_LAUNCHER = r"""@echo off
title Counselor Assistant - Demo
cd /d "%~dp0"
set COUNSELOR_DEMO=1
set COUNSELOR_DATA_DIR=%USERPROFILE%\CounselorAssistantDemo
set PYTHONPATH=%~dp0runtimes\windows\site-packages
echo.
echo  Starting Counselor Assistant Demo...
echo  Your browser will open in a moment.
echo.
echo  To stop the demo: close this window.
echo.
cd /d "%~dp0Counselor-Assistant"
"%~dp0runtimes\windows\python\python.exe" run.py
pause
"""

MAC_LAUNCHER = r"""#!/bin/bash
# Resolve our own directory even when double-clicked from Finder.
DIR="$(cd "$(dirname "$0")" && pwd)"
# Strip macOS quarantine if present (USB→iCloud→download path).
xattr -dr com.apple.quarantine "$DIR" 2>/dev/null || true
export COUNSELOR_DEMO=1
export COUNSELOR_DATA_DIR="$HOME/CounselorAssistantDemo"
export PYTHONPATH="$DIR/runtimes/macos/site-packages"
echo
echo "  Starting Counselor Assistant Demo..."
echo "  Your browser will open in a moment."
echo
echo "  To stop the demo: close this Terminal window."
echo
cd "$DIR/Counselor-Assistant"
exec "$DIR/runtimes/macos/python/bin/python3" run.py
"""

LINUX_LAUNCHER = r"""#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
export COUNSELOR_DEMO=1
export COUNSELOR_DATA_DIR="$HOME/CounselorAssistantDemo"
export PYTHONPATH="$DIR/runtimes/linux/site-packages"
echo
echo "  Starting Counselor Assistant Demo..."
echo "  Your browser will open in a moment."
echo "  (If it doesn't, visit http://127.0.0.1:5000/demo-login)"
echo
echo "  To stop the demo: close this terminal window."
echo
cd "$DIR/Counselor-Assistant"
exec "$DIR/runtimes/linux/python/bin/python3" run.py
"""

README_TEXT = """\
Counselor Assistant - Demo

To start the demo:

  Windows:  Double-click  START_HERE_Windows.bat
            (If Windows SmartScreen pops up: click "More info" then "Run anyway")

  Mac:      Double-click  START_HERE_Mac.command
            (First time: right-click the file and choose Open, then click Open
             in the dialog that appears)

  Linux:    Double-click  START_HERE_Linux.sh
            (or run it from a terminal: bash START_HERE_Linux.sh)

Your browser will open automatically to the dashboard.

This is a DEMO. All 25 students and their notes/grades/goals are fake.
Click around. Edit anything. Break things on purpose.

When you want to start over, click the "Reset Demo" button at the top of
any page. The demo resets back to its original 25 students.

To stop the demo: close the black/terminal window that opened with the app.

Where does my work go?
The demo writes a small SQLite database to your home folder, in:
    Windows:  C:\\Users\\<you>\\CounselorAssistantDemo\\
    Mac/Linux: ~/CounselorAssistantDemo/
You can delete that folder any time to wipe everything and start fresh.

Questions or issues?  [your contact here]
"""


def write_launchers(output):
    """Drop the three launcher files and mark Mac/Linux executable."""
    log('launchers', 'writing START_HERE_* files')
    (output / 'START_HERE_Windows.bat').write_text(WINDOWS_LAUNCHER, newline='\r\n')
    mac_path = output / 'START_HERE_Mac.command'
    mac_path.write_text(MAC_LAUNCHER, newline='\n')
    os.chmod(mac_path, 0o755)
    linux_path = output / 'START_HERE_Linux.sh'
    linux_path.write_text(LINUX_LAUNCHER, newline='\n')
    os.chmod(linux_path, 0o755)
    (output / 'README_FIRST.txt').write_text(README_TEXT, newline='\n')


def directory_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
            except OSError:
                pass
    return total


def human_size(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} TB'


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n', 1)[0])
    parser.add_argument('--output', required=True, help='Output directory (will be wiped)')
    parser.add_argument(
        '--skip-runtimes', action='store_true',
        help='Skip downloading/extracting Python — useful for fast iteration on launchers/README'
    )
    parser.add_argument('--clean', action='store_true', help='Wipe the output dir before building')
    args = parser.parse_args()

    output = Path(args.output).resolve()
    requirements_file = REPO_ROOT / 'requirements-demo.txt'
    if not requirements_file.exists():
        sys.exit('requirements-demo.txt not found at repo root')

    if args.clean and output.exists():
        log('clean', f'wiping {output}')
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    if not args.skip_runtimes:
        for platform, _spec in PLATFORMS.items():
            log('platform', f'=== {platform} ===')
            tarball = fetch_pbs(platform)
            runtime_dir = output / 'runtimes' / platform
            extract_pbs(tarball, runtime_dir)
            fetch_wheels(platform, requirements_file)
            install_wheels(platform, runtime_dir, requirements_file)

    copy_app(output)
    write_launchers(output)

    total = directory_size(output)
    log('done', f'bundle ready: {output}  ({human_size(total)})')
    for plat in PLATFORMS:
        rt_dir = output / 'runtimes' / plat
        if rt_dir.exists():
            log('size', f'  runtimes/{plat}: {human_size(directory_size(rt_dir))}')
    log('size', f'  Counselor-Assistant: {human_size(directory_size(output / "Counselor-Assistant"))}')


if __name__ == '__main__':
    main()
