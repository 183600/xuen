import json,glob,os,collections
import numpy as np
by=collections.defaultdict(list)
for f in sorted(glob.glob('exp/duo_rows_cache/*.json')):
    t=os.path.basename(f).rsplit('_',1)[0]
    d=json.load(open(f)); by[t].append([x['row'] for x in d['rows']])

out={}
for t in sorted(by):
    stall=[]; freeopen=[]; steady_closed_n=0; blocked_n=0
    for rows in by[t]:
        for side in ['left','right']:
            a=np.asarray([r[f'action.{side}_gripper'] for r in rows])
            s=np.asarray([r[f'observation.state.{side}_gripper'] for r in rows])
            d3=np.abs(a[3:]-a[:-3]); st=slice(3,None)
            aa=a[3:]; ss=s[3:]
            steady=d3<0.02
            closed=aa<0.5
            m=steady&closed
            if m.sum()>0:
                r=ss[m]-aa[m]
                stall.append(r)
                steady_closed_n+=int(m.sum()); blocked_n+=int((r>0.10).sum())
            mo=steady&(aa>4.0)
            if mo.sum()>0: freeopen.append(ss[mo]-aa[mo])
    st=np.concatenate(stall) if stall else np.array([0.0])
    fo=np.concatenate(freeopen) if freeopen else np.array([0.0])
    out[t]=dict(n=steady_closed_n, stall_med=float(np.median(st)), stall_mean=float(st.mean()),
                blocked_frac=float(blocked_n/steady_closed_n) if steady_closed_n else 0.0,
                open_offset_mean=float(fo.mean()), open_offset_med=float(np.median(fo)))
    print(f"{t:22s} n={steady_closed_n:6d} stall_med={out[t]['stall_med']:+.3f} mean={out[t]['stall_mean']:+.3f} blocked>0.1={out[t]['blocked_frac']:.3f} open_off={out[t]['open_offset_mean']:+.4f}")
json.dump(out,open('exp/lowcost_dyn_probe3_results.json','w'),indent=2)
