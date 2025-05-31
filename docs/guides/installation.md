# ON1Builder Installation Guide

This guide provides detailed instructions for installing ON1Builder in different environments and deployment scenarios.

## Prerequisites

Before installing ON1Builder, ensure your system meets the following requirements:

### System Requirements

- **CPU**: 4+ cores (8+ recommended for production)
- **RAM**: 8+ GB (16+ GB recommended for production)
- **Storage**: SSD with at least 100GB free space
- **Network**: Stable internet connection with low latency

### Software Requirements

- **Operating System**: Linux (Ubuntu 20.04+ recommended), macOS, or Windows with WSL2
- **Python**: Version 3.12 or higher
- **Docker**: Latest version (for containerized deployment)
- **Docker Compose**: Latest version (for multi-container orchestration)
- **Git**: For cloning the repository

## Installation Methods

ON1Builder can be installed and deployed in multiple ways:

1. [Local Development Installation](#local-development-installation)
2. [Production Installation](#production-installation)
3. [Docker Installation](#docker-installation)
4. [Multi-Chain Installation](#multi-chain-installation)

## Local Development Installation

For development and testing purposes:

### 1. Clone the Repository

```bash
git clone https://github.com/John0n1/ON1Builder.git
cd ON1Builder
```

### 2. Set Up Environment

```bash
# Copy the .env.example file
cp .env.example .env

# Edit the .env file with your configuration
nano .env
```

Configure the necessary environment variables:
- API keys for price data sources
- Blockchain RPC endpoints
- Wallet information

### 3. Install Dependencies Using Poetry (Recommended)

```bash
# Install poetry if not already installed
pip install poetry

# Install dependencies using the provided script
./setup_dev.sh

# Activate the virtual environment
poetry shell
```

### 4. Verify Installation

```bash
# Run the connection test
python -m on1builder test-connection --config configs/chains/config.yaml
```

## Production Installation

For production environments:

### 1. Clone the Repository

```bash
git clone https://github.com/John0n1/ON1Builder.git
cd ON1Builder
```

### 2. Set Up Environment

```bash
# Copy the .env.example file
cp .env.example .env

# Edit the .env file with your production configuration
nano .env
```

### 3. Set Correct Permissions

```bash
# Make scripts executable
chmod +x infra/bash/*.sh

# Set proper permissions for config files
chmod 600 .env
```

### 4. Run the Deployment Helper

```bash
./infra/bash/deploy_helper.sh
```

Select the appropriate deployment option from the interactive menu.

## Docker Installation

For containerized deployment:

### 1. Clone the Repository

```bash
git clone https://github.com/John0n1/ON1Builder.git
cd ON1Builder
```

### 2. Set Up Environment

```bash
# Copy the .env.example file
cp .env.example .env

# Edit the .env file with your configuration
nano .env
```

### 3. Build and Start the Docker Container

```bash
# Build the Docker image
docker build -t on1builder:latest .

# Run the container
docker run -d --name on1builder \
  --env-file .env \
  -v $(pwd)/configs:/app/configs \
  -v $(pwd)/data:/app/data \
  -p 5001:5001 \
  on1builder:latest
```

### 4. Verify the Installation

```bash
# Check container logs
docker logs on1builder
```

## Multi-Chain Installation

For running ON1Builder across multiple blockchains:

### 1. Follow the Standard Installation Steps

Complete either the [Production Installation](#production-installation) or [Docker Installation](#docker-installation) steps.

### 2. Configure Multi-Chain Settings

```bash
# Edit the multi-chain configuration file
nano configs/chains/config_multi_chain.yaml
```

Add the configuration for each blockchain you want to monitor.

### 3. Deploy the Multi-Chain Setup

```bash
# Using the deployment helper
./infra/bash/deploy_helper.sh

# Select option for Multi-Chain deployment
```

Alternatively, deploy directly:

```bash
./infra/bash/deploy_prod_multi_chain.sh
```

## Security Recommendations

1. **Private Key Management**:
   - Use environment variables for private keys
   - Consider using a secret management system like HashiCorp Vault

2. **Network Security**:
   - Run behind a firewall
   - Use VPN for remote access
   - Set up SSH key authentication

3. **Monitoring**:
   - Set up alert notifications
   - Monitor system resources
   - Implement log rotation

## Troubleshooting Installation Issues

### Common Issues

1. **Dependency Installation Errors**:
   ```bash
   pip install -r requirements.txt --no-cache-dir
   ```

2. **Permission Denied Errors**:
   ```bash
   chmod +x *.sh
   ```

3. **Docker Network Issues**:
   ```bash
   docker network inspect bridge
   ```

For more troubleshooting help, see the [Troubleshooting Guide](troubleshooting.md).

## Next Steps

After successful installation:

1. [Configure your system](configuration.md)
2. [Set up monitoring](monitoring.md)
3. [Run ON1Builder](running.md)

For detailed API configuration or custom development, refer to the [Configuration Reference](../reference/configuration_reference.md).
