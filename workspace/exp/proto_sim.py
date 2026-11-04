#!/usr/bin/env python3
"""Protocol-level mechanism check for UniBot round 16 (PROTO-COMP).

Question: given the *verified* UniBot-V1 protocol (32 tasks x 10 runs, 5
generalization axes x 2, 180 s per-run cap, action chunk 30 @ 30 fps, public
per-task rubrics, leaderboard per-task success/duration), what do the proposed
levers buy under an explicit, sweepable generative model?

Verified inputs (exp/proto_inputs.json, retrieved 2026-11-04):
  - rubric weights and step text per task (unibot.unitree.com/tasks_v2/*/info.json)
  - per-task success / duration / step score averaged over the 8 leaderboard models
  - protocol: 10 runs per task, 5 axes x 2, 180 s cap, chunk 30 @ 30 fps

Everything else is an ASSUMPTION and is swept, not claimed:
  - axis derailing probabilities, per-step completion probabilities, retry/stop
    policy, latency distribution, sim2real transfer discount.

This is NOT a benchmark result: it measures arithmetic consequences of the
protocol under a stated model, to size levers before spending robot time.
"""
import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
INPUTS = os.path.join(HERE, "proto_inputs.json")
OUT = os.path.join(HERE, "proto_results.json")

CHUNK_S = 1.0          # 30 steps @ 30 fps -> one chunk covers 1 s of motion
TIMEOUT_S = 180.0      # per-run hard cap (rules, retrieved 2026-11-04)
N_RUNS = 10            # runs per task
AXES = ["position", "distractor", "background", "unseen", "human"]

# ---- assumption block (swept in the report) --------------------------
BASE_DERAIL = {"position": 0.02, "distractor": 0.20, "background": 0.05,
               "unseen": 0.35, "human": 0.0}   # human handled by explicit interrupt
DIFF_Q = {"Easy": 0.88, "Medium": 0.80, "Hard": 0.70}
BASE_MAX_ATTEMPTS = 2
RETRY_MIN_BUDGET_FRAC = 0.30
SERVER_HARD_TIMEOUT_S = 5.0
LAT_SIGMA = 0.35
COUPLING = 0.5
SIM2REAL_DISCOUNT = 0.6
HOLD_FINAL_HOPELESS = 0.25      # stop retrying when the remaining steps look hopeless
P_INTERRUPT = 0.25              # mid-episode human perturbation probability
P_RECOVER = 0.60                # recovery success given an interruption


def axis_plan():
    plan = []
    for a in AXES:
        plan += [a, a]
    return plan


def step_probs(task, cfg):
    q = [DIFF_Q[task["difficulty"]]] * len(task["pts"])
    return q


def axis_derail(axis, cfg):
    d = BASE_DERAIL[axis]
    if cfg.get("axis_compiler"):
        # targeted synthetic data on the unseen-object / distractor axes
        if axis == "unseen":
            d = max(0.0, d * (1 - SIM2REAL_DISCOUNT))
        elif axis == "distractor":
            d = max(0.0, d * (1 - SIM2REAL_DISCOUNT))
    if cfg.get("perturb_recovery") and axis == "human":
        pass  # handled by interrupt/recovery
    return d


def attempt(task, axis, cfg, rng, budget_left, lat_median):
    pts = task["pts"]
    tot_w = float(sum(pts))
    dur = task["dur_avg8"]
    cost = [dur * w / tot_w for w in pts]
    q = step_probs(task, cfg)
    n = len(pts)

    derail = axis_derail(axis, cfg)
    derail_at = rng.randrange(n) if rng.random() < derail else None

    points = 0
    t = 0.0
    for j in range(n):
        c = cost[j]
        for _ in range(max(1, math.ceil(c / CHUNK_S))):
            if cfg.get("cloud_edge"):
                ports = cfg.get("ports", 3)
                lat = lat_median + rng.lognormvariate(0.0, LAT_SIGMA) * COUPLING / ports
            else:
                lat = lat_median + rng.lognormvariate(0.0, LAT_SIGMA)
            if lat > SERVER_HARD_TIMEOUT_S and not cfg.get("cloud_edge"):
                return points, t, False, "request_timeout"
            t += CHUNK_S + lat
        if t > budget_left:
            return points, t, False, "budget"
        if derail_at is not None and j >= derail_at:
            return points, t, False, "axis_derail"
        if axis == "human" and j == 0 and rng.random() < P_INTERRUPT:
            if cfg.get("perturb_recovery") and rng.random() < P_RECOVER:
                continue                      # re-anchor and continue
            return points, t, False, "perturbed"
        if rng.random() < min(0.99, q[j]):
            points += pts[j]
        else:
            return points, t, False, "step_fail"
    return points, t, True, None


