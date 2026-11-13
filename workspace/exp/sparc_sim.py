#!/usr/bin/env python3
"""SPARC toy simulator (stdlib only).

Compares plan-level execution controllers on a weighted, ordered scoring DAG
under (a) stochastic skill failures and (b) adversarial "reverse a completed
step" disturbances, with noisy map-predicate observations.

This is a deliberately small, synthetic sanity check -- NOT a robot experiment.
It only tests the *decision logic*: does map-diff + attribution + minimal
repair beat open-loop and naive reactive redoing?

Controllers
-----------
open_loop   : attempt each step once, in order, never re-observe.
reactive1   : redo the first step whose *single-frame* predicate is false.
reactive2   : same, but require 2 consecutive false readings (debounce).
sparc       : keep a persistent belief; a completed step that flips to false is
              attributed to an external agent only if (i) it persists 2 frames
              and (ii) we did not just act on it; then redo that step (minimal
              repair) before advancing. Single-frame flicker is ignored.

Scoring
-------
"final_state": a step scores iff its true status is done at the end.
"cumulative" : a step scores once it is first truly completed (progress banked).

Run: python sparc_sim.py
"""
import json
import random
from dataclasses import dataclass, field


@dataclass
class Step:
    weight: int
    fragile: bool = True


@dataclass
class Scenario:
    name: str
    weights: list
    p_skill: float = 0.55       # P(one attempt completes a pending step)
    h_disturb: float = 0.06     # per-chunk hazard that a completed step is reversed
    p_obs_flip: float = 0.10    # symmetric predicate readout noise
    horizon: int = 40
    scoring: str = "final_state"


def attempt(p):
    return random.random() < p


def observe(truth, p_flip):
    if random.random() < p_flip:
        return not truth
    return truth


def run_episode(sc, ctrl, rng):
    n = len(sc.weights)
    done = [False] * n           # true world state
    belief = [False] * n         # controller's map belief
    attempts = [0] * n
    wasted = 0                   # attempts on a step already truly done
    banked = [False] * n         # cumulative score
    scored = [False] * n
    last_obs_false = [0] * n
    last_acted = [False] * n
    ptr = 0

    for _ in range(sc.horizon):
        # ---- decide target ----
        target = None
        if ctrl == "open_loop":
            if ptr < n:
                target = ptr
                ptr += 1
        else:
            if ctrl == "reactive1":
                # first step the noisy single frame says is not done
                for i in range(n):
                    if not observe(done[i], sc.p_obs_flip):
                        target = i
                        break
            elif ctrl == "reactive2":
                for i in range(n):
                    obs = observe(done[i], sc.p_obs_flip)
                    if not obs:
                        last_obs_false[i] += 1
                    else:
                        last_obs_false[i] = 0
                    if last_obs_false[i] >= 2:
                        target = i
                        break
            elif ctrl == "sparc":
                # persistent belief: integrate 2-frame evidence, but only
                # re-open a completed step when it is not our own action.
                for i in range(n):
                    obs = observe(done[i], sc.p_obs_flip)
                    if not obs:
                        last_obs_false[i] += 1
                    else:
                        last_obs_false[i] = 0
                # regressions: believed-done but persistently observed undone
                for i in range(n):
                    if belief[i] and last_obs_false[i] >= 2 and not last_acted[i]:
                        target = i
                        break
                if target is None:
                    # retry a step we acted on but that did not become done
                    for i in range(n):
                        if not belief[i] and last_acted[i]:
                            target = i
                            break
                if target is None:
                    for i in range(n):
                        if not belief[i]:
                            target = i
                            break

        last_acted = [False] * n
        if target is not None:
            if done[target]:
                wasted += 1
            attempts[target] += 1
            if attempt(sc.p_skill):
                done[target] = True
                belief[target] = True
            else:
                belief[target] = False
            last_acted[target] = True

        # ---- adversarial disturbance: reverse a completed step ----
        if random.random() < sc.h_disturb:
            cands = [i for i in range(n) if done[i] and sc.weights[i] is not None]
            if cands:
                i = rng.choice(cands)
                done[i] = False
                # map does not instantly know; belief updated by observations

        # ---- cumulative banking ----
        if sc.scoring == "cumulative":
            for i in range(n):
                if done[i] and not banked[i]:
                    banked[i] = True

    final = banked if sc.scoring == "cumulative" else done
    score = sum(sc.weights[i] for i in range(n) if final[i])
    total = sum(sc.weights)
    success = all(final)
    return score, total, success, sum(attempts), wasted


def run(sc, ctrl, n_ep=4000):
    rng = random.Random(12345)
    random.seed(999)
    scores = succ = att = wst = 0
    for _ in range(n_ep):
        s, t, ok, a, w = run_episode(sc, ctrl, rng)
        scores += s
        succ += int(ok)
        att += a
        wst += w
    return {
        "score": round(scores / n_ep, 2),
        "score_pct": round(100.0 * scores / (n_ep * sum(sc.weights)), 2),
        "success_pct": round(100.0 * succ / n_ep, 2),
        "attempts_per_ep": round(att / n_ep, 2),
        "wasted_attempts_per_ep": round(wst / n_ep, 2),
        # score per action actually spent: proxy for latency/credibility cost
        "score_per_attempt": round(scores / max(att, 1e-9), 2),
    }


def main():
    scenarios = [
        Scenario("low_disturb_30_30_40", [30, 30, 40], h_disturb=0.02,
                 p_obs_flip=0.08),
        Scenario("high_disturb_30_30_40", [30, 30, 40], h_disturb=0.10,
                 p_obs_flip=0.10),
        Scenario("high_disturb_noisy_20x5", [20] * 5, h_disturb=0.10,
                 p_obs_flip=0.18),
        Scenario("high_disturb_cumulative", [30, 30, 40], h_disturb=0.10,
                 p_obs_flip=0.10, scoring="cumulative"),
        Scenario("tight_budget_30_30_40", [30, 30, 40], h_disturb=0.10,
                 p_obs_flip=0.10, horizon=12),
        Scenario("tight_budget_noisy_20x5", [20] * 5, h_disturb=0.10,
                 p_obs_flip=0.18, horizon=15),
    ]
    ctrols = ["open_loop", "reactive1", "reactive2", "sparc"]
    out = {}
    for sc in scenarios:
        out[sc.name] = {c: run(sc, c) for c in ctrols}
        print(f"\n== {sc.name} ==")
        for c in ctrols:
            r = out[sc.name][c]
            print(f"  {c:10s} score={r['score']:7.2f} ({r['score_pct']:5.1f}%) "
                  f"success={r['success_pct']:5.1f}% att/Ep={r['attempts_per_ep']:5.2f} "
                  f"wasted/Ep={r['wasted_attempts_per_ep']:5.2f} "
                  f"score/att={r['score_per_attempt']:5.2f}")
    with open("sparc_results.json", "w") as f:
        json.dump(out, f, indent=2)
    print("\nwrote sparc_results.json")


if __name__ == "__main__":
    main()
