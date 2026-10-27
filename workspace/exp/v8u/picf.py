"""v9.3 PICF: pruning-incremental constraint frontier.

PICF extends TAMO's live multi-leaf ICF frontier with three mechanisms:

  ESCALATE : an UNKNOWN probe is not immediately refined.  The leaf's
             node budget is doubled (up to Bmax) and the same leaf is
             re-probed.  REFINE happens only after the budget is spent.
  TARGET   : a leaf can be probed directly at the current target H=U-1;
             a NO then closes the leaf at the target instead of lifting
             the local bound one unit at a time.
  CUTPOOL  : every target-NO leaf contributes a valid no-good cut
             sum_{i,t in D_i(H,F)} x_{i,t} <= n-1.  When the root LP
             with the accumulated cuts becomes infeasible, a single
             CutPoolProof closes the whole frontier.

The ICF/TAMO partial-certificate invariant is unchanged.  The cut pool is
auxiliary: it is used only when it yields an independently auditable
global NO(H) proof.  Budget escalation is certified by the fact that a
larger node cap only explores more of the same finite tree; a result
returned under a smaller cap is never invalidated.
"""
import sys
import time
import heapq

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from sage import _domain
from rdf import check_schedule
from icf import CertLeafProof, _proof_forbid, cmax
from pact import PACT, pact_decide
from po import heads_tails
from gac import _root_lp, _cut_row, cut_lp_status

from tamo import (Leaf, Split, collect_leaves, split_leaf, close_empty,
                  allowed_times, box_measure, snapshot, tree_depth,
                  rank_of, rank_lt, _choose_split, pact_initial,
                  TamoFrontier, TamoPartialCertificate, TamoCertificate)


# --------------------------------------------------------------- proofs
class EnergeticProof(Proof):
    """NO(h | F) from a violated mandatory-part energy window."""

    kind = 'picf-energy'

    def __init__(self, inst, h, F, a, b, parts):
        super().__init__(inst, h)
        self.forbid0 = frozenset(F)
        self.a = int(a)
        self.b = int(b)
        self.parts = tuple(parts)

    def audit_rdf(self):
        try:
            if not (0 <= self.a < self.b <= self.h):
                return False
            need = 0
            for i, lo, hi in self.parts:
                p = self.inst['p'][i]
                times = allowed_times(self.inst, self.h, i, self.forbid0)
                if not times:
                    return False
                r, l = times[0], times[-1]
                if l < r + p:
                    need += max(0, min(self.b, r + p) - max(self.a, l))
            cap = self.inst['m'] * (self.b - self.a)
            return need > cap
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class CutPoolProof(Proof):
    """Global NO(H): a pool of valid no-good cuts makes the root LP infeasible.

    Each entry (F, proof) must certify NO(H | F).  The no-good cut for F
    excludes exactly the schedules whose every job starts inside F's
    allowed domain.  Every integer schedule satisfies every cut, because
    violating one would put all jobs in an infeasible box.  Hence the
    cut LP is a relaxation of the integer problem.
    """

    kind = 'picf-cutpool'

    def __init__(self, inst, h, entries, stats=None):
        super().__init__(inst, h)
        self.forbid0 = frozenset()
        self.entries = [(frozenset(F), p) for F, p in entries]
        self.stats = dict(stats or {})
        self.audit_lp = 0
        self.audit_t = 0.0

    def audit_rdf(self):
        t0 = time.time()
        try:
            lp = _root_lp(self.inst, self.h)
            rows = []
            for F, p in self.entries:
                if p is None or p.h != self.h or not p.audit_rdf():
                    return False
                if not (_proof_forbid(p) <= F):
                    return False
                row, rhs = _cut_row(lp, self.inst, self.h, F)
                rows.append((row, rhs))
            status, nlp = cut_lp_status(lp, rows)
            self.audit_lp += nlp
            self.audit_t = round(time.time() - t0, 5)
            return status == 2
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


