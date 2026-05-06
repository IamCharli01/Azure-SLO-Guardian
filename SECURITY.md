# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | ✅ Yes             |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability, please report it responsibly.

**Please do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please report them via:
- GitHub's private vulnerability reporting: [Report a vulnerability](https://github.com/IamCharli01/Azure-SLO-Guardian/security/advisories/new)

### What to include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response timeline

- **Acknowledgment**: Within 48 hours
- **Initial assessment**: Within 1 week
- **Fix timeline**: Depends on severity, typically within 30 days

## Security Best Practices

When using Azure SLO Guardian:

1. **Never commit credentials** — Use environment variables or Azure Managed Identity
2. **Use least-privilege access** — Grant only Reader access to Azure Monitor resources
3. **Rotate service principal secrets** regularly
4. **Review SLO configs** before committing — ensure no workspace IDs leak sensitive info
