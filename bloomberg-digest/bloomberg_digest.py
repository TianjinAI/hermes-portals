#!/usr/bin/env python3
"""
Bloomberg Daily Digest Pipeline v2
====================================
Two-stage approach:
  Stage 1: Summarize each newsletter individually (parallelizable, smaller prompts)
  Stage 2: Combine individual summaries into ranked brief + full HTML digest

Usage:
  python3 bloomberg_digest.py                    # Digest yesterday's newsletters
  python3 bloomberg_digest.py --date 2026-04-22  # Digest a specific date
  python3 bloomberg_digest.py --brief-only       # Only output brief (no HTML)
  python3 bloomberg_digest.py --stage1           # Only run stage 1 (per-newsletter)
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
import dateutil.parser
from pathlib import Path

# ─── Config ──────────────────────────────────────────────────────────────
ACCOUNT = "bamboo.ocean"
BLOOMBERG_DOMAIN = "news.bloomberg.com"
OUTPUT_DIR = Path.home() / ".hermes" / "bloomberg_digest"
BRIEF_DIR = OUTPUT_DIR / "briefs"
FULL_DIR = OUTPUT_DIR / "full"
RAW_DIR = OUTPUT_DIR / "raw"
LINKS_DIR = OUTPUT_DIR / "links"
SUMM_DIR = OUTPUT_DIR / "summaries"  # per-newsletter summaries
KB_DIR = OUTPUT_DIR / "knowledge"    # cumulative knowledge base

# LLM config — use fast models to keep pipeline under 3 min
LLM_BASE_URL = "https://opencode.ai/zen/v1"
LLM_MODEL_STAGE1 = "gpt-5.4-nano"   # fast per-newsletter summaries (~2s each)
LLM_MODEL_STAGE2 = "claude-haiku-4-5"  # better reasoning for combined digest
LLM_MODEL_ENTITIES = "claude-haiku-4-5"  # reliable JSON extraction for entities/themes/facts

# Timezone
USER_TZ = timezone(timedelta(hours=-5))  # CDT
UTC = timezone.utc


# ─── Helpers ─────────────────────────────────────────────────────────────

def get_api_key():
    env_path = Path.home() / ".hermes" / ".env"
    with open(env_path) as f:
        for line in f:
            if line.startswith("OPENCODE_ZEN_API_KEY="):
                return line.strip().split("=", 1)[1]
    raise RuntimeError("OPENCODE_ZEN_API_KEY not found")


def run_himalaya(*args, timeout=60):
    cmd = ["/home/admin/.local/bin/himalaya"] + list(args)
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"Himalaya error: {result.stderr[:300]}")
    return result.stdout


def llm_call(prompt: str, system: str = None, max_tokens: int = 4096, temperature: float = 0.3, model: str = None) -> str:
    """Call the LLM API using curl for reliability."""
    if model is None:
        model = LLM_MODEL_STAGE1
    api_key = get_api_key()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    })

    result = subprocess.run(
        ["curl", "-s", "-X", "POST", f"{LLM_BASE_URL}/chat/completions",
         "-H", f"Authorization: Bearer {api_key}",
         "-H", "Content-Type: application/json",
         "-d", "@-"],
        input=payload.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180
    )

    resp = json.loads(result.stdout)
    if "choices" not in resp:
        raise RuntimeError(f"LLM API error: {json.dumps(resp)[:300]}")
    return resp["choices"][0]["message"]["content"]


# ─── Fetch & Clean ──────────────────────────────────────────────────────

def fetch_bloomberg_envelopes(target_date: str):
    output = run_himalaya("envelope", "list", "--account", ACCOUNT, "--output", "json", "--page-size", "200")
    envelopes = json.loads(output)

    bloomberg_emails = []
    for e in envelopes:
        from_addr = str(e.get("from", "")).lower()
        if BLOOMBERG_DOMAIN not in from_addr:
            continue

        date_str = e.get("date", "")
        if not date_str:
            continue

        try:
            dt = dateutil.parser.parse(date_str)
            dt_user = dt.astimezone(USER_TZ)
            email_date = dt_user.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue

        if email_date == target_date:
            bloomberg_emails.append({
                "id": e["id"],
                "subject": e.get("subject", "(no subject)"),
                "from": e.get("from", {}),
                "date_utc": date_str,
                "date_local": dt_user.strftime("%Y-%m-%d %H:%M"),
            })

    bloomberg_emails.sort(key=lambda x: x["date_local"])
    return bloomberg_emails


def read_email_body(email_id: str) -> str:
    raw = run_himalaya("message", "read", email_id, "--account", ACCOUNT, timeout=30)
    return clean_bloomberg_text(raw, preserve_urls=True)


def clean_bloomberg_text(text: str, preserve_urls: bool = False) -> str:
    text = re.sub(r'^[\u200b\u200c\u200d\ufeff\u00a0\s\u2002\u2009\u200a\u202f\u205f‌ ]+$', '', text, flags=re.MULTILINE)
    text = re.sub(r'https?://sli\.bloomberg\.com/[^\s>]+', '', text)
    if not preserve_urls:
        text = re.sub(r'<https?://[^>]+>', '', text)
        text = re.sub(r'(?<=\s)https?://[^\s<>\)\]\}]+', '', text)
    text = re.sub(r'Read in browser\s*', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    lines = [line.rstrip() for line in text.split('\n')]
    return '\n'.join(lines).strip()


def extract_newsletter_metadata(body: str, email_id: str = None) -> dict:
    """Extract reporter, newsletter type, and URLs from raw newsletter body."""
    metadata = {
        "reporter": None,
        "newsletter_type": None,
        "urls": [],
    }

    lines = body.split('\n')

    # Extract reporter/byline — look for "— Name" pattern (byline signoff)
    for line in lines:
        m = re.match(r'^—\s+(.+?)(?:\s*<|$)', line)
        if m:
            name = m.group(1).strip().rstrip('.')
            # Skip newsletter-level signoffs, keep byline names
            if name and len(name.split()) <= 4 and not name.lower().startswith(
                ('check out', 'listen', 'your', 'market data', 'keep track')):
                metadata["reporter"] = name
                break

    # Extract newsletter type from sender/From name
    # Map sender patterns to newsletter identity
    sender_type_map = {
        "morning briefing": "Morning Briefing",
        "markets daily": "Markets Daily",
        "bloomberg technology": "Technology",
        "bloomberg politics": "Politics",
        "bloomberg crypto": "Crypto",
        "bloomberg weekend": "Weekend",
        "ed harrison": "Macro",
        "menaka doshi": "Geopolitics",
        "marcus wong": "Asia Markets",
        "tasos vossos": "Credit Markets",
        "the brink": "Brink",
        "etf iq": "ETF IQ",
        "hong kong edition": "Hong Kong Edition",
        "singapore edition": "Singapore Edition",
        "next china": "Next China",
        "going private": "Going Private",
        "the forecast": "The Forecast",
        "subscriber insider": "Subscriber Insider",
    }

    # Check sender/From name first (more reliable than subject)
    for keyword, label in sender_type_map.items():
        if body and keyword in body[:500].lower():
            metadata["newsletter_type"] = label
            break

    # Fallback: check subject line
    if metadata["newsletter_type"] is None:
        subject_line = None
        for line in lines:
            if line.startswith('Subject:'):
                subject_line = line.replace('Subject:', '').strip()
                break
        if subject_line:
            for keyword, label in sender_type_map.items():
                if keyword in subject_line.lower():
                    metadata["newsletter_type"] = label
                    break
        if metadata["newsletter_type"] is None and subject_line:
            metadata["newsletter_type"] = subject_line

    return metadata


def extract_urls_from_html(email_id: str, account: str = "bamboo.ocean") -> list:
    """Extract URLs from the HTML version of an email via himalaya export."""
    import tempfile, shutil

    tmpdir = tempfile.mkdtemp()
    try:
        result = subprocess.run(
            ["/home/admin/.local/bin/himalaya", "message", "export", str(email_id),
             "--account", account, "-d", tmpdir],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15
        )
        if result.returncode != 0:
            return []

        html_file = os.path.join(tmpdir, "index.html")
        if not os.path.exists(html_file):
            return []

        html = open(html_file).read()
        # Extract href URLs from anchor tags
        urls = re.findall(r'href="((?:https?:)?//[^"]+)"', html)
        # Filter out tracking, unsubscribe, preferences, and empty URLs
        filtered = []
        seen = set()
        for u in urls:
            u_clean = u.strip()
            if u_clean in seen:
                continue
            seen.add(u_clean)
            if any(skip in u_clean.lower() for skip in [
                'unsubscribe', 'preferences', 'opt-out',
                'forwardthisemail', 'sign up', 'reportit'
            ]):
                continue
            # Skip bare tracking IDs that aren't full URLs
            if not u_clean.startswith('http'):
                continue
            filtered.append(u_clean)
            if len(filtered) >= 20:
                break
        return filtered
    except Exception:
        return []
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def extract_key_content(body: str) -> str:
    """Extract substantive content, skipping email headers, limited to ~2500 chars."""
    lines = body.split('\n')
    content_start = 0
    for i, line in enumerate(lines):
        if line and not line.startswith(('From:', 'To:', 'Subject:')):
            content_start = i
            break

    content_lines = lines[content_start:]
    result = []
    char_count = 0
    for line in content_lines:
        stripped = line.strip()
        if not stripped:
            if result and result[-1] != '':
                result.append('')
            continue
        result.append(stripped)
        char_count += len(stripped)
        if char_count > 2500:
            # Add truncation note
            result.append("[...truncated]")
            break

    return '\n'.join(result)


# ─── Entity & Theme Extraction ───────────────────────────────────────────

def extract_entities_and_themes(summary_text: str, subject: str) -> dict:
    """Extract entities, themes, facts, and opinions from a newsletter summary."""
    prompt = f"""Extract key intelligence from this Bloomberg newsletter summary.

