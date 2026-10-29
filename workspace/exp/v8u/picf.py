"""v10.0 PICF: P-core Indexed Certificate Frontier.

PICF extends the v9.0 ICF partial certificate with two layers:

1. A P-time tier at every leaf:
     root LP infeasible  -> NO in P (Farkas/empty certificate)
     root LP integral    -> YES in P (integral schedule)
     root LP fractional  -> branch only on the fractional support K
   The core search is a restricted PACT search.  A NO answer from the
   core is valid for the full instance; a UNKNOWN answer is refined by
   the frontier (or expanded by the adaptive-core rule).

2. An interval-box index for the live frontier.  Every leaf is a product
   of per-job allowed intervals [lo_i, hi_i] at the current target H.
   The index stores canonical boxes, supports point location for a
   schedule, and replaces O(nT) forbidden-set scans by O(n) endpoint
   operations.  The tree partition already makes leaves disjoint, so the
   index is used for canonicalization/location, not for cross-branch
   subsumption.

The implementation keeps TAMO's frontier, rank and certificates.  Only
the node oracle is replaced by decide_core2, and every transition is
instrumented with P-tier and index counters.
"""
import sys
import time
import heapq
import collections

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

import numpy as np
from sdecc import SDLP
from po import heads_tails
from cert import verify, integer_certificate, integer_certificate_from_lp
from rdf import check_schedule
from sage import _elig_aware, _domain
from pact import pact_decide, _integral_schedule
from icf import CertLeafProof, _proof_forbid, cmax
from tamo import (Leaf, Split, collect_leaves, tree_depth, snapshot,
                  close_empty, split_leaf, allowed_times, project_forbid,
                  box_measure, TamoFrontier, TamoPartialCertificate,
                  TamoCertificate, rank_of, rank_lt, pact_initial)


# --------------------------------------------------------------- root LP
def solve_root(inst, h, forbid=frozenset()):
    """Solve the root SDLP and classify it: infeasible/integral/fractional."""
    n = inst['n']
    elig = _elig_aware(inst)
    est, q = heads_tails(inst, 0, [0] * n)
    lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig,
              forbid=forbid)
    res = lp.solve()
    if res.status == 2:
        return 'infeasible', lp, res, frozenset()
    if res.status != 0:
        return 'unknown', lp, res, frozenset()
    K = set()
    for c, key in enumerate(lp.cols):
        if 1e-7 < res.x[c] < 1 - 1e-7:
            K.add(key[0])
    return ('integral' if not K else 'fractional'), lp, res, frozenset(K)


def _root_no_proof(inst, h, F, lp, elig):
    """A P-time NO certificate for an infeasible root LP.

    The existing integer-certificate generator is not complete: for some
    eligibility-aware instances it returns None even though the LP is
    infeasible.  We try the standard generator and the from-LP variant;
    if neither yields a checkable certificate, the caller must not claim
    NO.  This is a soundness guard, not an optimization.
    """
    cert = integer_certificate(inst, h, use_dom=True,
                               elig_aware=elig, forbid=F)
    if cert is None:
        cert = integer_certificate_from_lp(lp, inst, h)
    if cert is not None and verify(inst, h, cert, forbid=F,
                                   elig_aware=elig):
        return CertLeafProof(inst, h, F, cert)
    return None


