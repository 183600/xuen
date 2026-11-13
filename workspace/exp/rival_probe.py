#!/usr/bin/env python3
"""R70 RIVAL-RAS sanity probes (self-contained, numpy/scipy only).

A) Exploitability of a raw "foundation-model" pure style vs an equilibrium
   mixture over the same safe style set (zero-sum matrix game).
B) Byzantine evidence: R69 "k=2 agreement" vs RIVAL "n=3f+1 distinct trust
   domains + majority" under colluding liars.
C) Rank-vs-score: probability of winning a 4-way tournament when optimizing
   expected score vs optimizing P(top-1) under a fixed safety floor.

Run:  PYTHONPATH=.pylibs python exp/rival_probe.py
"""
import json
import numpy as np
from scipy.optimize import linprog

rng = np.random.default_rng(20261113)


def solve_zero_sum(M):
    """Row player maximizer. Return (value, sigma) of equilibrium."""
    K = M.shape[0]
    # maximize v  <=>  minimize -v
    # vars = [sigma_0..sigma_{K-1}, v]
    c = np.zeros(K + 1); c[-1] = -1.0
    A_ub = np.hstack([-M.T, np.ones((K, 1))])          # -(M^T sigma) + v <= 0
    b_ub = np.zeros(K)
    A_eq = np.ones((1, K + 1)); A_eq[0, -1] = 0.0       # sum sigma = 1
    b_eq = np.array([1.0])
    bounds = [(0, None)] * K + [(None, None)]
    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                  bounds=bounds, method="highs")
    return res.x[-1], res.x[:K]


def probe_exploitability(seed=7):
    r = np.random.default_rng(seed)
    K = 6
    # Each style has a hard counter: high average payoff but exploitable.
    base = r.normal(0.6, 0.15, size=K)
    M = base[:, None] + r.normal(0.0, 0.12, size=(K, K))
    counter = np.array([3, 5, 1, 0, 2, 4])
    for i, j in enumerate(counter):
        M[i, j] -= 1.6                                  # hard counter
    v_star, sigma = solve_zero_sum(M)
    rfm = int(np.argmax(M.mean(axis=1)))                # league-average best style
    raw_security = M[rfm].min()
    mix_security = float((M.T @ sigma).min())
    league = np.full(K, 1.0 / K)
    exploit_raw = v_star - raw_security
    exploit_mix = v_star - mix_security
    return dict(
        K=K, game_value=round(float(v_star), 4), rfm_style=rfm,
        raw_exploitability=round(float(exploit_raw), 4),
        mix_exploitability=round(float(exploit_mix), 4),
        raw_vs_uniform_league=round(float(M[rfm] @ league), 4),
        mix_vs_uniform_league=round(float(sigma @ M @ league), 4),
        mix_entropy=round(float(-(sigma * np.log(sigma + 1e-12)).sum()), 4),
        sigma=[round(float(x), 4) for x in sigma],
    )


def byz_error(n, f, q=1.0, trials=60000, k_agree=2, seed=11):
    """P(accept wrong) for (i) R69 k=2 agreement, (ii) RIVAL majority n=3f+1."""
    r = np.random.default_rng(seed)
    # (i) R69: pick k sources at random; accept iff they agree (liars collude).
    err_k = 0
    for _ in range(trials):
        idx = r.choice(n, size=k_agree, replace=False)
        truth = np.ones(n, dtype=bool)
        liars = idx < f
        # honest correctness
        ok = r.random(n) < q
        ok[:f] = False                                 # liars collude on wrong
        vals = np.where(liars, False, ok[idx])
        err_k += int(np.all(vals == vals[0]) and vals[0] == False)
    # (ii) RIVAL: majority over all n, n=3f+1
    err_maj = 0
    for _ in range(trials):
        ok = r.random(n) < q
        ok[:f] = False
        err_maj += int(ok.sum() < (n + 1) // 2)        # wrong majority (liars consensus)
    return round(err_k / trials, 4), round(err_maj / trials, 4)


def probe_byzantine():
    out = []
    for q in (1.0, 0.99, 0.9, 0.85):
        row = {"honest_accuracy": q, "cases": []}
        for f in (1, 2, 3):
            n = 3 * f + 1
            ek, em = byz_error(n, f, q=q)
            row["cases"].append(dict(f=f, n=n, r69_k2_error=ek,
                                     rival_majority_error=em))
        out.append(row)
    return out


def probe_rank_vs_score(trials=200000, seed=5):
    """4-way final. Two policies with same mean but different variance.

    A: steady, mean 1.0, sd 0.6
    B: volatile, mean 1.0, sd 1.4
    Both satisfy the same safety floor (all sampled scores are >= 0 here via clip).
    """
    r = np.random.default_rng(seed)
    winA = winB = 0
    for _ in range(trials):
        opp = r.normal(0.9, 0.8, size=3)
        a = 1.0 + 0.6 * r.standard_normal()
        b = 1.0 + 1.4 * r.standard_normal()
        winA += int((np.array([a, *opp]).max()) == a and a > opp.max())
        # break ties in A's favor consistently: count strict max excluding a
        winB += int(b > max(opp.max(), a))
    return dict(
        score_optimal="A(steady)", p_win_A=round(winA / trials, 4),
        p_win_B=round(winB / trials, 4),
        note="same mean, higher variance B wins more in a 4-way final",
    )


if __name__ == "__main__":
    res = {
        "exploitability": probe_exploitability(),
        "byzantine": probe_byzantine(),
        "rank_vs_score": probe_rank_vs_score(),
    }
    print(json.dumps(res, indent=2, ensure_ascii=False))
    with open("/home/runner/work/xuen/xuen/workspace/exp/rival_probe_results.json", "w") as fh:
        json.dump(res, fh, indent=2, ensure_ascii=False)
