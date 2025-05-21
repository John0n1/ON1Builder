#!/bin/bash
# ON1Builder Permissions Setup Script

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Print banner
echo "============================================================"
echo "ON1Builder Permissions Setup"
echo "============================================================"
echo "Project directory: $PROJECT_DIR"
echo "============================================================"

# Function to set permissions on directory
set_dir_permissions() {
  local dir="$1"
  local perms="$2"
  local desc="$3"
  
  if [ -d "$dir" ]; then
    echo "Setting $perms permissions on $desc: $dir"
    chmod "$perms" "$dir"
  else
    echo "Warning: Directory $dir not found, skipping"
    # Create directory if required
    if [ "$4" = "create" ]; then
      echo "Creating directory: $dir"
      mkdir -p "$dir"
      chmod "$perms" "$dir"
    fi
  fi
}

# Function to set permissions on file
set_file_permissions() {
  local file="$1"
  local perms="$2"
  local desc="$3"
  
  if [ -f "$file" ]; then
    echo "Setting $perms permissions on $desc: $file"
    chmod "$perms" "$file"
  else
    echo "Warning: File $file not found, skipping"
  fi
}

# Set permissions on configuration directory
echo "Setting permissions on configuration directories..."
set_dir_permissions "${PROJECT_DIR}/config" "700" "Config directory" "create"
set_dir_permissions "${PROJECT_DIR}/config/grafana" "755" "Grafana config directory" "create"
set_dir_permissions "${PROJECT_DIR}/config/prometheus" "755" "Prometheus config directory" "create"

# Set permissions on deploy directory
echo "Setting permissions on deploy directory..."
set_dir_permissions "${PROJECT_DIR}/deploy" "755" "Deploy directory"

# Set permissions on data directory
echo "Setting permissions on data directories..."
set_dir_permissions "${PROJECT_DIR}/data" "755" "Data directory" "create"
set_dir_permissions "${PROJECT_DIR}/data/abi" "755" "ABI directory" "create"
set_dir_permissions "${PROJECT_DIR}/data/ml" "755" "ML directory" "create"
set_dir_permissions "${PROJECT_DIR}/data/logs" "755" "Logs directory" "create"

# Set permissions on scripts directory
echo "Setting permissions on scripts directories..."
set_dir_permissions "${PROJECT_DIR}/scripts" "755" "Scripts directory"
set_dir_permissions "${PROJECT_DIR}/src/on1builder" "755" "Python package directory"
set_dir_permissions "${PROJECT_DIR}/src/on1builder/utils" "755" "Python utils directory"

# Set permissions on backup directory
echo "Setting permissions on backup directories..."
set_dir_permissions "${PROJECT_DIR}/backups" "700" "Backup directory" "create"
set_dir_permissions "${PROJECT_DIR}/backups/config" "700" "Config backup directory" "create"
set_dir_permissions "${PROJECT_DIR}/backups/data" "700" "Data backup directory" "create"

# Make shell scripts executable
echo "Making shell scripts executable..."
find "${PROJECT_DIR}/deploy" -name "*.sh" -type f -exec chmod 755 {} \;
find "${PROJECT_DIR}/scripts" -name "*.sh" -type f -exec chmod 755 {} \;

# Set permissions on sensitive files
echo "Setting permissions on sensitive files..."
if [ -f "${PROJECT_DIR}/.env" ]; then
  set_file_permissions "${PROJECT_DIR}/.env" "600" "Environment file"
fi

# Set permissions on data files
echo "Setting permissions on data files..."
find "${PROJECT_DIR}/data" -type f -not -path "*/logs/*" -exec chmod 644 {} \;

# Set permissions on ABI files
echo "Setting permissions on ABI files..."
find "${PROJECT_DIR}/data/abi" -type f -name "*.json" -exec chmod 644 {} \;

# Verify permissions were set correctly
echo "============================================================"
echo "Verifying permissions..."

# Function to verify permissions
verify_permissions() {
  local path="$1"
  local expected="$2"
  local desc="$3"
  
  if [ -e "$path" ]; then
    local actual=$(stat -c "%a" "$path")
    if [ "$actual" = "$expected" ]; then
      echo "✓ $desc permissions correctly set to $actual"
    else
      echo "✗ $desc permissions incorrect: expected $expected, found $actual"
    fi
  fi
}

verify_permissions "${PROJECT_DIR}/config" "700" "Config directory"
verify_permissions "${PROJECT_DIR}/data" "755" "Data directory"
verify_permissions "${PROJECT_DIR}/deploy" "755" "Deploy directory"
verify_permissions "${PROJECT_DIR}/src/on1builder" "755" "Python package directory"
verify_permissions "${PROJECT_DIR}/backups" "700" "Backup directory"

if [ -f "${PROJECT_DIR}/.env" ]; then
  verify_permissions "${PROJECT_DIR}/.env" "600" "Environment file"
fi

echo "============================================================"
echo "Permissions setup complete"
echo "============================================================" 