Subject: {subject}

{summary_text}

Output format (STRICT JSON only, no markdown):
{{
  "entities": {{
    "companies": ["Company1", "Company2"],
    "people": ["Person1", "Person2"],
    "sectors": ["Sector1", "Sector2"],
    "countries": ["Country1", "Country2"],
    "assets": ["Asset1", "Asset2"]
  }},
  "themes": ["Theme1", "Theme2"],
  "facts": [
    {{
      "type": "data_point|event|decision|claim",
      "subject": "what the fact is about",
      "value": "specific value if applicable",
      "context": "why it matters",
      "source": "who said/did this"
    }}
  ],
  "opinions": [
    {{
      "speaker": "who said this",
      "role": "their title/position",
      "quote": "key quote or paraphrase",
      "topic": "what they're commenting on"
    }}
  ],
  "sentiment": "positive/negative/neutral/mixed",
  "key_metrics": ["metric1: value1", "metric2: value2"]
}}

Rules:
- Companies: Public companies, funds, institutions mentioned by name
- People: Executives, officials, analysts mentioned by name
- Sectors: Industry sectors (Tech, Energy, Finance, etc.)
- Countries: Nations or regions discussed
- Assets: Specific instruments (WTI crude, S&P 500, Gold, Bitcoin, etc.)
- Themes: 2-3 recurring topics (e.g., "geopolitical risk", "AI regulation", "crypto regulation")
- Facts: Specific data points, events, decisions, or claims with context
- Opinions: Direct quotes or paraphrased expert analysis
- Sentiment: Overall tone of the newsletter
- Key metrics: Specific numbers with context (e.g., "S&P 500: 7,140 (-0.4%)")"""

    try:
        resp = llm_call(prompt, max_tokens=800, temperature=0.1, model=LLM_MODEL_ENTITIES)
        # Extract JSON from response - try multiple patterns
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', resp, re.DOTALL)
        if not json_match:
            # Try a more lenient pattern
            json_match = re.search(r'\{.*\}', resp, re.DOTALL)
        
        if json_match:
            json_str = json_match.group()
            # Try to fix common JSON issues
            json_str = json_str.replace('\n', ' ').replace('\r', '')
            # Remove any trailing commas before closing braces
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)
            
            try:
                data = json.loads(json_str)
                # Ensure all required fields exist
                if "facts" not in data:
                    data["facts"] = []
                if "opinions" not in data:
                    data["opinions"] = []
                return data
            except json.JSONDecodeError as e:
                print(f"    ⚠️ JSON parse error: {e}")
                # Try to extract just the entities and themes
                try:
                    # Look for partial matches
                    entities_match = re.search(r'"entities":\s*\{[^}]+\}', json_str)
                    themes_match = re.search(r'"themes":\s*\[[^\]]+\]', json_str)
                    if entities_match and themes_match:
                        partial_data = json.loads('{' + entities_match.group() + ',' + themes_match.group() + '}')
                        partial_data["facts"] = []
                        partial_data["opinions"] = []
                        partial_data["sentiment"] = "neutral"
                        partial_data["key_metrics"] = []
                        return partial_data
                except:
                    pass
    except Exception as e:
        print(f"    ⚠️ Entity extraction failed: {e}")

    # Fallback: empty structure
    return {
        "entities": {"companies": [], "people": [], "sectors": [], "countries": [], "assets": []},
        "themes": [],
        "facts": [],
        "opinions": [],
        "sentiment": "neutral",
        "key_metrics": []
    }


def update_knowledge_base(target_date: str, newsletters_with_entities: list):
    """Update the cumulative knowledge base with today's entities, themes, facts, and opinions."""
    KB_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing knowledge base or create new
    kb_path = KB_DIR / "knowledge_base.json"
    if kb_path.exists():
        kb = json.loads(kb_path.read_text())
    else:
        kb = {
            "entities": {
                "companies": {},
                "people": {},
                "sectors": {},
                "countries": {},
                "assets": {}
            },
            "themes": {},
            "facts": [],
            "opinions": [],
            "reporters": {},
            "daily_summary": {},
            "last_updated": None
        }

    # Update entities
    for nl in newsletters_with_entities:
        entities = nl.get("entities", {})
        reporter = nl.get("reporter")
        newsletter_type = nl.get("newsletter_type")

        # Update companies
        for company in entities.get("companies", []):
            if company not in kb["entities"]["companies"]:
                kb["entities"]["companies"][company] = {
                    "first_seen": target_date,
                    "last_seen": target_date,
                    "mention_count": 0,
                    "contexts": []
                }
            kb["entities"]["companies"][company]["last_seen"] = target_date
            kb["entities"]["companies"][company]["mention_count"] += 1
            kb["entities"]["companies"][company]["contexts"].append({
                "date": target_date,
                "subject": nl.get("subject"),
                "newsletter_type": newsletter_type,
                "reporter": reporter
            })
            # Keep only last 20 contexts
            kb["entities"]["companies"][company]["contexts"] = \
                kb["entities"]["companies"][company]["contexts"][-20:]

        # Update people
        for person in entities.get("people", []):
            if person not in kb["entities"]["people"]:
                kb["entities"]["people"][person] = {
                    "first_seen": target_date,
                    "last_seen": target_date,
                    "mention_count": 0,
                    "contexts": []
                }
            kb["entities"]["people"][person]["last_seen"] = target_date
            kb["entities"]["people"][person]["mention_count"] += 1

        # Update sectors
        for sector in entities.get("sectors", []):
            if sector not in kb["entities"]["sectors"]:
                kb["entities"]["sectors"][sector] = {
                    "first_seen": target_date,
                    "last_seen": target_date,
                    "mention_count": 0
                }
            kb["entities"]["sectors"][sector]["last_seen"] = target_date
            kb["entities"]["sectors"][sector]["mention_count"] += 1

        # Update countries
        for country in entities.get("countries", []):
            if country not in kb["entities"]["countries"]:
                kb["entities"]["countries"][country] = {
                    "first_seen": target_date,
                    "last_seen": target_date,
                    "mention_count": 0
                }
            kb["entities"]["countries"][country]["last_seen"] = target_date
            kb["entities"]["countries"][country]["mention_count"] += 1

        # Update assets
        for asset in entities.get("assets", []):
            if asset not in kb["entities"]["assets"]:
                kb["entities"]["assets"][asset] = {
                    "first_seen": target_date,
                    "last_seen": target_date,
                    "mention_count": 0
                }
            kb["entities"]["assets"][asset]["last_seen"] = target_date
            kb["entities"]["assets"][asset]["mention_count"] += 1

        # Update themes
        for theme in entities.get("themes", []):
            if theme not in kb["themes"]:
                kb["themes"][theme] = {
                    "first_seen": target_date,
                    "last_seen": target_date,
                    "mention_count": 0,
                    "daily_mentions": {}
                }
            kb["themes"][theme]["last_seen"] = target_date
            kb["themes"][theme]["mention_count"] += 1
            if target_date not in kb["themes"][theme]["daily_mentions"]:
                kb["themes"][theme]["daily_mentions"][target_date] = 0
            kb["themes"][theme]["daily_mentions"][target_date] += 1

        # Store facts
        for fact in nl.get("facts", []):
            fact["date"] = target_date
            fact["newsletter_type"] = newsletter_type
            fact["reporter"] = reporter
            fact["subject"] = nl.get("subject")
            kb["facts"].append(fact)

        # Store opinions
        for opinion in nl.get("opinions", []):
            opinion["date"] = target_date
            opinion["newsletter_type"] = newsletter_type
            opinion["reporter"] = reporter
            opinion["subject"] = nl.get("subject")
            kb["opinions"].append(opinion)

        # Update reporters
        if reporter:
            if reporter not in kb["reporters"]:
                kb["reporters"][reporter] = {
                    "first_seen": target_date,
                    "last_seen": target_date,
                    "article_count": 0,
                    "newsletter_types": [],
                    "beats": []
                }
            kb["reporters"][reporter]["last_seen"] = target_date
            kb["reporters"][reporter]["article_count"] += 1
            if newsletter_type and newsletter_type not in kb["reporters"][reporter]["newsletter_types"]:
                kb["reporters"][reporter]["newsletter_types"].append(newsletter_type)

    # Convert sets to lists for JSON serialization
    for reporter in kb["reporters"]:
        kb["reporters"][reporter]["newsletter_types"] = list(kb["reporters"][reporter]["newsletter_types"])
        kb["reporters"][reporter]["beats"] = list(kb["reporters"][reporter]["beats"])

    # Update daily summary
    kb["daily_summary"][target_date] = {
        "newsletter_count": len(newsletters_with_entities),
        "unique_entities": {
            "companies": len(set(c for nl in newsletters_with_entities for c in nl.get("entities", {}).get("companies", []))),
            "people": len(set(p for nl in newsletters_with_entities for p in nl.get("entities", {}).get("people", []))),
            "themes": len(set(t for nl in newsletters_with_entities for t in nl.get("entities", {}).get("themes", [])))
        }
    }

    kb["last_updated"] = datetime.now(UTC).isoformat()

    # Limit facts and opinions to last 1000 entries to prevent unbounded growth
    if "facts" not in kb:
        kb["facts"] = []
    if "opinions" not in kb:
        kb["opinions"] = []
    kb["facts"] = kb["facts"][-1000:]
    kb["opinions"] = kb["opinions"][-500:]

    # Save knowledge base
    kb_path.write_text(json.dumps(kb, indent=2, default=str))
    print(f"  🧠 Knowledge base updated: {kb_path}")

    return kb


