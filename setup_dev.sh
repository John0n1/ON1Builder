#!/usr/bin/env bash
# setup_dev.sh
# Sets up the development environment for ON1Builder

# Stop on errors
set -e

echo "Setting up ON1Builder development environment..."

# Prevent running as root
if [ "$EUID" -eq 0 ]; then
    echo "Do not run setup_dev.sh as root or via sudo. Please run as a normal user." >&2
    exit 1
fi

# Check if curl is installed and install if not
if ! command -v curl &> /dev/null; then
    echo "curl is required but not found. Installing curl..."
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

# Check Python version is >= 3.12
if ! python3 - << 'PYCODE'
import sys
sys.exit(0 if sys.version_info >= (3, 12) else 1)
PYCODE
then
    echo "Python 3.12 or higher is required."
    exit 1
fi

# Ensure pip is available before pip install
if ! python3 -m pip --version &> /dev/null; then
    echo "pip not found; bootstrapping pip via ensurepip..."
    python3 - << 'PYCODE'
import ensurepip; ensurepip.bootstrap(upgrade=True)
PYCODE
fi

# Ensure user local bin is in PATH for Poetry
export PATH="$HOME/.local/bin:$PATH"

# Determine Poetry command (try binary or module)
if command -v poetry &> /dev/null; then
    POETRY_CMD=poetry
elif python3 -m poetry --version &> /dev/null; then
    POETRY_CMD="python3 -m poetry"
else
    echo "Poetry not found. Attempting to install via pip..."
    if python3 -m pip install --user poetry; then
        echo "Poetry installed via pip"
        POETRY_CMD="python3 -m poetry"
    else
        echo "pip install failed; installing Poetry via official installer..."
        curl -sSL https://install.python-poetry.org | python3 -
        # Ensure installer location is on PATH
        export PATH="$HOME/.local/bin:$PATH"
        if command -v poetry &> /dev/null; then
            POETRY_CMD=poetry
        else
            echo "Error: Poetry installation failed"
            exit 1
        fi
    fi
fi

# Create virtual environment and install dependencies
echo "Installing dependencies..."
$POETRY_CMD install

# Handle .env file creation
if [ ! -f ".env" ]; then
    if [ -f "template.env" ]; then
        cp template.env .env
        echo ".env file created from template.env. Please update with your API keys."
    else
        echo "Warning: template.env not found. Skipping .env file creation."
    fi
fi

# Source environment variables
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
else
    echo "Warning: .env file not found.  Continuing without sourcing environment variables."
fi

# Install package in development mode (editable install)
echo "Installing package in development mode..."
$POETRY_CMD install --no-root

echo "Development environment setup complete!"
echo ""
echo "To activate the environment, run: poetry shell"
echo "To run the application, use: python -m on1builder [command]"
echo ""
