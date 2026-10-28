"""GCL-ICF: a heap-ordered genetic certificate lattice for fixed-h scheduling.

The trusted object is a *frontier certificate*: a partition of start-time
boxes, each leaf carrying a local lower bound L_f and a replayable proof
of NO(L_f - 1 | F_f).  The global lower bound is min_f L_f.  A checked
schedule (s, m) with Cmax(s)=U is the upper witness.  If L=U the frontier
is an optimality certificate.

The new layer is a small-step certificate machine:

  * a heap orders the open leaves by their local lower bound;
  * a population of frontier certificates is evolved by certified
    crossover (overlay of two partition trees) and certified mutation
    (PROBE / SPLIT / GA-SCHEDULE);
  * only audited NO proofs and check_schedule-verified schedules enter
    any state.  The GA is therefore an untrusted oracle: it can only
    waste work, never invalidate a certificate.

This module intentionally keeps the live search, the overlay operator,
the GA hook and the population loop in one file so that every transition
can be audited by the same checker.
"""
import sys
import time
import heapq
import random
import collections

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from sage import SubsumptionProof, _domain, ga_schedule
from pact import PACT, pact_decide
from rdf import check_schedule
from cert import verify
from icf import cmax, CertLeafProof, _proof_forbid, corpora


# --------------------------------------------------------------- boxes
def project_forbid(inst, h, F):
    """Keep only forbidden pairs inside the start domains at horizon h."""
    out = set()
    for i, t in F:
        lo, hi = _domain(inst, h, i)
        if lo <= t <= hi:
            out.add((i, t))
    return frozenset(out)


def allowed_times(inst, h, i, F):
    lo, hi = _domain(inst, h, i)
    return [t for t in range(lo, hi + 1) if (i, t) not in F]


def box_measure(inst, h, F):
    return sum(len(allowed_times(inst, h, i, F))
               for i in range(inst['n']))


def empty_job(inst, h, F):
    for i in range(inst['n']):
        if not allowed_times(inst, h, i, F):
            return i
    return None


# --------------------------------------------------------------- live tree
class Leaf:
    __slots__ = ('F', 'L', 'proof', 'parent', 'side')

    def __init__(self, F, L, proof, parent=None, side=None):
        self.F = frozenset(F)
        self.L = int(L)
        self.proof = proof
        self.parent = parent
        self.side = side


class Split:
    __slots__ = ('F', 'i', 'mid', 'lo', 'hi', 'parent', 'side')

    def __init__(self, F, i, mid, parent=None, side=None):
        self.F = frozenset(F)
        self.i = int(i)
        self.mid = int(mid)
        self.lo = None
        self.hi = None
        self.parent = parent
        self.side = side


def collect_leaves(node, out):
    if isinstance(node, Leaf):
        out.append(node)
        return
    collect_leaves(node.lo, out)
    collect_leaves(node.hi, out)


def snapshot(node):
    if isinstance(node, Leaf):
        return ('leaf', frozenset(node.F), int(node.L), node.proof)
    return ('split', int(node.i), int(node.mid), frozenset(node.F),
            snapshot(node.lo), snapshot(node.hi))


def split_leaf(inst, leaf, i, mid, H):
    """Replace leaf by {s_i <= mid} and {s_i > mid} at horizon H."""
    times = allowed_times(inst, H, i, leaf.F)
    le = [t for t in times if t <= mid]
    gt = [t for t in times if t > mid]
    if not le or not gt:
        return None
    F_le = leaf.F | frozenset((i, t) for t in gt)
    F_gt = leaf.F | frozenset((i, t) for t in le)
    sp = Split(leaf.F, i, mid, leaf.parent, leaf.side)
    sp.lo = Leaf(F_le, leaf.L, leaf.proof, sp, 'lo')
    sp.hi = Leaf(F_gt, leaf.L, leaf.proof, sp, 'hi')
    if leaf.parent is None:
        pass
    elif leaf.side == 'lo':
        leaf.parent.lo = sp
    else:
        leaf.parent.hi = sp
    return sp


