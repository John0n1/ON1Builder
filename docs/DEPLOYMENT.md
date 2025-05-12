# ON1Builder Deployment Guide

This guide details the process of deploying ON1Builder in a production environment.

## Directory Structure Overview

```
ON1Builder/
├── config/                   # Configuration files
│   ├── config.yaml          # Main configuration
│   ├── config_multi_chain.yaml  # Multi-chain configuration
│   └── template.env         # Environment template
├── deploy/                  # Deployment scripts
│   ├── deploy_prod.sh       # Single-chain deployment
│   ├── deploy_prod_multi_chain.sh  # Multi-chain deployment
│   ├── vault_init.sh        # Vault initialization
│   └── vault_init_multi_chain.sh   # Multi-chain Vault setup
└── scripts/python/          # Application code
```

## Prerequisites

1. System Requirements:
   - Linux server (Ubuntu 20.04 or later recommended)
   - Python 3.12+
   - Docker and Docker Compose
   - HashiCorp Vault
   - Sufficient storage for blockchain data if running local nodes

2. Network Requirements:
   - RPC/WebSocket endpoints for each chain
   - Stable internet connection
   - Firewall configured for required ports

## Configuration Setup

1. Create configuration directory:
```bash
mkdir -p config
```

2. Copy configuration templates:
```bash
cp template.env config/template.env
cp config.yaml config/config.yaml
cp config_multi_chain.yaml config/config_multi_chain.yaml
```

3. Edit configurations:
   - Update `config/config.yaml` or `config/config_multi_chain.yaml`
   - Create environment file from template:
     ```bash
     cp config/template.env config/.env
     ```
   - Edit `.env` with your specific values

## Vault Setup

1. Initialize Vault:
```bash
cd deploy
./vault_init.sh  # For single chain
# OR
./vault_init_multi_chain.sh  # For multi-chain setup
```

2. Store secrets in Vault:
```bash
# Example using vault CLI
vault kv put secret/on1builder/chain_1 \
  WALLET_KEY="your-private-key" \
  HTTP_ENDPOINT="your-rpc-endpoint" \
  WEBSOCKET_ENDPOINT="your-ws-endpoint"
```

## Deployment Process

### Single Chain Deployment

1. Run deployment script:
```bash
cd deploy
./deploy_prod.sh
```

### Multi-Chain Deployment

1. Run multi-chain deployment script:
```bash
cd deploy
./deploy_prod_multi_chain.sh
```

### Verification

1. Check service status:
```bash
docker-compose ps
```

2. View logs:
```bash
docker-compose logs -f app
```

3. Access monitoring:
   - Grafana: http://your-server:3000
   - Metrics endpoint: http://your-server:5001/metrics

## Post-Deployment

1. Security checks:
   - Verify Vault is properly sealed
   - Check firewall rules
   - Review access logs

2. Setup monitoring:
   - Configure Grafana alerts
   - Set up log rotation
   - Enable metrics collection

3. Regular maintenance:
   - Key rotation schedule
   - Backup procedures
   - Update strategy

## Troubleshooting

### Common Issues

1. Configuration Issues:
   - Check paths in config files
   - Verify environment variables
   - Ensure correct permissions

2. Connection Issues:
   - Verify RPC endpoints
   - Check network connectivity
   - Review firewall rules

3. Vault Issues:
   - Check Vault status
   - Verify token permissions
   - Ensure proper initialization

## Maintenance

### Regular Tasks

1. Daily:
   - Monitor logs
   - Check metrics
   - Verify balances

2. Weekly:
   - Update dependencies
   - Backup configurations
   - Review security logs

3. Monthly:
   - Rotate keys
   - Update documentation
   - Performance review

### Backup Procedures

1. Configuration backup:
```bash
tar -czf backup_config.tar.gz config/
```

2. Data backup:
```bash
tar -czf backup_data.tar.gz data/
```

3. Vault backup (if applicable)

## Security Considerations

1. Access Control:
   - Limit SSH access
   - Use strong passwords
   - Implement 2FA where possible

2. Network Security:
   - Configure firewalls
   - Use VPN for remote access
   - Monitor network traffic

3. Key Management:
   - Regular key rotation
   - Secure key storage
   - Access logging

## Monitoring Setup

1. Grafana:
   - Import dashboards
   - Configure alerts
   - Set up users

2. Metrics:
   - Configure Prometheus
   - Set up exporters
   - Define alert rules

3. Logging:
   - Configure log rotation
   - Set up log aggregation
   - Define log levels

## Scaling Considerations

1. Hardware:
   - Monitor resource usage
   - Plan for expansion
   - Configure backups

2. Network:
   - Load balancing
   - Failover setup
   - Bandwidth monitoring

3. Database:
   - Connection pooling
   - Query optimization
   - Backup strategy

## Additional Resources

- [Security Guidelines](SECURITY.md)
- [Post-Deployment Checklist](post_deployment_checklist.md)
- [Architecture Overview](architecture.md)
