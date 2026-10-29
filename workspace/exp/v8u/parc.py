"""v9.2 PARC-ICF: Pareto-certified approximation with relaxation certificates.

PARC extends the v9.0 ICF state

    (L, U, s, m, pi),   pi : NO(L-1),  Cmax(s)=U,  L<=U

by a *secondary-objective Pareto layer*.  The primary objective is still
makespan.  The secondary objective is a linear schedule cost

    W(s) = sum_i w_i * (s_i + p_i),

with unit weights by default (total completion time).  For a slack
Delta >= 0 define the epsilon-constraint subproblem

    Q(Delta) = min { W(S) : S feasible, Cmax(S) <= U + Delta }.

A *relaxation certificate* for horizon h = U+Delta is a partition tree of
start-time boxes.  Every leaf carries either

  * a dual feasible witness for the LP relaxation of min W at horizon h,
    giving a lower bound b_l <= min_{S in leaf} W(S); or
  * an exact Farkas/empty certificate proving that the leaf is infeasible.

The global lower bound is b = min_l b_l.  An incumbent schedule s with
Cmax(s) <= h gives a = W(s) >= Q(Delta).  Thus

    b <= Q(Delta) <= a.

If a - b < 1 the bound is exact, because W is integral.  If a <= (1+eps)b
the incumbent is a certified (1+eps)-approximation.  If the search is
stopped earlier, (b,a) is still a sound bracket.

The Pareto layer evaluates a finite set of slacks Delta_0 < ... < Delta_k
and stores the resulting points.  The epsilon-constraint method computes
the supported Pareto front of (Cmax, W): a point is kept only if its
incumbent is not dominated by another point's incumbent, while its dual
bound remains attached as a certificate.  A geometric grid gives a
(1+alpha, 1+eps) bi-criteria coverage guarantee; the default grid is the
integer grid 0,1,2,4,8.

All certificate predicates are executable and independent of the search:
the audit re-checks schedules with `check_schedule`, Farkas leaves with
`verify`, dual witnesses against the LP matrix, and the partition tree
against the start-time domain.
"""
import heapq
import math
import time

import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog

import sys
sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from sdecc import SDLP
from po import heads_tails
from pact import _elig_aware, _integral_schedule
from cert import integer_certificate, verify
from rdf import check_schedule
from icf import (cmax, run_icf, ICFCertificate, PartialCertificate,
                 _choose_h)


TOL = 1e-6


# --------------------------------------------------------------- utilities
def weights(inst, mode='unit'):
    n = inst['n']
    if mode == 'unit':
        return [1.0] * n
    if mode == 'p':
        return [float(inst['p'][i]) for i in range(n)]
    if mode == 'wsp':
        return [float(max(1, inst['p'][i])) for i in range(n)]
    raise ValueError('unknown weight mode %r' % (mode,))


def wsum(inst, starts, w=None):
    n = inst['n']
    if w is None:
        w = [1.0] * n
    return float(sum(w[i] * (starts[i] + inst['p'][i]) for i in range(n)))


def _domain_times(inst, h, i):
    est, q = heads_tails(inst, 0, [0] * inst['n'])
    lo = est[i]
    hi = h - q[i] - inst['p'][i]
    return list(range(lo, hi + 1)) if lo <= hi else []


def _objective(lp, w):
    return np.asarray([w[key[0]] * (key[-1] + lp.p[key[0]])
                       for key in lp.cols], dtype=float)


def _bounds_from_F(lp, F):
    return [(0, 0) if (key[0], key[-1]) in F else (0, 1)
            for key in lp.cols]


def _active_from_bounds(bounds):
    return np.asarray([b != (0, 0) for b in bounds], dtype=bool)


def _solve_obj(lp, c, F):
    bounds = _bounds_from_F(lp, F)
    res = linprog(c, A_ub=lp.A, b_ub=lp.hi,
                  A_eq=lp.A[:lp.n_eq], b_eq=np.ones(lp.n),
                  bounds=bounds, method='highs')
    return res, bounds


