#!/usr/bin/env python3
"""Round-41 probe 2: does *phase-aligned* dataset reuse beat zero-order hold?

Proprio-only cross-episode nearest-neighbour retrieval fails badly (see
dataplane_probe.json q3).  The middleware question is therefore not "cache the
raw state" but "index the dataset by task phase / skill".  Here we test three
retrievers on the same cached real rows:

  ZOH       hold the current action for k steps (no dataset)
  NN_raw    nearest proprio, any episode (the failing baseline)
  NN_phase  nearest proprio among episodes within +-w of the normalized
            episode phase (task-progress alignment)
  MEAN_phase task-phase conditional mean action over ~1000 demos (a compiled
            nominal-trajectory prior; no test-episode leakage)

Metric: normalized action-chunk RMSE (z-scored per task), k=8.
"""
import glob, json, os
from collections import defaultdict
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); EXP = os.path.dirname(HERE)
OBS_FIELDS = ["observation.state.left_arm","observation.state.right_arm",
              "observation.state.left_gripper","observation.state.right_gripper"]
ACT_FIELDS = ["action.left_arm","action.right_arm",
              "action.left_gripper","action.right_gripper"]
K = 8; W = 0.05; NBIN = 40

def frames(task):
    fs=[]
    for p in glob.glob(os.path.join(EXP,"duo_rows_cache",f"{task}_*.json")):
        for it in json.load(open(p)).get("rows",[]): fs.append(it["row"])
    d={int(r["index"]):r for r in fs}
    fs=[d[k] for k in sorted(d)]
    fs.sort(key=lambda r:(int(r["episode_index"]),int(r["frame_index"])))
    return fs

def vec(r,fields):
    o=[]
    for f in fields:
        v=r[f]; o.extend(v if isinstance(v,list) else [v])
    return np.asarray(o,float)

def run(task):
    fs=frames(task)
    if len(fs)<200: return None
    ep=np.array([int(r["episode_index"]) for r in fs])
    fi=np.array([int(r["frame_index"]) for r in fs])
    O=np.vstack([vec(r,OBS_FIELDS) for r in fs]); A=np.vstack([vec(r,ACT_FIELDS) for r in fs])
    On=O/(O.std(0)+1e-8); An=A/(A.std(0)+1e-8)
    emax={e:fi[ep==e].max() for e in set(ep)}
    phase=np.array([fi[i]/max(emax[ep[i]],1) for i in range(len(fs))])
    valid=np.array([i+K<len(fs) and np.all(ep[i:i+K]==ep[i]) for i in range(len(fs))])
    idx=np.where(valid)[0]; q=idx[::10]; mem=idx[::2]
    # phase-conditional mean over memory frames (all episodes), NBIN bins
    bins=np.clip((phase*mem.size/NBIN).astype(int) if False else (phase*NBIN).astype(int),0,NBIN-1)
    meanA={}; 
    for b in range(NBIN):
        sel=mem[bins[mem]==b]
        if len(sel): meanA[b]=An[sel].mean(0)
    stats=defaultdict(list)
    for qi in q:
        amb=ep[mem]==ep[qi]
        true=An[qi:qi+K]; zoh=np.repeat(An[qi][None,:],K,0)
        ## raw NN
        d=np.linalg.norm(On[mem]-On[qi],axis=1); d[amb]=np.inf
        j=int(np.argmin(d)); mi=mem[j]
        stats["NN_raw"].append((np.sqrt(np.mean((An[mi:mi+K]-true)**2)),
                                np.sqrt(np.mean((zoh-true)**2))))
        ## phase-aligned NN
        d2=d.copy(); d2[np.abs(phase[mem]-phase[qi])>W]=np.inf
        if np.isfinite(d2).any():
            j=int(np.argmin(d2)); mi=mem[j]
            stats["NN_phase"].append((np.sqrt(np.mean((An[mi:mi+K]-true)**2)),
                                      np.sqrt(np.mean((zoh-true)**2))))
        ## phase-mean nominal trajectory
        if meanA:
            pred=[]
            for h in range(K):
                b=int(np.clip((phase[qi]+h/max(emax[ep[qi]],1))*NBIN,0,NBIN-1))
                b=min(b,NBIN-1); pred.append(meanA.get(b,An[qi]))
            pred=np.vstack(pred)
            stats["MEAN_phase"].append((np.sqrt(np.mean((pred-true)**2)),
                                        np.sqrt(np.mean((zoh-true)**2))))
    out={}
    for k,v in stats.items():
        if not v: continue
        a=np.array(v); ret=a[:,0]; z=a[:,1]
        out[k]={"n":len(v),"rmse_median":round(float(np.median(ret)),4),
                "zoh_median":round(float(np.median(z)),4),
                "gain_median_pct":round(100*(1-float(np.median(ret)/np.median(z))),1),
                "win_rate":round(float(np.mean(ret<z)),3)}
    return out

def main():
    tasks=sorted({os.path.basename(f).rsplit("_",1)[0] for f in glob.glob(os.path.join(EXP,"duo_rows_cache","*.json"))})
    per={}; 
    for t in tasks:
        r=run(t)
        if r: per[t]=r
    agg=defaultdict(lambda: defaultdict(list))
    for t,r in per.items():
        for k,v in r.items(): agg[k]["gain"].append(v["gain_median_pct"]); agg[k]["win"].append(v["win_rate"])
    summary={k:{"tasks":len(v["gain"]),"median_gain_pct":round(float(np.median(v["gain"])),1),
                "mean_gain_pct":round(float(np.mean(v["gain"])),1),
                "median_win_rate":round(float(np.median(v["win"])),3),
                "tasks_positive":int(sum(1 for g in v["gain"] if g>0))}
             for k,v in agg.items()}
    out={"chunk_len":K,"phase_window":W,"n_tasks":len(per),"summary":summary,"per_task":per}
    json.dump(out,open(os.path.join(HERE,"phase_probe.json"),"w"),ensure_ascii=False,indent=1)
    print(json.dumps(out["summary"],ensure_ascii=False,indent=1))
    for t in sorted(per):
        print(t, {k:v["gain_median_pct"] for k,v in per[t].items()})

if __name__=="__main__": main()
