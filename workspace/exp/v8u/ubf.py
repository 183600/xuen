"""v9.3 UBF-ICF: upper-bound-first repair with an ICF bracket.

The outer state is

    (L, U, s, m, pi, Omega)

where (L,U,s,m,pi) is the v9.0 ICF state and Omega is a *repair archive*:
a sequence of primal attempts at horizons U-1.  An attempt either returns a
schedule (upper-bound witness), a complete backtracking tree with no schedule
(a local NO proof), or an open frontier (budget exhausted).  The archive is
explanatory, not part of the final soundness argument; soundness still comes
from pi, the checked schedule, and the closing PACT probe.

The new move is primal-first: before spending a lower-bound probe, spend a
cheap randomized-restart backtracking budget trying to lower U.  If U reaches
the true optimum, one probe at U-1 closes the bracket, instead of a sequence
of probes from L upward.
"""
import sys
import time
import random

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from po import heads_tails
from rdf import check_schedule
from icf import cmax, run_icf
from pact import PACT, pact_decide


def _prep(inst):
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    return est, q


def _schedule(inst, order):
    """Earliest-start serial schedule generation for one priority order."""
    n = inst['n']
    m = inst['m']
    p = inst['p']
    elig = inst['elig']
    pred = inst['pred']
    starts = [0] * n
    machine = [-1] * n
    busy = [[] for _ in range(m)]
    for i in order:
        base = 0
        for j in pred[i]:
            v = starts[j] + p[j]
            if v > base:
                base = v
        best = None
        for k in elig[i]:
            t = base
            pi = p[i]
            for a, b in busy[k]:
                if t + pi <= a:
                    break
                if t < b:
                    t = b
            cand = (t + pi, t, k)
            if best is None or cand < best:
                best = cand
        ft, t, k = best
        starts[i] = t
        machine[i] = k
        busy[k].append((t, ft))
        busy[k].sort()
    return starts, machine, max(starts[i] + p[i] for i in range(n))


