#!/bin/bash
# ON1Builder Security Audit Script

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Print banner
echo "============================================================"
echo "ON1Builder Security Audit"
echo "============================================================"
echo "Project directory: $PROJECT_DIR"
echo "Date: $(date)"
echo "============================================================"

# Function to check if a command exists
command_exists() {
    command -v "$1" &> /dev/null
}

# Function to print with colors
print_status() {
    if [ "$1" == "PASS" ]; then
        echo -e "\e[32m[PASS]\e[0m $2"
    elif [ "$1" == "WARN" ]; then
        echo -e "\e[33m[WARN]\e[0m $2"
    elif [ "$1" == "FAIL" ]; then
        echo -e "\e[31m[FAIL]\e[0m $2"
    else
        echo -e "\e[34m[INFO]\e[0m $2"
    fi
}

# Check directory permissions
echo "Checking directory permissions..."
check_dir_perms() {
    local dir="$1"
    local expected_perms="$2"
    local desc="$3"
    
    if [ ! -d "$dir" ]; then
        print_status "FAIL" "$desc ($dir) does not exist"
        return
    fi
    
    local perms=$(stat -c "%a" "$dir")
    if [ "$perms" == "$expected_perms" ]; then
        print_status "PASS" "$desc permissions ($perms)"
    else
        print_status "WARN" "$desc permissions: expected $expected_perms, found $perms"
    fi
}

check_dir_perms "$PROJECT_DIR/config" "700" "Config directory"
check_dir_perms "$PROJECT_DIR/data" "755" "Data directory"
check_dir_perms "$PROJECT_DIR/resources/abi" "755" "ABI directory"
check_dir_perms "$PROJECT_DIR/data/ml" "755" "ML directory"
check_dir_perms "$PROJECT_DIR/deploy" "755" "Deploy directory"
check_dir_perms "$PROJECT_DIR/src/on1builder" "755" "Python package directory"

# Check for sensitive information in files
echo -e "\nChecking for sensitive information in files..."

# Function to check for sensitive patterns in files
check_sensitive_info() {
    local pattern="$1"
    local exclude="$2"
    local desc="$3"
    
    local count=0
    if [ -z "$exclude" ]; then
        count=$(grep -r "$pattern" --include="*.{py,js,sh,yml,yaml}" "$PROJECT_DIR" | wc -l)
    else
        count=$(grep -r "$pattern" --include="*.{py,js,sh,yml,yaml}" --exclude-dir="$exclude" "$PROJECT_DIR" | wc -l)
    fi
    
    if [ "$count" -gt 0 ]; then
        print_status "WARN" "Found potential $desc ($count matches)"
    else
        print_status "PASS" "No $desc found"
    fi
}

check_sensitive_info "private_key|privateKey|PRIVATE_KEY" "node_modules|venv" "private keys"
check_sensitive_info "password|PASSWORD|passwd|PASSWD" "node_modules|venv" "passwords"
check_sensitive_info "api[_-]key|API[_-]KEY" "node_modules|venv" "API keys"
check_sensitive_info "secret|SECRET" "node_modules|venv" "secrets"
check_sensitive_info "access[_-]token|ACCESS[_-]TOKEN" "node_modules|venv" "access tokens"

# Check .env file
echo -e "\nChecking .env file..."
if [ -f "$PROJECT_DIR/.env" ]; then
    print_status "WARN" ".env file exists, should not be committed to repository"
else
    print_status "PASS" "No .env file in repository"
fi

# Check for Python-specific security issues if bandit is installed
echo -e "\nChecking Python code for security issues..."
if command_exists bandit; then
    echo "Running bandit security check..."
    bandit -r "$PROJECT_DIR/src/on1builder" -f txt || true
else
    print_status "INFO" "Bandit not installed. Install with 'pip install bandit' for Python security scanning"
fi

# Check for JavaScript security issues if npm is installed
if command_exists npm && [ -d "$PROJECT_DIR/ui" ]; then
    echo -e "\nChecking JavaScript dependencies for vulnerabilities..."
    if [ -f "$PROJECT_DIR/package.json" ]; then
        cd "$PROJECT_DIR"
        npm audit --json || true
    else
        print_status "INFO" "No package.json found, skipping npm audit"
    fi
fi

# Check Docker security if docker is available
echo -e "\nChecking Docker security..."
if command_exists docker; then
    if [ -f "$PROJECT_DIR/Dockerfile" ]; then
        print_status "INFO" "Dockerfile exists, manually review for security best practices"
        
        # Check if running as root
        if grep -q "USER root" "$PROJECT_DIR/Dockerfile"; then
            print_status "WARN" "Dockerfile may be running as root"
        elif ! grep -q "USER" "$PROJECT_DIR/Dockerfile"; then
            print_status "WARN" "No USER directive in Dockerfile, may be running as root"
        else
            print_status "PASS" "Dockerfile specifies non-root user"
        fi
    fi
else
    print_status "INFO" "Docker not installed, skipping Docker security checks"
fi

# Check pre-commit hooks
echo -e "\nChecking pre-commit hooks..."
if [ -f "$PROJECT_DIR/.pre-commit-config.yaml" ]; then
    print_status "PASS" "pre-commit configuration file exists"
else
    print_status "WARN" "No pre-commit configuration file found"
fi

# Check configuration files
echo -e "\nChecking configuration files..."
CONFIG_FILES=(
    "config/config.yaml"
    "config/config_multi_chain.yaml"
    "config/.env.example"
)

for config_file in "${CONFIG_FILES[@]}"; do
    if [ -f "$PROJECT_DIR/$config_file" ]; then
        print_status "PASS" "$config_file exists"
    else
        print_status "WARN" "$config_file is missing"
    fi
done

# Check Vault status if running
echo -e "\nChecking Vault status..."
if curl -s -o /dev/null http://localhost:8200/v1/sys/health; then
    print_status "PASS" "Vault service is accessible"
    
    # If VAULT_TOKEN is set, check Vault configuration
    if [ -n "$VAULT_TOKEN" ]; then
        echo "Checking Vault secrets..."
        VAULT_PATH=${VAULT_PATH:-"secret/on1builder"}
        
        if curl -s -H "X-Vault-Token: $VAULT_TOKEN" http://localhost:8200/v1/${VAULT_PATH} | grep -q "data"; then
            print_status "PASS" "Vault secrets accessible at $VAULT_PATH"
        else
            print_status "WARN" "Could not access Vault secrets at $VAULT_PATH"
        fi
    else
        print_status "INFO" "VAULT_TOKEN not set, skipping Vault secrets check"
    fi
else
    print_status "INFO" "Vault service is not running, skipping Vault checks"
fi

# Summarize findings
echo -e "\n============================================================"
echo "Security Audit Summary"
echo "============================================================"
echo "Complete the following steps to improve security:"
echo "1. Review warnings and fix identified issues"
echo "2. Ensure all secrets are stored in Vault"
echo "3. Run regular security updates"
echo "4. Implement proper key rotation"
echo "5. Review user permissions"
echo "============================================================"
echo "Audit completed on $(date)" 