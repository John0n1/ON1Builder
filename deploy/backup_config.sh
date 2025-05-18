#!/bin/bash
# ON1Builder Configuration Backup Script

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR=${BACKUP_DIR:-"${PROJECT_DIR}/backups/config"}
DATE_FORMAT=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/config_backup_${DATE_FORMAT}.tar.gz"
RETENTION_DAYS=${RETENTION_DAYS:-30}

# Print banner
echo "============================================================"
echo "ON1Builder Configuration Backup"
echo "============================================================"
echo "Project directory: $PROJECT_DIR"
echo "Backup directory: $BACKUP_DIR"
echo "Backup file: $BACKUP_FILE"
echo "============================================================"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Create a list of files to back up
BACKUP_FILES=(
  "config/config.yaml"
  "config/config_multi_chain.yaml"
  "config/template.env"
  "config/grafana"
  "config/prometheus"
  ".pre-commit-config.yaml"
  "Dockerfile"
  "deploy/docker-compose.prod.yml"
  "deploy/docker-compose.multi-chain.yml"
)

# Create a temporary directory for backup
TEMP_DIR=$(mktemp -d)
echo "Creating temporary directory: $TEMP_DIR"

# Copy files to backup
for file in "${BACKUP_FILES[@]}"; do
  if [ -e "${PROJECT_DIR}/${file}" ]; then
    # Create directory structure
    mkdir -p "$TEMP_DIR/$(dirname "$file")"
    # Copy file or directory
    cp -r "${PROJECT_DIR}/${file}" "$TEMP_DIR/$(dirname "$file")/"
    echo "Backed up: $file"
  else
    echo "Warning: $file not found, skipping"
  fi
done

# Also back up .env file if it exists (but not to version control)
if [ -f "${PROJECT_DIR}/.env" ]; then
  cp "${PROJECT_DIR}/.env" "$TEMP_DIR/"
  echo "Backed up: .env"
fi

# Create compressed archive
echo "Creating backup archive..."
tar -czf "$BACKUP_FILE" -C "$TEMP_DIR" .
chmod 600 "$BACKUP_FILE" # Secure permissions for backup

# Clean up
rm -rf "$TEMP_DIR"

# Remove old backups
echo "Removing backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "config_backup_*.tar.gz" -type f -mtime +$RETENTION_DAYS -delete

echo "============================================================"
echo "Backup completed: $BACKUP_FILE"
echo "Size: $(du -h "$BACKUP_FILE" | cut -f1)"
echo "============================================================"

# Create a checksum file
echo "Generating checksum..."
sha256sum "$BACKUP_FILE" > "${BACKUP_FILE}.sha256"
echo "Checksum: $(cat "${BACKUP_FILE}.sha256" | cut -d ' ' -f1)"
echo "============================================================" 