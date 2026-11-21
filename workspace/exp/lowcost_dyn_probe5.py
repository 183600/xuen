import json,glob,os,collections
import numpy as np
by=collections.defaultdict(list)
for f in sorted(glob.glob('exp/duo_rows_cache/*.json')):
    t=os.path.basename(f).rsplit('_',1)[0]
    d=json.load(open(f)); by[t].append([x['row'] for x in d['rows']])

def series(rows,side):
    a=np.asarray([r[f'action.{side}_gripper'] for r in rows])
    s=np.asarray([r[f'observation.state.{side}_gripper'] for r in rows])
    ep=np.asarray([r['episode_index'] for r in rows])
    return a,s,ep

# ---- fit first-order free-space closing model on ConveyorSorting (no load) ----
X=[];Y=[]
for rows in by['ConveyorSorting']:
    for side in ['left','right']:
        a,s,ep=series(rows,side)
        for i in range(1,len(a)):
            if ep[i]!=ep[i-1]: continue
            X.append(a[i-1]-s[i-1]); Y.append(s[i]-s[i-1])
X=np.array(X);Y=np.array(Y)
alpha=float((X@Y)/(X@X))
print(f"free-space first-order closing gain alpha={alpha:.4f}  (tau={1/alpha:.2f} frames = {1000/(alpha*30):.0f} ms)  n={len(X)}")

def model_resid(t,side_filter=None):
    res=[]
    for rows in by[t]:
        for side in ['left','right']:
            a,s,ep=series(rows,side)
            q=s.copy()
            for i in range(1,len(a)):
                if ep[i]!=ep[i-1]:
                    q[i]=s[i]; continue
                pred=q[i-1]+alpha*(a[i-1]-q[i-1])
                q[i]=pred
            res.append(s-q)
    return np.concatenate(res)

for t in ['ConveyorSorting','PlugInEthernet','DisconnectEthernet','SyringeWaterTransfer','ZipUp','HangCup','FoldTowel','ArrangePlates','Unlock']:
    r=model_resid(t)
    print(f"  {t:22s} n={len(r):6d} model_resid mean={r.mean():+.4f} std={r.std():.4f} frac>0.1={np.mean(r>0.1):.3f} frac>0.2={np.mean(r>0.2):.3f}")

neg=model_resid('ConveyorSorting')
pos=np.concatenate([model_resid(t) for t in ['PlugInEthernet','DisconnectEthernet','SyringeWaterTransfer','ZipUp']])
def auc_pos_gt_neg(neg,pos):
    # P(pos>neg)
    allv=np.concatenate([neg,pos]); ranks=np.argsort(np.argsort(allv,kind='mergesort'),kind='mergesort')+1
    rp=ranks[len(neg):].sum(); return (rp-len(pos)*(len(pos)+1)/2)/(len(neg)*len(pos))
print(f"AUC P(contact-resid > free-resid) = {auc_pos_gt_neg(neg,pos):.4f}")

# latency: from close onset (action crosses <0.5) to model resid>0.1 for 3 consecutive frames
lats=[]
for t in ['PlugInEthernet','DisconnectEthernet','SyringeWaterTransfer','ZipUp']:
    for rows in by[t]:
        for side in ['left','right']:
            a,s,ep=series(rows,side)
            q=s.copy()
            for i in range(1,len(a)):
                if ep[i]!=ep[i-1]: q[i]=s[i]; continue
                q[i]=q[i-1]+alpha*(a[i-1]-q[i-1])
            r=s-q
            for i in range(1,len(a)):
                if ep[i]!=ep[i-1]: continue
                if a[i-1]>=0.5 and a[i]<0.5:
                    for j in range(i,len(a)):
                        if ep[j]!=ep[i]: break
                        if r[j]>0.1 and j+2<len(a) and r[j+1]>0.1 and r[j+2]>0.1:
                            lats.append(j-i); break
lats=np.array(lats)
if len(lats):
    print(f"latency close-onset -> sustained resid>0.1: n={len(lats)} med={np.median(lats):.0f} fr ({(np.median(lats))/30*1000:.0f} ms) p90={np.percentile(lats,90):.0f} fr")
