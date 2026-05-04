#!/usr/bin/env python3
"""Bloomberg Intelligence Portal v4."""

import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

PORT = int(os.environ.get("PORT", "5053"))
DATA_DIR = Path.home() / ".hermes" / "bloomberg_digest"
BRIEFS_DIR = DATA_DIR / "briefs"
FULL_DIR = DATA_DIR / "full"
KNOWLEDGE_BASE_PATH = DATA_DIR / "knowledge" / "knowledge_base.json"
WORKBUDDY_DIR = Path.home() / ".hermes" / "workbuddy_reports"

CSS_VARS = """
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
    --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    --radius: 8px;
    --radius-lg: 12px;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.04);
    --shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
    --shadow-md: 0 4px 6px rgba(0,0,0,0.06), 0 2px 4px rgba(0,0,0,0.04);
  }
"""

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

SECTION_PATTERN = re.compile(
    r"^#{2,3}\s+(?:[\W_]*\s*)?(Top Headlines \(by market impact\)|Key Market Data|What to Watch Today|Quick Scan)(?:\s*[\W_]*)$",
    re.IGNORECASE,
)
HEADLINE_PATTERN = re.compile(
    r"^\s*(\d+)\.\s+\*\*(.+?)\*\*\s*[—-]\s*(.+?)(?:\s*\[([^\]]+)\])?\s*$"
)
WATCH_PATTERN = re.compile(r"^\s*(\d+)\.\s+\*\*(.+?)\*\*\s*[—-]\s*(.+?)\s*$")
TABLE_DIVIDER_PATTERN = re.compile(r"^\|(?:\s*[:-]+\s*\|)+\s*$")


def read_text(path: Path):
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def load_json(path: Path):
    text = read_text(path)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def get_available_dates():
    dates = set()
    for pattern in ("*.json", "briefs/*.md", "full/*.html"):
        for path in DATA_DIR.glob(pattern):
            stem = path.stem
            if stem.endswith("_index") or stem.endswith("_links"):
                continue
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", stem):
                dates.add(stem)
    return sorted(dates, reverse=True)


def load_meta(date_str):
    return load_json(DATA_DIR / f"{date_str}.json")


def load_index(date_str):
    return load_json(DATA_DIR / f"{date_str}_index.json")


def load_full_html(date_str):
    return read_text(FULL_DIR / f"{date_str}.html")


def load_brief_markdown(date_str):
    return read_text(BRIEFS_DIR / f"{date_str}.md")


def normalize_space(value):
    return re.sub(r"\s+", " ", (value or "").strip())


def title_case_token(token):
    if token.isupper() and len(token) <= 5:
        return token
    return token[:1].upper() + token[1:].lower()


def normalize_topic_name(name):
    text = normalize_space(name)
    if not text:
        return ""
    parts = re.split(r"([/&,+])", text)
    normalized = []
    for part in parts:
        if part in {"/", "&", ",", "+"}:
            normalized.append(part)
            continue
        words = [title_case_token(word) for word in part.split()]
        normalized.append(" ".join(words))
    return "".join(normalized).strip()


def split_topic_tags(raw_tag):
    if not raw_tag:
        return []
    parts = re.split(r"[/,]", raw_tag)
    seen = []
    for part in parts:
        token = normalize_topic_name(part)
        if token and token not in seen:
            seen.append(token)
    return seen


def classify_change(text):
    lowered = text.lower()
    if any(marker in lowered for marker in ("+", "up", "rall", "gain", "record high")):
        return "up"
    if any(marker in lowered for marker in ("−", "-", "down", "drop", "plunge", "under pressure", "falls", "fell")):
        return "down"
    return "neutral"


def parse_market_line(line, current_group):
    item = line.lstrip("- ").strip()
    if not item:
        return None
    label, sep, remainder = item.partition(":")
    if not sep:
        return None
    label = normalize_space(label)
    remainder = normalize_space(remainder)
    value = remainder
    change = ""
    notes = ""
    paren_match = re.search(r"\(([^()]*)\)\s*$", remainder)
    if paren_match:
        inside = normalize_space(paren_match.group(1))
        value = normalize_space(remainder[:paren_match.start()])
        if inside:
            change = inside
    dash_parts = [normalize_space(part) for part in value.split(" — ", 1)]
    if len(dash_parts) == 2:
        value, notes = dash_parts
    value = re.sub(r"\*\*", "", value).strip() or remainder.replace("**", "")
    notes = notes.replace("**", "")
    if not change:
        if value.startswith(("+", "-", "−")) or "%" in value:
            change = value
        elif any(token in remainder.lower() for token in ("under pressure", "rallied", "record high")):
            change = remainder.replace("**", "")
    return {
        "group": current_group,
        "label": label,
        "value": value,
        "change": change,
        "notes": notes,
        "change_class": classify_change(change or notes or remainder),
    }


def parse_quick_scan(lines):
    rows = []
    for raw in lines:
        line = raw.strip()
        if not line.startswith("|") or TABLE_DIVIDER_PATTERN.match(line):
            continue
        parts = [segment.strip() for segment in line.strip("|").split("|")]
        if len(parts) != 3 or parts[0].lower() == "time":
            continue
        rows.append(
            {
                "time": parts[0],
                "subject": parts[1].replace("**", ""),
                "takeaway": parts[2],
            }
        )
    return rows


def parse_brief_markdown(content, fallback_date=None):
    parsed = {
        "date": fallback_date,
        "title": None,
        "headlines": [],
        "market_data": [],
        "watch_items": [],
        "quick_scan": [],
        "bottom_line": None,
    }
    if not content:
        return parsed

    lines = [line.rstrip() for line in content.splitlines()]
    current_section = None
    buckets = defaultdict(list)

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped == "---":
            continue
        if stripped.startswith("#") and "Bloomberg Daily Brief" in stripped:
            parsed["title"] = stripped.lstrip("#").strip()
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", stripped)
            if date_match:
                parsed["date"] = date_match.group(1)
            continue
        section_match = SECTION_PATTERN.match(stripped)
        if section_match:
            current_section = section_match.group(1).lower()
            continue
        if stripped.startswith("**Bottom Line:**"):
            parsed["bottom_line"] = stripped.split(":", 1)[1].strip()
            continue
        if current_section:
            buckets[current_section].append(line)

    for raw in buckets.get("top headlines (by market impact)", []):
        match = HEADLINE_PATTERN.match(raw.strip())
        if not match:
            continue
        rank, title, context, category = match.groups()
        topics = split_topic_tags(category or "")
        parsed["headlines"].append(
            {
                "rank": int(rank),
                "title": normalize_space(title),
                "context": normalize_space(context),
                "category": normalize_topic_name(category or ""),
                "topic_tags": topics,
            }
        )

    current_group = None
    for raw in buckets.get("key market data", []):
        stripped = raw.strip()
        if not stripped:
            continue
        group_match = re.match(r"^\*\*(.+?):\*\*$", stripped)
        if group_match:
            current_group = normalize_space(group_match.group(1))
            continue
        if stripped.startswith("-"):
            item = parse_market_line(stripped, current_group)
            if item:
                parsed["market_data"].append(item)

    for raw in buckets.get("what to watch today", []):
        match = WATCH_PATTERN.match(raw.strip())
        if not match:
            continue
        order, title, description = match.groups()
        parsed["watch_items"].append(
            {
                "rank": int(order),
                "title": normalize_space(title),
                "description": normalize_space(description),
            }
        )

    parsed["quick_scan"] = parse_quick_scan(buckets.get("quick scan", []))
    parsed["headlines"].sort(key=lambda item: item["rank"])
    parsed["watch_items"].sort(key=lambda item: item["rank"])
    return parsed


