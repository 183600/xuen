"""v10.2 TRIAGE-ICF: budgeted adaptive tolerance search over ICF/PACE.

State:
    C = (L, U, s, m, pi, eps, rho, kappa)

where (L,U,s,m,pi) is the v9.0 ICF partial certificate, eps is the
current certified relative tolerance, rho is the regime tag
(P/A/K/X/B), and kappa = (k,g,delta) is the hardness profile:

    k      fractional support size of the root LP at h = L (or U-1)
    g      (U-L)/L, the current relative gap
    delta  p_max/L, the additive-granularity parameter

The outer algorithm is a *budgeted tolerance search*: the predicate
"certify at tolerance eps within probe budget B" is monotone in eps
(if it succeeds at eps it succeeds at every larger eps), so a binary
search over a geometric tolerance grid returns the smallest certified
eps attainable within B.  The inner certifier is PACE's P/A/X layer
(chip -> LP -> exact PACT); the K layer is used by the optional
core-restricted oracle.  The invariant and the certificate formats are
those of v9.0/v9.1; this module only changes which layer is asked and
with which tolerance.

The trusted kernel is unchanged: NO proofs come from pact_decide,
schedules are accepted only by check_schedule, and every returned row
is audited by PACECertificate/PartialCertificate.
"""
import sys
import time
import math

sys.path[:0] = ['exp/v9pa', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from pace import pace_bounds, run_pace
from core_icf import solve_root
from icf import cmax


def hardness_profile(inst, L, U):
    """Compute (k,g,delta) at the current bracket."""
    L = int(L)
    U = int(U)
    h = max(0, min(L, U - 1))
    try:
        status, lp, res, K = solve_root(inst, h)
    except Exception:
        status, K = 'unknown', frozenset()
    k = len(K) if status == 'fractional' else 0
    g = (U - L) / float(max(1, L))
    delta = max(inst['p']) / float(max(1, L))
    return dict(k=k, g=g, delta=delta, lp_status=status, h=h)


def tolerance_grid(g0, floor=1e-3, max_rungs=24):
    """Ascending geometric eps grid from 0 (exact) to g0."""
    g0 = max(float(g0), 0.0)
    if g0 <= 1e-9:
        return [0.0]
    # descending positive rungs g0, g0/2, ...
    desc = []
    e = g0
    while e > floor and len(desc) < max_rungs:
        desc.append(e)
        e *= 0.5
    grid = sorted(set([0.0] + desc))
    return grid


def _budgeted_eps(inst, known, name, idx, eps, budget, init):
    return run_pace(inst, known, name, idx, eps=eps, mode='approx',
                    max_probes=budget, init=init)


def run_triage(inst, known, name, idx, budget=2, init='poly',
               eps_floor=1e-3, max_rungs=24):
    """Run the budgeted tolerance search.

    budget is the number of *exact probes* allowed per tolerance test.
    The returned row is the tightest certified state found; if no test
    succeeds (should not happen because eps=g0 is a valid A-certificate),
    the last partial row is returned.
    """
    t0 = time.time()
    pre = pace_bounds(inst, eps=1e9, stop_at_approx=False)
    L0, U0 = pre.get('L'), pre.get('U')
    if L0 is None or U0 is None:
        return dict(name=name, idx=idx, known=known, ok=False,
                    certified=False, error='no-bounds', t=0.0)
    prof = hardness_profile(inst, L0, U0)
    grid = tolerance_grid(prof['g'], floor=eps_floor, max_rungs=max_rungs)
    lo, hi = 0, len(grid) - 1
    best = None
    last = None
    tests = 0
    work = 0
    trace = []
    while lo <= hi:
        mid = (lo + hi) // 2
        eps = grid[mid]
        r = _budgeted_eps(inst, known, name, idx, eps, budget, init)
        tests += 1
        work += int(r.get('probes', 0))
        last = r
        trace.append(dict(eps=eps, certified=bool(r.get('certified')),
                          stage=r.get('stage'), L=r.get('L'),
                          U=r.get('U'), probes=r.get('probes', 0)))
        if r.get('certified'):
            best = r
            hi = mid - 1
        else:
            lo = mid + 1
    if best is None:
        best = last
    if best is None:
        return dict(name=name, idx=idx, known=known, ok=False,
                    certified=False, error='no-result', t=0.0)
    best = dict(best)
    best['triage_profile'] = prof
    best['triage_grid'] = grid
    best['triage_tests'] = tests
    best['triage_work'] = work
    best['triage_trace'] = trace
    best['triage_t'] = round(time.time() - t0, 4)
    return best