# --------------------------------------------------------------- energy
def energetic_violation(inst, h, F):
    """Return (a,b,parts) for a violated mandatory-part window, or None.

    The mandatory part of job i in box F is [max D_i, min D_i + p_i),
    where D_i is the allowed start set at horizon h.  This is a valid
    necessary condition for every schedule in the box.
    """
    n, m, p = inst['n'], inst['m'], inst['p']
    dom = []
    for i in range(n):
        ts = allowed_times(inst, h, i, F)
        if not ts:
            return None
        r, l = ts[0], ts[-1]
        dom.append((r, l, p[i]))
    # Candidate window endpoints are release times and deadlines.
    endpoints = set([0, h])
    for r, l, pi in dom:
        endpoints.add(r)
        endpoints.add(min(h, r + pi))
        endpoints.add(l)
        endpoints.add(min(h, l + pi))
    endpoints = sorted(t for t in endpoints if 0 <= t <= h)
    for ai, a in enumerate(endpoints):
        for b in endpoints[ai + 1:]:
            if b <= a:
                continue
            need = 0
            parts = []
            for i, (r, l, pi) in enumerate(dom):
                if l < r + pi:
                    e = max(0, min(b, r + pi) - max(a, l))
                    if e > 0:
                        need += e
                        parts.append((i, r, l))
            if need > m * (b - a):
                return a, b, parts
    return None




# --------------------------------------------------------------- energy bound
class WindowEnergyProof(Proof):
    """NO(h | F) from an energetic-reasoning window violation.

    For each job i let r_i be its earliest allowed start and d_i its
    latest allowed completion in box F at horizon h.  The minimum overlap
    of job i with [a,b) over all feasible starts is

        e_i(a,b) = max(0, p_i - max(0, a-r_i) - max(0, d_i-b)).

    If sum_i e_i(a,b) > m (b-a), no schedule exists.
    """

    kind = 'picf-window'

    def __init__(self, inst, h, F, a, b):
        super().__init__(inst, h)
        self.forbid0 = frozenset(F)
        self.a = int(a)
        self.b = int(b)

    def audit_rdf(self):
        try:
            v = energy_window_violation(self.inst, self.h, self.forbid0)
            return v is not None and int(v[0]) == self.a and int(v[1]) == self.b
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def energy_window_violation(inst, h, F=frozenset()):
    """Return (a,b,need,cap) for the first violated window, or None."""
    n, m, p = inst['n'], inst['m'], inst['p']
    if h < 0:
        return (0, 1, 1, 0)
    r = [0] * n
    d = [0] * n
    for i in range(n):
        ts = allowed_times(inst, h, i, F)
        if not ts:
            return (0, 1, 1, 0)
        r[i] = ts[0]
        d[i] = ts[-1] + p[i]
    pts = {0, h}
    for i in range(n):
        for v in (r[i], d[i], r[i] + p[i], d[i] - p[i]):
            pts.add(max(0, min(h, v)))
    pts = sorted(pts)
    for ia, a in enumerate(pts):
        for b in pts[ia + 1:]:
            if b <= a:
                continue
            need = 0
            for i in range(n):
                need += max(0, p[i] - max(0, a - r[i])
                            - max(0, d[i] - b))
            cap = m * (b - a)
            if need > cap:
                return (a, b, need, cap)
    return None


def energy_lb(inst, lo, hi, F=frozenset()):
    """Smallest h in [lo,hi] with no energetic violation, and its witness.

    Returns (h, proof) where proof certifies NO(h-1 | F).  If no h in the
    range is clean, returns (hi+1, proof at hi).
    """
    lo = max(0, int(lo))
    hi = max(lo - 1, int(hi))
    if hi < lo:
        return lo, None
    v_prev = None
    for h in range(lo, hi + 1):
        v = energy_window_violation(inst, h, F)
        if v is None:
            if v_prev is None:
                return h, None
            a, b = v_prev[0], v_prev[1]
            return h, WindowEnergyProof(inst, h - 1, F, a, b)
        v_prev = v
    a, b = v_prev[0], v_prev[1]
    return hi + 1, WindowEnergyProof(inst, hi, F, a, b)