# ─── Stage 1: Per-Newsletter Summaries ──────────────────────────────────

def summarize_single_newsletter(subject, from_name, date_local, content):
    """Summarize a single Bloomberg newsletter into structured bullet points."""
    prompt = f"""You are a financial news analyst. Summarize this Bloomberg newsletter into structured bullet points.

Subject: {subject}
From: {from_name} | Time: {date_local}

{content}

Output format (STRICT):
HEADLINE: [one-line headline capturing the main theme]
CATEGORY: [Markets/Geopolitics/Tech/Crypto/Politics/Energy/PrivateEquity/Macro]
IMPACT: [HIGH/MEDIUM/LOW]

KEY POINTS:
• [most important point with specific numbers if available]
• [second most important point]
• [third point]
• [fourth point if significant]
• [fifth point if significant]

DATA POINTS:
- [any specific numbers: prices, %, yields, valuations, etc.]

ACTIONABLE:
- [any specific action items or things to watch]"""

    return llm_call(prompt, max_tokens=800, temperature=0.2)


# ─── Stage 2: Combined Digest ──────────────────────────────────────────

def deduplicate_summaries(summaries: list) -> list:
    """Use LLM to identify and merge overlapping stories across newsletters."""
    if len(summaries) <= 1:
        return summaries

    # Build a compact representation for deduplication
    index_text = ""
    for i, s in enumerate(summaries):
        index_text += f"\n[{i}] {s['subject']}\n{s['summary_text'][:400]}\n"

    prompt = f"""You are a news editor. Below are {len(summaries)} Bloomberg newsletter summaries.

Identify which ones cover the SAME core story or event. Group them by topic.

Rules:
- Same geopolitical event (e.g., Iran/Hormuz) = SAME story even if different angles
- Same company earnings or product launch = SAME story
- Same market movement (e.g., oil price surge) = SAME story
- Different companies or different events = DIFFERENT stories

For each group, list the indices that belong together. Stories with no duplicates get their own group.

Output format (STRICT JSON only, no markdown):
{{
  "groups": [
    {{
      "indices": [0, 3, 5],
      "topic": "brief topic name",
      "primary_index": 0
    }}
  ]
}}

NEWSLETTER SUMMARIES:
{index_text}"""

    try:
        resp = llm_call(prompt, max_tokens=1500, temperature=0.1, model=LLM_MODEL_STAGE1)
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', resp, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            groups = data.get("groups", [])
        else:
            groups = []
    except Exception as e:
        print(f"  ⚠️ Deduplication failed: {e}, proceeding without dedup")
        groups = []

    if not groups:
        # Fallback: each summary is its own group
        groups = [{"indices": [i], "primary_index": i} for i in range(len(summaries))]

    # Merge summaries within each group
    merged = []
    used_indices = set()

    for group in groups:
        indices = group.get("indices", [])
        primary = group.get("primary_index", indices[0] if indices else 0)

        # Skip already-used indices (safety)
        fresh_indices = [i for i in indices if i not in used_indices and i < len(summaries)]
        if not fresh_indices:
            continue

        primary_idx = fresh_indices[0]
        primary_summary = summaries[primary_idx]

        if len(fresh_indices) == 1:
            # No duplicates, use as-is
            merged.append(primary_summary)
            used_indices.add(primary_idx)
            continue

        # Merge multiple summaries of the same story
        combined_text = ""
        for idx in fresh_indices:
            combined_text += f"\n--- SOURCE: {summaries[idx]['subject']} ---\n{summaries[idx]['summary_text']}\n"
            used_indices.add(idx)

        merge_prompt = f"""You are a financial news editor. Merge these overlapping Bloomberg newsletter summaries into ONE clean, comprehensive summary.

Remove ALL duplication. Do NOT repeat the same facts. Synthesize the best information from all sources into a single coherent summary.

Use this exact format:
HEADLINE: [one-line headline]
CATEGORY: [single category]
IMPACT: [HIGH/MEDIUM/LOW]

KEY POINTS:
• [merged point 1 - most important, with specific numbers]
• [merged point 2]
• [merged point 3]
• [point 4 if significant and not redundant]

DATA POINTS:
- [consolidated numbers from all sources - no duplicates]

ACTIONABLE:
- [action items]

SOURCE NEWSLETTERS: {', '.join([summaries[i]['subject'] for i in fresh_indices])}

INPUT SUMMARIES:
{combined_text}"""

        try:
            merged_summary = llm_call(merge_prompt, max_tokens=1000, temperature=0.2, model=LLM_MODEL_STAGE1)
        except Exception as e:
            print(f"  ⚠️ Merge failed for group {fresh_indices}: {e}")
            merged_summary = primary_summary["summary_text"]

        merged.append({
            "id": primary_summary["id"],
            "subject": primary_summary["subject"],
            "from_name": primary_summary["from_name"],
            "date_local": primary_summary["date_local"],
            "summary_text": merged_summary,
            "merged_from": [summaries[i]["subject"] for i in fresh_indices],
            "reporter": primary_summary.get("reporter"),
            "newsletter_type": primary_summary.get("newsletter_type"),
            "urls": [u for i in fresh_indices for u in summaries[i].get("urls", [])],
        })

    # Add any missed summaries
    for i, s in enumerate(summaries):
        if i not in used_indices:
            merged.append(s)

    print(f"  🔀 Deduplicated: {len(summaries)} → {len(merged)} unique stories")
    return merged


