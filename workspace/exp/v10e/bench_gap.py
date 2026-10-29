import sys, json, time
sys.path[:0] = ['exp/v10e', 'exp/v10b', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from mht import run_mht

cases = json.load(open('exp/v10c/gap_cases.json'))
out = []
t0 = time.time()
for j, d in enumerate(cases):
    t = time.time()
    r = run_mht(d['inst'], d['opt'], d['case'], d.get('idx'),
                W=32, cache_cap=64, max_time=120)
    r['wall'] = round(time.time() - t, 4)
    out.append(r)
    print(j, d['case'], 'L/U', r.get('L'), r.get('U'), 'probes',
          r.get('probes'), 'lp', r.get('lp'), 'cert', r.get('cert_lp'),
          'tot', r.get('total_lp'), 'spl', r.get('splits'),
          'certified', r.get('certified'), 'wall', r['wall'],
          flush=True)
json.dump(out, open('exp/v10e/bench_gap_w32.json', 'w'), indent=1)
print('TOTAL', round(time.time() - t0, 2))
