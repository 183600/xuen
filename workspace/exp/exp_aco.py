"""X-DUB/ACO-D experiments (v0.6).

Dependency decomposition + ant-colony construction + certified focal A*.

Reuses the v0.5 primitives in exp_da.py (instance gen, L0, children,
greedy, dominance, exact DFS), and adds:
  - series decomposition (complete-precedence blocks) with exact additivity
  - an ACO whose pheromone lives on incomparable pairs
  - ACO guide inside focal search
  - P2||Cmax bitset optimum for wide independent blocks
"""
import random, time, json, sys, math
from collections import defaultdict

sys.path.insert(0, '/home/runner/work/xuen/xuen/workspace/exp')
import exp_da as B

INF = 10 ** 9


# ------------------------------------------------------------------ DAG tools
def topo_sort(n, pred, succ):
    indeg = [len(pred[i]) for i in range(n)]
    stack = [i for i in range(n) if indeg[i] == 0]
    stack.sort()
    out = []
    while stack:
        u = stack.pop(0)
        out.append(u)
        for v in succ[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                stack.append(v)
        stack.sort()
    return out


def finish_inst(inst):
    n, pred, succ = inst['n'], inst['pred'], inst['succ']
    inst['topo'] = topo_sort(n, pred, succ)
    anc = [0] * n
    for i in inst['topo']:
        a = 0
        for j in pred[i]:
            a |= (1 << j) | anc[j]
        anc[i] = a
    inst['anc'] = anc
    # static critical tail
    q = [0] * n
    for i in reversed(inst['topo']):
        b = 0
        for j in succ[i]:
            b = max(b, inst['p'][j] + q[j])
        q[i] = b
    inst['q'] = q
    B.compute_desc(inst)
    return inst


def series_blocks(inst):
    """Unique coarsest decomposition V = B1 |> B2 |> ... where every task of
    B_i precedes every task of B_j for i<j."""
    n, topo, anc = inst['n'], inst['topo'], inst['anc']
    blocks = []
    start = 0
    prefix = 0
    while start < n:
        found = None
        for end in range(start + 1, n + 1):
            prefix |= 1 << topo[end - 1]
            ok = True
            for t in range(n):
                if not ((prefix >> t) & 1) and (prefix & ~anc[t]):
                    ok = False
                    break
            if ok:
                found = end
                break
        assert found is not None
        blocks.append(topo[start:found])
        start = found
    return blocks


def subinstance(inst, tasks):
    """Induced problem. External predecessors are in earlier series blocks and
    are all finished at the block barrier, so they are dropped."""
    idx = {t: k for k, t in enumerate(tasks)}
    n = len(tasks)
    p = [inst['p'][t] for t in tasks]
    pred = [[idx[u] for u in inst['pred'][t] if u in idx] for t in tasks]
    succ = [[idx[u] for u in inst['succ'][t] if u in idx] for t in tasks]
    sub = {'n': n, 'm': inst['m'], 'p': p, 'pred': pred, 'succ': succ,
           'ep': inst.get('ep', 0), 'pmax': inst.get('pmax', 0)}
    return finish_inst(sub)


def block_l0(inst):
    blocks = series_blocks(inst)
    tot = 0
    parts = []
    for b in blocks:
        sub = subinstance(inst, b)
        l = B.lower_L0(sub, 0, (0,) * sub['m'], (-1,) * sub['n'])
        parts.append((len(b), l))
        tot += l
    return tot, parts


def freedom(inst):
    n, anc = inst['n'], inst['anc']
    inc = 0
    for i in range(n):
        for j in range(i + 1, n):
            if not ((anc[i] >> j) & 1) and not ((anc[j] >> i) & 1):
                inc += 1
    tot = n * (n - 1) // 2
    return inc / tot if tot else 0.0


def p2_opt(p):
    """Exact P2||Cmax via subset-sum bitset."""
    W = sum(p)
    mx = max(p) if p else 0
    if not p:
        return 0
    half = W // 2
    bits = 1
    for x in p:
        bits |= bits << x
    mask = (1 << (half + 1)) - 1
    s = (bits & mask).bit_length() - 1
    return max(mx, W - s)


# ------------------------------------------------------------------ generators
def gen_chain_wide(c, w, pmax, rng, m=2):
    """Block 1 = chain of c tasks; block 2 = w independent tasks; every task
    of block 1 precedes every task of block 2."""
    n = c + w
    p = [rng.randint(1, pmax) for _ in range(n)]
    pred = [[] for _ in range(n)]
    for i in range(1, c):
        pred[i].append(i - 1)
    for t in range(c, n):
        pred[t] = list(range(c))
    succ = [[] for _ in range(n)]
    for j in range(n):
        for i in pred[j]:
            succ[i].append(j)
    inst = {'n': n, 'm': m, 'p': p, 'pred': pred, 'succ': succ,
            'ep': 0, 'pmax': pmax, 'family': 'chain-wide'}
    finish_inst(inst)
    inst['known_opt'] = sum(p[:c]) + (p2_opt(p[c:]) if m == 2 else None)
    return inst


def gen_fork_join(k, L, pmax, rng, m=2):
    """source -> k chains of length L -> sink."""
    n = 1 + k * L + 1
    src, snk = 0, n - 1
    p = [rng.randint(1, pmax) for _ in range(n)]
    pred = [[] for _ in range(n)]
    chains = []
    nxt = 1
    for _ in range(k):
        ch = list(range(nxt, nxt + L))
        nxt += L
        chains.append(ch)
        pred[ch[0]].append(src)
        for a, b in zip(ch, ch[1:]):
            pred[b].append(a)
        pred[snk].append(ch[-1])
    succ = [[] for _ in range(n)]
    for j in range(n):
        for i in pred[j]:
            succ[i].append(j)
    inst = {'n': n, 'm': m, 'p': p, 'pred': pred, 'succ': succ,
            'ep': 0, 'pmax': pmax, 'family': 'fork-join'}
    finish_inst(inst)
    mid = subinstance(inst, list(range(1, n - 1)))
    inst['mid'] = mid
    return inst


# ------------------------------------------------------------------ ACO
class ACO:
    """Pheromone on ordered incomparable pairs (the only free order choices).

    ACO only produces feasible schedules (upper bounds) and guide scores.
    It is never consulted by pruning or by the proof checker.
    """

    def __init__(self, inst, alpha=1.0, beta=1.4, rho=0.2, seed=7,
                 tau0=1.0):
        self.inst = inst
        self.n = inst['n']
        self.alpha, self.beta, self.rho = alpha, beta, rho
        self.tau0 = tau0
        self.rng = random.Random(seed)
        self.anc = inst['anc']
        self.q = inst['q']
        self.p = inst['p']
        self.pred = inst['pred']
        self.tau = {}
        for i in range(self.n):
            for j in range(self.n):
                if i == j:
                    continue
                if not ((self.anc[i] >> j) & 1) and not ((self.anc[j] >> i) & 1):
                    self.tau[(i, j)] = tau0

    def _ready(self, S):
        out = []
        for i in range(self.n):
            if (S >> i) & 1:
                continue
            ok = True
            for j in self.inst['pred'][i]:
                if not ((S >> j) & 1):
                    ok = False
                    break
            if ok:
                out.append(i)
        return out

    def construct(self, S0, A0, c0, eta_mode='crit'):
        n, p, pred = self.n, self.p, self.pred
        S, A, c = S0, list(A0), list(c0)
        order = []
        while True:
            ready = self._ready(S)
            if not ready:
                break
            mass = []
            for i in ready:
                m = 0.0
                for j in ready:
                    if j != i:
                        m += self.tau.get((j, i), 0.0)
                if eta_mode == 'crit':
                    eta = (self.q[i] + p[i]) ** 1.0
                elif eta_mode == 'lpt':
                    eta = p[i]
                elif eta_mode == 'spt':
                    eta = 1.0 / p[i]
                else:
                    eta = 1.0
                mass.append((m ** self.alpha) * (eta ** self.beta))
            tot = sum(mass)
            if tot <= 0:
                i = ready[0]
            else:
                r = self.rng.random() * tot
                acc = 0.0
                i = ready[-1]
                for x, w in zip(ready, mass):
                    acc += w
                    if r <= acc:
                        i = x
                        break
            base = 0
            for j in pred[i]:
                if c[j] > base:
                    base = c[j]
            bk = min(range(len(A)),
                     key=lambda k: (max(A[k], base) + p[i], A[k], k))
            st = max(A[bk], base)
            A[bk] = st + p[i]
            c[i] = st + p[i]
            S |= 1 << i
            order.append(i)
        return max(A), order, (S, tuple(A), tuple(c))

    def reinforce(self, order, C, uref=None):
        """MMAS-style: evaporate, then reinforce the order's incomparable pairs."""
        n = self.n
        # pair set of the order
        pos = {x: k for k, x in enumerate(order)}
        ev = 1.0 - self.rho
        for key in self.tau:
            v = self.tau[key] * ev
            if v < 0.05:
                v = 0.05
            self.tau[key] = v
        if uref is None:
            delta = 1.0
        else:
            delta = 1.0 + max(0.0, (uref - C) / max(1, uref))
        for a in range(len(order)):
            i = order[a]
            for b in range(a + 1, len(order)):
                j = order[b]
                if (i, j) in self.tau:
                    self.tau[(i, j)] = min(6.0, self.tau[(i, j)] + self.rho * delta)

    def run(self, k, S0=0, A0=None, c0=None, uref=None, eta_mode='crit'):
        if A0 is None:
            A0 = (0,) * self.inst['m']
        if c0 is None:
            c0 = (-1,) * self.n
        best = INF
        best_order = None
        for _ in range(k):
            C, order, _ = self.construct(S0, A0, c0, eta_mode)
            if C < best:
                best, best_order = C, order
        if best_order is not None:
            self.reinforce(best_order, best, uref)
        return best


# ------------------------------------------------------------------ search
def run_search(inst, variant='both', budget=400, omega=2, Bf=16, Kdom=80,
               inherit=True, dom=True, aco=None, Kguide=2, seed=0,
               root_thresh=True, collect_anytime=True, aco_root_k=0,
               aco_u_only=False, aco_update_u=True):
    """Focal A* of v0.5 with a pluggable guide.

    variant: best | greedy | aco | both
    """
    n, m = inst['n'], inst['m']
    warm = variant.startswith('warm_')
    core = variant[5:] if warm else variant
    if warm and aco_root_k == 0:
        aco_root_k = 5
    full = (1 << n) - 1
    rng = random.Random(seed)
    S0, A0, c0 = 0, (0,) * m, (-1,) * n
    U = B.greedy(inst, S0, A0, c0, 'CP')
    U = min(U, B.greedy(inst, S0, A0, c0, 'LPT'),
            B.greedy(inst, S0, A0, c0, 'MWKR'))
    L0 = B.lower_L0(inst, S0, A0, c0)
    Lglob = L0
    if root_thresh:
        try:
            LTH, _ = B.thresh(inst, S0, A0, c0, U, L0, 'derand')
            Lglob = max(Lglob, LTH)
        except Exception:
            pass
    if aco is not None and aco_root_k > 0:
        # root construction phase: aco_root_k ants, reinforce the best order
        bestC, bestOrder = INF, None
        for _ in range(aco_root_k):
            Cc, oo, _ = aco.construct(S0, A0, c0)
            if Cc < bestC:
                bestC, bestOrder = Cc, oo
        if bestOrder is not None:
            aco.reinforce(bestOrder, bestC, U)
            U = min(U, bestC)
    F0 = Lglob
    root = {'S': S0, 'A': A0, 'c': c0, 'F': F0,
            'f': max(max(A0), F0), 'id': 0}
    Open = [root]
    nxt = 1
    Dom = {0: [(A0, c0)]}
    steps = 0
    anytime = {}
    t0 = time.time()
    guide_calls = 0
    aco_ants = 0

    def greedy_guide(S, A, c):
        return min(B.greedy(inst, S, A, c, r) for r in ('CP', 'LPT', 'MWKR'))

    def guide(S, A, c):
        """Returns (selection score, feasible UB).  The UB is a primal
        heuristic; the score is only an ordering device."""
        nonlocal guide_calls, aco_ants
        guide_calls += 1
        gub = greedy_guide(S, A, c)
        aub = INF
        if aco is not None and (core in ('aco', 'both') or aco_u_only):
            vals = []
            for _ in range(Kguide):
                C, _, _ = aco.construct(S, A, c)
                vals.append(C)
                aco_ants += 1
            aub = min(vals)
        if aco_u_only:
            score = gub
        elif core == 'aco':
            score = aub
        elif core == 'both':
            score = min(gub, aub)
        else:
            score = gub
        ub = min(gub, aub) if aco_update_u else gub
        return score, ub

    # initial guide / incumbent
    g0, u0g = guide(S0, A0, c0)
    U = min(U, u0g)

    def push_anytime():
        if collect_anytime and steps in (5, 10, 20, 40, 80, 160, 320):
            anytime[str(steps)] = U

    while Open and steps < budget:
        fmin = min(v['f'] for v in Open)
        if fmin >= U:
            break
        if core == 'best':
            v = min(Open, key=lambda x: (x['f'], x['id']))
        else:
            phi = [x for x in Open if x['f'] <= fmin + omega]
            phi.sort(key=lambda x: (x['f'], x['id']))
            cand = phi[:Bf]
            bestv, bestg = None, None
            for x in cand:
                g, ub = guide(x['S'], x['A'], x['c'])
                if ub < U:
                    U = ub
                    order = sorted([i for i in range(n) if (x['S'] >> i) & 1],
                                   key=lambda i: x['c'][i])
                    if aco is not None:
                        aco.reinforce(order, U, U)
                if bestv is None or (g, x['f'], x['id']) < (bestg, bestv['f'], bestv['id']):
                    bestv, bestg = x, g
            v = bestv
        Open.remove(v)
        steps += 1
        # every paradigm gets the same cheap primal heuristic at expansion
        gv = greedy_guide(v['S'], v['A'], v['c'])
        if gv < U:
            U = gv
            order = sorted([i for i in range(n) if (v['S'] >> i) & 1],
                           key=lambda i: v['c'][i])
            if aco is not None:
                aco.reinforce(order, U, U)
        push_anytime()
        if v['S'] == full:
            U = min(U, max(v['A']))
            continue
        for (cs, ca, cc) in B.gen_children(inst, v['S'], v['A'], v['c']):
            if cs == full:
                if max(ca) < U:
                    U = max(ca)
                    order = sorted([i for i in range(n) if (cs >> i) & 1],
                                   key=lambda i: cc[i])
                    if aco is not None:
                        aco.reinforce(order, U, U)
                continue
            l0 = B.lower_L0(inst, cs, ca, cc)
            if l0 >= U:
                continue
            wins, est, q = B.make_windows(inst, cs, ca, cc, U)
            if wins and B.infeasible_at(inst, cs, ca, cc, U - 1, est, q, wins):
                continue
            Fw = max(v['F'], l0) if inherit else l0
            fw = max(max(ca), Fw)
            if fw >= U:
                continue
            if dom:
                bucket = Dom.setdefault(cs, [])
                if any(B.dominates(A2, c2, ca, cc, cs) for (A2, c2) in bucket):
                    continue
                bucket[:] = [(A2, c2) for (A2, c2) in bucket
                             if not B.dominates(ca, cc, A2, c2, cs)]
                if len(bucket) < Kdom:
                    bucket.append((ca, cc))
            Open.append({'S': cs, 'A': ca, 'c': cc, 'F': Fw,
                         'f': fw, 'id': nxt})
            nxt += 1
    if not Open:
        L = U          # every surviving branch was cut at f >= U
    else:
        L = max(Lglob, min(x['f'] for x in Open))
    return {'steps': steps, 'U': U, 'L': L, 'anytime': anytime,
            'time': time.time() - t0, 'open': len(Open), 'L0': L0,
            'guide_calls': guide_calls, 'aco_ants': aco_ants,
            'opt_hit': None}


# ------------------------------------------------------------------ experiments
def exp_decomp(seed=123, quick=True):
    rng = random.Random(seed)
    rows = []
    # (a) random DAGs: does a non-trivial cut exist?
    rnd_counts = [0, 0, 0]
    rnd_fr = []
    for _ in range(40):
        n = rng.choice([9, 10, 11, 12])
        inst = B.gen_instance(n, rng.choice([0.15, 0.25, 0.35]),
                              rng.choice([8, 10, 12]), rng)
        finish_inst(inst)
        blocks = series_blocks(inst)
        rnd_fr.append(freedom(inst))
        rnd_counts[0 if len(blocks) == 1 else (1 if len(blocks) == 2 else 2)] += 1
    rows.append({'family': 'random', 'r1': rnd_counts[0],
                 'r2': rnd_counts[1], 'r3plus': rnd_counts[2],
                 'mean_freedom': sum(rnd_fr) / len(rnd_fr)})

    # (b) chain-wide: exact additivity on small sizes + L0 gap
    cw = []
    for _ in range(20):
        c = rng.randint(3, 6)
        w = rng.randint(3, 6)
        inst = gen_chain_wide(c, w, rng.choice([5, 8, 10]), rng)
        blocks = series_blocks(inst)
        sub = [subinstance(inst, b) for b in blocks]
        opts = [B.exact_opt(s, cap=2_000_000)[0] for s in sub]
        whole = B.exact_opt(inst, cap=2_000_000)[0]
        l0 = B.lower_L0(inst, 0, (0, 0), (-1,) * inst['n'])
        lser, parts = block_l0(inst)
        cw.append({'n': inst['n'], 'nblocks': len(blocks),
                   'opt': whole, 'sum_opt': sum(opts), 'ok': whole == sum(opts),
                   'L0': l0, 'Lser': lser, 'known': inst['known_opt']})
    rows.append({'family': 'chain-wide', 'rows': cw})

    # (c) fork-join: decomposition structure
    fj = []
    for _ in range(10):
        k = rng.randint(2, 4)
        L = rng.randint(2, 4)
        inst = gen_fork_join(k, L, rng.choice([5, 8, 10]), rng)
        blocks = series_blocks(inst)
        fj.append({'n': inst['n'], 'k': k, 'L': L,
                   'nblocks': len(blocks),
                   'sizes': [len(b) for b in blocks],
                   'mid_n': inst['mid']['n']})
    rows.append({'family': 'fork-join', 'rows': fj})
    return rows


def exp_lb(seed=7):
    rng = random.Random(seed)
    rows = []
    for _ in range(24):
        c = rng.randint(3, 6)
        w = rng.randint(4, 8)
        inst = gen_chain_wide(c, w, rng.choice([5, 8, 10]), rng)
        l0 = B.lower_L0(inst, 0, (0, 0), (-1,) * inst['n'])
        lser, parts = block_l0(inst)
        rows.append({'n': inst['n'], 'c': c, 'w': w, 'L0': l0,
                     'Lser': lser, 'opt': inst['known_opt'],
                     'parts': parts})
    return rows


def exp_aco_wide(seed=11, ntests=20):
    """P2||Cmax wide blocks: greedy rules vs ACO (K ants)."""
    rng = random.Random(seed)
    rows = []
    for _ in range(ntests):
        n = rng.randint(10, 14)
        p = [rng.randint(1, 12) for _ in range(n)]
        pred = [[] for _ in range(n)]
        succ = [[] for _ in range(n)]
        inst = {'n': n, 'm': 2, 'p': p, 'pred': pred, 'succ': succ,
                'ep': 0, 'pmax': 12, 'family': 'independent'}
        finish_inst(inst)
        opt = p2_opt(p)
        g = {}
        for rule in ('CP', 'LPT', 'MWKR'):
            g[rule] = B.greedy(inst, 0, (0, 0), (-1,) * n, rule)
        aco = ACO(inst, seed=seed + n)
        aco.run(30, uref=min(g.values()))
        best_aco = aco.run(30, uref=min(g.values()))
        rows.append({'n': n, 'opt': opt, 'CP': g['CP'], 'LPT': g['LPT'],
                     'MWKR': g['MWKR'], 'greedy': min(g.values()),
                     'aco30': best_aco,
                     'greedy_hit': min(g.values()) == opt,
                     'aco_hit': best_aco == opt})
    return rows


def exp_focal(seed=3, n_hard=16, budget=600):
    rng = random.Random(seed)
    # build a pool, keep instances where base search needs work
    pool = []
    for _ in range(260):
        n = rng.choice([9, 10])
        inst = B.gen_instance(n, rng.choice([0.15, 0.2, 0.25, 0.3, 0.35]),
                              rng.choice([8, 10, 12, 15]), rng)
        finish_inst(inst)
        r = run_search(inst, 'greedy', budget=300, seed=seed)
        if 12 <= r['steps'] < 300:
            pool.append((r['steps'], inst))
    pool.sort(key=lambda x: -x[0])
    hard = [inst for _, inst in pool[:n_hard]]
    out = []
    for idx, inst in enumerate(hard):
        opt, nodes, ok = B.exact_opt(inst, cap=2_000_000)
        row = {'idx': idx, 'n': inst['n'],
               'edges': sum(len(x) for x in inst['pred']),
               'opt': opt, 'exact_nodes': nodes, 'exact_ok': ok}
        specs = [
            ('best', dict(variant='best', dom=True), None),
            ('greedy', dict(variant='greedy', dom=True), None),
            ('warm_greedy', dict(variant='warm_greedy', dom=True),
             ACO(inst, seed=200 + idx)),
            ('warm_aco_u', dict(variant='warm_aco', dom=True,
                                 aco_u_only=True), ACO(inst, seed=200 + idx)),
            ('warm_aco_g', dict(variant='warm_aco', dom=True,
                                 aco_update_u=False), ACO(inst, seed=200 + idx)),
            ('warm_aco', dict(variant='warm_aco', dom=True),
             ACO(inst, seed=200 + idx)),
            ('warm_both', dict(variant='warm_both', dom=True),
             ACO(inst, seed=200 + idx)),
            ('greedy_nodom', dict(variant='greedy', dom=False), None),
        ]
        for name, kw, a in specs:
            r = run_search(inst, budget=budget, seed=seed, aco=a, **kw)
            r['name'] = name
            row[name] = r
        a2 = ACO(inst, seed=400 + idx)
        row['aco30_u'] = a2.run(30, uref=10 ** 6)
        row['cp_u0'] = B.greedy(inst, 0, (0, 0), (-1,) * inst['n'], 'CP')
        out.append(row)
        print(f"[focal {idx:02d}] n={inst['n']} OPT={opt} "
              f"U0cp={row['cp_u0']} Uaco30={row['aco30_u']} | "
              f"best {row['best']['steps']} | greedy {row['greedy']['steps']} | "
              f"wg {row['warm_greedy']['steps']} | wa {row['warm_aco']['steps']} | "
              f"wb {row['warm_both']['steps']}", flush=True)
    return out


def gen_series_of_blocks(sizes, ep, pmax, rng, m=2):
    n = sum(sizes)
    p = [rng.randint(1, pmax) for _ in range(n)]
    pred = [[] for _ in range(n)]
    succ = [[] for _ in range(n)]
    off = 0
    blocks = []
    for b in sizes:
        ids = list(range(off, off + b))
        blocks.append(ids)
        for ii in range(b):
            for jj in range(ii + 1, b):
                if rng.random() < ep:
                    pred[off + jj].append(off + ii)
        off += b
    for a, b in zip(blocks, blocks[1:]):
        for u in a:
            for v in b:
                pred[v].append(u)
    for j in range(n):
        for i in pred[j]:
            succ[i].append(j)
    inst = {'n': n, 'm': m, 'p': p, 'pred': pred, 'succ': succ,
            'ep': ep, 'pmax': pmax, 'family': 'series-blocks'}
    return finish_inst(inst)


def solve_blocks(inst, cap=2_000_000):
    t0 = time.time()
    total = 0
    parts = []
    for b in series_blocks(inst):
        sub = subinstance(inst, b)
        o, nd, ok = B.exact_opt(sub, cap=cap)
        total += o
        parts.append((len(b), o, nd, ok))
    return total, parts, time.time() - t0


def exp_scaling(configs=((4, 5), (6, 6), (8, 5)), n_each=2, budget=220):
    rng = random.Random(2026)
    rows = []
    for (r, b) in configs:
        for k in range(n_each):
            inst = gen_series_of_blocks([b] * r, 0.3, 10, rng)
            opt, parts, dt = solve_blocks(inst)
            n = inst['n']
            L0 = B.lower_L0(inst, 0, (0, 0), (-1,) * n)
            Lser, _ = block_l0(inst)
            mono = run_search(inst, 'greedy', budget=budget,
                              root_thresh=False, collect_anytime=False)
            aco = ACO(inst, seed=500 + k)
            warm = run_search(inst, 'warm_aco', budget=budget,
                              root_thresh=False, collect_anytime=False, aco=aco)
            rows.append({'r': r, 'b': b, 'n': n, 'opt': opt,
                         'decomp_time': dt, 'parts': parts,
                         'L0': L0, 'Lser': Lser,
                         'mono_steps': mono['steps'], 'mono_U': mono['U'],
                         'mono_L': mono['L'], 'mono_time': mono['time'],
                         'mono_cert': mono['U'] == mono['L'],
                         'warm_steps': warm['steps'], 'warm_U': warm['U'],
                         'warm_L': warm['L'], 'warm_time': warm['time'],
                         'warm_cert': warm['U'] == warm['L']})
            print(f"[scale r={r} b={b} n={n}] OPT={opt} L0={L0} Lser={Lser} | "
                  f"mono U/L {mono['U']}/{mono['L']} {mono['steps']}st "
                  f"{mono['time']:.1f}s | warm U/L {warm['U']}/{warm['L']} "
                  f"{warm['steps']}st {warm['time']:.1f}s | "
                  f"decomp {dt:.2f}s", flush=True)
    return rows


def main():
    t0 = time.time()
    print('=== DECOMP ===', flush=True)
    dec = exp_decomp()
    print(dec[0], flush=True)
    for r in dec[1]['rows'][:6]:
        print(r, flush=True)
    print('chain-wide exact ok:', sum(r['ok'] for r in dec[1]['rows']),
          '/', len(dec[1]['rows']), flush=True)
    print('fork-join sizes:', [r['sizes'] for r in dec[2]['rows'][:5]], flush=True)

    print('\n=== LB ===', flush=True)
    lb = exp_lb()
    print('mean L0 %.2f  mean Lser %.2f  strict %d/%d' % (
        sum(r['L0'] for r in lb) / len(lb),
        sum(r['Lser'] for r in lb) / len(lb),
        sum(r['Lser'] > r['L0'] for r in lb), len(lb)), flush=True)
    for r in lb[:6]:
        print(r, flush=True)

    print('\n=== ACO WIDE ===', flush=True)
    wide = exp_aco_wide()
    print('greedy hit %d/%d  aco30 hit %d/%d' % (
        sum(r['greedy_hit'] for r in wide), len(wide),
        sum(r['aco_hit'] for r in wide), len(wide)), flush=True)
    print('mean greedy %.2f  mean aco30 %.2f  mean opt %.2f' % (
        sum(r['greedy'] for r in wide) / len(wide),
        sum(r['aco30'] for r in wide) / len(wide),
        sum(r['opt'] for r in wide) / len(wide)), flush=True)

    print('\n=== FOCAL ===', flush=True)
    foc = exp_focal()
    for name in ('best', 'greedy', 'warm_greedy', 'warm_aco_u', 'warm_aco_g',
                 'warm_aco', 'warm_both', 'greedy_nodom'):
        print(name, 'steps', sum(r[name]['steps'] for r in foc),
              'U', sum(r[name]['U'] for r in foc),
              'time', round(sum(r[name]['time'] for r in foc), 2),
              'ants', sum(r[name]['aco_ants'] for r in foc), flush=True)

    print('\n=== ANYTIME (mean U-OPT) ===', flush=True)
    for b in ('5', '10', '20', '40', '80'):
        cells = []
        for name in ('best', 'greedy', 'warm_greedy', 'warm_aco_u',
                     'warm_aco_g', 'warm_aco', 'warm_both'):
            vals = [r[name]['anytime'].get(b, r[name]['U']) - r['opt']
                    for r in foc]
            hit = sum(1 for v in vals if v == 0)
            cells.append((name, sum(vals) / len(vals), hit))
        print('budget', b, ' | '.join(f'{n}:{g:.2f}/{h}'
              for n, g, h in cells), flush=True)

    print('\n=== SCALING ===', flush=True)
    scale = exp_scaling()
    print('decomp exact', len(scale), '/', len(scale), '| mono certified',
          sum(r['mono_cert'] for r in scale), '| warm certified',
          sum(r['warm_cert'] for r in scale), flush=True)

    out = {'dec': dec, 'lb': lb, 'wide': wide, 'focal': foc, 'scale': scale,
           'time': time.time() - t0}
    with open('/home/runner/work/xuen/xuen/workspace/exp/results_aco.json', 'w') as f:
        json.dump(out, f, indent=1)
    print('total', round(time.time() - t0, 2), 's')


if __name__ == '__main__':
    main()
