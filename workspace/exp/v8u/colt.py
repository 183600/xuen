"""v10.0 COLT-ICF: cache-oblivious, LP-pruned frontier over ICF.

COLT keeps the v9.0 ICF state

    C = (L, U, s, m, pi),   pi : NO(L-1),  Cmax(s)=U,  L<=U,

and lifts it to a live frontier.  The new object is a *target-horizon
master LP* P(H), H = U-1.  Every leaf is a box F of forbidden start
times, and its subproblem is the same master LP with the columns in F
fixed to zero:

    P(F,H) = P(H)  with  x_{i,t,k} = 0 for (i,t) in F.

This is the linear-programming part: the matrix is built once, leaves
are bound restrictions, infeasible leaves are closed by Farkas
certificates, integral leaves give schedules, and fractional leaves are
split.  The search is a recursive depth-first traversal of the partition
tree, so the parent LP data and the active bounds stay hot; this is the
cache-oblivious scheduling part.  The final certificate tree can be
stored in van Emde Boas order, giving the standard cache-oblivious tree
traversal bound for the structural audit.

Transitions
-----------
LP-CLOSE(f)   P(F_f,H) infeasible -> closed leaf with Farkas/empty proof
LP-YES(f)     P(F_f,H) integral   -> global schedule, U shrinks, f stays open
SPLIT(f,i,m)  P(F_f,H) fractional -> two children partition the domain
SUBSUME(f)    F_closed subset F_f  -> close f with the old NO proof
BOUND(f)      L_f >= U             -> close f by horizon monotonicity

The invariant is the v9.0 frontier invariant with H = U-1.  If all leaves
close at H, the frontier is a NO(H) proof and L=U.  If the search stops
early, the same tree plus the incumbent is a valid partial certificate.

The module is deliberately a new outer loop, not a replacement of the
inner PACT oracle: pact_decide is the fallback when a Farkas certificate
or a start-time split is unavailable.
"""
import sys
import time
import heapq

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

import numpy as np

from sdecc import SDLP
from po import heads_tails
from cert import integer_certificate, verify
from pact import (PACT, pact_decide, _integral_schedule, _assign_machines,
                  _elig_aware)
from rdf import check_schedule
from sage import _domain
from icf import cmax, CertLeafProof
from tamo import (Leaf, Split, collect_leaves, snapshot, tree_depth,
                  box_measure, allowed_times, project_forbid, close_empty,
                  TamoFrontier, TamoPartialCertificate, TamoCertificate,
                  pact_initial)


# --------------------------------------------------------------- LP views
class MasterLP:
    """One SDLP matrix at a fixed horizon, solved with column bounds."""

    def __init__(self, inst, H):
        self.inst = inst
        self.H = int(H)
        n = inst['n']
        est, q = heads_tails(inst, 0, [0] * n)
        self.lp = SDLP(inst, self.H, est, q, use_dom=True,
                       elig_aware=_elig_aware(inst))
        self._index()

    def _index(self):
        self.N = self.lp.N
        self.cols = list(self.lp.cols)
        self.by_it = {}
        self.by_job = [[] for _ in range(self.inst['n'])]
        for c, key in enumerate(self.cols):
            i, t = key[0], key[-1]
            self.by_it.setdefault((i, t), []).append(c)
            self.by_job[i].append((c, t))

    def bounds(self, F):
        b = [(0, 1)] * self.N
        for it in F:
            for c in self.by_it.get(it, ()):
                b[c] = (0, 0)
        return b

    def solve(self, F):
        return self.lp.solve(self.bounds(F))

    def integral(self, z):
        sol = self.lp.integral_solution(z)
        if sol is None:
            return None
        starts = [x[0] for x in sol]
        machs = [x[1] for x in sol]
        if machs[0] is None:
            machs = _assign_machines(self.inst, starts)
        if machs is None:
            return None
        return starts, machs


