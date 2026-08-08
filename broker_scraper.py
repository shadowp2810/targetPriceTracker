"""
Scrape sell-side recommendations from PriceTargets.com brokerage pages.

One HTTP GET per configured broker per run. On failure, reuse that broker's
prior cache from the snapshot. Exact ticker matches against the US universe
are joined into each row's `firm_targets` map.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.pricetargets.com/brokerages"
USER_AGENT = (
    "Mozilla/5.0 (compatible; TargetPriceTracker/1.0; +https://targets.pranavp.dev)"
)
MAX_ROWS = 100
SCRAPE_DELAY_SEC = 1.0

# Configurable list — same HTML table shape on PriceTargets.com
BROKERS: list[dict[str, str]] = [
    {
        "slug": "morgan_stanley",
        "name": "Morgan Stanley",
        "short": "MS",
        "path": "morgan-stanley-stock-recommendations",
    },
    {
        "slug": "goldman_sachs",
        "name": "Goldman Sachs",
        "short": "GS",
        "path": "goldman-sachs-group-stock-recommendations",
    },
    {
        "slug": "jpmorgan",
        "name": "JPMorgan",
        "short": "JPM",
        "path": "jpmorgan-chase-co-stock-recommendations",
    },
    {
        "slug": "rbc",
        "name": "RBC",
        "short": "RBC",
        "path": "royal-bank-of-canada-stock-recommendations",
    },
    {
        "slug": "desjardins",
        "name": "Desjardins",
        "short": "DJ",
        "path": "desjardins-stock-recommendations",
    },
]

_MONEY_RE = re.compile(
    r"(?P<cad>C\$)?\s*\$?\s*(?P<num>\d+(?:,\d{3})*(?:\.\d+)?)",
    re.IGNORECASE,
)


def broker_meta(slug: str) -> Optional[dict[str, str]]:
    for b in BROKERS:
        if b["slug"] == slug:
            return b
    return None


def broker_source_url(path: str) -> str:
    return f"{BASE_URL}/{path.strip('/')}/"


def _parse_money(text: str) -> tuple[Optional[float], Optional[str]]:
    """Parse 'C$108.00', '$119.00', 'C$43.50 ➝ C$41.00' → (amount, CAD|USD|None)."""
    if not text:
        return None, None
    cleaned = text.replace("\xa0", " ").strip()
    if not cleaned or cleaned == "—":
        return None, None

    for sep in ("➝", "→", "->", " to "):
        if sep in cleaned:
            cleaned = cleaned.split(sep)[-1].strip()
            break

    matches = list(_MONEY_RE.finditer(cleaned))
    if not matches:
        return None, None
    m = matches[-1]
    try:
        amount = float(m.group("num").replace(",", ""))
    except ValueError:
        return None, None

    span_start = max(0, m.start() - 2)
    nearby = cleaned[span_start : m.end()]
    if "C$" in nearby:
        currency = "CAD"
    elif "$" in nearby:
        currency = "USD"
    else:
        currency = None
    return amount, currency


def _parse_date(text: str, sort_value: str = "") -> Optional[str]:
    if sort_value and len(sort_value) >= 8 and sort_value[:8].isdigit():
        raw = sort_value[:8]
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    text = (text or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_broker_html(html: str) -> list[dict]:
    """Parse a PriceTargets brokerage recommendations table."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        return []

    rows: list[dict] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 5:
            continue

        date_cell, company_cell, action_cell = cells[0], cells[1], cells[2]
        price_cell, target_cell = cells[3], cells[4]
        rating_cell = cells[5] if len(cells) > 5 else None

        ticker_el = company_cell.select_one(".ticker-area")
        name_el = company_cell.select_one(".title-area")
        ticker = (ticker_el.get_text(strip=True) if ticker_el else "").upper()
        ticker = ticker.split()[0] if ticker else ""
        if not ticker:
            continue

        name = name_el.get_text(strip=True) if name_el else company_cell.get_text(" ", strip=True)
        action = action_cell.get_text(" ", strip=True)
        rating = rating_cell.get_text(" ", strip=True) if rating_cell else None
        if rating:
            for sep in ("➝", "→", "->"):
                if sep in rating:
                    rating = rating.split(sep)[-1].strip()
                    break

        price, price_ccy = _parse_money(price_cell.get_text(" ", strip=True))
        target, target_ccy = _parse_money(target_cell.get_text(" ", strip=True))
        date_iso = _parse_date(
            date_cell.get_text(strip=True),
            sort_value=str(date_cell.get("data-sort-value") or ""),
        )

        upside = None
        if target is not None and price is not None and price != 0:
            if price_ccy == target_ccy or price_ccy is None or target_ccy is None:
                upside = round((target - price) / price * 100, 2)

        rows.append({
            "date": date_iso,
            "ticker": ticker,
            "name": name,
            "action": action or None,
            "price": price,
            "price_currency": price_ccy,
            "target": target,
            "target_currency": target_ccy,
            "rating": rating or None,
            "upside_pct": upside,
        })

    return rows[:MAX_ROWS]


