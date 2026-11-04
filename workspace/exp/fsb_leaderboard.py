import itertools
import json
import os
import statistics as st

TASKS = [
    "Hang the Cup", "Fruit Basket Collection", "Pack the Doll", "Fruit Sorting",
    "Disconnect Ethernet", "Color Arrangement", "Place Photo Frames", "Organize Bookshelf",
    "Toolbox Storage", "Plug Charger", "Pick Out Battery", "Unlock", "Arrange Test Tubes",
    "Open Pill Bottle", "Organize Tools", "Fold Towel", "Organize Stationery", "Pack Bag",
    "Zip Up", "Paper Cup Stacking", "Clear Plates", "Spell robot", "Store Racket",
    "Conveyor Food Sorting", "Stack Cups", "Plug In Ethernet", "Stack Bowls", "Store Earphones",
    "Pack Phone", "Remove Pinned Note", "Organize Pencil Case", "Syringe Water Transfer",
]

SUCCESS = {
    "MolmoAct2": [27.29, 27.85, 37.01, 31.76, 21.29, 37.32, 24.33, 33.02, 30.71, 30.51,
                  23.46, 23.52, 28.93, 28.57, 37.20, 27.19, 30.90, 28.77, 33.42, 35.28,
                  32.72, 28.62, 28.49, 32.26, 31.44, 27.54, 29.28, 27.73, 27.39, 33.75,
                  24.95, 27.89],
    "WALL-OSS-0.5": [32.89, 30.91, 25.82, 25.95, 30.09, 29.10, 26.71, 30.00, 23.96, 38.17,
                     21.45, 23.18, 34.38, 30.09, 20.92, 32.15, 33.06, 27.30, 30.95, 23.65,
                     27.52, 33.99, 28.02, 27.03, 34.59, 22.90, 24.59, 28.35, 21.49, 40.28,
                     28.70, 23.81],
    "DreamZero": [38.43, 30.77, 28.41, 35.50, 22.83, 32.78, 42.00, 25.04, 25.56, 34.50,
                  22.57, 20.54, 19.53, 28.06, 23.43, 23.25, 21.51, 28.52, 21.26, 25.92,
                  23.54, 22.94, 34.23, 35.38, 31.48, 16.94, 29.66, 28.52, 31.86, 30.66,
                  30.30, 26.86],
    "Spirit-v1.5": [9.03, 24.53, 33.37, 32.24, 33.44, 25.72, 34.22, 30.05, 23.62, 19.40,
                    30.03, 24.35, 30.65, 11.68, 25.35, 21.61, 26.30, 24.17, 31.36, 34.03,
                    21.98, 14.37, 20.45, 34.36, 35.48, 18.75, 36.28, 32.30, 22.25, 23.17,
                    21.16, 23.07],
    "DM0": [22.12, 32.38, 23.91, 28.78, 31.73, 25.10, 27.42, 22.96, 25.14, 18.53,
            16.17, 20.39, 23.74, 26.14, 19.15, 30.54, 9.09, 31.38, 17.09, 32.47,
            24.47, 21.17, 23.35, 17.09, 31.80, 12.87, 26.20, 25.61, 21.23, 13.31,
            26.33, 24.33],
    "PI-0.5": [15.46, 23.56, 23.26, 23.81, 23.95, 29.26, 18.10, 26.77, 22.76, 26.05,
               23.45, 28.17, 23.86, 19.79, 26.69, 16.71, 13.34, 24.59, 19.79, 33.88,
               18.05, 18.93, 24.56, 23.36, 19.87, 9.23, 11.33, 29.85, 24.72, 32.26,
               24.87, 29.35],
    "GigaBrain-0": [25.75, 27.85, 15.29, 19.83, 25.37, 26.27, 33.47, 25.33, 28.67, 20.93,
                    23.88, 14.39, 17.44, 22.11, 25.46, 22.28, 25.38, 21.19, 19.65, 21.12,
                    24.53, 17.03, 20.33, 37.55, 32.41, 19.30, 16.12, 23.30, 16.94, 18.86,
                    12.94, 22.22],
    "GR00T N1.5": [12.67, 24.50, 22.02, 18.23, 25.82, 11.38, 17.57, 19.78, 26.13, 16.47,
                   25.44, 6.30, 14.67, 15.37, 29.29, 18.92, 20.16, 16.35, 13.58, 18.04,
                   34.36, 17.54, 25.14, 25.96, 25.49, 14.27, 19.43, 27.40, 25.19, 26.13,
                   23.39, 19.00],
}

