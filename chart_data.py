"""
Build per-ticker chart series: weekly price, accumulating consensus target, earnings dates.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from typing import Any, Optional

import yfinance as yf

PRICE_PERIOD = "1y"
PRICE_INTERVAL = "1wk"
RECENT_DAILY_PERIOD = "10d"
MAX_TARGET_POINTS = 130  # ~6 months of weekday snapshots
MAX_EARNINGS = 12  # ~3y of quarters; trimmed to price window later
EARNINGS_FETCH_LIMIT = 24


def _iso(d: Any) -> Optional[str]:
    if d is None:
        return None
    if hasattr(d, "date"):
        try:
            return str(d.date())
        except Exception:
            pass
    if hasattr(d, "strftime"):
        try:
            return d.strftime("%Y-%m-%d")
        except Exception:
            pass
    s = str(d)
    return s[:10] if len(s) >= 10 else None


def _parse_closes(raw, tickers: list[str]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {t: [] for t in tickers}
    if raw is None or getattr(raw, "empty", True):
        return out
    if len(tickers) == 1:
        t = tickers[0]
        closes = raw["Close"].dropna() if "Close" in raw.columns else raw.iloc[:, 3].dropna()
        for idx, val in closes.items():
            d = _iso(idx)
            if d:
                out[t].append({"date": d, "close": round(float(val), 2)})
        return out
    for t in tickers:
        try:
            if t not in raw.columns.get_level_values(0):
                continue
            series = raw[t]["Close"].dropna()
            for idx, val in series.items():
                d = _iso(idx)
                if d:
                    out[t].append({"date": d, "close": round(float(val), 2)})
        except Exception:
            continue
    return out


def _download_prices(tickers: list[str], period: str, interval: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {t: [] for t in tickers}
    if not tickers:
        return out
    try:
        raw = yf.download(
            tickers=tickers,
            period=period,
            interval=interval,
            group_by="ticker",
            auto_adjust=True,
            threads=True,
            progress=False,
        )
        out = _parse_closes(raw, tickers)
    except Exception as e:
        print(f"[WARN] Price download failed ({interval}) — {type(e).__name__}: {e}")
    return out


def merge_weekly_with_recent_daily(
    weekly: dict[str, list[dict]],
    daily: dict[str, list[dict]],
) -> dict[str, list[dict]]:
    """
    Yahoo weekly bars are labeled with the week-start Monday, but Close is the
    latest session in that week — so mid-week the last label lags the real date.
    Keep completed weeks, then splice in daily bars for the current week.
    """
    from datetime import timedelta

    out: dict[str, list[dict]] = {}
    for t, wseries in weekly.items():
        dseries = daily.get(t) or []
        if not dseries:
            out[t] = list(wseries)
            continue
        if not wseries:
            out[t] = list(dseries)
            continue
        last_daily = dseries[-1]["date"]
        try:
            last_d = datetime.strptime(last_daily[:10], "%Y-%m-%d").date()
            week_start = (last_d - timedelta(days=last_d.weekday())).isoformat()
        except ValueError:
            out[t] = list(wseries)
            continue
        kept = [p for p in wseries if p["date"] < week_start]
        recent = [p for p in dseries if p["date"] >= week_start]
        out[t] = kept + recent if recent else list(wseries)
    return out


def fetch_weekly_prices(tickers: list[str]) -> dict[str, list[dict]]:
    """
    Chart prices: weekly history for 1y, with the current week filled from daily
    bars so the series ends on the latest trading day (not week-start Monday).
    """
    out: dict[str, list[dict]] = {t: [] for t in tickers}
    if not tickers:
        return out
    print(f"--- Chart prices (yfinance {PRICE_PERIOD} {PRICE_INTERVAL} + {RECENT_DAILY_PERIOD} daily) ---")
    # Chunk large batches (firm-pick refreshes)
    chunk = 120
    weekly: dict[str, list[dict]] = {t: [] for t in tickers}
    daily: dict[str, list[dict]] = {t: [] for t in tickers}
    for i in range(0, len(tickers), chunk):
        part = tickers[i : i + chunk]
        if len(tickers) > chunk:
            print(f"  price chunk {i // chunk + 1}/{(len(tickers) + chunk - 1) // chunk} ({len(part)})")
        weekly.update(_download_prices(part, PRICE_PERIOD, PRICE_INTERVAL))
        daily.update(_download_prices(part, RECENT_DAILY_PERIOD, "1d"))
    out = merge_weekly_with_recent_daily(weekly, daily)
    n_ok = sum(1 for t in tickers if out[t])
    print(f"[INFO] Chart prices: {n_ok}/{len(tickers)} tickers")
    return out


def _earnings_from_calendar(t: yf.Ticker) -> list[str]:
    dates: list[str] = []
    try:
        cal = t.calendar
        if not cal:
            return dates
        earnings = cal.get("Earnings Date") if isinstance(cal, dict) else None
        if earnings is None and hasattr(cal, "get"):
            earnings = cal.get("Earnings Date")
        if isinstance(earnings, (list, tuple)):
            for item in earnings:
                d = _iso(item)
                if d:
                    dates.append(d)
        else:
            d = _iso(earnings)
            if d:
                dates.append(d)
    except Exception:
        pass
    return dates


def _earnings_for_ticker(ticker: str, retries: int = 2) -> list[str]:
    dates: list[str] = []
    for attempt in range(retries + 1):
        dates = []
        try:
            t = yf.Ticker(ticker)
            # Historical + upcoming (primary)
            try:
                ed = t.get_earnings_dates(limit=EARNINGS_FETCH_LIMIT)
                if ed is not None and not ed.empty:
                    for idx in ed.index:
                        d = _iso(idx)
                        if d:
                            dates.append(d)
            except Exception:
                pass
            # Fallback property used by older yfinance paths
            if len(dates) < 2:
                try:
                    ed2 = getattr(t, "earnings_dates", None)
                    if ed2 is not None and hasattr(ed2, "empty") and not ed2.empty:
                        for idx in ed2.index:
                            d = _iso(idx)
                            if d:
                                dates.append(d)
                except Exception:
                    pass
            dates.extend(_earnings_from_calendar(t))
        except Exception:
            pass
        dates = sorted(set(dates))
        # Yahoo often rate-limits mid-run and only calendar survives → retry
        if len(dates) >= 2 or attempt == retries:
            return dates
    return dates


def fetch_earnings_dates(
    tickers: list[str],
    max_workers: int = 4,
    prev_chart: Optional[dict] = None,
) -> dict[str, list[str]]:
    """
    Fetch earnings dates; merge with any previously stored chart_history dates
    so a flaky Yahoo pass does not wipe past ER markers.
    """
    print(f"--- Earnings dates ({len(tickers)} tickers) ---")
    prev_chart = prev_chart or {}
    out: dict[str, list[str]] = {t: [] for t in tickers}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_earnings_for_ticker, t): t for t in tickers}
        done = 0
        for fut in as_completed(futures):
            t = futures[fut]
            try:
                out[t] = fut.result()
            except Exception:
                out[t] = []
            done += 1
            if done % 40 == 0 or done == len(tickers):
                print(f"  [{done}/{len(tickers)}] earnings…")

    # Merge prior history (union)
    for t in tickers:
        prev = prev_chart.get(t) or {}
        prev_earn = prev.get("earnings") if isinstance(prev, dict) else None
        if isinstance(prev_earn, list) and prev_earn:
            out[t] = sorted(set(out[t]) | {d for d in prev_earn if isinstance(d, str)})

    n_ok = sum(1 for t in tickers if out[t])
    n_rich = sum(1 for t in tickers if len(out[t]) >= 2)
    print(f"[INFO] Earnings dates: {n_ok}/{len(tickers)} with ≥1, {n_rich} with ≥2")
    return out


def update_target_history(
    analyzed: list[dict],
    prev_chart: Optional[dict],
    as_of: str,
) -> dict[str, list[dict]]:
    """
    Append today's primary consensus target per ticker (replace same-day).
    Returns ticker -> [{date, target, yf, fmp, av}, ...]
    """
    prev_chart = prev_chart or {}
    today = as_of[:10]
    out: dict[str, list[dict]] = {}

    for row in analyzed:
        ticker = row["ticker"]
        prev_list = list((prev_chart.get(ticker) or {}).get("targets") or [])
        # Also accept old shape: prev_chart[ticker] was a list
        if isinstance(prev_chart.get(ticker), list):
            prev_list = list(prev_chart[ticker])

        point = {
            "date": today,
            "target": row.get("primary_target"),
            "yf": row.get("yf_target_mean"),
            "fmp": row.get("fmp_latest_target"),
            "av": row.get("av_target"),
            "price": row.get("current_price"),
        }
        if point["target"] is None and point["yf"] is None and point["fmp"] is None:
            # Keep prior history even if today has no target
            out[ticker] = prev_list[-MAX_TARGET_POINTS:]
            continue

        if prev_list and prev_list[-1].get("date") == today:
            prev_list[-1] = point
        else:
            prev_list.append(point)
        out[ticker] = prev_list[-MAX_TARGET_POINTS:]
    return out


def next_earnings_on_or_after(earn: list[str], as_of: Optional[str] = None) -> Optional[str]:
    """Earliest earnings date on/after as_of (ISO day)."""
    day = (as_of or date.today().isoformat())[:10]
    future = sorted({d[:10] for d in earn if isinstance(d, str) and len(d) >= 10 and d[:10] >= day})
    return future[0] if future else None


def attach_charts(
    analyzed: list[dict],
    prices: dict[str, list[dict]],
    targets: dict[str, list[dict]],
    earnings: dict[str, list[str]],
    as_of: Optional[str] = None,
) -> dict:
    """
    Attach compact `chart` payloads to each analyzed row.
    Returns chart_history structure to persist in the snapshot.
    """
    history: dict[str, dict] = {}
    as_of_day = (as_of or date.today().isoformat())[:10]
    for row in analyzed:
        ticker = row["ticker"]
        price_series = prices.get(ticker) or []
        target_series = targets.get(ticker) or []
        full_earn = list(earnings.get(ticker) or [])
        next_er = next_earnings_on_or_after(full_earn, as_of_day)
        # Plot markers stay inside the price window only.
        earn = _trim_earnings(full_earn, price_series)

        chart = {
            "prices": price_series,
            "targets": [
                {"date": p["date"], "target": p.get("target")}
                for p in target_series
                if p.get("target") is not None
            ],
            "earnings": earn,
            "next_earnings": next_er,
        }
        row["chart"] = chart
        history[ticker] = {
            "targets": target_series,
            "earnings": full_earn[-(MAX_EARNINGS * 2) :],
            "next_earnings": next_er,
        }
    return history


def resolve_yf_symbol(ticker: str, *, tsx_bias: bool = False) -> str:
    """Map scrape tickers to yfinance symbols (class shares, TSX bias for CAD names)."""
    t = (ticker or "").strip().upper()
    if not t:
        return t
    if t.endswith((".TO", ".V", ".CN", ".NE")):
        return t
    if tsx_bias:
        if "." in t:
            return t.replace(".", "-") + ".TO"
        return t + ".TO"
    if "." in t:
        return t.replace(".", "-")
    return t


def yf_symbol_candidates(ticker: str, *, tsx_bias: bool = False) -> list[str]:
    t = (ticker or "").strip().upper()
    if not t:
        return []
    primary = resolve_yf_symbol(t, tsx_bias=tsx_bias)
    ordered: list[str] = [primary]
    if "." in t:
        dashed = t.replace(".", "-")
        ordered.extend([dashed, t, dashed + ".TO", dashed + ".V", t + ".TO"])
    else:
        ordered.extend([t, t + ".TO", t + ".V"])
    if tsx_bias:
        ordered = [primary] + [s for s in ordered if s != primary]
    seen: set[str] = set()
    out: list[str] = []
    for s in ordered:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def collect_broker_tickers(broker_cache: Optional[dict]) -> dict[str, set[str]]:
    """ticker -> set of broker slugs that have a pick for it."""
    out: dict[str, set[str]] = {}
    for slug, payload in (broker_cache or {}).items():
        for tk in (payload.get("by_ticker") or {}):
            if not tk:
                continue
            out.setdefault(tk, set()).add(slug)
    return out


def row_is_cad(row: Optional[dict], slug: str = "") -> bool:
    if slug == "desjardins":
        return True
    row = row or {}
    pc = str(row.get("price_currency") or "").upper()
    tc = str(row.get("target_currency") or "").upper()
    return pc == "CAD" or tc == "CAD"


def firm_chart_key(ticker: str, *, cad: bool) -> str:
    """Disambiguate US/CAD collisions (e.g. H = Hyatt vs Hydro One)."""
    t = (ticker or "").strip().upper()
    return f"{t}::CAD" if cad else t


def cad_biased_tickers(broker_cache: Optional[dict]) -> set[str]:
    """Tickers that have at least one CAD-denominated firm pick."""
    out: set[str] = set()
    for slug, payload in (broker_cache or {}).items():
        for tk, row in (payload.get("by_ticker") or {}).items():
            if tk and row_is_cad(row, slug):
                out.add(tk)
    return out


def _iter_firm_chart_specs(
    broker_cache: Optional[dict],
    universe: set[str],
) -> list[dict]:
    """
    One spec per (ticker, currency-realm).
    CAD and USD picks that share a ticker (H, CM, …) get separate charts.
    """
    specs: dict[str, dict] = {}
    for slug, payload in (broker_cache or {}).items():
        for tk, row in (payload.get("by_ticker") or {}).items():
            if not tk or tk in universe:
                continue
            cad = row_is_cad(row, slug)
            key = firm_chart_key(tk, cad=cad)
            sp = specs.get(key)
            if sp is None:
                sp = {
                    "key": key,
                    "ticker": tk,
                    "cad": cad,
                    "ref_price": None,
                    "ref_date": "",
                    "targets": [],
                }
                specs[key] = sp
            px = row.get("price")
            try:
                pxf = float(px) if px is not None else None
            except (TypeError, ValueError):
                pxf = None
            d = str(row.get("date") or "")
            if pxf and pxf > 0 and d >= sp["ref_date"]:
                sp["ref_price"] = pxf
                sp["ref_date"] = d
            tgt = row.get("target")
            try:
                tgtf = float(tgt) if tgt is not None else None
            except (TypeError, ValueError):
                tgtf = None
            if tgtf is not None:
                sp["targets"].append({
                    "date": (d or "1970-01-01")[:10],
                    "target": round(tgtf, 2),
                })
    return list(specs.values())


def scraped_ref_price(broker_cache: Optional[dict], ticker: str) -> Optional[float]:
    """Legacy helper: best scraped price for ticker (any currency)."""
    best: Optional[tuple[str, float]] = None
    for slug, payload in (broker_cache or {}).items():
        row = (payload.get("by_ticker") or {}).get(ticker)
        if not row:
            continue
        px = row.get("price")
        if px is None:
            continue
        try:
            val = float(px)
        except (TypeError, ValueError):
            continue
        if val <= 0:
            continue
        d = str(row.get("date") or "")
        if best is None or d >= best[0]:
            best = (d, val)
    return best[1] if best else None


def _price_mismatch(series: list[dict], ref: Optional[float], tol: float = 0.35) -> bool:
    if not ref or ref <= 0 or not series:
        return False
    last = series[-1].get("close")
    if last is None:
        return True
    return abs(float(last) - ref) / ref > tol


def firm_target_series(broker_cache: Optional[dict], as_of: str) -> dict[str, list[dict]]:
    """Build date/target series from scraped firm picks (legacy bare-ticker keys)."""
    today = as_of[:10]
    raw: dict[str, list[dict]] = {}
    for slug, payload in (broker_cache or {}).items():
        for tk, row in (payload.get("by_ticker") or {}).items():
            tgt = row.get("target")
            if tgt is None:
                continue
            try:
                val = float(tgt)
            except (TypeError, ValueError):
                continue
            d = str(row.get("date") or today)[:10]
            raw.setdefault(tk, []).append({"date": d, "target": round(val, 2), "firm": slug})
    out: dict[str, list[dict]] = {}
    for tk, pts in raw.items():
        pts.sort(key=lambda p: p["date"])
        dedup: dict[str, dict] = {}
        for p in pts:
            dedup[p["date"]] = {"date": p["date"], "target": p["target"]}
        out[tk] = list(dedup.values())[-MAX_TARGET_POINTS:]
    return out


def _trim_earnings(earn: list[str], price_series: list[dict], max_ahead_days: int = 0) -> list[str]:
    """Keep ER dates within the price window (no stretching past the last weekly bar)."""
    if not price_series:
        return earn[-MAX_EARNINGS:]
    start = price_series[0]["date"]
    end = price_series[-1]["date"]
    if max_ahead_days > 0:
        from datetime import datetime, timedelta

        try:
            end = (
                datetime.strptime(end[:10], "%Y-%m-%d").date()
                + timedelta(days=max_ahead_days)
            ).isoformat()
        except ValueError:
            pass
    return [d for d in earn if start <= d <= end][-MAX_EARNINGS:]


def build_firm_charts(
    broker_cache: Optional[dict],
    universe: set[str],
    as_of: str,
    prev_firm_charts: Optional[dict] = None,
    fetch_earnings: bool = True,
) -> dict[str, dict]:
    """
    Weekly price / firm-target / earnings charts for broker-pick tickers
    outside the main universe.

    Keys are bare tickers for USD picks, or `TICKER::CAD` for CAD picks so
    collisions like Hyatt (H) vs Hydro One (H) stay separate.
    """
    broker_cache = broker_cache or {}
    prev_firm_charts = prev_firm_charts or {}
    specs = _iter_firm_chart_specs(broker_cache, universe)
    if not specs:
        print("[INFO] Firm-pick charts: nothing outside universe")
        return {}

    key_to_yf: dict[str, str] = {
        sp["key"]: resolve_yf_symbol(sp["ticker"], tsx_bias=sp["cad"])
        for sp in specs
    }
    n_cad = sum(1 for sp in specs if sp["cad"])
    print(f"[INFO] Firm chart specs: {len(specs)} ({n_cad} CAD-disambiguated)")

    yf_syms = sorted(set(key_to_yf.values()))
    print(f"--- Firm-pick charts ({len(specs)} series → {len(yf_syms)} Yahoo symbols) ---")
    price_by_yf: dict[str, list[dict]] = {}
    chunk = 120

    def _download_syms(syms: list[str], label: str) -> None:
        if not syms:
            return
        for i in range(0, len(syms), chunk):
            part = syms[i : i + chunk]
            print(f"  {label} chunk {i // chunk + 1}/{(len(syms) + chunk - 1) // chunk} ({len(part)})")
            price_by_yf.update(fetch_weekly_prices(part))

    _download_syms(yf_syms, "prices")

    need_remap = []
    for sp in specs:
        key = sp["key"]
        series = price_by_yf.get(key_to_yf[key]) or []
        if not series or _price_mismatch(series, sp.get("ref_price")):
            need_remap.append(sp)

    if need_remap:
        alt_syms: list[str] = []
        for sp in need_remap:
            for cand in yf_symbol_candidates(sp["ticker"], tsx_bias=sp["cad"]):
                if cand not in price_by_yf:
                    alt_syms.append(cand)
        alt_syms = sorted(set(alt_syms))
        print(f"  remapping {len(need_remap)} series via {len(alt_syms)} alternate Yahoo symbols…")
        _download_syms(alt_syms, "remap")

        remapped = 0
        for sp in need_remap:
            key = sp["key"]
            ref = sp.get("ref_price")
            best_sym = key_to_yf[key]
            best_series = price_by_yf.get(best_sym) or []
            best_score = float("inf")
            if best_series and ref and ref > 0:
                best_score = abs(float(best_series[-1]["close"]) - ref) / ref
            elif best_series and not ref:
                best_score = 0.0
            for cand in yf_symbol_candidates(sp["ticker"], tsx_bias=sp["cad"]):
                series = price_by_yf.get(cand) or []
                if not series:
                    continue
                if ref and ref > 0:
                    score = abs(float(series[-1]["close"]) - ref) / ref
                else:
                    score = 0.0
                if sp["cad"] and cand.endswith((".TO", ".V")):
                    score -= 0.001
                if score < best_score:
                    best_score = score
                    best_sym = cand
                    best_series = series
            if best_sym != key_to_yf[key] and best_series:
                key_to_yf[key] = best_sym
                remapped += 1
        print(f"[INFO] Remapped to better Yahoo symbols: {remapped}/{len(need_remap)}")

    prices = {sp["key"]: price_by_yf.get(key_to_yf[sp["key"]]) or [] for sp in specs}
    n_px = sum(1 for sp in specs if prices[sp["key"]])
    print(f"[INFO] Firm-pick weekly prices: {n_px}/{len(specs)}")

    earnings: dict[str, list[str]] = {sp["key"]: [] for sp in specs}
    if fetch_earnings:
        earn_keys = [sp["key"] for sp in specs if prices[sp["key"]]]
        yf_for_earn = {key_to_yf[k]: k for k in earn_keys}
        prev_earn_hist = {
            ys: {"earnings": (prev_firm_charts.get(yf_for_earn[ys]) or {}).get("earnings") or []}
            for ys in yf_for_earn
        }
        earn_by_yf = fetch_earnings_dates(list(yf_for_earn.keys()), prev_chart=prev_earn_hist)
        for sp in specs:
            key = sp["key"]
            earn = list(earn_by_yf.get(key_to_yf[key]) or [])
            for prev_key in (key, sp["ticker"], firm_chart_key(sp["ticker"], cad=True)):
                prev_e = (prev_firm_charts.get(prev_key) or {}).get("earnings") or []
                if prev_e:
                    earn = sorted(set(earn) | {d for d in prev_e if isinstance(d, str)})
            earnings[key] = earn
    else:
        for sp in specs:
            key = sp["key"]
            earn: list[str] = []
            for prev_key in (key, sp["ticker"], firm_chart_key(sp["ticker"], cad=True)):
                prev_e = (prev_firm_charts.get(prev_key) or {}).get("earnings") or []
                if prev_e:
                    earn = sorted(set(earn) | {d for d in prev_e if isinstance(d, str)})
            earnings[key] = earn

    out: dict[str, dict] = {}
    usd_keys = {sp["ticker"] for sp in specs if not sp["cad"]}
    for sp in specs:
        key = sp["key"]
        price_series = prices.get(key) or []
        tpts = sp.get("targets") or []
        tpts = sorted(tpts, key=lambda p: p["date"])
        dedup: dict[str, dict] = {}
        for p in tpts:
            dedup[p["date"]] = {"date": p["date"], "target": p["target"]}
        target_series = list(dedup.values())[-MAX_TARGET_POINTS:]
        full_earn = list(earnings.get(key) or [])
        next_er = next_earnings_on_or_after(full_earn, as_of[:10] if as_of else None)
        earn = _trim_earnings(full_earn, price_series)
        if not price_series:
            for prev_key in (key, sp["ticker"]):
                prev = prev_firm_charts.get(prev_key) or {}
                if prev.get("prices"):
                    # Only reuse prior if yf_symbol realm matches
                    prev_yf = str(prev.get("yf_symbol") or "")
                    if sp["cad"] and not prev_yf.endswith((".TO", ".V")):
                        continue
                    price_series = prev["prices"]
                    if not earn:
                        earn = prev.get("earnings") or []
                    if not next_er:
                        next_er = prev.get("next_earnings") or next_earnings_on_or_after(
                            list(prev.get("earnings") or []), as_of[:10] if as_of else None
                        )
                    break
        chart = {
            "prices": price_series,
            "targets": target_series,
            "earnings": earn,
            "next_earnings": next_er,
            "yf_symbol": key_to_yf.get(key),
            "ticker": sp["ticker"],
            "cad": sp["cad"],
        }
        if chart["prices"] or chart["targets"]:
            out[key] = chart
            # Alias CAD-only names under bare ticker for simple lookups
            if sp["cad"] and sp["ticker"] not in usd_keys and sp["ticker"] not in out:
                out[sp["ticker"]] = chart

    print(f"[INFO] Firm-pick charts ready: {len(out)} keys")
    return out


def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


def _fundamentals_for_yf_symbol(yf_symbol: str, retries: int = 2) -> dict:
    empty = {"trailing_pe": None, "forward_pe": None, "market_cap": None}
    if not yf_symbol:
        return empty
    import time

    last = empty
    for attempt in range(retries + 1):
        try:
            t = yf.Ticker(yf_symbol)
            pe = fwd = mcap = None
            try:
                info = t.info or {}
                pe = _safe_float(info.get("trailingPE"))
                fwd = _safe_float(info.get("forwardPE"))
                mcap = _safe_float(info.get("marketCap"))
            except Exception:
                info = {}
            if mcap is None:
                try:
                    fi = t.fast_info
                    mcap = _safe_float(getattr(fi, "market_cap", None) or (fi.get("market_cap") if hasattr(fi, "get") else None))
                except Exception:
                    pass
            last = {"trailing_pe": pe, "forward_pe": fwd, "market_cap": mcap}
            if pe is not None or fwd is not None or mcap is not None:
                return last
        except Exception:
            pass
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))
    return last


def build_firm_fundamentals(
    broker_cache: Optional[dict],
    analyzed: list[dict],
    firm_charts: Optional[dict] = None,
    prev_fundamentals: Optional[dict] = None,
    max_workers: int = 4,
) -> dict[str, dict]:
    """
    PE / fwd PE / market cap for firm-pick rows.
    Keys match firm chart keys (`TICKER` or `TICKER::CAD`) plus bare universe tickers.
    """
    firm_charts = firm_charts or {}
    out: dict[str, dict] = {}
    prev_fundamentals = prev_fundamentals or {}

    def _has_vals(d: Optional[dict]) -> bool:
        d = d or {}
        return (
            d.get("trailing_pe") is not None
            or d.get("forward_pe") is not None
            or d.get("market_cap") is not None
        )

    # Seed from main universe (already fetched during yfinance pass)
    for row in analyzed:
        t = row.get("ticker")
        if not t:
            continue
        out[t] = {
            "trailing_pe": row.get("trailing_pe"),
            "forward_pe": row.get("forward_pe"),
            "market_cap": row.get("market_cap"),
        }

    # Specs needing Yahoo lookup (outside universe or CAD-disambiguated)
    universe = {r.get("ticker") for r in analyzed if r.get("ticker")}
    specs = _iter_firm_chart_specs(broker_cache, universe)
    to_fetch: dict[str, str] = {}  # chart key -> yf symbol
    for sp in specs:
        key = sp["key"]
        cached = prev_fundamentals.get(key) or {}
        if _has_vals(cached):
            out[key] = {
                "trailing_pe": cached.get("trailing_pe"),
                "forward_pe": cached.get("forward_pe"),
                "market_cap": cached.get("market_cap"),
            }
            continue
        # Universe USD row already covered
        if not sp["cad"] and _has_vals(out.get(key)):
            continue
        ys = (firm_charts.get(key) or {}).get("yf_symbol") or resolve_yf_symbol(
            sp["ticker"], tsx_bias=sp["cad"]
        )
        to_fetch[key] = ys

    if to_fetch:
        print(f"--- Firm fundamentals (yfinance info, {len(to_fetch)} tickers) ---")
        done = 0
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futs = {pool.submit(_fundamentals_for_yf_symbol, ys): key for key, ys in to_fetch.items()}
            for fut in as_completed(futs):
                key = futs[fut]
                try:
                    got = fut.result()
                except Exception:
                    got = {"trailing_pe": None, "forward_pe": None, "market_cap": None}
                # Don't clobber a prior good cache with an empty rate-limit miss
                if _has_vals(got):
                    out[key] = got
                elif _has_vals(prev_fundamentals.get(key)):
                    out[key] = {
                        "trailing_pe": (prev_fundamentals.get(key) or {}).get("trailing_pe"),
                        "forward_pe": (prev_fundamentals.get(key) or {}).get("forward_pe"),
                        "market_cap": (prev_fundamentals.get(key) or {}).get("market_cap"),
                    }
                else:
                    out[key] = got
                done += 1
                if done % 40 == 0 or done == len(to_fetch):
                    print(f"  [{done}/{len(to_fetch)}] fundamentals…")
        n_ok = sum(1 for k in to_fetch if _has_vals(out.get(k)))
        print(f"[INFO] Firm fundamentals fetched: {n_ok}/{len(to_fetch)} with ≥1 field")

    # Keep prior entries we didn't refresh
    for k, v in prev_fundamentals.items():
        if k not in out and isinstance(v, dict) and _has_vals(v):
            out[k] = {
                "trailing_pe": v.get("trailing_pe"),
                "forward_pe": v.get("forward_pe"),
                "market_cap": v.get("market_cap"),
            }
    return out


def enrich_broker_panels(panels: list[dict], fundamentals: Optional[dict]) -> list[dict]:
    """Attach trailing_pe / forward_pe / market_cap onto each pick row."""
    fundamentals = fundamentals or {}
    enriched_panels = []
    for panel in panels:
        slug = panel.get("slug") or ""
        picks_out = []
        for row in panel.get("picks") or []:
            pick = dict(row)
            tk = pick.get("ticker") or ""
            cad = row_is_cad(pick, slug)
            key = firm_chart_key(tk, cad=cad)
            fund = fundamentals.get(key) or fundamentals.get(tk) or {}
            for field in ("trailing_pe", "forward_pe", "market_cap"):
                if fund.get(field) is not None:
                    pick[field] = fund[field]
                elif field not in pick:
                    pick[field] = None
            picks_out.append(pick)
        enriched = dict(panel)
        enriched["picks"] = picks_out
        enriched_panels.append(enriched)
    return enriched_panels
