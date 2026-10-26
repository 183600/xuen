"""Fair wall-clock comparison: a fresh probe cache per (policy, instance)."""
import sys, json, time, argparse
sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']
import bench_balance as bb
from balance import run_balance, ProbeCache

POLS = ['lower-first', 'upper-first', 'binary', 'bayes-cap:3',
        'bayes-cap:3-cv']

def main(init='weak'):
    rows = bb.load_states(init)
    full = bb.table_from_states(rows)
    tabs = {tag: bb.cv_prior(rows, tag) for tag in ('base', 'pert', 'stress')}
    out = {}
    for pol in POLS:
        t0 = time.time()
        rs = []
        for r in rows:
            pt = full if pol != 'bayes-cap:3-cv' else tabs[r['tag']]
            policy = 'bayes-cap:3' if pol == 'bayes-cap:3-cv' else pol
            row = run_balance(r['inst'], r['known'], r['name'], r['idx'],
                              init=init, policy=policy, prior_table=pt,
                              cache=ProbeCache())
            row['corpus'] = r['tag']
            rs.append(row)
        wall = time.time() - t0
        out[pol] = rs
        print(pol, 'wall', round(wall, 2), 'probes', sum(x['probes'] for x in rs),
              'lp', sum(x['lp'] for x in rs), 'ok', sum(x['ok'] for x in rs),
              flush=True)
    json.dump(out, open('exp/v8u/bench_balance_time_%s.json' % init, 'w'),
              indent=1)

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--init', default='weak')
    main(ap.parse_args().init)
