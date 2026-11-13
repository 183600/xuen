#!/usr/bin/env python3
"""Round-1 (loop v4) mechanism check: tabletop reversible state machine.

Two independent, deliberately small analyses:

A. Stereo depth precision of the head pair, from the official
   robots/uniclib_calibration.json (baseline 60.11 mm, fx ~271-273 px).
   sigma_Z = Z^2 / (f * B) * sigma_d.

B. Synthetic undo/recovery Monte Carlo over the 32 official scoring-point
   vectors. It is NOT benchmark evidence: execution failure is switched off,
   undo hazard and detection probability are declared knobs, and time is
   measured in scoring-step slots. The point is to isolate the *relative*
   cost of "redo the whole task" vs "redo only the regressed suffix" when a
   human reverses progress.

Run: PYTHONPATH=.pylibs python3 exp/tt_trsm_sim.py
"""
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASKS_JSON = HERE / "official" / "tasks_v2_info.json"
OUT = HERE / "tt_trsm_results.json"

F_HEAD = 272.0
BASELINE_MM = 60.107653
SIGMA_DISPARITY_PX = 0.25

TASK_LIST = None


def load_tasks():
    global TASK_LIST
    d = json.load(open(TASKS_JSON, encoding="utf-8"))
    out = []
    for slug, v in d.items():
        w = [s["score"] for s in v["score_steps"]]
        out.append({"id": v["task_id"], "slug": slug, "weights": w})
    out.sort(key=lambda x: x["id"])
    TASK_LIST = out
    return out


def stereo_table():
    rows = []
    for z_m in (0.30, 0.40, 0.50, 0.60, 0.80, 1.00):
        z_mm = z_m * 1000.0
        sigma_z = (z_mm ** 2) / (F_HEAD * BASELINE_MM) * SIGMA_DISPARITY_PX
        rows.append({
            "distance_m": z_m,
            "depth_sigma_mm_at_0.25px": round(sigma_z, 2),
            "depth_sigma_mm_at_1px": round(sigma_z / SIGMA_DISPARITY_PX, 2),
        })
    return {
        "source": "robots/uniclib_calibration.json (retrieved 2026-11-13)",
        "baseline_mm": BASELINE_MM,
        "focal_px": F_HEAD,
        "subpixel_sigma_px": SIGMA_DISPARITY_PX,
        "formula": "sigma_Z = Z^2 / (f * B) * sigma_d",
        "rows": rows,
    }


def run_episode(weights, rng, strategy, p_undo, p_detect, p_fail, budget):
    n = len(weights)
    world = [0] * n
    belief = [0] * n
    executed = 0
    useful = 0
    timeouts = 0
    while True:
        i = next((k for k in range(n) if belief[k] == 0), None)
        if i is None:
            break
        if executed >= budget:
            timeouts = 1
            break
        executed += 1
        if rng.random() < p_fail:
            continue
        if world[i] == 0:
            useful += 1
        world[i] = 1
        belief[i] = 1
        if rng.random() < p_undo:
            j = i
            if i > 0 and rng.random() < 0.35:
                j = rng.randrange(i + 1)
            for k in range(j, n):
                world[k] = 0
            if strategy != "openloop" and rng.random() < p_detect:
                if strategy == "full_retry":
                    belief = [0] * n
                else:
                    for k in range(j, n):
                        belief[k] = 0
    score = sum(weights[k] for k in range(n) if world[k] == 1)
    success = int(all(world))
    return success, score, executed, executed - useful, timeouts


def monte_carlo(n_ep, seed, p_undo, p_detect, p_fail, budget_mult):
    rng = random.Random(seed)
    strategies = ("openloop", "full_retry", "suffix_redo")
    agg = {s: {"succ": 0, "score": 0.0, "exec": 0, "waste": 0, "timeout": 0, "n": 0}
           for s in strategies}
    for t in TASK_LIST:
        budget = budget_mult * len(t["weights"])
        for s in strategies:
            for _ in range(n_ep):
                ok, sc, ex, wa, to = run_episode(
                    t["weights"], rng, s, p_undo, p_detect, p_fail, budget)
                a = agg[s]
                a["succ"] += ok
                a["score"] += sc
                a["exec"] += ex
                a["waste"] += wa
                a["timeout"] += to
                a["n"] += 1
    out = {}
    for s, a in agg.items():
        n = a["n"]
        out[s] = {
            "success_rate": round(a["succ"] / n, 4),
            "avg_step_score": round(a["score"] / n, 2),
            "avg_executed_steps": round(a["exec"] / n, 2),
            "avg_wasted_steps": round(a["waste"] / n, 2),
            "timeout_rate": round(a["timeout"] / n, 4),
        }
    return out


def main():
    load_tasks()
    results = {
        "meta": {
            "purpose": "synthetic mechanism check, NOT benchmark evidence",
            "n_ep_per_task_per_strategy": 1500,
            "p_fail": 0.05,
            "budget_mult": 3.0,
            "undo_target": "current step, 35% uniform over completed prefix",
            "note": "execution failure disabled except p_fail; undo hazard and detection are declared knobs",
        },
        "stereo_depth": stereo_table(),
        "sweeps": {},
    }
    for p_undo in (0.0, 0.10, 0.20, 0.30):
        for p_detect in (0.5, 0.8, 1.0):
            key = f"undo{int(p_undo*100):02d}_detect{int(p_detect*100):03d}"
            results["sweeps"][key] = monte_carlo(
                1500, 20261113, p_undo, p_detect, 0.05, 3.0)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
