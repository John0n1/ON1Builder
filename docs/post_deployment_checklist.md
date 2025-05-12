# Post-Deployment Checklist

## Directory Structure Verification
- [ ] Verify correct permissions on directories:
  ```
  config/          # 700 (rwx------)
  data/           # 755 (rwxr-xr-x)
  data/abi/       # 644 (rw-r--r--)
  data/ml/        # 644 (rw-r--r--)
  deploy/         # 755 (rwxr-xr-x)
  scripts/python/ # 755 (rwxr-xr-x)
  ```

## Configuration Verification
- [ ] Check config files exist and are properly configured:
  - [ ] `config/config.yaml`
  - [ ] `config/config_multi_chain.yaml`
  - [ ] `config/template.env`
- [ ] Verify no sensitive data in config files
- [ ] Confirm all secrets are stored in Vault

## Data Directory Setup
- [ ] Verify ABI files in `data/abi/`:
  - [ ] `erc20_abi.json`
  - [ ] `aave_flashloan_abi.json`
  - [ ] `aave_pool_abi.json`
  - [ ] `uniswap_abi.json`
  - [ ] `sushiswap_abi.json`
- [ ] Check ML directory setup in `data/ml/`:
  - [ ] `price_model.joblib`
  - [ ] `training_data.csv`

## Security Checks
- [ ] Run security audit script:
  ```bash
  ./deploy/security_audit.sh
  ```
- [ ] Verify Vault configuration:
  - [ ] Check Vault status
  - [ ] Verify token permissions
  - [ ] Test secret retrieval
- [ ] Check file permissions
- [ ] Verify network security settings

## Monitoring Setup
- [ ] Configure Grafana dashboards:
  - [ ] Import `dashboards/on1builder-multi-chain-dashboard.json`
  - [ ] Set up alerts
- [ ] Verify metrics endpoint:
  ```bash
  curl http://localhost:5001/metrics
  ```
- [ ] Test logging configuration:
  - [ ] Check log rotation
  - [ ] Verify log levels
  - [ ] Test alert notifications

## Backup Verification
- [ ] Test backup scripts:
  ```bash
  ./deploy/backup_config.sh
  ./deploy/backup_data.sh
  ```
- [ ] Verify backup restoration process
- [ ] Document backup locations

## Performance Testing
- [ ] Run load tests
- [ ] Monitor resource usage
- [ ] Check transaction processing speed
- [ ] Verify multi-chain operation

## Documentation
- [ ] Update deployment documentation
- [ ] Review security guidelines
- [ ] Document any custom configurations
- [ ] Update troubleshooting guide

## Regular Maintenance Schedule
- [ ] Set up key rotation schedule
- [ ] Configure automated updates
- [ ] Plan regular security audits
- [ ] Schedule performance reviews

## Emergency Procedures
- [ ] Test emergency shutdown:
  ```bash
  ./deploy/emergency_shutdown.sh
  ```
- [ ] Verify recovery procedures
- [ ] Document incident response steps
- [ ] Test backup restoration

## Final Verification
- [ ] Run integration tests
- [ ] Verify all services are running
- [ ] Check monitoring systems
- [ ] Test alerting system
