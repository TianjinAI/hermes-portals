#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
from datetime import datetime

TOKSCALE = Path.home() / '.npm-global' / 'bin' / 'tokscale'
CACHE = Path(__file__).parent / 'tokscale_cache.json'

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
    mimo_total_tokens = mimo_provider['input'] + mimo_provider['output']
    total_cost = sum(m.get('cost', 0) for m in models)
    
    data = {
        'clients': clients,
        'monthly': monthly,
        'by_provider': by_provider,
        'mimo': {
            'input': mimo_provider['input'],
            'output': mimo_provider['output'],
            'total_tokens': mimo_total_tokens,
            'messageCount': mimo_provider['messageCount'],
            'monthly_limit': 60000000,
            'usage_pct': round(mimo_total_tokens / 60000000 * 100, 2) if mimo_total_tokens > 0 else 0
        },
        'total_cost': total_cost,
        'last_update': datetime.now().isoformat()
    }
    
    CACHE.write_text(json.dumps(data, indent=2))
    print('Cached: %d clients, %d months, %d models, MiMo: %d tokens' % (len(clients), len(monthly), len(models), mimo_total_tokens))
except Exception as e:
    print('Error: %s' % e, file=sys.stderr)
    sys.exit(1)
