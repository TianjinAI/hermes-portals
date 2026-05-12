#!/bin/bash
set -e

# Step 1: Read state and trigger delta export
STATE_FILE="/home/admin/.hermes/readwise_review/state.json"
LAST_EXPORT=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('last_export',''))")

if [ -n "$LAST_EXPORT" ]; then
    echo "Triggering delta export since: $LAST_EXPORT"
    readwise reader-export-documents --since-updated "$LAST_EXPORT" --json
else
    echo "No previous export found, doing full export"
    readwise reader-export-documents --json
fi
