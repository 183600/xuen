"""v9.1 MEC-PACT: minimax probes, external-memory frontier, certified convergence.

This module keeps the v9.0 ICF trust boundary

    (L, U, s, m, pi),  pi : NO(L-1),  Cmax(s)=U,  L<=U,

and adds three orthogonal pieces:

  * a minimax probe policy over the bracket [L,U], with asymmetric
    NO/YES costs derived from the LP pin;
  * a live multi-leaf frontier whose leaves carry local lower bounds and
    proofs, with alpha-cutoff when L_f >= U (the minimax prune);
  * a paged frontier store and a convergence ledger.  The store is
    simulated by a page cache; the ledger is a replayable sequence of
    certified brackets.

The single-leaf loop is the same as icf.run_icf; only choose_h changes,
so the experiments are directly comparable with v9.0.
"""
import sys
import time
import math
import json

sys.path[:0] = ['exp/v9mec', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from icf import (PartialCertificate, ICFCertificate, cmax, corpora,
                 _choose_h)
from pact import PACT, pact_decide
from sage import _domain
from rdf import check_schedule


INF = 1e18


# --------------------------------------------------------------- minimax DP
def minimax_value(a, b, pin=None, lam=2.0, costs=None):
    """Optimal worst-case probe cost on an integer bracket [a,b].

    A probe at h has two adversarial outcomes:
        YES -> [a,h], cost cY(h)
        NO  -> [h+1,b], cost cN(h)
    The recurrence is

        W(a,b) = min_h max(cY(h)+W(a,h), cN(h)+W(h+1,b)),  W(a,a)=0.

    With unit costs and balanced h this is ceil(log2(b-a+1)); the
    asymmetric costs encode the LP hint (NO above pin is expensive,
    YES below pin is expensive).  Returns (W, best_h_table).
    """
    if b <= a:
        return 0.0, {}
    G = float(b - a + 1)
    pin = a if pin is None else max(a, min(b, pin))
    if costs is None:
        cN = {h: 1.0 + lam * max(0.0, (h - pin) / G)
              for h in range(a, b)}
        cY = {h: 1.0 + lam * max(0.0, (pin - h) / G)
              for h in range(a, b)}
    else:
        cN, cY = costs
    W = {}
    act = {}
    for g in range(0, b - a + 1):
        for x in range(a, b - g + 1):
            y = x + g
            if g == 0:
                W[(x, y)] = 0.0
                act[(x, y)] = x
                continue
            best = INF
            bh = x
            for h in range(x, y):
                z = max(cY[h] + W[(x, h)],
                        cN[h] + W[(h + 1, y)])
                if z < best - 1e-12:
                    best = z
                    bh = h
            W[(x, y)] = best
            act[(x, y)] = bh
    return W[(a, b)], act


def choose_h(policy, L, U, first, pin=None, lam=2.0):
    if U <= L:
        return L
    if policy in ('lower-first', 'pact', 'binary', 'upper-first'):
        return _choose_h(policy, L, U, first)
    if policy == 'minimax':
        _, act = minimax_value(L, U, pin=pin, lam=lam)
        return act[(L, U)]
    if policy == 'minimax-unit':
        _, act = minimax_value(L, U, pin=L, lam=0.0)
        return act[(L, U)]
    raise ValueError('unknown policy %r' % (policy,))


def worst_case_probes(gap, policy):
    """Worst-case probe count for a given policy on a bracket of width gap."""
    if gap <= 0:
        return 0
    if policy in ('binary', 'minimax-unit'):
        return int(math.ceil(math.log2(gap + 1)))
    if policy == 'lower-first':
        return 1 + (0 if gap <= 1 else int(math.ceil(math.log2(gap))))
    if policy == 'pact':
        return min(gap, 4 + int(math.ceil(math.log2(max(1, gap)))))
    if policy == 'upper-first':
        return gap
    if policy == 'minimax':
        w, _ = minimax_value(0, gap, pin=0, lam=2.0)
        return w
    raise ValueError(policy)


# --------------------------------------------------------------- single leaf
def run_mec(inst, known, name, idx, policy='minimax', max_probes=64,
            lam=2.0):
    t0 = time.time()
    co = PACT(inst, pact_mode='complete', use_ga=False)
    lb, ub, sched, mach = co.initial_bounds()
    if ub is None:
        return dict(name=name, idx=idx, known=known, policy=policy,
                    ok=False, error='no-initial-ub', t=0.0)
    L, U = int(lb), int(ub)
    pin0 = L
    sched = list(sched) if sched is not None else None
    mach = list(mach) if mach is not None else None
    lb_proof = co._ensure_lb_proof(L)
    if lb_proof is None:
        r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            lb_proof = r['proof']
    if lb_proof is None:
        return dict(name=name, idx=idx, known=known, policy=policy,
                    ok=False, error='no-lb-proof', t=0.0)
    probes = 0
    pact_lp = pact_nodes = pact_cert_lp = 0
    partial_ok = partial_fail = 0
    first = True
    lb0, ub0 = L, U
    steps = []

    def audit_state():
        nonlocal partial_ok, partial_fail
        pc = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1

    audit_state()
    while L < U and probes < max_probes:
        L0, U0 = L, U
        h = choose_h(policy, L, U, first, pin=pin0, lam=lam)
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        probes += 1
        first = False
        pact_lp += r.get('lp_solves', 0)
        pact_nodes += r.get('nodes', 0)
        pact_cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False:
            lb_proof = r['proof']
            L = h + 1
            co._record_proof(lb_proof)
            steps.append(dict(h=h, v=False, L0=L0, U0=U0, L1=L, U1=U,
                              lp=r.get('lp_solves', 0)))
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                sched, mach = list(s2), list(m2)
            steps.append(dict(h=h, v=True, L0=L0, U0=U0, L1=L, U1=U,
                              cmax=c2, lp=r.get('lp_solves', 0)))
        else:
            steps.append(dict(h=h, v=None, L0=L0, U0=U0, L1=L, U1=U,
                              lp=r.get('lp_solves', 0)))
            break
        audit_state()

    final = ICFCertificate(inst, U, sched, mach, lb_proof) \
        if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                 probe=probes)
    partial_final = bool(partial.audit_rdf())
    return dict(
        name=name, idx=idx, known=known, policy=policy,
        opt=U, lb=L, lb0=lb0, ub0=ub0, gap0=ub0 - lb0,
        certified=bool(L == U and final_ok),
        audit=final_ok, cert_h=(U - 1 if L == U else None),
        probes=probes, queries=probes,
        pact_lp=pact_lp, pact_nodes=pact_nodes,
        pact_cert_lp=pact_cert_lp,
        pin_lp=getattr(co, 'pin_lp', 0),
        partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_final,
        proof_kind=(final.lb_proof.kind if final is not None else
                    getattr(lb_proof, 'kind', None)),
        steps=steps,
        t=round(time.time() - t0, 4),
        ok=bool(L == U and U == known and final_ok and
                partial_fail == 0 and partial_final),
    )


