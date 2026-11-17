#!/usr/bin/env python3
"""Round-2 (UniBot line) mechanism checks for the "competition strategy x
endurance" round.

These are toy/decision-theory checks, NOT robot results.  They use the
transcribed public UniBot-V1 teaser leaderboard (8 models x 32 tasks,
success rate in percent) as a *plausible field*, and answer four questions:

  A. How noisy is a rank built from n Bernoulli trials per task?
  B. When is increasing variance a winning move (underdog vs favourite)?
  C. How should scarce evaluation trials be split across tasks (Neyman vs
     uniform, plus a swing-task bonus)?
  D. How much does late-phase hazard / recovery cost under a fixed episode
     budget?

Run: python exp/racer_sim.py > exp/racer_results.json
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import numpy as np

EXP = Path("/home/runner/work/xuen/xuen/workspace/exp")
LB = json.loads((EXP / "lb_2026_11_04.json").read_text())
MODELS = [m["model_name"] for m in LB["models"]]
M = np.array([m["per_task"] for m in LB["models"]], dtype=float) / 100.0  # (8,32)
N_MODEL, N_TASK = M.shape
PUBLISHED = np.array([m["avg_success_rate"] for m in LB["models"]]) / 100.0


def rank_of(scores: np.ndarray) -> np.ndarray:
    """scores: (..., K) -> ranks (1 = best) along last axis."""
    order = np.argsort(-scores, axis=-1)
    ranks = np.empty_like(order)
    np.put_along_axis(ranks, order, np.arange(1, scores.shape[-1] + 1), axis=-1)
    return ranks


def part_a(rng: np.random.Generator, reps: int = 4000):
    best = int(np.argmax(PUBLISHED))
    out = {"true_best": MODELS[best], "true_best_mean": round(float(PUBLISHED[best]), 4),
           "trials_per_task": {}}
    for n in [1, 2, 4, 8, 16, 32, 64, 128, 256]:
        # (reps, 8, 32) binomial draws
        draws = rng.binomial(n, M[None, :, :], size=(reps, N_MODEL, N_TASK)) / n
        S = draws.mean(axis=2)                      # (reps, 8)
        R = rank_of(S)                              # (reps, 8)
        r_best = R[:, best]
        obs_win = np.argmax(S, axis=1)
        # how often does the observed champion have a worse *true* mean than best?
        false_champ = float(np.mean(PUBLISHED[obs_win] < PUBLISHED[best] - 1e-9))
        out["trials_per_task"][str(n)] = {
            "P_true_best_rank1": round(float(np.mean(r_best == 1)), 4),
            "P_true_best_top3": round(float(np.mean(r_best <= 3)), 4),
            "E_rank_true_best": round(float(np.mean(r_best)), 3),
            "P_false_champion": round(false_champ, 4),
            "sd_of_observed_score_pp": round(float(100 * np.std(S[:, best])), 2),
        }
    return out


def part_b():
    """P(beat leader) for Gaussian scores; leader mean = published best.
    Analytic + multi-submission (max of k independent draws)."""
    mu_l = float(PUBLISHED.max())
    sd_l = 0.005  # 0.5 pp leader uncertainty
    out = {"leader_mean": round(mu_l, 4), "leader_sd": sd_l, "grid": [],
           "crossover_mean": round(mu_l, 4), "submission_value": {}}

    def phi(x):
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    for mu in [0.27, 0.28, 0.29, 0.297, 0.30, 0.31, 0.32]:
        row = {"mu": round(mu, 4), "P_beat": {}}
        for sd in [0.0025, 0.005, 0.010, 0.015, 0.020]:
            p = phi((mu - mu_l) / math.sqrt(sd * sd + sd_l * sd_l))
            row["P_beat"][f"{sd:.4f}"] = round(p, 4)
        out["grid"].append(row)

    # underdog (28.7) vs favourite (30.7): value of k independent submissions
    for tag, mu in [("underdog", 0.287), ("favourite", 0.307)]:
        p1 = phi((mu - mu_l) / math.sqrt(0.010 ** 2 + sd_l ** 2))
        out["submission_value"][tag] = {
            "mu": round(mu, 4), "p_one": round(p1, 4),
            "p_best_of": {str(k): round(1 - (1 - p1) ** k, 4) for k in [1, 2, 3, 4]},
        }
    return out


def part_c():
    """Split N evaluation trials across tasks: uniform vs Neyman vs Neyman+cost.
    Neyman minimises Var(mean) = (1/32^2) * sum v_i / n_i, v_i = p(1-p)."""
    p = M.mean(axis=0)
    v = p * (1 - p)
    # representative per-task episode cost (normalised); unknown, use a mild spread
    cost = 0.9 + 0.2 * np.linspace(0, 1, N_TASK)
    out = {"per_task_p": [round(float(x), 4) for x in p],
           "variance_ratio_vs_uniform": {}}
    for N in [64, 128, 256, 512, 1024]:
        n_uni = np.full(N_TASK, N / N_TASK)
        var_uni = float(np.sum(v / n_uni) / N_TASK ** 2)
        # Neyman: n_i proportional to sqrt(v_i)
        w = np.sqrt(v)
        n_ney = N * w / w.sum()
        var_ney = float(np.sum(v / n_ney) / N_TASK ** 2)
        # cost-aware Neyman: n_i proportional to sqrt(v_i / c_i)
        wc = np.sqrt(v / cost)
        n_c = N * wc / wc.sum()
        var_c = float(np.sum(v / n_c) / N_TASK ** 2)
        out["variance_ratio_vs_uniform"][str(N)] = {
            "uniform_sd_pp": round(100 * math.sqrt(var_uni), 3),
            "neyman_sd_pp": round(100 * math.sqrt(var_ney), 3),
            "cost_aware_sd_pp": round(100 * math.sqrt(var_c), 3),
            "neyman_var_ratio": round(var_ney / var_uni, 4),
            "cost_aware_var_ratio": round(var_c / var_uni, 4),
            "max_min_trial_ratio": round(float(np.max(n_ney) / np.min(n_ney)), 3),
        }
    # swing tasks for the top-1 vs top-2 model: smallest per-task gaps
    top2 = np.argsort(-PUBLISHED)[:2]
    gap = M[top2[0]] - M[top2[1]]
    order = np.argsort(np.abs(gap))
    out["top2_gap"] = {
        "models": [MODELS[top2[0]], MODELS[top2[1]]],
        "swing_tasks": [
            {"task": LB["tasks"][int(i)], "gap_pp": round(100 * float(gap[i]), 2)}
            for i in order[:6]
        ],
        "safe_tasks": [
            {"task": LB["tasks"][int(i)], "gap_pp": round(100 * float(gap[i]), 2)}
            for i in order[-4:]
        ],
    }
    return out


def part_d(rng: random.Random, reps: int = 40000):
    """Fixed episode budget with per-phase cost and recovery.

    Baseline: phases succeed independently; episode fails at first failed phase.
    Proposed: on failure, with prob q a recovery attempt is allowed (bounded by
    retries and by remaining step budget).  We compare concentrating the same
    total hazard early vs late, and report the value of recovery.
    """
    K = 8
    cost = [1.0] * K

    def run(hazards, q, retries, rep, budget):
        ok = 0
        for _ in range(rep):
            spent = 0.0
            alive = True
            for j in range(K):
                if spent + cost[j] > budget:
                    alive = False
                    break
                spent += cost[j]
                tries = 0
                while rng.random() < hazards[j]:  # failed this attempt
                    if tries >= retries or spent + cost[j] > budget:
                        alive = False
                        break
                    if rng.random() > q:  # recovery attempt fails to help
                        alive = False
                        break
                    tries += 1
                    spent += cost[j]
                if not alive:
                    break
            ok += int(alive)
        return ok / rep

    total_h = 0.12
    # same product-ish total hazard, equally spread vs late-concentrated
    h_even = [1 - (1 - total_h) ** (1 / K)] * K
    late = [0.002] * (K - 1) + [1 - (1 - total_h) / (0.998 ** (K - 1))]
    early = [1 - (1 - total_h) / (0.998 ** (K - 1))] + [0.002] * (K - 1)
    out = {"nominal_steps": K, "total_hazard": total_h, "budgets": {}}
    for budget in [8.6, 11.0]:
        no_rec = {k: round(run(v, 0.0, 0, reps, budget), 4)
                  for k, v in [("even", h_even), ("late", late), ("early", early)]}
        rec = {k: round(run(v, 0.6, 2, reps, budget), 4)
               for k, v in [("even", h_even), ("late", late), ("early", early)]}
        out["budgets"][f"{budget:.1f}"] = {
            "reserve_ratio": round((budget - K) / K, 3),
            "no_recovery": no_rec,
            "with_recovery_q0.6_r2": rec,
            "recovery_gain_late_pp": round(100 * (rec["late"] - no_rec["late"]), 2),
            "recovery_gain_even_pp": round(100 * (rec["even"] - no_rec["even"]), 2),
        }
    return out


def part_f():
    """Paired vs unpaired A/B when a session-level nuisance u ~ N(0, su^2)
    shifts every episode of a run (lighting / object layout / robot state).

    With E_total episodes per arm and E_run = 32 (one trial per task) per run:
      unpaired var = V/(32 E_total) + 2 su^2 E_run / E_total
      paired   var = V/(32 E_total)          (same session, u cancels)
    Report the episode ratio unpaired/paired needed to detect delta at z=1.96.
    """
    p = M.mean(axis=0)
    V = float(np.sum(p * (1 - p)))
    z = 1.96
    out = {"V_sum_pq": round(V, 3), "episodes_per_run": 32, "ratio": {}}
    for d in [0.02, 0.03, 0.05]:
        row = {}
        e_paired = z * z * V / (N_TASK * d * d)
        for su in [0.02, 0.05, 0.10]:
            e_unpaired = z * z * (V / N_TASK + 2 * su * su * 32) / (d * d)
            row[f"session_sd_{int(su*100)}pp"] = {
                "paired_episodes": int(round(e_paired)),
                "unpaired_episodes": int(round(e_unpaired)),
                "ratio": round(e_unpaired / e_paired, 2),
            }
        out["ratio"][f"{d*100:.0f}pp"] = row
    return out


def part_e():
    """Detection budget: episodes E needed to resolve a true mean gain delta at
    z=1.96.  Var(score) = sum_i v_i / (32^2 * n_i); with equal n_i=E/32 this is
    V/(32*E), V=sum v_i.  So E = z^2 V / (32 delta^2)."""
    p = M.mean(axis=0)
    V = float(np.sum(p * (1 - p)))
    out = {"V_sum_pq": round(V, 3), "episode_sec": 45.0, "battery_h": 2.0,
           "n_robots": 3, "charges_per_robot_day": 1.0, "needed": {}}
    for d in [0.01, 0.02, 0.03, 0.05, 0.10]:
        E = (1.96 ** 2 * V) / (N_TASK * d * d)
        hours = E * 45.0 / 3600.0
        out["needed"][f"{d*100:.0f}pp"] = {
            "episodes": int(round(E)),
            "robot_hours": round(hours, 1),
            "battery_charges": round(hours / 2.0, 1),
            "days_3robots_1charge": round(hours / (3 * 2.0), 1),
        }
    return out


def main():
    rng = np.random.default_rng(20261117)
    rb = random.Random(20261117)
    out = {
        "source": LB.get("_source"),
        "note": "toy decision-theory checks on the transcribed teaser field; not robot results",
        "n_models": N_MODEL, "n_tasks": N_TASK,
        "published_mean_pp": [round(100 * x, 2) for x in PUBLISHED],
        "best_single_pp": round(100 * float(PUBLISHED.max()), 2),
        "mean_single_pp": round(100 * float(PUBLISHED.mean()), 2),
        "per_task_oracle_pp": round(100 * float(M.max(axis=0).mean()), 2),
        "A_rank_noise": part_a(rng),
        "B_variance_direction": part_b(),
        "C_eval_allocation": part_c(),
        "D_endurance_hazard": part_d(rb),
        "E_detection_budget": part_e(),
        "F_paired_design": part_f(),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
