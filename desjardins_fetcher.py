"""
Backward-compatible shim — prefer broker_scraper.py.
"""

from broker_scraper import (  # noqa: F401
    broker_meta,
    broker_picks_for_dashboard,
    fetch_broker_recommendations,
    parse_broker_html as parse_desjardins_html,
)


def fetch_desjardins_recommendations(prev_cache=None):
    broker = broker_meta("desjardins")
    return fetch_broker_recommendations(broker, prev_cache=prev_cache)


def attach_desjardins_to_results(results, desjardins):
    """Legacy helper: attach only Desjardins into firm_targets + flat fields."""
    from broker_scraper import attach_brokers_to_results

    cache = {"desjardins": desjardins or {}}
    counts = attach_brokers_to_results(results, cache)
    return counts.get("desjardins", 0)


def desjardins_picks_for_dashboard(desjardins):
    picks = list((desjardins or {}).get("by_ticker") or {}).values()
    picks.sort(key=lambda r: r.get("date") or "", reverse=True)
    return picks
