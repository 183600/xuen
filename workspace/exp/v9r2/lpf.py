"""v9.1 ICF-LPF: LP-pinned frontier with a monotone bucket queue.

This module is the live multi-leaf companion of v9.0 ICF-PACT.  The
state is a partition tree over start-time boxes.  An open leaf f carries

    lam_f : an integer lower bound on OPT(box_f)
    pi_f  : an audited NO(lam_f - 1 | box_f) proof

and the shared upper bound U comes from one checked schedule.  The global
lower bound is

    L = min( min_{open f} lam_f , U ).

The new ingredient is *per-leaf LP pinning*: for a box B and target h we
compute the smallest horizon tau <= h at which the SD LP relaxation of B
is feasible.  The last infeasible LP probe at tau-1 yields a Farkas
certificate, so raising lam from the inherited value to tau is certified,
not heuristic.  A leaf is closed when its LP is infeasible at the target
U-1 (a Farkas leaf), or when lam_f >= U (alpha cutoff).

The frontier queue uses the fact that keys are integers and only increase
while U only decreases: an array of buckets with a monotone cursor gives
O(1) amortized insert/pop and O(T) total cursor movement, instead of a
binary heap's O(log F) per operation.  The implementation below is a
reference version; the bucket queue is in `BucketQueue`.

Proofs are stored with their original horizon.  Since a NO(h) proof is
also a NO(h') proof for every h' <= h, a proof generated at an old target
or at a pin horizon can be reused after U decreases.  `TargetFrontierProof`
implements the domain-restricted check: cut the proof's forbidden set to
the current target domain before comparing it with the leaf box.
"""
import sys
import time
import heapq