def final_step_hopeless(task, cfg):
    q = step_probs(task, cfg)
    p = 1.0
    for v in q[1:]:
        p *= v
    return p < HOLD_FINAL_HOPELESS


def run_episode(task, axis, cfg, rng, lat_median):
    budget = TIMEOUT_S
    best = 0
    last = 0
    attempts = 0
    timed_out = False
    max_att = cfg.get("max_attempts", BASE_MAX_ATTEMPTS)
    hold = cfg.get("rubric_aware_stop") and final_step_hopeless(task, cfg)
    while attempts < max_att:
        attempts += 1
        pts, used, ok, _ = attempt(task, axis, cfg, rng, budget, lat_median)
        best = max(best, pts)
        last = pts
        budget -= used
        if ok:
            return True, pts, attempts, False
        if hold:
            break                                    # protect partial credit
        if budget <= TIMEOUT_S * RETRY_MIN_BUDGET_FRAC:
            timed_out = True
            break
    return False, (best if hold else last), attempts, timed_out


def aggregate(cfg, lat_median, tasks, seeds=8):
    per_task = []
    to_rate = 0
    att_avg = 0
    n_ep = 0
    plan = axis_plan()
    for task in tasks:
        succ = 0
        stepsum = 0
        atts = 0
        for run in range(N_RUNS):
            axis = plan[run]
            for s in range(seeds):
                rng = random.Random(abs(hash((task["id"], axis, run, s, cfg.get("tag", "")))) % (2 ** 31))
                ok, pts, att, to = run_episode(task, axis, cfg, rng, lat_median)
                succ += 1 if ok else 0
                stepsum += pts
                atts += att
                to_rate += 1 if to else 0
                att_avg += att
                n_ep += 1
        per_task.append({"id": task["id"], "name": task["name"],
                         "success": succ / (N_RUNS * seeds),
                         "step_score": stepsum / (N_RUNS * seeds),
                         "attempts": atts / (N_RUNS * seeds)})
    return {"avg_success": sum(t["success"] for t in per_task) / len(per_task),
            "avg_step_score": sum(t["step_score"] for t in per_task) / len(per_task),
            "timeout_rate": to_rate / n_ep,
            "avg_attempts": att_avg / n_ep,
            "per_task": per_task}


def calibrate(tasks, target, lat_median):
    lo, hi = 0.10, 3.0
    orig = dict(DIFF_Q)
    for _ in range(28):
        mid = 0.5 * (lo + hi)
        for k in DIFF_Q:
            DIFF_Q[k] = min(0.99, orig[k] * mid)
        r = aggregate({"tag": f"cal{mid:.4f}"}, lat_median, tasks, seeds=2)
        if r["avg_success"] * 100.0 < target:
            lo = mid
        else:
            hi = mid
    DIFF_Q.clear()
    DIFF_Q.update(orig)
    return 0.5 * (lo + hi)


