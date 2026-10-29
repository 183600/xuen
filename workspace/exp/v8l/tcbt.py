"""v8.11 TOTAL-BT: total-correctness backtracking on top of SAGE-ALC.

SAGE-ALC replaces the CHD oracle by a capped LP-branch tree.  That makes
Q=0 on the 252-instance corpus, but it leaves three gaps:

  * nodecap/depthcap can turn a decision into UNKNOWN;
  * an LP-infeasible leaf can lack an integer Farkas certificate;
  * the final audit checks only the last NO tree, not the bracket trace.

TOTAL-BT keeps SAGE's fast path and adds a complete backstop:

  * BT-COMPLETE: uncapped domain-split backtracking with the measure
    mu(F) = sum_i |D_i(h,F)|; every split strictly decreases mu.
  * RAT-FARKAS: when integer rounding fails, extract the Phase-I dual,
    clear denominators, and replay A^T Y >= 0, b^T Y < 0 in integers.
  * TOTAL-CERT: one certificate that replays the lower tree, the upper
    schedule, and every bracket step from the initial LB/UB to OPT.
"""
import sys
import time
import math
from fractions import Fraction

sys.setrecursionlimit(10000)

sys.path[:0] = ['exp/v8l', 'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e',
                'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from apex import Proof, BoundProof, OracleProof, bound_lb
from sage import (SAGE, BranchProof, SubsumptionProof, lp_branch_decide,
                  ga_schedule, _elig_aware, _domain)
from sdecc import SDLP
from cert import _farkas_lp, verify, integer_certificate
from rdf import check_schedule
from po import heads_tails


# --------------------------------------------------------- rational Farkas
def verify_farkas_int(lp, Y):
    """Exact replay of a Farkas certificate for an SDLP.

    Primal: A_eq x = 1, A_ub x <= hi, x >= 0.
    Certificate: Y_eq free, Y_ub >= 0, A^T Y >= 0, 1^T Y_eq + hi^T Y_ub < 0.
    """
    A = lp.A.tocsr()
    n_eq = lp.n_eq
    nr = A.shape[0]
    if len(Y) != nr:
        return False
    AT = A.T.tocsr()
    for j in range(lp.N):
        col = AT.getrow(j)
        s = 0
        for idx, val in zip(col.indices, col.data):
            s += int(val) * Y[idx]
        if s < 0:
            return False
    bty = (sum(int(lp.hi[i]) * Y[n_eq + i] for i in range(nr - n_eq))
           + sum(Y[:n_eq]))
    return bty < 0


def farkas_rational(lp, dens=(10 ** 4, 10 ** 5, 10 ** 6, 10 ** 7,
                            10 ** 8, 10 ** 9)):
    """Extract a small-denominator integer Farkas certificate from Phase-I."""
    r = _farkas_lp(lp)
    if r.status != 0 or r.fun >= 0 or r.x is None:
        return None
    for D in dens:
        y = [Fraction(float(v)).limit_denominator(D) for v in r.x]
        L = 1
        for f in y:
            L = L * f.denominator // math.gcd(L, f.denominator)
        Y = [int(f * L) for f in y]
        if verify_farkas_int(lp, Y):
            return Y
    return None


class RationalFarkasProof(Proof):
    kind = 'rat-farkas'

    def __init__(self, inst, h, F, Y, stats=None):
        super().__init__(inst, h)
        self.F = frozenset(F)
        self.Y = list(Y)
        self.stats = stats or {}

    def _lp(self):
        return SDLP(self.inst, self.h, use_dom=True,
                    elig_aware=_elig_aware(self.inst), forbid=self.F)

    def audit_rdf(self):
        try:
            return verify_farkas_int(self._lp(), self.Y)
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


# --------------------------------------------------- measure-audited tree
class MeasureBranchProof(BranchProof):
    """A BranchProof whose splits also have to decrease the domain measure."""

    kind = 'total-branch'

    def __init__(self, inst, h, tree, stats=None):
        super().__init__(inst, h, tree, stats)
        self.est, self.q = heads_tails(inst, 0, [0] * inst['n'])

    def _allowed(self, i, F):
        lo = self.est[i]
        hi = self.h - self.q[i] - self.inst['p'][i]
        return [t for t in range(lo, hi + 1) if (i, t) not in F]

    def _measure(self, F):
        return sum(len(self._allowed(i, F))
                   for i in range(self.inst['n']))

    def _rat_ok(self, F, Y):
        lp = SDLP(self.inst, self.h, use_dom=True,
                  elig_aware=_elig_aware(self.inst), forbid=F)
        return verify_farkas_int(lp, Y)

    def _check(self, node, F):
        if node[0] == 'rat':
            if set(node[1]) != set(F):
                return False
            return self._rat_ok(F, node[2])
        if not super()._check(node, F):
            return False
        if node[0] == 'node':
            _, i, mid, parent_F, _, _ = node
            if set(parent_F) != set(F):
                return False
            allowed = self._allowed(i, F)
            lo_t = [t for t in allowed if t > mid]
            hi_t = [t for t in allowed if t <= mid]
            if not lo_t or not hi_t:
                return False
            loF = F | {(i, t) for t in lo_t}
            hiF = F | {(i, t) for t in hi_t}
            mu = self._measure(F)
            if not (self._measure(loF) < mu
                    and self._measure(hiF) < mu):
                return False
        return True

    def size(self):
        nodes = [0]
        leaves = [0]
        rats = [0]

        def rec(t):
            nodes[0] += 1
            if t[0] in ('leaf', 'empty'):
                leaves[0] += 1
            elif t[0] == 'rat':
                leaves[0] += 1
                rats[0] += 1
            elif t[0] == 'node':
                rec(t[4])
                rec(t[5])
        rec(self.tree)
        return dict(nodes=nodes[0], leaves=leaves[0], rat_leaves=rats[0])


# --------------------------------------------------------- complete search
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
        busy = [[] for _ in range(m)]
        for i in sorted(range(n), key=lambda i: (starts[i], i)):
            for k in inst['elig'][i]:
                if all(starts[i] + p[i] <= a or starts[i] >= b
                       for a, b in busy[k]):
                    machs[i] = k
                    busy[k].append((starts[i], starts[i] + p[i]))
                    break
            if machs[i] is None:
                return None
    cmax = max(starts[i] + p[i] for i in range(n))
    if check_schedule(inst, cmax, starts, machs):
        return starts, machs
    return None


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

    if rec(0):
        return machs
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


def tc_decide(inst, h, use_rat=True, nodecap=None, depthcap=None,
              rational_dens=None):
    """Complete proof-producing decision procedure for SCHED(I,h).

    Returns dict(verdict, proof, schedule, machine, stats).  verdict is
    False (NO with MeasureBranchProof), True (YES with a checked schedule),
    or None only if a certificate primitive fails or a cap is exceeded.
    """
    t0 = time.time()
    n, m, p = inst['n'], inst['m'], inst['p']
    elig = _elig_aware(inst)
    est, q = heads_tails(inst, 0, [0] * n)
    lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig)
    base = [(0, 1)] * lp.N
    dens = rational_dens
    stats = dict(nodes=0, lp_solves=0, leaves=0, int_cert=0,
                 rat_cert=0, cert_lp=0, empty=0, singleton=0, depth=0,
                 unknown=False, tree_nodes=0, tree_leaves=0,
                 rat_leaves=0, root_measure=sum(
                     max(0, h - q[i] - p[i] - est[i] + 1)
                     for i in range(n)))

    def solve(bounds):
        stats['nodes'] += 1
        stats['lp_solves'] += 1
        if nodecap is not None and stats['nodes'] > nodecap:
            stats['unknown'] = True
            return None
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
            cand.append(((sum(v for _, v in dist), q[i],
                          len(inst['succ'][i]), -i), i, dist))
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
        stats['leaves'] += 1
        stats['cert_lp'] += 1
        cert = integer_certificate(inst, h, use_dom=True,
                                   elig_aware=elig, forbid=F)
        if cert is not None and verify(inst, h, cert, forbid=F):
            stats['int_cert'] += 1
            return ('leaf', frozenset(F), cert)
        if use_rat:
            stats['cert_lp'] += 1
            lp2 = SDLP(inst, h, est, q, use_dom=True,
                       elig_aware=elig, forbid=F)
            Y = farkas_rational(lp2, dens) if dens else farkas_rational(lp2)
            if Y is not None:
                stats['rat_cert'] += 1
                return ('rat', frozenset(F), Y)
        for i in range(n):
            lo, hi = _domain(inst, h, i)
            if lo <= hi and all((i, t) in F for t in range(lo, hi + 1)):
                stats['empty'] += 1
                return ('empty', frozenset(F), i)
        stats['unknown'] = True
        return None

    def dfs(bounds, F, depth):
        if depthcap is not None and depth > depthcap:
            stats['unknown'] = True
            return None
        res = solve(bounds)
        if res is None:
            return None
        if res.status == 2:
            return leaf_cert(F)
        if res.status != 0:
            stats['unknown'] = True
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
                return ('yes', got[0], got[1])
            singleton = _singleton_leaf(inst, h, F, lp, bounds)
            if singleton is not None:
                stats['singleton'] += 1
                return singleton
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
                return None
        else:
            i, mid = choose(z, bounds)
            if i is None:
                stats['unknown'] = True
                return None
        stats['depth'] = max(stats['depth'], depth)
        times = allowed_times(i, bounds)
        lo_t = [t for t in times if t > mid]
        hi_t = [t for t in times if t <= mid]
        if not lo_t or not hi_t:
            stats['unknown'] = True
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
        return dict(verdict=True, proof=None, schedule=tree[1],
                    machine=tree[2], **stats)
    proof = MeasureBranchProof(inst, h, tree, stats)
    if not proof.audit_rdf():
        stats['unknown'] = True
        return dict(verdict=None, proof=None, schedule=None, machine=None,
                    **stats)
    sz = proof.size()
    stats.update(tree_nodes=sz['nodes'], tree_leaves=sz['leaves'],
                 rat_leaves=sz['rat_leaves'])
    return dict(verdict=False, proof=proof, schedule=None, machine=None,
                **stats)


