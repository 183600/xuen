"""v9.2 TRIP-ICF: transition-ranked integer-programming frontier.

TRIP keeps the v9.0 ICF invariant for every leaf of a live partition
tree, and adds two objects:

  * a cut pool K.  Every NO probe on a box F at horizon h emits the
    no-good cut  sum_i sum_{t in D_i(h,F)} x_{i,t} <= n-1.  The cut is
    valid for *all* integer schedules (if all starts lie in F, the
    schedule has makespan <= h and would contradict NO(h|F)).
  * a CUT-LIFT transition.  When enough cuts at the same horizon h have
    accumulated, solve the root LP P(h) plus those cuts.  If it is
    infeasible, the pool is a flat NO(h) certificate.  Then every open
    leaf below h+1 is lifted to h+1 with that certificate as its local
    proof.  This is a global lower-bound jump, not a leaf-local one.

The state is

    (T, {(F_l,L_l,pi_l,st_l)}, s, m, U, K, rho)

with the invariant exactly as in v9.0, plus

    every cut (F,h,c) in K has c : NO(h|F) and h is its horizon.

The rank is TAMO's

    rho = (U, multiset of box measures mu(F_l), sum_open (U-L_l)).

PROBE-YES lowers U; PROBE-NO raises one L_l; SPLIT replaces mu(F) by
two strictly smaller measures; CUT-LIFT raises many L_l at once and
therefore also decreases the third component.  The fourth component is
a cut budget, only used to stop pathological cut loops.

The module reuses TAMO's live tree and certificate classes.  The new
code is the cut pool and the CUT-LIFT transition.
"""
import sys
import time
import heapq
import collections

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from rdf import check_schedule
from icf import cmax
from tamo import (Leaf, Split, collect_leaves, tree_depth, snapshot,
                  close_empty, split_leaf, allowed_times, box_measure,
                  rank_of, rank_lt, pact_initial, _choose_split,
                  TamoFrontier, TamoPartialCertificate, TamoCertificate)
from gac import _root_lp, _cut_row, cut_lp_status
from apex import Proof
from cert import verify
from icf import _proof_forbid



class CoreCutProof(Proof):
    """Flat NO(h) proof from valid core no-good cuts.

    Each entry is either
        {'F': F, 'proof': p}   with p a NO(h|F0) proof, F0 subset F,
    or
        {'F': F, 'cert': c}    with c a Farkas/empty leaf certificate.

    The cut row is  sum_{i,t in D_i(h,F)} x_{i,t} <= n-1.  If the root
    LP plus all rows is infeasible, the cuts prove NO(h).
    """

    kind = 'core-cut'

    def __init__(self, inst, h, cuts, stats=None):
        super().__init__(inst, h)
        self.cuts = [dict(F=frozenset(c['F']),
                          proof=c.get('proof'),
                          cert=c.get('cert')) for c in cuts]
        self.stats = dict(stats or {})
        self.audit_lp = 0
        self._audit_cache = None

    def _cut_ok(self, cut):
        F = frozenset(cut['F'])
        p = cut.get('proof')
        if p is not None:
            if getattr(p, 'h', None) != self.h:
                return False
            if not p.audit_rdf():
                return False
            return set(_proof_forbid(p)) <= set(F)
        c = cut.get('cert')
        if c is None:
            return False
        return bool(verify(self.inst, self.h, c, forbid=F))

    def audit_rdf(self):
        if self._audit_cache is not None:
            return self._audit_cache
        try:
            lp = _root_lp(self.inst, self.h)
            rows = []
            for cut in self.cuts:
                if not self._cut_ok(cut):
                    self._audit_cache = False
                    return False
                row, rhs = _cut_row(lp, self.inst, self.h, cut['F'])
                rows.append((row, rhs))
            status, nlp = cut_lp_status(lp, rows)
            self.audit_lp = nlp
            self._audit_cache = (status == 2)
            return self._audit_cache
        except Exception:
            self._audit_cache = False
            return False

    def proof_complete(self):
        return self.audit_rdf()


