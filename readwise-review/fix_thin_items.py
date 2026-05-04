#!/usr/bin/env python3
"""Regenerate 3 thin items via opencode run (Claude rate-limited)."""
import json, subprocess, re, os

REVIEW = os.path.expanduser('~/.hermes/readwise_review')
STATE = os.path.join(REVIEW, 'state.json')

with open(STATE) as f:
    state = json.load(f)

for idx in [5, 6, 21]:
    item = state['items'][idx]
    print(f'\n=== #{idx}: {item["title"][:40]} ===')
    
    fp = item.get('filepath','')
    content = item.get('transcript_preview','') or item.get('content','') or ''
    if not content and fp and os.path.exists(fp):
        with open(fp) as f:
            text = f.read()
        if text.startswith('---'):
            end = text.find('---',3)
            text = text[end+3:].strip() if end != -1 else text
        content = text
    content = content[:2000]
    
    url = item['url']
    author = item['author']
    pub = item.get('published_date','')[:10]
    lang = 'Chinese' if any(ord(c) > 127 for c in item['title'][:20]) else 'English'
    
    prompt = f'You are a curator. Generate a structured llm-wiki note in {lang}.\n\n'
    prompt += 'OUTPUT MUST START EXACTLY:\n---\nsource: ' + url + '\nauthor: ' + author + '\ncreated: ' + pub + '\ntype: 编译笔记\ntags: [AI, Technology]\nstatus: pending\n---\n\n'
    prompt += 'Title: ' + item['title'] + '\n\nContent:\n' + content + '\n\n'
    prompt += 'Then continue with:\n# Title\n> summary\n---\n## 一、theme (3-5 paragraphs, NO bullet points)\n## 二、theme (3-5 paragraphs)\n## 三、theme (3-5 paragraphs)\n> source attribution\n\nIMPORTANT: Use ## CHINESE NUMBERING format. Write real paragraphs not bullet lists.'
    
    r = subprocess.run(
        ['opencode', 'run', prompt, '--model', 'opencode-go/glm-5'],
        capture_output=True, text=True, timeout=120
    )
    output = (r.stdout or '').strip()
    
    # Try different extraction strategies
    fences = re.search(r'```(?:markdown|md)?\s*([\s\S]*?)```', output)
    note = fences.group(1).strip() if fences else output
    
    if note.count('---') >= 2 and '## 一' in note:
        sections = re.findall(r'## ([一二三四五六七八九十]+[、.][^\n]+)', note)
        sm = re.search(r'> 摘要[：:]\s*(.+?)(?:\n|$)', note)
        tg = re.search(r'tags:\s*\[([^\]]+)\]', note)
        
        state['items'][idx]['summary'] = {
            'summary': sm.group(1).strip() if sm else item['title'],
            'detailed_summary': note,
            'key_points': sections[:10],
            'topics': [t.strip() for t in tg.group(1).split(',')] if tg else ['AI'],
            'language': 'zh' if 'Chinese' in lang else 'en',
            'format': 'llm-wiki'
        }
        with open(STATE, 'w') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        print(f'  ✅ {len(note)} chars, {len(sections)} sections')
    else:
        print(f'  ❌ Missing format. Length={len(note)}')
        print(f'  Has ---: {note.count("---") >= 2}, Has ## 一: {"## 一" in note}')
        print(f'  Preview: {note[:200]}')

print('\nDone!')
