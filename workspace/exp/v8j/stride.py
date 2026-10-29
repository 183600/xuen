"""v8.9 STRIDE-ALC: streaming robust interval-domain decision evidence.

STRIDE keeps SAGE's LP pin, LNS, GA and CHD fallback.  It replaces the
all-or-nothing LP-BRANCH probe by a resumable stream of box refinements:

  * a state is a box B = prod_i [lo_i, hi_i] of allowed start times;
  * LP infeasible -> a verified Farkas leaf closes B (NO);
  * LP integral   -> a checked schedule closes B (YES);
  * fractional    -> split one job's interval into B_L, B_R;
  * certificate generation failure -> a hole, not a global UNKNOWN.

The open leaves of a paused search form a partition of the root box.  A
YES found in any leaf is a global YES; a NO proof is a complete tree of
closed leaves.  Holes are isolated: they preserve soundness, keep the
rest of the probe alive, and can be repaired or delegated later.

Two data structures make the stream cheap:

  * BoxTree: a split record (job, mid) instead of a frozenset of
    forbidden (job, time) pairs at every node;
  * MonotoneStore: NO is downward closed and LB upward closed, so the
    proof store quotient is just (max NO horizon, proof at that horizon).

The streaming verifier is a one-pass post-order checker with a stack of
boxes; its memory is O(depth * n), independent of the number of nodes.
"""
import sys
import time
import random
import collections

