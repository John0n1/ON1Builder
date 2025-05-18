# ON1Builder Usage Guide

This guide provides detailed instructions for using the deployment scripts and utilities included with ON1Builder.

## Table of Contents

1. [Setup and Configuration](#setup-and-configuration)
2. [Deployment Scripts](#deployment-scripts)
3. [Security Tools](#security-tools)
4. [Backup and Recovery](#backup-and-recovery)
5. [Monitoring and Maintenance](#monitoring-and-maintenance)
6. [Troubleshooting](#troubleshooting)

## Setup and Configuration

### Initial Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/John0n1/ON1Builder.git
   cd ON1Builder
   ```

2. Set proper file permissions:
   ```bash
   ./deploy/set_permissions.sh
   ```

3. Create your environment file:
   ```bash
   cp template.env .env
   ```

4. Edit the `.env` file with your specific configuration values.

### Configuration Files

Key configuration files:

- `config/config.yaml` - Single-chain configuration
- `config/config_multi_chain.yaml` - Multi-chain configuration
- `.env` - Environment variables for sensitive information

## Deployment Scripts

### Deployment Helper

The simplest way to deploy ON1Builder is to use the deployment helper script:

```bash
./deploy/deploy_helper.sh
```

This interactive script will guide you through the deployment process and offers the following options:

1. Deploy Single Chain
2. Deploy Multi-Chain
3. Security Audit
4. Backup Configuration
5. Backup Data
6. Set Proper Permissions
7. Setup Cron Jobs
8. Verify Deployment
9. Test Alert System
10. Build and Push Docker Image
11. Emergency Shutdown

You can also run specific operations directly:

```bash
./deploy/deploy_helper.sh --single    # Deploy single chain
./deploy/deploy_helper.sh --multi     # Deploy multi-chain
./deploy/deploy_helper.sh --security  # Run security audit
```

### Single Chain Deployment

For deploying a single chain instance manually:

```bash
./deploy/deploy_prod.sh
```

This will:
1. Initialize HashiCorp Vault
2. Build and start the Docker containers
3. Configure monitoring with Prometheus and Grafana

### Multi-Chain Deployment

For deploying with multiple chains manually:

```bash
./deploy/deploy_prod_multi_chain.sh
```

### Docker Image Management

Build and push the Docker image to a registry:

```bash
./deploy/build_and_push.sh
```

Available environment variables:
- `DOCKER_REGISTRY` - Registry hostname (default: "ghcr.io")
- `DOCKER_REPOSITORY` - Image repository name (default: "john0n1/on1builder")
- `DOCKER_TAG` - Image tag (default: "latest")
- `SKIP_PUSH` - Set to anything to skip pushing to registry
- `PUSH_LATEST` - Set to anything to also push as latest tag

### Vault Management

Initialize HashiCorp Vault for secure secret storage:

```bash
./deploy/vault_init.sh         # For single chain
./deploy/vault_init_multi_chain.sh   # For multi-chain
```

## Security Tools

### Permissions Setup

Set proper file permissions:

```bash
./deploy/set_permissions.sh
```

### Security Audit

Run a comprehensive security audit:

```bash
./deploy/security_audit.sh
```

This checks:
- Directory permissions
- Sensitive information in files
- Configuration file security
- Docker security settings
- Vault status

### Emergency Shutdown

In case of emergency, immediately stop all services and secure funds:

```bash
./deploy/emergency_shutdown.sh
```

**Warning**: This is for emergencies only and will immediately transfer funds to the emergency wallet.

## Backup and Recovery

### Configuration Backup

Backup all configuration files:

```bash
./deploy/backup_config.sh
```

Environment variables:
- `BACKUP_DIR` - Custom backup directory
- `RETENTION_DAYS` - Days to keep backups (default: 30)

### Data Backup

Backup all data files and ML models:

```bash
./deploy/backup_data.sh
```

### Scheduled Backups

To set up scheduled backups:

```bash
./deploy/cron_setup.sh
```

## Monitoring and Maintenance

### Verify Deployment

Verify your deployment is working correctly:

```bash
./deploy/verify_multi_chain.sh
```

### Monitoring

Access the monitoring dashboards:
- Grafana: http://localhost:3000
- Metrics API: http://localhost:5001/metrics

### API Endpoints

Key API endpoints:
- Health check: `GET /healthz`
- Metrics: `GET /metrics`
- Bot status: `GET /status`
- Start bot: `POST /start`
- Stop bot: `POST /stop`
- Test alert: `POST /api/test-alert`
- Simulate transaction: `POST /api/simulate-transaction`

## Alert System

The alert system provides real-time notifications through Slack and email. For detailed information, see [Alert System Documentation](alert_system.md).

## Transaction Simulation

Before executing transactions, you can simulate them to estimate profitability and gas costs. For more details, see [Transaction Simulation Documentation](transaction_simulation.md).

## Troubleshooting

### Common Issues

#### Connection Problems

If you're experiencing connection issues:

```bash
# Check the API health
curl http://localhost:5001/healthz

# View application logs
docker logs on1builder
```

#### Permission Errors

If you encounter permission errors during startup:

```bash
# Reset permissions
./deploy/set_permissions.sh
```

#### Vault Issues

If Vault isn't accessible:

```bash
# Check Vault status
docker logs on1builder-vault

# Re-initialize Vault
./deploy/vault_init.sh
```

### Getting Support

For additional support:
- Open an issue on GitHub
- Check the documentation in the `docs` directory
- Review the logs in `data/logs` 