# --------------------------------------------------------- total certificate
class TotalCertificate(Proof):
    """A single certificate for OPT=v: lower tree + upper schedule + trace."""

    kind = 'total'

    def __init__(self, inst, opt, lb_proof, schedule, machine, trace,
                 lb0, ub0, init_schedule, init_machine,
                 init_lb_proof=None, init_bound=None):
        super().__init__(inst, opt)
        self.opt = opt
        self.lb_proof = lb_proof
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.trace = list(trace)
        self.lb0 = lb0
        self.ub0 = ub0
        self.init_schedule = list(init_schedule) if init_schedule else None
        self.init_machine = list(init_machine) if init_machine else None
        self.init_lb_proof = init_lb_proof
        self.init_bound = init_bound

    def _schedule_ok(self, h, s, m):
        if s is None or m is None:
            return False
        cmax = max(s[i] + self.inst['p'][i]
                   for i in range(self.inst['n']))
        return cmax <= h and check_schedule(self.inst, cmax, s, m)

    def audit_rdf(self):
        try:
            if self.lb_proof is None:
                return False
            if self.lb_proof.h != self.opt - 1:
                return False
            if not self.lb_proof.audit_rdf():
                return False
            if not self._schedule_ok(self.opt, self.schedule,
                                     self.machine):
                return False
            if not self._schedule_ok(self.ub0, self.init_schedule,
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
            for step in self.trace:
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
                    if not self._schedule_ok(h, s, m):
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


# --------------------------------------------------------------- TOTAL-BT
class TOTAL(SAGE):
    def __init__(self, inst, use_tc=True, tc_first=False, use_rat=True,
                 tc_nodecap=None, tc_depthcap=None, **kw):
        super().__init__(inst, **kw)
        self.use_tc = use_tc
        self.tc_first = tc_first
        self.use_rat = use_rat
        self.tc_nodecap = tc_nodecap
        self.tc_depthcap = tc_depthcap
        self.tc_lp = 0
        self.tc_cert_lp = 0
        self.tc_rat = 0
        self.tc_int = 0
        self.tc_nodes = 0
        self.tc_leaves = 0
        self.tc_calls = 0
        self.tc_yes = 0
        self.tc_no = 0
        self.tc_unknown = 0
        self.total_trace = []
        self.total_cert = None
        self.total_audit = False
        self.init_lb = self.init_ub = None
        self.init_schedule = self.init_machine = None
        self.stats.update(tc_calls=0, tc_yes=0, tc_no=0,
                          tc_unknown=0, tc_lp=0, tc_cert_lp=0,
                          tc_rat=0)

    def initial_bounds(self):
        b = super().initial_bounds()
        self.init_lb, self.init_ub = b[0], b[1]
        self.init_schedule = list(b[2]) if b[2] is not None else None
        self.init_machine = list(b[3]) if b[3] is not None else None
        return b

    def _tc_run(self, h):
        r = tc_decide(self.inst, h, use_rat=self.use_rat,
                      nodecap=self.tc_nodecap,
                      depthcap=self.tc_depthcap)
        self.tc_calls += 1
        self.stats['tc_calls'] += 1
        self.tc_lp += r['lp_solves']
        self.stats['tc_lp'] += r['lp_solves']
        self.tc_cert_lp += r.get('cert_lp', 0)
        self.stats['tc_cert_lp'] += r.get('cert_lp', 0)
        self.tc_nodes += r['nodes']
        self.tc_leaves += r['leaves']
        self.tc_rat += r.get('rat_cert', 0)
        self.tc_int += r.get('int_cert', 0)
        self.stats['tc_rat'] += r.get('rat_cert', 0)
        return r

    def _trace(self, h, v, payload, engine):
        step = dict(h=h, v=v, engine=engine)
        if v is False:
            p = payload
            if not isinstance(p, Proof):
                p = OracleProof(payload)
            step['proof'] = p
        elif v is True:
            s, m, cmax = payload
            step['schedule'] = list(s)
            step['machine'] = list(m)
            step['cmax'] = cmax
        else:
            step['proof'] = None
        self.total_trace.append(step)

    def _probe(self, h):
        if self.tc_first and self.use_tc:
            r = self._tc_run(h)
            if r['verdict'] is False:
                self.tc_no += 1
                self.stats['tc_no'] += 1
                self._record_proof(r['proof'])
                self._trace(h, False, r['proof'], 'tc')
                return False, r['proof']
            if r['verdict'] is True:
                self.tc_yes += 1
                self.stats['tc_yes'] += 1
                s, m = r['schedule'], r['machine']
                cmax = max(s[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                self._trace(h, True, (s, m, cmax), 'tc')
                return True, (s, m, cmax)
            self.tc_unknown += 1
            self.stats['tc_unknown'] += 1

        if self.use_bb:
            r = lp_branch_decide(self.inst, h,
                                 nodecap=self.bb_nodecap,
                                 depthcap=self.bb_depthcap)
            self.bb_lp += r['lp_solves']
            self.cert_lp_total += r.get('cert_lp', 0)
            if r['verdict'] is False:
                self.stats['bb_no'] += 1
                self._record_proof(r['proof'])
                self._trace(h, False, r['proof'], 'bb')
                return False, r['proof']
            if r['verdict'] is True and self.bb_yes:
                s, m = r['schedule'], r['machine']
                cmax = max(s[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                if check_schedule(self.inst, h, s, m):
                    self.stats['bb_yes'] += 1
                    self._trace(h, True, (s, m, cmax), 'bb')
                    return True, (s, m, cmax)
            if r['verdict'] is True:
                self.stats['bb_yes_ignored'] = (
                    self.stats.get('bb_yes_ignored', 0) + 1)
            else:
                self.stats['bb_unknown'] += 1
                if self.use_tc:
                    r2 = self._tc_run(h)
                    if r2['verdict'] is False:
                        self.tc_no += 1
                        self.stats['tc_no'] += 1
                        self._record_proof(r2['proof'])
                        self._trace(h, False, r2['proof'], 'tc')
                        return False, r2['proof']
                    if r2['verdict'] is True:
                        self.tc_yes += 1
                        self.stats['tc_yes'] += 1
                        s, m = r2['schedule'], r2['machine']
                        cmax = max(s[i] + self.inst['p'][i]
                                   for i in range(self.inst['n']))
                        self._trace(h, True, (s, m, cmax), 'tc')
                        return True, (s, m, cmax)
                    self.tc_unknown += 1
                    self.stats['tc_unknown'] += 1

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
                self._trace(h, True, (s, m, cmax), 'ga')
                return True, (s, m, cmax)
            self.stats['ga_no'] += 1

        self.stats['chd_fallback'] += 1
        v, st, rdf = self._decide(h)
        self.queries += 1
        self._absorb(st)
        self._record(h, v, st)
        if v is False:
            self._trace(h, False, rdf, 'chd')
        elif v is True:
            s, m = rdf.schedule, rdf.machine
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self._trace(h, True, (s, m, cmax), 'chd')
        else:
            self._trace(h, None, None, 'chd')
        return v, rdf

    def _final_proof(self):
        p = self._ensure_lb_proof(self.lb)
        if p is not None:
            self.lb_proof = p
            self.certified = True
            self.stats['proof_final'] += 1
            return True
        if self.use_tc:
            r = self._tc_run(self.lb - 1)
            if r['verdict'] is False:
                self._record_proof(r['proof'])
                self.lb_proof = r['proof']
                self.certified = True
                self.stats['proof_final'] += 1
                return True
        return super()._final_proof()

    def optimize(self):
        self.total_trace = []
        lb, ub, sched, mach = self.initial_bounds()
        if ub is None:
            return self._result()
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
                if cmax < self.opt and check_schedule(self.inst, cmax, s, m):
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
        cert = TotalCertificate(
            self.inst, self.opt, self.lb_proof, self.schedule,
            self.machine, self.total_trace, self.lb0, self.ub0,
            self.init_schedule, self.init_machine,
            init_lb_proof=init_lb_proof,
            init_bound=init_bound if init_lb_proof is None else None)
        self.total_cert = cert
        self.total_audit = bool(cert.audit_rdf())
        if not self.total_audit:
            self.certified = False

    def _result(self):
        r = super()._result()
        r['total_audit'] = self.total_audit
        r['tc_calls'] = self.tc_calls
        r['tc_yes'] = self.tc_yes
        r['tc_no'] = self.tc_no
        r['tc_unknown'] = self.tc_unknown
        r['tc_lp'] = self.tc_lp
        r['tc_cert_lp'] = self.tc_cert_lp
        r['tc_nodes'] = self.tc_nodes
        r['tc_leaves'] = self.tc_leaves
        r['tc_rat'] = self.tc_rat
        r['tc_int'] = self.tc_int
        r['total_kind'] = getattr(getattr(self, 'total_cert', None),
                                  'kind', None)
        return r


def run_total(inst, known, name, idx, **kw):
    t0 = time.time()
    co = TOTAL(inst, **kw)
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
