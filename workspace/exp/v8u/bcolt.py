"""v10.1 BCOLT: batched cache-oblivious LP-pruned tree over ICF.

BCOLT keeps the v9.0 ICF frontier invariant but changes the unit of work
from a single probe to a *horizon batch*:

    h = min { L_f : f open }

All open leaves with local lower bound h are processed against one
master LP P(h).  A leaf F is the same matrix with the columns in F fixed
to zero.  If P(F,h) is infeasible, the leaf closes with a Farkas
certificate and contributes h+1; if it is integral, the LP gives a
schedule and U shrinks to h (lower-first closure); if it is fractional,
the leaf splits and the children stay in the same batch.

The two new ingredients are:

  * LP asset reuse: one SDLP matrix per horizon h, not one per probe.
    The cache ``lp_by_h`` survives U updates because P(h) does not
    depend on U.
  * Cache-oblivious batching: a batch is a contiguous set of leaves
    sharing the same matrix; the DFS traversal keeps the matrix and the
    active bound vectors hot.  The certificate tree is vEB-layout
    compatible (see colt.veb_index).

The correctness argument is the v9.0 frontier invariant.  A batch that
closes every leaf at h raises the global lower bound to h+1.  A batch
that finds an integral schedule at h proves OPT <= h; since the frontier
already proves NO(h-1), it also proves OPT >= h, so the bracket closes.
A batch that stops early leaves a valid partial certificate.
"""
import sys
import time
import heapq

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from cert import integer_certificate, verify
from pact import pact_decide
from rdf import check_schedule
from icf import cmax, CertLeafProof
from sage import _domain
from tamo import (Leaf, Split, collect_leaves, snapshot, tree_depth,
                  box_measure, allowed_times, close_empty,
                  TamoFrontier, TamoPartialCertificate, TamoCertificate,
                  pact_initial)
from colt import (MasterLP, RebuildLP, _farkas_proof, _candidate_jobs,
                  _split_box, _weighted_mid, _total_frac, _frac_dist,
                  veb_index, tree_height)


class LooseLeafProof(CertLeafProof):
    """Farkas proof for the full-capacity relaxation.

    ``elig_aware=False`` drops the per-machine eligibility rows, so an
    infeasibility certificate is valid for the original problem as well
    (the relaxation has more schedules).  Some boxes only admit a
    certificate in this weaker model; this wrapper keeps the audit
    honest about which model was used.
    """

    def __init__(self, inst, h, F, cert, elig_aware=False):
        super().__init__(inst, h, F, cert)
        self.elig_aware = elig_aware

    def audit_rdf(self):
        try:
            c = self.cert
            if c is None:
                return False
            if c.get('kind') == 'empty':
                i = c['job']
                lo, hi = _domain(self.inst, self.h, i)
                return all((i, t) in self.forbid0
                           for t in range(lo, hi + 1))
            return bool(verify(self.inst, self.h, c,
                               forbid=self.forbid0,
                               elig_aware=self.elig_aware))
        except Exception:
            return False


def _farkas_proof_loose(inst, H, F):
    cert = integer_certificate(inst, H, forbid=F, elig_aware=False)
    if cert is not None and verify(inst, H, cert, forbid=F,
                                   elig_aware=False):
        return LooseLeafProof(inst, H, F, cert, elig_aware=False)
    return None


def split_leaf_at(inst, leaf, i, mid, h, H0):
    """Split a leaf on job i at the local horizon h."""
    times = allowed_times(inst, h, i, leaf.F)
    le = [t for t in times if t <= mid]
    gt = [t for t in times if t > mid]
    if not le or not gt:
        return None
    F_le = leaf.F | frozenset((i, t) for t in gt)
    F_gt = leaf.F | frozenset((i, t) for t in le)
    sp = Split(leaf.F, i, mid)
    sp.lo = Leaf(F_le, leaf.L, leaf.proof,
                 box_measure(inst, H0, F_le), sp, 'lo')
    sp.hi = Leaf(F_gt, leaf.L, leaf.proof,
                 box_measure(inst, H0, F_gt), sp, 'hi')
    return sp


