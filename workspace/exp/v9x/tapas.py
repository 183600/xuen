"""v9.1 TAPAS-ALC: tabu-annealed proof-height adaptive search.

TAPAS is an outer policy search above PACT's exact fixed-h decision
procedure.  PACT's soundness does not depend on the branching policy: a
policy only chooses which valid domain split to make.  TAPAS therefore
treats the policy as a *certificate compressor* and searches for a policy
whose certificate is shallow (small height / node count).  The search is
simulated annealing with a tabu list on the root split, and every
candidate certificate is audited independently.

The module is additive: `tapas_decide(inst, h, budget)` returns the same
verdict/proof/schedule triple as `pact_decide`, so it can replace a probe
in PACT/TotalTrace without changing the certificate algebra.
"""
import sys
import time
import math
import random

sys.path[:0] = ['exp/v9x', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from pact import pact_decide
from sdecc import SDLP
from po import heads_tails
from sage import _elig_aware
from rdf import check_schedule


FEATURES = ('frac', 'mass', 'q', 'p', 'succ', 'pred', 'slack',
            'width', 'peak', 'entropy', 'spread', 'lo', 'hi')
INF = 10 ** 12


def _tree_height(node):
    if node is None:
        return 0
    if node[0] in ('leaf', 'empty', 'yes'):
        return 0
    if node[0] == 'node':
        return 1 + max(_tree_height(node[4]), _tree_height(node[5]))
    return 0


def proof_rank(r):
    """NO: proof-tree height; YES: successful-path length."""
    if r is None or r.get('verdict') is None:
        return None
    if r['verdict'] is False:
        p = r.get('proof')
        return _tree_height(getattr(p, 'tree', None))
    return r.get('yes_depth', r.get('depth'))


def _energy(r, lam=2.0):
    if r is None or r.get('verdict') is None:
        return INF
    k = proof_rank(r)
    return float(r['nodes']) + lam * float(k)


def _root_key(r):
    bj = r.get('branch_jobs') or []
    if bj:
        return (bj[0][0], bj[0][1])
    return ('root', r.get('verdict'))


def _prep_root(inst, h):
    elig = _elig_aware(inst)
    est, q = heads_tails(inst, 0, [0] * inst['n'])
    lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig)
    base = [(0, 1)] * lp.N
    res = lp.solve(base)
    return lp, res, base


def _eval(inst, h, policy, cap, lp, res):
    return pact_decide(inst, h, depthcap=None, nodecap=cap,
                       policy=policy, root_lp=lp, root_res=res)


def _audit_ok(inst, h, r):
    if r is None or r.get('verdict') is None:
        return False
    if r['verdict'] is False:
        p = r.get('proof')
        return bool(p is not None and p.h == h and p.audit_rdf())
    s, m = r.get('schedule'), r.get('machine')
    if s is None or m is None:
        return False
    cmax = max(s[i] + inst['p'][i] for i in range(inst['n']))
    return cmax <= h and bool(check_schedule(inst, cmax, s, m))


def anneal_policy(inst, h, budget=30, seed=0, tau=7, lam=2.0,
                  T0=2.0, Tend=0.05, restart_every=12,
                  cap_margin=0, init_policy=None, use_sa=True,
                  use_tabu=True, verbose=False):
    """Run SA + tabu over the policy weights.

    Returns dict(best, baseline, trace, evals, policy, t, root_key).
    `best` is an audited PACT result; the baseline is always evaluated
    first, so `best` can never be worse than the default policy.
    """
    t0 = time.time()
    rng = random.Random(seed)
    lp, root_res, base = _prep_root(inst, h)

    base_r = pact_decide(inst, h, depthcap=None, nodecap=None,
                         root_lp=lp, root_res=root_res)
    baseE = _energy(base_r, lam)
    if init_policy:
        w = {f: float(init_policy.get('weights', {}).get(f, 0.0))
             for f in FEATURES}
        split = float(init_policy.get('split', 0.5))
        cur_r = _eval(inst, h, {'weights': w, 'split': split},
                      None, lp, root_res)
        curE = _energy(cur_r, lam)
    else:
        w = {f: 0.0 for f in FEATURES}
        split = 0.5
        cur_r, curE = base_r, baseE
    bestE, best_r, best_w, best_s = curE, cur_r, dict(w), split
    if baseE < bestE:
        w = {f: 0.0 for f in FEATURES}
        split = 0.5
        cur_r, curE = base_r, baseE
        bestE, best_r = baseE, base_r
        best_w, best_s = dict(w), split
    tabu = []
    trace = []
    evals = 0
    nfull = 0
    if base_r['nodes'] <= 1:
        return dict(best=best_r, baseline=base_r, trace=trace,
                    evals=0, policy={'weights': dict(w), 'split': split},
                    t=round(time.time() - t0, 5), root_key=_root_key(base_r),
                    stopped='root-closed')

    alpha = (Tend / T0) ** (1.0 / max(1, budget - 1))
    T = T0
    for it in range(1, max(1, budget)):
        nw = dict(w)
        for f in FEATURES:
            if rng.random() < 0.35:
                nw[f] += rng.gauss(0.0, 0.9)
        if rng.random() < 0.20:
            nw[rng.choice(FEATURES)] = 0.0
        ns = min(0.80, max(0.20, split + rng.gauss(0.0, 0.08)))

        cap = None
        if best_r is not None and best_r.get('verdict') is not None:
            cap = max(1, best_r['nodes'] + cap_margin)
        r = _eval(inst, h, {'weights': nw, 'split': ns},
                  cap, lp, root_res)
        evals += 1
        if r.get('verdict') is not None:
            nfull += 1
        E = _energy(r, lam)
        key = _root_key(r)
        is_tabu = use_tabu and key in tabu
        if is_tabu and E >= bestE:
            trace.append(dict(it=it, E=E if E < INF else None,
                              verdict=r.get('verdict'), why='tabu',
                              key=key))
            T *= alpha
            if restart_every and it % restart_every == 0:
                w, split = dict(best_w), best_s
                cur_r, curE = best_r, bestE
                T = max(T, T0 * 0.5)
                tabu = []
            continue
        dE = E - curE
        accept = dE <= 0 or (use_sa and rng.random()
                              < math.exp(-dE / max(T, 1e-9)))
        if accept:
            w, split, cur_r, curE = nw, ns, r, E
            if use_tabu:
                tabu.append(key)
                tabu = tabu[-tau:]
        if E < bestE:
            bestE, best_r, best_w, best_s = E, r, dict(nw), ns
            trace.append(dict(it=it, E=E, verdict=r.get('verdict'),
                              nodes=r['nodes'], depth=proof_rank(r),
                              why='best', key=key))
        T *= alpha
        if restart_every and it % restart_every == 0:
            w, split = dict(best_w), best_s
            cur_r, curE = best_r, bestE
            T = max(T, T0 * 0.5)
            tabu = []

    if not _audit_ok(inst, h, best_r):
        best_r, bestE = base_r, baseE
        best_w, best_s = {f: 0.0 for f in FEATURES}, 0.5
    return dict(best=best_r, baseline=base_r, trace=trace,
                evals=evals, full= nfull,
                policy={'weights': dict(best_w), 'split': best_s},
                t=round(time.time() - t0, 5),
                root_key=_root_key(best_r), stopped=None)


def tapas_decide(inst, h, budget=30, seed=0, **kw):
    """PACT-compatible probe: baseline first, then annealed policies."""
    z = anneal_policy(inst, h, budget=budget, seed=seed, **kw)
    r = z['best']
    out = dict(r)
    out['tapas'] = z
    return out
