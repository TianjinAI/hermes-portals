#!/usr/bin/env python3
"""
Readwise Review Pipeline with YouMind YouTube integration.
"""

import json
import os
import subprocess
import sys
import re
from datetime import datetime, timezone
from pathlib import Path

REVIEW_DIR = os.path.expanduser('~/.hermes/readwise_review')
STATE_FILE = os.path.join(REVIEW_DIR, 'state.json')
EXPORT_DIR = os.path.expanduser('~/.hermes/readwise_export/reader_md')
YOUMIND_SCRIPT = os.path.join(REVIEW_DIR, 'youmind_transcript.py')

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        'last_export': None,
        'last_updated': None,
        'items': [],
        'decisions': {},
        'processed_ids': [],
        'history_count': 0
    }

def save_state(state):
    os.makedirs(REVIEW_DIR, exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def parse_frontmatter(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if content.startswith('---'):
        end = content.find('---', 3)
        if end != -1:
            fm_text = content[3:end].strip()
            body = content[end+3:].strip()
            
            fm = {}
            for line in fm_text.split('\n'):
                if ':' in line:
                    key, _, value = line.partition(':')
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    if key == 'tags':
                        if value.startswith('['):
                            fm[key] = [t.strip().strip("'\"") for t in value[1:-1].split(',') if t.strip()]
                        else:
                            fm[key] = []
                    else:
                        fm[key] = value
            
            return fm, body
    
    return {}, content

def fetch_youtube_transcript(url):
    """Fetch YouTube transcript using YouMind."""
    api_key = os.environ.get('YOUMIND_API_KEY', '')
    if not api_key:
        # Try to load from .env
        env_file = os.path.expanduser('~/.hermes/.env')
        if os.path.exists(env_file):
            with open(env_file) as f:
                for line in f:
                    if line.startswith('YOUMIND_API_KEY='):
                        api_key = line.strip().split('=', 1)[1]
                        break
    
    if not api_key:
        return None, "YOUMIND_API_KEY not set"
    
    env = os.environ.copy()
    env['YOUMIND_API_KEY'] = api_key
    
    try:
        # Save URL as material
        result = subprocess.run(
            ['youmind', 'call', 'createMaterialByUrl', '--url', url],
            capture_output=True,
            text=True,
            env=env,
            timeout=30
        )
        
        if result.returncode != 0:
            return None, f"Error: {result.stderr}"
        
        data = json.loads(result.stdout)
        material_id = data.get('id')
        
        if not material_id:
            return None, "No material ID returned"
        
        # Wait for processing — up to 60 seconds. If YouMind can't get it by then, it won't.
        import time
        max_attempts = 12
        for attempt in range(max_attempts):
            time.sleep(5)
            
            if attempt % 6 == 0 and attempt > 0:
                elapsed = (attempt + 1) * 5
                print(f"  ⏳ Still waiting for transcript... ({elapsed}s)")
            
            result = subprocess.run(
                ['youmind', 'call', 'getMaterial', '--id', material_id, '--includeBlocks', 'true'],
                capture_output=True,
                text=True,
                env=env,
                timeout=30
            )
            
            if result.returncode != 0:
                continue
            
            material = json.loads(result.stdout)
            
            # Check for transcript
            transcript = material.get('transcript', {})
            if transcript and transcript.get('contents'):
                content = transcript['contents'][0]
                if content.get('status') == 'completed':
                    return content.get('plain', ''), None
        
        return None, "Transcript not available via YouMind (YouTube likely lacks API-accessible captions)"
    
    except subprocess.TimeoutExpired:
        return None, "Timeout"
    except Exception as e:
        return None, str(e)

def fetch_youtube_transcript_notebooklm(url, title=""):
    """Fetch YouTube transcript via NotebookLM CLI.
    
    NotebookLM can transcribe any YouTube video, with or without subtitles.
    Uses a dedicated 'Hermes-Transcripts' notebook for all sources.
    """
    COOKIE_STR = None
    profile_file = os.path.expanduser('~/.notebooklm-mcp-cli/profiles/default/cookies.json')
    if os.path.exists(profile_file):
        import json
        with open(profile_file) as f:
            d = json.load(f)
        COOKIE_STR = "; ".join(f"{k}={v}" for k, v in d.items())

    env = os.environ.copy()
    if COOKIE_STR:
        env["NOTEBOOKLM_COOKIES"] = COOKIE_STR

    import subprocess, json
    
    # 1. Get or create the dedicated notebook
    try:
        result = subprocess.run(
            ["nlm", "notebook", "list"],
            capture_output=True, text=True, env=env, timeout=15
        )
        notebooks = json.loads(result.stdout)
        nb_id = None
        for nb in notebooks:
            if nb.get("title") == "Hermes-Transcripts":
                nb_id = nb["id"]
                break
        if not nb_id:
            result = subprocess.run(
                ["nlm", "notebook", "create", "Hermes-Transcripts"],
                capture_output=True, text=True, env=env, timeout=15
            )
            output = result.stdout
            import re
            match = re.search(r'[a-f0-9-]{36}', output)
            if not match:
                return None, "Failed to create NotebookLM notebook"
            nb_id = match.group(0)
    except Exception as e:
        return None, f"NotebookLM setup failed: {e}"

    # 2. Add YouTube source with a unique-ish title to deduplicate
    short_title = title[:80] if title else "YouTube"
    try:
        result = subprocess.run(
            ["nlm", "source", "add", nb_id, "--youtube", url, "--wait", "--wait-timeout", "600"],
            capture_output=True, text=True, env=env, timeout=620
        )
        if result.returncode != 0:
            return None, f"NotebookLM source add failed: {result.stderr[:200]}"
        
        # Extract source ID from output
        import re
        sid_match = re.search(r'Source ID: ([a-f0-9-]{36})', result.stdout)
        if not sid_match:
            return None, "Could not find source ID in NotebookLM output"
        source_id = sid_match.group(1)
    except subprocess.TimeoutExpired:
        return None, "NotebookLM processing timed out (video may be very long)"
    except Exception as e:
        return None, f"NotebookLM source add error: {e}"

    # 3. Get the content/transcript
    try:
        result = subprocess.run(
            ["nlm", "source", "content", source_id],
            capture_output=True, text=True, env=env, timeout=15
        )
        if result.returncode != 0:
            return None, f"NotebookLM content fetch failed: {result.stderr[:200]}"
        
        data = json.loads(result.stdout)
        transcript = data.get("value", {}).get("content", "")
        if transcript:
            return transcript, None
        return None, "NotebookLM returned empty content"
    except Exception as e:
        return None, f"NotebookLM content error: {e}"

def main():
    """Import existing Readwise export into the review portal."""
    print("=" * 60)
    print("Readwise Pipeline (with YouMind YouTube integration)")
    print("=" * 60)
    
    state = load_state()
    
    # Check for new items from export
    md_files = list(Path(EXPORT_DIR).rglob('*.md'))
    print(f"Found {len(md_files)} markdown files in export")
    
    new_items = []
    for filepath in md_files:
        filename = filepath.stem
        doc_id = filename.split('(')[-1].rstrip(')') if '(' in filename else filename
        
        if doc_id in state['processed_ids']:
            continue
        
        fm, body = parse_frontmatter(filepath)
        
        title = fm.get('title', 'Untitled')
        category = fm.get('category', 'unknown')
        url = fm.get('url', '')
        author = fm.get('author', 'Unknown')
        published_date = fm.get('published_date', '')
        
        is_youtube = 'youtube.com' in url or 'youtu.be' in url
        
        transcript = None
        transcript_source = None
        if is_youtube:
            if not body.startswith('Unfortunately'):
                print(f"  📺 YouMind: {title[:50]}...")
                transcript, error = fetch_youtube_transcript(url)
                if transcript:
                    print(f"    ✅ YouMind got transcript ({len(transcript)} chars)")
                    transcript_source = "youmind"
                else:
                    print(f"    ⚠️ YouMind: {error or 'no transcript'}")
            
            if not transcript:
                print(f"  🧠 NotebookLM: {title[:50]}...")
                transcript, error = fetch_youtube_transcript_notebooklm(url, title)
                if transcript:
                    print(f"    ✅ NotebookLM got transcript ({len(transcript)} chars)")
                    transcript_source = "notebooklm"
                else:
                    print(f"    ⚠️ NotebookLM: {error}")
        
        # Determine folder
        folder_map = {
            'email': 'Email',
            'rss': 'RSS',
            'article': 'Articles',
            'podcast': 'Podcasts',
            'video': 'Videos',
            'pdf': 'PDFs'
        }
        
        if is_youtube:
            folder = 'YouTube'
        else:
            folder = folder_map.get(category, 'Other')
        
        # Create content for summarization
        content = body
        if transcript:
            content = f"[YouTube Transcript]\n{transcript}\n\n[Original Content]\n{body}"
        
        item = {
            'id': doc_id,
            'title': title,
            'author': author,
            'category': category,
            'folder': folder,
            'url': url,
            'published_date': published_date,
            'has_transcript': transcript is not None,
            'transcript_preview': transcript[:500] if transcript else None,
            'content': content[:5000],
            'filepath': str(filepath),
            'processed_at': datetime.now(timezone.utc).isoformat()
        }
        
        new_items.append(item)
        state['processed_ids'].append(doc_id)
    
    state['items'].extend(new_items)
    state['last_export'] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    
    print(f"\nProcessed {len(new_items)} new items")
    print(f"Total items: {len(state['items'])}")
    
    if new_items:
        print(f"\n📝 Generating llm-wiki summaries for {len(new_items)} new items...")
        script = os.path.join(REVIEW_DIR, 'generate_llmwiki.py')
        if os.path.exists(script):
            result = subprocess.run(
                [sys.executable, script],
                capture_output=True, text=True, timeout=600
            )
            if result.returncode == 0:
                print(result.stdout.strip().split('\n')[-1])
                print("✅ Summaries generated successfully")
            else:
                print(f"⚠️ Summary generation failed: {result.stderr[:200]}")
        else:
            print(f"⚠️ generate_llmwiki.py not found at {script}")

if __name__ == '__main__':
    main()
