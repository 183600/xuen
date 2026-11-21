import json, glob, os, collections
import numpy as np

files = sorted(glob.glob('exp/duo_rows_cache/*.json'))
by_task = collections.defaultdict(list)
for f in files:
    t = os.path.basename(f).rsplit('_', 1)[0]
    d = json.load(open(f))
    by_task[t].append([x['row'] for x in d['rows']])

def vec(rows,key):
    return np.asarray([r[key] for r in rows],dtype=np.float64)

out={}
for t in sorted(by_task):
    close_block=[]; close_n=0; blocked_n=0
    slip_ev=[]; trans_n=0
    grip_res=[]; arm_speed=[]
    for rows in by_task[t]:
        for side in ['left','right']:
            a=vec(rows,f'action.{side}_gripper')
            s=vec(rows,f'observation.state.{side}_gripper')
            da=np.diff(a)
            ds=s[1:]-a[1:]
            # closing frames: action decreases (toward 0)
            cm=da < -0.02
            if cm.sum()>0:
                close_n+=int(cm.sum())
                blocked_n+=int((ds[cm] > 0.05).sum())
                close_block.append(ds[cm])
            # transport: gripper closed (action<1.0), arm moving
            arm=vec(rows,f'action.{side}_arm')
            av=np.linalg.norm(np.diff(arm,axis=0),axis=1)
            gm=(a[1:]<1.0)
            mv=av>0.02
            # slip proxy: state opens while commanded closed during motion
            sl=gm & mv & (np.diff(s)>0.01)
            if (gm&mv).sum()>0:
                trans_n+=int((gm&mv).sum()); slip_ev.append(int(sl.sum()))
            grip_res.append(np.abs(s-a)); arm_speed.append(av)
    cb=np.concatenate(close_block) if close_block else np.array([0.0])
    out[t]=dict(close_blocked_frac=(blocked_n/close_n if close_n else 0.0),
                close_pos_resid_mean=float(cb.mean()), close_pos_resid_p90=float(np.percentile(cb,90)),
                slip_frac=(sum(slip_ev)/trans_n if trans_n else 0.0),
                n_close=close_n, n_trans=trans_n)
    print(f"{t:22s} blocked={out[t]['close_blocked_frac']:.3f} close_resid={out[t]['close_pos_resid_mean']:+.3f} p90={out[t]['close_pos_resid_p90']:.3f} slip={out[t]['slip_frac']:.4f}")

json.dump(out,open('exp/lowcost_dyn_probe2_results.json','w'),indent=2)

contact_rich=['PlugInEthernet','Unlock','PlugCharger','SyringeWaterTransfer','ZipUp','DisconnectEthernet','PourOutMedicine']
transport=['ConveyorSorting','ColorArrangement','FruitCollection','ArrangePlates','HangCup','OrganizeBookshelf','FoldTowel','ArrangeTestTubes']
def mean(keys,k): return float(np.mean([out[t][k] for t in keys if t in out]))
print("\nGROUP MEANS")
for k in ['close_blocked_frac','close_pos_resid_mean','slip_frac']:
    a=mean(contact_rich,k); b=mean(transport,k)
    print(f"  {k:22s} contact-rich={a:.4f}  transport={b:.4f}  ratio={a/b if b else float('nan'):.2f}")
