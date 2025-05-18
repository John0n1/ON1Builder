#!/bin/bash
# ON1Builder Deployment Helper Script

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Print banner
echo "============================================================"
echo "ON1Builder Deployment Helper"
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

# Show menu function
show_menu() {
    echo ""
    echo "Please select an option:"
    echo "1) Deploy Single Chain"
    echo "2) Deploy Multi-Chain"
    echo "3) Security Audit"
    echo "4) Backup Configuration"
    echo "5) Backup Data"
    echo "6) Set Proper Permissions"
    echo "7) Setup Cron Jobs"
    echo "8) Verify Deployment"
    echo "9) Test Alert System"
    echo "10) Build and Push Docker Image"
    echo "11) Verify Integration"
    echo "12) Emergency Shutdown"
    echo "0) Exit"
    echo ""
    read -p "Enter your choice: " choice
    
    case $choice in
        1) deploy_single_chain ;;
        2) deploy_multi_chain ;;
        3) security_audit ;;
        4) backup_config ;;
        5) backup_data ;;
        6) set_permissions ;;
        7) setup_cron ;;
        8) verify_deployment ;;
        9) test_alert ;;
        10) build_docker ;;
        11) verify_integration ;;
        12) emergency_shutdown ;;
        0) exit 0 ;;
        *) print_error "Invalid option"; show_menu ;;
    esac
}

# Function to check .env file
check_env_file() {
    if [ ! -f "$PROJECT_DIR/.env" ]; then
        print_warning "No .env file found. Creating from template..."
        cp "$PROJECT_DIR/template.env" "$PROJECT_DIR/.env"
        print_info "Please edit .env file with your configuration before continuing."
        read -p "Press Enter to continue after editing the .env file..."
    fi
}

# Function to deploy single chain
deploy_single_chain() {
    print_info "Deploying single chain setup..."
    check_env_file
    
    # Confirm with user
    read -p "This will deploy the ON1Builder for a single chain. Continue? (y/n): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        print_info "Deployment cancelled."
        return
    fi
    
    # Run deployment script
    bash "$PROJECT_DIR/deploy/deploy_prod.sh"
    
    print_success "Single chain deployment completed."
    show_menu
}

# Function to deploy multi-chain
deploy_multi_chain() {
    print_info "Deploying multi-chain setup..."
    check_env_file
    
    # Check if CHAINS environment variable is set
    if ! grep -q "CHAINS=" "$PROJECT_DIR/.env"; then
        print_warning "CHAINS variable not found in .env file."
        read -p "Enter comma-separated chain IDs (e.g., 1,137,42161): " chains
        echo "CHAINS=$chains" >> "$PROJECT_DIR/.env"
    fi
    
    # Confirm with user
    read -p "This will deploy the ON1Builder for multiple chains. Continue? (y/n): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        print_info "Deployment cancelled."
        return
    fi
    
    # Run deployment script
    bash "$PROJECT_DIR/deploy/deploy_prod_multi_chain.sh"
    
    print_success "Multi-chain deployment completed."
    show_menu
}

# Function for security audit
security_audit() {
    print_info "Running security audit..."
    bash "$PROJECT_DIR/deploy/security_audit.sh"
    
    print_success "Security audit completed."
    show_menu
}

# Function to backup configuration
backup_config() {
    print_info "Backing up configuration..."
    
    # Ask for backup directory
    read -p "Enter backup directory (default: ./backups/config): " backup_dir
    backup_dir=${backup_dir:-"$PROJECT_DIR/backups/config"}
    
    # Export variable for the backup script
    export BACKUP_DIR="$backup_dir"
    
    # Run backup script
    bash "$PROJECT_DIR/deploy/backup_config.sh"
    
    print_success "Configuration backup completed."
    show_menu
}

# Function to backup data
backup_data() {
    print_info "Backing up data..."
    
    # Ask for backup directory
    read -p "Enter backup directory (default: ./backups/data): " backup_dir
    backup_dir=${backup_dir:-"$PROJECT_DIR/backups/data"}
    
    # Export variable for the backup script
    export BACKUP_DIR="$backup_dir"
    
    # Run backup script
    bash "$PROJECT_DIR/deploy/backup_data.sh"
    
    print_success "Data backup completed."
    show_menu
}