class RebuildLP(MasterLP):
    """Ablation: rebuild the SDLP with ``forbid=F`` for every leaf."""

    def __init__(self, inst, H, F):
        self.inst = inst
        self.H = int(H)
        self.F = frozenset(F)
        n = inst['n']
        est, q = heads_tails(inst, 0, [0] * n)
        self.lp = SDLP(inst, self.H, est, q, use_dom=True,
                       elig_aware=_elig_aware(inst), forbid=self.F)
        self._index()

    def solve(self, F=None):
        return self.lp.solve()


# --------------------------------------------------------------- helpers
def _frac_dist(mp, z, i, F):
    dist = []
    for c, t in mp.by_job[i]:
        if (i, t) in F:
            continue
        dist.append((t, float(z[c])))
    if not dist:
        return None
    dist.sort()
    total = sum(v for _, v in dist)
    frac = sum(v for _, v in dist if 1e-7 < v < 1 - 1e-7)
    return dist, total, frac


def _weighted_mid(dist, total):
    if total <= 0:
        return dist[len(dist) // 2][0]
    acc = 0.0
    mid = dist[0][0]
    for t, v in dist:
        acc += v
        if acc >= 0.5 * total:
            mid = t
            break
    times = [t for t, _ in dist]
    if all(t <= mid for t in times):
        mid = times[max(0, len(times) // 2 - 1)]
    if all(t > mid for t in times):
        mid = times[len(times) // 2]
    return mid


def _split_box(inst, H, F, i, mid):
    times = [t for t in allowed_times(inst, H, i, F)]
    lo = [t for t in times if t > mid]
    hi = [t for t in times if t <= mid]
    if not lo or not hi:
        return None
    F0 = F | frozenset((i, t) for t in lo)
    F1 = F | frozenset((i, t) for t in hi)
    return F0, F1


def _candidate_jobs(mp, z, F, k):
    cand = []
    for i in range(mp.inst['n']):
        d = _frac_dist(mp, z, i, F)
        if d is None:
            continue
        dist, total, frac = d
        if frac <= 1e-7 or len(dist) <= 1:
            continue
        cand.append((frac, total, -i, i, dist))
    cand.sort(reverse=True)
    return cand[:k]


def _total_frac(mp, z, F):
    out = 0.0
    for i in range(mp.inst['n']):
        d = _frac_dist(mp, z, i, F)
        if d is not None:
            out += d[2]
    return out


def _farkas_proof(inst, H, F):
    cert = integer_certificate(inst, H, forbid=F)
    if cert is not None and verify(inst, H, cert, forbid=F):
        return CertLeafProof(inst, H, F, cert)
    return None


def _fallback(inst, H, F, depthcap=None, nodecap=None):
    return pact_decide(inst, H, depthcap=depthcap, nodecap=nodecap,
                       forbid0=F)


# --------------------------------------------------------------- main loop
def run_colt(inst, known, name, idx, initial=None, order='dfs',
             split='frac', strong_k=3, subsumption=True,
             master_reuse=True, max_nodes=200000, max_time=120.0,
             audit_every=False, include_tree=False, debug=False,
             mode='colt', tau=4):
    """Run COLT and return a benchmark row.

    order: 'dfs' (cache-oblivious recursive schedule), 'bfs' (heap on
           box measure), or 'veb' (heap on van Emde Boas index).
    split: 'frac', 'strong', 'domain', or 'oracle'.
    master_reuse: False rebuilds SDLP per leaf (ablation).
    """
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
    closed_boxes = []          # (F, h, proof)
    U = U0
    H = U - 1

    nodes = lp_solves = cert_lp = strong_lp = fallback_lp = 0
    probe_lp = 0
    splits = yes = no = subsumed = bound_closed = empty_closed = 0
    max_open = 1
    partial_checks = partial_fail = 0
    target_rounds = 0
    stop_reason = 'closed'

    def make_lp(F):
        return MasterLP(inst, H) if master_reuse else RebuildLP(inst, H, F)

    lp_cache = {}

    def solve_box(F):
        """Return (mp, res); cache within one target horizon."""
        nonlocal lp_solves
        if F in lp_cache:
            return lp_cache[F]
        mp = make_lp(F)
        res = mp.solve(F)
        lp_solves += 1
        lp_cache[F] = (mp, res)
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
        for Fc, hc, pc in closed_boxes:
            if Fc <= leaf.F:
                close_leaf(leaf, hc, pc, 'subsume')
                return True
        return False

    def maybe_close_empty(leaf):
        if close_empty(inst, leaf, H):
            open_ids.discard(id(leaf))
            closed_boxes.append((leaf.F, H, leaf.proof))
            return True
        return False

    def split_leaf_colt(leaf, i, mid):
        nonlocal splits, max_open
        times = allowed_times(inst, H, i, leaf.F)
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
        splits += 1
        max_open = max(max_open, len(open_ids))
        return sp

    def choose_split(leaf, z, mp):
        nonlocal strong_lp
        if split == 'domain':
            best = None
            for i in range(inst['n']):
                times = allowed_times(inst, H, i, leaf.F)
                if len(times) >= 2 and (best is None or
                                        len(times) > best[0]):
                    best = (len(times), i, times[len(times) // 2 - 1])
            if best is None:
                return None
            return best[1], best[2], None
        if split == 'oracle':
            r = _fallback(inst, H, leaf.F, depthcap=1, nodecap=1)
            bj = r.get('branch_jobs') or []
            if bj:
                i, mid = int(bj[0][0]), int(bj[0][1])
                sp = _split_box(inst, H, leaf.F, i, mid)
                if sp is not None:
                    return i, mid, None
            return None
        cand = _candidate_jobs(mp, z, leaf.F,
                               strong_k if split == 'strong' else 1)
        if not cand:
            return None
        if split == 'strong' and len(cand) > 1:
            best = None
            for frac, total, negi, i, dist in cand:
                mid = _weighted_mid(dist, total)
                sp = _split_box(inst, H, leaf.F, i, mid)
                if sp is None:
                    continue
                F0, F1 = sp
                mp0, r0 = solve_box(F0)
                mp1, r1 = solve_box(F1)
                strong_lp += 2
                closed = int(r0.status == 2) + int(r1.status == 2)
                fr = 0.0
                if r0.status == 0:
                    fr += _total_frac(mp0, r0.x, F0)
                if r1.status == 0:
                    fr += _total_frac(mp1, r1.x, F1)
                score = (closed, -fr, -frac)
                if best is None or score > best[0]:
                    best = (score, i, mid, F0, F1)
            if best is None:
                return None
            _, i, mid, F0, F1 = best
            return i, mid, (F0, F1)
        frac, total, negi, i, dist = cand[0]
        mid = _weighted_mid(dist, total)
        return i, mid, None

    def close_no_with_fallback(leaf):
        nonlocal cert_lp, fallback_lp
        proof = _farkas_proof(inst, H, leaf.F)
        cert_lp += 1
        if proof is not None:
            close_leaf(leaf, H, proof, 'no')
            return True
        r = _fallback(inst, H, leaf.F, depthcap=None, nodecap=None)
        fallback_lp += r.get('lp_solves', 0)
        cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False and r['proof'] is not None:
            if r['proof'].audit_rdf():
                close_leaf(leaf, H, r['proof'], 'no')
                return True
        return False

    def oracle_on_leaf(leaf):
        """Fallback for no-split or numerical cases; returns 'yes' or None."""
        nonlocal U, s, m, yes, fallback_lp, cert_lp
        r = _fallback(inst, H, leaf.F, depthcap=None, nodecap=None)
        fallback_lp += r.get('lp_solves', 0)
        cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False and r['proof'] is not None \
                and r['proof'].audit_rdf():
            close_leaf(leaf, H, r['proof'], 'no')
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

    def probe_leaf(leaf):
        """Lower-first probe at leaf.L with a one-node PACT oracle."""
        nonlocal U, s, m, yes, probe_lp, cert_lp
        h = leaf.L
        if h >= U:
            close_leaf(leaf, leaf.L - 1, leaf.proof, 'bound')
            return 'closed'
        if h >= H:
            return 'skip'
        r = _fallback(inst, h, leaf.F, depthcap=None, nodecap=1)
        probe_lp += r.get('lp_solves', 0)
        cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False and r['proof'] is not None \
                and r['proof'].audit_rdf():
            leaf.L = h + 1
            leaf.proof = r['proof']
            if leaf.L >= U:
                close_leaf(leaf, leaf.L - 1, leaf.proof, 'bound')
                return 'closed'
            return 'raised'
        if r['verdict'] is True:
            c = cmax(inst, r['schedule'])
            if c < U and check_schedule(inst, c, r['schedule'],
                                        r['machine']):
                U = c
                s = list(r['schedule'])
                m = list(r['machine'])
                yes += 1
                return 'yes'
        return 'unknown'

    def process_hybrid(leaf):
        nonlocal U, s, m, yes, nodes
        if try_subsumption(leaf):
            return None
        if leaf.L >= U:
            close_leaf(leaf, leaf.L - 1, leaf.proof, 'bound')
            return None
        if maybe_close_empty(leaf):
            return None
        nodes += 1
        mp, res = solve_box(leaf.F)
        if res.status == 2:
            close_no_with_fallback(leaf)
            return None
        if res.status != 0:
            return oracle_on_leaf(leaf)
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
        # Target LP is feasible but fractional.  For a small local gap,
        # spend one-node probes at leaf.L; for a wide gap, split now.
        if U - leaf.L <= tau:
            for _ in range(max(1, tau)):
                out = probe_leaf(leaf)
                if out in ('closed', 'yes', 'unknown', 'skip'):
                    if out in ('closed', 'yes'):
                        return None if out == 'closed' else 'yes'
                    break
        ch = choose_split(leaf, res.x, mp)
        if ch is None:
            return oracle_on_leaf(leaf)
        i, mid, _ = ch
        sp = split_leaf_colt(leaf, i, mid)
        if sp is None:
            return None
        return 'split', sp

    def process(leaf):
        """Process one open leaf at H.  Return ('yes',), ('split', sp), or None."""
        nonlocal U, s, m, yes, nodes
        if try_subsumption(leaf):
            return None
        if leaf.L >= U:
            close_leaf(leaf, leaf.L - 1, leaf.proof, 'bound')
            return None
        if maybe_close_empty(leaf):
            return None
        nodes += 1
        mp, res = solve_box(leaf.F)
        if res.status == 2:
            close_no_with_fallback(leaf)
            return None
        if res.status != 0:
            return oracle_on_leaf(leaf)
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
        ch = choose_split(leaf, res.x, mp)
        if ch is None:
            return oracle_on_leaf(leaf)
        i, mid, _ = ch
        sp = split_leaf_colt(leaf, i, mid)
        if sp is None:
            return None
        return 'split', sp

    # ---------------------------------------------------------- outer loop
    while U > L0 and nodes < max_nodes and time.time() - t0 < max_time:
        H = U - 1
        lp_cache = {}
        target_rounds += 1
        round_splits = 0
        # Frontier order.  DFS uses an explicit stack and pushes the
        # children of a split; this is the recursive cache-oblivious
        # traversal.  BFS/VEB use a heap.
        stack = [l for l in open_leaves if id(l) in open_ids]
        stack.reverse()
        heap = []
        if order != 'dfs':
            for l in stack:
                if order == 'bfs':
                    key = (-l.mu, id(l))
                else:
                    key = (l.L, -l.mu, id(l))
                heapq.heappush(heap, key + (l,))
        while True:
            if order == 'dfs':
                while stack and id(stack[-1]) not in open_ids:
                    stack.pop()
                if not stack:
                    break
                leaf = stack.pop()
            else:
                while heap and id(heap[0][-1]) not in open_ids:
                    heapq.heappop(heap)
                if not heap:
                    break
                leaf = heapq.heappop(heap)[-1]
            if id(leaf) not in open_ids:
                continue
            out = process(leaf) if mode == 'colt' else process_hybrid(leaf)
            if out == 'yes':
                break
            if out is not None and out[0] == 'split':
                sp = out[1]
                round_splits += 1
                if order == 'dfs':
                    # LIFO: push hi then lo so lo is processed first.
                    if id(sp.lo) in open_ids:
                        stack.append(sp.lo)
                    if id(sp.hi) in open_ids:
                        stack.append(sp.hi)
                else:
                    for c in (sp.lo, sp.hi):
                        if id(c) not in open_ids:
                            continue
                        if order == 'bfs':
                            key = (-c.mu, id(c))
                        else:
                            key = (c.L, -c.mu, id(c))
                        heapq.heappush(heap, key + (c,))
            if nodes >= max_nodes or time.time() - t0 >= max_time:
                break
        if audit_every:
            state_audit()
        if not open_ids:
            break
        # If a YES was found, U shrank; loop to a smaller target.  If no
        # YES and no split happened, the frontier is exhausted.
        if U == H + 1 and round_splits == 0:
            break

    # ---------------------------------------------------------- finalize
    leaves = []
    collect_leaves(holder[0], leaves)
    # Any open leaf with L_f >= U already carries a NO(L_f-1) proof with
    # L_f-1 >= U-1; close it at its own horizon.  This is the natural
    # finalization of the ICF invariant and also handles the L0=U case.
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
    L = fp.L if fp_ok else None
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
        name=name, idx=idx, known=known, alg='colt',
        order=order, split=split, master_reuse=bool(master_reuse),
        subsumption=bool(subsumption),
        L0=L0, U0=U0, L=L, U=U, opt=U,
        nodes=nodes, lp=lp_solves, cert_lp=cert_lp,
        probe_lp=probe_lp, mode=mode, tau=tau,
        strong_lp=strong_lp, fallback_lp=fallback_lp,
        splits=splits, yes=yes, no=no, subsumed=subsumed,
        bound_closed=bound_closed, empty_closed=empty_closed,
        leaves=len(leaves),
        open=len(open_left), max_open=max_open,
        depth=tree_depth(holder[0]), target_rounds=target_rounds,
        partial_checks=partial_checks, partial_fail=partial_fail,
        frontier_ok=fp_ok, certified=bool(not open_left and L == U
                                           and final_ok),
        audit=final_ok, proof=final_ok,
        partial_final=partial_final,
        stop_reason=stop_reason,
        cert_h=(U - 1 if not open_left and L == U else None),
        t=round(dt, 4),
        ok=bool(not open_left and L == U == known and final_ok
                and partial_fail == 0),
    )
    if include_tree:
        out['tree'] = snapshot(holder[0])
        out['schedule'] = s
        out['machine'] = m
    return out


# --------------------------------------------------------------- vEB layout
def veb_index(depth, path, D):
    """Index of a node at ``depth`` with path bits ``path`` in a vEB layout."""
    if D <= 0:
        return 0
    h = (D + 1) // 2
    if depth < h:
        return (1 << depth) - 1 + path
    sub = path >> (depth - h)
    rest = path & ((1 << (depth - h)) - 1)
    top = (1 << h) - 1
    bottom_size = (1 << (D - h + 1)) - 1
    return top + sub * bottom_size + veb_index(depth - h, rest, D - h)


def tree_height(tree):
    if tree[0] == 'leaf':
        return 0
    return 1 + max(tree_height(tree[4]), tree_height(tree[5]))
