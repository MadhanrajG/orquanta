# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| v4.x (current) | Yes |
| v3.x and earlier | No |

## Reporting a Vulnerability

**Do not file a public GitHub issue for security vulnerabilities.**

If you discover a security vulnerability in OrQuanta, please report it responsibly through one of the following channels:

- **Email:** security@orquanta.com
- **Subject line:** `[SECURITY] <brief description>`

We will acknowledge your report within 48 hours and aim to provide a resolution timeline within 7 days.

### What to Include

Please provide as much of the following as possible:

- Description of the vulnerability and its potential impact
- Step-by-step reproduction instructions
- Affected component(s) and version(s)
- Any proof-of-concept code or screenshots

### What to Expect

1. **Acknowledgement** within 48 hours.
2. **Initial assessment** (severity, affected scope) within 5 business days.
3. **Fix and coordinated disclosure** timeline agreed with the reporter.
4. **Credit** in the release notes (unless you prefer to remain anonymous).

## Scope

The following are in scope for responsible disclosure:

- Authentication and authorisation bypass
- Remote code execution
- SQL injection or database exposure
- Sensitive data exposure (API keys, tokens, PII)
- WebSocket security issues
- Stripe webhook manipulation
- Agent execution safety bypasses
- Privilege escalation
- Denial-of-service vulnerabilities

The following are **out of scope**:

- Vulnerabilities in third-party services (RunPod, Stripe, etc.) — report those to the respective vendors
- Social engineering attacks
- Physical access attacks
- Issues that require a compromised account with existing admin access
- Theoretical vulnerabilities without a working proof of concept

## Security Hardening Notes for Operators

When deploying OrQuanta in production, ensure the following are configured:

| Setting | Requirement |
|---|---|
| `JWT_SECRET_KEY` | Minimum 64 random hex characters |
| `STRIPE_WEBHOOK_SECRET` | Required; webhook rejects without it in production |
| `DATABASE_URL` | Do not use default credentials |
| `WS_AUTH_REQUIRED` | Must remain `true` in production |
| `REQUIRE_HIGH_COST_APPROVAL` | Recommended `true` to block runaway agent spend |
| `SAFETY_OVERRIDE_TOKEN` | Set to a random secret; never use default |
| `ENVIRONMENT` | Set to `production` to enable production-mode security checks |
| `USE_REAL_PROVIDERS` | Only set to `true` when real GPU provider keys are configured |

## Bug Bounty

OrQuanta does not currently operate a formal paid bug bounty programme. We recognise and credit all responsible disclosures in our changelogs and release notes.

## Contact

security@orquanta.com
