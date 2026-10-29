"""ASR-ICF: approximation-scheme reinsertion for invariant-carrying frontiers.

v9.3 PD-ICF leaves a primal defect at the LP anchor L*: SGS on the LP
marginal orders may fail to produce a schedule of length <= L*.  ASR-ICF
adds a bounded-defect decoder family

    REINSERT_k(L)

in the space of topological priority orders.  k is the number of jobs
removed from a base order and reinserted at another position.  k=0 is the
PD-ICF portfolio; k=1 is the first level of the scheme and costs at most
O(|Pi| n^2) SGS calls.  A hit at L closes the bracket with no exact
probe.  A miss still returns the shortest schedule seen, so the upper
bound U becomes the *approximate* upper bound of the scheme; the exact
probe then only has to resolve the residual defect U-L.

The certificate state is unchanged:

    C = (L, U, s, m, pi),   pi : NO(L-1), Cmax(s)=U, L<=U.

Every accepted schedule is checked by check_schedule; every intermediate
state is audited as a v9.0 PartialCertificate.
"""
import sys
import time
import collections

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from icf import PartialCertificate, ICFCertificate, cmax
from pact import PACT, pact_decide
from lpr import (sgs, topo_order, marginals, quantile,
                 _pin_weak, _guide_at)
from po import heads_tails
from lbp import ParametricSD
from rdf import check_schedule
from pdicf import decode_orders, decode_random


def topo_ok(inst, order):
    """Correct topological-order predicate.

    pdicf._is_topo has reversed polarity (it rejects every valid order);
    the local-search negative result in v9.3 was produced with that
    predicate and is therefore vacuous.  ASR-ICF uses this one.
    """
    pos = [0] * inst['n']
    for k, v in enumerate(order):
        pos[v] = k
    for u in range(inst['n']):
        for v in inst['succ'][u]:
            if pos[u] >= pos[v]:
                return False
    return True


def base_orders(inst, ps, res, H=0, use_cfa=True):
    """All deterministic LP-marginal orders, not just the first hit."""
    if res is None or getattr(res, 'x', None) is None:
        return []
    mrg = marginals(inst, ps, res)
    mean = [m for m, _ in mrg]
    est, tail = heads_tails(inst, 0, [0] * inst['n'])
    keys = []
    for q in (0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98):
        keys.append(('q%g' % q,
                     lambda i, q=q: (quantile(mrg[i][1], q) + i * 1e-6)))
    keys.append(('mean', lambda i: (mean[i] + i * 1e-6)))
    keys.append(('tail', lambda i: (-tail[i] + i * 1e-6)))
    if use_cfa:
        from pdicf import cfa_orders
        keys.extend(cfa_orders(inst, mean, tail, 0))
    out = []
    for tag, key in keys:
        order = topo_order(inst, key)
        if order is not None:
            out.append((tag, order))
    return out


def reinsert_decode(inst, ps, res, L, U, use_cfa=True, later_only=True,
                    max_work=None):
    """One-defect reinsertion decoder.

    For every base order and every job v, remove v and reinsert it at a
    later (or any) position; keep only topological orders.  Decode each
    with SGS at horizon L.  Return the first schedule of length <= L, or
    the shortest schedule seen as a certified upper bound.

    Complexity: O(|Pi| n^2 T_SGS) in the worst case.
    """
    if res is None or getattr(res, 'x', None) is None:
        return dict(hit=False, cmax=None, schedule=None, machine=None,
                    work=0, kind='no-guide', order=None, base=None,
                    moved=None)
    n = inst['n']
    best = None
    work = 0
    for tag, order in base_orders(inst, ps, res, H=L, use_cfa=use_cfa):
        pos0 = [0] * n
        for k, v in enumerate(order):
            pos0[v] = k
        for i in range(n):
            pos = pos0[i]
            rem = order[:pos] + order[pos + 1:]
            js = range(pos, n) if later_only else range(n)
            for j in js:
                if j == pos:
                    continue
                o2 = rem[:j] + [i] + rem[j:]
                if not topo_ok(inst, o2):
                    continue
                work += 1
                r = sgs(inst, o2, None)
                if r is None:
                    continue
                s, m, c = r
                if not check_schedule(inst, c, s, m):
                    continue
                if c <= L:
                    return dict(hit=True, cmax=c, schedule=s, machine=m,
                                work=work, kind='reinsert:%s' % tag,
                                order=o2, base=tag, moved=(i, pos, j))
                if best is None or c < best[0]:
                    best = (c, s, m, o2, tag, i, pos, j)
                if max_work is not None and work >= max_work:
                    break
            if max_work is not None and work >= max_work:
                break
        if max_work is not None and work >= max_work:
            break
    if best is None:
        return dict(hit=False, cmax=None, schedule=None, machine=None,
                    work=work, kind='miss', order=None, base=None,
                    moved=None)
    c, s, m, o2, tag, i, pos, j = best
    return dict(hit=False, cmax=c, schedule=s, machine=m, work=work,
                kind='near:%s' % tag, order=o2, base=tag,
                moved=(i, pos, j))


