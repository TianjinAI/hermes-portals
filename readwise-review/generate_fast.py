#!/usr/bin/env python3
"""Generate LLM summaries for all items using claude -p (fast)."""

import json
import os
import subprocess
import sys
import re
import time

REVIEW_DIR = os.path.expanduser('~/.hermes/readwise_review')
STATE_FILE = os.path.join(REVIEW_DIR, 'state.json')

def load_state():
    with open(STATE_FILE) as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def read_content(item):
    """Get content preview for an item."""
    fp = item.get('filepath', '')
    has_t = item.get('has_transcript', False)
    
    if has_t and item.get('transcript_preview'):
        return item['transcript_preview'][:800]
    
    if 'content' in item and item['content']:
        return item['content'][:800]
    
    if fp and os.path.exists(fp):
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                text = f.read()
            if text.startswith('---'):
                end = text.find('---', 3)
                if end != -1:
                    text = text[end+3:].strip()
            return text[:800]
        except:
            pass
    return ""

def call_claude(title, content, folder, url, author, lang):
    prompt = f"""You are a curator. Generate a structured JSON summary.

Title: {title[:120]}
Author: {author}
Type: {folder}
URL: {url}

Content:
{content[:500].strip()}

Return ONLY valid JSON:
- "summary": 1-2 sentence summary in {lang}
- "detailed_summary": 3-5 sentence detailed summary in {lang}
- "key_points": array of 3-5 key points in {lang}
- "topics": array of 2-4 topic tags in {lang}
- "language": "{lang}"

Return ONLY the JSON."""
    
    try:
        result = subprocess.run(
            ['claude', '-p', prompt, '--allowedTools', 'Read', '--max-turns', '2', '--effort', 'low'],
            capture_output=True, text=True, timeout=45
        )
        return (result.stdout or result.stderr or '').strip()
    except subprocess.TimeoutExpired:
        return ''
    except Exception as e:
        return str(e)

def main():
    state = load_state()
    
    # Find items needing summaries
    todo = []
    for i, item in enumerate(state['items']):
        has_s = ('summary' in item and item['summary'] and 
                 item['summary'].get('summary') and 
                 item['summary']['summary'] != '[待处理]')
        if not has_s:
            todo.append((i, item))
    
    total = len(todo)
    print(f"Need summaries for {total} items", flush=True)
    if total == 0:
        print("Nothing to do!")
        return
    
    done = 0
    for idx, (item_idx, item) in enumerate(todo):
        title = item.get('title', 'Untitled')[:120]
        content = read_content(item)
        url = item.get('url', '')
        author = item.get('author', 'Unknown')
        folder = item.get('folder', 'Other')
        
        cn = len(re.findall(r'[\u4e00-\u9fff]', content))
        lang = 'zh' if cn > 10 else 'en'
        
        print(f"[{idx+1}/{total}] {title[:40]}...", end=' ', flush=True)
        
        output = call_claude(title, content, folder, url, author, lang)
        
        # Extract JSON from output
        # Try common formats
        jm = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', output)
        if not jm:
            jm = re.search(r'\{[^{}]*"summary"[^{}]*"key_points"[^{}]*\}', output)
        if not jm:
            jm = re.search(r'\{[\s\S]*?\}', output)
        
        if jm:
            try:
                # Use capture group if available (regex 1 has group 1), else full match
                matched = jm.group(1) if jm.lastindex and jm.group(1) else jm.group(0)
                summary_data = json.loads(matched)
                state['items'][item_idx]['summary'] = summary_data
                save_state(state)
                print(f"✅ ({len(summary_data.get('summary',''))}c)", flush=True)
                done += 1
            except json.JSONDecodeError:
                print(f"❌ JSON parse error", flush=True)
                if len(output) < 200:
                    print(f"   Raw: {output}", flush=True)
        else:
            print(f"❌ No JSON", flush=True)
        
        time.sleep(0.3)
    
    with_s = sum(1 for i in state['items'] if 'summary' in i and i['summary'] and i['summary'].get('summary') and i['summary']['summary'] != '[待处理]')
    print(f"\nDone! {with_s}/{len(state['items'])} items have summaries (generated {done})")

if __name__ == '__main__':
    main()
