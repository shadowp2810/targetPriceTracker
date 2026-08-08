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
import time
from datetime import datetime, timezone
from typing import Any, Optional

import requests
import yfinance as yf

# FMP v4 price-target returns named analyst rows matching:
# analystName, analystCompany, priceTarget, adjPriceTarget, priceWhenPosted, ...
FMP_PRICE_TARGET_URL = "https://financialmodelingprep.com/api/v4/price-target"
AV_OVERVIEW_URL = "https://www.alphavantage.co/query"

AV_DAILY_LIMIT = 25
FMP_ANALYST_LIMIT = 5
YF_DELAY_SEC = 0.15
FMP_DELAY_SEC = 0.25
AV_DELAY_SEC = 12.5  # free tier ~5 req/min; stay under the limit


def _env_key(name: str) -> Optional[str]:
    val = os.environ.get(name, "").strip()
    return val or None


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
# Financial Modeling Prep — named analyst targets
# ---------------------------------------------------------------------------
def fetch_fmp_analysts(ticker: str, api_key: str, limit: int = FMP_ANALYST_LIMIT) -> list[dict]:
    """
    Fetch the latest named analyst price-target updates for a ticker.
    Uses FMP v4 /price-target (fields: analystName, analystCompany, priceTarget, ...).
    """
    try:
        resp = requests.get(
            FMP_PRICE_TARGET_URL,
            params={"symbol": ticker, "apikey": api_key},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            # FMP sometimes returns {"Error Message": ...}
            if isinstance(data, dict) and data.get("Error Message"):
                print(f"  [WARN] {ticker}: FMP error — {data['Error Message']}")
            return []

        rows = []
        for item in data[:limit]:
            rows.append({
                "symbol": item.get("symbol") or ticker,
                "analyst_name": item.get("analystName"),
                "analyst_company": item.get("analystCompany"),
                "price_target": _safe_float(item.get("priceTarget")),
                "adj_price_target": _safe_float(item.get("adjPriceTarget")),
                "price_when_posted": _safe_float(item.get("priceWhenPosted")),
                "news_url": item.get("newsURL"),
                "news_title": item.get("newsTitle"),
                "news_base_url": item.get("newsBaseURL"),
                "recommendation_key": item.get("recommendationKey"),
                "date": (item.get("publishedDate") or item.get("date") or "")[:10] or None,
            })
        return rows
    except Exception as e:
        print(f"  [WARN] {ticker}: FMP failed — {e}")
        return []


def fmp_latest_target(analysts: list[dict]) -> Optional[float]:
    """Most recent non-null price target from the FMP analyst list."""
    for row in analysts:
        pt = row.get("adj_price_target") or row.get("price_target")
        if pt is not None:
            return pt
    return None


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
            print(f"  [WARN] {ticker}: Alpha Vantage — {msg}")
            return None
        if "Error Message" in data:
            print(f"  [WARN] {ticker}: Alpha Vantage — {data['Error Message']}")
            return None

        return {
            "av_target": _safe_float(data.get("AnalystTargetPrice")),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        print(f"  [WARN] {ticker}: Alpha Vantage failed — {e}")
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
    fmp_key = _env_key("FMP_API_KEY")
    av_key = _env_key("ALPHA_VANTAGE_API_KEY")

    if not fmp_key:
        print("[WARN] FMP_API_KEY not set — skipping named analyst fetch")
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

    # ---- Pass 2: FMP named analysts (all tickers if key present) ----
    if fmp_key:
        print(f"\n--- FMP price targets ({total} tickers) ---")
        for i, ticker in enumerate(tickers, 1):
            print(f"[{i}/{total}] FMP {ticker}")
            analysts = fetch_fmp_analysts(ticker, fmp_key)
            results[ticker]["fmp_analysts"] = analysts
            results[ticker]["fmp_latest_target"] = fmp_latest_target(analysts)
            time.sleep(FMP_DELAY_SEC)
    else:
        for ticker in tickers:
            results[ticker]["fmp_analysts"] = []
            results[ticker]["fmp_latest_target"] = None

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
