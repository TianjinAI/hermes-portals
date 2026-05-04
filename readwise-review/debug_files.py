#!/usr/bin/env python3
"""Debug: Check which files are not in processed_ids."""
import json
import os
from pathlib import Path

STATE_FILE = os.path.expanduser('~/.hermes/readwise_review/state.json')
EXPORT_DIR = os.path.expanduser('~/.hermes/readwise_export/reader_md')

with open(STATE_FILE) as f:
    state = json.load(f)

processed_ids = set(state.get('processed_ids', []))
print(f"Processed IDs count: {len(processed_ids)}")

# Get all file IDs
md_files = list(Path(EXPORT_DIR).rglob('*.md'))
print(f"Total MD files: {len(md_files)}")

not_processed = []
for filepath in md_files:
    filename = filepath.stem
    doc_id = filename.split('(')[-1].rstrip(')') if '(' in filename else filename
    if doc_id not in processed_ids:
        not_processed.append((filepath, doc_id))

print(f"\nFiles not in processed_ids: {len(not_processed)}")
for fp, doc_id in not_processed[:10]:
    print(f"  {doc_id}: {fp}")