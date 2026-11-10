#!/usr/bin/env python3
"""Round-41 probe: data-plane middleware + dataset coverage.

Three arithmetic / measurement questions, all using already-public artifacts:

  Q1 (surrogate-eval sizing)  Given the 32-task leaderboard (8 models), how many
     local evaluation episodes does one need to resolve a 1pp / 2pp difference in
     average success?  Compare uniform vs Neyman (sigma-proportional) allocation.
     Inputs: exp/r16_leaderboard_stats.json (fetched 2026-11-04).

  Q2 (dataset coverage gap)  Using the public 32-task profile (rubric, difficulty,
     unseen-object note, human-perturbation note, episode count), what predicts a
     task's leaderboard headroom?  Produce a gap-driven acquisition weight.
     Inputs: exp/r16_task_profile.json, exp/r16_leaderboard_stats.json.

  Q3 (retrieval data-plane feasibility)  On cached real UniBot rows (proprio +
     action, 14 tasks x ~3k frames), how well does nearest-neighbour observation
     retrieval from *other episodes* predict the next action chunk, versus
     zero-order hold?  This is the empirical premise for a retrieval/cache
     middleware.  Inputs: exp/duo_rows_cache/*.json (HF datasets-server rows,
     retrieved 2026-11-02).

No modelling story is allowed to override these numbers; every claim in the
round-41 artifact cites a field of the emitted JSON.
"""
import glob
import json
import os
import statistics as st
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(HERE)
OUT = os.path.join(HERE, "dataplane_probe.json")

# ---------------------------------------------------------------- Q1 ----------
def q1_surrogate_sizing():
    lb = json.load(open(os.path.join(EXP, "r16_leaderboard_stats.json")))
    prof = json.load(open(os.path.join(EXP, "r16_task_profile.json")))["tasks"]
    eps = {k: v["eps"] for k, v in prof.items()}
    tasks = lb["per_task"]
    # p_t: per-task mean success across the 8 public models / 100.
    p = np.array([t["mean"] / 100.0 for t in tasks])
    sigma = np.sqrt(p * (1 - p))
    n_tasks = len(tasks)

    # Stratified estimator of the unweighted task-mean: Var = (1/T^2) sum s_t^2/n_t.
    def se_pct(n):
        var = np.sum(sigma ** 2 / np.asarray(n, dtype=float)) / n_tasks ** 2
        return 100.0 * np.sqrt(var)

    rows = []
    for per_task in (5, 10, 20, 40, 80, 160):
        M = per_task * n_tasks
        uniform = np.full(n_tasks, per_task, dtype=float)
        neyman = sigma / sigma.sum() * M
        # enforce the same integer budget by rounding the Neyman allocation
        neyman_i = np.floor(neyman).astype(int)
        neyman_i[: M - neyman_i.sum()] += 1
        se_u, se_n = se_pct(uniform), se_pct(neyman_i)
        rows.append({
            "M_episodes": int(M),
            "uniform_per_task": per_task,
            "se_uniform_pp": round(se_u, 3),
            "se_neyman_pp": round(se_n, 3),
            "two_model_diff_95pp": round(1.96 * np.sqrt(2) * se_u, 2),
            "variance_reduction_pct": round(100 * (1 - se_n ** 2 / se_u ** 2), 1),
        })

    # M needed for a target SE under Neyman (continuous solution) and delta detection
    # For a two-sided 95% CI of a difference, SE_diff ~ sqrt(2)*SE; detect delta if
    # delta >= 1.96*sqrt(2)*SE  ->  SE <= delta/(1.96*sqrt(2)).
    def M_for_se(target_se_frac):
        # SE^2 = (1/T^2) * (sum sigma)^2 / M  for Neyman
        return (sigma.sum() ** 2) / ((n_tasks * target_se_frac) ** 2)

    targets = {}
    for d in (0.5, 1.0, 2.0):
        se_req = (d / 100.0) / (1.96 * np.sqrt(2))
        targets[f"detect_{d}pp"] = {
            "required_SE_pp": round(100 * se_req, 3),
            "M_neyman": int(np.ceil(M_for_se(se_req))),
        }
    return {
        "per_task_success_proxy_mean_range_pct": [round(100 * p.min(), 2), round(100 * p.max(), 2)],
        "sigma_range": [round(float(sigma.min()), 4), round(float(sigma.max()), 4)],
        "sigma_cv": round(float(sigma.std() / sigma.mean()), 4),
        "allocation_curve": rows,
        "detection_budget": targets,
        "task_sigma_weights_top5": sorted(
            [{"id": t["id"], "task": t["task"], "p_pct": round(100 * pi, 2),
              "sigma": round(float(si), 4)} for t, pi, si in zip(tasks, p, sigma)],
            key=lambda x: -x["sigma"])[:5],
        "episodes_corr_sigma": round(float(np.corrcoef(
            [eps[t["id"]] for t in tasks], sigma)[0, 1]), 4),
    }


