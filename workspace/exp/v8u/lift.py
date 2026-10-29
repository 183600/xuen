"""v9.1 LIFT-ICF: synchronous incremental repair of NO certificates.

v9.0 ICF keeps a partial certificate

    (L, U, s, m, pi),   pi : NO(L-1),  Cmax(s)=U,  L <= U.

The missing piece in the one-leaf specialization was that every probe
was paid for from scratch.  LIFT-ICF adds an *incremental certificate
lift*: after a NO probe at h, the same BranchProof tree is repaired to
h+1, h+2, ... as long as every leaf can be re-certified at the larger
horizon.  The lift is a synchronous pass over the tree: all leaves are
visited at the new horizon before the next horizon is attempted.

Two facts make the pass cheap and auditable:

  * a leaf whose old Farkas/empty certificate still verifies at the new
    horizon is reused with no LP solve;
  * a leaf whose certificate expires gets one fresh integer Farkas
    certificate at the new horizon.

If the whole tree repairs, the result is a genuine NO(h') proof; the
outer ICF bound can jump directly to h'+1.  If repair fails, the old
proof is kept and the ordinary probe loop continues.  Thus every
intermediate state still satisfies the v9.0 invariant; the lift changes
the *rate* at which L moves, not the trusted certificate language.

The repair is only a proof-transformation.  It does not decide the
NP-hard scheduling problem and does not claim a polynomial bound on the
number of outer probes.  Each repair pass is polynomial in the size of
the tree and the LP, and the number of passes is bounded by the current
bracket width.
"""
import sys
import time

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from sage import BranchProof, SubsumptionProof, _domain
from cert import integer_certificate, verify
from rdf import check_schedule
from pact import PACT, pact_decide
from icf import (PartialCertificate, ICFCertificate, cmax, _choose_h,
                 corpora)


def allowed_times(inst, h, i, F):
    lo, hi = _domain(inst, h, i)
    return [t for t in range(lo, hi + 1) if (i, t) not in F]


def _new_stats():
    return dict(reuse=0, new_lp=0, nodes=0, fail=0, empty=0, collapse=0)


def _repair_node(inst, node, F, h, stats):
    """Rebuild one BranchProof node at horizon h.

    The node's own box is F; child forbidden sets are recomputed from F
    and the split threshold, so a tree built at a smaller horizon is
    valid for the larger domain as well.  Returns a node or None.
    """
    tag = node[0]
    if tag == 'leaf':
        oldF = frozenset(node[1])
        cert = node[2]
        if set(oldF) != set(F):
            return None
        stats['nodes'] += 1
        if cert.get('kind') == 'empty':
            i = cert['job']
            if not allowed_times(inst, h, i, F):
                stats['reuse'] += 1
                stats['empty'] += 1
                return ('empty', frozenset(F), i)
        else:
            try:
                if verify(inst, h, cert, forbid=F):
                    stats['reuse'] += 1
                    return ('leaf', frozenset(F), cert)
            except Exception:
                pass
        stats['new_lp'] += 1
        nc = integer_certificate(inst, h, use_dom=True, forbid=F)
        if nc is not None:
            try:
                if verify(inst, h, nc, forbid=F):
                    return ('leaf', frozenset(F), nc)
            except Exception:
                pass
        for i in range(inst['n']):
            if not allowed_times(inst, h, i, F):
                stats['empty'] += 1
                return ('empty', frozenset(F), i)
        stats['fail'] += 1
        return None

    if tag == 'empty':
        i = int(node[2])
        stats['nodes'] += 1
        if not allowed_times(inst, h, i, F):
            stats['reuse'] += 1
            stats['empty'] += 1
            return ('empty', frozenset(F), i)
        stats['fail'] += 1
        return None

    _, i, mid, pF, lo, hi = node
    if set(pF) != set(F):
        return None
    stats['nodes'] += 1
    times = allowed_times(inst, h, i, F)
    hi_t = [t for t in times if t > mid]
    lo_t = [t for t in times if t <= mid]
    if not hi_t:
        stats['collapse'] += 1
        return _repair_node(inst, hi, F, h, stats)
    if not lo_t:
        stats['collapse'] += 1
        return _repair_node(inst, lo, F, h, stats)
    Flo = frozenset(F) | frozenset((i, t) for t in lo_t)
    Fhi = frozenset(F) | frozenset((i, t) for t in hi_t)
    a = _repair_node(inst, hi, Fhi, h, stats)
    if a is None:
        return None
    b = _repair_node(inst, lo, Flo, h, stats)
    if b is None:
        return None
    return ('split', i, mid, frozenset(F), b, a)


def repair_branch(inst, proof, h2):
    """Try to lift a BranchProof from proof.h to h2 > proof.h."""
    if proof is None or getattr(proof, 'kind', None) != 'branch':
        return None, _new_stats()
    if h2 <= proof.h:
        return proof, _new_stats()
    stats = _new_stats()
    tree = _repair_node(inst, proof.tree, proof.forbid0, h2, stats)
    if tree is None:
        return None, stats
    q = BranchProof(inst, h2, tree, stats={}, forbid0=proof.forbid0)
    if not q.audit_rdf():
        stats['fail'] += 1
        return None, stats
    return q, stats