# --------------------------------------------------------------- frontier
def proof_box(p):
    """Root forbidden set exposed by a proof (empty for global proofs)."""
    seen = set()
    while p is not None and id(p) not in seen:
        seen.add(id(p))
        f = getattr(p, 'forbid0', None)
        if f is not None:
            return frozenset(f)
        p = getattr(p, 'source', None)
    return frozenset()


def cut_box(inst, target, F):
    """Drop forbidden literals outside the target domain."""
    out = set()
    for (i, t) in F:
        lo, hi = _domain(inst, target, i)
        if lo <= t <= hi:
            out.add((i, t))
    return frozenset(out)


class BoxCutProof:
    """NO(source_h | src_box) rebased to NO(target | cut(src_box))."""

    kind = 'mec-box-cut'

    def __init__(self, inst, target, source, src_box, target_box):
        self.inst = inst
        self.h = int(target)
        self.source = source
        self.src_box = frozenset(src_box)
        self.forbid0 = frozenset(target_box)

    def audit_rdf(self):
        try:
            if self.source is None or self.source.h < self.h:
                return False
            if self.src_box != proof_box(self.source):
                return False
            if self.forbid0 != cut_box(self.inst, self.h, self.src_box):
                return False
            return bool(self.source.audit_rdf())
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class MECFrontierProof:
    """A FrontierProof rebuilt at the final target horizon.

    The partition tree was built at the initial U-1, which is >= the
    final target.  Splits remain non-empty when the horizon drops, and
    each leaf proof is rebased with BoxCutProof.  This is the mixed-
    horizon rule that v9.0 listed as a risk.
    """

    kind = 'mec-frontier'

    def __init__(self, inst, target, tree):
        self.inst = inst
        self.h = int(target)
        self.target = int(target)
        self.tree = tree

    def _times(self, i, F):
        lo, hi = _domain(self.inst, self.target, i)
        return [t for t in range(lo, hi + 1) if (i, t) not in F]

    def _check(self, node, F):
        tag = node[0]
        if tag == 'leaf':
            _, leaf_F, h, proof = node
            lf = cut_box(self.inst, self.target, leaf_F)
            if set(lf) != set(F):
                return False
            if proof is None:
                return False
            src_box = proof_box(proof)
            target_box = cut_box(self.inst, self.target, src_box)
            if not set(target_box) <= set(F):
                return False
            if proof.h < self.target:
                return False
            return bool(proof.audit_rdf())
        if tag == 'split':
            _, i, mid, parent_F, lo, hi = node
            pf = cut_box(self.inst, self.target, parent_F)
            if set(pf) != set(F):
                return False
            times = sorted(self._times(i, F))
            lo_t = [t for t in times if t > mid]
            hi_t = [t for t in times if t <= mid]
            if not lo_t or not hi_t:
                return False
            loF = F | {(i, t) for t in lo_t}
            hiF = F | {(i, t) for t in hi_t}
            return self._check(lo, loF) and self._check(hi, hiF)
        return False

    def audit_rdf(self):
        try:
            return self._check(self.tree, frozenset())
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class FLeaf:
    __slots__ = ('F', 'L', 'proof', 'parent', 'children', 'i', 'mid')

    def __init__(self, F, L, proof):
        self.F = frozenset(F)
        self.L = int(L)
        self.proof = proof
        self.parent = None
        self.children = None
        self.i = self.mid = None


