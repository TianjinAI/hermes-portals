#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path
from datetime import datetime
from urllib.request import urlopen, Request

TOKSCALE = Path.home() / '.npm-global' / 'bin' / 'tokscale'
CACHE = Path(__file__).parent / 'tokscale_cache.json'
def load_hermes_env():
    """Load API keys from ~/.hermes/.env so script has access to MINIMAX_API_KEY etc."""
    env_file = Path.home() / '.hermes' / '.env'
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                if k not in os.environ:
                    os.environ[k] = v

load_hermes_env()

MINIMAX_API_KEY = os.getenv('MINIMAX_API_KEY', '')
# cn domain works with API key auth; en domain (api.minimax.io) needs session cookie
MINIMAX_TOKEN_PLAN_URL = 'https://api.minimaxi.com/v1/api/openplatform/coding_plan/remains'

def fetch_minimax_remaining():
    """Call MiniMax coding_plan/remains endpoint. Returns (monthly_used_pct, interval_used_pct) tuple or (None, None) on failure.
    monthly limit: 15K msgs (resets monthly).
    5-hr interval limit: 1500 msgs (sliding window).
    Note: API returns usage_count directly — compute used_pct = usage / total."""
    if not MINIMAX_API_KEY:
        return None, None
    try:
        req = Request(
            MINIMAX_TOKEN_PLAN_URL,
            headers={'Authorization': f'Bearer {MINIMAX_API_KEY}', 'Content-Type': 'application/json'}
        )
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            for m in data.get('model_remains', []):
                if m.get('model_name') == 'MiniMax-M*':
                    # Monthly quota
                    w_total = m.get('current_weekly_total_count', 0)
                    w_used = m.get('current_weekly_usage_count', 0)
                    monthly_used_pct = round(w_used / w_total * 100, 2) if w_total > 0 else None
                    # 5-hr interval quota
                    i_total = m.get('current_interval_total_count', 0)
                    i_used = m.get('current_interval_usage_count', 0)
                    interval_used_pct = round(i_used / i_total * 100, 2) if i_total > 0 else None
                    return monthly_used_pct, interval_used_pct
            return None, None
    except Exception as e:
        print('MiniMax API error: %s' % e, file=sys.stderr)
        return None, None

def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    return json.loads(r.stdout.decode()) if r.stdout else {}

try:
    clients = run([str(TOKSCALE), 'clients', '--json']).get('clients', [])
    monthly = run([str(TOKSCALE), 'monthly', '--json']).get('monthly', [])
    models = run([str(TOKSCALE), 'models', '--json']).get('entries', [])
    
    by_provider = {}
    for m in models:
        for p in [x.strip() for x in m.get('provider', '').split(',')]:
            if p not in by_provider:
                by_provider[p] = {'input': 0, 'output': 0, 'cost': 0, 'messageCount': 0, 'models': []}
            by_provider[p]['input'] += m.get('input', 0)
            by_provider[p]['output'] += m.get('output', 0)
            by_provider[p]['cost'] += m.get('cost', 0)
            by_provider[p]['messageCount'] += m.get('messageCount', 0)
            by_provider[p]['models'].append({
                'model': m.get('model', ''),
                'input': m.get('input', 0),
                'output': m.get('output', 0),
                'cost': m.get('cost', 0),
                'messageCount': m.get('messageCount', 0)
            })
    
    mimo_provider = by_provider.get('xiaomi', {'input': 0, 'output': 0, 'cost': 0, 'messageCount': 0})
    minimax_provider = by_provider.get('minimax_cn', {'input': 0, 'output': 0, 'cost': 0, 'messageCount': 0})
    mimo_total_tokens = mimo_provider['input'] + mimo_provider['output']
    minimax_total_tokens = minimax_provider['input'] + minimax_provider['output']
    total_cost = sum(m.get('cost', 0) for m in models)

    # MiniMax — real-time via coding_plan/remains API (CN domain works with API key)
    # Response: { "model_remains": [{ "model_name": "MiniMax-M*", "current_weekly_total_count": 15000,
    #   "current_weekly_usage_count": N, "current_interval_total_count": 1500, "current_interval_usage_count": M }] }
    # monthly limit: 15K msgs; 5-hr interval limit: 1500 msgs (sliding window)
    mm_used_pct, mm_interval_used_pct = fetch_minimax_remaining()
    mm_remaining_pct = round(100 - mm_used_pct, 2) if mm_used_pct is not None else None

    data = {
        'clients': clients,
        'monthly': monthly,
        'by_provider': by_provider,
        'mimo': {
            'input': mimo_provider['input'],
            'output': mimo_provider['output'],
            'total_tokens': mimo_total_tokens,
            'messageCount': mimo_provider['messageCount'],
            'monthly_limit': 200000000,
            'usage_pct': round(mimo_total_tokens / 200000000 * 100, 2) if mimo_total_tokens > 0 else 0,
        },
        'minimax': {
            'input': minimax_provider['input'],
            'output': minimax_provider['output'],
            'total_tokens': minimax_total_tokens,
            'messageCount': minimax_provider['messageCount'],
            'monthly_limit': 15000,
            'remaining': mm_remaining_pct,         # monthly remaining % (100 - used)
            'interval_used': mm_interval_used_pct, # 5-hr interval used %
            'used_pct': mm_used_pct,               # monthly used %
        },
        'total_cost': total_cost,
        'last_update': datetime.now().isoformat()
    }
    
    CACHE.write_text(json.dumps(data, indent=2))
    print('Cached: %d clients, %d months, %d models, MiMo: %d tokens' % (len(clients), len(monthly), len(models), mimo_total_tokens))
except Exception as e:
    print('Error: %s' % e, file=sys.stderr)
    sys.exit(1)
