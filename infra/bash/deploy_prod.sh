#!/bin/bash
# ON1Builder Production Deployment Script

set -e

# Parse command line arguments
MULTI_CHAIN=false
for arg in "$@"; do
    case $arg in
        --multi-chain)
            MULTI_CHAIN=true
            shift
            ;;
        *)
            # Unknown option
            ;;
    esac
done

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
VAULT_ADDR=${VAULT_ADDR:-"http://localhost:8200"}
VAULT_TOKEN=${VAULT_TOKEN:-""}
VAULT_PATH=${VAULT_PATH:-"secret/on1builder"}
GRAFANA_URL=${GRAFANA_URL:-"http://localhost:3000"}
GRAFANA_USER=${GRAFANA_USER:-"admin"}
GRAFANA_PASSWORD=${GRAFANA_PASSWORD:-"admin"}
CHAINS=${CHAINS:-"1"}  # Default to Ethereum mainnet

# Print banner
echo "============================================================"
if [ "$MULTI_CHAIN" = true ]; then
    echo "ON1Builder Production Deployment with Multi-Chain Support"
else
    echo "ON1Builder Production Deployment"
fi
echo "============================================================"
echo "Project directory: $PROJECT_DIR"
echo "Vault address: $VAULT_ADDR"
echo "Vault path: $VAULT_PATH"
echo "Grafana URL: $GRAFANA_URL"
if [ "$MULTI_CHAIN" = true ]; then
    echo "Chains: $CHAINS"
fi
echo "============================================================"

# Check required environment variables
check_env_var() {
    if [ -z "${!1}" ]; then
        echo "Error: $1 environment variable is not set"
        exit 1
    fi
}

echo "Validating required environment variables..."
check_env_var "VAULT_ADDR"
check_env_var "VAULT_TOKEN"
check_env_var "SMTP_PASSWORD"
check_env_var "SLACK_WEBHOOK_URL"

if [ "$MULTI_CHAIN" = true ]; then
    # Check chain-specific environment variables
    IFS=',' read -ra CHAIN_ARRAY <<< "$CHAINS"
    for chain_id in "${CHAIN_ARRAY[@]}"; do
        wallet_key_var="CHAIN_${chain_id}_WALLET_KEY"
        http_endpoint_var="CHAIN_${chain_id}_HTTP_ENDPOINT"

        # Check if chain-specific wallet key is set
        if [ -z "${!wallet_key_var}" ]; then
            # If not, check if global wallet key is set
            if [ -z "$WALLET_KEY" ]; then
                echo "Error: Neither $wallet_key_var nor WALLET_KEY environment variable is set"
                exit 1
            fi
        fi

        # Check if chain-specific HTTP endpoint is set
        if [ -z "${!http_endpoint_var}" ]; then
            # If not, check if global HTTP endpoint is set
            if [ -z "$HTTP_ENDPOINT" ]; then
                echo "Error: Neither $http_endpoint_var nor HTTP_ENDPOINT environment variable is set"
                exit 1
            fi
        fi
    done
else
    # Single-chain mode
    check_env_var "WALLET_KEY"
    check_env_var "HTTP_ENDPOINT"
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed or not in PATH"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "Error: Docker Compose is not installed or not in PATH"
    exit 1
fi

# Check if curl is installed
if ! command -v curl &> /dev/null; then
    echo "Error: curl is not installed or not in PATH"
    exit 1
fi

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    echo "Error: jq is not installed or not in PATH"
    exit 1
fi

# Initialize and unseal Vault
echo "Initializing and unsealing Vault..."
if [ "$MULTI_CHAIN" = true ]; then
    docker-compose -f docker/compose/docker-compose.multi-chain.yml up -d vault
else
    docker-compose -f docker/compose/docker-compose.prod.yml up -d vault
fi
sleep 5

# Check if Vault is running
echo "Checking Vault status..."
VAULT_STATUS=$(curl -s -o /dev/null -w "%{http_code}" $VAULT_ADDR/v1/sys/health)
if [ "$VAULT_STATUS" != "200" ]; then
    echo "Error: Vault is not running or not accessible"
    exit 1
fi

# Initialize Vault
if [ "$MULTI_CHAIN" = true ]; then
    # Initialize Vault with multi-chain support
    echo "Initializing Vault with multi-chain support..."
    chmod +x $PROJECT_DIR/deploy/vault_init_multi_chain.sh
    $PROJECT_DIR/deploy/vault_init_multi_chain.sh
else
    # Write secrets to Vault for single-chain mode
    echo "Writing secrets to Vault..."
    curl -s -X POST -H "X-Vault-Token: $VAULT_TOKEN" -d "{\"data\":{\"WALLET_KEY\":\"$WALLET_KEY\",\"SMTP_PASSWORD\":\"$SMTP_PASSWORD\",\"SLACK_WEBHOOK_URL\":\"$SLACK_WEBHOOK_URL\",\"ALERT_THRESHOLD_ETH\":\"0.01\"}}" $VAULT_ADDR/v1/$VAULT_PATH
