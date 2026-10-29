"""v10.1 WICF: work-invariant carrying frontier with primal repair.

State:

    (L, U, s, m, pi, Omega)

where (L,U,s,m,pi) is the v9.0 ICF partial certificate and Omega is a
work ledger.  The ledger records the work already spent on primal repair,
probes and splits.  The invariant is:

    I_W = I_ICF  and  Omega.spent <= Omega.budget.

The algorithm has two regimes:

  * complete: if the post-repair bracket is narrow, use the complete
    PACT oracle (no UNKNOWN, no frontier blow-up);
  * frontier: otherwise, use a budgeted live frontier with per-leaf
    escalation, so that an UNKNOWN is either retried with a larger
    budget or split.

The key move is primal-first: repair U before probing.  If repair reaches
OPT, the first upper probe at U-1 is a NO and the bracket closes in one
probe, independent of how far L was from OPT.
"""
import sys
import time

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from rdf import check_schedule
from icf import run_icf
from picf import run_picf
from core_icf import run_core_icf
from ubf import randomized_repair


def _initial(inst):
    from pact import PACT, pact_decide
    co = PACT(inst, pact_mode='complete', use_ga=False)
    lb, ub, s, m = co.initial_bounds()
    if ub is None:
        return None
    L, U = int(lb), int(ub)
    s, m = list(s), list(m)
    proof = co._ensure_lb_proof(L)
    if proof is None:
        r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            proof = r['proof']
    if proof is None:
        return None
    return (L, U, s, m, proof, getattr(co, 'pin_lp', 0))


def run_wicf(inst, known, name, idx, initial=None, seed=0,
             repair_iters=400, repair_time=1.0, repair_stall=120,
             policy='upper-first', gap_complete=4, B0=1, Bmax=8,
             use_core=False, max_probes=64, work_budget=None,
             frontier_policy='adaptive'):
    """Run WICF and return a benchmark row.

    work_budget, when set, caps the number of probe/split units; the
    repair budget is capped at half of it.  The returned state is still
    a valid partial certificate when the cap is reached.
    """
    t0 = time.time()
    pin_lp = 0
    if initial is None:
        ini = _initial(inst)
        if ini is None:
            return dict(name=name, idx=idx, known=known, alg='wicf',
                        ok=False, error='no-initial', t=0.0)
        L, U, s, m, proof, pin_lp = ini
    else:
        L, U, s, m, proof = initial
        L, U = int(L), int(U)
        s, m = list(s), list(m)

    ub0 = int(U)
    lb0 = int(L)
    rep = dict(U=U, iters=0, improved=0, t=0.0)
    repair_used = False
    if U - L > 1:
        ri = int(repair_iters)
        if work_budget is not None:
            ri = min(ri, max(1, int(work_budget) // 2))
        rep = randomized_repair(inst, U, s, m, iters=ri, seed=seed,
                                target=L, time_cap=repair_time,
                                stall=repair_stall)
        if rep['U'] < U and check_schedule(inst, rep['U'],
                                            rep['schedule'],
                                            rep['machine']):
            U = rep['U']
            s, m = rep['schedule'], rep['machine']
            repair_used = True

    gap = U - L
    if policy == 'portfolio':
        if ub0 - U >= 2:
            policy = 'upper-first'
            use_core = False
        else:
            policy = 'lower-first'
            use_core = True
    if policy == 'auto':
        # Repair is only worth an upper-first close when it actually moved
        # the upper bound close to the lower bound.  Otherwise the LP pin
        # lower bound is the better first probe (v9.0 lower-first).
        policy = ('upper-first' if ub0 - U >= 2 else 'lower-first')
    regime = 'complete' if gap <= gap_complete else 'frontier'
    if work_budget is not None:
        max_probes = min(int(max_probes), max(0, int(work_budget)))

    if regime == 'complete':
        if use_core:
            r = run_core_icf(inst, known, name, idx, policy=policy,
                             max_probes=max_probes,
                             initial=(L, U, s, m, proof))
        else:
            r = run_icf(inst, known, name, idx, policy=policy,
                        max_probes=max_probes,
                        initial=(L, U, s, m, proof))
    else:
        r = run_picf(inst, known, name, idx, B0=B0, Bmax=Bmax,
                     policy=frontier_policy, max_probes=max_probes,
                     initial=(L, U, s, m, proof))

    probes = int(r.get('probes', r.get('queries', 0)))
    splits = int(r.get('splits', 0))
    search_lp = int(r.get('pact_lp', r.get('lp', 0)))
    cert_lp = int(r.get('pact_cert_lp', r.get('cert_lp', 0)))
    root_lp = int(r.get('root_lp', 0))
    total_lp = int(r.get('total_lp', search_lp + cert_lp + root_lp))
    r['alg'] = 'wicf'
    r['regime'] = regime
    r['use_core'] = bool(use_core)
    r['policy'] = policy if regime == 'complete' else frontier_policy
    r['lb0'] = lb0
    r['ub0'] = ub0
    r['ub_after_repair'] = U
    r['repair_used'] = repair_used
    r['repair_iters'] = int(rep.get('iters', 0))
    r['repair_improved'] = int(rep.get('improved', 0))
    r['repair_t'] = float(rep.get('t', 0.0))
    r['wicf_probes'] = probes
    r['wicf_splits'] = splits
    r['wicf_lp'] = total_lp
    r['pin_lp'] = pin_lp
    r['work_repair'] = r['repair_iters']
    r['work_probes'] = probes
    r['work_splits'] = splits
    r['work_total'] = r['work_repair'] + probes + splits
    r['work_budget'] = work_budget
    r['t'] = round(time.time() - t0, 4)
    r['ok'] = bool(r.get('ok')) and repair_used is not None
    return r
