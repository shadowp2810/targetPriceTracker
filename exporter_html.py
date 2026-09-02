"""
Generates a self-contained HTML dashboard from analyzed price-target data.
Chart.js from CDN. All data embedded as JSON. No backend required.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


def write_html(
    analyzed: list[dict],
    output_path: Path,
    timestamp: str,
    iso_timestamp: str = "",
    stats: Optional[dict] = None,
    snapshot_info: Optional[dict] = None,
    broker_panels: Optional[list] = None,
    desjardins_picks: Optional[list] = None,  # legacy unused
    firm_charts: Optional[dict] = None,
) -> None:
    stats = stats or {}
    snapshot_info = snapshot_info or {}
    broker_panels = broker_panels or []
    firm_charts = firm_charts or {}
    # Compat: if only legacy desjardins_picks passed
    if not broker_panels and desjardins_picks:
        broker_panels = [{
            "slug": "desjardins",
            "name": "Desjardins",
            "short": "DJ",
            "source_url": snapshot_info.get("desjardins_source_url"),
            "picks": desjardins_picks,
        }]

    # Strip bulky news fields from embedded payload; keep essentials for UI
    slim = []
    for row in analyzed:
        analysts = []
        for a in row.get("fmp_analysts") or []:
            analysts.append({
                "analyst_name": a.get("analyst_name"),
                "analyst_company": a.get("analyst_company"),
                "price_target": a.get("adj_price_target") or a.get("price_target"),
                "price_when_posted": a.get("price_when_posted"),
                "recommendation_key": a.get("recommendation_key"),
                "previous_grade": a.get("previous_grade"),
                "action": a.get("action"),
                "date": a.get("date"),
                "news_title": a.get("news_title"),
                "news_url": a.get("news_url"),
                "source": a.get("source"),
            })
        firm_targets = {}
        for slug, ft in (row.get("firm_targets") or {}).items():
            firm_targets[slug] = {
                "slug": ft.get("slug") or slug,
                "name": ft.get("name"),
                "short": ft.get("short"),
                "target": ft.get("target"),
                "rating": ft.get("rating"),
                "date": ft.get("date"),
                "action": ft.get("action"),
                "currency": ft.get("currency"),
                "upside_pct": ft.get("upside_pct"),
                "week_delta": ft.get("week_delta"),
            }
        slim.append({
            "ticker": row.get("ticker"),
            "name": row.get("name"),
            "sector": row.get("sector"),
            "industry": row.get("industry"),
            "current_price": row.get("current_price"),
            "primary_target": row.get("primary_target"),
            "primary_target_source": row.get("primary_target_source"),
            "upside_pct": row.get("upside_pct"),
            "yf_target_mean": row.get("yf_target_mean"),
            "yf_target_median": row.get("yf_target_median"),
            "yf_target_high": row.get("yf_target_high"),
            "yf_target_low": row.get("yf_target_low"),
            "fmp_latest_target": row.get("fmp_latest_target"),
            "fmp_target_high": row.get("fmp_target_high"),
            "fmp_target_low": row.get("fmp_target_low"),
            "fmp_target_median": row.get("fmp_target_median"),
            "av_target": row.get("av_target"),
            "av_from_cache": row.get("av_from_cache"),
            "av_fetched_at": row.get("av_fetched_at"),
            "firm_targets": firm_targets,
            "n_firm_targets": row.get("n_firm_targets") or len(firm_targets),
            "best_firm_slug": row.get("best_firm_slug"),
            "best_firm_upside_pct": row.get("best_firm_upside_pct"),
            "desjardins_target": row.get("desjardins_target"),
            "desjardins_rating": row.get("desjardins_rating"),
            "desjardins_date": row.get("desjardins_date"),
            "desjardins_action": row.get("desjardins_action"),
            "desjardins_currency": row.get("desjardins_currency"),
            "upside_desjardins_pct": row.get("upside_desjardins_pct"),
            "week_delta_desjardins": row.get("week_delta_desjardins"),
            "n_analysts": row.get("n_analysts"),
            "recommendation_key": row.get("recommendation_key"),
            "trailing_pe": row.get("trailing_pe"),
            "forward_pe": row.get("forward_pe"),
            "market_cap": row.get("market_cap"),
            "avg_volume": row.get("avg_volume"),
            "fifty_two_week_high": row.get("fifty_two_week_high"),
            "fifty_two_week_low": row.get("fifty_two_week_low"),
            "beta": row.get("beta"),
            "above_target": row.get("above_target"),
            "divergence_pct": row.get("divergence_pct"),
            "divergence_flag": row.get("divergence_flag"),
            "week_delta_yf": row.get("week_delta_yf"),
            "week_delta_fmp": row.get("week_delta_fmp"),
            "week_delta_av": row.get("week_delta_av"),
            "week_delta_upside": row.get("week_delta_upside"),
            "rank": row.get("rank"),
            "fmp_analysts": analysts,
            "chart": row.get("chart") or {"prices": [], "targets": [], "earnings": []},
        })

    # Firm-pick charts for tickers outside the main universe (slim: drop empty)
    firm_charts_slim = {}
    for tk, ch in firm_charts.items():
        if not isinstance(ch, dict):
            continue
        prices = ch.get("prices") or []
        targets = ch.get("targets") or []
        if not prices and not targets:
            continue
        firm_charts_slim[tk] = {
            "prices": prices,
            "targets": targets,
            "earnings": ch.get("earnings") or [],
            "next_earnings": ch.get("next_earnings"),
        }

    data_payload = json.dumps(
        {
            "generated": timestamp,
            "iso_timestamp": iso_timestamp,
            "stats": stats,
            "snapshot_info": snapshot_info,
            "tickers": slim,
            "broker_panels": broker_panels,
            "firm_charts": firm_charts_slim,
        },
        default=str,
    )

    wb_age = snapshot_info.get("week_baseline_age_days")
    if wb_age is None:
        week_label = "no prior week baseline"
    elif wb_age == 0:
        week_label = "vs earlier today"
    elif wb_age == 1:
        week_label = "vs 1 day ago"
    else:
        week_label = f"vs {wb_age} days ago"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Stock Price Target Tracker</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js"></script>
<style>
  :root {{
    --bg: #0f1117;
    --surface: #1a1d27;
    --surface2: #22263a;
    --border: #2e3250;
    --accent: #4f7ef8;
    --green: #22c55e;
    --green-bg: #052e16;
    --red: #ef4444;
    --red-bg: #2d0b0b;
    --yellow: #f59e0b;
    --yellow-bg: #2c1f06;
    --text: #e2e8f0;
    --text-muted: #94a3b8;
    --text-dim: #64748b;
    --radius: 10px;
    --font: 'IBM Plex Sans', 'Segoe UI', system-ui, sans-serif;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    font-size: 13px;
    min-height: 100vh;
  }}
  .header {{
    background: linear-gradient(135deg, #1a1d27 0%, #0f1117 55%, #12182a 100%);
    border-bottom: 1px solid var(--border);
    padding: 28px 28px 22px;
  }}
  .header h1 {{
    font-size: 1.55rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    margin-bottom: 6px;
  }}
  .header .sub {{
    color: var(--text-muted);
    font-size: 0.92rem;
  }}
  .header .meta {{
    margin-top: 10px;
    color: var(--text-dim);
    font-size: 0.8rem;
  }}
  .stats {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 12px;
    padding: 18px 28px;
  }}
  .stat {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px 16px;
  }}
  .stat .label {{ color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em; }}
  .stat .value {{ font-size: 1.35rem; font-weight: 700; margin-top: 4px; }}
  .controls {{
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
    padding: 0 28px 14px;
  }}
  .controls input, .controls select {{
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 8px;
    padding: 8px 12px;
    font: inherit;
  }}
  .controls input {{ min-width: 220px; }}
  .controls label {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: var(--text-muted);
    cursor: pointer;
    user-select: none;
  }}
  .chart-wrap {{
    margin: 0 28px 14px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 12px 16px;
    height: 160px;
  }}
  .table-wrap {{
    margin: 0 28px 20px;
    overflow-x: auto;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
  }}
  /* Main universe table: ~7 data rows visible, scroll for the rest */
  .table-wrap.main-scroll {{
    max-height: calc(2.6rem + 7 * 3.05rem);
    overflow-y: auto;
    margin-bottom: 8px;
  }}
  .table-wrap.main-scroll thead th {{
    z-index: 2;
    box-shadow: 0 1px 0 var(--border);
  }}
  .table-hint {{
    margin: 0 28px 18px;
    color: var(--text-dim);
    font-size: 0.78rem;
  }}
  .jump-link {{
    margin-left: auto;
    color: var(--accent);
    font-size: 0.85rem;
    text-decoration: none;
  }}
  .jump-link:hover {{ text-decoration: underline; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    min-width: 1100px;
  }}
  th, td {{
    padding: 9px 10px;
    border-bottom: 1px solid var(--border);
    text-align: right;
    white-space: nowrap;
  }}
  th {{
    position: sticky;
    top: 0;
    background: var(--surface2);
    color: var(--text-muted);
    font-weight: 600;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    cursor: pointer;
    user-select: none;
  }}
  th:hover {{ color: var(--text); }}
  th.sorted-asc::after {{ content: " ▲"; color: var(--accent); }}
  th.sorted-desc::after {{ content: " ▼"; color: var(--accent); }}
  td:first-child, th:first-child,
  td:nth-child(2), th:nth-child(2) {{ text-align: left; }}
  tr:hover td {{ background: rgba(79, 126, 248, 0.06); }}
  tr.expandable {{ cursor: pointer; }}
  tr.detail-row td {{
    background: #141824;
    text-align: left;
    white-space: normal;
    padding: 14px 16px;
  }}
  .detail-chart-wrap {{
    height: 240px;
    margin: 0 0 14px;
    background: #10131c;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 12px;
  }}
  .detail-chart-title {{
    font-weight: 700;
    margin-bottom: 6px;
  }}
  .detail-chart-sub {{
    color: var(--text-dim);
    font-size: 0.78rem;
    margin-bottom: 8px;
  }}
  .ticker {{ font-weight: 700; color: var(--accent); }}
  .name {{ color: var(--text-dim); font-size: 0.78rem; }}
  .pos {{ color: var(--green); font-weight: 600; }}
  .neg {{ color: var(--red); font-weight: 600; }}
  .flag {{
    display: inline-block;
    padding: 2px 7px;
    border-radius: 999px;
    font-size: 0.7rem;
    font-weight: 700;
    background: var(--yellow-bg);
    color: var(--yellow);
  }}
  .badge {{
    display: inline-block;
    padding: 2px 7px;
    border-radius: 6px;
    font-size: 0.7rem;
    background: var(--surface2);
    color: var(--text-muted);
  }}
  .badge.cache {{ color: var(--text-dim); }}
  .analysts {{
    width: 100%;
    border-collapse: collapse;
    margin-top: 8px;
  }}
  .analysts th, .analysts td {{
    text-align: left;
    font-size: 0.8rem;
    padding: 6px 8px;
    border-bottom: 1px solid var(--border);
  }}
  .muted {{ color: var(--text-dim); }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .section-title {{
    margin: 8px 28px 10px;
    font-size: 1.05rem;
    font-weight: 700;
  }}
  .section-sub {{
    margin: 0 28px 12px;
    color: var(--text-muted);
    font-size: 0.85rem;
  }}
  #brokerTable {{ min-width: 1100px; }}
  .tabs {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 0 28px 12px;
  }}
  .tab {{
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text-muted);
    border-radius: 8px;
    padding: 7px 12px;
    font: inherit;
    cursor: pointer;
  }}
  .tab.active {{
    color: var(--text);
    border-color: var(--accent);
    background: var(--surface2);
  }}
  @media (max-width: 700px) {{
    .header, .stats, .controls, .chart-wrap, .table-wrap, .section-title, .section-sub, .tabs, .table-hint {{ margin-left: 12px; margin-right: 12px; padding-left: 12px; padding-right: 12px; }}
    .header {{ margin: 0; padding: 20px 16px; }}
    .stats {{ padding: 14px 16px; margin: 0; }}
    .controls {{ padding: 0 16px 14px; margin: 0; }}
  }}
</style>
</head>
<body>
  <header class="header">
    <h1>Stock Price Target Tracker</h1>
    <div class="sub">12-month analyst targets · yfinance · FMP · Alpha Vantage · MS/GS/JPM/RBC/Desjardins · weekly change tracking</div>
    <div class="meta">Generated {timestamp} · Week deltas {week_label} · <a href="https://targets.pranavp.dev">targets.pranavp.dev</a></div>
  </header>

  <section class="stats" id="stats"></section>

  <section class="controls">
    <input type="search" id="search" placeholder="Filter ticker or name…" />
    <select id="recFilter">
      <option value="">All recommendations</option>
      <option value="strong_buy">Strong Buy</option>
      <option value="buy">Buy</option>
      <option value="hold">Hold</option>
      <option value="underperform">Underperform</option>
      <option value="sell">Sell</option>
    </select>
    <label><input type="checkbox" id="aboveOnly" /> Above target only</label>
    <label><input type="checkbox" id="divOnly" /> Divergence flagged</label>
    <label><input type="checkbox" id="positiveOnly" /> Upside &gt; 0</label>
    <label><input type="checkbox" id="firmOnly" /> Has firm target</label>
    <a class="jump-link" href="#firm-picks">Firm picks ↓</a>
  </section>

  <div class="chart-wrap">
    <canvas id="upsideChart"></canvas>
  </div>

  <div class="table-wrap main-scroll">
    <table id="mainTable">
      <thead>
        <tr>
          <th data-key="rank">#</th>
          <th data-key="ticker">Ticker</th>
          <th data-key="current_price">Price</th>
          <th data-key="primary_target">Target</th>
          <th data-key="upside_pct">Upside %</th>
          <th data-key="yf_target_mean">YF Mean</th>
          <th data-key="fmp_latest_target">FMP</th>
          <th data-key="av_target">AV</th>
          <th data-key="n_firm_targets"># Firms</th>
          <th data-key="best_firm_upside_pct">Best Firm Upside</th>
          <th data-key="divergence_pct">Div %</th>
          <th data-key="week_delta_yf">YF Δwk</th>
          <th data-key="trailing_pe">P/E</th>
          <th data-key="forward_pe">Fwd P/E</th>
          <th data-key="market_cap">Mkt Cap</th>
          <th data-key="recommendation_key">Rec</th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>
  <p class="table-hint">Showing 7 rows — scroll inside the table for the full universe.</p>

  <h2 class="section-title" id="firm-picks">Firm picks</h2>
  <p class="section-sub">Sell-side recommendations scraped from PriceTargets.com (MS · GS · JPM · RBC · Desjardins). Click a row for the price vs target chart. P/E · Fwd P/E · mkt cap from Yahoo.</p>
  <div class="tabs" id="brokerTabs"></div>
  <div class="table-wrap">
    <table id="brokerTable">
      <thead>
        <tr>
          <th data-bk-key="date">Date</th>
          <th data-bk-key="ticker">Ticker</th>
          <th data-bk-key="name">Name</th>
          <th data-bk-key="rating">Rating</th>
          <th data-bk-key="action">Action</th>
          <th data-bk-key="price">Price</th>
          <th data-bk-key="target">Target</th>
          <th data-bk-key="upside_pct">Upside %</th>
          <th data-bk-key="trailing_pe">P/E</th>
          <th data-bk-key="forward_pe">Fwd P/E</th>
          <th data-bk-key="market_cap">Mkt Cap</th>
        </tr>
      </thead>
      <tbody id="brokerBody"></tbody>
    </table>
  </div>

<script>
const DATA = {data_payload};

const fmt = {{
  num(v, d=2) {{
    if (v === null || v === undefined || v === '') return '—';
    return Number(v).toLocaleString(undefined, {{ maximumFractionDigits: d, minimumFractionDigits: 0 }});
  }},
  pct(v) {{
    if (v === null || v === undefined || v === '') return '—';
    const n = Number(v);
    const cls = n > 0 ? 'pos' : (n < 0 ? 'neg' : '');
    return `<span class="${{cls}}">${{n > 0 ? '+' : ''}}${{n.toFixed(2)}}%</span>`;
  }},
  money(v, ccy) {{
    if (v === null || v === undefined || v === '') return '—';
    const prefix = (ccy === 'CAD') ? 'C$' : '$';
    return prefix + Number(v).toLocaleString(undefined, {{ maximumFractionDigits: 2 }});
  }},
  mcap(v) {{
    if (v === null || v === undefined || v === '') return '—';
    const n = Number(v);
    if (n >= 1e12) return '$' + (n/1e12).toFixed(2) + 'T';
    if (n >= 1e9) return '$' + (n/1e9).toFixed(1) + 'B';
    if (n >= 1e6) return '$' + (n/1e6).toFixed(0) + 'M';
    return '$' + n.toLocaleString();
  }},
  delta(v) {{
    if (v === null || v === undefined || v === '') return '—';
    const n = Number(v);
    const cls = n > 0 ? 'pos' : (n < 0 ? 'neg' : '');
    return `<span class="${{cls}}">${{n > 0 ? '+' : ''}}${{n.toFixed(2)}}</span>`;
  }},
}};

function renderStats() {{
  const s = DATA.stats || {{}};
  const panels = DATA.broker_panels || [];
  const items = [
    ['Tickers', s.n_tickers ?? DATA.tickers.length],
    ['Avg Upside', s.avg_upside_pct != null ? s.avg_upside_pct + '%' : '—'],
    ['Median Upside', s.median_upside_pct != null ? s.median_upside_pct + '%' : '—'],
    ['Above Target', s.n_above_target ?? 0],
    ['Divergence Flags', s.n_divergence_flag ?? 0],
    ['AV Coverage', `${{s.n_with_av ?? 0}} / ${{DATA.tickers.length}}`],
    ['Firm coverage', s.n_with_firm_targets ?? 0],
    ['Brokers scraped', s.n_brokers ?? panels.length],
  ];
  document.getElementById('stats').innerHTML = items.map(([label, value]) =>
    `<div class="stat"><div class="label">${{label}}</div><div class="value">${{value}}</div></div>`
  ).join('');
}}

let sortKey = 'upside_pct';
let sortDir = 'desc';
let bkSortKey = 'date';
let bkSortDir = 'desc';
let activeBroker = ((DATA.broker_panels || [])[0] || {{}}).slug || 'morgan_stanley';
let expanded = new Set();
let brokerExpanded = new Set(); // keys: `${{slug}}::${{ticker}}`

function filtered() {{
  const q = document.getElementById('search').value.trim().toLowerCase();
  const rec = document.getElementById('recFilter').value;
  const aboveOnly = document.getElementById('aboveOnly').checked;
  const divOnly = document.getElementById('divOnly').checked;
  const positiveOnly = document.getElementById('positiveOnly').checked;
  const firmOnly = document.getElementById('firmOnly').checked;

  return DATA.tickers.filter(t => {{
    if (q && !(t.ticker || '').toLowerCase().includes(q) && !(t.name || '').toLowerCase().includes(q)) return false;
    if (rec && (t.recommendation_key || '') !== rec) return false;
    if (aboveOnly && !t.above_target) return false;
    if (divOnly && !t.divergence_flag) return false;
    if (positiveOnly && !(t.upside_pct > 0)) return false;
    if (firmOnly && !(t.n_firm_targets > 0)) return false;
    return true;
  }});
}}

function sortedRows() {{
  const rows = filtered().slice();
  rows.sort((a, b) => {{
    const av = a[sortKey], bv = b[sortKey];
    const aNull = av === null || av === undefined || av === '';
    const bNull = bv === null || bv === undefined || bv === '';
    if (aNull && bNull) return 0;
    if (aNull) return 1;
    if (bNull) return -1;
    if (typeof av === 'string' || typeof bv === 'string') {{
      const cmp = String(av).localeCompare(String(bv));
      return sortDir === 'asc' ? cmp : -cmp;
    }}
    const cmp = Number(av) - Number(bv);
    return sortDir === 'asc' ? cmp : -cmp;
  }});
  return rows;
}}

function nextEarningsNote(chart) {{
  const next = chart && chart.next_earnings;
  if (!next) return '';
  const asOf = String((DATA && DATA.iso_timestamp) || '').slice(0, 10)
    || new Date().toISOString().slice(0, 10);
  const a = Date.parse(asOf + 'T00:00:00');
  const b = Date.parse(String(next).slice(0, 10) + 'T00:00:00');
  if (Number.isNaN(a) || Number.isNaN(b)) return ` · next ER ${{next}}`;
  const days = Math.round((b - a) / 86400000);
  if (days < 0) return '';
  if (days === 0) return ` · earnings today (${{next}})`;
  if (days === 1) return ` · next ER in 1 day (${{next}})`;
  return ` · next ER in ${{days}} days (${{next}})`;
}}

function chartBlock(t, canvasId) {{
  const c = (t && t.chart) || {{}};
  const nP = (c.prices || []).length;
  const nT = (c.targets || []).length;
  const nE = (c.earnings || []).length;
  if (!t) {{
    return `<div class="muted" style="margin-bottom:12px">No chart — no price data for this ticker yet.</div>`;
  }}
  if (!nP && !nT) {{
    return `<div class="muted" style="margin-bottom:12px">No price/target history yet for this ticker.</div>`;
  }}
  const id = canvasId || `chart-${{t.ticker}}`;
  const erNote = nextEarningsNote(c);
  const sub = t._firmOnly
    ? `Weekly close · green = this firm’s target · orange dashed = past earnings (${{nE}})${{erNote}}`
    : `Weekly close · green = consensus target · orange dashed = past earnings (${{nE}})${{erNote}}`;
  return `<div style="margin-bottom:12px">
    <div class="detail-chart-title">Price vs ${{t._firmOnly ? 'firm target' : 'consensus target'}}</div>
    <div class="detail-chart-sub">${{sub}}</div>
    <div class="detail-chart-wrap"><canvas id="${{id}}" data-ticker="${{t.ticker}}"></canvas></div>
  </div>`;
}}

function firmBlock(t) {{
  const firms = Object.values(t.firm_targets || {{}});
  if (!firms.length) return '';
  const body = firms.map(f => {{
    const ccyNote = f.currency && f.currency !== 'USD'
      ? ` <span class="muted">(${{f.currency}})</span>` : '';
    return `<tr>
      <td>${{f.name || f.short || f.slug}}</td>
      <td>${{fmt.money(f.target, f.currency)}}${{ccyNote}}</td>
      <td>${{fmt.pct(f.upside_pct)}}</td>
      <td>${{f.rating || '—'}}</td>
      <td>${{f.action || '—'}}</td>
      <td>${{f.date || '—'}}</td>
      <td>${{fmt.delta(f.week_delta)}}</td>
    </tr>`;
  }}).join('');
  return `<div style="margin-bottom:12px"><strong>Sell-side firm targets</strong>
    <table class="analysts">
      <thead><tr><th>Firm</th><th>Target</th><th>Upside</th><th>Rating</th><th>Action</th><th>Date</th><th>Δwk</th></tr></thead>
      <tbody>${{body}}</tbody>
    </table>
  </div>`;
}}

function analystTable(t) {{
  const rows = t.fmp_analysts || [];
  const meta = `<span class="muted"> · FMP consensus ${{fmt.money(t.fmp_latest_target)}} (hi ${{fmt.money(t.fmp_target_high)}} / lo ${{fmt.money(t.fmp_target_low)}}) · 52W ${{fmt.money(t.fifty_two_week_low)}} – ${{fmt.money(t.fifty_two_week_high)}} · β ${{fmt.num(t.beta)}}</span>`;
  const chart = chartBlock(t);
  const firms = firmBlock(t);
  if (!rows.length) {{
    return `<div>${{chart}}${{firms}}<strong>FMP detail</strong>${{meta}}<div class="muted" style="margin-top:8px">No firm-level FMP rows for this ticker (budget/plan limit).</div></div>`;
  }}
  const isGrades = rows[0].source === 'grades';
  const title = isGrades
    ? `Recent firm grades (FMP free tier — no individual $ targets)`
    : `Named analyst targets (FMP)`;
  const body = rows.map(a => {{
    const rating = a.recommendation_key || '—';
    const ratingExtra = a.previous_grade ? ` <span class="muted">(${{a.action || 'from'}} ${{a.previous_grade}})</span>` : '';
    return `<tr>
      <td>${{a.analyst_company || '—'}}</td>
      <td>${{a.analyst_name || '—'}}</td>
      <td>${{a.price_target != null ? fmt.money(a.price_target) : '—'}}</td>
      <td>${{a.date || '—'}}</td>
      <td>${{rating}}${{ratingExtra}}</td>
      <td>${{a.news_url ? `<a href="${{a.news_url}}" target="_blank" rel="noopener">${{a.news_title || 'link'}}</a>` : (a.news_title || '—')}}</td>
    </tr>`;
  }}).join('');
  return `<div>${{chart}}${{firms}}<strong>${{title}}</strong>${{meta}}
    <table class="analysts">
      <thead><tr><th>Firm</th><th>Analyst</th><th>Target</th><th>Date</th><th>Rating</th><th>News</th></tr></thead>
      <tbody>${{body}}</tbody>
    </table>
  </div>`;
}}

const detailCharts = {{}};

function destroyDetailChart(key) {{
  if (detailCharts[key]) {{
    detailCharts[key].destroy();
    delete detailCharts[key];
  }}
}}

function buildAlignedSeries(prices, targets) {{
  // Axis = price bars + target snapshot dates only (earnings never stretch the timeline)
  const dateSet = new Set();
  (prices || []).forEach(p => dateSet.add(p.date));
  (targets || []).forEach(t => {{ if (t && t.date) dateSet.add(t.date); }});
  const labels = Array.from(dateSet).sort();
  const priceMap = Object.fromEntries((prices || []).map(p => [p.date, p.close]));
  const priceData = labels.map(d => (priceMap[d] != null ? priceMap[d] : null));

  const sortedT = (targets || []).slice().sort((a, b) => String(a.date).localeCompare(String(b.date)));
  const firstTarget = sortedT.length ? sortedT[0].target : null;
  let i = 0;
  let cur = null;
  const targetData = labels.map(d => {{
    while (i < sortedT.length && sortedT[i].date <= d) {{
      cur = sortedT[i].target;
      i += 1;
    }}
    // Before first snapshot: still show earliest known consensus as a reference line
    return cur != null ? cur : firstTarget;
  }});

  return {{ labels, priceData, targetData }};
}}

function mapEarningsAnnotations(prices, earnings, maxGapDays = 10) {{
  // Snap ER to nearest weekly price label; ignore dates after the last price bar
  if (!(prices || []).length) return [];
  const start = prices[0].date;
  const end = prices[prices.length - 1].date;
  const priceDates = prices.map(p => p.date);
  const out = [];
  const used = new Set();
  (earnings || []).forEach(d => {{
    if (!d || d < start || d > end) return;
    const tEarn = Date.parse(d);
    if (Number.isNaN(tEarn)) return;
    let best = priceDates[0];
    let bestDiff = Infinity;
    priceDates.forEach(l => {{
      const diff = Math.abs(Date.parse(l) - tEarn);
      if (diff < bestDiff) {{ bestDiff = diff; best = l; }}
    }});
    if (bestDiff > maxGapDays * 86400000) return;
    if (used.has(best)) return;
    used.add(best);
    out.push({{ date: d, label: best }});
  }});
  return out;
}}

function renderDetailChart(ticker, canvasId, chartSource) {{
  const chartKey = canvasId || ticker;
  const t = chartSource || DATA.tickers.find(x => x.ticker === ticker);
  if (!t) return;
  const canvas = document.getElementById(canvasId || `chart-${{ticker}}`);
  if (!canvas) return;
  destroyDetailChart(chartKey);

  const c = t.chart || {{}};
  const prices = c.prices || [];
  const targets = c.targets || [];
  const earnMarks = mapEarningsAnnotations(prices, c.earnings || []);
  if (!prices.length && !targets.length) return;

  const {{ labels, priceData, targetData }} = buildAlignedSeries(prices, targets);
  const hasTarget = targetData.some(v => v != null);

  const annotations = {{}};
  earnMarks.forEach((m, idx) => {{
    annotations[`e${{idx}}`] = {{
      type: 'line',
      xMin: m.label,
      xMax: m.label,
      borderColor: 'rgba(249, 115, 22, 0.85)',
      borderWidth: 1.5,
      borderDash: [4, 3],
      label: {{
        display: true,
        content: 'ER',
        position: 'start',
        backgroundColor: 'rgba(249, 115, 22, 0.85)',
        color: '#111',
        font: {{ size: 9, weight: 'bold' }},
      }},
    }};
  }});

  const earnLabels = new Set(earnMarks.map(m => m.label));
  const earnDates = new Set(earnMarks.map(m => m.date));

  detailCharts[chartKey] = new Chart(canvas, {{
    type: 'line',
    data: {{
      labels,
      datasets: [
        {{
          label: 'Price',
          data: priceData,
          borderColor: '#4f7ef8',
          backgroundColor: 'rgba(79,126,248,0.12)',
          fill: true,
          tension: 0.15,
          pointRadius: 0,
          borderWidth: 2,
          spanGaps: true,
        }},
        {{
          label: 'Consensus target',
          data: hasTarget ? targetData : [],
          borderColor: '#22c55e',
          backgroundColor: 'transparent',
          fill: false,
          tension: 0,
          stepped: 'before',
          pointRadius: targets.length <= 12 ? 3 : 0,
          borderWidth: 2,
          spanGaps: true,
        }},
      ],
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{
          labels: {{ color: '#94a3b8', boxWidth: 12, font: {{ size: 11 }} }},
        }},
        annotation: {{ annotations }},
        tooltip: {{
          callbacks: {{
            afterBody(items) {{
              const x = items[0] && items[0].label;
              if (x && earnLabels.has(x)) return ['Earnings report'];
              return [];
            }},
          }},
        }},
      }},
      scales: {{
        x: {{
          ticks: {{ color: '#64748b', maxTicksLimit: 8, font: {{ size: 10 }} }},
          grid: {{ color: '#2e3250' }},
        }},
        y: {{
          ticks: {{ color: '#64748b', font: {{ size: 10 }} }},
          grid: {{ color: '#2e3250' }},
        }},
      }},
    }},
  }});
}}

function renderTable() {{
  Object.keys(detailCharts).forEach(k => {{
    if (!String(k).startsWith('bk-chart-')) destroyDetailChart(k);
  }});
  const tbody = document.getElementById('tbody');
  const rows = sortedRows();
  document.querySelectorAll('#mainTable th[data-key]').forEach(th => {{
    th.classList.remove('sorted-asc', 'sorted-desc');
    if (th.dataset.key === sortKey) th.classList.add(sortDir === 'asc' ? 'sorted-asc' : 'sorted-desc');
  }});

  tbody.innerHTML = rows.map(t => {{
    const flags = [];
    if (t.above_target) flags.push('<span class="flag">above target</span>');
    if (t.divergence_flag) flags.push('<span class="flag">divergence</span>');
    const shorts = Object.values(t.firm_targets || {{}}).map(f => f.short || f.slug).filter(Boolean);
    if (shorts.length) flags.push(`<span class="flag">${{shorts.join(' · ')}}</span>`);
    const avBadge = t.av_from_cache ? '<span class="badge cache" title="cached from prior AV fetch">cache</span>' : '';
    const bestFirm = (t.firm_targets || {{}})[t.best_firm_slug] || {{}};
    const open = expanded.has(t.ticker);
    return `<tr class="expandable" data-ticker="${{t.ticker}}">
      <td>${{t.rank ?? ''}}</td>
      <td><div class="ticker">${{t.ticker}}</div><div class="name">${{t.name || ''}}</div>${{flags.join(' ')}}</td>
      <td>${{fmt.money(t.current_price)}}</td>
      <td>${{fmt.money(t.primary_target)}} <span class="badge">${{t.primary_target_source || ''}}</span></td>
      <td>${{fmt.pct(t.upside_pct)}}</td>
      <td>${{fmt.money(t.yf_target_mean)}}</td>
      <td>${{fmt.money(t.fmp_latest_target)}}</td>
      <td>${{fmt.money(t.av_target)}} ${{avBadge}}</td>
      <td>${{t.n_firm_targets || 0}}</td>
      <td>${{fmt.pct(t.best_firm_upside_pct)}}${{bestFirm.short ? ` <span class="badge">${{bestFirm.short}}</span>` : ''}}</td>
      <td>${{t.divergence_pct != null ? fmt.num(t.divergence_pct) + '%' : '—'}}</td>
      <td>${{fmt.delta(t.week_delta_yf)}}</td>
      <td>${{fmt.num(t.trailing_pe)}}</td>
      <td>${{fmt.num(t.forward_pe)}}</td>
      <td>${{fmt.mcap(t.market_cap)}}</td>
      <td>${{t.recommendation_key || '—'}}</td>
    </tr>
    <tr class="detail-row" style="display:${{open ? 'table-row' : 'none'}}" data-detail="${{t.ticker}}">
      <td colspan="16">${{analystTable(t)}}</td>
    </tr>`;
  }}).join('');

  // Re-draw charts for rows that stay expanded after filter/sort
  expanded.forEach(ticker => {{
    requestAnimationFrame(() => renderDetailChart(ticker));
  }});
}}

function currentBrokerPanel() {{
  return (DATA.broker_panels || []).find(p => p.slug === activeBroker) || (DATA.broker_panels || [])[0] || null;
}}

function renderBrokerTabs() {{
  const tabs = document.getElementById('brokerTabs');
  const panels = DATA.broker_panels || [];
  tabs.innerHTML = panels.map(p =>
    `<button type="button" class="tab ${{p.slug === activeBroker ? 'active' : ''}}" data-slug="${{p.slug}}">${{p.short || p.name}} (${{(p.picks || []).length}})</button>`
  ).join('');
}}

function tickerRow(ticker) {{
  return (DATA.tickers || []).find(x => x.ticker === ticker) || null;
}}

function firmChartKey(r, brokerSlug) {{
  const ccy = String((r && (r.price_currency || r.target_currency)) || '').toUpperCase();
  if (ccy === 'CAD' || brokerSlug === 'desjardins') {{
    return `${{(r && r.ticker) || ''}}::CAD`;
  }}
  return (r && r.ticker) || '';
}}

function chartForBrokerPick(r, brokerSlug) {{
  const ccy = String((r && (r.price_currency || r.target_currency)) || '').toUpperCase();
  const isCad = ccy === 'CAD' || brokerSlug === 'desjardins';
  // Universe charts are US listings — don't use them for CAD collisions (e.g. H)
  if (!isCad) {{
    const uni = tickerRow(r.ticker);
    if (uni) return uni;
  }}
  const fcMap = DATA.firm_charts || {{}};
  const key = firmChartKey(r, brokerSlug);
  let fc = fcMap[key] || (!isCad ? fcMap[r.ticker] : null) || (isCad ? fcMap[r.ticker] : null);
  // If CAD alias missing, try bare only when it was stored as CAD-only
  if (!fc && isCad && fcMap[r.ticker] && fcMap[r.ticker].cad) fc = fcMap[r.ticker];
  if (!fc) return null;
  const date = String(r.date || '').slice(0, 10);
  const targets = (r.target != null && !Number.isNaN(Number(r.target)))
    ? [{{ date: date || ((fc.prices || []).slice(-1)[0] || {{}}).date || '', target: Number(r.target) }}].filter(p => p.date)
    : (fc.targets || []);
  const useTargets = targets.length ? targets : (fc.targets || []);
  return {{
    ticker: r.ticker,
    name: r.name,
    _firmOnly: true,
    chart: {{
      prices: fc.prices || [],
      targets: useTargets,
      earnings: fc.earnings || [],
      next_earnings: fc.next_earnings || null,
    }},
  }};
}}

function brokerPickRow(key) {{
  const panel = currentBrokerPanel();
  // key format is `${{slug}}::${{ticker}}` (ticker may contain dots, not ::)
  const parts = key.split('::');
  const tk = parts.slice(1).join('::');
  return ((panel && panel.picks) || []).find(p => p.ticker === tk) || {{ ticker: tk }};
}}

function renderBrokerPanel() {{
  // Destroy prior broker detail charts
  Object.keys(detailCharts).forEach(k => {{
    if (String(k).startsWith('bk-chart-')) destroyDetailChart(k);
  }});
  renderBrokerTabs();
  const panel = currentBrokerPanel();
  const slug = (panel && panel.slug) || activeBroker;
  const rows = ((panel && panel.picks) || []).slice().sort((a, b) => {{
    const av = a[bkSortKey], bv = b[bkSortKey];
    const aNull = av === null || av === undefined || av === '';
    const bNull = bv === null || bv === undefined || bv === '';
    if (aNull && bNull) return 0;
    if (aNull) return 1;
    if (bNull) return -1;
    if (typeof av === 'string' || typeof bv === 'string') {{
      const cmp = String(av).localeCompare(String(bv));
      return bkSortDir === 'asc' ? cmp : -cmp;
    }}
    const cmp = Number(av) - Number(bv);
    return bkSortDir === 'asc' ? cmp : -cmp;
  }});
  document.querySelectorAll('#brokerTable th[data-bk-key]').forEach(th => {{
    th.classList.remove('sorted-asc', 'sorted-desc');
    if (th.dataset.bkKey === bkSortKey) th.classList.add(bkSortDir === 'asc' ? 'sorted-asc' : 'sorted-desc');
  }});
  // Drop expansions for other broker tabs
  brokerExpanded = new Set([...brokerExpanded].filter(k => k.startsWith(slug + '::')));

  document.getElementById('brokerBody').innerHTML = rows.map(r => {{
    const key = `${{slug}}::${{r.ticker}}`;
    const open = brokerExpanded.has(key);
    const pickChart = chartForBrokerPick(r, slug);
    const canvasId = `bk-chart-${{slug}}-${{r.ticker}}`.replace(/[^a-zA-Z0-9_-]/g, '_');
    const detail = open
      ? `<tr class="detail-row" data-bk-detail="${{key}}"><td colspan="11">${{chartBlock(pickChart, canvasId)}}</td></tr>`
      : `<tr class="detail-row" data-bk-detail="${{key}}" style="display:none"><td colspan="11"></td></tr>`;
    return `<tr class="expandable" data-bk-key="${{key}}" data-bk-ticker="${{r.ticker || ''}}" data-bk-slug="${{slug}}">
    <td style="text-align:left">${{r.date || '—'}}</td>
    <td style="text-align:left"><span class="ticker">${{r.ticker || ''}}</span></td>
    <td style="text-align:left">${{r.name || '—'}}</td>
    <td>${{r.rating || '—'}}</td>
    <td style="text-align:left">${{r.action || '—'}}</td>
    <td>${{fmt.money(r.price, r.price_currency)}}</td>
    <td>${{fmt.money(r.target, r.target_currency)}}</td>
    <td>${{fmt.pct(r.upside_pct)}}</td>
    <td>${{fmt.num(r.trailing_pe)}}</td>
    <td>${{fmt.num(r.forward_pe)}}</td>
    <td>${{fmt.mcap(r.market_cap)}}</td>
  </tr>${{detail}}`;
  }}).join('') || '<tr><td colspan="11" class="muted" style="text-align:left">No rows for this broker.</td></tr>';

  brokerExpanded.forEach(key => {{
    const [, ticker] = key.split('::');
    const canvasId = `bk-chart-${{slug}}-${{ticker}}`.replace(/[^a-zA-Z0-9_-]/g, '_');
    const pick = ((panel && panel.picks) || []).find(p => p.ticker === ticker);
    const pickChart = chartForBrokerPick(pick || {{ ticker }}, slug);
    if (pickChart) requestAnimationFrame(() => renderDetailChart(ticker, canvasId, pickChart));
  }});
}}

function renderChart() {{
  const rows = sortedRows().filter(t => t.upside_pct != null).slice(0, 30);
  const ctx = document.getElementById('upsideChart');
  if (window._chart) window._chart.destroy();
  window._chart = new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: rows.map(t => t.ticker),
      datasets: [{{
        label: 'Upside %',
        data: rows.map(t => t.upside_pct),
        backgroundColor: rows.map(t => t.upside_pct >= 0 ? 'rgba(34,197,94,0.7)' : 'rgba(239,68,68,0.7)'),
      }}],
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{ display: false }},
        title: {{ display: true, text: 'Top upside (filtered view, max 30)', color: '#94a3b8', font: {{ size: 12 }} }},
      }},
      scales: {{
        x: {{ ticks: {{ color: '#64748b', maxRotation: 90 }}, grid: {{ color: '#2e3250' }} }},
        y: {{ ticks: {{ color: '#64748b' }}, grid: {{ color: '#2e3250' }} }},
      }},
    }},
  }});
}}

function refresh() {{
  renderTable();
  renderChart();
  renderBrokerPanel();
}}

document.querySelectorAll('#mainTable th[data-key]').forEach(th => {{
  th.addEventListener('click', () => {{
    const key = th.dataset.key;
    if (sortKey === key) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    else {{ sortKey = key; sortDir = key === 'ticker' ? 'asc' : 'desc'; }}
    refresh();
  }});
}});

document.querySelectorAll('#brokerTable th[data-bk-key]').forEach(th => {{
  th.addEventListener('click', () => {{
    const key = th.dataset.bkKey;
    if (bkSortKey === key) bkSortDir = bkSortDir === 'asc' ? 'desc' : 'asc';
    else {{ bkSortKey = key; bkSortDir = key === 'ticker' || key === 'name' ? 'asc' : 'desc'; }}
    renderBrokerPanel();
  }});
}});

document.getElementById('brokerTabs').addEventListener('click', (e) => {{
  const btn = e.target.closest('button.tab');
  if (!btn) return;
  activeBroker = btn.dataset.slug;
  renderBrokerPanel();
}});

document.getElementById('tbody').addEventListener('click', (e) => {{
  const tr = e.target.closest('tr.expandable');
  if (!tr) return;
  const ticker = tr.dataset.ticker;
  if (expanded.has(ticker)) {{
    expanded.delete(ticker);
    destroyDetailChart(ticker);
  }} else {{
    expanded.add(ticker);
  }}
  const detail = document.querySelector(`tr[data-detail="${{ticker}}"]`);
  if (detail) detail.style.display = expanded.has(ticker) ? 'table-row' : 'none';
  if (expanded.has(ticker)) {{
    requestAnimationFrame(() => renderDetailChart(ticker));
  }}
}});

document.getElementById('brokerBody').addEventListener('click', (e) => {{
  const tr = e.target.closest('tr.expandable');
  if (!tr) return;
  const key = tr.dataset.bkKey;
  const ticker = tr.dataset.bkTicker;
  const slug = tr.dataset.bkSlug;
  if (!key || !ticker) return;
  const canvasId = `bk-chart-${{slug}}-${{ticker}}`.replace(/[^a-zA-Z0-9_-]/g, '_');
  const detail = document.querySelector(`tr[data-bk-detail="${{key}}"]`);
  if (brokerExpanded.has(key)) {{
    brokerExpanded.delete(key);
    destroyDetailChart(canvasId);
    if (detail) {{ detail.style.display = 'none'; detail.querySelector('td').innerHTML = ''; }}
  }} else {{
    brokerExpanded.add(key);
    if (detail) {{
      detail.style.display = 'table-row';
      const pick = brokerPickRow(key);
      const pickChart = chartForBrokerPick(pick, slug);
      detail.querySelector('td').innerHTML = chartBlock(pickChart, canvasId);
      if (pickChart) requestAnimationFrame(() => renderDetailChart(ticker, canvasId, pickChart));
    }}
  }}
}});

['search', 'recFilter', 'aboveOnly', 'divOnly', 'positiveOnly', 'firmOnly'].forEach(id => {{
  document.getElementById(id).addEventListener('input', refresh);
  document.getElementById(id).addEventListener('change', refresh);
}});

renderStats();
refresh();
</script>
</body>
</html>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"HTML written: {output_path} ({output_path.stat().st_size // 1024} KB)")
