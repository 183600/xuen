import json,glob,os,re,collections
import numpy as np
from scipy.stats import spearmanr

def task_of(f): return re.match(r'(.+)_(\d+)\.json$',os.path.basename(f)).group(1)
tasks=sorted(set(task_of(f) for f in glob.glob('exp/duo_rows_cache/*.json')))
lb={t['task']:t for t in json.load(open('exp/r16_leaderboard_stats.json'))['per_task']}
name2lb={'ArrangePlates':'Clear Plates','ArrangeTestTubes':'Arrange Test Tubes','ColorArrangement':'Color Arrangement','ConveyorSorting':'Conveyor Food Sorting','DisconnectEthernet':'Disconnect Ethernet','FoldTowel':'Fold Towel','FruitCollection':'Fruit Basket Collection','HangCup':'Hang the Cup','OrganizeBookshelf':'Organize Bookshelf','PlugCharger':'Plug Charger','PlugInEthernet':'Plug In Ethernet','PourOutMedicine':'Open Pill Bottle','SyringeWaterTransfer':'Syringe Water Transfer','Unlock':'Unlock','ZipUp':'Zip Up'}

def load(T):
    by=collections.defaultdict(list)
    for f in sorted(glob.glob(f'exp/duo_rows_cache/{T}_*.json')):
        for r in json.load(open(f))['rows']: by[r['row']['episode_index']].append(r['row'])
    return {ep:sorted(rs,key=lambda r:r['frame_index']) for ep,rs in by.items()}

res={}
for T in tasks:
    eps=load(T)
    same=[]; best=[]; offb=[]; ori=[]; offsets=[]; rots=[]
    for ep,rs in eps.items():
        for side in ['left','right']:
            ob=np.array([r[f'observation.state.{side}_ee_pose_gripper_torso'][:3] for r in rs])
            ac=np.array([r[f'action.{side}_ee_pose_gripper_torso'][:3] for r in rs])
            oo=np.array([r[f'observation.state.{side}_ee_pose_gripper_torso'][3:] for r in rs])
            ao=np.array([r[f'action.{side}_ee_pose_gripper_torso'][3:] for r in rs])
            same.append(np.linalg.norm(ob-ac,axis=1))
            ori.append(np.linalg.norm(oo-ao,axis=1))
            d=ac-ob
            offsets.append(d)
            # in EE local frame: rotate offset by orientation (approx, treat ori as direction set)
            # best lag
            bests=[]
            for lag in range(0,7):
                o=ob[lag:]; a=ac[:len(ac)-lag]
                if len(o)<10: break
                bests.append(np.linalg.norm(o-a,axis=1).mean())
            best.append((int(np.argmin(bests)),bests[int(np.argmin(bests))]))
    same=np.concatenate(same); ori=np.concatenate(ori)
    offs=np.vstack(offsets)
    # circular-ish consistency of offset direction (unit vectors)
    un=offs/np.maximum(np.linalg.norm(offs,axis=1,keepdims=True),1e-9)
    mean_dir=un.mean(0); dir_consistency=float(np.linalg.norm(mean_dir))
    bestlag=int(np.median([b[0] for b in best]))
    bestres=float(np.mean([b[1] for b in best]))
    res[T]=dict(same_offset_mm=float(same.mean()*1000),same_offset_p90_mm=float(np.percentile(same,90)*1000),
                same_offset_std_mm=float(same.std()*1000),ori_offset_deg=float(np.degrees(ori.mean())),
                best_lag=bestlag,best_lag_res_mm=bestres*1000,
                offset_mean=offs.mean(0).tolist(),offset_dir_consistency=dir_consistency,
                lb_mean=lb[name2lb[T]]['mean'],difficulty=lb[name2lb[T]]['difficulty'])
    r=res[T]
    print(f"{T:22s} succ={r['lb_mean']:5.1f} offset={r['same_offset_mm']:5.1f}mm p90={r['same_offset_p90_mm']:5.1f} ori={r['ori_offset_deg']:4.1f}deg lag*={r['best_lag']} best={r['best_lag_res_mm']:5.1f} dircons={r['offset_dir_consistency']:.2f} off={np.round(r['offset_mean'],3)}")

succ=np.array([res[T]['lb_mean'] for T in tasks])
print('--- corr ---')
for k in ['same_offset_mm','ori_offset_deg','best_lag_res_mm','offset_dir_consistency']:
    v=np.array([res[T][k] for T in tasks]); rho,p=spearmanr(v,succ); print(f'{k:22s} rho={rho:+.3f} p={p:.3f}')
json.dump(res,open('exp/pose_calib_results.json','w'),indent=1,ensure_ascii=False)