def _minimize_core_cuts(inst, h, cuts, root_lp=None, max_cuts=64):
    """Greedy singleton-first/deletion compression for CoreCutProof."""
    t0 = time.time()
    cuts = cuts[-max_cuts:]
    lp = root_lp if root_lp is not None else _root_lp(inst, h)
    stats = dict(candidate_cuts=len(cuts), selected_cuts=0,
                 lp_solves=0, t=0.0)

    def infeasible(sub):
        cp = CoreCutProof(inst, h, sub)
        ok = cp.audit_rdf()
        stats['lp_solves'] += int(cp.audit_lp)
        return bool(ok)

    if not cuts:
        ok = infeasible([])
        stats['t'] = round(time.time() - t0, 5)
        return ([], stats) if ok else (None, stats)
    if not infeasible(cuts):
        stats['t'] = round(time.time() - t0, 5)
        return None, stats
    for cut in cuts:
        if infeasible([cut]):
            stats['selected_cuts'] = 1
            stats['t'] = round(time.time() - t0, 5)
            return [cut], stats
    cur = list(cuts)
    for cut in list(cur):
        sub = [c for c in cur if c is not cut]
        if infeasible(sub):
            cur = sub
    stats['selected_cuts'] = len(cur)
    stats['t'] = round(time.time() - t0, 5)
    return cur, stats


def _try_cut_lift(inst, h, cuts, root_lp=None, max_cuts=64):
    """Try to turn the cut pool at h into a flat NO(h) proof."""
    if not cuts:
        return None, dict(lp_solves=0, candidates=0, selected=0,
                          reason='empty')
    cutting = cuts[-max_cuts:]
    lp = root_lp if root_lp is not None else _root_lp(inst, h)
    selected, stats = _minimize_core_cuts(inst, h, cutting, root_lp=lp,
                                          max_cuts=max_cuts)
    if selected is None:
        stats = dict(stats)
        stats['reason'] = 'lp-feasible'
        return None, stats
    cp = CoreCutProof(inst, h, selected, stats=stats)
    if not cp.audit_rdf():
        stats = dict(stats)
        stats['reason'] = 'audit-failed'
        return None, stats
    stats = dict(stats)
    stats['audit_lp'] = int(cp.audit_lp)
    stats['reason'] = 'ok'
    return cp, stats


