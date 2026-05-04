#!/usr/bin/env python3
"""Generate LLM summaries for all items in state.json that lack them."""

import json
import os
import subprocess
import sys
import re
import time

REVIEW_DIR = os.path.expanduser('~/.hermes/readwise_review')
STATE_FILE = os.path.join(REVIEW_DIR, 'state.json')
EXPORT_DIR = os.path.expanduser('~/.hermes/readwise_export/reader_md')

def load_state():
    with open(STATE_FILE) as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def read_item_content(filepath):
    """Read the body content from a markdown file."""
    if not filepath or not os.path.exists(filepath):
        return ""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        # Extract body (after frontmatter)
        if content.startswith('---'):
            end = content.find('---', 3)
            if end != -1:
                content = content[end+3:].strip()
        return content
    except:
        return ""

def call_llm(prompt):
    """Call opencode CLI to generate a response."""
    try:
        result = subprocess.run(
            ['timeout', '120', 'opencode', 'run', prompt, '--model', 'opencode-go/glm-5'],
            capture_output=True, text=True, timeout=130
        )
        return result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return None, "Timeout"
    except Exception as e:
        return None, str(e)

def generate_summary(item, content):
    """Generate a summary for a single item."""
    title = item.get('title', 'Untitled')[:100]
    url = item.get('url', '')
    author = item.get('author', 'Unknown')
    category = item.get('category', 'unknown')
    folder = item.get('folder', 'Other')
    
    # YouTube items: use transcript if available
    has_transcript = item.get('has_transcript', False)
    transcript_preview = item.get('transcript_preview', '')
    
    # Prepare content snippet
    content_snippet = content[:3000] if content else transcript_preview[:3000] if transcript_preview else ''
    
    # Use a more detailed prompt for YouTube content
    is_yt = 'youtube.com' in url or 'youtu.be' in url
    
    language_hint = "Chinese (zh)"
    # Simple language detection
    if content_snippet and len(re.findall(r'[\u4e00-\u9fff]', content_snippet)) < 10:
        language_hint = "English (en)"
    
    prompt = f"""You are a professional content curator. Generate a structured summary for the following item.

Title: {title}
URL: {url}
Author: {author}
Category: {category}
Folder: {folder}
Item Type: {"YouTube Video (with transcript)" if is_yt and has_transcript else "YouTube Video" if is_yt else category}

Content:
{content_snippet[:2500]}

Return ONLY valid JSON (no markdown, no code fences), with these exact fields:
- "summary": a 1-2 sentence summary in {language_hint}
- "detailed_summary": a 3-5 sentence detailed summary in {language_hint} using llm-wiki format with markdown
- "key_points": array of 3-5 key points in {language_hint}
- "topics": array of 2-4 topic tags in {language_hint}
- "language": "zh" or "en"
"""
    return prompt

def main():
    state = load_state()
    
    # Find items needing summaries
    need_summary = []
    for i, item in enumerate(state['items']):
        has_s = ('summary' in item and item['summary'] and 
                 item['summary'].get('summary') and 
                 item['summary']['summary'] != '[待处理]')
        if not has_s:
            need_summary.append((i, item))
    
    total = len(need_summary)
    print(f"Items needing summaries: {total}")
    
    if total == 0:
        print("Nothing to do!")
        return
    
    # Process with progress indicators
    for idx, (item_idx, item) in enumerate(need_summary):
        title = item.get('title', 'Untitled')[:60]
        print(f"\n[{idx+1}/{total}] {title}")
        sys.stdout.flush()
        
        # Read content
        filepath = item.get('filepath', '')
        content = read_item_content(filepath)
        
        # Generate prompt
        prompt = generate_summary(item, content)
        
        # The prompt for YouTube with transcript items - save context by being concise
        is_yt = 'youtube.com' in item.get('url','') or 'youtu.be' in item.get('url','')
        has_t = item.get('has_transcript', False)
        
        if is_yt and has_t and item.get('transcript_preview'):
            # For YouTube items with transcripts, include the full transcript preview
            tp = item.get('transcript_preview', '')
            content_snippet = tp[:2500]
        
        # Call LLM
        stdout, stderr = call_llm(prompt)
        
        if not stdout:
            print(f"  ❌ LLM call failed: {stderr[:200]}")
            continue
        
        # Extract JSON from output
        json_match = re.search(r'\{[\s\S]*\}', stdout)
        if not json_match:
            print(f"  ❌ No JSON found in output")
            print(f"     Output: {stdout[:200]}")
            continue
        
        try:
            summary_data = json.loads(json_match.group(0))
            state['items'][item_idx]['summary'] = summary_data
            save_state(state)
            print(f"  ✅ Summary saved ({len(summary_data.get('summary',''))} chars, {len(summary_data.get('key_points',[]))} key points)")
        except json.JSONDecodeError as e:
            print(f"  ❌ JSON parse error: {e}")
            print(f"     Raw: {json_match.group(0)[:200]}")
        
        # Rate limit
        time.sleep(0.5)
    
    # Final summary
    with_s = sum(1 for i in state['items'] if 'summary' in i and i['summary'] and i['summary'].get('summary') and i['summary']['summary'] != '[待处理]')
    print(f"\n{'='*40}")
    print(f"Done! {with_s}/{len(state['items'])} items now have summaries")
    print(f"{'='*40}")

if __name__ == '__main__':
    main()
