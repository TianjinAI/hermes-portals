#!/usr/bin/env python3
"""Bloomberg Daily Digest Portal v3 — Light theme, standalone on port 5053"""

import json
import os
import re
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("PORT", "5053"))
DATA_DIR = Path.home() / ".hermes" / "bloomberg_digest"

# ─── Newsletter Type Colors ──────────────────────────────────────────────

NL_COLORS = {
    "Morning Briefing": "#2563eb",
    "Markets Daily": "#059669",
    "Technology": "#7c3aed",
    "Politics": "#dc2626",
    "Crypto": "#d97706",
    "Geopolitics": "#e11d48",
    "Macro": "#0891b2",
    "Asia Markets": "#db2777",
    "Weekend": "#78716c",
    "Weekend Edition": "#78716c",
}

def get_nl_color(nl_type):
    if not nl_type:
        return "#78716c"
    for key, color in NL_COLORS.items():
        if key.lower() in nl_type.lower():
            return color
    h = hashlib.md5(nl_type.encode()).hexdigest()[:6]
    return f"#{h}"

# ─── Data Loaders ────────────────────────────────────────────────────────

def get_available_dates():
    dates = set()
    for f in DATA_DIR.glob("*.json"):
        if f.stem.count("-") >= 2 and not f.stem.endswith("_index") and not f.stem.endswith("_links"):
            stem = f.stem
            if re.match(r"^\d{4}-\d{2}-\d{2}$", stem):
                dates.add(stem)
    return sorted(dates, reverse=True)

def load_meta(date_str):
    path = DATA_DIR / f"{date_str}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None

def load_index(date_str):
    path = DATA_DIR / f"{date_str}_index.json"
    if path.exists():
        return json.loads(path.read_text())
    return None

def load_full_html(date_str):
    path = DATA_DIR / "full" / f"{date_str}.html"
    if path.exists():
        return path.read_text()
    return None

def load_brief(date_str):
    path = DATA_DIR / "briefs" / f"{date_str}.md"
    if path.exists():
        return path.read_text()
    return None

def build_kb_index():
    kb = {"dates": [], "newsletter_types": {}, "total_newsletters": 0, "total_links": 0}
    for date_str in get_available_dates():
        meta = load_meta(date_str)
        index = load_index(date_str)
        if meta:
            entry = {
                "date": date_str,
                "newsletter_count": meta.get("newsletter_count", 0),
                "story_count": len(meta.get("newsletters", [])),
            }
            kb["dates"].append(entry)
            kb["total_newsletters"] += meta.get("newsletter_count", 0)
        if index:
            for nl in index.get("newsletters", []):
                nt = nl.get("newsletter_type", "Unknown")
                if nt not in kb["newsletter_types"]:
                    kb["newsletter_types"][nt] = {"count": 0, "dates": set()}
                kb["newsletter_types"][nt]["count"] += 1
                kb["newsletter_types"][nt]["dates"].add(date_str)
                kb["total_links"] += nl.get("url_count", 0)
    for nt in kb["newsletter_types"]:
        kb["newsletter_types"][nt]["dates"] = sorted(kb["newsletter_types"][nt]["dates"])
    return kb

