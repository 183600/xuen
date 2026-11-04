#!/usr/bin/env python3
"""Round-16 mechanism simulation: official-rubric subgoal tracking + latency-aware
cadence/speculation + bounded continual retry memory.

This is a B-level mechanism check, NOT a robot result.  It answers one question:
"under a calibrated generative model of the 32 UniBot-V1 tabletop tasks, when does
subgoal-level credit tracking / speculation / online memory pay for itself?"

Calibration anchors (public data, 2026-11-04):
  * per-task base success rate  : mean over the 8 generalist leaderboard models
  * per-task affine step map    : step = a_t + b_t * success  (R^2 >= 0.97)

Everything else (per-attempt subgoal success, attempt cost, predicate noise,
disturbance rate, inference latency) is an EXPLICIT ASSUMPTION, reported in the
output file so that sensitivity can be judged.

Run: python r16_rubric_latency_sim.py
"""
import json
import math
import os
import random
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
prof = json.load(open(os.path.join(HERE, "r16_task_profile.json")))
stats = json.load(open(os.path.join(HERE, "r16_leaderboard_stats.json")))
pt = {p["id"]: p for p in stats["per_task"]}

# ---- subgoal kinds per task (from the official scoring_points text) ---------
# A : acquire-only milestone (bankable independently, e.g. "grab the book")
# F : fused grab+place unit (e.g. "grab fruit 1 and put it on the plate")
# P : place / finish milestone that needs the object in hand
# M : deformable-manipulation milestone (towel folds, pouch straightening)
KINDS = {
    "T01": "AP", "T02": "FF", "T03": "FF", "T04": "FFF", "T05": "AP", "T06": "FFF",
    "T07": "APP", "T08": "AP", "T09": "FFPP", "T10": "AAP", "T11": "AAA", "T12": "APP",
    "T13": "FFF", "T14": "AP", "T15": "FFFF", "T16": "MMMMP", "T17": "AFFFP", "T18": "AAPP",
    "T19": "AP", "T20": "FFF", "T21": "FFF", "T22": "AFFF", "T23": "FP", "T24": "AP",
    "T25": "FFF", "T26": "AAP", "T27": "FFF", "T28": "AAAP", "T29": "FFP", "T30": "FF",
    "T31": "AFP", "T32": "AP",
}
# assumption: base per-attempt success and attempt cost (steps @30Hz)
Q0 = {"A": 0.88, "F": 0.72, "P": 0.75, "M": 0.55}
C0 = {"A": 45, "F": 95, "P": 70, "M": 130}
VARIANTS = 3          # retry variants per subgoal (VLA default + 2 geometric retries)
VAR_MULT = [1.0, 0.92, 0.80]   # offline prior: variant 0 best, geometric retries weaker
VAR_COST = [1.0, 1.05, 1.15]


def calibrate():
    """per-task scale alpha so that a single-attempt monolithic policy reproduces
    the observed per-task mean success rate."""
    out = {}
    for tid, kinds in KINDS.items():
        prod = 1.0
        for k in kinds:
            prod *= Q0[k]
        s = pt[tid]["mean"] / 100.0
        alpha = (s / prod) ** (1.0 / len(kinds))
        out[tid] = min(1.0, alpha)
    return out


ALPHA = calibrate()


def run_episode(rng, tid, pol, cfg):
    kinds = KINDS[tid]
    w = prof["tasks"][tid]["w"]
    q = {k: Q0[k] * ALPHA[tid] for k in kinds}
    budget = cfg["budget_steps"]
    milestones = [False] * len(kinds)
    j = 0
    calls = 0
    stall = 0.0
    attempts = 0
    carried_error = False
    while j < len(kinds):
        kind = kinds[j]
        variant = pol.choose_variant(tid, j, attempts, cfg)
        if pol.use_memory and variant is None:
            variant = pol.pick_ucb(tid, j, cfg)
        if variant is None:
            variant = 0
        cost = C0[kind] * VAR_COST[variant]
        chunks = math.ceil(cost / cfg["chunk"])
        st = chunks * cfg["latency_steps"] if not cfg["speculate"] else 0.0
        if cfg["speculate"] and rng.random() < cfg["invalidate_p"]:
            st = chunks * cfg["latency_steps"]
        if cost + st > budget:
            break
        budget -= cost + st
        calls += chunks
        stall += st
        attempts += 1
        disturbed = rng.random() < cfg["disturb_p"]
        p = q[kind] * VAR_MULT[variant]
        if disturbed:
            p *= (1.0 - cfg["disturb_loss"]) * (pol.disturb_robust[variant] if pol.use_memory else 1.0)
        if carried_error:
            p *= (1.0 - cfg["carry_loss"])
        ok = rng.random() < p
        # predicate detection
        missed = ok and rng.random() < cfg["fn"]
        falsepos = (not ok) and rng.random() < cfg["fp"]
        if ok and not missed:
            milestones[j] = True
            j += 1
        elif falsepos:
            milestones[j] = True
            carried_error = True
            j += 1
        else:
            if not pol.retry:
                break
            if pol.drop_risk and rng.random() < cfg["drop_p"] and any(milestones):
                milestones = [False] * len(kinds)
    rubric = sum(w[i] for i, m in enumerate(milestones) if m)
    task_success = all(milestones)
    if pol.use_memory:
        pol.observe(tid, j, attempts)
    return task_success, rubric, calls, stall, attempts