def load_known_entities():
    kb = load_json(KNOWLEDGE_BASE_PATH) or {}
    entities = kb.get("entities", {})
    names = []
    for group_name in ("companies", "people", "countries", "sectors"):
        group = entities.get(group_name, {})
        for name, info in group.items():
            mentions = int(info.get("mention_count", 0)) if isinstance(info, dict) else 0
            names.append(
                {
                    "name": name,
                    "kind": group_name[:-1] if group_name.endswith("s") else group_name,
                    "mentions": mentions,
                }
            )
    names.sort(key=lambda item: (-len(item["name"]), -item["mentions"], item["name"].lower()))
    return kb, names


def extract_entities_from_text(text, known_entities):
    STOP_ENTITIES = {
        "AI", "US", "UK", "CEO", "IPO", "GDP", "Fed", "SEC", "EU",
        "Deal", "Board", "Growth", "Risk", "Impact", "Outlook",
        "Strategy", "Demand", "Supply", "Price", "Value", "Rate",
    }
    MIN_ENTITY_LENGTH = 4
    hits = []
    lowered = f" {text.lower()} "
    seen = set()
    for entity in known_entities:
        name = entity["name"].strip()
        if len(name) < MIN_ENTITY_LENGTH or name in STOP_ENTITIES:
            continue
        pattern = f" {name.lower()} "
        if pattern in lowered and name.lower() not in seen:
            seen.add(name.lower())
            hits.append(entity)
    return hits


def topic_heat_label(days_appeared):
    if days_appeared >= 5:
        return "High"
    if days_appeared >= 3:
        return "Medium"
    return "Emerging"