# Function to set permissions
set_permissions() {
    print_info "Setting proper file permissions..."
    bash "$PROJECT_DIR/deploy/set_permissions.sh"
    
    print_success "File permissions set."
    show_menu
}

# Function to setup cron jobs
setup_cron() {
    print_info "Setting up cron jobs..."
    bash "$PROJECT_DIR/deploy/cron_setup.sh"
    
    print_success "Cron jobs setup completed."
    show_menu
}

# Function to verify deployment
verify_deployment() {
    print_info "Verifying deployment..."
    
    if [ -f "$PROJECT_DIR/.env" ]; then
        source "$PROJECT_DIR/.env"
    fi
    
    if [ -n "$CHAINS" ]; then
        bash "$PROJECT_DIR/deploy/verify_multi_chain.sh"
    else
        print_info "Checking API health..."
        curl -s http://localhost:5001/healthz
        
        print_info "Checking system status..."
        curl -s http://localhost:5001/status
    fi
    
    print_success "Verification completed."
    show_menu
}

# Function to test alert system
test_alert() {
    print_info "Testing alert system..."
    
    read -p "Enter alert message (default: Test alert from deployment helper): " message
    message=${message:-"Test alert from deployment helper"}
    
    read -p "Enter alert level (INFO/WARN/ERROR, default: INFO): " level
    level=${level:-"INFO"}
    
    curl -s -X POST -H "Content-Type: application/json" \
         -d "{\"message\":\"$message\",\"level\":\"$level\"}" \
         http://localhost:5001/api/test-alert
    
    print_success "Alert test sent."
    show_menu
}

# Function to build and push Docker image
build_docker() {
    print_info "Building and pushing Docker image..."
    
    read -p "Enter Docker tag (default: latest): " tag
    tag=${tag:-"latest"}
    export DOCKER_TAG="$tag"
    
    read -p "Skip pushing to registry? (y/n, default: n): " skip_push
    if [[ "$skip_push" =~ ^[Yy]$ ]]; then
        export SKIP_PUSH=1
    fi
    
    bash "$PROJECT_DIR/deploy/build_and_push.sh"
    
    print_success "Docker build process completed."
    show_menu
}

# Function for emergency shutdown
emergency_shutdown() {
    print_info "EMERGENCY SHUTDOWN PROCEDURE"
    print_warning "This will immediately stop all services and secure funds."
    print_warning "This should only be used in emergency situations."
    
    read -p "Are you ABSOLUTELY SURE you want to proceed? (yes/NO): " confirm
    if [ "$confirm" != "yes" ]; then
        print_info "Emergency shutdown aborted."
        show_menu
        return
    fi
    
    bash "$PROJECT_DIR/deploy/emergency_shutdown.sh"
    
    print_success "Emergency shutdown completed."
    exit 0
}

# Function to verify integration
verify_integration() {
    print_info "Verifying integration between components..."
    
    # Run the verification script
    bash "$PROJECT_DIR/deploy/verify_integration.sh"
    
    print_success "Integration verification completed."
    show_menu
}

# Main execution
if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
    echo "Usage: $0 [OPTION]"
    echo "Options:"
    echo "  --single       Deploy single chain"
    echo "  --multi        Deploy multi-chain"
    echo "  --security     Run security audit"
    echo "  --backup-config Backup configuration"
    echo "  --backup-data   Backup data"
    echo "  --permissions  Set proper permissions"
    echo "  --cron         Setup cron jobs"
    echo "  --verify       Verify deployment"
    echo "  --alert        Test alert system"
    echo "  --build        Build and push Docker image"
    echo "  --integration  Verify integration between components"
    echo "  --emergency    Emergency shutdown"
    echo "  --help, -h     Show this help"
    exit 0
fi

# Direct command line options
if [ $# -gt 0 ]; then
    case "$1" in
        --single) deploy_single_chain ;;
        --multi) deploy_multi_chain ;;
        --security) security_audit ;;
        --backup-config) backup_config ;;
        --backup-data) backup_data ;;
        --permissions) set_permissions ;;
        --cron) setup_cron ;;
        --verify) verify_deployment ;;
        --alert) test_alert ;;
        --build) build_docker ;;
        --integration) verify_integration ;;
        --emergency) emergency_shutdown ;;
        *) print_error "Unknown option: $1"; exit 1 ;;
    esac
else
    # Show interactive menu
    show_menu
fi 