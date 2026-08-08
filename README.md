# Stock Price Target Tracker

Tracks **12-month analyst / institution price targets** for ~138 US stocks (S&P 500 IT + Nasdaq-100), compares them to the current price, and publishes a self-contained HTML dashboard every weekday.

> **Live dashboard →** [targets.pranavp.dev](https://targets.pranavp.dev)

Same deploy pattern as [options.pranavp.dev](https://options.pranavp.dev): Python fetch → analyze → embed JSON in HTML → commit to `docs/` → GitHub Pages.

---

## What it does

Every weekday after the US close, the pipeline:

1. Fetches **yfinance** fundamentals + consensus targets for every ticker
2. Pulls the latest **named analyst** price targets from **Financial Modeling Prep** (firm, analyst, target, date, rating)
3. Cross-checks with **Alpha Vantage** `AnalystTargetPrice` for the top 25 by market cap (rest served from yesterday’s cache)
4. Computes upside %, consensus divergence, above-target flags, and **week-over-week** target deltas
5. Writes `docs/index.html` + `reports/latest_targets.json` and pushes to GitHub Pages

---

## Data sources

| Source | What we use | Limit | Key |
|---|---|---|---|
| **yfinance** `==1.5.2` | `currentPrice`, `targetMean/Median/High/Low`, `numberOfAnalystOpinions`, `recommendationKey`, P/E, mcap, volume, 52W, beta | None | No key |
| **FMP** `/stable/price-target-consensus` | Consensus / high / low / median targets | 250 req/day | `FMP_API_KEY` |
| **FMP** `/stable/grades` (free) or `/stable/price-target-news` (paid) | Firm grades, or named $-targets if plan allows | shares FMP budget | `FMP_API_KEY` |
| **Alpha Vantage** `OVERVIEW` | `AnalystTargetPrice` (third consensus) | 25 req/day | `ALPHA_VANTAGE_API_KEY` |

> **Note:** FMP legacy `/api/v3` and `/api/v4` endpoints return 403 for new keys. Named dollar price targets (`price-target-news`) require a paid FMP plan; the free tier uses consensus + firm grades instead.

### Rate-limit strategy

- **yfinance** — all tickers every run
- **FMP** — consensus for all tickers; firm detail rows for as many as fit under ~240 req/day
- **Alpha Vantage** — refresh top 25 by market cap (missing/oldest first); cache the rest inside `reports/latest_targets.json` so each ticker refreshes roughly every ~6 trading days

Local runs load `FMP_API_KEY` / `ALPHA_VANTAGE_API_KEY` from a gitignored `.env` automatically (existing shell env / GitHub Secrets always win).

---

## Local setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade -r requirements.txt

export FMP_API_KEY="your_fmp_key"
export ALPHA_VANTAGE_API_KEY="your_av_key"

# smoke test on a few tickers (AV limit 2 to stay polite)
python main.py --tickers AAPL MSFT NVDA --av-limit 2

# full universe
python main.py
```

Optional Excel export:

```bash
python main.py --tickers AAPL MSFT --excel
```

Outputs:

- `docs/index.html` — dashboard (open in a browser)
- `reports/latest_targets.json` — weekday snapshot + AV cache + week baseline

---

## GitHub Secrets (required for Actions)

In the repo: **Settings → Secrets and variables → Actions → New repository secret**

| Secret name | Where to get it |
|---|---|
| `FMP_API_KEY` | Sign up at [financialmodelingprep.com](https://site.financialmodelingprep.com/developer/docs) |
| `ALPHA_VANTAGE_API_KEY` | Sign up at [alphavantage.co](https://www.alphavantage.co/support/#api-key) |

The workflow injects both as env vars when running `python main.py`.

---

## GitHub Pages

1. Push this repo to GitHub
2. **Settings → Pages →** Source: **Deploy from a branch** → Branch: `main` → Folder: `/docs`
3. Custom domain: `targets.pranavp.dev` (repo already has `docs/CNAME`)
4. Point a DNS CNAME for `targets` → `youruser.github.io`

Schedule: `30 21 * * 1-5` (9:30 PM UTC ≈ 4:30 PM ET). Manual runs: **Actions → Daily Targets Report → Run workflow**.

---

## Module layout

| File | Role |
|---|---|
| `main.py` | Orchestrates fetch → analyze → export; manages snapshots |
| `universe.py` | S&P 500 IT + Nasdaq-100 ticker list |
| `fetcher.py` | yfinance + FMP + Alpha Vantage (AV rate-limit + cache) |
| `analyzer.py` | Upside %, divergence, above-target, weekly deltas, ranking |
| `exporter_html.py` | Self-contained HTML + Chart.js + embedded JSON |
| `reports/latest_targets.json` | Weekday snapshot (AV cache + week baseline) |
| `docs/index.html` | GitHub Pages entry |

---

## Snapshot / weekly diffs

`reports/latest_targets.json` updates every weekday run and stores:

- `tickers` — full analyzed rows for the dashboard
- `av_cache` — Alpha Vantage targets + `fetched_at` for cache reuse
- `week_baseline` — compact per-ticker targets refreshed every ~7 days; UI columns `YF Δwk` / FMP / AV compare against this baseline

---

## Dashboard features

- Sortable / filterable table (ticker, recommendation, above-target, divergence, upside &gt; 0)
- Upside % = `(target − price) / price`
- Consensus columns: yfinance mean · FMP latest · Alpha Vantage
- Divergence flag when sources disagree by ≥ 10% of their midpoint
- Expand a row for the named FMP analyst table (firm, analyst, target, date, rating, news)
- Fundamentals alongside targets: P/E, forward P/E, market cap, volume, 52W, beta, recommendation
- Chart.js bar chart of upside for the current filtered view