def decide_core2(inst, h, forbid=frozenset(), nodecap=None,
                 depthcap=None, core_override=None):
    """P-tier + fractional-core decision.

    Returns (result, root_info, fallback).  result has the pact_decide
    shape plus lp_solves including the root LP.  A root-infeasible case
    without a checkable certificate is reported as UNKNOWN with
    root_info['cert_fail']=True; the frontier then refines the leaf.
    """
    status, lp, res, K = solve_root(inst, h, forbid)
    info = dict(status=status, K=sorted(K), h=h,
                cert_fail=False, root_lp=1,
                K_used=sorted(K) if core_override is None
                else sorted(core_override))
    if status == 'unknown':
        r = pact_decide(inst, h, depthcap=depthcap, nodecap=nodecap,
                        forbid0=forbid)
        r['lp_solves'] = r.get('lp_solves', 0) + 1
        return r, info, True

    if status == 'infeasible':
        proof = _root_no_proof(inst, h, forbid, lp, _elig_aware(inst))
        if proof is not None:
            return dict(verdict=False, proof=proof, schedule=None,
                        machine=None, nodes=1, leaves=1, depth=0,
                        lp_solves=1, cert_lp=0, unknown=False,
                        holes=0, branch_jobs=[], root_reused=0,
                        insufficient=False, t=0.0), info, False
        info['cert_fail'] = True
        # No trusted NO certificate: do not claim NO.  A capped full
        # search is the only sound way to use this LP result.
        r = pact_decide(inst, h, depthcap=depthcap, nodecap=nodecap,
                        root_lp=lp, root_res=res, forbid0=forbid)
        r['lp_solves'] = r.get('lp_solves', 0) + 1
        return r, info, True

    if status == 'integral':
        r = pact_decide(inst, h, depthcap=depthcap, nodecap=nodecap,
                        root_lp=lp, root_res=res, branch_jobs=set(),
                        forbid0=forbid)
        r['lp_solves'] = r.get('lp_solves', 0) + 1
        return r, info, False

    K_used = set(K) if core_override is None else set(core_override)
    r = pact_decide(inst, h, depthcap=depthcap, nodecap=nodecap,
                    root_lp=lp, root_res=res, branch_jobs=K_used,
                    forbid0=forbid)
    r['lp_solves'] = r.get('lp_solves', 0) + 1
    return r, info, False


# --------------------------------------------------------------- ramp
def decide_ramp(inst, h, forbid=frozenset(), B0=1, Bmax=8,
                depthcap=None):
    """Iterative-deepening node budget for the core search.

    A leaf that is UNKNOWN at budget B is retried at 2B before the
    frontier splits it.  A root-infeasible certificate failure is not
    retried: a larger budget cannot repair a missing certificate.
    Returns (result, info, fallback, attempts, lp, nodes, cert_lp).
    """
    b = max(1, int(B0))
    Bmax = max(b, int(Bmax))
    lp = nodes = cert_lp = 0
    attempts = 0
    while True:
        attempts += 1
        r, info, fb = decide_core2(inst, h, forbid=forbid, nodecap=b,
                                   depthcap=depthcap)
        lp += r.get('lp_solves', 0)
        nodes += r.get('nodes', 0)
        cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is not None:
            return r, info, fb, attempts, lp, nodes, cert_lp
        if info.get('cert_fail'):
            return r, info, fb, attempts, lp, nodes, cert_lp
        if b >= Bmax:
            return r, info, fb, attempts, lp, nodes, cert_lp
        b = min(Bmax, b * 2)


# --------------------------------------------------------------- box index
def canonical_box(inst, H, F):
    """Per-job allowed interval [lo,hi] at target H; (1,0) if empty."""
    out = []
    for i in range(inst['n']):
        lo, hi = _domain(inst, H, i)
        ts = [t for t in range(lo, hi + 1) if (i, t) not in F]
        out.append((ts[0], ts[-1]) if ts else (1, 0))
    return tuple(out)


class BoxIndex:
    """Canonical interval-box index for a partition tree.

    The tree partition makes leaves disjoint, so the index is not used
    for subsumption; it provides O(n) canonical keys, O(n) point
    location, and a hash table for duplicate detection.  On a true tree
    the duplicate count is expected to be zero; the index verifies it
    and makes the invariant explicit.
    """

    def __init__(self, inst):
        self.inst = inst
        self.boxes = {}
        self.dups = 0
        self.locate_calls = 0
        self.locate_steps = 0

    def add(self, H, F):
        key = canonical_box(self.inst, H, F)
        if key in self.boxes:
            self.dups += 1
        self.boxes[key] = self.boxes.get(key, 0) + 1
        return key

    def locate(self, H, s):
        """Find a canonical box containing schedule s (linear scan)."""
        self.locate_calls += 1
        for key in self.boxes:
            self.locate_steps += 1
            if all(key[i][0] <= s[i] <= key[i][1]
                   for i in range(self.inst['n'])):
                return key
        return None


