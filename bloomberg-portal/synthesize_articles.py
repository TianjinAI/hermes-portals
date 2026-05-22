#!/usr/bin/env python3
"""
Stage 3: Synthesize full articles from Bloomberg newsletter digests.
Generates detailed prose articles for each top headline.

Usage:
  python3 synthesize_articles.py                    # Yesterday's date
  python3 synthesize_articles.py --date 2026-05-15  # Specific date
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ─── Config ──────────────────────────────────────────────────────────────
# Use explicit base dir — avoids Path.home() returning profile subdir
BASE_DIR = Path("/home/admin/.hermes/bloomberg_digest")
DIGEST_DIR = BASE_DIR
ARTICLES_DIR = DIGEST_DIR / "articles"
SUMMARIES_DIR = DIGEST_DIR / "summaries"
OUTPUT_DIR = DIGEST_DIR

# Deepseek direct API
LLM_BASE_URL = "https://api.deepseek.com/v1"
LLM_MODEL = "deepseek-chat"

# Timezone
USER_TZ = timezone(timedelta(hours=-5))  # CDT
UTC = timezone.utc


# ─── Helpers ─────────────────────────────────────────────────────────────

def get_api_key():
    env_path = Path("/home/admin/.hermes/.env")
    if not env_path.exists():
        env_path = Path("/home/admin/.env")
    with open(env_path) as f:
        for line in f:
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.strip().split("=", 1)[1]
    raise RuntimeError("DEEPSEEK_API_KEY not found in .env")


def llm_call(prompt: str, system: str = None, max_tokens: int = 4096,
             temperature: float = 0.3, model: str = None) -> str:
    """Call Deepseek API directly (non-streaming JSON)."""
    if model is None:
        model = LLM_MODEL
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
        "stream": False,
    })

    import subprocess
    result = subprocess.run(
        ["curl", "-s", "-X", "POST",
         f"{LLM_BASE_URL}/chat/completions",
         "-H", f"Authorization: Bearer {api_key}",
         "-H", "Content-Type: application/json",
         "-d", payload],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120
    )

    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr}")

    data = json.loads(result.stdout.strip())

    if "error" in data:
        raise RuntimeError(f"API error: {data['error']}")

    return data["choices"][0]["message"].get("content", "")


def extract_top_headlines(brief_md: str, max_count: int = 8) -> list:
    """Extract top headlines from brief markdown — parse numbered list items."""
    headlines = []
    # Match lines starting with a number followed by period or close paren
    pattern = r'^\s*(\d+)[\.\)]\s+\*\*([^*]+)\*\*'
    for line in brief_md.split('\n'):
        m = re.match(pattern, line)
        if m:
            rank = int(m.group(1))
            title = m.group(2).strip()
            # Grab context: the rest of the line after **title** —
            rest = line.split('**', 2)[-1] if '**' in line else ''
            context = rest.lstrip(' —').strip() if '—' in line else ''
            headlines.append({
                "rank": rank,
                "title": title,
                "context": context,
                "category": "General",
            })
        if len(headlines) >= max_count:
            break
    return headlines


def load_date_data(target_date: str) -> dict:
    """Load all data for a given date."""
    # Load index (newsletters + entity data)
    index_path = DIGEST_DIR / f"{target_date}_index.json"
    meta_path = DIGEST_DIR / f"{target_date}.json"

    newsletters = []
    if index_path.exists():
        with open(index_path) as f:
            index_data = json.load(f)
            newsletters = index_data.get("newsletters", [])

    # Load individual summaries
    summaries = []
    for nl in newsletters:
        nid = nl.get("id", "")
        summ_path = SUMMARIES_DIR / f"{target_date}_{nid}.txt"
        if summ_path.exists():
            summaries.append({
                "newsletter": nl,
                "summary": summ_path.read_text(encoding="utf-8", errors="replace"),
            })

    # Load brief markdown for headline extraction
    brief_path = DIGEST_DIR / "briefs" / f"{target_date}.md"
    brief_md = ""
    if brief_path.exists():
        brief_md = brief_path.read_text(encoding="utf-8", errors="replace")

    return {
        "date": target_date,
        "newsletters": newsletters,
        "summaries": summaries,
        "brief_md": brief_md,
    }


def synthesize_article(headline: dict, summaries_data: list,
                       article_number: int, total: int) -> dict:
    """Generate a full prose article for a single headline."""
    title = headline.get("title", "Untitled")
    rank = headline.get("rank", 0)

    # Build context from available summaries
    # Find summaries most likely to cover this headline
    relevant = []
    title_words = set(title.lower().split())
    for item in summaries_data:
        summ = item.get("summary", "")
        # Score by word overlap
        words = set(summ.lower().split())
        score = len(title_words & words)
        relevant.append((score, item))
    relevant.sort(key=lambda x: -x[0])
    top_summaries = [item for _, item in relevant[:5]]  # Use top 5 most relevant

    summaries_text = "\n\n".join([
        f"--- {s['newsletter'].get('subject','')[:80]} ---\n{s['summary'][:1500]}"
        for s in top_summaries
    ])

    system = """You are a Bloomberg Intelligence senior editor writing a detailed news article.
