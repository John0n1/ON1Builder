#!/usr/bin/env bash
# setup_dev_environment.sh — bootstrap development environment for ON1Builder

set -euo pipefail

# 1) refuse to run as root
if [ "$EUID" -eq 0 ]; then
  echo "⚠️  Please do not run as root or via sudo." >&2
  exit 1
fi

# 2) ensure curl
if ! command -v curl &>/dev/null; then
  echo "🔄 Installing curl…"
  if [ -f /etc/debian_version ]; then
    sudo apt-get update && sudo apt-get install -y curl
  elif [ -f /etc/redhat-release ]; then
    sudo yum install -y curl
  elif grep -qEi "ID=(arch|opensuse)" /etc/os-release; then
    sudo pacman -Sy --noconfirm curl || sudo zypper install -y curl
  else
    echo "⚠️  Unsupported distro; install curl manually." >&2
    exit 1
  fi
fi

# 3) check Python ≥3.12
if ! python3 - <<'PYCODE'
import sys
sys.exit(0 if sys.version_info >= (3,12) else 1)
PYCODE
then
  echo "⚠️  Python 3.12 or newer is required." >&2
  exit 1
fi

# 4) ensure pip
if ! python3 -m pip --version &>/dev/null; then
  echo "🔄 Bootstrapping pip…"
  python3 -m ensurepip --upgrade
fi

# 5) add ~/.local/bin to PATH in this session
export PATH="$HOME/.local/bin:$PATH"

# 6) create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
  echo "🔄 Creating virtual environment..."
  python3 -m venv venv
fi

# 7) activate the virtualenv
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# 8) install project dependencies
echo "📦 Installing dependencies via pip..."
pip install --upgrade pip
pip install -e ".[dev]"

# 9) copy .env if needed
if [ ! -f .env ] && [ -f configs/.env.example ]; then
  echo "⚙️  Copying configs/.env.example → .env"
  cp configs/.env.example .env
fi

# 10) load environment variables
if [ -f .env ]; then
  echo "🔐 Loading .env into session"
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

echo "✅ Development environment ready!"
echo "   • To enter venv any time:   source venv/bin/activate"
echo "   • To run the CLI:           on1builder --help"
