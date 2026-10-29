"""v9.0 constructor ablation at h=OPT.

Compares the v8.0 i.i.d. random trials, the archive constructor, the
pure Markov-chain backstop, and a starved archive with/without the MC
backstop.  All schedules pass check_schedule.
"""
import sys
import pickle
import time
import json

sys.path[:0] = ['exp/v9d', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from cab import CAB

FILES = {'holdout': 'exp/v20/holdout_cases50.pkl',
         'synth': 'exp/v28/synth2_45.pkl',
         'large_a': 'exp/v14/large_a.pkl',
         'large_b': 'exp/v14/large_b.pkl',
         'large_het': 'exp/v14/large_het.pkl',
         'hard3': 'exp/v13/hard3.pkl',
         'deep': 'exp/v18/deep.pkl'}

CFGS = [
    ('iid8/48', dict(mc_on=False, mc_fallback=False,
                     cand_steps1=8, cand_steps2=48)),
    ('arch100/600', dict(uniform=0.0)),
    ('mc-only', dict(cand_steps1=0, cand_steps2=0, mc_steps3=1200)),
    ('starve20/60-mc', dict(cand_steps1=20, cand_steps2=60)),
    ('starve20/60-nomc', dict(cand_steps1=20, cand_steps2=60,
                              mc_fallback=False)),
]


def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]


def corpus():
    return [(name, idx, inst, opt)
            for name, f in FILES.items()
            for idx, (inst, opt) in enumerate(load(f))]


def main():
    data = corpus()
    out = {}
    for tag, kw in CFGS:
        runs = []
        for seed in [0, 1, 2]:
            t0 = time.time()
            yes = yn = ev = lp = calls = mcused = 0
            miss = []
            for name, idx, inst, opt in data:
                q = CAB(inst, opt, yes_scan=True, seed0=seed, **kw)
                v, st = q.decide(budget=100, nodecap=5000)
                yes += int(v is True)
                yn += st.get('yes_nodes', 0)
                ev += st.get('mc_evals', 0)
                lp += st['lp_solves']
                calls += st.get('yes_calls', 0)
                mcused += int(bool(st.get('mc_used')))
                if v is not True:
                    miss.append([name, idx])
            runs.append(dict(seed=seed, yes=yes, ynodes=yn, mc=ev, lp=lp,
                             calls=calls, mcused=mcused,
                             t=round(time.time() - t0, 2), miss=miss))
            print(tag, seed, runs[-1], flush=True)
        out[tag] = runs
    json.dump(out, open('exp/v9d/bench_ctor.json', 'w'))


if __name__ == '__main__':
    main()
