"""Round-2 analysis B: retry/abstain as an optimal-stopping ('business') decision.

A grasp is either good (rest-of-task success q_g) or bad (q_b).  A noisy
detector emits a score; retrying costs c_r seconds of the episode budget,
switching to a non-prehensile primitive costs c_p and succeeds w.p. q_p.

We compare:
  baseline  : never intervene
  fixed     : round-1 heuristic (score<tau with FPR=2%, max 3 retries, then primitive)
  optimal   : dynamic-programming value of the 'retry option' (GOV)

Everything is a *model simulation* with assumed parameters; the artifact
pre-registers the experiments that must estimate them from official data.
"""
import json, math, os
import numpy as np
from scipy.stats import norm

rng = np.random.default_rng(20261117)

Q_G, Q_B = 0.80, 0.05      # rest-of-task success | good / bad grasp
PI = 0.70                  # prior P(good grasp) on a fresh attempt
C_R, C_P = 6.0, 10.0       # seconds
T_MIN = 4.0                # minimum remaining time to be able to finish
MAX_RETRY = 3
F_PRIM = 0.35              # fraction of episodes where a non-prehensile primitive applies
BMAX = 80.0
DR = 0.5
R_GRID = np.arange(0.0, BMAX + DR, DR)
N_RETRY = MAX_RETRY + 1


def posterior(score, d):
    """P(good | score) for equal-variance Gaussian score model."""
    lg = norm.logpdf(score, d / 2, 1.0) + math.log(PI)
    lb = norm.logpdf(score, -d / 2, 1.0) + math.log(1 - PI)
    m = max(lg, lb)
    return math.exp(lg - m) / (math.exp(lg - m) + math.exp(lb - m))


# quadrature nodes for the score mixture
Z = np.linspace(-4, 4, 321)


def score_mixture(d):
    """nodes and weights of the marginal score distribution"""
    sg = Z + d / 2
    sb = Z - d / 2
    wg = PI * norm.pdf(Z) 
    wb = (1 - PI) * norm.pdf(Z)
    return np.concatenate([sg, sb]), np.concatenate([wg, wb]) / 2.0


def build_value(d, prim_feasible, max_retry=MAX_RETRY):
    """W[n, i] = expected optimal value at a fresh decision with R=R_GRID[i]."""
    nodes, weights = score_mixture(d)
    post = np.array([posterior(s, d) for s in nodes])
    cont = post * Q_G + (1 - post) * Q_B          # value of continuing
    nR = len(R_GRID)
    W = np.zeros((max_retry + 1, nR))
    for n in range(max_retry, -1, -1):
        for i, R in enumerate(R_GRID):
            vals = cont.copy()
            if R < T_MIN:
                vals[:] = 0.0
            # switch to primitive
            if prim_feasible and R >= C_P + T_MIN:
                vals = np.maximum(vals, Q_P)
            # retry
            if n < max_retry and R >= C_R + T_MIN:
                vretry = np.interp(R - C_R, R_GRID, W[n + 1])
                vals = np.maximum(vals, vretry)
            W[n, i] = float((vals * weights).sum())
    return W


Q_P = 0.25


def action_values(p, R, n, d, W, prim_feasible, max_retry=MAX_RETRY):
    vcont = p * Q_G + (1 - p) * Q_B if R >= T_MIN else 0.0
    vret = -1.0
    if n < max_retry and R >= C_R + T_MIN:
        vret = float(np.interp(R - C_R, R_GRID, W[n + 1]))
    vsw = Q_P if (prim_feasible and R >= C_P + T_MIN) else -1.0
    return {'continue': vcont, 'retry': vret, 'switch': vsw}


