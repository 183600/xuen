"""v9.0 GRSC ablation on the 11 QNC-UNKNOWN YES instances.

det-greedy / rand-greedy: single serial SGS run, no backtracking.
GRSC c: bounded DFS with nodecap c per restart, 96 randomized restarts.
"""
import sys, json, pickle, random, time
sys.path[:0] = ['exp/v90', 'exp/v13']
from grsc import GRSC, check_schedule, heads_tails

FILES = {
    'holdout': 'exp/v20/holdout_cases50.pkl',
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


def cases():
    out = {}
    for name, f in FILES.items():
        for idx, (inst, opt) in enumerate(load(f)):
            out[(name, idx)] = (inst, opt)
    return out


def greedy_once(inst, h, seed=0, mode='mixed'):
    rng = random.Random(seed)
    n, m, p, elig = inst['n'], inst['m'], inst['p'], inst['elig']
    est, q, latest = heads_tails(inst, h)
    if any(est[i] > latest[i] for i in range(n)):
        return None, 0
    starts, machs = [None] * n, [None] * n
    busy = [[] for _ in range(m)]
    rem = [len(inst['pred'][i]) for i in range(n)]
    done = [False] * n
    predfin = [0] * n
    nodes = 0

    def earliest(bk, base, pi):
        t = base
        for a, b in sorted(bk):
            if t + pi <= a:
                break
            if t < b:
                t = b
        return t

    while not all(done):
        nodes += 1
        av = [i for i in range(n) if not done[i] and rem[i] == 0]
        if not av:
            return None, nodes
        if mode == 'rand':
            rng.shuffle(av)
        elif mode == 'est':
            av.sort(key=lambda i: (est[i] + rng.random() * rng.choice([0, 2, 5, 10]), rng.random()))
        else:
            av.sort(key=lambda i: (latest[i] + rng.random() * rng.choice([0, 2, 5, 10]), rng.random()))
        placed = False
        for i in av:
            base = max(est[i], predfin[i])
            opts = []
            for k in elig[i]:
                tt = earliest(busy[k], base, p[i])
                if tt <= latest[i]:
                    opts.append((tt, k))
            opts.sort()
            if not opts:
                continue
            tt, k = opts[0]
            starts[i] = tt
            machs[i] = k
            done[i] = True
            busy[k].append((tt, tt + p[i]))
            busy[k].sort()
            for j in inst['succ'][i]:
                predfin[j] = max(predfin[j], tt + p[i])
                rem[j] -= 1
            placed = True
            break
        if not placed:
            return None, nodes
    return (starts, machs), nodes


def main():
    cs = cases()
    rows = json.load(open('exp/v72t/qnc_yes_only.json'))
    gaps = [(r['case'], r['idx']) for r in rows if r['verdict'] is not True]
    out = {}
    for label, modes, restarts in [('det-greedy', ('est', 'mixed', 'rand'), 3),
                                   ('rand-greedy', ('est', 'mixed', 'rand'), 96)]:
        found = nodes = 0
        t0 = time.time()
        for key in gaps:
            inst, h = cs[key]
            for r in range(restarts):
                res, nd = greedy_once(inst, h, seed=r, mode=modes[r % 3])
                nodes += nd
                if res and check_schedule(inst, h, *res):
                    found += 1
                    break
        out[label] = dict(found=found, nodes=nodes, t=time.time() - t0)
    for nc in (40, 400, 4000):
        found = nodes = 0
        t0 = time.time()
        for key in gaps:
            inst, h = cs[key]
            g = GRSC(inst, h, nodecap=nc, restarts=96, seed=0,
                     modes=('est', 'mixed', 'rand'))
            if g.solve():
                found += 1
            nodes += g.nodes
        out['grsc-%d' % nc] = dict(found=found, nodes=nodes, t=time.time() - t0)
    out['n_gaps'] = len(gaps)
    json.dump(out, open('exp/v90/ablation.json', 'w'), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
