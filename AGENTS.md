# Portfolio Tracker agent guide

This repository uses `AGENTS.md` as the operational contract for coding agents.
Apply these instructions to the whole repository. Ask questions in the user's
language and explain financial terms in plain language.

## Start here

Before changing or starting the application, read `README.md`,
`docs/CALCULATIONS.md`, and `SECURITY.md`. Determine whether this is:

1. a new empty installation;
2. an existing installation that must be preserved; or
3. a restore from a private SQLite backup.

Do not infer that a database is disposable. `portfolio.db`, `.env`, backups,
exports, and spreadsheets are private user data, even though Git ignores them.
Never run `demo --replace`, restore a backup, delete a database, or replace an
existing `.env` without explicit confirmation. Back up an existing database
before any migration or bulk data change.

## Required installation interview

For a new installation, do not silently keep the sample defaults. Ask the user
one concise, grouped set of questions and allow unknown items to be skipped:

- Desired portfolio target in rubles (`PORTFOLIO_GOAL`).
- Earliest portfolio tracking date (`PORTFOLIO_TRACKING_START_DATE`). Explain
  that a new installation should set this before importing T-Invest; do not
  silently import the account's full lifetime history.
- Whether to connect T-Invest. If yes, ask them to create a **read-only** token
  and whether one specific account should be selected when the token sees more
  than one account.
- Currency valuation source: official CBR (`cbr`, recommended), the configured
  bank's cash buy rate (`bank_buy`), or its cash sell rate (`bank_sell`). For a
  bank mode, also ask which Bankiros bank page represents their bank.
- Manual foreign-currency holdings: code, amount held, acquisition date,
  historical total cost in RUB, and (optionally) the current rate. Do not assume
  that the user owns only USD or CNY.
- Bank deposits: name, principal, opening date, maturity date, annual rate in
  percent, and either simple interest or monthly capitalization.
- Background intervals for snapshots, T-Invest prices, and currency rates.
  Explain that `0` disables a job and jobs run only while the app is open.
- A private backup directory outside the repository and whether an existing
  backup should be restored.

The current accounting base currency is RUB. If the user needs another base
currency, say that this is a code change and clarify the scope before proceeding.

Never ask the user to paste a token into a chat or commit it. Ask them to enter
it directly in their local `.env`; an agent may update it only in a trusted local
session after explicit permission. Never echo a token or account ID in logs,
tool output, tests, documentation, or final messages. User-specific values belong
only in `.env` and the ignored SQLite database, never in tracked examples.

## Installation workflow

Use Python 3.11 or 3.12 and bind the server to `127.0.0.1`. The frontend has no
build step. On Windows, use `.venv\Scripts\python.exe`; on macOS/Linux, use
`.venv/bin/python`.

1. Create `.venv` and install `requirements.txt`.
2. If `.env` is absent, copy `.env.example` to `.env`. Apply the answers by
   editing only the relevant keys; preserve unknown keys in an existing file.
3. Run `python -m app.cli init`, then `python -m app.cli doctor`. The doctor
   command reports readiness but never prints secrets or the database path.
4. Preview the selected history window with
   `python -m app.cli tracking-start --date YYYY-MM-DD`. For an existing
   database, apply it only after confirmation; `--apply` creates a backup first.
5. Add each manual deposit with `python -m app.cli add-deposit` and each manual
   currency holding with `python -m app.cli add-currency`. Use `--append` only
   when the user explicitly confirms this is an additional currency purchase;
   the default duplicate guard is intentional.
6. If T-Invest was selected, restart the process after `.env` changes and run
   `python -m app.cli sync-ops --days 3650` only after the user confirms the
   account. Then refresh prices. T-Invest access must remain read-only.
7. Refresh currency rates, take an initial snapshot, and create a private backup.
8. Install `requirements-dev.txt`, run the verification commands below, start
   the app, and tell the user where the private data and backups live.

Example commands contain placeholders only:

```bash
python -m app.cli add-deposit --name "My deposit" --principal 250000 --open-date 2026-01-15 --close-date 2027-01-15 --rate 16 --mode simple
python -m app.cli add-currency --code USD --quantity 1000 --invested 90000 --date 2026-01-15
python -m app.cli tracking-start --date 2026-04-01 --apply
python -m app.cli fetch-fx --source cbr
python -m app.cli snapshot
python -m app.cli backup --output <PRIVATE-BACKUP-DIRECTORY>
```

## Development and verification

Keep financial calculations in `app/services/`, request validation in
`app/schemas.py`, local API routes in `app/routers/api.py`, and browser code in
`static/`. Reuse service functions from both the API and CLI so their accounting
behavior cannot drift.

Run from the repository root:

```bash
python -m pytest -q
python -m compileall -q app scripts tests
python scripts/check_public.py
```

Tests must use a temporary `DB_PATH` and must never open or mutate the user's
`portfolio.db`. When UI code changes, launch the local app and visually inspect
the relevant desktop and mobile states. Do not claim financial accuracy beyond
the rules and limitations documented in `docs/CALCULATIONS.md`.

Before a public commit, inspect the actual staged files and run
`scripts/check_public.py`. Never weaken `.gitignore` or the privacy check merely
to make a check pass. Do not add real portfolio values, tokens, account IDs,
local user paths, database files, backups, exports, IDE settings, agent caches,
screenshots, or generated Python caches to Git.