# ------------------------------------------------------------ dual witness
class DualWitness:
    """A dual-feasible vector for the bound-constrained SDLP."""

    __slots__ = ('y', 'z', 'mu', 'active', 'value', 'ok', 'slack_min')

    def __init__(self, y, z, mu, active, value, ok, slack_min):
        self.y = y
        self.z = z
        self.mu = mu
        self.active = active
        self.value = float(value)
        self.ok = bool(ok)
        self.slack_min = float(slack_min)

    def audit(self, lp, c, tol=1e-5):
        try:
            y = np.asarray(self.y, dtype=float)
            z = np.asarray(self.z, dtype=float)
            mu = np.asarray(self.mu, dtype=float)
            active = np.asarray(self.active, dtype=bool)
            if y.size != lp.A.shape[0] or z.size != lp.n \
                    or mu.size != lp.N:
                return False
            if y.max(initial=0.0) > tol:
                return False
            if active.any() and mu[active].max(initial=0.0) > tol:
                return False
            slack = c - lp.A.T.dot(y) - lp.A[:lp.n_eq].T.dot(z) - mu
            if active.any() and slack[active].min(initial=0.0) < -tol:
                return False
            val = (float(lp.hi.dot(y)) + float(np.sum(z))
                   + float(np.sum(mu[active])))
            if abs(val - self.value) > 1e-4 * (1.0 + abs(self.value)):
                return False
            return bool(self.ok)
        except Exception:
            return False


def _make_witness(lp, c, res, active, tol=1e-7):
    y = np.minimum(np.asarray(res.ineqlin.marginals, dtype=float), 0.0)
    z = np.asarray(res.eqlin.marginals, dtype=float)
    mu = np.minimum(np.asarray(res.upper.marginals, dtype=float), 0.0)
    mu[~active] = 0.0
    slack = c - lp.A.T.dot(y) - lp.A[:lp.n_eq].T.dot(z) - mu
    value = (float(lp.hi.dot(y)) + float(np.sum(z))
             + float(np.sum(mu[active])))
    ok = (y.max(initial=0.0) <= tol
          and (not active.any()
               or mu[active].max(initial=0.0) <= tol)
          and (not active.any()
               or slack[active].min(initial=0.0) >= -tol))
    return DualWitness(y, z, mu, active, value, ok,
                       slack[active].min(initial=0.0)
                       if active.any() else 0.0)


# ------------------------------------------------------------ primal dive
def dive_primal(inst, h, lp, c, w, est, q, elig_aware, incumbent=None,
                nodecap=64):
    """Depth-first LP-guided dive used to seed the B&B incumbent.

    At each node the child with the smaller LP bound is visited first.  The
    routine is deliberately budgeted: it is a primal heuristic, not a proof.
    """
    n = inst['n']
    best_sched = None
    best_w = float('inf')
    if incumbent is not None:
        s, m = incumbent
        cc = max(s[i] + inst['p'][i] for i in range(n))
        if cc <= h and check_schedule(inst, cc, s, m):
            best_sched = (list(s), list(m))
            best_w = wsum(inst, s, w)
    nodes = [0]

    def consider(got):
        nonlocal best_sched, best_w
        if got is None:
            return
        s, m = got
        cc = max(s[i] + inst['p'][i] for i in range(n))
        if cc > h or not check_schedule(inst, cc, s, m):
            return
        ww = wsum(inst, s, w)
        if ww < best_w - 1e-9:
            best_w = ww
            best_sched = (list(s), list(m))

    def dfs(F, depth):
        if nodes[0] >= nodecap or depth > 48:
            return
        res, bounds = _solve_obj(lp, c, F)
        nodes[0] += 1
        if res.status != 0:
            return
        z = res.x
        frac = any(bounds[j] != (0, 0) and 1e-7 < z[j] < 1 - 1e-7
                   for j in range(lp.N))
        if not frac:
            consider(_integral_from_lp(inst, lp, z, elig_aware))
            return
        picked = _choose_branch(lp, z, F, inst, h, est, q)
        if picked is None:
            return
        i, mid, _ = picked
        times = _domain_times_cached(inst, h, i, est, q)
        kids = []
        for side in ('lo', 'hi'):
            FF = _child_F(F, i, times, mid, side)
            r2, _ = _solve_obj(lp, c, FF)
            nodes[0] += 1
            if r2.status == 0:
                kids.append((float(r2.fun), FF))
        kids.sort(key=lambda x: x[0])
        for val, FF in kids:
            if best_w - val < 1 - TOL:
                continue
            dfs(FF, depth + 1)
            if nodes[0] >= nodecap:
                return

    dfs(frozenset(), 0)
    return best_sched, best_w, nodes[0]


