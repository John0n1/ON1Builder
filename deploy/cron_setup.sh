#!/bin/bash
# ON1Builder Cron Setup Script

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Print banner
echo "============================================================"
echo "ON1Builder Cron Setup"
echo "============================================================"
echo "Project directory: $PROJECT_DIR"
echo "============================================================"

# Check if cron is installed
if ! command -v crontab &> /dev/null; then
    echo "Error: crontab command not found"
    exit 1
fi

# Create a temporary file for crontab configuration
TEMP_CRON_FILE=$(mktemp)

# Add header
echo "# ON1Builder cron jobs" > "$TEMP_CRON_FILE"
echo "# Generated at $(date)" >> "$TEMP_CRON_FILE"
echo "" >> "$TEMP_CRON_FILE"

# Set environment variables
echo "SHELL=/bin/bash" >> "$TEMP_CRON_FILE"
echo "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" >> "$TEMP_CRON_FILE"
echo "PROJECT_DIR=$PROJECT_DIR" >> "$TEMP_CRON_FILE"

# Add cron jobs
echo "# Check service status every 5 minutes" >> "$TEMP_CRON_FILE"
echo "*/5 * * * * cd \$PROJECT_DIR && ./deploy/verify_multi_chain.sh --quiet >> /var/log/on1builder_verify.log 2>&1" >> "$TEMP_CRON_FILE"

echo "# Rotate logs daily" >> "$TEMP_CRON_FILE"
echo "0 0 * * * find \$PROJECT_DIR/data/logs -name \"*.log\" -mtime +7 -exec rm {} \; >> /var/log/on1builder_log_rotation.log 2>&1" >> "$TEMP_CRON_FILE"

echo "# Backup configuration weekly" >> "$TEMP_CRON_FILE"
echo "0 1 * * 0 mkdir -p \$PROJECT_DIR/backups && tar -czf \$PROJECT_DIR/backups/config_backup_\$(date +\%Y\%m\%d).tar.gz \$PROJECT_DIR/config/ >> /var/log/on1builder_backup.log 2>&1" >> "$TEMP_CRON_FILE"

echo "# Rotate backups monthly" >> "$TEMP_CRON_FILE"
echo "0 2 1 * * find \$PROJECT_DIR/backups -name \"config_backup_*.tar.gz\" -mtime +30 -exec rm {} \; >> /var/log/on1builder_backup_rotation.log 2>&1" >> "$TEMP_CRON_FILE"

echo "# Update system packages weekly" >> "$TEMP_CRON_FILE"
echo "0 3 * * 0 apt-get update && apt-get upgrade -y >> /var/log/on1builder_system_update.log 2>&1" >> "$TEMP_CRON_FILE"

# If in multi-chain mode, add chain-specific cron jobs
if [ -n "$CHAINS" ]; then
    echo "# Chain-specific monitoring" >> "$TEMP_CRON_FILE"
    IFS=',' read -ra CHAIN_ARRAY <<< "$CHAINS"
    for chain_id in "${CHAIN_ARRAY[@]}"; do
        chain_name=${CHAIN_NAME:-"Chain $chain_id"}
        echo "*/10 * * * * curl -s http://localhost:5001/api/check_chain/$chain_id >> /var/log/on1builder_chain_${chain_id}_check.log 2>&1" >> "$TEMP_CRON_FILE"
    done
fi

# Try to install crontab
echo "Installing cron jobs..."
if crontab "$TEMP_CRON_FILE"; then
    echo "Cron jobs installed successfully!"
else
    echo "Error: Failed to install cron jobs"
    cat "$TEMP_CRON_FILE"
    rm "$TEMP_CRON_FILE"
    exit 1
fi

# Clean up
rm "$TEMP_CRON_FILE"

echo "============================================================"
echo "Cron setup completed successfully!"
echo "============================================================" 