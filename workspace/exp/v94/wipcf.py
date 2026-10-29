"""v9.4 WIPCF: Window-Indexed Partial-Correctness Frontier.

WIPCF keeps the v9.3 PD-ICF state

    C = (L, U, s, m, pi),  pi : NO(L-1), Cmax(s)=U, L<=U

and inserts a *certified window prescan* before the exact fixed-h oracle.
The prescan is a partial-correctness object: every domain reduction is a
local, replayable lemma; if it stops early the bracket is unchanged; if
it empties a domain it emits a replayable NO(h) proof and raises L
without calling pact_decide.

The spatial index is a set of time windows [a,b) with a capacity bound
cap(M)(b-a).  For each task i and window q the index stores

    theta_iq = mandatory overlap of i's current hull with q,
    slack_iq = sum_j theta_jq - theta_iq - cap_q (b_q-a_q).

A start t is removed when some window has

    slack_iq + overlap(t, p_i, a_q, b_q) > 0.

The naive scan is O(|D_i| * |W|) per task.  The optional WindowIndex
first builds, for each task, an interval upper bound on the violation
score and only scans windows that can actually violate.  The filter is
conservative (it never removes a sound start), so the certificate replay
is unchanged.
"""
import sys
import time
import math
import random
import heapq
import collections