def compute_trend_split(day_counts):
    if len(day_counts) <= 1:
        total = sum(day_counts)
        return "stable", {"recent": total, "earlier": total}
    split = max(1, len(day_counts) // 2)
    earlier = sum(day_counts[:split])
    recent = sum(day_counts[split:])
    if recent > earlier:
        return "rising", {"recent": recent, "earlier": earlier}
    if recent < earlier:
        return "falling", {"recent": recent, "earlier": earlier}
    return "stable", {"recent": recent, "earlier": earlier}


def compute_trend_sliding_window(day_counts):
    """Sliding-window trend: compare last 3 vs prior 3 (excluding last 3)."""
    if len(day_counts) <= 1:
        total = sum(day_counts)
        return "stable", {"recent": total, "earlier": total}
    if len(day_counts) <= 3:
        return compute_trend_split(day_counts)
    recent = sum(day_counts[-3:])
    earlier = sum(day_counts[:-3])
    if recent > earlier:
        return "rising", {"recent": recent, "earlier": earlier}
    if recent < earlier:
        return "falling", {"recent": recent, "earlier": earlier}
    return "stable", {"recent": recent, "earlier": earlier}


def compute_trend(day_counts):
    """Entry point: uses sliding-window when >=7 days, split otherwise."""
    if len(day_counts) >= 7:
        return compute_trend_sliding_window(day_counts)
    return compute_trend_split(day_counts)


def build_intelligence():
    kb, known_entities = load_known_entities()
    briefs = []
    for path in sorted(BRIEFS_DIR.glob("*.md")):
        date_str = path.stem
        brief = parse_brief_markdown(read_text(path), fallback_date=date_str)
        if brief["headlines"]:
            briefs.append(brief)

    topic_map = {}
    date_order = [brief["date"] for brief in briefs if brief.get("date")]

    def ensure_topic(name, topic_type):
        key = (topic_type, normalize_topic_name(name))
        if not key[1]:
            return None
        if key not in topic_map:
            topic_map[key] = {
                "name": key[1],
                "type": topic_type,
                "dates": set(),
                "articles": [],
                "by_date": Counter(),
                "entities": Counter(),
            }
        return topic_map[key]

    for brief in briefs:
        date_str = brief.get("date")
        for headline in brief.get("headlines", []):
            article = {
                "date": date_str,
                "rank": headline["rank"],
                "title": headline["title"],
                "context": headline["context"],
                "category": headline.get("category") or None,
            }
            headline_text = f"{headline['title']} {headline['context']}"
            entity_hits = extract_entities_from_text(headline_text, known_entities)
            for topic_name in headline.get("topic_tags", []):
                topic = ensure_topic(topic_name, "category")
                if topic is None:
                    continue
                topic["dates"].add(date_str)
                topic["articles"].append(article)
                topic["by_date"][date_str] += 1
                for entity in entity_hits:
                    topic["entities"][entity["name"]] += 1
            for entity in entity_hits:
                topic = ensure_topic(entity["name"], "entity")
                if topic is None:
                    continue
                topic["dates"].add(date_str)
                topic["articles"].append(article)
                topic["by_date"][date_str] += 1

    topic_records = []
    for topic in topic_map.values():
        days_appeared = len(topic["dates"])
        article_count = len(topic["articles"])
        if not article_count:
            continue
        score = (days_appeared * 5) + article_count
        if topic["type"] == "entity":
            score = int(score * 0.5)
        ordered_articles = sorted(
            topic["articles"],
            key=lambda item: (item["date"], -item["rank"]),
            reverse=True,
        )
        day_counts = [topic["by_date"].get(day, 0) for day in date_order]
        trend, trend_counts = compute_trend(day_counts)
        topic_records.append(
            {
                "topic": topic["name"],
                "type": topic["type"],
                "score": score,
                "days_appeared": days_appeared,
                "article_count": article_count,
                "heat_level": topic_heat_label(days_appeared),
                "trend": trend,
                "trend_counts": trend_counts,
                "dates": sorted(topic["dates"]),
                "related_entities": [name for name, _ in topic["entities"].most_common(3)],
                "related_articles": ordered_articles[:4],
                "coverage_share": round((days_appeared / max(1, len(briefs))) * 100, 1),
            }
        )

    topic_records.sort(key=lambda item: (-item["score"], item["topic"].lower()))

    # Cross-topic connections: entity overlap and date overlap for top 12 topics
    top12 = topic_records[:12]
    topic_map_by_name = {r["topic"]: r for r in topic_records}
    for i, topic_a in enumerate(top12):
        connections = []
        for j, topic_b in enumerate(top12):
            if i >= j:
                continue
            shared_entities = sorted(
                set(topic_a.get("related_entities", []))
                & set(topic_b.get("related_entities", []))
            )
            shared_dates = sorted(
                set(topic_a.get("dates", []))
                & set(topic_b.get("dates", []))
            )
            if shared_entities or shared_dates:
                connections.append({
                    "topic": topic_b["topic"],
                    "shared_entities": shared_entities,
                    "shared_dates": shared_dates,
                })
        topic_a["connections"] = connections

    hot_topics = topic_records[:8]

    insights = []
    forward_looking_phrases = [
        "This trend is likely to persist in the coming sessions.",
        "Market participants should watch for continued developments.",
        "The trajectory suggests further attention in the near term.",
        "Analysts are closely monitoring follow-on effects.",
        "Ongoing developments could influence broader market sentiment.",
    ]
    import random
    random.seed(42)
    for topic in hot_topics[:3]:
        story_titles = "; ".join(article["title"] for article in topic["related_articles"][:2])
        entity_text = ""
        if topic.get("related_entities"):
            entity_text = f" Related entities: {', '.join(topic['related_entities'])}."
        connected_text = ""
        if topic.get("connections"):
            conn_names = [c["topic"] for c in topic["connections"][:3]]
            if conn_names:
                connected_text = f" Connected to: {', '.join(conn_names)}."
        forward_text = " " + random.choice(forward_looking_phrases)
        insights.append(
            {
                "topic": topic["topic"],
                "text": (
                    f"{topic['topic']} appeared in {topic['days_appeared']} of {max(1, len(briefs))} brief days "
                    f"({topic['coverage_share']}% of coverage) across {topic['article_count']} ranked articles. "
                    f"Trend is {topic['trend']}. Key stories: {story_titles}.{entity_text}{connected_text}{forward_text}"
                ),
            }
        )

    trends = []
    for topic in topic_records[:8]:
        trends.append(
            {
                "topic": topic["topic"],
                "direction": topic["trend"],
                "days_appeared": topic["days_appeared"],
                "article_count": topic["article_count"],
                "recent": topic["trend_counts"]["recent"],
                "earlier": topic["trend_counts"]["earlier"],
            }
        )

    stats = {
        "brief_days": len(briefs),
        "topics_analyzed": len(topic_records),
        "headlines_analyzed": sum(len(brief.get("headlines", [])) for brief in briefs),
        "known_entities": sum(
            len(group)
            for group in (kb.get("entities") or {}).values()
            if isinstance(group, dict)
        ),
        "date_range": {
            "start": date_order[0] if date_order else None,
            "end": date_order[-1] if date_order else None,
        },
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }

    # Topic of the day: highest-scoring topic per brief day
    topic_of_the_day = []
    for brief in briefs:
        date_str = brief.get("date")
        if not date_str:
            continue
        best_topic = None
        best_score = -1
        for topic in topic_records:
            if date_str in topic.get("dates", []):
                if topic["score"] > best_score:
                    best_score = topic["score"]
                    best_topic = topic["topic"]
        if best_topic:
            topic_of_the_day.append({
                "date": date_str,
                "topic": best_topic,
                "score": best_score,
            })

    # ---- WorkBuddy analysis for Intel tab ----
    wb_index = build_workbuddy_index()
    wb_reports = wb_index.get("reports", [])
    if wb_reports:
        wb_cards = []
        for r in wb_reports:
            report = read_workbuddy_report(r["path"])
            if report and report.get("html"):
                p_match = re.search(r"<p>(.*?)</p>", report["html"])
                summary_line = p_match.group(1)[:300] if p_match else ""
                wb_cards.append('\n'.join([
                    '<div class="topic-card" style="border-color:rgba(5,150,105,0.3)">',
                    '  <div class="topic-top">',
                    '    <div class="topic-main">',
                    f'      <div class="topic-name" style="font-size:15px"><span style="display:inline-flex;align-items:center;gap:8px"><span style="width:24px;height:24px;border-radius:6px;background:linear-gradient(135deg,#059669,#34d399);color:#fff;display:inline-flex;align-items:center;justify-content:center;font-weight:900;font-size:12px">W</span>{r["name"]}</span></div>',
                    f'      <div class="topic-meta">{r.get("date","") or "No date"} | {r["size"]/1024:.0f} KB | WorkBuddy/翠鸟 Deep-Dive</div>',
                    '    </div>',
                    '  </div>',
                    f'  <div style="margin-top:10px;color:var(--text-secondary);font-size:13px;line-height:1.6">{summary_line}&#8230;</div>',
                    '  <details style="margin-top:12px">',
                    '    <summary style="cursor:pointer;font-size:12px;font-weight:700;color:var(--accent)">View full analysis →</summary>',
                    f'    <div class="analysis-report-body" style="margin-top:12px;padding:14px;background:var(--surface-alt);border-radius:var(--radius);border:1px solid var(--border-light);max-height:600px;overflow-y:auto">{report["html"]}</div>',
                    '  </details>',
                    '</div>',
                ]))
        wb_html = '\n'.join([
            '<div class="section-header" style="margin-top:18px">',
            '  <div class="section-icon" style="background:rgba(5,150,105,0.12);color:#059669">\U0001f52c</div>',
            '  <div class="section-title" style="color:#059669">WorkBuddy Deep-Dive Analysis</div>',
            f'  <div class="section-count">{len(wb_reports)} report{"s" if len(wb_reports)>1 else ""}</div>',
            '</div>',
            f'<div class="topic-stack">{"".join(wb_cards)}</div>',
        ])
    else:
        wb_html = ""

    return {
        "hot_topics": hot_topics,
        "topic_of_the_day": topic_of_the_day,
        "trends": trends,
        "insights": insights,
        "stats": stats,
        "workbuddy_html": wb_html,
    }


def get_nl_color(newsletter_type):
    if not newsletter_type:
        return "#78716c"
    lowered = newsletter_type.lower()
    for key, color in NL_COLORS.items():
        if key.lower() in lowered:
            return color
    return "#78716c"


def build_kb_index():
    kb = {"dates": [], "newsletter_types": {}, "total_newsletters": 0, "total_links": 0}
    for date_str in get_available_dates():
        meta = load_meta(date_str) or {}
        index = load_index(date_str) or {}
        entry = {
            "date": date_str,
            "newsletter_count": meta.get("newsletter_count", len(index.get("newsletters", []))),
            "story_count": len((meta.get("newsletters") or []) or (index.get("newsletters") or [])),
        }
        kb["dates"].append(entry)
        kb["total_newsletters"] += entry["newsletter_count"]
        for newsletter in index.get("newsletters", []):
            newsletter_type = newsletter.get("newsletter_type", "Unknown")
            record = kb["newsletter_types"].setdefault(
                newsletter_type, {"count": 0, "dates": set()}
            )
            record["count"] += 1
            record["dates"].add(date_str)
            kb["total_links"] += newsletter.get("url_count", len(newsletter.get("urls", [])))
    for newsletter_type, record in kb["newsletter_types"].items():
        record["dates"] = sorted(record["dates"])
    return kb


def build_date_payload(date_str):
    brief_markdown = load_brief_markdown(date_str)
    brief_parsed = (
        parse_brief_markdown(brief_markdown, fallback_date=date_str) if brief_markdown else None
    )
    return {
        "date": date_str,
        "meta": load_meta(date_str),
        "index": load_index(date_str),
        "full_html": load_full_html(date_str),
        "brief_markdown": brief_markdown,
        "brief_parsed": brief_parsed,
    }


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Bloomberg Intelligence Portal</title>
<style>
__CSS_VARS__
__WB_STYLES__
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: var(--sans);
    background: linear-gradient(180deg, var(--bg) 0%, var(--bg-warm) 100%);
    color: var(--text);
    min-height: 100vh;
    font-size: 13px;
    line-height: 1.6;
  }}
  button, select {{ font: inherit; }}
  .header {{
    position: sticky; top: 0; z-index: 100;
    background: #1a1a1a; color: white; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  }}
  .header-inner {{
    max-width: 1180px; margin: 0 auto; min-height: 58px; padding: 10px 20px;
    display: flex; align-items: center; gap: 18px; flex-wrap: wrap;
  }}
  .brand {{ display: flex; align-items: center; gap: 10px; }}
  .brand-mark {{
    width: 28px; height: 28px; border-radius: 6px; background: var(--accent);
    color: white; display: flex; align-items: center; justify-content: center; font-weight: 700;
  }}
  .brand-text {{ font-size: 15px; font-weight: 600; }}
  .brand-text span {{ color: #9ca3af; font-weight: 400; }}
  .toolbar {{ display: flex; gap: 10px; align-items: center; margin-left: auto; flex-wrap: wrap; }}
  .date-nav {{ display: flex; align-items: center; gap: 6px; }}
  .nav-btn, .action-btn {{
    background: #374151; border: 1px solid #4b5563; color: #e5e7eb; cursor: pointer;
    border-radius: 8px; padding: 7px 12px; transition: 0.15s ease;
  }}
  .nav-btn:hover, .action-btn:hover {{ background: #4b5563; color: #fff; }}
  .date-btn {{ min-width: 132px; font-family: var(--mono); }}
  .view-tabs {{ display: flex; background: #111827; border-radius: 9px; padding: 3px; gap: 3px; }}
  .view-tabs button {{
    background: transparent; border: 0; color: #9ca3af; padding: 7px 12px; border-radius: 7px;
    text-transform: uppercase; letter-spacing: 0.5px; font-size: 11px; font-weight: 600; cursor: pointer;
  }}
  .view-tabs button.active {{ background: var(--accent); color: white; }}
  .page {{ max-width: 1180px; margin: 0 auto; padding: 28px 20px 40px; }}
  .section-header {{
    display: flex; align-items: center; gap: 10px; margin: 0 0 14px;
    padding-bottom: 8px; border-bottom: 2px solid var(--border);
  }}
  .section-icon {{
    width: 32px; height: 32px; border-radius: var(--radius); display: flex;
    align-items: center; justify-content: center; flex-shrink: 0;
  }}
  .section-title {{ font-size: 11px; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 1px; }}
  .section-count {{ margin-left: auto; color: var(--text-muted); font-family: var(--mono); font-size: 11px; }}
  .card {{
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm); padding: 18px; margin-bottom: 18px;
  }}
  .hero {{ display: grid; grid-template-columns: 1.2fr .8fr; gap: 18px; margin-bottom: 20px; }}
  .hero-title {{ font-size: 28px; line-height: 1.15; font-weight: 700; margin-bottom: 8px; max-width: 14ch; }}
  .hero-sub {{ color: var(--text-secondary); max-width: 58ch; }}
  .hero-meta {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 14px; }}
  .chip {{
    display: inline-flex; align-items: center; gap: 6px; border-radius: 999px; padding: 6px 10px;
    background: var(--surface-alt); border: 1px solid var(--border-light); color: var(--text-secondary);
    font-size: 11px; font-weight: 600;
  }}
  .market-strip {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(165px, 1fr)); gap: 10px; margin-bottom: 20px; }}
  .market-item {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 12px; box-shadow: var(--shadow-sm); }}
  .market-group {{ font-size: 10px; text-transform: uppercase; letter-spacing: 0.6px; color: var(--text-muted); margin-bottom: 4px; }}
  .market-label {{ font-size: 12px; color: var(--text-secondary); margin-bottom: 6px; }}
  .market-value {{ font-family: var(--mono); font-size: 17px; font-weight: 700; }}
  .market-change {{ font-family: var(--mono); font-size: 12px; margin-top: 4px; }}
  .up {{ color: var(--green); }}
  .down {{ color: var(--red); }}
  .neutral {{ color: var(--text-muted); }}
  .story-list {{ display: grid; gap: 12px; }}
  .story-card {{
    background: linear-gradient(180deg, white, var(--surface-alt)); border: 1px solid var(--border);
    border-radius: var(--radius-lg); padding: 16px; display: grid; grid-template-columns: 52px 1fr; gap: 14px;
  }}
  .story-rank {{
    width: 52px; height: 52px; border-radius: 14px; background: var(--accent-light); color: var(--accent);
    display: flex; align-items: center; justify-content: center; font-size: 22px; font-weight: 700; font-family: var(--mono);
    border: 1px solid var(--accent-border);
  }}
  .story-title {{ font-size: 17px; line-height: 1.3; font-weight: 700; margin-bottom: 6px; }}
  .story-context {{ color: var(--text-secondary); font-size: 13px; }}
  .story-tags {{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }}
  .tag {{
    display: inline-flex; align-items: center; border-radius: 999px; padding: 4px 9px; font-size: 10px;
    text-transform: uppercase; letter-spacing: 0.4px; font-weight: 700; background: var(--accent-light); color: var(--accent);
  }}
  .watch-grid {{ display: grid; gap: 10px; }}
  .watch-item {{ display: grid; grid-template-columns: 28px 1fr; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--border-light); }}
  .watch-item:last-child {{ border-bottom: 0; }}
  .watch-rank {{
    width: 28px; height: 28px; border-radius: 999px; background: var(--amber-bg); color: var(--amber);
    border: 1px solid rgba(217,119,6,0.22); display: flex; align-items: center; justify-content: center; font-weight: 700; font-family: var(--mono);
  }}
  .watch-title {{ font-weight: 700; margin-bottom: 2px; }}
  .watch-desc {{ color: var(--text-secondary); }}
  .quick-table {{ width: 100%; border-collapse: collapse; }}
  .quick-table th, .quick-table td {{ border-bottom: 1px solid var(--border-light); text-align: left; padding: 10px 8px; vertical-align: top; }}
  .quick-table th {{ font-size: 10px; text-transform: uppercase; letter-spacing: 0.6px; color: var(--text-muted); }}
  .quick-table td {{ font-size: 12px; }}
  .intel-actions {{ display: flex; align-items: center; gap: 10px; margin-left: auto; }}
  .stat-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 18px; }}
  .stat-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 18px; box-shadow: var(--shadow-sm); }}
  .stat-num {{ font-size: 28px; font-weight: 700; font-family: var(--mono); color: var(--accent); }}
  .stat-label {{ color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.7px; font-size: 10px; margin-top: 6px; }}
  .intel-grid {{ display: grid; grid-template-columns: 1.35fr .95fr; gap: 18px; align-items: start; }}
  .topic-stack, .trend-stack, .insight-stack {{ display: grid; gap: 14px; }}
  .topic-card {{ border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); padding: 16px; box-shadow: var(--shadow-sm); }}
  .topic-top {{ display: flex; gap: 12px; align-items: start; }}
  .topic-main {{ flex: 1; }}
  .topic-name {{ font-size: 18px; font-weight: 700; margin-bottom: 4px; }}
  .topic-meta {{ color: var(--text-secondary); font-size: 12px; }}
  .heat-badge {{ background: var(--red-bg); color: var(--red); border: 1px solid rgba(220,38,38,0.15); border-radius: 999px; padding: 5px 9px; font-size: 11px; font-weight: 700; white-space: nowrap; }}
  .topic-articles {{ margin-top: 12px; display: grid; gap: 8px; }}
  .topic-article {{ background: var(--surface-alt); border: 1px solid var(--border-light); border-radius: 10px; padding: 10px 12px; }}
  .topic-article-title {{ font-size: 13px; font-weight: 700; margin-bottom: 3px; }}
  .topic-article-meta {{ color: var(--text-muted); font-size: 11px; font-family: var(--mono); margin-bottom: 4px; }}
  .topic-article-context {{ color: var(--text-secondary); font-size: 12px; }}
  .trend-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 14px; }}
  .trend-head {{ display: flex; justify-content: space-between; gap: 10px; margin-bottom: 8px; }}
  .trend-name {{ font-weight: 700; }}
  .trend-dir {{ font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }}
  .trend-bar {{ height: 7px; border-radius: 999px; background: var(--border-light); overflow: hidden; margin: 8px 0; }}
  .trend-fill {{ height: 100%; background: var(--accent); border-radius: inherit; }}
  .insight-card {{ background: linear-gradient(180deg, var(--surface), #fff7f3); border: 1px solid var(--accent-border); border-radius: var(--radius-lg); padding: 15px; }}
  .insight-topic {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px; color: var(--accent); font-weight: 700; margin-bottom: 6px; }}
  .full-shell {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); overflow: hidden; }}
  .full-frame {{ padding: 20px; }}
  .full-frame h1, .full-frame h2 {{ color: var(--accent); margin: 24px 0 12px; }}
  .full-frame h3 {{ margin: 20px 0 10px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.6px; color: var(--text-secondary); border-bottom: 2px solid var(--border); padding-bottom: 6px; }}
  .full-frame p {{ margin: 10px 0; }}
  .full-frame ul, .full-frame ol {{ padding-left: 22px; margin: 10px 0; }}
  .full-frame table {{ width: 100%; border-collapse: collapse; margin: 12px 0; }}
  .full-frame th, .full-frame td {{ border: 1px solid var(--border); padding: 10px; text-align: left; }}
  .full-frame th {{ background: var(--surface-alt); font-size: 10px; text-transform: uppercase; letter-spacing: 0.6px; color: var(--text-secondary); }}
  .kb-tags {{ display: flex; flex-wrap: wrap; gap: 8px; }}
  .type-tag {{ display: inline-flex; align-items: center; gap: 6px; padding: 7px 11px; border-radius: 999px; background: var(--surface-alt); border: 1px solid var(--border-light); }}
  .type-dot {{ width: 10px; height: 10px; border-radius: 999px; }}
  .history-list {{ display: grid; gap: 10px; }}
  .history-row {{ display: flex; justify-content: space-between; gap: 14px; padding: 10px 0; border-bottom: 1px solid var(--border-light); }}
  .history-row:last-child {{ border-bottom: 0; }}
  .history-date {{ font-family: var(--mono); font-weight: 700; cursor: pointer; color: var(--text); }}
  .history-date:hover {{ color: var(--accent); }}
  .muted {{ color: var(--text-muted); }}
  .empty, .loading {{ padding: 36px 16px; text-align: center; color: var(--text-muted); }}
  @media (max-width: 960px) {{
    .hero, .intel-grid {{ grid-template-columns: 1fr; }}
    .toolbar {{ margin-left: 0; }}
  }}
  @media (max-width: 640px) {{
    .page {{ padding: 18px 14px 28px; }}
    .header-inner {{ padding: 10px 14px; }}
    .story-card {{ grid-template-columns: 1fr; }}
    .story-rank {{ width: 44px; height: 44px; }}
  }}