Write a well-structured, 400-600 word article in flowing prose (not bullet points).
Include:
1. Opening paragraph with key takeaway and why it matters
2. Background and context
3. Key facts, figures, and numbers
4. Stakeholder perspectives (government, markets, companies, analysts)
5. Forward outlook / what to watch

Use authoritative, neutral financial journalism tone. No hype, no speculation without attribution.
Reference specific entities, figures, and dates. Mark key numbers in **bold**.
Do NOT use bullet points in the article body — only in the Key Facts section if needed."""

    prompt = f"""Article {article_number} of {total}: "{title}"
Context: {headline.get('context', 'No additional context')}

Source newsletters (summaries):
{summaries_text[:8000]}

Write the full article now. Start directly with the article text — no preamble like "Here is the article" or "Article {article_number}:"."""

    article_text = llm_call(
        prompt,
        system=system,
        max_tokens=4096,
        temperature=0.3,
    )

    # Collect source attribution
    sources = []
    for s in top_summaries[:3]:
        nl = s.get("newsletter", {})
        src_name = nl.get("subject", "Bloomberg")[:60]
        src_from = nl.get("from_name", "Bloomberg")
        sources.append({
            "newsletter": src_name,
            "from": src_from,
        })

    # Collect links from relevant newsletters
    links = []
    for s in top_summaries[:3]:
        for url in s.get("newsletter", {}).get("urls", [])[:3]:
            if url not in links:
                links.append(url)

    return {
        "title": title,
        "rank": rank,
        "article": article_text.strip(),
        "sources": sources,
        "links": links[:10],
        "category": headline.get("category", "General"),
    }


def run(target_date: str):
    print(f"📝 Synthesize Articles — {target_date}")

    data = load_date_data(target_date)
    if not data["summaries"]:
        print(f"  ⚠️ No newsletter summaries found for {target_date}")
        return

    headlines = extract_top_headlines(data["brief_md"], max_count=8)
    if not headlines:
        print(f"  ⚠️ No headlines extracted from brief. Using first few newsletters.")
        # Fallback: use newsletter subjects as headlines
        for i, nl in enumerate(data["newsletters"][:6]):
            headlines.append({
                "rank": i + 1,
                "title": nl.get("subject", "Untitled")[:100],
                "context": "",
                "category": "General",
            })

    print(f"  Found {len(headlines)} headlines, generating articles...")

    articles = []
    for i, headline in enumerate(headlines):
        print(f"  [{i+1}/{len(headlines)}] {headline['title'][:60]}...")
        try:
            article = synthesize_article(headline, data["summaries"], i+1, len(headlines))
            articles.append(article)
        except Exception as ex:
            print(f"    ⚠️ Failed: {ex}")
            articles.append({
                "title": headline["title"],
                "rank": headline["rank"],
                "article": "[Article generation failed — source newsletters may be used directly.]",
                "sources": [],
                "links": [],
                "category": headline.get("category", "General"),
            })

    # Save
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "date": target_date,
        "generated_at": datetime.now(UTC).isoformat(),
        "headline_count": len(articles),
        "articles": articles,
    }
    out_path = ARTICLES_DIR / f"{target_date}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"  ✅ {len(articles)} articles → {out_path}")

    return out


def main():
    parser = argparse.ArgumentParser(description="Synthesize Bloomberg articles")
    parser.add_argument("--date", help="Target date YYYY-MM-DD (default: yesterday)")
    args = parser.parse_args()

    if args.date:
        target_date = args.date
    else:
        now_user = datetime.now(UTC).astimezone(USER_TZ)
        yesterday = now_user - timedelta(days=1)
        target_date = yesterday.strftime("%Y-%m-%d")

    run(target_date)


if __name__ == "__main__":
    main()