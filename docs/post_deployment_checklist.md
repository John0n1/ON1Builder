# ON1Builder Post-Deployment Checklist

## Initial Checks

- [ ] Verify all Docker containers are running
  ```bash
  docker ps
  ```

- [ ] Check the API health endpoint
  ```bash
  curl http://localhost:5001/healthz
  ```

- [ ] Validate metrics endpoint is accessible
  ```bash
  curl http://localhost:5001/metrics
  ```

- [ ] Confirm Grafana dashboard is accessible
  ```bash
  curl http://localhost:3000
  ```

- [ ] Run the deployment helper for interactive verification
  ```bash
  ./deploy/deploy_helper.sh --verify
  ```

## Security Verification

- [ ] Run security audit script
  ```bash
  ./deploy/security_audit.sh
  ```

- [ ] Verify permissions are set correctly
  ```bash
  ./deploy/set_permissions.sh
  ```

- [ ] Check Vault status
  ```bash
  curl -s http://localhost:8200/v1/sys/health | grep "initialized"
  ```

- [ ] Verify all sensitive keys are stored in Vault
  ```bash
  export VAULT_TOKEN=your-token
  export VAULT_ADDR=http://localhost:8200
  vault kv list secret/on1builder
  ```

- [ ] Test the alert system with the deployment helper
  ```bash
  ./deploy/deploy_helper.sh --alert
  ```

## Configuration Validation

- [ ] Verify environment variables are loaded
  ```bash
  docker exec on1builder env | grep HTTP_ENDPOINT
  ```

- [ ] Check if chains are configured correctly
  ```bash
  ./deploy/verify_multi_chain.sh
  ```

- [ ] Validate API configuration
  ```bash
  curl http://localhost:5001/status
  ```

## Data Integrity

- [ ] Verify ABI files are accessible
  ```bash
  ls -la data/abi
  ```

- [ ] Check ML model files are present
  ```bash
  ls -la data/ml
  ```

- [ ] Create initial configuration backup using the helper script
  ```bash
  ./deploy/deploy_helper.sh --backup-config
  ```

- [ ] Create initial data backup using the helper script
  ```bash
  ./deploy/deploy_helper.sh --backup-data
  ```

## Monitoring Setup

- [ ] Ensure logs are being generated
  ```bash
  tail -f data/logs/app.log
  ```

- [ ] Set up Grafana alerts
  1. Navigate to http://localhost:3000/alerting/list
  2. Create alerts for low balance and errors

- [ ] Set up recurring backups via cron with helper script
  ```bash
  ./deploy/deploy_helper.sh --cron
  ```

## Performance Testing

- [ ] Run the bot in dry-run mode
  ```bash
  curl -X POST http://localhost:5001/start
  ```

- [ ] Monitor resource usage
  ```bash
  docker stats
  ```

- [ ] Test transaction simulation
  ```bash
  curl -X POST -H "Content-Type: application/json" -d '{"tx_hash":"0x123...","chain_id":"1"}' http://localhost:5001/api/simulate-transaction
  ```

- [ ] Test alert system
  ```bash
  curl -X POST -H "Content-Type: application/json" -d '{"message":"Test alert from post-deployment checklist","level":"INFO"}' http://localhost:5001/api/test-alert
  ```

## Chain-Specific Verification

For each deployed chain:

- [ ] Verify RPC endpoint connectivity
  ```bash
  curl -X POST -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' $CHAIN_X_HTTP_ENDPOINT
  ```

- [ ] Check balance of configured wallet
  ```bash
  curl -X GET http://localhost:5001/metrics | grep wallet_balance
  ```

- [ ] Verify network congestion monitoring
  ```bash
  curl -X GET http://localhost:5001/metrics | grep network_congestion
  ```

## Error Handling

- [ ] Test emergency shutdown procedure (in development only)
  ```bash
  # Only test this in a development environment
  # ./deploy/deploy_helper.sh --emergency
  ```

- [ ] Verify logs contain appropriate information
  ```bash
  grep ERROR data/logs/app.log
  ```

## Final Steps

- [ ] Document deployed version information
  ```bash
  docker exec on1builder python --version
  docker exec on1builder pip list | grep web3
  ```

- [ ] Create a backup of the entire deployment
  ```bash
  ./deploy/deploy_helper.sh --backup-config
  ./deploy/deploy_helper.sh --backup-data
  ```

- [ ] Set up regular security audits in cron
  ```bash
  echo "0 1 * * 1 cd /path/to/ON1Builder && ./deploy/security_audit.sh >> /var/log/on1builder_security_audit.log 2>&1" | crontab -
  ```

- [ ] Make the deployment helper script executable
  ```bash
  chmod +x ./deploy/deploy_helper.sh
  ```