sys.path[:0] = ['exp/v8j', 'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e',
                'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from apex import Proof
from sage import (SAGE, SubsumptionProof, ga_schedule, _elig_aware,
                  self_tail)
from po import heads_tails
from cert import verify, integer_certificate
from sdecc import SDLP
from rdf import check_schedule


def box_forbidden(inst, h, est, q, lo, hi):
    F = set()
    n, p = inst['n'], inst['p']
    for i in range(n):
        last = h - q[i] - p[i]
        for t in range(est[i], last + 1):
            if t < lo[i] or t > hi[i]:
                F.add((i, t))
    return frozenset(F)


def box_volume(lo, hi):
    v = 1
    for a, b in zip(lo, hi):
        v *= max(0, b - a + 1)
    return v


class BoxProof(Proof):
    """A replayable NO(h) proof whose nodes are interval boxes."""

    kind = 'branch'

    def __init__(self, inst, h, tree, root_lo, root_hi, stats=None):
        super().__init__(inst, h)
        self.tree = tree
        self.root_lo = tuple(root_lo)
        self.root_hi = tuple(root_hi)
        self.stats = stats or {}

    def _check(self, node, lo, hi):
        tag = node[0]
        if tag == 'leaf':
            if tuple(node[1]) != tuple(lo) or tuple(node[2]) != tuple(hi):
                return False
            est, q = heads_tails(self.inst, 0, [0] * self.inst['n'])
            F = box_forbidden(self.inst, self.h, est, q, lo, hi)
            return bool(verify(self.inst, self.h, node[3], forbid=F))
        if tag == 'empty':
            if tuple(node[1]) != tuple(lo) or tuple(node[2]) != tuple(hi):
                return False
            return lo[node[3]] > hi[node[3]]
        if tag != 'no':
            return False
        _, i, mid, nlo, nhi, left, right = node
        if tuple(nlo) != tuple(lo) or tuple(nhi) != tuple(hi):
            return False
        if not (lo[i] <= mid < hi[i]):
            return False
        loL, hiL = list(lo), list(hi)
        loR, hiR = list(lo), list(hi)
        hiL[i] = mid
        loR[i] = mid + 1
        if loL[i] > hiL[i] or loR[i] > hiR[i]:
            return False
        return (self._check(left, loL, hiL)
                and self._check(right, loR, hiR))

    def audit_rdf(self):
        try:
            return self._check(self.tree, self.root_lo, self.root_hi)
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def stream_events(tree):
    """Post-order event stream of a BoxProof tree."""
    tag = tree[0]
    if tag == 'leaf':
        yield ('leaf', tree[1], tree[2], tree[3])
    elif tag == 'empty':
        yield ('empty', tree[1], tree[2], tree[3])
    elif tag == 'no':
        yield from stream_events(tree[5])
        yield from stream_events(tree[6])
        yield ('split', tree[1], tree[2])
    else:
        raise ValueError('not a complete NO tree: %r' % (tag,))


def verify_stream(inst, h, events, root_lo, root_hi):
    """One-pass verifier.  Returns (ok, closed_boxes, max_stack)."""
    est, q = heads_tails(inst, 0, [0] * inst['n'])
    stack = []
    max_stack = 0
    for ev in events:
        if ev[0] == 'leaf':
            _, lo, hi, cert = ev
            lo, hi = tuple(lo), tuple(hi)
            F = box_forbidden(inst, h, est, q, lo, hi)
            if not verify(inst, h, cert, forbid=F):
                return False, stack, max_stack
            stack.append((lo, hi))
        elif ev[0] == 'empty':
            _, lo, hi, i = ev
            lo, hi = tuple(lo), tuple(hi)
            if lo[i] <= hi[i]:
                return False, stack, max_stack
            stack.append((lo, hi))
        elif ev[0] == 'split':
            _, i, mid = ev
            if len(stack) < 2:
                return False, stack, max_stack
            rlo, rhi = stack.pop()
            llo, lhi = stack.pop()
            if lhi[i] != mid or rlo[i] != mid + 1:
                return False, stack, max_stack
            for j in range(len(llo)):
                if j == i:
                    continue
                if llo[j] != rlo[j] or lhi[j] != rhi[j]:
                    return False, stack, max_stack
            stack.append((llo, rhi))
        else:
            return False, stack, max_stack
        max_stack = max(max_stack, len(stack))
    ok = (len(stack) == 1 and tuple(stack[0][0]) == tuple(root_lo)
          and tuple(stack[0][1]) == tuple(root_hi))
    return ok, stack, max_stack


class MonotoneStore:
    """O(1) quotient of the monotone NO/LB proof store."""

    def __init__(self):
        self.by_h = {}
        self.no_h = -1
        self.no_proof = None
        self.inserts = 0

    def add(self, proof):
        if proof is None:
            return
        self.inserts += 1
        self.by_h[proof.h] = proof
        if proof.h > self.no_h:
            self.no_h = proof.h
            self.no_proof = proof

    def exact(self, h):
        return self.by_h.get(h)

    def stronger(self, h):
        if self.no_proof is not None and self.no_h >= h:
            return self.no_proof
        return None


class _Task:
    __slots__ = ('bounds', 'lo', 'hi', 'depth', 'stage', 'i', 'mid',
                 'children', 'parent', 'side')

    def __init__(self, bounds, lo, hi, depth, parent=None, side=None):
        self.bounds = bounds
        self.lo = lo
        self.hi = hi
        self.depth = depth
        self.stage = 0
        self.i = None
        self.mid = None
        self.children = [None, None]
        self.parent = parent
        self.side = side


class StreamBranch:
    """Resumable DFS over the interval-box lattice.

    run(budget) processes at most `budget` LP nodes and pauses.  No node
    is ever solved twice, so the total work over a sequence of budgets is
    the size of the final tree.  `nodecap` is a hard total cap; when it is
    reached the remaining leaves become holes.
    """

    def __init__(self, inst, h, nodecap=96, depthcap=24, policy=None):
        self.inst = inst
        self.h = h
        self.nodecap = nodecap
        self.depthcap = depthcap
        self.policy = policy or {}
        self.n = inst['n']
        self.m = inst['m']
        self.p = inst['p']
        self.elig = _elig_aware(inst)
        self.est, self.q = heads_tails(inst, 0, [0] * self.n)
        self.lp = SDLP(inst, h, self.est, self.q, use_dom=True,
                       elig_aware=self.elig)
        self.N = self.lp.N
        self.root_lo = tuple(self.est)
        self.root_hi = tuple(h - self.q[i] - self.p[i]
                             for i in range(self.n))
        self.stack = [_Task([(0, 1)] * self.N,
                            list(self.root_lo), list(self.root_hi), 0)]
        self.nodes = 0
        self.leaves = 0
        self.cert_lp = 0
        self.maxdepth = 0
        self.branch_jobs = []
        self.holes = []
        self.final = None
        self.verdict = None
        self.schedule = None
        self.machine = None
        self.cmax = None
        self.rounds = 0
        self.t0 = time.time()

    def _solve(self, bounds):
        self.nodes += 1
        return self.lp.solve(bounds)

    def _allowed_cols(self, i, bounds):
        return [c for c, key in enumerate(self.lp.cols)
                if key[0] == i and bounds[c] != (0, 0)]

    def _choose(self, z, bounds):
        cand = []
        for i in range(self.n):
            cols = self._allowed_cols(i, bounds)
            times = sorted(set(self.lp.cols[c][-1] for c in cols))
            if len(times) <= 1:
                continue
            mass = 0.0
            dist = []
            for tt in times:
                v = sum(z[c] for c in cols
                        if self.lp.cols[c][-1] == tt)
                dist.append((tt, v))
                mass += v
            frac = sum(v for _, v in dist if 1e-7 < v < 1 - 1e-7)
            if frac <= 1e-7:
                continue
            score = (mass, self_tail(self.q, i),
                     len(self.inst['succ'][i]), -i)
            cand.append((score, i, dist))
        if not cand:
            return None, None
        cand.sort(reverse=True)
        _, i, dist = cand[0]
        total = sum(v for _, v in dist)
        split = self.policy.get('split', 0.5)
        acc = 0.0
        mid = dist[0][0]
        for tt, v in dist:
            acc += v
            if acc >= split * total:
                mid = tt
                break
        times = [tt for tt, _ in dist]
        lo_t = [tt for tt in times if tt > mid]
        hi_t = [tt for tt in times if tt <= mid]
        if not lo_t or not hi_t:
            mid = times[len(times) // 2 - 1] if len(times) > 1 else times[0]
            lo_t = [tt for tt in times if tt > mid]
            hi_t = [tt for tt in times if tt <= mid]
        if not lo_t or not hi_t:
            return None, None
        return i, mid

    def _bound_side(self, bounds, i, mid, side):
        b = list(bounds)
        for c, key in enumerate(self.lp.cols):
            if key[0] != i:
                continue
            tt = key[-1]
            if (side == 'lo' and tt > mid) or (side == 'hi' and tt <= mid):
                b[c] = (0, 0)
        return b

    def _leaf_cert(self, lo, hi):
        F = box_forbidden(self.inst, self.h, self.est, self.q, lo, hi)
        self.cert_lp += 1
        cert = integer_certificate(self.inst, self.h, use_dom=True,
                                   elig_aware=self.elig, forbid=F)
        if cert is not None and verify(self.inst, self.h, cert, forbid=F):
            return ('leaf', list(lo), list(hi), cert)
        for i in range(self.n):
            if lo[i] > hi[i]:
                return ('empty', list(lo), list(hi), i)
        return None

    def _integral(self, z):
        starts = [None] * self.n
        machs = [None] * self.n
        for c, key in enumerate(self.lp.cols):
            if z[c] > 1 - 1e-7:
                i, t = key[0], key[-1]
                if starts[i] is not None:
                    return None
                starts[i] = t
                if self.elig:
                    machs[i] = key[1]
        if any(x is None for x in starts):
            return None
        if not self.elig:
            busy = [[] for _ in range(self.m)]
            for i in sorted(range(self.n), key=lambda i: (starts[i], i)):
                for k in self.inst['elig'][i]:
                    if all(starts[i] + self.p[i] <= a or starts[i] >= b
                           for a, b in busy[k]):
                        machs[i] = k
                        busy[k].append((starts[i],
                                        starts[i] + self.p[i]))
                        break
                if machs[i] is None:
                    return None
        cmax = max(starts[i] + self.p[i] for i in range(self.n))
        if check_schedule(self.inst, cmax, starts, machs):
            return starts, machs
        return None

    def _attach(self, task, node):
        if node[0] == 'yes':
            self.verdict = True
            self.final = ('yes',)
            return
        p = task.parent
        if p is None:
            self.final = node
            if node[0] == 'yes':
                self.verdict = True
            elif node[0] in ('leaf', 'empty', 'no'):
                self.verdict = False
            else:
                self.verdict = None
            return
        p.children[task.side] = node
        if p.children[0] is None or p.children[1] is None:
            return
        a, b = p.children
        if a[0] == 'yes' or b[0] == 'yes':
            self.stack.remove(p)
            self.verdict = True
            self.final = ('yes',)
            return
        is_no = lambda x: x[0] in ('leaf', 'empty', 'no')
        kind = 'no' if (is_no(a) and is_no(b)) else 'partial'
        res = (kind, p.i, p.mid, list(p.lo), list(p.hi), a, b)
        self.stack.remove(p)
        self._attach(p, res)

    def _close(self, task, node):
        self.stack.remove(task)
        self._attach(task, node)

    def _make_hole(self, task, reason):
        self.holes.append((list(task.lo), list(task.hi), reason))
        self.stack.remove(task)
        self._attach(task, ('hole', list(task.lo), list(task.hi), reason))

    def step(self):
        if self.verdict is not None:
            return True
        if not self.stack:
            self.verdict = False if not self.holes else None
            return True
        t = self.stack[-1]
        if t.stage == 1:
            return False
        if self.nodes >= self.nodecap or t.depth > self.depthcap:
            self._make_hole(t, 'budget' if self.nodes >= self.nodecap
                            else 'depth')
            return False
        res = self._solve(t.bounds)
        if res is None or res.status not in (0, 2):
            self._make_hole(t, 'lp')
            return False
        if res.status == 2:
            self.leaves += 1
            node = self._leaf_cert(t.lo, t.hi)
            if node is None:
                self._make_hole(t, 'cert')
                return False
            self._close(t, node)
            return False
        z = res.x
        frac = any(1e-7 < z[c] < 1 - 1e-7 and t.bounds[c] != (0, 0)
                   for c in range(self.N))
        if not frac:
            got = self._integral(z)
            if got is None:
                self._make_hole(t, 'decode')
                return False
            s, m = got
            cmax = max(s[i] + self.p[i] for i in range(self.n))
            self.schedule, self.machine, self.cmax = s, m, cmax
            self._close(t, ('yes', s, m, cmax))
            return False
        i, mid = self._choose(z, t.bounds)
        if i is None:
            self._make_hole(t, 'choose')
            return False
        self.maxdepth = max(self.maxdepth, t.depth)
        t.stage = 1
        t.i, t.mid = i, mid
        self.branch_jobs.append((i, mid))
        loL, hiL = list(t.lo), list(t.hi)
        loR, hiR = list(t.lo), list(t.hi)
        hiL[i] = min(hiL[i], mid)
        loR[i] = max(loR[i], mid + 1)
        if loL[i] > hiL[i] or loR[i] > hiR[i]:
            self._make_hole(t, 'emptysplit')
            return False
        bL = self._bound_side(t.bounds, i, mid, 'lo')
        bR = self._bound_side(t.bounds, i, mid, 'hi')
        right = _Task(bR, loR, hiR, t.depth + 1, t, 1)
        left = _Task(bL, loL, hiL, t.depth + 1, t, 0)
        self.stack.append(right)
        self.stack.append(left)
        return False

    def run(self, budget):
        self.rounds += 1
        for _ in range(max(0, budget)):
            if self.verdict is not None or not self.stack:
                break
            self.step()
        if self.verdict is True:
            return 'yes'
        if self.verdict is False and not self.holes:
            return 'no'
        if not self.stack:
            return 'open'
        return 'paused'

    def frontier(self):
        out = []
        for t in self.stack:
            if t.stage == 0:
                out.append((list(t.lo), list(t.hi), 'open'))
        for lo, hi, reason in self.holes:
            out.append((list(lo), list(hi), 'hole:' + reason))
        return out


class STRIDE(SAGE):
    def __init__(self, inst, round_budget=1, bb_total_nodecap=96,
                 bb_depthcap=24, use_bb=True, use_ga=True, bb_yes=True,
                 **kw):
        super().__init__(inst, use_bb=use_bb, use_ga=use_ga,
                         bb_yes=bb_yes, **kw)
        self.round_budget = round_budget
        self.bb_total_nodecap = bb_total_nodecap
        self.bb_depthcap = bb_depthcap
        self.store = MonotoneStore()
        self.stats.update(bb_open=0, bb_holes=0, bb_rounds=0,
                          bb_max_frontier=0)
        self.hole_reasons = collections.Counter()

    def _record_proof(self, p):
        p = super()._record_proof(p)
        if p is not None:
            self.store.add(p)
        return p

    def _ensure_lb_proof(self, value):
        p = super(SAGE, self)._ensure_lb_proof(value)
        if p is not None:
            return p
        h = value - 1
        src = self.store.stronger(h)
        if src is None:
            return None
        if src.h == h:
            return src
        return self._record_proof(SubsumptionProof(self.inst, h, src))

    def _probe(self, h):
        if self.use_bb:
            sb = StreamBranch(self.inst, h,
                              nodecap=self.bb_total_nodecap,
                              depthcap=self.bb_depthcap)
            st = 'paused'
            guard = 0
            while st == 'paused' and guard < 100000:
                st = sb.run(self.round_budget)
                guard += 1
            self.bb_lp += sb.nodes
            self.cert_lp_total += sb.cert_lp
            self.stats['bb_rounds'] += sb.rounds
            self.stats['bb_max_frontier'] = max(
                self.stats['bb_max_frontier'], len(sb.frontier()))
            self.stats['bb_holes'] += len(sb.holes)
            for _, _, reason in sb.holes:
                self.hole_reasons[reason] += 1
            self.stats['hole_reasons'] = dict(self.hole_reasons)
            if st == 'no':
                proof = BoxProof(self.inst, h, sb.final,
                                 sb.root_lo, sb.root_hi,
                                 stats=dict(nodes=sb.nodes,
                                            leaves=sb.leaves,
                                            cert_lp=sb.cert_lp))
                if proof.audit_rdf():
                    self.stats['bb_no'] += 1
                    self._record_proof(proof)
                    return False, proof
                st = 'open'
                sb.holes.append((list(sb.root_lo), list(sb.root_hi),
                                 'audit'))
            if st == 'yes':
                s, m = sb.schedule, sb.machine
                cmax = max(s[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                if self.bb_yes and check_schedule(self.inst, h, s, m):
                    self.stats['bb_yes'] += 1
                    return True, (s, m, cmax)
                if not self.bb_yes:
                    self.stats['bb_yes_ignored'] = \
                        self.stats.get('bb_yes_ignored', 0) + 1
            if st in ('open', 'paused'):
                self.stats['bb_open'] += 1
                if st == 'paused':
                    self.hole_reasons['pause_guard'] += 1
                self.stats['hole_reasons'] = dict(self.hole_reasons)
        if self.use_ga:
            got, st = ga_schedule(self.inst, h, pop=self.ga_pop,
                                  gens=self.ga_gens,
                                  budget=self.ga_budget)
            self.ga_stats.append(st)
            if got is not None:
                s, m = got
                cmax = max(s[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                self.stats['ga_yes'] += 1
                return True, (s, m, cmax)
            self.stats['ga_no'] += 1
        self.stats['chd_fallback'] += 1
        v, st, rdf = self._decide(h)
        self.queries += 1
        self._absorb(st)
        self._record(h, v, st)
        return v, rdf
