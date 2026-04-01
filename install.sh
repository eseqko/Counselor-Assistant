#!/usr/bin/env bash
# ============================================================
#  Counselor Assistant - Installer for Linux (EndeavourOS/Arch)
# ============================================================
#  Works on: EndeavourOS, Arch Linux, Manjaro
#  Also works on: Ubuntu, Debian, Fedora (auto-detects)
# ============================================================
set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  COUNSELOR ASSISTANT - Linux Installer${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""
echo "  All data stays local - nothing is uploaded to the cloud."
echo "  FERPA & ASCA compliant by design."
echo ""

# --- Detect package manager ---
install_deps() {
    if command -v pacman &>/dev/null; then
        echo -e "${GREEN}[1/5]${NC} Detected Arch-based system (EndeavourOS/Arch/Manjaro)"
        echo "       Installing Python and dependencies..."
        sudo pacman -S --needed --noconfirm python python-pip python-virtualenv 2>/dev/null || true
    elif command -v apt-get &>/dev/null; then
        echo -e "${GREEN}[1/5]${NC} Detected Debian-based system"
        echo "       Installing Python and dependencies..."
        sudo apt-get update -qq
        sudo apt-get install -y -qq python3 python3-pip python3-venv 2>/dev/null || true
    elif command -v dnf &>/dev/null; then
        echo -e "${GREEN}[1/5]${NC} Detected Fedora-based system"
        echo "       Installing Python and dependencies..."
        sudo dnf install -y -q python3 python3-pip python3-virtualenv 2>/dev/null || true
    else
        echo -e "${YELLOW}[1/5]${NC} Could not detect package manager."
        echo "       Please ensure Python 3.9+ is installed."
    fi
}

# --- Check Python ---
check_python() {
    if command -v python3 &>/dev/null; then
        PYTHON=python3
    elif command -v python &>/dev/null; then
        PYTHON=python
    else
        echo -e "${RED}[ERROR]${NC} Python not found after installation attempt."
        echo "        Please install Python 3.9+ manually."
        exit 1
    fi
    PY_VER=$($PYTHON --version 2>&1)
    echo -e "       ${GREEN}OK${NC} - $PY_VER"
    echo ""
}

# --- Navigate to script directory ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- Install system deps ---
install_deps
echo ""
check_python

# --- Create virtual environment ---
if [ ! -d "venv" ]; then
    echo -e "${GREEN}[2/5]${NC} Creating virtual environment..."
    $PYTHON -m venv venv
    echo "       Done."
else
    echo -e "${GREEN}[2/5]${NC} Virtual environment already exists."
fi
echo ""

# --- Activate and install pip deps ---
source venv/bin/activate
echo -e "${GREEN}[3/5]${NC} Installing Python dependencies..."
pip install -r requirements.txt --quiet --disable-pip-version-check
echo "       Done."
echo ""

# --- Create data directories ---
echo -e "${GREEN}[4/5]${NC} Setting up data directory..."
mkdir -p data/backups data/uploads
echo "       Done."
echo ""

# --- Create launcher script ---
echo -e "${GREEN}[5/5]${NC} Creating launcher..."
cat > start.sh << 'LAUNCHER'
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
source venv/bin/activate
echo ""
echo "  Counselor Assistant is running at: http://127.0.0.1:5000"
echo "  Press Ctrl+C to stop."
echo ""
python run.py
LAUNCHER
chmod +x start.sh
echo "       Done."
echo ""

# --- Create .desktop file for app menu ---
DESKTOP_FILE="$HOME/.local/share/applications/counselor-assistant.desktop"
mkdir -p "$(dirname "$DESKTOP_FILE")"
cat > "$DESKTOP_FILE" << DESKTOP
[Desktop Entry]
Name=Counselor Assistant
Comment=FERPA-Compliant School Counselor Tool
Exec=bash -c 'cd "$SCRIPT_DIR" && ./start.sh'
Terminal=true
Type=Application
Categories=Education;Office;
Keywords=counselor;school;student;FERPA;
DESKTOP
echo -e "       Created app menu entry."
echo ""

echo -e "${CYAN}============================================================${NC}"
echo -e "${GREEN}  INSTALLATION COMPLETE${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""
echo "  To start Counselor Assistant:"
echo "    Option 1: ./start.sh (from this directory)"
echo "    Option 2: Find 'Counselor Assistant' in your app menu"
echo ""
echo "  Then open: http://127.0.0.1:5000"
echo ""
echo "  Your data is stored in: $SCRIPT_DIR/data/"
echo "  Back up this folder regularly!"
echo ""
echo -e "${CYAN}============================================================${NC}"
echo ""

read -p "  Launch now? (Y/n): " LAUNCH
if [[ "$LAUNCH" != "n" && "$LAUNCH" != "N" ]]; then
    echo ""
    echo "  Starting Counselor Assistant..."
    xdg-open http://127.0.0.1:5000 2>/dev/null &
    python run.py
fi
