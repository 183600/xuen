"""DBR-ICF: deterministic diverse-beam rounding for invariant-carrying frontiers.

v9.3 PD-ICF closes many brackets by decoding the LP marginal solution, but
its decoder portfolio ends with up to 50 random restarts and a wall-clock
cutoff.  ASR-ICF adds a deterministic one-defect reinsertion search, but it
runs the search from *all* 15 LP-marginal orders, costing O(|Pi| n^2 SGS)
per probe.  DBR-ICF keeps the ICF state

    C = (L, U, s, m, pi),   pi : NO(L-1),  Cmax(s)=U,  L<=U

and replaces the random/all-order decoder by a deterministic, space-bounded
beam over the LP-marginal order portfolio:

  BASE    evaluate the K=15 deterministic marginal orders at horizon L.
          A base hit closes the bracket with no probe.

  BEAM    keep only k<=K orders, chosen by farthest-point diversity in the
          Hamming metric (a greedy 2-approximation of the max-min k-center
          objective).  Reinsert one job in each beam member; a hit closes.
          If the beam misses, take the next k orders in the same diversity
          order (a batch), up to b batches.  Space is O(k n); b controls
          time, not memory.

  PROBE   the v9.0 fixed-h oracle, used only when the beam misses.

The algorithm is deterministic: no RNG, no wall-clock cutoff, and canonical
tie-breaking by (makespan, tag, job index, position).  Every generated order
is a topological order; every accepted schedule is checked by
check_schedule; every state is audited as a PartialCertificate.
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
from lpr import (sgs, _pin_weak, _guide_at)
from lbp import ParametricSD
from rdf import check_schedule
from asr import base_orders, topo_ok


def hamming(a, b):
    """Hamming distance between two permutations of the same set."""
    pos = [0] * len(a)
    for k, v in enumerate(a):
        pos[v] = k
    return sum(1 for x, y in zip(a, b) if x != y)


def diversity_order(scored):
    """Farthest-point ordering of candidate orders.

    The first element is the best-makespan order.  Each subsequent element
    maximizes the minimum Hamming distance to the already selected orders;
    ties are broken by makespan and tag.  This is the standard greedy
    2-approximation of the max-min k-center objective.  It gives a
    deterministic, parameter-free way to cover different topological
    orders instead of taking k nearly identical top-makespan orders.
    """
    if not scored:
        return []
    scored = sorted(scored, key=lambda x: (x[0], x[1]))
    out = [scored[0]]
    rest = scored[1:]
    while rest:
        best = None
        best_key = None
        for item in rest:
            c, tag, order = item
            dmin = min(hamming(order, s[2]) for s in out)
            key = (-dmin, c, tag)
            if best_key is None or key < best_key:
                best_key = key
                best = item
        out.append(best)
        rest.remove(best)
    return out


def beam_round(inst, ps, res, L, U, k=4, max_batches=1, use_cfa=True):
    """Deterministic diverse-beam decoder at horizon L.

    Returns a dict with hit, cmax, schedule, machine, work, kind, base,
    moved, batches.  A miss may still return the shortest schedule seen;
    the caller may use it to tighten U, but it is only a heuristic upper
    bound and is checked by check_schedule.
    """
    n = inst['n']
    work = 0
    scored = []
    seen = set()

    for tag, order in base_orders(inst, ps, res, H=L, use_cfa=use_cfa):
        key = tuple(order)
        if key in seen:
            continue
        seen.add(key)
        work += 1
        r = sgs(inst, order, None)
        if r is None:
            continue
        s, m, c = r
        if not check_schedule(inst, c, s, m):
            continue
        if c <= L:
            return dict(hit=True, cmax=c, schedule=s, machine=m, work=work,
                        kind='base:%s' % tag, base=tag, moved=None,
                        batches=0)
        scored.append((c, tag, order))

    order_all = diversity_order(scored)
    best = None
    best_key = None
    batches = 0
    for b in range(max_batches):
        lo = b * k
        if lo >= len(order_all):
            break
        batches += 1
        for c0, tag, order in order_all[lo:lo + k]:
            pos0 = [0] * n
            for pos, v in enumerate(order):
                pos0[v] = pos
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
                                    kind='reinsert:%s' % tag, base=tag,
                                    moved=(i, pos, j), batches=batches)
                    key = (c, tag, i, pos, j)
                    if best_key is None or key < best_key:
                        best_key = key
                        best = (c, s, m, o2, tag, i, pos, j)
    if best is None:
        return dict(hit=False, cmax=None, schedule=None, machine=None,
                    work=work, kind='miss', base=None, moved=None,
                    batches=batches)
    c, s, m, o2, tag, i, pos, j = best
    return dict(hit=False, cmax=c, schedule=s, machine=m, work=work,
                kind='near:%s' % tag, base=tag, moved=(i, pos, j),
                batches=batches)


def run_dbr(inst, known, name, idx, initial=None, mode='dbr', k=4,
            max_batches=1, use_cfa=True, max_probes=64):
    """Run DBR-ICF on one instance.

    mode:
      'beam'  only the deterministic beam decoder + exact probes
      'dbr'   beam + exact probes (same control flow; kept for clarity)
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
    if L < U:
        ps, guide, extra = _guide_at(co, L)
        pin_lp += extra
        if ps is None or guide is None or getattr(guide, 'x', None) is None:
            ps = ParametricSD(inst, int(U))
            guide = ps.solve_h(L)
            pin_lp += 1

    probes = 0
    search_lp = 0
    cert_lp = 0
    beam_work = 0
    beam_hits = 0
    beam_tight = 0
    beam_batches = 0
    base_hits = 0
    reinsert_hits = 0
    probe_no = 0
    probe_yes = 0
    probe_unknown = 0
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

    def try_beam(target):
        nonlocal beam_work, beam_hits, beam_tight, beam_batches
        nonlocal base_hits, reinsert_hits
        if ps is None or target >= U:
            return None
        r = beam_round(inst, ps, guide, target, U, k=k,
                       max_batches=max_batches, use_cfa=use_cfa)
        beam_work += r['work']
        beam_batches += r['batches']
        if r['hit']:
            beam_hits += 1
            if r['kind'].startswith('base:'):
                base_hits += 1
            else:
                reinsert_hits += 1
            return r
        if r['cmax'] is not None and r['cmax'] < U:
            if use_sched(r['cmax'], r['schedule'], r['machine']):
                beam_tight += 1
                steps.append(('TIGHTEN', target, r['cmax'], r['kind']))
                audit()
        return None

    audit()
    if L < U:
        r = try_beam(L)
        if r is not None:
            use_sched(r['cmax'], r['schedule'], r['machine'])
            steps.append(('BEAM', L, r['cmax'], r['kind']))
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
            probe_no += 1
            L = h + 1
            proof = r['proof']
            steps.append(('NO', h))
            audit()
            if L < U:
                r2 = try_beam(L)
                if r2 is not None:
                    use_sched(r2['cmax'], r2['schedule'], r2['machine'])
                    steps.append(('BEAM', L, r2['cmax'], r2['kind']))
                    audit()
        elif r['verdict'] is True:
            probe_yes += 1
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            use_sched(c2, s2, m2)
            steps.append(('YES', h, c2))
            audit()
        else:
            probe_unknown += 1
            steps.append(('UNKNOWN', h))
            break

    if L < U and probes < max_probes:
        h = U - 1
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        probes += 1
        search_lp += r.get('lp_solves', 0)
        cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False:
            probe_no += 1
            L = h + 1
            proof = r['proof']
            steps.append(('NO', h))
            audit()
        elif r['verdict'] is True:
            probe_yes += 1
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            use_sched(c2, s2, m2)
            steps.append(('YES', h, c2))
            audit()
        else:
            probe_unknown += 1
            steps.append(('UNKNOWN', h))

    final = (ICFCertificate(inst, U, s, m, proof)
             if L == U else None)
    final_ok = bool(final is not None and final.audit_rdf())
    pc = PartialCertificate(inst, L, U, s, m, proof, probe=probes)
    partial_final = bool(pc.audit_rdf())
    return dict(
        name=name, idx=idx, known=known, mode=mode,
        L0=L0, U0=U0, L=L, U=U, opt=U,
        anchor_h=L, anchor_ok=bool((co.pin or {}).get('param') is not None),
        defect=defect_after_round,
        probes=probes, search_lp=search_lp, cert_lp=cert_lp,
        pin_lp=pin_lp, beam_work=beam_work, beam_hits=beam_hits,
        beam_tight=beam_tight, beam_batches=beam_batches,
        base_hits=base_hits, reinsert_hits=reinsert_hits,
        probe_no=probe_no, probe_yes=probe_yes,
        probe_unknown=probe_unknown,
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
