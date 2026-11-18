"""UniBot-PIVOT round-1 summary: recompute headline numbers from exp/duo_rows_cache.
Run: PYTHONPATH=.venv/lib/python3.12/site-packages:.pylibs python3 exp/pivot_summary.py
"""
import json,glob,os,re,collections
import numpy as np

def task_of(f): return re.match(r'(.+)_(\d+)\.json$',os.path.basename(f)).group(1)
tasks=sorted(set(task_of(f) for f in glob.glob('exp/duo_rows_cache/*.json')))
mp=json.load(open('exp/mob_pose_results.json'))
pc=json.load(open('exp/pose_calib_results.json'))
# velocity model
X=[];Y=[]
for T in tasks:
    by=collections.defaultdict(list)
    for f in sorted(glob.glob(f'exp/duo_rows_cache/{T}_*.json')):
        for r in json.load(open(f))['rows']: by[r['row']['episode_index']].append(r['row'])
    for ep,rs in by.items():
        rs=sorted(rs,key=lambda r:r['frame_index'])
        for side in ['left','right']:
            ob=np.array([r[f'observation.state.{side}_ee_pose_gripper_torso'][:3] for r in rs])
            ac=np.array([r[f'action.{side}_ee_pose_gripper_torso'][:3] for r in rs])
            v=np.gradient(ob,axis=0)*30.0; a=np.gradient(ac,axis=0)*30.0
            d=ac-ob; n=min(len(d),len(v)); sl=slice(1,n-1)
            X.append(np.hstack([v[sl],a[sl]])); Y.append(d[sl])
X=np.vstack(X);Y=np.vstack(Y)
Xf=np.hstack([np.ones((len(X),1)),X])
beta,_,_,_=np.linalg.lstsq(Xf,Y,rcond=None)
pred=Xf@beta
rms=lambda A: float(np.sqrt((A**2).sum(1).mean())*1000)
r2=1-((Y-pred)**2).sum()/((Y-Y.mean(0))**2).sum()
summary={
 'data':{'tasks':len(tasks),'episodes':int(sum(mp[t]['n_ep'] for t in tasks)),
         'frames':int(sum(mp[t]['n'] for t in tasks)),'control_hz':30},
 'body':{'pivot_within_std':float(np.mean([mp[t]['piv_within'] for t in tasks])),
         'pivot_across_std':float(np.mean([mp[t]['piv_across'] for t in tasks])),
         'lower_within_std':float(np.mean([mp[t]['low_within'] for t in tasks])),
         'waist_within_std':float(np.mean([mp[t]['waist_within'] for t in tasks])),
         'var_share_arm':float(np.mean([mp[t]['var_share_arm'] for t in tasks])),
         'var_share_pivot':float(np.mean([mp[t]['var_share_pivot'] for t in tasks])),
         'var_share_lower':float(np.mean([mp[t]['var_share_lower'] for t in tasks]))},
 'frame_kabsch':{'res_mean_mm':float(np.mean([mp[t]['frame_res_mm'] for t in tasks])),
                 'res_min_mm':float(np.min([mp[t]['frame_res_mm'] for t in tasks])),
                 'res_max_mm':float(np.max([mp[t]['frame_res_mm'] for t in tasks])),
                 'angle_deg_mean':float(np.mean([mp[t]['frame_ang'] for t in tasks]))},
 'pose_gap':{'same_frame_mm_mean':float(np.mean([pc[t]['same_offset_mm'] for t in tasks])),
             'same_frame_p90_mm_mean':float(np.mean([pc[t]['same_offset_p90_mm'] for t in tasks])),
             'ori_deg_mean':float(np.mean([pc[t]['ori_offset_deg'] for t in tasks])),
             'best_lag_frames_median':int(np.median([pc[t]['best_lag'] for t in tasks])),
             'best_lag_res_mm_mean':float(np.mean([pc[t]['best_lag_res_mm'] for t in tasks])),
             'const_corrected_rms_mm':rms(Y-Y.mean(0)),
             'velocity_model_r2':float(r2),
             'velocity_model_rms_mm':rms(Y-pred),
             'raw_rms_mm':rms(Y)},
 'workspace':{'r_xy_mean_m':float(np.mean([mp[t]['pt_r_xy_mean'] for t in tasks])),
              'z_span_min_m':float(np.min([mp[t]['pt_span'][2] for t in tasks])),
              'z_span_max_m':float(np.max([mp[t]['pt_span'][2] for t in tasks]))},
 'virtual_base':{'leverage_cm_per_10deg':float(2*np.mean([mp[t]['pt_r_xy_mean'] for t in tasks])*np.sin(np.radians(5))*100)},
}
json.dump(summary,open('exp/pivot_summary.json','w'),indent=1,ensure_ascii=False)
print(json.dumps(summary,indent=1,ensure_ascii=False))
