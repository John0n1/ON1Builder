#!/bin/bash
# ON1Builder Data Backup Script

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR=${BACKUP_DIR:-"${PROJECT_DIR}/backups/data"}
DATE_FORMAT=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/data_backup_${DATE_FORMAT}.tar.gz"
RETENTION_DAYS=${RETENTION_DAYS:-30}

# Print banner
echo "============================================================"
echo "ON1Builder Data Backup"
echo "============================================================"
echo "Project directory: $PROJECT_DIR"
echo "Backup directory: $BACKUP_DIR"
echo "Backup file: $BACKUP_FILE"
echo "============================================================"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Create a list of files to back up
DATA_DIRS=(
  "data/abi"
  "data/ml"
)

# Create a temporary directory for backup
TEMP_DIR=$(mktemp -d)
echo "Creating temporary directory: $TEMP_DIR"

# Copy data directories to backup
for dir in "${DATA_DIRS[@]}"; do
  if [ -d "${PROJECT_DIR}/${dir}" ]; then
    # Create directory structure
    mkdir -p "$TEMP_DIR/$(dirname "$dir")"
    # Copy directory
    cp -r "${PROJECT_DIR}/${dir}" "$TEMP_DIR/$(dirname "$dir")/"
    echo "Backed up directory: $dir"
  else
    echo "Warning: $dir not found, skipping"
  fi
done

# Back up individual files
DATA_FILES=(
  "data/token_addresses.json"
  "data/token_symbols.json"
  "data/erc20_signatures.json"
)

for file in "${DATA_FILES[@]}"; do
  if [ -f "${PROJECT_DIR}/${file}" ]; then
    # Create directory structure
    mkdir -p "$TEMP_DIR/$(dirname "$file")"
    # Copy file
    cp "${PROJECT_DIR}/${file}" "$TEMP_DIR/$(dirname "$file")/"
    echo "Backed up file: $file"
  else
    echo "Warning: $file not found, skipping"
  fi
done

# Back up logs (but skip large ones > 100MB)
LOG_DIR="${PROJECT_DIR}/data/logs"
if [ -d "$LOG_DIR" ]; then
  mkdir -p "$TEMP_DIR/data/logs"
  echo "Backing up logs..."
  
  # Find log files smaller than 100MB
  find "$LOG_DIR" -name "*.log" -size -100M -type f | while read -r logfile; do
    cp "$logfile" "$TEMP_DIR/data/logs/"
    echo "Backed up log: $(basename "$logfile")"
  done
  
  # Check if any logs were skipped
  LARGE_LOGS=$(find "$LOG_DIR" -name "*.log" -size +100M -type f | wc -l)
  if [ "$LARGE_LOGS" -gt 0 ]; then
    echo "Warning: Skipped $LARGE_LOGS log files larger than 100MB"
  fi
else
  echo "Warning: Log directory not found, skipping logs backup"
fi

# Create compressed archive
echo "Creating backup archive..."
tar -czf "$BACKUP_FILE" -C "$TEMP_DIR" .
chmod 600 "$BACKUP_FILE" # Secure permissions for backup

# Clean up
rm -rf "$TEMP_DIR"

# Remove old backups
echo "Removing backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "data_backup_*.tar.gz" -type f -mtime +$RETENTION_DAYS -delete

echo "============================================================"
echo "Backup completed: $BACKUP_FILE"
echo "Size: $(du -h "$BACKUP_FILE" | cut -f1)"
echo "============================================================"

# Create a checksum file
echo "Generating checksum..."
sha256sum "$BACKUP_FILE" > "${BACKUP_FILE}.sha256"
echo "Checksum: $(cat "${BACKUP_FILE}.sha256" | cut -d ' ' -f1)"
echo "============================================================" 