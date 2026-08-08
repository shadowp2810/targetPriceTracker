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


def firm_upside_vs_usd_price(
    firm_target: Optional[float],
    firm_currency: Optional[str],
    usd_price: Optional[float],
) -> Optional[float]:
    """Upside vs yfinance USD price only when firm target is USD (no FX)."""
    if firm_target is None or usd_price is None:
        return None
    if firm_currency and firm_currency.upper() != "USD":
        return None
    return upside_pct(firm_target, usd_price)


def analyze_ticker(raw: dict, week_baseline: Optional[dict] = None) -> dict:
    """Enrich a single ticker fetch result with derived metrics."""
    price = _f(raw.get("current_price"))
    yf_mean = _f(raw.get("yf_target_mean"))
    fmp_latest = _f(raw.get("fmp_latest_target"))
    av_target = _f(raw.get("av_target"))
    dj_target = _f(raw.get("desjardins_target"))
    dj_currency = raw.get("desjardins_currency")

    target, target_source = primary_target(yf_mean, fmp_latest, av_target)
    up = upside_pct(target, price)
    div = consensus_divergence(yf_mean, fmp_latest, av_target, price)
    above_target = bool(price is not None and target is not None and price > target)
    upside_dj = firm_upside_vs_usd_price(dj_target, dj_currency, price)

    baseline = week_baseline or {}
    baseline_firms = baseline.get("firm_targets") or {}

    # Enrich each firm target with upside + week delta
    firm_targets = {}
    for slug, ft in (raw.get("firm_targets") or {}).items():
        ft_target = _f(ft.get("target"))
        ft_up = firm_upside_vs_usd_price(ft_target, ft.get("currency"), price)
        prev_t = _f((baseline_firms.get(slug) or {}).get("target"))
        enriched = {
            **ft,
            "target": round(ft_target, 2) if ft_target is not None else None,
            "upside_pct": ft_up,
            "week_delta": week_delta(ft_target, prev_t),
        }
        firm_targets[slug] = enriched

    # Best USD firm upside for sorting/display
    usd_firm_upsides = [
        (slug, ft["upside_pct"])
        for slug, ft in firm_targets.items()
        if ft.get("upside_pct") is not None
    ]
    best_firm_slug = None
    best_firm_upside = None
    if usd_firm_upsides:
        best_firm_slug, best_firm_upside = max(usd_firm_upsides, key=lambda x: x[1])

    analyzed = {
        **raw,
        "firm_targets": firm_targets,
        "n_firm_targets": len(firm_targets),
        "best_firm_slug": best_firm_slug,
        "best_firm_upside_pct": best_firm_upside,
        "primary_target": target,
        "primary_target_source": target_source,
        "upside_pct": up,
        "upside_yf_pct": upside_pct(yf_mean, price),
        "upside_fmp_pct": upside_pct(fmp_latest, price),
        "upside_av_pct": upside_pct(av_target, price),
        "upside_desjardins_pct": upside_dj,
        "above_target": above_target,
        "divergence_pct": div["divergence_pct"],
        "divergence_flag": div["divergence_flag"],
        "divergence_sources": div["sources_used"],
        "week_delta_yf": week_delta(yf_mean, _f(baseline.get("yf_target_mean"))),
        "week_delta_fmp": week_delta(fmp_latest, _f(baseline.get("fmp_latest_target"))),
        "week_delta_av": week_delta(av_target, _f(baseline.get("av_target"))),
        "week_delta_desjardins": week_delta(dj_target, _f(baseline.get("desjardins_target"))),
        "week_delta_upside": week_delta(up, _f(baseline.get("upside_pct"))),
    }
    # Round a few display-friendly fields
    for key in ("yf_target_mean", "yf_target_median", "yf_target_high", "yf_target_low",
                "fmp_latest_target", "av_target", "primary_target", "desjardins_target",
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
        firm_base = {}
        for slug, ft in (row.get("firm_targets") or {}).items():
            firm_base[slug] = {"target": ft.get("target")}
        out[row["ticker"]] = {
            "yf_target_mean": row.get("yf_target_mean"),
            "fmp_latest_target": row.get("fmp_latest_target"),
            "av_target": row.get("av_target"),
            "desjardins_target": row.get("desjardins_target"),
            "firm_targets": firm_base,
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
    with_dj = sum(
        1 for r in analyzed
        if r.get("desjardins_target") is not None or r.get("desjardins_rating")
    )
    with_firm = sum(1 for r in analyzed if (r.get("n_firm_targets") or 0) > 0)
    return {
        "n_tickers": len(analyzed),
        "n_with_upside": len(upsides),
        "avg_upside_pct": round(sum(upsides) / len(upsides), 2) if upsides else None,
        "median_upside_pct": round(sorted(upsides)[len(upsides) // 2], 2) if upsides else None,
        "n_above_target": above,
        "n_divergence_flag": diverged,
        "n_with_av": with_av,
        "n_with_fmp": with_fmp,
        "n_with_desjardins": with_dj,
        "n_with_firm_targets": with_firm,
        "top_upside": analyzed[0]["ticker"] if analyzed and analyzed[0].get("upside_pct") is not None else None,
    }
