"""v10.0 AXIOM-ICF: abstract cost semantics + synthesized probe plans
with a live invariant-carrying frontier.

The v9.0 ICF state is kept:

    C = (L, U, s, m, pi),   pi : NO(L-1), Cmax(s)=U, L<=U.

New objects
-----------
Plan
    A synthesized decision tree over the abstract bracket [a,b].  The
    hidden optimum is abstracted by the interval [a,b]; a probe at h has
    two abstract successors [a,h] (YES) and [h+1,b] (NO).  The plan is the
    fixed point of the max-plus Bellman equation

        V(a,b) = min_h max( cN(h) + V(h+1,b),
                            cY(h) + V(a,h) ),     V(a,a)=0.

    The plan certificate is the table (V,H); an independent auditor checks
    every Bellman equality, so the declared worst-case cost is not a
    trusted flag.

Frontier
    A live partition tree of boxes F.  Open leaves carry a local bound
    L_f and a NO(L_f-1 | F) proof; closed leaves carry a proof at a
    horizon >= U-1.  PROBE, SPLIT, LIFT and CLOSE preserve the partial
    certificate.  A budgeted oracle that returns UNKNOWN is absorbed by
    SPLIT instead of stopping the run.

ProjectedFrontierProof
    The final NO(U-1) certificate.  Splits may have been created at a
    larger horizon (when U was larger); the audit projects every box onto
    the current target domain, so a split remains a partition after U
    shrinks.  Leaf proofs at h >= target are accepted; their forbidden
    pairs outside the target domain are irrelevant.

The AXIOM loop uses the synthesized plan on the global bracket and the
frontier only as a fallback for UNKNOWN.  On the exact corpus the plan is
the only active outer component; on the budgeted corpus the frontier is
what makes the run total.
"""
import sys
import time
import math

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from sage import BranchProof, _domain
from cert import verify
from rdf import check_schedule
from pact import PACT, pact_decide
from icf import (PartialCertificate, ICFCertificate, CertLeafProof,
                 FrontierProof, cmax, _proof_forbid, corpora)


# ------------------------------------------------------------------ costs
class ConstantCost:
    """A declared per-probe cost model.  It is not a correctness oracle;
    it only defines the objective of the synthesized plan."""

    def __init__(self, cN=1.0, cY=1.0, name='const'):
        self.cN = float(cN)
        self.cY = float(cY)
        self.name = name

    def no(self, h, a, b):
        return self.cN

    def yes(self, h, a, b):
        return self.cY

    def bound(self, h, a, b, side):
        return self.no(h, a, b) if side == 'NO' else self.yes(h, a, b)

    def key(self):
        return (self.name, self.cN, self.cY)


class RobustCost:
    """Worst case over a finite credal set of constant models."""

    def __init__(self, models, name='robust'):
        self.models = list(models)
        self.name = name

    def no(self, h, a, b):
        return max(m.no(h, a, b) for m in self.models)

    def yes(self, h, a, b):
        return max(m.yes(h, a, b) for m in self.models)

    def key(self):
        return (self.name, tuple(m.key() for m in self.models))


