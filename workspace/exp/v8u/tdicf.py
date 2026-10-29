"""v9.4 TD-ICF: total-decoder invariant-carrying frontier.

PD-ICF (v9.3) used the LP marginal decoder as a *partial* function:
whenever the decoded schedule exceeded the target horizon h, serial SGS
returned None and the schedule was discarded.  That loses a valid upper
bound and makes the decoder's defect unobservable.

TD-ICF changes the decoder's input/output contract:

    DECODE(P, x, h) -> (s, m, c)      with (s,m) feasible, c = Cmax(s)

always.  If c <= h the decoder *hits*; otherwise it returns a concrete
schedule with defect delta = c - h.  The controller can therefore update

    U <- min(U, c)

on every decoder call, not only on hits.  The bracket theorem becomes

    L <= OPT <= min(U, c) =: U'.

The exact oracle is still the only source of a global NO; the decoder is
a primal heuristic and its output is always checked by check_schedule.

The probe policy can use the defect.  With U-L = 1, one probe at L closes
the bracket either way; with a larger defect, TD-ICF can probe the upper
end U-1 or the midpoint.  The default 'lower' policy is the PD-ICF
baseline; 'defect' uses U-1 when the defect exceeds one, and 'binary'
uses the midpoint.

All intermediate states are audited as v9.0 PartialCertificate objects;
the final state is an ICFCertificate.
"""
import sys
import time
import random
import heapq

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from icf import PartialCertificate, ICFCertificate, cmax
from pact import PACT, pact_decide
from lbp import ParametricSD
from lpr import _pin_weak, _guide_at, topo_order, marginals, quantile
from pdicf import cfa_orders
from po import heads_tails
from rdf import check_schedule


def sgs_total(inst, order):
    """Serial SGS with a total output: never truncates at the horizon."""
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
    c = max(starts[i] + p[i] for i in range(n))
    return starts, machine, c


def _keys(inst, ps, res, H, use_cfa=True):
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
    return mrg, mean, tail, keys


def decode_total(inst, ps, res, H, use_cfa=True):
    """Deterministic total decoder.  Always returns the best schedule seen."""
    if res is None or getattr(res, 'x', None) is None:
        return dict(hit=False, cmax=None, schedule=None, machine=None,
                    work=0, kind='no-guide', order=None)
    mrg, mean, tail, keys = _keys(inst, ps, res, H, use_cfa)
    work = 0
    best = None
    for tag, key in keys:
        order = topo_order(inst, key)
        if order is None:
            continue
        work += 1
        s, m, c = sgs_total(inst, order)
        if not check_schedule(inst, c, s, m):
            continue
        if c <= H:
            return dict(hit=True, cmax=c, schedule=s, machine=m,
                        work=work, kind=tag, order=order)
        if best is None or c < best[0]:
            best = (c, s, m, order, tag)
    if best is None:
        return dict(hit=False, cmax=None, schedule=None, machine=None,
                    work=work, kind='miss', order=None)
    c, s, m, order, tag = best
    return dict(hit=False, cmax=c, schedule=s, machine=m,
                work=work, kind=tag, order=order)


def decode_random_total(inst, ps, res, H, restarts=50, seed=0,
                        time_cap=0.08):
    """Randomized total decoder: the best schedule is kept on a miss."""
    if res is None or getattr(res, 'x', None) is None:
        return dict(hit=False, cmax=None, schedule=None, machine=None,
                    work=0, kind='no-guide', order=None)
    mrg, mean, tail, _ = _keys(inst, ps, res, H, use_cfa=False)
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
        s, m, c = sgs_total(inst, order)
        if not check_schedule(inst, c, s, m):
            continue
        if best is None or c < best[0]:
            best = (c, s, m, order)
        if c <= H:
            return dict(hit=True, cmax=c, schedule=s, machine=m,
                        work=work, kind='rand', order=order)
    if best is None:
        return dict(hit=False, cmax=None, schedule=None, machine=None,
                    work=work, kind='miss', order=None)
    c, s, m, order = best
    return dict(hit=False, cmax=c, schedule=s, machine=m,
                work=work, kind='miss', order=order)


def run_tdicf(inst, known, name, idx, initial=None, mode='td',
              use_cfa=True, restarts=50, time_cap=0.08,
              max_probes=64, seed=0, policy='lower'):
    """Run TD-ICF on one instance.

    policy:
      'lower'   probe at L (PD-ICF baseline)
      'defect'  probe at U-1 while U-L>1, otherwise at L
      'binary'  probe at the midpoint while U-L>1, otherwise at L
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
    if mode in ('round', 'td') and L < U:
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
    partial_ok = 0
    partial_fail = 0
    steps = []
    defect_after_round = U - L
    total_defect = 0

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

    def try_round(target):
        nonlocal round_work, round_hits, search_lp, total_defect
        if ps is None or target >= U:
            return None
        res = guide
        if res is None or getattr(res, 'x', None) is None:
            res = ps.solve_h(target)
            search_lp += 1
        r = decode_total(inst, ps, res, target, use_cfa=use_cfa)
        round_work += r['work']
        if r['cmax'] is not None:
            total_defect += r['cmax'] - target
            use_sched(r['cmax'], r['schedule'], r['machine'])
        if r['hit']:
            round_hits += 1
            return r
        if restarts > 0:
            r2 = decode_random_total(inst, ps, res, target,
                                     restarts=restarts, seed=seed,
                                     time_cap=time_cap)
            round_work += r2['work']
            if r2['cmax'] is not None:
                total_defect += r2['cmax'] - target
                use_sched(r2['cmax'], r2['schedule'], r2['machine'])
            if r2['hit']:
                round_hits += 1
                return r2
        return None

    audit()
    if mode in ('round', 'td') and L < U:
        r = try_round(L)
        if r is not None:
            steps.append(('ROUND', L, r['cmax'], r['kind']))
            audit()
        defect_after_round = U - L

    first = True
    while L < U and probes < max_probes:
        if policy == 'lower':
            h = L
        elif policy == 'defect':
            h = L if (U - L <= 1 or first) else U - 1
        elif policy == 'binary':
            h = L if (U - L <= 1 or first) else (L + U) // 2
        else:
            h = L
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
            if L < U and mode in ('round', 'td') and ps is not None:
                r2 = try_round(L)
                if r2 is not None:
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

    if L < U and probes < max_probes and mode in ('round', 'td'):
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
        name=name, idx=idx, known=known, mode=mode, policy=policy,
        L0=L0, U0=U0, L=L, U=U, opt=U,
        defect=defect_after_round, total_defect=total_defect,
        probes=probes, search_lp=search_lp, cert_lp=cert_lp,
        pin_lp=pin_lp, round_work=round_work,
        round_hits=round_hits,
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
