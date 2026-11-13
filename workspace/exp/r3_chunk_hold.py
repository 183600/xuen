import numpy as np, glob, os, json
HS=[1,2,4,8,16,32,64]
out={}
for p in sorted(glob.glob('exp/unibot_states/*.npz')):
 d=np.load(p,allow_pickle=True)['contig'].item()
 A=np.concatenate([d['action.left_ee_pose_gripper_base'],d['action.right_ee_pose_gripper_base'],d['action.left_gripper'][:,None],d['action.right_gripper'][:,None]],1).astype(float)
 sd=A.std(0); sd[sd<1e-8]=1
 row={}
 for mode in ['hold','linear']:
  errs=[]
  for h in HS:
   e=[]
   for t in range(1,len(A)-h):
    if mode=='hold': pred=np.repeat(A[t][None],h,0)
    else:
     dA=A[t]-A[t-1]; pred=A[t][None]+dA[None]*np.arange(1,h+1)[:,None]
    e.append(np.sqrt((((pred-A[t+1:t+1+h])/sd)**2).mean()))
   errs.append(float(np.mean(e)))
  row[mode]=dict(zip(map(str,HS),errs))
 out[os.path.basename(p)[:-4]]=row
 print(os.path.basename(p)[:-4], 'hold',[round(x,2) for x in row['hold'].values()],'lin',[round(x,2) for x in row['linear'].values()])
json.dump({'horizons':HS,'tasks':out},open('exp/r3_chunk_hold.json','w'),indent=1)