</style>
</head>
<body>
<div class="header">
  <div class="header-inner">
    <div class="brand">
      <div class="brand-mark">B</div>
      <div class="brand-text">Bloomberg <span>Intelligence Portal</span></div>
    </div>
    <div class="toolbar">
      <div class="date-nav">
        <button class="nav-btn" onclick="navDate(-1)">&larr;</button>
        <button class="nav-btn date-btn" id="dateDisplay" onclick="pickDate()">--</button>
        <button class="nav-btn" onclick="navDate(1)">&rarr;</button>
      </div>
      <div class="view-tabs">
        <button id="tabBrief" class="active" onclick="setView('brief')">Brief</button>
        <button id="tabFull" onclick="setView('full')">Full</button>
        <button id="tabIntel" onclick="setView('intel')">Intel</button>
        <button id="tabKb" onclick="setView('kb')">KB</button>
      </div>
    </div>
  </div>
</div>
<div class="page" id="content"><div class="loading">Loading portal...</div></div>
<script>
let availableDates = [];
let currentDate = null;
let currentView = 'brief';
const cache = Object.create(null);

function esc(value) {
  return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\\"/g, '&quot;');
}

function setActiveTab() {
  ['brief', 'full', 'intel', 'kb'].forEach(view => {
    document.getElementById('tab' + view.charAt(0).toUpperCase() + view.slice(1)).classList.toggle('active', currentView === view);
  });
}

