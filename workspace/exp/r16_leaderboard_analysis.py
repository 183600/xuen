"""第 16 轮：UniBot 排行榜结构分析（可复现，B 级证据）

输入：unibot.unitree.com/leaderboard_data.json（2026-11-02 抓取）
输出：exp/r16_leaderboard_stats.json + 控制台表格

分析问题
  Q1 任务难度是否由「共同难度因子」主导？  -> 双因素方差分解 + 模型间相关
  Q2 模型之间是否存在互补专长？            -> 模型×任务交互项占比 + oracle 路由上界
  Q3 步骤分是否只是成功率的线性变换？      -> step_score / success 比值与时长的关系
  Q4 哪些任务对所有模型都难？              -> 跨模型均值与离散度
  Q5 长任务是否更难（多子目标/多阶段）？   -> 任务平均时长 vs 成功率的组间比较
"""
import json
import itertools
import math
import os
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "r16_leaderboard_raw.json")
OUT = os.path.join(HERE, "r16_leaderboard_stats.json")

with open(SRC, encoding="utf-8") as f:
    data = json.load(f)

tasks = data["tasks"]
models = data["models"]
names = [m["model_name"] for m in models]
S = {m["model_name"]: {t["task"]: t["success_rate"] for t in m["task_metrics"]} for m in models}
D = {m["model_name"]: {t["task"]: t["avg_duration_sec"] for t in m["task_metrics"]} for m in models}
K = {m["model_name"]: {t["task"]: t["step_score"] for t in m["task_metrics"]} for m in models}

report = {}

# ---------- Q3: step_score 与 success_rate 的关系 ----------
ratios = []
for m in models:
    for t in m["task_metrics"]:
        if t["success_rate"] > 0:
            ratios.append((m["model_name"], t["task"], t["step_score"] / t["success_rate"],
                           t["avg_duration_sec"], t["success_rate"]))
allr = [x[2] for x in ratios]
# 每个模型整体比值
model_ratio = {m["model_name"]: round(m["avg_step_score"] / m["avg_success_rate"], 4) for m in models}
# 比值与时长的相关（Pearson）
def pearson(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)

ratio_vs_dur = pearson([x[3] for x in ratios], [x[2] for x in ratios])
ratio_vs_succ = pearson([x[4] for x in ratios], [x[2] for x in ratios])

report["Q3_step_score_relation"] = {
    "ratio_mean": round(sum(allr) / len(allr), 4),
    "ratio_std": round(st.pstdev(allr), 4),
    "ratio_min": round(min(allr), 4),
    "ratio_max": round(max(allr), 4),
    "ratio_p05": round(sorted(allr)[int(0.05 * len(allr))], 4),
    "ratio_p95": round(sorted(allr)[int(0.95 * len(allr))], 4),
    "model_level_ratio": model_ratio,
    "corr_ratio_vs_duration": round(ratio_vs_dur, 4),
    "corr_ratio_vs_success": round(ratio_vs_succ, 4),
    "n_pairs": len(allr),
}

# ---------- Q1/Q2: 双因素方差分解 ----------
grand = sum(S[n][t] for n in names for t in tasks) / (len(names) * len(tasks))
row_mean = {n: sum(S[n][t] for t in tasks) / len(tasks) for n in names}
col_mean = {t: sum(S[n][t] for n in names) / len(names) for t in tasks}
ss_tot = sum((S[n][t] - grand) ** 2 for n in names for t in tasks)
ss_task = len(names) * sum((col_mean[t] - grand) ** 2 for t in tasks)
ss_model = len(tasks) * sum((row_mean[n] - grand) ** 2 for n in names)
ss_int = ss_tot - ss_task - ss_model
df_tot, df_task, df_model, df_int = (len(names) * len(tasks) - 1, len(tasks) - 1, len(names) - 1,
                                      (len(names) - 1) * (len(tasks) - 1))
ms_task, ms_model, ms_int = ss_task / df_task, ss_model / df_model, ss_int / df_int
report["Q1_Q2_variance_decomposition"] = {
    "grand_mean_success": round(grand, 3),
    "ss_total": round(ss_tot, 2),
    "share_task_effect": round(ss_task / ss_tot, 4),
    "share_model_effect": round(ss_model / ss_tot, 4),
    "share_interaction": round(ss_int / ss_tot, 4),
    "F_task": round(ms_task / ms_int, 3),
    "F_model": round(ms_model / ms_int, 3),
    "F_interaction": 1.0,
}

