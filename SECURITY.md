# Security and privacy

Portfolio Tracker is a local application. It has no login screen and its API can read, change and export the whole portfolio. Keep the server bound to `127.0.0.1`; do not expose it to the internet or start it with `--host 0.0.0.0` on an untrusted network.

## Files that must stay private

- `.env` — contains the T-Invest token and possibly an account ID.
- `*.db`, `*.sqlite*` — contain positions, operations, balances and history.
- `backups/` — restorable copies of the same financial data.
- exported `.xlsx`, `.xls` and `.csv` files.

These paths are covered by `.gitignore`. Before every public push run:

```bash
python scripts/check_public.py
```

Use only a **read-only** T-Invest token. The application does not need trading or transfer permissions.

## MCP write access

The local MCP server can change the ignored SQLite database through explicit
ledger tools. Connect it only to a trusted local client. Write tools require
`confirm=true` and an idempotency key, but those checks do not replace reviewing
the concrete amounts, dates and asset identifiers before asking a model to apply
them. Hypothetical questions must not trigger write tools.

MCP cannot trade or transfer funds at T-Invest. Broker synchronization uses the
same read-only token and only updates local data. Keep the server on `stdio`; do
not wrap it in a remotely reachable transport without adding authentication and
an explicit threat model.

## If a secret was committed

1. Revoke the token immediately in T-Invest and issue a new read-only token.
2. Remove the file from the entire Git history, not only from the latest commit.
3. Check branches, tags, pull requests, forks and existing clones.
4. Run the public-repository check again before pushing.

GitHub documents the history-rewrite process in its guide to removing sensitive data. A rewritten history does not revoke a credential and cannot erase copies that somebody already cloned, so rotation comes first.

## Backups

The optional UI backup feature stores complete, unencrypted SQLite files in a separate Git repository. That repository must remain private, must never be used as the public source-code remote, and must not contain `.env` or tokens. Anyone with repository access can read the financial data, and old backups remain in Git history.

Git credentials are handled by the system credential manager. Do not embed a username, password or token in `BACKUP_GIT_REPOSITORY`. Keep another independent backup and occasionally test the restore workflow. Setup and recovery steps are documented in the README.

## Reporting a vulnerability

Do not open a public issue containing tokens, database extracts, account IDs or transaction details. Describe the problem without private data, or contact the repository owner privately.
