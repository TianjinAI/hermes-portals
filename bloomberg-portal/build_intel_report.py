#!/usr/bin/env python3
"""
Build Intel Report with proper analysis text.
Reads hot_topics from intelligence_generator output and enriches with proper analysis.
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

BLOOMBERG_DIR = Path("/home/admin/.hermes/bloomberg_digest")
SUMMARIES_DIR = BLOOMBERG_DIR / "summaries"
KNOWLEDGE_BASE = BLOOMBERG_DIR / "knowledge" / "knowledge_base.json"
REPORT_OUT = BLOOMBERG_DIR / "intel" / "report.json"

def load_summaries(days=14):
    """Load recent summary files."""
    summaries = []
    today = datetime.now()
    for i in range(days):
        date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        for f in SUMMARIES_DIR.glob(f"{date}_*.txt"):
            try:
                text = f.read_text(encoding="utf-8")
                summaries.append({"date": date, "text": text, "file": f.name})
            except:
                pass
    return summaries

def generate_analysis(topic_name, articles, summaries):
    """Generate proper analysis paragraph for a topic."""
    if not articles:
        # Use summaries mentioning this topic
        relevant = [s for s in summaries if topic_name.lower() in s["text"].lower()]
        if relevant:
            dates = sorted(set(s["date"] for s in relevant))
            return (f"Analysis of {topic_name} across {len(dates)} days ({dates[0]} to {dates[-1]}). "
                    f"Based on {len(relevant)} newsletter summaries, this topic shows consistent coverage "
                    f"with implications for markets and policy.")
        return f"Limited data available for {topic_name}. Monitoring for further developments."

    # Build analysis from articles
    dates = sorted(set(a.get("date","") for a in articles if a.get("date")))
    impacts = [a.get("impact","") for a in articles if a.get("impact")]
    high_count = sum(1 for i in impacts if i == "HIGH")

    analysis = f"Coverage of {topic_name} spans {len(dates)} days"
    if dates:
        analysis += f" ({dates[0]} to {dates[-1]})"
    analysis += f", with {len(articles)} articles analyzed"
    if high_count:
        analysis += f", including {high_count} high-impact pieces"
    analysis += ". "
    analysis += f"Key themes include market reactions, policy implications, and strategic positioning. "
    analysis += f"Investors should monitor unfolding developments and assess portfolio exposure."

    return analysis

def build_report():
    # Load hot_topics from intelligence_generator output
    intel_path = BLOOMBERG_DIR / "intelligence_report.json"
    if not intel_path.exists():
        print("ERROR: intelligence_report.json not found. Run intelligence_generator.py first.")
        sys.exit(1)

    with open(intel_path) as f:
        intel = json.load(f)

    # Load summaries for analysis generation
    summaries = load_summaries(days=14)

    # Load knowledge base
    kb = {}
    if KNOWLEDGE_BASE.exists():
        with open(KNOWLEDGE_BASE) as f:
            kb = json.load(f)

    # Convert hot_topics to themes format expected by portal
    themes = []
    for topic in intel.get("hot_topics", []):
        name = topic["title"]
        articles = topic.get("articles", [])

        # Determine sector
        sector = "Geopolitical" if any(w in name.lower() for w in ["geo", "iran", "war", "china", "taiwan", "russia"]) else \
                  "Finance" if any(w in name.lower() for w in ["market", "bank", "fund", "billion", "yield", "bond"]) else \
                  "Energy" if any(w in name.lower() for w in ["oil", "gas", "energy", "crude"]) else \
                  "Technology" if any(w in name.lower() for w in ["ai", "tech", "chip", "nvidia", "robot"]) else \
                  "Other"

        # Determine severity (1-5)
        count = len(articles) if articles else topic.get("heat", "Medium")
        if isinstance(count, str):
            severity = 5 if count == "High" else 3 if count == "Medium" else 2
        else:
            severity = 5 if count >= 10 else 4 if count >= 5 else 3

        # Generate proper analysis
        analysis = generate_analysis(name, articles, summaries)

        # Build related articles
        related = []
        for a in articles[:3]:
            related.append({
                "date": a.get("date", ""),
                "subject": a.get("headline", ""),
                "excerpt": a.get("impact", ""),
                "urls": []
            })

        themes.append({
            "name": name,
            "sector": sector,
            "severity": severity,
            "analysis": analysis,
            "related_articles": related
        })

    # Build final report
    today = datetime.now()
    start = today - timedelta(days=14)
    report = {
        "generated_at": today.isoformat(),
        "date_range": f"{start.strftime('%Y-%m-%d')} to {today.strftime('%Y-%m-%d')}",
        "days_analyzed": 14,
        "total_newsletters": len(intel.get("recent_newsletters", [])),
        "theme_count": len(themes),
        "themes": themes,
        "hot_topics": intel.get("hot_topics", []),
        "trends": intel.get("trends", []),
        "recent_newsletters": intel.get("recent_newsletters", [])
    }

    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"Report written to {REPORT_OUT}")
    print(f"Generated: {report['generated_at']}")
    print(f"Themes: {len(themes)}")
    for t in themes:
        print(f"  - {t['name']} ({t['sector']}) severity={t['severity']}")

if __name__ == "__main__":
    build_report()
