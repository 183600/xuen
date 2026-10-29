"""v9.3 PD-ICF: primal-dual invariant-carrying frontier.

The v9.0 ICF state

    C = (L, U, s, m, pi),   pi : NO(L-1),  Cmax(s)=U,  L<=U

is kept unchanged.  PD-ICF adds a *dual anchor* and a *primal decoder*
around the exact fixed-h oracle:

  ANCHOR  compute the SD-LP value threshold

              L* = min { h : P_h is feasible }

          with one parametric matrix, and install the Farkas proof at
          L*-1.  This is a certified lower-bound transition.

  ROUND   take the LP solution at L* (or at the current L), interpret
          its per-task start-time marginals as a priority distribution,
          and decode it with serial SGS at horizon L*.  A hit closes the
          bracket without any exact oracle call.

  PROBE   the v9.0 complete fixed-h decision procedure, used only on the
          residual interval left after ANCHOR + ROUND.

The new quantity is the *observable defect*

    delta = U_round - L*

where U_round is the best schedule produced by the decoder.  The bracket
theorem is

    L* <= OPT <= U_round.

If delta = 0 the state is already optimal; if delta is small the exact
search is confined to the defect interval, not the original gap.

The decoder portfolio includes a control-flow-analysis order based on
the dominator tree of the precedence DAG: if i dominates j, every path
to j passes through i, so i is a safe priority predecessor of j.

All accepted schedules pass check_schedule; all NO answers replay a
Farkas/Branch proof.  Every intermediate state is audited as a v9.0
PartialCertificate.
"""
import sys
import time
import math
import random
import heapq
import collections

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from icf import PartialCertificate, ICFCertificate, cmax, corpora
from pact import PACT, pact_decide
from taicf import FarkasPin
from lbp import ParametricSD, farkas_bounds
from lpr import sgs, topo_order, marginals, quantile, _pin_weak, _guide_at
from po import heads_tails
from rdf import check_schedule
from cert import verify


# --------------------------------------------------------------- anchor
def anchor(inst, L, U):
    """Parametric SD-LP threshold plus a Farkas certificate at L*-1.

    Returns dict(h, cert, solves, ok, param, guide).
    ``guide`` is a feasible LP result at some horizon >= h, used only as
    a priority hint for the primal decoder.
    """
    ps = ParametricSD(inst, int(U))
    lo, hi = int(L), int(U)
    last_bad = None
    last_good = None
    solves = 0
    ok = True
    while lo < hi:
        mid = (lo + hi) // 2
        bounds = ps.bounds_h(mid)
        res = ps.solve_h(mid)
        solves += 1
        if res.status == 0:
            hi = mid
            last_good = res
        elif res.status == 2:
            lo = mid + 1
            last_bad = (mid, bounds)
        else:
            ok = False
            break
    cert = None
    if ok and lo > L and last_bad is not None and last_bad[0] == lo - 1:
        c = farkas_bounds(ps.lp, last_bad[0], last_bad[1])
        solves += 1
        if c is not None and verify(inst, last_bad[0], c):
            cert = c
        else:
            ok = False
    guide = last_good
    if ok and guide is None and lo < U:
        guide = ps.solve_h(lo)
        solves += 1
    return dict(h=lo, cert=cert, solves=solves, ok=ok,
                param=ps, guide=guide,
                last_bad=(None if last_bad is None else last_bad[0]))


# ------------------------------------------------------- control-flow CFA
def dominator_depths(inst):
    """Dominator and post-dominator depths of the precedence DAG.

    A virtual source (index n) points to every source, and a virtual sink
    (also index n) is pointed to by every sink.  The dataflow equations

        dom(v)  = {v} union  Intersection_{u in pred(v)} dom(u)
        pdom(v) = {v} union  Intersection_{w in succ(v)} pdom(w)

    are solved by chaotic iteration.  For n <= 21 this bitset version is
    both simpler and faster than Lengauer-Tarjan, and it is the same
    fixpoint a control-flow analysis would compute.
    """
    n = inst['n']
    preds = [set(inst['pred'][i]) for i in range(n)]
    succs = [set(inst['succ'][i]) for i in range(n)]
    for i in range(n):
        if not preds[i]:
            preds[i].add(n)
        if not succs[i]:
            succs[i].add(n)

    def solve(adj):
        dom = [set(range(n + 1)) for _ in range(n + 1)]
        dom[n] = {n}
        changed = True
        while changed:
            changed = False
            for v in range(n):
                inter = None
                for u in adj[v]:
                    inter = set(dom[u]) if inter is None else inter & dom[u]
                nd = ({v} | inter) if inter is not None else {v}
                if nd != dom[v]:
                    dom[v] = nd
                    changed = True
        return [len(dom[i]) for i in range(n)]

    return solve(preds), solve(succs)


