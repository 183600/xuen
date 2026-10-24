"""v9.0 CHD ablation on the 141 YES corpus."""
import sys
import pickle
import json
import time
from collections import Counter

sys.setrecursionlimit(100000)
sys.path[:0] = ['exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from chd import CHD

FILES = {'holdout': 'exp/v20/holdout_cases50.pkl',
         'synth': 'exp/v28/synth2_45.pkl',
         'large_a': 'exp/v14/large_a.pkl',
         'large_b': 'exp/v14/large_b.pkl',
         'large_het': 'exp/v14/large_het.pkl',
         'hard3': 'exp/v13/hard3.pkl',
         'deep': 'exp/v18/deep.pkl'}


def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]


def corpus():
    out = []
    for name, f in FILES.items():
        for idx, (inst, opt) in enumerate(load(f)):
            out.append((name, idx, inst, opt))
    return out


VARIANTS = [
    ('full', {}),
    ('no_hull', dict(hull_on=False)),
    ('no_lds', dict(cheap_disc=0, hull_disc=0)),
    ('hull_only', dict(cheap_disc=-1)),
    ('hull_only_d0', dict(cheap_disc=-1, hull_disc=0)),
    ('cheap_d1', dict(cheap_disc=1)),
    ('cheap_d3', dict(cheap_disc=3)),
    ('hull_d2', dict(hull_disc=2)),
    ('no_random', dict(random_fallback=False)),
]


def main():
    cs = corpus()
    out = []
    for vname, kw in VARIANTS:
        t0 = time.time()
        rows = []
        for name, idx, inst, opt in cs:
            q = CHD(inst, opt, yes_scan=True, **kw)
            v, st = q.decide(budget=100, nodecap=5000)
            rows.append(dict(name=name, idx=idx, v=v,
                             lp=st.get('lp_solves'),
                             nodes=st.get('nodes'),
                             phase=st.get('phase'),
                             why=st.get('why'),
                             lds_nodes=st.get('lds_nodes'),
                             hull_lp=st.get('hull_lp'),
                             hull_time=st.get('hull_time'),
                             used_random=st.get('used_random'),
                             audit=bool(q.audit_chd()),
                             pc=bool(q.proof_complete())))
        dt = time.time() - t0
        agg = dict(variant=vname, yes=sum(r['v'] is True for r in rows),
                   unk=sum(r['v'] is None for r in rows),
                   no=sum(r['v'] is False for r in rows),
                   lp=sum(r['lp'] for r in rows),
                   lds_nodes=sum(r['lds_nodes'] for r in rows),
                   hull_lp=sum(r['hull_lp'] or 0 for r in rows),
                   hull_time=round(sum(r['hull_time'] or 0 for r in rows), 3),
                   random=sum(bool(r['used_random']) for r in rows),
                   audit=sum(r['audit'] for r in rows),
                   pc=sum(r['pc'] for r in rows),
                   t=round(dt, 2),
                   phases=dict(Counter(r['phase'] for r in rows)))
        out.append(dict(agg=agg, rows=rows))
        print(agg, flush=True)
    json.dump(out, open('exp/v9b/bench_ablate.json', 'w'))
    print('\nsummary')
    for x in out:
        a = x['agg']
        print('%-12s YES %3d UNK %2d LP %5d LDS %6d hullLP %4d '
              'hullT %5.2f rand %2d t %5.2f %s' %
              (a['variant'], a['yes'], a['unk'], a['lp'], a['lds_nodes'],
               a['hull_lp'], a['hull_time'], a['random'], a['t'],
               a['phases']))


if __name__ == '__main__':
    main()
