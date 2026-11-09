"""Round-38 leaderboard structural analysis.

Source: https://unibot.unitree.com/leaderboard_data.json (webfetch, 2026-11-09).

Questions:
  Q1  Is the per-task `avg_duration_sec` a policy-independent budget (episode
      timeout) or policy-dependent (early termination)? -> compare across the 8
      generalist entries: if duration is nearly identical across models but
      differs strongly across tasks, the evaluator uses a per-task time budget.
  Q2  Does faster correlate with better? (per-task Pearson r over 8 models)
  Q3  Step-score vs success-rate gap: how much partial credit exists on average?
  Q4  Which tasks are "hard" for the whole field (rank by mean success)?
  Q5  Spread of per-task success across models (are hard tasks uniformly hard or
      is there a "task-specific expert" pattern -> compositional headroom)?
"""
import json
import statistics as st

LB = "/tmp/opencode/lb_now.json"

d = json.load(open(LB))
models = d["models"]
tasks = d["tasks"]
print(f"tasks={len(tasks)} models={len(models)} specialist={d.get('specialist')}")
print("model table:")
for m in models:
    print(f"  r{m['model_id']:>2} {m['model_name']:<16} {m['user_name']:<22} "
          f"succ={m['avg_success_rate']:>5} dur={m['avg_duration_sec']:>6} step={m['avg_step_score']:>5}")

# --- Q1: duration variance across models, per task -------------------------------
print("\n[Q1] per-task duration across 8 models (policy-dependent?)")
durs, succs, steps = [], [], []
for t_i, t in enumerate(tasks):
    d_t = [m["task_metrics"][t_i]["avg_duration_sec"] for m in models]
    s_t = [m["task_metrics"][t_i]["success_rate"] for m in models]
    st_t = [m["task_metrics"][t_i]["step_score"] for m in models]
    durs.append(d_t); succs.append(s_t); steps.append(st_t)

spread = [(max(d_t) - min(d_t)) / st.mean(d_t) for d_t in durs]
print(f"  relative duration spread across models: mean={st.mean(spread):.4f} "
      f"median={st.median(spread):.4f} max={max(spread):.4f}")
print(f"  cross-task duration spread (max-min over tasks, model0): "
      f"{min(durs[0]):.1f}s..{max(durs[0]):.1f}s  (ratio {max(durs[0])/min(durs[0]):.2f})")
allm = [d_i for d_t in durs for d_i in d_t]
print(f"  all durations: mean={st.mean(allm):.2f} sd={st.pstdev(allm):.2f}")

# --- Q2: duration vs success correlation ----------------------------------------
def pearson(x, y):
    mx, my = st.mean(x), st.mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den = (sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y)) ** 0.5
    return num / den if den else 0.0

print("\n[Q2] per-task corr(duration, success) across models; and corr(success, step_score)")
r_dur, r_step = [], []
for t_i, t in enumerate(tasks):
    r_dur.append(pearson(durs[t_i], succs[t_i]))
    r_step.append(pearson(succs[t_i], steps[t_i]))
    print(f"  {t:<28} dur_mean={st.mean(durs[t_i]):>5.1f}s  succ_mean={st.mean(succs[t_i]):>5.2f} "
          f"step_mean={st.mean(steps[t_i]):>5.2f}  r(dur,succ)={r_dur[-1]:+.2f}  r(succ,step)={r_step[-1]:+.2f}")
print(f"  mean r(dur,succ)={st.mean(r_dur):+.3f}   mean r(succ,step)={st.mean(r_step):+.3f}")

# --- Q3: step-score vs success gap ----------------------------------------------
print("\n[Q3] partial credit: step_score - success (means over 8 models)")
gaps = [(st.mean(steps[i]) - st.mean(succs[i])) for i in range(len(tasks))]
for t, g, s_, st_ in zip(tasks, gaps, [st.mean(x) for x in succs], [st.mean(x) for x in steps]):
    print(f"  {t:<28} succ={s_:>5.2f} step={st_:>5.2f} gap={g:+6.2f}  ratio={st_/max(s_,1e-9):.2f}")
print(f"  mean gap={st.mean(gaps):.2f}  mean ratio={st.mean([st.mean(steps[i])/max(st.mean(succs[i]),1e-9) for i in range(len(tasks))]):.3f}")

# --- Q4: hard tasks --------------------------------------------------------------
print("\n[Q4] field-difficulty ranking (mean success over 8 models)")
order = sorted(range(len(tasks)), key=lambda i: st.mean(succs[i]))
for i in order:
    print(f"  {tasks[i]:<28} mean_succ={st.mean(succs[i]):>5.2f}  best={max(succs[i]):>5.2f} "
          f"({models[succs[i].index(max(succs[i]))]['model_name']})  mean_step={st.mean(steps[i]):>5.2f}")

# --- Q5: is there a task-specialist structure? -----------------------------------
print("\n[Q5] task-specialist structure: per-task best model and its margin over field mean")
n_best = {}
for i, t in enumerate(tasks):
    b = max(succs[i]); n_best[models[succs[i].index(b)]['model_name']] = n_best.get(models[succs[i].index(b)]['model_name'], 0) + 1
    print(f"  {t:<28} best={b:>5.2f} field_mean={st.mean(succs[i]):>5.2f} margin={b-st.mean(succs[i]):+5.2f} "
          f"({models[succs[i].index(b)]['model_name']})")
print("  #task-wins per model:", n_best)

# --- Q6: rank stability vs field size ------------------------------------------
print("\n[Q6] headroom: how much would the field mean move if each model's weak tasks were fixed to the best-in-field")
field_mean = st.mean([st.mean(x) for x in succs])
best_model_mean = max(m["avg_success_rate"] for m in models)
print(f"  field mean per-task avg={field_mean:.2f}  best model avg={best_model_mean:.2f}")
oracle = st.mean([max(succs[i]) for i in range(len(tasks))])
print(f"  per-task oracle (best of 8) = {oracle:.2f}  -> oracle ceiling today")
top1 = models[0]
print(f"  top1 {top1['model_name']}: succ={top1['avg_success_rate']} step={top1['avg_step_score']} dur={top1['avg_duration_sec']}")
print(f"  gap top1->oracle = {oracle - top1['avg_success_rate']:.2f} pts (success-rate units)")

json.dump({"per_task_mean_succ": [st.mean(x) for x in succs],
           "per_task_mean_step": [st.mean(x) for x in steps],
           "per_task_mean_dur": [st.mean(x) for x in durs],
           "per_task_best_succ": [max(x) for x in succs],
           "field_mean": field_mean, "oracle": oracle},
          open("/home/runner/work/xuen/xuen/workspace/exp/r38_lb_stats.json", "w"), indent=1)
print("\nsaved r38_lb_stats.json")