def repair_any(inst, proof, h2):
    """Lift the proof kinds that carry a horizon-independent witness.

    BoundProof is deliberately excluded: its value proves NO(value-1)
    only, so re-stamping it above value-1 would be unsound.  The caller
    can still fall back to the ordinary probe.
    """
    if proof is None:
        return None, _new_stats()
    kind = getattr(proof, 'kind', None)
    if kind == 'branch':
        return repair_branch(inst, proof, h2)
    if kind in ('farkas', 'energy'):
        try:
            import copy
            q = copy.copy(proof)
            q.h = h2
            if q.audit_rdf():
                st = _new_stats()
                st['reuse'] += 1
                return q, st
        except Exception:
            pass
        return None, _new_stats()
    if kind == 'lb-no':
        src = getattr(proof, 'source', None)
        if src is not None and getattr(src, 'h', -1) >= h2:
            st = _new_stats()
            st['reuse'] += 1
            return SubsumptionProof(inst, h2, src), st
        return None, _new_stats()
    return None, _new_stats()


def lift_proof(inst, proof, U, max_steps=None, time_limit=None):
    """Greedy synchronous lift; returns (proof, h_reached, stats)."""
    st = dict(steps=0, reuse=0, new_lp=0, nodes=0, fail=0,
              empty=0, collapse=0, t=0.0)
    t0 = time.time()
    h = proof.h if proof is not None else -1
    while proof is not None and h < U - 1:
        if max_steps is not None and st['steps'] >= max_steps:
            break
        if time_limit is not None and time.time() - t0 >= time_limit:
            break
        q, s = repair_any(inst, proof, h + 1)
        st['steps'] += 1
        for k in ('reuse', 'new_lp', 'nodes', 'fail', 'empty',
                  'collapse'):
            st[k] += s.get(k, 0)
        if q is None:
            st['fail'] += 1
            break
        proof, h = q, h + 1
    st['t'] = round(time.time() - t0, 4)
    return proof, h, st


def _initial(inst, initial):
    if initial is not None:
        L, U, s, m, proof = initial
        return (int(L), int(U), list(s), list(m), proof, None)
    co = PACT(inst, pact_mode='complete', use_ga=False)
    L, U, s, m = co.initial_bounds()
    if U is None:
        return None
    proof = co._ensure_lb_proof(L)
    if proof is None:
        r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            proof = r['proof']
    return (int(L), int(U), list(s), list(m), proof, co)


def run_lift_icf(inst, known, name, idx, policy='lower-first',
                 max_probes=64, initial=None, lift=True, lift_cap=None,
                 lift_time=None, audit_every=True):
    """ICF loop with an incremental certificate lift after every NO."""
    t0 = time.time()
    got = _initial(inst, initial)
    if got is None:
        return dict(name=name, idx=idx, known=known, ok=False,
                    certified=False, error='no-initial-ub', t=0.0)
    L, U, s, m, proof, co = got
    if proof is None:
        return dict(name=name, idx=idx, known=known, ok=False,
                    certified=False, error='no-lb-proof', t=0.0)
    probes = search_lp = search_cert_lp = pin_lp = 0
    lift_steps = lift_lp = lift_reuse = lift_nodes = lift_fail = 0
    lift_time_total = 0.0
    partial_ok = partial_fail = 0
    unknown = 0
    steps = []
    first = True
    lb0, ub0 = L, U
    policy = policy or 'lower-first'
    policy = 'gap:4' if policy in ('pact', 'gap4') else policy

    def audit():
        nonlocal partial_ok, partial_fail
        if not audit_every:
            return
        pc = PartialCertificate(inst, L, U, s, m, proof,
                                probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1

    audit()
    while L < U and probes < max_probes:
        if policy == 'relower':
            h = L
        elif policy == 'lower-first':
            h = L if first else (L + U) // 2
        else:
            h = _choose_h(policy, L, U, first)
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        probes += 1
        first = False
        search_lp += r.get('lp_solves', 0)
        search_cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False:
            proof = r['proof']
            L = h + 1
            lifted = 0
            if lift and L < U:
                q, hq, st = lift_proof(
                    inst, proof, U,
                    max_steps=lift_cap, time_limit=lift_time)
                lift_steps += st['steps']
                lift_lp += st['new_lp']
                lift_reuse += st['reuse']
                lift_nodes += st['nodes']
                lift_fail += st['fail']
                lift_time_total += st['t']
                if q is not None and hq >= L:
                    proof = q
                    lifted = hq + 1 - L
                    L = hq + 1
            steps.append(dict(h=h, v=False, L0=h + 1, L1=L,
                              lifted=lifted,
                              lp=r.get('lp_solves', 0), t=r.get('t', 0)))
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                s, m = list(s2), list(m2)
            steps.append(dict(h=h, v=True, cmax=c2,
                              lp=r.get('lp_solves', 0)))
        else:
            unknown += 1
            steps.append(dict(h=h, v=None, lp=r.get('lp_solves', 0)))
            break
        audit()

    final = ICFCertificate(inst, U, s, m, proof) if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, L, U, s, m, proof)
    partial_final = bool(partial.audit_rdf())
    dt = time.time() - t0
    total_lp = search_lp + search_cert_lp + lift_lp + pin_lp
    return dict(
        name=name, idx=idx, known=known, policy=policy, lift=bool(lift),
        opt=U, lb=L, lb0=lb0, ub0=ub0, gap0=ub0 - lb0,
        certified=bool(L == U and final_ok),
        audit=final_ok, proof=final_ok,
        cert_h=(U - 1 if L == U else None),
        probes=probes, queries=probes,
        search_lp=search_lp, search_cert_lp=search_cert_lp,
        lift_lp=lift_lp, lift_reuse=lift_reuse, lift_steps=lift_steps,
        lift_nodes=lift_nodes, lift_fail=lift_fail,
        lift_t=round(lift_time_total, 4),
        total_lp=total_lp,
        partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_final, unknown=unknown,
        steps=steps,
        proof_kind=getattr(proof, 'kind', None),
        t=round(dt, 4),
        ok=bool(L == U and U == known and final_ok and
                partial_fail == 0 and partial_final),
    )
