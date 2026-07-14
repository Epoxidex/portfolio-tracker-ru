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

## If a secret was committed

1. Revoke the token immediately in T-Invest and issue a new read-only token.
2. Remove the file from the entire Git history, not only from the latest commit.
3. Check branches, tags, pull requests, forks and existing clones.
4. Run the public-repository check again before pushing.

GitHub documents the history-rewrite process in its guide to removing sensitive data. A rewritten history does not revoke a credential and cannot erase copies that somebody already cloned, so rotation comes first.

## Backups

Public Git hosting is intentionally **not** a backup for portfolio data. Keep database backups in a private, preferably encrypted location and occasionally test restoring one. Commands are documented in the README.

## Reporting a vulnerability

Do not open a public issue containing tokens, database extracts, account IDs or transaction details. Describe the problem without private data, or contact the repository owner privately.
