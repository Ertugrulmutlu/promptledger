# Security Policy

PromptLedger is a local-first prompt version control and evaluation tool.

Security reports are taken seriously, especially issues involving local data exposure, unsafe file access, dashboard endpoints, SQLite database handling, package integrity, or accidental disclosure of prompt content and evaluation data.

## Supported Versions

Security fixes are provided for the latest released version of PromptLedger.

| Version | Supported |
|---|---|
| 0.7.x | Yes |
| Older versions | No |

Users are encouraged to upgrade to the latest available release:

```bash
pip install --upgrade promptledger
```

## Reporting a Vulnerability

Please do not report security vulnerabilities through a public GitHub issue, discussion, pull request, or social media post.

Report vulnerabilities privately by contacting:

```text
ertugrulmutlu004@gmail.com
```

Replace `ertugrulmutlu004@gmail.com` with an email address you actively monitor before publishing this file.

When reporting a vulnerability, include as much of the following information as possible:

- A clear description of the issue
- The affected PromptLedger version
- Your operating system
- Your Python version
- The command or workflow that triggers the issue
- Steps to reproduce the vulnerability
- Expected and actual behavior
- Potential security impact
- A minimal proof of concept, when safe
- Suggested mitigations, if known

Please remove API keys, credentials, private prompts, personal information, and other sensitive data from reports.

## Response Process

After receiving a report, the maintainer will attempt to:

1. Acknowledge the report within 7 days
2. Review and reproduce the issue
3. Assess its severity and affected versions
4. Develop and test a fix when necessary
5. Coordinate disclosure with the reporter
6. Publish a patched release and security advisory when appropriate

Response times may vary depending on the complexity and severity of the issue.

## Scope

Examples of security issues that may be in scope include:

- Unauthorized access to prompt content or evaluation data
- Arbitrary file reading or writing
- Path traversal in dashboard or export functionality
- Unsafe handling of user-controlled file paths
- SQL injection
- Remote code execution
- Command injection
- Cross-site scripting in the local dashboard
- Unsafe dashboard write endpoints
- Exposure of secrets through logs, exports, or error messages
- Database corruption caused by malformed or malicious input
- Package or build configuration issues that affect distribution integrity
- Vulnerabilities that bypass the intended local-only security boundary

PromptLedger binds its dashboard to `127.0.0.1` by default. Users who change the host binding are responsible for understanding the network exposure this may create.

## Out of Scope

The following are generally not considered security vulnerabilities:

- Feature requests
- General bugs without a security impact
- Social engineering attacks against project maintainers
- Vulnerabilities in unsupported PromptLedger versions
- Issues caused by exposing the local dashboard to untrusted networks
- Compromised operating systems or Python environments
- Sensitive information intentionally stored in prompt content
- Third-party model providers or benchmark tools not maintained by PromptLedger
- Denial-of-service scenarios requiring full local machine access

These issues may still be reported through the normal GitHub issue tracker when they do not contain sensitive security information.

## Sensitive Data

PromptLedger stores prompt history, metadata, labels, markers, and evaluation results locally in SQLite.

Users should avoid storing:

- API keys
- Access tokens
- Passwords
- Private credentials
- Personal information
- Confidential production data

PromptLedger includes basic warnings for common secret formats, but these checks are not comprehensive and should not be treated as a secret-management system.

## Coordinated Disclosure

Please allow reasonable time for investigation and remediation before publicly disclosing a vulnerability.

The project will make a reasonable effort to credit reporters in release notes or security advisories unless anonymity is requested.

## Security Updates

Security fixes may be published through:

- New PyPI releases
- GitHub releases
- GitHub security advisories
- The project changelog

Users should monitor the repository and keep PromptLedger updated.
