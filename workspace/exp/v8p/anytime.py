"""R-ACT anytime engine: resumable recursive frontier search."""
import sys
import time
import math
import heapq
import random

sys.path[:0] = ['exp/v8p', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from sage import _elig_aware, _domain
from pact import (_assign_machines, _integral_schedule, _singleton_leaf)
from sdecc import SDLP
from cert import verify, integer_certificate
from rdf import check_schedule
from po import heads_tails
from ract import RACTProof, local_bound, topo_order


class ANode:
    __slots__ = ('id', 'bounds', 'F', 'depth', 'parent', 'left', 'right',
                 'status', 'kind', 'cert', 'schedule', 'machine', 'lb',
                 'width', 'branch', 'lp_calls')

    def __init__(self, nid, bounds, F, depth, parent=None):
        self.id = nid
        self.bounds = bounds
        self.F = F
        self.depth = depth
        self.parent = parent
        self.left = None
        self.right = None
        self.status = 'open'
        self.kind = None
        self.cert = None
        self.schedule = None
        self.machine = None
        self.lb = 0
        self.width = 0
        self.branch = None
        self.lp_calls = 0


class AnytimeSearch:
    """A resumable, budgeted fixed-h search.

    expand_one() solves at most one LP (plus one certificate LP for a
    Farkas leaf).  The frontier is the current tree; open leaves carry a
    local lower bound.  proof() returns a RACTProof that certifies the
    interval [lb_value(), ub_value()].
    """

    def __init__(self, inst, h, policy='dfs', seed=0, bound_close=True):
        self.inst = inst
        self.h = h
        self.policy = policy
        self.seed = seed
        self.bound_close = bound_close
        self.n = inst['n']
        self.m = inst['m']
        self.p = inst['p']
        self.elig = _elig_aware(inst)
        self.est, self.q = heads_tails(inst, 0, [0] * self.n)
        self.topo = topo_order(inst)
        self.lp = SDLP(inst, h, self.est, self.q, use_dom=True,
                       elig_aware=self.elig)
        self.base = [(0, 1)] * self.lp.N
        self.nodes = 0
        self.lp_calls = 0
        self.cert_calls = 0
        self.yes = None
        self.heap = []
        self.open = {}
        self.root = self._new_node(self.base, frozenset(), 0, None)
        self._push(self.root)

    # ------------------------------------------------------------- bounds
    def _local(self, F):
        return local_bound(self.inst, self.h, F, self.est, self.q,
                           self.topo)

    def _new_node(self, bounds, F, depth, parent):
        nd = ANode(self.nodes, bounds, F, depth, parent)
        self.nodes += 1
        nd.lb, nd.width, wit = self._local(F)
        if nd.lb == float('inf'):
            nd.status = 'no'
            nd.kind = 'empty'
            nd.cert = ('empty', frozenset(F), wit[1])
        elif self.bound_close and nd.lb > self.h:
            nd.status = 'no'
            nd.kind = 'bound'
            nd.cert = ('bound', frozenset(F), nd.lb, wit)
        return nd

    def _push(self, nd):
        if nd.status != 'open':
            return
        if self.policy == 'dfs':
            key = (-nd.depth, nd.id)
        elif self.policy == 'bfs':
            key = (nd.depth, nd.lb, nd.id)
        elif self.policy == 'min_lb':
            key = (nd.lb, nd.width, nd.depth, nd.id)
        elif self.policy == 'max_lb':
            key = (-nd.lb, nd.width, nd.depth, nd.id)
        elif self.policy == 'min_width':
            key = (nd.width, nd.lb, nd.depth, nd.id)
        elif self.policy == 'random':
            rng = random.Random(self.seed * 100003 + nd.id * 7919)
            key = (rng.random(),)
        else:
            raise ValueError(self.policy)
        heapq.heappush(self.heap, (key, nd.id, nd))
        self.open[nd.id] = nd

    def _allowed_times(self, i, bounds):
        return sorted({key[-1] for c, key in enumerate(self.lp.cols)
                       if key[0] == i and bounds[c] != (0, 0)})

    def _choose(self, z, bounds):
        cand = []
        for i in range(self.n):
            times = self._allowed_times(i, bounds)
            if len(times) <= 1:
                continue
            dist = []
            for tt in times:
                v = sum(z[c] for c, key in enumerate(self.lp.cols)
                        if key[0] == i and key[-1] == tt
                        and bounds[c] != (0, 0))
                dist.append((tt, v))
            frac = sum(v for _, v in dist if 1e-7 < v < 1 - 1e-7)
            if frac <= 1e-7:
                continue
            mass = sum(v for _, v in dist)
            cand.append(((mass, self.q[i], len(self.inst['succ'][i]), -i),
                         i, dist))
        if not cand:
            return None, None
        cand.sort(reverse=True)
        _, i, dist = cand[0]
        total = sum(v for _, v in dist)
        acc = 0.0
        mid = dist[0][0]
        for tt, v in dist:
            acc += v
            if acc >= 0.5 * total:
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

    def _leaf_cert(self, F):
        self.cert_calls += 1
        cert = integer_certificate(self.inst, self.h, use_dom=True,
                                   elig_aware=self.elig, forbid=F)
        if cert is not None and verify(self.inst, self.h, cert, forbid=F):
            return ('leaf', frozenset(F), cert)
        for i in range(self.n):
            lo, hi = _domain(self.inst, self.h, i)
            if lo <= hi and all((i, t) in F for t in range(lo, hi + 1)):
                return ('empty', frozenset(F), i)
        return None

    # ------------------------------------------------------------ expand
    def expand_one(self):
        if self.yes is not None:
            return 'yes'
        if not self.heap:
            return 'done'
        _, _, nd = heapq.heappop(self.heap)
        self.open.pop(nd.id, None)
        if nd.status != 'open':
            return 'skip'
        self.lp_calls += 1
        nd.lp_calls += 1
        res = self.lp.solve(nd.bounds)
        if res.status == 2:
            nd.status = 'no'
            cert = self._leaf_cert(nd.F)
            if cert is not None:
                nd.kind = 'cert'
                nd.cert = cert
                return 'no'
            # last resort: a local bound / empty leaf
            lb, width, wit = self._local(nd.F)
            if lb > self.h:
                nd.kind = 'bound'
                nd.cert = ('bound', frozenset(nd.F), lb, wit)
                return 'no'
            nd.status = 'stuck'
            nd.kind = 'stuck'
            return 'stuck'
        if res.status != 0:
            nd.status = 'stuck'
            nd.kind = 'lp_error'
            return 'stuck'
        z = res.x
        frac = False
        for c, key in enumerate(self.lp.cols):
            if 1e-7 < z[c] < 1 - 1e-7 and nd.bounds[c] != (0, 0):
                frac = True
                break
        if not frac:
            got = _integral_schedule(self.inst, self.lp, z, self.elig)
            if got is not None:
                s, m = got
                nd.status = 'yes'
                nd.kind = 'integral'
                nd.schedule, nd.machine = s, m
                cmax = max(s[i] + self.p[i] for i in range(self.n))
                self.yes = (s, m, cmax, nd)
                return 'yes'
            single = _singleton_leaf(self.inst, self.h, nd.F, self.lp,
                                     nd.bounds)
            if single is not None:
                _, s, m = single
                nd.status = 'yes'
                nd.kind = 'singleton'
                nd.schedule, nd.machine = s, m
                cmax = max(s[i] + self.p[i] for i in range(self.n))
                self.yes = (s, m, cmax, nd)
                return 'yes'
            i = None
            mid = None
            for j in range(self.n):
                times = self._allowed_times(j, nd.bounds)
                if len(times) > 1:
                    i = j
                    mid = times[len(times) // 2 - 1]
                    break
            if i is None:
                nd.status = 'stuck'
                nd.kind = 'ambiguous'
                return 'stuck'
        else:
            i, mid = self._choose(z, nd.bounds)
            if i is None:
                nd.status = 'stuck'
                nd.kind = 'no_branch'
                return 'stuck'
        times = self._allowed_times(i, nd.bounds)
        lo_t = [t for t in times if t > mid]
        hi_t = [t for t in times if t <= mid]
        if not lo_t or not hi_t:
            nd.status = 'stuck'
            nd.kind = 'degenerate'
            return 'stuck'
        loF = nd.F | {(i, t) for t in lo_t}
        hiF = nd.F | {(i, t) for t in hi_t}
        nd.left = self._new_node(self._bound_side(nd.bounds, i, mid, 'lo'),
                                 loF, nd.depth + 1, nd)
        nd.right = self._new_node(self._bound_side(nd.bounds, i, mid, 'hi'),
                                  hiF, nd.depth + 1, nd)
        nd.status = 'split'
        nd.kind = 'split'
        nd.branch = (i, mid, frozenset(nd.F))
        nd.lb = min(nd.left.lb, nd.right.lb)
        nd.width = nd.left.width + nd.right.width
        self._push(nd.left)
        self._push(nd.right)
        return 'split'

    def run(self, budget=None, stop_at_yes=True, depth_limit=None):
        steps = 0
        deferred = []
        while self.heap:
            if self.yes is not None and stop_at_yes:
                break
            if budget is not None and steps >= budget:
                break
            _, _, nd = heapq.heappop(self.heap)
            self.open.pop(nd.id, None)
            if depth_limit is not None and nd.depth >= depth_limit:
                deferred.append(nd)
                continue
            # put it back so expand_one sees the same node
            heapq.heappush(self.heap, (( -nd.depth, nd.id) if self.policy == 'dfs'
                                      else (nd.lb, nd.width, nd.depth, nd.id),
                                      nd.id, nd))
            self.open[nd.id] = nd
            r = self.expand_one()
            steps += 1
            if r == 'done':
                break
        for nd in deferred:
            self._push(nd)
        return self.result()

    # ------------------------------------------------------------ output
    def _tree(self, x):
        if x.status == 'split':
            i, mid, F = x.branch
            return ('node', i, mid, F, self._tree(x.left),
                    self._tree(x.right))
        if x.status == 'yes':
            return ('yes', frozenset(x.F), x.schedule, x.machine)
        if x.status == 'no':
            if x.kind == 'cert':
                return x.cert
            if x.kind == 'empty':
                return x.cert
            if x.kind == 'bound':
                return x.cert
        # open or stuck: a frontier leaf with its local bound
        return ('open', frozenset(x.F), x.lb)

    def proof(self):
        tree = self._tree(self.root)
        return RACTProof(self.inst, self.h, tree, dict(
            nodes=self.nodes, lp=self.lp_calls, cert=self.cert_calls))

    def result(self):
        p = self.proof()
        L = p.lb_value()
        U = p.ub_value()
        if self.yes is not None:
            return dict(status='yes', schedule=self.yes[0],
                        machine=self.yes[1], cmax=self.yes[2],
                        L=L, U=U, nodes=self.nodes, lp=self.lp_calls,
                        cert=self.cert_calls, open=len(self.open),
                        proof=p)
        if not self.heap:
            return dict(status='no', L=L, U=U, nodes=self.nodes,
                        lp=self.lp_calls, cert=self.cert_calls,
                        open=0, proof=p)
        return dict(status='partial', L=L, U=U, nodes=self.nodes,
                    lp=self.lp_calls, cert=self.cert_calls,
                    open=len(self.open), proof=p)
