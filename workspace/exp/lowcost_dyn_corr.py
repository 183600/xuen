import json, numpy as np
from scipy.stats import spearmanr, pearsonr

probe=json.load(open('exp/lowcost_dyn_probe_results.json'))
dyn=json.load(open('exp/dynamics_probe_results.json'))['tasks']
# map task -> lb_mean and difficulty
rows=[]
for t,v in probe.items():
    if t in dyn:
        rows.append((t, v, dyn[t]['lb_mean'], dyn[t].get('difficulty')))
rows.sort(key=lambda r:r[2])
print(f"{'task':22s} {'lb_mean':>7s} {'stall':>6s} {'arm_p95':>7s} {'grip_p95':>8s}")
for t,v,lb,d in rows:
    print(f"{t:22s} {lb:7.2f} {v['stall']:6.3f} {v['arm_p95']:7.4f} {v['resid_p95']:8.4f}")
lb=np.array([r[2] for r in rows])
for key in ['stall','arm_p95','arm_mean','resid_p95','gvel_p95']:
    x=np.array([r[1][key] for r in rows])
    rho,p=spearmanr(x,lb)
    print(f"Spearman({key:10s}, lb_mean) = {rho:+.3f}  p={p:.4f}")