def _latest_by_ticker(rows: list[dict]) -> dict[str, dict]:
    by_ticker: dict[str, dict] = {}
    for row in rows:
        tk = row["ticker"]
        prev = by_ticker.get(tk)
        if prev is None or (row.get("date") or "") > (prev.get("date") or ""):
            by_ticker[tk] = row
    return by_ticker


def _empty_broker_payload(
    broker: dict[str, str],
    prev: Optional[dict] = None,
) -> dict:
    url = broker_source_url(broker["path"])
    if prev and (prev.get("by_ticker") or prev.get("rows")):
        out = dict(prev)
        out["from_cache"] = True
        out["slug"] = broker["slug"]
        out["name"] = broker["name"]
        out["short"] = broker["short"]
        out["source_url"] = out.get("source_url") or url
        return out
    return {
        "slug": broker["slug"],
        "name": broker["name"],
        "short": broker["short"],
        "fetched_at": None,
        "source_url": url,
        "from_cache": True,
        "by_ticker": {},
        "rows": [],
    }


def _merge_by_ticker(
    fresh: dict[str, dict],
    previous: Optional[dict[str, dict]],
) -> dict[str, dict]:
    """
    Merge today's page into the prior map. PriceTargets only lists ~100 recent
    ratings, so without merging mega-caps fall out of cache between updates.
    Newer ISO dates win; equal/missing dates prefer the fresh row.
    """
    merged = dict(previous or {})
    for ticker, row in fresh.items():
        prev = merged.get(ticker)
        if prev is None or (row.get("date") or "") >= (prev.get("date") or ""):
            merged[ticker] = row
    return merged


def fetch_broker_recommendations(
    broker: dict[str, str],
    prev_cache: Optional[dict] = None,
) -> dict:
    """Fetch + parse one brokerage page; merge into prior by_ticker cache."""
    url = broker_source_url(broker["path"])
    label = broker["name"]
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"  [WARN] {label}: HTTP {resp.status_code} — using cache")
            return _empty_broker_payload(broker, prev=prev_cache)

        rows = parse_broker_html(resp.text)
        if not rows:
            print(f"  [WARN] {label}: parsed 0 rows — using cache")
            return _empty_broker_payload(broker, prev=prev_cache)

        fresh = _latest_by_ticker(rows)
        prev_map = (prev_cache or {}).get("by_ticker") or {}
        by_ticker = _merge_by_ticker(fresh, prev_map)
        payload = {
            "slug": broker["slug"],
            "name": broker["name"],
            "short": broker["short"],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source_url": url,
            "from_cache": False,
            "by_ticker": by_ticker,
            "rows": rows,  # today's page only (for reference)
        }
        print(
            f"  [INFO] {label}: {len(rows)} page rows → "
            f"{len(by_ticker)} cached tickers (+{max(0, len(by_ticker) - len(prev_map))} new)"
        )
        return payload
    except Exception as e:
        print(f"  [WARN] {label}: {type(e).__name__} — using cache")
        return _empty_broker_payload(broker, prev=prev_cache)