# ─── HTML ────────────────────────────────────────────────────────────────

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Bloomberg Digest</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #f8f7f0;
    --bg-warm: #f5f4eb;
    --surface: #ffffff;
    --surface-alt: #fafaf5;
    --surface-hover: #f5f4eb;
    --border: #e8e6db;
    --border-light: #ede9de;
    --text: #1a1a1a;
    --text-secondary: #57534e;
    --text-muted: #a8a29e;
    --text-dim: #d6d3d1;
    --accent: #ff6b35;
    --accent-light: rgba(255,107,53,0.08);
    --accent-border: rgba(255,107,53,0.25);
    --green: #059669;
    --green-bg: rgba(5,150,105,0.08);
    --red: #dc2626;
    --red-bg: rgba(220,38,38,0.08);
    --amber: #d97706;
    --amber-bg: rgba(217,119,6,0.08);
    --blue: #2563eb;
    --blue-bg: rgba(37,99,235,0.08);
    --purple: #7c3aed;
    --purple-bg: rgba(124,58,237,0.08);
    --mono: 'JetBrains Mono', ui-monospace, monospace;
    --sans: 'Inter', -apple-system, system-ui, sans-serif;
    --radius: 8px;
    --radius-lg: 12px;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.04);
    --shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
    --shadow-md: 0 4px 6px rgba(0,0,0,0.06), 0 2px 4px rgba(0,0,0,0.04);
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  body {
    font-family: var(--sans);
    background: var(--bg);
    color: var(--text);
    font-size: 13px;
    line-height: 1.6;
    min-height: 100vh;
    overflow-x: hidden;
  }
  a { color: var(--blue); text-decoration: none; }
  a:hover { text-decoration: underline; }

  /* ── Header ──────────────────────────────────────────────────────────── */
  .header {
    position: fixed; top: 0; left: 0; right: 0; height: 52px;
    background: #1a1a1a;
    display: flex; align-items: center; padding: 0 24px; z-index: 100; gap: 16px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  }
  .logo { display: flex; align-items: center; gap: 10px; }
  .logo-icon {
    width: 28px; height: 28px; background: var(--accent);
    border-radius: 5px; display: flex; align-items: center; justify-content: center;
    font-size: 12px; font-weight: 700; color: #fff;
  }
  .logo-text { font-size: 15px; font-weight: 600; color: #ffffff; }
  .logo-text span { color: #9ca3af; font-weight: 400; }
  .nav-center { display: flex; align-items: center; gap: 10px; margin-left: auto; }
  .nav-center .sep { width: 1px; height: 24px; background: #374151; margin: 0 4px; }
  .date-nav { display: flex; align-items: center; gap: 6px; }
  .nav-btn {
    background: #374151; border: 1px solid #4b5563; color: #d1d5db;
    width: 30px; height: 30px; border-radius: 6px; cursor: pointer;
    display: flex; align-items: center; justify-content: center; font-size: 14px;
    transition: all 0.15s;
  }
  .nav-btn:hover { background: #4b5563; color: #ffffff; }
  .date-display {
    font-family: var(--mono); font-size: 12px; color: #d1d5db;
    padding: 6px 12px; background: #374151; border: 1px solid #4b5563;
    border-radius: 6px; cursor: pointer; min-width: 110px; text-align: center;
  }
  .date-display:hover { border-color: var(--accent); color: #ffffff; }
  .view-tabs { display: flex; gap: 0; }
  .view-tabs button {
    background: none; border: 1px solid transparent; color: #9ca3af;
    padding: 6px 14px; cursor: pointer; font-size: 11px; font-weight: 500;
    text-transform: uppercase; letter-spacing: 0.5px; transition: all 0.15s;
  }
  .view-tabs button:first-child { border-radius: 6px 0 0 6px; }
  .view-tabs button:last-child { border-radius: 0 6px 6px 0; }
  .view-tabs button.active { background: var(--accent); color: #ffffff; }
  .view-tabs button:hover:not(.active) { color: #ffffff; background: #374151; }

  /* ── Layout ──────────────────────────────────────────────────────────── */
  .main { margin-top: 52px; display: flex; min-height: calc(100vh - 52px); }
  .content { flex: 1; padding: 24px; max-width: 1000px; margin: 0 auto; width: 100%; }
  .sidebar {
    width: 240px; background: var(--surface); border-left: 1px solid var(--border);
    padding: 20px 16px; flex-shrink: 0; display: none;
  }
  @media (min-width: 1200px) { .sidebar { display: block; } }

  /* ── Section Headers ─────────────────────────────────────────────────── */
  .section-header {
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 12px; padding-bottom: 8px;
    border-bottom: 2px solid var(--border);
  }
  .section-icon {
    width: 32px; height: 32px; border-radius: var(--radius);
    display: flex; align-items: center; justify-content: center; font-size: 16px;
    flex-shrink: 0;
  }
  .section-title { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; color: var(--text-secondary); }
  .section-count {
    margin-left: auto; font-size: 11px; color: var(--text-muted);
    font-family: var(--mono);
  }

  /* ── Cards ───────────────────────────────────────────────────────────── */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 16px;
    margin-bottom: 16px;
    box-shadow: var(--shadow-sm);
  }

  /* ── Market Hero Strip ───────────────────────────────────────────────── */
  .market-strip {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 10px; margin-bottom: 20px;
  }
  .market-item {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 12px;
    box-shadow: var(--shadow-sm); transition: all 0.15s;
  }
  .market-item:hover { box-shadow: var(--shadow); transform: translateY(-1px); }
  .market-item .label { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); margin-bottom: 4px; }
  .market-item .value { font-size: 18px; font-weight: 600; font-family: var(--mono); color: var(--text); }
  .market-item .change { font-size: 12px; font-family: var(--mono); font-weight: 500; margin-top: 4px; }
  .up { color: var(--green); }
  .down { color: var(--red); }
  .neutral { color: var(--text-muted); }

  /* ── Headlines ───────────────────────────────────────────────────────── */
  .headline-list { list-style: none; }
  .headline-item {
    display: flex; gap: 14px; padding: 12px 8px;
    border-bottom: 1px solid var(--border-light);
    transition: background 0.15s; border-radius: var(--radius);
  }
  .headline-item:last-child { border-bottom: none; }
  .headline-item:hover { background: var(--surface-hover); }
  .headline-rank {
    font-family: var(--mono); font-size: 20px; font-weight: 700;
    color: var(--text-dim); width: 30px; flex-shrink: 0; text-align: center;
    line-height: 1.2;
  }
  .headline-body { flex: 1; min-width: 0; }
  .headline-title { font-size: 14px; font-weight: 500; color: var(--text); line-height: 1.4; }
  .headline-context { font-size: 12px; color: var(--text-secondary); margin-top: 4px; line-height: 1.5; }
  .headline-tags { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
  .tag {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 3px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.3px;
  }
  .tag-cat { background: var(--accent-light); color: var(--accent); }

  /* ── Newsletter Cards ────────────────────────────────────────────────── */
  .nl-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 14px;
  }
  .nl-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-lg); padding: 16px;
    transition: all 0.2s; position: relative; overflow: hidden;
    box-shadow: var(--shadow-sm);
  }
  .nl-card:hover { box-shadow: var(--shadow-md); transform: translateY(-2px); }
  .nl-card::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
    background: var(--nl-color, var(--border));
  }
  .nl-header { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
  .nl-type-badge {
    font-size: 10px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.5px; padding: 4px 10px; border-radius: 4px;
    background: var(--nl-color-bg, rgba(0,0,0,0.04));
    color: var(--nl-color, var(--text-secondary));
  }
  .nl-time { font-size: 10px; color: var(--text-muted); font-family: var(--mono); margin-left: auto; }
  .nl-subject { font-size: 14px; font-weight: 500; line-height: 1.4; margin-bottom: 8px; }
  .nl-reporter {
    display: flex; align-items: center; gap: 8px;
    font-size: 12px; color: var(--text-secondary); margin-bottom: 10px;
  }
  .nl-avatar {
    width: 24px; height: 24px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 10px; font-weight: 600; color: #fff; flex-shrink: 0;
  }
  .nl-links { display: flex; gap: 6px; flex-wrap: wrap; }
  .nl-link {
    font-size: 10px; padding: 3px 8px; background: var(--surface-alt);
    border: 1px solid var(--border-light); border-radius: 4px; color: var(--blue);
    transition: all 0.15s;
  }
  .nl-link:hover { background: var(--blue-bg); border-color: var(--blue); }
  .nl-url-more { font-size: 10px; color: var(--text-muted); padding: 3px 0; }

  /* ── What to Watch ───────────────────────────────────────────────────── */
  .watch-list { list-style: none; }
  .watch-item {
    display: flex; gap: 12px; padding: 10px 0;
    border-bottom: 1px solid var(--border-light);
  }
  .watch-item:last-child { border-bottom: none; }
  .watch-num {
    width: 24px; height: 24px; border-radius: 50%;
    background: var(--accent-light); color: var(--accent);
    display: flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 600; flex-shrink: 0;
    border: 1px solid var(--accent-border);
  }
  .watch-text { font-size: 13px; color: var(--text-secondary); line-height: 1.5; }
  .watch-text strong { color: var(--text); font-weight: 500; }

  /* ── Knowledge Base ──────────────────────────────────────────────────── */
  .kb-stats {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
    gap: 12px; margin-bottom: 20px;
  }
  .kb-stat {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-lg); padding: 20px; text-align: center;
    box-shadow: var(--shadow-sm); transition: all 0.2s;
  }
  .kb-stat:hover { box-shadow: var(--shadow); transform: translateY(-1px); }
  .kb-stat .num { font-size: 32px; font-weight: 700; color: var(--accent); font-family: var(--mono); }
  .kb-stat .label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.8px; margin-top: 6px; font-weight: 500; }
  .type-tags { display: flex; flex-wrap: wrap; gap: 8px; }
  .type-tag {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 6px 12px; border-radius: 6px; font-size: 12px; font-weight: 500;
    background: var(--surface); border: 1px solid var(--border);
    color: var(--text-secondary); box-shadow: var(--shadow-sm);
  }
  .type-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
  .date-list { list-style: none; }
  .date-list li { padding: 8px 0; border-bottom: 1px solid var(--border-light); }
  .date-list li:last-child { border-bottom: none; }
  .date-list a { font-size: 13px; color: var(--text-secondary); display: flex; justify-content: space-between; }
  .date-list a:hover { color: var(--accent); }
  .date-list .count { font-family: var(--mono); font-size: 11px; color: var(--text-muted); }

  /* ── Intelligence View ───────────────────────────────────────────────── */
  .intel-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 16px; margin-bottom: 16px;
  }
  .intel-column { display: flex; flex-direction: column; gap: 16px; }
  .entity-list, .theme-list, .reporter-list { display: flex; flex-direction: column; gap: 8px; }
  .entity-item, .theme-item, .reporter-item {
    padding: 10px; background: var(--surface-alt); border-radius: var(--radius);
    border: 1px solid var(--border-light);
  }
  .entity-name, .theme-name, .reporter-name {
    font-size: 13px; font-weight: 500; color: var(--text);
  }
  .entity-count, .theme-count, .reporter-count {
    font-size: 11px; color: var(--text-muted); font-family: var(--mono);
  }
  .entity-meta, .theme-meta {
    font-size: 10px; color: var(--text-dim); margin-top: 4px;
  }
  .theme-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
  .theme-bar {
    height: 6px; background: var(--border); border-radius: 3px; overflow: hidden;
  }
  .theme-bar-fill {
    height: 100%; background: var(--accent); border-radius: 3px; transition: width 0.3s;
  }
  .reporter-types { display: flex; gap: 4px; margin-top: 6px; flex-wrap: wrap; }
  .reporter-type {
    font-size: 10px; padding: 2px 6px; background: var(--blue-bg); color: var(--blue);
    border-radius: 3px;
  }
  .empty { color: var(--text-muted); font-size: 12px; padding: 10px 0; }

  /* ── Full Digest ─────────────────────────────────────────────────────── */
  .full-digest { max-width: 100%; }
  .full-digest h2 { font-size: 22px; font-weight: 600; color: var(--accent); margin: 28px 0 14px; }
  .full-digest h3 { font-size: 13px; font-weight: 600; margin: 24px 0 10px; color: var(--text); border-bottom: 2px solid var(--border); padding-bottom: 8px; text-transform: uppercase; letter-spacing: 0.8px; }
  .full-digest p { margin: 10px 0; line-height: 1.7; }
  .full-digest ul, .full-digest ol { margin: 10px 0; padding-left: 24px; }
  .full-digest li { margin: 6px 0; line-height: 1.6; }
  .full-digest strong { font-weight: 600; color: var(--text); }
  .full-digest em { color: var(--text-secondary); font-style: normal; }
  .full-digest table { border-collapse: collapse; width: 100%; margin: 14px 0; }
  .full-digest td, .full-digest th { border: 1px solid var(--border); padding: 10px 14px; text-align: left; font-size: 13px; }
  .full-digest th { background: var(--surface-alt); color: var(--text-secondary); font-weight: 600; text-transform: uppercase; font-size: 10px; letter-spacing: 0.5px; }

  /* ── Loading ─────────────────────────────────────────────────────────── */
  .loading { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 80px; }
  .spinner { width: 32px; height: 32px; border: 3px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; margin-bottom: 16px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .loading-text { font-size: 13px; color: var(--text-muted); }

  /* ── Sidebar ─────────────────────────────────────────────────────────── */
  .sidebar-title { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; color: var(--text-muted); margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
  .sidebar .date-list a { font-family: var(--mono); font-size: 12px; }
</style>
</head>
<body>

<div class="header">
  <div class="logo">
    <div class="logo-icon">B</div>
    <div class="logo-text">Bloomberg <span>Digest</span></div>
  </div>
  <div class="nav-center">
    <div class="date-nav">
      <button class="nav-btn" onclick="navDate(-1)" title="Previous">&larr;</button>
      <div class="date-display" id="dateDisplay" onclick="pickDate()">—</div>
      <button class="nav-btn" onclick="navDate(1)" title="Next">&rarr;</button>
    </div>
    <div class="sep"></div>
    <div class="view-tabs">
      <button id="vBrief" class="active" onclick="setView('brief')">Brief</button>
      <button id="vFull" onclick="setView('full')">Full</button>
      <button id="vIntel" onclick="setView('intel')">Intel</button>
      <button id="vKB" onclick="setView('kb')">KB</button>
    </div>
  </div>
</div>

<div class="main">
  <div class="content" id="content">
    <div class="loading"><div class="spinner"></div><div class="loading-text">Loading digest...</div></div>
  </div>
  <div class="sidebar">
    <div class="sidebar-title">Archive</div>
    <ul class="date-list" id="dateList"></ul>
  </div>
</div>

<script>
let currentDate = null;
let currentView = 'brief';
let availableDates = [];
let cachedData = {};

async function init() {
  const res = await fetch('/api/dates');
  const data = await res.json();
  availableDates = data.dates || [];
  document.getElementById('dateList').innerHTML = availableDates.map(d =>
    `<li><a href="#" onclick="event.preventDefault();goDate('${d}')">${d} <span class="count">▸</span></a></li>`
  ).join('');
  if (availableDates.length > 0) { currentDate = availableDates[0]; render(); }
}
init();

async function render() {
  if (!currentDate) return;
  document.getElementById('dateDisplay').textContent = currentDate;
  document.getElementById('content').innerHTML = '<div class="loading"><div class="spinner"></div><div class="loading-text">Loading ' + currentDate + '...</div></div>';

  if (currentView === 'kb') { await renderKB(); return; }
  if (currentView === 'intel') { await renderIntel(); return; }

  const cacheKey = currentDate;
  if (!cachedData[cacheKey]) {
    const res = await fetch('/api/date/' + currentDate);
    if (!res.ok) { document.getElementById('content').innerHTML = '<div class="card"><p style="color:var(--text-muted)">No digest for this date.</p></div>'; return; }
    cachedData[cacheKey] = await res.json();
  }
  const data = cachedData[cacheKey];
  if (currentView === 'brief') renderBrief(data);
  else renderFull(data);
}

function renderBrief(data) {
  const html = data.full_html || '';
  const index = data.index || {};
  const newsletters = index.newsletters || [];

  // Parse market data
  let marketHtml = '';
  const mkt = html.match(/<h3>[^<]*Market Data[^<]*<\\/h3>([\\s\\S]*?)(?:<h3>|$)/i);
  if (mkt) {
    const items = parseMarketData(mkt[1]);
    marketHtml = items.map(m => `
      <div class="market-item">
        <div class="label">${esc(m.label)}</div>
        <div class="value">${esc(m.value)}</div>
        <div class="change ${m.cls}">${esc(m.change)}</div>
      </div>
    `).join('');
  }

  // Parse headlines
  let headlinesHtml = '';
  const hl = html.match(/<h3>[^<]*(?:Critical Headlines|Top Headlines)[^<]*<\\/h3>\\s*<ol>([\\s\\S]*?)<\\/ol>/i);
  if (hl) {
    const items = hl[1].split(/<li>/i).filter(s => s.trim());
    headlinesHtml = items.map((item, i) => {
      const title = item.replace(/<[^>]+>/g, '').replace(/\\s+/g, ' ').trim();
      if (!title) return '';
      const emMatch = item.match(/<em>([^<]+)<\\/em>/i);
      const cat = emMatch ? emMatch[1] : '';
      const parts = title.split(/[—–\\.] /);
      const mainTitle = parts[0] || title;
      const context = parts.slice(1).join('. ').substring(0, 200);
      return `
        <li class="headline-item">
          <div class="headline-rank">${i + 1}</div>
          <div class="headline-body">
            <div class="headline-title">${esc(mainTitle)}</div>
            ${context ? `<div class="headline-context">${esc(context)}</div>` : ''}
            ${cat ? `<div class="headline-tags"><span class="tag tag-cat">${esc(cat)}</span></div>` : ''}
          </div>
        </li>
      `;
    }).join('');
  }

  // Parse What to Watch
  let watchHtml = '';
  const wtch = html.match(/<h3>[^<]*What to Watch[^<]*<\\/h3>([\\s\\S]*?)(?:<h3>|$)/i);
  if (wtch) {
    const items = wtch[1].split(/<li>/i).filter(s => s.trim());
    watchHtml = items.map((item, i) => {
      const text = item.replace(/<[^>]+>/g, '').replace(/\\s+/g, ' ').trim();
      if (!text) return '';
      const parts = text.split(/[—–]/);
      const bold = parts[0] || '';
      const rest = parts.slice(1).join(' — ');
      return `
        <li class="watch-item">
          <div class="watch-num">${i + 1}</div>
          <div class="watch-text"><strong>${esc(bold)}</strong>${rest ? ' — ' + esc(rest.substring(0, 200)) : ''}</div>
        </li>
      `;
    }).join('');
  }

  // Newsletter cards
  const nlCards = newsletters.map(nl => {
    const color = getNlColor(nl.newsletter_type);
    const colorBg = color + '12';
    const avatar = nl.reporter ? makeAvatar(nl.reporter, color) : '';
    const urls = nl.urls || [];
    const linkHtml = urls.slice(0, 4).map(u =>
      `<a class="nl-link" href="${esc(u)}" target="_blank" title="${esc(u)}">link</a>`
    ).join('');
    const more = urls.length > 4 ? `<span class="nl-url-more">+${urls.length - 4}</span>` : '';
    return `
      <div class="nl-card" style="--nl-color:${color};--nl-color-bg:${colorBg}">
        <div class="nl-header">
          <span class="nl-type-badge">${esc(nl.newsletter_type || 'Newsletter')}</span>
          <span class="nl-time">${esc(nl.date_local || '')}</span>
        </div>
        <div class="nl-subject">${esc(nl.subject)}</div>
        ${nl.reporter ? `<div class="nl-reporter">${avatar}<span>${esc(nl.reporter)}</span></div>` : ''}
        <div class="nl-links">${linkHtml}${more}</div>
      </div>
    `;
  }).join('');

  document.getElementById('content').innerHTML = `
    ${marketHtml ? `
    <div class="section-header">
      <div class="section-icon" style="background:var(--green-bg);color:var(--green)">📈</div>
      <div class="section-title">Markets</div>
    </div>
    <div class="market-strip">${marketHtml}</div>
    ` : ''}

    <div class="section-header">
      <div class="section-icon" style="background:var(--red-bg);color:var(--red)">🔥</div>
      <div class="section-title">Top Headlines</div>
      <div class="section-count">${headlinesHtml.split('headline-item').length - 1} stories</div>
    </div>
    <div class="card">
      <ol class="headline-list" style="padding-left:0">${headlinesHtml}</ol>
    </div>

    <div class="section-header">
      <div class="section-icon" style="background:var(--blue-bg);color:var(--blue)">📰</div>
      <div class="section-title">Newsletters</div>
      <div class="section-count">${newsletters.length} sources</div>
    </div>
    <div class="nl-grid">${nlCards}</div>

    ${watchHtml ? `
    <div class="section-header" style="margin-top:24px">
      <div class="section-icon" style="background:var(--amber-bg);color:var(--amber)">💡</div>
      <div class="section-title">What to Watch</div>
    </div>
    <div class="card">
      <ul class="watch-list">${watchHtml}</ul>
    </div>
    ` : ''}
  `;
}

function renderFull(data) {
  const html = data.full_html || '<p style="color:var(--text-muted)">Full digest not available.</p>';
  document.getElementById('content').innerHTML = '<div class="full-digest">' + html + '</div>';
}
// ─── Knowledge Base ──────────────────────────────────────────────────────
async function renderKB() {
  const res = await fetch('/api/kb');
  const data = await res.json();
  const types = data.newsletter_types || {};
  const typeTags = Object.entries(types)
    .sort((a, b) => b[1].count - a[1].count)
    .map(([type, info]) => {
      const color = getNlColor(type);
      return `<span class="type-tag"><span class="type-dot" style="background:${color}"></span>${esc(type)} <span style="color:var(--text-muted)">(${info.count})</span></span>`;
    }).join('');

  const dateHistory = (data.dates || []).map(d =>
    `<li><a href="#" onclick="event.preventDefault();goDate('${d.date}')">${d.date} <span class="count">${d.newsletter_count} nl · ${d.story_count} stories</span></a></li>`
  ).join('');

  document.getElementById('content').innerHTML = `
    <div class="section-header">
      <div class="section-icon" style="background:var(--purple-bg);color:var(--purple)">📊</div>
      <div class="section-title">Knowledge Base</div>
    </div>
    <div class="kb-stats">
      <div class="kb-stat"><div class="num">${data.total_dates || 0}</div><div class="label">Days</div></div>
      <div class="kb-stat"><div class="num">${data.total_newsletters || 0}</div><div class="label">Newsletters</div></div>
      <div class="kb-stat"><div class="num">${data.total_links || 0}</div><div class="label">Links</div></div>
      <div class="kb-stat"><div class="num">${Object.keys(types).length}</div><div class="label">Types</div></div>
    </div>
    <div class="card">
      <div class="section-header" style="margin-bottom:12px">
        <div class="section-title">Newsletter Types</div>
      </div>
      <div class="type-tags">${typeTags}</div>
    </div>
    <div class="card">
      <div class="section-header" style="margin-bottom:12px">
        <div class="section-title">Daily History</div>
      </div>
      <ul class="date-list">${dateHistory}</ul>
    </div>
  `;
}

// ─── Intelligence View ──────────────────────────────────────────────────
async function renderIntel() {
  const res = await fetch('/api/intelligence');
  const data = await res.json();

  if (data.error) {
    document.getElementById('content').innerHTML = `
      <div class="card">
        <div class="section-header">
          <div class="section-icon" style="background:var(--blue-bg);color:var(--blue)">🧠</div>
          <div class="section-title">Cumulative Intelligence</div>
        </div>
        <p style="color:var(--text-muted);padding:20px 0">Knowledge base not yet built. Run the Bloomberg digest pipeline first to start accumulating intelligence.</p>
      </div>
    `;
    return;
  }

  // Top entities by mention count
  const topCompanies = Object.entries(data.entities?.companies || {})
    .sort((a, b) => b[1].mention_count - a[1].mention_count)
    .slice(0, 10)
    .map(([name, info]) => `
      <div class="entity-item">
        <div class="entity-name">${esc(name)}</div>
        <div class="entity-count">${info.mention_count} mentions</div>
        <div class="entity-meta">Last: ${info.last_seen}</div>
      </div>
    `).join('');

  const topPeople = Object.entries(data.entities?.people || {})
    .sort((a, b) => b[1].mention_count - a[1].mention_count)
    .slice(0, 8)
    .map(([name, info]) => `
      <div class="entity-item">
        <div class="entity-name">${esc(name)}</div>
        <div class="entity-count">${info.mention_count} mentions</div>
      </div>
    `).join('');

  // Top themes with frequency
  const topThemes = Object.entries(data.themes || {})
    .sort((a, b) => b[1].mention_count - a[1].mention_count)
    .slice(0, 8)
    .map(([theme, info]) => {
      const maxMentions = Math.max(...Object.values(info.daily_mentions || {}));
      const barWidth = maxMentions > 0 ? Math.min(100, (info.mention_count / maxMentions) * 100) : 0;
      return `
        <div class="theme-item">
          <div class="theme-header">
            <div class="theme-name">${esc(theme)}</div>
            <div class="theme-count">${info.mention_count} total</div>
          </div>
          <div class="theme-bar">
            <div class="theme-bar-fill" style="width:${barWidth}%"></div>
          </div>
          <div class="theme-meta">Active: ${info.first_seen} → ${info.last_seen}</div>
        </div>
      `;
    }).join('');

  // Reporter network
  const topReporters = Object.entries(data.reporters || {})
    .sort((a, b) => b[1].article_count - a[1].article_count)
    .slice(0, 6)
    .map(([name, info]) => {
      const types = (info.newsletter_types || []).slice(0, 3).map(t =>
        `<span class="reporter-type">${esc(t)}</span>`
      ).join('');
      return `
        <div class="reporter-item">
          <div class="reporter-name">${esc(name)}</div>
          <div class="reporter-count">${info.article_count} articles</div>
          <div class="reporter-types">${types}</div>
        </div>
      `;
    }).join('');

  // Top sectors and countries
  const topSectors = Object.entries(data.entities?.sectors || {})
    .sort((a, b) => b[1].mention_count - a[1].mention_count)
    .slice(0, 6)
    .map(([name, info]) => `<span class="type-tag">${esc(name)} (${info.mention_count})</span>`)
    .join('');

  const topCountries = Object.entries(data.entities?.countries || {})
    .sort((a, b) => b[1].mention_count - a[1].mention_count)
    .slice(0, 6)
    .map(([name, info]) => `<span class="type-tag">${esc(name)} (${info.mention_count})</span>`)
    .join('');

  document.getElementById('content').innerHTML = `
    <div class="section-header">
      <div class="section-icon" style="background:var(--blue-bg);color:var(--blue)">🧠</div>
      <div class="section-title">Cumulative Intelligence</div>
      <div class="section-count">Last updated: ${data.last_updated ? data.last_updated.split('T')[0] : 'Never'}</div>
    </div>

    <div class="intel-grid">
      <div class="intel-column">
        <div class="card">
          <div class="section-header" style="margin-bottom:12px">
            <div class="section-title">🏢 Top Companies</div>
          </div>
          <div class="entity-list">${topCompanies || '<div class="empty">No data yet</div>'}</div>
        </div>

        <div class="card">
          <div class="section-header" style="margin-bottom:12px">
            <div class="section-title">👤 Key People</div>
          </div>
          <div class="entity-list">${topPeople || '<div class="empty">No data yet</div>'}</div>
        </div>
      </div>

      <div class="intel-column">
        <div class="card">
          <div class="section-header" style="margin-bottom:12px">
            <div class="section-title">🔥 Trending Themes</div>
          </div>
          <div class="theme-list">${topThemes || '<div class="empty">No data yet</div>'}</div>
        </div>

        <div class="card">
          <div class="section-header" style="margin-bottom:12px">
            <div class="section-title">📰 Reporter Network</div>
          </div>
          <div class="reporter-list">${topReporters || '<div class="empty">No data yet</div>'}</div>
        </div>
      </div>
    </div>

    <div class="card" style="margin-top:16px">
      <div class="section-header" style="margin-bottom:12px">
        <div class="section-title">🌍 Sectors & Regions</div>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:8px">
        ${topSectors ? `<div><strong>Sectors:</strong> ${topSectors}</div>` : ''}
        ${topCountries ? `<div><strong>Countries:</strong> ${topCountries}</div>` : ''}
      </div>
    </div>
  `;
}

// ─── Helpers ─────────────────────────────────────────────────────────────
const NL_COLORS = {
  "morning briefing": "#2563eb", "markets daily": "#059669",
  "technology": "#7c3aed", "politics": "#dc2626", "crypto": "#d97706",
  "geopolitics": "#e11d48", "macro": "#0891b2", "asia markets": "#db2777",
  "weekend": "#78716c",
};
function getNlColor(type) {
  if (!type) return '#78716c';
  const t = type.toLowerCase();
  for (const [k, v] of Object.entries(NL_COLORS)) {
    if (t.includes(k)) return v;
  }
  let h = 0; for (let i = 0; i < t.length; i++) h = t.charCodeAt(i) + ((h << 5) - h);
  return '#' + ((h >> 24) & 0xFF).toString(16).padStart(2,'0') + ((h >> 16) & 0xFF).toString(16).padStart(2,'0') + ((h >> 8) & 0xFF).toString(16).padStart(2,'0');
}

function makeAvatar(name, color) {
  const parts = name.split(' ').filter(Boolean);
  const initials = parts.length >= 2 ? parts[0][0] + parts[parts.length-1][0] : (parts[0] || '?').substring(0,2);
  return `<span class="nl-avatar" style="background:${color}">${initials.toUpperCase()}</span>`;
}

function parseMarketData(html) {
  const items = [];
  const parts = html.split(/<li>/i).filter(s => s.trim());
  for (const p of parts) {
    const text = p.replace(/<[^>]+>/g, '').replace(/\\s+/g, ' ').trim();
    if (!text) continue;
    const m = text.match(/^(.+?):\\s*(.+?)$/);
    if (!m) continue;
    const label = m[1].trim();
    const rest = m[2].trim();
    const changeMatch = rest.match(/([+-]?\\d+\\.?\\d*%?)/);
    const change = changeMatch ? changeMatch[1] : '';
    const value = rest.replace(/[+-]?\\d+\\.?\\d*%?/g, '').replace(/\\(\\)/g, '').trim();
    const cls = change.startsWith('+') ? 'up' : change.startsWith('-') ? 'down' : 'neutral';
    items.push({ label, value: value || rest, change, cls });
  }
  return items;
}

function setView(view) {
  currentView = view;
  document.querySelectorAll('.view-tabs button').forEach(b => b.classList.remove('active'));
  document.getElementById('vBrief').classList.toggle('active', view === 'brief');
  document.getElementById('vFull').classList.toggle('active', view === 'full');
  document.getElementById('vIntel').classList.toggle('active', view === 'intel');
  document.getElementById('vKB').classList.toggle('active', view === 'kb');
  render();
}
function goDate(d) { currentDate = d; render(); }
function navDate(delta) {
  const idx = availableDates.indexOf(currentDate);
  if (idx === -1) return;
  const n = Math.max(0, Math.min(availableDates.length - 1, idx + delta));
  if (n !== idx) { currentDate = availableDates[n]; render(); }
}
function pickDate() {
  const d = prompt('Enter date (YYYY-MM-DD):', currentDate);
  if (d && /^\\d{4}-\\d{2}-\\d{2}$/.test(d)) goDate(d);
}
function esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
</script>
</body>
</html>
"""

# ─── HTTP Handler ────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(HTML_PAGE.encode())
            elif path == "/api/dates":
                self.json({"dates": get_available_dates()})
            elif path.startswith("/api/date/"):
                date_str = path.split("/")[-1]
                meta = load_meta(date_str)
                if not meta:
                    self.send_error(404, "Not found"); return
                self.json({
                    "meta": meta,
                    "full_html": load_full_html(date_str),
                    "brief": load_brief(date_str),
                    "index": load_index(date_str),
                })
            elif path == "/api/kb":
                kb = build_kb_index()
                self.json({
                    "dates": kb["dates"],
                    "total_dates": len(kb["dates"]),
                    "total_newsletters": kb["total_newsletters"],
                    "total_links": kb["total_links"],
                    "newsletter_types": {k: {"count": v["count"], "dates": list(v["dates"])}
                                          for k, v in kb["newsletter_types"].items()},
                })
            elif path == "/api/intelligence":
                # Load cumulative knowledge base
                kb_path = DATA_DIR / "knowledge" / "knowledge_base.json"
                if kb_path.exists():
                    kb = json.loads(kb_path.read_text())
                    self.json(kb)
                else:
                    self.json({"error": "Knowledge base not yet built"})
            else:
                self.send_error(404, "Not Found")
        except Exception as e:
            self.send_error(500, str(e))

    def json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    print(f"📊 Bloomberg Digest Portal v3 — http://0.0.0.0:{PORT}")
    print(f"📁 Data: {DATA_DIR}")
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down")
        server.server_close()
