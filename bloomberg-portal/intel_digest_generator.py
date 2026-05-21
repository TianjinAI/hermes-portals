#!/usr/bin/env python3
"""
Bloomberg Intelligence Digest Generator
========================================
Reads Bloomberg daily briefs from the last 14 days, calls LLM (Power_Max via 9Router)
to synthesize standout themes with analytical depth, and saves to intel/digest.json.

Usage:
    python3 intel_digest_generator.py              # Process latest briefs
    python3 intel_digest_generator.py --days 7     # Override lookback window
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

BLOOMBERG_DIR = os.path.expanduser("~/.hermes/bloomberg_digest")
INTEL_DIR = Path(BLOOMBERG_DIR) / "intel"
BRIEFS_DIR = Path(BLOOMBERG_DIR) / "briefs"
DIGEST_FILE = INTEL_DIR / "digest.json"

LLM_URL = "http://localhost:20128/v1/chat/completions"
LLM_MODEL = "Best_China"


def get_api_key():
    """Read 9Router API key from .env."""
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        for line in env_path.read_text().split("\n"):
            if line.startswith("OPENCODE_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key and key != "***":
                    return key
    return os.environ.get("OPENCODE_API_KEY", "")


def load_briefs(days=14):
    """Load brief markdown files from the last N days, newest first."""
    briefs = []
    md_files = sorted(BRIEFS_DIR.glob("*.md"))
    # Take the most recent `days` files (skip weekends = fewer than calendar days)
    for path in md_files[-days:]:
        text = path.read_text(encoding="utf-8").strip()
        if len(text) < 50:
            continue  # Skip near-empty files
        briefs.append({"date": path.stem, "path": str(path), "text": text})
    return briefs


def build_prompt(briefs):
    """Build the synthesis prompt from brief content."""
    lines = []
    lines.append(
        "You are a senior macro research analyst at a top hedge fund. "
        "Review the Bloomberg daily briefs below and synthesize an intelligence report.\n"
        "Identify 5-8 standout THEMES — not keyword buckets or categories, but real narrative threads that cut across multiple briefs.\n"
        "For each theme provide:\n"
        "  - name: punchy, specific theme title (e.g., 'AI IPO Mega-Wave Reshapes Equity Markets')\n"
        "  - relevance: HIGH | MEDIUM | EMERGING\n"
        "  - synthesis: 2-3 paragraph analytical summary — what is happening, why it matters, what is the trajectory\n"
        "  - highlights: 3-5 bullet-point key takeaways\n"
        "  - articles: 3-6 specific headlines from the briefs that substantiate this theme, with date and full headline text\n\n"
        "Also produce:\n"
        "  - executive_summary: 1-2 paragraph top-level narrative of the overall market/intelligence landscape across all briefs\n\n"
        "Output ONLY valid JSON. No markdown fences. No explanation. Structure:\n"
        '{\n'
        '  "executive_summary": "...",\n'
        '  "themes": [\n'
        '    {\n'
        '      "name": "...",\n'
        '      "relevance": "HIGH",\n'
        '      "synthesis": "...",\n'
        '      "highlights": ["...", "..."],\n'
        '      "articles": [{"date": "YYYY-MM-DD", "headline": "..."}]\n'
        '    }\n'
        '  ]\n'
        '}\n\n'
        "=== DAILY BRIEFS ===\n"
    )
    for brief in briefs:
        lines.append(f"\n--- {brief['date']} ---\n")
        # Truncate very long briefs to avoid context overflow
        text = brief["text"]
        if len(text) > 1500:
            text = text[:1500] + "\n...[truncated]..."
        lines.append(text)
    lines.append("\n=== END OF BRIEFS ===\n")
    return "\n".join(lines)


def call_llm(prompt: str, max_tokens=4096, temperature=0.3) -> str:
    """Call Power_Max via 9Router HTTP API using curl (no requests dependency)."""
    import subprocess
    import json as json_mod

    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("OPENCODE_API_KEY not found in .env or environment")

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a senior macro research analyst. "
                    "You synthesize market intelligence from daily briefs. "
                    "Always output valid JSON ONLY. No markdown fences, no commentary, no explanation. "
                    "Do NOT wrap output in ```json or ``` blocks. Raw JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": 12288,
        "stream": False,
    }

    payload_bytes = json_mod.dumps(payload).encode("utf-8")
    result = subprocess.run(
        [
            "curl", "-s", LLM_URL,
            "-H", "Content-Type: application/json; charset=utf-8",
            "-H", "Authorization: Bearer " + api_key,
            "-d", "@-",
            "--max-time", "120",
        ],
        input=payload_bytes,
        capture_output=True,
        timeout=130,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr.decode('utf-8', errors='replace')[:200]}")
    data = json_mod.loads(result.stdout)
    content = (
        data.get("choices", [{}])[0].get("message", {}).get("content", "")
    ).strip()
    # Debug: if content empty, dump raw response
    if not content:
        msg = data.get("choices", [{}])[0].get("message", {})
        print(f"[DEBUG] Empty content. Raw message keys: {list(msg.keys())}", file=sys.stderr)
        print(f"[DEBUG] Full response: {json_mod.dumps(data, indent=2)[:2000]}", file=sys.stderr)
        return "{}"
    # Strip any reasoning tokens if they leak
    content = re.sub(r"<\|.*?\|>", "", content, flags=re.DOTALL)
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    # Strip markdown code fences
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    return content


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate intelligence digest from briefs")
    parser.add_argument("--days", type=int, default=14, help="Lookback window (default: 14)")
    parser.add_argument("--dry-run", action="store_true", help="Print prompt only, do not call LLM")
    args = parser.parse_args()

    print(f"Loading briefs from {BRIEFS_DIR} (last {args.days} days)...")
    briefs = load_briefs(days=args.days)
    print(f"Loaded {len(briefs)} briefs")

    if not briefs:
        print("No briefs found. Exiting.")
        sys.exit(0)

    prompt = build_prompt(briefs)

    if args.dry_run:
        print("=== PROMPT ===")
        print(prompt)
        print("=== END PROMPT ===")
        print(f"Prompt length: {len(prompt)} chars, ~{len(prompt)//4} tokens")
        return

    print(f"Calling LLM ({LLM_MODEL}) — this takes 15-60s...")
    try:
        content = call_llm(prompt)
    except Exception as e:
        print(f"LLM call failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Parse and validate JSON
    try:
        digest = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}", file=sys.stderr)
        print(f"First 500 chars of response:\n{content[:500]}", file=sys.stderr)
        sys.exit(1)

    # Add metadata
    digest["generated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    digest["briefs_analyzed"] = len(briefs)
    digest["date_range"] = {
        "start": briefs[0]["date"] if briefs else None,
        "end": briefs[-1]["date"] if briefs else None,
    }

    # Save
    INTEL_DIR.mkdir(parents=True, exist_ok=True)
    DIGEST_FILE.write_text(json.dumps(digest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Digest saved to {DIGEST_FILE}")
    print(f"Themes: {len(digest.get('themes', []))}")
    for theme in digest.get("themes", []):
        art_count = len(theme.get("articles", []))
        print(f"  - {theme['name']} ({theme.get('relevance', '?')}) · {art_count} articles")


if __name__ == "__main__":
    main()
