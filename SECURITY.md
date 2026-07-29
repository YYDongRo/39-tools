# Security Policy

## Supported versions

Agent DevTools is currently an early-stage project without a stable release.
Security fixes are applied to the latest code on the `main` branch.

## Reporting a vulnerability

Do not disclose vulnerabilities, credentials, private traces, or sensitive
screenshots in a public issue.

Use GitHub's private vulnerability reporting from the repository's **Security**
tab. If that option is unavailable, open an issue containing no sensitive
details and ask the maintainer to establish a private contact channel.

Include, when possible:

- the affected version or commit;
- a minimal reproduction;
- the expected and observed behavior;
- the potential impact;
- suggested mitigations, if known.

## Trace and credential safety

Agent DevTools reports may contain URLs, action arguments, typed text,
screenshots, page metadata, and error details. Review and redact generated
traces before sharing them.

Keep model-provider keys in environment variables. Agent DevTools should not
write provider keys to traces or reports. Revoke any credential that may have
been committed, logged, or shared accidentally.
