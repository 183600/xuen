"""Round-16 (cycle-3 r1) leaderboard headroom analysis for the UniBot World Challenge.

DATA SOURCE (transcribed from the official leaderboard JSON fetched with the
webfetch tool on 2026-11-03 UTC; direct curl is blocked by a WAF that returns
HTTP 567 "Access Restricted"):

    https://unibot.unitree.com/leaderboard_data.json

This script is a DESCRIPTIVE analysis of published leaderboard numbers. It is
NOT benchmark evidence about our own policy and it does not fit any model of
robot behaviour. Every quantity below is a deterministic function of the
published table.

Questions:
  Q1  How flat is the field? (avg-success spread across 8 generalist models)
  Q2  How large is the per-task spread relative to the average spread?
  Q3  What is the headroom of "per-task routing" (mean of per-task maxima)?
  Q4  Is the average dragged down by a few catastrophic tasks (floor effect)?
  Q5  What does the step_score/success_rate ratio imply about WHERE failures
      happen inside an episode (early vs terminal checkpoints)?
  Q6  Does episode duration explain success?

Usage: python3 exp/lb_headroom_r16.py
"""
import json
import math
import os
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))

TASKS = [
    "Hang the Cup", "Fruit Basket Collection", "Pack the Doll", "Fruit Sorting",
    "Disconnect Ethernet", "Color Arrangement", "Place Photo Frames",
    "Organize Bookshelf", "Toolbox Storage", "Plug Charger", "Pick Out Battery",
    "Unlock", "Arrange Test Tubes", "Open Pill Bottle", "Organize Tools",
    "Fold Towel", "Organize Stationery", "Pack Bag", "Zip Up",
    "Paper Cup Stacking", "Clear Plates", "Spell robot", "Store Racket",
    "Conveyor Food Sorting", "Stack Cups", "Plug In Ethernet", "Stack Bowls",
    "Store Earphones", "Pack Phone", "Remove Pinned Note",
    "Organize Pencil Case", "Syringe Water Transfer",
]

# model -> (avg_success_rate, avg_step_score, avg_duration_sec, 32 task rates)
LEADERBOARD = {
    "MolmoAct2": (29.7, 39.0, 44.02, [
        27.29, 27.85, 37.01, 31.76, 21.29, 37.32, 24.33, 33.02, 30.71, 30.51,
        23.46, 23.52, 28.93, 28.57, 37.20, 27.19, 30.90, 28.77, 33.42, 35.28,
        32.72, 28.62, 28.49, 32.26, 31.44, 27.54, 29.28, 27.73, 27.39, 33.75,
        24.95, 27.89]),
    "WALL-OSS-0.5": (28.5, 38.9, 43.74, [
        32.89, 30.91, 25.82, 25.95, 30.09, 29.10, 26.71, 30.00, 23.96, 38.17,
        21.45, 23.18, 34.38, 30.09, 20.92, 32.15, 33.06, 27.30, 30.95, 23.65,
        27.52, 33.99, 28.02, 27.03, 34.59, 22.90, 24.59, 28.35, 21.49, 40.28,
        28.70, 23.81]),
    "DreamZero": (27.9, 37.9, 44.59, [
        38.43, 30.77, 28.41, 35.50, 22.83, 32.78, 42.00, 25.04, 25.56, 34.50,
        22.57, 20.54, 19.53, 28.06, 23.43, 23.25, 21.51, 28.52, 21.26, 25.92,
        23.54, 22.94, 34.23, 35.38, 31.48, 16.94, 29.66, 28.52, 31.86, 30.66,
        30.30, 26.86]),
    "Spirit-v1.5": (25.9, 34.4, 45.19, [
        9.03, 24.53, 33.37, 32.24, 33.44, 25.72, 34.22, 30.05, 23.62, 19.40,
        30.03, 24.35, 30.65, 11.68, 25.35, 21.61, 26.30, 24.17, 31.36, 34.03,
        21.98, 14.37, 20.45, 34.36, 35.48, 18.75, 36.28, 32.30, 22.25, 23.17,
        21.16, 23.07]),
    "DM0": (23.5, 31.7, 45.11, [
        22.12, 32.38, 23.91, 28.78, 31.73, 25.10, 27.42, 22.96, 25.14, 18.53,
        16.17, 20.39, 23.74, 26.14, 19.15, 30.54, 9.09, 31.38, 17.09, 32.47,
        24.47, 21.17, 23.35, 17.09, 31.80, 12.87, 26.20, 25.61, 21.23, 13.31,
        26.33, 24.33]),
    "PI-0.5": (22.8, 30.6, 43.88, [
        15.46, 23.56, 23.26, 23.81, 23.95, 29.26, 18.10, 26.77, 22.76, 26.05,
        23.45, 28.17, 23.86, 19.79, 26.69, 16.71, 13.34, 24.59, 19.79, 33.88,
        18.05, 18.93, 24.56, 23.36, 19.87, 9.23, 11.33, 29.85, 24.72, 32.26,
        24.87, 29.35]),
    "GigaBrain-0": (22.6, 29.5, 43.76, [
        25.75, 27.85, 15.29, 19.83, 25.37, 26.27, 33.47, 25.33, 28.67, 20.93,
        23.88, 14.39, 17.44, 22.11, 25.46, 22.28, 25.38, 21.19, 19.65, 21.12,
        23.54, 17.03, 20.33, 37.55, 32.41, 19.30, 16.12, 23.30, 16.94, 18.86,
        12.94, 22.22]),
    "GR00T N1.5": (20.5, 28.1, 44.71, [
        12.67, 24.50, 22.02, 18.23, 25.82, 11.38, 17.57, 19.78, 26.13, 16.47,
        25.44, 6.30, 14.67, 15.37, 29.29, 18.92, 20.16, 16.35, 13.58, 18.04,
        34.36, 17.54, 25.14, 25.96, 25.49, 14.27, 19.43, 27.40, 25.19, 26.13,
        23.39, 19.00]),
}


