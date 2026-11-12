"""Toy calibration for Cross-Object Affordance Transfer + Ethics-Review gate.

NOT a robot experiment.  A synthetic object-class benchmark used to check that
the proposed quantities are computable and to contrast three mechanisms:

  * appearance policy      : binds to visual identity -> memorises seen objects
  * affordance policy      : binds to (role, affordance, relation) -> transfers
  * ethics-review gate      : non-compensatory per-risk-class harm cap

Run:  PYTHONPATH=.pylibs python exp/coat_er_sim.py
"""
import json

import numpy as np

rng = np.random.default_rng(11)

AFFORDANCES = ["grasp", "pour", "insert", "stack", "deform"]
# 24 object classes: 16 seen, 8 held out (novel).  risk=1 means handling may
# hurt a person or damage property (sharp / liquid / powered / medicine).
SEEN = [
    (0, [1, 0, 0, 1, 0]), (0, [1, 0, 0, 0, 0]), (1, [1, 1, 0, 0, 0]),
    (0, [1, 0, 1, 0, 0]), (1, [1, 0, 0, 0, 1]), (0, [1, 0, 0, 1, 0]),
    (0, [1, 0, 1, 0, 0]), (1, [1, 1, 0, 0, 0]), (0, [1, 0, 0, 1, 0]),
    (0, [1, 0, 0, 0, 1]), (1, [1, 0, 1, 0, 0]), (0, [1, 0, 0, 1, 0]),
    (0, [1, 0, 0, 0, 0]), (1, [1, 1, 0, 0, 0]), (0, [1, 0, 0, 1, 0]),
    (0, [1, 0, 1, 0, 0]),
]
NOVEL = [
    (0, [1, 0, 0, 1, 0]),  # same affordances, new appearance
    (1, [1, 1, 0, 0, 0]),  # unseen risky bottle
    (0, [1, 0, 1, 0, 0]),
    (1, [1, 0, 0, 0, 1]),  # unseen frangible/medicine
    (0, [1, 0, 0, 1, 0]),
    (1, [1, 0, 1, 0, 0]),  # unseen powered connector
    (0, [1, 0, 0, 1, 0]),
    (0, [1, 0, 0, 0, 0]),
]
OBJECTS = [("seen", r, a) for r, a in SEEN] + [("novel", r, a) for r, a in NOVEL]

# visual prototype distance to the nearest seen object (0 = seen identity,
# 1 = maximally unfamiliar appearance)
NOVELTY = []
for split, _, _ in OBJECTS:
    NOVELTY.append(0.0 if split == "seen" else float(rng.uniform(0.55, 0.95)))

# instruction requires an affordance set; here each object is queried for a
# goal that matches its own affordances (the honest transfer setting)
MATCH = [1.0 for _ in OBJECTS]


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def success_prob(policy, novelty, match, aggression):
    if policy == "appearance":
        return sigmoid(1.7 - 2.9 * novelty + 0.9 * aggression)
    return sigmoid(1.35 - 1.05 * novelty + 1.3 * (match - 0.5)
                   + 0.85 * aggression)


def harm_prob(risk, novelty, aggression):
    # aggressive execution exposes the object's risk; conservative execution
    # is a *verified* subroutine that removes most risk-correlated harm.
    if aggression <= 0.0:
        return sigmoid(-7.0 + 1.2 * risk + 1.0 * novelty)
    return sigmoid(-6.0 + 2.6 * risk + 1.8 * novelty
                   + 2.0 * aggression + 1.8 * risk * aggression)


def harm_lcb(risk, novelty, aggression, n=200, z=1.64):
    """One-sided lower confidence bound on per-trial harm."""
    p = harm_prob(risk, novelty, aggression)
    var = max(p * (1 - p), 1e-9) / n
    return max(0.0, p - z * np.sqrt(var))


def run_policy(policy, gate=None, alpha=0.02, lam=None, risk_weight=1.0):
    rows = []
    for (split, risk, _), novelty, match in zip(OBJECTS, NOVELTY, MATCH):
        # pick execution aggressiveness
        if gate == "ethics":
            aggression = 1.0
            if harm_lcb(risk, novelty, 1.0) > alpha:
                aggression = 0.0
                if harm_lcb(risk, novelty, 0.0) > alpha:
                    aggression = -1.0  # abstain: do nothing, no harm
        elif gate == "soft":
            w = risk_weight if risk else 1.0
            grid = [0.0, 0.5, 1.0]
            aggression = max(
                grid,
                key=lambda a: success_prob(policy, novelty, match, a) * 100.0
                + 55.0 * (0.4 + 0.6 * a)
                * success_prob(policy, novelty, match, a)
                - lam * w * harm_prob(risk, novelty, a))
        else:
            aggression = 1.0

        if aggression < 0:
            p = h = 0.0
            score = 0.0
        else:
            p = success_prob(policy, novelty, match, aggression)
            h = harm_prob(risk, novelty, aggression)
            step = 55.0 * (0.4 + 0.6 * aggression) * p
            score = 100.0 * p + step
        rows.append(dict(split=split, risk=risk, novelty=novelty,
                         aggression=aggression, success=p, harm=h,
                         score=score))
    return rows


def summarize(rows):
    groups = {}
    for r in rows:
        key = f"{r['split']}_{'risk' if r['risk'] else 'normal'}"
        groups.setdefault(key, []).append(r)

    def agg(key, field):
        vals = [x[field] for x in groups[key]]
        return float(np.mean(vals))

    out = {}
    for key in groups:
        out[key] = {
            "success": round(agg(key, "success"), 3),
            "harm": round(agg(key, "harm"), 4),
            "score": round(agg(key, "score"), 1),
            "aggression": round(agg(key, "aggression"), 3),
        }
    succ = {k: v["success"] for k, v in out.items()}
    harm = {k: v["harm"] for k, v in out.items()}
    out["_overall"] = {
        "mean_success": round(float(np.mean([r["success"] for r in rows])), 3),
        "mean_score": round(float(np.mean([r["score"] for r in rows])), 1),
        "novelty_gap": round(succ["seen_normal"] - succ["novel_normal"], 3),
        "worst_group_success": round(min(succ.values()), 3),
        "max_group_harm": round(max(harm.values()), 4),
        "risk_violations": sum(1 for v in harm.values() if v > 0.02),
    }
    return out


CONFIGS = {
    "appearance_aggressive": lambda: run_policy("appearance"),
    "affordance_aggressive": lambda: run_policy("affordance"),
    "affordance_soft_penalty": lambda: run_policy("affordance", "soft", lam=200.0),
    "affordance_soft_population": lambda: run_policy(
        "affordance", "soft", lam=200.0, risk_weight=0.15),
    "affordance_ethics_gate": lambda: run_policy("affordance", "ethics"),
}


def main():
    out = {name: summarize(fn()) for name, fn in CONFIGS.items()}
    out["_sweep_alpha"] = {
        str(a): summarize(run_policy("affordance", "ethics", alpha=a))["_overall"]
        for a in (0.005, 0.01, 0.02, 0.05, 0.10)
    }
    out["_sweep_lambda"] = {
        str(lam): summarize(run_policy("affordance", "soft", lam=lam))["_overall"]
        for lam in (0, 100, 200, 400, 800, 1600)
    }
    out["_meta"] = {
        "kind": "synthetic object-class calibration; not robot data",
        "n_objects": len(OBJECTS),
        "seen": len(SEEN),
        "novel": len(NOVEL),
        "alpha_harm": 0.02,
        "seed": 11,
    }
    with open("exp/coat_er_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
