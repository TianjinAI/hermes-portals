#!/usr/bin/env python3
"""
Intel Digest Generator — LLM-powered thematic intelligence digest.
Generates digest.json from Bloomberg briefs using Deepseek API.

Usage: python3 intel_digest_generator.py [--days 14] [--output intel/digest.json]

Schedule: Friday-only (US CDT morning = ~14:00 UTC)
           2-week lookback window (--days 14)
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ─── Config ──────────────────────────────────────────────────────────────
BASE_DIR = Path(os.path.expanduser("~/.hermes/bloomberg_digest"))
BRIEFS_DIR = BASE_DIR / "briefs"
INTEL_DIR = BASE_DIR / "intel"
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# ─── Helpers ──────────────────────────────────────────────────────────────

def get_api_key():
    env_path = Path("/home/admin/.hermes/.env")
    with open(env_path) as f:
        for line in f:
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("DEEPSEEK_API_KEY not found in .env")


def llm_call(prompt: str, max_tokens: int = 12288) -> str:
    """Call Deepseek API for structured generation."""
    api_key = get_api_key()
    messages = [
        {"role": "system", "content": "You are a senior macro intelligence analyst. You produce structured JSON digests that are accurate, data-rich, and actionable. Never invent data — only synthesize from provided sources."},
        {"role": "user", "content": prompt}
    ]

    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "stream": False,
    })

    result = subprocess.run(
        ["curl", "-s", "--max-time", "180", "-X", "POST", DEEPSEEK_URL,
         "-H", f"Authorization: Bearer {api_key}",
         "-H", "Content-Type: application/json",
         "-d", payload],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=200
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr}")
    data = json.loads(result.stdout.strip())
    if "error" in data:
        raise RuntimeError(f"API error: {data['error']}")
    return data["choices"][0]["message"].get("content", "")


def read_briefs(days: int) -> list[dict]:
    """Read brief markdown files from the last N days."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    briefs = []
    for md_file in sorted(BRIEFS_DIR.rglob("*.md")):
        date_str = md_file.stem
        try:
            file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if file_date >= cutoff:
            content = md_file.read_text(encoding="utf-8")
            if len(content.strip()) > 100:  # Skip tiny/empty briefs
                briefs.append({"date": date_str, "content": content[:4000]})
    return briefs


def build_prompt(briefs: list[dict], date_range: str) -> str:
    """Build the prompt for Intel digest generation."""
    brief_text = "\n\n".join(
        f"### {b['date']}\n{b['content']}" for b in briefs
    )
    prompt = f"""You are an intelligence analyst producing a weekly briefing for senior decision-makers.

Analyze the following Bloomberg daily briefs from {date_range} and synthesize a thematic intelligence digest.

{brief_text}

---

Generate a JSON response with this exact structure:
{{
  "executive_summary": "A 3-5 sentence executive summary covering the most important cross-cutting themes from this period.",
  "themes": [
    {{
      "name": "Theme name (e.g., 'Hormuz Crisis Reshapes Global Energy Markets')",
      "relevance": "Why this theme matters to investors/policymakers right now (1-2 sentences)",
      "synthesis": "A 3-4 paragraph synthesis connecting all related developments across the lookback period. Identify pattern shifts, inflection points, and what's changed.",
      "highlights": [
        "3-5 bullet-point highlights, each a complete sentence of market-relevant insight"
      ],
      "articles": [
        {{"date": "YYYY-MM-DD", "headline": "Key article headline from that day's brief"}},
        ...
      ]
    }},
    ... (5-8 themes, ordered by importance)
  ],
  "generated_at": "ISO timestamp",
  "briefs_analyzed": N,
  "date_range": {{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}}
}}

Guidelines:
- Themes must be MACRO-RELEVANT: markets, geopolitics, monetary policy, energy, technology, trade
- No filler themes. Every theme must be actionable for investment decisions.
- Synthesis should connect dots across dates — show the arc of the story, not isolated events.
- Highlights must be punchy and data-rich, not generic observations.
- Articles must reference actual headlines from the briefs, not invented.
- Return ONLY valid JSON. No markdown, no code fences, no preamble."""
    return prompt


def main():
    parser = argparse.ArgumentParser(description="Generate Intel digest from Bloomberg briefs")
    parser.add_argument("--days", type=int, default=14, help="Lookback window in days")
    parser.add_argument("--output", type=str, default=str(INTEL_DIR / "digest.json"),
                        help="Output path for digest JSON")
    args = parser.parse_args()

    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    # Read briefs
    briefs = read_briefs(args.days)
    if not briefs:
        print("No briefs found in lookback window. Exiting.")
        sys.exit(1)

    dates = sorted(b['date'] for b in briefs)
    date_range_str = f"{dates[0]} to {dates[-1]}"
    print(f"Read {len(briefs)} briefs from {date_range_str}")

    # Generate digest
    prompt = build_prompt(briefs, date_range_str)

    print("Generating Intel digest via Deepseek... (this may take 2-4 min)")
    response = llm_call(prompt, max_tokens=12288)

    # Parse and validate JSON
    response = response.strip()
    # Strip markdown code fences if present
    if response.startswith("```"):
        lines = response.split("\n")
        response = "\n".join(lines[1:])  # Remove first fence line
        if response.endswith("```"):
            response = response[:-3].strip()
    if response.endswith("```"):
        response = response[:-3].strip()

    try:
        digest = json.loads(response)
    except json.JSONDecodeError:
        # Try to extract JSON from within the response
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            digest = json.loads(match.group(0))
        else:
            print(f"Failed to parse JSON. Raw response: {response[:500]}")
            sys.exit(1)

    # Add metadata
    digest["generated_at"] = datetime.now(timezone.utc).isoformat()
    digest["briefs_analyzed"] = len(briefs)
    digest["date_range"] = {"start": dates[0], "end": dates[-1]}

    # Write output
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(digest, f, indent=2, ensure_ascii=False)

    print(f"Intel digest saved to {args.output}")
    print(f"  Themes: {len(digest.get('themes', []))}")
    print(f"  Briefs analyzed: {digest['briefs_analyzed']}")
    print(f"  Date range: {digest['date_range']['start']} to {digest['date_range']['end']}")


if __name__ == "__main__":
    main()