def run_trip(inst, known, name, idx, B=1, policy='lower',
             split_mode='oracle', max_probes=200000, initial=None,
             audit_every=True, cut_q=2, cut_max_pool=32,
             cut_max_cuts=64, cut_attempt_limit=10000,
             timelimit=None, include_tree=False, debug=False):
    """One TRIP run.  Returns a benchmark row.

    The search work is counted separately from certificate audits:
    ``lp`` is the number of LP solves spent by the probe oracle, and
    ``cut_lp`` is the number spent by CUT-LIFT (including the final
    audit of the flat cut proof).
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
    live = set(id(l) for l in leaves)
    byid = {id(l): l for l in leaves}
    heap = [(l.L, -l.mu, id(l)) for l in leaves]
    heapq.heapify(heap)

    probes = splits = closes_lift = closes_empty = 0
    yes = no = unknown = 0
    lp = nodes = cert_lp = 0
    cut_lp = cut_attempts = cut_ok = cut_compressed = 0
    cut_pool_size = 0
    cut_by_h = collections.defaultdict(list)
    root_lps = {}
    max_leaves = len(leaves)
    rank_checks = rank_fail = 0
    partial_checks = partial_fail = 0
    final_ok = False
    rho = rank_of(inst, H0, U, holder[0], Mmax, recompute=True)

    def rebuild_heap():
        nonlocal live, byid, heap
        leaves_now = []
        collect_leaves(holder[0], leaves_now)
        live = set(id(x) for x in leaves_now if not x.closed)
        byid = {id(x): x for x in leaves_now}
        heap = [(x.L, -x.mu, id(x)) for x in leaves_now
                if not x.closed]
        heapq.heapify(heap)
        return leaves_now

    def lift_with_cut(cp, h):
        """Materialise a global NO(h) proof into every open leaf."""
        nonlocal closes_lift, U, H
        G = h + 1
        leaves_now = []
        collect_leaves(holder[0], leaves_now)
        for x in leaves_now:
            if x.closed:
                continue
            if x.L <= h:
                x.proof = cp
                x.L = G
            if x.L >= U:
                x.closed = True
                x.h = (x.proof.h if x.proof is not None
                       else U - 1)
                closes_lift += 1
        # Cuts below the new floor are superseded.
        for hh in list(cut_by_h):
            if hh < G:
                del cut_by_h[hh]
        rebuild_heap()

    def state_audit():
        nonlocal partial_checks, partial_fail
        if not audit_every:
            return
        fp = TamoFrontier(inst, U - 1, snapshot(holder[0]))
        pc = TamoPartialCertificate(inst, U - 1, fp, s, m, probe=probes)
        partial_checks += 1
        if not pc.audit_rdf():
            partial_fail += 1
            if debug:
                print('AUDIT FAIL probes', probes, 'U', U)

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
        if timelimit is not None and time.time() - t0 > timelimit:
            break
        if policy == 'lower':
            h = leaf.L
        elif policy in ('upper', 'target'):
            h = U - 1
        else:
            h = (leaf.L + U) // 2
        if h >= U:
            h = U - 1
        r = __import__('pact').pact_decide(
            inst, h, depthcap=None, nodecap=B,
            forbid0=frozenset(leaf.F))
        probes += 1
        lp += r.get('lp_solves', 0)
        nodes += r.get('nodes', 0)
        cert_lp += r.get('cert_lp', 0)
        before = rho
        kind = None

        if r['verdict'] is False:
            no += 1
            proof = r['proof']
            # Emit one no-good cut for the queried box.
            cut_by_h[h].append(dict(F=frozenset(leaf.F), proof=proof))
            cut_pool_size += 1
            leaf.proof = proof
            leaf.L = h + 1
            kind = 'probe-no'
            if leaf.L >= U:
                leaf.closed = True
                leaf.h = (leaf.proof.h if leaf.proof is not None
                          else U - 1)
                live.discard(id(leaf))
                byid.pop(id(leaf), None)
                closes_lift += 1
            else:
                heapq.heappush(heap, (leaf.L, -leaf.mu, id(leaf)))

            pool = cut_by_h[h]
            if (len(pool) >= cut_q and len(pool) <= cut_max_pool and
                    cut_attempts < cut_attempt_limit):
                if h not in root_lps:
                    root_lps[h] = _root_lp(inst, h)
                cp, st = _try_cut_lift(inst, h, pool,
                                       root_lp=root_lps[h],
                                       max_cuts=cut_max_cuts)
                cut_attempts += 1
                cut_lp += st.get('lp_solves', 0) + st.get('audit_lp', 0)
                if cp is not None:
                    cut_ok += 1
                    cut_compressed += int(st.get('selected_cuts', 0))
                    lift_with_cut(cp, h)
                    kind = 'cut-lift'
                    if debug:
                        print('CUT-LIFT h', h, 'pool', len(pool),
                              'selected', st.get('selected_cuts'),
                              'leaves', len(byid), 'U', U)
                elif debug:
                    print('CUT-MISS h', h, 'pool', len(pool),
                          'reason', st.get('reason'))
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
                        x.h = (x.proof.h if x.proof is not None
                               else U - 1)
                        live.discard(id(x))
                        byid.pop(id(x), None)
                        closes_lift += 1
                if not live:
                    break
            else:
                kind = 'probe-yes-stale'
        else:
            unknown += 1
            pair = _choose_split(inst, leaf, H, r, split_mode)
            if pair is None:
                break
            i, mid = pair
            sp = split_leaf(inst, leaf, i, mid, H, H0)
            if sp is None:
                break
            splits += 1
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
            kind = 'refine'
            leaves = []
            collect_leaves(holder[0], leaves)
            max_leaves = max(max_leaves, len(leaves))

        if kind in ('probe-no', 'probe-yes', 'refine', 'cut-lift'):
            rho2 = rank_of(inst, H0, U, holder[0], Mmax,
                           recompute=True)
            rank_checks += 1
            if not rank_lt(rho2, before):
                rank_fail += 1
            rho = rho2
        state_audit()

    leaves = []
    collect_leaves(holder[0], leaves)
    open_now = [x for x in leaves if not x.closed]
    L = min([x.L for x in open_now] +
            [x.h + 1 for x in leaves if x.closed] + [U])
    # When L=U, any remaining open leaf already carries NO(U-1).
    if L == U:
        for x in open_now:
            x.closed = True
            x.h = x.proof.h if x.proof is not None else U - 1
        open_now = []
    # A final all-closed frontier is an optimality certificate.
    if not open_now and L == U:
        fp = TamoFrontier(inst, U - 1, snapshot(holder[0]))
        cert = TamoCertificate(inst, U - 1, fp, s, m)
        final_ok = bool(cert.audit_rdf())
    fp = TamoFrontier(inst, U - 1, snapshot(holder[0]))
    partial = TamoPartialCertificate(inst, U - 1, fp, s, m,
                                     probe=probes)
    partial_final = bool(partial.audit_rdf())
    dt = time.time() - t0
    out = dict(
        name=name, idx=idx, known=known, B=B, policy=policy,
        split_mode=split_mode, L0=L0, U0=U0, L=L, U=U,
        opt=U, probes=probes, splits=splits,
        yes=yes, no=no, unknown=unknown,
        closes_lift=closes_lift, closes_empty=closes_empty,
        lp=lp, nodes=nodes, cert_lp=cert_lp,
        cut_lp=cut_lp, cut_attempts=cut_attempts, cut_ok=cut_ok,
        cut_compressed=cut_compressed, cut_pool=cut_pool_size,
        leaves=len(leaves), open=len(open_now),
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


def corpora():
    from icf import corpora as c
    return c()