def reinsert_decode2(inst, ps, res, L, U, use_cfa=True, width=8):
    """Two-level insertion scheme, kept for ablation.

    Round 1 keeps the best `width` orders by makespan; round 2 applies a
    single reinsertion to each.  This is the k=2 level of the family and
    is deliberately not used in the main run (see the artifact).
    """
    if res is None or getattr(res, 'x', None) is None:
        return dict(hit=False, cmax=None, schedule=None, machine=None,
                    work=0, kind='no-guide')
    n = inst['n']
    work = 0
    pool = []
    seen = set()
    for tag, order in base_orders(inst, ps, res, H=L, use_cfa=use_cfa):
        r = sgs(inst, order, None)
        work += 1
        if r is None:
            continue
        s, m, c = r
        if not check_schedule(inst, c, s, m):
            continue
        if c <= L:
            return dict(hit=True, cmax=c, schedule=s, machine=m,
                        work=work, kind='reinsert0:%s' % tag)
        pool.append((c, tag, order))
        seen.add(tuple(order))
    pool.sort(key=lambda x: x[0])
    pool = pool[:width]
    best = None
    for rnd in (1, 2):
        cand = []
        for c0, tag, order in pool:
            pos0 = [0] * n
            for k, v in enumerate(order):
                pos0[v] = k
            for i in range(n):
                pos = pos0[i]
                rem = order[:pos] + order[pos + 1:]
                for j in range(pos, n):
                    if j == pos:
                        continue
                    o2 = rem[:j] + [i] + rem[j:]
                    if not topo_ok(inst, o2):
                        continue
                    work += 1
                    r = sgs(inst, o2, None)
                    if r is None:
                        continue
                    s, m, c = r
                    if not check_schedule(inst, c, s, m):
                        continue
                    if c <= L:
                        return dict(hit=True, cmax=c, schedule=s,
                                    machine=m, work=work,
                                    kind='reinsert%d:%s' % (rnd, tag))
                    if best is None or c < best[0]:
                        best = (c, s, m)
                    cand.append((c, tag, o2))
        cand.sort(key=lambda x: x[0])
        pool = cand[:width]
        if not pool:
            break
    return dict(hit=False, cmax=(best[0] if best else None),
                schedule=(best[1] if best else None),
                machine=(best[2] if best else None),
                work=work, kind='miss')