def main():
    global SIM2REAL_DISCOUNT
    data = json.load(open(INPUTS))
    tasks = data["tasks"]
    meta = data["meta"]
    target = meta["leaderboard_avg_success_top1"]
    lat_med = 0.5
    s = calibrate(tasks, target, lat_med)
    for k in DIFF_Q:
        DIFF_Q[k] = min(0.99, DIFF_Q[k] * s)

    results = {"calibration_scale": round(s, 4), "lat_median_s": lat_med,
               "target_success": target, "configs": {}, "sweep": {}, "sensitivity": {},
               "per_task_base": None, "per_task_all": None}

    configs = {
        "base": {},
        "axis_compiler": {"axis_compiler": True},
        "perturb_recovery": {"perturb_recovery": True},
        "rubric_aware_stop": {"rubric_aware_stop": True},
        "cloud_edge_N3": {"cloud_edge": True, "ports": 3},
        "all": {"axis_compiler": True, "perturb_recovery": True,
                "rubric_aware_stop": True, "cloud_edge": True, "ports": 3},
    }
    for name, extra in configs.items():
        cfg = dict(extra)
        cfg["tag"] = name
        r = aggregate(cfg, lat_med, tasks, seeds=10)
        results["configs"][name] = {k: v for k, v in r.items() if k != "per_task"}
        if name == "base":
            results["per_task_base"] = r["per_task"]
        if name == "all":
            results["per_task_all"] = r["per_task"]

    for lat in (0.2, 0.5, 1.0, 2.0):
        for ports in (1, 3):
            row = {}
            for name in ("base", "cloud_edge_N3", "all"):
                cfg = dict(configs[name])
                cfg["tag"] = f"{name}_l{lat}_p{ports}"
                if "ports" in cfg:
                    cfg["ports"] = ports
                r = aggregate(cfg, lat, tasks, seeds=5)
                row[name] = {"avg_success": round(r["avg_success"], 4),
                             "avg_step_score": round(r["avg_step_score"], 2),
                             "timeout_rate": round(r["timeout_rate"], 4),
                             "avg_attempts": round(r["avg_attempts"], 3)}
            results["sweep"][f"lat_{lat}_ports_{ports}"] = row

    for disc in (0.3, 0.6, 0.9):
        SIM2REAL_DISCOUNT = disc
        cfg = dict(configs["all"])
        cfg["tag"] = f"disc{disc}"
        r = aggregate(cfg, lat_med, tasks, seeds=5)
        results["sensitivity"][f"sim2real_discount_{disc}"] = {
            "avg_success": round(r["avg_success"], 4),
            "avg_step_score": round(r["avg_step_score"], 2)}

    json.dump(results, open(OUT, "w"), indent=1)
    print("calibration scale =", round(s, 4), "(baseline now reproduces the observed top-1 success rate)")
    print()
    print(f"{'config':<18}{'success':>9}{'step':>8}{'timeout':>9}{'attempts':>10}   deltas")
    b = results["configs"]["base"]
    for name in configs:
        c = results["configs"][name]
        print(f"{name:<18}{c['avg_success']*100:8.2f}%{c['avg_step_score']:8.2f}"
              f"{c['timeout_rate']*100:8.2f}%{c['avg_attempts']:10.2f}"
              f"   d_succ={100*(c['avg_success']-b['avg_success']):+.2f}pp"
              f" d_step={c['avg_step_score']-b['avg_step_score']:+.2f}")
    print()
    print(f"{'lat/ports':<18}{'base succ':>11}{'edge succ':>11}{'all succ':>10}"
          f"{'base step':>11}{'all step':>10}{'base TO':>9}{'all TO':>8}")
    for k, v in results["sweep"].items():
        print(f"{k:<18}{v['base']['avg_success']*100:10.2f}%{v['cloud_edge_N3']['avg_success']*100:10.2f}%"
              f"{v['all']['avg_success']*100:9.2f}%{v['base']['avg_step_score']:11.2f}"
              f"{v['all']['avg_step_score']:10.2f}{v['base']['timeout_rate']*100:8.2f}%"
              f"{v['all']['timeout_rate']*100:7.2f}%")
    print()
    print("sim2real discount sensitivity (all levers):")
    for k, v in results["sensitivity"].items():
        print(f"  {k:<28} success={v['avg_success']*100:.2f}%  step={v['avg_step_score']:.2f}")
    print()
    print("worst 8 tasks by leaderboard baseline success (base -> all):")
    pt = {t["id"]: t for t in results["per_task_base"]}
    pa = {t["id"]: t for t in results["per_task_all"]}
    for t in sorted(results["per_task_base"], key=lambda x: x["success"])[:8]:
        a = pt[t["id"]]
        c = pa[t["id"]]
        print(f"  {t['id']} {t['name']:<20} succ {a['success']*100:5.1f}% -> {c['success']*100:5.1f}%"
              f"   step {a['step_score']:5.1f} -> {c['step_score']:5.1f}")


if __name__ == "__main__":
    main()