class Frontier:
    """A live multi-leaf lower-bound frontier with alpha cutoff.

    Invariant: each open leaf f carries pi_f : NO(L_f-1 | F_f); the
    global lower bound is min_f L_f; the global upper bound U comes from
    one feasible schedule.  If L_f >= U the leaf is closed by
    monotonicity (pi_f already proves NO(U-1 | F_f)); this is the
    minimax/alpha cutoff.  Splitting is sound because a proof for F is
    also a proof for any F' superset of F.
    """
    def __init__(self, inst, root_F, L, root_proof, U):
        self.inst = inst
        self.root = FLeaf(root_F, L, root_proof)
        self.open = [self.root]
        self.closed = []
        self.U = int(U)
        self.leaves = 1
        self.splits = 0
        self.prunes = 0
        self.probes = 0
        self.lp = 0
        self.cert_lp = 0
        self.nodes = 0
        self.ledger = []
        self.fallbacks = 0
        self.global_no = 0

    def L(self):
        return min(f.L for f in self.open) if self.open else self.U

    def _allowed(self, f, i, target):
        lo, hi = _domain(self.inst, target, i)
        return [t for t in range(lo, hi + 1) if (i, t) not in f.F]

    def split(self, f, target, mode='width'):
        """Split f on a job/time; children inherit L_f and pi_f."""
        cand = []
        for i in range(self.inst['n']):
            ts = self._allowed(f, i, target)
            if len(ts) < 2:
                continue
            cand.append((i, ts))
        if not cand:
            return False
        if mode == 'width':
            i, ts = max(cand, key=lambda x: (len(x[1]), -x[0]))
        else:
            i, ts = cand[0]
        mid = ts[len(ts) // 2 - 1]
        lo_t = [t for t in ts if t > mid]
        hi_t = [t for t in ts if t <= mid]
        if not lo_t or not hi_t:
            return False
        F0 = f.F | {(i, t) for t in lo_t}
        F1 = f.F | {(i, t) for t in hi_t}
        a = FLeaf(F0, f.L, f.proof)
        b = FLeaf(F1, f.L, f.proof)
        a.parent = b.parent = f
        f.children = (a, b)
        f.i, f.mid = i, mid
        self.open.remove(f)
        self.open.extend((a, b))
        self.leaves += 1
        self.splits += 1
        return True

    def prune(self):
        """Close every open leaf with L_f >= U (alpha cutoff)."""
        keep = []
        for f in self.open:
            if f.L >= self.U:
                self.closed.append(f)
                self.prunes += 1
            else:
                keep.append(f)
        self.open = keep

    def probe(self, f, h):
        r = pact_decide(self.inst, h, depthcap=None, nodecap=None,
                        forbid0=f.F)
        self.probes += 1
        self.lp += r.get('lp_solves', 0)
        self.cert_lp += r.get('cert_lp', 0)
        self.nodes += r.get('nodes', 0)
        if r['verdict'] is False:
            f.L = h + 1
            f.proof = r['proof']
            self.ledger.append(dict(op='NO', h=h, L=f.L, U=self.U,
                                    lp=r.get('lp_solves', 0)))
            self.prune()
        elif r['verdict'] is True:
            c = cmax(self.inst, r['schedule'])
            if c < self.U and check_schedule(self.inst, c,
                                             r['schedule'],
                                             r['machine']):
                self.U = c
                self.schedule = list(r['schedule'])
                self.machine = list(r['machine'])
            self.ledger.append(dict(op='YES', h=h, cmax=c, U=self.U,
                                    lp=r.get('lp_solves', 0)))
            self.prune()
        else:
            # Local oracle is inconclusive (e.g. a sub-box LP leaf has no
            # replayable Farkas certificate).  Fall back to the global
            # root; a global NO closes every leaf by monotonicity, and a
            # global YES gives a valid incumbent.
            self.fallbacks += 1
            g = pact_decide(self.inst, h, depthcap=None, nodecap=None)
            self.probes += 1
            self.lp += g.get('lp_solves', 0)
            self.cert_lp += g.get('cert_lp', 0)
            self.nodes += g.get('nodes', 0)
            if g['verdict'] is False:
                self.global_no += 1
                for x in self.open:
                    if x.L <= h:
                        x.L = h + 1
                        x.proof = g['proof']
                self.ledger.append(dict(op='GLOBAL-NO', h=h,
                                        L=self.L(), U=self.U,
                                        lp=g.get('lp_solves', 0)))
                self.prune()
            elif g['verdict'] is True:
                c = cmax(self.inst, g['schedule'])
                if c < self.U and check_schedule(self.inst, c,
                                                 g['schedule'],
                                                 g['machine']):
                    self.U = c
                    self.schedule = list(g['schedule'])
                    self.machine = list(g['machine'])
                self.ledger.append(dict(op='GLOBAL-YES', h=h,
                                        cmax=c, U=self.U,
                                        lp=g.get('lp_solves', 0)))
                self.prune()
            else:
                self.ledger.append(dict(op='UNKNOWN', h=h, L=f.L,
                                        U=self.U))
        return r['verdict']

    def _tree(self, f, target):
        if f.children is None:
            return ('leaf', f.F, f.proof.h, f.proof)
        a, b = f.children
        return ('split', f.i, f.mid, f.F,
                self._tree(a, target), self._tree(b, target))

    def certificate(self, target):
        if self.open:
            return None
        return MECFrontierProof(self.inst, target,
                                self._tree(self.root, target))


def run_frontier(inst, known, name, idx, split_rounds=2, target=None,
                 policy='minimax', max_probes=256):
    """Pre-split the root, then run a lower-first/minimax frontier."""
    t0 = time.time()
    co = PACT(inst, pact_mode='complete', use_ga=False)
    lb, ub, sched, mach = co.initial_bounds()
    if ub is None:
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='no-initial-ub', t=0.0)
    L, U = int(lb), int(ub)
    target = U - 1 if target is None else int(target)
    proof = co._ensure_lb_proof(L)
    if proof is None:
        r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            proof = r['proof']
    if proof is None:
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='no-lb-proof', t=0.0)
    fr = Frontier(inst, frozenset(), L, proof, U)
    fr.schedule, fr.machine = list(sched), list(mach)
    for _ in range(split_rounds):
        cand = sorted(fr.open, key=lambda f: (f.L, -len(f.F)))
        if not cand:
            break
        if not fr.split(cand[0], target):
            break
    first = True
    pin0 = L
    while fr.open and fr.L() < fr.U and fr.probes < max_probes:
        f = min(fr.open, key=lambda x: (x.L, len(x.F)))
        h = choose_h(policy, f.L, fr.U, first, pin=pin0)
        first = False
        v = fr.probe(f, h)
        if v is None:
            break
        if not fr.open:
            break
    cert = fr.certificate(fr.U - 1) if not fr.open else None
    cert_ok = bool(cert is not None and cert.audit_rdf())
    sched_ok = bool(fr.schedule is not None and fr.machine is not None
                    and check_schedule(inst, fr.U, fr.schedule,
                                       fr.machine))
    final_ok = bool(fr.L() == fr.U and sched_ok and cert_ok)
    return dict(name=name, idx=idx, known=known, policy=policy,
                opt=fr.U, L=fr.L(), U=fr.U, known_opt=known,
                gap0=U - L, leaves=fr.leaves, splits=fr.splits,
                prunes=fr.prunes, probes=fr.probes,
                fallbacks=fr.fallbacks, global_no=fr.global_no,
                pact_lp=fr.lp, pact_cert_lp=fr.cert_lp,
                nodes=fr.nodes,
                frontier_ok=cert_ok, final_audit=final_ok,
                schedule_ok=sched_ok,
                certified=final_ok,
                t=round(time.time() - t0, 4),
                ok=bool(final_ok and fr.U == known))