# 模型两两相关（跨 32 任务）
def corr(a, b):
    xa = [S[a][t] for t in tasks]
    xb = [S[b][t] for t in tasks]
    return pearson(xa, xb)

corr_pairs = []
for a, b in itertools.combinations(names, 2):
    corr_pairs.append((a, b, round(corr(a, b), 3)))
mean_corr = sum(c[2] for c in corr_pairs) / len(corr_pairs)
# 平均相关矩阵的最小/最大特征值（标准化后的 PCA）
import numpy as np
M = np.array([[S[n][t] for t in tasks] for n in names], dtype=float)
Mc = M - M.mean(axis=1, keepdims=True)
C = np.corrcoef(Mc)
ev = np.linalg.eigvalsh(C)
report["Q1_Q2_variance_decomposition"]["model_pair_corr"] = {
    "pairs": corr_pairs,
    "mean_pairwise_corr": round(mean_corr, 3),
    "corr_matrix_eigenvalues": [round(float(v), 3) for v in ev],
    "first_eig_share": round(float(ev[-1] / ev.sum()), 3),
}

# ---------- Q2: oracle 路由上界 ----------
oracle = sum(max(S[n][t] for n in names) for t in tasks) / len(tasks)
# 随机选一个模型的期望（即榜单平均）
random_pick = grand
# top-2 oracle（两个模型取 max 的平均）
top2 = {}
oracle2 = 0.0
for t in tasks:
    vals = sorted((S[n][t] for n in names), reverse=True)
    oracle2 += (vals[0] + vals[1]) / 2
oracle2 /= len(tasks)
# 每个模型与 oracle 的差距
gap = {n: round(oracle - row_mean[n], 2) for n in names}
report["Q2_oracle_router"] = {
    "leader_avg": round(row_mean[names[0]], 2),
    "oracle_best_per_task": round(oracle, 2),
    "oracle_top2_per_task": round(oracle2, 2),
    "random_pick_expectation": round(random_pick, 2),
    "headroom_vs_leader_pp": round(oracle - row_mean[names[0]], 2),
    "per_model_gap_to_oracle_pp": gap,
}

# ---------- Q4: 任务难度谱 ----------
task_stats = []
for t in tasks:
    vals = [S[n][t] for n in names]
    durs = [D[n][t] for n in names]
    best = max(names, key=lambda n: S[n][t])
    worst = min(names, key=lambda n: S[n][t])
    task_stats.append({
        "task": t,
        "mean": round(sum(vals) / len(vals), 2),
        "min": round(min(vals), 2),
        "max": round(max(vals), 2),
        "spread": round(max(vals) - min(vals), 2),
        "std": round(st.pstdev(vals), 2),
        "mean_duration": round(sum(durs) / len(durs), 1),
        "best_model": best,
        "best_score": round(max(vals), 2),
        "leader_score": round(S[names[0]][t], 2),
    })
task_stats.sort(key=lambda x: x["mean"])
report["Q4_task_difficulty"] = {
    "all": task_stats,
    "universally_hard_mean_lt20": [x["task"] for x in task_stats if x["mean"] < 20],
    "leader_weakest": sorted(
        [{"task": t, "leader": S[names[0]][t]} for t in tasks], key=lambda x: x["leader"])[:8],
    "leader_strongest": sorted(
        [{"task": t, "leader": S[names[0]][t]} for t in tasks], key=lambda x: -x["leader"])[:8],
}

# ---------- Q5: 时长与成功率 ----------
long_tasks = [x for x in task_stats if x["mean_duration"] >= 48]
short_tasks = [x for x in task_stats if x["mean_duration"] < 38]
report["Q5_duration"] = {
    "long_task_count": len(long_tasks),
    "long_task_mean_success": round(sum(x["mean"] for x in long_tasks) / max(1, len(long_tasks)), 2),
    "short_task_count": len(short_tasks),
    "short_task_mean_success": round(sum(x["mean"] for x in short_tasks) / max(1, len(short_tasks)), 2),
    "corr_task_mean_duration_vs_task_mean_success": round(
        pearson([x["mean_duration"] for x in task_stats], [x["mean"] for x in task_stats]), 3),
    "per_task": [{"task": x["task"], "dur": x["mean_duration"], "succ": x["mean"]} for x in task_stats],
}

