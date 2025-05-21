#!/usr/bin/env bash
# setup_dev.sh
# Sets up the development environment for ON1Builder

# Stop on errors
set -e

echo "Setting up ON1Builder development environment..."

# Check if Poetry is installed
if ! command -v poetry &> /dev/null; then
    echo "Poetry not found. Installing Poetry..."
    curl -sSL https://install.python-poetry.org | python3 -
fi

# Create virtual environment and install dependencies
echo "Installing dependencies..."
poetry install

# Create development .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file from template..."
    cp template.env .env
    echo "Please update .env file with your API keys and configuration"
fi

# Install the package in development mode
echo "Installing package in development mode..."
poetry install --no-root

echo "Development environment setup complete!"
echo ""
echo "To activate the environment, run: poetry shell"
echo "To run the application, use: python -m on1builder [command]"
echo ""
