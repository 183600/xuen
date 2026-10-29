import json, sys, time
sys.path[:0] = ['exp/v9acf', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from dacs import run_dacs
mode = sys.argv[1]
rows = []
for d in json.load(open('exp/v10b/gap_stress.json')):
    r = run_dacs(d['inst'], d['opt'], 'gap', d['idx'], mode=mode)
    r['seed'] = d['seed']
    rows.append(r)
    print(mode, d['idx'], r['probes'], r['lp'], r['rounds'], r['ok'], flush=True)
json.dump(rows, open('exp/v9acf/gap_%s.json' % mode, 'w'), indent=1)
print('DONE', mode, sum(r['probes'] for r in rows),
      sum(r['lp'] for r in rows), sum(r['rounds'] for r in rows),
      sum(r['ok'] for r in rows), flush=True)