# ---------- 榜单一致性：排行榜均值 vs 32 任务均值 ----------
recompute = {}
for m in models:
    recompute[m["model_name"]] = round(
        sum(t["success_rate"] for t in m["task_metrics"]) / len(m["task_metrics"]), 3)
report["Q0_integrity"] = {
    "reported_vs_recomputed_avg_success": {
        m["model_name"]: [m["avg_success_rate"], recompute[m["model_name"]]] for m in models},
    "rank_by_reported": [g["model_name"] for g in data["generalist"]],
    "rank_by_recomputed": sorted(recompute, key=lambda n: -recompute[n]),
    "generalist_vs_specialist_counts": {"generalist": len(data["generalist"]),
                                        "specialist": len(data["specialist"])},
    "note": "step_score = k * success_rate 的比例常数在模型间仅 1.30-1.37 波动",
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

# ---------------- 控制台摘要 ----------------
print("== Q0 榜单一致性 ==")
for n, (rep, rec) in report["Q0_integrity"]["reported_vs_recomputed_avg_success"].items():
    print(f"  {n:16s} reported={rep:5.1f} recomputed={rec:6.3f}")
print("  rank reported   :", report["Q0_integrity"]["rank_by_reported"])
print("  rank recomputed :", report["Q0_integrity"]["rank_by_recomputed"])

print("\n== Q1/Q2 方差分解（成功率的 32×8 矩阵）==")
v = report["Q1_Q2_variance_decomposition"]
print(f"  总均值 {v['grand_mean_success']}%  任务效应 {v['share_task_effect']:.1%}  "
      f"模型效应 {v['share_model_effect']:.1%}  交互项 {v['share_interaction']:.1%}")
print(f"  模型两两相关均值 {v['model_pair_corr']['mean_pairwise_corr']}  "
      f"相关矩阵特征值 {v['model_pair_corr']['corr_matrix_eigenvalues']}  "
      f"首特征占比 {v['model_pair_corr']['first_eig_share']}")

print("\n== Q2 oracle 路由上界 ==")
o = report["Q2_oracle_router"]
print(f"  榜首均值 {o['leader_avg']}%  逐任务取最优 {o['oracle_best_per_task']}%  "
      f"top2 平均 {o['oracle_top2_per_task']}%  随机取一模型 {o['random_pick_expectation']}%")
print(f"  相对榜首的专长空间：+{o['headroom_vs_leader_pp']}pp")

print("\n== Q3 步骤分结构 ==")
q3 = report["Q3_step_score_relation"]
print(f"  step/success 比值：mean {q3['ratio_mean']}  std {q3['ratio_std']}  "
      f"[{q3['ratio_min']}, {q3['ratio_max']}]  p05 {q3['ratio_p05']} p95 {q3['ratio_p95']}")
print(f"  corr(比值, 时长) = {q3['corr_ratio_vs_duration']}   corr(比值, 成功率) = {q3['corr_ratio_vs_success']}")
print("  模型级比值：", q3["model_level_ratio"])

print("\n== Q4 任务难度（按 8 模型均值升序，前 8 / 后 5）==")
for x in task_stats[:8]:
    print(f"  {x['task']:26s} mean {x['mean']:5.2f}  spread {x['spread']:5.2f}  "
          f"dur {x['mean_duration']:5.1f}s  best={x['best_model']} {x['best_score']}")
print("  ...")
for x in task_stats[-5:]:
    print(f"  {x['task']:26s} mean {x['mean']:5.2f}  spread {x['spread']:5.2f}  "
          f"dur {x['mean_duration']:5.1f}s  best={x['best_model']} {x['best_score']}")
print("  全模型均值 <20% 的任务：", report["Q4_task_difficulty"]["universally_hard_mean_lt20"])

print("\n== Q5 时长 ==")
q5 = report["Q5_duration"]
print(f"  长任务(>=48s, n={q5['long_task_count']}) 均值成功 {q5['long_task_mean_success']}%   "
      f"短任务(<38s, n={q5['short_task_count']}) 均值成功 {q5['short_task_mean_success']}%   "
      f"corr(dur, succ) = {q5['corr_task_mean_duration_vs_task_mean_success']}")

print(f"\n写出：{OUT}")
