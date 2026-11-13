"""Round-v3 mechanism check: does intent anticipation pay for itself?

Inspiration word: 「意图识别」 (intent recognition).

A completed scoring step can be undone by a human.  The policy cannot see the
human's intent directly, only a noisy hazard cue.  We compare three policies on
a synthetic 5-step task (weights 20/20/20/20/20), where reaching step 5 is a
success (score 100) and otherwise the score is the sum of the kept prefix:

  R  reactive / myopic : always attempt the next step, never guard.
  B  belief-based      : forward-filter a 2-regime hazard HMM and guard when
                         P(high hazard) > 0.5.
  O  oracle            : knows the current regime and solves the finite-horizon
                         MDP (regime still switches with PERSIST).

The question is narrow: with a guard action that lowers the undo hazard but
spends a decision epoch, how much expected score does *anticipation* recover
over pure reaction, and how close is the belief policy to the oracle?

THIS IS A MECHANISM CHECK ON A SYNTHETIC PROCESS, NOT A BENCHMARK RESULT.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

EXP = Path("/home/runner/work/xuen/xuen/workspace/exp")
OUT = EXP / "visc_intent_dp_results.json"

G = 5
W = [20.0] * G
P_STEP = 0.45
H_LOW = 0.03
H_HIGH = 0.55
H_GUARD = 0.03
PERSIST = 0.88
T_HORIZON = 30
OBS_SIGMA = 0.7
N_EP = 20000
SEED = 20261113


def score_of(g: int) -> float:
    return 100.0 if g >= G else float(sum(W[:g]))


def value_iteration(actions):
    """Finite-horizon DP over (g, regime). g==G is absorbing success."""
    V = {(g, r): score_of(g) for g in range(G + 1) for r in (0, 1)}
    policy = {}
    for _ in range(T_HORIZON):
        nV, pol = {}, {}
        for g in range(G + 1):
            for r in (0, 1):
                if g >= G:
                    nV[(g, r)] = 100.0
                    pol[(g, r)] = "done"
                    continue
                best_a, best_v = None, -1e18
                for a in actions:
                    h = H_GUARD if a == "guard" else (H_HIGH if r == 1 else H_LOW)
                    v = 0.0
                    for r_next, pr in ((r, PERSIST), (1 - r, 1 - PERSIST)):
                        # the human can only undo an already-completed step
                        if g > 0:
                            v += pr * h * V[(g - 1, r_next)]
                            keep = 1.0 - h
                        else:
                            keep = 1.0
                        if a == "attempt":
                            v += pr * keep * (P_STEP * V[(min(G, g + 1), r_next)]
                                              + (1 - P_STEP) * V[(g, r_next)])
                        else:
                            v += pr * keep * V[(g, r_next)]
                    if v > best_v:
                        best_v, best_a = v, a
                nV[(g, r)] = best_v
                pol[(g, r)] = best_a
        V = nV
        policy = pol
    return V, policy


def simulate(policy_fn, rng, n_ep=N_EP, belief=False):
    scores, succ, guard_frac = [], [], []
    for _ in range(n_ep):
        r = int(rng.random() < 0.5)
        g = 0
        guards = 0
        filt = _BeliefFilter() if belief else None
        for _t in range(T_HORIZON):
            if g >= G:
                break
            cue = r + rng.normal(0.0, OBS_SIGMA)
            ph = filt.update(cue) if filt is not None else None
            a = policy_fn(g, r, ph)
            if a == "guard":
                guards += 1
                h = H_GUARD
            else:
                h = H_HIGH if r == 1 else H_LOW
            undone = rng.random() < h and g > 0
            if undone:
                g -= 1
            elif a == "attempt" and rng.random() < P_STEP and g < G:
                g += 1
            r = r if rng.random() < PERSIST else 1 - r
        scores.append(score_of(g))
        succ.append(1.0 if g >= G else 0.0)
        guard_frac.append(guards / T_HORIZON)
    return {
        "step_score_mean": round(float(np.mean(scores)), 3),
        "step_score_sd": round(float(np.std(scores)), 3),
        "success_rate": round(float(np.mean(succ)), 4),
        "guard_fraction": round(float(np.mean(guard_frac)), 4),
    }


class _BeliefFilter:
    """2-regime HMM forward filter for the hazard cue."""

    def __init__(self):
        self.p = np.array([0.5, 0.5])
        self.trans = np.array([[PERSIST, 1 - PERSIST],
                               [1 - PERSIST, PERSIST]])
        self.means = np.array([0.0, 1.0])

    def update(self, cue: float) -> float:
        lik = np.exp(-0.5 * ((cue - self.means) / OBS_SIGMA) ** 2)
        self.p = lik * (self.trans.T @ self.p)
        self.p /= self.p.sum()
        return float(self.p[1])


def main() -> None:
    rng = np.random.default_rng(SEED)
    V_react, _ = value_iteration({"attempt"})
    V_opt, pol_opt = value_iteration({"attempt", "guard"})
    reactive_dp = float(np.mean([V_react[(0, r)] for r in (0, 1)]))
    oracle_dp = float(np.mean([V_opt[(0, r)] for r in (0, 1)]))

    def reactive(g, r, ph):
        return "attempt"

    reactive_mc = simulate(reactive, np.random.default_rng(SEED))

    sweep = []
    for thr in (0.40, 0.50, 0.60, 0.70, 0.80):
        for g_min in (1, 2, 3):
            def belief(g, r, ph, thr=thr, g_min=g_min):
                return "guard" if (ph is not None and ph > thr and g >= g_min) else "attempt"
            res = simulate(belief, np.random.default_rng(SEED), belief=True)
            sweep.append({"threshold": thr, "g_min": g_min, **res})
    best = max(sweep, key=lambda r: r["step_score_mean"])

    out = {
        "note": "synthetic 5-step process; not a benchmark result",
        "params": {
            "G": G, "weights": W, "p_step": P_STEP, "h_low": H_LOW,
            "h_high": H_HIGH, "h_guard": H_GUARD, "persist": PERSIST,
            "horizon": T_HORIZON, "obs_sigma": OBS_SIGMA, "n_ep": N_EP,
        },
        "reactive_monte_carlo": reactive_mc,
        "belief_best_monte_carlo": best,
        "belief_sweep": sweep,
        "reactive_dp_expected": round(reactive_dp, 3),
        "oracle_dp_expected": round(oracle_dp, 3),
        "oracle_policy": {f"g={g},r={r}": pol_opt[(g, r)]
                          for g in range(G + 1) for r in (0, 1)},
    }
    out["belief_vs_reactive_pp"] = round(
        best["step_score_mean"] - reactive_mc["step_score_mean"], 3)
    out["oracle_minus_reactive_pp"] = round(oracle_dp - reactive_dp, 3)
    out["belief_captures_oracle_gain_pct"] = (
        round(100.0 * out["belief_vs_reactive_pp"]
              / (oracle_dp - reactive_dp), 1)
        if oracle_dp > reactive_dp else None)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")
    print(json.dumps({k: out[k] for k in (
        "reactive_monte_carlo", "belief_best_monte_carlo",
        "reactive_dp_expected", "oracle_dp_expected", "oracle_policy",
        "belief_vs_reactive_pp", "oracle_minus_reactive_pp",
        "belief_captures_oracle_gain_pct")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