sys.path[:0] = ['exp/v9r2', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8j', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof, FarkasProof
from sage import BranchProof, _elig_aware, _domain
from cert import verify, integer_certificate
from sdecc import SDLP
from po import heads_tails
from prism import box_forbid
from rdf import check_schedule
from pact import PACT, pact_decide, _assign_machines, _integral_schedule
from icf import CertLeafProof


def cmax(inst, starts):
    return max(starts[i] + inst['p'][i] for i in range(inst['n']))


def _cut_domain(inst, h, F):
    """Drop forbidden literals outside the horizon-h start domain."""
    est, q = heads_tails(inst, 0, [0] * inst['n'])
    p = inst['p']
    out = set()
    for (i, t) in F:
        lo, hi = est[i], h - q[i] - p[i]
        if lo <= t <= hi:
            out.add((i, t))
    return frozenset(out)


def _allowed(inst, h, lo, hi, i):
    a, b = _domain(inst, h, i)
    a = max(a, int(lo[i]))
    b = min(b, int(hi[i]))
    return list(range(a, b + 1)) if a <= b else []


class TargetFrontierProof(Proof):
    """A partition tree whose leaves prove NO(target | F).

    Node forms:
        ('leaf', F, h, proof)
        ('split', i, mid, F, left, right)
    A leaf proof at h >= target is accepted if its root forbidden set,
    restricted to the target domain, is contained in F.  A NO proof on a
    weaker forbidden set implies NO on the leaf box (which forbids more).
    """

    kind = 'lpf-frontier'

    def __init__(self, inst, target, tree):
        super().__init__(inst, target)
        self.target = int(target)
        self.tree = tree

    def _check(self, node, F):
        tag = node[0]
        if tag == 'leaf':
            _, leaf_F, h, proof = node
            if frozenset(leaf_F) != F:
                return False
            if proof is None or proof.h != h or h < self.target:
                return False
            if not proof.audit_rdf():
                return False
            pf = _cut_domain(self.inst, self.target,
                             getattr(proof, 'forbid0', frozenset()))
            return set(pf) <= set(F)
        if tag == 'split':
            _, i, mid, parent_F, left, right = node
            if frozenset(parent_F) != F:
                return False
            ts = [t for t in _domain_times(self.inst, self.target, i)
                  if (i, t) not in F]
            lo_t = [t for t in ts if t > mid]
            hi_t = [t for t in ts if t <= mid]
            if not lo_t or not hi_t:
                return False
            loF = F | {(i, t) for t in lo_t}
            hiF = F | {(i, t) for t in hi_t}
            return (self._check(left, frozenset(loF))
                    and self._check(right, frozenset(hiF)))
        return False

    def audit_rdf(self):
        try:
            return self._check(self.tree, frozenset())
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def _domain_times(inst, h, i):
    a, b = _domain(inst, h, i)
    return list(range(a, b + 1))


class OptCertificate:
    """U-optimal frontier plus a checked schedule."""

    kind = 'lpf-opt'

    def __init__(self, inst, opt, schedule, machine, frontier):
        self.inst = inst
        self.opt = int(opt)
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.frontier = frontier

    def audit_rdf(self):
        try:
            if self.frontier is None or not self.frontier.audit_rdf():
                return False
            if self.schedule is None or self.machine is None:
                return False
            if cmax(self.inst, self.schedule) != self.opt:
                return False
            return bool(check_schedule(self.inst, self.opt,
                                       self.schedule, self.machine))
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class Leaf:
    __slots__ = ('lo', 'hi', 'lam', 'proof', 'parent', 'children',
                 'i', 'mid', 'closed', 'dead', 'empty_job', 'kind')

    def __init__(self, lo, hi, lam, proof):
        self.lo = tuple(int(x) for x in lo)
        self.hi = tuple(int(x) for x in hi)
        self.lam = int(lam)
        self.proof = proof
        self.parent = None
        self.children = None
        self.i = self.mid = None
        self.closed = False
        self.dead = False
        self.empty_job = None
        self.kind = 'open'

    def close(self):
        self.closed = True
        self.kind = 'closed'


class BucketQueue:
    """Monotone integer-key bucket queue.

    Keys are in [0, max_key].  Insertions never use a key below the
    cursor (children inherit the popped key or a pin raises it), and the
    cursor never moves backward.  Lazy dead entries are skipped on pop.
    """

    def __init__(self, max_key):
        self.max_key = int(max_key)
        self.buckets = [[] for _ in range(self.max_key + 1)]
        self.cursor = 0
        self.size = 0
        self.inserts = 0
        self.pops = 0
        self.skips = 0
        self.steps = 0

    def insert(self, leaf):
        k = max(0, min(self.max_key, leaf.lam))
        self.buckets[k].append(leaf)
        self.size += 1
        self.inserts += 1
        if k < self.cursor:
            # Only possible when the root key is below the initial cursor.
            self.cursor = k

    def pop_min(self):
        while self.cursor <= self.max_key:
            b = self.buckets[self.cursor]
            if b:
                leaf = b.pop()
                self.size -= 1
                self.pops += 1
                if leaf.dead or leaf.closed:
                    self.skips += 1
                    continue
                return leaf
            self.cursor += 1
            self.steps += 1
        return None

    def min_key(self):
        j = self.cursor
        while j <= self.max_key and not self.buckets[j]:
            j += 1
        return j

    def __bool__(self):
        return self.size > 0


class LPFrontier:
    def __init__(self, inst, L, U, schedule, machine, root_proof,
                 init_kwargs=None):
        self.inst = inst
        self.U = int(U)
        self.schedule = list(schedule)
        self.machine = list(machine)
        self.L0, self.U0 = int(L), int(U)
        self.elig = _elig_aware(inst)
        self.est, self.q = heads_tails(inst, 0, [0] * len(inst['p']))
        target = self.U - 1
        lo = [self.est[i] for i in range(inst['n'])]
        hi = [target - self.q[i] - inst['p'][i]
              for i in range(inst['n'])]
        self.root = Leaf(lo, hi, L, root_proof)
        self.queue = BucketQueue(max(1, self.U0))
        self.queue.insert(self.root)
        self.stats = dict(nodes=1, splits=0, closed=0, prunes=0,
                          pin_solves=0, target_solves=0, cert_lp=0,
                          fallback=0, yes=0, empty=0, pin_fail=0,
                          max_lam=0, t=0.0, queue_steps=0)
        self.init_kwargs = dict(init_kwargs or {})

    # ------------------------------------------------------------- boxes
    def _F(self, h, leaf):
        return box_forbid(self.inst, h, leaf.lo, leaf.hi)

    def _empty_job(self, h, leaf):
        for i in range(self.inst['n']):
            if not _allowed(self.inst, h, leaf.lo, leaf.hi, i):
                return i
        return None

    def _target(self):
        return self.U - 1

    # ---------------------------------------------------------- LP oracle
    def _build_lp(self, h, leaf):
        F = self._F(h, leaf)
        return SDLP(self.inst, h, self.est, self.q, use_dom=True,
                    elig_aware=self.elig, forbid=F), F

    def _solve_h(self, lp, h):
        b = [(0, 1)] * lp.N
        for c, key in enumerate(lp.cols):
            i, t = key[0], key[-1]
            if t > h - self.q[i] - self.inst['p'][i]:
                b[c] = (0, 0)
        return lp.solve(b)

    def _farkas(self, h, leaf):
        self.stats['cert_lp'] += 1
        F = self._F(h, leaf)
        c = integer_certificate(self.inst, h, use_dom=True,
                                elig_aware=self.elig, forbid=F)
        if c is None or not verify(self.inst, h, c, forbid=F):
            return None
        return CertLeafProof(self.inst, h, F, c)

    def _pin(self, lp, target, leaf):
        """Raise leaf.lam via LP feasibility; close if LP infeasible."""
        if lp.N == 0:
            return 'empty'
        res = self._solve_h(lp, target)
        self.stats['target_solves'] += 1
        if res.status == 2:
            return 'close'
        if res.status != 0:
            return 'unknown'
        if leaf.lam >= target:
            return res
        low, high = leaf.lam, target
        last_no = None
        while low < high:
            mid = (low + high) // 2
            r = self._solve_h(lp, mid)
            self.stats['pin_solves'] += 1
            if r.status == 2:
                low = mid + 1
                last_no = mid
            elif r.status == 0:
                high = mid
            else:
                return 'unknown'
        tau = low
        if tau > leaf.lam:
            if last_no is None:
                return 'unknown'
            pi = self._farkas(last_no, leaf)
            if pi is None:
                self.stats['pin_fail'] += 1
                return res
            leaf.lam = tau
            leaf.proof = pi
        return res

    # --------------------------------------------------------- transitions
    def _close_empty(self, leaf):
        target = self._target()
        i = self._empty_job(target, leaf)
        if i is None:
            return False
        F = self._F(target, leaf)
        leaf.proof = CertLeafProof(self.inst, target, F,
                                   {'kind': 'empty', 'job': i})
        leaf.close()
        leaf.kind = 'empty'
        self.stats['empty'] += 1
        self.stats['closed'] += 1
        return True

    def _close_no(self, leaf, h, proof):
        leaf.proof = proof
        leaf.close()
        leaf.kind = 'no'
        self.stats['closed'] += 1

    def _yes(self, leaf, starts, machine):
        c = cmax(self.inst, starts)
        if c < self.U and check_schedule(self.inst, c, starts, machine):
            self.U = c
            self.schedule = list(starts)
            self.machine = list(machine)
            self.stats['yes'] += 1
            return True
        return False

    def _choose_split(self, lp, z, leaf, target):
        best = None
        for i in range(self.inst['n']):
            times = _allowed(self.inst, target, leaf.lo, leaf.hi, i)
            if len(times) <= 1:
                continue
            dist = []
            frac = 0.0
            mass = 0.0
            for t in times:
                v = 0.0
                for c, key in enumerate(lp.cols):
                    if key[0] == i and key[-1] == t and z[c] > 1e-9:
                        v += z[c]
                dist.append((t, v))
                mass += v
                if 1e-7 < v < 1 - 1e-7:
                    frac += v
            if frac <= 1e-7:
                continue
            score = (mass, frac, -i)
            if best is None or score > best[0]:
                best = (score, i, dist, times)
        if best is None:
            # integral columns but no decoded schedule: split any wide job
            for i in range(self.inst['n']):
                times = _allowed(self.inst, target, leaf.lo, leaf.hi, i)
                if len(times) > 1:
                    mid = times[len(times) // 2 - 1]
                    return i, mid, times
            return None, None, None
        _, i, dist, times = best
        total = sum(v for _, v in dist)
        acc = 0.0
        mid = times[0]
        for t, v in dist:
            acc += v
            if acc >= 0.5 * max(total, 1e-12):
                mid = t
                break
        left = [t for t in times if t <= mid]
        right = [t for t in times if t > mid]
        if not left or not right:
            mid = times[len(times) // 2 - 1]
            left = [t for t in times if t <= mid]
            right = [t for t in times if t > mid]
        if not left or not right:
            return None, None, None
        return i, mid, times

    def _do_split(self, leaf, i, mid):
        llo, lhi = list(leaf.lo), list(leaf.hi)
        lhi[i] = mid
        rlo, rhi = list(leaf.lo), list(leaf.hi)
        rlo[i] = mid + 1
        a = Leaf(llo, lhi, leaf.lam, leaf.proof)
        b = Leaf(rlo, rhi, leaf.lam, leaf.proof)
        a.parent = b.parent = leaf
        leaf.children = (a, b)
        leaf.i, leaf.mid = i, mid
        leaf.dead = True
        self.queue.insert(a)
        self.queue.insert(b)
        self.stats['nodes'] += 2
        self.stats['splits'] += 1

    def _fallback(self, leaf, target):
        self.stats['fallback'] += 1
        F = self._F(target, leaf)
        r = pact_decide(self.inst, target, depthcap=None, nodecap=None,
                        forbid0=F)
        self.stats['pin_solves'] += r.get('lp_solves', 0)
        self.stats['cert_lp'] += r.get('cert_lp', 0)
        if r['verdict'] is False:
            self._close_no(leaf, target, r['proof'])
            return 'closed'
        if r['verdict'] is True:
            if not self._yes(leaf, r['schedule'], r['machine']):
                return 'stuck'
            if leaf.lam >= self.U:
                leaf.close()
                leaf.kind = 'alpha'
                self.stats['prunes'] += 1
                self.stats['closed'] += 1
                return 'closed'
            self.queue.insert(leaf)
            return 'yes'
        return 'stuck'

    def step(self):
        leaf = self.queue.pop_min()
        if leaf is None:
            return False
        target = self._target()
        if leaf.lam >= self.U:
            leaf.close()
            leaf.kind = 'alpha'
            self.stats['prunes'] += 1
            self.stats['closed'] += 1
            return True
        if self._close_empty(leaf):
            return True
        h = target
        lp, F = self._build_lp(h, leaf)
        pin = self._pin(lp, h, leaf)
        if pin == 'empty':
            self._close_empty(leaf)
            return True
        if pin == 'close':
            pi = self._farkas(h, leaf)
            if pi is None:
                if self._fallback(leaf, h) == 'stuck':
                    return False
            else:
                self._close_no(leaf, h, pi)
            return True
        if pin == 'unknown':
            return self._fallback(leaf, h) != 'stuck'
        if leaf.lam >= self.U:
            leaf.close()
            leaf.kind = 'alpha'
            self.stats['prunes'] += 1
            self.stats['closed'] += 1
            return True
        z = pin.x
        got = _integral_schedule(self.inst, lp, z, self.elig)
        if got is not None and self._yes(leaf, got[0], got[1]):
            # The target moved down.  The leaf is still open (unless its
            # lower bound already catches the new U), so queue it again
            # under the new target instead of splitting it at the old one.
            if leaf.lam >= self.U:
                leaf.close()
                leaf.kind = 'alpha'
                self.stats['prunes'] += 1
                self.stats['closed'] += 1
                return True
            self.queue.insert(leaf)
            return True
        i, mid, times = self._choose_split(lp, z, leaf, h)
        if i is None:
            return self._fallback(leaf, h) != 'stuck'
        self._do_split(leaf, i, mid)
        return True

    def run(self, max_steps=200000, max_lp=200000):
        t0 = time.time()
        while self.stats['nodes'] < max_steps:
            if self.stats['pin_solves'] + self.stats['target_solves'] > max_lp:
                break
            if not self.step():
                break
        self.stats['t'] = round(time.time() - t0, 4)
        self.stats['queue_steps'] = self.queue.steps
        self.stats['open'] = self._count_open()
        self.stats['L'] = self.L()
        return self

    def _count_open(self):
        seen = set()

        def rec(x):
            if id(x) in seen:
                return 0
            seen.add(id(x))
            if x.children is None:
                return 0 if (x.closed or x.dead) else 1
            return rec(x.children[0]) + rec(x.children[1])
        return rec(self.root)

    def L(self):
        if not self.queue:
            return self.U
        return min(self.U, self.queue.min_key())

    # -------------------------------------------------------- certificate
    def _leaf_tree(self, leaf, target):
        F = self._F(target, leaf)
        if leaf.kind == 'empty':
            return ('leaf', F, target, leaf.proof)
        return ('leaf', F, leaf.proof.h, leaf.proof)

    def _norm(self, leaf, target):
        i0 = self._empty_job(target, leaf)
        if i0 is not None:
            F = self._F(target, leaf)
            pi = CertLeafProof(self.inst, target, F,
                               {'kind': 'empty', 'job': i0})
            return ('leaf', F, target, pi)
        if leaf.children is None:
            return self._leaf_tree(leaf, target)
        a, b = leaf.children
        l = self._norm(a, target)
        r = self._norm(b, target)
        lo_t = _allowed(self.inst, target, leaf.lo, leaf.hi, leaf.i)
        left_t = [t for t in lo_t if t <= leaf.mid]
        right_t = [t for t in lo_t if t > leaf.mid]
        if not left_t:
            return r
        if not right_t:
            return l
        F = self._F(target, leaf)
        return ('split', leaf.i, leaf.mid, F, l, r)

    def certificate(self):
        if self._count_open() > 0:
            return None
        target = self._target()
        tree = self._norm(self.root, target)
        fp = TargetFrontierProof(self.inst, target, tree)
        return OptCertificate(self.inst, self.U, self.schedule,
                              self.machine, fp)

    def partial_tree(self):
        target = self._target()
        return self._norm(self.root, target)