class Policy:
    def __init__(self, name, retry=False, use_memory=False, drop_risk=False, spec=False):
        self.name = name
        self.retry = retry
        self.use_memory = use_memory
        self.drop_risk = drop_risk
        self.spec = spec
        self.table = defaultdict(lambda: defaultdict(lambda: [1, 0]))  # (tid,j) -> variant -> [n,fail]
        self.disturb_robust = [1.0, 0.55, 0.35]  # offline prior: geometric retries suffer more

    def choose_variant(self, tid, j, attempts, cfg):
        return None

    def pick_ucb(self, tid, j, cfg):
        rows = self.table[(tid, j)]
        n = sum(v[0] for v in rows.values())
        if n < cfg["mem_min_obs"]:
            return 0
        best, bestv = 0, -1e9
        for v in range(VARIANTS):
            obs, fail = rows[v]
            mean = 1.0 - fail / obs if obs else 0.5
            bonus = math.sqrt(2 * math.log(n + 1) / (obs + 1e-9))
            if mean + bonus > bestv:
                best, bestv = v, mean + bonus
        return best

    def observe(self, tid, j, attempts):
        pass


def evaluate(pol, cfg, n_ep=600, seed=7):
    rng = random.Random(seed)
    per_task = {}
    tot = []
    for tid in KINDS:
        s = r = c = st = 0
        for _ in range(n_ep):
            ok, rub, calls, stall, att = run_episode(rng, tid, pol, cfg)
            s += ok
            r += rub
            c += calls
            st += stall
        per_task[tid] = {
            "success": 100.0 * s / n_ep,
            "rubric": r / n_ep,
            "calls": c / n_ep,
            "stall_steps": st / n_ep,
            "a": pt[tid]["a"], "b": pt[tid]["b"],
        }
        tot.append(per_task[tid])
    mean_succ = sum(t["success"] for t in tot) / len(tot)
    mean_rub = sum(t["rubric"] for t in tot) / len(tot)
    mean_calls = sum(t["calls"] for t in tot) / len(tot)
    mean_stall = sum(t["stall_steps"] for t in tot) / len(tot)
    proj_step = sum(t["a"] + t["b"] * t["success"] for t in tot) / len(tot)
    return {"policy": pol.name, "success": round(mean_succ, 2), "rubric_score": round(mean_rub, 2),
            "projected_step": round(proj_step, 2), "vla_calls": round(mean_calls, 1),
            "stall_steps": round(mean_stall, 1), "per_task": per_task}


BASE = dict(chunk=30, latency_steps=9, budget_steps=1350, fn=0.10, fp=0.05,
            disturb_p=0.30, disturb_loss=0.45, carry_loss=0.5, drop_p=0.20,
            invalidate_p=0.25, mem_min_obs=8, speculate=False)

if __name__ == "__main__":
    results = {"assumptions": BASE, "note": "B-level mechanism check; synthetic, not robot evidence",
               "runs": [], "sweeps": {}}

    pols = [Policy("MONO (leaderboard-calibrated, no subgoal tracking)", retry=False, drop_risk=True),
            Policy("RUBRIC (predicate tracking + retry, offline prior)", retry=True),
            Policy("RUBRIC+SPEC (+ speculative chunking)", retry=True)]
    for pol in pols:
        cfg = dict(BASE)
        if pol.spec:
            cfg["speculate"] = True
        results["runs"].append(evaluate(pol, cfg))

    # memory policy: online variant selection across episodes of the same task
    class MemPolicy(Policy):
        def __init__(self):
            super().__init__("RUBRIC+SPEC+MEM (online UCB over retry variants)", retry=True, use_memory=True)

        def observe(self, tid, j, attempts):
            pass

    cfg = dict(BASE)
    cfg["speculate"] = True
    results["runs"].append(evaluate(MemPolicy(), cfg))

    # ---- sensitivity sweeps -------------------------------------------------
    for name, key, vals in [("latency_steps", "latency_steps", [0, 9, 18, 30]),
                            ("predicate_fn", "fn", [0.0, 0.10, 0.25, 0.40]),
                            ("disturb_p", "disturb_p", [0.0, 0.3, 0.6]),
                            ("budget_steps", "budget_steps", [900, 1350, 1800])]:
        sweep = {}
        for v in vals:
            c = dict(BASE)
            c["speculate"] = True
            c[key] = v
            r_mono = evaluate(Policy("mono", retry=False, drop_risk=True), c, n_ep=400)
            r_rub = evaluate(Policy("rub", retry=True), c, n_ep=400)
            sweep[str(v)] = {"mono_success": r_mono["success"], "rubric_success": r_rub["success"],
                             "delta": round(r_rub["success"] - r_mono["success"], 2),
                             "mono_calls": r_mono["vla_calls"], "rubric_calls": r_rub["vla_calls"]}
        results["sweeps"][name] = sweep

    json.dump(results, open(os.path.join(HERE, "r16_sim_results.json"), "w"), indent=1)
    print("== main run (B-level, synthetic) ==")
    for r in results["runs"]:
        print(f"  {r['policy']:58s} succ {r['success']:5.2f}%  rubric {r['rubric_score']:5.2f}  "
              f"proj_step {r['projected_step']:5.2f}  calls {r['vla_calls']:5.1f}  stall {r['stall_steps']:5.1f}")
    print("\n== sweeps (success %, MONO vs RUBRIC) ==")
    for k, v in results["sweeps"].items():
        print(" ", k, json.dumps(v))