# ---------------------------------------------------------------- Q2 ----------
def q2_coverage_gap():
    lb = json.load(open(os.path.join(EXP, "r16_leaderboard_stats.json")))
    prof = json.load(open(os.path.join(EXP, "r16_task_profile.json")))["tasks"]
    rows = []
    for t in lb["per_task"]:
        pr = prof[t["id"]]
        rows.append({
            "id": t["id"], "task": t["task"], "difficulty": t["difficulty"],
            "rubric_steps": t["rubric_steps"], "eps": pr["eps"],
            "has_unseen_note": pr["unseen"] is not None,
            "has_human_note": (pr["h1"] is not None) or (pr["h4"] is not None),
            "mean_success_pct": t["mean"], "best_success_pct": t["max"],
            "spread_pp": t["spread"],
        })

    def group(keyfn):
        g = defaultdict(list)
        for r in rows:
            g[keyfn(r)].append(r)
        return {k: {
            "n": len(v),
            "mean_success_pct": round(st.mean(x["mean_success_pct"] for x in v), 2),
            "mean_best_success_pct": round(st.mean(x["best_success_pct"] for x in v), 2),
            "mean_spread_pp": round(st.mean(x["spread_pp"] for x in v), 2),
        } for k, v in g.items()}

    def corr(a, b):
        return round(float(np.corrcoef(a, b)[0, 1]), 4)

    # acquisition weight: headroom x heterogeneity (spread) / prior data mass
    # w_t ~ (100 - mean_t) * spread_t / sqrt(eps_t); rank tasks for self-collection
    w = [(100 - r["mean_success_pct"]) * r["spread_pp"] / np.sqrt(r["eps"]) for r in rows]
    tot = sum(w)
    order = sorted(range(len(rows)), key=lambda i: -w[i])
    top8 = sum(w[i] for i in order[:8]) / tot
    top16 = sum(w[i] for i in order[:16]) / tot
    return {
        "n_tasks": len(rows),
        "by_unseen_note": group(lambda r: r["has_unseen_note"]),
        "by_human_note": group(lambda r: r["has_human_note"]),
        "by_difficulty": group(lambda r: r["difficulty"]),
        "corr_mean_success_vs_spread": corr(
            [r["mean_success_pct"] for r in rows], [r["spread_pp"] for r in rows]),
        "corr_mean_success_vs_rubric_steps": corr(
            [r["mean_success_pct"] for r in rows], [r["rubric_steps"] for r in rows]),
        "corr_mean_success_vs_episodes": corr(
            [r["mean_success_pct"] for r in rows], [r["eps"] for r in rows]),
        "corr_spread_vs_episodes": corr(
            [r["spread_pp"] for r in rows], [r["eps"] for r in rows]),
        "acquisition_weight_top8_mass": round(top8, 3),
        "acquisition_weight_top16_mass": round(top16, 3),
        "acquisition_weight_top8": [
            {"id": rows[i]["id"], "task": rows[i]["task"],
             "weight_share_pct": round(100 * w[i] / tot, 2),
             "mean_success_pct": rows[i]["mean_success_pct"],
             "spread_pp": rows[i]["spread_pp"]}
            for i in order[:8]
        ],
        "episodes_range": [min(r["eps"] for r in rows), max(r["eps"] for r in rows)],
    }


# ---------------------------------------------------------------- Q3 ----------
OBS_FIELDS = (["observation.state.left_arm", "observation.state.right_arm"]
              + ["observation.state.left_gripper", "observation.state.right_gripper"])
ACT_FIELDS = (["action.left_arm", "action.right_arm"]
              + ["action.left_gripper", "action.right_gripper"])


def _task_frames(task):
    frames = []
    for page in glob.glob(os.path.join(EXP, "duo_rows_cache", f"{task}_*.json")):
        d = json.load(open(page))
        for item in d.get("rows", []):
            frames.append(item["row"])
    if not frames:
        return None
    # dedupe on the HF row index (pages can overlap at boundaries)
    seen = {}
    for r in frames:
        seen[int(r["index"])] = r
    frames = [seen[k] for k in sorted(seen)]
    frames.sort(key=lambda r: (int(r["episode_index"]), int(r["frame_index"])))
    return frames