def corr(a, b):
    ma, mb = st.mean(a), st.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den if den else float("nan")


def main():
    names = list(LEADERBOARD)
    succ = {n: dict(zip(TASKS, LEADERBOARD[n][3])) for n in names}
    avg = {n: LEADERBOARD[n][0] for n in names}
    step = {n: LEADERBOARD[n][1] for n in names}
    dur = {n: LEADERBOARD[n][2] for n in names}

    print("=" * 78)
    print("Q1/Q2  field flatness, per-model task dispersion")
    print("=" * 78)
    print(f"{'model':16s} {'avg':>5} {'step':>5} {'step/succ':>9} {'min':>5} {'max':>5} "
          f"{'std':>5} {'p25':>5} {'dur':>6}")
    for n in names:
        v = sorted(succ[n][t] for t in TASKS)
        print(f"{n:16s} {avg[n]:5.1f} {step[n]:5.1f} {step[n]/avg[n]:9.3f} "
              f"{v[0]:5.1f} {v[-1]:5.1f} {st.pstdev(v):5.2f} {v[8]:5.1f} {dur[n]:6.2f}")
    avgs = [avg[n] for n in names]
    print(f"\navg-success spread over 8 models: {min(avgs):.1f} .. {max(avgs):.1f} "
          f"(range {max(avgs)-min(avgs):.1f} pp, ratio {max(avgs)/min(avgs):.2f}x)")

    print("\n" + "=" * 78)
    print("Q2  per-task dispersion across the field")
    print("=" * 78)
    rows = []
    for t in TASKS:
        v = [succ[n][t] for n in names]
        rows.append((st.mean(v), t, min(v), max(v), st.pstdev(v), max(v) - min(v)))
    rows.sort()
    print(f"{'mean':>6} {'min':>6} {'max':>6} {'std':>6} {'range':>6}  task")
    for m, t, lo, hi, sd, rg in rows:
        print(f"{m:6.2f} {lo:6.2f} {hi:6.2f} {sd:6.2f} {rg:6.2f}  {t}")
    ranges = [r[5] for r in rows]
    print(f"\nmean per-task range across models = {st.mean(ranges):.2f} pp")
    print(f"mean per-task std   across models = {st.mean(r[4] for r in rows):.2f} pp")
    print(f"average-level spread across models = {max(avgs)-min(avgs):.2f} pp")
    print(f"--> per-task range is {st.mean(ranges)/(max(avgs)-min(avgs)):.1f}x the average-level spread")

    print("\n" + "=" * 78)
    print("Q3  headroom of per-task routing (upper bound)")
    print("=" * 78)
    mean_of_mean = st.mean(r[0] for r in rows)
    mean_of_max = st.mean(r[3] for r in rows)
    print(f"mean of task means    = {mean_of_mean:.2f}  (the field's operating point)")
    print(f"mean of task maxima   = {mean_of_max:.2f}  (oracle per-task routing)")
    print(f"headroom              = {mean_of_max-mean_of_mean:+.2f} pp")
    print(f"worst-task mean       = {min(r[0] for r in rows):.2f} ({rows[0][1]})")
    print(f"best-task mean        = {max(r[0] for r in rows):.2f} ({rows[-1][1]})")

    print("\n" + "=" * 78)
    print("Q4  floor effect: replace a model's k worst tasks by the field median")
    print("=" * 78)
    med = {t: st.median([succ[n][t] for n in names]) for t in TASKS}
    for k in (1, 3, 5, 8):
        out = []
        for n in names:
            s = succ[n]
            worst = sorted(TASKS, key=lambda t: s[t])[:k]
            new = sum(med[t] if t in worst else s[t] for t in TASKS) / 32
            out.append((n, avg[n], new))
        print(f"k={k}: " + "  ".join(f"{n}:{a:.1f}->{b:.1f}" for n, a, b in out))
    mins = [min(succ[n][t] for t in TASKS) for n in names]
    print(f"\ncorr(avg_success, min_task_success) = {corr(avgs, mins):.3f}")
    print(f"corr(avg_success, mean_task_std)    = "
          f"{corr(avgs, [st.pstdev([succ[n][t] for t in TASKS]) for n in names]):.3f}")
    # rank stability under a small global handicap
    print("\nranking under a uniform handicap h added to every task rate "
          "(robustness of the order):")
    for h in (0.0, 2.0, 5.0):
        order = sorted(names, key=lambda n: -(sum(succ[n][t] for t in TASKS) / 32 + h))
        print(f"  h={h:4.1f}: " + " > ".join(order[:4]) + " ...")

    print("\n" + "=" * 78)
    print("Q5  what step_score / success_rate implies about failure timing")
    print("=" * 78)
    print("if a task's score is 100 pts and success = 100 pts, then for a model")
    print("the average score of a FAILED episode is (step - succ)/(100-succ)*100")
    print(f"{'model':16s} {'succ':>5} {'step':>5} {'credit on failure':>18}")
    for n in names:
        pc = (step[n] - avg[n]) / (100 - avg[n]) * 100
        print(f"{n:16s} {avg[n]:5.1f} {step[n]:5.1f} {pc:17.1f}/100")
    pcs = [(step[n] - avg[n]) / (100 - avg[n]) * 100 for n in names]
    print(f"\nmean credit earned by FAILED episodes = {st.mean(pcs):.1f}/100")
    print(f"that is ~{st.mean(pcs)/100*100:.0f}% of the checkpoints: failures are "
          "EARLY, not terminal")

    print("\n" + "=" * 78)
    print("Q6  does duration explain success?")
    print("=" * 78)
    pairs = []
    for n in names:
        for t in TASKS:
            pairs.append((LEADERBOARD[n][2], succ[n][t]))
    print(f"corr(duration, success) over 256 model-task cells = "
          f"{corr([a for a, _ in pairs], [b for _, b in pairs]):.3f}")
    print(f"corr(avg_duration, avg_success) over 8 models        = "
          f"{corr([dur[n] for n in names], avgs):.3f}")
    # per-task duration spread
    dd = []
    for t in TASKS:
        v = [LEADERBOARD[n][2] for n in names]
        dd.append(st.pstdev(v))
    print(f"mean per-task std of avg_duration across models = {st.mean(dd):.3f} s "
          "(all models spend nearly the same wall-clock per task)")

    out = {
        "field_avg_spread_pp": max(avgs) - min(avgs),
        "mean_per_task_range_pp": st.mean(ranges),
        "mean_of_task_means": mean_of_mean,
        "mean_of_task_maxima": mean_of_max,
        "routing_headroom_pp": mean_of_max - mean_of_mean,
        "mean_failed_episode_credit_pts": st.mean(pcs),
        "corr_avg_success_min_task": corr(avgs, mins),
    }
    path = os.path.join(HERE, "lb_headroom_r16_results.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
