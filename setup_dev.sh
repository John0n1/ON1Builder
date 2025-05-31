#!/usr/bin/env bash
# -*- coding: utf-8 -*-
set -e

if [ "$EUID" -eq 0 ]; then
    echo "Do not run setup_dev.sh as root or via sudo. Please run as a normal user." >&2
    exit 1
fi

if ! command -v curl &> /dev/null; then
    if [[ -f /etc/debian_version ]]; then
        sudo apt-get update && sudo apt-get install curl -y
    elif [[ -f /etc/redhat-release ]]; then
        sudo yum install curl -y
    elif [[ -f /etc/os-release ]]; then
        if grep -q "ID=arch" /etc/os-release; then
            sudo pacman -Sy --noconfirm curl
        elif grep -q "ID=opensuse" /etc/os-release; then
            sudo zypper install curl
        else
            echo "Unsupported distribution. Please install curl manually."
            exit 1
        fi
    else
        echo "Unsupported distribution. Please install curl manually."
        exit 1
    fi
fi

if ! python3 - << 'PYCODE'
import sys
sys.exit(0 if sys.version_info >= (3, 12) else 1)
PYCODE
then
    echo "Python 3.12 or higher is required."
    exit 1
fi

if ! python3 -m pip --version &> /dev/null; then
    python3 - << 'PYCODE'
import ensurepip; ensurepip.bootstrap(upgrade=True)
PYCODE
fi

export PATH="$HOME/.local/bin:$PATH"

BASHRC_UPDATED=0
if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' "$HOME/.bashrc"; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
    BASHRC_UPDATED=1
fi

if [ "$BASHRC_UPDATED" -eq 1 ] && [[ $- == *i* ]]; then
    source "$HOME/.bashrc"
fi

if command -v poetry &> /dev/null; then
    POETRY_CMD=poetry
elif python3 -m poetry --version &> /dev/null; then
    POETRY_CMD="python3 -m poetry"
else
    if python3 -m pip install --user poetry; then
        POETRY_CMD="python3 -m poetry"
    else
        curl -sSL https://install.python-poetry.org | python3 -
        export PATH="$HOME/.local/bin:$PATH"
        if command -v poetry &> /dev/null; then
            POETRY_CMD=poetry
        else
            echo "Error: Poetry installation failed"
            exit 1
        fi
    fi
fi

$POETRY_CMD install

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
    fi
fi

if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

$POETRY_CMD install
VENV_PATH=$($POETRY_CMD env info --path 2>/dev/null)

if [ -n "$VENV_PATH" ] && [ -f "$VENV_PATH/bin/activate" ]; then
    echo "Poetry virtual environment detected at: $VENV_PATH"
    echo "To activate the virtual environment, run:"
    echo "source $VENV_PATH/bin/activate"
else 
    echo "Could not find Poetry virtual environment. It may need to be manually activated."
    echo "Try running: $POETRY_CMD env use python"
fi
# Check if the script is sourced or executed
if (return 0 2>/dev/null); then
    IS_SOURCED=0
else
    IS_SOURCED=1
fi
# If sourced, IS_SOURCED will be 0, otherwise it will be 1

(return 0 2>/dev/null)
IS_SOURCED=$?

if ! command -v poetry &> /dev/null; then
    POETRY_BIN_PATHS=(
        "$HOME/.local/bin/poetry"
        "$(python3 -m site --user-base 2>/dev/null)/bin/poetry"
        "$(python3 -m site --user-site 2>/dev/null | sed 's|/lib/python[^/]*/site-packages$||')/bin/poetry"
    )
    for bin_path in "${POETRY_BIN_PATHS[@]}"; do
        if [ -f "$bin_path" ]; then
            ln -sf "$bin_path" "$HOME/.local/bin/poetry"
            chmod +x "$HOME/.local/bin/poetry"
            export PATH="$HOME/.local/bin:$PATH"
            break
        fi
    done
fi

if ! command -v poetry &> /dev/null; then
    curl -sSL https://install.python-poetry.org | python3 -
    export PATH="$HOME/.local/bin:$PATH"
    if [ -f "$HOME/.local/bin/poetry" ]; then
        chmod +x "$HOME/.local/bin/poetry"
    fi
fi

if ! command -v poetry &> /dev/null; then
    POETRY_BIN="$HOME/.local/bin/poetry"
    if [ -f "$POETRY_BIN" ]; then
        if [ -w /usr/local/bin ]; then
            ln -sf "$POETRY_BIN" /usr/local/bin/poetry
        else
            sudo ln -sf "$POETRY_BIN" /usr/local/bin/poetry 2>/dev/null || true
        fi
    fi
fi

if ! command -v poetry &> /dev/null; then
    FOUND_POETRY="$(find "$HOME" -type f -name poetry -perm -u+x 2>/dev/null | head -n1)"
    if [ -n "$FOUND_POETRY" ]; then
        mkdir -p "$HOME/.local/bin"
        ln -sf "$FOUND_POETRY" "$HOME/.local/bin/poetry"
        chmod +x "$HOME/.local/bin/poetry"
        export PATH="$HOME/.local/bin:$PATH"
    fi
fi

if ! command -v poetry &> /dev/null; then
    SHELL_PROFILE=""
    if [ -n "$BASH_VERSION" ]; then
        SHELL_PROFILE="$HOME/.bashrc"
    elif [ -n "$ZSH_VERSION" ]; then
        SHELL_PROFILE="$HOME/.zshrc"
    fi
    if [ -f "$HOME/.local/bin/poetry" ] && [ -n "$SHELL_PROFILE" ]; then
        if ! grep -q 'alias poetry=' "$SHELL_PROFILE"; then
            echo "alias poetry=\"$HOME/.local/bin/poetry\"" >> "$SHELL_PROFILE"
            export PATH="$HOME/.local/bin:$PATH"
            alias poetry="$HOME/.local/bin/poetry"
        fi
    fi
fi

if ! command -v poetry &> /dev/null; then
    exec $SHELL -l
fi

POETRY_ENV_PATH=$($POETRY_CMD env info -p 2>/dev/null)
if [ -n "$POETRY_ENV_PATH" ]; then
    if [ -f "$POETRY_ENV_PATH/bin/activate" ]; then
        source "$POETRY_ENV_PATH/bin/activate"
    fi
fi

ACTIVATION_CMD=$($POETRY_CMD env activate 2>/dev/null)
if [ -n "$ACTIVATION_CMD" ]; then
    eval "$ACTIVATION_CMD"
fi
#!/usr/bin/env bash
# -*- coding: utf-8 -*-
#
# setup_dev.sh — bootstrap development environment for ON1Builder
#

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

# 6) install Poetry if missing
if ! command -v poetry &>/dev/null; then
  echo "🔄 Installing Poetry…"
  curl -sSL https://install.python-poetry.org | python3 -
  export PATH="$HOME/.local/bin:$PATH"
fi

# 7) create & activate the virtualenv
poetry env use python3
eval "$(poetry env info -p >/dev/null 2>&1 && poetry shell || echo "source $(poetry env info -p)/bin/activate")"

# 8) install project dependencies
echo "📦 Installing dependencies via Poetry…"
poetry install --no-interaction

# 9) copy .env if needed
if [ ! -f .env ] && [ -f .env.example ]; then
  echo "⚙️  Copying .env.example → .env"
  cp .env.example .env
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
echo "   • To enter venv any time:   poetry shell"
echo "   • To run the CLI:           on1builder --help"
