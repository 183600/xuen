"""v8.9 PACT-ALC: parameterized certificate trees with total trace.

PACT keeps SAGE's outer bracket, LP pin, GA upper side, STAB closure and
CHD fallback.  It replaces the single capped LP-BRANCH probe by a
three-valued, depth-parameterized search:

    decide(h, d) in {NO(proof), YES(schedule), UNKNOWN}

The parameter d is the certificate depth (number of nested split
decisions on a root-to-leaf path).  For d = 0,1,2,... the search is
iterative-deepening; a branch that exceeds d is a hole, not a global
abort.  If a certificate of depth <= d exists, decide(h,d) finds one.
If it returns UNKNOWN, the caller either raises d or hands the probe to
GENETIC-UB / the complete engine.

The complete engine has no depth cap.  Its termination measure is

    mu(F) = sum_i |D_i(h,F)|,

and every non-trivial split strictly decreases mu(F) on both children.
That gives total correctness for the decision procedure, and the total
trace certificate replays the whole bracket, not just the last NO tree.
"""
import sys
import time
import math

sys.path[:0] = ['exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e',
                'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from apex import Proof, OracleProof, bound_lb
from sage import (SAGE, BranchProof, SubsumptionProof, ga_schedule,
                  _elig_aware, _domain)
from sdecc import SDLP
from cert import verify, integer_certificate
from rdf import check_schedule
from po import heads_tails


# --------------------------------------------------------------- helpers
def _assign_machines(inst, starts):
    n, m, p = inst['n'], inst['m'], inst['p']
    order = sorted(range(n),
                   key=lambda i: (len(inst['elig'][i]), starts[i], i))
    busy = [[] for _ in range(m)]
    machs = [None] * n

    def rec(pos):
        if pos == n:
            return True
        i = order[pos]
        for k in inst['elig'][i]:
            if all(starts[i] + p[i] <= a or starts[i] >= b
                   for a, b in busy[k]):
                busy[k].append((starts[i], starts[i] + p[i]))
                machs[i] = k
                if rec(pos + 1):
                    return True
                busy[k].pop()
                machs[i] = None
        return False

    return machs if rec(0) else None


def _integral_schedule(inst, lp, z, elig):
    n, m, p = inst['n'], inst['m'], inst['p']
    starts = [None] * n
    machs = [None] * n
    for c, key in enumerate(lp.cols):
        if z[c] > 1 - 1e-7:
            i, t = key[0], key[-1]
            if starts[i] is not None:
                return None
            starts[i] = t
            if elig:
                machs[i] = key[1]
    if any(x is None for x in starts):
        return None
    if not elig:
        machs = _assign_machines(inst, starts)
        if machs is None:
            return None
    cmax = max(starts[i] + p[i] for i in range(n))
    if check_schedule(inst, cmax, starts, machs):
        return starts, machs
    return None


def _singleton_leaf(inst, h, F, lp, bounds):
    starts = [None] * inst['n']
    for c, key in enumerate(lp.cols):
        if bounds[c] != (0, 0):
            i, t = key[0], key[-1]
            if starts[i] is not None and starts[i] != t:
                return None
            starts[i] = t
    if any(x is None for x in starts):
        return None
    machs = _assign_machines(inst, starts)
    if machs is not None and check_schedule(inst, h, starts, machs):
        return ('yes', starts, machs)
    return None


# --------------------------------------------------- depth-parameterized
def pact_decide(inst, h, depthcap=None, nodecap=None, policy=None,
                seed=0, root_lp=None, root_res=None, branch_jobs=None,
                forbid0=None, timelimit=None):
    """Three-valued fixed-h decision procedure.

    Returns dict(verdict, proof, schedule, machine, nodes, leaves,
    depth, lp_solves, cert_lp, unknown, t).  verdict False = NO with a
    BranchProof, True = YES with a checked schedule, None = a hole.
    A hole is local: siblings are still explored.  A NO node is emitted
    only when both children are NO; one UNKNOWN child makes the parent
    UNKNOWN.

    If branch_jobs is not None, only jobs in that set may be used as
    branching variables.  A fractional LP with no allowed fractional
    job is reported as stats['insufficient'] = True (a special hole).
    """
    t0 = time.time()
    n, m, p = inst['n'], inst['m'], inst['p']
    elig = _elig_aware(inst)
    est, q = heads_tails(inst, 0, [0] * n)
    if (root_lp is not None and root_res is not None
            and root_lp.inst is inst and root_lp.T == h):
        lp = root_lp
    else:
        lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig,
                  forbid=forbid0)
    base = [(0, 1)] * lp.N
    stats = dict(nodes=0, leaves=0, depth=0, yes_depth=None,
                 lp_solves=0, cert_lp=0,
                 unknown=False, holes=0, branch_jobs=[], root_reused=0,
                 insufficient=False)
    policy = policy or {}
    allowed = None if branch_jobs is None else set(branch_jobs)

    def solve(bounds, depth):
        if timelimit is not None and time.time() - t0 > timelimit:
            stats['unknown'] = True
            stats['timeout'] = True
            return None
        if nodecap is not None and stats['nodes'] >= nodecap:
            stats['unknown'] = True
            return None
        stats['nodes'] += 1
        if (depth == 0 and root_res is not None and bounds == base):
            stats['root_reused'] += 1
            return root_res
        stats['lp_solves'] += 1
        return lp.solve(bounds)

    def allowed_times(i, bounds):
        return sorted({key[-1] for c, key in enumerate(lp.cols)
                       if key[0] == i and bounds[c] != (0, 0)})

    def choose(z, bounds):
        cand = []
        for i in range(n):
            if allowed is not None and i not in allowed:
                continue
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
            peak = max(v for _, v in dist)
            ent = -sum(v * math.log(v) for _, v in dist if v > 1e-12)
            mean_t = sum(tt * v for tt, v in dist) / max(mass, 1e-12)
            var_t = sum(v * (tt - mean_t) ** 2 for tt, v in dist) / max(mass, 1e-12)
            feats = dict(
                frac=frac, mass=mass, q=float(q[i]), p=float(p[i]),
                succ=float(len(inst['succ'][i])),
                pred=float(len(inst['pred'][i])),
                slack=float(h - q[i] - p[i] - est[i]),
                width=float(len(times)), peak=peak, entropy=ent,
                spread=math.sqrt(var_t),
                lo=float(times[0]), hi=float(times[-1]))
            cand.append((i, dist, feats))
        if not cand:
            return None, None
        weights = policy.get('weights')
        if weights:
            names = list(cand[0][2])
            lo = {k: min(c[2][k] for c in cand) for k in names}
            hi = {k: max(c[2][k] for c in cand) for k in names}
            scored = []
            for i, dist, feats in cand:
                sc = 0.0
                for k in names:
                    w = weights.get(k, 0.0)
                    if not w:
                        continue
                    span = hi[k] - lo[k]
                    val = 0.5 if span <= 1e-12 else (feats[k] - lo[k]) / span
                    sc += w * val
                scored.append(((sc, -i), i, dist))
            scored.sort(reverse=True)
            _, i, dist = scored[0]
        else:
            cand = [((c[2]['mass'], q[c[0]], len(inst['succ'][c[0]]), -c[0]),
                     c[0], c[1]) for c in cand]
            cand.sort(reverse=True)
            _, i, dist = cand[0]
        total = sum(v for _, v in dist)
        split = policy.get('split', 0.5)
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
                return ('empty', frozenset(F), i)
        return None

    def _has_yes(t):
        if t is None:
            return False
        if t[0] == 'yes':
            return True
        if t[0] == 'node':
            return _has_yes(t[4]) or _has_yes(t[5])
        return False

    def dfs(bounds, F, depth):
        if depthcap is not None and depth > depthcap:
            stats['unknown'] = True
            stats['holes'] += 1
            return None
        res = solve(bounds, depth)
        if res is None:
            return None
        if res.status == 2:
            stats['leaves'] += 1
            node = leaf_cert(F)
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
                stats['yes_depth'] = depth
                return ('yes', got[0], got[1])
            singleton = _singleton_leaf(inst, h, F, lp, bounds)
            if singleton is not None:
                stats['yes_depth'] = depth
                return singleton
            # all starts may still be ambiguous; choose any job with
            # multiple allowed times as a branching variable.
            i = None
            mid = None
            for j in range(n):
                if allowed is not None and j not in allowed:
                    continue
                times = allowed_times(j, bounds)
                if len(times) > 1:
                    i = j
                    mid = times[len(times) // 2 - 1]
                    break
            if i is None:
                if allowed is not None:
                    stats['insufficient'] = True
                stats['unknown'] = True
                stats['holes'] += 1
                return None
        else:
            i, mid = choose(z, bounds)
            if i is None:
                if allowed is not None:
                    stats['insufficient'] = True
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
        if _has_yes(lo):
            return ('node', i, mid, frozenset(F), lo, ('cut',))
        hi = dfs(bound_side(bounds, i, mid, 'hi'), hiF, depth + 1)
        if _has_yes(hi):
            return ('node', i, mid, frozenset(F), lo, hi)
        if lo is None or hi is None:
            return None
        return ('node', i, mid, frozenset(F), lo, hi)

    F0 = frozenset(forbid0 or ())
    stats['forbid0'] = len(F0)
    tree = dfs(base, F0, 0)
    stats['t'] = round(time.time() - t0, 5)
    if tree is None:
        return dict(verdict=None, proof=None, schedule=None, machine=None,
                    **stats)
    if _has_yes(tree):
        yes_leaf = tree
        while yes_leaf[0] == 'node':
            yes_leaf = yes_leaf[4] if _has_yes(yes_leaf[4]) else yes_leaf[5]
        return dict(verdict=True, proof=None, schedule=yes_leaf[1],
                    machine=yes_leaf[2], tree=tree, **stats)
    proof = BranchProof(inst, h, tree, stats, forbid0=F0)
    if not proof.audit_rdf():
        stats['unknown'] = True
        return dict(verdict=None, proof=None, schedule=None, machine=None,
                    **stats)
    return dict(verdict=False, proof=proof, schedule=None, machine=None,
                **stats)


# ------------------------------------------------------------- total trace
class TotalTrace(Proof):
    """One certificate for OPT=v: initial bounds + probe trace + final NO."""

    kind = 'total-trace'

    def __init__(self, inst, opt, lb0, ub0, init_lb_proof, init_bound,
                 init_schedule, init_machine, steps, final_lb_proof,
                 final_schedule, final_machine):
        super().__init__(inst, opt)
        self.opt = opt
        self.lb0 = lb0
        self.ub0 = ub0
        self.init_lb_proof = init_lb_proof
        self.init_bound = init_bound
        self.init_schedule = (list(init_schedule)
                              if init_schedule is not None else None)
        self.init_machine = (list(init_machine)
                             if init_machine is not None else None)
        self.steps = list(steps)
        self.final_lb_proof = final_lb_proof
        self.final_schedule = (list(final_schedule)
                               if final_schedule is not None else None)
        self.final_machine = (list(final_machine)
                              if final_machine is not None else None)

    def _sched_ok(self, h, s, m):
        if s is None or m is None:
            return False
        cmax = max(s[i] + self.inst['p'][i]
                   for i in range(self.inst['n']))
        return cmax <= h and check_schedule(self.inst, cmax, s, m)

    def audit_rdf(self):
        try:
            if self.final_lb_proof is None:
                return False
            if self.final_lb_proof.h != self.opt - 1:
                return False
            if not self.final_lb_proof.audit_rdf():
                return False
            if not self._sched_ok(self.opt, self.final_schedule,
                                  self.final_machine):
                return False
            if not self._sched_ok(self.ub0, self.init_schedule,
                                  self.init_machine):
                return False
            if self.init_lb_proof is not None:
                if self.init_lb_proof.h != self.lb0 - 1:
                    return False
                if not self.init_lb_proof.audit_rdf():
                    return False
            elif self.init_bound is None:
                return False
            elif self.init_bound != bound_lb(self.inst):
                return False
            elif self.lb0 > self.init_bound:
                return False
            if self.lb0 > self.ub0:
                return False
            lb, ub = self.lb0, self.ub0
            for step in self.steps:
                h = step['h']
                v = step['v']
                if not (lb <= h < ub):
                    return False
                if v is False:
                    p = step.get('proof')
                    if p is None or p.h != h or not p.audit_rdf():
                        return False
                    lb = max(lb, h + 1)
                elif v is True:
                    s = step.get('schedule')
                    m = step.get('machine')
                    if not self._sched_ok(h, s, m):
                        return False
                    cmax = max(s[i] + self.inst['p'][i]
                               for i in range(self.inst['n']))
                    ub = min(ub, cmax)
                else:
                    return False
            return lb == ub == self.opt
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


# --------------------------------------------------------------- PACT-ALC
class PACT(SAGE):
    def __init__(self, inst, pact_depth=3, pact_nodecap=96,
                 complete_fallback=True, use_ga=True,
                 pact_iterative=True, pact_mode='param', **kw):
        super().__init__(inst, use_ga=use_ga, **kw)
        self.pact_depth = pact_depth
        self.pact_nodecap = pact_nodecap
        self.pact_iterative = pact_iterative
        self.pact_mode = pact_mode
        self.complete_fallback = complete_fallback
        self.pact_lp = 0
        self.pact_cert_lp = 0
        self.pact_nodes = 0
        self.pact_calls = 0
        self.pact_no = 0
        self.pact_yes = 0
        self.pact_unknown = 0
        self.pact_depth_hist = []
        self.steps = []
        self.total_cert = None
        self.total_audit = False
        self.stats.update(pact_calls=0, pact_no=0, pact_yes=0,
                          pact_unknown=0, complete_fallback=0)

    def _run_depth(self, h, d):
        r = pact_decide(self.inst, h, depthcap=d,
                        nodecap=self.pact_nodecap)
        self.pact_calls += 1
        self.pact_lp += r['lp_solves']
        self.pact_cert_lp += r.get('cert_lp', 0)
        self.pact_nodes += r['nodes']
        return r

    def _probe(self, h):
        if self.pact_mode == 'closing' and self.opt - self.lb > 1:
            # bracketing probe: use SAGE's capped engines, then trace.
            v, payload = super()._probe(h)
            if v is False:
                p = payload if isinstance(payload, Proof) else OracleProof(payload)
                self._record_proof(p)
                self.steps.append(dict(h=h, v=False, proof=p,
                                       engine='sage'))
                return False, p
            if v is True:
                if isinstance(payload, tuple):
                    s, m, cmax = payload
                else:
                    s, m = payload.schedule, payload.machine
                    cmax = max(s[i] + self.inst['p'][i]
                               for i in range(self.inst['n']))
                self.steps.append(dict(h=h, v=True, schedule=s,
                                       machine=m, cmax=cmax,
                                       engine='sage'))
                return True, (s, m, cmax)
            self.steps.append(dict(h=h, v=None, engine='sage'))
            return v, payload
        if self.pact_mode == 'closing':
            # closing probe: complete certificate search first.
            r = pact_decide(self.inst, h, depthcap=None, nodecap=None)
            self.pact_lp += r['lp_solves']
            self.pact_cert_lp += r.get('cert_lp', 0)
            self.pact_nodes += r['nodes']
            if r['verdict'] is False:
                self.pact_no += 1
                self.stats['pact_no'] += 1
                self._record_proof(r['proof'])
                self.steps.append(dict(h=h, v=False, proof=r['proof'],
                                       engine='complete'))
                return False, r['proof']
            if r['verdict'] is True:
                self.pact_yes += 1
                self.stats['pact_yes'] += 1
                s, m = r['schedule'], r['machine']
                cmax = max(s[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                self.steps.append(dict(h=h, v=True, schedule=s,
                                       machine=m, cmax=cmax,
                                       engine='complete'))
                return True, (s, m, cmax)
        # Phase 1: parameterized NO-first iterative deepening.
        if self.pact_depth is None:
            depth_list = []
        elif self.pact_iterative:
            depth_list = list(range(self.pact_depth + 1))
        else:
            depth_list = [self.pact_depth]
        for d in depth_list:
            r = self._run_depth(h, d)
            if r['verdict'] is False:
                self.pact_no += 1
                self.stats['pact_no'] += 1
                self._record_proof(r['proof'])
                self.steps.append(dict(h=h, v=False, proof=r['proof'],
                                       engine='pact', depth=d))
                return False, r['proof']
            if r['verdict'] is True:
                self.pact_yes += 1
                self.stats['pact_yes'] += 1
                s, m = r['schedule'], r['machine']
                cmax = max(s[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                self.steps.append(dict(h=h, v=True, schedule=s,
                                       machine=m, cmax=cmax,
                                       engine='pact', depth=d))
                return True, (s, m, cmax)
            self.pact_unknown += 1
            self.stats['pact_unknown'] += 1
        # Phase 2: genetic upper side.
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
                self.steps.append(dict(h=h, v=True, schedule=s,
                                       machine=m, cmax=cmax,
                                       engine='ga'))
                return True, (s, m, cmax)
            self.stats['ga_no'] += 1
        # Phase 3: complete certificate search (no depth cap).
        if self.complete_fallback:
            self.stats['complete_fallback'] += 1
            r = pact_decide(self.inst, h, depthcap=None,
                            nodecap=None)
            self.pact_lp += r['lp_solves']
            self.pact_cert_lp += r.get('cert_lp', 0)
            self.pact_nodes += r['nodes']
            if r['verdict'] is False:
                self.pact_no += 1
                self.stats['pact_no'] += 1
                self._record_proof(r['proof'])
                self.steps.append(dict(h=h, v=False, proof=r['proof'],
                                       engine='complete'))
                return False, r['proof']
            if r['verdict'] is True:
                self.pact_yes += 1
                self.stats['pact_yes'] += 1
                s, m = r['schedule'], r['machine']
                cmax = max(s[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                self.steps.append(dict(h=h, v=True, schedule=s,
                                       machine=m, cmax=cmax,
                                       engine='complete'))
                return True, (s, m, cmax)
        # Phase 4: CHD last resort.
        self.stats['chd_fallback'] += 1
        v, st, rdf = self._decide(h)
        self.queries += 1
        self._absorb(st)
        self._record(h, v, st)
        if v is False:
            self.steps.append(dict(h=h, v=False, proof=rdf,
                                   engine='chd'))
        elif v is True:
            s, m = rdf.schedule, rdf.machine
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='chd'))
        else:
            self.steps.append(dict(h=h, v=None, engine='chd'))
        return v, rdf

    def initial_bounds(self):
        b = super().initial_bounds()
        self.init_lb, self.init_ub = b[0], b[1]
        self.init_schedule = list(b[2]) if b[2] is not None else None
        self.init_machine = list(b[3]) if b[3] is not None else None
        return b

    def _final_proof(self):
        ok = super()._final_proof()
        return ok

    def optimize(self):
        self.steps = []
        lb, ub, sched, mach = self.initial_bounds()
        if ub is None:
            return self._result()
        self.steps = []
        self.lb, self.opt = lb, ub
        self.schedule, self.machine = sched, mach
        self.lb0, self.ub0 = lb, ub
        self.pin_lp_total = getattr(self, 'pin_lp', 0)
        if self.lb == self.opt:
            self._final_proof()
            self._build_total()
            return self._result()
        limit = max(self.max_queries, (self.ub0 - self.lb0) + 1)
        while self.lb < self.opt and self.queries < limit:
            if self.opt - self.lb <= self.scan_cap:
                h = self.lb
                self.stats['scan_q'] += 1
            else:
                h = (self.lb + self.opt) // 2
                self.stats['bin_q'] += 1
            v, payload = self._probe(h)
            if v is True:
                if isinstance(payload, tuple):
                    s, m, cmax = payload
                else:
                    rdf = payload
                    s, m = rdf.schedule, rdf.machine
                    cmax = max(s[i] + self.inst['p'][i]
                               for i in range(self.inst['n']))
                if cmax < self.opt and check_schedule(self.inst, cmax,
                                                      s, m):
                    self.schedule = list(s)
                    self.machine = list(m)
                    self.opt = cmax
            elif v is False:
                self.lb = max(self.lb, h + 1)
                if isinstance(payload, Proof):
                    self._record_proof(payload)
                    self.lb_proof = payload
                else:
                    self.no_states[h] = payload
                    self.lb_proof = payload
            else:
                self.unknown += 1
                self._recover_unknown(h)
        if self.lb == self.opt:
            self._final_proof()
        self._build_total()
        return self._result()

    def _build_total(self):
        if not self.certified or self.lb != self.opt:
            self.total_cert = None
            self.total_audit = False
            return
        init_lb_proof = self.proofs.get(self.lb0 - 1)
        init_bound = bound_lb(self.inst)
        cert = TotalTrace(
            self.inst, self.opt, self.lb0, self.ub0, init_lb_proof,
            init_bound if init_lb_proof is None else None,
            self.init_schedule, self.init_machine, self.steps,
            self.lb_proof, self.schedule, self.machine)
        self.total_cert = cert
        self.total_audit = bool(cert.audit_rdf())
        if not self.total_audit:
            self.certified = False

    def _result(self):
        r = super()._result()
        r['total_audit'] = self.total_audit
        r['pact_calls'] = self.pact_calls
        r['pact_no'] = self.pact_no
        r['pact_yes'] = self.pact_yes
        r['pact_unknown'] = self.pact_unknown
        r['pact_lp'] = self.pact_lp
        r['pact_cert_lp'] = self.pact_cert_lp
        r['pact_nodes'] = self.pact_nodes
        r['total_kind'] = getattr(getattr(self, 'total_cert', None),
                                  'kind', None)
        return r


def run_pact(inst, known, name, idx, **kw):
    t0 = time.time()
    co = PACT(inst, **kw)
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
