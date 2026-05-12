#!/usr/bin/env python3
"""Update state.json timestamps after successful delta export."""
import json, os
from datetime import datetime, timezone

STATE_FILE = os.path.expanduser('~/.hermes/readwise_review/state.json')
with open(STATE_FILE) as f:
    state = json.load(f)

# Update last_export to now
now = datetime.now(timezone.utc).isoformat()
state['last_export'] = now
print(f"Updated last_export: {now}")
print(f"last_updated remains: {state.get('last_updated')}")

with open(STATE_FILE, 'w') as f:
    json.dump(state, f, indent=2, ensure_ascii=False)

print(f"Total items: {len(state.get('items', []))}")
print(f"Processed IDs: {len(state.get('processed_ids', []))}")
