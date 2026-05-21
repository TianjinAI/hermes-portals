#!/usr/bin/env python3
"""
Generate llm-wiki format summaries for portal items using claude -p.
Target format: In_Process style with YAML frontmatter + numbered sections.
"""

import json
import os
import requests
import subprocess
import sys
import re
import time
from datetime import datetime
from pathlib import Path

# Load MINIMAX_API_KEY from ~/.hermes/.env
_env_file = Path.home() / '.hermes' / '.env'
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            if k not in os.environ:
                os.environ[k] = v

MINIMAX_API_KEY = os.environ.get('OPENCODE_API_KEY', '')
if not MINIMAX_API_KEY:
    env_file = os.path.expanduser('~/.hermes/.env')
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                if line.startswith('OPENCODE_API_KEY='):
                    MINIMAX_API_KEY = line.strip().split('=', 1)[1]
                    break
if not MINIMAX_API_KEY:
    env_file = os.path.expanduser('~/.env')
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                if line.startswith('OPENCODE_API_KEY='):
                    MINIMAX_API_KEY = line.strip().split('=', 1)[1]
                    break

# ⚠️ Absolute path required — systemd sets HOME=/home/admin/.hermes/profiles/tg-bot-c/home
REVIEW_DIR = "/home/admin/.hermes/readwise_review"
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
    from datetime import datetime as _dt, timedelta as _td

    state = load_state()
    
    # Only process items from TODAY — never process historical backlog
    cutoff = _dt.now().strftime('%Y-%m-%d')
    
    # Check ALL items — including ones with placeholder summaries
    todo = []
    for i, item in enumerate(state['items']):
        has_valid = ('summary' in item and item['summary'] and 
                     item['summary'].get('detailed_summary') and
                     '## 一、' in item['summary']['detailed_summary'])
        pub = (item.get('published_date') or '')[:10]
        # Only process if published within last 7 days
        if not has_valid and pub >= cutoff:
            todo.append((i, item))
    
    total = len(todo)
    print(f"Need llm-wiki format summaries for {total} items", flush=True)
    if total == 0:
        print("All items already in llm-wiki format!")
        return
    
    done = 0
    for idx, (item_idx, item) in enumerate(todo):
        title = item.get('title', 'Untitled')[:200]
        content = read_content(item)
        if len(content.strip()) < 20:
            print(f'[{idx+1}/{total}] {title[:60]} — skipping, no content', flush=True)
            continue
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
            response = requests.post(
                'http://localhost:20128/v1/chat/completions',
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {MINIMAX_API_KEY}'
                },
                json={
                    'model': 'Best_China',
                    'messages': [{'role': 'user', 'content': prompt}],
                    'temperature': 0.7,
                    'max_tokens': 2048
                },
                timeout=60
            )
            if response.status_code == 401:
                print(f'   ⚠️  401 AUTH FAILED — key: {MINIMAX_API_KEY[:15]}... len={len(MINIMAX_API_KEY)}')
            # Handle all possible response formats from 9router/Various providers
            raw = response.text.strip()
            
            # Remove trailing SSE termination markers
            json_text = raw
            for marker in ['\ndata: [DONE]', '\ndata:[DONE]', 'data: [DONE]', 'data:[DONE]']:
                if json_text.endswith(marker):
                    json_text = json_text[:-len(marker)].rstrip()
            
            # Check if this is pure SSE (starts with data:) — extract content from last delta
            if json_text.startswith('data:'):
                # Pure SSE stream — each line is data: <JSON>
                # Collect all delta content, ignoring control lines
                content_chunks = []
                for line in json_text.split('\n'):
                    stripped = line.strip()
                    if stripped.startswith('data: ') and not stripped.startswith('data: [DONE]'):
                        try:
                            chunk_data = json.loads(stripped[6:])
                            delta = chunk_data.get('choices', [{}])[0].get('delta', {})
                            if delta.get('content'):
                                content_chunks.append(delta['content'])
                        except (json.JSONDecodeError, IndexError, KeyError):
                            pass  # skip malformed chunk lines
                output = ''.join(content_chunks)
                data = {'choices': [{'message': {'content': output}}]}
            elif '\ndata:' in json_text:
                # Hybrid: JSON body then SSE stream — take JSON part only
                json_text = json_text.split('\ndata:')[0].rstrip()
                try:
                    data = json.loads(json_text)
                except json.JSONDecodeError:
                    pos = json_text.rfind('}')
                    data = json.loads(json_text[:pos+1]) if pos >= 0 else {}
                output = (data.get('choices', [{}])[0].get('message', {}).get('content') or '').strip()
                data = {'choices': [{'message': {'content': output}}]}
            else:
                # Plain JSON response
                try:
                    data = json.loads(json_text)
                except json.JSONDecodeError:
                    pos = json_text.rfind('}')
                    data = json.loads(json_text[:pos+1]) if pos >= 0 else {}
                output = (data.get('choices', [{}])[0].get('message', {}).get('content') or '').strip()
                data = {'choices': [{'message': {'content': output}}]}
            
            output = output.strip()
        except requests.exceptions.Timeout:
            print(f"⏰ timeout", flush=True)
            continue
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