def _topo_random(inst, rng, mode, est, q):
    n = inst['n']
    p = inst['p']
    succ = inst['succ']
    indeg = [len(inst['pred'][i]) for i in range(n)]
    ready = [i for i in range(n) if indeg[i] == 0]
    out = []
    while ready:
        if mode == 0:
            ready.sort(key=lambda i: (-(q[i] + rng.random() * 5.0), i))
        elif mode == 1:
            ready.sort(key=lambda i: (-(q[i] + 0.5 * p[i] +
                                        rng.random() * 8.0), i))
        elif mode == 2:
            ready.sort(key=lambda i: (rng.random(), i))
        else:
            ready.sort(key=lambda i: (est[i] - 0.3 * q[i] +
                                      rng.random() * 6.0, i))
        pick = 0 if (len(ready) == 1 or rng.random() < 0.7) else 1
        i = ready.pop(pick)
        out.append(i)
        for j in succ[i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                ready.append(j)
    return out



def _prep_graph(inst):
    n = inst['n']
    p = inst['p']
    pred = inst['pred']
    succ = inst['succ']
    indeg = [len(pred[i]) for i in range(n)]
    ready = [i for i in range(n) if indeg[i] == 0]
    topo = []
    while ready:
        i = ready.pop()
        topo.append(i)
        for j in succ[i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                ready.append(j)
    est = [0] * n
    for i in topo:
        est[i] = max([0] + [est[j] + p[j] for j in pred[i]])
    tail = [0] * n
    for i in reversed(topo):
        tail[i] = max([0] + [p[j] + tail[j] for j in succ[i]])
    pm = [0] * n
    for i in range(n):
        for j in pred[i]:
            pm[i] |= 1 << j
    return est, tail, pm


def limited_discrepancy_repair(inst, U, starts0, machine0, target=None,
                               max_disc=4, node_budget=3000,
                               time_cap=0.15, seed=0):
    """Depth-first limited-discrepancy search over SGS decisions.

    The first child at each node is the greedy choice; any other child costs
    one discrepancy.  A path with <=d discrepancies is explored in pass d.
    This is a genuine chronological backtracking search; the budget makes it
    a partial (witness-producing) search, never a NO proof.
    """
    n = inst['n']
    m = inst['m']
    p = inst['p']
    elig = inst['elig']
    succ = inst['succ']
    est, tail, pm = _prep_graph(inst)
    rng = random.Random(seed)
    best = int(U)
    bs = list(starts0)
    bm = list(machine0)
    total_nodes = 0
    total_t = 0.0
    for disc_lim in range(max_disc + 1):
        if best <= 1 or (target is not None and best <= target):
            break
        starts = [-1] * n
        machine = [-1] * n
        occ = [0] * m
        pred_ready = [0] * n
        nodes = [0]
        t0 = time.time()

        def lower(unsched):
            mx = 0
            for i in range(n):
                if not ((unsched >> i) & 1):
                    continue
                v = max(est[i], pred_ready[i]) + p[i] + tail[i]
                if v > mx:
                    mx = v
            return mx

        def rec(unsched, cmax, disc):
            nodes[0] += 1
            if nodes[0] > node_budget or time.time() - t0 > time_cap:
                return None
            if unsched == 0:
                return (list(starts), list(machine))
            if lower(unsched) > best - 1:
                return None
            sched = ((1 << n) - 1) ^ unsched
            alts = []
            for i in range(n):
                if ((unsched >> i) & 1) and (pm[i] & sched) == pm[i]:
                    hr = max(est[i], pred_ready[i])
                    key = (-(tail[i] + p[i]) + rng.random() * 0.01, hr, i)
                    alts.append((key, i, hr))
            alts.sort()
            for ai, (_, i, hr) in enumerate(alts):
                ms = []
                for k in elig[i]:
                    t = hr
                    while t + p[i] <= best - 1:
                        if (occ[k] >> t) & ((1 << p[i]) - 1) == 0:
                            break
                        t += 1
                    if t + p[i] <= best - 1:
                        ms.append((t + p[i], t, k))
                ms.sort()
                for mi, (ft, t, k) in enumerate(ms):
                    nd = disc + (1 if ai > 0 else 0) + (1 if mi > 0 else 0)
                    if nd > disc_lim:
                        continue
                    starts[i] = t
                    machine[i] = k
                    occ[k] |= ((1 << p[i]) - 1) << t
                    old = [pred_ready[j] for j in succ[i]]
                    for j in succ[i]:
                        if pred_ready[j] < ft:
                            pred_ready[j] = ft
                    r = rec(unsched & ~(1 << i), max(cmax, ft), nd)
                    if r is not None:
                        return r
                    for j, o in zip(succ[i], old):
                        pred_ready[j] = o
                    occ[k] &= ~(((1 << p[i]) - 1) << t)
                    starts[i] = -1
                    machine[i] = -1
            return None

        r = rec((1 << n) - 1, 0, 0)
        total_nodes += nodes[0]
        total_t += time.time() - t0
        if r is not None:
            s2, m2 = r
            c2 = max(s2[i] + p[i] for i in range(n))
            if c2 < best and check_schedule(inst, c2, s2, m2):
                best = c2
                bs, bm = s2, m2
    return dict(U=best, schedule=bs, machine=bm, nodes=total_nodes,
                t=round(total_t, 4))


def randomized_repair(inst, U, starts0, machine0, iters=400,
                      seed=0, target=None, time_cap=1.0, stall=120):
    """Randomized-restart backtracking rollouts at h=U-1.

    Each rollout is a depth-first root-to-leaf path in the SGS tree; restarts
    backtrack to the root with a fresh randomized value ordering.  This is the
    budgeted version of the full backtracking repair.  If target is reached we
    stop early; if no improvement is found for `stall` rollouts we stop.
    """
    n = inst['n']
    p = inst['p']
    est, q = _prep(inst)
    rng = random.Random(seed)
    best = int(U)
    bs = list(starts0)
    bm = list(machine0)
    t0 = time.time()
    last = 0
    it = 0
    improved = 0
    for it in range(1, iters + 1):
        if best <= 1:
            break
        if target is not None and best <= target:
            break
        if time.time() - t0 > time_cap:
            break
        if it - last > stall:
            break
        order = _topo_random(inst, rng, (it - 1) % 4, est, q)
        s, m, c = _schedule(inst, order)
        if c < best and check_schedule(inst, c, s, m):
            best = c
            bs, bm = s, m
            last = it
            improved += 1
    return dict(U=best, schedule=bs, machine=bm, iters=it,
                improved=improved, t=round(time.time() - t0, 4))


def run_ubf(inst, known, name, idx, repair_iters=400, repair_time=1.0,
            repair_stall=120, seed=0, policy='lower-first', initial=None,
            max_probes=64, use_pact_init=True):
    """Primal-first bracket: repair U, then run the v9.0 ICF closure."""
    t0 = time.time()
    if initial is None:
        co = PACT(inst, pact_mode='complete', use_ga=False)
        lb, ub, s, m = co.initial_bounds()
        if ub is None:
            return dict(name=name, idx=idx, known=known, alg='ubf',
                        ok=False, error='no-initial-ub', t=0.0)
        L, U = int(lb), int(ub)
        proof = co._ensure_lb_proof(L)
        if proof is None:
            r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
            if r['verdict'] is False:
                proof = r['proof']
        if proof is None:
            return dict(name=name, idx=idx, known=known, alg='ubf',
                        ok=False, error='no-lb-proof', t=0.0)
    else:
        L, U, s, m, proof = initial
        L, U = int(L), int(U)
    ub0 = U
    rep = dict(U=U, iters=0, improved=0, t=0.0)
    close_policy = policy
    if policy == 'hybrid':
        if U - L <= 1:
            close_policy = 'lower-first'
        else:
            close_policy = 'upper-first'
    if U - L > 1:
        rep = randomized_repair(inst, U, s, m, iters=repair_iters,
                                seed=seed, target=L,
                                time_cap=repair_time,
                                stall=repair_stall)
        if rep['U'] < U and check_schedule(inst, rep['U'],
                                            rep['schedule'],
                                            rep['machine']):
            U = rep['U']
            s, m = rep['schedule'], rep['machine']
    row = run_icf(inst, known, name, idx, policy=close_policy,
                  max_probes=max_probes, use_pact_init=use_pact_init,
                  initial=(L, U, s, m, proof))
    if initial is None:
        row['pin_lp'] = getattr(co, 'pin_lp', 0)
    row['ub0'] = ub0
    row['ub_after_repair'] = U
    row['repair_iters'] = rep['iters']
    row['repair_improved'] = rep['improved']
    row['repair_t'] = rep['t']
    row['t'] = round(time.time() - t0, 4)
    row['total_lp'] = (row.get('pact_lp', 0) +
                       row.get('pact_cert_lp', 0) +
                       row.get('pin_lp', 0))
    row['alg'] = 'ubf'
    row['close_policy'] = close_policy
    return row
