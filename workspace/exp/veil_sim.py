"""Synthetic mechanism check for VEIL (round 66): privacy-constrained evidence.

NOT benchmark evidence. Isolates three questions:

  Q1  When fault-relevant directions and sensitive (privacy) directions overlap,
      what does the minimum-leakage / attribution-accuracy frontier look like?
  Q2  Under a Gaussian DP release of the grasp-sufficient statistic, how much
      per-release privacy budget is needed to keep fault attribution usable?
  Q3  Does "privacy protection -> weaker evidence -> probe more -> leak more"
      admit a budget-feasible stopping rule, or does it force a fallback?

Declared generative model (NOT fitted): linear-Gaussian evidence
    rho = S_F theta_h + A_S psi + n,   n ~ N(0, sigma_n^2 I)
with theta_h a fault amplitude in the fault subspace U_F = col(S_F), psi the
sensitive attribute in U_S = col(A_S). The released statistic is a projection
P rho (plus Gaussian DP noise in Q2). Leakage is the Gaussian mutual
information I(psi; P rho) = 0.5 sum_i log(1 + sigma_i^2 / sigma_n^2), where
sigma_i are singular values of P A_S / sigma_n. Accuracy is Monte-Carlo
nearest-signature classification. Everything is synthetic and only checks
that the proposed quantities are well-defined and behave monotonically; it is
not evidence about a real robot.
"""
import json
import os

import numpy as np

SEED = 7
D, K_H, K_S, N_H = 12, 3, 3, 6
SIG_N = 0.5
THETA = 4.0
TRIALS = 4000


def build(seed=SEED):
    rng = np.random.default_rng(seed)
    U, _ = np.linalg.qr(rng.normal(size=(D, K_H)))
    W = rng.normal(size=(D, K_S))
    W = W - U @ (U.T @ W)
    W, _ = np.linalg.qr(W)
    coef = rng.normal(size=(K_H, N_H))
    coef /= np.linalg.norm(coef, axis=0, keepdims=True)
    S = U @ coef
    B = rng.normal(size=(K_S, K_S))
    return rng, U, W, S, B


def sensitive_basis(U, W, overlap):
    ang = np.arccos(np.clip(overlap, -1.0, 1.0))
    V = np.cos(ang) * U[:, :K_S] + np.sin(ang) * W
    V, _ = np.linalg.qr(V)
    return V


def leakage(P, A):
    M = P @ A
    ev = np.linalg.eigvalsh(M.T @ M / SIG_N**2)
    return float(0.5 * np.sum(np.log1p(np.clip(ev, 0.0, None))))


def accuracy(rng, P, S, A, reps=TRIALS):
    sig = P @ S
    ok = 0
    for _ in range(reps):
        h = rng.integers(N_H)
        psi = rng.normal(size=K_S)
        rho = S[:, h] * THETA + A @ psi + SIG_N * rng.normal(size=D)
        z = P @ rho
        dist = np.sum((z[:, None] - sig) ** 2, axis=0)
        ok += int(np.argmin(dist) == h)
    return ok / reps


def dp_accuracy(rng, U, S, A, eps, reps=TRIALS):
    """Release T = U^T rho with Gaussian noise; eps ~ sens^2/(2 sigma^2)."""
    sigma = np.sqrt(1.0 / (2.0 * max(eps, 1e-6)))
    sig = U.T @ S
    ok = 0
    for _ in range(reps):
        h = rng.integers(N_H)
        psi = rng.normal(size=K_S)
        rho = S[:, h] * THETA + A @ psi + SIG_N * rng.normal(size=D)
        z = U.T @ rho + sigma * rng.normal(size=K_H)
        dist = np.sum((z[:, None] - sig) ** 2, axis=0)
        ok += int(np.argmin(dist) == h)
    return ok / reps


def main():
    rng, U, W, S, B = build()
    I = np.eye(D)
    PU = U @ U.T
    rows = []
    for overlap in (1.0, 0.7, 0.4, 0.0):
        V = sensitive_basis(U, W, overlap)
        A = V @ B
        PVp = I - V @ V.T
        rows.append({
            "overlap": overlap,
            "acc_fault_proj": round(accuracy(rng, PU, S, A), 4),
            "leak_fault_proj": round(leakage(PU, A), 4),
            "acc_free_proj": round(accuracy(rng, PVp, S, A), 4),
            "leak_free_proj": 0.0,
            "acc_full": round(accuracy(rng, I, S, A), 4),
            "leak_full": round(leakage(I, A), 4),
        })

    # Q2: DP frontier at a partial-overlap operating point.
    V = sensitive_basis(U, W, 0.4)
    A = V @ B
    eps_grid = (0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 2.0, 5.0)
    frontier = {str(e): round(dp_accuracy(rng, U, S, A, e), 4)
                for e in eps_grid}
    eps_req = None
    for e in np.linspace(0.02, 10.0, 80):
        if dp_accuracy(rng, U, S, A, float(e), reps=1500) >= 0.90:
            eps_req = round(float(e), 3)
            break

    # Q3: can the budget buy the required identifiability, or must we fall back?
    rows_budget = []
    for budget in (0.5, 1.0, 2.0, 5.0):
        for eps_p in (0.1, 0.25, 0.5):
            k = int(np.floor(budget / eps_p))
            reach = bool(eps_req is not None and k * eps_p >= eps_req)
            rows_budget.append({"budget": budget, "eps_per_probe": eps_p,
                                "max_probes": k,
                                "eps_total": round(k * eps_p, 3),
                                "eps_required_for_acc_0.90": eps_req,
                                "budget_feasible": reach})

    out = {
        "meta": {
            "purpose": "synthetic mechanism check, NOT benchmark evidence",
            "seed": SEED, "d": D, "k_H": K_H, "k_S": K_S, "n_hyp": N_H,
            "sigma_n": SIG_N, "theta": THETA, "trials": TRIALS,
        },
        "q1_frontier": rows,
        "q2_dp_frontier_overlap_0.4": frontier,
        "q2_eps_required_acc_0.90": eps_req,
        "q3_budget_feasibility": rows_budget,
    }
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "veil_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
