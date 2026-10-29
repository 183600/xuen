"""X-DUB/RO* experiments.

- RO-ROLLOUT: 1-ply lookahead with deadline-aware (LST) playout.
- base: v0.5-style FOCAL+DOM+inherit with 4-rule greedy UB.
- pv:   same exact search, but U0 from RO-ROLLOUT.
Compares node counts, anytime gaps, rollout hit rate, and the
"last-Delta" scaling limitation.
"""
import sys, time, json, random, pickle
sys.path.insert(0, '/home/runner/work/xuen/xuen/workspace/exp')
import exp_da as E

# ------------------------------------------------------------------ policies
def greedy_rule(inst, S, A, c, rule):
    n, p, pred, desc = inst['n'], inst['p'], inst['pred'], inst['desc']
    A = list(A); c = list(c)
    while True:
        est, q = E.heads_tails(inst, S, tuple(c))
        ready = [i for i in range(n)
                 if not ((S >> i) & 1) and all((S >> j) & 1 for j in pred[i])]
        if not ready:
            break
        if rule == 'CP':      i = max(ready, key=lambda x: (q[x], -x))
        elif rule == 'LST':   i = max(ready, key=lambda x: (p[x] + q[x], -x))
        elif rule == 'LPT':   i = max(ready, key=lambda x: (p[x], -x))
        elif rule == 'MWKR':
            def rw(x):
                d = desc[x]; s = 0
                for j in range(n):
                    if (d >> j) & 1 and not ((S >> j) & 1):
                        s += p[j]
                return s
            i = max(ready, key=lambda x: (rw(x), -x))
        else:
            i = min(ready)
        base = max([c[j] for j in pred[i]] + [0])
        bk = min(range(len(A)), key=lambda k: (max(A[k], base) + p[i], k))
        st = max(A[bk], base); A[bk] = st + p[i]; c[i] = st + p[i]; S |= 1 << i
    return max(A)

def portfolio(inst, S, A, c, rules=('CP', 'LST', 'LPT', 'MWKR')):
    return {r: greedy_rule(inst, S, A, c, r) for r in rules}

# ------------------------------------------------------------------ rollout
def rollout(inst, inner='LST', cap_actions=None):
    n, p, pred = inst['n'], inst['p'], inst['pred']
    S, A, c = 0, [0] * inst['m'], [-1] * n
    pv = []
    while True:
        ready = [i for i in range(n)
                 if not ((S >> i) & 1) and all((S >> j) & 1 for j in pred[i])]
        if not ready:
            break
        best = None
        for i in ready:
            base = max([c[j] for j in pred[i]] + [0])
            for k in range(len(A)):
                st = max(A[k], base)
                A2 = list(A); A2[k] = st + p[i]
                c2 = list(c); c2[i] = st + p[i]
                val = greedy_rule(inst, S | (1 << i), tuple(sorted(A2)),
                                  tuple(c2), inner)
                if best is None or (val, i, k) < best:
                    best = (val, i, k)
        val, i, k = best
        base = max([c[j] for j in pred[i]] + [0]); st = max(A[k], base)
        A[k] = st + p[i]; c[i] = st + p[i]; S |= 1 << i
        pv.append((i, k))
    return max(A), pv

