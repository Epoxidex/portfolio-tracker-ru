# Portfolio Tracker RU

A local-first web dashboard for a personal investment portfolio. It imports supported operations and prices from T-Invest, tracks manual bank deposits and foreign currency, stores historical snapshots in SQLite, and shows portfolio value, P&L, period changes, leaders and a payment calendar.

The application runs on your computer. There is no cloud account and the application adds no first-party telemetry. Diagnostic error reporting built into the official T-Invest SDK is disabled by default.

> **Privacy:** never commit `.env`, `portfolio.db`, backups or spreadsheet exports. They contain credentials or personal financial data. The repository includes a pre-publication check, but a `.gitignore` rule is not a substitute for checking what is actually staged.

## What is included

- current positions and weighted-average cost basis;
- prices and supported operation history from T-Invest;
- manual deposits with simple interest or monthly capitalization;
- CBR rates and optional cash buy/sell rates scraped from one selected bank page;
- portfolio snapshots and day/week/month comparisons;
- leaders ranked by ruble impact on the portfolio;
- value, allocation, return and price-history charts;
- coupon, dividend, deposit-interest and maturity calendar;
- Excel export plus restorable SQLite backup/restore commands.

The project is a personal dashboard, not a broker report or a tax calculator. Read [calculation rules and current limitations](docs/CALCULATIONS.md) before relying on the numbers.

## Quick start

Requirements: Python 3.11 or 3.12 and internet access for initial dependency installation. The frontend has no build step.

### Windows PowerShell

```powershell
git clone https://github.com/Epoxidex/portfolio-tracker-ru.git
cd portfolio-tracker-ru
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m app.cli init
.\.venv\Scripts\python.exe -m app.cli serve
```

Or, after cloning, run `powershell -ExecutionPolicy Bypass -File .\run.ps1`.

### macOS / Linux

```bash
git clone https://github.com/Epoxidex/portfolio-tracker-ru.git
cd portfolio-tracker-ru
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.cli init
python -m app.cli serve
```

Or run `chmod +x run.sh && ./run.sh`.

Open <http://127.0.0.1:8000>. Keep this address local: the application has no authentication and must not be exposed directly to the internet.

The first start creates an **empty** database. Synthetic demo data is optional and never loaded automatically:

```bash
python -m app.cli demo --replace
```

`--replace` is deliberately required because the command deletes the current local data.

### Install with a coding agent

This repository includes [AGENTS.md](AGENTS.md), a setup and privacy contract for compatible coding agents. After cloning, you can give an agent the repository and say:

> Read `AGENTS.md`, ask me the required setup questions, and install the application locally without exposing or replacing my private data.

The agent is instructed to ask about the portfolio goal, tracking start date, T-Invest connection, currency source and holdings, bank deposits, update intervals, and private backups. Personal answers are stored only in ignored `.env`/SQLite files, not in tracked configuration examples.

## Connect T-Invest

1. Choose the earliest tracking date in the dashboard or set `PORTFOLIO_TRACKING_START_DATE=YYYY-MM-DD` before importing. This prevents lifetime broker history from being pulled silently.
2. Create a **read-only** T-Invest API token. Trading and transfer permissions are neither required nor recommended.
3. Open `.env` and set `TINVEST_TOKEN=...`.
4. If the token can see several accounts, set `TINVEST_ACCOUNT_ID`; otherwise the first returned account is used.
5. Restart the application so the environment is reloaded.
6. Click **Import T-Invest**. The application imports supported operations from the selected date, reconciles active quantities with the broker's current portfolio, refreshes prices and saves a snapshot.

The token stays in `.env` and is never returned by `/api/status`. Synchronization is read-only from the broker's perspective. `TINVEST_SDK_ERROR_REPORTING=0` also disables the SDK's optional error-reporting channel; enabling it is an explicit opt-in.

Current operation support covers buys, sells, coupons, dividends and bond repayments. Taxes, every fee type and every corporate action are not yet fully reconciled. T-Invest API data also does not replace a broker report when exact history matters.

For an existing database, preview and safely apply a new boundary from the terminal:

```bash
python -m app.cli tracking-start --date 2026-04-01
python -m app.cli tracking-start --date 2026-04-01 --apply
```

The second command creates a SQLite backup, removes older imported broker operations and snapshots containing removed phantom positions, and updates `.env`. Manual deposits and currency entries are preserved. Restart a running server afterward.

## Add a bank deposit

Click **Add deposit** in the Positions block or in the first-run panel. Enter:

- a recognizable name;
- principal;
- opening and closing dates;
- the annual rate as a normal percentage — enter `18`, not `0.18`;
- interest paid at maturity without capitalization, or monthly capitalization.

The modal previews interest before saving. The instrument and its opening cash flow are created atomically, so a failed request does not leave a half-created deposit. Deposit terms are manual and are not imported from T-Invest.

An agent or terminal user can perform the same operation without constructing an API request:

