"""ACO-HPO over a decision-list portfolio of sound components.

An ant constructs a policy:
    if cond1: cfg1  elif cond2: cfg2  else: default_cfg
Pheromone lives on (position, condition) and (position, config).  Fitness is
the total wall time on the training cases plus a small complexity penalty.
All configurations are sound, so any policy is sound.
"""
import random, math, pickle, collections, statistics

CONDS = ['n<=12', 'n<=14', 'n<=16', 'n<=18', 'n<=20',
         'full', 'notfull', 'S<=2', 'S<=4', 'S<=6', 'S<=10',
         'm==3', 'm==4']

def feat(r, c):
    n, full, S, m = r['n'], r['full'], r['S'], r['m']
    return {'n<=12': n <= 12, 'n<=14': n <= 14, 'n<=16': n <= 16,
            'n<=18': n <= 18, 'n<=20': n <= 20, 'full': full,
            'notfull': not full, 'S<=2': S <= 2, 'S<=4': S <= 4,
            'S<=6': S <= 6, 'S<=10': S <= 10, 'm==3': m == 3, 'm==4': m == 4}[c]

def eval_policy(pol, cases, bycase, penalty=0.002):
    c1, f1, c2, f2, f3 = pol
    tot = 0.0
    for k in cases:
        r = bycase[k]
        if c1 is not None and feat(r, c1):
            f = f1
        elif c2 is not None and feat(r, c2):
            f = f2
        else:
            f = f3
        tot += r['perf'][f]
    return tot + penalty * ((c1 is not None) + (c2 is not None))

def build_data(rows):
    bycase = {}
    for r in rows:
        k = (r['fam'], r['idx'])
        if k not in bycase:
            bycase[k] = dict(n=r['n'], full=r['full'], S=r['S'], m=r['m'], perf={})
        bycase[k]['perf'][r['cfg']] = r['perf']
    cfgs = sorted({r['cfg'] for r in rows})
    return list(bycase), bycase, cfgs

def softmax(xs, temp=1.0):
    mx = max(xs); z = [math.exp((x - mx) / temp) for x in xs]; s = sum(z)
    return [v / s for v in z]

def sample(probs):
    u = random.random(); a = 0.0
    for i, p in enumerate(probs):
        a += p
        if u <= a: return i
    return len(probs) - 1

def aco(train, bycase, cfgs, seed=0, ants=24, iters=40, alpha=1.0):
    rng = random.Random(seed)
    conds = CONDS + [None]
    nc, nf = len(conds), len(cfgs)
    # tau[pos][kind][value]
    tau_c = [[1.0] * nc for _ in range(2)]
    tau_f = [[1.0] * nf for _ in range(3)]
    best = (1e18, None)
    hist = []
    for it in range(iters):
        cand = []
        for a in range(ants):
            cs = []
            for pos in range(2):
                pc = softmax([v ** alpha for v in tau_c[pos]])
                ci = sample([p / sum(pc) for p in pc])
                cs.append(conds[ci])
            pf = softmax([v ** alpha for v in tau_f[2]])
            fi = sample([p / sum(pf) for p in pf])
            # rules use configs sampled from position pheromone, but conditioned on chosen cond
            pol = []
            for pos in range(2):
                pf = softmax([v ** alpha for v in tau_f[pos]])
                fi = sample([p / sum(pf) for p in pf])
                pol += [cs[pos], cfgs[fi]]
            pol.append(cfgs[fi] if False else cfgs[sample(
                [p / sum(softmax([v ** alpha for v in tau_f[2]]))
                 for p in softmax([v ** alpha for v in tau_f[2]])])])
            val = eval_policy(pol, train, bycase)
            cand.append((val, pol))
        cand.sort(key=lambda x: x[0])
        if cand[0][0] < best[0]:
            best = (cand[0][0], cand[0][1])
        # MMAS-ish update: evaporate, deposit on top 6
        rho = 0.25
        for pos in range(2):
            for i in range(nc): tau_c[pos][i] *= (1 - rho)
            for i in range(nf): tau_f[pos][i] *= (1 - rho)
        for i in range(nf): tau_f[2][i] *= (1 - rho)
        for val, pol in cand[:6]:
            c1, f1, c2, f2, f3 = pol
            dep = 1.0 / (1e-6 + val)
            for pos, c in enumerate((c1, c2)):
                if c is not None:
                    tau_c[pos][conds.index(c)] += dep
            for pos, f in enumerate((f1, f2)):
                tau_f[pos][cfgs.index(f)] += dep
            tau_f[2][cfgs.index(f3)] += dep
        hist.append(best[0])
    return best, hist

def main():
    rows = pickle.load(open('exp/v42/matrix_no.pkl', 'rb'))
    cases, bycase, cfgs = build_data(rows)
    print('cases', len(cases), 'cfgs', len(cfgs))
    for seed in range(3):
        best, hist = aco(cases, bycase, cfgs, seed=seed)
        print('seed', seed, 'best', round(best[0], 4), best[1], 'hist', [round(x, 4) for x in hist[::8]])
    # leave-one-index-mod-5-out CV: train on 4/5, test on 1/5
    for K in [5]:
        tests = []
        for fold in range(K):
            tr = [k for k in cases if k[1] % K != fold]
            te = [k for k in cases if k[1] % K == fold]
            best, _ = aco(tr, bycase, cfgs, seed=100 + fold)
            pol = best[1]
            tev = eval_policy(pol, te, bycase, penalty=0)
            tests.append((tev, pol))
            print('fold', fold, 'train', round(best[0], 4), 'test', round(tev, 4), pol)
        print('CV test total', round(sum(t for t, _ in tests), 4))

if __name__ == '__main__':
    main()
