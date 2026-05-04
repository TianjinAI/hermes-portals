#!/usr/bin/env python3
"""Cache tokscale data every 2 hours (7am-11pm server time)."""
import json
import subprocess
from pathlib import Path
from datetime import datetime

TOKSCALE_BIN = Path.home() / ".npm-global" / "bin" / "tokscale"
CACHE_FILE = Path(__file__).parent / "tokscale_cache.json"

def run_tokscale():
    """Query tokscale for clients + monthly only (skip hourly)."""
    result = {
        "clients": [],
        "monthly": [],
        "total_cost": 0,
        "last_update": datetime.utcnow().isoformat(),
    }
    if not TOKSCALE_BIN.exists():
        result["error"] = "tokscale not installed"
        return result
    
    try:
        # Clients scan
        r = subprocess.run(
            [str(TOKSCALE_BIN), "clients", "--json"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, timeout=60,
        )
        if r.returncode == 0:
            data = json.loads(r.stdout)
            result["clients"] = data.get("clients", [])
        
        # Monthly usage (all-time summary)
        r = subprocess.run(
            [str(TOKSCALE_BIN), "monthly", "--json"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, timeout=60,
        )
        if r.returncode == 0:
            data = json.loads(r.stdout)
            result["monthly"] = data.get("entries", [])
            result["total_cost"] = data.get("totalCost", 0)
    except Exception as e:
        result["error"] = str(e)
    
    return result

if __name__ == "__main__":
    data = run_tokscale()
    CACHE_FILE.write_text(json.dumps(data, indent=2))
    print(f"✓ Cached tokscale data: {len(data['clients'])} clients, $({data['total_cost']:.2f} total cost)")
