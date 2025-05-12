#!/bin/bash
# Script to initialize and configure HashiCorp Vault for ON1Builder

set -e

# Configuration
VAULT_ADDR=${VAULT_ADDR:-"http://localhost:8200"}
VAULT_TOKEN=${VAULT_TOKEN:-""}
VAULT_PATH=${VAULT_PATH:-"secret/on1builder"}
VAULT_KEYS_FILE="vault-keys.json"
VAULT_ROOT_TOKEN_FILE="vault-root-token"
CHAINS=${CHAINS:-"1"}  # Default to Ethereum mainnet

# Print banner
echo "============================================================"
echo "ON1Builder Vault Initialization"
echo "============================================================"
echo "Vault address: $VAULT_ADDR"
echo "Vault path: $VAULT_PATH"
echo "Chains: $CHAINS"
echo "============================================================"

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

# Function to check if Vault is running
check_vault_status() {
    echo "Checking Vault status..."
    if curl -s -o /dev/null -w "%{http_code}" $VAULT_ADDR/v1/sys/health; then
        return 0
    else
        return 1
    fi
}

# Function to check if Vault is initialized
check_vault_initialized() {
    echo "Checking if Vault is initialized..."
    INIT_STATUS=$(curl -s $VAULT_ADDR/v1/sys/init | jq -r '.initialized')
    if [ "$INIT_STATUS" == "true" ]; then
        echo "Vault is already initialized"
        return 0
    else
        echo "Vault is not initialized"
        return 1
    fi
}

# Function to check if Vault is sealed
check_vault_sealed() {
    echo "Checking if Vault is sealed..."
    SEAL_STATUS=$(curl -s $VAULT_ADDR/v1/sys/seal-status | jq -r '.sealed')
    if [ "$SEAL_STATUS" == "true" ]; then
        echo "Vault is sealed"
        return 0
    else
        echo "Vault is unsealed"
        return 1
    fi
}

# Function to initialize Vault
initialize_vault() {
    echo "Initializing Vault..."
    curl -s -X PUT -d '{"secret_shares": 5, "secret_threshold": 3}' $VAULT_ADDR/v1/sys/init > $VAULT_KEYS_FILE

    # Extract root token
    ROOT_TOKEN=$(jq -r '.root_token' $VAULT_KEYS_FILE)
    echo $ROOT_TOKEN > $VAULT_ROOT_TOKEN_FILE

    echo "Vault initialized successfully"
    echo "Root token saved to $VAULT_ROOT_TOKEN_FILE"
    echo "Unseal keys saved to $VAULT_KEYS_FILE"

    # Set VAULT_TOKEN to the root token
    VAULT_TOKEN=$ROOT_TOKEN
}

# Function to unseal Vault
unseal_vault() {
    echo "Unsealing Vault..."

    # Get unseal keys
    UNSEAL_KEYS=$(jq -r '.keys_base64[:3][]' $VAULT_KEYS_FILE)

    # Unseal Vault with the first 3 keys
    for KEY in $UNSEAL_KEYS; do
        curl -s -X PUT -d "{\"key\": \"$KEY\"}" $VAULT_ADDR/v1/sys/unseal
    done

    echo "Vault unsealed successfully"
}

# Function to enable secrets engine
enable_secrets_engine() {
    echo "Enabling secrets engine..."

    # Check if secrets engine is already enabled
    SECRETS_ENGINES=$(curl -s -H "X-Vault-Token: $VAULT_TOKEN" $VAULT_ADDR/v1/sys/mounts | jq -r 'keys[]')
    if echo "$SECRETS_ENGINES" | grep -q "^secret/"; then
        echo "Secrets engine already enabled"
    else
        curl -s -X POST -H "X-Vault-Token: $VAULT_TOKEN" -d '{"type": "kv", "options": {"version": "2"}}' $VAULT_ADDR/v1/sys/mounts/secret
        echo "Secrets engine enabled successfully"
    fi
}

