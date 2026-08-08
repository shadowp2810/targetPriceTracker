# Stock Price Target Tracker

Tracks **12-month analyst / institution price targets** for ~138 US stocks (S&P 500 IT + Nasdaq-100), compares them to the current price, and publishes a self-contained HTML dashboard every weekday.

> **Live dashboard →** [targets.pranavp.dev](https://targets.pranavp.dev)

Same deploy pattern as [options.pranavp.dev](https://options.pranavp.dev): Python fetch → analyze → embed JSON in HTML → commit to `docs/` → GitHub Pages.

---

## What it does

Every weekday after the US close, the pipeline:

1. Fetches **yfinance** fundamentals + consensus targets for every ticker
2. Pulls **FMP** consensus (+ firm grades on the free tier)
3. Cross-checks with **Alpha Vantage** `AnalystTargetPrice` for the top 25 by market cap (rest served from yesterday’s cache)
4. Scrapes sell-side firm targets from [PriceTargets.com](https://www.pricetargets.com/brokerages/) for **Morgan Stanley, Goldman Sachs, JPMorgan, RBC, Desjardins** (one page each / day)
5. Computes upside %, consensus divergence, above-target flags, and **week-over-week** target deltas
6. Writes `docs/index.html` + `reports/latest_targets.json` and pushes to GitHub Pages

---

## Data sources

| Source | What we use | Limit | Key |
|---|---|---|---|
| **yfinance** `==1.5.2` | `currentPrice`, `targetMean/Median/High/Low`, `numberOfAnalystOpinions`, `recommendationKey`, P/E, mcap, volume, 52W, beta | None | No key |
| **FMP** `/stable/price-target-consensus` | Consensus / high / low / median targets | 250 req/day | `FMP_API_KEY` |
| **FMP** `/stable/grades` (free) or `/stable/price-target-news` (paid) | Firm grades, or named $-targets if plan allows | shares FMP budget | `FMP_API_KEY` |
| **Alpha Vantage** `OVERVIEW` | `AnalystTargetPrice` (third consensus) | 25 req/day | `ALPHA_VANTAGE_API_KEY` |
| **Broker scrapes** (PriceTargets.com) | MS · GS · JPM · RBC · Desjardins firm targets/ratings | 1 page/broker/day | No key |

> **Note:** FMP legacy `/api/v3` and `/api/v4` endpoints return 403 for new keys. Named dollar price targets (`price-target-news`) require a paid FMP plan; the free tier uses consensus + firm grades instead.

### Broker scrape notes

- Configured in [`broker_scraper.py`](broker_scraper.py) `BROKERS` list — add/remove firms by path slug
- Exact ticker matches join into each row’s `firm_targets` (not folded into consensus / divergence)
- CAD targets are not FX-converted against USD yfinance prices (firm upside stays blank for CAD)
- Dashboard **Firm picks** panel has a tab per broker; expand a main-table row to see all matched firms
- On scrape failure for a firm, that firm’s prior `broker_cache` entry is reused
- Each page only shows ~100 recent ratings — we **merge** into `by_ticker` so coverage accumulates across days

### Rate-limit strategy

- **yfinance** — all tickers every run
- **FMP** — consensus for all tickers; firm detail rows for as many as fit under ~240 req/day
- **Alpha Vantage** — refresh top 25 by market cap (missing/oldest first); cache the rest inside `reports/latest_targets.json` so each ticker refreshes roughly every ~6 trading days
- **Broker scrapes** — one HTTP GET per configured firm (~5/day)

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
| `fetcher.py` | yfinance + FMP + Alpha Vantage + broker scrapes |
| `broker_scraper.py` | PriceTargets.com multi-broker scrape + cache |
| `desjardins_fetcher.py` | Thin shim around `broker_scraper` (compat) |
| `analyzer.py` | Upside %, divergence, above-target, weekly deltas, ranking |
| `exporter_html.py` | Self-contained HTML + Chart.js + embedded JSON |
| `reports/latest_targets.json` | Weekday snapshot (AV + broker caches + week baseline) |
| `docs/index.html` | GitHub Pages entry |

---

## Snapshot / weekly diffs

`reports/latest_targets.json` updates every weekday run and stores:

- `tickers` — full analyzed rows for the dashboard
- `av_cache` — Alpha Vantage targets + `fetched_at` for cache reuse
- `broker_cache` — per-firm scraped rows + `by_ticker` maps (MS/GS/JPM/RBC/Desjardins)
- `week_baseline` — compact per-ticker targets refreshed every ~7 days

---

## Dashboard features

- Sortable / filterable table (ticker, recommendation, above-target, divergence, upside &gt; 0, Has firm target)
- Upside % = `(target − price) / price`
- Consensus columns: yfinance mean · FMP latest · Alpha Vantage
- Firm columns: `# Firms` + best USD firm upside (expand row for MS/GS/JPM/RBC/DJ detail)
- Firm picks panel with per-broker tabs
- Divergence flag when sources disagree by ≥ 10% of their midpoint
- Fundamentals alongside targets: P/E, forward P/E, market cap, volume, 52W, beta, recommendation
- Chart.js bar chart of upside for the current filtered view