def run_asr(inst, known, name, idx, initial=None, mode='asr',
            use_cfa=True, restarts=50, time_cap=0.08, max_probes=64,
            seed=0, k=1):
    """Run ASR-ICF on one instance.

    mode:
      'pd'   PD-ICF baseline (no reinsertion)
      'asr'  PD-ICF + one-defect reinsertion + best-effort U
      'asr2' PD-ICF + two-level reinsertion (ablation)
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
    ps = None
    guide = None
    if mode in ('round', 'pd', 'asr', 'asr2') and L < U:
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
    reinsert_work = 0
    reinsert_hits = 0
    reinsert_tight = 0
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

    def _guide_res(target):
        nonlocal search_lp
        res = guide
        if res is None or getattr(res, 'x', None) is None:
            res = ps.solve_h(target)
            search_lp += 1
        return res

    def try_round_det(target):
        nonlocal round_work, round_hits, cfa_hits
        if ps is None or target >= U:
            return None
        r = decode_orders(inst, ps, _guide_res(target), target,
                          use_cfa=use_cfa)
        round_work += r['work']
        if r['hit']:
            round_hits += 1
            if r['kind'].startswith('cfa:'):
                cfa_hits += 1
            return r
        return None

    def try_round_rand(target):
        nonlocal round_work, round_hits
        if ps is None or target >= U or restarts <= 0:
            return None
        r = decode_random(inst, ps, _guide_res(target), target,
                          restarts=restarts, seed=seed,
                          time_cap=time_cap)
        round_work += r['work']
        if r['hit']:
            round_hits += 1
            return r
        return None

    def try_round(target, do_random=True):
        r = try_round_det(target)
        if r is not None:
            return r
        if do_random:
            return try_round_rand(target)
        return None

    def try_reinsert(target, level=1):
        nonlocal reinsert_work, reinsert_hits, reinsert_tight
        if ps is None or target >= U:
            return None
        res = guide
        if res is None or getattr(res, 'x', None) is None:
            res = ps.solve_h(target)
            search_lp += 1
        if level == 2:
            r = reinsert_decode2(inst, ps, res, target, U,
                                 use_cfa=use_cfa)
        else:
            r = reinsert_decode(inst, ps, res, target, U,
                                use_cfa=use_cfa)
        reinsert_work += r['work']
        if r['hit']:
            reinsert_hits += 1
            return r
        if r['cmax'] is not None and r['cmax'] < U:
            if use_sched(r['cmax'], r['schedule'], r['machine']):
                reinsert_tight += 1
                steps.append(('TIGHTEN', target, r['cmax'], r['kind']))
                audit()
        return None

    audit()
    if mode in ('round', 'pd', 'asr', 'asr2') and L < U:
        r = try_round_det(L)
        if r is not None:
            use_sched(r['cmax'], r['schedule'], r['machine'])
            steps.append(('ROUND', L, r['cmax'], r['kind']))
            audit()
        elif mode in ('asr', 'asr2'):
            rr = try_reinsert(L, level=(2 if mode == 'asr2' else 1))
            if rr is not None:
                use_sched(rr['cmax'], rr['schedule'], rr['machine'])
                steps.append(('REINSERT', L, rr['cmax'], rr['kind']))
                audit()
        if L < U and mode in ('round', 'pd', 'asr', 'asr2'):
            r = try_round_rand(L)
            if r is not None:
                use_sched(r['cmax'], r['schedule'], r['machine'])
                steps.append(('RAND', L, r['cmax'], r['kind']))
                audit()
        defect_after_round = U - L

    first = True
    while L < U and probes < max_probes:
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
            if L < U and mode in ('round', 'pd', 'asr', 'asr2') and ps is not None:
                r2 = try_round_det(L)
                if r2 is not None:
                    use_sched(r2['cmax'], r2['schedule'], r2['machine'])
                    steps.append(('ROUND', L, r2['cmax'], r2['kind']))
                    audit()
                elif mode in ('asr', 'asr2'):
                    rr = try_reinsert(L, level=(2 if mode == 'asr2' else 1))
                    if rr is not None:
                        use_sched(rr['cmax'], rr['schedule'], rr['machine'])
                        steps.append(('REINSERT', L, rr['cmax'], rr['kind']))
                        audit()
                if L < U:
                    r3 = try_round_rand(L)
                    if r3 is not None:
                        use_sched(r3['cmax'], r3['schedule'], r3['machine'])
                        steps.append(('RAND', L, r3['cmax'], r3['kind']))
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

    if L < U and probes < max_probes and mode in ('pd', 'asr', 'asr2'):
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
        anchor_h=L, anchor_ok=anchor_ok, anchor_lp=anchor_lp,
        defect=defect_after_round,
        probes=probes, search_lp=search_lp, cert_lp=cert_lp,
        pin_lp=pin_lp, round_work=round_work,
        round_hits=round_hits, cfa_hits=cfa_hits,
        reinsert_work=reinsert_work, reinsert_hits=reinsert_hits,
        reinsert_tight=reinsert_tight,
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