def build_brief_digest(summaries: list, target_date: str) -> str:
    """Build the concise Telegram-friendly brief from individual summaries."""
    combined_summaries = ""
    for s in summaries:
        combined_summaries += f"\n---\n{s['summary_text']}\n"

    prompt = f"""You are a senior financial news editor. Below are structured summaries of {len(summaries)} Bloomberg newsletters from {target_date}.

Produce a CONCISE DAILY BRIEFING for a busy executive. Use this EXACT format:

## Bloomberg Daily Brief — {target_date}

### 🔥 Top Headlines (by market impact)
Rank the top 8-12 most important headlines across ALL newsletters. For each:
- **Headline** — 1-sentence with key numbers [CATEGORY]

### 📊 Key Market Data
Group all specific data points:
- Equities: [indices, stocks, % changes]
- Fixed Income: [yields, spreads]
- Commodities: [oil, gold, etc.]
- FX: [dollar, pairs]
- Crypto: [BTC, etc.]

### 💡 What to Watch Today
3-5 items that will drive markets today

### 🗞️ Quick Scan
Chronological list of all newsletters (time + subject → 1-sentence takeaway each)

Be CONCISE. Bold important items. No filler.

NEWSLETTER SUMMARIES:
{combined_summaries}"""

    return llm_call(prompt, max_tokens=3000, temperature=0.3, model=LLM_MODEL_STAGE2)