```bash
python -m app.cli add-deposit --name "My deposit" --principal 250000 --open-date 2026-01-15 --close-date 2027-01-15 --rate 16 --mode simple
```

## Currency rates

`FX_RATE_SOURCE` controls how existing non-ruble currency positions are valued:

- `cbr` — official CBR rate; the stable default for a fresh clone;
- `bank_buy` — what the configured bank pays when you sell it currency;
- `bank_sell` — what the configured bank charges when you buy currency.

The bank modes parse `BANKIROS_URL`, currently a page for one bank, not a market-wide best rate. The parser recognizes USD, EUR, CNY, GBP, CHF, TRY and AED when those rows exist; CBR supports the currencies present in its daily feed. Only currency instruments already present in the local database are repriced.

Add an opening manual holding with its historical ruble cost, then fetch the current rate:

```bash
python -m app.cli add-currency --code USD --quantity 1000 --invested 90000 --date 2026-01-15
python -m app.cli fetch-fx --source cbr
```

The duplicate guard refuses to add the same currency twice accidentally. For a real additional purchase, pass `--append` and provide that purchase's own amount, cost, and date.

No currency request runs automatically when the page opens. Use **Rates** or **Update all**, or configure `FX_EVERY_MIN`.

## Snapshots and comparisons

`SNAPSHOT_EVERY_MIN=60` creates snapshots while the application is running. Buttons that complete a full T-Invest import also save a snapshot.

The dashboard compares the current last snapshot with:

- the last snapshot of the immediately preceding calendar day;
- the last snapshot inside the preceding Monday–Sunday week;
- the last snapshot inside the preceding calendar month.

If a required period has no snapshot, the UI shows “no reference snapshot” instead of fabricating a number. Full formulas are documented in [docs/CALCULATIONS.md](docs/CALCULATIONS.md).

## Back up and restore your data

GitHub restores the **code**, not your private portfolio. T-Invest can rebuild part of the broker history, but it cannot recreate manual deposits, manual currency entries, local notes or historical snapshots.

Create a consistent SQLite backup while the application is running or stopped:

```bash
python -m app.cli backup
python -m app.cli backup --output D:\PrivateBackups\portfolio
```

Backups under the project `backups/` directory are ignored by Git. Copy them to a private encrypted disk or private cloud location.

To restore, stop the web server first:

```bash
python -m app.cli restore D:\PrivateBackups\portfolio\portfolio-20260714-180000.db --yes
```

The command validates the backup and creates a safety copy of the current database before replacing it.

## Tests and public-repository check

```bash
python -m pip install -r requirements-dev.txt
pytest -q
python scripts/check_public.py
```

The tests use a temporary `DB_PATH` and do not touch `portfolio.db`.

Before the first public push:

1. Run `python scripts/check_public.py`.
2. Inspect `git status --short` and `git diff --cached` yourself.
3. Confirm that `.env`, databases, backups, exports and local IDE/agent folders are absent.
4. Search the complete Git history if this directory was ever committed elsewhere.
5. Choose and add a `LICENSE`. No license is added automatically because that is the repository owner's legal choice.

If a real token was ever committed, revoke it before rewriting history. See [SECURITY.md](SECURITY.md).

## Configuration

| Variable | Default | Purpose |
|---|---:|---|
| `TINVEST_TOKEN` | empty | Read-only T-Invest token |
| `TINVEST_ACCOUNT_ID` | first account | Select one account explicitly |
| `TINVEST_SDK_ERROR_REPORTING` | `0` | Opt in to the official SDK's diagnostic error reports |
| `PORTFOLIO_GOAL` | `1000000` | Progress target in rubles |
| `PORTFOLIO_TRACKING_START_DATE` | empty | Earliest T-Invest import/history date (`YYYY-MM-DD`) |
| `FX_RATE_SOURCE` | `cbr` | `cbr`, `bank_buy` or `bank_sell` |
| `BANKIROS_URL` | Kamkombank page | Optional third-party cash-rate page |
| `DB_PATH` | `portfolio.db` | SQLite path, relative to project root or absolute |
| `SNAPSHOT_EVERY_MIN` | `60` | Background snapshot interval, `0` disables |
| `FETCH_EVERY_MIN` | `0` | Background T-Invest price interval |
| `FX_EVERY_MIN` | `0` | Background currency-rate interval |

## Project structure

```text
app/
  main.py              FastAPI app and background jobs
  config.py            environment configuration
  db.py, models.py     SQLite / SQLAlchemy
  routers/api.py       local REST API
  services/            portfolio, snapshots, T-Invest, FX, calendar
  dataio.py            verified backup and restore
static/                 HTML, CSS and JavaScript (no build step)
tests/                  isolated calculation and API tests
scripts/check_public.py pre-publication privacy check
AGENTS.md              installation and safety contract for coding agents
```

The charts and calendar currently load ECharts, FullCalendar and fonts from public CDNs, so the dashboard is not fully offline even though portfolio data stays local.