# --------------------------------------------------------------- main loop
def _policy_h(policy, L, U):
    if policy == 'lower':
        return L
    if policy == 'target':
        return U - 1
    if policy == 'binary':
        return (L + U) // 2
    if policy == 'adaptive':
        # target is cheap when the remaining bracket is tiny; otherwise
        # probe the lower side first, as in ICF lower-first.
        return U - 1 if U - L <= 2 else L
    raise ValueError(policy)


def _check_cuts(inst, H, entries):
    """Try to build a CutPoolProof from the current target-NO entries."""
    if not entries:
        return None
    cp = CutPoolProof(inst, H, entries)
    if cp.audit_rdf():
        return cp
    return None


def run_picf(inst, known, name, idx, B0=1, Bmax=8, policy='lower',
             cut_pool=False, cut_check_every=4, prop=False,
             energy_init=False, energy_lift=False,
             max_probes=200000, initial=None, audit_every=True,
             include_tree=False, debug=False):
    t0 = time.time()
    if initial is None:
        L0, U0, s, m, proof0 = pact_initial(inst)
    else:
        L0, U0, s, m, proof0 = initial
    L0, U0 = int(L0), int(U0)
    s, m = list(s), list(m)
    if energy_init:
        Le, ep = energy_lb(inst, L0, U0 - 1)
        if Le > L0:
            L0 = Le
            if ep is not None:
                proof0 = ep
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
    budgets = {id(l): B0 for l in leaves}

    probes = splits = closes_lift = closes_empty = 0
    yes = no = unknown = escalations = 0
    lp = nodes = cert_lp = 0
    cut_entries = []
    cut_seen = set()
    cut_checks = cut_lp = cut_lift_tries = 0
    cut_lift_ok = False
    next_cut_check = cut_check_every
    max_leaves = len(leaves)
    rank_checks = rank_fail = 0
    partial_checks = partial_fail = 0
    energy_closes = 0
    rho = rank_of(inst, H0, U, holder[0], Mmax, recompute=True)

    def budget_rank():
        return sum(Bmax - budgets.get(id(x), B0)
                   for x in _open_leaves(holder[0]))

    def _open_leaves(node):
        out = []
        def walk(x):
            if isinstance(x, Leaf):
                if not x.closed:
                    out.append(x)
            else:
                walk(x.lo); walk(x.hi)
        walk(node)
        return out

    def full_rank():
        r = rank_of(inst, H0, U, holder[0], Mmax, recompute=True)
        return (r[0], r[1], r[2], budget_rank())

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
                print('AUDIT FAIL', probes, U, flush=True)

    def push_leaf(x):
        live.add(id(x))
        byid[id(x)] = x
        budgets.setdefault(id(x), B0)
        heapq.heappush(heap, (x.L, -x.mu, id(x)))

    def close_leaf(x, h):
        x.closed = True
        x.h = int(h)
        live.discard(id(x))
        byid.pop(id(x), None)

    def add_cut(F, p):
        key = frozenset(F)
        if key in cut_seen:
            return
        cut_seen.add(key)
        cut_entries.append((key, p))

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

        before = full_rank()

        # incremental energetic lifting: raise the local lower bound by
        # more than one unit, with an auditable window proof.
        if energy_lift:
            Le, ep = energy_lb(inst, leaf.L, U - 1, leaf.F)
            if Le > leaf.L:
                leaf.L = Le
                if ep is not None:
                    leaf.proof = ep
                if leaf.L >= U:
                    close_leaf(leaf, U - 1)
                    closes_lift += 1
                    if leaf.proof is not None and leaf.proof.h == U - 1:
                        add_cut(leaf.F, leaf.proof)
                    rho = full_rank()
                    state_audit()
                    continue
                heapq.heappush(heap, (leaf.L, -leaf.mu, id(leaf)))
                rho = full_rank()
                state_audit()
                continue

        # cheap sound propagation before spending an LP
        if prop:
            ev = energetic_violation(inst, min(H, max(leaf.L, 0)), leaf.F)
            if ev is not None:
                a, b, parts = ev
                hh = min(H, max(leaf.L, 0))
                leaf.proof = EnergeticProof(inst, hh, leaf.F, a, b, parts)
                leaf.L = hh + 1
                energy_closes += 1
                if hh == H or leaf.L >= U:
                    close_leaf(leaf, hh)
                    if hh == H:
                        add_cut(leaf.F, leaf.proof)
                else:
                    heapq.heappush(heap, (leaf.L, -leaf.mu, id(leaf)))
                rho = full_rank()
                state_audit()
                continue

        h = _policy_h(policy, leaf.L, U)
        if h >= U:
            h = U - 1
        if h < leaf.L:
            h = leaf.L
        b = budgets.get(id(leaf), B0)
        r = pact_decide(inst, h, depthcap=None, nodecap=b,
                        forbid0=frozenset(leaf.F))
        probes += 1
        lp += r.get('lp_solves', 0)
        nodes += r.get('nodes', 0)
        cert_lp += r.get('cert_lp', 0)
        kind = None

        if r['verdict'] is False:
            no += 1
            leaf.proof = r['proof']
            leaf.L = h + 1
            if h == H:
                close_leaf(leaf, H)
                closes_lift += 1
                add_cut(leaf.F, leaf.proof)
                kind = 'probe-no-target'
            elif leaf.L >= U:
                close_leaf(leaf, leaf.L - 1)
                closes_lift += 1
                kind = 'probe-no-lift'
            else:
                kind = 'probe-no'
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
                # Cuts proved at the old target are not valid at the new,
                # smaller target; discard the pool and restart it.
                cut_entries.clear()
                cut_seen.clear()
                next_cut_check = cut_check_every
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
                        close_leaf(x, x.L - 1)
                        closes_lift += 1
                if not live:
                    break
            else:
                kind = 'probe-yes-stale'
        else:
            unknown += 1
            if b < Bmax:
                budgets[id(leaf)] = min(Bmax, 2 * b)
                escalations += 1
                heapq.heappush(heap, (leaf.L, -leaf.mu, id(leaf)))
                kind = 'escalate'
            else:
                pair = _choose_split(inst, leaf, H, r, 'oracle')
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
                budgets.pop(id(leaf), None)
                for c in (sp.lo, sp.hi):
                    if close_empty(inst, c, H):
                        closes_empty += 1
                    else:
                        push_leaf(c)
                kind = 'refine'
                max_leaves = max(max_leaves,
                                 len(_open_leaves(holder[0])))

        if kind in ('probe-no-target', 'probe-no', 'probe-no-lift',
                    'probe-yes', 'refine', 'escalate'):
            rho2 = full_rank()
            rank_checks += 1
            if not rank_lt(rho2, before):
                rank_fail += 1
                if debug:
                    print('RANK FAIL', kind, before, rho2, flush=True)
            rho = rho2
        state_audit()

        if cut_pool and len(cut_entries) >= next_cut_check:
            cut_checks += 1
            cp = _check_cuts(inst, H, cut_entries)
            cut_lift_tries += 1
            if cp is not None:
                root = Leaf(frozenset(), U, cp, Mmax)
                root.closed = True
                root.h = H
                holder[0] = root
                live.clear()
                byid.clear()
                heap.clear()
                budgets.clear()
                cut_lift_ok = True
                cut_lp += cp.audit_lp
                break
            next_cut_check *= 2

    # close remaining open leaves for the final certificate
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
        name=name, idx=idx, known=known, B0=B0, Bmax=Bmax,
        policy=policy, cut_pool=cut_pool, prop=prop,
        L0=L0, U0=U0, L=L, U=U, opt=U,
        probes=probes, splits=splits,
        yes=yes, no=no, unknown=unknown, escalations=escalations,
        closes_lift=closes_lift, closes_empty=closes_empty,
        energy_closes=energy_closes,
        lp=lp, nodes=nodes, cert_lp=cert_lp,
        cut_checks=cut_checks, cut_lp=cut_lp,
        cut_lift_tries=cut_lift_tries, cut_lift_ok=cut_lift_ok,
        cuts=len(cut_entries),
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
