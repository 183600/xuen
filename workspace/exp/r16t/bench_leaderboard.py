"""第 16 轮：UniBot 榜单「时序/接口」再分析（B 级证据，真实数据）

输入：exp/r16t/leaderboard_snapshot.json
  = unibot.unitree.com/leaderboard_data.json 的逐字转写（2026-11-02 抓取，
    2026-11-03 用 webfetch 复读，8 个模型的聚合指标与 32 任务列表完全一致，
    见 AGG_20261103 断言）。

输出：exp/r16t/bench_leaderboard.json

本轮要回答的问题（决定创新方向，不为了分析而分析）：
  Q1 成功率方差里，任务 / 模型 / 模型×任务交互 各占多少？
     -> 若交互项占主导，说明「选更强的通才模型」或「按任务路由模型」都不是大头。
  Q2 8 个已提交模型做「逐任务 oracle 路由」能涨多少？
     -> 给「任务级路由」这条路的收益上界定价。
  Q3 步骤分是不是成功率的线性变换？
     -> 若近似线性，就不必单独优化步骤分，专注成功率。
  Q4 episode 时长由谁决定（任务还是模型）？
     -> 若由任务决定，则「推理慢」不会体现在时长上，说明榜单无法暴露延迟代价；
        也说明固定墙钟预算下每一步都是稀缺资源。
  Q5 长任务是否更难（时长 vs 成功率的相关）？
     -> 若强负相关，说明长时程/陈旧计划是系统性瓶颈（时序创新的动机）。
  Q6 任务难度的两副面孔：普遍难（低成功率 + 低离散）vs 高度两极化
     （离散大、模型间差异大）？
     -> 前者要「系统级通用机制」，后者要「任务级专门机制」，两者的资源分配不同。
"""
import json
import os
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "leaderboard_snapshot.json")
OUT = os.path.join(HERE, "bench_leaderboard.json")

# 2026-11-03 通过 webfetch 复读官方 JSON 得到的聚合指标（用于「榜单是否变化」断言）
AGG_20261103 = {
    "MolmoAct2": (29.7, 39.0, 44.02),
    "WALL-OSS-0.5": (28.5, 38.9, 43.74),
    "DreamZero": (27.9, 37.9, 44.59),
    "Spirit-v1.5": (25.9, 34.4, 45.19),
    "DM0": (23.5, 31.7, 45.11),
    "PI-0.5": (22.8, 30.6, 43.88),
    "GigaBrain-0": (22.6, 29.5, 43.76),
    "GR00T N1.5": (20.5, 28.1, 44.71),
}


def two_way_anova(matrix):
    """无重复两因素方差分解：行=任务，列=模型，返回 task/model/interaction 的平方和占比。"""
    n_rows = len(matrix)
    n_cols = len(matrix[0])
    grand = sum(sum(r) for r in matrix) / (n_rows * n_cols)
    ss_total = sum((x - grand) ** 2 for r in matrix for x in r)
    row_means = [sum(r) / n_cols for r in matrix]
    col_means = [sum(matrix[i][j] for i in range(n_rows)) / n_rows for j in range(n_cols)]
    ss_task = n_cols * sum((m - grand) ** 2 for m in row_means)
    ss_model = n_rows * sum((m - grand) ** 2 for m in col_means)
    ss_inter = ss_total - ss_task - ss_model
    return {
        "task_frac": ss_task / ss_total,
        "model_frac": ss_model / ss_total,
        "interaction_frac": ss_inter / ss_total,
        "ss_total": ss_total,
        "task_means": row_means,
        "model_means": col_means,
    }


def spearman(x, y):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = rank(x), rank(y)
    n = len(x)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else 0.0


def pearson(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den = (sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y)) ** 0.5
    return num / den if den else 0.0


with open(SRC, encoding="utf-8") as f:
    data = json.load(f)

tasks = data["tasks"]
models = data["models"]
names = [m["model_name"] for m in models]

# ---------- 榜单是否变化的断言 ----------
unchanged = True
mismatch = []
for m in models:
    got = (m["avg_success_rate"], m["avg_step_score"], m["avg_duration_sec"])
    exp = AGG_20261103.get(m["model_name"])
    if exp is None or max(abs(a - b) for a, b in zip(got, exp)) > 1e-6:
        unchanged = False
        mismatch.append([m["model_name"], got, exp])

