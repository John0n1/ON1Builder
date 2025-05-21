<!-- [MermaidChart: 32f1a0c0-2ee4-4776-aeeb-e7899bb145ac] -->

# Architecture Overview

This document provides a comprehensive overview of the ON1Builder architecture, including how components interact and the system's workflow.

## High-Level Architecture

ON1Builder follows a modular architecture designed for high performance, reliability, and extensibility across multiple blockchains.

```mermaid
flowchart TB
    subgraph ON1Builder
        CoreSystem["Core System"]
        Monitoring["Monitoring System"]
        ChainWorkers["Chain Workers"]
        SafetyNet["Safety Net"]
        BlockchainInterface["Blockchain Interface"]
        
        CoreSystem <--> ChainWorkers
        ChainWorkers --> SafetyNet
        SafetyNet <--> BlockchainInterface
        Monitoring --> CoreSystem
        Monitoring --> ChainWorkers
        
        subgraph CoreComponents
            direction LR
            MainCore["MainCore"]
            MultiChainCore["MultiChainCore"]
            TransactionCore["TransactionCore"]
            NonceCore["NonceCore"]
            
            MainCore --- MultiChainCore
            MultiChainCore --- TransactionCore
            TransactionCore --- NonceCore
        end
        
        CoreSystem --- CoreComponents
    end
    
    Blockchain[(Blockchain Networks)]
    BlockchainInterface <--> Blockchain
```

## Core Components

### MainCore

The `MainCore` is the central component that bootstraps and coordinates all other components. It:

- Manages the AsyncIO event loop
- Initializes all components
- Handles startup and shutdown sequences
- Maintains the application lifecycle

### MultiChainCore

For multi-chain deployments, the `MultiChainCore` extends `MainCore` to manage parallel operations across multiple blockchains. It:

- Creates and manages blockchain-specific workers
- Coordinates cross-chain operations
- Provides unified interfaces for interacting with multiple chains

### ChainWorker

Each `ChainWorker` handles blockchain-specific operations for a single chain. It:

- Connects to blockchain nodes
- Monitors blocks and transactions
- Executes blockchain-specific strategies
- Reports metrics and status

### TransactionCore

Handles all transaction-related operations:

- Building transaction objects
- Signing transactions with wallet keys
- Estimating gas and costs
- Simulating transactions before execution
- Submitting transactions to the network
- Tracking transaction status

### NonceCore

Manages transaction nonces to ensure proper transaction ordering:

- Tracks current nonce values
- Prevents nonce conflicts
- Handles nonce recovery in error cases

### Safety Net

Implements safeguards to protect against risks:

- Transaction validation before execution
- Profitability checks
- Gas price limits and controls
- Error handling and recovery procedures

### Monitoring

Provides comprehensive monitoring capabilities:

- Logging all system activities
- Prometheus metrics
- Health check endpoints
- Alerting through multiple channels

## Data Flow

```mermaid
sequenceDiagram
    participant Config as Configuration
    participant Core as MainCore
    participant Chain as ChainWorker
    participant TX as TransactionCore
    participant Safety as SafetyNet
    participant Blockchain as Blockchain Network
    participant Monitor as Monitoring System

    Note over Config,Monitor: Initialization Phase
    Config->>Core: Load configuration
    Core->>Chain: Initialize workers
    Chain->>Blockchain: Establish connections
    Core->>Monitor: Setup monitoring

    Note over Config,Monitor: Operation Phase
    Blockchain->>Chain: Blockchain events
    Chain->>Chain: Identify opportunities
    Chain->>TX: Request transaction build
    TX->>TX: Build and simulate transaction
    TX->>Safety: Perform safety checks
    alt Is Safe and Profitable
        Safety->>TX: Approve transaction
        TX->>Blockchain: Execute transaction
        Blockchain-->>TX: Transaction result
        TX->>Monitor: Log result
    else Failed Checks
        Safety->>TX: Reject transaction
        TX->>Monitor: Log rejection reason
    end

    Note over Config,Monitor: Monitoring (Continuous)
    Chain->>Monitor: Update metrics
    TX->>Monitor: Track transaction status
    Monitor->>Monitor: Trigger alerts if needed
```

1. **Initialization**:
   - Configuration loaded
   - Connections established to blockchains
   - Components initialized

2. **Operation**:
   - Blockchain events monitored
   - Opportunities identified by strategy components
   - Transactions built and simulated by TransactionCore
   - Safety checks performed by SafetyNet
   - Profitable transactions executed
   - Results tracked and recorded

