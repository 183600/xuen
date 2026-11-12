"""Round-2 synthetic mechanism check: PROTOFORGE multi-fidelity racing.

NOT benchmark evidence.  Isolates one question about rapid prototyping:

  With K candidate task wrappers/adapters and three evaluation fidelities
  (static-frame unit tests; open-loop replay; closed-loop replay), does
  successive-halving racing select a near-best candidate at much lower compute
  than evaluating every candidate at the highest fidelity?

Declared generative model (not fit):
  true utility theta_i ~ N(0,1)
  fidelity f observation = theta_i + eps_f, eps_f ~ N(0, sigma_f)
  costs: low=1, mid=4, high=16; sigma: low=0.90, mid=0.45, high=0.16
Strategies: uniform-low, uniform-mid, uniform-high, 2-stage, 3-stage racing.
Metrics over 4000 repetitions: P(select true best), expected regret
(theta_best - theta_selected), total cost.
"""
import json, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "protoforge_racing_results.json")
RNG = np.random.default_rng(20261112)

K = 24
REPS = 4000
SIGMA = {0: 0.90, 1: 0.45, 2: 0.16}
COST = {0: 1.0, 1: 4.0, 2: 16.0}


def observe(theta, level, rng):
    return theta + rng.normal(0.0, SIGMA[level], size=theta.shape)


def run_strategy(theta, strategy, rng):
    if strategy == "uniform_low":
        est = observe(theta, 0, rng)
        return int(np.argmax(est)), COST[0] * len(theta)
    if strategy == "uniform_mid":
        est = observe(theta, 1, rng)
        return int(np.argmax(est)), COST[1] * len(theta)
    if strategy == "uniform_high":
        est = observe(theta, 2, rng)
        return int(np.argmax(est)), COST[2] * len(theta)
    if strategy == "two_stage":
        e0 = observe(theta, 0, rng)
        idx = np.argsort(e0)[-len(theta)//2:]
        e1 = observe(theta[idx], 1, rng)
        return int(idx[np.argmax(e1)]), COST[0]*len(theta) + COST[1]*len(idx)
    if strategy == "three_stage":
        e0 = observe(theta, 0, rng)
        idx = np.argsort(e0)[-len(theta)//2:]
        e1 = observe(theta[idx], 1, rng)
        idx2 = idx[np.argsort(e1)[-max(1, len(idx)//2):]]
        e2 = observe(theta[idx2], 2, rng)
        cost = COST[0]*len(theta) + COST[1]*len(idx) + COST[2]*len(idx2)
        return int(idx2[np.argmax(e2)]), cost
    raise ValueError(strategy)


def main():
    strategies = ["uniform_low", "uniform_mid", "uniform_high", "two_stage", "three_stage"]
    out = dict(
        note="Synthetic selection experiment only; costs/noise declared in script.",
        config=dict(K=K, REPS=REPS, SIGMA=SIGMA, COST=COST, seed=20261112),
        results={},
    )
    for s in strategies:
        best_hits = 0
        regrets = []
        costs = []
        for _ in range(REPS):
            theta = RNG.normal(size=K)
            sel, cost = run_strategy(theta, s, RNG)
            best_hits += int(sel == int(np.argmax(theta)))
            regrets.append(float(theta.max() - theta[sel]))
            costs.append(cost)
        out["results"][s] = dict(
            p_select_best=best_hits / REPS,
            mean_regret=float(np.mean(regrets)),
            mean_cost=float(np.mean(costs)),
            cost_per_regret=float(np.mean(costs) / max(1e-9, np.mean(regrets))),
        )
        r = out["results"][s]
        print(f"{s:12s} P(best)={r['p_select_best']:.3f} regret={r['mean_regret']:.3f} "
              f"cost={r['mean_cost']:.1f}")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
