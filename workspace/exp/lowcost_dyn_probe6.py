import json,glob,os,collections
import numpy as np
from scipy.stats import spearmanr, mannwhitneyu
by=collections.defaultdict(list)
for f in sorted(glob.glob('exp/duo_rows_cache/*.json')):
    t=os.path.basename(f).rsplit('_',1)[0]
    d=json.load(open(f)); by[t].append([x['row'] for x in d['rows']])
def ser(rows,side):
    a=np.asarray([r[f'action.{side}_gripper'] for r in rows]); s=np.asarray([r[f'observation.state.{side}_gripper'] for r in rows]); ep=np.asarray([r['episode_index'] for r in rows]); return a,s,ep
X=[];Y=[];Yp=[]
for rows in by['ConveyorSorting']:
    for side in ['left','right']:
        a,s,ep=ser(rows,side)
        for i in range(1,len(a)):
            if ep[i]!=ep[i-1]: continue
            X.append(a[i-1]-s[i-1]); Y.append(s[i]-s[i-1])
X=np.array(X);Y=np.array(Y); alpha=float((X@Y)/(X@X))
# R2 of one-step prediction on Conveyor
pred=alpha*X; ss_res=((Y-pred)**2).sum(); ss_tot=((Y-Y.mean())**2).sum()
print(f"alpha={alpha:.4f} R2_oneshot={1-ss_res/ss_tot:.4f}")
def mres(t):
    out=[]
    for rows in by[t]:
        for side in ['left','right']:
            a,s,ep=ser(rows,side); q=s.copy()
            for i in range(1,len(a)):
                if ep[i]!=ep[i-1]: q[i]=s[i]; continue
                q[i]=q[i-1]+alpha*(a[i-1]-q[i-1])
            out.append(s-q)
    return np.concatenate(out)
dyn=json.load(open('exp/dynamics_probe_results.json'))['tasks']
rows=[]
for t in sorted(by):
    r=mres(t); rows.append((t,float(r.mean()),float(np.mean(r>0.1)),dyn.get(t,{}).get('lb_mean')))
rows_lb=[(t,m,f,lb) for t,m,f,lb in rows if lb is not None]
print(f"{'task':22s} {'model_resid':>11s} {'frac>0.1':>8s} {'lb_mean':>7s}")
for t,m,f,lb in sorted(rows_lb,key=lambda x:-x[1]):
    print(f"{t:22s} {m:+11.4f} {f:8.3f} {lb:7.2f}")
ms=np.array([x[1] for x in rows_lb]); lbs=np.array([x[3] for x in rows_lb])
rho,p=spearmanr(ms,lbs); print(f"Spearman(model_resid_mean, lb_mean)={rho:+.3f} p={p:.4f} n={len(ms)}")
contact=['PlugInEthernet','DisconnectEthernet','SyringeWaterTransfer','ZipUp','Unlock','PlugCharger','PourOutMedicine']
transport=['ConveyorSorting','ColorArrangement','FruitCollection','ArrangePlates','HangCup','OrganizeBookshelf','FoldTowel','ArrangeTestTubes']
cm=np.array([mres(t).mean() for t in contact]); tm=np.array([mres(t).mean() for t in transport])
u,p=mannwhitneyu(cm,tm,alternative='greater')
print(f"contact group mean={cm.mean():.4f} transport={tm.mean():.4f} MannWhitney p={p:.5f}")
