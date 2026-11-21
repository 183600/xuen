import json,glob,os,collections
import numpy as np
by=collections.defaultdict(list)
for f in sorted(glob.glob('exp/duo_rows_cache/*.json')):
    t=os.path.basename(f).rsplit('_',1)[0]
    d=json.load(open(f)); by[t].append([x['row'] for x in d['rows']])

def residuals(rows, side):
    a=np.asarray([r[f'action.{side}_gripper'] for r in rows])
    s=np.asarray([r[f'observation.state.{side}_gripper'] for r in rows])
    ep=np.asarray([r['episode_index'] for r in rows])
    return a,s,ep

def steady_closed(t):
    out=[]
    for rows in by[t]:
        for side in ['left','right']:
            a,s,ep=residuals(rows,side)
            for i in range(3,len(a)):
                if ep[i]!=ep[i-3]: continue
                if abs(a[i]-a[i-3])<0.02 and a[i]<0.5:
                    out.append(s[i]-a[i])
    return np.array(out) if out else np.array([])

def free_open(t):
    out=[]
    for rows in by[t]:
        for side in ['left','right']:
            a,s,ep=residuals(rows,side)
            for i in range(3,len(a)):
                if ep[i]!=ep[i-3]: continue
                if abs(a[i]-a[i-3])<0.02 and a[i]>4.0:
                    out.append(s[i]-a[i])
    return np.array(out) if out else np.array([])

fo=np.concatenate([free_open(t) for t in by if len(free_open(t))])
print(f"free-open offset: n={len(fo)} mean={fo.mean():+.4f} std={fo.std():.4f} p95abs={np.percentile(np.abs(fo),95):.4f}")

freeclosed=steady_closed('ConveyorSorting')
print(f"ConveyorSorting (free-closed proxy): n={len(freeclosed)} mean={freeclosed.mean():+.4f} std={freeclosed.std():.4f} p95={np.percentile(freeclosed,95):+.4f}")

contact_tasks=['PlugInEthernet','DisconnectEthernet','SyringeWaterTransfer','ZipUp']
pos=np.concatenate([steady_closed(t) for t in contact_tasks if len(steady_closed(t))])
print(f"contact-rich (4 tasks): n={len(pos)} mean={pos.mean():+.4f} std={pos.std():.4f} p05={np.percentile(pos,5):+.4f}")

# AUC via rank
def auc(neg,pos):
    allv=np.concatenate([neg,pos]); ranks=np.argsort(np.argsort(allv))+1
    rn=ranks[:len(neg)].sum(); return (rn-len(neg)*(len(neg)+1)/2)/(len(neg)*len(pos))
print(f"AUC(ConveyorSorting free-closed vs contact-rich) = {auc(freeclosed,pos):.3f}")

# detection latency: at a closing transition, frames until resid>0.1
lats=[]
for t in contact_tasks:
    for rows in by[t]:
        for side in ['left','right']:
            a,s,ep=residuals(rows,side)
            for i in range(1,len(a)):
                if ep[i]!=ep[i-1]: continue
                if a[i-1]>=0.5 and a[i]<0.5:  # close onset
                    r=s[i:]-a[i:]
                    hit=np.where(r>0.10)[0]
                    if len(hit): lats.append(hit[0])
lats=np.array(lats)
if len(lats):
    print(f"detection latency (frames@30Hz) after close onset: n={len(lats)} med={np.median(lats):.0f} ({np.median(lats)/30*1000:.0f} ms) p90={np.percentile(lats,90):.0f}")

# blocked fraction at threshold 0.1
for t in ['ConveyorSorting','PlugInEthernet','DisconnectEthernet','SyringeWaterTransfer','ZipUp','HangCup','FoldTowel','ArrangePlates']:
    r=steady_closed(t)
    if len(r): print(f"  {t:22s} n={len(r):5d} frac(resid>0.10)={np.mean(r>0.10):.3f} frac(resid>0.20)={np.mean(r>0.20):.3f}")