def _vec(row, fields):
    out = []
    for f in fields:
        v = row[f]
        if isinstance(v, list):
            out.extend(v)
        else:
            out.append(v)
    return np.asarray(out, dtype=np.float64)


def q3_retrieval(k=8):
    tasks = sorted({os.path.basename(f).rsplit("_", 1)[0]
                    for f in glob.glob(os.path.join(EXP, "duo_rows_cache", "*.json"))})
    per_task = {}
    for task in tasks:
        frames = _task_frames(task)
        if frames is None or len(frames) < 200:
            continue
        ep = np.array([int(r["episode_index"]) for r in frames])
        O = np.vstack([_vec(r, OBS_FIELDS) for r in frames])
        A = np.vstack([_vec(r, ACT_FIELDS) for r in frames])
        # z-score each proprio/action dimension within the task
        osd = O.std(axis=0) + 1e-8
        asd = A.std(axis=0) + 1e-8
        On, An = O / osd, A / asd
        # valid chunk starts: the next k frames stay in the same episode
        valid = np.array([i + k < len(frames) and np.all(ep[i:i + k] == ep[i])
                          for i in range(len(frames))])
        idx = np.where(valid)[0]
        if len(idx) < 50:
            continue
        # queries every 10th valid frame; memory every 2nd valid frame
        q = idx[::10]
        mem = idx[::2]
        # brute-force nearest neighbour in normalized proprio space, excluding the
        # query's own episode so we measure cross-episode (dataset) reuse.
        hits = []
        for qi in q:
            same = ep[mem] == ep[qi]
            d = np.linalg.norm(On[mem] - On[qi], axis=1)
            d = np.where(same, np.inf, d)
            j = int(np.argmin(d))
            if not np.isfinite(d[j]):
                continue
            mi = mem[j]
            true_chunk = An[qi:qi + k]
            ret_chunk = An[mi:mi + k]
            zoh_chunk = np.repeat(An[qi][None, :], k, axis=0)
            ret_rmse = float(np.sqrt(np.mean((ret_chunk - true_chunk) ** 2)))
            zoh_rmse = float(np.sqrt(np.mean((zoh_chunk - true_chunk) ** 2)))
            hits.append({
                "obs_dist": float(d[j]), "ret_rmse": ret_rmse, "zoh_rmse": zoh_rmse,
                "action_dist": float(np.sqrt(np.mean((ret_chunk - true_chunk) ** 2))),
            })
        if not hits:
            continue
        ret = np.array([h["ret_rmse"] for h in hits])
        zoh = np.array([h["zoh_rmse"] for h in hits])
        od = np.array([h["obs_dist"] for h in hits])
        per_task[task] = {
            "n_queries": len(hits),
            "retrieval_rmse_median": round(float(np.median(ret)), 4),
            "zoh_rmse_median": round(float(np.median(zoh)), 4),
            "retrieval_gain_median_pct": round(
                100 * (1 - float(np.median(ret) / np.median(zoh))), 1),
            "retrieval_win_rate": round(float(np.mean(ret < zoh)), 3),
            "obs_dist_median": round(float(np.median(od)), 4),
            # a "cache hit" at the median neighbour distance: the query has a
            # genuinely similar state somewhere in the dataset
            "cache_hit_rate_at_median": round(float(np.mean(od <= np.median(od))), 3),
        }

    if not per_task:
        return {"error": "no cached rows"}
    gains = [v["retrieval_gain_median_pct"] for v in per_task.values()]
    wins = [v["retrieval_win_rate"] for v in per_task.values()]
    return {
        "chunk_len": k,
        "n_tasks": len(per_task),
        "per_task": per_task,
        "median_gain_pct": round(float(np.median(gains)), 1),
        "mean_gain_pct": round(float(np.mean(gains)), 1),
        "median_win_rate": round(float(np.median(wins)), 3),
        "min_gain_pct": round(float(np.min(gains)), 1),
        "max_gain_pct": round(float(np.max(gains)), 1),
    }


def main():
    out = {
        "source_note": "r41 probe; arithmetic on public artifacts (no new downloads)",
        "q1_surrogate_sizing": q1_surrogate_sizing(),
        "q2_coverage_gap": q2_coverage_gap(),
        "q3_retrieval_feasibility": q3_retrieval(k=8),
    }
    with open(OUT, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
