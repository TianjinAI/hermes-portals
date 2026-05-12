#!/bin/bash
# Step 1: Delta export from Readwise Reader
set -e

WORK_DIR="/home/admin/.hermes/readwise_review"
STATE_FILE="$WORK_DIR/state.json"
EXPORT_DIR="/home/admin/.hermes/readwise_export/reader_md/"

# Read last_updated from state
LAST_UPDATED=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('last_updated',''))" 2>/dev/null || echo "")
echo "last_updated: $LAST_UPDATED"
ITEMS_COUNT=$(python3 -c "import json; print(len(json.load(open('$STATE_FILE')).get('items',[])))" 2>/dev/null || echo "0")
echo "existing items: $ITEMS_COUNT"

# Trigger export
if [ -n "$LAST_UPDATED" ]; then
    echo "Running delta export (since $LAST_UPDATED)..."
    EXPORT_OUTPUT=$(readwise reader-export-documents --since-updated "$LAST_UPDATED" --json 2>&1)
else
    echo "Running full export..."
    EXPORT_OUTPUT=$(readwise reader-export-documents --json 2>&1)
fi

echo "Export trigger output: $EXPORT_OUTPUT"

DOC_TOTAL=$(echo "$EXPORT_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('documents_total', -1))" 2>/dev/null || echo "-1")
echo "documents_total: $DOC_TOTAL"

if [ "$DOC_TOTAL" = "0" ]; then
    echo "No new documents. Skipping download."
    NEW_UPDATED=$(echo "$EXPORT_OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('last_updated',''))" 2>/dev/null || echo "")
    if [ -n "$NEW_UPDATED" ] && [ "$NEW_UPDATED" != "$LAST_UPDATED" ]; then
        python3 -c "
import json
s=json.load(open('$STATE_FILE'))
s['last_updated']='$NEW_UPDATED'
with open('$STATE_FILE','w') as f: json.dump(s, f, ensure_ascii=False, indent=2)
"
        echo "Saved new last_updated: $NEW_UPDATED"
    fi
    exit 0
fi

EXPORT_ID=$(echo "$EXPORT_OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('export_id',''))" 2>/dev/null || echo "")
echo "export_id: $EXPORT_ID"

if [ -z "$EXPORT_ID" ]; then
    echo "ERROR: No export_id"
    exit 1
fi

# Poll
echo "Polling for export completion..."
for i in $(seq 1 40); do
    sleep 5
    POLL=$(readwise reader-get-export-documents-status --export-id "$EXPORT_ID" --json 2>&1)
    STATUS=$(echo "$POLL" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
    echo "  Poll $i: status=$STATUS"
    if [ "$STATUS" = "completed" ]; then
        break
    fi
done

if [ "$STATUS" != "completed" ]; then
    echo "ERROR: Export did not complete"
    exit 1
fi

# Get download URL
DOWNLOAD_URL=$(echo "$POLL" | python3 -c "import sys,json; print(json.load(sys.stdin).get('download_url',''))" 2>/dev/null || echo "")
NEW_UPDATED=$(echo "$POLL" | python3 -c "import sys,json; print(json.load(sys.stdin).get('last_updated',''))" 2>/dev/null || echo "")

echo "download_url: ${DOWNLOAD_URL:0:50}..."
echo "new last_updated: $NEW_UPDATED"

if [ -z "$DOWNLOAD_URL" ]; then
    echo "ERROR: No download_url"
    exit 1
fi

# Download
echo "Downloading zip..."
curl -sLo /tmp/rw_export.zip "$DOWNLOAD_URL"
ls -la /tmp/rw_export.zip

# Extract
mkdir -p "$EXPORT_DIR"
unzip -o /tmp/rw_export.zip -d "$EXPORT_DIR"
rm -f /tmp/rw_export.zip
echo "Extraction complete"

# Update state
if [ -n "$NEW_UPDATED" ] && [ "$NEW_UPDATED" != "$LAST_UPDATED" ]; then
    python3 -c "
import json
s=json.load(open('$STATE_FILE'))
s['last_updated']='$NEW_UPDATED'
with open('$STATE_FILE','w') as f: json.dump(s, f, ensure_ascii=False, indent=2)
"
    echo "Updated state.json last_updated: $NEW_UPDATED"
fi

echo "Export completed successfully"