def cfa_orders(inst, mean, tail, H):
    """Priority keys that respect the dominator/post-dominator skeleton."""
    dep, pdep = dominator_depths(inst)
    p = inst['p']
    est, _ = heads_tails(inst, 0, [0] * inst['n'])
    return [
        ('cfa:dom-mean',
         lambda i: (dep[i], mean[i], i * 1e-6)),
        ('cfa:pdom-mean',
         lambda i: (pdep[i], mean[i], i * 1e-6)),
        ('cfa:dom-pdom-mean',
         lambda i: (dep[i], pdep[i], mean[i], i * 1e-6)),
        ('cfa:slack-mean',
         lambda i: (H - tail[i] - p[i] - est[i], mean[i], i * 1e-6)),
        ('cfa:dom-tail',
         lambda i: (-dep[i], -tail[i], mean[i], i * 1e-6)),
        ('cfa:pdom-tail',
         lambda i: (-pdep[i], -tail[i], mean[i], i * 1e-6)),
    ]


# ------------------------------------------------------------- rounding
def decode_orders(inst, ps, res, H, use_cfa=True):
    """Deterministic decoder portfolio.  Returns (hit, work, kind).

    The orders are exactly the v9.1 LPR quantile/mean/latest/tail family
    plus, when use_cfa is true, the dominator orders above.  Every order
    is a topological order; SGS enforces the horizon H and the result
    still has to pass check_schedule.
    """
    if res is None or getattr(res, 'x', None) is None:
        return dict(hit=False, cmax=None, schedule=None, machine=None,
                    work=0, kind='no-guide')
    mrg = marginals(inst, ps, res)
    mean = [m for m, _ in mrg]
    est, tail = heads_tails(inst, 0, [0] * inst['n'])
    keys = []
    for q in (0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98):
        keys.append(('q%g' % q,
                     lambda i, q=q: (quantile(mrg[i][1], q) + i * 1e-6)))
    keys.append(('mean', lambda i: (mean[i] + i * 1e-6)))
    keys.append(('latest',
                 lambda i: (-(H - tail[i] - inst['p'][i]) + i * 1e-6)))
    keys.append(('tail', lambda i: (-tail[i] + i * 1e-6)))
    if use_cfa:
        keys.extend(cfa_orders(inst, mean, tail, H))
    work = 0
    best = None
    for tag, key in keys:
        order = topo_order(inst, key)
        if order is None:
            continue
        work += 1
        r = sgs(inst, order, H)
        if r is None:
            continue
        s, m, c = r
        if c <= H and check_schedule(inst, c, s, m):
            return dict(hit=True, cmax=c, schedule=s, machine=m,
                        work=work, kind=tag, order=order)
        if best is None or c < best[0]:
            best = (c, s, m, order)
    return dict(hit=False, cmax=(best[0] if best else None),
                schedule=(best[1] if best else None),
                machine=(best[2] if best else None),
                work=work, kind='miss',
                order=(best[3] if best else None))


def decode_random(inst, ps, res, H, restarts=50, seed=0,
                  time_cap=0.08):
    """Randomized marginals decoder, in the spirit of LPR's random mode."""
    if res is None or getattr(res, 'x', None) is None:
        return dict(hit=False, cmax=None, schedule=None, machine=None,
                    work=0, kind='no-guide')
    mrg = marginals(inst, ps, res)
    est, tail = heads_tails(inst, 0, [0] * inst['n'])
    rng = random.Random(seed)
    t0 = time.time()
    work = 0
    best = None
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
        r = sgs(inst, order, H)
        if r is None:
            continue
        s, m, c = r
        if c <= H and check_schedule(inst, c, s, m):
            return dict(hit=True, cmax=c, schedule=s, machine=m,
                        work=work, kind='rand', order=order)
        if best is None or c < best[0]:
            best = (c, s, m, order)
    return dict(hit=False, cmax=(best[0] if best else None),
                schedule=(best[1] if best else None),
                machine=(best[2] if best else None),
                work=work, kind='miss',
                order=(best[3] if best else None))


def _is_topo(inst, order):
    pos = [0] * inst['n']
    for k, v in enumerate(order):
        pos[v] = k
    for u in range(inst['n']):
        for v in inst['pred'][u]:
            if pos[u] >= pos[v]:
                return False
    return True


