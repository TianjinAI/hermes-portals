#!/usr/bin/env python3
"""Batch-generate summaries using claude -p in parallel processes."""

import json
import os
import subprocess
import sys
import re
import time
from pathlib import Path

REVIEW_DIR = os.path.expanduser('~/.hermes/readwise_review')
STATE_FILE = os.path.join(REVIEW_DIR, 'state.json')
EXPORT_DIR = os.path.expanduser('~/.hermes/readwise_export/reader_md')

def load_state():
    with open(STATE_FILE) as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def read_content(item):
    """Read content for an item."""
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

def detect_lang(text):
    if not text:
        return "en"
    cn = len(re.findall(r'[\u4e00-\u9fff]', text))
    return "zh" if cn > 10 else "en"

def process_batch(batch, batch_name):
    """Process a batch of items using claude -p."""
    state = load_state()
    results = []
    
    for idx, (item_idx, item) in enumerate(batch):
        title = item.get('title', 'Untitled')[:120]
        content = read_content(item)
        url = item.get('url', '')
        author = item.get('author', 'Unknown')
        folder = item.get('folder', 'Other')
        lang = detect_lang(content)
        
        # Truncate content for prompt
        content_short = content[:600].strip()
        
        prompt = f"""You are a curator. Generate a structured JSON summary for this item.

Title: {title}
Author: {author}
Type: {folder}
URL: {url}

Content:
{content_short}

Return ONLY valid JSON with these fields:
- "summary": 1-2 sentence summary in {lang}
- "detailed_summary": 3-5 sentence detailed summary in {lang}
- "key_points": array of 3-5 key points in {lang}
- "topics": array of 2-4 topic tags in {lang}
- "language": "{lang}"

Return ONLY the JSON object wrapped in ```json...``` or plain."""
        
        print(f"  [{batch_name}] Item {idx+1}/{len(batch)}: {title[:40]}...", flush=True)
        
        try:
            result = subprocess.run(
                ['claude', '-p', prompt, '--allowedTools', 'Read', '--max-turns', '2', '--effort', 'low'],
                capture_output=True, text=True, timeout=45
            )
            output = result.stdout or result.stderr
            
            # Try to extract JSON
            json_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', output)
            if not json_match:
                json_match = re.search(r'\{[^{}]*"summary"[^{}]*"key_points"[^{}]*\}', output)
            if not json_match:
                json_match = re.search(r'\{[\s\S]*?\}', output)
            
            if json_match:
                summary_data = json.loads(json_match.group(1) if '```' in str(type(json_match)) else json_match.group(0))
                results.append((item_idx, summary_data))
                print(f"    ✅ Got summary ({len(summary_data.get('summary',''))} chars)", flush=True)
            else:
                print(f"    ❌ No JSON in output", flush=True)
                print(f"    Output: {output[:200]}", flush=True)
        except subprocess.TimeoutExpired:
            print(f"    ❌ Timeout", flush=True)
        except Exception as e:
            print(f"    ❌ {e}", flush=True)
        
        time.sleep(0.5)  # Small delay between items
    
    # Save all results for this batch
    state = load_state()
    for item_idx, summary_data in results:
        state['items'][item_idx]['summary'] = summary_data
    save_state(state)
    print(f"  [{batch_name}] Saved {len(results)} summaries", flush=True)
    return len(results)

def main():
    state = load_state()
    
    # Collect items needing summaries
    todo = []
    for i, item in enumerate(state['items']):
        has_s = ('summary' in item and item['summary'] and 
                 item['summary'].get('summary') and 
                 item['summary']['summary'] != '[待处理]')
        if not has_s:
            todo.append((i, item))
    
    total = len(todo)
    print(f"Need {total} summaries")
    
    if total == 0:
        print("Nothing to do!")
        return
    
    # Split into batches for parallel processing
    # Each subprocess handles its own batch sequentially
    n_parallel = 3  # Number of parallel processes
    batch_size = (total + n_parallel - 1) // n_parallel
    batches = [todo[j:j+batch_size] for j in range(0, total, batch_size)]
    
    print(f"Split into {len(batches)} batches (parallel)")
    
    # Write batch data to temp files so subprocesses can read independently
    batch_data = []
    for b_idx, batch in enumerate(batches):
        batch_info = [(idx, item.get('title',''), item) for idx, item in batch]
        batch_file = os.path.join(REVIEW_DIR, f'_batch_{b_idx}.json')
        with open(batch_file, 'w') as f:
            json.dump([(idx, item) for idx, item in batch], f, indent=2, ensure_ascii=False)
        batch_data.append((b_idx, batch_file))
    
    # Start parallel processes
    processes = []
    for b_idx, batch_file in batch_data:
        cmd = f'cd {REVIEW_DIR} && python3.11 -c "