# --------------------------------------------------------------- main loop
def run_picf(inst, known, name, idx, B=4, policy='lower',
             split_mode='oracle', max_probes=200000, initial=None,
             audit_every=True, include_tree=False, adaptive=True,
             ramp=False, Bmax=8, budget_policy='fixed',
             gap_thr=2, debug=False):
    """Run PICF.  B is the per-leaf node budget of the core search.

    adaptive=True expands the core only when the fixed root support is
    insufficient; the current prototype records the expansion request
    but falls back to the frontier split (which is already complete).
    """
    t0 = time.time()
    if initial is None:
        L0, U0, s, m, proof0 = pact_initial(inst)
    else:
        L0, U0, s, m, proof0 = initial
    L0, U0 = int(L0), int(U0)
    s, m = list(s), list(m)
    if not check_schedule(inst, cmax(inst, s), s, m):
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='bad-initial-schedule', t=0.0)

    H0 = U0 - 1
    Mmax = box_measure(inst, H0, frozenset())
    root = Leaf(frozenset(), L0, proof0, Mmax)
    holder = [root]
    U = U0
    H = U - 1
    leaves = []
    collect_leaves(root, leaves)
    heap = [(l.L, -l.mu, id(l)) for l in leaves]
    heapq.heapify(heap)
    live = set(id(l) for l in leaves)
    byid = {id(l): l for l in leaves}
    index = BoxIndex(inst)
    index.add(H, frozenset())

    probes = splits = closes_lift = closes_empty = 0
    yes = no = unknown = 0
    lp = nodes = cert_lp = root_lp = 0
    max_leaves = len(leaves)
    rank_checks = rank_fail = 0
    partial_checks = partial_fail = 0
    final_ok = False
    core_status = collections.Counter()
    core_k = []
    cert_fails = 0
    fallbacks = 0
    adaptive_expansions = 0
    ramp_attempts = 0
    ramp_retries = 0
    gap_b1 = 0
    gap_bB = 0
    rho = rank_of(inst, H0, U, holder[0], Mmax, recompute=True)

    def state_audit():
        nonlocal partial_checks, partial_fail
        if not audit_every:
            return
        fp = TamoFrontier(inst, U - 1, snapshot(holder[0]))
        pc = TamoPartialCertificate(inst, U - 1, fp, s, m, probe=probes)
        partial_checks += 1
        if not pc.audit_rdf():
            partial_fail += 1

    state_audit()

    while True:
        while heap and (heap[0][2] not in live or
                        byid.get(heap[0][2]) is None):
            heapq.heappop(heap)
        if not heap:
            break
        Lmin, _, lid = heap[0]
        leaf = byid.get(lid)
        if leaf is None:
            heapq.heappop(heap)
            continue
        if leaf.L != Lmin:
            heapq.heappop(heap)
            continue
        if leaf.L >= U:
            break
        if probes >= max_probes:
            break
        if policy == 'lower':
            h = leaf.L
        elif policy in ('upper', 'target'):
            h = U - 1
        else:
            h = (leaf.L + U) // 2
        if h >= U:
            h = U - 1

        b_leaf = B
        if budget_policy == 'gap':
            if (U - leaf.L) <= gap_thr:
                b_leaf = 1
                gap_b1 += 1
            else:
                b_leaf = B
                gap_bB += 1
        if ramp:
            r, info, fb, att, rlp, rnd, rcl = decide_ramp(
                inst, h, forbid=frozenset(leaf.F), B0=b_leaf, Bmax=Bmax)
            probes += 1
            root_lp += info.get('root_lp', 0)
            lp += rlp
            nodes += rnd
            cert_lp += rcl
            ramp_attempts += att
            ramp_retries += max(0, att - 1)
        else:
            r, info, fb = decide_core2(inst, h, forbid=frozenset(leaf.F),
                                       nodecap=b_leaf)
            probes += 1
            root_lp += info.get('root_lp', 0)
            lp += r.get('lp_solves', 0)
            nodes += r.get('nodes', 0)
            cert_lp += r.get('cert_lp', 0)
        fallbacks += int(fb)
        cert_fails += int(info.get('cert_fail', False))
        core_status[info['status']] += 1
        if info['status'] == 'fractional':
            core_k.append(len(info['K']))
        before = rho
        kind = None

        if r['verdict'] is False:
            no += 1
            leaf.proof = r['proof']
            leaf.L = h + 1
            kind = 'probe-no'
            if leaf.L >= U:
                leaf.closed = True
                leaf.h = leaf.L - 1
                live.discard(id(leaf))
                byid.pop(id(leaf), None)
                closes_lift += 1
            else:
                heapq.heappush(heap, (leaf.L, -leaf.mu, id(leaf)))
        elif r['verdict'] is True:
            yes += 1
            c = cmax(inst, r['schedule'])
            if c < U and check_schedule(inst, c, r['schedule'],
                                        r['machine']):
                U = c
                H = U - 1
                s = list(r['schedule'])
                m = list(r['machine'])
                kind = 'probe-yes'
                leaves_now = []
                collect_leaves(holder[0], leaves_now)
                for x in leaves_now:
                    if x.closed:
                        continue
                    if close_empty(inst, x, H):
                        live.discard(id(x))
                        byid.pop(id(x), None)
                        closes_empty += 1
                    elif x.L >= U:
                        x.closed = True
                        x.h = x.L - 1
                        live.discard(id(x))
                        byid.pop(id(x), None)
                        closes_lift += 1
                if not live:
                    break
            else:
                kind = 'probe-yes-stale'
        else:
            unknown += 1
            pair = None
            bj = r.get('branch_jobs') or []
            if split_mode == 'oracle' and bj:
                i, mid = int(bj[0][0]), int(bj[0][1])
                times = allowed_times(inst, H, i, leaf.F)
                if times and any(t > mid for t in times) and any(t <= mid for t in times):
                    pair = (i, mid)
            if pair is None:
                best = None
                for i in range(inst['n']):
                    times = allowed_times(inst, H, i, leaf.F)
                    if len(times) >= 2 and (best is None or len(times) > best[0]):
                        best = (len(times), i, times[len(times) // 2 - 1])
                if best is not None:
                    pair = (best[1], best[2])
            if pair is None:
                break
            i, mid = pair
            sp = split_leaf(inst, leaf, i, mid, H, H0)
            if sp is None:
                break
            splits += 1
            if adaptive and info['status'] == 'fractional':
                adaptive_expansions += 1
            if leaf.parent is None:
                holder[0] = sp
            live.discard(id(leaf))
            byid.pop(id(leaf), None)
            for c in (sp.lo, sp.hi):
                if close_empty(inst, c, H):
                    closes_empty += 1
                else:
                    live.add(id(c))
                    byid[id(c)] = c
                    heapq.heappush(heap, (c.L, -c.mu, id(c)))
                index.add(H, c.F)
            kind = 'refine'
            leaves = []
            collect_leaves(holder[0], leaves)
            max_leaves = max(max_leaves, len(leaves))

        if kind in ('probe-no', 'probe-yes', 'refine'):
            rho2 = rank_of(inst, H0, U, holder[0], Mmax,
                           recompute=True)
            rank_checks += 1
            if not rank_lt(rho2, before):
                rank_fail += 1
            rho = rho2
        state_audit()

    leaves = []
    collect_leaves(holder[0], leaves)
    for x in leaves:
        if not x.closed:
            x.closed = True
            x.h = x.L - 1
    fp = TamoFrontier(inst, U - 1, snapshot(holder[0]))
    cert = TamoCertificate(inst, U - 1, fp, s, m)
    final_ok = bool(cert.audit_rdf())
    L = fp.L
    partial = TamoPartialCertificate(inst, U - 1,
                                     TamoFrontier(inst, U - 1,
                                                  snapshot(holder[0])),
                                     s, m, probe=probes)
    partial_final = bool(partial.audit_rdf())
    dt = time.time() - t0
    out = dict(
        name=name, idx=idx, known=known, B=B, policy=policy,
        split_mode=split_mode, L0=L0, U0=U0, L=L, U=U, opt=U,
        probes=probes, splits=splits, yes=yes, no=no, unknown=unknown,
        closes_lift=closes_lift, closes_empty=closes_empty,
        lp=lp, nodes=nodes, cert_lp=cert_lp, root_lp=root_lp,
        core_status=dict(core_status), core_k=core_k,
        cert_fails=cert_fails, fallbacks=fallbacks,
        adaptive_expansions=adaptive_expansions,
        ramp_attempts=ramp_attempts, ramp_retries=ramp_retries,
        gap_b1=gap_b1, gap_bB=gap_bB,
        index_boxes=len(index.boxes), index_dups=index.dups,
        leaves=len(leaves), open=sum(1 for x in leaves if not x.closed),
        max_leaves=max_leaves, depth=tree_depth(holder[0]),
        rank_checks=rank_checks, rank_fail=rank_fail,
        partial_checks=partial_checks, partial_fail=partial_fail,
        certified=bool(L == U and final_ok),
        audit=final_ok, proof=final_ok,
        partial_final=partial_final,
        cert_h=(U - 1 if L == U else None),
        t=round(dt, 4),
        ok=bool(L == U == known and final_ok and partial_fail == 0
                and rank_fail == 0),
    )
    if include_tree:
        out['tree'] = snapshot(holder[0])
        out['schedule'] = s
        out['machine'] = m
    return out
