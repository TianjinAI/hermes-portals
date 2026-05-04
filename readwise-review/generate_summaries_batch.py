#!/usr/bin/env python3
"""Batch-generate LLM summaries for all items that need them, grouped in chunks of 5."""

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

def call_llm(prompt):
    try:
        result = subprocess.run(
            ['opencode', 'run', prompt, '--model', 'opencode-go/glm-5'],
            capture_output=True, text=True, timeout=180
        )
        return result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return None, "Timeout"
    except Exception as e:
        return None, str(e)

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
    
    print(f"Need summaries for {len(todo)} items")
    if not todo:
        return
    
    # Batch into groups of 5
    batch_size = 5
    batches = [todo[j:j+batch_size] for j in range(0, len(todo), batch_size)]
    print(f"Split into {len(batches)} batches of {batch_size}")
    
    for b_idx, batch in enumerate(batches):
        print(f"\n{'='*50}")
        print(f"Batch {b_idx+1}/{len(batches)} ({len(batch)} items)")
        
        # Build prompt with all items in this batch
        items_text = ""
        for idx, (item_idx, item) in enumerate(batch):
            title = item.get('title', 'Untitled')[:100]
            url = item.get('url', '')
            author = item.get('author', 'Unknown')
            category = item.get('category', 'unknown')
            folder = item.get('folder', 'Other')
            fp = item.get('filepath', '')
            has_t = item.get('has_transcript', False)
            
            # Try to read content preview
            content_snippet = ""
            if 'content' in item and item['content']:
                content_snippet = item['content'][:500]
            elif fp and os.path.exists(fp):
                try:
                    with open(fp, 'r', encoding='utf-8') as f:
                        text = f.read()
                    if text.startswith('---'):
                        end = text.find('---', 3)
                        if end != -1:
                            text = text[end+3:].strip()
                    content_snippet = text[:500]
                except:
                    pass
            
            # For YouTube items, use transcript preview
            if has_t and item.get('transcript_preview'):
                content_snippet = item['transcript_preview'][:500]
            
            items_text += f"""
--- Item {idx+1} ---
ID: {item.get('id', '')[:20]}
Title: {title}
URL: {url}
Author: {author}
Category: {category}
Folder: {folder}
HasTranscript: {has_t}
Content: {content_snippet[:400]}
"""
        
        prompt = f"""You are a professional content curator. Generate structured summaries for {len(batch)} items below.

For EACH item, output a JSON object with these fields:
- "summary": 1-2 sentence summary (match the item's language)
- "detailed_summary": 3-5 sentence detailed summary in llm-wiki format with markdown
- "key_points": array of 3-5 key points
- "topics": array of 2-4 topic tags
- "language": "zh" or "en"

Return a JSON array of objects, one per item in the SAME ORDER as listed below.
Each object in the array corresponds to Item 1, Item 2, etc.

{items_text}

Return ONLY valid JSON array (no markdown, no code fences):
"""
        
        print(f"  Sending prompt ({len(prompt)} chars)...")
        sys.stdout.flush()
        
        stdout, stderr = call_llm(prompt)
        
        if not stdout:
            print(f"  ❌ LLM call failed: {stderr[:200]}")
            continue
        
        # Extract JSON array
        json_match = re.search(r'\[[\s\S]*\]', stdout)
        if not json_match:
            print(f"  ❌ No JSON array in output")
            print(f"     Output preview: {stdout[:300]}")
            continue
        
        try:
            summaries = json.loads(json_match.group(0))
            print(f"  Got {len(summaries)} summaries from response")
            
            if len(summaries) != len(batch):
                print(f"  ⚠️ Mismatch: got {len(summaries)} summaries for {len(batch)} items")
                # Use what we got
                for idx in range(min(len(summaries), len(batch))):
                    state['items'][batch[idx][0]]['summary'] = summaries[idx]
            else:
                for idx, (item_idx, item) in enumerate(batch):
                    state['items'][item_idx]['summary'] = summaries[idx]
            
            save_state(state)
            print(f"  ✅ Batch saved!")
            
        except json.JSONDecodeError as e:
            print(f"  ❌ JSON parse error: {e}")
            # Try individual items from the output
            obj_matches = re.findall(r'\{[^{}]*"summary"[^{}]*\}', stdout)
            print(f"  Found {len(obj_matches)} individual JSON objects as fallback")
            for idx, obj_str in enumerate(obj_matches[:len(batch)]):
                try:
                    state['items'][batch[idx][0]]['summary'] = json.loads(obj_str)
                except:
                    pass
            save_state(state)
        
        time.sleep(1)
    
    with_s = sum(1 for i in state['items'] if 'summary' in i and i['summary'] and i['summary'].get('summary') and i['summary']['summary'] != '[待处理]')
    print(f"\n{'='*50}")
    print(f"Done! {with_s}/{len(state['items'])} items now have summaries")

if __name__ == '__main__':
    main()