def migrate_legacy_desjardins_cache(prev_snapshot: Optional[dict]) -> dict[str, dict]:
    """Lift old top-level desjardins_cache into broker_cache['desjardins']."""
    broker_cache = dict((prev_snapshot or {}).get("broker_cache") or {})
    legacy = (prev_snapshot or {}).get("desjardins_cache")
    if legacy and "desjardins" not in broker_cache:
        meta = broker_meta("desjardins") or {
            "slug": "desjardins",
            "name": "Desjardins",
            "short": "DJ",
            "path": "desjardins-stock-recommendations",
        }
        broker_cache["desjardins"] = {
            **legacy,
            "slug": "desjardins",
            "name": meta["name"],
            "short": meta["short"],
            "source_url": legacy.get("source_url") or broker_source_url(meta["path"]),
        }
    return broker_cache


def fetch_all_brokers(prev_snapshot: Optional[dict] = None) -> dict[str, dict]:
    """
    Scrape every configured broker. Returns slug -> payload.
    """
    prev_cache = migrate_legacy_desjardins_cache(prev_snapshot)
    out: dict[str, dict] = {}
    print(f"\n--- Broker scrapes (PriceTargets.com, {len(BROKERS)} firms) ---")
    for i, broker in enumerate(BROKERS):
        slug = broker["slug"]
        out[slug] = fetch_broker_recommendations(broker, prev_cache=prev_cache.get(slug))
        if i < len(BROKERS) - 1:
            time.sleep(SCRAPE_DELAY_SEC)
    return out


def attach_brokers_to_results(
    results: dict[str, dict],
    broker_cache: dict[str, dict],
) -> dict[str, int]:
    """
    Exact-match join into row['firm_targets'][slug].
    Also mirrors Desjardins onto legacy desjardins_* fields.
    Returns slug -> match count.
    """
    match_counts = {b["slug"]: 0 for b in BROKERS}
    for ticker, row in results.items():
        if ticker.startswith("__"):
            continue
        firm_targets: dict[str, dict] = {}
        for broker in BROKERS:
            slug = broker["slug"]
            hit = (broker_cache.get(slug) or {}).get("by_ticker", {}).get(ticker)
            if not hit:
                continue
            firm_targets[slug] = {
                "slug": slug,
                "name": broker["name"],
                "short": broker["short"],
                "target": hit.get("target"),
                "rating": hit.get("rating"),
                "date": hit.get("date"),
                "action": hit.get("action"),
                "currency": hit.get("target_currency"),
                "price": hit.get("price"),
                "price_currency": hit.get("price_currency"),
            }
            match_counts[slug] += 1

        row["firm_targets"] = firm_targets
        row["n_firm_targets"] = len(firm_targets)

        # Legacy Desjardins flat fields (dashboard / week baseline compat)
        dj = firm_targets.get("desjardins")
        if dj:
            row["desjardins_target"] = dj.get("target")
            row["desjardins_rating"] = dj.get("rating")
            row["desjardins_date"] = dj.get("date")
            row["desjardins_action"] = dj.get("action")
            row["desjardins_currency"] = dj.get("currency")
            row["desjardins_price"] = dj.get("price")
            row["desjardins_price_currency"] = dj.get("price_currency")
        else:
            row["desjardins_target"] = None
            row["desjardins_rating"] = None
            row["desjardins_date"] = None
            row["desjardins_action"] = None
            row["desjardins_currency"] = None
            row["desjardins_price"] = None
            row["desjardins_price_currency"] = None

    return match_counts


def broker_picks_for_dashboard(broker_cache: dict[str, dict]) -> list[dict]:
    """
    One entry per configured broker for the dashboard picks panels.
    """
    panels = []
    for broker in BROKERS:
        slug = broker["slug"]
        payload = broker_cache.get(slug) or {}
        picks = list((payload.get("by_ticker") or {}).values())
        picks.sort(key=lambda r: r.get("date") or "", reverse=True)
        panels.append({
            "slug": slug,
            "name": broker["name"],
            "short": broker["short"],
            "source_url": payload.get("source_url") or broker_source_url(broker["path"]),
            "from_cache": payload.get("from_cache", False),
            "fetched_at": payload.get("fetched_at"),
            "picks": picks,
        })
    return panels
