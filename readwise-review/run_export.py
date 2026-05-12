#!/usr/bin/env python3
"""Step 1: Delta export from Readwise Reader"""
import json, subprocess, sys, os, time, shutil
from pathlib import Path

WORK_DIR = Path("/home/admin/.hermes/readwise_review")
STATE_FILE = WORK_DIR / "state.json"
EXPORT_DIR = Path("/home/admin/.hermes/readwise_export/reader_md/")

def main():
    # Read state
    with open(STATE_FILE) as f:
        state = json.load(f)
    last_updated = state.get("last_updated", "")
    print(f"last_updated: {last_updated}")
    print(f"existing items: {len(state.get('items', []))}")

    # Trigger export
    if last_updated:
        cmd = ["readwise", "reader-export-documents", "--since-updated", last_updated, "--json"]
        print(f"Running delta export (since {last_updated})...")
    else:
        cmd = ["readwise", "reader-export-documents", "--json"]
        print("Running full export (no last_updated)...")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    print(f"Export trigger exit code: {result.returncode}")
    print(f"Export trigger stdout: {result.stdout[:500]}")
    if result.stderr:
        print(f"Export trigger stderr: {result.stderr[:500]}")

    if result.returncode != 0:
        print("ERROR: Export trigger failed")
        sys.exit(1)

    export_data = json.loads(result.stdout)
    export_id = export_data.get("export_id")
    print(f"export_id: {export_id}")
    
    doc_total = export_data.get("documents_total", -1)
    print(f"documents_total: {doc_total}")
    
    if doc_total == 0:
        # Save the last_updated from response for next run
        new_updated = export_data.get("last_updated", last_updated)
        if new_updated and new_updated != last_updated:
            state["last_updated"] = new_updated
            with open(STATE_FILE, "w") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            print(f"Saved new last_updated: {new_updated}")
        print("No new documents in delta export. Skipping download.")
        return True

    if not export_id:
        print("ERROR: No export_id in response")
        sys.exit(1)

    # Poll for completion
    print("Polling for export completion...")
    for i in range(40):
        time.sleep(5)
        poll = subprocess.run(
            ["readwise", "reader-get-export-documents-status", "--export-id", export_id, "--json"],
            capture_output=True, text=True, timeout=30
        )
        if poll.returncode != 0:
            print(f"Poll error: {poll.stderr[:200]}")
            continue
        status_data = json.loads(poll.stdout)
        status = status_data.get("status")
        print(f"  Poll {i+1}: status={status}")
        if status == "completed":
            break
    else:
        print("ERROR: Export did not complete in time")
        sys.exit(1)

    # Get final data
    final = subprocess.run(
        ["readwise", "reader-get-export-documents-status", "--export-id", export_id, "--json"],
        capture_output=True, text=True, timeout=30
    )
    final_data = json.loads(final.stdout)
    download_url = final_data.get("download_url")
    new_last_updated = final_data.get("last_updated", "")
    
    print(f"download_url available: {bool(download_url)}")
    print(f"new last_updated: {new_last_updated}")

    if not download_url:
        print("ERROR: No download_url in completed export")
        sys.exit(1)

    # Download and extract
    zip_path = "/tmp/rw_export.zip"
    dl = subprocess.run(["curl", "-sLo", zip_path, download_url], capture_output=True, text=True, timeout=120)
    if dl.returncode != 0:
        print(f"ERROR: Download failed: {dl.stderr[:200]}")
        sys.exit(1)
    
    print(f"Downloaded zip to {zip_path} ({os.path.getsize(zip_path) if os.path.exists(zip_path) else '?'} bytes)")

    # Extract
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    unzip = subprocess.run(["unzip", "-o", zip_path, "-d", str(EXPORT_DIR)], capture_output=True, text=True, timeout=60)
    print(f"Unzip output: {unzip.stdout[:300]}")
    if unzip.stderr:
        print(f"Unzip stderr: {unzip.stderr[:300]}")

    # Cleanup
    if os.path.exists(zip_path):
        os.remove(zip_path)
        print("Cleaned up zip file")

    # Save new last_updated to state
    if new_last_updated and new_last_updated != last_updated:
        state["last_updated"] = new_last_updated
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        print(f"Updated state.json last_updated: {new_last_updated}")

    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
