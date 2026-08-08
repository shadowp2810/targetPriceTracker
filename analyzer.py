"""
Computes upside %, consensus divergence, above-target flags, and weekly deltas.
"""

from __future__ import annotations

from typing import Any, Optional


def _f(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        if f != f:
            return None
        return f
    except (TypeError, ValueError):
        return None


def upside_pct(target: Optional[float], price: Optional[float]) -> Optional[float]:
    """(target - price) / price * 100."""
    if target is None or price is None or price == 0:
        return None
    return round((target - price) / price * 100, 2)


def consensus_divergence(
    yf_mean: Optional[float],
    fmp_latest: Optional[float],
    av_target: Optional[float],
    price: Optional[float],
) -> dict:
    """
    Score how far the three consensus sources disagree.
    divergence_pct = (max - min) / mid * 100 across available sources.
    Flagged when spread > 10% of mid-price or > $5 absolute (whichever is looser
    relative to price context — we use pct of average target).
    """
    vals = [v for v in (_f(yf_mean), _f(fmp_latest), _f(av_target)) if v is not None]
    if len(vals) < 2:
        return {
            "divergence_pct": None,
            "divergence_flag": False,
            "sources_used": len(vals),
            "high": max(vals) if vals else None,
            "low": min(vals) if vals else None,
        }

    high, low = max(vals), min(vals)
    mid = (high + low) / 2
    div_pct = round((high - low) / mid * 100, 2) if mid else None
    # Flag when sources disagree by more than 10% of their midpoint
    flagged = div_pct is not None and div_pct >= 10.0
    return {
        "divergence_pct": div_pct,
        "divergence_flag": flagged,
        "sources_used": len(vals),
        "high": high,
        "low": low,
    }


def primary_target(
    yf_mean: Optional[float],
    fmp_latest: Optional[float],
    av_target: Optional[float],
) -> tuple[Optional[float], str]:
    """
    Prefer yfinance mean (broadest coverage), then FMP latest, then AV.
    Returns (target, source_label).
    """
    if yf_mean is not None:
        return yf_mean, "yfinance"
    if fmp_latest is not None:
        return fmp_latest, "fmp"
    if av_target is not None:
        return av_target, "alpha_vantage"
    return None, "none"


def week_delta(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    if current is None or previous is None:
        return None
    return round(current - previous, 2)


def analyze_ticker(raw: dict, week_baseline: Optional[dict] = None) -> dict:
    """Enrich a single ticker fetch result with derived metrics."""
    price = _f(raw.get("current_price"))
    yf_mean = _f(raw.get("yf_target_mean"))
    fmp_latest = _f(raw.get("fmp_latest_target"))
    av_target = _f(raw.get("av_target"))

    target, target_source = primary_target(yf_mean, fmp_latest, av_target)
    up = upside_pct(target, price)
    div = consensus_divergence(yf_mean, fmp_latest, av_target, price)
    above_target = bool(price is not None and target is not None and price > target)

    baseline = week_baseline or {}
    analyzed = {
        **raw,
        "primary_target": target,
        "primary_target_source": target_source,
        "upside_pct": up,
        "upside_yf_pct": upside_pct(yf_mean, price),
        "upside_fmp_pct": upside_pct(fmp_latest, price),
        "upside_av_pct": upside_pct(av_target, price),
        "above_target": above_target,
        "divergence_pct": div["divergence_pct"],
        "divergence_flag": div["divergence_flag"],
        "divergence_sources": div["sources_used"],
        "week_delta_yf": week_delta(yf_mean, _f(baseline.get("yf_target_mean"))),
        "week_delta_fmp": week_delta(fmp_latest, _f(baseline.get("fmp_latest_target"))),
        "week_delta_av": week_delta(av_target, _f(baseline.get("av_target"))),
        "week_delta_upside": week_delta(up, _f(baseline.get("upside_pct"))),
    }
    # Round a few display-friendly fields
    for key in ("yf_target_mean", "yf_target_median", "yf_target_high", "yf_target_low",
                "fmp_latest_target", "av_target", "primary_target",
                "trailing_pe", "forward_pe", "beta",
                "fifty_two_week_high", "fifty_two_week_low"):
        if analyzed.get(key) is not None:
            analyzed[key] = round(float(analyzed[key]), 2)
    return analyzed


def analyze_all(
    fetch_results: dict[str, dict],
    week_baseline_by_ticker: Optional[dict[str, dict]] = None,
) -> list[dict]:
    """
    Analyze every ticker and return a list ranked by upside % (desc).
    Tickers with no upside sort to the end.
    """
    week_baseline_by_ticker = week_baseline_by_ticker or {}
    analyzed = []
    for ticker, raw in fetch_results.items():
        if ticker.startswith("__"):
            continue
        analyzed.append(analyze_ticker(raw, week_baseline_by_ticker.get(ticker)))

    def sort_key(row: dict):
        up = row.get("upside_pct")
        return (up is None, -(up or 0))

    analyzed.sort(key=sort_key)
    for rank, row in enumerate(analyzed, 1):
        row["rank"] = rank
    return analyzed


def build_week_baseline(analyzed: list[dict]) -> dict[str, dict]:
    """Compact per-ticker fields stored as the next week's comparison baseline."""
    out = {}
    for row in analyzed:
        out[row["ticker"]] = {
            "yf_target_mean": row.get("yf_target_mean"),
            "fmp_latest_target": row.get("fmp_latest_target"),
            "av_target": row.get("av_target"),
            "upside_pct": row.get("upside_pct"),
            "primary_target": row.get("primary_target"),
        }
    return out


def summary_stats(analyzed: list[dict]) -> dict:
    upsides = [r["upside_pct"] for r in analyzed if r.get("upside_pct") is not None]
    above = sum(1 for r in analyzed if r.get("above_target"))
    diverged = sum(1 for r in analyzed if r.get("divergence_flag"))
    with_av = sum(1 for r in analyzed if r.get("av_target") is not None)
    with_fmp = sum(1 for r in analyzed if r.get("fmp_latest_target") is not None)
    return {
        "n_tickers": len(analyzed),
        "n_with_upside": len(upsides),
        "avg_upside_pct": round(sum(upsides) / len(upsides), 2) if upsides else None,
        "median_upside_pct": round(sorted(upsides)[len(upsides) // 2], 2) if upsides else None,
        "n_above_target": above,
        "n_divergence_flag": diverged,
        "n_with_av": with_av,
        "n_with_fmp": with_fmp,
        "top_upside": analyzed[0]["ticker"] if analyzed and analyzed[0].get("upside_pct") is not None else None,
    }