fi

# Build and push Docker image
echo "Building and pushing Docker image..."
chmod +x $PROJECT_DIR/deploy/build_and_push.sh
$PROJECT_DIR/deploy/build_and_push.sh

# Start the application
if [ "$MULTI_CHAIN" = true ]; then
    echo "Starting the application with multi-chain support..."
    docker-compose -f docker/compose/docker-compose.multi-chain.yml up -d
else
    echo "Starting the application..."
    docker-compose -f docker/compose/docker-compose.prod.yml up -d
fi

# Wait for the application to start
echo "Waiting for the application to start..."
for i in {1..30}; do
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:5001/healthz | grep -q "200"; then
        echo "Application is running"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "Error: Application failed to start"
        exit 1
    fi
    echo "Waiting for application to start ($i/30)..."
    sleep 2
done

# Check metrics endpoint
echo "Checking metrics endpoint..."
METRICS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5001/metrics)
if [ "$METRICS_STATUS" != "200" ]; then
    echo "Error: Metrics endpoint is not accessible"
    exit 1
fi
echo "Metrics endpoint is accessible"

# Check if metrics show data for all chains
if [ "$MULTI_CHAIN" = true ]; then
    echo "Checking metrics for all chains..."
    METRICS_RESPONSE=$(curl -s http://localhost:5001/metrics)
    IFS=',' read -ra CHAIN_ARRAY <<< "$CHAINS"
    for chain_id in "${CHAIN_ARRAY[@]}"; do
        if ! echo "$METRICS_RESPONSE" | grep -q "\"chain_id\":\"$chain_id\""; then
            echo "Warning: Metrics for chain $chain_id not found"
        else
            echo "Metrics for chain $chain_id found"
        fi
    done
fi

# Set up cron jobs
echo "Setting up cron jobs..."
chmod +x $PROJECT_DIR/deploy/cron_setup.sh
$PROJECT_DIR/deploy/cron_setup.sh

# Import Grafana dashboard
echo "Importing Grafana dashboard..."
# Wait for Grafana to start
for i in {1..30}; do
    if curl -s -o /dev/null -w "%{http_code}" $GRAFANA_URL/api/health | grep -q "200"; then
        echo "Grafana is running"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "Error: Grafana failed to start"
        exit 1
    fi
    echo "Waiting for Grafana to start ($i/30)..."
    sleep 2
done

# Import dashboard
curl -s -X POST -H "Content-Type: application/json" -H "Accept: application/json" -u "$GRAFANA_USER:$GRAFANA_PASSWORD" -d @$PROJECT_DIR/dashboards/on1builder-dashboard.json $GRAFANA_URL/api/dashboards/db

# Import multi-chain dashboard if it exists
if [ "$MULTI_CHAIN" = true ] && [ -f "$PROJECT_DIR/dashboards/on1builder-multi-chain-dashboard.json" ]; then
    curl -s -X POST -H "Content-Type: application/json" -H "Accept: application/json" -u "$GRAFANA_USER:$GRAFANA_PASSWORD" -d @$PROJECT_DIR/dashboards/on1builder-multi-chain-dashboard.json $GRAFANA_URL/api/dashboards/db
    echo "Multi-chain dashboard imported"
fi

# Trigger a test alert
echo "Triggering a test alert..."
curl -s -X POST -H "Content-Type: application/json" -d '{"message":"Test alert from deployment script","level":"INFO"}' http://localhost:5001/api/test-alert

# Prompt user to confirm receipt of the alert
echo "============================================================"
echo "Deployment completed successfully!"
echo "============================================================"
echo "Please check your Slack for a test alert and confirm receipt."
echo "Press Enter when you have received the alert..."
read -r

if [ "$MULTI_CHAIN" = true ]; then
    echo "Deployment verified. ON1Builder is now running in production mode with multi-chain support."
    echo "You can access the dashboard at $GRAFANA_URL/d/on1builder/on1builder-dashboard"
    echo "============================================================"
    echo "Configured chains:"
    IFS=',' read -ra CHAIN_ARRAY <<< "$CHAINS"
    for chain_id in "${CHAIN_ARRAY[@]}"; do
        chain_name_var="CHAIN_${chain_id}_CHAIN_NAME"
        chain_name=${!chain_name_var:-"Chain $chain_id"}
        echo "- $chain_name (ID: $chain_id)"
    done
else
    echo "Deployment verified. ON1Builder is now running in production mode."
    echo "You can access the dashboard at $GRAFANA_URL/d/on1builder/on1builder-dashboard"
fi
echo "============================================================"