S = [[t["success_rate"] for t in m["task_metrics"]] for m in models]
D = [[t["avg_duration_sec"] for t in m["task_metrics"]] for m in models]
K = [[t["step_score"] for t in m["task_metrics"]] for m in models]

report = {
    "source": "https://unibot.unitree.com/leaderboard_data.json",
    "retrieved": ["2026-11-02", "2026-11-03"],
    "leaderboard_unchanged_since_20261102": unchanged,
    "mismatch": mismatch,
    "n_models": len(models),
    "n_tasks": len(tasks),
    "models": [
        {
            "model": m["model_name"],
            "user": m["user_name"],
            "avg_success": m["avg_success_rate"],
            "avg_step_score": m["avg_step_score"],
            "avg_duration": m["avg_duration_sec"],
        }
        for m in models
    ],
}

# ---------- Q1 方差分解 ----------
report["variance_decomposition"] = {
    "success_rate": {k: v for k, v in two_way_anova(S).items() if not k.endswith("means")},
    "step_score": {k: v for k, v in two_way_anova(K).items() if not k.endswith("means")},
    "avg_duration_sec": {k: v for k, v in two_way_anova(D).items() if not k.endswith("means")},
}

# ---------- Q2 oracle 路由收益 ----------
best_single = max(models, key=lambda m: m["avg_success_rate"])["avg_success_rate"]
per_task_best = [max(S[j][i] for j in range(len(models))) for i in range(len(tasks))]
per_task_mean = [sum(S[j][i] for j in range(len(models))) / len(models) for i in range(len(tasks))]
per_task_worst = [min(S[j][i] for j in range(len(models))) for i in range(len(tasks))]
winners = [names[max(range(len(models)), key=lambda j: S[j][i])] for i in range(len(tasks))]
win_count = {n: winners.count(n) for n in names}
report["oracle_routing"] = {
    "best_single_avg": best_single,
    "per_task_oracle_avg": sum(per_task_best) / len(tasks),
    "per_task_worst_avg": sum(per_task_worst) / len(tasks),
    "per_task_mean_avg": sum(per_task_mean) / len(tasks),
    "oracle_gain_pp": sum(per_task_best) / len(tasks) - best_single,
    "winner_count_per_model": win_count,
    "note": "oracle 路由是任务条件选择的上界，不是可达分数（测试时无逐任务标签）",
}

# ---------- Q3 step_score 与 success_rate 的关系 ----------
xs, ys = [], []
for j in range(len(models)):
    for i in range(len(tasks)):
        xs.append(S[j][i])
        ys.append(K[j][i])
n = len(xs)
mx, my = sum(xs) / n, sum(ys) / n
b = sum((a - mx) * (c - my) for a, c in zip(xs, ys)) / sum((a - mx) ** 2 for a in xs)
a0 = my - b * mx
resid = [c - (a0 + b * a) for a, c in zip(xs, ys)]
ss_res = sum(r * r for r in resid)
ss_tot = sum((c - my) ** 2 for c in ys)
agg = [(m["avg_success_rate"], m["avg_step_score"]) for m in models]
report["step_score_vs_success"] = {
    "cell_fit_slope": b,
    "cell_fit_intercept": a0,
    "cell_r2": 1 - ss_res / ss_tot,
    "cell_max_abs_resid": max(abs(r) for r in resid),
    "cell_resid_std": st.pstdev(resid),
    "aggregate_ratios": {m["model_name"]: round(m["avg_step_score"] / m["avg_success_rate"], 4) for m in models},
    "aggregate_ratio_mean": sum(m["avg_step_score"] / m["avg_success_rate"] for m in models) / len(models),
    "aggregate_ratio_spread": max(m["avg_step_score"] / m["avg_success_rate"] for m in models)
    - min(m["avg_step_score"] / m["avg_success_rate"] for m in models),
    "rank_identical": [m["model_name"] for m in models]
    == [
        m["model_name"]
        for m in sorted(models, key=lambda m: -m["avg_success_rate"])
    ],
}

