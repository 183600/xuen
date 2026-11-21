import json, glob, os, collections, math
import numpy as np

files = sorted(glob.glob('exp/duo_rows_cache/*.json'))
by_task = collections.defaultdict(list)
for f in files:
    t = os.path.basename(f).rsplit('_', 1)[0]
    d = json.load(open(f))
    by_task[t].append([x['row'] for x in d['rows']])

def arr(rows, key, dim=None):
    out=[]
    for r in rows:
        v=r[key]
        out.append(v)
    a=np.asarray(out, dtype=np.float64)
    return a

print("task | n_eps n_frames | grip_state[min,max] | grip_resid_mean p95 | arm_resid_mean p95 | grip_act_vel p95 | grip_stall_frac")
allres={}
for t in sorted(by_task):
    eps=by_task[t]
    st=[]; sa=[]; arm_r=[]; gv=[]
    for rows in eps:
        gs_l=arr(rows,'observation.state.left_gripper')
        gs_r=arr(rows,'observation.state.right_gripper')
        ga_l=arr(rows,'action.left_gripper')
        ga_r=arr(rows,'action.right_gripper')
        st.append(np.concatenate([gs_l,gs_r]))
        sa.append(np.concatenate([ga_l,ga_r]))
        for side in ['left','right']:
            a=arr(rows,f'action.{side}_arm'); s=arr(rows,f'observation.state.{side}_arm')
            # tracking residual with best lag 0..3
            best=None
            for lag in range(0,4):
                if lag==0:
                    rr=np.linalg.norm(a-s,axis=1)
                else:
                    rr=np.linalg.norm(a[lag:]-s[:-lag],axis=1)
                m=np.median(rr)
                if best is None or m<best[0]: best=(m,rr)
            arm_r.append(best[1])
        # gripper state velocity magnitude (per frame), both sides
        for side in ['left','right']:
            g=arr(rows,f'observation.state.{side}_gripper')
            gv.append(np.abs(np.diff(g)))
    st=np.concatenate(st); sa=np.concatenate(sa); arm_r=np.concatenate(arm_r); gv=np.concatenate(gv)
    resid=sa-st
    # stall: command closing (sa decreasing) but state not following -> resid large positive
    stall=np.mean(np.abs(resid)>0.05)
    allres[t]=dict(n_eps=len(eps),n_frames=len(st),
        gs_min=float(st.min()),gs_max=float(st.max()),
        resid_mean=float(resid.mean()),resid_p95=float(np.percentile(np.abs(resid),95)),
        arm_mean=float(arm_r.mean()),arm_p95=float(np.percentile(arm_r,95)),
        gvel_p95=float(np.percentile(gv,95)),stall=float(stall))
    print(f"{t:22s} {len(eps):3d} {len(st):6d} | [{st.min():.3f},{st.max():.3f}] | {resid.mean():+.4f} {np.percentile(np.abs(resid),95):.4f} | {arm_r.mean():.4f} {np.percentile(arm_r,95):.4f} | {np.percentile(gv,95):.4f} | {stall:.4f}")

json.dump(allres, open('exp/lowcost_dyn_probe_results.json','w'), indent=2)
print("\nwrote exp/lowcost_dyn_probe_results.json")
