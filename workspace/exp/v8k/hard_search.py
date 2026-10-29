"""Small hard-instance probe for v8.10 CDCL-ALC.

The seed-0 instance is the one used in the round-1 notes: n=18, m=3,
random p in [1,20], q in [0,10], 10 precedence edges, eligibility 0.8.
h=69 is the first horizon where the root LP is already infeasible; the
integer certificate path fails there, so both PRISM and CDCL return
UNKNOWN.  h=70/72/74 are YES probes used to measure widening overhead.
"""
import random
import sys
import time

sys.path[:0] = ['exp/v8k', 'exp/v8j', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from cdcl import cdcl_decide
from prism import interval_branch_decide


def rand_inst(n=18, m=3, seed=0):
    rng = random.Random(seed)
    p = [rng.randint(1, 20) for _ in range(n)]
    q = [rng.randint(0, 10) for _ in range(n)]
    pred = [[] for _ in range(n)]
    succ = [[] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < 0.05:
                succ[i].append(j)
                pred[j].append(i)
    elig = []
    for _ in range(n):
        e = [k for k in range(m) if rng.random() < 0.8]
        if not e:
            e = [rng.randrange(m)]
        elig.append(e)
    return dict(n=n, m=m, p=p, q=q, pred=pred, succ=succ, elig=elig,
                pmask=[sum(1 << k for k in e) for e in elig],
                desc=[0] * n, full=(1 << n) - 1)


def one(inst, h):
    out = []
    for tag, fn in (
            ('prism', lambda: interval_branch_decide(
                inst, h, nodecap=96, depthcap=24)),
            ('cdcl', lambda: cdcl_decide(
                inst, h, nodecap=96, depthcap=24,
                learn=True, widen=False)),
            ('cdclw', lambda: cdcl_decide(
                inst, h, nodecap=96, depthcap=24,
                learn=True, widen=True, widen_budget=32))):
        t = time.time()
        r = fn()
        out.append((tag, r['verdict'], r['nodes'], r.get('leaves'),
                    r.get('lp_solves'), r.get('cert_lp'),
                    r.get('lemmas'), r.get('learn_hits'),
                    round(time.time() - t, 3),
                    r['proof'].audit_rdf() if r.get('proof') else None))
    return out


if __name__ == '__main__':
    inst = rand_inst()
    print('p', inst['p'])
    print('q', inst['q'])
    print('edges', sum(len(x) for x in inst['succ']))
    for h in (69, 70, 72, 74):
        print('h', h)
        for row in one(inst, h):
            print(' ', row)