# ------------------------------------------------------------------ exact search
def search(inst, U0=None, rules=('CP', 'LST', 'LPT', 'MWKR'),
           budget=3000, omega=2, Bf=32, Kdom=60, want_anytime=True):
    n = inst['n']; full = (1 << n) - 1
    S0, A0, c0 = 0, tuple([0] * inst['m']), (-1,) * n
    if U0 is None:
        U0 = min(portfolio(inst, S0, A0, c0, rules).values())
    U = U0
    L0 = E.lower_L0(inst, S0, A0, c0)
    anytime = {0: U}
    root = {'S': S0, 'A': A0, 'c': c0, 'F': L0, 'f': max(max(A0), L0), 'id': 0}
    Open = [root]; nxt = 1; Dom = {0: [(A0, c0)]}; steps = 0
    stopped = 'open'
    while Open and steps < budget:
        fmin = min(v['f'] for v in Open)
        if fmin >= U:
            stopped = 'proved'; break
        phi = [v for v in Open if v['f'] <= fmin + omega]
        phi.sort(key=lambda v: (v['f'], v['id']))
        cand = phi[:Bf]; bestv = None; bestg = None
        for v in cand:
            g = min(portfolio(inst, v['S'], v['A'], v['c'], rules).values())
            if g < U:
                U = g
            if bestv is None or (g, v['f'], v['id']) < (bestg, bestv['f'], bestv['id']):
                bestv, bestg = v, g
        v = bestv; Open.remove(v); steps += 1
        if steps in (1, 2, 5, 10, 20, 50):
            anytime[steps] = U
        for (cs, ca, cc) in E.gen_children(inst, v['S'], v['A'], v['c']):
            if cs == full:
                if max(ca) < U:
                    U = max(ca)
                continue
            l0 = E.lower_L0(inst, cs, ca, cc)
            if l0 >= U:
                continue
            wins, est, q = E.make_windows(inst, cs, ca, cc, U)
            if wins and E.infeasible_at(inst, cs, ca, cc, U - 1, est, q, wins):
                continue
            g = min(portfolio(inst, cs, ca, cc, rules).values())
            if g < U:
                U = g
            Fw = max(v['F'], l0); fw = max(max(ca), Fw)
            if fw >= U:
                continue
            b = Dom.setdefault(cs, [])
            if any(E.dominates(A2, c2, ca, cc, cs) for (A2, c2) in b):
                continue
            b[:] = [(A2, c2) for (A2, c2) in b
                    if not E.dominates(ca, cc, A2, c2, cs)]
            if len(b) < Kdom:
                b.append((ca, cc))
            Open.append({'S': cs, 'A': ca, 'c': cc, 'F': Fw,
                         'f': fw, 'id': nxt}); nxt += 1
    if not Open:
        stopped = 'exhausted'
    L = max(L0, min((x['f'] for x in Open), default=L0))
    for b in (1, 2, 5, 10, 20, 50, 100):
        if b not in anytime:
            anytime[b] = U
    return {'steps': steps, 'U': U, 'L': L, 'L0': L0, 'proved': L >= U,
            'anytime': anytime, 'stopped': stopped}

# ------------------------------------------------------------------ data
def build_pool(seed=77, tries=500, min_steps=12):
    rng = random.Random(seed)
    hard = []
    for _ in range(tries):
        n = rng.choice([9, 10])
        inst = E.gen_instance(n, rng.choice([0.1, 0.15, 0.2, 0.25, 0.3]),
                              rng.choice([8, 10, 12, 15, 20]), rng)
        r = E.run(inst, 'AG', budget=1200)
        if r['open'] == 0 and r['steps'] >= min_steps:
            hard.append((r['steps'], inst, r))
    hard.sort(key=lambda x: -x[0])
    return hard

def broad_pool(seed=2024, count=90):
    rng = random.Random(seed)
    out = []
    for _ in range(count):
        n = rng.choice([8, 9, 10])
        inst = E.gen_instance(n, rng.choice([0.1, 0.15, 0.2, 0.25, 0.3, 0.35]),
                              rng.choice([8, 10, 12, 15, 20]), rng)
        r = E.run(inst, 'AG', budget=1500)
        if r['open'] != 0:
            continue
        out.append((r['steps'], inst, r))
    out.sort(key=lambda x: -x[0])
    return out