def close_empty(inst, leaf, H):
    """Close a leaf that has no allowed start at horizon H."""
    i = empty_job(inst, H, leaf.F)
    if i is None:
        return False
    leaf.L = int(H) + 1
    leaf.proof = CertLeafProof(inst, H, leaf.F,
                               {'kind': 'empty', 'job': i})
    return True


# --------------------------------------------------------------- projection
def project_tree(inst, target, node):
    """Project a tree to a smaller target horizon, collapsing empty sides."""
    tag = node[0]
    if tag == 'leaf':
        _, F, L, proof = node
        Fp = project_forbid(inst, target, F)
        if empty_job(inst, target, Fp) is not None:
            return None
        if proof is None or proof.h != L - 1:
            return None
        return ('leaf', Fp, int(L), proof)
    _, i, mid, F, lo, hi = node
    Fp = project_forbid(inst, target, F)
    if empty_job(inst, target, Fp) is not None:
        return None
    times = allowed_times(inst, target, i, Fp)
    le = [t for t in times if t <= mid]
    gt = [t for t in times if t > mid]
    if not le:
        return project_tree(inst, target, hi)
    if not gt:
        return project_tree(inst, target, lo)
    plo = project_tree(inst, target, lo)
    phi = project_tree(inst, target, hi)
    if plo is None:
        return phi
    if phi is None:
        return plo
    return ('split', i, mid, Fp, plo, phi)


# --------------------------------------------------------------- certificate
class GCLFrontierProof(Proof):
    """A partial frontier at target horizon h.

    Leaf: ('leaf', F, L, proof), proof : NO(L-1 | F).
    Split: ('split', i, mid, F, lo, hi), children partition F on job i
    at the target horizon.  A leaf is closed at this target iff
    L-1 >= target; otherwise it is an open local bound.
    """

    kind = 'gcl-frontier'

    def __init__(self, inst, target, tree):
        super().__init__(inst, target)
        self.target = int(target)
        self.tree = tree
        self.L = None
        self.n_open = None

    def _check(self, node, F):
        tag = node[0]
        if tag == 'leaf':
            _, leaf_F, L, proof = node
            if set(leaf_F) != set(F):
                return None
            if proof is None or proof.h != L - 1:
                return None
            if not proof.audit_rdf():
                return None
            relF = project_forbid(self.inst, self.target, F)
            relP = project_forbid(self.inst, self.target,
                                  _proof_forbid(proof))
            if not relP <= relF:
                return None
            if empty_job(self.inst, self.target, relF) is not None:
                return None
            return (int(L), 0 if L - 1 >= self.target else 1)
        if tag == 'split':
            _, i, mid, parent_F, lo, hi = node
            if set(parent_F) != set(F):
                return None
            times = allowed_times(self.inst, self.target, i, F)
            le = [t for t in times if t <= mid]
            gt = [t for t in times if t > mid]
            if not le or not gt:
                return None
            loF = F | frozenset((i, t) for t in gt)
            hiF = F | frozenset((i, t) for t in le)
            a = self._check(lo, loF)
            b = self._check(hi, hiF)
            if a is None or b is None:
                return None
            return (min(a[0], b[0]), a[1] + b[1])
        return None

    def audit_rdf(self):
        try:
            r = self._check(self.tree, frozenset())
            if r is None:
                return False
            self.L = int(r[0])
            self.n_open = int(r[1])
            return True
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class GCLPartialCertificate:
    """A certified bracket L <= OPT <= U at any intermediate state."""

    kind = 'gcl-partial'

    def __init__(self, inst, frontier, schedule, machine, probe=0):
        self.inst = inst
        self.frontier = frontier
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.probe = int(probe)
        self.L = None
        self.U = None

    def audit_rdf(self):
        try:
            if not self.frontier.audit_rdf():
                return False
            if self.frontier.L is None:
                return False
            if self.schedule is None or self.machine is None:
                return False
            U = cmax(self.inst, self.schedule)
            if self.frontier.L > U:
                return False
            if not check_schedule(self.inst, U, self.schedule,
                                  self.machine):
                return False
            self.L = self.frontier.L
            self.U = U
            return True
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class GCLCertificate:
    """Final certificate: all leaves closed at U-1 plus Cmax=U."""

    kind = 'gcl-opt'

    def __init__(self, inst, opt, schedule, machine, frontier):
        self.inst = inst
        self.opt = int(opt)
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.frontier = frontier
        self.L = None

    def audit_rdf(self):
        try:
            if not self.frontier.audit_rdf():
                return False
            if self.frontier.n_open != 0:
                return False
            if self.frontier.L != self.opt:
                return False
            if self.schedule is None or self.machine is None:
                return False
            if cmax(self.inst, self.schedule) != self.opt:
                return False
            if not check_schedule(self.inst, self.opt,
                                  self.schedule, self.machine):
                return False
            self.L = self.frontier.L
            return True
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