import json, subprocess, sys, re, os, time

REVIEW_DIR = {repr(REVIEW_DIR)}
STATE_FILE = os.path.join(REVIEW_DIR, {repr(STATE_FILE.replace(REVIEW_DIR, \\'.\\'))})
batch_file = {repr(batch_file)}

def load_state():
    with open(STATE_FILE) as f:
        return json.load(f)
def save_state(state):
    with open(STATE_FILE, \\'w\\') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def call_claude(prompt):
    try:
        result = subprocess.run(
            [\\'claude\\', \\'-p\\', prompt, \\'--allowedTools\\', \\'Read\\', \\'--max-turns\\', \\'2\\', \\'--effort\\', \\'low\\'],
            capture_output=True, text=True, timeout=45
        )
        return result.stdout
    except:
        return None

# Load batch
with open(batch_file) as f:
    batch = json.load(f)

results = []
for idx, item in batch:
    title = item.get(\\'title\\', \\'Untitled\\')[:120]
    content = item.get(\\'content\\', \\'\\')[:600] or item.get(\\'transcript_preview\\', \\'\\')[:600]
    fp = item.get(\\'filepath\\', \\'\\')
    if not content and fp and os.path.exists(fp):
        try:
            with open(fp, \\'r\\', encoding=\\'utf-8\\') as f:
                text = f.read()
            if text.startswith(\\'---\\'):
                end = text.find(\\'---\\', 3)
                if end != -1:
                    text = text[end+3:].strip()
            content = text[:600]
        except:
            pass
    
    cn = len(re.findall(r[\\u4e00-\\u9fff], content))
    lang = \\'zh\\' if cn > 10 else \\'en\\'
    folder = item.get(\\'folder\\', \\'Other\\')
    url = item.get(\\'url\\', \\'\\')
    author = item.get(\\'author\\', \\'Unknown\\')
    
    prompt = f\\\"\"You are a curator. Generate a structured JSON summary for this item.
Title: {title}
Author: {author}
Type: {folder}
URL: {url}
Content: {content[:500].strip()}
Return ONLY valid JSON with fields: summary, detailed_summary, key_points (array), topics (array), language (\\\"{lang}\\\"). Return ONLY the JSON.\\\"\"
    
    print(f\\\"  [{b_idx}] {title[:30]}...\\\", flush=True)
    output = call_claude(prompt)
    if output:
        jm = re.search(r\\'bib\\'\\''
        
        # Simplified regex
        jm = re.search(r\{[^{}]*\"summary\"[^{}]*\"key_points\"[^{}]*\}', output) if output else None
        if not jm and output:
            jm = re.search(r'\{[\s\S]*?\}', output)
        if jm:
            try:
                sd = json.loads(jm.group(0))
                results.append((idx, sd))
                print(f\\\"    ✅\\\", flush=True)
            except:
                print(f\\\"    ❌ parse fail\\\", flush=True)
        else:
            print(f\\\"    ❌ no JSON\\\", flush=True)
    else:
        print(f\\\"    ❌ fail\\\", flush=True)
    time.sleep(0.3)

# Save results
state = load_state()
for idx, sd in results:
    state[\\'items\\'][idx][\\'summary\\'] = sd
save_state(state)
print(f\\\"  Done: {len(results)} summaries\\\", flush=True)
" 2>&1'
        
        print(f"Starting batch {b_idx+1} ({len(batch_data[b_idx][1])} items in {batch_data[b_idx][0]})")
        
        p = subprocess.Popen(
            ['bash', '-c', cmd],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True
        )
        processes.append((b_idx, p))
    
    # Wait for all and collect output
    for b_idx, p in processes:
        stdout, _ = p.communicate()
        print(f"\nBatch {b_idx+1} output:")
        for line in stdout.split('\n'):
            if line.strip():
                print(f"  {line}")
    
    # Final count
    state = load_state()
    with_s = sum(1 for i in state['items'] if 'summary' in i and i['summary'] and i['summary'].get('summary') and i['summary']['summary'] != '[待处理]')
    print(f"\n{'='*50}")
    print(f"Done! {with_s}/{len(state['items'])} items have summaries")

if __name__ == '__main__':
    main()
