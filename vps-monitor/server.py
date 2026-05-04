#!/usr/bin/env python3
"""VPS Monitor — port 5057. System stats + LLM token usage tracker."""
import json, os, time, subprocess, sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timedelta

PORT = 5057
DIR = Path(__file__).parent
USAGE_DB = DIR / "usage.db"


def sh(cmd):
    return subprocess.check_output(cmd, universal_newlines=True, timeout=5)


# ── System Stats ──────────────────────────────────────────────────────

def get_stats():
    s = {"time": time.strftime("%Y-%m-%d %H:%M:%S %Z"), "unix": time.time()}

    # Memory
    try:
        mem = {}
        for line in sh(["cat", "/proc/meminfo"]).split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                v = int(v.strip().split()[0]) * 1024
                mem[k.strip()] = v
        buff_cache = mem.get("Buffers", 0) + mem.get("Cached", 0) + mem.get("SReclaimable", 0)
        used_raw = mem.get("MemTotal", 0) - mem.get("MemFree", 0) - buff_cache
        s["memory"] = {
            "total": mem.get("MemTotal", 0),
            "used": mem.get("MemTotal", 0) - mem.get("MemAvailable", 0),
            "used_raw": max(used_raw, 0),
            "free": mem.get("MemFree", 0),
            "shared": mem.get("Shmem", 0),
            "buff_cache": buff_cache,
            "available": mem.get("MemAvailable", 0),
        }
        s["swap"] = {
            "total": mem.get("SwapTotal", 0),
            "used": mem.get("SwapTotal", 0) - mem.get("SwapFree", 0),
            "free": mem.get("SwapFree", 0),
            "cached": mem.get("SwapCached", 0),
        }
        app_pct = s["memory"]["used_raw"] / max(s["memory"]["total"], 1)
        swap_pct = s["swap"]["used"] / max(s["swap"]["total"], 1)
        s["pressure"] = round(app_pct * 60 + swap_pct * 40, 1)
    except Exception:
        s["memory"] = {"total": 0, "used": 0, "free": 0, "shared": 0, "buff_cache": 0, "available": 0}
        s["swap"] = {"total": 0, "used": 0, "free": 0, "cached": 0}
        s["pressure"] = 0

    # Swap activity
    try:
        out = sh(["vmstat", "1", "2"]).strip().split("\n")
        if len(out) >= 3:
            cols = out[2].split()
            si = int(cols[6]) if len(cols) > 6 else 0
            so = int(cols[7]) if len(cols) > 7 else 0
            s["swap_activity"] = {"si": si, "so": so}
        else:
            s["swap_activity"] = {"si": 0, "so": 0}
    except Exception:
        s["swap_activity"] = {"si": 0, "so": 0}

    # Load
    try:
        l = os.getloadavg()
        cpus = os.cpu_count() or 1
        s["load"] = {"1m": round(l[0], 2), "5m": round(l[1], 2), "15m": round(l[2], 2), "cores": cpus}
    except Exception:
        s["load"] = {"1m": 0, "5m": 0, "15m": 0, "cores": 1}

    # Disk
    try:
        parts = sh(["df", "-B1", "/"]).strip().split("\n")[1].split()
        s["disk"] = {"total": int(parts[1]), "used": int(parts[2]), "free": int(parts[3]), "pct": parts[4]}
    except Exception:
        s["disk"] = {"total": 0, "used": 0, "free": 0, "pct": "?"}

    # Top processes
    try:
        out = sh(["ps", "aux", "--sort=-%mem", "--no-headers"])
        procs = []
        for line in out.strip().split("\n")[:10]:
            p = line.split(None, 10)
            if len(p) >= 11:
                procs.append({"user": p[0], "pid": int(p[1]), "cpu": float(p[2]), "mem": float(p[3]),
                              "vsz": int(p[4]), "rss": int(p[5]), "time": p[9], "cmd": p[10][:80]})
        s["top_procs"] = procs
    except Exception:
        s["top_procs"] = []

    # Uptime / connections
    try:
        s["uptime"] = sh(["uptime", "-p"]).strip()
    except Exception:
        s["uptime"] = "?"
    try:
        s["connections"] = sh(["ss", "-t", "state", "established"]).count("\n") - 1
    except Exception:
        s["connections"] = 0

    return s


# ── Token Usage Aggregation ───────────────────────────────────────────