# --------------------------------------------------------------- live state
class FrontierState:
    """One heap-ordered frontier certificate plus its incumbent."""

    def __init__(self, inst, initial, H0=None):
        L0, U0, sched, mach, proof = initial
        self.inst = inst
        self.H0 = int(U0 - 1 if H0 is None else H0)
        self.root = Leaf(frozenset(), int(L0), proof)
        self.schedule = list(sched)
        self.machine = list(mach)
        self.U = int(U0)
        self.heap = []
        self.counter = 0
        self.live = set()
        self.probes = 0
        self.splits = 0
        self.yes = 0
        self.no = 0
        self.unknown = 0
        self.lp = 0
        self.cert_lp = 0
        self.ga_calls = 0
        self.ga_improve = 0
        self.ga_stats = []
        self.partial_ok = 0
        self.partial_fail = 0
        self.audit_every = True
        self._push(self.root)

    # -- heap
    def _push(self, leaf):
        if leaf.L < self.U:
            self.counter += 1
            heapq.heappush(self.heap, (leaf.L, self.counter, leaf))
            self.live.add(leaf)

    def _rebuild(self):
        self.heap = []
        self.counter = 0
        self.live = set()
        leaves = []
        collect_leaves(self.root, leaves)
        for leaf in leaves:
            if close_empty(self.inst, leaf, self.U - 1):
                pass
            self._push(leaf)

    def _pop(self):
        while self.heap:
            L, _, leaf = heapq.heappop(self.heap)
            if leaf not in self.live:
                continue
            if leaf.L != L:
                continue
            if leaf.L >= self.U:
                self.live.discard(leaf)
                continue
            self.live.discard(leaf)
            return leaf
        return None

    def leaves(self):
        out = []
        collect_leaves(self.root, out)
        return out

    def live_leaves(self):
        return [x for x in self.leaves() if x.L < self.U]

    def global_L(self):
        ls = self.leaves()
        if not ls:
            return self.U
        return min(x.L for x in ls)

    # -- certificate
    def frontier(self, target=None):
        target = int(self.U - 1 if target is None else target)
        tree = project_tree(self.inst, target, snapshot(self.root))
        if tree is None:
            return None
        fp = GCLFrontierProof(self.inst, target, tree)
        return fp if fp.audit_rdf() else None

    def audit_state(self):
        fp = self.frontier()
        if fp is None:
            self.partial_fail += 1
            return None
        pc = GCLPartialCertificate(self.inst, fp, self.schedule,
                                   self.machine, probe=self.probes)
        if pc.audit_rdf():
            self.partial_ok += 1
        else:
            self.partial_fail += 1
        return pc

    def final_certificate(self):
        fp = self.frontier()
        if fp is None or fp.n_open != 0 or fp.L != self.U:
            return None
        cert = GCLCertificate(self.inst, self.U, self.schedule,
                              self.machine, fp)
        return cert if cert.audit_rdf() else None

    # -- transitions
    def _adopt_schedule(self, s2, m2):
        c2 = cmax(self.inst, s2)
        if c2 < self.U and check_schedule(self.inst, c2, s2, m2):
            self.U = int(c2)
            self.schedule = list(s2)
            self.machine = list(m2)
            self._rebuild()
            return True
        return False

    def probe(self, policy='binary', nodecap=None, rng=None):
        leaf = self._pop()
        if leaf is None:
            return dict(kind='empty')
        h = choose_h(policy, leaf.L, self.U, rng)
        r = pact_decide(self.inst, h, depthcap=None, nodecap=nodecap,
                        forbid0=frozenset(leaf.F))
        self.probes += 1
        self.lp += int(r.get('lp_solves', 0))
        self.cert_lp += int(r.get('cert_lp', 0))
        if r['verdict'] is False:
            self.no += 1
            leaf.L = int(h) + 1
            leaf.proof = r['proof']
            if leaf.L < self.U:
                self._push(leaf)
            return dict(kind='no', h=h, L=leaf.L)
        if r['verdict'] is True:
            self.yes += 1
            c2 = cmax(self.inst, r['schedule'])
            improved = self._adopt_schedule(r['schedule'], r['machine'])
            return dict(kind='yes', h=h, cmax=c2, improved=improved)
        self.unknown += 1
        pair = choose_split(self.inst, leaf, self.H0, r)
        if pair is None:
            r2 = pact_decide(self.inst, h, depthcap=None, nodecap=None,
                             forbid0=frozenset(leaf.F))
            self.probes += 1
            self.lp += int(r2.get('lp_solves', 0))
            self.cert_lp += int(r2.get('cert_lp', 0))
            if r2['verdict'] is False:
                self.no += 1
                leaf.L = int(h) + 1
                leaf.proof = r2['proof']
                if leaf.L < self.U:
                    self._push(leaf)
                return dict(kind='no-fallback', h=h, L=leaf.L)
            if r2['verdict'] is True:
                self.yes += 1
                improved = self._adopt_schedule(r2['schedule'],
                                                r2['machine'])
                return dict(kind='yes-fallback', h=h, improved=improved)
            self.unknown += 1
            return dict(kind='stuck', h=h)
        i, mid = pair
        was_root = leaf.parent is None
        sp = split_leaf(self.inst, leaf, i, mid, self.H0)
        if sp is None:
            return dict(kind='stuck', h=h)
        if was_root:
            self.root = sp
        self.splits += 1
        for c in (sp.lo, sp.hi):
            if not close_empty(self.inst, c, self.U - 1):
                self._push(c)
        return dict(kind='split', h=h, i=i, mid=mid)

    def ga_step(self, budget=300, pop=20, gens=10, seed=0):
        self.ga_calls += 1
        got, st = ga_schedule(self.inst, self.U - 1, pop=pop, gens=gens,
                              budget=budget, seed=seed)
        self.ga_stats.append(st)
        if got is None:
            return False
        improved = self._adopt_schedule(got[0], got[1])
        if improved:
            self.ga_improve += 1
        return improved

    def run(self, max_steps=200, policy='binary', nodecap=None,
            ga_every=0, ga_budget=300, ga_pop=20, ga_gens=10,
            seed=0, audit_every=True):
        rng = random.Random(seed)
        self.audit_every = audit_every
        if audit_every:
            self.audit_state()
        for step in range(max_steps):
            if self.global_L() >= self.U:
                break
            if ga_every and step and step % ga_every == 0:
                self.ga_step(budget=ga_budget, pop=ga_pop,
                             gens=ga_gens, seed=seed + step)
            out = self.probe(policy=policy, nodecap=nodecap, rng=rng)
            if audit_every:
                self.audit_state()
            if out['kind'] == 'empty':
                break
            if out['kind'] == 'stuck':
                break
        return self.result()

    def result(self):
        fp = self.frontier()
        L = fp.L if fp is not None else None
        final = self.final_certificate() if L is not None else None
        return dict(
            L=L, U=self.U, lag1=self.global_L(),
            probes=self.probes, splits=self.splits,
            yes=self.yes, no=self.no, unknown=self.unknown,
            lp=self.lp, cert_lp=self.cert_lp,
            ga_calls=self.ga_calls, ga_improve=self.ga_improve,
            leaves=len(self.leaves()),
            open=(fp.n_open if fp is not None else None),
            partial_ok=self.partial_ok, partial_fail=self.partial_fail,
            certified=bool(final is not None),
            audit=bool(final is not None),
            schedule=list(self.schedule),
            machine=list(self.machine),
            tree=snapshot(self.root),
        )


