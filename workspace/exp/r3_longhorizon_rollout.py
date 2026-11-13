"""Round-3 toy: closed-loop linear BC vs dynamics-only rollout on cached G1_Dex1
trajectories (D-level mechanism check, NOT robot evidence)."""
import json, glob, os
import numpy as np

HS = [1, 2, 4, 8, 16, 32, 64]
TASKS = {'G1_Dex1_ArrangeTestTubes':'T13','G1_Dex1_ConveyorSorting':'T24',
 'G1_Dex1_FoldTowel':'T16','G1_Dex1_HangCup':'T01','G1_Dex1_OrganizeTools':'T15',
 'G1_Dex1_PackDoll':'T03','G1_Dex1_PlugInEthernet':'T26','G1_Dex1_SpellRobot':'T22',
 'G1_Dex1_StackBowls':'T27','G1_Dex1_ToolboxStorage':'T09','G1_Dex1_Unlock':'T12',
 'G1_Dex1_ZipUp':'T19'}

def vec(x):
    S = np.concatenate([x['observation.state.left_ee_pose_gripper_base'],
        x['observation.state.right_ee_pose_gripper_base'],
        x['observation.state.left_gripper'][:,None],
        x['observation.state.right_gripper'][:,None]], 1).astype(float)
    A = np.concatenate([x['action.left_ee_pose_gripper_base'],
        x['action.right_ee_pose_gripper_base'],
        x['action.left_gripper'][:,None],
        x['action.right_gripper'][:,None]], 1).astype(float)
    return S, A

def ridge(X, Y, lam=1e-2):
    X1 = np.c_[X, np.ones(len(X))]
    return np.linalg.solve(X1.T@X1 + lam*np.eye(X1.shape[1]), X1.T@Y), X1

out={'horizons':HS,'tasks':{},'notes':'linear ridge; D-level'}
for p in sorted(glob.glob('exp/unibot_states/*.npz')):
    name=os.path.splitext(os.path.basename(p))[0]
    if name not in TASKS: continue
    d=np.load(p,allow_pickle=True)['contig'].item(); S,A=vec(d)
    sm,ss=S.mean(0),S.std(0); ss[ss<1e-8]=1
    am,asd=A.mean(0),A.std(0); asd[asd<1e-8]=1
    Sz=(S-sm)/ss; Az=(A-am)/asd
    n=len(S); ntr=int(.7*n)
    # dynamics on standardized state; delta in standardized units
    Xd=np.c_[Sz[:-1],Az[:-1]]; Yd=Sz[1:]-Sz[:-1]
    Wd,_=ridge(Xd,Yd)
    # policy
    Wp,_=ridge(Sz[:ntr],Az[:ntr],lam=1e-1)
    def fdyn(s,a):
        x=np.r_[s,a,1.0]; return x@Wd
    def fpol(s):
        return np.r_[s,1.0]@Wp
    errs_true=[]; errs_bc=[]
    starts=range(ntr,n-max(HS)-1,7)
    for h in HS:
        et=[]; eb=[]
        for t in starts:
            s=S[t].copy()
            for u in range(h):
                a=A[t+u]
                s=s+fdyn((s-sm)/ss,(a-am)/asd)*ss
            et.append(np.sqrt((((s-S[t+h])/ss)**2).mean()))
            s=S[t].copy()
            for u in range(h):
                a=fpol((s-sm)/ss)*asd+am
                s=s+fdyn((s-sm)/ss,(a-am)/asd)*ss
            eb.append(np.sqrt((((s-S[t+h])/ss)**2).mean()))
        errs_true.append(float(np.mean(et))); errs_bc.append(float(np.mean(eb)))
    out['tasks'][name]={'task_id':TASKS[name],'true_action':dict(zip(map(str,HS),errs_true)),
                        'closed_loop_bc':dict(zip(map(str,HS),errs_bc))}
    print(TASKS[name], 'true', [round(x,2) for x in errs_true], 'bc', [round(x,2) for x in errs_bc])
json.dump(out,open('exp/r3_longhorizon_rollout.json','w'),indent=1)