# ---------- Q4 时长由谁决定 ----------
per_task_dur_mean = [sum(D[j][i] for j in range(len(models))) / len(models) for i in range(len(tasks))]
per_task_dur_cv = [
    st.pstdev([D[j][i] for j in range(len(models))]) / per_task_dur_mean[i] for i in range(len(tasks))
]
report["duration_structure"] = {
    "per_task_cv_across_models_median": st.median(per_task_dur_cv),
    "per_task_cv_across_models_max": max(per_task_dur_cv),
    "per_task_cv_across_models_min": min(per_task_dur_cv),
    "between_task_cv_of_task_mean_duration": st.pstdev(per_task_dur_mean) / (sum(per_task_dur_mean) / len(per_task_dur_mean)),
    "within_task_cv_median": st.median(per_task_dur_cv),
    "interpretation": "若任务间 CV 远大于任务内 CV，则 episode 时长由任务决定而非模型速度决定",
}

# ---------- Q5 时长 vs 成功率 ----------
report["duration_vs_success"] = {
    "spearman_mean_over_models": spearman(per_task_dur_mean, per_task_mean),
    "pearson_mean_over_models": pearson(per_task_dur_mean, per_task_mean),
    "spearman_top1_model": spearman([D[0][i] for i in range(len(tasks))], [S[0][i] for i in range(len(tasks))]),
    "spearman_per_model": {
        names[j]: spearman([D[j][i] for i in range(len(tasks))], [S[j][i] for i in range(len(tasks))])
        for j in range(len(models))
    },
}

# ---------- Q6 普遍难 vs 两极化 ----------
rows = []
for i, t in enumerate(tasks):
    vals = [S[j][i] for j in range(len(models))]
    rows.append(
        {
            "task": t,
            "mean_success": per_task_mean[i],
            "std": st.pstdev(vals),
            "cv": st.pstdev(vals) / per_task_mean[i],
            "max": max(vals),
            "min": min(vals),
            "mean_duration": per_task_dur_mean[i],
        }
    )
rows_by_cv = sorted(rows, key=lambda r: -r["cv"])
rows_by_mean = sorted(rows, key=lambda r: r["mean_success"])
report["task_profiles"] = {
    "most_polarized": rows_by_cv[:6],
    "least_polarized": rows_by_cv[-6:],
    "hardest": rows_by_mean[:6],
    "easiest": rows_by_mean[-6:],
    "all": rows,
}
# 成功率与两极化度的关系：两极化任务是否更容易被「任务级机制」救回
report["polarization_vs_mean"] = {
    "spearman_cv_vs_mean_success": spearman([r["cv"] for r in rows], [r["mean_success"] for r in rows]),
    "spearman_std_vs_mean_success": spearman([r["std"] for r in rows], [r["mean_success"] for r in rows]),
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=1)

# ---------- 控制台摘要 ----------
print("榜单未变化断言:", unchanged, mismatch)
vd = report["variance_decomposition"]
for key in ("success_rate", "step_score", "avg_duration_sec"):
    v = vd[key]
    print(
        f"{key:18s} task={v['task_frac']:.3f} model={v['model_frac']:.3f} inter={v['interaction_frac']:.3f}"
    )
o = report["oracle_routing"]
print(f"best_single={o['best_single_avg']:.2f}  per_task_oracle={o['per_task_oracle_avg']:.2f}  gain={o['oracle_gain_pp']:.2f}pp")
print("逐任务冠军计数:", o["winner_count_per_model"])
ss = report["step_score_vs_success"]
print(f"step_score ≈ {ss['cell_fit_slope']:.4f}*success + {ss['cell_fit_intercept']:.3f}  R2={ss['cell_r2']:.5f}  maxresid={ss['cell_max_abs_resid']:.2f}")
ds = report["duration_structure"]
print(f"时长：任务间CV={ds['between_task_cv_of_task_mean_duration']:.3f} 任务内CV中位={ds['within_task_cv_median']:.4f}")
dv = report["duration_vs_success"]
print("时长~成功率 Spearman(均值模型):", round(dv["spearman_mean_over_models"], 3), " 单模型:", {k: round(v, 2) for k, v in dv["spearman_per_model"].items()})
print("两极化 top3:", [(r["task"], round(r["cv"], 2), round(r["mean_success"], 1)) for r in rows_by_cv[:3]])
print("最难 top3:", [(r["task"], round(r["mean_success"], 1), round(r["mean_duration"], 1)) for r in rows_by_mean[:3]])
print("输出:", OUT)