sys.path[:0] = ['exp/v94', 'exp/v93', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from icf import PartialCertificate, ICFCertificate, cmax, corpora
from pact import PACT, pact_decide
from lpr import (sgs, topo_order, marginals, quantile, _pin_weak,
                 _guide_at)
from pdicf import decode_orders, decode_random, cfa_orders
from po import heads_tails
from rdf import check_schedule
from cert import verify
from ehc2 import (propagate, EhcProof, initial_domains, _machine_subsets,
                  _endpoints, hull_min_overlap, overlap, _replay)


# ------------------------------------------------------ domain decoder
def sgs_dom(inst, order, H, D):
    """Serial SGS restricted to the certified start domains D.

    D_i is a superset of the starts used by any feasible schedule at H
    (the reduction events are sound), so restricting the search to D
    loses no feasible schedule.  The function is still only a heuristic
    decoder; the result must pass check_schedule.
    """
    n, m, p = inst['n'], inst['m'], inst['p']
    elig, pred = inst['elig'], inst['pred']
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
        for t in sorted(D[i]):
            if t < base or t + p[i] > H:
                continue
            for k in elig[i]:
                ok = True
                for a, b in busy[k]:
                    if t + p[i] <= a:
                        break
                    if t < b:
                        ok = False
                        break
                if not ok:
                    continue
                cand = (t + p[i], t, k)
                if best is None or cand < best:
                    best = cand
        if best is None:
            return None
        ft, t, k = best
        starts[i] = t
        machine[i] = k
        busy[k].append((t, ft))
        busy[k].sort()
    c = max(starts[i] + p[i] for i in range(n))
    return starts, machine, c


def decode_dom(inst, ps, res, H, D, restarts=50, seed=0,
               time_cap=0.08):
    """Deterministic + randomized LP-marginal orders, decoded by sgs_dom."""
    if res is None or getattr(res, 'x', None) is None:
        return dict(hit=False, cmax=None, schedule=None, machine=None,
                    work=0, kind='no-guide')
    mrg = marginals(inst, ps, res)
    mean = [m for m, _ in mrg]
    est, tail = heads_tails(inst, 0, [0] * inst['n'])
    keys = []
    for q in (0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98):
        keys.append(('dom-q%g' % q,
                     lambda i, q=q: (quantile(mrg[i][1], q) + i * 1e-6)))
    keys.append(('dom-mean', lambda i: (mean[i] + i * 1e-6)))
    keys.append(('dom-latest',
                 lambda i: (-(H - tail[i] - inst['p'][i]) + i * 1e-6)))
    keys.append(('dom-tail', lambda i: (-tail[i] + i * 1e-6)))
    keys.extend([(('dom-' + tag), key)
                 for tag, key in cfa_orders(inst, mean, tail, H)])
    work = 0
    best = None
    for tag, key in keys:
        order = topo_order(inst, key)
        if order is None:
            continue
        work += 1
        r = sgs_dom(inst, order, H, D)
        if r is None:
            continue
        s, m, c = r
        if c <= H and check_schedule(inst, c, s, m):
            return dict(hit=True, cmax=c, schedule=s, machine=m,
                        work=work, kind=tag)
        if best is None or c < best[0]:
            best = (c, s, m)
    rng = random.Random(seed)
    t0 = time.time()
    for it in range(restarts):
        if time.time() - t0 > time_cap:
            break
        mode = it % 4
        if mode == 0:
            q = rng.choice([0.05, 0.1, 0.2, 0.3, 0.4, 0.5,
                            0.6, 0.7, 0.8, 0.9])
            key = lambda i, q=q: (quantile(mrg[i][1], q) +
                                  rng.random() * 0.5)
        elif mode == 1:
            key = lambda i: (mrg[i][0] + rng.random() * H * 0.15)
        elif mode == 2:
            key = lambda i: (quantile(mrg[i][1], rng.random()) +
                             rng.random() * 0.1)
        else:
            key = lambda i: (-tail[i] + rng.random() * 3.0)
        order = topo_order(inst, key)
        if order is None:
            continue
        work += 1
        r = sgs_dom(inst, order, H, D)
        if r is None:
            continue
        s, m, c = r
        if c <= H and check_schedule(inst, c, s, m):
            return dict(hit=True, cmax=c, schedule=s, machine=m,
                        work=work, kind='dom-rand')
        if best is None or c < best[0]:
            best = (c, s, m)
    return dict(hit=False, cmax=(best[0] if best else None),
                schedule=(best[1] if best else None),
                machine=(best[2] if best else None),
                work=work, kind='dom-miss')


# ------------------------------------------------------- window prescan
def window_prescan(inst, h, max_iters=8, max_energy_checks=None,
                   use_index=False):
    """Run hull-energetic reduction and return a three-valued result.

    Returns dict(status, D, proof, info).  status:
      'no'     a replayable NO(h) proof was produced;
      'open'   the reduction is sound but did not empty a domain;
      'fail'   a reduction emptied a domain but its replay failed.
    Only 'no' with a verified proof may change L.
    """
    t0 = time.time()
    if use_index:
        D, info = propagate_indexed(inst, h, max_iters=max_iters,
                                    max_energy_checks=max_energy_checks)
    else:
        D, info = propagate(inst, h, use_energy=True, energy_mode='all',
                            max_iters=max_iters,
                            max_energy_checks=max_energy_checks)
    info['t'] = round(time.time() - t0, 5)
    if D is None:
        proof = EhcProof(inst, h, info.get('events', []),
                         info.get('initial_empty'))
        if proof.audit_rdf():
            return dict(status='no', D=None, proof=proof, info=info)
        return dict(status='fail', D=None, proof=None, info=info)
    return dict(status='open', D=D, proof=None, info=info)




# --------------------------------------------------- indexed propagation
def propagate_indexed(inst, h, use_prec=True, max_energy_checks=None,
                      max_iters=None, energy_mode='all'):
    """Hull-energetic propagation with a window interval index.

    The naive energy loop scans every window q for every candidate start
    t.  Here, for each task i, a window q is first bounded by

        ub_q = (tot_q - theta_iq - cap_q (b_q-a_q))
               + min(p_i, b_q-a_q),

    which is an upper bound on the violation score of any t.  Windows
    with ub_q <= 0 cannot remove any start and are discarded.  The
    remaining windows are inserted into an interval index over their
    possible start range [max(0,a-p_i+1), b-1]; a sweep with a max-heap
    gives ub(t), the largest bound among windows that can contain t.
    Only t with ub(t) > 0 are scanned.  The filter is conservative: it
    never skips a window that could violate, so the replay certificate is
    unchanged.
    """
    t0 = time.time()
    n, m, p = inst['n'], inst['m'], inst['p']
    D = initial_domains(inst, h)
    if D is None:
        est, q = heads_tails(inst, 0, [0] * n)
        i = next(i for i in range(n)
                 if est[i] > h - q[i] - p[i])
        return None, dict(empty=True, initial_empty=i, events=[],
                          iters=0, energy_checks=0, budget_hit=False,
                          skipped=0, scanned=0, t=time.time() - t0)
    subsets = _machine_subsets(inst, energy_mode)
    events = []
    it = 0
    checks = 0
    skipped = 0
    scanned = 0
    budget_hit = False

    def no(reason):
        return None, dict(empty=True, reason=reason, events=events,
                          iters=it, energy_checks=checks,
                          budget_hit=budget_hit, skipped=skipped,
                          scanned=scanned, t=time.time() - t0)

    while True:
        it += 1
        changed = 0
        if use_prec:
            for i in range(n):
                if not D[i]:
                    return no(('prec', i))
                for j in inst['succ'][i]:
                    if not D[j]:
                        return no(('prec', j))
                    lo = min(D[i]) + p[i]
                    if lo > max(D[j]):
                        events.append(('x', i, j, 'succ'))
                        return no(('prec', i, j))
                    rem = [t for t in D[j] if t < lo]
                    if rem:
                        D[j].difference_update(rem)
                        for t in rem:
                            events.append(('p', j, t, i))
                        changed += len(rem)
                    hi = max(D[j]) - p[i]
                    if min(D[i]) > hi:
                        events.append(('x', i, j, 'pred'))
                        return no(('prec', i, j))
                    rem = [t for t in D[i] if t > hi]
                    if rem:
                        D[i].difference_update(rem)
                        for t in rem:
                            events.append(('p', i, t, j))
                        changed += len(rem)
                    if not D[i] or not D[j]:
                        events.append(('z', i if not D[i] else j))
                        return no(('prec', i, j))
        if not budget_hit:
            for mask, cap, J in subsets:
                E = _endpoints(D, p, h, J)
                ints = [(E[u], E[v]) for u in range(len(E))
                        for v in range(u + 1, len(E))]
                theta = {}
                for j in J:
                    d = D[j]
                    if not d:
                        events.append(('z', j))
                        return no(('prec', j))
                    r = min(d)
                    u = max(d)
                    pj = p[j]
                    theta[j] = [hull_min_overlap(r, u, pj, a, b)
                                for a, b in ints]
                tot = [0] * len(ints)
                for j in J:
                    tj = theta[j]
                    for q in range(len(ints)):
                        tot[q] += tj[q]
                for i in J:
                    ti = theta[i]
                    pi = p[i]
                    active = []
                    for q, (a, b) in enumerate(ints):
                        capq = cap * (b - a)
                        base = tot[q] - ti[q] - capq
                        mx = min(pi, b - a)
                        if base + mx <= 0:
                            continue
                        if base > 0:
                            # the window is overloaded even with zero
                            # overlap from i; it can shave every start.
                            l, r = 0, h
                        else:
                            l = max(0, a - pi + 1)
                            r = b - 1
                        if l > r:
                            continue
                        active.append((l, r, base + mx, q))
                    active.sort()
                    hp = []
                    ai = 0
                    for t in sorted(D[i]):
                        if max_energy_checks is not None \
                                and checks >= max_energy_checks:
                            budget_hit = True
                            break
                        while ai < len(active) and active[ai][0] <= t:
                            l, r, ub, q = active[ai]
                            heapq.heappush(hp, (-ub, r, q))
                            ai += 1
                        while hp and hp[0][1] < t:
                            heapq.heappop(hp)
                        if not hp or -hp[0][0] <= 0:
                            skipped += 1
                            continue
                        hit = None
                        for l, r, ub, q in active:
                            if l <= t <= r:
                                checks += 1
                                scanned += 1
                                a, b = ints[q]
                                total = (tot[q] - ti[q]
                                         + overlap(t, pi, a, b))
                                if total > cap * (b - a):
                                    hit = (a, b)
                                    break
                        if hit is not None:
                            D[i].discard(t)
                            events.append(('e', i, t, mask,
                                           hit[0], hit[1]))
                            changed += 1
                        if not D[i]:
                            events.append(('z', i))
                            return no(('energy', i, t))
                    if budget_hit:
                        break
                if budget_hit:
                    break
        if not changed:
            break
        if max_iters is not None and it >= max_iters:
            break
        if it > n * (h + 1) + 8:
            break
    return D, dict(empty=False, events=events, iters=it,
                   sizes=[len(d) for d in D], energy_checks=checks,
                   budget_hit=budget_hit, skipped=skipped,
                   scanned=scanned, t=time.time() - t0)


# ------------------------------------------------------------ algorithm
def run_wipcf(inst, known, name, idx, initial=None, mode='pd',
              use_cfa=True, restarts=50, time_cap=0.08,
              max_probes=64, seed=0, prescan=True, prescan_index=True,
              prescan_iters=8, prescan_checks=None,
              prescan_gap=64, dom_decode=False, dom_restarts=50):
    """Run WIPCF on one instance.

    mode is kept for comparison with PD-ICF:
      'anchor'  no prescan / no rounding, exact probes only
      'round'   no prescan, PD-ICF rounding + probes
      'pd'      prescan + PD-ICF rounding + probes
    """
    t0 = time.time()
    if initial is None:
        co = PACT(inst, pact_mode='complete', use_ga=False)
        L, U, s, m = co.initial_bounds()
        L, U = int(L), int(U)
        s, m = list(s), list(m)
        proof = co._ensure_lb_proof(L)
        if proof is None:
            r0 = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
            if r0['verdict'] is False:
                proof = r0['proof']
        pin_lp = getattr(co, 'pin_lp', 0)
    else:
        L0, U0, s0, m0, proof0 = initial
        co, L, U, s, m, proof, pin_lp = _pin_weak(
            inst, L0, U0, s0, m0, proof0)
    if proof is None:
        return dict(name=name, idx=idx, known=known, mode=mode,
                    ok=False, error='no-lb-proof', t=0.0)
    L0, U0 = int(L), int(U)
    ps = None
    guide = None
    if mode in ('round', 'pd') and L < U:
        ps, guide, extra = _guide_at(co, L)
        pin_lp += extra
        if ps is None or guide is None or getattr(guide, 'x', None) is None:
            from lbp import ParametricSD
            ps = ParametricSD(inst, int(U))
            guide = ps.solve_h(L)
            pin_lp += 1

    probes = 0
    search_lp = 0
    cert_lp = 0
    round_work = 0
    round_hits = 0
    cfa_hits = 0
    dom_hits = 0
    prescan_no = 0
    prescan_open = 0
    prescan_fail = 0
    prescan_work = 0
    prescan_time = 0.0
    partial_ok = 0
    partial_fail = 0
    steps = []
    defect_after_round = U - L

    def audit():
        nonlocal partial_ok, partial_fail
        pc = PartialCertificate(inst, L, U, s, m, proof, probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1

    def use_sched(c, s2, m2):
        nonlocal U, s, m
        if c < U and check_schedule(inst, c, s2, m2):
            U = c
            s, m = list(s2), list(m2)
            return True
        return False

    def try_round(target, do_random=True):
        nonlocal round_work, round_hits, cfa_hits, search_lp
        if ps is None or target >= U:
            return None
        res = guide
        if res is None or getattr(res, 'x', None) is None:
            res = ps.solve_h(target)
            search_lp += 1
        r = decode_orders(inst, ps, res, target, use_cfa=use_cfa)
        round_work += r['work']
        if r['hit']:
            round_hits += 1
            if r['kind'].startswith('cfa:'):
                cfa_hits += 1
            return r
        if do_random and restarts > 0:
            r2 = decode_random(inst, ps, res, target, restarts=restarts,
                               seed=seed, time_cap=time_cap)
            round_work += r2['work']
            if r2['hit']:
                round_hits += 1
                return r2
        return None

    def try_dom(target, D):
        nonlocal round_work, dom_hits, search_lp
        if ps is None or D is None or target >= U:
            return None
        res = guide
        if res is None or getattr(res, 'x', None) is None:
            res = ps.solve_h(target)
            search_lp += 1
        r = decode_dom(inst, ps, res, target, D, restarts=dom_restarts,
                       seed=seed)
        round_work += r['work']
        if r['hit']:
            dom_hits += 1
            return r
        return None

    audit()
    if mode in ('round', 'pd') and L < U:
        r = try_round(L)
        if r is not None:
            use_sched(r['cmax'], r['schedule'], r['machine'])
            steps.append(('ROUND', L, r['cmax'], r['kind']))
            audit()
        defect_after_round = U - L

    first = True
    while L < U and probes < max_probes:
        # ---- certified window prescan at the current L
        if mode == 'pd' and prescan and (U - L) <= prescan_gap:
            st = window_prescan(inst, L, max_iters=prescan_iters,
                                max_energy_checks=prescan_checks,
                                use_index=prescan_index)
            prescan_time += st['info'].get('t', 0.0)
            prescan_work += st['info'].get('energy_checks', 0)
            if st['status'] == 'no':
                prescan_no += 1
                L = L + 1
                proof = st['proof']
                steps.append(('PRESCAN-NO', L - 1))
                audit()
                # try the primal decoder at the raised lower bound
                r = try_round(L)
                if r is not None:
                    use_sched(r['cmax'], r['schedule'], r['machine'])
                    steps.append(('ROUND', L, r['cmax'], r['kind']))
                    audit()
                else:
                    r = try_dom(L, st['D'])
                    if r is not None:
                        use_sched(r['cmax'], r['schedule'], r['machine'])
                        steps.append(('DOM', L, r['cmax'], r['kind']))
                        audit()
                defect_after_round = U - L
                if L >= U:
                    break
                continue
            elif st['status'] == 'open':
                prescan_open += 1
                if dom_decode and mode == 'pd':
                    r = try_dom(L, st['D'])
                    if r is not None:
                        use_sched(r['cmax'], r['schedule'], r['machine'])
                        steps.append(('DOM', L, r['cmax'], r['kind']))
                        audit()
                        defect_after_round = U - L
                        if L >= U:
                            break
                        continue
            else:
                prescan_fail += 1

        # ---- exact fixed-h oracle
        h = L if first else (L + U) // 2
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        probes += 1
        first = False
        search_lp += r.get('lp_solves', 0)
        cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False:
            L = h + 1
            proof = r['proof']
            steps.append(('NO', h))
            audit()
            if L < U and mode in ('round', 'pd') and ps is not None:
                r2 = try_round(L)
                if r2 is not None:
                    use_sched(r2['cmax'], r2['schedule'], r2['machine'])
                    steps.append(('ROUND', L, r2['cmax'], r2['kind']))
                    audit()
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            use_sched(c2, s2, m2)
            steps.append(('YES', h, c2))
            audit()
        else:
            steps.append(('UNKNOWN', h))
            break

    if L < U and probes < max_probes and mode == 'pd':
        h = U - 1
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        probes += 1
        search_lp += r.get('lp_solves', 0)
        cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False:
            L = h + 1
            proof = r['proof']
            steps.append(('NO', h))
            audit()
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            use_sched(c2, s2, m2)
            steps.append(('YES', h, c2))
            audit()
        else:
            steps.append(('UNKNOWN', h))

    final = (ICFCertificate(inst, U, s, m, proof)
             if L == U else None)
    final_ok = bool(final is not None and final.audit_rdf())
    pc = PartialCertificate(inst, L, U, s, m, proof, probe=probes)
    partial_final = bool(pc.audit_rdf())
    return dict(
        name=name, idx=idx, known=known, mode=mode,
        L0=L0, U0=U0, L=L, U=U, opt=U,
        defect=defect_after_round,
        probes=probes, search_lp=search_lp, cert_lp=cert_lp,
        pin_lp=pin_lp, round_work=round_work,
        round_hits=round_hits, cfa_hits=cfa_hits, dom_hits=dom_hits,
        prescan_no=prescan_no, prescan_open=prescan_open,
        prescan_fail=prescan_fail, prescan_work=prescan_work,
        prescan_time=round(prescan_time, 4),
        partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_final,
        certified=bool(L == U and final_ok), audit=final_ok,
        proof=final_ok, cert_h=(U - 1 if L == U else None),
        proof_kind=getattr(proof, 'kind', None),
        steps=steps, t=round(time.time() - t0, 4),
        schedule=list(s) if s is not None else None,
        machine=list(m) if m is not None else None,
        ok=bool(L == U == known and final_ok and partial_fail == 0
                and partial_final))