def build_full_digest(summaries: list, target_date: str) -> str:
    """Build the full HTML digest for the portal."""
    # Build metadata-rich input for the LLM
    combined_summaries = ""
    for s in summaries:
        meta_info = []
        if s.get("reporter"):
            meta_info.append(f"By {s['reporter']}")
        if s.get("newsletter_type"):
            meta_info.append(f"Newsletter: {s['newsletter_type']}")
        urls = s.get("urls", [])
        if urls:
            meta_info.append(f"Links: {len(urls)} URLs")
        meta_str = " | ".join(meta_info) if meta_info else ""
        combined_summaries += f"\n--- [{meta_str}]\n{s['summary_text']}\n"

    prompt = f"""You are a senior financial news editor. Below are summaries of {len(summaries)} Bloomberg newsletters from {target_date}.

Each summary includes metadata: reporter/byline, newsletter type, and link count. Use this to add attribution and identity to each section.

Produce a FULL DAILY DIGEST in HTML. Use <h2>, <h3>, <p>, <ul>, <li>, <strong>, <em>, <table>, <tr>, <td>, <a>, <div> tags. NO <html>/<head>/<body> tags — just content.

<h2>Bloomberg Daily Digest — {target_date}</h2>

<h3>🔥 Critical Headlines</h3>
Top 15 headlines ranked by impact. Each with 2-3 sentences of context + numbers + <em>category</em>.

<h3>📊 Market Data Snapshot</h3>
ALL data points in clean lists grouped by: Equities, Fixed Income, Commodities, FX, Crypto.

<h3>📰 Per-Newsletter Cards</h3>
For EACH newsletter, create a card with:
- Reporter name (if available)
- Newsletter type/identity
- That newsletter's unique angle on shared stories
- List of key URLs as clickable links with 1-line context each

<h3>🌍 Macro & Geopolitical Analysis</h3>
3-5 paragraphs synthesizing major themes and interconnections.

<h3>🤖 Tech & AI</h3>
Detailed analysis of all tech/AI content.

<h3>💹 Markets Strategy & Positioning</h3>
Key positioning themes and smart money flows.

<h3>💡 What to Watch</h3>
5-8 specific items with expected impact.

<h3>🗞️ Full Newsletter Breakdown</h3>
For EACH newsletter: time, subject, sender, reporter + 5-8 bullet points + actionable insights.

NEWSLETTER SUMMARIES:
{combined_summaries}"""

    return llm_call(prompt, max_tokens=8000, temperature=0.3, model=LLM_MODEL_STAGE2)