3. **Monitoring**:
   - All activities logged
   - Metrics updated in real-time
   - Alerts triggered based on conditions
   - Health status maintained

## System Workflows

### Transaction Workflow

```mermaid
flowchart LR
    A[Opportunity Detection] --> B[Transaction Creation]
    B --> C[Safety Checks]
    C --> D[Transaction Execution]
    D --> E[Transaction Monitoring]
    E --> F[Result Tracking]
    
    style A fill:#f9f,stroke:#333,stroke-width:2px
    style C fill:#bbf,stroke:#333,stroke-width:2px
    style D fill:#bfb,stroke:#333,stroke-width:2px
    style F fill:#fbf,stroke:#333,stroke-width:2px
```

### Multi-Chain Workflow

```mermaid
flowchart TB
    Main[MultiChainCore] --> Workers
    
    subgraph Workers
        direction LR
        C1[Chain 1 Worker] 
        C2[Chain 2 Worker]
        C3[Chain N Worker]
    end
    
    C1 --> B1[(Blockchain 1)]
    C2 --> B2[(Blockchain 2)]
    C3 --> B3[(Blockchain N)]
    
    style Main fill:#f9f,stroke:#333,stroke-width:2px
    style Workers fill:#dfd,stroke:#333,stroke-width:1px
    style B1 fill:#bbf,stroke:#333,stroke-width:2px
    style B2 fill:#bbf,stroke:#333,stroke-width:2px
    style B3 fill:#bbf,stroke:#333,stroke-width:2px
```

## Deployment Architecture

ON1Builder supports multiple deployment configurations:

### Single-Node Deployment

All components run on a single server or container.

```mermaid
flowchart TB
    subgraph Server
        Core["ON1Builder Core"]
        Monitor["Monitoring<br/>(Prometheus, Grafana)"]
        
        Core <--> Monitor
    end
    
    style Server fill:#f5f5f5,stroke:#333,stroke-width:1px
    style Core fill:#bbf,stroke:#333,stroke-width:2px
    style Monitor fill:#bfb,stroke:#333,stroke-width:2px
```

### Distributed Deployment

Components distributed across multiple servers:

```mermaid
flowchart TB
    subgraph ControlNode["Control Node"]
        Manager["ON1Builder Manager"]
    end
    
    subgraph MonitorNode["Monitoring Node"]
        Prometheus["Prometheus"]
        Grafana["Grafana"]
        Prometheus --- Grafana
    end
    
    subgraph WorkerNodes["Worker Nodes"]
        Worker1["Worker 1<br/>(Chain A)"]
        Worker2["Worker 2<br/>(Chain B)"]
    end
    
    Manager <--> Prometheus
    Manager <--> Worker1
    Manager <--> Worker2
    Worker1 --> Prometheus
    Worker2 --> Prometheus
    
    style ControlNode fill:#f9f9f9,stroke:#333,stroke-width:1px
    style MonitorNode fill:#f9f9f9,stroke:#333,stroke-width:1px
    style WorkerNodes fill:#f9f9f9,stroke:#333,stroke-width:1px
    style Manager fill:#bbf,stroke:#333,stroke-width:2px
    style Prometheus fill:#bfb,stroke:#333,stroke-width:2px
    style Worker1 fill:#fbb,stroke:#333,stroke-width:2px
    style Worker2 fill:#fbb,stroke:#333,stroke-width:2px
```

## Security Architecture

```mermaid
flowchart TB
    subgraph NetworkSecurity["Network Isolation Layer"]
        VPN["VPN/Private Network"]
        Firewall["Firewall Rules"]
        AccessControl["API Access Controls"]
    end
    
    subgraph SecretManagement["Secret Management"]
        Vault["HashiCorp Vault"]
        EnvVar["Environment Variables"]
        KeyRotation["Credential Rotation"]
    end
    
    subgraph TxSecurity["Transaction Security"]
        Simulation["Transaction Simulation"]
        GasLimits["Gas Price Limits"]
        ProfitChecks["Profitability Checks"]
        SlippageProtection["Slippage Protection"]
    end
    
    subgraph AuditMonitor["Auditing & Monitoring"]
        Logging["Secure Logging"]
        Alerts["Security Alerts"]
        AuditTrail["Audit Trail"]
    end
    
    NetworkSecurity --> SecretManagement
    SecretManagement --> TxSecurity
    TxSecurity --> AuditMonitor
    
    style NetworkSecurity fill:#f9f9f9,stroke:#333,stroke-width:1px
    style SecretManagement fill:#f9f9f9,stroke:#333,stroke-width:1px
    style TxSecurity fill:#f9f9f9,stroke:#333,stroke-width:1px
    style AuditMonitor fill:#f9f9f9,stroke:#333,stroke-width:1px
```

