# Security Policy

## Supported Versions

We release patches for security vulnerabilities for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 2.1.x   | :white_check_mark: |
| < 2.1   | :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them via email to: **john@on1.no**

Please include the following information:

- Type of issue (e.g. buffer overflow, SQL injection, cross-site scripting, etc.)
- Full paths of source file(s) related to the manifestation of the issue
- The location of the affected source code (tag/branch/commit or direct URL)
- Any special configuration required to reproduce the issue
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue, including how an attacker might exploit the issue

We will respond to your report within 48 hours and will keep you informed of our progress towards a fix.

## Security Considerations for Users

### Private Key Security
- **Never** commit your `.env` file or private keys to version control
- Use hardware wallets or secure key management systems when possible
- Regularly rotate API keys and access tokens
- Monitor your wallet addresses for unauthorized transactions

### Configuration Security
- Use strong, unique passwords for all services
- Enable 2FA where available for all external services
- Regularly review and audit your configuration files
- Use environment variables for sensitive data

### Network Security
- Use VPN connections when trading from public networks
- Ensure RPC endpoints use HTTPS/WSS protocols
- Regularly update and patch your system
- Monitor network traffic for suspicious activity

### Operational Security
- Run the bot on dedicated, secured systems
- Implement proper logging and monitoring
- Regularly backup configuration and data
- Test recovery procedures

## Dependencies

We regularly audit our dependencies for known vulnerabilities and update them as needed. Users are encouraged to:

- Keep the package updated to the latest version
- Review dependency security advisories
- Report any suspicious behavior immediately

## Bug Bounty

While we don't currently have a formal bug bounty program, we appreciate security researchers who responsibly disclose vulnerabilities. We will acknowledge contributions in our release notes when appropriate.

## Contact

For security-related questions or concerns, contact: **john@on1.no**

For general questions, use GitHub issues or discussions.
