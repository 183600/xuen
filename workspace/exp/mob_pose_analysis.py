import json,glob,os,re,collections
import numpy as np
from scipy.stats import spearmanr

def task_of(f): return re.match(r'(.+)_(\d+)\.json$',os.path.basename(f)).group(1)
tasks=sorted(set(task_of(f) for f in glob.glob('exp/duo_rows_cache/*.json')))
lb=json.load(open('exp/r16_leaderboard_stats.json'))['per_task']
name2lb={
 'ArrangePlates':'Clear Plates','ArrangeTestTubes':'Arrange Test Tubes','ColorArrangement':'Color Arrangement',
 'ConveyorSorting':'Conveyor Food Sorting','DisconnectEthernet':'Disconnect Ethernet','FoldTowel':'Fold Towel',
 'FruitCollection':'Fruit Basket Collection','HangCup':'Hang the Cup','OrganizeBookshelf':'Organize Bookshelf',
 'PlugCharger':'Plug Charger','PlugInEthernet':'Plug In Ethernet','PourOutMedicine':'Open Pill Bottle',
 'SyringeWaterTransfer':'Syringe Water Transfer','Unlock':'Unlock','ZipUp':'Zip Up'}
lb_by={t['task']:t for t in lb}

def kabsch(A,B):
    ca=A.mean(0); cb=B.mean(0)
    H=(A-ca).T@(B-cb)
    U,S,Vt=np.linalg.svd(H)
    d=np.sign(np.linalg.det(Vt.T@U.T))
    D=np.diag([1,1,d]); R=Vt.T@D@U.T; t=cb-R@ca
    return R,t,S

allres={}
for T in tasks:
    by=collections.defaultdict(list)
    for f in sorted(glob.glob(f'exp/duo_rows_cache/{T}_*.json')):
        for r in json.load(open(f))['rows']: by[r['row']['episode_index']].append(r['row'])
    ep_rows=[]
    for ep,rs in sorted(by.items()):
        rs=sorted(rs,key=lambda r:r['frame_index'])
        if len(rs)<20: continue
        piv=np.array([r['action.pivot'] for r in rs],float)
        bc=np.array([r['action.base_command'] for r in rs],float)
        low=np.array([r['action.lower_body'] for r in rs],float)
        wa=np.array([r['observation.state.waist_state_joint'] for r in rs],float)
        la=np.array([r['action.left_arm'] for r in rs],float); ra=np.array([r['action.right_arm'] for r in rs],float)
        lg=np.array([r['action.left_gripper'] for r in rs],float)[:,None]; rg=np.array([r['action.right_gripper'] for r in rs],float)[:,None]
        pt=np.array([[r['observation.state.left_ee_pose_gripper_torso'][:3],r['observation.state.right_ee_pose_gripper_torso'][:3]] for r in rs]).reshape(-1,3)
        pb=np.array([[r['observation.state.left_ee_pose_gripper_base'][:3],r['observation.state.right_ee_pose_gripper_base'][:3]] for r in rs]).reshape(-1,3)
        ot=np.array([[r['observation.state.left_ee_pose_gripper_torso'][3:],r['observation.state.right_ee_pose_gripper_torso'][3:]] for r in rs]).reshape(-1,3)
        R,tt,S=kabsch(pb,pt)
        res=np.linalg.norm((pb@R.T+tt)-pt,axis=1)
        ang=np.degrees(np.arccos(np.clip((np.trace(R)-1)/2,-1,1)))
        at=np.array([[r['action.left_ee_pose_gripper_torso'][:3],r['action.right_ee_pose_gripper_torso'][:3]] for r in rs]).reshape(-1,3)
        obsL=pt[0::2]; obsR=pt[1::2]; actL=at[0::2]; actR=at[1::2]
        e=np.vstack([obsL[1:]-actL[:-1],obsR[1:]-actR[:-1]])
        dp = np.concatenate([np.linalg.norm(np.diff(pt[0::2],axis=0),axis=1),np.linalg.norm(np.diff(pt[1::2],axis=0),axis=1)])
        do = np.concatenate([np.linalg.norm(np.diff(ot[0::2],axis=0),axis=1),np.linalg.norm(np.diff(ot[1::2],axis=0),axis=1)])
        ep_rows.append(dict(ep=ep,n=len(rs),piv=piv,bc=bc,low=low,wa=wa,la=la,ra=ra,lg=lg,rg=rg,
                            pt=pt,pb=pb,ot=ot,R=R,tt=tt,res=res,ang=ang,track=e,dp=dp,do=do))
    n=sum(e['n'] for e in ep_rows)
    def within_std(x): return float(np.mean([e[x].std(0).mean() for e in ep_rows]))
    def across_std(x): return float(np.array([e[x].mean(0) for e in ep_rows]).std(0).mean())
    pt=np.vstack([e['pt'] for e in ep_rows]); pb=np.vstack([e['pb'] for e in ep_rows]); ot=np.vstack([e['ot'] for e in ep_rows])
    track=np.vstack([e['track'] for e in ep_rows]); res=np.concatenate([e['res'] for e in ep_rows])
    dp=np.concatenate([e['dp'] for e in ep_rows]); do=np.concatenate([e['do'] for e in ep_rows])
    angs=np.array([e['ang'] for e in ep_rows]); waist=np.vstack([e['wa'] for e in ep_rows])
    # action variance share (arms+grip vs pivot vs lower)
    A=np.vstack([np.hstack([e['la'],e['ra'],e['lg'],e['rg']]) for e in ep_rows])
    P=np.vstack([e['piv'] for e in ep_rows]); L=np.vstack([e['low'] for e in ep_rows])
    vA=float(A.var(0).sum()); vP=float(P.var(0).sum()); vL=float(L.var(0).sum())
    allres[T]=dict(n=n,n_ep=len(ep_rows),
        piv_within=within_std('piv'),bc_within=within_std('bc'),low_within=within_std('low'),waist_within=within_std('wa'),
        piv_across=across_std('piv'),bc_across=across_std('bc'),low_across=across_std('low'),waist_across=across_std('wa'),
        pt_mean=pt.mean(0).tolist(),pt_span=(pt.max(0)-pt.min(0)).tolist(),
        pt_r_xy_mean=float(np.linalg.norm(pt[:,:2],axis=1).mean()),
        pb_span=(pb.max(0)-pb.min(0)).tolist(),
        track_rms_mm=float(np.sqrt((track**2).sum(1).mean())*1000),
        track_mean_mm=float(np.linalg.norm(track,axis=1).mean()*1000),
        pos_step_mm=float(dp.mean()*1000), ori_step=float(do.mean()),
        frame_res_mm=float(res.mean()*1000),frame_res_max_mm=float(res.max()*1000),frame_ang=float(angs.mean()),
        waist_mean=waist.mean(0).tolist(),
        var_share_arm=float(vA/(vA+vP+vL)),var_share_pivot=float(vP/(vA+vP+vL)),var_share_lower=float(vL/(vA+vP+vL)))
    r=allres[T]; Lb=lb_by[name2lb[T]]
    r['task_lb']=name2lb[T]; r['lb_mean']=Lb['mean']; r['difficulty']=Lb['difficulty']; r['rubric_steps']=Lb['rubric_steps']

