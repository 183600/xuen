"""Round-2 analysis A: 'business-model' view of the UniBot teaser leaderboard.

Treats the 32 tasks as 32 equally-weighted product lines and the 8 models as
firms.  Computes (i) per-task headroom / moat / contestability, (ii) market
concentration of per-task winners, (iii) a budget-constrained allocation curve,
and (iv) the arithmetic of the +3-point target.

Input : exp/r16_leaderboard_data.json (transcribed teaser table)
Output: exp/sage_r2/portfolio_results.json
"""
import json, math, os
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = json.load(open(os.path.join(ROOT, 'r16_leaderboard_data.json')))
TASKS = D['tasks']
MODELS = [m['model_name'] for m in D['models']]
S = np.array([[t['success_rate'] for t in m['task_metrics']] for m in D['models']], float)  # 8x32
DUR = np.array([[t['avg_duration_sec'] for t in m['task_metrics']] for m in D['models']], float)
STEP = np.array([[t['step_score'] for t in m['task_metrics']] for m in D['models']], float)

nM, nT = S.shape
base_idx = int(np.argmax(S.mean(axis=1)))
base = S[base_idx]
best = S.max(axis=0)
best_idx = S.argmax(axis=0)
second = np.sort(S, axis=0)[-2]
median = np.median(S, axis=0)
mean = S.mean(axis=0)
std = S.std(axis=0, ddof=0)

per_task = []
for j, t in enumerate(TASKS):
    head = best[j] - base[j]
    per_task.append({
        'task': t,
        'mean': round(float(mean[j]), 3),
        'std': round(float(std[j]), 3),
        'best': round(float(best[j]), 3),
        'best_model': MODELS[int(best_idx[j])],
        'second': round(float(second[j]), 3),
        'base': round(float(base[j]), 3),
        'headroom_vs_base': round(float(head), 3),
        'headroom_pts': round(float(head / nT), 4),   # contribution to 32-task average
        'moat_best_minus_2nd': round(float(best[j] - second[j]), 3),
        'moat_best_minus_median': round(float(best[j] - median[j]), 3),
        'contestable_within_1pt': int(np.sum(best[j] - S[:, j] <= 1.0)),
        'contestable_within_5pt': int(np.sum(best[j] - S[:, j] <= 5.0)),
        'cv': round(float(std[j] / mean[j]), 3),
    })

per_task.sort(key=lambda r: -r['headroom_vs_base'])
oracle_gain = float((best - base).sum() / nT)

# winner concentration over 32 tasks
from collections import Counter
wins = Counter(MODELS[int(i)] for i in best_idx)
win_share = np.array([wins.get(m, 0) / nT for m in MODELS])
hhi = float((win_share ** 2).sum())            # 1/8=0.125 (perfectly spread) .. 1.0
entropy = float(-(win_share[win_share > 0] * np.log(win_share[win_share > 0])).sum())
max_entropy = math.log(nM)

# budget-constrained allocation: with k "investments" (each brings one task to
# best-model level), maximise mean success.  Budget == number of task-fixes.
gains = np.sort((best - base) / nT)[::-1]
alloc_curve = []
for k in range(0, nT + 1):
    alloc_curve.append({'k': k, 'avg_gain': round(float(gains[:k].sum()), 3)})

# +3-point arithmetic
target = 3.0
need_task_points = target * nT
hard6 = ['Plug In Ethernet', 'Unlock', 'Spell robot', 'Organize Stationery',
         'Open Pill Bottle', 'Pick Out Battery']
hard6_gain_now = float(sum(best[TASKS.index(t)] - base[TASKS.index(t)] for t in hard6))
# gain needed if we only improve the hard-6, from base to 100
hard6_deficit = float(sum(100.0 - base[TASKS.index(t)] for t in hard6))
hard6_to_best_avg = hard6_gain_now / 6.0

# step/success coupling (recheck on same snapshot)
x, y = S.ravel(), STEP.ravel()
slope, intercept = np.polyfit(x, y, 1)
r = float(np.corrcoef(x, y)[0, 1])

# duration economics: is a retry cheap?  within-task duration vs success
dur_corr = float(np.mean([np.corrcoef(S[:, j], DUR[:, j])[0, 1] for j in range(nT)]))
dur_mean = float(DUR.mean())

