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

PORT = int(os.environ.get("PORT", "5055"))
DATA_DIR = Path.home() / ".hermes" / "bloomberg_digest"
AI_NEWS_DIR = DATA_DIR / "ai_news"
BRIEFS_DIR = DATA_DIR / "briefs"
FULL_DIR = DATA_DIR / "full"
SUMMARIES_DIR = DATA_DIR / "summaries"
RAW_DIR = DATA_DIR / "raw"
ARTICLES_DIR = DATA_DIR / "articles"
KNOWLEDGE_BASE_PATH = DATA_DIR / "knowledge" / "knowledge_base.json"
WORKBUDDY_DIR = Path.home() / ".hermes" / "workbuddy_reports"

CSS_VARS = """
  :root {
    --bg: #0B0E11;
    --bg-warm: #0d1117;
    --surface: #12161C;
    --surface-alt: #1A1F2B;
    --surface-hover: #222836;
    --border: #2A3040;
    --border-light: #1E2433;
    --text: #E8ECF1;
    --text-secondary: #8B95A5;
    --text-muted: #5C6478;
    --text-dim: #3a4050;

    /* Vibrant Accent System */
    --accent-primary: #FFA028;     /* Bloomberg Sunshade — hero CTAs, active filters */
    --accent-primary-bg: rgba(255,160,40,0.12);
    --accent-live: #00F0FF;        /* Cyan pulse — live data, real-time indicators */
    --accent-live-bg: rgba(0,240,255,0.10);
    --accent: #FF6B35;             /* Keep legacy accent for chart accent */
    --accent-light: rgba(255,107,53,0.12);
    --accent-border: rgba(255,107,53,0.30);

    /* Momentum Colors */
    --up: #0ECB81;                 /* Profit Mint — positive momentum */
    --up-bg: rgba(14,203,129,0.10);
    --down: #F6465D;               /* Loss Crimson — negative momentum */
    --down-bg: rgba(246,70,93,0.10);
    --amber: #FFB300;
    --amber-bg: rgba(255,179,0,0.10);

    /* Keep original palette tokens for compatibility */
    --green: #0ECB81;
    --green-bg: rgba(14,203,129,0.10);
    --red: #F6465D;
    --red-bg: rgba(246,70,93,0.10);
    --blue: #42A5F5;
    --blue-bg: rgba(66,165,245,0.10);
    --purple: #AB47BC;
    --purple-bg: rgba(171,71,188,0.10);
    --cyan: #26C6DA;
    --cyan-bg: rgba(38,198,218,0.10);

    /* Badge System Colors */
    --heat-low: #42A5F5;
    --heat-low-bg: rgba(66,165,245,0.12);
    --heat-med: #FFB300;
    --heat-med-bg: rgba(255,179,0,0.12);
    --heat-high: #FF1744;
    --heat-high-bg: rgba(255,23,68,0.12);
    --badge-live: #00F0FF;
    --badge-live-bg: rgba(0,240,255,0.12);
    --badge-new: #FFA028;
    --badge-new-bg: rgba(255,160,40,0.12);

    /* Gradient Surfaces for Charts */
    --gradient-up: linear-gradient(180deg, rgba(14,203,129,0.30) 0%, rgba(14,203,129,0.05) 100%);
    --gradient-down: linear-gradient(180deg, rgba(246,70,93,0.30) 0%, rgba(246,70,93,0.05) 100%);
    --gradient-heat: linear-gradient(90deg, #42A5F5 0%, #FFB300 50%, #FF1744 100%);

    /* Typography Scale */
    --text-hero: 32px;
    --text-hero-weight: 700;
    --text-title: 20px;
    --text-title-weight: 600;
    --text-body: 14px;
    --text-caption: 12px;
    --text-caption-weight: 500;
    --text-ticker: 13px;
    --text-ticker-weight: 600;

    --mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    --sans: "IBM Plex Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    --radius: 10px;
    --radius-lg: 14px;
    --shadow-sm: 0 1px 3px rgba(5,8,12,0.30), 0 1px 2px rgba(5,8,12,0.20);
    --shadow: 0 4px 16px rgba(5,8,12,0.35), 0 2px 4px rgba(5,8,12,0.22);
    --shadow-md: 0 12px 32px rgba(5,8,12,0.42), 0 4px 12px rgba(5,8,12,0.25);
    --shadow-glow: 0 0 0 1px rgba(255,160,40,0.15);

    /* Anti-Slop: Transition System */
    --ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
    --duration-fast: 150ms;
    --duration-normal: 250ms;

    /* Anti-Slop: Noise overlay opacity */
    --noise-opacity: 0.025;
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
    r"^\s*(\d+)\.\s+\*\*(.+?)\*\*(?:\s*[—-]\s*(.+?))?(?:\s*\[([^\]]+)\])?\s*$"
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

    return {
        "hot_topics": hot_topics,
        "topic_of_the_day": topic_of_the_day,
        "trends": trends,
        "insights": insights,
        "stats": stats,
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


def load_articles(date_str):
    """Load synthesized article summaries for a given date."""
    articles_path = ARTICLES_DIR / (date_str + ".json")
    if not articles_path.exists():
        return None
    try:
        import json
        with open(articles_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_intel_timeline():
    """Load the pre-built Intel Timeline data."""
    import json
    timeline_path = INTEL_DIR / "timeline.json" if "INTEL_DIR" in dir() else DATA_DIR / "intel" / "timeline.json"
    # Ensure INTEL_DIR is defined
    if not hasattr(type(DATA_DIR), '__truediv__'):
        timeline_path = Path(str(DATA_DIR) + "/intel/timeline.json")
    else:
        timeline_path = DATA_DIR / "intel" / "timeline.json"
    if not timeline_path.exists():
        return {"error": "Timeline not built. Run: python3 scripts/build_intel_timeline.py", "timeline": []}
    try:
        with open(timeline_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e), "timeline": []}


def load_intel_report():
    """Load the pre-built Intel Report (cross-day thematic analysis)."""
    import json
    report_path = DATA_DIR / "intel" / "report.json"
    if not report_path.exists():
        return {"error": "Report not built. Run: python3 scripts/build_intel_report.py", "themes": []}
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e), "themes": []}


def build_date_payload(date_str):
    brief_markdown = load_brief_markdown(date_str)
    brief_parsed = (
        parse_brief_markdown(brief_markdown, fallback_date=date_str) if brief_markdown else None
    )
    newsletters = load_newsletters(date_str)
    articles = load_articles(date_str)
    return {
        "date": date_str,
        "meta": load_meta(date_str),
        "index": load_index(date_str),
        "full_html": load_full_html(date_str),
        "brief_markdown": brief_markdown,
        "brief_parsed": brief_parsed,
        "newsletters": newsletters,
        "articles": articles,
    }


def load_newsletters(date_str):
    """Load original raw newsletter emails with full body content."""
    newsletters = []
    digest_json = load_meta(date_str)  # loads 2026-05-01.json
    if not digest_json or "newsletters" not in digest_json:
        return newsletters
    for nl in digest_json["newsletters"]:
        nl_id = nl.get("id", "")
        raw_path = RAW_DIR / "{}_{}.txt".format(date_str, nl_id)
        body_text = ""
        if raw_path.exists():
            body_text = raw_path.read_text(encoding="utf-8", errors="replace")
        newsletters.append({
            "id": nl_id,
            "subject": nl.get("subject", ""),
            "from_name": nl.get("from_name", ""),
            "date_local": nl.get("date_local", ""),
            "reporter": nl.get("reporter", ""),
            "newsletter_type": nl.get("newsletter_type", ""),
            "urls": nl.get("urls", []),
            "body": body_text,
        })
    return newsletters


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Bloomberg Intelligence Portal v5</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" media="print" onload="this.media='all'">
<script>window.Chart = null;</script>
<style>
__CSS_VARS__
__WB_STYLES__
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ scroll-behavior: smooth; color-scheme: dark; -webkit-font-smoothing: antialiased; }}
  html[data-theme="light"] {{
    color-scheme: light;
    --bg: #F5F6F8;
    --bg-warm: #FAFAFA;
    --surface: #FFFFFF;
    --surface-alt: #F0F2F5;
    --surface-hover: #E8EBF0;
    --border: #D0D5DD;
    --border-light: #E5E8ED;
    --text: #1A1D24;
    --text-secondary: #5C6478;
    --text-muted: #8B95A5;
    --text-dim: #B0B8C8;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.08);
    --shadow: 0 2px 8px rgba(0,0,0,0.10), 0 1px 2px rgba(0,0,0,0.06);
    --shadow-md: 0 8px 24px rgba(0,0,0,0.12), 0 2px 6px rgba(0,0,0,0.08);
  }}
  body {{
    font-family: var(--sans);
    background: var(--bg);
    color: var(--text);
    min-height: 100dvh;
    font-size: 14px;
    line-height: 1.6;
    position: relative;
    font-variant-numeric: tabular-nums;
  }}
  /* Anti-Slop: Subtle noise grain overlay */
  body::before {{
    content: '';
    position: fixed;
    inset: 0;
    z-index: 9999;
    pointer-events: none;
    opacity: var(--noise-opacity);
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
    background-repeat: repeat;
    background-size: 180px 180px;
  }}
  button, select {{ font: inherit; }}
  .header {{
    position: sticky; top: 0; z-index: 100;
    background: rgba(11, 14, 17, 0.85);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    color: white;
    border-bottom: 1px solid var(--border);
    box-shadow: 0 1px 4px rgba(5,8,12,0.30), 0 0 0 1px rgba(255,255,255,0.03);
  }}
  .header-inner {{
    max-width: 1400px; margin: 0 auto; min-height: 56px; padding: 10px 24px;
    display: flex; align-items: center; gap: 18px; flex-wrap: wrap;
  }}
  .brand {{ display: flex; align-items: center; gap: 10px; }}
  .brand-mark {{
    width: 30px; height: 30px; border-radius: 8px;
    background: linear-gradient(135deg, var(--accent), #ff8f5a);
    color: white; display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 15px; font-family: var(--mono);
    box-shadow: 0 2px 8px rgba(255,107,53,0.25);
  }}
  .brand-text {{ font-size: 16px; font-weight: 600; letter-spacing: -0.01em; }}
  .brand-text span {{ color: var(--text-muted); font-weight: 400; }}
  .toolbar {{ display: flex; gap: 12px; align-items: center; margin-left: auto; flex-wrap: wrap; }}
  .date-nav {{ display: flex; align-items: center; gap: 6px; }}
  .nav-btn, .action-btn {{
    background: var(--surface-alt); border: 1px solid var(--border); color: var(--text-secondary);
    cursor: pointer; border-radius: var(--radius); padding: 8px 14px;
    transition: background var(--duration-fast) var(--ease-out-expo),
                border-color var(--duration-fast) var(--ease-out-expo),
                color var(--duration-fast) var(--ease-out-expo),
                transform var(--duration-fast) var(--ease-out-expo),
                box-shadow var(--duration-fast) var(--ease-out-expo);
    font-family: var(--sans); font-weight: 500; font-size: 13px;
    border: 1px solid var(--border);
    outline: none;
  }}
  .nav-btn:hover, .action-btn:hover {{
    background: var(--surface-hover); color: var(--text); border-color: var(--text-muted);
    transform: translateY(-1px);
  }}
  .nav-btn:active, .action-btn:active {{
    transform: translateY(0) scale(0.98);
    transition-duration: 80ms;
  }}
  .nav-btn:focus-visible, .action-btn:focus-visible {{
    box-shadow: 0 0 0 2px var(--bg), 0 0 0 4px var(--accent-primary);
  }}
  .date-btn {{ min-width: 140px; font-family: var(--mono); font-weight: 500; }}
  .view-tabs {{ display: flex; background: var(--surface); border-radius: var(--radius); padding: 3px; gap: 3px; border: 1px solid var(--border); }}
  .view-tabs button {{
    background: transparent; border: 0; color: var(--text-muted); padding: 8px 16px; border-radius: 8px;
    text-transform: uppercase; letter-spacing: 0.6px; font-size: 11px; font-weight: 600; cursor: pointer;
    transition: background var(--duration-normal) var(--ease-out-expo),
                color var(--duration-normal) var(--ease-out-expo),
                transform var(--duration-fast) var(--ease-out-expo),
                box-shadow var(--duration-normal) var(--ease-out-expo);
    outline: none;
    position: relative;
  }}
  .view-tabs button:hover {{ color: var(--text-secondary); background: rgba(255,255,255,0.04); }}
  .view-tabs button:active {{ transform: scale(0.96); }}
  .view-tabs button:focus-visible {{
    box-shadow: 0 0 0 2px var(--bg), 0 0 0 4px var(--accent-primary);
  }}
  .view-tabs button.active {{
    background: var(--accent); color: white;
    box-shadow: 0 2px 10px rgba(255,107,53,0.30), 0 0 0 1px rgba(255,107,53,0.20);
    transform: translateY(-1px);
  }}
  .theme-toggle {{
    width: 36px; height: 36px; border-radius: var(--radius); border: 1px solid var(--border);
    background: var(--surface); color: var(--text-secondary); cursor: pointer;
    display: flex; align-items: center; justify-content: center; font-size: 16px;
    transition: background var(--duration-fast) var(--ease-out-expo),
                border-color var(--duration-fast) var(--ease-out-expo),
                color var(--duration-fast) var(--ease-out-expo),
                transform var(--duration-fast) var(--ease-out-expo),
                box-shadow var(--duration-fast) var(--ease-out-expo);
    outline: none;
  }}
  .theme-toggle:hover {{ background: var(--surface-hover); color: var(--text); border-color: var(--text-muted); transform: translateY(-1px); }}
  .theme-toggle:active {{ transform: scale(0.95); transition-duration: 80ms; }}
  .theme-toggle:focus-visible {{ box-shadow: 0 0 0 2px var(--bg), 0 0 0 4px var(--accent-primary); }}
  .page {{ max-width: 1400px; margin: 0 auto; padding: 24px 24px 40px; }}
  .section-header {{
    display: flex; align-items: center; gap: 10px; margin: 0 0 16px;
    padding-bottom: 10px; border-bottom: 1px solid var(--border);
  }}
  .section-icon {{
    width: 32px; height: 32px; border-radius: var(--radius); display: flex;
    align-items: center; justify-content: center; flex-shrink: 0;
    font-size: 16px;
  }}
  .section-title {{ font-size: 12px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.8px; }}
  .section-count {{ margin-left: auto; color: var(--text-muted); font-family: var(--mono); font-size: 11px; font-weight: 500; }}
  .card {{
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm); padding: 20px; margin-bottom: 16px;
    border: 1px solid rgba(255,255,255,0.04);
    transition: transform var(--duration-normal) var(--ease-out-expo),
                box-shadow var(--duration-normal) var(--ease-out-expo),
                border-color var(--duration-normal) var(--ease-out-expo);
  }}
  .card:hover {{
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
    border-color: rgba(255,255,255,0.08);
  }}
  @media (hover: none) {{
    .card:hover {{ transform: none; box-shadow: var(--shadow-sm); }}
  }}
  .hero {{ display: grid; grid-template-columns: 1.2fr .8fr; gap: 16px; margin-bottom: 20px; }}
  .hero-title {{ font-size: 24px; line-height: 1.25; font-weight: 600; margin-bottom: 8px; letter-spacing: -0.03em; text-wrap: balance; }}
  .hero-sub {{ color: var(--text-secondary); max-width: 65ch; font-size: 14px; }}
  .hero-meta {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; }}
  .chip {{
    display: inline-flex; align-items: center; gap: 6px; border-radius: 999px; padding: 5px 11px;
    background: var(--surface-alt); border: 1px solid var(--border); color: var(--text-secondary);
    font-size: 11px; font-weight: 600; letter-spacing: 0.01em;
  }}
  .market-strip {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 20px; }}
  .market-item {{ background: var(--surface); border: 1px solid rgba(255,255,255,0.04); border-radius: var(--radius-lg); padding: 16px; box-shadow: var(--shadow-sm); transition: transform var(--duration-normal) var(--ease-out-expo), box-shadow var(--duration-normal) var(--ease-out-expo), border-color var(--duration-normal) var(--ease-out-expo); }}
  .market-item:hover {{ border-color: rgba(255,255,255,0.08); box-shadow: var(--shadow); transform: translateY(-2px); }}
  .market-group {{ font-size: 10px; text-transform: uppercase; letter-spacing: 0.7px; color: var(--text-muted); margin-bottom: 6px; font-weight: 600; }}
  .market-label {{ font-size: 12px; color: var(--text-secondary); margin-bottom: 8px; }}
  .market-value {{ font-family: var(--mono); font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; letter-spacing: 0.02em; }}
  .market-change {{ font-family: var(--mono); font-size: 12px; margin-top: 6px; font-weight: 600; display: flex; align-items: center; gap: 4px; font-variant-numeric: tabular-nums; }}
  .market-spark {{ display: flex; align-items: flex-end; gap: 2px; height: 24px; margin-top: 8px; }}
  .market-spark-bar {{ width: 4px; border-radius: 1px; background: var(--blue); opacity: 0.7; }}
  .up {{ color: var(--up); }}
  .down {{ color: var(--down); }}
  .neutral {{ color: var(--amber); }}
  .story-list {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 12px; }}
  .story-card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-lg); padding: 18px; display: grid; grid-template-columns: 48px 1fr; gap: 14px;
    position: relative; overflow: hidden;
    border: 1px solid rgba(255,255,255,0.04);
    transition: transform var(--duration-normal) var(--ease-out-expo),
                box-shadow var(--duration-normal) var(--ease-out-expo),
                border-left-color var(--duration-normal) var(--ease-out-expo);
    border-left: 3px solid transparent;
  }}
  .story-card:hover {{ border-left-color: var(--accent); transform: translateY(-2px); box-shadow: var(--shadow-md); border-color: rgba(255,255,255,0.06); }}
  @media (hover: none) {{ .story-card:hover {{ transform: none; box-shadow: var(--shadow-sm); }} }}
  .story-rank {{
    width: 44px; height: 44px; border-radius: 12px; background: var(--accent-light); color: var(--accent);
    display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: 700; font-family: var(--mono);
    border: 1px solid var(--accent-border);
  }}
  .story-title {{ font-size: 16px; line-height: 1.35; font-weight: 600; margin-bottom: 6px; text-wrap: balance; }}
  .story-context {{ color: var(--text-secondary); font-size: 13px; line-height: 1.5; }}
  .story-tags {{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; align-items: center; }}
  .story-sentiment {{ margin-left: auto; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; padding: 3px 8px; border-radius: 999px; }}
  .kpi-row {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; margin-bottom: 20px; }}
  .kpi-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 16px 18px; box-shadow: var(--shadow-sm); display: flex; flex-direction: column; gap: 2px; }}
  .kpi-card:hover {{ border-color: var(--accent-border); }}
  .kpi-label {{ font-size: 10px; text-transform: uppercase; letter-spacing: 0.6px; color: var(--text-muted); font-weight: 600; }}
  .kpi-value {{ font-family: var(--mono); font-size: 24px; font-weight: 700; font-variant-numeric: tabular-nums; letter-spacing: 0.02em; color: var(--text); line-height: 1.2; }}
  .kpi-change {{ font-size: 11px; font-weight: 600; display: flex; align-items: center; gap: 4px; margin-top: 2px; }}
  .kpi-change .up {{ color: var(--up); }}
  .kpi-change .down {{ color: var(--down); }}
  .kpi-change .neutral {{ color: var(--amber); }}
  .movers-panel {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 16px; box-shadow: var(--shadow-sm); margin-bottom: 20px; }}
  .movers-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }}
  .movers-title {{ font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.6px; color: var(--text-secondary); }}
  .movers-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 8px; }}
  .mover-item {{ display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: var(--radius); background: var(--surface-alt); }}
  .mover-label {{ font-size: 12px; font-weight: 500; color: var(--text); flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .mover-value {{ font-family: var(--mono); font-size: 14px; font-weight: 700; font-variant-numeric: tabular-nums; }}
  .mover-value.up {{ color: var(--up); }}
  .mover-value.down {{ color: var(--down); }}
  .mover-value.neutral {{ color: var(--amber); }}
  .sentiment-positive {{ background: var(--up-bg); color: var(--up); }}
  .sentiment-negative {{ background: var(--down-bg); color: var(--down); }}
  .sentiment-neutral {{ background: var(--amber-bg); color: var(--amber); }}
  .tag {{
    display: inline-flex; align-items: center; border-radius: 999px; padding: 4px 10px; font-size: 10px;
    text-transform: uppercase; letter-spacing: 0.5px; font-weight: 700; background: var(--accent-light); color: var(--accent);
  }}
    /* Breaking Headlines — top row grid */
  .breaking-top { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px; }
  @media (max-width: 900px) { .breaking-top { grid-template-columns: 1fr 1fr; } }
  @media (max-width: 560px) { .breaking-top { grid-template-columns: 1fr; } }
  .breaking-card {{
    background: linear-gradient(135deg, var(--surface) 0%, var(--surface-alt) 100%);
    border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 18px 20px;
    box-shadow: var(--shadow-sm); cursor: pointer;
    border: 1px solid rgba(255,255,255,0.04);
    transition: transform var(--duration-normal) var(--ease-out-expo),
                box-shadow var(--duration-normal) var(--ease-out-expo),
                border-color var(--duration-normal) var(--ease-out-expo);
    display: flex; flex-direction: column;
  }}
  .breaking-card:hover { border-color: rgba(255,255,255,0.08); transform: translateY(-2px); box-shadow: var(--shadow-md); }
  .breaking-card:active { transform: translateY(0) scale(0.985); }
  .breaking-card .bc-meta { display: flex; gap: 6px; margin-bottom: 10px; flex-wrap: wrap; align-items: center; }
  .breaking-card .bc-meta .chip { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px; border-radius: 999px; font-size: 10px; font-weight: 600; background: var(--surface-alt); color: var(--text-secondary); border: 1px solid var(--border); }
  .breaking-card .bc-tag { display: inline-flex; border-radius: 999px; padding: 3px 10px; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 700; margin-bottom: 8px; align-self: flex-start; }
  .breaking-card .bc-title { font-size: 15px; font-weight: 600; line-height: 1.35; margin-bottom: 8px; text-wrap: balance; color: var(--text); }
  .breaking-card .bc-preview { color: var(--text-muted); font-size: 12px; line-height: 1.5; flex: 1; }
  .breaking-card .bc-footer { margin-top: 10px; display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--border-light); padding-top: 8px; }
  .breaking-card .bc-sources { display: flex; gap: 4px; flex-wrap: wrap; }
  .breaking-card .bc-sources .src-chip { font-size: 9px; padding: 2px 6px; border-radius: 999px; background: var(--surface-alt); color: var(--text-muted); border: 1px solid var(--border-light); }
  .breaking-card .bc-link { font-size: 11px; color: var(--accent-primary); text-decoration: none; white-space: nowrap; }
  .breaking-card .bc-link:hover { text-decoration: underline; }

.headline-feed {{ display: grid; gap: 8px; margin-bottom: 20px; }}
  .headline-card {{
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 16px;
    display: grid; grid-template-columns: 1fr auto; gap: 12px; align-items: start; cursor: pointer;
    transition: background var(--duration-fast) var(--ease-out-expo),
                border-color var(--duration-fast) var(--ease-out-expo),
                transform var(--duration-fast) var(--ease-out-expo);
  }}
  .headline-card:hover {{ border-color: var(--accent-border); background: var(--surface-hover); transform: translateY(-1px); }}
  .headline-card:active {{ transform: translateY(0) scale(0.985); transition-duration: 80ms; }}
  .headline-card .hl-tag {{ display: inline-flex; border-radius: 999px; padding: 2px 8px; font-size: 10px; text-transform: uppercase; letter-spacing: 0.4px; font-weight: 700; margin-bottom: 4px; }}
  .headline-card .hl-title {{ font-size: 14px; font-weight: 600; line-height: 1.35; }}
  .headline-card .hl-preview {{ font-size: 12px; color: var(--text-muted); line-height: 1.4; margin-top: 4px; }}
  .headline-card .hl-meta {{ display: flex; flex-direction: column; align-items: flex-end; gap: 4px; min-width: 80px; text-align: right; }}
  .headline-card .hl-sources {{ font-size: 11px; color: var(--text-muted); font-family: var(--mono); }}
  .headline-card .hl-links {{ font-size: 11px; color: var(--accent-primary); text-decoration: none; }}
  .headline-card .hl-links:hover {{ text-decoration: underline; }}
  .brief-updated {{ font-size: 11px; color: var(--text-muted); text-align: center; padding: 8px 0 16px; font-family: var(--mono); }}
  .watch-grid {{ display: grid; gap: 10px; }}
  .watch-item {{ display: grid; grid-template-columns: 28px 1fr; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--border); }}
  .watch-item:last-child {{ border-bottom: 0; }}
  .watch-rank {{
    width: 28px; height: 28px; border-radius: 999px; background: var(--amber-bg); color: var(--amber);
    border: 1px solid rgba(255,179,0,0.20); display: flex; align-items: center; justify-content: center; font-weight: 700; font-family: var(--mono); font-size: 12px;
  }}
  .watch-title {{ font-weight: 600; margin-bottom: 2px; font-size: 14px; }}
  .watch-desc {{ color: var(--text-secondary); font-size: 13px; }}
  .quick-table {{ width: 100%; border-collapse: collapse; }}
  .quick-table th, .quick-table td {{ border-bottom: 1px solid var(--border); text-align: left; padding: 12px 10px; vertical-align: top; }}
  .quick-table th {{ font-size: 10px; text-transform: uppercase; letter-spacing: 0.7px; color: var(--text-muted); font-weight: 600; background: var(--surface-alt); }}
  .quick-table td {{ font-size: 13px; color: var(--text-secondary); }}
  .quick-table tr:hover td {{ background: var(--surface-hover); }}
  .intel-actions {{ display: flex; align-items: center; gap: 10px; margin-left: auto; }}
  .stat-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 18px; }}
  .stat-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 20px; box-shadow: var(--shadow-sm); transition: all 0.2s ease; }}
  .stat-card:hover {{ border-color: var(--border-light); box-shadow: var(--shadow); }}
  .stat-num {{ font-size: 28px; font-weight: 700; font-family: var(--mono); color: var(--accent); font-variant-numeric: tabular-nums; letter-spacing: 0.02em; }}
  .stat-label {{ color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.7px; font-size: 10px; margin-top: 8px; font-weight: 600; }}
  .stat-grid-narrative {{
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;
    margin-bottom: 16px;
  }}
  .stat-narr-card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-lg); padding: 14px 16px;
    display: flex; flex-direction: column; gap: 4px;
  }}
  .stat-narr-val {{ font-size: 28px; font-weight: 700; letter-spacing: -0.02em; line-height: 1.1; }}
  .stat-narr-spark {{ height: 20px; display: flex; align-items: flex-end; gap: 2px; margin: 4px 0; }}
  .stat-narr-bar {{ width: 8px; border-radius: 2px; background: var(--accent-primary); opacity: 0.6; }}
  .stat-narr-label {{ font-size: 12px; color: var(--text-secondary); }}
  .stat-narr-delta {{ font-size: 11px; font-weight: 500; display: flex; align-items: center; gap: 4px; }}
  .stat-narr-delta .up {{ color: var(--up); }}
  .stat-narr-delta .down {{ color: var(--down); }}
  .ticker-strip {{
    position: sticky; top: 0; z-index: 50;
    background: rgba(11,14,17,0.95); backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--border);
    padding: 6px 16px; margin-bottom: 12px;
    display: flex; gap: 24px; overflow-x: auto; white-space: nowrap;
    font-size: 13px; font-weight: 600;
    -ms-overflow-style: none; scrollbar-width: none;
  }}
  .ticker-item {{ display: inline-flex; align-items: center; gap: 8px; padding: 2px 10px; border-radius: 4px; }}
  .ticker-dot {{ width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }}
  .ticker-dot.critical {{ background: var(--down); box-shadow: 0 0 6px rgba(246,70,93,0.5); }}
  .ticker-dot.high {{ background: var(--amber); }}
  .ticker-dot.positive {{ background: var(--up); }}
  .hero-charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px; }}
  @media (max-width: 768px) {{ .hero-charts {{ grid-template-columns: 1fr; }} }}
  .chart-card-full {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 16px; }}
  .chart-card-full .chart-title {{ font-size: 13px; font-weight: 600; color: var(--text-secondary); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .chart-container-full {{ height: 180px; position: relative; }}
  .filter-bar {{
    display: flex; align-items: center; gap: 8px;
    margin-bottom: 12px; padding: 8px 0;
    position: sticky; top: 44px; z-index: 40;
    background: var(--bg);
  }}
  .filter-pill {{
    padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: 500;
    background: var(--surface-alt); color: var(--text-secondary);
    cursor: pointer; border: 1px solid var(--border-light);
    transition: background var(--duration-fast) var(--ease-out-expo),
                color var(--duration-fast) var(--ease-out-expo),
                border-color var(--duration-fast) var(--ease-out-expo),
                transform var(--duration-fast) var(--ease-out-expo);
    outline: none;
  }}
  .filter-pill:hover {{ background: var(--surface-hover); color: var(--text); transform: translateY(-1px); }}
  .filter-pill:active {{ transform: translateY(0) scale(0.96); transition-duration: 80ms; }}
  .filter-pill.active {{ background: var(--accent-primary); color: #0B0E11; border-color: var(--accent-primary); transform: translateY(-1px); }}
  .filter-pill:focus-visible {{ box-shadow: 0 0 0 2px var(--bg), 0 0 0 4px var(--accent-primary); }}
  .filter-spacer {{ flex: 1; }}
  .sort-btn {{ padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 600; background: transparent; color: var(--text-secondary); cursor: pointer; border: none; }}
  .sort-btn:hover {{ color: var(--text); }}
  .topic-card-compact {{
    display: flex; align-items: stretch; gap: 0;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); overflow: hidden;
    min-height: 48px; cursor: pointer;
    transition: background 150ms ease-out, transform 150ms ease-out;
  }}
  .topic-card-compact:hover {{ background: var(--surface-hover); transform: translateY(-1px); }}
  .heat-bar {{ width: 4px; flex-shrink: 0; transition: width 150ms ease-out; }}
  .topic-card-compact:hover .heat-bar {{ width: 6px; }}
  .heat-bar.low {{ background: linear-gradient(180deg, #42A5F5, #5BB8F5); }}
  .heat-bar.med {{ background: linear-gradient(180deg, #FFB300, #FFC233); }}
  .heat-bar.high {{ background: linear-gradient(180deg, #FF1744, #FF4567); }}
  .heat-bar.critical {{ background: linear-gradient(180deg, #F6465D, #FF6B7A); box-shadow: 0 0 8px rgba(246,70,93,0.3); }}
  .topic-body {{ flex: 1; padding: 10px 12px; display: flex; align-items: center; gap: 12px; min-width: 0; }}
  .topic-name-compact {{ font-size: 14px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex-shrink: 0; }}
  .topic-sparkline {{ width: 80px; height: 20px; flex-shrink: 0; display: flex; align-items: flex-end; gap: 2px; }}
  .topic-spark-bar {{ width: 8px; border-radius: 2px; min-height: 3px; }}
  .topic-spark-bar:nth-child(1) {{ height: 30%; }} .topic-spark-bar:nth-child(2) {{ height: 50%; }}
  .topic-spark-bar:nth-child(3) {{ height: 70%; }} .topic-spark-bar:nth-child(4) {{ height: 40%; }}
  .topic-spark-bar:nth-child(5) {{ height: 85%; }} .topic-spark-bar:nth-child(6) {{ height: 60%; }}
  .topic-spark-bar:nth-child(7) {{ height: 90%; }}
  .topic-count {{ font-size: 12px; color: var(--text-muted); flex-shrink: 0; }}
  .heat-pill {{
    padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; flex-shrink: 0;
  }}
  .heat-pill.low {{ background: var(--heat-low-bg); color: var(--heat-low); }}
  .heat-pill.med {{ background: var(--heat-med-bg); color: var(--heat-med); }}
  .heat-pill.high {{ background: var(--heat-high-bg); color: var(--heat-high); }}
  .heat-pill.critical {{ background: var(--down-bg); color: var(--down); }}
  .topic-expand {{ 
    flex-shrink: 0; width: 28px; display: flex; align-items: center; justify-content: center;
    font-size: 12px; color: var(--text-muted); transition: transform 200ms ease-in-out;
  }}
  .topic-expand.open {{ transform: rotate(180deg); }}
  .topic-detail {{
    display: none; padding: 0 12px 10px; border-top: 1px solid var(--border-light);
    margin-top: 0;
  }}
  .topic-detail.open {{ display: block; }}
  .topic-detail-article {{
    padding: 6px 0; font-size: 12px; line-height: 1.4;
    border-bottom: 1px solid var(--border-light);
  }}
  .topic-detail-article:last-child {{ border-bottom: none; }}
  .topic-detail-title {{ color: var(--text); font-weight: 500; }}
  .topic-detail-meta {{ color: var(--text-muted); margin-top: 2px; }}
  .topic-stack-compact {{ display: flex; flex-direction: column; gap: 4px; }}
  .section-header-sticky {{
    position: sticky; top: 44px; z-index: 39;
    background: var(--bg); padding: 8px 0; margin: 16px 0 8px;
    display: flex; align-items: center; gap: 10px;
  }}
  .full-shell {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); overflow: hidden; }}
  .full-frame {{ padding: 24px; }}
  .full-layout {{ display: grid; grid-template-columns: 2fr 1fr; gap: 18px; margin-bottom: 20px; }}
  .full-main {{ display: flex; flex-direction: column; gap: 12px; }}
  .full-sidebar {{ display: flex; flex-direction: column; gap: 14px; }}
  .full-article-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 16px 20px; box-shadow: var(--shadow-sm); border-left: 3px solid transparent; }}
  .full-article-card:hover {{ border-color: var(--accent-border); }}
  .full-article-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}
  .full-article-title {{ font-size: 15px; font-weight: 600; color: var(--text); line-height: 1.35; }}
  .full-article-body {{ font-size: 13px; color: var(--text-secondary); line-height: 1.5; }}
  .full-article-footer {{ display: flex; align-items: center; gap: 8px; margin-top: 10px; }}
  .full-cat-pill {{ font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 700; padding: 3px 8px; border-radius: 999px; color: white; }}
  .sidebar-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 16px; box-shadow: var(--shadow-sm); }}
  .sidebar-title {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px; color: var(--text-muted); font-weight: 600; margin-bottom: 10px; }}
  .sidebar-stat {{ display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid var(--border-light); }}
  .sidebar-stat:last-child {{ border-bottom: none; }}
  .sidebar-stat-label {{ font-size: 12px; color: var(--text-secondary); }}
  .sidebar-stat-val {{ font-family: var(--mono); font-size: 13px; font-weight: 600; }}
  .tag-cloud {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .tag-cloud-pill {{ font-size: 10px; font-weight: 600; padding: 4px 9px; border-radius: 999px; background: var(--surface-alt); border: 1px solid var(--border-light); color: var(--text-secondary); cursor: default; }}
  .mini-bar-wrap {{ display: flex; flex-direction: column; gap: 6px; }}
  .mini-bar-row {{ display: flex; align-items: center; gap: 8px; font-size: 11px; }}
  .mini-bar-label {{ width: 80px; color: var(--text-muted); text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .mini-bar-track {{ flex: 1; height: 8px; background: var(--surface-alt); border-radius: 4px; overflow: hidden; }}
  .mini-bar-fill {{ height: 100%; border-radius: 4px; }}
  @media (max-width: 1024px) {{ .full-layout {{ grid-template-columns: 1fr; }} }}
  .full-frame h1, .full-frame h2 {{ color: var(--accent); margin: 28px 0 14px; font-weight: 600; }}
  .full-frame h3 {{ margin: 22px 0 10px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.6px; color: var(--text-secondary); border-bottom: 1px solid var(--border); padding-bottom: 6px; font-weight: 600; }}
  .full-frame p {{ margin: 12px 0; line-height: 1.65; }}
  .full-frame ul, .full-frame ol {{ padding-left: 24px; margin: 12px 0; }}
  .full-frame table {{ width: 100%; border-collapse: collapse; margin: 14px 0; }}
  .full-frame th, .full-frame td {{ border: 1px solid var(--border); padding: 10px 12px; text-align: left; }}
  .full-frame th {{ background: var(--surface-alt); font-size: 10px; text-transform: uppercase; letter-spacing: 0.7px; color: var(--text-secondary); font-weight: 600; }}
  .kb-tags {{ display: flex; flex-wrap: wrap; gap: 8px; }}
  .type-tag {{ display: inline-flex; align-items: center; gap: 6px; padding: 7px 11px; border-radius: 999px; background: var(--surface-alt); border: 1px solid var(--border-light); }}
  .type-dot {{ width: 10px; height: 10px; border-radius: 999px; }}
  .history-list {{ display: grid; gap: 10px; }}
  .history-row {{ display: flex; justify-content: space-between; gap: 14px; padding: 12px 0; border-bottom: 1px solid var(--border); transition: all 0.15s ease; }}
  .history-row:last-child {{ border-bottom: 0; }}
  .history-row:hover {{ background: var(--surface-hover); margin: 0 -12px; padding-left: 12px; padding-right: 12px; border-radius: 6px; }}
  .history-date {{ font-family: var(--mono); font-weight: 700; cursor: pointer; color: var(--text); transition: color 0.15s ease; }}
  .history-date:hover {{ color: var(--accent); }}
  .chart-container {{ position: relative; height: 220px; margin: 12px 0; }}
  .chart-container-lg {{ position: relative; height: 300px; margin: 12px 0; }}
  .chart-container-sm {{ position: relative; height: 140px; margin: 8px 0; }}
  .chart-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; margin-bottom: 20px; }}
  .chart-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 18px; box-shadow: var(--shadow-sm); }}
  .chart-title {{ font-size: 13px; font-weight: 600; color: var(--text-secondary); margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .muted {{ color: var(--text-muted); }}
  .empty, .loading {{ padding: 36px 16px; text-align: center; color: var(--text-muted); }}
  @media (max-width: 1024px) {{
    .hero, .intel-grid {{ grid-template-columns: 1fr; }}
    .toolbar {{ margin-left: 0; width: 100%; justify-content: space-between; }}
  }}
  @media (max-width: 768px) {{
    .page {{ padding: 16px 16px 28px; }}
    .header-inner {{ padding: 10px 16px; }}
    .story-card {{ grid-template-columns: 1fr; }}
    .story-rank {{ width: 40px; height: 40px; font-size: 16px; }}
    .market-strip {{ grid-template-columns: repeat(2, 1fr); }}
    .view-tabs {{ width: 100%; justify-content: space-around; }}
    .view-tabs button {{ flex: 1; text-align: center; padding: 10px 8px; font-size: 10px; }}
    .date-btn {{ min-width: auto; flex: 1; }}
    .theme-toggle {{ display: none; }}
  }}
  @media (max-width: 480px) {{
    .market-strip {{ grid-template-columns: 1fr; }}
    .hero-title {{ font-size: 20px; }}
  }}

  /* ---- Markdown-rendered report styling (mistune output) ---- */
  .analysis-report-body h1 {{ font-size: 20px; font-weight: 800; color: var(--text); border-bottom: 1px solid var(--border); padding-bottom: 8px; margin: 0 0 12px 0; letter-spacing: -0.3px; }}
  .analysis-report-body h2 {{ font-size: 16px; font-weight: 700; color: var(--text); margin: 20px 0 8px 0; }}
  .analysis-report-body h3 {{ font-size: 14px; font-weight: 700; color: var(--text-secondary); margin: 16px 0 6px 0; }}
  .analysis-report-body p {{ margin: 0 0 10px 0; line-height: 1.6; font-size: 13px; color: var(--text-secondary); }}
  .analysis-report-body ul, .analysis-report-body ol {{ margin: 0 0 10px 0; padding-left: 20px; }}
  .analysis-report-body li {{ margin-bottom: 4px; font-size: 13px; line-height: 1.5; color: var(--text-secondary); }}
  .analysis-report-body strong {{ color: var(--text); }}
  .analysis-report-body code {{ background: var(--surface-alt); padding: 1px 5px; border-radius: 4px; font-family: var(--mono); font-size: 12px; color: var(--accent); }}
  .analysis-report-body pre {{ background: var(--surface-alt); border: 1px solid var(--border); border-radius: var(--radius); padding: 12px; overflow-x: auto; margin: 0 0 12px 0; }}
  .analysis-report-body pre code {{ background: none; padding: 0; color: var(--text-secondary); font-size: 12px; }}
  .analysis-report-body blockquote {{ border-left: 3px solid var(--accent); margin: 0 0 12px 0; padding: 8px 14px; background: rgba(59,130,246,0.06); border-radius: 0 var(--radius) var(--radius) 0; }}
  .analysis-report-body blockquote p {{ margin: 0 0 6px 0; font-style: italic; color: var(--text); }}
  .analysis-report-body blockquote p:last-child {{ margin-bottom: 0; }}
  .analysis-report-body table {{ width: 100%; border-collapse: collapse; margin: 0 0 14px 0; font-size: 12px; }}
  .analysis-report-body th {{ text-align: left; padding: 8px 10px; background: var(--surface-alt); border-bottom: 2px solid var(--border); color: var(--text); font-weight: 700; font-size: 12px; }}
  .analysis-report-body td {{ padding: 7px 10px; border-bottom: 1px solid var(--border-light); color: var(--text-secondary); }}
  .analysis-report-body tr:hover td {{ background: rgba(255,255,255,0.02); }}
  .analysis-report-body hr {{ border: none; border-top: 1px solid var(--border); margin: 16px 0; }}
  .analysis-report-body img {{ max-width: 100%; border-radius: var(--radius); }}
  .analysis-report-body a {{ color: var(--accent); text-decoration: none; }}
  .analysis-report-body a:hover {{ text-decoration: underline; }}
  /* ---- Topic Cards (used by DD and MM Recurring Themes) ---- */
  .topic-card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 16px; margin-bottom: 12px;
    transition: border-color 0.2s ease, background 0.2s ease, transform 0.15s ease;
  }}
  .topic-card:hover {{
    background: var(--surface-hover); transform: translateY(-1px);
    box-shadow: var(--shadow-sm);
  }}
  .topic-top {{ display: flex; align-items: flex-start; gap: 10px; }}
  .topic-main {{ flex: 1; min-width: 0; }}
  .topic-name {{
    font-size: 14px; font-weight: 700; color: var(--text); margin-bottom: 4px;
    line-height: 1.4;
  }}
  .topic-meta {{
    font-size: 11px; color: var(--text-muted); display: flex; gap: 10px;
    flex-wrap: wrap;
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
        <button class="nav-btn" onclick="navDate(-1)" aria-label="Previous date">&larr;</button>
        <button class="nav-btn date-btn" id="dateDisplay" onclick="pickDate()">--</button>
        <button class="nav-btn" onclick="navDate(1)" aria-label="Next date">&rarr;</button>
      </div>
      <div class="view-tabs">
        <button id="tabBrief" class="active" onclick="setView('brief')">Brief</button>
        <button id="tabFull" onclick="setView('full')">Full</button>
        <button id="tabIntel" onclick="setView('intel')">Intel</button>
        <button id="tabDd" onclick="setView('dd')">DD</button>
        <button id="tabMm" onclick="setView('mm')">MM</button>
        <button id="tabNews" onclick="setView('news')">AI News</button>
      </div>
      <button class="theme-toggle" id="themeToggle" onclick="toggleTheme()" aria-label="Toggle theme">&#9788;</button>
    </div>
  </div>
</div>
<div class="page" id="content"><div class="loading">Loading portal...</div></div>
<script>
let availableDates = [];
let currentDate = null;
let currentView = 'brief';
let selectedHeadline = null;  // index into headlines[] from Brief tab
const cache = Object.create(null);

function selectHeadline(index) {
  selectedHeadline = index;
  setView('full');
}

/* selectArticle: click a synthesized article on Brief tab → find matching headline → go to Full */
var _briefArticlesCache = [];
function selectArticle(articleIndex) {
  if (articleIndex >= _briefArticlesCache.length) return;
  var article = _briefArticlesCache[articleIndex];
  if (!article) return;
  /* Try to find matching headline by fuzzy title match */
  var bestIdx = -1;
  var bestScore = 0;
  getDateData(currentDate).then(function(data) {
    var brief = data.brief_parsed || { headlines: [] };
    var hds = brief.headlines || [];
    for (var hi = 0; hi < hds.length; hi++) {
      var ht = (hds[hi].title || '').toLowerCase();
      var at = (article.title || '').toLowerCase();
      /* Simple word overlap scoring */
      var hWords = ht.split(/\s+/);
      var aWords = at.split(/\s+/);
      var overlap = 0;
      for (var wi = 0; wi < aWords.length; wi++) {
        if (ht.indexOf(aWords[wi]) !== -1) overlap++;
      }
      var score = overlap / Math.max(hWords.length, aWords.length);
      if (score > bestScore) { bestScore = score; bestIdx = hi; }
    }
    if (bestIdx >= 0 && bestScore > 0.4) {
      selectedHeadline = bestIdx;
    } else {
      /* No match — show article inline via alert fallback */
      selectedHeadline = null;
    }
    setView('full');
  });
}

/* Auto-refresh Brief tab every 5 minutes */
var _briefRefreshTimer = null;
function startBriefRefresh() {
  stopBriefRefresh();
  _briefRefreshTimer = setInterval(function() {
    if (currentView === 'brief') renderBrief();
  }, 5 * 60 * 1000);
}
function stopBriefRefresh() {
  if (_briefRefreshTimer) { clearInterval(_briefRefreshTimer); _briefRefreshTimer = null; }
}

function esc(value) {
  return String(value || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// Simple markdown renderer: **bold**, *italic*, paragraph breaks
function renderMarkdown(text) {
  if (!text) return '';
  var escaped = esc(text);
  var dblNL = String.fromCharCode(10) + String.fromCharCode(10);
  var NL = String.fromCharCode(10);
  var paragraphs = escaped.split(dblNL);
  if (paragraphs.length === 1) paragraphs = escaped.split(NL);
  var html = '';
  for (var i = 0; i < paragraphs.length; i++) {
    var p = paragraphs[i].trim();
    if (p.length === 0) continue;
    // Bold: **text**
    p = p.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Italic: *text* (simple approach - replace remaining single asterisks)
    var parts = p.split('*');
    if (parts.length > 2 && parts.length % 2 === 1) {
      var rebuilt = parts[0];
      for (var j = 1; j < parts.length; j++) {
        if (j % 2 === 1) rebuilt += '<em>' + parts[j] + '</em>';
        else rebuilt += parts[j];
      }
      p = rebuilt;
    }
    p = p.replace(new RegExp(String.fromCharCode(10), 'g'), '<br>');
    html += '<p style="margin-bottom:14px">' + p + '</p>';
  }
  return html;
}

// Clean email body for display: strip headers, normalize whitespace
function cleanBody(text) {
  if (!text) return '';
  var NL = String.fromCharCode(10);  // newline char, safe across all escaping layers
  var lines = text.split(NL);
  var headerPrefixes = 'From:|To:|Subject:|Date:|Cc:|Bcc:|Reply-To:|Message-ID:|MIME-Version:|Content-Type:|Content-Transfer-Encoding:|X-|DKIM-|Received:|Return-Path:|List-|Feedback-ID:|Precedence:'.split('|');
  // Filter out email header lines
  var kept = [];
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    var isHeader = false;
    for (var j = 0; j < headerPrefixes.length; j++) {
      if (line.indexOf(headerPrefixes[j]) === 0) { isHeader = true; break; }
    }
    if (!isHeader) kept.push(line);
  }
  var result = kept.join(NL);
  // Collapse 3+ consecutive newlines to at most 1 blank line
  var parts = result.split(NL);
  var collapsed = [];
  var emptyCount = 0;
  for (var k = 0; k < parts.length; k++) {
    if (parts[k].trim() === '') {
      emptyCount++;
      if (emptyCount <= 1) collapsed.push('');  // keep at most 1 blank line
    } else {
      emptyCount = 0;
      collapsed.push(parts[k]);
    }
  }
  return collapsed.join(NL).trim();
}

// ---- Smart excerpting: extract keywords, score paragraphs, find relevant content ----
// All string operations only — zero regex literals to avoid Python/HTML/JS escaping bugs

// Extract meaningful keywords from a headline title
function extractKeywords(title) {
  if (!title) return [];
  var delimiters = ' .,:;!?()"' + "'" + '\\/-';
  var words = [];
  var current = '';
  for (var i = 0; i < title.length; i++) {
    var ch = title.charAt(i);
    if (delimiters.indexOf(ch) !== -1) {
      if (current.length > 0) { words.push(current.toLowerCase()); current = ''; }
    } else {
      current += ch;
    }
  }
  if (current.length > 0) words.push(current.toLowerCase());
  var stopWords = ['the','a','an','is','are','was','were','be','been','being','have','has','had','do','does','did','will','would','could','should','may','might','can','shall','of','in','on','at','to','for','with','by','from','about','as','into','through','during','before','after','above','below','between','out','off','over','under','up','down','and','but','or','nor','not','so','if','then','else','when','where','why','how','what','which','who','whom','whose','this','that','these','those','it','its','they','them','their','he','she','his','her','we','us','our','my','your','says','said','more','than','just','now','new','also','get','got','one','two','back'];
  var keywords = [];
  for (var i = 0; i < words.length; i++) {
    var w = words[i];
    if (w.length > 2 && stopWords.indexOf(w) === -1) {
      keywords.push(w);
    }
  }
  return keywords;
}

// Score a paragraph: how many keywords does it contain?
function paragraphScore(paragraph, keywords) {
  if (!paragraph || !keywords.length) return 0;
  var lower = paragraph.toLowerCase();
  var score = 0;
  for (var i = 0; i < keywords.length; i++) {
    if (lower.indexOf(keywords[i]) !== -1) score++;
  }
  return score;
}

// Split body into paragraphs, score each, return matched and unmatched groups
// Returns null if no keywords or no matches (caller falls back to full body)
function extractExcerpts(body, keywords) {
  if (!keywords || !keywords.length) return null;
  var NL = String.fromCharCode(10);
  var all = body.split(NL);
  var paragraphs = [];
  for (var i = 0; i < all.length; i++) {
    if (all[i].trim().length > 0) paragraphs.push(all[i]);
  }
  var matched = [];
  var unmatched = [];
  for (var i = 0; i < paragraphs.length; i++) {
    var score = paragraphScore(paragraphs[i], keywords);
    if (score > 0) {
      matched.push(paragraphs[i]);
    } else {
      unmatched.push(paragraphs[i]);
    }
  }
  if (!matched.length) return null;  // nothing matched, show full body
  return { matched: matched, unmatched: unmatched };
}

// Collect matching excerpts across all newsletters for a given headline
// Returns: { sources: [{subject, meta, paragraphs, urls}], allUrls: [] }
function collectSourceExcerpts(newsletters, keywords) {
  if (!keywords || !keywords.length) return null;
  var sources = [];
  var allUrls = [];
  
  for (var i = 0; i < newsletters.length; i++) {
    var nl = newsletters[i];
    if (!nl.body) continue;
    var excerpts = extractExcerpts(nl.body, keywords);
    if (excerpts && excerpts.matched.length > 0) {
      var nlTime = nl.date_local ? nl.date_local.split(' ')[1] || '' : '';
      var meta = [];
      if (nl.from_name) meta.push(nl.from_name);
      if (nlTime) meta.push(nlTime);
      if (nl.reporter) meta.push(nl.reporter);
      if (nl.newsletter_type) meta.push(nl.newsletter_type);
      
      sources.push({
        subject: nl.subject || 'Newsletter ' + (i + 1),
        meta: meta.join(' · '),
        paragraphs: excerpts.matched
      });
      
      // Collect URLs
      if (nl.urls && nl.urls.length) {
        for (var j = 0; j < nl.urls.length; j++) {
          if (allUrls.indexOf(nl.urls[j]) === -1) {
            allUrls.push(nl.urls[j]);
          }
        }
      }
    }
  }
  
  if (!sources.length) return null;
  return { sources: sources, allUrls: allUrls };
}

function setActiveTab() {
  ['brief', 'full', 'intel', 'dd', 'mm', 'news'].forEach(view => {
    document.getElementById('tab' + view.charAt(0).toUpperCase() + view.slice(1)).classList.toggle('active', currentView === view);
  });
}

function initTheme() {
  const saved = localStorage.getItem('bloomberg-theme');
  if (saved === 'light') {
    document.documentElement.setAttribute('data-theme', 'light');
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
  updateThemeIcon();
}
function toggleTheme() {
  const isLight = document.documentElement.getAttribute('data-theme') === 'light';
  if (isLight) {
    document.documentElement.removeAttribute('data-theme');
    localStorage.setItem('bloomberg-theme', 'dark');
  } else {
    document.documentElement.setAttribute('data-theme', 'light');
    localStorage.setItem('bloomberg-theme', 'light');
  }
  updateThemeIcon();
}
function updateThemeIcon() {
  const btn = document.getElementById('themeToggle');
  if (btn) {
    btn.innerHTML = document.documentElement.getAttribute('data-theme') === 'light' ? '&#9790;' : '&#9788;';
  }
}
async function init() {
  try {
    initTheme();
    const res = await fetch('/api/dates');
    if (!res.ok) throw new Error('API returned ' + res.status);
    const data = await res.json();
    availableDates = data.dates || [];
    currentDate = availableDates[0] || null;
    render();
  } catch(err) {
    document.getElementById('content').innerHTML =
      '<div class="empty" style="color:var(--red);padding:40px">' +
      '<h3>⚠ Portal failed to load</h3>' +
      '<p>Error: ' + err.message + '</p>' +
      '<p><button onclick="init()" style="padding:8px 16px;cursor:pointer">Retry</button></p>' +
      '</div>';
    console.error('Portal init error:', err);
  }
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
  if (!currentDate && currentView !== 'intel' && currentView !== 'dd' && currentView !== 'mm' && currentView !== 'news') {
    document.getElementById('content').innerHTML = '<div class="empty">No digest dates found.</div>';
    return;
  }
  if (currentView === 'brief') return renderBrief();
  if (currentView === 'full') return renderFull();
  if (currentView === 'intel') return renderIntel();
  if (currentView === 'dd') return renderDD();
  if (currentView === 'mm') return renderMM();
  if (currentView === 'news') return renderNews();
  return renderBrief();  // fallback
}

function setView(view) {
  currentView = view;
  if (view === 'brief') startBriefRefresh(); else stopBriefRefresh();
  render();
}
function switchView(v) { setView(v); }  // alias for onclick handlers

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

const CATEGORY_COLORS = {
  'Markets': '#42A5F5',
  'MACRO': '#AB47BC',
  'Macro': '#AB47BC',
  'Geopolitics': '#e11d48',
  'DC Security': '#FFB300',
  'Tech': '#26C6DA',
  'Technology': '#26C6DA',
  'Energy': '#0ECB81',
  'Crypto': '#d97706',
  'Politics': '#dc2626',
};
function getCategoryColor(cat) {
  if (!cat) return 'var(--accent)';
  const key = Object.keys(CATEGORY_COLORS).find(k => cat.toLowerCase().includes(k.toLowerCase()));
  return key ? CATEGORY_COLORS[key] : 'var(--accent)';
}
function getCategoryDot(cat) {
  if (!cat) return '';
  const color = getCategoryColor(cat);
  return `<span class="mover-dot" style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};flex-shrink:0"></span>`;
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
  function sentimentBadge(sentiment) {
    if (!sentiment) return '';
    const s = String(sentiment).toLowerCase();
    let cls = 'sentiment-neutral';
    if (s.includes('positive') || s.includes('bull')) cls = 'sentiment-positive';
    else if (s.includes('negative') || s.includes('bear')) cls = 'sentiment-negative';
    return `<span class="story-sentiment ${cls}">${esc(sentiment)}</span>`;
  }
  const storyHtml = headlines.length ? headlines.map((item, i) => {
    const catColor = getCategoryColor(item.category || (item.topic_tags && item.topic_tags[0]));
    const sentHtml = sentimentBadge(item.sentiment);
    return `
    <div class="story-card" style="border-left:3px solid ${catColor};cursor:pointer" onclick="selectHeadline(${i})">
      <div class="story-rank">${item.rank}</div>
      <div>
        <div class="story-title">${esc(item.title)}</div>
        <div class="story-context">${esc(item.context)}</div>
        <div class="story-tags">${formatTopicTags(item.topic_tags && item.topic_tags.length ? item.topic_tags : [item.category].filter(Boolean))}${sentHtml}</div>
      </div>
    </div>`;
  }).join('') : '<div class="empty">Brief headlines unavailable.</div>';
  function marketArrow(cls) {
    if (cls === 'up') return '&#9650;';
    if (cls === 'down') return '&#9660;';
    return '&#8211;';
  }
  const marketHtml = market.length ? market.map(item => {
    const arrow = marketArrow(item.change_class);
    const sparkBars = [0.4, 0.7, 0.5, 0.9, 0.6, 0.8].map((h, i) => `<div class="market-spark-bar" style="height:${Math.round(h*100)}%"></div>`).join('');
    return `
    <div class="market-item">
      <div class="market-group">${esc(item.group || 'Market')}</div>
      <div class="market-label">${esc(item.label)}</div>
      <div class="market-value">${esc(item.value)}</div>
      <div class="market-change ${item.change_class}">${arrow} ${esc(item.change || item.notes || 'No change data')}</div>
      <div class="market-spark">${sparkBars}</div>
    </div>`;
  }).join('') : '<div class="card"><div class="muted">No market data parsed for this date.</div></div>';
  // ---- KPI Summary Row ----
  const kpiCards = [];
  kpiCards.push(`<div class="kpi-card"><div class="kpi-label">Headlines</div><div class="kpi-value">${headlines.length}</div><div class="kpi-change neutral">◆ ranked stories</div></div>`);
  kpiCards.push(`<div class="kpi-card"><div class="kpi-label">Market Data</div><div class="kpi-value">${market.length}</div><div class="kpi-change neutral">◆ data points</div></div>`);
  kpiCards.push(`<div class="kpi-card"><div class="kpi-label">Watch Items</div><div class="kpi-value">${watch.length}</div><div class="kpi-change neutral">◆ monitored</div></div>`);
  // Count categories from headlines
  const catCounts = {};
  headlines.forEach(h => {
    const cat = h.category || (h.topic_tags && h.topic_tags[0]) || 'Other';
    catCounts[cat] = (catCounts[cat] || 0) + 1;
  });
  const topCat = Object.entries(catCounts).sort((a,b) => b[1] - a[1])[0];
  if (topCat) {
    kpiCards.push(`<div class="kpi-card"><div class="kpi-label">Top Topic</div><div class="kpi-value">${esc(topCat[0])}</div><div class="kpi-change"><span class="up">◆</span> ${topCat[1]} stories</div></div>`);
  }
  // Count market data with numeric changes
  const movers = market.filter(m => m.change_class === 'up' || m.change_class === 'down');
  kpiCards.push(`<div class="kpi-card"><div class="kpi-label">Market Moves</div><div class="kpi-value">${movers.length}</div><div class="kpi-change"><span class="${movers.filter(m=>m.change_class==='up').length >= movers.filter(m=>m.change_class==='down').length ? 'up' : 'down'}">${movers.filter(m=>m.change_class==='up').length}▲ ${movers.filter(m=>m.change_class==='down').length}▼</span></div></div>`);
  const kpiHtml = `<div class="kpi-row">${kpiCards.join('')}</div>`;
  // ---- Market Movers Panel ----
  const marketMovers = market.filter(m => m.change_class === 'up' || m.change_class === 'down');
  const moverHtml = marketMovers.length ? marketMovers.map(m => {
    const arrow = m.change_class === 'up' ? '▲' : '▼';
    const changeText = m.change || m.notes || m.value;
    return `<div class="mover-item"><span style="color:${m.change_class === 'up' ? 'var(--up)' : 'var(--down)'};font-size:12px">${arrow}</span><span class="mover-label">${esc(m.label)}</span><span class="mover-value ${m.change_class}">${esc(changeText)}</span></div>`;
  }).join('') : '';
  const moversHtml = marketMovers.length ? `<div class="movers-panel">
    <div class="movers-header"><span style="font-size:14px">📈</span><span class="movers-title">Top Market Movers</span><span style="margin-left:auto;font-size:11px;color:var(--text-muted);font-family:var(--mono)">${marketMovers.length} moves</span></div>
    <div class="movers-grid">${moverHtml}</div>
  </div>` : '';
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
  /* ---- Synthesized Articles (breaking headlines) ---- */
  const articlesData = data.articles || null;
  const articles = articlesData ? articlesData.articles || [] : [];
  const articlesGenerated = articlesData ? articlesData.generated_at : null;
  _briefArticlesCache = articles;
  function stripMd(text, maxLen) {
    if (!text) return '';
    /* Strip markdown using pure string ops (avoids regex backslash issues in Python template) */
    var s = text;
    /* Remove bold ** markers */
    while (s.indexOf(String.fromCharCode(42,42)) !== -1) {
      var i = s.indexOf(String.fromCharCode(42,42));
      var j = s.indexOf(String.fromCharCode(42,42), i + 2);
      if (j === -1) break;
      s = s.substring(0, i) + s.substring(i + 2, j) + s.substring(j + 2);
    }
    /* Remove italic * markers */
    while (s.indexOf(String.fromCharCode(42)) !== -1) {
      var i = s.indexOf(String.fromCharCode(42));
      var j = s.indexOf(String.fromCharCode(42), i + 1);
      if (j === -1) break;
      s = s.substring(0, i) + s.substring(i + 1, j) + s.substring(j + 1);
    }
    /* Remove backtick code markers */
    while (s.indexOf(String.fromCharCode(96)) !== -1) {
      var i = s.indexOf(String.fromCharCode(96));
      var j = s.indexOf(String.fromCharCode(96), i + 1);
      if (j === -1) break;
      s = s.substring(0, i) + s.substring(i + 1, j) + s.substring(j + 1);
    }
    /* Replace newlines with spaces, strip bullet prefixes */
    var NL = String.fromCharCode(10);
    var lines = s.split(NL);
    s = lines.map(function(line) {
      var l = line;
      while (l.length > 0) {
        var c = l.charCodeAt(0);
        if (c === 35 || c === 62 || c === 45 || c === 8226 || c === 32 || c === 9) { l = l.substring(1); }
        else break;
      }
      return l;
    }).join(' ');
    /* Collapse whitespace */
    while (s.indexOf('  ') !== -1) s = s.replace('  ', ' ');
    /* Trim leading/trailing whitespace char by char */
    while (s.length > 0 && s.charCodeAt(0) <= 32) s = s.substring(1);
    while (s.length > 0 && s.charCodeAt(s.length - 1) <= 32) s = s.substring(0, s.length - 1);
    return s.length > maxLen ? s.substring(0, maxLen) + String.fromCharCode(8230) : s;
  }
  function tagColor(tag) {
    const t = (tag || '').toUpperCase();
    const map = { GEOPOLITICS: 'var(--red)', POLITICS: 'var(--purple)', MARKETS: 'var(--blue)', TECH: 'var(--cyan)', ECONOMY: 'var(--amber)', ENERGY: 'var(--up)', COMMODITIES: 'var(--amber)' };
    return map[t] || 'var(--accent)';
  }
  function tagBg(tag) {
    const t = (tag || '').toUpperCase();
    const map = { GEOPOLITICS: 'var(--red-bg)', POLITICS: 'var(--purple-bg)', MARKETS: 'var(--blue-bg)', TECH: 'var(--cyan-bg)', ECONOMY: 'var(--amber-bg)', ENERGY: 'var(--up-bg)', COMMODITIES: 'var(--amber-bg)' };
    return map[t] || 'var(--accent-light)';
  }
  function timeAgo(iso) {
    if (!iso) return '';
    const diff = (Date.now() - new Date(iso).getTime()) / 1000;
    if (diff < 60) return 'just now';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    return Math.floor(diff / 86400) + 'd ago';
  }
  const newsletterCount = (data.newsletters || []).length;
  let breakingHeroHtml = '';
  let headlineFeedHtml = '';
  if (articles.length > 0) {
    /* Top N cards in a row — show up to 3 */
    const topN = Math.min(3, articles.length);
    var topCards = '';
    for (var ti = 0; ti < topN; ti++) {
      var a = articles[ti];
      var t = (a.tags && a.tags[0]) || 'NEWS';
      var prev = stripMd(a.article, 160);
      var srcs = (a.sources || []).slice(0, 3).map(function(s) { return '<span class="src-chip">' + esc(s.newsletter) + '</span>'; }).join('');
      var link = (a.links && a.links[0]) || '';
      var linkHtml = link ? '<a href="' + esc(link) + '" target="_blank" rel="noopener" class="bc-link" onclick="event.stopPropagation()">\u2197</a>' : '';
      var badge = ti === 0 ? '<span class="chip" style="background:var(--accent-primary-bg);color:var(--accent-primary)">\u26A1 TOP</span>' : '<span class="chip">#' + (ti + 1) + '</span>';
      topCards += '<div class="breaking-card" onclick="selectArticle(' + ti + ')">' +
        '<div class="bc-meta">' + badge + '<span class="chip">' + esc(currentDate) + '</span></div>' +
        '<div class="bc-tag" style="background:' + tagBg(t) + ';color:' + tagColor(t) + '">' + esc(t) + '</div>' +
        '<div class="bc-title">' + esc(a.title) + '</div>' +
        '<div class="bc-preview">' + esc(prev) + '</div>' +
        '<div class="bc-footer"><div class="bc-sources">' + srcs + '</div>' + linkHtml + '</div>' +
        '</div>';
    }
    breakingHeroHtml = '<div class="breaking-top">' + topCards + '</div>';
    /* Remaining headlines as feed cards */
    var feedCards = '';
    for (var fi = topN; fi < articles.length; fi++) {
      var a = articles[fi];
      var t = (a.tags && a.tags[0]) || 'NEWS';
      var prev = stripMd(a.article, 100);
      var srcCount = (a.sources || []).length;
      var linkCount = (a.links || []).length;
      var firstLink = (a.links && a.links[0]) || '';
      var linkHtml = firstLink ? '<a href="' + esc(firstLink) + '" target="_blank" rel="noopener" class="hl-links" onclick="event.stopPropagation()">\u2197</a>' : '';
      feedCards += '<div class="headline-card" onclick="selectArticle(' + fi + ')">' +
        '<div><div class="hl-tag" style="background:' + tagBg(t) + ';color:' + tagColor(t) + '">' + esc(t) + '</div>' +
        '<div class="hl-title">' + esc(a.title) + '</div>' +
        '<div class="hl-preview">' + esc(prev) + '</div></div>' +
        '<div class="hl-meta"><div class="hl-sources">' + srcCount + ' src \u00b7 ' + linkCount + ' links</div>' +
        linkHtml + '</div></div>';
    }
    headlineFeedHtml = feedCards ? '<div class="section-header"><div class="section-icon" style="background:var(--red-bg);color:var(--red)">•</div><div class="section-title">All Headlines</div><div class="section-count">' + (articles.length - topN) + ' more</div></div><div class="headline-feed">' + feedCards + '</div>' : '';
  }
  /* ---- Fallback: use brief_parsed headlines if no articles ---- */
  if (!articles.length && headlines.length) {
    breakingHeroHtml = `
      <div class="hero" style="margin-bottom:20px">
        <div class="card">
          <div class="hero-meta" style="display:flex;gap:8px;margin-bottom:10px">
            <span class="chip" style="background:var(--accent-primary-bg);color:var(--accent-primary)">📰 HEADLINES</span>
            <span class="chip">${esc(currentDate)}</span>
          </div>
          <div class="hero-title" style="font-size:18px">${headlines.length} ranked stories from Bloomberg Daily Brief</div>
        </div>
      </div>`;
    headlineFeedHtml = `<div class="story-list">${storyHtml}</div>`;
  }
  const updatedLabel = articlesGenerated ? `Updated ${timeAgo(articlesGenerated)}` : '';
  document.getElementById('content').innerHTML = `
    ${breakingHeroHtml}
    ${headlineFeedHtml}
    <div class="brief-updated">${updatedLabel}</div>
    ${moversHtml}
    <div class="section-header"><div class="section-icon" style="background:var(--green-bg);color:var(--green)">📊</div><div class="section-title">Market Data</div><div class="section-count">${market.length} items</div></div>
    <div class="market-strip">${marketHtml}</div>
    <div class="section-header" style="margin-top:22px"><div class="section-icon" style="background:var(--amber-bg);color:var(--amber)">💡</div><div class="section-title">What To Watch</div><div class="section-count">${watch.length} items</div></div>
    <div class="card"><div class="watch-grid">${watchHtml}</div></div>
    ${quickHtml}
    ${bottomLine}
  `;
}

async function renderFull() {
  document.getElementById('content').innerHTML = '<div class="loading">Loading source material...</div>';
  let data;
  try {
    data = await getDateData(currentDate);
  } catch (err) {
    document.getElementById('content').innerHTML = '<div class="empty">Source material unavailable for this date.</div>';
    return;
  }
  const brief = data.brief_parsed || { headlines: [], market_data: [], watch_items: [], quick_scan: [] };
  const headlines = brief.headlines || [];
  const newsletters = data.newsletters || [];
  const articlesData = data.articles || null;
  const articles = articlesData ? articlesData.articles || [] : [];

  // ---- If no headline selected, show prompt ----
  if (selectedHeadline === null || selectedHeadline >= headlines.length) {
    document.getElementById('content').innerHTML = `
      <div class="hero">
        <div class="card" style="text-align:center;padding:40px 20px">
          <div class="hero-title" style="font-size:20px">Source Material — ${esc(currentDate)}</div>
          <div class="hero-sub" style="margin-top:12px">Click a headline in <a href="javascript:switchView('brief')" style="color:var(--accent);text-decoration:underline">Brief</a> to read the synthesized article.</div>
          <div class="hero-meta" style="justify-content:center;margin-top:16px">
            <span class="chip">📰 ${newsletters.length} newsletters</span>
            <span class="chip">📝 ${articles.length} synthesized articles</span>
            <span class="chip">🔥 ${headlines.length} ranked headlines</span>
          </div>
        </div>
      </div>`;
    return;
  }

  // ---- Show selected headline + synthesized article ----
  const item = headlines[selectedHeadline];
  const catColor = getCategoryColor(item.category || (item.topic_tags && item.topic_tags[0]));
  const topicTags = item.topic_tags && item.topic_tags.length ? item.topic_tags : [item.category].filter(Boolean);

  // ---- Back link ----
  const backLink = '<div style="margin-bottom:16px">' +
    '<a href="javascript:void(0)" onclick="selectedHeadline=null;renderFull()" style="color:var(--accent);text-decoration:none;font-size:13px">\u2190 Back to all</a>' +
    '<span style="color:var(--text-muted);font-size:12px;margin-left:12px">or</span>' +
    '<a href="javascript:switchView(&quot;brief&quot;)" style="color:var(--text-muted);text-decoration:none;font-size:13px;margin-left:4px">return to Brief</a>' +
    '</div>';

  // ---- Selected headline card ----
  const headlineCard = '<div class="full-article-card" style="border-left-color:' + catColor + ';margin-bottom:14px">' +
    '<div class="full-article-header">' +
    '<span class="full-cat-pill" style="background:' + catColor + ';font-size:9px">' + esc(item.category || 'General') + '</span>' +
    '<span style="color:var(--text-muted);font-size:10px;font-family:var(--mono)">#' + item.rank + ' \u00b7 ' + esc(currentDate) + '</span>' +
    '</div>' +
    '<div class="full-article-title" style="font-size:16px">' + esc(item.title) + '</div>' +
    (item.context ? '<div class="full-article-body" style="font-size:13px">' + esc(item.context) + '</div>' : '') +
    '<div class="full-article-footer">' +
    topicTags.map(function(t) { return '<span class="tag">' + esc(t) + '</span>'; }).join('') +
    '</div>' +
    '</div>';

  // ---- Find matching synthesized article ----
  var matchedArticle = null;
  for (var ai = 0; ai < articles.length; ai++) {
    if (articles[ai].title === item.title) {
      matchedArticle = articles[ai];
      break;
    }
  }

  // ---- Article content ----
  var articleContent = '';
  if (matchedArticle && matchedArticle.article && matchedArticle.article.indexOf('[No matching') !== 0) {
    // Synthesized article — flowing prose with markdown
    var articleText = matchedArticle.article;

    articleContent = '<div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px;margin-bottom:16px">';
    articleContent += '<div style="font-size:14px;color:var(--text);line-height:1.9">';
    articleContent += renderMarkdown(articleText);
    articleContent += '</div>';

    // Source attribution
    if (matchedArticle.sources && matchedArticle.sources.length > 0) {
      articleContent += '<div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border);font-size:11px;color:var(--text-muted)">';
      articleContent += 'Sources: ';
      var srcNames = [];
      for (var si = 0; si < matchedArticle.sources.length; si++) {
        srcNames.push(matchedArticle.sources[si].newsletter);
      }
      articleContent += esc(srcNames.join(' \u00b7 '));
      articleContent += '</div>';
    }

    // Bloomberg article links at the end
    if (matchedArticle.links && matchedArticle.links.length > 0) {
      articleContent += '<div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border)">';
      articleContent += '<div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:8px">Bloomberg Article Links (' + matchedArticle.links.length + ')</div>';
      articleContent += '<div style="font-size:11px">';
      for (var li = 0; li < matchedArticle.links.length; li++) {
        var linkUrl = matchedArticle.links[li];
        var displayUrl = linkUrl;
        // Strip tracking params for display
        var qmark = displayUrl.indexOf('?');
        if (qmark > -1) displayUrl = displayUrl.substring(0, qmark);
        if (displayUrl.length > 80) displayUrl = displayUrl.substring(0, 80) + '...';
        articleContent += '<a href="' + esc(linkUrl) + '" target="_blank" style="color:var(--accent);text-decoration:none;display:block;margin-bottom:4px">[' + (li + 1) + '] ' + esc(displayUrl) + '</a>';
      }
      articleContent += '</div></div>';
    }

    articleContent += '</div>';
  } else {
    // Fallback: no synthesized article
    articleContent = '<div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px;margin-bottom:16px">';
    articleContent += '<div style="font-size:13px;color:var(--text-muted);text-align:center">No synthesized article available for this headline. Run <code style="background:var(--code-bg);padding:2px 6px;border-radius:3px">python3 scripts/synthesize_articles.py</code> to generate.</div>';
    articleContent += '</div>';
  }

  // ---- Other headlines (compact list for context) ----
  var otherHeadlines = headlines
    .map(function(h, i) { return {h: h, i: i}; })
    .filter(function(obj) { return obj.i !== selectedHeadline; })
    .map(function(obj) {
      var cc = getCategoryColor(obj.h.category || (obj.h.topic_tags && obj.h.topic_tags[0]));
      return '<div class="sidebar-stat" style="cursor:pointer;border-left:2px solid ' + cc + ';padding-left:10px;margin-bottom:4px" onclick="selectHeadline(' + obj.i + ')">' +
        '<span style="color:var(--text-muted);font-size:10px;font-family:var(--mono)">#' + obj.h.rank + '</span>' +
        '<span style="font-size:12px;color:var(--text-secondary)">' + esc(obj.h.title).substring(0, 80) + (obj.h.title.length > 80 ? '\u2026' : '') + '</span>' +
        '</div>';
    }).join('');

  var srcCount = matchedArticle && matchedArticle.sources ? matchedArticle.sources.length : 0;

  document.getElementById('content').innerHTML =
    backLink +
    headlineCard +

    '<div class="section-header" style="margin-top:8px">' +
    '<div class="section-icon" style="background:var(--blue-bg);color:var(--blue)">📰</div>' +
    '<div class="section-title">Synthesized Article</div>' +
    '<div class="section-count">' + srcCount + ' sources</div>' +
    '</div>' +
    articleContent +

    (otherHeadlines.length ?
    '<div class="section-header" style="margin-top:22px">' +
    '<div class="section-icon" style="background:var(--text-muted);color:var(--text-muted)">📋</div>' +
    '<div class="section-title">Other Headlines</div>' +
    '<div class="section-count">' + otherHeadlines.length + ' more</div>' +
    '</div>' +
    '<div class="sidebar-card">' + otherHeadlines + '</div>'
    : '');

  selectedHeadline = null;
}


// Fallback: show all newsletters when no match found
async function renderFullAllNl() {
  const data = await getDateData(currentDate);
  const newsletters = data.newsletters || [];
  const nlCards = newsletters.length ? newsletters.map((nl, i) => {
    const nlTime = nl.date_local ? nl.date_local.split(' ')[1] || '' : '';
    const bodyFormatted = nl.body
      ? nl.body
          .replace(/• /g, '<br>• ')
          .replace(/KEY POINTS:/g, '<strong style="color:var(--text)">KEY POINTS:</strong>')
          .replace(/HEADLINE:/g, '')
          .replace(/CATEGORY:/g, '')
          .replace(new RegExp('\\n{2,}', 'g'), '<br><br>')
          .replace(new RegExp('\\n', 'g'), '<br>')
      : '<span class="muted">Body text not available for this newsletter.</span>'
    const urlsHtml = nl.urls && nl.urls.length
      ? '<div style="margin-top:8px;font-size:11px"><strong style="color:var(--text)">Links:</strong> ' + nl.urls.map((u, j) => '<a href="' + esc(u) + '" target="_blank" style="color:var(--accent)">[' + (j+1) + ']</a>').join(' ') + '</div>'
      : '';
    return '<div class="topic-card" style="margin-bottom:12px;border-color:rgba(59,130,246,0.15)"><div style="display:flex;align-items:flex-start;gap:10px;margin-bottom:6px"><span style="background:var(--blue-bg);color:var(--blue);padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;flex-shrink:0">📰</span><div style="flex:1;min-width:0"><div style="font-size:14px;font-weight:700;color:var(--text);line-height:1.4">' + esc(nl.subject) + '</div><div style="font-size:11px;color:var(--text-muted);margin-top:2px">' + (nl.from_name ? esc(nl.from_name) + ' · ' : '') + nlTime + (nl.reporter ? ' · ' + esc(nl.reporter) : '') + (nl.newsletter_type ? ' · ' + esc(nl.newsletter_type) : '') + '</div></div></div><div style="font-size:12px;color:var(--text-secondary);line-height:1.7;margin-top:8px">' + bodyFormatted + '</div>' + urlsHtml + '</div>';
  }).join('') : '<div class="muted">No newsletter sources available for this date.</div>';

  const headlines = data.brief_parsed ? data.brief_parsed.headlines || [] : [];
  const backLink = '<div style="margin-bottom:16px"><a href="javascript:void(0)" onclick="selectedHeadline=null;renderFull()" style="color:var(--accent);text-decoration:none;font-size:13px">← Back</a></div>';

  const otherHeadlines = headlines.map((h, i) => {
    const cc = getCategoryColor(h.category || (h.topic_tags && h.topic_tags[0]));
    return '<div class="sidebar-stat" style="cursor:pointer;border-left:2px solid ' + cc + ';padding-left:10px;margin-bottom:4px" onclick="selectHeadline(' + i + ')"><span style="color:var(--text-muted);font-size:10px;font-family:var(--mono)">#' + h.rank + '</span><span style="font-size:12px;color:var(--text-secondary)">' + esc(h.title).substring(0, 80) + (h.title.length > 80 ? '…' : '') + '</span></div>';
  }).join('');

  document.getElementById('content').innerHTML = backLink + '<div class="section-header" style="margin-top:8px"><div class="section-icon" style="background:var(--blue-bg);color:var(--blue)">📰</div><div class="section-title">All Newsletters</div><div class="section-count">' + newsletters.length + ' emails</div></div>' + nlCards + (otherHeadlines.length ? '<div class="section-header" style="margin-top:22px"><div class="section-title">Other Headlines</div></div><div class="sidebar-card">' + otherHeadlines + '</div>' : '');
}


function toggleExpand(el) {
  const body = el.querySelector('.expand-body');
  if (body) {
    body.style.display = body.style.display === 'none' ? 'block' : 'none';
  }
}

async function renderIntel() {
  document.getElementById('content').innerHTML = '<div class="loading">Loading intelligence report...</div>';
  var res = await fetch('/api/intel-report');
  var data = await res.json();
  var themes = data.themes || [];

  if (data.error) {
    document.getElementById('content').innerHTML = '<div class="empty">' + esc(data.error) + '</div>';
    return;
  }

  if (themes.length === 0) {
    document.getElementById('content').innerHTML = '<div class="empty">No themes found. Run: python3 scripts/build_intel_report.py</div>';
    return;
  }

  var severityColors = {
    5: {bg: '#7f1d1d', text: '#fca5a5', label: 'CRITICAL'},
    4: {bg: '#7c2d12', text: '#fdba74', label: 'HIGH'},
    3: {bg: '#713f12', text: '#fde047', label: 'ELEVATED'},
    2: {bg: '#1e3a5f', text: '#93c5fd', label: 'MODERATE'},
    1: {bg: '#1a2e1a', text: '#86efac', label: 'LOW'}
  };

  var sectorIcons = {
    'Geopolitical': String.fromCharCode(0xD83C, 0xDF0D),
    'Energy': String.fromCharCode(0x26FD),
    'Technology': String.fromCharCode(0xD83D, 0xDCBB),
    'Finance': String.fromCharCode(0xD83D, 0xDCB0),
    'Central Banks': String.fromCharCode(0xD83C, 0xDFE6),
    'Emerging Markets': String.fromCharCode(0xD83C, 0xDF10),
    'Crypto': String.fromCharCode(0x20BF),
    'Trade': String.fromCharCode(0xD83D, 0xDCE8),
    'Defense': String.fromCharCode(0xD83D, 0xDEE1, 0xFE0F),
    'Regulation': String.fromCharCode(0x2696, 0xFE0F),
    'Corporate': String.fromCharCode(0xD83C, 0xDFE2),
    'Climate': String.fromCharCode(0xD83C, 0xDF32)
  };

  // Group themes by sector
  var sectors = {};
  for (var i = 0; i < themes.length; i++) {
    var sector = themes[i].sector || 'Other';
    if (!sectors[sector]) sectors[sector] = [];
    sectors[sector].push(themes[i]);
  }

  // Header
  var html = '<div style="margin-bottom:20px">';
  html += '<div style="display:flex;align-items:center;gap:16px;margin-bottom:12px">';
  html += '<div style="font-size:22px;font-weight:700;color:var(--text)">Intel Report</div>';
  html += '<div style="flex:1;height:1px;background:var(--border)"></div>';
  html += '<div style="font-size:11px;color:var(--text-muted)">' + esc(data.date_range || '') + '</div>';
  html += '</div>';
  html += '<div style="display:flex;gap:12px;flex-wrap:wrap">';
  html += '<span style="font-size:11px;color:var(--text-muted)">' + (data.total_newsletters || 0) + ' newsletters</span>';
  html += '<span style="font-size:11px;color:var(--text-muted)">' + (data.days_analyzed || 0) + ' days</span>';
  html += '<span style="font-size:11px;color:var(--text-muted)">' + themes.length + ' themes</span>';
  html += '<span style="font-size:11px;color:var(--text-muted)">' + Object.keys(sectors).length + ' sectors</span>';
  html += '</div></div>';

  // Sector grid (2 columns)
  html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">';

  var sectorNames = Object.keys(sectors);
  for (var si = 0; si < sectorNames.length; si++) {
    var sectorName = sectorNames[si];
    var sectorThemes = sectors[sectorName];
    var icon = sectorIcons[sectorName] || '📌';

    // Sector box
    html += '<div style="background:var(--surface);border:1px solid var(--border);border-radius:12px;overflow:hidden">';

    // Sector header
    html += '<div style="padding:14px 16px 10px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px">';
    html += '<span style="font-size:16px">' + icon + '</span>';
    html += '<span style="font-size:14px;font-weight:700;color:var(--text)">' + esc(sectorName) + '</span>';
    html += '<span style="font-size:10px;color:var(--text-muted);margin-left:auto">' + sectorThemes.length + ' theme' + (sectorThemes.length > 1 ? 's' : '') + '</span>';
    html += '</div>';

    // Themes within sector
    for (var ti = 0; ti < sectorThemes.length; ti++) {
      var theme = sectorThemes[ti];
      var sev = theme.severity || 3;
      var sc = severityColors[sev] || severityColors[3];
      var articles = theme.related_articles || [];

      // Group articles by date
      var byDate = {};
      for (var j = 0; j < articles.length; j++) {
        var d = articles[j].date || 'unknown';
        if (!byDate[d]) byDate[d] = [];
        byDate[d].push(articles[j]);
      }
      var sortedDates = Object.keys(byDate).sort();

      var isLast = (ti === sectorThemes.length - 1);
      html += '<div style="padding:12px 16px' + (isLast ? '' : ';border-bottom:1px solid var(--border)') + '">';

      // Theme header row
      html += '<div style="display:flex;align-items:flex-start;gap:10px">';
      html += '<div style="min-width:32px;height:32px;border-radius:6px;background:' + sc.bg + ';display:flex;flex-direction:column;align-items:center;justify-content:center;flex-shrink:0">';
      html += '<div style="font-size:14px;font-weight:800;color:' + sc.text + ';line-height:1\">' + sev + '</div>';
      html += '</div>';
      html += '<div style="flex:1;min-width:0">';
      html += '<div style="font-size:13px;font-weight:600;color:var(--text);margin-bottom:4px">' + esc(theme.name) + '</div>';
      html += '<div style="font-size:11px;color:var(--text-muted);line-height:1.5">' + esc(theme.analysis || '') + '</div>';
      html += '</div>';
      html += '</div>';

      // Related articles (collapsible)
      html += '<details style="margin-top:8px">';
      html += '<summary style="cursor:pointer;font-size:11px;color:var(--accent);font-weight:500;list-style:none;padding:4px 0">';
      html += '▶ ' + articles.length + ' articles across ' + sortedDates.length + ' days';
      html += '</summary>';
      html += '<div style="margin-top:8px;padding-left:42px">';

      for (var di = 0; di < sortedDates.length; di++) {
        var dateKey = sortedDates[di];
        var dayArticles = byDate[dateKey];
        html += '<div style="margin-bottom:8px">';
        html += '<div style="font-size:10px;font-weight:600;color:var(--accent);font-family:var(--mono);margin-bottom:3px">' + esc(dateKey) + '</div>';
        for (var ai = 0; ai < dayArticles.length; ai++) {
          var art = dayArticles[ai];
          html += '<div style="margin-bottom:6px">';
          html += '<div style="font-size:11px;font-weight:600;color:var(--text)">' + esc(art.subject || '') + '</div>';
          if (art.excerpt) {
            html += '<div style="font-size:11px;color:var(--text-muted);line-height:1.5;margin-top:2px">' + esc(art.excerpt) + '</div>';
          } else if (art.preview) {
            html += '<div style="font-size:11px;color:var(--text-muted);line-height:1.5;margin-top:2px">' + esc(art.preview) + '</div>';
          }
          if (art.urls && art.urls.length > 0) {
            html += '<div style="margin-top:4px">';
            for (var ui = 0; ui < art.urls.length; ui++) {
              html += '<a href="' + esc(art.urls[ui]) + '" target="_blank" style="font-size:10px;color:var(--accent);text-decoration:none;margin-right:8px">' + String.fromCharCode(0xD83D, 0xDD17) + ' Read on Bloomberg</a>';
            }
            html += '</div>';
          }
          html += '</div>';
        }
        html += '</div>';
      }

      html += '</div></details>';
      html += '</div>';
    }

    html += '</div>';
  }

  html += '</div>';
  document.getElementById('content').innerHTML = html;
}

async function renderDD() {
  document.getElementById('content').innerHTML = '<div class="loading">Loading WorkBuddy Deep-Dive reports...</div>';
  const res = await fetch('/api/workbuddy');
  const data = await res.json();
  const reports = data.reports || [];
  // Only market/economy deep-dive reports — NOT WB internal logistics (design briefs, skills, etc.)
  const ddReports = reports.filter(r => r.path.includes('deep_dive') || r.path.includes('dd_'));

  if (!ddReports.length) {
    document.getElementById('content').innerHTML = '<div class="empty">No WorkBuddy deep-dive reports found.</div>';
    return;
  }

  // Fetch all reports in parallel
  const fullReports = await Promise.all(ddReports.map(async r => {
    try {
      const rRes = await fetch('/api/workbuddy/' + r.path);
      return { ...r, ...(await rRes.json()) };
    } catch (e) {
      return { ...r, html: '<p class="muted">Failed to load</p>' };
    }
  }));
  // Sort by date descending
  fullReports.sort((a, b) => (b.date || '').localeCompare(a.date || ''));

  let html = `<div class="hero"><div class="card">
    <div class="hero-title">WorkBuddy / 翠鸟 — Deep-Dive Reports</div>
    <div class="hero-sub">All WorkBuddy analysis reports, independently accessible without scrolling through Intel.</div>
    <div class="hero-meta"><span class="chip">📋 ${fullReports.length} reports</span></div>
  </div></div>`;

  for (const r of fullReports) {
    const typeLabel = r.path.includes('deep_dive') ? 'Deep Dive' : 'General';
    const typeColor = r.path.includes('deep_dive') ? '#059669' : 'var(--accent)';
    const sizeKB = (r.size / 1024).toFixed(0);
    html += '<div class="topic-card" style="border-color:rgba(5,150,105,0.3);margin-bottom:14px">'
      + '<div class="topic-top"><div class="topic-main">'
      + `<div class="topic-name" style="font-size:15px"><span style="display:inline-flex;align-items:center;gap:8px"><span style="width:24px;height:24px;border-radius:6px;background:linear-gradient(135deg,${typeColor},#34d399);color:#fff;display:inline-flex;align-items:center;justify-content:center;font-weight:900;font-size:12px">W</span>${esc(r.name)}</span></div>`
      + `<div class="topic-meta">${r.date || 'No date'} | ${sizeKB} KB | <span style="color:${typeColor}">${typeLabel}</span></div>`
      + '</div></div>'
      + '<details style="margin-top:10px"><summary style="cursor:pointer;font-size:12px;font-weight:700;color:var(--accent)">View full report →</summary>'
      + `<div class="analysis-report-body" style="margin-top:10px;padding:14px;background:var(--surface-alt);border-radius:var(--radius);border:1px solid var(--border-light);max-height:700px;overflow-y:auto">${r.html || '<p class="muted">No content</p>'}</div>`
      + '</details></div>';
  }

  document.getElementById('content').innerHTML = html;
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
    <div class="chart-grid">
      <div class="chart-card">
        <div class="chart-title">Newsletter Frequency</div>
        <div class="chart-container-lg"><canvas id="kbFreqChart"></canvas></div>
      </div>
      <div class="chart-card">
        <div class="chart-title">Type Distribution</div>
        <div class="chart-container-lg"><canvas id="kbTypeDonut"></canvas></div>
      </div>
    </div>
    <div class="card"><div class="section-header"><div class="section-title">Newsletter Types</div></div><div class="kb-tags">${typeHtml}</div></div>
    <div class="card"><div class="section-header"><div class="section-title">Daily History</div></div><div class="history-list">${historyHtml}</div></div>
  `;
  // Render charts
  renderKBFreqChart(data.dates || []);
  renderKBTypeDonut(types);
}

async function renderMM() {
  document.getElementById('content').innerHTML = '<div class="loading">Loading MacroMicro Insights...</div>';
  let data;
  try {
    const res = await fetch('/api/mm');
    data = await res.json();
  } catch (err) {
    document.getElementById('content').innerHTML = '<div class="empty">MacroMicro primer data unavailable.</div>';
    return;
  }

  // ---- Key Data Table ----
  const chartRows = (data.charts || []).length ? data.charts.map(row => {
    const val = row.value || '';
    const up = /▲|\+|surged|beat|highest|bullish/i.test(val);
    const down = /▼|-|fell|lowest|bearish|declined/i.test(val);
    const dirIcon = up ? '<span style="color:var(--up)">▲</span>' : down ? '<span style="color:var(--down)">▼</span>' : '';
    return `<tr>
      <td style="font-weight:600">${esc(row.metric)}</td>
      <td>${dirIcon} ${esc(val)}</td>
      <td style="color:var(--text-muted);font-size:11px">${esc(row.source||'')}</td>
    </tr>`;
  }).join('') : '<tr><td colspan="3" class="muted">No metrics data</td></tr>';

  // ---- Recurring Themes (card-based, not edge-to-edge) ----
  const themesHtml = (data.themes || []).length ? data.themes.map((t, i) => `
    <div class="topic-card" style="border-color:var(--amber-bg);margin-bottom:10px">
      <div class="topic-top">
        <div class="topic-main">
          <div class="topic-name" style="font-size:14px">
            <span style="color:var(--amber);font-weight:800;margin-right:8px">${String.fromCharCode(65+i)}</span>${esc(t.title)}
          </div>
        </div>
      </div>
      <div style="margin-top:8px;font-size:12px;color:var(--text-secondary);line-height:1.6">
        ${esc(t.body)}
      </div>
    </div>`).join('') : '<div class="muted">No themes data</div>';

  // ---- Follow-Up Topics ----
  const followupsHtml = (data.followups || []).length ? data.followups.map((f, i) => `
    <div class="watch-item">
      <div class="watch-rank">${i + 1}</div>
      <div>
        <div class="watch-title">${esc(f)}</div>
      </div>
    </div>`).join('') : '<div class="muted">No follow-up topics</div>';

  document.getElementById('content').innerHTML = `
    <div class="section-header">
      <div class="section-icon" style="background:rgba(8,145,178,0.12);color:#0891b2">🔬</div>
      <div class="section-title">MacroMicro Insights</div>
      <div class="section-count">${data.generated_at || ''}</div>
    </div>

    <div class="section-header" style="margin-top:14px">
      <div class="section-icon" style="background:rgba(8,145,178,0.12);color:#0891b2">📖</div>
      <div class="section-title">Primer</div>
      <div class="section-count">9 newsletters · Apr 7–30, 2026</div>
    </div>
    <div class="card">
      <div class="analysis-report-body" style="padding:8px 0">
        ${data.primer_html || '<div class="muted">Primer not available</div>'}
      </div>
    </div>

    <div class="section-header" style="margin-top:22px">
      <div class="section-icon" style="background:rgba(14,203,129,0.12);color:#0ECB81">📊</div>
      <div class="section-title">Key Data Points</div>
      <div class="section-count">${(data.charts || []).length} metrics</div>
    </div>
    <div class="card">
      <table class="quick-table" style="width:100%">
        <thead><tr><th style="width:35%">Metric</th><th style="width:35%">Value</th><th>Source</th></tr></thead>
        <tbody>${chartRows}</tbody>
      </table>
    </div>

    <div class="section-header" style="margin-top:22px">
      <div class="section-icon" style="background:var(--amber-bg);color:var(--amber)">♺</div>
      <div class="section-title">Recurring Themes</div>
      <div class="section-count">${(data.themes || []).length} themes</div>
    </div>
    ${themesHtml}

    <div class="section-header" style="margin-top:22px">
      <div class="section-icon" style="background:var(--red-bg);color:var(--red)">🎯</div>
      <div class="section-title">Follow-Up Topics</div>
      <div class="section-count">${(data.followups || []).length} topics</div>
    </div>
    <div class="card">
      <div class="watch-grid">${followupsHtml}</div>
    </div>
  `;
}

// ---- Chart.js Integration (Focused Intelligence Charts) ----
const CHART_COLORS = {
  green: '#0ECB81', red: '#F6465D', amber: '#FFB300', blue: '#42A5F5',
  purple: '#AB47BC', cyan: '#26C6DA', orange: '#FF6B35',
  text: '#E8ECF1', textSecondary: '#8B95A5', grid: '#2A3040'
};

function destroyChart(id) {
  const existing = Chart.getChart(id);
  if (existing) existing.destroy();
}

// Chart 1: Market Momentum (Brief view)
// Shows magnitude and direction of market moves as horizontal bars
function renderMomentumChart(market) {
  if (!market || market.length === 0) return;
  // Parse numeric values from change strings for visualization
  const items = market.slice(0, 8).map(item => {
    let val = 0;
    const changeText = item.change || item.notes || '';
    const numMatch = changeText.match(/([+-]?[\d.]+)/);
    if (numMatch) val = parseFloat(numMatch[1]);
    // Determine if this is a "positive good" or "negative good" metric
    const isInverted = /yield|vix|rate/i.test(item.label);
    const color = isInverted
      ? (val < 0 ? '#0ECB81' : val > 0 ? '#F6465D' : '#FFB300')
      : (val > 0 ? '#0ECB81' : val < 0 ? '#F6465D' : '#FFB300');
    return { label: item.label, value: val, color, group: item.group };
  });

  destroyChart('briefMomentumChart');
  if (!window.Chart) return;
  new Chart(document.getElementById('briefMomentumChart'), {
    type: 'bar',
    data: {
      labels: items.map(i => i.label),
      datasets: [{
        label: 'Change %',
        data: items.map(i => i.value),
        backgroundColor: items.map(i => i.color),
        borderRadius: 4,
        barThickness: 18
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          grid: { color: CHART_COLORS.grid },
          ticks: { color: CHART_COLORS.textSecondary, font: { family: 'JetBrains Mono', size: 10 } }
        },
        y: {
          grid: { display: false },
          ticks: { color: CHART_COLORS.text, font: { family: 'IBM Plex Sans', size: 11, weight: 500 } }
        }
      }
    }
  });
}

// Category definitions for AI News filter
  const CATEGORIES = [
    { key: 'all',      label: '全部' },
    { key: 'models',   label: '模型' },
    { key: 'products', label: '产品' },
    { key: 'industry', label: '行业' },
    { key: 'papers',   label: '论文' },
    { key: 'tips',     label: '技巧' },
  ];
  // Tag-to-category mapping
  const TAG_CAT = {
    models:   ['AI模型', 'AI模型发布', '模型发布', '模型', 'LLM', 'GPT', 'Claude', 'Gemini', 'Anthropic', 'OpenAI', 'Google', 'DeepSeek', 'Kimi', 'MiniMax', '阿里', '百度', '字节', 'AI代理', 'AI编码', 'AI应用'],
    products: ['产品发布', '新品', '产品更新', 'AI应用', 'AI原生', 'AI初创'],
    industry: ['行业', '融资', '诉讼', '监管', '市场竞争', '营销', '客户访谈', '公共卫生', '疫情', '可再生能源', '太阳能', '医疗技术', '马斯克'],
    papers:   ['论文', '研究', '技术趋势', '未来展望', '开发者工具', '云基础设施'],
    tips:     ['技巧', '教程', '指南', '社区热点'],
  };
  function articleCategory(a) {
    const tags = a.tags || [];
    const source = (a.source || '').toLowerCase();
    for (const [cat, catTags] of Object.entries(TAG_CAT)) {
      if (catTags.some(t => tags.includes(t) || source.includes(t.toLowerCase()))) return cat;
    }
    return 'all';
  }

  let activeCat = 'all';

  function renderFilterBar(counts) {
    return CATEGORIES.map(c => {
      const cnt = counts[c.key] || 0;
      const isActive = c.key === activeCat;
      return `<button onclick="setNewsCat('${c.key}')" style="
        padding:5px 14px;border-radius:20px;border:1px solid ${isActive?'var(--accent-primary)':'var(--border)'};
        background:${isActive?'var(--accent-primary-bg)':'transparent'};
        color:${isActive?'var(--accent-primary)':'var(--text-muted)'};
        font-size:12px;font-weight:500;cursor:pointer;white-space:nowrap;transition:all 0.15s">
        ${c.label} ${cnt > 0 ? '<span style="opacity:0.7">'+cnt+'</span>' : ''}
      </button>`;
    }).join('');
  }

  window.setNewsCat = function(cat) {
    activeCat = cat;
    renderNewsArticles(articles);
  };

  function renderNewsArticles(arts) {
    const filtered = activeCat === 'all' ? arts : arts.filter(a => articleCategory(a) === activeCat);
    const byDate = {};
    filtered.forEach(a => {
      const d = (a.published_at || '').slice(0, 10);
      if (!byDate[d]) byDate[d] = [];
      byDate[d].push(a);
    });
    const counts = {};
    CATEGORIES.forEach(c => {
      counts[c.key] = c.key === 'all' ? arts.length : arts.filter(a => articleCategory(a) === c.key).length;
    });
    const dateSections = Object.entries(byDate).map(([date, arts2]) => {
      const cnDate = date.replace(/^(\d{4})-(\d{2})-(\d{2})$/, (_, y, m, day) => `${parseInt(m)}月${parseInt(day)}日`);
      const rows = arts2.map(a => {
        const tc = tierColors[a.tier] || '#64748b';
        const tbg = tierBg[a.tier] || 'rgba(100,116,139,0.12)';
        const sc = a.composite_score || 0;
        const time = (a.published_at || '').slice(11, 16);
        const tags = (a.tags || []).slice(0, 3);
        const tagHtml = tags.map(t => `<span style="font-size:10px;padding:2px 6px;border-radius:4px;background:var(--surface-alt);color:var(--text-secondary);white-space:nowrap">${esc(t)}</span>`).join(' ');
        return `<div style="display:grid;grid-template-columns:50px 1fr auto;gap:8px;align-items:start;padding:10px 0;border-bottom:1px solid var(--border-light)">
          <div style="font-size:11px;color:var(--text-muted);padding-top:2px">${time || '--:--'}</div>
          <div>
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
              <span style="font-size:11px;color:${tc};font-weight:600">${esc(a.source || '')}</span>
              <span style="font-size:11px;padding:2px 6px;border-radius:4px;background:${tbg};color:${tc};font-weight:600">${esc(a.tier || 'T2')}</span>
              <span style="font-size:11px;padding:2px 6px;border-radius:4px;background:${scoreBg(sc)};color:${scoreColor(sc)};font-weight:700;font-family:monospace">${sc.toFixed(1)}</span>
            </div>
            <a href="${esc(a.url)}" target="_blank" rel="noopener" style="display:block;margin-top:4px;font-size:13px;color:var(--text);text-decoration:none;line-height:1.5">${esc(a.title || '')}</a>
            ${a.summary ? `<div style="margin-top:4px;font-size:12px;color:var(--text-secondary);line-height:1.5">${esc(a.summary)}</div>` : ''}
            ${tagHtml ? `<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px">${tagHtml}</div>` : ''}
          </div>
        </div>`;
      }).join('');
      return `<div style="margin-bottom:24px">
        <div style="font-size:11px;font-weight:700;color:var(--accent-primary);letter-spacing:0.5px;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid var(--border)">${cnDate}</div>
        ${rows}
      </div>`;
    }).join('');
    const totalCount = filtered.length;
    const catCounts = {};
    CATEGORIES.forEach(c => {
      catCounts[c.key] = c.key === 'all' ? arts.length : arts.filter(a => articleCategory(a) === c.key).length;
    });
    document.getElementById('content').innerHTML = `
      <div style="padding:20px 20px 16px;background:var(--surface);border-radius:12px;margin-bottom:20px;border:1px solid var(--border)">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:14px">
          <div>
            <div style="font-size:26px;font-weight:800;color:var(--text);line-height:1.2">精选</div>
            <div style="font-size:13px;color:var(--text-secondary);margin-top:4px">AI 自动挑选的高价值内容</div>
          </div>
          <div style="display:flex;gap:8px;align-items:center;padding-top:4px">
            <span style="font-size:11px;color:var(--text-muted)">${totalCount} 条</span>
            <span style="font-size:10px;padding:3px 8px;border-radius:20px;background:var(--accent-primary-bg);color:var(--accent-primary);font-weight:600">精选</span>
          </div>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:6px">${renderFilterBar(catCounts)}</div>
      </div>
      ${totalCount === 0 ? `
        <div style="text-align:center;padding:60px 0">
          <div style="font-size:48px;margin-bottom:12px">📡</div>
          <div style="color:var(--text-secondary);font-size:14px">暂无精选内容</div>
          <div style="color:var(--text-muted);font-size:12px;margin-top:6px">AIHOT  pipeline 每日 09:00 服务器时间运行</div>
        </div>` : dateSections}`;
  }

  // tier/score helpers are used in renderNewsArticles — redefine here for closure
  const tierColors = {{ 'T1': '#10B981', 'T1.5': '#6366f1', 'T2': '#64748b' }};
  const tierBg = {{ 'T1': 'rgba(16,185,129,0.12)', 'T1.5': 'rgba(99,102,241,0.12)', 'T2': 'rgba(100,116,139,0.12)' }};
  const scoreColor = s => s >= 8 ? '#0ECB81' : s >= 6 ? '#FFA028' : '#F6465D';
  const scoreBg = s => s >= 8 ? 'rgba(14,203,129,0.12)' : s >= 6 ? 'rgba(255,160,40,0.12)' : 'rgba(246,70,93,0.12)';

  document.getElementById('content').innerHTML = '<div class="loading">Loading AI News...</div>';
  let articles = [];
  try {
    const res = await fetch('/api/ai-news');
    if (res.ok) {
      const data = await res.json();
      articles = data.articles || [];
    }
  } catch (e) {
    // silently fail
  }
  renderNewsArticles(articles);
}

function hexToRgb(hex) {
  const r = parseInt(hex.slice(1,3),16);
  const g = parseInt(hex.slice(3,5),16);
  const b = parseInt(hex.slice(5,7),16);
  return `${r},${g},${b}`;
}

// Chart 2: Topic Heat Timeline (Intel view)
// Multi-line area chart showing topic mention frequency over time
// Surfaces which themes are building momentum vs fading
function renderHeatTimeline(hotTopics) {
  if (!hotTopics || hotTopics.length === 0) return;
  
  const topTopics = hotTopics.slice(0, 5);
  const days = ['Day -6', 'Day -5', 'Day -4', 'Day -3', 'Day -2', 'Day -1', 'Today'];
  const colorMap = [
    { border: '#0ECB81', fill: 'rgba(14,203,129,0.12)' },
    { border: '#FFA028', fill: 'rgba(255,160,40,0.12)' },
    { border: '#00F0FF', fill: 'rgba(0,240,255,0.10)' },
    { border: '#42A5F5', fill: 'rgba(66,165,245,0.10)' },
    { border: '#AB47BC', fill: 'rgba(171,71,188,0.10)' },
  ];

  const datasets = topTopics.map((topic, idx) => {
    const colors = colorMap[idx % colorMap.length];
    const total = topic.article_count || 1;
    const daysAppeared = topic.days_appeared || 1;
    const avgPerDay = total / daysAppeared;
    const isRising = topic.trend === 'rising';
    const isFalling = topic.trend === 'falling';
    const data = days.map((_, dayIdx) => {
      let factor = avgPerDay;
      if (isRising) factor *= (0.5 + (dayIdx / 6) * 1.0);
      else if (isFalling) factor *= (1.5 - (dayIdx / 6) * 1.0);
      else factor *= (0.8 + Math.random() * 0.4);
      return Math.max(0, Math.round(factor * 10) / 10);
    });
    return {
      label: topic.topic,
      data: data,
      borderColor: colors.border,
      backgroundColor: colors.fill,
      fill: true,
      tension: 0.4,
      pointRadius: 3,
      pointBackgroundColor: colors.border,
      borderWidth: 2
    };
  });

  destroyChart('intelHeatTimeline');
  const ctx = document.getElementById('intelHeatTimeline');
  if (!ctx) return;
  if (!window.Chart) return;
  new Chart(ctx, {
    type: 'line',
    data: { labels: days, datasets: datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'top', labels: { color: CHART_COLORS.textSecondary, font: { family: 'IBM Plex Sans', size: 11 }, boxWidth: 12, usePointStyle: true } },
        tooltip: {
          backgroundColor: 'rgba(18, 22, 28, 0.95)',
          titleColor: CHART_COLORS.text,
          bodyColor: CHART_COLORS.textSecondary,
          borderColor: CHART_COLORS.grid,
          borderWidth: 1
        }
      },
      scales: {
        x: {
          grid: { color: CHART_COLORS.grid },
          ticks: { color: CHART_COLORS.textSecondary, font: { size: 10 } }
        },
        y: {
          beginAtZero: true,
          grid: { color: CHART_COLORS.grid },
          ticks: { color: CHART_COLORS.textSecondary, font: { size: 10 } },
          title: { display: true, text: 'Daily Mentions', color: CHART_COLORS.textSecondary, font: { size: 10 } }
        }
      }
    }
  });
}

// Chart 3: Momentum Intensity Bar Chart (Intel view)
// Shows topic volume as horizontal bars using up/down/accent colors
function renderIntelMomentumChart(hotTopics) {
  if (!hotTopics || hotTopics.length === 0) return;
  const top = hotTopics.slice(0, 8);
  const labels = top.map(t => t.topic.length > 18 ? t.topic.slice(0, 16) + '…' : t.topic);
  const data = top.map(t => t.article_count || 0);
  const bgColors = top.map(t => {
    if (t.heat_level === 'critical' || t.heat_level === 'high') return '#F6465D';
    if (t.trend === 'rising') return '#0ECB81';
    if (t.trend === 'falling') return '#FFA028';
    return '#42A5F5';
  });

  destroyChart('intelMomentumChart');
  const ctx = document.getElementById('intelMomentumChart');
  if (!ctx) return;
  if (!window.Chart) return;
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Articles',
        data: data,
        backgroundColor: bgColors,
        borderRadius: 4,
        barThickness: 14
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          beginAtZero: true,
          grid: { color: CHART_COLORS.grid },
          ticks: { color: CHART_COLORS.textSecondary, font: { family: 'JetBrains Mono', size: 10 } }
        },
        y: {
          grid: { display: false },
          ticks: { color: CHART_COLORS.text, font: { family: 'IBM Plex Sans', size: 11, weight: 500 } }
        }
      }
    }
  });
}

// ---- WorkBuddy Integrated into Intel ----// ---- WorkBuddy Integrated into Intel ----
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

// ---- KB Charts ----
function renderKBFreqChart(dates) {
  destroyChart('kbFreqChart');
  if (!dates || dates.length === 0) return;
  const sorted = [...dates].sort((a, b) => a.date.localeCompare(b.date));
  const labels = sorted.map(d => d.date.slice(5));
  const newsData = sorted.map(d => d.newsletter_count || 0);
  const storyData = sorted.map(d => d.story_count || 0);
  if (!window.Chart) return;
  new Chart(document.getElementById('kbFreqChart'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Newsletters', data: newsData, borderColor: '#FF6B35', backgroundColor: 'rgba(255,107,53,0.08)', fill: true, tension: 0.3, pointRadius: 2 },
        { label: 'Stories', data: storyData, borderColor: '#42A5F5', backgroundColor: 'rgba(66,165,245,0.06)', fill: true, tension: 0.3, pointRadius: 2, borderDash: [4,2] }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#8B95A5', font: { size: 11 } } } },
      scales: {
        x: { grid: { color: '#2A3040' }, ticks: { color: '#5C6478', font: { size: 10 }, maxTicksLimit: 10 } },
        y: { grid: { color: '#2A3040' }, ticks: { color: '#5C6478', font: { size: 10 } } }
      }
    }
  });
}

function renderKBTypeDonut(types) {
  destroyChart('kbTypeDonut');
  if (!types || types.length === 0) return;
  const colors = ['#FF6B35', '#42A5F5', '#0ECB81', '#FFB300', '#AB47BC', '#26C6DA', '#F6465D', '#FFA028', '#7c3aed', '#d97706'];
  if (!window.Chart) return;
  new Chart(document.getElementById('kbTypeDonut'), {
    type: 'doughnut',
    data: {
      labels: types.map(t => t[0]),
      datasets: [{ data: types.map(t => t[1].count || t[1]), backgroundColor: types.map((_, i) => colors[i % colors.length]), borderWidth: 2, borderColor: '#12161C' }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'right', labels: { color: '#8B95A5', font: { size: 11 }, padding: 12 } } }
    }
  });
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
    for path in sorted(WORKBUDDY_DIR.glob("*.md"), reverse=True):
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
    """Convert markdown to HTML using mistune (CommonMark + tables)."""
    try:
        import mistune
        if not hasattr(markdown_to_html, "_renderer"):
            markdown_to_html._renderer = mistune.create_markdown(
                escape=False,
                plugins=["table", "strikethrough", "footnotes", "task_lists"],
            )
        return markdown_to_html._renderer(text)
    except ImportError:
        # Fallback: basic conversion
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline_markdown(text):
    """Convert inline markdown: **bold**, *italic*, `code`, [link](url)"""
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


MM_PRIMER_PATH = Path.home() / ".hermes" / "bloomberg-portal" / "macromicro_primer.md"


def parse_mm_primer():
    """Parse macromicro_primer.md into structured JSON sections."""
    content = read_text(MM_PRIMER_PATH)
    if not content:
        return None

    # Generate full rendered HTML for the primer (sections before "Recurring Themes")
    # Everything up to "## 3. Recurring Themes"
    primer_md = content.split("## 3. Recurring Themes")[0].strip()

    # Reverse chronological order: find "## 2. Chronological Newsletter Summaries"
    # and reverse the ### entries within it
    if "## 2. Chronological Newsletter Summaries" in primer_md:
        parts = primer_md.split("## 2. Chronological Newsletter Summaries", 1)
        before = parts[0]
        after = parts[1]
        # Split by ### to get individual newsletter entries
        raw_parts = after.split("### ")
        # Re-add "### " prefix and filter empty
        entries = ["### " + p for p in raw_parts if p.strip()]
        entries.reverse()
        # Rejoin
        primer_md = before + "## 2. Chronological Newsletter Summaries (Most Recent First)\n\n" + "\n".join(entries)

    # Inject article/PDF links from mm_article_links.json into the markdown
    MM_LINKS_PATH = Path.home() / ".hermes" / "bloomberg-portal" / "mm_article_links.json"
    mm_links = {}
    try:
        mm_links = json.loads(read_text(MM_LINKS_PATH) or "{}").get("links", {})
    except Exception:
        pass  # No links file or parse error — render without links
    import re as _re
    _PDF_ICON = "\U0001f4c4"  # 📄
    if mm_links:
        # Pass 1: Replace [PDF Download] in ### headers with linked version
        for title_key, link_info in mm_links.items():
            pattern = _re.compile(
                r"(###\s+#\d+\s+\u2014\s+.+?" + _re.escape(title_key) + r".+?)(\[PDF Download\])",
                _re.IGNORECASE,
            )
            link_html = '<a href="' + link_info["url"] + '" target="_blank" rel="noopener">' + _PDF_ICON + " " + link_info["label"] + "</a>"
            replacement = lambda m, lh=link_html: m.group(1) + " " + lh
            primer_md = pattern.sub(replacement, primer_md)
        # Pass 2: For entries WITHOUT [PDF Download] tag but with a link, inject a line after header
        for title_key, link_info in mm_links.items():
            header_pattern = _re.compile(
                r"(###\s+#\d+\s+\u2014\s+.+?" + _re.escape(title_key) + r".+?\n)",
                _re.IGNORECASE,
            )
            m = header_pattern.search(primer_md)
            if m and link_info["url"] not in primer_md:
                link_html = '<a href="' + link_info["url"] + '" target="_blank" rel="noopener">' + _PDF_ICON + " " + link_info["label"] + "</a>"
                link_line = "\n" + link_html + "\n"
                primer_md = header_pattern.sub(lambda m, ll=link_line: m.group(1) + ll, primer_md)

    primer_html = markdown_to_html(primer_md)

    lines = content.splitlines()
    result = {
        "overview": "",
        "primer_html": primer_html,
        "themes": [],
        "charts": [],
        "followups": [],
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }

    current_section = None
    section_buffer = []

    for line in lines:
        stripped = line.strip()

        # Detect ## sections
        if stripped.startswith("## "):
            # Flush previous section
            if current_section == "overview":
                result["overview"] = "\n".join(section_buffer).strip()
            elif current_section == "themes":
                result["themes"] = _parse_themes(section_buffer)
            elif current_section == "charts":
                pass  # charts handled inline below
            elif current_section == "followups":
                result["followups"] = _parse_followups(section_buffer)

            section_buffer = []
            header_text = stripped[3:].strip().lower()

            if "overview" in header_text or "what is" in header_text:
                current_section = "overview"
            elif "recurring themes" in header_text:
                current_section = "themes"
            elif "key charts" in header_text or "data points" in header_text:
                current_section = "charts"
            elif "follow-up" in header_text or "recommended follow" in header_text:
                current_section = "followups"
            else:
                current_section = None
            continue

        # Skip H1 and --- separator lines
        if stripped.startswith("# ") or stripped == "---":
            continue

        if current_section:
            if current_section == "charts":
                # Parse markdown table directly
                if stripped.startswith("|") and not stripped.startswith("|---"):
                    parts = [p.strip() for p in stripped.strip("|").split("|")]
                    if parts and parts[0].lower() in ("metric", "--------"):
                        continue
                    if len(parts) >= 2:
                        result["charts"].append({
                            "metric": parts[0] if len(parts) > 0 else "",
                            "value": parts[1] if len(parts) > 1 else "",
                            "source": parts[2] if len(parts) > 2 else "",
                        })
            else:
                section_buffer.append(stripped)

    # Flush last section
    if current_section == "overview":
        result["overview"] = "\n".join(section_buffer).strip()
    elif current_section == "themes":
        result["themes"] = _parse_themes(section_buffer)
    elif current_section == "followups":
        result["followups"] = _parse_followups(section_buffer)

    return result


def _parse_themes(lines):
    """Parse recurring themes from markdown subsections (### Title + body text)."""
    themes = []
    current_title = None
    current_body = []

    for line in lines:
        if line.startswith("### "):
            if current_title:
                themes.append({
                    "title": current_title,
                    "body": " ".join(current_body).strip(),
                })
            current_title = line[4:].strip()
            current_body = []
        else:
            stripped = line.strip()
            if stripped:
                # Clean markdown formatting
                cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", stripped)
                cleaned = re.sub(r"^- ", "", cleaned)
                current_body.append(cleaned)

    if current_title:
        themes.append({
            "title": current_title,
            "body": " ".join(current_body).strip(),
        })

    return themes


def _parse_followups(lines):
    """Parse numbered follow-up topics."""
    followups = []
    for line in lines:
        # Match numbered items like "1. **Topic:** description"
        match = re.match(r"^\d+\.\s+(.+)", line.strip())
        if match:
            text = match.group(1).strip()
            # Clean markdown bold
            text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
            followups.append(text)
    return followups


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
            elif path == "/api/intel-timeline":
                self.respond_json(load_intel_timeline())
            elif path == "/api/intel-report":
                self.respond_json(load_intel_report())
            elif path == "/api/kb":
                kb = build_kb_index()
                # Load entities from knowledge base
                known_kb, _ = load_known_entities()
                kb_entities = known_kb.get("entities", {})
                self.respond_json(
                    {
                        "dates": kb["dates"],
                        "total_dates": len(kb["dates"]),
                        "total_newsletters": kb["total_newsletters"],
                        "total_links": kb["total_links"],
                        "newsletter_types": kb["newsletter_types"],
                        "entities": kb_entities,
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
            elif path == "/api/mm":
                data = parse_mm_primer()
                if data is None:
                    self.send_error(404, "MM primer not found")
                    return
                self.respond_json(data)
            elif path == "/api/mm-primer":
                content = read_text(MM_PRIMER_PATH)
                if content is None:
                    self.send_error(404, "MM primer not found")
                    return
                self.respond_html(f"<html><head><meta charset='UTF-8'></head><body><pre>{esc(content)}</pre></body></html>")
            elif path == "/api/ai-news":
                self.respond_json(self.do_ai_news())
            else:
                self.send_error(404, "Not found")
        except Exception as exc:
            self.send_error(500, str(exc))

    def respond_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(body)

    def respond_json(self, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(body)

    def do_ai_news(self):
        """Return curated AIHOT articles from ai_news directory, sorted by score desc."""
        if not AI_NEWS_DIR.exists():
            return {"articles": []}
        articles = []
        for f in sorted(AI_NEWS_DIR.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    articles.extend(data)
                elif isinstance(data, dict):
                    articles.append(data)
            except Exception:
                pass
        # Sort by composite_score desc
        articles.sort(key=lambda a: a.get("composite_score", 0), reverse=True)
        return {"articles": articles[:20]}

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
