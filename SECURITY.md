# Security Policy and Guidelines

## Overview

This document outlines security policies and best practices for deploying and maintaining ON1Builder. Given the financial nature of MEV operations, security is paramount.

## Directory Structure Security

```
ON1Builder/
├── config/                   # Configuration (restricted access)
│   └── .env.example         # Never commit actual .env files
├── data/                    # Data directory (controlled access)
│   ├── abi/                # Contract ABIs
│   └── ml/                 # ML models and data
├── deploy/                  # Deployment scripts
└── scripts/python/          # Application code
```

## Critical Security Rules

1. **Never commit sensitive data:**
   - Private keys
   - API keys
   - RPC endpoints
   - Production configurations
   - Actual .env files

2. **Use HashiCorp Vault:**
   - Store all secrets in Vault
   - Rotate Vault tokens regularly
   - Use separate Vault paths for different environments
   - Example path structure:
     ```
     secret/
     ├── on1builder/
     │   ├── development/
     │   ├── staging/
     │   └── production/
     │       ├── chain_1/
     │       └── chain_137/
     ```

3. **File Permissions:**
   ```bash
   # Set restrictive permissions on config directory
   chmod 700 config/
   chmod 600 config/*

   # Set appropriate permissions on data directory
   chmod 755 data/
   chmod 644 resources/abi/*
   chmod 644 data/ml/*
   ```

## Environment Security

### Production Environment

1. **System Hardening:**
   ```bash
   # Update system packages
   apt update && apt upgrade -y

   # Install security tools
   apt install fail2ban ufw auditd

   # Configure firewall
   ufw default deny incoming
   ufw default allow outgoing
   ufw allow ssh
   ufw allow 5001/tcp  # API port
   ufw allow 3000/tcp  # Grafana
   ufw enable
   ```

2. **User Management:**
   ```bash
   # Create service user
   useradd -r -s /bin/false on1builder

   # Set proper ownership
   chown -R on1builder:on1builder /path/to/ON1Builder
   ```

### Docker Security

1. **Container Security:**
   ```yaml
   # docker-compose.multi-chain.yml security settings
   services:
     app:
       user: "on1builder"
       read_only: true
       security_opt:
         - no-new-privileges:true
       volumes:
         - type: bind
           source: ./config
           target: /app/config
           read_only: true
   ```

2. **Image Security:**
   - Use specific version tags
   - Scan images for vulnerabilities
   - Use minimal base images

## Network Security

1. **RPC Endpoint Security:**
   - Use authenticated endpoints
   - Implement rate limiting
   - Monitor for suspicious activity

2. **API Security:**
   ```python
   # Example API security configuration in app_multi_chain.py
   from flask_limiter import Limiter
   from flask_limiter.util import get_remote_address

   limiter = Limiter(
       app,
       key_func=get_remote_address,
       default_limits=["200 per day", "50 per hour"]
   )
   ```

## Key Management

1. **Wallet Key Rotation:**
   ```bash
   # Script location: deploy/rotate_keys.sh
   # Rotation schedule: Every 30 days
   0 0 1 * * /path/to/ON1Builder/deploy/rotate_keys.sh
   ```

2. **API Key Security:**
   - Rotate API keys monthly
   - Use separate keys per environment
   - Monitor API key usage

## Monitoring and Alerts

1. **Security Monitoring:**
   ```yaml
   # Grafana alert example
   alerts:
     - name: Unauthorized Access Attempt
       condition: count(unauthorized_access) > 5
       interval: 5m
       notifications:
         - slack
         - email
   ```

2. **Log Monitoring:**
   ```python
   # Example logging configuration
   LOGGING = {
       'handlers': {
           'security_file': {
               'class': 'logging.FileHandler',
               'filename': 'data/logs/security.log',
               'formatter': 'detailed',
               'level': 'WARNING',
           }
       }
   }
   ```

## Incident Response

1. **Emergency Shutdown:**
   ```bash
   # Location: deploy/emergency_shutdown.sh
   #!/bin/bash
   # Immediate bot shutdown and fund securing
   docker-compose down
   # Additional security measures...
   ```

2. **Recovery Procedures:**
   - Document in `docs/incident_response.md`
   - Regular recovery drills
   - Backup verification

## Security Checklist

### Daily Checks
- [ ] Monitor system logs
- [ ] Check unauthorized access attempts
- [ ] Verify Vault status
- [ ] Monitor transaction patterns

### Weekly Checks
- [ ] Review API usage patterns
- [ ] Check system updates
- [ ] Verify backup integrity
- [ ] Review security alerts

### Monthly Checks
- [ ] Rotate API keys
- [ ] Update system packages
- [ ] Review access logs
- [ ] Test recovery procedures

## Reporting Security Issues

1. **Responsible Disclosure:**
   - Email: security@example.com
   - Do not disclose publicly
   - Include detailed information

2. **Bug Bounty Program:**
   - Scope defined in `SECURITY.md`
   - Rewards based on severity
   - Responsible disclosure required

## Security Updates

1. **System Updates:**
   ```bash
   # Location: deploy/update_system.sh
   #!/bin/bash
   apt update
   apt upgrade -y
   # Additional security patches...
   ```

2. **Dependency Updates:**
   ```bash
   # Regular dependency updates
   pip install --upgrade -r requirements.txt
   ```

## Compliance

1. **Audit Logging:**
   ```python
   # Example audit log configuration
   AUDIT_LOG_CONFIG = {
       'path': 'data/logs/audit.log',
       'retention': '90 days',
       'format': 'json'
   }
   ```

2. **Access Control:**
   - Role-based access
   - Audit trails
   - Regular access reviews

## Additional Resources

- [OWASP Smart Contract Security](https://owasp.org/www-project-smart-contract-security/)
- [Ethereum Security Best Practices](https://ethereum.org/en/developers/docs/smart-contracts/security/)
- [Docker Security](https://docs.docker.com/engine/security/)
