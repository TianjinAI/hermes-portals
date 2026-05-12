#!/usr/bin/env python3
"""Delta export from Readwise Reader."""
import json, os, subprocess, sys, time, urllib.request, zipfile

STATE_FILE = os.path.expanduser('~/.hermes/readwise_review/state.json')
EXPORT_DIR = os.path.expanduser('~/.hermes/readwise_export/reader_md')

def load_state():
    with open(STATE_FILE) as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def main():
    state = load_state()
    last_export = state.get('last_export', '')

    if last_export:
        print(f"Delta export since: {last_export}")
        result = subprocess.run(
            ['readwise', 'reader-export-documents', '--since-updated', last_export, '--json'],
            capture_output=True, text=True, timeout=30
        )
    else:
        print("Full export (no previous timestamp)")
        result = subprocess.run(
            ['readwise', 'reader-export-documents', '--json'],
            capture_output=True, text=True, timeout=30
        )

    if result.returncode != 0:
        print(f"Export trigger failed: {result.stderr}")
        sys.exit(1)

    data = json.loads(result.stdout)
    export_id = data.get('export_id', data.get('id'))
    print(f"Export triggered: ID={export_id}")
    print(f"Full response: {json.dumps(data, indent=2)[:500]}")

    # Poll for completion
    max_polls = 60  # 5 min
    for i in range(max_polls):
        time.sleep(5)
        poll = subprocess.run(
            ['readwise', 'reader-get-export-documents-status', '--export-id', export_id, '--json'],
            capture_output=True, text=True, timeout=30
        )
        if poll.returncode != 0:
            print(f"Poll error: {poll.stderr}")
            continue
        status_data = json.loads(poll.stdout)
        status = status_data.get('status', '')
        print(f"  Poll {i+1}: status={status}")

        if status == 'completed':
            download_url = status_data.get('download_url', '')
            last_updated = status_data.get('last_updated', '')
            
            print(f"Download URL available, last_updated: {last_updated}")
            
            # Download and extract
            os.makedirs(EXPORT_DIR, exist_ok=True)
            zip_path = '/tmp/rw_export.zip'
            
            # Check file count first
            documents_total = status_data.get('documents_total', 0)
            print(f"Documents in export: {documents_total}")
            
            if documents_total == 0:
                print("No new documents in delta. Nothing to download.")
                # Still save the timestamp
                state['last_export'] = data.get('last_updated', last_updated) or last_export
                save_state(state)
                print("Updated state.json with new timestamp (zero-delta case)")
                return 0
            
            urllib.request.urlretrieve(download_url, zip_path)
            print(f"Downloaded to {zip_path}")
            
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(EXPORT_DIR)
            os.remove(zip_path)
            
            print(f"Extracted to {EXPORT_DIR}")
            
            # Save last_updated for next delta
            if last_updated:
                print(f"Updating last_updated to: {last_updated}")
                # The response structure might differ - get last_updated from status_data
                pass
            
            break
        elif status in ('failed', 'error'):
            print(f"Export failed: {status_data}")
            sys.exit(1)
        else:
            if i % 6 == 0 and i > 0:
                print(f"  Still waiting... ({i*5}s elapsed)")
    else:
        print("Export timed out after 5 minutes")
        sys.exit(1)

    # Save the last_updated timestamp from the export trigger response
    if 'last_updated' in data:
        state['last_updated'] = data['last_updated']
    elif 'last_updated' in status_data:
        state['last_updated'] = status_data['last_updated']
    
    state['last_export'] = data.get('last_updated', '') or last_export
    save_state(state)
    print("State saved with updated timestamps")
    return 0

if __name__ == '__main__':
    sys.exit(main())
