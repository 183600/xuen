"""ADA: Anytime Dual Ascent for the start-time LP Farkas certificate.

Dual (Farkas) certificate for infeasibility of the start-time LP at horizon h:
  beta_t >= 0 (time-cut price), gamma_e >= 0 (precedence-cut price)
  alpha_i = min_{t in W_i} [ B_i(t) + t * sigma_i ],
    B_i(t) = sum_{u=t}^{t+p_i-1} beta_u,
    sigma_i = sum_{j in succ(i)} gamma_ij - sum_{k in pred(i)} gamma_ki
  D(beta,gamma) = sum_i alpha_i + sum_{i->j} p_i gamma_ij - m sum_t beta_t.
D > 0  =>  no nonpreemptive schedule with makespan <= h.
D is concave and positively homogeneous; we ascend on the L1 simplex.
"""
import numpy as np


def build_windows(inst, h, est, q):
    n, p = inst['n'], inst['p']
    lo = [est[i] for i in range(n)]
    hi = [h - q[i] - p[i] for i in range(n)]
    return lo, hi


def evaluate(inst, h, est, q, beta, gamma):
    n, m, p = inst['n'], inst['m'], inst['p']
    pred, succ = inst['pred'], inst['succ']
    T = len(beta)
    # prefix sums
    pref = np.concatenate([[0.0], np.cumsum(beta)])
    lo, hi = build_windows(inst, h, est, q)
    sig = np.zeros(n)
    for i in range(n):
        sig[i] = sum(gamma[(i, j)] for j in succ[i]) - sum(gamma[(k, i)] for k in pred[i])
    alpha = np.empty(n)
    tstar = np.empty(n, dtype=int)
    for i in range(n):
        ts = np.arange(lo[i], hi[i] + 1)
        vals = pref[ts + p[i]] - pref[ts] + ts * sig[i]
        k = int(np.argmin(vals))
        alpha[i] = vals[k]
        tstar[i] = ts[k]
    obj = alpha.sum() + sum(p[i] * gamma[(i, j)] for i in range(n) for j in succ[i]) - m * beta.sum()
    return obj, alpha, tstar


def ada(inst, h, est=None, q=None, steps=2000, seed=0, eta0=None, verbose=False):
    from po import heads_tails
    n, m, p = inst['n'], inst['m'], inst['p']
    pred, succ = inst['pred'], inst['succ']
    if est is None or q is None:
        est, q = heads_tails(inst, 0, [0] * n)
    lo, hi = build_windows(inst, h, est, q)
    if any(hi[i] < lo[i] for i in range(n)):
        return {'D': 1.0, 'beta': None, 'gamma': None, 'steps': 0, 'reason': 'empty-window'}
    T = h
    beta = np.ones(T) / T
    gamma = {(i, j): 0.0 for i in range(n) for j in succ[i]}
    if eta0 is None:
        eta0 = 1.0 / max(1.0, T)
    best = -1e18
    best_state = None
    rng = np.random.default_rng(seed)
    D = 0.0
    for k in range(steps):
        D, alpha, tstar = evaluate(inst, h, est, q, beta, gamma)
        if D > best:
            best = D
            best_state = (beta.copy(), gamma.copy())
        if D > 1e-7:
            return {'D': D, 'beta': beta.copy(), 'gamma': gamma.copy(), 'steps': k + 1, 'reason': 'certified'}
        # subgradient
        gb = -m * np.ones(T)
        for i in range(n):
            ts = tstar[i]
            gb[ts:ts + p[i]] += 1.0
        gg = {}
        for i in range(n):
            for j in succ[i]:
                gg[(i, j)] = p[i] - tstar[i] + tstar[j]
        eta = eta0 / np.sqrt(1.0 + k / 10.0)
        beta = np.maximum(0.0, beta + eta * gb)
        for e, g in gg.items():
            gamma[e] = max(0.0, gamma[e] + eta * g)
        # normalize to L1 = 1
        s = beta.sum() + sum(gamma.values())
        if s > 0:
            beta /= s
            for e in gamma:
                gamma[e] /= s
        if verbose and k % 100 == 0:
            print(k, D, beta.sum(), sum(gamma.values()))
    D, alpha, tstar = evaluate(inst, h, est, q, beta, gamma)
    if D > best:
        best = D
        best_state = (beta.copy(), gamma.copy())
    return {'D': best, 'beta': best_state[0], 'gamma': best_state[1], 'steps': steps, 'reason': 'budget'}
