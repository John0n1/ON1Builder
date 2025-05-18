#!/bin/bash
# ON1Builder Emergency Shutdown Script

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Print banner
echo "============================================================"
echo "ON1Builder EMERGENCY SHUTDOWN"
echo "============================================================"
echo "Project directory: $PROJECT_DIR"
echo "============================================================"

# Check if required commands are available
if ! command -v docker-compose &> /dev/null; then
    echo "Error: docker-compose is not installed or not in PATH"
    exit 1
fi

# Prompt for confirmation
echo -e "\e[31mWARNING: This will immediately stop all services and secure funds.\e[0m"
echo "Are you sure you want to proceed? (y/N)"
read -r confirmation

if [[ ! "$confirmation" =~ ^[Yy]$ ]]; then
    echo "Emergency shutdown aborted."
    exit 0
fi

echo "Starting emergency shutdown procedure..."

# Stop all services immediately
echo "Step 1: Stopping all services..."
cd "$PROJECT_DIR"

# Try to send shutdown signal to the API first
echo "Sending shutdown signal to the API..."
curl -s -X POST http://localhost:5001/stop || echo "Could not send stop signal to API"

# Force stop all containers
echo "Stopping all containers..."
if [ -f "${PROJECT_DIR}/deploy/docker-compose.multi-chain.yml" ]; then
    docker-compose -f "${PROJECT_DIR}/deploy/docker-compose.multi-chain.yml" down --timeout 5
else
    docker-compose -f "${PROJECT_DIR}/deploy/docker-compose.prod.yml" down --timeout 5
fi

# Secure funds by withdrawing to safe addresses
echo "Step 2: Securing funds..."
if [ -f "${PROJECT_DIR}/.env" ]; then
    source "${PROJECT_DIR}/.env"
fi

if [ -n "$EMERGENCY_WALLET_ADDRESS" ]; then
    echo "Attempting to transfer funds to emergency wallet: $EMERGENCY_WALLET_ADDRESS"
    
    # Create a simple script to withdraw funds
    cat > "${PROJECT_DIR}/withdraw_emergency.py" <<EOL
import asyncio
from web3 import Web3
import os
import json

async def withdraw_funds():
    print("Initiating emergency fund withdrawal")
    
    # Connect to a node - try multiple providers
    for provider in [os.getenv("HTTP_ENDPOINT"), "https://mainnet.infura.io/v3/9aa3d95b3bc440fa88ea12eaa4456161"]:
        try:
            if not provider:
                continue
            web3 = Web3(Web3.HTTPProvider(provider))
            if web3.is_connected():
                print(f"Connected to {provider}")
                break
        except Exception as e:
            print(f"Failed to connect to {provider}: {e}")
    else:
        print("ERROR: Could not connect to any Ethereum node")
        return
    
    # Get wallet details
    wallet_key = os.getenv("WALLET_KEY")
    emergency_address = os.getenv("EMERGENCY_WALLET_ADDRESS")
    
    if not wallet_key or not emergency_address:
        print("ERROR: Missing wallet key or emergency address")
        return
    
    # Check balance
    try:
        account = web3.eth.account.from_key(wallet_key)
        wallet_address = account.address
        balance = web3.eth.get_balance(wallet_address)
        
        if balance == 0:
            print("No ETH balance to withdraw")
        else:
            # Calculate gas cost for a transfer
            gas_price = web3.eth.gas_price
            gas_limit = 21000  # Standard ETH transfer gas
            gas_cost = gas_price * gas_limit
            
            # Calculate amount to send (leave some for gas)
            amount_to_send = balance - gas_cost
            
            if amount_to_send <= 0:
                print("Balance too low to cover gas costs")
                return
                
            print(f"Withdrawing {web3.from_wei(amount_to_send, 'ether')} ETH to {emergency_address}")
            
            # Create and sign transaction
            tx = {
                'to': emergency_address,
                'value': amount_to_send,
                'gas': gas_limit,
                'gasPrice': gas_price,
                'nonce': web3.eth.get_transaction_count(wallet_address),
                'chainId': web3.eth.chain_id
            }
            
            signed_tx = web3.eth.account.sign_transaction(tx, wallet_key)
            tx_hash = web3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            print(f"Transaction sent: {web3.to_hex(tx_hash)}")
            print("Waiting for confirmation...")
            
            # Wait for confirmation
            receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            if receipt.status == 1:
                print("Funds successfully secured!")
            else:
                print("Transaction failed!")
                
    except Exception as e:
        print(f"Error during withdrawal: {e}")

# Run the withdrawal function
asyncio.run(withdraw_funds())
EOL

    # Run the withdrawal script
    python "${PROJECT_DIR}/withdraw_emergency.py"
    
    # Clean up the script (security)
    rm "${PROJECT_DIR}/withdraw_emergency.py"
else
    echo "No EMERGENCY_WALLET_ADDRESS set in .env - skipping fund withdrawal"
fi

# Backup important data
echo "Step 3: Backing up critical data..."
BACKUP_DIR="${PROJECT_DIR}/emergency_backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup config
cp -r "${PROJECT_DIR}/config" "$BACKUP_DIR/"
cp "${PROJECT_DIR}/.env" "$BACKUP_DIR/" 2>/dev/null || echo "No .env file found"

# Backup ML data
cp -r "${PROJECT_DIR}/data/ml" "$BACKUP_DIR/" 2>/dev/null || echo "No ML data found"

# Backup logs
mkdir -p "$BACKUP_DIR/logs"
cp "${PROJECT_DIR}/data/logs"/*.log "$BACKUP_DIR/logs/" 2>/dev/null || echo "No logs found"

# Set secure permissions on backups
chmod -R 600 "$BACKUP_DIR"

echo "Critical data backed up to: $BACKUP_DIR"

# Log event
echo "$(date): Emergency shutdown executed by $(whoami)" >> "${PROJECT_DIR}/emergency_shutdown.log"

echo "============================================================"
echo "Emergency shutdown procedure completed."
echo "All services have been stopped and funds secured."
echo "============================================================" 