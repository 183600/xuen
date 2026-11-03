"""FORGE-DA evidence, part 2: is the evaluation fleet a useful *active
annotation oracle*?

Mechanism question (synthetic; NOT benchmark evidence):
  The hidden test is 32 tasks x 2 trials x 5 generalization axes.
  Suppose we have a fixed budget B of synthetic-augmentation / re-annotation
  "slots" and each slot applied to cell (task, axis) raises that cell's success
  with diminishing returns.  The evaluation fleet returns per-cell success
  counts online.  Does a failure-driven greedy allocator beat uniform
  allocation, and how much of the oracle gap does it close?

Declared generative model (illustrative magnitudes; not fit to any board):
  p0[i,j]   ~ Beta(2,4)          latent base success per cell (heterogeneous)
  headroom  = cap - p0          cap ~ U(0.75, 0.9)
  one slot  : p <- p + eta*(cap-p),   eta ~ U(0.05,0.12) per cell
  observation: n=10 Bernoulli per cell (the official 10 runs/task split
               across the 5 axes, i.e. 2 per axis); rounded to the grid.
  allocators: uniform | greedy-on-observed-success | greedy-on-uncertainty
              (UCB) | oracle-on-true-p.
Output: exp/forge_sim_results.json
"""
import json
import os
import numpy as np

RNG = np.random.default_rng(20261103)
NT, NA = 32, 5
TRIALS = 2          # official: each axis appears twice
BUDGET = 40
N_SEEDS = 300
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "forge_sim_results.json")


def make_world():
    p0 = RNG.beta(2, 4, size=(NT, NA))
    cap = RNG.uniform(0.75, 0.90, size=(NT, NA))
    eta = RNG.uniform(0.05, 0.12, size=(NT, NA))
    return p0, cap, eta


def observe(p):
    return RNG.binomial(TRIALS, p)


def run_alloc(p0, cap, eta, policy):
    p = p0.copy()
    obs = observe(p)
    for _ in range(BUDGET):
        if policy == "uniform":
            valid = [(i, j) for i in range(NT) for j in range(NA)]
            i, j = valid[int(RNG.integers(len(valid)))]
        elif policy == "greedy":
            rate = obs / TRIALS
            # focus on cells that are hardest *and* still have headroom
            score = (1 - rate) * (cap - p)
            i, j = np.unravel_index(np.argmax(score), score.shape)
        elif policy == "ucb":
            rate = obs / TRIALS
            bonus = np.sqrt(2 * np.log(2 + _) / (TRIALS + 1))
            score = (rate + bonus) * (cap - p)      # optimistic where uncertain
            i, j = np.unravel_index(np.argmax(score), score.shape)
        elif policy == "oracle":
            score = (cap - p)                        # true headroom
            i, j = np.unravel_index(np.argmax(score), score.shape)
        else:
            raise ValueError(policy)
        p[i, j] = p[i, j] + eta[i, j] * (cap[i, j] - p[i, j])
        obs[i, j] = observe(p[i, j])
    return p.mean()


def main():
    agg = {k: [] for k in ("none", "uniform", "greedy", "ucb", "oracle")}
    for _ in range(N_SEEDS):
        p0, cap, eta = make_world()
        agg["none"].append(p0.mean())
        for pol in ("uniform", "greedy", "ucb", "oracle"):
            agg[pol].append(run_alloc(p0, cap, eta, pol))
    res = {k: {"mean": float(np.mean(v)), "std": float(np.std(v))}
           for k, v in agg.items()}
    base = res["none"]["mean"]
    uni = res["uniform"]["mean"]
    grd = res["greedy"]["mean"]
    ucb = res["ucb"]["mean"]
    orc = res["oracle"]["mean"]
    res["deltas_pp"] = {
        "uniform_over_none": round((uni - base) * 100, 2),
        "greedy_over_uniform": round((grd - uni) * 100, 2),
        "ucb_over_greedy": round((ucb - grd) * 100, 2),
        "greedy_over_none": round((grd - base) * 100, 2),
        "oracle_over_greedy": round((orc - grd) * 100, 2),
    }
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2)
    print("=" * 70)
    print("FORGE-DA fleet active-annotation allocator (synthetic, "
          f"{N_SEEDS} seeds, budget={BUDGET} slots)")
    print("=" * 70)
    print(f"{'allocator':14s} {'mean succ':>10s} {'std':>8s}")
    for k in ("none", "uniform", "greedy", "ucb", "oracle"):
        print(f"{k:14s} {res[k]['mean']:10.4f} {res[k]['std']:8.4f}")
    print("-" * 70)
    for k, v in res["deltas_pp"].items():
        print(f"  {k:24s} {v:+6.2f} pp")
    print("=" * 70)
    return res


if __name__ == "__main__":
    main()