def get_usage():
    """Aggregate token usage by provider for 24h, 7d, 30d, and all-time."""
    result = {
        "by_provider": {},
        "by_provider_windows": {},  # per-provider costs per time window
        "totals": {"24h": {}, "7d": {}, "30d": {}, "all": {}},
        "daily": [],
    }
    if not USAGE_DB.exists():
        return result

    try:
        conn = sqlite3.connect(str(USAGE_DB))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        now = datetime.utcnow()
        cuts = {
            "24h": (now - timedelta(hours=24)).isoformat(),
            "7d": (now - timedelta(days=7)).isoformat(),
            "30d": (now - timedelta(days=30)).isoformat(),
        }

        # Per-provider aggregation (all time) with models breakdown
        cur.execute("""
            SELECT provider,
                   SUM(input_tokens) as inp, SUM(output_tokens) as out,
                   SUM(total_tokens) as total, SUM(reasoning_tokens) as reason,
                   SUM(cost) as cost,
                   COUNT(*) as calls
            FROM api_calls
            GROUP BY provider
            ORDER BY cost DESC
        """)
        for row in cur.fetchall():
            p = row["provider"]
            result["by_provider"][p] = dict(row)

        # Per-provider model breakdown
        cur.execute("""
            SELECT provider, model,
                   SUM(cost) as cost, COUNT(*) as calls
            FROM api_calls
            GROUP BY provider, model
            ORDER BY provider, cost DESC
        """)
        for row in cur.fetchall():
            r = dict(row)
            p = r.pop("provider")
            result["by_provider"].setdefault(p, {})
            if "models" not in result["by_provider"][p]:
                result["by_provider"][p]["models"] = []
            result["by_provider"][p]["models"].append(r)

        # Per-provider costs per time window (for cap bars)
        for label, cutoff in cuts.items():
            cur.execute("""
                SELECT provider,
                       SUM(cost) as cost,
                       SUM(total_tokens) as total,
                       COUNT(*) as calls
                FROM api_calls WHERE timestamp >= ?
                GROUP BY provider
                ORDER BY cost DESC
            """, (cutoff,))
            window_data = {}
            for row in cur.fetchall():
                window_data[row["provider"]] = dict(row)
            result["by_provider_windows"][label] = window_data

        # Totals per time window
        for label, cutoff in cuts.items():
            cur.execute("""
                SELECT SUM(input_tokens) as inp, SUM(output_tokens) as out,
                       SUM(total_tokens) as total, SUM(cost) as cost,
                       COUNT(*) as calls
                FROM api_calls WHERE timestamp >= ?
            """, (cutoff,))
            row = cur.fetchone()
            result["totals"][label] = dict(row) if row and row["total"] else {"inp": 0, "out": 0, "total": 0, "cost": 0, "calls": 0}

        # All-time totals
        cur.execute("""
            SELECT SUM(input_tokens) as inp, SUM(output_tokens) as out,
                   SUM(total_tokens) as total, SUM(cost) as cost,
                   COUNT(*) as calls
            FROM api_calls
        """)
        row = cur.fetchone()
        result["totals"]["all"] = dict(row) if row and row["total"] else {"inp": 0, "out": 0, "total": 0, "cost": 0, "calls": 0}

        # Daily trend (last 14 days) — all providers combined
        cutoff_14d = (now - timedelta(days=14)).isoformat()
        cur.execute("""
            SELECT DATE(timestamp) as day,
                   SUM(total_tokens) as total, SUM(cost) as cost,
                   COUNT(*) as calls
            FROM api_calls WHERE timestamp >= ?
            GROUP BY DATE(timestamp)
            ORDER BY day ASC
        """, (cutoff_14d,))
        for row in cur.fetchall():
            result["daily"].append(dict(row))

        # Daily trend per provider (last 5 days) — for PAYG per-card bars
        cutoff_5d = (now - timedelta(days=4)).isoformat()  # 5 days including today
        cur.execute("""
            SELECT provider, DATE(timestamp) as day,
                   SUM(cost) as cost, SUM(total_tokens) as total
            FROM api_calls WHERE timestamp >= ?
            GROUP BY provider, DATE(timestamp)
            ORDER BY provider, day ASC
        """, (cutoff_5d,))
        daily_by_prov = {}
        for row in cur.fetchall():
            r = dict(row)
            p = r.pop("provider")
            daily_by_prov.setdefault(p, []).append(r)
        result["daily_by_provider"] = daily_by_prov

        conn.close()
    except Exception:
        pass

    return result


# ── ChatGPT Plus Quota Query ─────────────────────────────────────────