def local_search(inst, order, H, budget=300, time_cap=0.05):
    """Adjacent-swap / insertion descent in the priority-order space.

    A near-miss from LP rounding is often one adjacent swap away from a
    schedule at the target horizon.  The neighborhood is restricted to
    topological orders, so every candidate is a legal SGS priority list.
    """
    if order is None:
        return dict(hit=False, cmax=None, schedule=None, machine=None,
                    work=0, kind='miss', order=None)
    n = inst['n']
    t0 = time.time()
    cache = {}

    def ev(o):
        key = tuple(o)
        if key in cache:
            return cache[key]
        r = sgs(inst, list(o), H)
        if r is None:
            cache[key] = (10 ** 9, None, None)
            return cache[key]
        s, m, c = r
        if c > H or not check_schedule(inst, c, s, m):
            c = 10 ** 9
        cache[key] = (c, s, m)
        return cache[key]

    c, s, m = ev(order)
    best = (c, s, m, list(order))
    work = 1
    if c <= H:
        return dict(hit=True, cmax=c, schedule=s, machine=m,
                    work=work, kind='local', order=list(order))
    while work < budget and time.time() - t0 < time_cap:
        improved = None
        o0 = best[3]
        for i in range(n - 1):
            o = list(o0)
            o[i], o[i + 1] = o[i + 1], o[i]
            if not _is_topo(inst, o):
                continue
            c2, s2, m2 = ev(o)
            work += 1
            if c2 < best[0]:
                improved = (c2, s2, m2, o)
        if improved is None:
            for i in range(n):
                for j in range(n):
                    if i == j:
                        continue
                    o = list(o0)
                    v = o.pop(i)
                    o.insert(j, v)
                    if not _is_topo(inst, o):
                        continue
                    c2, s2, m2 = ev(o)
                    work += 1
                    if c2 < best[0]:
                        improved = (c2, s2, m2, o)
        if improved is None:
            break
        best = improved
        if best[0] <= H:
            return dict(hit=True, cmax=best[0], schedule=best[1],
                        machine=best[2], work=work, kind='local',
                        order=best[3])
    return dict(hit=False, cmax=(best[0] if best[0] < 10 ** 9 else None),
                schedule=best[1], machine=best[2], work=work,
                kind='miss', order=best[3])


# -------------------------------------------------------------- algorithm
def run_pdicf(inst, known, name, idx, initial=None, mode='pd',
              use_cfa=True, restarts=50, time_cap=0.08,
              max_probes=64, seed=0, repair=False,
              repair_budget=300, repair_time=0.05):
    """Run PD-ICF on one instance.

    mode:
      'anchor'  dual anchor + exact probes only
      'round'   primal rounding at the initial L + exact probes
      'pd'      dual anchor + deterministic/random decoding + probes
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
    anchor_lp = 0
    anchor_ok = bool((co.pin or {}).get('param') is not None)
    anchor_h = L
    ps = None
    guide = None
    # The initializer (PACT pin / _pin_weak) has already produced the
    # dual LP anchor and the Farkas proof at L-1.  Reuse its parametric
    # matrix as the primal guide; only solve a fresh LP if the initializer
    # did not leave one.
    if mode in ('round', 'pd') and L < U:
        ps, guide, extra = _guide_at(co, L)
        pin_lp += extra
        if ps is None or guide is None or getattr(guide, 'x', None) is None:
            ps = ParametricSD(inst, int(U))
            guide = ps.solve_h(L)
            pin_lp += 1


    probes = 0
    search_lp = 0
    cert_lp = 0
    round_work = 0
    round_hits = 0
    cfa_hits = 0
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
        else:
            r2 = None
        if repair and (r.get('order') is not None or
                       (r2 is not None and r2.get('order') is not None)):
            o = (r2.get('order') if r2 is not None and
                 r2.get('order') is not None else r.get('order'))
            r3 = local_search(inst, o, target, budget=repair_budget,
                              time_cap=repair_time)
            round_work += r3['work']
            if r3['hit']:
                round_hits += 1
                return r3
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
        if mode == 'pd' and defect_after_round <= 2:
            h = L if first else (L + U) // 2
        elif mode in ('anchor', 'pd'):
            h = L if first else (L + U) // 2
        else:
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
        anchor_h=anchor_h, anchor_ok=anchor_ok,
        anchor_lp=anchor_lp, defect=defect_after_round,
        probes=probes, search_lp=search_lp, cert_lp=cert_lp,
        pin_lp=pin_lp, round_work=round_work,
        round_hits=round_hits, cfa_hits=cfa_hits,
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