# ------------------------------------------------------------------- plan
class Plan:
    """A synthesized probe plan plus its Bellman table."""

    def __init__(self, L, U, cost, tie='mid'):
        self.L = int(L)
        self.U = int(U)
        self.cost = cost
        self.tie = tie
        self.V = {}
        self.H = {}
        self.C = {}
        self._synth()

    def _pref(self, a, b, h):
        if self.tie == 'low':
            return (0, h)
        if self.tie == 'high':
            return (0, -h)
        mid = (a + b) // 2
        return (0, abs(h - mid), h)

    def _synth(self):
        L, U = self.L, self.U
        for a in range(L, U + 1):
            self.V[(a, a)] = 0.0
            self.H[(a, a)] = None
        for w in range(1, U - L + 1):
            for a in range(L, U - w + 1):
                b = a + w
                best = None
                bh = None
                for h in range(a, b):
                    vn = self.cost.no(h, a, b) + self.V[(h + 1, b)]
                    vy = self.cost.yes(h, a, b) + self.V[(a, h)]
                    v = max(vn, vy)
                    if best is None or v < best - 1e-12:
                        best, bh = v, h
                    elif abs(v - best) <= 1e-12:
                        if self._pref(a, b, h) < self._pref(a, b, bh):
                            bh = h
                self.V[(a, b)] = best
                self.H[(a, b)] = bh
                ranked = []
                for hh in range(a, b):
                    vn = self.cost.no(hh, a, b) + self.V[(hh + 1, b)]
                    vy = self.cost.yes(hh, a, b) + self.V[(a, hh)]
                    ranked.append((max(vn, vy), hh))
                ranked.sort(key=lambda x: (x[0], abs(x[1] - (a + b) // 2), x[1]))
                self.C[(a, b)] = [hh for _, hh in ranked]

    def probe(self, a, b):
        return self.H.get((a, b))

    def fallbacks(self, a, b):
        """All probe heights for [a,b], best first.  The first is the
        primary plan; the rest are the synthesized contingency order for
        an UNKNOWN primary probe."""
        return list(self.C.get((a, b), []))

    def value(self, a, b):
        return self.V.get((a, b))

    def audit(self):
        """Independent replay of every Bellman equality."""
        try:
            L, U = self.L, self.U
            for a in range(L, U + 1):
                if self.V.get((a, a)) != 0.0 or self.H.get((a, a)) is not None:
                    return False
            for w in range(1, U - L + 1):
                for a in range(L, U - w + 1):
                    b = a + w
                    h = self.H.get((a, b))
                    if h is None or not (a <= h < b):
                        return False
                    vn = self.cost.no(h, a, b) + self.V[(h + 1, b)]
                    vy = self.cost.yes(h, a, b) + self.V[(a, h)]
                    if abs(self.V[(a, b)] - max(vn, vy)) > 1e-9:
                        return False
            return True
        except Exception:
            return False

    def path(self, opt):
        """The run induced by a hidden optimum opt (offline analysis)."""
        a, b = self.L, self.U
        out = []
        while a < b:
            h = self.probe(a, b)
            out.append(h)
            if opt <= h:
                b = h
            else:
                a = h + 1
        return out


# --------------------------------------------------------------- frontier
class FLeaf:
    __slots__ = ('F', 'L', 'proof', 'left', 'right', 'i', 'mid')

    def __init__(self, F, L, proof):
        self.F = frozenset(F)
        self.L = int(L)
        self.proof = proof
        self.left = None
        self.right = None
        self.i = None
        self.mid = None

    def is_leaf(self):
        return self.left is None

    def leaves(self):
        if self.is_leaf():
            return [self]
        return self.left.leaves() + self.right.leaves()


def _project(F, inst, target):
    out = set()
    for (i, t) in F:
        lo, hi = _domain(inst, target, i)
        if lo <= t <= hi:
            out.add((i, t))
    return frozenset(out)


class ProjectedFrontierProof(Proof):
    """A partition tree audited after projecting every box to target.

    The tree is built when U may have been larger.  A split on job i at
    mid was a partition of the then-current domain; restricting to a
    smaller target domain preserves the partition.  Forbidden pairs
    outside the target domain are ignored by the coverage check.  A leaf
    proof at h >= target is valid for its projected cell because the cell
    can only contain schedules that never use a projected-away time.
    """

    kind = 'axiom-frontier'

    def __init__(self, inst, target, root):
        super().__init__(inst, target)
        self.target = int(target)
        self.root = root

    def _allowed(self, i, F):
        lo, hi = _domain(self.inst, self.target, i)
        return [t for t in range(lo, hi + 1) if (i, t) not in F]

    def _check(self, node, cell):
        Fproj = _project(node.F, self.inst, self.target)
        if set(Fproj) != set(cell):
            return False
        if node.is_leaf():
            if node.proof is None:
                return False
            if node.proof.h < self.target:
                return False
            if not node.proof.audit_rdf():
                return False
            pf = _project(_proof_forbid(node.proof), self.inst,
                          self.target)
            if not set(pf) <= set(cell):
                return False
            return True
        if node.i is None or node.mid is None:
            return False
        times = self._allowed(node.i, cell)
        lo_t = [t for t in times if t > node.mid]
        hi_t = [t for t in times if t <= node.mid]
        if not lo_t:
            # The >mid child is empty at this target; the <=mid child
            # inherits the whole parent cell.
            return self._check(node.left, cell)
        if not hi_t:
            return self._check(node.right, cell)
        loF = frozenset(cell | {(node.i, t) for t in lo_t})
        hiF = frozenset(cell | {(node.i, t) for t in hi_t})
        return self._check(node.left, loF) and self._check(node.right, hiF)

    def audit_rdf(self):
        try:
            return self._check(self.root, frozenset())
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()

    def leaf_count(self):
        return len(self.root.leaves())


class FrontierPartialCertificate:
    """A partial certificate for a live frontier.

    Invariant: every leaf has an audited NO(L_f-1 | F) proof, the global
    lower bound is L = min_f min(L_f, U), and (s,m) is a schedule of
    length U.  Any feasible schedule belongs to one leaf, so
    L <= OPT <= U even when no leaf has reached U-1.
    """

    kind = 'axiom-partial'

    def __init__(self, inst, root, U, schedule, machine, L=None):
        self.inst = inst
        self.root = root
        self.U = int(U)
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        if L is None:
            L = min(min(l.L, self.U) for l in root.leaves())
        self.L = int(L)

    def _sched_ok(self):
        if self.schedule is None or self.machine is None:
            return False
        c = cmax(self.inst, self.schedule)
        if c != self.U:
            return False
        return bool(check_schedule(self.inst, c, self.schedule,
                                   self.machine))

    def _leaf_ok(self, leaf):
        if leaf.proof is None:
            return False
        if leaf.proof.h != leaf.L - 1:
            return False
        return bool(leaf.proof.audit_rdf())

    def _partition_ok(self, node, cell, target):
        Fproj = _project(node.F, self.inst, target)
        if set(Fproj) != set(cell):
            return False
        if node.is_leaf():
            return True
        lo_i, hi_i = _domain(self.inst, target, node.i)
        times = [t for t in range(lo_i, hi_i + 1)
                 if (node.i, t) not in cell]
        lo_t = [t for t in times if t > node.mid]
        hi_t = [t for t in times if t <= node.mid]
        if not lo_t:
            return self._partition_ok(node.left, cell, target)
        if not hi_t:
            return self._partition_ok(node.right, cell, target)
        loF = frozenset(cell | {(node.i, t) for t in lo_t})
        hiF = frozenset(cell | {(node.i, t) for t in hi_t})
        return (self._partition_ok(node.left, loF, target) and
                self._partition_ok(node.right, hiF, target))

    def audit_rdf(self):
        try:
            leaves = self.root.leaves()
            if not leaves or self.U < 0:
                return False
            L = min(min(l.L, self.U) for l in leaves)
            if L != self.L or L > self.U:
                return False
            if not self._sched_ok():
                return False
            if not self._partition_ok(self.root, frozenset(),
                                      max(0, self.U - 1)):
                return False
            for leaf in leaves:
                if not self._leaf_ok(leaf):
                    return False
            return True
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class AXIOMCertificate:
    """Final optimality certificate: projected frontier at U-1 + schedule."""

    kind = 'axiom-opt'

    def __init__(self, inst, U, schedule, machine, root, leaves):
        self.inst = inst
        self.U = int(U)
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.root = root
        self.leaves = list(leaves)
        self.frontier = ProjectedFrontierProof(inst, self.U - 1, root)

    def audit_rdf(self):
        try:
            if not self.frontier.audit_rdf():
                return False
            for leaf in self.leaves:
                if leaf.L < self.U:
                    return False
            if self.schedule is None or self.machine is None:
                return False
            if cmax(self.inst, self.schedule) != self.U:
                return False
            return bool(check_schedule(self.inst, self.U,
                                       self.schedule, self.machine))
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


# ------------------------------------------------------------------ driver
def _split_box(inst, F, i, target):
    """Split the allowed start times of job i at the time median."""
    lo, hi = _domain(inst, target, i)
    times = [t for t in range(lo, hi + 1) if (i, t) not in F]
    if len(times) < 2:
        return None
    mid = times[len(times) // 2 - 1]
    lo_t = [t for t in times if t > mid]
    hi_t = [t for t in times if t <= mid]
    if not lo_t or not hi_t:
        return None
    F0 = frozenset(F | {(i, t) for t in lo_t})
    F1 = frozenset(F | {(i, t) for t in hi_t})
    return i, mid, F0, F1


def _candidate_jobs(inst, F, target):
    n = inst['n']
    rows = []
    for i in range(n):
        lo, hi = _domain(inst, target, i)
        times = [t for t in range(lo, hi + 1) if (i, t) not in F]
        if len(times) < 2:
            continue
        width = len(times)
        slack = max(0, target - lo - inst['p'][i])
        rows.append((-width, -slack, -inst['p'][i], i))
    rows.sort()
    return [r[-1] for r in rows]


def _eval_split(inst, leaf, i, mid, F0, F1, h, nodecap, depthcap):
    """One-step lookahead used by SPLIT synthesis.  Results are cached in
    the returned child descriptors so the oracle is not called twice."""
    outs = []
    for F in (F0, F1):
        r = pact_decide(inst, h, depthcap=depthcap, nodecap=nodecap,
                        forbid0=F)
        outs.append(r)
    return outs


def _make_leaf(inst, F, L, proof, r):
    leaf = FLeaf(F, L, proof)
    if r is not None:
        if r['verdict'] is True:
            # A YES leaf is handled by the caller (it lowers U).  Keep the
            # proof of the parent for now; the caller replaces the state.
            leaf.L = L
        elif r['verdict'] is False:
            leaf.L = r['proof'].h + 1
            leaf.proof = r['proof']
    return leaf


def run_axiom(inst, known, name, idx, initial=None, policy='plan',
              cost=None, nodecap=None, depthcap=None, max_probes=128,
              max_leaves=64, target=None, plan_tie='mid',
              allow_split=True, split_lookahead=False,
              max_retries=None):
    """Run the AXIOM loop.

    policy:
      plan     : synthesized plan under `cost`
      lower    : lower-first (first probe L, then binary)
      binary   : bisection
      gap:T    : lower-first for gap <= T, then binary
    """
    t0 = time.time()
    if initial is None:
        co = PACT(inst, pact_mode='complete', use_ga=False)
        L, U, sched, mach = co.initial_bounds()
        if U is None:
            return dict(name=name, idx=idx, known=known, ok=False,
                        error='no-ub', t=0.0)
        L, U = int(L), int(U)
        proof = co._ensure_lb_proof(L)
        if proof is None:
            r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
            if r['verdict'] is False:
                proof = r['proof']
        if proof is None:
            return dict(name=name, idx=idx, known=known, ok=False,
                        error='no-lb', t=0.0)
        sched, mach = list(sched), list(mach)
    else:
        L, U, sched, mach, proof = initial
        L, U = int(L), int(U)
        sched, mach = list(sched), list(mach)
        co = None

    if target is None:
        target = U - 1
    target = int(target)
    cost = cost or ConstantCost(1.0, 1.0, 'unit')
    plan = None
    if policy == 'plan':
        plan = Plan(L, U, cost, tie=plan_tie)
        if not plan.audit():
            return dict(name=name, idx=idx, known=known, ok=False,
                        error='plan-audit', t=0.0)

    root = FLeaf(frozenset(), L, proof)
    leaves = [root]
    probes = 0
    search_lp = 0
    nodes = 0
    cert_lp = 0
    unknown = 0
    no_probes = 0
    yes_probes = 0
    splits = 0
    split_lp = 0
    partial_ok = 0
    partial_fail = 0
    plan_audit = bool(plan is not None and plan.audit())
    plan_value = plan.value(L, U) if plan is not None else None
    first_probe = True

    def global_L():
        return min(min(l.L, U) for l in root.leaves())

    def audit_state():
        nonlocal partial_ok, partial_fail
        pc = FrontierPartialCertificate(inst, root, U, sched, mach,
                                        L=global_L())
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1

    audit_state()

    def choose_h(a, b):
        if plan is not None and policy == 'plan':
            h = plan.probe(a, b)
            if h is not None:
                return h
        if policy == 'lower':
            return a
        if policy == 'lowerfirst':
            return a if first_probe else (a + b) // 2
        if policy == 'binary':
            return (a + b) // 2
        if policy.startswith('gap:'):
            thr = int(policy.split(':')[1])
            if b - a <= thr and first_probe:
                return a
            return (a + b) // 2
        return (a + b) // 2

    while global_L() < U and probes < max_probes and len(root.leaves()) <= max_leaves:
        Lg = global_L()
        # Choose an open leaf with the smallest effective bound; ties by
        # the smallest box measure (most constrained) to make progress.
        cand = []
        for leaf in root.leaves():
            eff = min(leaf.L, U)
            if eff >= U:
                continue
            cand.append((eff, len(leaf.F), id(leaf), leaf))
        if not cand:
            break
        cand.sort(key=lambda x: (x[0], x[1], x[2]))
        leaf = cand[0][3]
        a = min(leaf.L, U)
        b = U
        h = choose_h(a, b)
        h = max(a, min(h, b - 1))
        r = pact_decide(inst, h, depthcap=depthcap, nodecap=nodecap,
                        forbid0=leaf.F)
        probes += 1
        first_probe = False
        search_lp += r.get('lp_solves', 0)
        nodes += r.get('nodes', 0)
        cert_lp += r.get('cert_lp', 0)

        if r['verdict'] is False:
            no_probes += 1
            leaf.L = h + 1
            leaf.proof = r['proof']
            audit_state()
            continue
        if r['verdict'] is True:
            yes_probes += 1
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                sched, mach = list(s2), list(m2)
            audit_state()
            continue

        # UNKNOWN primary probe.  Before paying for a split, use the
        # synthesized contingency order: an UNKNOWN at h does not change
        # the bracket, so another height is always sound.  This is the
        # recovery transition for the third oracle outcome.
        tried = {h}
        if max_retries is None:
            max_retries = 5 if nodecap is None else 1
        if plan is not None and policy == 'plan':
            retry = plan.fallbacks(a, b)
        else:
            mid = (a + b) // 2
            retry = [h + 1, h - 1, mid, b - 1, a, h + 2, h - 2]
        for h2 in retry:
            if len(tried) >= 1 + max_retries:
                break
            if h2 in tried or not (a <= h2 < b):
                continue
            tried.add(h2)
            r2 = pact_decide(inst, h2, depthcap=depthcap,
                             nodecap=nodecap, forbid0=leaf.F)
            probes += 1
            search_lp += r2.get('lp_solves', 0)
            nodes += r2.get('nodes', 0)
            cert_lp += r2.get('cert_lp', 0)
            if r2['verdict'] is not None:
                r, h = r2, h2
                break
        if r['verdict'] is False:
            no_probes += 1
            leaf.L = h + 1
            leaf.proof = r['proof']
            audit_state()
            continue
        if r['verdict'] is True:
            yes_probes += 1
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                sched, mach = list(s2), list(m2)
            audit_state()
            continue

        # Still UNKNOWN: synthesize a split.  Try the oracle's own branch first,
        # then the widest-domain jobs; one-step lookahead picks the split
        # with the most decided children.
        unknown += 1
        if not allow_split or splits >= max_leaves:
            break
        cands = []
        for bj in (r.get('branch_jobs') or [])[:2]:
            try:
                cands.append((int(bj[0]), int(bj[1])))
            except Exception:
                pass
        for i in _candidate_jobs(inst, leaf.F, max(0, U - 1))[:4]:
            sp = _split_box(inst, leaf.F, i, max(0, U - 1))
            if sp is not None:
                cands.append((sp[0], sp[1]))
        seen = set()
        best = None
        for (i, mid) in cands:
            if (i, mid) in seen:
                continue
            seen.add((i, mid))
            sp = _split_box(inst, leaf.F, i, max(0, U - 1))
            if sp is None or sp[0] != i or sp[1] != mid:
                # mid from the oracle may not equal our median; build it
                lo, hi = _domain(inst, max(0, U - 1), i)
                times = [t for t in range(lo, hi + 1) if (i, t) not in leaf.F]
                lo_t = [t for t in times if t > mid]
                hi_t = [t for t in times if t <= mid]
                if not lo_t or not hi_t:
                    continue
                F0 = frozenset(leaf.F | {(i, t) for t in lo_t})
                F1 = frozenset(leaf.F | {(i, t) for t in hi_t})
            else:
                _, _, F0, F1 = sp
            if not split_lookahead:
                best = ((0,), i, mid, F0, F1, [None, None])
                break
            outs = _eval_split(inst, leaf, i, mid, F0, F1, h,
                               nodecap, depthcap)
            split_lp += sum(o.get('lp_solves', 0) for o in outs)
            split_nodes = sum(o.get('nodes', 0) for o in outs)
            decided = sum(o['verdict'] is not None for o in outs)
            no = sum(o['verdict'] is False for o in outs)
            yes = sum(o['verdict'] is True for o in outs)
            score = (-decided, -no, -yes, split_nodes, i, mid)
            if best is None or score < best[0]:
                best = (score, i, mid, F0, F1, outs)
            if decided == 2:
                break
        if best is None:
            # Cannot split: fall back to the exact oracle once, then stop.
            r = pact_decide(inst, h, depthcap=None, nodecap=None,
                            forbid0=leaf.F)
            probes += 1
            search_lp += r.get('lp_solves', 0)
            nodes += r.get('nodes', 0)
            cert_lp += r.get('cert_lp', 0)
            if r['verdict'] is False:
                no_probes += 1
                leaf.L = h + 1
                leaf.proof = r['proof']
            elif r['verdict'] is True:
                yes_probes += 1
                s2, m2 = r['schedule'], r['machine']
                c2 = cmax(inst, s2)
                if c2 < U and check_schedule(inst, c2, s2, m2):
                    U = c2
                    sched, mach = list(s2), list(m2)
            audit_state()
            continue
        _, i, mid, F0, F1, outs = best
        leaf.i = i
        leaf.mid = mid
        child0 = _make_leaf(inst, F0, leaf.L, leaf.proof, outs[0])
        child1 = _make_leaf(inst, F1, leaf.L, leaf.proof, outs[1])
        leaf.left = child0
        leaf.right = child1
        splits += 1
        # A YES child lowers U; a NO child raises its local bound.
        for child, rr in ((child0, outs[0]), (child1, outs[1])):
            if rr is None:
                continue
            if rr['verdict'] is True:
                s2, m2 = rr['schedule'], rr['machine']
                c2 = cmax(inst, s2)
                if c2 < U and check_schedule(inst, c2, s2, m2):
                    U = c2
                    sched, mach = list(s2), list(m2)
            elif rr['verdict'] is False:
                child.L = rr['proof'].h + 1
                child.proof = rr['proof']
        audit_state()

    Lg = global_L()
    leaves = root.leaves()
    final = None
    final_ok = False
    if Lg == U and all(l.L >= U for l in leaves):
        final = AXIOMCertificate(inst, U, sched, mach, root, leaves)
        final_ok = bool(final.audit_rdf())
    partial = FrontierPartialCertificate(inst, root, U, sched, mach,
                                         L=Lg)
    partial_final = bool(partial.audit_rdf())
    dt = time.time() - t0
    return dict(
        name=name, idx=idx, known=known, corpus=None,
        policy=policy, cost=cost.name,
        opt=U, lb=Lg, lb0=int(initial[0]) if initial is not None else int(L),
        ub0=int(initial[1]) if initial is not None else int(U),
        certified=bool(final_ok and Lg == U),
        audit=final_ok, proof=final_ok,
        cert_h=(U - 1 if final_ok else None),
        queries=probes, probes=probes,
        pact_lp=search_lp, split_lp=split_lp,
        pact_nodes=nodes, pact_cert_lp=cert_lp,
        nodes=nodes,
        unknown=unknown, splits=splits,
        no_probes=no_probes, yes_probes=yes_probes,
        leaves=len(leaves),
        partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_final,
        plan_audit=plan_audit, plan_value=plan_value,
        proof_kind=(final.frontier.kind if final is not None else
                    getattr(proof, 'kind', None)),
        total_audit=final_ok,
        t=round(dt, 4),
        ok=bool(Lg == U and U == known and final_ok and
                partial_fail == 0 and partial_final),
    )