def get_chatgpt_plus_usage():
    """Query ChatGPT Plus usage via Codex OAuth token."""
    try:
        auth_path = Path.home() / ".codex" / "auth.json"
        if not auth_path.exists():
            return {"error": "Codex auth not found"}
        auth = json.loads(auth_path.read_text())
        if auth.get("auth_mode") != "chatgpt":
            return {"error": "Codex not in chatgpt mode"}
        tokens = auth.get("tokens", {})
        access_token = tokens.get("access_token", "")
        account_id = tokens.get("account_id", "")
        if not access_token:
            return {"error": "No access token"}

        import urllib.request
        req = urllib.request.Request(
            "https://chatgpt.com/backend-api/wham/usage",
            headers={
                "Authorization": f"Bearer {access_token}",
                "ChatGPT-Account-Id": account_id,
                "User-Agent": "codex-cli",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return {
            "plan_type": data.get("plan_type", ""),
            "email": data.get("email", ""),
            "rate_limit": data.get("rate_limit", {}),
            "credits": data.get("credits", {}),
        }
    except Exception as e:
        return {"error": str(e)}


# ── OpenCode Go Usage (manual config) ────────────────────────────────

GO_USAGE_FILE = DIR / "go_usage.json"

def get_go_usage():
    """Read manual Go usage config (updated by user from workspace page)."""
    try:
        if GO_USAGE_FILE.exists():
            return json.loads(GO_USAGE_FILE.read_text())
    except:
        pass
    return {"5hr": 0, "5day": 0, "30day": 0, "error": "Config not found"}

# ── OpenCode Stats ─────────────────────────────

def get_opencode_stats():
    """Query OpenCode CLI stats for Zen cost."""
    try:
        import subprocess
        r = subprocess.run(
            ["opencode", "stats", "--days", "30"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0:
            return {"error": r.stderr.strip()}
        out = r.stdout
        # Parse total cost
        cost = None
        for line in out.split("\n"):
            line = line.strip()
            if "Total Cost" in line:
                import re
                m = re.search(r'\$?([0-9]+\.[0-9]+)', line)
                if m:
                    cost = float(m.group(1))
        return {"total_cost_30d": cost, "raw": out[:500]}
    except Exception as e:
        return {"error": str(e)}


# ── Tokscale Cross-Agent Token Tracking ───────────────────────────────

TOKSCALE_CACHE = DIR / "tokscale_cache.json"

def get_tokscale_data():
    """Read cached tokscale data (refreshed by cron every 2 hours)."""
    if not TOKSCALE_CACHE.exists():
        return {"clients": [], "monthly": [], "total_cost": 0, "error": "cache not found"}
    try:
        return json.loads(TOKSCALE_CACHE.read_text())
    except Exception as e:
        return {"clients": [], "monthly": [], "total_cost": 0, "error": str(e)}


# ── HTTP Handler ──────────────────────────────────────────────────────


# ── Mimo Usage (manual config) ────────────────────────────────────────

MIMO_USAGE_FILE = DIR / "mimo_usage.json"

def get_mimo_usage():
    """Read manual Mimo usage config."""
    try:
        if MIMO_USAGE_FILE.exists():
            return json.loads(MIMO_USAGE_FILE.read_text())
    except:
        pass
    return {"credits_total": 60000000, "credits_used": 0, "error": "Config not found"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        p = urlparse(self.path)
        try:
            if p.path == "/":
                body = (DIR / "index.html").read_bytes()
                self._respond(200, "text/html", body)
            elif p.path == "/api/stats":
                body = json.dumps(get_stats()).encode()
                self._respond(200, "application/json", body)
            elif p.path == "/api/usage":
                u = get_usage()
                u["chatgpt_plus"] = get_chatgpt_plus_usage()
                u["opencode_stats"] = get_opencode_stats()
                u["go_usage"] = get_go_usage()
                u["mimo_usage"] = get_mimo_usage()
                body = json.dumps(u).encode()
                self._respond(200, "application/json", body)
            elif p.path == "/api/tokscale":
                body = json.dumps(get_tokscale_data()).encode()
                self._respond(200, "application/json", body)
            elif p.path == "/api/usage/reset":
                # DELETE all usage data (confirm with ?confirm=1)
                if p.query == "confirm=1" and USAGE_DB.exists():
                    conn = sqlite3.connect(str(USAGE_DB))
                    conn.execute("DELETE FROM api_calls")
                    conn.commit()
                    conn.close()
                self._respond(200, "application/json", json.dumps({"ok": True}).encode())
            else:
                self.send_error(404)
        except Exception as e:
            self.send_error(500, str(e))

    def _respond(self, code, mime, body):
        self.send_response(code)
        self.send_header("Content-Type", f"{mime}; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"VPS Monitor on http://0.0.0.0:{PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

