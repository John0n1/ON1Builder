#!/bin/bash
# Script to verify multi-chain support in dry-run mode

set -e

# Configuration
CHAINS=${CHAINS:-"1,137"}  # Default to Ethereum Mainnet and Polygon
HTTP_ENDPOINT=${HTTP_ENDPOINT:-"https://eth-mainnet.g.alchemy.com/v2/demo"}
WEBSOCKET_ENDPOINT=${WEBSOCKET_ENDPOINT:-"wss://eth-mainnet.g.alchemy.com/v2/demo"}
CHAIN_1_HTTP_ENDPOINT=${CHAIN_1_HTTP_ENDPOINT:-"https://eth-mainnet.g.alchemy.com/v2/demo"}
CHAIN_1_WEBSOCKET_ENDPOINT=${CHAIN_1_WEBSOCKET_ENDPOINT:-"wss://eth-mainnet.g.alchemy.com/v2/demo"}
CHAIN_1_WALLET_ADDRESS=${CHAIN_1_WALLET_ADDRESS:-"0x0000000000000000000000000000000000000000"}
CHAIN_137_HTTP_ENDPOINT=${CHAIN_137_HTTP_ENDPOINT:-"https://polygon-rpc.com"}
CHAIN_137_WEBSOCKET_ENDPOINT=${CHAIN_137_WEBSOCKET_ENDPOINT:-"wss://polygon-rpc.com"}
CHAIN_137_WALLET_ADDRESS=${CHAIN_137_WALLET_ADDRESS:-"0x0000000000000000000000000000000000000000"}

# Print banner
echo "============================================================"
echo "ON1Builder Multi-Chain Verification"
echo "============================================================"
echo "Chains: $CHAINS"
echo "============================================================"

# Export environment variables
export CHAINS="$CHAINS"
export HTTP_ENDPOINT="$HTTP_ENDPOINT"
export WEBSOCKET_ENDPOINT="$WEBSOCKET_ENDPOINT"
export CHAIN_1_HTTP_ENDPOINT="$CHAIN_1_HTTP_ENDPOINT"
export CHAIN_1_WEBSOCKET_ENDPOINT="$CHAIN_1_WEBSOCKET_ENDPOINT"
export CHAIN_1_WALLET_ADDRESS="$CHAIN_1_WALLET_ADDRESS"
export CHAIN_137_HTTP_ENDPOINT="$CHAIN_137_HTTP_ENDPOINT"
export CHAIN_137_WEBSOCKET_ENDPOINT="$CHAIN_137_WEBSOCKET_ENDPOINT"
export CHAIN_137_WALLET_ADDRESS="$CHAIN_137_WALLET_ADDRESS"
export DRY_RUN="true"
export GO_LIVE="false"

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

# Start the application with multi-chain support
echo "Starting the application with multi-chain support in dry-run mode..."
docker-compose -f docker-compose.multi-chain.yml up -d

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
echo "Checking metrics for all chains..."
METRICS_RESPONSE=$(curl -s http://localhost:5001/metrics)
IFS=',' read -ra CHAIN_ARRAY <<< "$CHAINS"
for chain_id in "${CHAIN_ARRAY[@]}"; do
    if ! echo "$METRICS_RESPONSE" | grep -q "\"chain_id\":\"$chain_id\""; then
        echo "Warning: Metrics for chain $chain_id not found"
    else
        echo "Metrics for chain $chain_id found"
        
        # Check expected profit for this chain
        PROFIT=$(echo "$METRICS_RESPONSE" | grep -o "\"chain_id\":\"$chain_id\".*\"total_profit_eth\":[0-9.]*" | grep -o "\"total_profit_eth\":[0-9.]*" | cut -d':' -f2)
        echo "Expected profit for chain $chain_id: $PROFIT ETH"
    fi
done

# Print success message
echo "============================================================"
echo "Multi-chain verification completed successfully!"
echo "============================================================"
echo "Configured chains:"
for chain_id in "${CHAIN_ARRAY[@]}"; do
    chain_name_var="CHAIN_${chain_id}_CHAIN_NAME"
    chain_name=${!chain_name_var:-"Chain $chain_id"}
    echo "- $chain_name (ID: $chain_id)"
done
echo "============================================================"

# Ask if user wants to stop the application
echo "Do you want to stop the application? (y/n)"
read -r response
if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    echo "Stopping the application..."
    docker-compose -f docker-compose.multi-chain.yml down
    echo "Application stopped"
else
    echo "Application is still running. You can stop it later with:"
    echo "docker-compose -f docker-compose.multi-chain.yml down"
fi
