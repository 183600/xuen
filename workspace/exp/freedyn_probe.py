"""Free-space gripper dynamics -> training-free contact/stall detector.

Data: exp/duo_rows_cache (HF datasets-server pages, 15/32 tasks, first 3000
frames/task, state+action only, 30 Hz).  This is a subset probe, not the
full UniBot benchmark.  Run: PYTHONPATH=.pylibs python exp/freedyn_probe.py
"""
import json, glob, os, collections
import numpy as np
from scipy.stats import spearmanr, mannwhitneyu

CACHE = 'exp/duo_rows_cache'
TAU = 0.10          # contact threshold on free-space residual
K_HOLD = 2          # consecutive frames to declare contact
FREE_TASK = 'ConveyorSorting'   # no object in sampled closed frames (proxy)
CONTACT = ['PlugInEthernet','DisconnectEthernet','SyringeWaterTransfer',
           'ZipUp','Unlock','PlugCharger','PourOutMedicine']
TRANSPORT = ['ConveyorSorting','ColorArrangement','FruitCollection',
             'ArrangePlates','HangCup','OrganizeBookshelf','FoldTowel',
             'ArrangeTestTubes']

by = collections.defaultdict(list)
for f in sorted(glob.glob(os.path.join(CACHE, '*.json'))):
    t = os.path.basename(f).rsplit('_', 1)[0]
    d = json.load(open(f))
    by[t].append([x['row'] for x in d['rows']])

def ser(rows, side):
    a = np.asarray([r[f'action.{side}_gripper'] for r in rows], float)
    s = np.asarray([r[f'observation.state.{side}_gripper'] for r in rows], float)
    ep = np.asarray([r['episode_index'] for r in rows])
    return a, s, ep

# ---- 1. fit one scalar: free-space first-order closing gain ----
X, Y = [], []
for rows in by[FREE_TASK]:
    for side in ('left', 'right'):
        a, s, ep = ser(rows, side)
        for i in range(1, len(a)):
            if ep[i] == ep[i-1]:
                X.append(a[i-1] - s[i-1]); Y.append(s[i] - s[i-1])
X = np.array(X); Y = np.array(Y)
alpha = float((X @ Y) / (X @ X))
pred = alpha * X
r2 = float(1 - ((Y - pred) ** 2).sum() / ((Y - Y.mean()) ** 2).sum())

# ---- 2. free-space open offset (unloaded calibration) ----
free_open = []
for t in by:
    for rows in by[t]:
        for side in ('left', 'right'):
            a, s, ep = ser(rows, side)
            for i in range(3, len(a)):
                if ep[i] == ep[i-3] and abs(a[i]-a[i-3]) < 0.02 and a[i] > 4.0:
                    free_open.append(s[i] - a[i])
free_open = np.array(free_open)

# ---- 3. residual per task under the free-space model ----
def resid(t):
    out = []
    for rows in by[t]:
        for side in ('left', 'right'):
            a, s, ep = ser(rows, side)
            q = s.copy()
            for i in range(1, len(a)):
                if ep[i] != ep[i-1]:
                    q[i] = s[i]
                else:
                    q[i] = q[i-1] + alpha * (a[i-1] - q[i-1])
            out.append(s - q)
    return np.concatenate(out)

dyn = json.load(open('exp/dynamics_probe_results.json'))['tasks']
per_task = {}
for t in sorted(by):
    r = resid(t)
    per_task[t] = dict(n=int(len(r)), mean=float(r.mean()), std=float(r.std()),
                       frac_gt_tau=float(np.mean(r > TAU)),
                       frac_gt_2tau=float(np.mean(r > 2*TAU)),
                       lb_mean=dyn.get(t, {}).get('lb_mean'))
    r = resid(t)

# ---- 4. separability: free vs contact ----
neg = resid(FREE_TASK)
pos = np.concatenate([resid(t) for t in CONTACT if t in by])
allv = np.concatenate([neg, pos])
ranks = np.argsort(np.argsort(allv, kind='mergesort'), kind='mergesort') + 1
auc = float((ranks[len(neg):].sum() - len(pos)*(len(pos)+1)/2) / (len(neg)*len(pos)))
precision_at_tau = float(1 - np.mean(neg > TAU))
recall_at_tau = float(np.mean(pos > TAU))

# ---- 5. detection latency from close onset to sustained residual ----
lat = []
for t in CONTACT:
    if t not in by: continue
    for rows in by[t]:
        for side in ('left', 'right'):
            a, s, ep = ser(rows, side)
            q = s.copy()
            for i in range(1, len(a)):
                q[i] = s[i] if ep[i] != ep[i-1] else q[i-1] + alpha*(a[i-1]-q[i-1])
            r = s - q
            for i in range(1, len(a)):
                if ep[i] != ep[i-1] or not (a[i-1] >= 0.5 and a[i] < 0.5):
                    continue
                for j in range(i, min(i+30, len(a))):
                    if ep[j] != ep[i]: break
                    if all(r[k] > TAU for k in range(j, min(j+K_HOLD, len(a)))):
                        lat.append(j - i); break
lat = np.array(lat) if lat else np.array([np.nan])

# ---- 6. group test + weak teaser correlation ----
cm = np.array([per_task[t]['mean'] for t in CONTACT if t in by])
tm = np.array([per_task[t]['mean'] for t in TRANSPORT if t in by])
u, p_group = mannwhitneyu(cm, tm, alternative='greater')
lb = [(per_task[t]['mean'], per_task[t]['lb_mean']) for t in per_task
      if per_task[t]['lb_mean'] is not None]
rho, p_rho = spearmanr([x[0] for x in lb], [x[1] for x in lb])

out = dict(alpha=alpha, r2_oneshot=r2, tau=TAU, k_hold=K_HOLD,
           free_open=dict(n=int(len(free_open)), mean=float(free_open.mean()),
                          std=float(free_open.std()),
                          p95abs=float(np.percentile(np.abs(free_open), 95))),
           free_resid=dict(mean=float(neg.mean()), std=float(neg.std()),
                           p95=float(np.percentile(neg, 95))),
           contact_resid=dict(mean=float(pos.mean()), std=float(pos.std()),
                              frac_gt_tau=recall_at_tau),
           auc_pos_gt_neg=auc, precision_at_tau=precision_at_tau,
           recall_at_tau=recall_at_tau,
           latency_frames=dict(n=int(len(lat)), median=float(np.nanmedian(lat)),
                               p90=float(np.nanpercentile(lat, 90)),
                               median_ms=float(np.nanmedian(lat)/30*1000)),
           group=dict(contact_mean=float(cm.mean()), transport_mean=float(tm.mean()),
                      mannwhitney_p=float(p_group)),
           teaser_spearman=dict(rho=float(rho), p=float(p_rho), n=len(lb)),
           per_task=per_task,
           caveat='15/32 tasks, first 3000 frames/task, state+action only; '
                  'task-level contact labels heuristic; teaser leaderboard is placeholder.')
json.dump(out, open('exp/freedyn_probe_results.json', 'w'), indent=2)
print(json.dumps({k: v for k, v in out.items() if k != 'per_task'}, indent=2))