def simulate(policy, d, budget, prim_feasible, n_ep=200_000, max_retry=MAX_RETRY,
             fixed_tau=None):
    W = build_value(d, prim_feasible, max_retry) if policy == 'optimal' else None
    if fixed_tau is None:
        fixed_tau = d / 2 + norm.ppf(0.02)      # FPR = 2%
    succ = 0
    retries_used = 0
    for _ in range(n_ep):
        R = budget
        n = 0
        good = rng.random() < PI
        score = rng.normal(d / 2 if good else -d / 2, 1.0)
        while True:
            p = posterior(score, d)
            if policy == 'baseline':
                act = 'continue'
            elif policy == 'fixed':
                if score < fixed_tau and n < max_retry and R >= C_R + T_MIN:
                    act = 'retry'
                elif n >= max_retry and prim_feasible and R >= C_P + T_MIN:
                    act = 'switch'
                else:
                    act = 'continue'
            else:  # optimal (GOV)
                vs = action_values(p, R, n, d, W, prim_feasible, max_retry)
                act = max(vs, key=vs.get)
            if act == 'continue':
                succ += int(rng.random() < (Q_G if good else Q_B))
                break
            if act == 'switch':
                retries_used += 1
                succ += int(rng.random() < Q_P)
                break
            # retry
            retries_used += 1
            R -= C_R
            n += 1
            good = rng.random() < PI
            score = rng.normal(d / 2 if good else -d / 2, 1.0)
    return succ / n_ep, retries_used / n_ep


def run():
    out = {}
    ds = {0.0: 0.50, 1.0: 0.760, 1.5: 0.856, 2.0: 0.921, 2.5: 0.961, 4.0: 0.998}
    for d, auc in ds.items():
        rows = {}
        for budget in (30.0, 45.0, 60.0, 80.0):
            acc = {}
            for pol in ('baseline', 'fixed', 'optimal'):
                s_feas, r_feas = simulate(pol, d, budget, True, n_ep=60_000)
                s_no, r_no = simulate(pol, d, budget, False, n_ep=60_000)
                acc[pol] = {
                    'success': round(F_PRIM * s_feas + (1 - F_PRIM) * s_no, 4),
                    'retries_per_ep': round(F_PRIM * r_feas + (1 - F_PRIM) * r_no, 3),
                }
            rows[f'budget_{int(budget)}s'] = acc
        out[f'd={d} (AUC~{auc})'] = rows
    # value of information: perfect detector vs no detector, both with optimal policy
    voi = {}
    for budget in (30.0, 45.0, 60.0):
        s_perfect, _ = simulate('optimal', 8.0, budget, True, n_ep=60_000)  # near-perfect
        s_none, _ = simulate('optimal', 0.0, budget, True, n_ep=60_000)    # useless signal
        s_base, _ = simulate('baseline', 0.0, budget, True, n_ep=60_000)
        voi[f'budget_{int(budget)}s'] = {
            'baseline': round(F_PRIM * s_base + (1 - F_PRIM) * s_base, 4),
            'optimal_no_info': round(s_none, 4),
            'optimal_perfect_info': round(s_perfect, 4),
            'value_of_information_pts': round(s_perfect - s_none, 4),
        }
    out['value_of_information'] = voi
    out['assumptions'] = {'q_good': Q_G, 'q_bad': Q_B, 'prior_good': PI,
                          'retry_cost_s': C_R, 'primitive_cost_s': C_P,
                          'primitive_success': Q_P, 'primitive_feasible_frac': F_PRIM,
                          'max_retries': MAX_RETRY, 't_min_s': T_MIN}
    here = os.path.dirname(os.path.abspath(__file__))
    json.dump(out, open(os.path.join(here, 'option_value_results.json'), 'w'),
              ensure_ascii=False, indent=2)

    print('=== fixed heuristic vs optimal stopping (GOV) ===')
    for dk, rows in out.items():
        if not dk.startswith('d='):
            continue
        print(dk)
        for bk, acc in rows.items():
            print('  %-12s base %.3f  fixed %.3f  optimal %.3f  (retries %.2f/%.2f)' %
                  (bk, acc['baseline']['success'], acc['fixed']['success'],
                   acc['optimal']['success'], acc['fixed']['retries_per_ep'],
                   acc['optimal']['retries_per_ep']))
    print('=== value of information ===')
    for bk, v in voi.items():
        print(' ', bk, v)


if __name__ == '__main__':
    run()