Security is implemented at multiple levels:

1. **Network Isolation**:
   - VPN or private network for inter-component communication
   - Restricted access to API endpoints

2. **Secret Management**:
   - Integration with HashiCorp Vault for secure secrets
   - Environment variable isolation
   - No hardcoded credentials

3. **Access Controls**:
   - Role-based access to system components
   - API authentication and authorization
   - Audit logging of all operations

4. **Transaction Protection**:
   - Simulation before execution
   - Gas price limitations
   - Profit requirements
   - Slippage protection

## Disaster Recovery

```mermaid
flowchart LR
    subgraph Normal["Normal Operation"]
        Monitoring["Continuous Monitoring"]
        Backup["Automated Backups"]
    end
    
    subgraph Incident["Incident Occurs"]
        Detection["Issue Detection"]
        Assessment["Impact Assessment"]
        Classification["Severity Classification"]
    end
    
    subgraph Recovery["Recovery Process"]
        Containment["Containment"]
        Restoration["Service Restoration"]
        RootCause["Root Cause Analysis"]
    end
    
    subgraph PostRecovery["Post-Recovery"]
        Improvement["Process Improvement"]
        Documentation["Incident Documentation"]
        Prevention["Preventative Measures"]
    end
    
    Normal -- "Incident Detected" --> Incident
    Incident -- "Recovery Plan Activated" --> Recovery
    Recovery -- "Services Restored" --> PostRecovery
    PostRecovery -- "Cycle Continues" --> Normal
    
    style Normal fill:#bfb,stroke:#333,stroke-width:1px
    style Incident fill:#fbb,stroke:#333,stroke-width:1px
    style Recovery fill:#bbf,stroke:#333,stroke-width:1px
    style PostRecovery fill:#fbf,stroke:#333,stroke-width:1px
```

The system includes disaster recovery capabilities:

1. **Automatic backup** of configuration and state
2. **Graceful degradation** during partial failures
3. **Self-healing** capabilities for common issues
4. **Rollback procedures** for failed deployments

## Extensibility

```mermaid
flowchart TB
    Core["ON1Builder Core"]
    
    subgraph StrategyExtensions["Strategy Extensions"]
        S1["Custom Strategy 1"]
        S2["Custom Strategy 2"] 
        S3["Custom Strategy 3"]
    end
    
    subgraph ChainAdapters["Chain Adapters"]
        C1["Ethereum Adapter"]
        C2["Polygon Adapter"]
        C3["Custom Chain Adapter"]
    end
    
    subgraph IntegrationAPIs["Integration APIs"]
        A1["REST API"]
        A2["WebSocket API"]
        A3["gRPC API"]
    end
    
    subgraph CustomMonitors["Custom Monitors"]
        M1["Performance Monitor"]
        M2["Security Monitor"]
        M3["Custom Monitor"]
    end
    
    Core --- StrategyExtensions
    Core --- ChainAdapters
    Core --- IntegrationAPIs
    Core --- CustomMonitors
    
    style Core fill:#f96,stroke:#333,stroke-width:2px
    style StrategyExtensions fill:#f9f9f9,stroke:#333,stroke-width:1px
    style ChainAdapters fill:#f9f9f9,stroke:#333,stroke-width:1px
    style IntegrationAPIs fill:#f9f9f9,stroke:#333,stroke-width:1px
    style CustomMonitors fill:#f9f9f9,stroke:#333,stroke-width:1px
```

ON1Builder is designed to be extensible:

1. **Plugin Architecture** for adding new strategies
2. **Chain Adapters** for supporting additional blockchains
3. **API Interfaces** for integration with external systems
4. **Custom Monitors** for specific monitoring needs

## Conclusion

The ON1Builder architecture provides a robust, scalable, and secure framework for executing blockchain transactions across multiple chains. Its modular design allows for easy maintenance, extension, and customization while maintaining high performance and reliability.

---

**Next Steps:**

- Explore the [API Reference](api.md) for integrating with ON1Builder
- Learn about all available [Configuration Options](configuration_reference.md)
- Understand the [Components](components.md) in detail
- Try the [Single Chain Example](../examples/single_chain_example.md) to get started
- Return to the [Main Documentation](../index.md)