async function init() {
  const res = await fetch('/api/dates');
  const data = await res.json();
  availableDates = data.dates || [];
  currentDate = availableDates[0] || null;
  render();
}

async function getDateData(dateStr) {
  if (!cache[dateStr]) {
    const res = await fetch('/api/date/' + dateStr);
    if (!res.ok) throw new Error('Date not found');
    cache[dateStr] = await res.json();
  }
  return cache[dateStr];
}

async function render() {
  setActiveTab();
  document.getElementById('dateDisplay').textContent = currentDate || 'No dates';
  if (!currentDate && currentView !== 'kb' && currentView !== 'intel') {
    document.getElementById('content').innerHTML = '<div class="empty">No digest dates found.</div>';
    return;
  }
  if (currentView === 'brief') return renderBrief();
  if (currentView === 'full') return renderFull();
  if (currentView === 'intel') return renderIntel();
  return renderKB();
}

function setView(view) {
  currentView = view;
  render();
}

function navDate(delta) {
  if (!availableDates.length || !currentDate) return;
  const idx = availableDates.indexOf(currentDate);
  if (idx === -1) return;
  const next = Math.max(0, Math.min(availableDates.length - 1, idx + delta));
  if (next !== idx) {
    currentDate = availableDates[next];
    render();
  }
}

function pickDate() {
  const entered = prompt('Enter date (YYYY-MM-DD):', currentDate || '');
  if (entered && /^\d{4}-\d{2}-\d{2}$/.test(entered)) {
    currentDate = entered;
    render();
  }
}

function formatTopicTags(tags) {
  return (tags || []).map(tag => `<span class="tag">${esc(tag)}</span>`).join('');
}

