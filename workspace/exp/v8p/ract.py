"""v9.0 R-ACT: recursive anytime certificate trees.

R-ACT extends PACT-ALC with three things:

1. BOUND leaf: a residual node F is NO(h|F) if a heads/tails relaxation
   computed on the forbidden domain already exceeds h.  This closes
   leaves without an LP or a Farkas certificate.
2. FRONTIER certificate: a partial search tree is a first-class proof of
   an interval [L,U].  Closed NO leaves contribute h+1; open leaves
   contribute a local relaxation bound; YES leaves contribute a schedule.
3. Anytime recursive expansion: the frontier is resumable.  At any LP
   budget the algorithm returns a certified interval; continuing the
   expansion can only raise L and lower U.

The outer bracket is PACT's.  The final lower-bound object may be a
frontier with lb_value = OPT instead of a full NO(OPT-1) tree.
"""
import sys
import time
import math
import heapq

sys.path[:0] = ['exp/v8p', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof, OracleProof, bound_lb
from sage import (SAGE, BranchProof, SubsumptionProof, ga_schedule,
                  _elig_aware, _domain)
from pact import (PACT, TotalTrace, pact_decide, _assign_machines,
                  _integral_schedule, _singleton_leaf)
from sdecc import SDLP
from cert import verify, integer_certificate
from rdf import check_schedule
from po import heads_tails


# --------------------------------------------------------------- bounds
def topo_order(inst):
    n = inst['n']
    indeg = [len(inst['pred'][i]) for i in range(n)]
    stack = [i for i in range(n) if indeg[i] == 0]
    out = []
    while stack:
        i = stack.pop()
        out.append(i)
        for j in inst['succ'][i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                stack.append(j)
    return out


def local_bound(inst, h, F, est, q, topo):
    """Heads/tails + total-work lower bound of the residual node F.

    Returns (lb, width, detail).  lb is a valid lower bound on Cmax for
    every schedule that satisfies Cmax <= h and the forbidden starts F.
    A value > h proves NO(h|F).  detail is a replayable witness:
    (kind, job, value) with kind in {'head', 'work'}.
    """
    n, m, p = inst['n'], inst['m'], inst['p']
    r = [0] * n
    width = 0
    for i in range(n):
        lo, hi = _domain(inst, h, i)
        first = None
        cnt = 0
        for t in range(lo, hi + 1):
            if (i, t) not in F:
                if first is None:
                    first = t
                cnt += 1
        if first is None:
            return float('inf'), 0, ('empty', i, 0)
        r[i] = first
        width += cnt
    e = [0] * n
    for i in topo:
        v = r[i]
        for j in inst['pred'][i]:
            v = max(v, e[j] + p[j])
        e[i] = v
    best = None
    for i in range(n):
        val = e[i] + p[i] + q[i]
        if best is None or val > best[0]:
            best = (val, 'head', i)
    work = math.ceil(sum(p) / m)
    if work > best[0]:
        best = (work, 'work', -1)
    return best[0], width, best


# ------------------------------------------------------------- R-ACT proof
class RACTProof(Proof):
    """A recursive certificate tree.

    Leaf tags:
      ('leaf', F, cert)       Farkas leaf, NO(h|F)
      ('empty', F, i)         empty domain, NO(h|F)
      ('bound', F, lb, wit)   local relaxation > h, NO(h|F)
      ('yes', F, s, m)        schedule with Cmax <= h
      ('open', F, lb)         unexplored leaf with local bound lb
    Internal:
      ('node', i, mid, F, lo, hi)
    """

    kind = 'ract'

    def __init__(self, inst, h, tree, stats=None):
        super().__init__(inst, h)
        self.tree = tree
        self.stats = stats or {}
        self.est, self.q = heads_tails(inst, 0, [0] * inst['n'])
        self.topo = topo_order(inst)

    def _allowed(self, i, F):
        lo, hi = _domain(self.inst, self.h, i)
        return [t for t in range(lo, hi + 1) if (i, t) not in F]

    def _sched_ok(self, s, m):
        if s is None or m is None:
            return False
        cmax = max(s[i] + self.inst['p'][i] for i in range(self.inst['n']))
        return cmax <= self.h and check_schedule(self.inst, cmax, s, m)

    def _check(self, node, F):
        tag = node[0]
        if tag == 'leaf':
            if set(node[1]) != set(F):
                return False
            cert = node[2]
            if cert.get('kind') == 'empty':
                return not self._allowed(cert['job'], F)
            return bool(verify(self.inst, self.h, cert, forbid=F))
        if tag == 'empty':
            return set(node[1]) == set(F) and not self._allowed(node[2], F)
        if tag == 'bound':
            if set(node[1]) != set(F):
                return False
            lb, width, wit = local_bound(self.inst, self.h, F,
                                         self.est, self.q, self.topo)
            return lb == node[2] and lb > self.h
        if tag == 'yes':
            return set(node[1]) == set(F) and self._sched_ok(node[2], node[3])
        if tag == 'open':
            if set(node[1]) != set(F):
                return False
            lb, width, wit = local_bound(self.inst, self.h, F,
                                         self.est, self.q, self.topo)
            return lb == node[2]
        _, i, mid, parent_F, lo, hi = node
        if set(parent_F) != set(F):
            return False
        allowed = self._allowed(i, F)
        lo_t = [t for t in allowed if t > mid]
        hi_t = [t for t in allowed if t <= mid]
        if not lo_t or not hi_t:
            return False
        loF = F | {(i, t) for t in lo_t}
        hiF = F | {(i, t) for t in hi_t}
        return self._check(lo, loF) and self._check(hi, hiF)

    def audit_rdf(self):
        try:
            return self._check(self.tree, frozenset())
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()

    def _leaves(self):
        out = []
        def walk(x):
            if x[0] in ('leaf', 'empty', 'bound', 'yes', 'open'):
                out.append(x)
            else:
                walk(x[4])
                walk(x[5])
        walk(self.tree)
        return out

    def lb_value(self):
        vals = []
        for x in self._leaves():
            if x[0] in ('leaf', 'empty', 'bound'):
                vals.append(self.h + 1)
            elif x[0] == 'open':
                vals.append(x[2])
            elif x[0] == 'yes':
                vals.append(local_bound(self.inst, self.h, x[1],
                                        self.est, self.q, self.topo)[0])
        return min(vals) if vals else self.h + 1

    def ub_value(self):
        vals = []
        for x in self._leaves():
            if x[0] == 'yes':
                vals.append(max(x[2][i] + self.inst['p'][i]
                                for i in range(self.inst['n'])))
        return min(vals) if vals else None


# --------------------------------------------------------------- decide
def ract_decide(inst, h, depthcap=None, nodecap=None, policy=None,
                bound_close=True):
    """DFS version of R-ACT, compatible with pact_decide's interface."""
    t0 = time.time()
    n, m, p = inst['n'], inst['m'], inst['p']
    elig = _elig_aware(inst)
    est, q = heads_tails(inst, 0, [0] * n)
    topo = topo_order(inst)
    lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig)
    base = [(0, 1)] * lp.N
    stats = dict(nodes=0, leaves=0, depth=0, lp_solves=0, cert_lp=0,
                 unknown=False, holes=0, branch_jobs=[], bound=0,
                 empty=0, open=0)
    policy = policy or {}

    def solve(bounds, depth):
        if nodecap is not None and stats['nodes'] >= nodecap:
            stats['unknown'] = True
            return None
        stats['nodes'] += 1
        stats['lp_solves'] += 1
        return lp.solve(bounds)

    def allowed_times(i, bounds):
        return sorted({key[-1] for c, key in enumerate(lp.cols)
                       if key[0] == i and bounds[c] != (0, 0)})

    def choose(z, bounds):
        cand = []
        for i in range(n):
            times = allowed_times(i, bounds)
            if len(times) <= 1:
                continue
            dist = []
            for tt in times:
                v = sum(z[c] for c, key in enumerate(lp.cols)
                        if key[0] == i and key[-1] == tt
                        and bounds[c] != (0, 0))
                dist.append((tt, v))
            frac = sum(v for _, v in dist if 1e-7 < v < 1 - 1e-7)
            if frac <= 1e-7:
                continue
            mass = sum(v for _, v in dist)
            cand.append(((mass, q[i], len(inst['succ'][i]), -i), i, dist))
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

    def bound_side(bounds, i, mid, side):
        b = list(bounds)
        for c, key in enumerate(lp.cols):
            if key[0] != i:
                continue
            tt = key[-1]
            if (side == 'lo' and tt > mid) or (side == 'hi' and tt <= mid):
                b[c] = (0, 0)
        return b

    def leaf_cert(F):
        stats['cert_lp'] += 1
        cert = integer_certificate(inst, h, use_dom=True,
                                   elig_aware=elig, forbid=F)
        if cert is not None and verify(inst, h, cert, forbid=F):
            return ('leaf', frozenset(F), cert)
        for i in range(n):
            lo, hi = _domain(inst, h, i)
            if lo <= hi and all((i, t) in F for t in range(lo, hi + 1)):
                stats['empty'] += 1
                return ('empty', frozenset(F), i)
        return None

    def bound_leaf(F):
        lb, width, wit = local_bound(inst, h, F, est, q, topo)
        if lb > h:
            stats['bound'] += 1
            return ('bound', frozenset(F), lb, wit)
        if lb == float('inf'):
            stats['empty'] += 1
            return ('empty', frozenset(F), wit[1])
        return None

    def dfs(bounds, F, depth):
        if depthcap is not None and depth > depthcap:
            stats['unknown'] = True
            stats['holes'] += 1
            return None
        if bound_close:
            bl = bound_leaf(F)
            if bl is not None:
                return bl
        res = solve(bounds, depth)
        if res is None:
            return None
        if res.status == 2:
            stats['leaves'] += 1
            node = leaf_cert(F)
            if node is None:
                node = bound_leaf(F)
            if node is None:
                stats['unknown'] = True
                stats['holes'] += 1
            return node
        if res.status != 0:
            stats['unknown'] = True
            stats['holes'] += 1
            return None
        z = res.x
        frac = False
        for c, key in enumerate(lp.cols):
            if 1e-7 < z[c] < 1 - 1e-7 and bounds[c] != (0, 0):
                frac = True
                break
        if not frac:
            got = _integral_schedule(inst, lp, z, elig)
            if got is not None:
                return ('yes', frozenset(F), got[0], got[1])
            singleton = _singleton_leaf(inst, h, F, lp, bounds)
            if singleton is not None:
                return ('yes', frozenset(F), singleton[1], singleton[2])
            i = None
            mid = None
            for j in range(n):
                times = allowed_times(j, bounds)
                if len(times) > 1:
                    i = j
                    mid = times[len(times) // 2 - 1]
                    break
            if i is None:
                stats['unknown'] = True
                stats['holes'] += 1
                return None
        else:
            i, mid = choose(z, bounds)
            if i is None:
                stats['unknown'] = True
                stats['holes'] += 1
                return None
        stats['depth'] = max(stats['depth'], depth)
        stats['branch_jobs'].append((i, mid, depth))
        times = allowed_times(i, bounds)
        lo_t = [t for t in times if t > mid]
        hi_t = [t for t in times if t <= mid]
        if not lo_t or not hi_t:
            stats['unknown'] = True
            stats['holes'] += 1
            return None
        loF = F | {(i, t) for t in lo_t}
        hiF = F | {(i, t) for t in hi_t}
        lo = dfs(bound_side(bounds, i, mid, 'lo'), loF, depth + 1)
        if lo is not None and lo[0] == 'yes':
            return lo
        hi = dfs(bound_side(bounds, i, mid, 'hi'), hiF, depth + 1)
        if hi is not None and hi[0] == 'yes':
            return hi
        if lo is None or hi is None:
            return None
        return ('node', i, mid, frozenset(F), lo, hi)

    tree = dfs(base, frozenset(), 0)
    stats['t'] = round(time.time() - t0, 5)
    if tree is None:
        return dict(verdict=None, proof=None, schedule=None, machine=None,
                    **stats)
    if tree[0] == 'yes':
        return dict(verdict=True, proof=None, schedule=tree[2],
                    machine=tree[3], **stats)
    proof = RACTProof(inst, h, tree, stats)
    if not proof.audit_rdf():
        stats['unknown'] = True
        return dict(verdict=None, proof=None, schedule=None, machine=None,
                    **stats)
    return dict(verdict=False, proof=proof, schedule=None, machine=None,
                **stats)


# --------------------------------------------------------------- R-ACT-C
class RACT(PACT):
    """PACT with the R-ACT complete decision procedure."""

    def __init__(self, inst, ract_mode='complete', **kw):
        super().__init__(inst, pact_depth=None, use_ga=False,
                         complete_fallback=True, **kw)
        self.ract_mode = ract_mode
        self.ract_bound = 0
        self.ract_empty = 0
        self.stats.update(ract_bound=0, ract_empty=0)

    def _probe(self, h):
        if self.ract_mode != 'complete':
            return super()._probe(h)
        r = ract_decide(self.inst, h, depthcap=None, nodecap=None)
        self.pact_calls += 1
        self.pact_lp += r['lp_solves']
        self.pact_cert_lp += r.get('cert_lp', 0)
        self.pact_nodes += r['nodes']
        self.ract_bound += r.get('bound', 0)
        self.ract_empty += r.get('empty', 0)
        self.stats['ract_bound'] += r.get('bound', 0)
        self.stats['ract_empty'] += r.get('empty', 0)
        if r['verdict'] is False:
            self.pact_no += 1
            self.stats['pact_no'] += 1
            self._record_proof(r['proof'])
            self.steps.append(dict(h=h, v=False, proof=r['proof'],
                                   engine='ract'))
            return False, r['proof']
        if r['verdict'] is True:
            self.pact_yes += 1
            self.stats['pact_yes'] += 1
            s, m = r['schedule'], r['machine']
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='ract'))
            return True, (s, m, cmax)
        # fall back to PACT's complete search, then CHD
        self.pact_unknown += 1
        self.stats['pact_unknown'] += 1
        r = pact_decide(self.inst, h, depthcap=None, nodecap=None)
        self.pact_lp += r['lp_solves']
        self.pact_cert_lp += r.get('cert_lp', 0)
        self.pact_nodes += r['nodes']
        if r['verdict'] is False:
            self.pact_no += 1
            self.stats['pact_no'] += 1
            self._record_proof(r['proof'])
            self.steps.append(dict(h=h, v=False, proof=r['proof'],
                                   engine='pact'))
            return False, r['proof']
        if r['verdict'] is True:
            self.pact_yes += 1
            self.stats['pact_yes'] += 1
            s, m = r['schedule'], r['machine']
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='pact'))
            return True, (s, m, cmax)
        self.stats['chd_fallback'] += 1
        v, st, rdf = self._decide(h)
        self.queries += 1
        self._absorb(st)
        self._record(h, v, st)
        if v is False:
            self.steps.append(dict(h=h, v=False, proof=rdf, engine='chd'))
        elif v is True:
            s, m = rdf.schedule, rdf.machine
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='chd'))
        else:
            self.steps.append(dict(h=h, v=None, engine='chd'))
        return v, rdf

    def _result(self):
        r = super()._result()
        r['ract_bound'] = self.ract_bound
        r['ract_empty'] = self.ract_empty
        return r


