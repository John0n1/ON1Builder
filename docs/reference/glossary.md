# Glossary of Terms

This glossary provides definitions for technical terms used throughout the ON1Builder documentation.

## Blockchain Terms

### MEV (Miner Extractable Value)
Value that can be extracted from blockchain users by miners or validators who can control transaction ordering within a block. ON1Builder helps identify and capture MEV opportunities.

### RPC (Remote Procedure Call)
A protocol that enables a program to request a service from another program located on a different network without understanding network details. In blockchain, RPC endpoints allow interaction with the blockchain network.

### DEX (Decentralized Exchange)
A type of cryptocurrency exchange that operates without a central authority, allowing for direct peer-to-peer cryptocurrency transactions.

### Gas
A fee required to conduct a transaction or execute a contract on blockchain platforms like Ethereum. Gas is paid in the blockchain's native cryptocurrency.

### Triangular Arbitrage
A trading strategy that exploits price discrepancies between three different assets to generate profit with minimal risk.

### Flash Loan
A type of uncollateralized loan where assets are borrowed and returned within a single transaction block, commonly used in arbitrage and other MEV strategies.

## ON1Builder-Specific Terms

### Chain Worker
A component in ON1Builder that manages operations for a specific blockchain, handling transaction monitoring, submission, and other chain-specific tasks.

### Safety Net
A component that implements protection mechanisms and fail-safes to prevent losses and ensure transaction integrity.

### Transaction Core
The component responsible for handling transaction creation, signing, and submission across different blockchains.

### Strategy
A defined approach to identify and execute profit opportunities. ON1Builder allows for both built-in and custom strategies.

### Block Time
The average time interval between the creation of consecutive blocks in a blockchain. This varies significantly between different blockchains.

### Gas Price Strategy
A method for determining the appropriate gas price for transactions. ON1Builder supports multiple strategies (e.g., "fast", "medium", "slow") to optimize transaction costs versus confirmation speed.
