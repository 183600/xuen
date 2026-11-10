"""Round-44 toy mechanism check: intent-certified navigation vs point-estimate intent.

Graph:
  S --4-- J --1-- V
            J --1-- A_e --1-- A_p --1-- A_g
            J --1-- B_e --1-- B_p --1-- B_g
Public (intent-agnostic) nodes: S, J, V, A_e, B_e
Private nodes: A_p/A_g allowed only under intent A; B_p/B_g only under intent B.
A wrong-intent commitment enters the other intent's private zone => violation.
"""
import json
import random

PUBLIC = {"S", "J", "V", "A_e", "B_e"}
PRIVATE = {"A": {"A_p", "A_g"}, "B": {"B_p", "B_g"}}
DIST_S_J = 4
DIST_J_GOAL = 3
DIST_J_V = 1
QUERY_COST = 3

def simulate(n=40000, seed=44, p_prior=0.80, q_signal=0.95,
             p_high_correct=0.90, p_high_wrong=0.35):
    rng = random.Random(seed)
    stats = {k: {"viol": 0, "succ": 0, "steps": 0, "queries": 0}
             for k in ("baseline", "conservative", "icn")}

    for _ in range(n):
        truth = "A" if rng.random() < 0.5 else "B"

        # 1) point-estimate baseline: commit at start from a p_prior-accurate classifier
        guess = truth if rng.random() < p_prior else ("B" if truth == "A" else "A")
        st = stats["baseline"]
        st["steps"] += DIST_S_J + DIST_J_GOAL
        if guess == truth:
            st["succ"] += 1
        else:
            st["viol"] += 1

        # 2) purely conservative: never foreclose an intent, stay in common safe set
        st = stats["conservative"]
        st["steps"] += DIST_S_J  # patrol to the junction, then wait
        # no violation, no success

        # 3) intent-certified navigation: go to the vantage, observe, abstain if unsure
        st = stats["icn"]
        signal = truth if rng.random() < q_signal else ("B" if truth == "A" else "A")
        high = rng.random() < (p_high_correct if signal == truth else p_high_wrong)
        steps = DIST_S_J + 2 * DIST_J_V + DIST_J_GOAL
        if not high:
            steps += QUERY_COST
            st["queries"] += 1
            commit = truth              # explicit user query is an oracle in this toy
        else:
            commit = signal             # conformal singleton
        st["steps"] += steps
        if commit == truth:
            st["succ"] += 1
        else:
            st["viol"] += 1
    out = {}
    for k, st in stats.items():
        out[k] = {
            "violation_rate": round(st["viol"] / n, 4),
            "success_rate": round(st["succ"] / n, 4),
            "mean_steps": round(st["steps"] / n, 3),
            "query_rate": round(st["queries"] / n, 4),
        }
    return out

if __name__ == "__main__":
    res = simulate()
    print(json.dumps(res, indent=2, ensure_ascii=False))