STEP = {
    "MolmoAct2": [35.84, 36.57, 48.60, 41.71, 27.96, 49.01, 31.95, 43.36, 40.33, 40.06,
                  30.81, 30.88, 37.99, 37.52, 48.85, 35.70, 40.58, 37.78, 43.88, 46.33,
                  42.97, 37.58, 37.41, 42.36, 41.28, 36.16, 38.45, 36.41, 35.97, 44.32,
                  32.76, 36.62],
    "WALL-OSS-0.5": [44.89, 42.19, 35.24, 35.42, 41.07, 39.72, 36.46, 40.95, 32.70, 52.10,
                     29.28, 31.64, 46.93, 41.07, 28.55, 43.88, 45.12, 37.26, 42.24, 32.28,
                     37.56, 46.39, 38.24, 36.89, 47.21, 31.26, 33.56, 38.70, 29.33, 54.98,
                     39.17, 32.50],
    "DreamZero": [52.20, 41.80, 38.59, 48.22, 31.01, 44.53, 57.05, 34.01, 34.72, 46.87,
                  30.66, 27.90, 26.53, 38.12, 31.83, 31.58, 29.22, 38.74, 28.88, 35.21,
                  31.98, 31.16, 46.50, 48.06, 42.76, 23.01, 40.29, 38.74, 43.28, 41.65,
                  41.16, 36.49],
}

NAMES = list(SUCCESS)
OUT = {
    "source": "https://unibot.unitree.com/leaderboard_data.json",
    "retrieved": "2026-11-04",
    "n_models": len(NAMES),
    "n_tasks": len(TASKS),
}

model_mean = {m: st.mean(SUCCESS[m]) for m in NAMES}
task_mean = {t: st.mean([SUCCESS[m][i] for m in NAMES]) for i, t in enumerate(TASKS)}
OUT["model_avg_success"] = {m: round(v, 2) for m, v in model_mean.items()}
OUT["task_avg_success"] = {t: round(v, 2) for t, v in task_mean.items()}

grand = st.mean([SUCCESS[m][i] for m in NAMES for i in range(len(TASKS))])
ss_tot = sum((SUCCESS[m][i] - grand) ** 2 for m in NAMES for i in range(len(TASKS)))
ss_model = len(TASKS) * sum((model_mean[m] - grand) ** 2 for m in NAMES)
ss_task = len(NAMES) * sum((task_mean[t] - grand) ** 2 for t in TASKS)
ss_inter = sum((SUCCESS[m][i] - model_mean[m] - task_mean[t] + grand) ** 2
                for m in NAMES for i, t in enumerate(TASKS))
OUT["variance_decomposition_pct"] = {
    "model_main_effect": round(100 * ss_model / ss_tot, 1),
    "task_main_effect": round(100 * ss_task / ss_tot, 1),
    "task_x_model_interaction": round(100 * ss_inter / ss_tot, 1),
}
OUT["within_task_between_model_sd"] = round(st.mean(
    [st.pstdev([SUCCESS[m][i] for m in NAMES]) for i in range(len(TASKS))]), 2)
OUT["between_task_sd_of_model_means"] = round(st.pstdev(list(model_mean.values())), 2)

oracle = st.mean([max(SUCCESS[m][i] for m in NAMES) for i in range(len(TASKS))])
best_single = max(NAMES, key=lambda m: model_mean[m])
OUT["oracle_per_task_best_of_8"] = round(oracle, 2)
OUT["best_single_model"] = {"name": best_single, "avg_success": round(model_mean[best_single], 2)}
OUT["headroom_vs_best_single_pp"] = round(oracle - model_mean[best_single], 2)
OUT["headroom_vs_field_mean_pp"] = round(oracle - grand, 2)

wins = {m: 0 for m in NAMES}
for i in range(len(TASKS)):
    wins[max(NAMES, key=lambda m: SUCCESS[m][i])] += 1
OUT["per_task_winner_counts"] = wins


def ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0] * len(v)
    for pos, i in enumerate(order):
        r[i] = pos + 1
    return r


cors = []
for a, b in itertools.combinations(NAMES, 2):
    ra, rb = ranks(SUCCESS[a]), ranks(SUCCESS[b])
    ma, mb = st.mean(ra), st.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    cors.append(num / den)
OUT["mean_pairwise_spearman_across_tasks"] = round(st.mean(cors), 3)
OUT["spearman_min_max"] = [round(min(cors), 3), round(max(cors), 3)]

ratio_stats = {}
for m in STEP:
    ratios = [STEP[m][i] / SUCCESS[m][i] for i in range(len(TASKS))]
    ratio_stats[m] = {
        "mean": round(st.mean(ratios), 4),
        "min": round(min(ratios), 4),
        "max": round(max(ratios), 4),
        "std": round(st.pstdev(ratios), 5),
    }
OUT["step_over_success_ratio"] = ratio_stats
OUT["step_score_is_per_model_affine"] = all(v["std"] < 0.005 for v in ratio_stats.values())

if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "fsb_leaderboard_results.json"), "w") as f:
        json.dump(OUT, f, indent=1, ensure_ascii=False)
    print(json.dumps(OUT, indent=1, ensure_ascii=False))
