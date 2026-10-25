"""Prototype: best-first / anytime fixed-h search for R-ACT."""
import sys, time, math, heapq, random
sys.path[:0] = ['exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e',
                'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']
from sdecc import SDLP
from cert import verify, integer_certificate
from rdf import check_schedule
from po import heads_tails
from pact import (_elig_aware, _assign_machines, _integral_schedule,
                  _singleton_leaf, _domain)
from sage import _elig_aware as _ea


def topo_order(inst):
    n = inst['n']
    indeg = [len(inst['pred'][i]) for i in range(n)]
    succ = inst['succ']
    stack = [i for i in range(n) if indeg[i] == 0]
    out = []
    while stack:
        i = stack.pop()
        out.append(i)
        for j in succ[i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                stack.append(j)
    return out


class Node:
    __slots__ = ('id','bounds','F','depth','parent','left','right','status',
                 'kind','cert','schedule','machine','lb','width','key',
                 'lp_calls')
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
        self.key = None
        self.lp_calls = 0


class AnytimeSearch:
    def __init__(self, inst, h, policy='min_lb', seed=0, bound_close=True,
                 pact_choose=False):
        self.inst = inst
        self.h = h
        self.policy = policy
        self.seed = seed
        self.bound_close = bound_close
        self.pact_choose = pact_choose
        self.n = inst['n']
        self.m = inst['m']
        self.p = inst['p']
        self.elig = _elig_aware(inst)
        self.est, self.q = heads_tails(inst, 0, [0] * self.n)
        self.lp = SDLP(inst, h, self.est, self.q, use_dom=True,
                       elig_aware=self.elig)
        self.base = [(0, 1)] * self.lp.N
        self.nodes = 0
        self.lp_calls = 0
        self.cert_calls = 0
        self.yes = None
        self.heap = []
        self.open = {}
        self.topo = topo_order(inst)
        self.root = self._new_node(self.base, frozenset(), 0, None)
        self.L = self.root.lb
        self.U = None
        self._push(self.root)

    def _new_node(self, bounds, F, depth, parent):
        nd = Node(self.nodes, bounds, F, depth, parent)
        self.nodes += 1
        nd.lb, nd.width = self.local_bound(nd)
        if self.bound_close and nd.lb > self.h:
            nd.status = 'no'
            nd.kind = 'bound'
        elif nd.lb == float('inf'):
            nd.status = 'no'
            nd.kind = 'empty'
        return nd

    def local_bound(self, nd):
        """Heads/tails + total work lower bound for this residual node."""
        h = self.h
        r = []
        width = 0
        for i in range(self.n):
            lo, hi = _domain(self.inst, h, i)
            times = [t for t in range(lo, hi + 1) if (i, t) not in nd.F]
            if not times:
                return float('inf'), 0
            r.append(times[0])
            width += len(times)
        e = [0] * self.n
        for i in self.topo:
            v = r[i]
            for j in self.inst['pred'][i]:
                v = max(v, e[j] + self.p[j])
            e[i] = v
        lb1 = max(e[i] + self.p[i] + self.q[i] for i in range(self.n))
        lb2 = math.ceil(sum(self.p) / self.m)
        return max(lb1, lb2), width

    def _push(self, nd):
        if nd.status != 'open':
            return
        pol = self.policy
        if pol == 'min_lb':
            key = (nd.lb, nd.width, nd.depth, nd.id)
        elif pol == 'max_lb':
            key = (-nd.lb, nd.width, nd.depth, nd.id)
        elif pol == 'min_width':
            key = (nd.width, nd.lb, nd.depth, nd.id)
        elif pol == 'max_width':
            key = (-nd.width, nd.lb, nd.depth, nd.id)
        elif pol == 'bfs':
            key = (nd.depth, nd.lb, nd.id)
        elif pol == 'dfs':
            key = (-nd.depth, nd.id)
        elif pol == 'random':
            rng = random.Random(self.seed * 100003 + nd.id * 7919)
            key = (rng.random(),)
        elif pol == 'fifo':
            key = (nd.id,)
        else:
            raise ValueError(pol)
        nd.key = key
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
            ent = -sum(v * math.log(v) for _, v in dist if v > 1e-12)
            if self.pact_choose:
                cand.append(((mass, self.q[i], len(self.inst['succ'][i]), -i), i, dist))
            else:
                cand.append(((mass, self.q[i], len(self.inst['succ'][i]),
                              len(times), -i), i, dist))
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
        if not [tt for tt in times if tt > mid] or not [tt for tt in times if tt <= mid]:
            mid = times[len(times) // 2 - 1] if len(times) > 1 else times[0]
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
            if cert is None:
                nd.kind = 'stuck'
                nd.status = 'stuck'
                return 'stuck'
            nd.kind = 'cert'
            nd.cert = cert
            self._update_bounds()
            return 'no'
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
                self.yes = (s, m, max(s[i] + self.p[i] for i in range(self.n)), nd)
                self._update_bounds()
                return 'yes'
            single = _singleton_leaf(self.inst, self.h, nd.F, self.lp, nd.bounds)
            if single is not None:
                _, s, m = single
                nd.status = 'yes'
                nd.kind = 'singleton'
                nd.schedule, nd.machine = s, m
                self.yes = (s, m, max(s[i] + self.p[i] for i in range(self.n)), nd)
                self._update_bounds()
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
        nd.lb = min(nd.left.lb, nd.right.lb)
        nd.width = nd.left.width + nd.right.width
        self._push(nd.left)
        self._push(nd.right)
        self._update_bounds()
        return 'split'

    def _update_bounds(self):
        leaves = []
        def walk(x):
            if x.status in ('open', 'yes', 'stuck'):
                leaves.append(x)
            elif x.status == 'split':
                walk(x.left); walk(x.right)
            elif x.status == 'no':
                leaves.append(x)
        walk(self.root)
        vals = []
        for x in leaves:
            if x.status == 'no':
                vals.append(self.h + 1)
            else:
                vals.append(x.lb)
        self.L = min(vals) if vals else self.h + 1
        if self.yes is not None:
            self.U = self.yes[2]

    def run(self, budget=None, stop_at_yes=True):
        steps = 0
        while self.heap:
            if self.yes is not None and stop_at_yes:
                break
            if budget is not None and steps >= budget:
                break
            r = self.expand_one()
            steps += 1
            if r == 'done':
                break
        return self.result()

    def result(self):
        if self.yes is not None:
            return dict(status='yes', schedule=self.yes[0], machine=self.yes[1],
                        cmax=self.yes[2], L=self.L, U=self.U,
                        nodes=self.nodes, lp=self.lp_calls,
                        cert=self.cert_calls, open=len(self.open))
        if not self.heap:
            return dict(status='no', L=self.h + 1, U=self.U,
                        nodes=self.nodes, lp=self.lp_calls,
                        cert=self.cert_calls, open=0)
        return dict(status='partial', L=self.L, U=self.U,
                    nodes=self.nodes, lp=self.lp_calls,
                    cert=self.cert_calls, open=len(self.open))