def run_ract(inst, known, name, idx, **kw):
    t0 = time.time()
    co = RACT(inst, **kw)
    r = co.optimize()
    dt = time.time() - t0
    r.update(name=name, idx=idx, known=known, t=round(dt, 4))
    b = getattr(co, 'chip', None) or {}
    p = getattr(co, 'pin', None) or {}
    r['chip_lb'] = b.get('lb')
    r['chip_ub'] = b.get('ub')
    r['pin_lb'] = p.get('lb')
    r['pin_solves'] = p.get('solves')
    r['pin_lp'] = getattr(co, 'pin_lp', 0)
    r['bb_lp'] = getattr(co, 'bb_lp', 0)
    r['cert_lp'] = getattr(co, 'cert_lp_total', 0)
    r['ga_stats'] = getattr(co, 'ga_stats', [])
    r['proof_kind'] = getattr(getattr(co, 'lb_proof', None),
                              'kind', None)
    r['stats2'] = getattr(co, 'stats', {})
    r['lns'] = getattr(co, 'lns_stats', None)
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof'] and r['total_audit']
                   and r['cert_h'] == known - 1)
    return r


# --------------------------------------------------------------- R-ACT-I
class RACTIter(RACT):
    """R-ACT with resumable iterative deepening.

    The frontier is expanded to depth 0, then 1, then 2, ... without
    rebuilding the tree.  A node is solved at most once, so the total
    LP count is the same as the complete search, while every depth
    yields an auditable frontier certificate.
    """

    def __init__(self, inst, ract_depth=4, **kw):
        super().__init__(inst, ract_mode='iter', **kw)
        self.ract_depth = ract_depth
        self.depth_trace = []
        self.stats.update(ract_depth_trace=0)

    def _probe(self, h):
        from anytime import AnytimeSearch
        s = AnytimeSearch(self.inst, h, policy='dfs')
        r = None
        trace = []
        for d in range(0, self.ract_depth + 1):
            r = s.run(depth_limit=d)
            trace.append(dict(d=d, status=r['status'], L=r['L'],
                              U=r['U'], lp=r['lp'], open=r['open']))
            if r['status'] in ('no', 'yes'):
                break
        if r is None or r['status'] == 'partial':
            r = s.run()
            trace.append(dict(d='inf', status=r['status'], L=r['L'],
                              U=r['U'], lp=r['lp'], open=r['open']))
        self.depth_trace.append(dict(h=h, trace=trace))
        self.pact_calls += 1
        self.pact_lp += r['lp']
        self.pact_cert_lp += r['cert']
        self.pact_nodes += r['nodes']
        if r['status'] == 'no':
            self.pact_no += 1
            self.stats['pact_no'] += 1
            self._record_proof(r['proof'])
            self.steps.append(dict(h=h, v=False, proof=r['proof'],
                                   engine='ract-iter'))
            return False, r['proof']
        if r['status'] == 'yes':
            self.pact_yes += 1
            self.stats['pact_yes'] += 1
            sched, mach = r['schedule'], r['machine']
            cmax = max(sched[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=sched, machine=mach,
                                   cmax=cmax, engine='ract-iter'))
            return True, (sched, mach, cmax)
        # a stuck frontier: fall back to PACT's complete search
        self.pact_unknown += 1
        self.stats['pact_unknown'] += 1
        r = pact_decide(self.inst, h, depthcap=None, nodecap=None)
        self.pact_lp += r['lp_solves']
        self.pact_cert_lp += r.get('cert_lp', 0)
        self.pact_nodes += r['nodes']
        if r['verdict'] is False:
            self.pact_no += 1
            self.stats['pact_no'] += 1
            self._record_proof(r['proof'])
            self.steps.append(dict(h=h, v=False, proof=r['proof'],
                                   engine='pact'))
            return False, r['proof']
        if r['verdict'] is True:
            self.pact_yes += 1
            self.stats['pact_yes'] += 1
            sched, mach = r['schedule'], r['machine']
            cmax = max(sched[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=sched, machine=mach,
                                   cmax=cmax, engine='pact'))
            return True, (sched, mach, cmax)
        self.stats['chd_fallback'] += 1
        v, st, rdf = self._decide(h)
        self.queries += 1
        self._absorb(st)
        self._record(h, v, st)
        if v is False:
            self.steps.append(dict(h=h, v=False, proof=rdf, engine='chd'))
        elif v is True:
            sched, mach = rdf.schedule, rdf.machine
            cmax = max(sched[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=sched, machine=mach,
                                   cmax=cmax, engine='chd'))
        else:
            self.steps.append(dict(h=h, v=None, engine='chd'))
        return v, rdf

    def _result(self):
        r = super()._result()
        r['depth_trace'] = self.depth_trace
        return r


def run_ract_iter(inst, known, name, idx, **kw):
    t0 = time.time()
    co = RACTIter(inst, **kw)
    r = co.optimize()
    dt = time.time() - t0
    r.update(name=name, idx=idx, known=known, t=round(dt, 4))
    b = getattr(co, 'chip', None) or {}
    p = getattr(co, 'pin', None) or {}
    r['chip_lb'] = b.get('lb')
    r['chip_ub'] = b.get('ub')
    r['pin_lb'] = p.get('lb')
    r['pin_solves'] = p.get('solves')
    r['pin_lp'] = getattr(co, 'pin_lp', 0)
    r['bb_lp'] = getattr(co, 'bb_lp', 0)
    r['cert_lp'] = getattr(co, 'cert_lp_total', 0)
    r['ga_stats'] = getattr(co, 'ga_stats', [])
    r['proof_kind'] = getattr(getattr(co, 'lb_proof', None),
                              'kind', None)
    r['stats2'] = getattr(co, 'stats', {})
    r['lns'] = getattr(co, 'lns_stats', None)
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof'] and r['total_audit']
                   and r['cert_h'] == known - 1)
    return r