async function renderBrief() {
  document.getElementById('content').innerHTML = '<div class="loading">Loading brief...</div>';
  let data;
  try {
    data = await getDateData(currentDate);
  } catch (err) {
    document.getElementById('content').innerHTML = '<div class="empty">Digest not available for this date.</div>';
    return;
  }
  const brief = data.brief_parsed || { headlines: [], market_data: [], watch_items: [], quick_scan: [] };
  const headlines = brief.headlines || [];
  const market = brief.market_data || [];
  const watch = brief.watch_items || [];
  const quick = brief.quick_scan || [];
  const storyHtml = headlines.length ? headlines.map(item => `
    <div class="story-card">
      <div class="story-rank">${item.rank}</div>
      <div>
        <div class="story-title">${esc(item.title)}</div>
        <div class="story-context">${esc(item.context)}</div>
        <div class="story-tags">${formatTopicTags(item.topic_tags && item.topic_tags.length ? item.topic_tags : [item.category].filter(Boolean))}</div>
      </div>
    </div>`).join('') : '<div class="empty">Brief headlines unavailable.</div>';
  const marketHtml = market.length ? market.map(item => `
    <div class="market-item">
      <div class="market-group">${esc(item.group || 'Market')}</div>
      <div class="market-label">${esc(item.label)}</div>
      <div class="market-value">${esc(item.value)}</div>
      <div class="market-change ${item.change_class}">${esc(item.change || item.notes || 'No change data')}</div>
    </div>`).join('') : '<div class="card"><div class="muted">No market data parsed for this date.</div></div>';
  const watchHtml = watch.length ? watch.map(item => `
    <div class="watch-item">
      <div class="watch-rank">${item.rank}</div>
      <div>
        <div class="watch-title">${esc(item.title)}</div>
        <div class="watch-desc">${esc(item.description)}</div>
      </div>
    </div>`).join('') : '<div class="empty">No watch items parsed.</div>';
  const quickHtml = quick.length ? `
    <div class="card">
      <table class="quick-table">
        <thead><tr><th>Time</th><th>Subject</th><th>Takeaway</th></tr></thead>
        <tbody>${quick.map(row => `<tr><td>${esc(row.time)}</td><td>${esc(row.subject)}</td><td>${esc(row.takeaway)}</td></tr>`).join('')}</tbody>
      </table>
    </div>` : '';
  const bottomLine = brief.bottom_line ? `<div class="card"><div class="section-header"><div class="section-icon" style="background:var(--purple-bg);color:var(--purple)">◎</div><div class="section-title">Bottom Line</div></div><div>${esc(brief.bottom_line)}</div></div>` : '';
  document.getElementById('content').innerHTML = `
    <div class="hero">
      <div class="card">
        <div class="hero-title">Ranked market brief for ${esc(currentDate)}</div>
        <div class="hero-sub">Server-side markdown parsing now drives this view. Stories stay in market-impact order, market data is structured, and the watchlist is preserved as data instead of scraped HTML.</div>
        <div class="hero-meta">
          <span class="chip">${headlines.length} ranked stories</span>
          <span class="chip">${market.length} market datapoints</span>
          <span class="chip">${watch.length} watch items</span>
        </div>
      </div>
      <div class="card">
        <div class="section-header"><div class="section-icon" style="background:var(--blue-bg);color:var(--blue)">📎</div><div class="section-title">Available Sources</div></div>
        <div class="muted">Markdown brief: ${data.brief_markdown ? 'yes' : 'no'}<br/>Full digest HTML: ${data.full_html ? 'yes' : 'no'}<br/>Newsletter index: ${data.index ? 'yes' : 'no'}</div>
      </div>
    </div>
    <div class="section-header"><div class="section-icon" style="background:var(--green-bg);color:var(--green)">📊</div><div class="section-title">Market Data</div><div class="section-count">${market.length} items</div></div>
    <div class="market-strip">${marketHtml}</div>
    <div class="section-header"><div class="section-icon" style="background:var(--red-bg);color:var(--red)">🔥</div><div class="section-title">Top Headlines</div><div class="section-count">${headlines.length} ranked</div></div>
    <div class="story-list">${storyHtml}</div>
    <div class="section-header" style="margin-top:22px"><div class="section-icon" style="background:var(--amber-bg);color:var(--amber)">💡</div><div class="section-title">What To Watch</div><div class="section-count">${watch.length} items</div></div>
    <div class="card"><div class="watch-grid">${watchHtml}</div></div>
    ${quickHtml}
    ${bottomLine}
  `;
}

async function renderFull() {
  document.getElementById('content').innerHTML = '<div class="loading">Loading full digest...</div>';
  let data;
  try {
    data = await getDateData(currentDate);
  } catch (err) {
    document.getElementById('content').innerHTML = '<div class="empty">Digest not available for this date.</div>';
    return;
  }
  const html = data.full_html || '<p class="muted">Full HTML digest not available for this date.</p>';
  document.getElementById('content').innerHTML = `<div class="full-shell"><div class="full-frame">${html}</div></div>`;
}

async function renderIntel(forceRefresh = false) {
  document.getElementById('content').innerHTML = '<div class="loading">Building cross-day intelligence...</div>';
  const url = forceRefresh ? '/api/intel?refresh=1' : '/api/intel';
  const res = await fetch(url);
  const data = await res.json();
  const hotTopics = data.hot_topics || [];
  const insights = data.insights || [];
  const trends = data.trends || [];
  const stats = data.stats || {};
  const topicHtml = hotTopics.length ? hotTopics.map(topic => {
    const articleHtml = (topic.related_articles || []).map(article => `
      <div class="topic-article">
        <div class="topic-article-title">${esc(article.title)}</div>
        <div class="topic-article-meta">${esc(article.date)} · rank ${article.rank}${article.category ? ' · ' + esc(article.category) : ''}</div>
        <div class="topic-article-context">${esc(article.context)}</div>
      </div>`).join('');
    return `
      <div class="topic-card">
        <div class="topic-top">
          <div class="topic-main">
            <div class="topic-name">${esc(topic.topic)}</div>
            <div class="topic-meta">${topic.days_appeared} days · ${topic.article_count} related articles · ${topic.type}</div>
          </div>
          <div class="heat-badge">${esc(topic.heat_level)} heat</div>
        </div>
        <div class="story-tags" style="margin-top:10px">
          <span class="tag">${esc(topic.trend)}</span>
          ${(topic.related_entities || []).map(name => `<span class="tag">${esc(name)}</span>`).join('')}
        </div>
        <div class="topic-articles">${articleHtml}</div>
      </div>`;
  }).join('') : '<div class="card"><div class="muted">Not enough brief history yet to surface hot topics.</div></div>';
  const insightHtml = insights.length ? insights.map(item => `<div class="insight-card"><div class="insight-topic">${esc(item.topic)}</div><div>${esc(item.text)}</div></div>`).join('') : '<div class="card"><div class="muted">Insights will appear once more brief history is available.</div></div>';
  const maxTrendArticles = Math.max(1, ...trends.map(item => item.article_count || 0));
  const trendHtml = trends.length ? trends.map(item => `
    <div class="trend-card">
      <div class="trend-head">
        <div class="trend-name">${esc(item.topic)}</div>
        <div class="trend-dir ${item.direction === 'rising' ? 'up' : item.direction === 'falling' ? 'down' : 'neutral'}">${esc(item.direction)}</div>
      </div>
      <div class="muted">${item.days_appeared} days · recent ${item.recent} vs earlier ${item.earlier}</div>
      <div class="trend-bar"><div class="trend-fill" style="width:${Math.round(((item.article_count || 0) / maxTrendArticles) * 100)}%"></div></div>
      <div class="muted">${item.article_count} related ranked articles</div>
    </div>`).join('') : '<div class="card"><div class="muted">Trend indicators unavailable.</div></div>';
  const wbHtml = data.workbuddy_html || '';
  document.getElementById('content').innerHTML = `
    <div class="section-header">
      <div class="section-icon" style="background:var(--blue-bg);color:var(--blue)">🧠</div>
      <div class="section-title">Cross-Day Intelligence</div>
      <div class="intel-actions">
        <button class="action-btn" onclick="renderIntel(true)">Refresh</button>
        <div class="section-count">${esc(stats.generated_at || '')}</div>
      </div>
    </div>
    <div class="stat-grid">
      <div class="stat-card"><div class="stat-num">${stats.brief_days || 0}</div><div class="stat-label">Brief Days</div></div>
      <div class="stat-card"><div class="stat-num">${stats.headlines_analyzed || 0}</div><div class="stat-label">Headlines Analyzed</div></div>
      <div class="stat-card"><div class="stat-num">${stats.topics_analyzed || 0}</div><div class="stat-label">Tracked Topics</div></div>
      <div class="stat-card"><div class="stat-num">${stats.known_entities || 0}</div><div class="stat-label">Known Entities</div></div>
    </div>
    ${wbHtml}
    <div class="intel-grid">
      <div>
        <div class="section-header"><div class="section-icon" style="background:var(--red-bg);color:var(--red)">♨</div><div class="section-title">Hot Topics</div><div class="section-count">${hotTopics.length} surfaced</div></div>
        <div class="topic-stack">${topicHtml}</div>
      </div>
      <div>
        <div class="section-header"><div class="section-icon" style="background:var(--purple-bg);color:var(--purple)">◎</div><div class="section-title">Insights</div></div>
        <div class="insight-stack">${insightHtml}</div>
        <div class="section-header" style="margin-top:20px"><div class="section-icon" style="background:var(--green-bg);color:var(--green)">↕</div><div class="section-title">Trends</div></div>
        <div class="trend-stack">${trendHtml}</div>
      </div>
    </div>
  `;
}

