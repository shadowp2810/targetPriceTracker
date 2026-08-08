"""
Fetches analyst price targets and fundamentals from three sources:

1. yfinance  — fundamentals + consensus (targetMean/Median/High/Low), no key
2. FMP       — named per-firm analyst targets (free tier: 250 req/day)
3. Alpha Vantage OVERVIEW — third consensus AnalystTargetPrice (25 req/day)

Alpha Vantage only covers ~25 tickers/day. Priority = highest market-cap first;
remaining tickers reuse cached values from the previous snapshot.
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests
import yfinance as yf

# FMP stable API (legacy /api/v3 and /api/v4 return 403 for new keys)
FMP_CONSENSUS_URL = "https://financialmodelingprep.com/stable/price-target-consensus"
FMP_PRICE_TARGET_NEWS_URL = "https://financialmodelingprep.com/stable/price-target-news"
FMP_GRADES_URL = "https://financialmodelingprep.com/stable/grades"
AV_OVERVIEW_URL = "https://www.alphavantage.co/query"

AV_DAILY_LIMIT = 25
FMP_ANALYST_LIMIT = 5
FMP_DAILY_BUDGET = 240  # free tier ~250/day; leave headroom
YF_DELAY_SEC = 0.15
FMP_DELAY_SEC = 0.25
AV_DELAY_SEC = 12.5  # free tier ~5 req/min; stay under the limit

# requests exceptions often embed the full URL including ?apikey=...
_SECRET_QUERY_RE = re.compile(
    r"(?i)([?&](?:apikey|api_key|access_token|token)=)([^&\s\"'<>]+)"
)


def load_dotenv(path: str | Path = ".env") -> None:
    """
    Load KEY=VALUE pairs from .env into os.environ if not already set.
    Does not override existing env vars (so GitHub Actions secrets win).
    """
    p = Path(path)
    if not p.is_file():
        return
    try:
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception as e:
        print(f"[WARN] Could not load {p}: {type(e).__name__}")


def _env_key(name: str) -> Optional[str]:
    val = os.environ.get(name, "").strip()
    return val or None


def _redact(text: Any, *secrets: Optional[str]) -> str:
    """Strip known secrets and common API-key query params from log strings."""
    out = str(text)
    for secret in secrets:
        if secret and len(secret) >= 4:
            out = out.replace(secret, "***")
    return _SECRET_QUERY_RE.sub(r"\1***", out)


def _safe_exc(exc: BaseException, *secrets: Optional[str]) -> str:
    """
    Format an exception for logs without leaking API keys.
    HTTPError is reduced to status code (response.url often contains apikey=).
    """
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, requests.RequestException):
        # Avoid str(exc) — PreparedRequest URLs include query params with keys
        return _redact(type(exc).__name__, *secrets)
    return _redact(f"{type(exc).__name__}: {exc}", *secrets)


def _safe_float(val: Any) -> Optional[float]:
    if val is None or val == "" or val == "None" or val == "-":
        return None
    try:
        f = float(val)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


def _safe_int(val: Any) -> Optional[int]:
    f = _safe_float(val)
    if f is None:
        return None
    try:
        return int(f)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# yfinance
# ---------------------------------------------------------------------------
def fetch_yfinance(ticker: str) -> dict:
    """
    Pull fundamentals + consensus targets from ticker.info.
    Returns a dict with None defaults on failure.
    """
    empty = {
        "name": None,
        "current_price": None,
        "yf_target_mean": None,
        "yf_target_median": None,
        "yf_target_high": None,
        "yf_target_low": None,
        "n_analysts": None,
        "recommendation_key": None,
        "trailing_pe": None,
        "forward_pe": None,
        "market_cap": None,
        "avg_volume": None,
        "fifty_two_week_high": None,
        "fifty_two_week_low": None,
        "beta": None,
        "sector": None,
        "industry": None,
    }
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        price = _safe_float(info.get("currentPrice"))
        if price is None:
            price = _safe_float(info.get("regularMarketPrice"))
        if price is None:
            try:
                hist = t.history(period="1d")
                if not hist.empty:
                    price = float(hist["Close"].iloc[-1])
            except Exception:
                pass

        return {
            "name": info.get("longName") or info.get("shortName"),
            "current_price": round(price, 2) if price is not None else None,
            "yf_target_mean": _safe_float(info.get("targetMeanPrice")),
            "yf_target_median": _safe_float(info.get("targetMedianPrice")),
            "yf_target_high": _safe_float(info.get("targetHighPrice")),
            "yf_target_low": _safe_float(info.get("targetLowPrice")),
            "n_analysts": _safe_int(info.get("numberOfAnalystOpinions")),
            "recommendation_key": info.get("recommendationKey"),
            "trailing_pe": _safe_float(info.get("trailingPE")),
            "forward_pe": _safe_float(info.get("forwardPE")),
            "market_cap": _safe_float(info.get("marketCap")),
            "avg_volume": _safe_int(info.get("averageVolume")),
            "fifty_two_week_high": _safe_float(info.get("fiftyTwoWeekHigh")),
            "fifty_two_week_low": _safe_float(info.get("fiftyTwoWeekLow")),
            "beta": _safe_float(info.get("beta")),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
        }
    except Exception as e:
        print(f"  [WARN] {ticker}: yfinance failed — {e}")
        return empty


# ---------------------------------------------------------------------------
# Financial Modeling Prep (stable API)
# ---------------------------------------------------------------------------
def _fmp_first_row(data: Any) -> dict:
    if isinstance(data, list):
        return data[0] if data and isinstance(data[0], dict) else {}
    if isinstance(data, dict):
        if data.get("Error Message") or data.get("error"):
            return {}
        return data
    return {}


def fetch_fmp_consensus(ticker: str, api_key: str) -> dict:
    """
    Free-tier consensus targets from /stable/price-target-consensus.
    Returns fmp_latest_target (= targetConsensus) plus high/low/median.
    """
    empty = {
        "fmp_latest_target": None,
        "fmp_target_high": None,
        "fmp_target_low": None,
        "fmp_target_median": None,
    }
    try:
        resp = requests.get(
            FMP_CONSENSUS_URL,
            params={"symbol": ticker, "apikey": api_key},
            timeout=30,
        )
        if resp.status_code == 402:
            print(f"  [WARN] {ticker}: FMP consensus restricted under current plan")
            return empty
        resp.raise_for_status()
        row = _fmp_first_row(resp.json())
        if not row:
            return empty
        return {
            "fmp_latest_target": _safe_float(row.get("targetConsensus")),
            "fmp_target_high": _safe_float(row.get("targetHigh")),
            "fmp_target_low": _safe_float(row.get("targetLow")),
            "fmp_target_median": _safe_float(row.get("targetMedian")),
        }
    except Exception as e:
        print(f"  [WARN] {ticker}: FMP consensus failed — {_safe_exc(e, api_key)}")
        return empty


def probe_fmp_price_target_news(api_key: str) -> bool:
    """
    One-shot check: named price-target-news is paid on many plans (HTTP 402).
    Returns True if the endpoint returns usable rows for AAPL.
    """
    try:
        resp = requests.get(
            FMP_PRICE_TARGET_NEWS_URL,
            params={"symbol": "AAPL", "page": 0, "limit": 1, "apikey": api_key},
            timeout=30,
        )
        if resp.status_code in (401, 402, 403):
            print(
                "[INFO] FMP price-target-news not available on this plan — "
                "using grades (firm + rating, no individual $ targets)"
            )
            return False
        data = resp.json()
        return isinstance(data, list) and len(data) > 0
    except Exception:
        return False


def fetch_fmp_price_target_news(
    ticker: str, api_key: str, limit: int = FMP_ANALYST_LIMIT
) -> list[dict]:
    """Named per-firm price targets (paid endpoint on most plans)."""
    try:
        resp = requests.get(
            FMP_PRICE_TARGET_NEWS_URL,
            params={"symbol": ticker, "page": 0, "limit": limit, "apikey": api_key},
            timeout=30,
        )
        if resp.status_code in (401, 402, 403):
            return []
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            return []
        rows = []
        for item in data[:limit]:
            rows.append({
                "symbol": item.get("symbol") or ticker,
                "analyst_name": item.get("analystName"),
                "analyst_company": item.get("analystCompany"),
                "price_target": _safe_float(item.get("priceTarget")),
                "adj_price_target": _safe_float(item.get("adjPriceTarget") or item.get("priceTarget")),
                "price_when_posted": _safe_float(item.get("priceWhenPosted")),
                "news_url": item.get("newsURL") or item.get("newsUrl"),
                "news_title": item.get("newsTitle"),
                "news_base_url": item.get("newsBaseURL") or item.get("newsBaseUrl"),
                "recommendation_key": item.get("recommendationKey") or item.get("newGrade"),
                "date": (item.get("publishedDate") or item.get("date") or "")[:10] or None,
                "source": "price-target-news",
            })
        return rows
    except Exception as e:
        print(f"  [WARN] {ticker}: FMP news failed — {_safe_exc(e, api_key)}")
        return []


def fetch_fmp_grades(ticker: str, api_key: str, limit: int = FMP_ANALYST_LIMIT) -> list[dict]:
    """
    Free-tier firm grade history from /stable/grades.
    Has firm + rating + date, but not dollar price targets.
    """
    try:
        resp = requests.get(
            FMP_GRADES_URL,
            params={"symbol": ticker, "apikey": api_key},
            timeout=30,
        )
        if resp.status_code in (401, 402, 403):
            return []
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            return []
        rows = []
        for item in data[:limit]:
            rows.append({
                "symbol": item.get("symbol") or ticker,
                "analyst_name": None,
                "analyst_company": item.get("gradingCompany"),
                "price_target": None,
                "adj_price_target": None,
                "price_when_posted": None,
                "news_url": None,
                "news_title": None,
                "news_base_url": None,
                "recommendation_key": item.get("newGrade"),
                "previous_grade": item.get("previousGrade"),
                "action": item.get("action"),
                "date": (item.get("date") or "")[:10] or None,
                "source": "grades",
            })
        return rows
    except Exception as e:
        print(f"  [WARN] {ticker}: FMP grades failed — {_safe_exc(e, api_key)}")
        return []


# ---------------------------------------------------------------------------
# Alpha Vantage — third consensus (rate-limited)
# ---------------------------------------------------------------------------
def fetch_alpha_vantage_target(ticker: str, api_key: str) -> Optional[dict]:
    """
    Fetch OVERVIEW and extract AnalystTargetPrice.
    Returns {"av_target": float|None, "fetched_at": iso} or None on hard failure.
    """
    try:
        resp = requests.get(
            AV_OVERVIEW_URL,
            params={
                "function": "OVERVIEW",
                "symbol": ticker,
                "apikey": api_key,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data or "Note" in data or "Information" in data:
            msg = data.get("Note") or data.get("Information") or "empty/rate-limited"
            print(f"  [WARN] {ticker}: Alpha Vantage — {_redact(msg, api_key)}")
            return None
        if "Error Message" in data:
            print(f"  [WARN] {ticker}: Alpha Vantage — {_redact(data['Error Message'], api_key)}")
            return None

        return {
            "av_target": _safe_float(data.get("AnalystTargetPrice")),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        print(f"  [WARN] {ticker}: Alpha Vantage failed — {_safe_exc(e, api_key)}")
        return None


def select_av_refresh_tickers(
    tickers_by_mcap: list[str],
    av_cache: dict[str, dict],
    limit: int = AV_DAILY_LIMIT,
) -> list[str]:
    """
    Pick up to `limit` tickers to refresh from Alpha Vantage.
    Priority: missing from cache first, then oldest fetched_at, among highest mcap.
    """
    missing = [t for t in tickers_by_mcap if t not in av_cache or av_cache[t].get("av_target") is None]
    if len(missing) >= limit:
        return missing[:limit]

    remaining_slots = limit - len(missing)
    cached = [t for t in tickers_by_mcap if t not in missing]

    def _fetched_at(t: str) -> str:
        return av_cache.get(t, {}).get("fetched_at") or ""

    cached_sorted = sorted(cached, key=_fetched_at)  # oldest first
    return missing + cached_sorted[:remaining_slots]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def fetch_all(
    tickers: list[str],
    prev_snapshot: Optional[dict] = None,
    av_daily_limit: int = AV_DAILY_LIMIT,
) -> tuple[dict[str, dict], dict[str, dict]]:
    """
    Fetch all three sources for every ticker.

    Returns (results, av_cache) where results maps ticker -> {
        ...yfinance fields...,
        "fmp_analysts": [...],
        "fmp_latest_target": float|None,
        "av_target": float|None,
        "av_fetched_at": str|None,
        "av_from_cache": bool,
    }
    and av_cache is the updated Alpha Vantage cache to persist in the snapshot.
    """
    load_dotenv()
    fmp_key = _env_key("FMP_API_KEY")
    av_key = _env_key("ALPHA_VANTAGE_API_KEY")

    if not fmp_key:
        print("[WARN] FMP_API_KEY not set — skipping FMP fetch (add to .env or env)")
    if not av_key:
        print("[WARN] ALPHA_VANTAGE_API_KEY not set — using cache only for AV targets")

    av_cache: dict[str, dict] = {}
    if prev_snapshot:
        av_cache = dict(prev_snapshot.get("av_cache") or {})
        # Also accept per-ticker av fields from older snapshot shapes
        for t_data in prev_snapshot.get("tickers") or []:
            if isinstance(t_data, dict) and t_data.get("ticker"):
                tk = t_data["ticker"]
                if tk not in av_cache and t_data.get("av_target") is not None:
                    av_cache[tk] = {
                        "av_target": t_data.get("av_target"),
                        "fetched_at": t_data.get("av_fetched_at"),
                    }

    results: dict[str, dict] = {}
    total = len(tickers)

    # ---- Pass 1: yfinance (all tickers) ----
    print(f"--- yfinance ({total} tickers) ---")
    for i, ticker in enumerate(tickers, 1):
        print(f"[{i}/{total}] yfinance {ticker}")
        results[ticker] = {"ticker": ticker, **fetch_yfinance(ticker)}
        time.sleep(YF_DELAY_SEC)

    # ---- Pass 2: FMP consensus (+ firm grades or paid news) ----
    if fmp_key:
        fmp_reqs = 0
        use_news = probe_fmp_price_target_news(fmp_key)
        fmp_reqs += 1
        detail_mode = "price-target-news" if use_news else "grades"
        # Consensus for every ticker; detail rows only while under daily budget
        detail_budget = max(0, FMP_DAILY_BUDGET - total - fmp_reqs)
        by_mcap = sorted(
            tickers,
            key=lambda t: results[t].get("market_cap") or 0,
            reverse=True,
        )
        detail_tickers = set(by_mcap[:detail_budget])

        print(
            f"\n--- FMP stable ({total} consensus"
            f" + {len(detail_tickers)} {detail_mode}) ---"
        )
        for i, ticker in enumerate(tickers, 1):
            print(f"[{i}/{total}] FMP {ticker}")
            consensus = fetch_fmp_consensus(ticker, fmp_key)
            fmp_reqs += 1
            results[ticker].update(consensus)

            if ticker in detail_tickers:
                if use_news:
                    analysts = fetch_fmp_price_target_news(ticker, fmp_key)
                else:
                    analysts = fetch_fmp_grades(ticker, fmp_key)
                fmp_reqs += 1
            else:
                analysts = []
            results[ticker]["fmp_analysts"] = analysts
            results[ticker]["fmp_detail_source"] = detail_mode if analysts else None
            time.sleep(FMP_DELAY_SEC)
        print(f"[INFO] FMP requests used this run: ~{fmp_reqs}")
    else:
        for ticker in tickers:
            results[ticker]["fmp_analysts"] = []
            results[ticker]["fmp_latest_target"] = None
            results[ticker]["fmp_detail_source"] = None

    # ---- Pass 3: Alpha Vantage (top N by market cap, rest from cache) ----
    by_mcap = sorted(
        tickers,
        key=lambda t: results[t].get("market_cap") or 0,
        reverse=True,
    )
    to_refresh = select_av_refresh_tickers(by_mcap, av_cache, limit=av_daily_limit) if av_key else []

    print(f"\n--- Alpha Vantage (refresh {len(to_refresh)}/{av_daily_limit}, rest cached) ---")
    refreshed: set[str] = set()
    for i, ticker in enumerate(to_refresh, 1):
        print(f"[{i}/{len(to_refresh)}] Alpha Vantage {ticker}")
        av = fetch_alpha_vantage_target(ticker, av_key)  # type: ignore[arg-type]
        if av is not None:
            av_cache[ticker] = av
            refreshed.add(ticker)
        time.sleep(AV_DELAY_SEC)

    for ticker in tickers:
        cached = av_cache.get(ticker) or {}
        results[ticker]["av_target"] = cached.get("av_target")
        results[ticker]["av_fetched_at"] = cached.get("fetched_at")
        results[ticker]["av_from_cache"] = ticker not in refreshed

    return results, av_cache