# ------------------------------------------------------------- Farkas fallback
def lp_farkas(lp, tol=1e-6):
    """A real-valued Farkas certificate for an infeasible SDLP.

    The primal is A_ub x <= b, A_eq x = d, 0 <= x <= 1.  A ray
    y<=0, z free, mu<=0 with A_ub^T y + A_eq^T z + mu <= 0 and
    b^T y + d^T z + 1^T mu > 0 refutes feasibility.
    """
    A = lp.A.tocsr()
    hi = lp.hi
    n_eq = lp.n_eq
    N = lp.N
    nr = A.shape[0]
    B = sp.hstack([A.T, A[:n_eq].T, sp.identity(N, format='csr')],
                  format='csr')
    c = np.zeros(nr + n_eq + N)
    c[:nr] = hi
    c[nr:nr + n_eq] = 1.0
    c[nr + n_eq:] = 1.0
    A_ub = sp.vstack([B, sp.csr_matrix(c.reshape(1, -1))],
                     format='csr')
    b_ub = np.zeros(N + 1)
    b_ub[-1] = 1.0
    bounds = ([(None, 0)] * nr + [(None, None)] * n_eq
              + [(None, 0)] * N)
    try:
        res = linprog(-c, A_ub=A_ub, b_ub=b_ub, bounds=bounds,
                      method='highs')
    except Exception:
        return None
    if res.status != 0:
        return None
    y = res.x[:nr]
    z = res.x[nr:nr + n_eq]
    mu = res.x[nr + n_eq:]
    value = float(hi.dot(y) + np.sum(z) + np.sum(mu))
    if y.max(initial=0.0) > tol or mu.max(initial=0.0) > tol:
        return None
    slack = A.T.dot(y) + A[:n_eq].T.dot(z) + mu
    if slack.max(initial=0.0) > tol or value <= tol:
        return None
    return dict(kind='lp_farkas', y=y, z=z, mu=mu, value=value,
                slack_max=float(slack.max(initial=0.0)))


def verify_lp_farkas(lp, cert, tol=1e-5):
    try:
        y = np.asarray(cert['y'], dtype=float)
        z = np.asarray(cert['z'], dtype=float)
        mu = np.asarray(cert['mu'], dtype=float)
        if y.size != lp.A.shape[0] or z.size != lp.n_eq \
                or mu.size != lp.N:
            return False
        if y.max(initial=0.0) > tol or mu.max(initial=0.0) > tol:
            return False
        slack = lp.A.T.dot(y) + lp.A[:lp.n_eq].T.dot(z) + mu
        if slack.max(initial=0.0) > tol:
            return False
        value = float(lp.hi.dot(y) + np.sum(z) + np.sum(mu))
        return value > tol
    except Exception:
        return False


def _certify_infeasible(inst, h, F, est, q, elig_aware):
    """Return (cert, ok) for a box whose LP is infeasible."""
    cert = integer_certificate(inst, h, use_dom=True,
                               elig_aware=elig_aware, forbid=F)
    if cert is not None and verify(inst, h, cert, forbid=F):
        return cert, True
    for i in range(inst['n']):
        times = _domain_times_cached(inst, h, i, est, q)
        if times and all((i, t) in F for t in times):
            return {'kind': 'empty', 'job': i}, True
    try:
        lpF = SDLP(inst, h, est, q, use_dom=True,
                   elig_aware=elig_aware, forbid=F)
        f = lp_farkas(lpF)
        if f is not None and verify_lp_farkas(lpF, f):
            return f, True
    except Exception:
        pass
    return None, False


# ---------------------------------------------------------------- tree nodes
class RelaxNode:
    """A node in the secondary relaxation tree.

    kind = 'split' | 'leaf'
    leaf status = 'open' | 'integral' | 'infeasible' | 'closed'
    """

    __slots__ = ('kind', 'F', 'i', 'mid', 'lo', 'hi', 'h', 'status',
                 'lb', 'res_fun', 'z', 'witness', 'sched', 'mach', 'w',
                 'sched_cmax', 'farkas', 'depth')

    def __init__(self, kind, F, h, depth=0):
        self.kind = kind
        self.F = frozenset(F)
        self.i = None
        self.mid = None
        self.lo = None
        self.hi = None
        self.h = h
        self.status = None
        self.lb = None
        self.res_fun = None
        self.z = None
        self.witness = None
        self.sched = None
        self.mach = None
        self.w = None
        self.sched_cmax = None
        self.farkas = None
        self.depth = depth


