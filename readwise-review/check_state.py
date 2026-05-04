#!/usr/bin/env python3
"""Check current state counts."""
import json
import os

STATE_FILE = os.path.expanduser('~/.hermes/readwise_review/state.json')

with open(STATE_FILE) as f:
    state = json.load(f)

items = state.get('items', [])
processed_ids = state.get('processed_ids', [])

print(f"Total items in state: {len(items)}")
print(f"Processed IDs count: {len(processed_ids)}")

# Count items with valid summaries
with_valid_summary = 0
without_summary = []
for i, item in enumerate(items):
    summary = item.get('summary', {})
    ds = summary.get('detailed_summary', '') if summary else ''
    has_valid = ds and '## 一、' in ds
    if has_valid:
        with_valid_summary += 1
    else:
        without_summary.append((i, item.get('title', 'Unknown')[:50], item.get('id', 'no-id')[:20]))

print(f"Items with valid llm-wiki summary: {with_valid_summary}")
print(f"Items without valid summary: {len(without_summary)}")
print("\nFirst 5 items without valid summary:")
for i, title, doc_id in without_summary[:5]:
    print(f"  [{i}] {title}... (id: {doc_id})")