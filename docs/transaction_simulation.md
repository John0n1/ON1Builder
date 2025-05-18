# ON1Builder Transaction Simulation

This document explains how to use the transaction simulation functionality in ON1Builder.

## Overview

Transaction simulation allows you to analyze and predict the outcome of a blockchain transaction before it's executed on-chain. This is particularly useful for:

1. Evaluating transaction profitability
2. Estimating gas costs
3. Detecting potentially failing transactions
4. Testing arbitrage opportunities

## API Endpoint

The transaction simulation feature can be accessed through the following API endpoint:

```
POST /api/simulate-transaction
```

### Request Format

```json
{
  "tx_hash": "<transaction-hash>",
  "chain_id": "<chain-id>"
}
```

- **tx_hash**: The hash of the transaction to simulate
- **chain_id**: The ID of the blockchain where the transaction exists

### Response Format

```json
{
  "success": true,
  "result": {
    "transaction": {
      "hash": "<tx-hash>",
      "from": "<from-address>",
      "to": "<to-address>",
      "value": "<value-wei>",
      "gas": "<gas-limit>",
      "gasPrice": "<gas-price-wei>",
      "input": "<transaction-input-data>"
    },
    "chain_id": "<chain-id>",
    "simulation_results": {
      "success": true,
      "gas_used": "<estimated-gas-used>",
      "gas_cost_eth": "<estimated-gas-cost-in-eth>",
      "profit_estimate_eth": "<estimated-profit-in-eth>",
      "is_profitable": true|false,
      "error": null
    }
  }
}
```

In case of failure:

```json
{
  "success": false,
  "error": "<error-message>"
}
```

## Example Usage

### Using cURL

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"tx_hash":"0x123abc...","chain_id":"1"}' \
  http://localhost:5001/api/simulate-transaction
```

### Using Python

```python
import requests
import json

url = "http://localhost:5001/api/simulate-transaction"
payload = {
    "tx_hash": "0x123abc...",
    "chain_id": "1"
}
headers = {"Content-Type": "application/json"}

response = requests.post(url, data=json.dumps(payload), headers=headers)
result = response.json()

if result["success"]:
    sim_result = result["result"]["simulation_results"]
    print(f"Gas used: {sim_result['gas_used']}")
    print(f"Gas cost: {sim_result['gas_cost_eth']} ETH")
    print(f"Profit estimate: {sim_result['profit_estimate_eth']} ETH")
    print(f"Is profitable: {sim_result['is_profitable']}")
else:
    print(f"Simulation failed: {result['error']}")
```

## Key Features

### Gas Estimation

The simulation provides accurate gas usage estimation by executing the transaction against a forked state of the blockchain.

### Profitability Analysis

For MEV opportunities, the simulation calculates:
- The potential profit of the transaction
- The cost of gas required to execute it
- The net profit after gas costs

### Error Detection

The simulation detects potential issues that might cause a transaction to fail, such as:
- Insufficient balance
- Contract execution errors
- Reverted transactions

## How It Works

1. The transaction is retrieved from the transaction pool
2. A local fork of the blockchain is created at the current block
3. The transaction is executed against this fork
4. The state changes and gas consumption are calculated
5. For known MEV patterns, profit is estimated by analyzing state changes

## Limitations

- Simulations are estimates and may not match actual on-chain execution
- Complex transactions involving multiple contracts may have varying results
- Network conditions can change between simulation and actual execution
- Simulations don't account for front-running or other competitive MEV scenarios

## Security Considerations

- Transaction simulation is resource-intensive and rate-limited
- Simulation results are stored temporarily and then purged
- Private keys are never used in the simulation process 