def _domain_times_cached(inst, h, i, est=None, q=None):
    if est is None or q is None:
        est, q = heads_tails(inst, 0, [0] * inst['n'])
    lo = est[i]
    hi = h - q[i] - inst['p'][i]
    return list(range(lo, hi + 1)) if lo <= hi else []


def _child_F(F, i, times, mid, side):
    out = set(F)
    if side == 'lo':
        out.update((i, t) for t in times if t > mid)
    else:
        out.update((i, t) for t in times if t <= mid)
    return frozenset(out)


def _choose_branch(lp, z, F, inst, h, est, q):
    """Pick a job/time split (mass-median, matching the v9.0 branch rule)."""
    n = inst['n']
    best = None
    for i in range(n):
        times = _domain_times_cached(inst, h, i, est, q)
        allowed = [t for t in times if (i, t) not in F]
        if len(allowed) <= 1:
            continue
        mass = {}
        for c, key in enumerate(lp.cols):
            if key[0] != i or (i, key[-1]) in F:
                continue
            if z[c] <= 1e-8:
                continue
            mass[key[-1]] = mass.get(key[-1], 0.0) + float(z[c])
        if len(mass) <= 1:
            continue
        frac = sum(v for v in mass.values() if 1e-7 < v < 1 - 1e-7)
        total = sum(mass.values())
        if total <= 1e-9:
            continue
        acc = 0.0
        mid = None
        for t in sorted(mass):
            acc += mass[t]
            if acc >= 0.5 * total:
                mid = t
                break
        if mid is None:
            mid = sorted(mass)[len(mass) // 2]
        lo_t = [t for t in allowed if t > mid]
        hi_t = [t for t in allowed if t <= mid]
        if not lo_t or not hi_t:
            continue
        score = (frac, len(mass), i)
        if best is None or score > best[0]:
            best = (score, i, mid)
    if best is None:
        # Fallback for integral-but-unassignable LP solutions: split any
        # job with at least two allowed times.
        for i in range(n):
            times = _domain_times_cached(inst, h, i, est, q)
            allowed = [t for t in times if (i, t) not in F]
            if len(allowed) > 1:
                mid = allowed[len(allowed) // 2 - 1]
                return i, mid, 'ambig'
        return None
    return best[1], best[2], 'frac'


def _integral_from_lp(inst, lp, z, elig):
    from pact import _assign_machines
    starts = [None] * inst['n']
    machs = [None] * inst['n']
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
    h = lp.T
    if check_schedule(inst, h, starts, machs):
        return starts, machs
    return None


# ------------------------------------------------------------- B&B for Q(D)
def bb_secondary(inst, h, w=None, incumbent=None, nodecap=256,
                 eps=0.0, collect_tree=False, collect_witness=False,
                 seed_schedules=None, dual_audit=True, goals=None,
                 dive=True, divecap=64, dive_gap=4.0):
    """Best-first branch-and-bound for min W subject to Cmax <= h.

    incumbent: (starts, machines) or None.
    nodecap: maximum number of LP solves (root counts as one).
    eps: stop when best <= (1+eps) * global lower bound.
    goals: optional list of target makespans; a schedule with cmax <= goal
           may seed the incumbent with its W value, but the LP horizon is h.
    """
    t0 = time.time()
    n = inst['n']
    if w is None:
        w = weights(inst, 'unit')
    elig_aware = _elig_aware(inst)
    est, q = heads_tails(inst, 0, [0] * n)
    lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig_aware)
    c = _objective(lp, w)
    domains = [_domain_times_cached(inst, h, i, est, q) for i in range(n)]

    best_sched = None
    best_w = float('inf')
    best_cmax = None

    def consider(starts, machs):
        nonlocal best_sched, best_w, best_cmax
        if starts is None or machs is None:
            return False
        cc = max(starts[i] + inst['p'][i] for i in range(n))
        if cc > h:
            return False
        if not check_schedule(inst, cc, starts, machs):
            return False
        ww = wsum(inst, starts, w)
        if ww < best_w - 1e-9:
            best_w = ww
            best_sched = (list(starts), list(machs))
            best_cmax = cc
            return True
        return False

    if incumbent is not None:
        consider(incumbent[0], incumbent[1])
    for s in (seed_schedules or ()):
        if s is not None:
            consider(s[0], s[1])

    stats = dict(root=None, b=0.0, a=float('inf'), exact=False,
                 eps_ok=False, nodes=0, lp=0, leaves=0, open=0,
                 dual_checks=0, dual_fail=0, farkas_checks=0,
                 farkas_fail=0, holes=0, root_integral=False,
                 best_cmax=None, tree=None, t=0.0, reason='',
                 dive_nodes=0, dive_best=None, _best_sched=None)

    root = RelaxNode('leaf', frozenset(), h)
    res, bounds = _solve_obj(lp, c, root.F)
    stats['nodes'] = 1
    stats['lp'] = 1
    if res.status == 0:
        stats['root'] = float(res.fun)
        root.res_fun = float(res.fun)
        root.lb = float(res.fun)
        root.z = np.asarray(res.x, dtype=float)
        if collect_witness:
            active = _active_from_bounds(bounds)
            wit = _make_witness(lp, c, res, active)
            root.witness = wit
            if dual_audit:
                stats['dual_checks'] += 1
                if not wit.audit(lp, c):
                    stats['dual_fail'] += 1
    elif res.status == 2:
        stats['root'] = float('inf')
        stats['b'] = float('inf')
        stats['a'] = best_w
        stats['exact'] = True
        stats['reason'] = 'root_infeasible'
        stats['t'] = round(time.time() - t0, 4)
        return stats
    else:
        stats['root'] = None
        stats['holes'] += 1
        stats['b'] = 0.0
        stats['a'] = best_w
        stats['reason'] = 'root_status_%s' % res.status
        stats['t'] = round(time.time() - t0, 4)
        stats['_best_sched'] = best_sched
        return stats

    # Try the root LP as an integral incumbent.
    z = root.z
    frac = any(bounds[cc] != (0, 0) and 1e-7 < z[cc] < 1 - 1e-7
               for cc in range(lp.N))
    if not frac:
        got = _integral_from_lp(inst, lp, z, elig_aware)
        if got is not None:
            consider(got[0], got[1])
            root.status = 'integral'
            root.sched, root.mach = got
            root.w = wsum(inst, got[0], w)
            root.sched_cmax = max(got[0][i] + inst['p'][i]
                                  for i in range(n))
            stats['root_integral'] = True
            b = root.lb
            stats.update(b=float(b), a=float(best_w),
                         exact=bool(best_w - b < 1 - TOL),
                         eps_ok=bool(best_w <= (1 + eps) * b + TOL
                                     or best_w - b < 1 - TOL),
                         leaves=1, open=0, best_cmax=best_cmax,
                         reason='root_integral',
                         t=round(time.time() - t0, 4),
                         tree=root if collect_tree else None,
                         _best_sched=best_sched)
            return stats

    if dive and best_w - root.lb > dive_gap:
        ds, dw, dn = dive_primal(inst, h, lp, c, w, est, q, elig_aware,
                                 incumbent=best_sched, nodecap=divecap)
        stats['dive_nodes'] = dn
        if ds is not None:
            consider(ds[0], ds[1])
            stats['dive_best'] = best_w

    root.status = 'open'
    heap = [(root.lb, 0, root)]
    counter = 0
    leaves = []
    stop_reason = ''

    def min_open_lb():
        vals = [x[0] for x in heap]
        for nd in leaves:
            if nd.status != 'infeasible' and nd.lb is not None:
                vals.append(nd.lb)
        return min(vals) if vals else float('inf')

    while heap and stats['nodes'] < nodecap:
        bnow = min_open_lb()
        if best_w - bnow < 1 - TOL:
            stop_reason = 'integrality'
            break
        if eps > 0 and best_w <= (1 + eps) * bnow + TOL:
            stop_reason = 'eps'
            break
        lb, _, node = heapq.heappop(heap)
        if best_w <= lb + TOL:
            node.status = 'closed'
            leaves.append(node)
            continue

        z = node.z
        if z is None:
            res, bounds = _solve_obj(lp, c, node.F)
            stats['nodes'] += 1
            stats['lp'] += 1
            if res.status == 2:
                node.status = 'infeasible'
                cert, ok = _certify_infeasible(inst, h, node.F,
                                               est, q, elig_aware)
                node.farkas = cert
                stats['farkas_checks'] += 1
                if not ok:
                    stats['farkas_fail'] += 1
                    stats['holes'] += 1
                leaves.append(node)
                continue
            if res.status != 0:
                node.status = 'open'
                node.lb = 0.0
                stats['holes'] += 1
                leaves.append(node)
                continue
            node.res_fun = float(res.fun)
            node.lb = float(res.fun)
            node.z = np.asarray(res.x, dtype=float)
            if collect_witness:
                active = _active_from_bounds(bounds)
                wit = _make_witness(lp, c, res, active)
                node.witness = wit
                if dual_audit:
                    stats['dual_checks'] += 1
                    if not wit.audit(lp, c):
                        stats['dual_fail'] += 1
            z = node.z

        bounds = _bounds_from_F(lp, node.F)
        frac = any(bounds[cc] != (0, 0) and 1e-7 < z[cc] < 1 - 1e-7
                   for cc in range(lp.N))
        got = None
        if not frac:
            got = _integral_from_lp(inst, lp, z, elig_aware)
            if got is not None:
                consider(got[0], got[1])
                node.status = 'integral'
                node.sched, node.mach = got
                node.w = wsum(inst, got[0], w)
                node.sched_cmax = max(got[0][i] + inst['p'][i]
                                      for i in range(n))
                leaves.append(node)
                continue

        picked = _choose_branch(lp, z, node.F, inst, h, est, q)
        if picked is None:
            node.status = 'open'
            stats['holes'] += 1
            leaves.append(node)
            continue
        i, mid, why = picked
        times = domains[i]
        node.kind = 'split'
        node.i = i
        node.mid = mid
        lo = RelaxNode('leaf', _child_F(node.F, i, times, mid, 'lo'),
                       h, node.depth + 1)
        hi = RelaxNode('leaf', _child_F(node.F, i, times, mid, 'hi'),
                       h, node.depth + 1)
        node.lo, node.hi = lo, hi

        for ch in (lo, hi):
            r2, b2 = _solve_obj(lp, c, ch.F)
            stats['nodes'] += 1
            stats['lp'] += 1
            if r2.status == 2:
                ch.status = 'infeasible'
                cert, ok = _certify_infeasible(inst, h, ch.F,
                                               est, q, elig_aware)
                ch.farkas = cert
                stats['farkas_checks'] += 1
                if not ok:
                    stats['farkas_fail'] += 1
                    stats['holes'] += 1
                leaves.append(ch)
            elif r2.status != 0:
                ch.status = 'open'
                ch.lb = 0.0
                stats['holes'] += 1
                leaves.append(ch)
            else:
                ch.res_fun = float(r2.fun)
                ch.lb = float(r2.fun)
                ch.z = np.asarray(r2.x, dtype=float)
                if collect_witness:
                    active = _active_from_bounds(b2)
                    wit = _make_witness(lp, c, r2, active)
                    ch.witness = wit
                    if dual_audit:
                        stats['dual_checks'] += 1
                        if not wit.audit(lp, c):
                            stats['dual_fail'] += 1
                counter += 1
                heapq.heappush(heap, (ch.lb, counter, ch))

    b = min_open_lb()
    if not np.isfinite(b):
        b = best_w
    stats['nodes'] = max(stats['nodes'], 1)
    stats['open'] = len(heap)
    stats['leaves'] = len(leaves) + len(heap)
    stats['b'] = float(b)
    stats['a'] = float(best_w)
    stats['best_cmax'] = best_cmax
    stats['exact'] = bool(np.isfinite(best_w) and
                          (best_w - b < 1 - TOL or abs(best_w - b) < TOL))
    stats['eps_ok'] = bool(np.isfinite(best_w) and
                           (best_w <= (1 + eps) * b + TOL or
                            stats['exact']))
    stats['reason'] = stop_reason or ('exact' if stats['exact'] else 'open')
    stats['t'] = round(time.time() - t0, 4)
    stats['tree'] = root if collect_tree else None
    stats['_best_sched'] = best_sched
    return stats


# --------------------------------------------------------------- Pareto layer
def pareto_front(inst, U, primary_schedule, primary_machine, primary_proof,
                 deltas=(0, 1, 2, 4, 8), w=None, nodecap=256, eps=0.0,
                 collect_tree=False, collect_witness=False):
    """Compute the certified (Cmax, W) frontier over the given slacks."""
    if w is None:
        w = weights(inst, 'unit')
    points = []
    incumbent = (list(primary_schedule), list(primary_machine))
    current_w = wsum(inst, primary_schedule, w)
    for D in sorted(set(int(x) for x in deltas)):
        h = U + D
        bb = bb_secondary(inst, h, w=w, incumbent=incumbent,
                          nodecap=nodecap, eps=eps,
                          collect_tree=collect_tree,
                          collect_witness=collect_witness)
        sched = bb.get('_best_sched')
        if sched is not None and bb['a'] < current_w - 1e-9:
            incumbent = sched
            current_w = bb['a']
        points.append(dict(
            delta=D, h=h, b=bb['b'], a=bb['a'],
            exact=bb['exact'], eps_ok=bb['eps_ok'],
            nodes=bb['nodes'], lp=bb['lp'], open=bb['open'],
            dual_checks=bb.get('dual_checks', 0),
            dual_fail=bb.get('dual_fail', 0),
            farkas_checks=bb.get('farkas_checks', 0),
            farkas_fail=bb.get('farkas_fail', 0),
            holes=bb.get('holes', 0),
            root=bb.get('root'), best_cmax=bb.get('best_cmax'),
            t=bb.get('t', 0.0), reason=bb.get('reason', ''),
            primary_schedule=list(primary_schedule),
            tree=bb.get('tree') if collect_tree else None,
            schedule=sched,
            w=w,
        ))
    keep = []
    for p in points:
        cp = p['best_cmax'] if p['best_cmax'] is not None else p['h']
        dom = False
        for q in points:
            if q is p:
                continue
            cq = q['best_cmax'] if q['best_cmax'] is not None else q['h']
            if (cq <= cp and q['a'] <= p['a'] + 1e-9 and
                    q['b'] >= p['b'] - 1e-9 and
                    (cq < cp - 1e-9 or q['a'] < p['a'] - 1e-9)):
                dom = True
                break
        if not dom:
            keep.append(p)
    return points, keep


# ------------------------------------------------------------------ auditing
def audit_relax_tree(root, inst, h, w, b=None, a=None, sched=None,
                     machine=None, tol=1e-5, max_errors=12):
    """Replay a relaxation tree without trusting any stored statistic.

    Returns (ok, stats, errors).  The audit checks the split partition, every
    leaf dual/Farkas certificate, every integral schedule, and the global
    lower/upper bounds.
    """
    n = inst['n']
    elig_aware = _elig_aware(inst)
    est, q = heads_tails(inst, 0, [0] * n)
    lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig_aware)
    c = _objective(lp, w)
    stats = dict(depth=0, splits=0, leaves=0, infeasible=0, integral=0,
                 open=0, closed=0, dual=0, farkas=0, schedules=0)
    errors = []

    def err(msg):
        if len(errors) < max_errors:
            errors.append(msg)

    leaf_lbs = []
    best_integral = float('inf')

    def leaf_status(nd):
        return 'open' if nd.status == 'leaf' else nd.status

    def rec(nd, depth):
        nonlocal best_integral
        stats['depth'] = max(stats['depth'], depth)
        if nd.depth != depth:
            err('depth mismatch: stored %s actual %s' % (nd.depth, depth))
        if nd.kind == 'split':
            stats['splits'] += 1
            times = _domain_times_cached(inst, h, nd.i, est, q)
            if nd.i is None or nd.mid is None:
                err('split without job/mid')
                return
            want_lo = frozenset(set(nd.F) |
                                {(nd.i, t) for t in times if t > nd.mid})
            want_hi = frozenset(set(nd.F) |
                                {(nd.i, t) for t in times if t <= nd.mid})
            if nd.lo is None or nd.hi is None:
                err('split without children')
                return
            if nd.lo.F != want_lo:
                err('lo child box mismatch at depth %d' % depth)
            if nd.hi.F != want_hi:
                err('hi child box mismatch at depth %d' % depth)
            if (nd.lo.F & nd.hi.F) != nd.F:
                err('children do not share exactly the parent box')
            if (nd.lo.F | nd.hi.F) != (want_lo | want_hi):
                err('children do not cover the split domain')
            rec(nd.lo, depth + 1)
            rec(nd.hi, depth + 1)
            return

        stats['leaves'] += 1
        st = leaf_status(nd)
        if st == 'infeasible':
            stats['infeasible'] += 1
            if nd.farkas is None:
                err('infeasible leaf without certificate')
                return
            try:
                lpF = SDLP(inst, h, est, q, use_dom=True,
                           elig_aware=elig_aware, forbid=nd.F)
                cert = nd.farkas
                if cert.get('kind') == 'lp_farkas':
                    ok = verify_lp_farkas(lpF, cert)
                else:
                    ok = verify(inst, h, cert, forbid=nd.F)
                stats['farkas'] += 1
                if not ok:
                    err('Farkas certificate failed at depth %d' % depth)
            except Exception as exc:
                err('Farkas audit exception: %s' % exc)
            return
        if st == 'integral':
            stats['integral'] += 1
            if nd.sched is None or nd.mach is None:
                err('integral leaf without schedule')
            else:
                cc = max(nd.sched[i] + inst['p'][i] for i in range(n))
                ww = wsum(inst, nd.sched, w)
                stats['schedules'] += 1
                if cc > h:
                    err('integral schedule exceeds horizon')
                if not check_schedule(inst, cc, nd.sched, nd.mach):
                    err('integral schedule fails replay')
                if abs(ww - nd.w) > tol:
                    err('integral W mismatch')
                if nd.lb is None or abs(nd.lb - ww) > tol:
                    err('integral LP bound not equal to W')
                best_integral = min(best_integral, ww)
            if nd.lb is not None:
                leaf_lbs.append(nd.lb)
        elif st == 'closed':
            stats['closed'] += 1
            if nd.lb is None:
                err('closed leaf without bound')
            else:
                leaf_lbs.append(nd.lb)
        else:
            stats['open'] += 1
            if nd.lb is None:
                err('open leaf without bound')
            else:
                leaf_lbs.append(nd.lb)
        if nd.status not in ('infeasible',):
            if nd.witness is not None:
                stats['dual'] += 1
                if not nd.witness.audit(lp, c):
                    err('dual witness failed at depth %d' % depth)
                if nd.lb is not None and \
                        abs(nd.witness.value - nd.lb) > 1e-4 * (1 + abs(nd.lb)):
                    err('dual value differs from leaf bound')
            else:
                res, _ = _solve_obj(lp, c, nd.F)
                if res.status != 0:
                    err('leaf LP replay status %s' % res.status)
                elif nd.lb is None or abs(float(res.fun) - nd.lb) > tol:
                    err('leaf LP replay bound mismatch')

    rec(root, 0)
    if not leaf_lbs:
        err('no finite leaf bounds')
    else:
        min_leaf = min(leaf_lbs)
        if b is not None:
            if b > min_leaf + tol:
                err('global lower bound exceeds a leaf bound')
            if any(leaf_status(nd) == 'open' for nd in _iter_leaves(root)):
                open_lbs = [nd.lb for nd in _iter_leaves(root)
                            if leaf_status(nd) == 'open' and nd.lb is not None]
                if open_lbs and abs(min(open_lbs) - b) > tol:
                    err('global bound is not the minimum open-leaf bound')
    if sched is not None:
        cc = max(sched[i] + inst['p'][i] for i in range(n))
        if cc > h or not check_schedule(inst, cc, sched, machine):
            err('incumbent schedule fails replay')
        if a is not None and abs(wsum(inst, sched, w) - a) > tol:
            err('incumbent objective mismatch')
        if a is not None and best_integral < a - tol:
            err('incumbent is not the best integral schedule')
    stats['ok'] = not errors
    return (not errors), stats, errors


def _iter_leaves(root):
    if root.kind == 'split':
        yield from _iter_leaves(root.lo)
        yield from _iter_leaves(root.hi)
    else:
        yield root


def audit_pareto(inst, U, primary_schedule, primary_machine, points,
                 primary_proof=None, tol=1e-5):
    """Audit a whole Pareto certificate.  Each point must carry its tree."""
    from icf import ICFCertificate
    primary_ok = None
    if primary_proof is not None:
        pc = ICFCertificate(inst, U, primary_schedule, primary_machine,
                            primary_proof)
        primary_ok = bool(pc.audit_rdf())
    point_ok = []
    for p in points:
        tree = p.get('tree')
        if tree is None:
            point_ok.append(None)
            continue
        ok, _, _ = audit_relax_tree(
            tree, inst, p['h'], p.get('w') or weights(inst, 'unit'),
            b=p.get('b'), a=p.get('a'),
            sched=p.get('schedule')[0] if p.get('schedule') else None,
            machine=p.get('schedule')[1] if p.get('schedule') else None,
            tol=tol)
        point_ok.append(bool(ok))
    return primary_ok, point_ok
