"""X-DUB/DA round-1 experiments.

Implements, on small random DAGs for P|prec|Cmax (m=2):
  - exact DFS OPT (independent of search heuristics)
  - v0.5-style X-DUB/AG*  (focal + DOM + inherit + root THRESH)
  - X-DUB/DA             (same + GAP-LEDGER automaton + DERAND-WINDOW + periodic root cert)
  - a THRESH scan benchmark: full scan vs UB-pruned vs UB+best-pruned
  - ledger statistics: binding family / margin vs actual THRESH gain
"""
import random, time, json, sys, math
from collections import defaultdict

BP_COUNT = [0]


# ---------------------------------------------------------------- instances
def gen_instance(n, ep, pmax, rng, m=2):
    p = [rng.randint(1, pmax) for _ in range(n)]
    pred = [[] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < ep:
                pred[j].append(i)
    succ = [[] for _ in range(n)]
    for j in range(n):
        for i in pred[j]:
            succ[i].append(j)
    inst = {'n': n, 'm': m, 'p': p, 'pred': pred, 'succ': succ,
            'ep': ep, 'pmax': pmax}
    compute_desc(inst)
    return inst


def compute_desc(inst):
    n, succ = inst['n'], inst['succ']
    desc = [0] * n
    for i in range(n - 1, -1, -1):
        d = 0
        for j in succ[i]:
            d |= (1 << j) | desc[j]
        desc[i] = d
    inst['desc'] = desc


# ---------------------------------------------------------------- state math
def heads_tails(inst, S, c):
    n, p, pred, succ = inst['n'], inst['p'], inst['pred'], inst['succ']
    est = [0] * n
    for i in range(n):
        if (S >> i) & 1:
            est[i] = c[i]
        else:
            e = 0
            for j in pred[i]:
                if (S >> j) & 1:
                    if c[j] > e:
                        e = c[j]
                else:
                    t = est[j] + p[j]
                    if t > e:
                        e = t
            est[i] = e
    q = [0] * n
    for i in range(n - 1, -1, -1):
        if (S >> i) & 1:
            continue
        b = 0
        for j in succ[i]:
            if not ((S >> j) & 1):
                t = p[j] + q[j]
                if t > b:
                    b = t
        q[i] = b
    return est, q


def lower_L0(inst, S, A, c):
    est, q = heads_tails(inst, S, c)
    n, p, m = inst['n'], inst['p'], inst['m']
    C = max(A)
    rem = 0
    crit = C
    for i in range(n):
        if not ((S >> i) & 1):
            rem += p[i]
            t = est[i] + p[i] + q[i]
            if t > crit:
                crit = t
    return max(C, crit, (rem + m - 1) // m)


def gen_children(inst, S, A, c):
    n, p, pred = inst['n'], inst['p'], inst['pred']
    out = {}
    for i in range(n):
        if (S >> i) & 1:
            continue
        ok = True
        base = 0
        for j in pred[i]:
            if not ((S >> j) & 1):
                ok = False
                break
            if c[j] > base:
                base = c[j]
        if not ok:
            continue
        for k in range(len(A)):
            st = max(A[k], base)
            na = list(A)
            na[k] = st + p[i]
            na = tuple(sorted(na))
            nc = list(c)
            nc[i] = st + p[i]
            out[(S | (1 << i), na, tuple(nc))] = None
    return list(out.keys())


# ---------------------------------------------------------------- packing
def packable(sizes, caps):
    """Exact 2-bin feasibility by bitset subset-sum."""
    BP_COUNT[0] += 1
    if not sizes:
        return True
    c1, c2 = sorted(caps, reverse=True)
    tot = sum(sizes)
    if tot > c1 + c2:
        return False
    bits = 1
    for s in sizes:
        bits |= bits << s
    lo = max(0, tot - c2)
    hi = c1
    if lo > hi:
        return False
    mask = ((1 << (hi + 1)) - 1) ^ ((1 << lo) - 1)
    return (bits & mask) != 0


# ---------------------------------------------------------------- windows
def make_windows(inst, S, A, c, U):
    """Fixed window family for this state; independent of H."""
    n, p = inst['n'], inst['p']
    est, q = heads_tails(inst, S, c)
    R = [i for i in range(n) if not ((S >> i) & 1)]
    if not R:
        return [], est, q
    avals = sorted(set([0] + [est[i] for i in R]))
    bset = set([max(A)])
    for i in R:
        bset.add(est[i] + p[i])
        bset.add((U - 1) - q[i])
    bvals = sorted(b for b in bset if 0 < b <= U - 1)
    wins = set()
    for a in avals:
        if a > U - 1:
            continue
        qmax = None
        for i in R:
            if est[i] >= a:
                if qmax is None or q[i] > qmax:
                    qmax = q[i]
        if qmax is None:
            continue
        for b in bvals:
            if b <= a:
                continue
            ub = min(U - 1, b + qmax)
            wins.add((a, b, ub))
    # descending admissible upper bound; deterministic tie-break
    return sorted(wins, key=lambda w: (-w[2], w[0], w[1])), est, q


def window_infeasible_at(inst, S, A, c, H, a, b, est, q):
    n, p = inst['n'], inst['p']
    caps = [max(0, b - max(a, Ak)) for Ak in A]
    X = []
    for i in range(n):
        if not ((S >> i) & 1) and est[i] >= a and H - q[i] <= b:
            X.append(p[i])
    if not X:
        return False
    return not packable(X, caps)


def infeasible_at(inst, S, A, c, H, est, q, wins):
    for a, b, ub in wins:
        if window_infeasible_at(inst, S, A, c, H, a, b, est, q):
            return True
    return False


def bsearch_window(inst, S, A, c, est, q, a, b, lo, hi):
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if window_infeasible_at(inst, S, A, c, mid, a, b, est, q):
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def thresh(inst, S, A, c, U, L0, mode='full'):
    """mode: full | ub | derand.  Returns (L_TH, n_pack_tests).

    full   : every window, binary search over [L0, U-1]
    ub     : every window, search range capped by b+qmax (but no best bound)
    derand : windows sorted by ub, stop when ub<=best, lower bound best+1
    """
    wins, est, q = make_windows(inst, S, A, c, U)
    BP_COUNT[0] = 0
    if not wins:
        return L0, 0
    best = None
    for (a, b, ub) in wins:
        if mode == 'full':
            lo, hi = L0, U - 1
        elif mode == 'ub':
            lo, hi = L0, min(U - 1, ub)
        else:  # derand
            if best is not None and ub <= best:
                break
            lo = L0 if best is None else max(L0, best + 1)
            hi = min(U - 1, ub)
        if lo > hi:
            continue
        h = bsearch_window(inst, S, A, c, est, q, a, b, lo, hi)
        if h is not None:
            best = h if best is None else max(best, h)
    return (best + 1 if best is not None else L0), BP_COUNT[0]


def point_avail(inst, S, A, c, U):
    """v0.5 single-point AVAIL at H=U-1: returns U if infeasible else L0."""
    L0 = lower_L0(inst, S, A, c)
    wins, est, q = make_windows(inst, S, A, c, U)
    if wins and infeasible_at(inst, S, A, c, U - 1, est, q, wins):
        return U
    return L0


# ---------------------------------------------------------------- greedy
def greedy(inst, S, A, c, rule):
    n, p, pred, desc = inst['n'], inst['p'], inst['pred'], inst['desc']
    S = S
    A = list(A)
    c = list(c)
    while True:
        ready = []
        for i in range(n):
            if (S >> i) & 1:
                continue
            if all((S >> j) & 1 for j in pred[i]):
                ready.append(i)
        if not ready:
            break
        if rule == 'CP':
            _, q = heads_tails(inst, S, tuple(c))
            i = max(ready, key=lambda x: (q[x], -x))
        elif rule == 'LPT':
            i = max(ready, key=lambda x: (p[x], -x))
        else:  # MWKR
            def rw(x):
                s = 0
                d = desc[x]
                for j in range(n):
                    if (d >> j) & 1 and not ((S >> j) & 1):
                        s += p[j]
                return s
            i = max(ready, key=lambda x: (rw(x), -x))
        base = 0
        for j in pred[i]:
            if c[j] > base:
                base = c[j]
        bk = min(range(len(A)), key=lambda k: (max(A[k], base) + p[i], k))
        st = max(A[bk], base)
        A[bk] = st + p[i]
        c[i] = st + p[i]
        S |= 1 << i
    return max(A)


def guide(inst, S, A, c):
    return min(greedy(inst, S, A, c, r) for r in ('CP', 'LPT', 'MWKR'))


# ---------------------------------------------------------------- domination
def dominates(A1, c1, A2, c2, S):
    for x, y in zip(A1, A2):
        if x > y:
            return False
    for i in range(len(c1)):
        if (S >> i) & 1 and c1[i] > c2[i]:
            return False
    return True


# ---------------------------------------------------------------- search
def run(inst, variant='AG', budget=400, omega=2, Bf=32, Kdom=60,
        W_U=20, T_scan=60, delta=1, guide_mode='good', K_cert=4):
    n = inst['n']
    def G(S, A, c):
        vals = [greedy(inst, S, A, c, r) for r in ('CP', 'LPT', 'MWKR')]
        actual = max(vals) if guide_mode == 'worst' else min(vals)
        score = -actual if guide_mode == 'anti' else actual
        return score, actual
    full = (1 << n) - 1
    S0, A0, c0 = 0, (0, 0), (-1,) * n
    U = greedy(inst, S0, A0, c0, 'CP')
    L0 = lower_L0(inst, S0, A0, c0)
    if variant in ('AGt', 'DAt', 'DA'):
        LTH, _ = thresh(inst, S0, A0, c0, U, L0,
                        'full' if variant == 'AGt' else 'derand')
    else:
        LTH = L0
    Lglob = max(L0, LTH)
    F0 = Lglob
    root = {'S': S0, 'A': A0, 'c': c0, 'F': F0,
            'f': max(max(A0), F0), 'id': 0}
    Open = [root]
    nxt = 1
    Dom = {0: [(A0, c0)]}
    steps = 0
    last_imp = 0
    last_progress = 0
    prev_fmin = root['f']
    anytime = {}
    t0 = time.time()
    while Open and steps < budget:
        fmin = min(v['f'] for v in Open)
        if fmin >= U:
            break
        if fmin > prev_fmin:
            prev_fmin = fmin
            last_progress = steps
        if variant in ('DA', 'DAa'):
            mode = 'DIVE' if (steps - last_progress) < W_U and (U - fmin) > delta else 'CLIMB'
        else:
            mode = 'DIVE'
        if mode == 'DIVE':
            phi = [v for v in Open if v['f'] <= fmin + omega]
            phi.sort(key=lambda v: (v['f'], v['id']))
            cand = phi[:Bf]
        else:
            # CLIMB: restrict to the exact f-min layer, but still use the
            # guide to break ties inside it (omega = 0 focal).
            cand = [v for v in Open if v['f'] == fmin]
        bestv = None
        bestg = None
        for v in cand:
            g, act = G(v['S'], v['A'], v['c'])
            if act < U:
                U = act
                last_imp = steps
                last_progress = steps
            if bestv is None or (g, v['f'], v['id']) < (bestg, bestv['f'], bestv['id']):
                bestv, bestg = v, g
        v = bestv
        Open.remove(v)
        steps += 1
        if steps in (5, 10, 20, 40, 80, 160, 320):
            anytime[str(steps)] = U
        if variant == 'DAc' and steps % T_scan == 0 and Open:
            cands = sorted(Open, key=lambda x: (-(U - x['f']), x['id']))[:K_cert]
            for x in cands:
                L0x = lower_L0(inst, x['S'], x['A'], x['c'])
                if L0x >= U:
                    continue
                Lx, _ = thresh(inst, x['S'], x['A'], x['c'], U, L0x, 'derand')
                if Lx > x['F']:
                    x['F'] = Lx
                    x['f'] = max(max(x['A']), Lx)
            Open = [x for x in Open if x['f'] < U]
        if variant == 'DA' and steps % T_scan == 0:
            newL, _ = thresh(inst, 0, (0, 0), (-1,) * n, U, L0, 'derand')
            if newL > Lglob:
                Lglob = newL
                for x in Open:
                    x['F'] = max(x['F'], Lglob)
                    x['f'] = max(max(x['A']), x['F'])
                Open = [x for x in Open if x['f'] < U]
        for (cs, ca, cc) in gen_children(inst, v['S'], v['A'], v['c']):
            if cs == full:
                if max(ca) < U:
                    U = max(ca)
                    last_imp = steps
                    last_progress = steps
                continue
            l0 = lower_L0(inst, cs, ca, cc)
            if l0 >= U:
                continue
            wins, est, q = make_windows(inst, cs, ca, cc, U)
            if wins and infeasible_at(inst, cs, ca, cc, U - 1, est, q, wins):
                continue
            g, act = G(cs, ca, cc)
            if act < U:
                U = act
                last_imp = steps
                last_progress = steps
            Fw = max(v['F'], l0)
            fw = max(max(ca), Fw)
            if fw >= U:
                continue
            bucket = Dom.setdefault(cs, [])
            if any(dominates(A2, c2, ca, cc, cs) for (A2, c2) in bucket):
                continue
            bucket[:] = [(A2, c2) for (A2, c2) in bucket
                         if not dominates(ca, cc, A2, c2, cs)]
            if len(bucket) < Kdom:
                bucket.append((ca, cc))
            Open.append({'S': cs, 'A': ca, 'c': cc, 'F': Fw,
                         'f': fw, 'id': nxt})
            nxt += 1
    L = max(Lglob, min((x['f'] for x in Open), default=Lglob))
    return {'steps': steps, 'U': U, 'L': L, 'anytime': anytime,
            'time': time.time() - t0, 'open': len(Open),
            'L0': L0, 'LTH': LTH}


# ---------------------------------------------------------------- exact OPT
def exact_opt(inst, cap=2_000_000):
    n = inst['n']
    full = (1 << n) - 1
    ub = greedy(inst, 0, (0, 0), (-1,) * n, 'CP')
    best = [ub]
    nodes = [0]
    sys.setrecursionlimit(10000)

    def dfs(S, A, c):
        nodes[0] += 1
        if nodes[0] > cap:
            raise RuntimeError('cap')
        C = max(A)
        if S == full:
            if C < best[0]:
                best[0] = C
            return
        if max(C, lower_L0(inst, S, A, c)) >= best[0]:
            return
        for (cs, ca, cc) in gen_children(inst, S, A, c):
            if max(ca) >= best[0]:
                continue
            dfs(cs, ca, cc)

    try:
        dfs(0, (0, 0), (-1,) * n)
        return best[0], nodes[0], True
    except RuntimeError:
        return best[0], nodes[0], False


# ---------------------------------------------------------------- ledger / THRESH bench
def random_prefix(inst, rng, frac):
    n, p, pred = inst['n'], inst['p'], inst['pred']
    S, A, c = 0, [0, 0], [-1] * n
    target = max(1, int(n * frac))
    done = 0
    while done < target:
        ready = [i for i in range(n)
                 if not ((S >> i) & 1) and all((S >> j) & 1 for j in pred[i])]
        if not ready:
            break
        i = rng.choice(ready)
        base = max([c[j] for j in pred[i]] + [0])
        k = rng.randrange(2)
        st = max(A[k], base)
        A[k] = st + p[i]
        c[i] = st + p[i]
        S |= 1 << i
        done += 1
    return S, tuple(sorted(A)), tuple(c)


def thresh_bench(insts, rng, n_states=24):
    rows = []
    for inst in insts:
        for _ in range(2):
            S, A, c = random_prefix(inst, rng, rng.choice([0.4, 0.55, 0.7]))
            U = guide(inst, S, A, c)
            L0 = lower_L0(inst, S, A, c)
            if L0 >= U:
                continue
            full, nf = thresh(inst, S, A, c, U, L0, 'full')
            ub, nu = thresh(inst, S, A, c, U, L0, 'ub')
            dr, nd = thresh(inst, S, A, c, U, L0, 'derand')
            wins, _, _ = make_windows(inst, S, A, c, U)
            headroom = (max(w[2] for w in wins) + 1 - L0) if wins else 0
            rows.append({'L0': L0, 'U': U, 'full': full, 'ub': ub, 'der': dr,
                         'nf': nf, 'nu': nu, 'nd': nd, 'headroom': headroom,
                         'gain': full - L0})
    return rows


# ---------------------------------------------------------------- main
def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 12345
    rng = random.Random(seed)
    t_start = time.time()

    # ---------------- candidate pool: keep the harder ones
    cand = []
    for _ in range(60):
        n = rng.choice([9, 10, 11])
        inst = gen_instance(n, rng.choice([0.15, 0.2, 0.25, 0.3]),
                            rng.choice([8, 10, 12, 15]), rng)
        r = run(inst, 'AG', budget=120)
        cand.append((r['steps'], inst))
    cand.sort(key=lambda x: -x[0])
    hard = [inst for (st, inst) in cand[:12]]
    print('[pool] hardest steps:', [st for (st, _) in cand[:12]], flush=True)

    # ---------------- search comparison
    out = []
    for idx, inst in enumerate(hard):
        t0 = time.time()
        opt, ok = None, None
        if inst['n'] <= 9:
            try:
                opt, nodes, ok = exact_opt(inst, cap=900_000)
            except Exception:
                opt, ok = None, False
        ag = run(inst, 'AG', budget=500)
        daa = run(inst, 'DAa', budget=500)
        agb = run(inst, 'AG', budget=500, guide_mode='bad')
        dab = run(inst, 'DAa', budget=500, guide_mode='bad')
        if opt is None:
            opt = ag['U']
            ok = None
        out.append({'idx': idx, 'n': inst['n'], 'ep': inst['ep'],
                    'pmax': inst['pmax'],
                    'edges': sum(len(x) for x in inst['pred']),
                    'opt': opt, 'exact_ok': ok,
                    'AG': ag, 'DAa': daa, 'AGbad': agb, 'DAbad': dab})
        print(f'[{idx:02d}] n={inst["n"]} e={sum(len(x) for x in inst["pred"])} '
              f'OPT={opt} ok={ok} | AG {ag["steps"]} | DAa {daa["steps"]} '
              f'| AGbad {agb["steps"]}/{agb["U"]} | DAbad {dab["steps"]}/{dab["U"]} '
              f'| {time.time()-t0:.2f}s', flush=True)

    # ---------------- THRESH bench + ledger features
    bench = thresh_bench(hard, rng, 24)
    for row in bench:
        inst = None
    print('\n=== SEARCH COMPARISON ===', flush=True)
    n = len(out)
    print('AG steps:', sum(o['AG']['steps'] for o in out),
          'DAa steps:', sum(o['DAa']['steps'] for o in out))
    print('good guide: DAa<AG', sum(o['DAa']['steps'] < o['AG']['steps'] for o in out),
          'ties', sum(o['DAa']['steps'] == o['AG']['steps'] for o in out),
          'losses', sum(o['DAa']['steps'] > o['AG']['steps'] for o in out))
    print('bad guide : DAbad<AGbad',
          sum(o['DAbad']['steps'] < o['AGbad']['steps'] for o in out),
          'ties', sum(o['DAbad']['steps'] == o['AGbad']['steps'] for o in out),
          'losses', sum(o['DAbad']['steps'] > o['AGbad']['steps'] for o in out))
    print('bad-guide U sums: AGbad', sum(o['AGbad']['U'] for o in out),
          'DAbad', sum(o['DAbad']['U'] for o in out),
          'OPT', sum(o['opt'] for o in out))

    print('\n=== ANYTIME gap (U-OPT) ===')
    for b in ('5', '10', '20', '40', '80'):
        agv = [o['AG']['anytime'].get(b, o['AG']['U']) - o['opt'] for o in out]
        dav = [o['DAa']['anytime'].get(b, o['DAa']['U']) - o['opt'] for o in out]
        print(f'budget {b:>3}: AG={sum(agv)/n:.2f}  DAa={sum(dav)/n:.2f}')

    print('\n=== THRESH BENCH ===')
    if bench:
        m = len(bench)
        print('states:', m)
        print('mean L0 %.3f  full %.3f  ub %.3f  derand %.3f' % (
            sum(r['L0'] for r in bench) / m, sum(r['full'] for r in bench) / m,
            sum(r['ub'] for r in bench) / m, sum(r['der'] for r in bench) / m))
        print('full==derand', sum(r['full'] == r['der'] for r in bench), '/', m,
              ' full==ub', sum(r['full'] == r['ub'] for r in bench), '/', m)
        print('mean BP tests: full %.2f  ub %.2f  derand %.2f' % (
            sum(r['nf'] for r in bench) / m, sum(r['nu'] for r in bench) / m,
            sum(r['nd'] for r in bench) / m))
        print('gain>0', sum(r['gain'] > 0 for r in bench), '/', m,
              ' mean gain %.3f' % (sum(r['gain'] for r in bench) / m))
        pos = [r for r in bench if r['gain'] > 0]
        if pos:
            print('mean BP on gain>0: full %.2f derand %.2f' % (
                sum(r['nf'] for r in pos) / len(pos),
                sum(r['nd'] for r in pos) / len(pos)))

    summary = {'seed': seed, 'instances': out, 'bench': bench,
               'total_time': time.time() - t_start}
    with open('/home/runner/work/xuen/xuen/workspace/exp/results.json', 'w') as f:
        json.dump(summary, f, indent=1)
    print('\ntotal wall:', round(time.time() - t_start, 2), 's')


if __name__ == '__main__':
    main()
