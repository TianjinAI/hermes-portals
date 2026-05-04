#!/usr/bin/env python3
"""
Import existing Readwise export into the review portal.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

REVIEW_DIR = os.path.expanduser('~/.hermes/readwise_review')
STATE_FILE = os.path.join(REVIEW_DIR, 'state.json')
EXPORT_DIR = os.path.expanduser('~/.hermes/readwise_export/reader_md')

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        'last_export': None,
        'last_updated': None,
        'items': [],
        'decisions': {},
        'processed_ids': []
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

def main():
    print("=" * 60)
    print("Importing Readwise Export")
    print("=" * 60)
    
    state = load_state()
    
    md_files = list(Path(EXPORT_DIR).rglob('*.md'))
    print(f"Found {len(md_files)} markdown files")
    
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
        
        # Create a simple summary placeholder
        summary = {
            'summary': f"[待处理] {title}",
            'key_points': ['等待LLM处理'],
            'topics': [category],
            'language': 'zh'
        }
        
        item = {
            'id': doc_id,
            'title': title,
            'author': author,
            'category': category,
            'folder': folder,
            'url': url,
            'published_date': published_date,
            'has_transcript': False,
            'transcript_preview': None,
            'content_preview': body[:500] if body else '',
            'summary': summary,
            'filepath': str(filepath),
            'processed_at': datetime.now(timezone.utc).isoformat()
        }
        
        new_items.append(item)
        state['processed_ids'].append(doc_id)
    
    state['items'].extend(new_items)
    state['last_export'] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    
    print(f"\nImported {len(new_items)} items")
    print(f"Total items: {len(state['items'])}")
    
    # Show breakdown by category
    from collections import Counter
    cats = Counter(i['category'] for i in state['items'])
    print("\nBy category:")
    for cat, count in cats.most_common():
        print(f"  {cat}: {count}")

if __name__ == '__main__':
    main()
