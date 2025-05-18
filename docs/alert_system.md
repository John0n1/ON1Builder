# ON1Builder Alert System

This document explains how to configure and use the alert system in ON1Builder.

## Overview

The ON1Builder alert system provides real-time notifications for important events and critical issues. Alerts can be delivered through multiple channels including:

1. Slack notifications
2. Email alerts
3. Log entries

## Configuration

### Environment Variables

To configure the alert system, set the following environment variables in your `.env` file:

#### Slack Alerts

```
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/TXXXXXX/BXXXXXX/XXXXXXXX
```

#### Email Alerts

```
SMTP_SERVER=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=alerts@example.com
SMTP_PASSWORD=your-secure-password
ALERT_EMAIL=recipient@example.com
```

#### Optional Configuration

```
# Set the environment name to distinguish between production/staging/dev
ENVIRONMENT=production

# Configure alerting thresholds
BALANCE_ALERT_THRESHOLD=0.1  # Alert when wallet balance falls below 0.1 ETH
GAS_PRICE_ALERT_THRESHOLD=100  # Alert when gas price exceeds 100 Gwei
```

## API Endpoint

You can trigger manual alerts through the API for testing or custom notifications:

```
POST /api/test-alert
```

### Request Format

```json
{
  "message": "Alert message content",
  "level": "INFO"  // Can be "INFO", "WARN", or "ERROR"
}
```

### Response Format

```json
{
  "status": "success",
  "message": "Test alert sent"
}
```

## Example Usage

### Using cURL

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"message":"Low balance warning","level":"WARN"}' \
  http://localhost:5001/api/test-alert
```

### Using Python

```python
import requests
import json

url = "http://localhost:5001/api/test-alert"
payload = {
    "message": "Transaction execution failed",
    "level": "ERROR"
}
headers = {"Content-Type": "application/json"}

response = requests.post(url, data=json.dumps(payload), headers=headers)
result = response.json()

print(f"Alert status: {result['status']}")
```

### Using the Deployment Helper

```bash
./deploy/deploy_helper.sh --alert
```

## Alert Types

ON1Builder generates several types of alerts automatically:

### System Alerts

- Service start/stop notifications
- Health check failures
- High resource usage (memory, CPU)

### Operational Alerts

- Low wallet balance
- High gas price conditions
- Network congestion

### Security Alerts

- Failed authentication attempts
- Unusual transaction patterns
- Configuration changes

### Performance Alerts

- Transaction execution failures
- Delayed block processing
- API endpoint unavailability

## Alert Levels

Alerts are categorized by severity level:

- **INFO**: Informational messages, normal operation events
- **WARN**: Warning conditions, potential issues requiring attention
- **ERROR**: Error conditions, issues requiring immediate attention

## Slack Integration

Slack alerts include:

- Color-coded messages based on alert level (green for INFO, red for ERROR)
- Contextual information (environment, timestamp)
- Formatted message content

Example Slack message:

```
🔴 ON1Builder Alert
---------------------
ERROR Alert
Transaction execution failed: insufficient gas
Environment: production
Time: 2023-06-01 14:23:45
```

## Email Integration

Email alerts include:

- Subject line with alert level
- HTML-formatted body with alert details
- Environment and timestamp information

## Best Practices

1. **Set appropriate thresholds** to avoid alert fatigue
2. **Create dedicated Slack channels** for different alert types
3. **Use a dedicated email address** for alert notifications
4. **Test the alert system regularly** with the test endpoint
5. **Document response procedures** for different alert levels

## Limitations

- Email delivery may be delayed by SMTP server processing
- External notification systems may have rate limits
- Critical alerts should use multiple notification channels for redundancy 