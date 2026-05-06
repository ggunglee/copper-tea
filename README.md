# Copper Tea

Commodity event based stock watchlist and Telegram alert system.

This project does not contain broker integration, order routing, or trading execution. It scores watchlist candidates and sends Telegram alerts.

## Quick Start

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
cp .env.example .env
python scripts/init_db.py
python scripts/seed_db.py
python -m app.main run-once --force
```

If `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are blank, alerts are printed to the console.
If Telegram is reachable but slow, tune these values in `.env`:

```text
TELEGRAM_CONNECT_TIMEOUT=10
TELEGRAM_READ_TIMEOUT=30
TELEGRAM_SEND_RETRIES=3
```

## Normal Runs

The default schedule is Asia/Seoul weekdays, hourly from 08:30 to 23:30:

```text
08:30,09:30,10:30,11:30,12:30,13:30,14:30,15:30,
16:30,17:30,18:30,19:30,20:30,21:30,22:30,23:30
```

Run once with the internal schedule guard:

```bash
python scripts/run_once.py
```

Run a long-lived scheduler:

```bash
python -m app.main scheduler
```

Run the scheduler and Telegram command bot together, so `/help`, `/positions`,
and `/watch_kr` keep answering outside the alert windows:

```bash
python -m app.main service
```

Force a manual run:

```bash
python -m app.main run-once --force
```

## Watchlists

Edit these files and reseed:

```text
app/seeds/commodities.yml
app/seeds/companies.yml
app/seeds/benchmarks.yml
```

Then run:

```bash
python scripts/seed_db.py
```

## Positions

Add or update a manually held position:

```bash
python scripts/add_position.py FCX 10 42.50 --currency USD --buy-date 2026-04-28
python scripts/add_position.py 005490.KS 3 390000 --currency KRW --buy-date 2026-04-28
```

Sell attractiveness is calculated only for active positions.

Telegram helpers:

```text
/watch_buy  - all active buy watchlist companies
/watch_kr   - Korean KOSPI/KOSDAQ watchlist companies only
/add_watch ticker / company / market / sector
/add_watch_bulk
/remove_watch ticker
/value_targets
/add_value ticker / company / market / fair_value / buy_price / currency / notes
/add_value_bulk
/add_value_auto ticker
/estimate_value ticker
/remove_value ticker
```

Bulk watchlist import from Termux:

```bash
python scripts/import_watchlist.py <<'EOF'
267260.KS / HD Hyundai Electric / KR_KOSPI / copper_electrical_equipment
010120.KS / LS ELECTRIC / KR_KOSPI / electrical_equipment_power_grid
096770.KS / SK Innovation / KR_KOSPI / refining_energy_battery
EOF
```

Valuation watchlist import:

```bash
python scripts/import_value_targets.py <<'EOF'
KO / Coca-Cola / US / 65 / 58 / USD / dividend staple
XOM / Exxon Mobil / US / 125 / 105 / USD / oil major dividend
005490.KS / POSCO Holdings / KR_KOSPI / 500000 / 410000 / KRW / steel and battery materials
EOF
```

Valuation targets are checked independently from commodity signals. Alerts fire
when current price is at or below the configured buy price plus the alert buffer
of 5% by default, and the alert includes current PER/PBR/ROE when available.

You can also let the app calculate a conservative starting point:

```text
/estimate_value KO
/add_value_auto KO
/add_value_auto XOM / Exxon Mobil / US / dividend energy
```

The automatic estimate uses current price, PER, PBR, ROE, market, and known
sector to infer a fair value, then sets the buy price at a 10% safety margin.

## Providers

Default providers use Yahoo-style HTTP endpoints for prices and basic fundamentals, with mock fallback when fields are missing. You can switch to CSV in `.env`:

```text
PRICE_PROVIDER=csv
NEWS_PROVIDER=csv
FUNDAMENTALS_PROVIDER=csv
```

Provider options:

```text
PRICE_PROVIDER=yahoo|csv|mock
FUNDAMENTALS_PROVIDER=yahoo|csv|mock
NEWS_PROVIDER=rss|mock|csv
```

Commodity-first signal gate:

```text
COMMODITY_SHOCK_DAILY_PCT=3
COMMODITY_TREND_MOMENTUM_PCT=7
COMMODITY_STRUCTURAL_EVENT_SCORE=65
```

A stock is scored only after a sharp commodity move is confirmed by trend momentum
or a structural event such as war, sanctions, export/import controls, shortages,
strikes, mine closures, inventory stress, or policy changes.

CSV files go under `data/csv/`:

```text
commodity_moves.csv
stock_moves.csv
news_events.csv
fundamentals.csv
```

Later API integrations should implement the interfaces in `app/providers/base.py`.

## Termux Notes

Suggested packages:

```bash
pkg update
pkg install python git
pip install -e .
```

Use Termux:Boot or Samsung Modes and Routines only as external triggers. The app itself checks weekday run windows and stores the last completed run slot in `data/state/last_slot.txt`, so repeated triggers should not produce repeated runs.

Status:

```bash
python scripts/show_status.py
```

If Termux was killed during a run and future scheduled runs appear stuck, check:

```bash
ls -l data/state
python scripts/show_status.py
```

The app now clears stale `data/state/run.lock` files when the recorded process is
gone or the lock is older than two hours.

To update the phone copy without moving zip files:

```bash
git clone https://github.com/<owner>/<repo>.git copper-tea
cd copper-tea
pip install -e .
git pull --ff-only
```

Keep `.env` only on the phone. It is ignored by git.

## GitHub Actions Scheduler

This repository includes a scheduled workflow at `.github/workflows/scheduled-run.yml`.
It runs on weekdays at 09:00 and 21:00 Asia/Seoul, and can also be started from
the GitHub Actions tab with `workflow_dispatch`.

Add these repository secrets in GitHub:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

GitHub Actions sets `TELEGRAM_NOTIFY_RUN_SUMMARY=true`, so a manual or scheduled
run still sends a Telegram completion message when there are no new alerts. It
also sets `TELEGRAM_FAIL_ON_SEND_ERROR=true`, so an invalid Telegram token/chat
ID fails the workflow instead of silently looking like "0 alerts".

Optional repository variables can override `.env.example` defaults:

```text
PRICE_PROVIDER=yahoo
NEWS_PROVIDER=rss
FUNDAMENTALS_PROVIDER=yahoo
MIN_BUY_SCORE=65
MIN_SELL_SCORE=65
```

The workflow initializes and seeds `data/app.sqlite3` on the runner, then runs:

```bash
python -m app.main run-once --force
```

It caches the SQLite database by Asia/Seoul date so the second daily run can see
the first run's alert history and avoid same-day duplicate alerts.