def run_bcolt(inst, known, name, idx, initial=None, split='frac',
              strong_k=3, subsumption=True, master_reuse=True,
              max_nodes=200000, max_time=120.0, audit_every=False,
              include_tree=False, debug=False):
    t0 = time.time()
    if initial is None:
        try:
            L0, U0, s, m, proof0 = pact_initial(inst)
        except Exception as exc:
            return dict(name=name, idx=idx, known=known, ok=False,
                        error=str(exc), t=0.0)
    else:
        L0, U0, s, m, proof0 = initial
    L0, U0 = int(L0), int(U0)
    s, m = list(s), list(m)
    if not check_schedule(inst, cmax(inst, s), s, m):
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='bad-initial-schedule', t=0.0)

    H0 = U0 - 1
    root = Leaf(frozenset(), L0, proof0,
                box_measure(inst, H0, frozenset()))
    holder = [root]
    open_ids = {id(root)}
    open_leaves = [root]
    closed_boxes = []
    U = U0
    L = L0

    nodes = lp_solves = cert_lp = strong_lp = fallback_lp = 0
    splits = yes = no = subsumed = bound_closed = empty_closed = 0
    max_open = 1
    partial_checks = partial_fail = 0
    batches = 0
    lp_by_h = {}
    lp_cache = {}

    def get_master(h):
        if not master_reuse:
            return None
        mp = lp_by_h.get(h)
        if mp is None:
            mp = MasterLP(inst, h)
            lp_by_h[h] = mp
        return mp

    def solve_box(h, F):
        nonlocal lp_solves
        key = (h, F)
        if key in lp_cache:
            return lp_cache[key]
        if master_reuse:
            mp = get_master(h)
            res = mp.solve(F)
        else:
            mp = RebuildLP(inst, h, F)
            res = mp.solve(F)
        lp_solves += 1
        lp_cache[key] = (mp, res)
        return mp, res

    def state_audit():
        nonlocal partial_checks, partial_fail
        fp = TamoFrontier(inst, U - 1, snapshot(holder[0]))
        pc = TamoPartialCertificate(inst, U - 1, fp, s, m,
                                    probe=nodes)
        partial_checks += 1
        if not pc.audit_rdf():
            partial_fail += 1
            if debug:
                print('AUDIT FAIL', name, idx, 'U', U, 'nodes', nodes)

    def close_leaf(leaf, h, proof, why):
        nonlocal no, subsumed, bound_closed, empty_closed
        leaf.closed = True
        leaf.h = int(h)
        leaf.proof = proof
        open_ids.discard(id(leaf))
        closed_boxes.append((leaf.F, int(h), proof))
        if why == 'no':
            no += 1
        elif why == 'subsume':
            subsumed += 1
        elif why == 'bound':
            bound_closed += 1
        elif why == 'empty':
            empty_closed += 1

    def try_subsumption(leaf):
        if not subsumption:
            return False
        best = None
        for Fc, hc, pc in closed_boxes:
            if Fc <= leaf.F and hc >= leaf.L:
                if best is None or hc > best[0]:
                    best = (hc, pc)
        if best is None:
            return False
        hc, pc = best
        leaf.proof = pc
        leaf.L = hc + 1
        if leaf.L >= U:
            close_leaf(leaf, leaf.L - 1, leaf.proof, 'bound')
        else:
            subsumed += 1
        return True

    def close_bound_leaves():
        """Close every open leaf whose local bound already reaches U."""
        for leaf in list(open_leaves):
            if id(leaf) in open_ids and not leaf.closed and leaf.L >= U:
                close_leaf(leaf, leaf.L - 1, leaf.proof, 'bound')

    def raise_no(leaf, h, proof):
        """The box has no schedule at h: raise its local bound to h+1."""
        nonlocal no
        leaf.proof = proof
        leaf.L = h + 1
        no += 1
        if leaf.L >= U:
            close_leaf(leaf, leaf.L - 1, leaf.proof, 'bound')
        return 'raise'

    def close_no(leaf, h):
        nonlocal cert_lp, fallback_lp
        proof = _farkas_proof(inst, h, leaf.F)
        cert_lp += 1
        if proof is None:
            proof = _farkas_proof_loose(inst, h, leaf.F)
            cert_lp += 1
        if proof is not None:
            return raise_no(leaf, h, proof)
        r = pact_decide(inst, h, depthcap=None, nodecap=1,
                        forbid0=leaf.F)
        fallback_lp += r.get('lp_solves', 0)
        cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False and r['proof'] is not None \
                and r['proof'].audit_rdf():
            return raise_no(leaf, h, r['proof'])
        if r['verdict'] is True:
            c = cmax(inst, r['schedule'])
            if c < U and check_schedule(inst, c, r['schedule'],
                                        r['machine']):
                return ('yes', c, r['schedule'], r['machine'])
        return False

    def choose_split(leaf, z, mp, h):
        nonlocal strong_lp
        if split == 'domain':
            best = None
            for i in range(inst['n']):
                times = allowed_times(inst, h, i, leaf.F)
                if len(times) >= 2 and (best is None or
                                        len(times) > best[0]):
                    best = (len(times), i, times[len(times) // 2 - 1])
            if best is None:
                return None
            return best[1], best[2]
        if split == 'oracle':
            r = pact_decide(inst, h, depthcap=1, nodecap=1,
                            forbid0=leaf.F)
            bj = r.get('branch_jobs') or []
            if bj:
                i, mid = int(bj[0][0]), int(bj[0][1])
                if _split_box(inst, h, leaf.F, i, mid) is not None:
                    return i, mid
            return None
        cand = _candidate_jobs(mp, z, leaf.F,
                               strong_k if split == 'strong' else 1)
        if not cand:
            return None
        if split == 'strong' and len(cand) > 1:
            best = None
            for frac, total, negi, i, dist in cand:
                mid = _weighted_mid(dist, total)
                sp = _split_box(inst, h, leaf.F, i, mid)
                if sp is None:
                    continue
                F0, F1 = sp
                mp0, r0 = solve_box(h, F0)
                mp1, r1 = solve_box(h, F1)
                strong_lp += 2
                closed = int(r0.status == 2) + int(r1.status == 2)
                fr = 0.0
                if r0.status == 0:
                    fr += _total_frac(mp0, r0.x, F0)
                if r1.status == 0:
                    fr += _total_frac(mp1, r1.x, F1)
                score = (closed, -fr, -frac)
                if best is None or score > best[0]:
                    best = (score, i, mid)
            if best is None:
                return None
            return best[1], best[2]
        frac, total, negi, i, dist = cand[0]
        mid = _weighted_mid(dist, total)
        return i, mid

    def oracle_on_leaf(leaf, h):
        nonlocal U, s, m, yes, fallback_lp, cert_lp
        r = pact_decide(inst, h, depthcap=None, nodecap=None,
                        forbid0=leaf.F)
        fallback_lp += r.get('lp_solves', 0)
        cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False and r['proof'] is not None \
                and r['proof'].audit_rdf():
            close_leaf(leaf, h, r['proof'], 'no')
        elif r['verdict'] is True:
            c = cmax(inst, r['schedule'])
            if c < U and check_schedule(inst, c, r['schedule'],
                                        r['machine']):
                U = c
                s = list(r['schedule'])
                m = list(r['machine'])
                yes += 1
                return 'yes'
        return None

    def process(leaf, h):
        nonlocal U, s, m, yes, nodes
        if try_subsumption(leaf):
            return None
        if leaf.L >= U:
            close_leaf(leaf, leaf.L - 1, leaf.proof, 'bound')
            return None
        if close_empty(inst, leaf, h):
            open_ids.discard(id(leaf))
            closed_boxes.append((leaf.F, h, leaf.proof))
            return None
        nodes += 1
        mp, res = solve_box(h, leaf.F)
        if res.status == 2:
            out = close_no(leaf, h)
            if isinstance(out, tuple) and out and out[0] == 'yes':
                _, c, s2, m2 = out
                U = c
                s = list(s2)
                m = list(m2)
                yes += 1
                return 'yes'
            return None if out is False else out
        if res.status != 0:
            return oracle_on_leaf(leaf, h)
        sol = mp.integral(res.x)
        if sol is not None:
            starts, machs = sol
            c = cmax(inst, starts)
            if c < U and check_schedule(inst, c, starts, machs):
                U = c
                s = list(starts)
                m = list(machs)
                yes += 1
                return 'yes'
        ch = choose_split(leaf, res.x, mp, h)
        if ch is None:
            return oracle_on_leaf(leaf, h)
        i, mid = ch
        sp = split_leaf_at(inst, leaf, i, mid, h, H0)
        if sp is None:
            return None
        if leaf.parent is None:
            holder[0] = sp
        elif leaf.side == 'lo':
            leaf.parent.lo = sp
        else:
            leaf.parent.hi = sp
        open_ids.discard(id(leaf))
        try:
            open_leaves.remove(leaf)
        except ValueError:
            pass
        for c in (sp.lo, sp.hi):
            open_ids.add(id(c))
            open_leaves.append(c)
        nonlocal splits, max_open
        splits += 1
        max_open = max(max_open, len(open_ids))
        return 'split', sp

    # ---------------------------------------------------------- main loop
    while open_ids and L < U and nodes < max_nodes \
            and time.time() - t0 < max_time:
        close_bound_leaves()
        if not open_ids:
            L = U
            break
        h = min(l.L for l in open_leaves
                if id(l) in open_ids and not l.closed)
        if h >= U:
            close_bound_leaves()
            L = U
            break
        batches += 1
        stack = [l for l in open_leaves
                 if id(l) in open_ids and not l.closed and l.L == h]
        stack.reverse()
        found_yes = False
        while stack:
            while stack and (id(stack[-1]) not in open_ids
                             or stack[-1].closed or stack[-1].L != h):
                stack.pop()
            if not stack:
                break
            leaf = stack.pop()
            out = process(leaf, h)
            if out == 'yes':
                found_yes = True
                break
            if out is not None and out[0] == 'split':
                sp = out[1]
                for c in (sp.hi, sp.lo):
                    if id(c) in open_ids:
                        stack.append(c)
            if nodes >= max_nodes or time.time() - t0 >= max_time:
                break
        if audit_every:
            state_audit()
        if found_yes:
            # OPT <= h and the frontier already proves NO(h-1), so the
            # bracket closes at h.  Close every remaining open leaf at
            # its own proof horizon.
            close_bound_leaves()
            if not open_ids:
                L = U
                break
            # If U < h (should not happen), leave the partial state.
            if U <= h:
                L = U
                break
        # If every leaf at h is gone, the whole frontier proves NO(h).
        if not any(id(l) in open_ids and not l.closed and l.L == h
                   for l in open_leaves):
            L = h + 1
        if L >= U:
            L = U
            break

    # ---------------------------------------------------------- finalize
    leaves = []
    collect_leaves(holder[0], leaves)
    for l in leaves:
        if id(l) in open_ids and not l.closed and l.L >= U:
            l.closed = True
            l.h = l.L - 1
            open_ids.discard(id(l))
    open_left = [l for l in leaves if id(l) in open_ids and not l.closed]
    if open_left and (nodes >= max_nodes or time.time() - t0 >= max_time):
        stop_reason = 'budget'
    elif open_left:
        stop_reason = 'open'
    else:
        stop_reason = 'closed'

    fp = TamoFrontier(inst, U - 1, snapshot(holder[0]))
    fp_ok = bool(fp.audit_rdf())
    Lf = fp.L if fp_ok else None
    if not open_left:
        cert = TamoCertificate(inst, U - 1, fp, s, m)
        final_ok = bool(cert.audit_rdf())
    else:
        cert = None
        final_ok = False
    partial = TamoPartialCertificate(inst, U - 1, fp, s, m,
                                     probe=nodes)
    partial_final = bool(partial.audit_rdf())
    dt = time.time() - t0
    out = dict(
        name=name, idx=idx, known=known, alg='bcolt',
        split=split, master_reuse=bool(master_reuse),
        subsumption=bool(subsumption),
        L0=L0, U0=U0, L=Lf, U=U, opt=U,
        nodes=nodes, lp=lp_solves, cert_lp=cert_lp,
        strong_lp=strong_lp, fallback_lp=fallback_lp,
        splits=splits, yes=yes, no=no, subsumed=subsumed,
        bound_closed=bound_closed, empty_closed=empty_closed,
        leaves=len(leaves), open=len(open_left), max_open=max_open,
        depth=tree_depth(holder[0]), batches=batches,
        lp_horizons=len(lp_by_h),
        partial_checks=partial_checks, partial_fail=partial_fail,
        frontier_ok=fp_ok,
        certified=bool(not open_left and Lf == U and final_ok),
        audit=final_ok, proof=final_ok,
        partial_final=partial_final, stop_reason=stop_reason,
        cert_h=(U - 1 if not open_left and Lf == U else None),
        t=round(dt, 4),
        ok=bool(not open_left and Lf == U == known and final_ok
                and partial_fail == 0),
    )
    if include_tree:
        out['tree'] = snapshot(holder[0])
        out['schedule'] = s
        out['machine'] = m
    return out