# --------------------------------------------------------------- policies
def choose_h(policy, L, U, rng=None):
    L, U = int(L), int(U)
    if U <= L:
        return L
    if policy == 'lower':
        return L
    if policy == 'upper':
        return U - 1
    if policy == 'binary':
        return (L + U) // 2
    if policy == 'pact':
        return L if U - L <= 4 else (L + U) // 2
    if policy == 'random':
        return (rng or random).randint(L, U - 1)
    if policy.startswith('mix:'):
        # alternate lower and binary by a deterministic step counter is
        # handled by callers; here mix:0.5 means midpoint
        return (L + U) // 2
    raise ValueError('unknown policy %r' % (policy,))


def choose_split(inst, leaf, H, r=None):
    """Choose a split at the envelope horizon H."""
    if r is not None:
        bj = r.get('branch_jobs') or []
        for item in bj:
            try:
                i, mid = int(item[0]), int(item[1])
            except Exception:
                continue
            times = allowed_times(inst, H, i, leaf.F)
            if any(t <= mid for t in times) and any(t > mid for t in times):
                return i, mid
    best = None
    for i in range(inst['n']):
        times = allowed_times(inst, H, i, leaf.F)
        if len(times) >= 2:
            mid = times[len(times) // 2 - 1]
            score = len(times)
            if best is None or score > best[0]:
                best = (score, i, mid)
    if best is None:
        return None
    return best[1], best[2]


# --------------------------------------------------------------- overlay
def _contains_leaf(inst, H, node, F_base):
    """Return a leaf of node whose box contains the base box, if any."""
    tag = node[0]
    Fb = project_forbid(inst, H, F_base)
    if tag == 'leaf':
        _, F, L, proof = node
        Fo = project_forbid(inst, H, F)
        if Fo <= Fb:
            return node
        return None
    _, i, mid, F, lo, hi = node
    Fo = project_forbid(inst, H, F)
    if not Fo <= Fb:
        return None
    r = _contains_leaf(inst, H, lo, F_base)
    if r is not None:
        return r
    return _contains_leaf(inst, H, hi, F_base)


def overlay(inst, H, base, other):
    """Certified one-sided crossover of two partition trees.

    The base tree supplies the partition.  Each base leaf inherits the
    strongest applicable local bound from the other tree (if the other
    leaf's box contains it).  The result is a sound certificate; it is
    not necessarily the full lattice join, only a sound and cheap one.
    """
    tag = base[0]
    if tag == 'leaf':
        _, F, L, proof = base
        g = _contains_leaf(inst, H, other, F)
        if g is not None:
            _, gF, gL, gproof = g
            if int(gL) > int(L):
                L, proof = int(gL), gproof
        return ('leaf', frozenset(F), int(L), proof)
    _, i, mid, F, lo, hi = base
    return ('split', int(i), int(mid), frozenset(F),
            overlay(inst, H, lo, other),
            overlay(inst, H, hi, other))


def cert_metrics(inst, U, tree):
    target = int(U) - 1
    proj = project_tree(inst, target, tree)
    if proj is None:
        return None
    fp = GCLFrontierProof(inst, target, proj)
    if not fp.audit_rdf():
        return None
    return dict(L=fp.L, open=fp.n_open, leaves=count_leaves(proj),
                tree=proj, frontier=fp)


def count_leaves(node):
    if node[0] == 'leaf':
        return 1
    return count_leaves(node[4]) + count_leaves(node[5])


def crossover(inst, U, tree_a, tree_b, H):
    """Return the better audited overlay of two trees at the same envelope."""
    cands = []
    for base, other in ((tree_a, tree_b), (tree_b, tree_a)):
        tr = overlay(inst, H, base, other)
        m = cert_metrics(inst, U, tr)
        if m is not None:
            cands.append(m)
    ma = cert_metrics(inst, U, tree_a)
    mb = cert_metrics(inst, U, tree_b)
    for m in (ma, mb):
        if m is not None:
            cands.append(m)
    if not cands:
        return None
    best = max(cands, key=lambda m: (m['L'], -m['open'], -m['leaves']))
    return best


# --------------------------------------------------------------- population
class Population:
    """A small genetic population of frontier certificates.

    Every individual is mutated by its own heap search and by the GA
    upper oracle; crossover is the certified overlay above.  Only
    audited individuals are retained.
    """

    def __init__(self, inst, initial, mu=4, H0=None):
        self.inst = inst
        self.H0 = int(initial[1] - 1 if H0 is None else H0)
        self.initial = initial
        self.mu = int(mu)
        self.members = [FrontierState(inst, initial, H0=self.H0)
                        for _ in range(self.mu)]
        self.crossovers = 0
        self.cross_ok = 0
        self.cross_fail = 0
        self.audit_ok = 0
        self.audit_fail = 0
        self.best_tree = None
        self.best = None

    def _share_U(self):
        U = min(m.U for m in self.members)
        for m in self.members:
            if m.U != U:
                m.U = U
                # keep the schedule of the member that attained U
                m._rebuild()

    def _best_member(self):
        cands = []
        for m in self.members:
            tree = snapshot(m.root)
            cm = cert_metrics(self.inst, m.U, tree)
            if cm is not None:
                cands.append((cm['L'], -cm['open'], -cm['leaves'], m, cm))
        if not cands:
            return None
        return max(cands, key=lambda x: x[:3])

    def _select(self):
        self.members.sort(key=lambda m: (-self._metric(m)['L'],
                                         self._metric(m)['open'],
                                         len(m.leaves())))
        del self.members[self.mu:]

    def _metric(self, m):
        cm = cert_metrics(self.inst, m.U, snapshot(m.root))
        if cm is None:
            return dict(L=-1, open=10**9, leaves=10**9)
        return cm

    def step(self, k=1, policy='binary', nodecap=None, ga_every=0,
             ga_budget=300, ga_pop=20, ga_gens=10, seed=0,
             cross=True, audit_every=True):
        # mutate each individual a few times
        for m in self.members:
            m.run(max_steps=k, policy=policy, nodecap=nodecap,
                  ga_every=ga_every, ga_budget=ga_budget,
                  ga_pop=ga_pop, ga_gens=ga_gens, seed=seed,
                  audit_every=audit_every)
        self._share_U()
        if cross and len(self.members) >= 2:
            # select two distinct parents by fitness
            ms = sorted(self.members,
                        key=lambda m: (-self._metric(m)['L'],
                                       self._metric(m)['open']))
            a, b = ms[0], ms[1]
            H = self.H0
            cm = crossover(self.inst, min(a.U, b.U),
                           snapshot(a.root), snapshot(b.root), H)
            self.crossovers += 1
            if cm is not None:
                self.cross_ok += 1
                child = FrontierState(self.inst, self.initial, H0=H)
                child.root = tree_to_live(cm['tree'], self.inst)
                child.U = min(a.U, b.U)
                child.schedule = list(a.schedule if a.U <= b.U
                                      else b.schedule)
                child.machine = list(a.machine if a.U <= b.U
                                     else b.machine)
                child._rebuild()
                if child.audit_state() is not None:
                    self.audit_ok += 1
                    self.members.append(child)
                else:
                    self.audit_fail += 1
            else:
                self.cross_fail += 1
        self._select()
        self._share_U()
        b = self._best_member()
        if b is not None:
            self.best = b[3]
            self.best_tree = b[4]['tree']
        return self.best

    def result(self):
        b = self._best_member()
        if b is None:
            return dict(certified=False, L=None, U=None,
                        crossovers=self.crossovers)
        _, _, _, m, cm = b
        final = m.final_certificate()
        return dict(
            L=cm['L'], U=m.U, certified=bool(final is not None),
            audit=bool(final is not None),
            probes=sum(x.probes for x in self.members),
            splits=sum(x.splits for x in self.members),
            lp=sum(x.lp for x in self.members),
            cert_lp=sum(x.cert_lp for x in self.members),
            ga_calls=sum(x.ga_calls for x in self.members),
            ga_improve=sum(x.ga_improve for x in self.members),
            crossovers=self.crossovers, cross_ok=self.cross_ok,
            cross_fail=self.cross_fail,
            audit_ok=self.audit_ok, audit_fail=self.audit_fail,
            partial_ok=sum(x.partial_ok for x in self.members),
            partial_fail=sum(x.partial_fail for x in self.members),
            leaves=cm['leaves'], open=cm['open'],
            schedule=list(m.schedule), machine=list(m.machine),
            tree=cm['tree'],
        )


def tree_to_live(node, inst, parent=None, side=None):
    if node[0] == 'leaf':
        _, F, L, proof = node
        return Leaf(F, L, proof, parent, side)
    _, i, mid, F, lo, hi = node
    sp = Split(F, i, mid, parent, side)
    sp.lo = tree_to_live(lo, inst, sp, 'lo')
    sp.hi = tree_to_live(hi, inst, sp, 'hi')
    return sp


# --------------------------------------------------------------- helpers
def pact_initial(inst):
    co = PACT(inst, pact_mode='complete', use_ga=False)
    lb, ub, sched, mach = co.initial_bounds()
    if ub is None:
        raise RuntimeError('no initial upper bound')
    L, U = int(lb), int(ub)
    proof = co._ensure_lb_proof(L)
    if proof is None:
        r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            proof = r['proof']
    if proof is None:
        raise RuntimeError('no lower-bound proof')
    return L, U, list(sched), list(mach), proof


def weak_initial(inst):
    from hap import init_weak
    return init_weak(inst)


def run_frontier(inst, known, name, idx, initial=None, policy='binary',
                 nodecap=None, max_steps=200, ga_every=0,
                 ga_budget=300, ga_pop=20, ga_gens=10, seed=0,
                 audit_every=True):
    t0 = time.time()
    if initial is None:
        initial = pact_initial(inst)
    st = FrontierState(inst, initial)
    out = st.run(max_steps=max_steps, policy=policy,
                 nodecap=nodecap, ga_every=ga_every,
                 ga_budget=ga_budget, ga_pop=ga_pop,
                 ga_gens=ga_gens, seed=seed,
                 audit_every=audit_every)
    out.update(name=name, idx=idx, known=known, policy=policy,
               nodecap=nodecap, t=round(time.time() - t0, 4))
    out['ok'] = bool(out['certified'] and out['U'] == known
                     and out['partial_fail'] == 0)
    return out


def run_population(inst, known, name, idx, initial=None, mu=4,
                   rounds=4, k=2, policy='binary', nodecap=None,
                   ga_every=0, ga_budget=300, ga_pop=20, ga_gens=10,
                   seed=0, cross=True, audit_every=True):
    t0 = time.time()
    if initial is None:
        initial = pact_initial(inst)
    pop = Population(inst, initial, mu=mu)
    for r in range(rounds):
        b = pop.step(k=k, policy=policy, nodecap=nodecap,
                     ga_every=ga_every, ga_budget=ga_budget,
                     ga_pop=ga_pop, ga_gens=ga_gens,
                     seed=seed + r, cross=cross,
                     audit_every=audit_every)
        if b is not None and b.global_L() >= b.U:
            break
    out = pop.result()
    out.update(name=name, idx=idx, known=known, mu=mu, rounds=rounds,
               k=k, policy=policy, nodecap=nodecap,
               t=round(time.time() - t0, 4))
    out['ok'] = bool(out['certified'] and out['U'] == known
                     and out.get('partial_fail', 0) == 0)
    return out