res = {
    'source': 'exp/r16_leaderboard_data.json (teaser, transcribed)',
    'n_models': nM, 'n_tasks': nT,
    'baseline_model': MODELS[base_idx],
    'oracle_avg_gain_vs_baseline': round(oracle_gain, 3),
    'oracle_in_task_points': round(oracle_gain * nT, 2),
    'winner_counts': dict(wins),
    'winner_hhi': round(hhi, 4),
    'winner_hhi_min_for_8': round(1.0 / nM, 4),
    'winner_entropy_bits': round(entropy / math.log(2), 3),
    'winner_max_entropy_bits': round(max_entropy / math.log(2), 3),
    'mean_contestable_within_1pt': round(float(np.mean([p['contestable_within_1pt'] for p in per_task])), 2),
    'mean_moat_best_minus_2nd': round(float(np.mean([p['moat_best_minus_2nd'] for p in per_task])), 3),
    'mean_moat_best_minus_median': round(float(np.mean([p['moat_best_minus_median'] for p in per_task])), 3),
    'target_plus3_avg': target,
    'target_plus3_task_points': need_task_points,
    'hard6_deficit_from_base_to_100': round(hard6_deficit, 1),
    'hard6_reachable_gain_from_base_to_best': round(hard6_gain_now, 1),
    'hard6_avg_gain_from_base_to_best': round(hard6_to_best_avg, 2),
    'step_success_slope': round(float(slope), 4),
    'step_success_intercept': round(float(intercept), 4),
    'step_success_r': round(r, 4),
    'within_task_duration_success_corr_mean': round(dur_corr, 4),
    'mean_duration_sec': round(dur_mean, 2),
    'per_task': per_task,
    'allocation_curve': alloc_curve,
}
json.dump(res, open(os.path.join(os.path.dirname(__file__), 'portfolio_results.json'), 'w'),
          ensure_ascii=False, indent=2)

print('baseline', MODELS[base_idx], 'oracle gain', round(oracle_gain, 3),
      '=', round(oracle_gain * nT, 1), 'task-points')
print('winners', dict(wins), 'HHI', round(hhi, 4), 'entropy(bits)', round(entropy / math.log(2), 3))
print('moat best-2nd mean', res['mean_moat_best_minus_2nd'],
      'best-median', res['mean_moat_best_minus_median'])
print('hard6 reachable', round(hard6_gain_now, 1), 'deficit', round(hard6_deficit, 1))
print('top headroom:')
for p in per_task[:10]:
    print('  %-26s head %5.2f -> %+0.3f avg-pt  moat %5.2f  winner %s' %
          (p['task'], p['headroom_vs_base'], p['headroom_pts'], p['moat_best_minus_2nd'], p['best_model']))
print('bottom headroom:')
for p in per_task[-5:]:
    print('  %-26s head %5.2f  best %5.2f (%s)' % (p['task'], p['headroom_vs_base'], p['best'], p['best_model']))
print('allocation gain at k=4,8,16:', alloc_curve[4]['avg_gain'], alloc_curve[8]['avg_gain'], alloc_curve[16]['avg_gain'])

# ---- business-model extras: proven headroom vs capability frontier ----
mean_arr = mean
level_med = float(np.median(best))
hr_med = float(np.median(best - base))
quad = {}
for p in per_task:
    hi_level = p['best'] >= level_med
    hi_hr = p['headroom_vs_base'] >= hr_med
    key = ('proven-quickwin' if hi_level and hi_hr else
           'frontier-rd' if (not hi_level) and hi_hr else
           'commodity' if hi_level and (not hi_hr) else 'frontier-nobody')
    quad.setdefault(key, []).append(p['task'])
proven_hr = float(sum(p['headroom_vs_base'] for p in per_task if p['best'] >= 30.0))
total_hr = float(sum(p['headroom_vs_base'] for p in per_task))
hard6_detail = {t: {'base': round(float(base[TASKS.index(t)]), 2),
                    'best': round(float(best[TASKS.index(t)]), 2),
                    'headroom': round(float(best[TASKS.index(t)] - base[TASKS.index(t)]), 2),
                    'winner': MODELS[int(best_idx[TASKS.index(t)])]} for t in hard6}
extras = {
    'corr_taskmean_vs_headroom': round(float(np.corrcoef(mean, best - base)[0, 1]), 3),
    'best_level_median': round(level_med, 2),
    'headroom_median': round(hr_med, 2),
    'quadrants': {k: {'n': len(v), 'tasks': v,
                      'headroom_sum': round(float(sum(next(p['headroom_vs_base'] for p in per_task if p['task'] == t) for t in v)), 2)}
                  for k, v in quad.items()},
    'proven_headroom_best_ge_30': round(proven_hr, 2),
    'proven_headroom_share': round(proven_hr / total_hr, 3) if total_hr else None,
    'conversion_scenarios': {f'{c}%': round(oracle_gain * c / 100, 3) for c in (25, 40, 70, 100)},
    'hard6_detail': hard6_detail,
}
res.update(extras)
json.dump(res, open(os.path.join(os.path.dirname(__file__), 'portfolio_results.json'), 'w'),
          ensure_ascii=False, indent=2)
print('\nQUADRANTS')
for k, v in extras['quadrants'].items():
    print(' ', k, v['n'], 'headroom_sum', v['headroom_sum'])
print('corr(mean,headroom)', extras['corr_taskmean_vs_headroom'],
      'proven share', extras['proven_headroom_share'])
print('hard6 detail', json.dumps(hard6_detail, ensure_ascii=False))
print('conversion', extras['conversion_scenarios'])
