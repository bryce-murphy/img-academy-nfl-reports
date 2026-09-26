# Security policy

Use this repository's **Security → Report a vulnerability** for private disclosure. Never put credentials, exploit payloads containing secrets, or personal account tokens in public issues.

The supported version is the current main branch. Rotate any exposed credential immediately, even if a commit is removed. Removing history does not revoke a token.

## Repository controls

Verified September 26, 2026: public-repository secret scanning, push protection, Dependabot alerts and security fixes, CodeQL, private vulnerability reporting, and read-only default Actions permissions are enabled. Actions cannot approve pull requests. Allowed actions are GitHub-owned actions plus `github/codeql-action`; full commit-SHA pinning is enforced. Non-provider secret patterns and validity checks were not enabled at verification; core secret scanning and push protection are enabled.

`main` requires pull requests and up-to-date passing `tests` and `analyze` checks from GitHub Actions. Signed commits, linear history, and resolved review conversations are required. Administrators are subject to these controls. Force pushes and branch deletion are disabled. External approving reviews are set to zero for the solo maintainer; stale approvals are dismissed. Adding a collaborator should trigger review of this policy before requiring an external approval.

Use a feature branch and a signed commit, then a pull request; do not temporarily disable protections to land changes. GitHub's web editor or `createCommitOnBranch` API can produce verified commits when a local signing key is not configured. The existing initial commit predates signature enforcement.

Workflow inputs are passed through environment variables and validated; untrusted pull-request text is never inserted into shell programs. Pull requests never receive social credentials. No pull_request_target workflow or self-hosted runner is used.

No runtime third-party Python dependencies are needed by the initial report builder. Data has explicit HTTPS origins, download limits, schema checks, upstream timestamps, and SHA-256 manifests. All external text is escaped before HTML rendering. Only approved NFL/ESPN image hosts are rendered.

No setup guarantees a completely safe repository. Account 2FA/passkeys, collaborator access, OAuth grants, alert review, and credential rotation remain account-owner responsibilities.

## Future publishing boundary

Report generation remains separate from social publishing. Before enabling social posts, create a main-only protected publishing environment with scoped OAuth credentials. Never place tokens in this public repository, JSON drafts, Quarto output, artifact paths, browser URLs, or logs. Publishing must have a persistent per-platform ledger, content hash, and remote post IDs. An uncertain API timeout must stop for reconciliation rather than retry and create duplicate posts. Use a kill switch and expiry checks.
