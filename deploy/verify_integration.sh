#!/bin/bash
# ON1Builder Integration Verification Script

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Print banner
echo "============================================================"
echo "ON1Builder Integration Verification"
echo "============================================================"
echo "Project directory: $PROJECT_DIR"
echo "Date: $(date)"
echo "============================================================"

# Function to print with colors
print_info() {
    echo -e "\e[34m[INFO]\e[0m $1"
}

print_success() {
    echo -e "\e[32m[SUCCESS]\e[0m $1"
}

print_warning() {
    echo -e "\e[33m[WARNING]\e[0m $1"
}

print_error() {
    echo -e "\e[31m[ERROR]\e[0m $1"
}

# Check for running containers
print_info "Checking for running ON1Builder containers..."
if docker ps | grep -q "on1builder"; then
    print_success "ON1Builder containers are running"
else
    print_warning "No ON1Builder containers found"
    read -p "Do you want to start the containers? (y/n): " start_containers
    if [[ "$start_containers" =~ ^[Yy]$ ]]; then
        print_info "Starting containers with deploy_helper.sh..."
        "$PROJECT_DIR/deploy/deploy_helper.sh" --multi
    else
        print_info "Skipping container start"
    fi
fi

# Check Python imports
print_info "Verifying Python imports..."
cd "$PROJECT_DIR"

python -c "
import sys
sys.path.append('$PROJECT_DIR')
try:
    from scripts.python.app_multi_chain import app
    from scripts.python.transaction_core import TransactionCore
    from scripts.python.multi_chain_core import MultiChainCore
    from scripts.python.chain_worker import ChainWorker
    from scripts.python.txpool_monitor import TxpoolMonitor
    from scripts.python.safety_net import SafetyNet
    print('✓ All Python imports successful')
except ImportError as e:
    print(f'✗ Import error: {e}')
    exit(1)
" || {
    print_error "Python imports verification failed"
    exit 1
}

# Test API endpoint (if container is running)
if docker ps | grep -q "on1builder"; then
    print_info "Testing API endpoints..."
    
    # Test health endpoint
    response=$(curl -s http://localhost:5001/healthz)
    if echo "$response" | grep -q "ok"; then
        print_success "Health endpoint is working"
    else
        print_warning "Health endpoint check failed"
    fi
    
    # Test metrics endpoint
    response=$(curl -s http://localhost:5001/metrics)
    if echo "$response" | grep -q "total_chains"; then
        print_success "Metrics endpoint is working"
    else
        print_warning "Metrics endpoint check failed"
    fi
    
    # Test alert system
    print_info "Testing alert system..."
    response=$(curl -s -X POST -H "Content-Type: application/json" -d '{"message":"Integration test alert","level":"INFO"}' http://localhost:5001/api/test-alert)
    if echo "$response" | grep -q "success"; then
        print_success "Alert system is working"
    else
        print_warning "Alert system check failed"
    fi
    
    # Test transaction simulation with a sample tx (this might fail if tx doesn't exist)
    print_info "Testing transaction simulation (may fail if transaction doesn't exist)..."
    tx_hash="0x0000000000000000000000000000000000000000000000000000000000000001"  # Replace with real tx hash in prod
    chain_id="1"  # Ethereum mainnet
    response=$(curl -s -X POST -H "Content-Type: application/json" -d "{\"tx_hash\":\"$tx_hash\",\"chain_id\":\"$chain_id\"}" http://localhost:5001/api/simulate-transaction)
    if echo "$response" | grep -q "success\|error"; then
        print_info "Transaction simulation API responded"
    else
        print_warning "Transaction simulation API check failed"
    fi
else
    print_warning "Skipping API tests since containers are not running"
fi

# Verify file permissions
print_info "Verifying file permissions..."
if [ -x "$PROJECT_DIR/deploy/deploy_helper.sh" ] && [ -x "$PROJECT_DIR/deploy/emergency_shutdown.sh" ]; then
    print_success "Deployment scripts are executable"
else
    print_warning "Some deployment scripts are not executable"
    read -p "Fix permissions? (y/n): " fix_permissions
    if [[ "$fix_permissions" =~ ^[Yy]$ ]]; then
        chmod +x "$PROJECT_DIR/deploy"/*.sh
        print_success "Fixed script permissions"
    fi
fi

# Verify documentation references
print_info "Verifying documentation references..."
missing_docs=0

# Check for docs mentioning the alert system
if grep -q "alert" "$PROJECT_DIR/docs/alert_system.md"; then
    print_success "Alert system documentation exists"
else
    print_warning "Alert system documentation is missing or incomplete"
    missing_docs=$((missing_docs + 1))
fi

# Check for docs mentioning transaction simulation
if grep -q "simulate" "$PROJECT_DIR/docs/transaction_simulation.md"; then
    print_success "Transaction simulation documentation exists"
else
    print_warning "Transaction simulation documentation is missing or incomplete"
    missing_docs=$((missing_docs + 1))
fi

# Check for deploy helper in usage guide
if grep -q "deploy_helper" "$PROJECT_DIR/docs/usage_guide.md"; then
    print_success "Deployment helper is documented in usage guide"
else
    print_warning "Deployment helper documentation is missing from usage guide"
    missing_docs=$((missing_docs + 1))
fi

if [ "$missing_docs" -eq 0 ]; then
    print_success "All documentation checks passed"
else
    print_warning "$missing_docs documentation issues found"
fi

# Verify connection between shell scripts and Python files
print_info "Verifying connectivity between shell scripts and Python files..."

# Check if deploy scripts reference the correct Python files
if grep -q "app_multi_chain.py" "$PROJECT_DIR/deploy/docker-compose.multi-chain.yml" &&
   grep -q "app_multi_chain.py" "$PROJECT_DIR/Dockerfile"; then
    print_success "Deployment scripts correctly reference Python entry points"
else
    print_warning "Deployment script references to Python entry points may be incorrect"
fi

echo "============================================================"
print_success "Integration verification completed!"
echo "============================================================" 