# ─── Main Pipeline ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Bloomberg Daily Digest Pipeline")
    parser.add_argument("--date", help="Target date YYYY-MM-DD (default: yesterday CDT)")
    parser.add_argument("--brief-only", action="store_true", help="Skip full HTML")
    parser.add_argument("--stage1", action="store_true", help="Only per-newsletter summaries")
    args = parser.parse_args()

    if args.date:
        target_date = args.date
    else:
        now_user = datetime.now(UTC).astimezone(USER_TZ)
        yesterday = now_user - timedelta(days=1)
        target_date = yesterday.strftime("%Y-%m-%d")

    print(f"📊 Bloomberg Digest — {target_date}")

    # ── Step 1: Fetch envelopes ──
    envelopes = fetch_bloomberg_envelopes(target_date)
    print(f"Found {len(envelopes)} Bloomberg newsletters")

    if not envelopes:
        BRIEF_DIR.mkdir(parents=True, exist_ok=True)
        (BRIEF_DIR / f"{target_date}.md").write_text(f"No Bloomberg newsletters on {target_date}.")
        print(f"No newsletters for {target_date}")
        return

    # ── Step 2: Read emails + extract content ──
    emails_with_content = []
    for e in envelopes:
        print(f"  📥 Reading: {e['subject'][:55]}...")
        try:
            raw_body = read_email_body(str(e["id"]))
            content = extract_key_content(raw_body)

            from_name = ""
            if isinstance(e["from"], dict):
                from_name = e["from"].get("name", e["from"].get("addr", ""))
            else:
                from_name = str(e["from"])

            # Extract metadata from raw body
            meta = extract_newsletter_metadata(raw_body)
            # Extract URLs from HTML version (preserves links that plain text strips)
            meta["urls"] = extract_urls_from_html(str(e["id"]), ACCOUNT)

            # Save raw
            RAW_DIR.mkdir(parents=True, exist_ok=True)
            (RAW_DIR / f"{target_date}_{e['id']}.txt").write_text(raw_body)

            emails_with_content.append({
                "id": e["id"],
                "subject": e["subject"],
                "from_name": from_name,
                "date_local": e["date_local"],
                "content": content,
                "raw_body": raw_body,  # keep for metadata
                "reporter": meta["reporter"],
                "newsletter_type": meta["newsletter_type"],
                "urls": meta["urls"],
            })
        except Exception as ex:
            print(f"  ⚠️ Error reading {e['id']}: {ex}")

    if not emails_with_content:
        print("No content extracted")
        return

    # ── Step 3: Stage 1 — Per-newsletter summaries ──
    print(f"\n🤖 Stage 1: Summarizing {len(emails_with_content)} newsletters...")
    summaries = []
    SUMM_DIR.mkdir(parents=True, exist_ok=True)

    for i, e in enumerate(emails_with_content):
        print(f"  [{i+1}/{len(emails_with_content)}] {e['subject'][:50]}...")
        try:
            summary = summarize_single_newsletter(
                e["subject"], e["from_name"], e["date_local"], e["content"]
            )
            # Save individual summary
            (SUMM_DIR / f"{target_date}_{e['id']}.txt").write_text(summary)

            summaries.append({
                "id": e["id"],
                "subject": e["subject"],
                "from_name": e["from_name"],
                "date_local": e["date_local"],
                "summary_text": summary,
                "reporter": e.get("reporter"),
                "newsletter_type": e.get("newsletter_type"),
                "urls": e.get("urls", []),
            })
        except Exception as ex:
            print(f"  ⚠️ Error summarizing {e['id']}: {ex}")
            # Use raw content as fallback
            summaries.append({
                "id": e["id"],
                "subject": e["subject"],
                "from_name": e["from_name"],
                "date_local": e["date_local"],
                "summary_text": f"Subject: {e['subject']}\n{e['content'][:500]}",
                "reporter": e.get("reporter"),
                "newsletter_type": e.get("newsletter_type"),
                "urls": e.get("urls", []),
            })

    if args.stage1:
        print(f"\nStage 1 complete. {len(summaries)} summaries saved to {SUMM_DIR}")
        return

    # ── Step 3.5: Extract entities and themes ──
    print(f"\n🧠 Extracting entities and themes...")
    newsletters_with_entities = []
    for i, s in enumerate(summaries):
        print(f"  [{i+1}/{len(summaries)}] {s['subject'][:50]}...")
        entities_data = extract_entities_and_themes(s["summary_text"], s["subject"])
        newsletters_with_entities.append({
            **s,
            "entities": entities_data.get("entities", {}),
            "themes": entities_data.get("themes", []),
            "facts": entities_data.get("facts", []),
            "opinions": entities_data.get("opinions", []),
            "sentiment": entities_data.get("sentiment", "neutral"),
            "key_metrics": entities_data.get("key_metrics", [])
        })

    # ── Step 3.6: Update cumulative knowledge base ──
    print(f"\n📚 Updating knowledge base...")
    kb = update_knowledge_base(target_date, newsletters_with_entities)

    # ── Step 4: Deduplicate overlapping stories ──
    print(f"\n🔀 Deduplicating overlapping stories...")
    summaries = deduplicate_summaries(summaries)

    # ── Step 4: Stage 2 — Combined digest ──
    print(f"\n🤖 Stage 2: Building brief digest...")
    try:
        brief = build_brief_digest(summaries, target_date)
    except Exception as ex:
        print(f"  ⚠️ Brief generation failed: {ex}")
        # Fallback: just concatenate individual summaries
        brief = f"## Bloomberg Daily Brief — {target_date}\n\n"
        for s in summaries:
            brief += f"### {s['date_local']} — {s['subject']}\n{s['summary_text']}\n\n"

    # Save brief
    BRIEF_DIR.mkdir(parents=True, exist_ok=True)
    brief_path = BRIEF_DIR / f"{target_date}.md"
    brief_path.write_text(brief)
    print(f"  ✅ Brief saved: {brief_path}")

    full_html = ""
    if not args.brief_only:
        print(f"🤖 Stage 2: Building full digest...")
        try:
            full_html = build_full_digest(summaries, target_date)
            FULL_DIR.mkdir(parents=True, exist_ok=True)
            full_path = FULL_DIR / f"{target_date}.html"
            full_path.write_text(full_html)
            print(f"  ✅ Full saved: {full_path}")
        except Exception as ex:
            print(f"  ⚠️ Full generation failed: {ex}")

    # ── Step 5: Output brief to stdout ──
    print(f"\n{'='*60}")
    print(f"BLOOMBERG DAILY BRIEF — {target_date}")
    print(f"{'='*60}")
    print(brief)

    # ── Step 6: Save metadata JSON for portal ──
    meta = {
        "date": target_date,
        "newsletter_count": len(emails_with_content),
        "newsletters": [
            {
                "id": s["id"],
                "subject": s["subject"],
                "from_name": s["from_name"],
                "date_local": s["date_local"],
                "reporter": s.get("reporter"),
                "newsletter_type": s.get("newsletter_type"),
                "urls": s.get("urls", []),
            }
            for s in summaries
        ],
        "brief_path": str(brief_path),
        "full_path": str(FULL_DIR / f"{target_date}.html") if full_html else None,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    (OUTPUT_DIR / f"{target_date}.json").write_text(json.dumps(meta, indent=2))

    # ── Step 7: Save complete newsletter index (pre-dedup) for knowledge base ──
    # This preserves per-newsletter identity even when dedup merges stories
    kb_index = {
        "date": target_date,
        "raw_count": len(emails_with_content),
        "deduped_count": len(summaries),
        "newsletters": [
            {
                "id": e["id"],
                "subject": e["subject"],
                "from_name": e["from_name"],
                "date_local": e["date_local"],
                "reporter": e.get("reporter"),
                "newsletter_type": e.get("newsletter_type"),
                "url_count": len(e.get("urls", [])),
                "urls": e.get("urls", []),
                "summary_preview": e.get("content", "")[:500],
            }
            for e in emails_with_content
        ],
    }
    (OUTPUT_DIR / f"{target_date}_index.json").write_text(json.dumps(kb_index, indent=2))

    # ── Step 8: Save links for potential expansion ──
    LINKS_DIR.mkdir(parents=True, exist_ok=True)
    all_links = []
    for e in emails_with_content:
        for url in e.get("urls", []):
            all_links.append({
                "newsletter_id": e["id"],
                "newsletter_type": e.get("newsletter_type"),
                "reporter": e.get("reporter"),
                "subject": e["subject"],
                "url": url,
            })
    if all_links:
        (LINKS_DIR / f"{target_date}_links.json").write_text(
            json.dumps(all_links, indent=2)
        )
        print(f"  🔗 Links saved: {len(all_links)} URLs → {LINKS_DIR / f'{target_date}_links.json'}")


if __name__ == "__main__":
    main()