def main():
    t_start = time.time()
    hard = pickle.load(open('/home/runner/work/xuen/xuen/workspace/exp/hard17.pkl', 'rb'))
    # hard17 was built with the same seed/params as build_pool; reuse.
    broad = broad_pool()
    summary = {'hard17': [], 'broad': [], 'scaling': [], 'negatives': {}}

    # ---------------- hard17: base vs rollout
    tb = tp = tr = 0
    for st, inst, r in hard:
        opt = r['U']; L0 = r['L0']
        t0 = time.time(); uroll, pv = rollout(inst); t_roll = time.time() - t0
        b = search(inst, None); p = search(inst, uroll)
        assert b['U'] == opt and p['U'] == opt
        tb += b['steps']; tp += p['steps']; tr += uroll - opt
        summary['hard17'].append({
            'n': inst['n'], 'edges': sum(len(x) for x in inst['pred']),
            'opt': opt, 'L0': L0, 'ag_steps': st,
            'roll': uroll, 'roll_hit': uroll == opt, 'roll_sec': t_roll,
            'base_steps': b['steps'], 'pv_steps': p['steps'],
            'base_gap0': b['anytime'][0] - opt, 'pv_gap0': p['anytime'][0] - opt})
    summary['hard17_totals'] = {'base': tb, 'pv': tp, 'roll_excess': tr}

    # ---------------- broad: rollout hit rate and anytime
    hits = 0; excess = 0; tb = tp = 0; wins = ties = losses = 0
    gaps = {('base', k): 0 for k in (0, 1, 2, 5, 10, 20)}
    gaps.update({('pv', k): 0 for k in (0, 1, 2, 5, 10, 20)})
    for st, inst, r in broad:
        opt = r['U']
        uroll, pv = rollout(inst)
        b = search(inst, None); p = search(inst, uroll)
        assert b['U'] == opt and p['U'] == opt
        hits += uroll == opt; excess += uroll - opt
        tb += b['steps']; tp += p['steps']
        if p['steps'] < b['steps']: wins += 1
        elif p['steps'] == b['steps']: ties += 1
        else: losses += 1
        for k in (0, 1, 2, 5, 10, 20):
            gaps[('base', k)] += b['anytime'][k] - opt
            gaps[('pv', k)] += p['anytime'][k] - opt
        summary['broad'].append({'n': inst['n'], 'opt': opt, 'L0': r['L0'],
                                 'roll': uroll, 'base': b['steps'], 'pv': p['steps']})
    N = len(broad)
    summary['broad_totals'] = {
        'n': N, 'roll_hits': hits, 'roll_excess': excess,
        'base': tb, 'pv': tp, 'wins': wins, 'ties': ties, 'losses': losses,
        'gap_base': {k: gaps[('base', k)] / N for k in (0, 1, 2, 5, 10, 20)},
        'gap_pv': {k: gaps[('pv', k)] / N for k in (0, 1, 2, 5, 10, 20)}}

    # ---------------- scaling limitation
    for delta in (1, 2, 3, 4):
        same = 0; drop = 0
        for st, inst, r in hard:
            opt = r['U']
            inst2 = dict(inst)
            inst2['p'] = [max(1, x - delta) for x in inst['p']]
            inst2['pred'] = inst['pred']; inst2['succ'] = inst['succ']
            inst2['desc'] = inst['desc']
            res = E.run(inst2, 'AG', budget=2500)
            if res['open'] != 0:
                continue
            if res['U'] == opt:
                same += 1
            drop += opt - res['U']
        summary['scaling'].append({'delta': delta, 'same_opt': same,
                                   'n': len(hard), 'mean_drop': drop / len(hard)})

    # ---------------- CR bound
    cr_greater = 0; cr_vals = []
    for st, inst, r in hard:
        u = r['U']; L0 = r['L0']; rho = 2 - 1 / inst['m']
        lb = (u + rho - 1e-9) // rho  # ceil
        lb = int(-(-u // rho))
        cr_vals.append(lb - L0)
        if lb > L0: cr_greater += 1
    summary['cr'] = {'greater_than_L0': cr_greater, 'n': len(hard),
                     'mean_slack': sum(cr_vals) / len(cr_vals)}

    summary['wall'] = time.time() - t_start
    with open('/home/runner/work/xuen/xuen/workspace/exp/results_ro.json', 'w') as f:
        json.dump(summary, f, indent=1)
    print(json.dumps({k: v for k, v in summary.items()
                      if k not in ('hard17', 'broad')}, indent=1))
    print('hard17:')
    for row in summary['hard17']:
        print(row)
    print('broad totals', summary['broad_totals'])

if __name__ == '__main__':
    main()