async function renderKB() {
  document.getElementById('content').innerHTML = '<div class="loading">Loading knowledge base stats...</div>';
  const res = await fetch('/api/kb');
  const data = await res.json();
  const types = Object.entries(data.newsletter_types || {}).sort((a, b) => b[1].count - a[1].count);
  const typeHtml = types.length ? types.map(([name, info]) => `
    <span class="type-tag"><span class="type-dot" style="background:${getColor(name)}"></span>${esc(name)} <span class="muted">(${info.count})</span></span>`).join('') : '<div class="muted">No newsletter type history yet.</div>';
  const historyHtml = (data.dates || []).length ? data.dates.map(item => `
    <div class="history-row"><div class="history-date" onclick="goDate('${item.date}')">${esc(item.date)}</div><div class="muted">${item.newsletter_count} newsletters · ${item.story_count} stories</div></div>`).join('') : '<div class="muted">No date history.</div>';
  document.getElementById('content').innerHTML = `
    <div class="section-header"><div class="section-icon" style="background:var(--purple-bg);color:var(--purple)">📚</div><div class="section-title">Knowledge Base</div></div>
    <div class="stat-grid">
      <div class="stat-card"><div class="stat-num">${data.total_dates || 0}</div><div class="stat-label">Days</div></div>
      <div class="stat-card"><div class="stat-num">${data.total_newsletters || 0}</div><div class="stat-label">Newsletters</div></div>
      <div class="stat-card"><div class="stat-num">${data.total_links || 0}</div><div class="stat-label">Links</div></div>
      <div class="stat-card"><div class="stat-num">${types.length}</div><div class="stat-label">Types</div></div>
    </div>
    <div class="card"><div class="section-header"><div class="section-title">Newsletter Types</div></div><div class="kb-tags">${typeHtml}</div></div>
    <div class="card"><div class="section-header"><div class="section-title">Daily History</div></div><div class="history-list">${historyHtml}</div></div>
  `;
}

// ---- WorkBuddy Integrated into Intel ----
// renderIntel() gets workbuddy data from the API and displays it inline

function goDate(dateStr) {
  currentDate = dateStr;
  currentView = 'brief';
  render();
}

function getColor(type) {
  const mapping = {
    'Morning Briefing': '#2563eb', 'Markets Daily': '#059669', 'Technology': '#7c3aed', 'Politics': '#dc2626',
    'Crypto': '#d97706', 'Geopolitics': '#e11d48', 'Macro': '#0891b2', 'Asia Markets': '#db2777', 'Weekend': '#78716c'
  };
  const lowered = String(type || '').toLowerCase();
  for (const [key, color] of Object.entries(mapping)) {
    if (lowered.includes(key.toLowerCase())) return color;
  }
  return '#78716c';
}

