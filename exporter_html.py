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
) -> None:
    stats = stats or {}
    snapshot_info = snapshot_info or {}

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
        })

    data_payload = json.dumps(
        {
            "generated": timestamp,
            "iso_timestamp": iso_timestamp,
            "stats": stats,
            "snapshot_info": snapshot_info,
            "tickers": slim,
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
    margin: 0 28px 18px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
    height: 220px;
  }}
  .table-wrap {{
    margin: 0 28px 40px;
    overflow-x: auto;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
  }}
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
  @media (max-width: 700px) {{
    .header, .stats, .controls, .chart-wrap, .table-wrap {{ margin-left: 12px; margin-right: 12px; padding-left: 12px; padding-right: 12px; }}
    .header {{ margin: 0; padding: 20px 16px; }}
    .stats {{ padding: 14px 16px; margin: 0; }}
    .controls {{ padding: 0 16px 14px; margin: 0; }}
  }}
</style>
</head>
<body>
  <header class="header">
    <h1>Stock Price Target Tracker</h1>
    <div class="sub">12-month analyst targets · yfinance · FMP · Alpha Vantage · weekly change tracking</div>
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
  </section>

  <div class="chart-wrap">
    <canvas id="upsideChart"></canvas>
  </div>

  <div class="table-wrap">
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
  money(v) {{
    if (v === null || v === undefined || v === '') return '—';
    return '$' + Number(v).toLocaleString(undefined, {{ maximumFractionDigits: 2 }});
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
  const items = [
    ['Tickers', s.n_tickers ?? DATA.tickers.length],
    ['Avg Upside', s.avg_upside_pct != null ? s.avg_upside_pct + '%' : '—'],
    ['Median Upside', s.median_upside_pct != null ? s.median_upside_pct + '%' : '—'],
    ['Above Target', s.n_above_target ?? 0],
    ['Divergence Flags', s.n_divergence_flag ?? 0],
    ['AV Coverage', `${{s.n_with_av ?? 0}} / ${{DATA.tickers.length}}`],
  ];
  document.getElementById('stats').innerHTML = items.map(([label, value]) =>
    `<div class="stat"><div class="label">${{label}}</div><div class="value">${{value}}</div></div>`
  ).join('');
}}

let sortKey = 'upside_pct';
let sortDir = 'desc';
let expanded = new Set();

function filtered() {{
  const q = document.getElementById('search').value.trim().toLowerCase();
  const rec = document.getElementById('recFilter').value;
  const aboveOnly = document.getElementById('aboveOnly').checked;
  const divOnly = document.getElementById('divOnly').checked;
  const positiveOnly = document.getElementById('positiveOnly').checked;

  return DATA.tickers.filter(t => {{
    if (q && !(t.ticker || '').toLowerCase().includes(q) && !(t.name || '').toLowerCase().includes(q)) return false;
    if (rec && (t.recommendation_key || '') !== rec) return false;
    if (aboveOnly && !t.above_target) return false;
    if (divOnly && !t.divergence_flag) return false;
    if (positiveOnly && !(t.upside_pct > 0)) return false;
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

function analystTable(t) {{
  const rows = t.fmp_analysts || [];
  const meta = `<span class="muted"> · FMP consensus ${{fmt.money(t.fmp_latest_target)}} (hi ${{fmt.money(t.fmp_target_high)}} / lo ${{fmt.money(t.fmp_target_low)}}) · 52W ${{fmt.money(t.fifty_two_week_low)}} – ${{fmt.money(t.fifty_two_week_high)}} · β ${{fmt.num(t.beta)}}</span>`;
  if (!rows.length) {{
    return `<div><strong>FMP detail</strong>${{meta}}<div class="muted" style="margin-top:8px">No firm-level FMP rows for this ticker (budget/plan limit).</div></div>`;
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
  return `<div><strong>${{title}}</strong>${{meta}}
    <table class="analysts">
      <thead><tr><th>Firm</th><th>Analyst</th><th>Target</th><th>Date</th><th>Rating</th><th>News</th></tr></thead>
      <tbody>${{body}}</tbody>
    </table>
  </div>`;
}}

function renderTable() {{
  const tbody = document.getElementById('tbody');
  const rows = sortedRows();
  document.querySelectorAll('th').forEach(th => {{
    th.classList.remove('sorted-asc', 'sorted-desc');
    if (th.dataset.key === sortKey) th.classList.add(sortDir === 'asc' ? 'sorted-asc' : 'sorted-desc');
  }});

  tbody.innerHTML = rows.map(t => {{
    const flags = [];
    if (t.above_target) flags.push('<span class="flag">above target</span>');
    if (t.divergence_flag) flags.push('<span class="flag">divergence</span>');
    const avBadge = t.av_from_cache ? '<span class="badge cache" title="cached from prior AV fetch">cache</span>' : '';
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
      <td>${{t.divergence_pct != null ? fmt.num(t.divergence_pct) + '%' : '—'}}</td>
      <td>${{fmt.delta(t.week_delta_yf)}}</td>
      <td>${{fmt.num(t.trailing_pe)}}</td>
      <td>${{fmt.num(t.forward_pe)}}</td>
      <td>${{fmt.mcap(t.market_cap)}}</td>
      <td>${{t.recommendation_key || '—'}}</td>
    </tr>
    <tr class="detail-row" style="display:${{open ? 'table-row' : 'none'}}" data-detail="${{t.ticker}}">
      <td colspan="14">${{analystTable(t)}}</td>
    </tr>`;
  }}).join('');
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
}}

document.querySelectorAll('th[data-key]').forEach(th => {{
  th.addEventListener('click', () => {{
    const key = th.dataset.key;
    if (sortKey === key) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    else {{ sortKey = key; sortDir = key === 'ticker' ? 'asc' : 'desc'; }}
    refresh();
  }});
}});

document.getElementById('tbody').addEventListener('click', (e) => {{
  const tr = e.target.closest('tr.expandable');
  if (!tr) return;
  const ticker = tr.dataset.ticker;
  if (expanded.has(ticker)) expanded.delete(ticker);
  else expanded.add(ticker);
  const detail = document.querySelector(`tr[data-detail="${{ticker}}"]`);
  if (detail) detail.style.display = expanded.has(ticker) ? 'table-row' : 'none';
}});

['search', 'recFilter', 'aboveOnly', 'divOnly', 'positiveOnly'].forEach(id => {{
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
