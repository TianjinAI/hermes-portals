#!/usr/bin/env python3
"""
Generate llm-wiki format summaries for portal items using Deepseek API.
Target format: In_Process style with YAML frontmatter + numbered sections.
"""

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

REVIEW_DIR = os.path.expanduser('~/.hermes/readwise_review')
STATE_FILE = os.path.join(REVIEW_DIR, 'state.json')
API_URL = "https://api.deepseek.com/v1/chat/completions"


def get_api_key():
    env_path = Path("/home/admin/.hermes/.env")
    if env_path.exists():
        for line in env_path.read_text().split("\n"):
            if line.startswith("DEEPSEEK_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key and key != "***":
                    return key
    return os.environ.get("DEEPSEEK_API_KEY", "")


def call_llm(prompt: str, max_tokens: int = 4000) -> str:
    """Call Deepseek API directly (non-streaming JSON)."""
    import json, subprocess

    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not found")

    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "stream": False
    }

    result = subprocess.run(
        ["curl", "-s", "--max-time", "120", "-X", "POST", API_URL,
         "-H", f"Authorization: Bearer {api_key}",
         "-H", "Content-Type: application/json; charset=utf-8",
         "-d", json.dumps(payload, ensure_ascii=False)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=125
    )
    data = json.loads(result.stdout.strip())
    msg = data["choices"][0]["message"]
    content = msg.get("content") or ""
    if not content:
        raise RuntimeError(f"No content in response: {json.dumps(msg)[:200]}")
    return content

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
        return item['transcript_preview'][:2000]
    if 'content' in item and item['content']:
        return item['content'][:2000]
    if fp and os.path.exists(fp):
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                text = f.read()
            if text.startswith('---'):
                end = text.find('---', 3)
                if end != -1:
                    text = text[end+3:].strip()
            return text[:2000]
        except:
            pass
    return ""

def generate_summaries():
    state = load_state()
    
    # DELTA-ONLY by default. Backfill mode via BACKFILL_ALL=1.
    fix_date = os.environ.get('FIX_DATE', '')
    backfill_all = os.environ.get('BACKFILL_ALL', '0') == '1'
    if backfill_all:
        cutoff = None
        print("BACKFILL mode: processing all items with invalid/missing llm-wiki summaries")
    elif fix_date:
        cutoff = datetime.strptime(fix_date, '%Y-%m-%d')
        print(f"FIX mode: processing items from {fix_date}")
    else:
        cutoff = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    todo = []
    for i, item in enumerate(state['items']):
        # Check if already has valid summary
        has_valid = ('summary' in item and item['summary'] and 
                     item['summary'].get('detailed_summary') and
                     '## 一、' in item['summary']['detailed_summary'])
        if has_valid:
            continue
        
        # Check if item was processed today (or on FIX_DATE)
        proc_at = item.get('processed_at', '')
        if proc_at:
            try:
                dt = datetime.fromisoformat(proc_at.replace('Z', '+00:00'))
                item_date = dt.strftime('%Y-%m-%d')
                if fix_date:
                    if item_date != fix_date:
                        continue
                else:
                    if cutoff is not None and dt.replace(tzinfo=None) < cutoff:
                        # Skip items from before today
                        continue
            except:
                pass
        
        todo.append((i, item))
    
    total = len(todo)
    print(f"Need llm-wiki format summaries for {total} items", flush=True)
    
    # Batch limit support for incremental cron runs
    batch_limit = int(os.environ.get('BATCH_LIMIT', '0'))
    if batch_limit > 0 and total > batch_limit:
        todo = todo[:batch_limit]
        total = batch_limit
        print(f"Batch mode: processing {total} items (BATCH_LIMIT={batch_limit})", flush=True)
    
    if total == 0:
        print("All items already in llm-wiki format!")
        return
    
    done = 0
    for idx, (item_idx, item) in enumerate(todo):
        title = item.get('title', 'Untitled')[:200]
        content = read_content(item)
        url = item.get('url', '')
        author = item.get('author', 'Unknown')
        folder = item.get('folder', 'Other')
        pub_date = item.get('published_date', '')[:10] or datetime.now().strftime('%Y-%m-%d')
        
        # Determine type and language
        cn = len(re.findall(r'[\u4e00-\u9fff]', content + title))
        is_zh = cn > 10
        lang = 'Chinese' if is_zh else 'English'
        
        # Determine content type
        content_type = '编译笔记'
        if folder == 'Podcasts':
            content_type = '播客笔记'
        elif folder == 'YouTube':
            content_type = '视频笔记'
        elif folder == 'Email':
            content_type = '邮件编译'
        elif folder == 'RSS':
            content_type = '编译笔记'
        
        # Generate topic tags from content
        tags_hint = 'AI, Agent, Technology' if 'AI' in title or 'Claude' in title or 'Codex' in title else 'Technology'
        if is_zh and '大模型' in content:
            tags_hint = 'AI, 大模型, Agent'
        elif is_zh and '科学上网' in title:
            tags_hint = 'VPS, 网络, 科学上网'
        elif 'Yardeni' in author or 'Economic' in title:
            tags_hint = '经济, 市场, 宏观'
        elif 'MacroMicro' in author:
            tags_hint = 'Economy'
        
        print(f"[{idx+1}/{total}] {title[:50]}...", end=' ', flush=True)
        
        # Build prompt for llm-wiki format
        lang_instruction = 'Use ' + lang + ' throughout the note.'
        
        prompt = 'You are a curator. Generate a structured llm-wiki note. ' + lang_instruction + '\n\n'
        prompt += 'Start with EXACTLY:\n'
        prompt += '---\nsource: ' + url + '\nauthor: ' + author + '\ncreated: ' + pub_date + '\ntype: ' + content_type + '\ntags: [' + tags_hint + ']\nstatus: pending\n---\n\n'
        prompt += 'Then H1 title, then > 摘要：summary in ' + lang + ', then ---, then ## 一、 (Chinese-numbered, 3 sections minimum, 3-5 paragraphs each), then > [!info] 来源 with 原始链接.\n\n'
        prompt += 'Content to analyze: ' + title + '\n\n' + content[:1200].strip()

        try:
            output = call_llm(prompt).strip()
        except Exception as e:
            print(f"❌ {e}", flush=True)
            continue
        
        # Extract the llm-wiki note
        # First try to find content between ``` markers (if claude wraps it)
        jm = re.search(r'```(?:markdown|md)?\s*([\s\S]*?)\s*```', output)
        if jm:
            note = jm.group(1).strip()
        else:
            # Try to find YAML frontmatter directly
            jm2 = re.search(r'^---\s*\n[\s\S]*?\n---\s*\n[\s\S]*', output)
            if jm2:
                note = jm2.group(0).strip()
            else:
                note = output
        
        # Verify it has the required structure
        has_yaml = note.startswith('---')
        has_sections = bool(re.search(r'## [一二三四五六七八九十\d]+[、.]', note))
        has_source = '[!info]' in note or '来源' in note
        
        if not has_yaml or not has_sections:
            print(f"⚠️  missing format elements (yaml={'✅' if has_yaml else '❌'} sections={'✅' if has_sections else '❌'} source={'✅' if has_source else '❌'})", flush=True)
            print(f"   Output preview: {note[:200]}", flush=True)
            continue
        
        # Save
        summary = {
            'summary': re.search(r'> 摘要[：:]\s*(.+?)(?:\n|$)', note),
            'detailed_summary': note,
            'key_points': [],  # Will be extracted from section headers
            'topics': [],
            'language': 'zh' if is_zh else 'en',
            'format': 'llm-wiki'
        }
        
        # Extract summary from blockquote
        sm = re.search(r'> 摘要[：:]\s*(.+?)(?:\n|$)', note)
        if sm:
            summary['summary'] = sm.group(1).strip()
        else:
            # Fallback: extract first line
            first_line = note.split('\n')[0] if note else title
            summary['summary'] = title[:200]
        
        # Extract section headers as key points
        sections = re.findall(r'## ([一二三四五六七八九十\d]+[、.].+)', note)
        summary['key_points'] = sections[:10] if sections else ['Key insights']
        
        # Extract tags from YAML
        tg = re.search(r'tags:\s*\[([^\]]+)\]', note)
        if tg:
            summary['topics'] = [t.strip() for t in tg.group(1).split(',')]
        else:
            summary['topics'] = [folder.lower()]
        
        state['items'][item_idx]['summary'] = summary
        save_state(state)
        
        # Count sections
        n_sections = len(sections)
        print(f"✅ ({n_sections} sections, {len(note)} chars)", flush=True)
        done += 1
        time.sleep(0.3)
    
    # Final count
    state = load_state()
    valid = sum(1 for i in state['items'] if 'summary' in i and i['summary'] and 
                i['summary'].get('detailed_summary') and 
                '## 一、' in i['summary']['detailed_summary'])
    print(f"\nDone! {valid}/{len(state['items'])} items in llm-wiki format (generated {done})")

if __name__ == '__main__':
    generate_summaries()