json.dump(allres,open('exp/mob_pose_results.json','w'),indent=1,ensure_ascii=False)
print(f"{'task':22s} {'mean':>5s} {'diff':>6s} {'pivW':>6s} {'lowW':>6s} {'waW':>6s} {'rxy':>5s} {'zspan':>6s} {'trk':>5s} {'step':>5s} {'fres':>5s} {'ori':>6s} {'arm%':>5s}")
for T in tasks:
    r=allres[T]
    print(f"{T:22s} {r['lb_mean']:5.1f} {r['difficulty']:>6s} {r['piv_within']:6.4f} {r['low_within']:6.3f} {r['waist_within']:6.3f} {r['pt_r_xy_mean']:5.3f} {r['pt_span'][2]:6.3f} {r['track_rms_mm']:5.1f} {r['pos_step_mm']:5.1f} {r['frame_res_mm']:5.2f} {r['ori_step']:6.3f} {100*r['var_share_arm']:5.1f}")
succ=np.array([allres[T]['lb_mean'] for T in tasks])
print('--- Spearman vs lb_mean ---')
for k in ['pt_r_xy_mean','track_rms_mm','frame_res_mm','frame_ang','waist_within','low_within','ori_step','pos_step_mm','rubric_steps','zspan','var_share_arm']:
    v=np.array([allres[T]['pt_span'][2] if k=='zspan' else allres[T][k] for T in tasks])
    rho,p=spearmanr(v,succ); print(f'{k:16s} rho={rho:+.3f} p={p:.3f}')
print('--- summary ---')
for k in ['piv_within','low_within','waist_within','piv_across','track_rms_mm','pos_step_mm','frame_res_mm','frame_ang','var_share_arm','var_share_pivot','var_share_lower']:
    v=np.array([allres[T][k] for T in tasks]); print(f'{k:16s} mean={v.mean():.5f} min={v.min():.5f} max={v.max():.5f}')