# Function to write global secrets to Vault
write_global_secrets() {
    echo "Writing global secrets to Vault..."

    # Check if required environment variables are set
    if [ -z "$SMTP_PASSWORD" ]; then
        echo "Error: SMTP_PASSWORD environment variable is not set"
        exit 1
    fi

    if [ -z "$SLACK_WEBHOOK_URL" ]; then
        echo "Error: SLACK_WEBHOOK_URL environment variable is not set"
        exit 1
    fi

    # Write global secrets to Vault
    curl -s -X POST -H "X-Vault-Token: $VAULT_TOKEN" \
        -d "{\"data\":{\"SMTP_PASSWORD\":\"$SMTP_PASSWORD\",\"SLACK_WEBHOOK_URL\":\"$SLACK_WEBHOOK_URL\",\"ALERT_THRESHOLD_ETH\":\"${ALERT_THRESHOLD_ETH:-0.01}\"}}" \
        $VAULT_ADDR/v1/$VAULT_PATH

    echo "Global secrets written to Vault successfully"
}

# Function to write chain-specific secrets to Vault
write_chain_secrets() {
    local chain_id=$1
    local wallet_key_var="CHAIN_${chain_id}_WALLET_KEY"
    local wallet_key=${!wallet_key_var}

    # If chain-specific wallet key is not set, use the global one
    if [ -z "$wallet_key" ]; then
        if [ -z "$WALLET_KEY" ]; then
            echo "Error: Neither $wallet_key_var nor WALLET_KEY environment variable is set"
            exit 1
        fi
        wallet_key=$WALLET_KEY
    fi

    echo "Writing secrets for chain $chain_id to Vault..."

    # Write chain-specific secrets to Vault
    curl -s -X POST -H "X-Vault-Token: $VAULT_TOKEN" \
        -d "{\"data\":{\"WALLET_KEY\":\"$wallet_key\"}}" \
        $VAULT_ADDR/v1/$VAULT_PATH/chain_$chain_id

    echo "Secrets for chain $chain_id written to Vault successfully"
}

# Function to write secrets to Vault
write_secrets() {
    echo "Writing secrets to Vault..."

    # Write global secrets to Vault
    write_global_secrets

    # Write chain-specific secrets to Vault
    IFS=',' read -ra CHAIN_ARRAY <<< "$CHAINS"
    for chain_id in "${CHAIN_ARRAY[@]}"; do
        write_chain_secrets $chain_id
    done

    echo "All secrets written to Vault successfully"
}

# Function to create a policy for the application
create_policy() {
    echo "Creating policy for the application..."

    # Create policy file
    cat > on1builder-policy.hcl << EOL
# ON1Builder policy
path "secret/data/on1builder" {
  capabilities = ["read"]
}

# Allow access to chain-specific secrets
path "secret/data/on1builder/chain_*" {
  capabilities = ["read"]
}
EOL

    # Create policy
    curl -s -X PUT -H "X-Vault-Token: $VAULT_TOKEN" \
        -d "{\"policy\": \"$(cat on1builder-policy.hcl | sed 's/"/\\"/g')\"}" \
        $VAULT_ADDR/v1/sys/policies/acl/on1builder

    echo "Policy created successfully"
}

# Function to create a token for the application
create_token() {
    echo "Creating token for the application..."

    # Create token
    TOKEN_RESPONSE=$(curl -s -X POST -H "X-Vault-Token: $VAULT_TOKEN" \
        -d '{"policies": ["on1builder"], "ttl": "720h", "renewable": true}' \
        $VAULT_ADDR/v1/auth/token/create)

    # Extract token
    APP_TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.auth.client_token')

    echo "Token created successfully: $APP_TOKEN"
    echo "Use this token in your application configuration"
    echo "export VAULT_TOKEN=$APP_TOKEN" > app-token.sh
}

# Main function
main() {
    # Check if Vault is running
    if ! check_vault_status; then
        echo "Error: Vault is not running or not accessible"
        exit 1
    fi

    # Check if Vault is initialized
    if ! check_vault_initialized; then
        initialize_vault
    fi

    # If VAULT_TOKEN is not set, use the root token
    if [ -z "$VAULT_TOKEN" ]; then
        if [ -f "$VAULT_ROOT_TOKEN_FILE" ]; then
            VAULT_TOKEN=$(cat $VAULT_ROOT_TOKEN_FILE)
            echo "Using root token from $VAULT_ROOT_TOKEN_FILE"
        else
            echo "Error: VAULT_TOKEN environment variable is not set and no root token file found"
            exit 1
        fi
    fi

    # Check if Vault is sealed
    if check_vault_sealed; then
        unseal_vault
    fi

    # Enable secrets engine
    enable_secrets_engine

    # Write secrets to Vault
    write_secrets

    # Create policy
    create_policy

    # Create token
    create_token

    echo "============================================================"
    echo "Vault initialization completed successfully"
    echo "============================================================"
}

# Run main function
main
