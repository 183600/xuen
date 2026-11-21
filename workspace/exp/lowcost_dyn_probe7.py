import json,glob,os,collections
import numpy as np
from scipy.stats import spearmanr
by=collections.defaultdict(list)
for f in sorted(glob.glob('exp/duo_rows_cache/*.json')):
    t=os.path.basename(f).rsplit('_',1)[0]
    d=json.load(open(f)); by[t].append([x['row'] for x in d['rows']])
alpha=0.9494
def ser(rows,side):
    a=np.asarray([r[f'action.{side}_gripper'] for r in rows]); s=np.asarray([r[f'observation.state.{side}_gripper'] for r in rows])
    arm=np.asarray([r[f'observation.state.{side}_arm'] for r in rows]); ep=np.asarray([r['episode_index'] for r in rows]); return a,s,arm,ep
# per-task: correlation between |arm accel| and gripper model residual, in closed-command frames
print(f"{'task':22s} {'n':>6s} {'rho(accel,resid)':>17s} {'p':>8s}")
for t in sorted(by):
    acc=[]; res=[]
    for rows in by[t]:
        for side in ['left','right']:
            a,s,arm,ep=ser(rows,side); q=s.copy()
            for i in range(1,len(a)):
                if ep[i]!=ep[i-1]: q[i]=s[i]; continue
                q[i]=q[i-1]+alpha*(a[i-1]-q[i-1])
            r=s-q
            v=np.diff(arm,axis=0); ac=np.linalg.norm(np.diff(v,axis=0),axis=1)
            for i in range(2,len(a)):
                if ep[i]!=ep[i-2]: continue
                if a[i]<0.5 and abs(a[i]-a[i-3] if i>=3 else 0)<0.02:
                    acc.append(ac[i-2]); res.append(r[i])
    if len(acc)>50:
        rho,p=spearmanr(acc,res)
        print(f"{t:22s} {len(acc):6d} {rho:+17.3f} {p:8.4f}")