init();
</script>
</body>
</html>
"""
# ---- WorkBuddy Analysis Integration ----

MARKDOWN_RENDERER_STYLE = """
.analysis-shell { max-width: 860px; margin: 0 auto; }
.analysis-header { display: flex; align-items: center; gap: 14px; padding: 18px 22px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); margin-bottom: 18px; }
.analysis-logo { width: 40px; height: 40px; border-radius: 10px; background: linear-gradient(135deg, #059669, #34d399); display: flex; align-items: center; justify-content: center; color: white; font-weight: 900; font-size: 18px; }
.analysis-title { font-weight: 700; font-size: 16px; }
.analysis-meta { color: var(--text-muted); font-size: 12px; margin-top: 2px; }
.analysis-list { display: grid; gap: 10px; }
.analysis-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 16px 20px; cursor: pointer; display: flex; gap: 14px; align-items: center; box-shadow: var(--shadow-sm); transition: border-color .15s; }
.analysis-card:hover { border-color: var(--accent); }
.analysis-card-icon { width: 36px; height: 36px; border-radius: 8px; background: var(--accent-light); color: var(--accent); display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 14px; flex-shrink: 0; }
.analysis-card-title { font-weight: 700; font-size: 14px; }
.analysis-card-date { color: var(--text-muted); font-size: 11px; font-family: var(--mono); margin-top: 2px; }
.analysis-report { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); overflow: hidden; }
.analysis-report-header { padding: 18px 22px; border-bottom: 1px solid var(--border-light); display: flex; align-items: center; gap: 14px; }
.analysis-report-body { padding: 22px; line-height: 1.6; font-size: 14px; color: var(--text); }
.analysis-report-body h1 { font-size: 22px; margin: 0 0 16px; color: var(--text); }
.analysis-report-body h2 { font-size: 17px; margin: 28px 0 12px; color: var(--accent); border-bottom: 2px solid var(--border-light); padding-bottom: 6px; }
.analysis-report-body h3 { font-size: 14px; margin: 22px 0 10px; text-transform: uppercase; letter-spacing: 0.4px; color: var(--text-secondary); }
.analysis-report-body p { margin: 10px 0; }
.analysis-report-body table { width: 100%; border-collapse: collapse; margin: 14px 0; font-size: 13px; }
.analysis-report-body th, .analysis-report-body td { border: 1px solid var(--border); padding: 8px 10px; text-align: left; }
.analysis-report-body th { background: var(--surface-alt); font-weight: 700; font-size: 11px; text-transform: uppercase; letter-spacing: 0.4px; color: var(--text-secondary); }
.analysis-report-body ul, .analysis-report-body ol { padding-left: 22px; margin: 10px 0; }
.analysis-report-body li { margin: 4px 0; }
.analysis-report-body strong { color: var(--text); }
.analysis-report-body hr { border: none; border-top: 1px solid var(--border-light); margin: 22px 0; }
.analysis-report-body blockquote { border-left: 3px solid var(--accent); padding-left: 14px; margin: 14px 0; color: var(--text-secondary); }
.analysis-back { display: inline-flex; align-items: center; gap: 6px; color: var(--accent); cursor: pointer; font-weight: 700; font-size: 13px; margin-bottom: 14px; }
.analysis-back:hover { text-decoration: underline; }
"""


def esc(value):
    if value is None:
        return ""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_workbuddy_index():
    if not WORKBUDDY_DIR.exists():
        return {"reports": []}
    reports = []
    for path in sorted(WORKBUDDY_DIR.glob("*_result.md"), reverse=True):
        stem = path.stem
        # Extract readable name from filename
        name = stem.replace("_result", "").replace("hermes_", "")
        # Try to extract date
        date_match = re.search(r"(\d{8})", name)
        date_str = ""
        if date_match:
            raw = date_match.group(1)
            date_str = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        # Clean up name
        display_name = re.sub(r"^\d{8}_\d{6}_?", "", name)
        display_name = display_name.replace("_", " ").replace("  ", " ").strip()
        display_name = display_name[:1].upper() + display_name[1:] if display_name else "Untitled"
        reports.append({
            "id": stem,
            "name": display_name,
            "date": date_str,
            "size": path.stat().st_size,
            "path": path.name,
        })
    return {"reports": reports}


def read_workbuddy_report(report_path):
    path = WORKBUDDY_DIR / report_path
    if not path.exists():
        return None
    content = read_text(path)
    if not content:
        return None
    # Convert markdown to safe HTML (basic conversion)
    html = markdown_to_html(content)
    return {"content": content, "html": html, "path": report_path, "size": path.stat().st_size}


def markdown_to_html(text):
    """Basic markdown → HTML for WorkBuddy reports"""
    lines = text.split("\n")
    html_parts = []
    in_table = False
    in_list = False
    list_type = None
    in_blockquote = False

    for line in lines:
        stripped = line.rstrip()

        # HR
        if re.match(r"^---+\s*$", stripped) and len(stripped) >= 3:
            html_parts.append("<hr>")
            continue

        # Headings
        h_match = re.match(r"^(#{1,3})\s+(.+?)(?:\s*\{[^}]*\})?\s*$", stripped)
        if h_match:
            level = len(h_match.group(1))
            text = h_match.group(2).replace("**", "").replace("*", "")
            html_parts.append(f"<h{level}>{text}</h{level}>")
            continue

        # Blockquote
        bq_match = re.match(r"^>\s*(.*)", stripped)
        if bq_match:
            html_parts.append(f"<blockquote><p>{bq_match.group(1)}</p></blockquote>")
            continue

        # Tables
        if stripped.startswith("|") and stripped.endswith("|"):
            if not in_table:
                in_table = True
                html_parts.append("<table>")
            parts = [p.strip() for p in stripped.strip("|").split("|")]
            # Header separator
            if re.match(r"^[:\- ]+$", parts[0]) if parts else False:
                continue
            if any("---" in p for p in parts):
                continue
            html_parts.append("<tr><td>" + "</td><td>".join(esc(p) for p in parts) + "</td></tr>")
            continue
        elif in_table:
            html_parts.append("</table>")
            in_table = False

        # List items
        li_match = re.match(r"^(\s*)[-*+]\s+(.*)", stripped)
        if li_match:
            indent = len(li_match.group(1))
            text = li_match.group(2)
            if not in_list:
                in_list = True
                list_type = "ul"
                html_parts.append(f"<{list_type}>")
            html_parts.append(f"<li>{inline_markdown(text)}</li>")
            continue
        elif in_list:
            html_parts.append(f"</{list_type}>")
            in_list = False

        # Numbered list
        nl_match = re.match(r"^(\s*)(\d+)\.\s+(.*)", stripped)
        if nl_match:
            text = nl_match.group(3)
            if not in_list:
                in_list = True
                list_type = "ol"
                html_parts.append(f"<{list_type}>")
            html_parts.append(f"<li>{inline_markdown(text)}</li>")
            continue
        elif in_list:
            html_parts.append(f"</{list_type}>")
            in_list = False

        # Paragraph (non-empty lines)
        if stripped:
            html_parts.append(f"<p>{inline_markdown(stripped)}</p>")
        else:
            html_parts.append("<p><br></p>")

    # Close any open tags
    if in_table:
        html_parts.append("</table>")
    if in_list and list_type:
        html_parts.append(f"</{list_type}>")

    return "\n".join(html_parts)


def inline_markdown(text):
    """Convert inline markdown: **bold**, *italic*, `code`, [link](url)"""
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


HTML_PAGE = HTML_PAGE.replace("__CSS_VARS__", CSS_VARS).replace("{{", "{").replace("}}", "}")
HTML_PAGE = HTML_PAGE.replace("__WB_STYLES__", MARKDOWN_RENDERER_STYLE)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/":
                self.respond_html(HTML_PAGE)
            elif path == "/api/dates":
                self.respond_json({"dates": get_available_dates()})
            elif path.startswith("/api/date/"):
                date_str = path.rsplit("/", 1)[-1]
                payload = build_date_payload(date_str)
                if not any(
                    payload[key]
                    for key in ("meta", "index", "full_html", "brief_markdown", "brief_parsed")
                ):
                    self.send_error(404, "Not found")
                    return
                self.respond_json(payload)
            elif path == "/api/intel":
                self.respond_json(build_intelligence())
            elif path == "/api/kb":
                kb = build_kb_index()
                self.respond_json(
                    {
                        "dates": kb["dates"],
                        "total_dates": len(kb["dates"]),
                        "total_newsletters": kb["total_newsletters"],
                        "total_links": kb["total_links"],
                        "newsletter_types": kb["newsletter_types"],
                    }
                )
            elif path == "/api/workbuddy":
                self.respond_json(build_workbuddy_index())
            elif path.startswith("/api/workbuddy/"):
                report_path = path.rsplit("/", 1)[-1]
                report = read_workbuddy_report(report_path)
                if report is None:
                    self.send_error(404, "Report not found")
                    return
                self.respond_json(report)
            else:
                self.send_error(404, "Not found")
        except Exception as exc:
            self.send_error(500, str(exc))

    def respond_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_json(self, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return


if __name__ == "__main__":
    print(f"Bloomberg Intelligence Portal v4 running on http://0.0.0.0:{PORT}")
    print(f"Data directory: {DATA_DIR}")
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
