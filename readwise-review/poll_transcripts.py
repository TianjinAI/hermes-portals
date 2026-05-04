#!/usr/bin/env python3
"""Poll YouMind for pending YouTube transcripts."""
import json, os, subprocess, time

with open(os.path.expanduser("~/.hermes/.env")) as f:
    for line in f:
        if line.startswith("YOUMIND_API_KEY="):
            os.environ["YOUMIND_API_KEY"] = line.strip().split("=", 1)[1]
            break

PENDING = {
    "019dc5be-b0cf-784b-b2a7-b432f7eeddaa": "piJz8qlLCF4",
    "019dc5be-b8d1-7e33-92c6-3b7fc5242677": "vG1RBqn1sG4",
}

OUTDIR = os.path.expanduser("~/.hermes/readwise_review/transcripts")
os.makedirs(OUTDIR, exist_ok=True)

for attempt in range(120):  # Up to 60 min
    still_pending = {}
    for mid, vid in PENDING.items():
        outfile = os.path.join(OUTDIR, f"{vid}.txt")
        if os.path.exists(outfile):
            continue
        try:
            r = subprocess.run(
                ["youmind", "call", "getMaterial", "--id", mid, "--includeBlocks", "true"],
                capture_output=True, text=True, timeout=30, env=os.environ
            )
            if r.returncode != 0 or not r.stdout:
                still_pending[mid] = vid
                continue
            data = json.loads(r.stdout)
            t = data.get("transcript") or {}
            contents = t.get("contents") or []
            if contents and contents[0].get("status") == "completed":
                plain = contents[0].get("plain", "")
                with open(outfile, "w") as f:
                    f.write(plain)
                print(f"DONE: {vid} ({len(plain)} chars)")
            else:
                still_pending[mid] = vid
        except Exception as e:
            still_pending[mid] = vid

    if not still_pending:
        print("All done!")
        break
    PENDING = still_pending
    print(f"[{time.strftime('%H:%M:%S')}] Attempt {attempt+1}: {len(still_pending)} pending...")
    time.sleep(30)
else:
    print(f"Pending: {list(PENDING.values())}")
