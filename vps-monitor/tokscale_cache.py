#!/usr/bin/env python3
"""Cache tokscale data every 2 hours (7am-11pm server time)."""
import json
import subprocess
from pathlib import Path
from datetime import datetime

TOKSCALE_BIN = Path.home() / ".npm-global" / "bin" / "tokscale"
CACHE_FILE = Path(__file__).parent / "tokscale_cache.json"

def run_tokscale():
    """Query tokscale for clients + monthly + models."""
    result = {
        "clients": [],
        "monthly": [],
        "models": [],
        "by_provider": {},
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
        
        # Model-level costs (per client, per model)
        r = subprocess.run(
            [str(TOKSCALE_BIN), "models", "--json"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, timeout=60,
        )
        if r.returncode == 0:
            data = json.loads(r.stdout)
            result["models"] = data.get("entries", [])
            
            # Aggregate by provider (extract from model name or provider field)
            provider_map = {
                'deepseek': 'DeepSeek',
                'glm': 'GLM',
                'gpt': 'OpenAI',
                'claude': 'Anthropic',
                'kimi': 'Kimi',
                'mimo': 'Mimo',
                'qwen': 'Qwen',
                'minimax': 'MiniMax',
            }
            
            for entry in result["models"]:
                model = entry.get("model", "unknown")
                # Find provider from model name
                provider = "Other"
                for prefix, name in provider_map.items():
                    if model.startswith(prefix) or prefix in model.lower():
                        provider = name
                        break
                
                if provider not in result["by_provider"]:
                    result["by_provider"][provider] = {
                        "cost": 0,
                        "input": 0,
                        "output": 0,
                        "messageCount": 0,
                        "models": [],
                    }
                
                p = result["by_provider"][provider]
                p["cost"] += entry.get("cost", 0)
                p["input"] += entry.get("input", 0)
                p["output"] += entry.get("output", 0)
                p["messageCount"] += entry.get("messageCount", 0)
                p["models"].append({
                    "model": model,
                    "cost": entry.get("cost", 0),
                    "messageCount": entry.get("messageCount", 0),
                })
            
            # Sort providers by cost
            result["by_provider"] = dict(
                sorted(result["by_provider"].items(), key=lambda x: -x[1]["cost"])
            )
            
    except Exception as e:
        result["error"] = str(e)
    
    return result

if __name__ == "__main__":
    data = run_tokscale()
    CACHE_FILE.write_text(json.dumps(data, indent=2))
    prov_count = len(data.get('by_provider', {}))
    print(f"✓ Cached: {len(data['clients'])} clients, {prov_count} providers, $({data['total_cost']:.2f} total)")
