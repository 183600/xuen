"""Can progress direction be detected from short proprioceptive windows?
D-level: forward vs time-reversed windows, paired at the same original phase."""
import numpy as np, glob, os, json

def vec(x):
    return np.concatenate([x['observation.state.left_ee_pose_gripper_base'],
        x['observation.state.right_ee_pose_gripper_base'],
        x['observation.state.left_gripper'][:,None],
        x['observation.state.right_gripper'][:,None]],1).astype(float)

def feats(S, t, w=5):
    a=S[max(0,t-w):t+1]
    if len(a)<2: a=np.repeat(S[t][None],2,0)
    d1=S[t]-S[max(0,t-1)]
    d3=S[t]-S[max(0,t-3)]
    d5=S[t]-S[max(0,t-w)]
    vel=np.diff(a,axis=0)
    return np.r_[S[t], d1, d3, d5, vel.mean(0), vel.std(0)]

def ridge_fit(X,y,lam=1.0):
    X1=np.c_[X,np.ones(len(X))]
    return np.linalg.solve(X1.T@X1+lam*np.eye(X1.shape[1]),X1.T@y)

out={}
for p in sorted(glob.glob('exp/unibot_states/*.npz')):
    name=os.path.basename(p)[:-4]
    S=vec(np.load(p,allow_pickle=True)['contig'].item())
    Sr=S[::-1]; n=len(S); w=5
    ts=np.arange(w,n)
    Xf=np.array([feats(S,t,w) for t in ts])
    Xr=np.array([feats(Sr,n-1-t,w) for t in ts])
    X=np.r_[Xf,Xr]; y=np.r_[np.ones(len(ts)),-np.ones(len(ts))]
    tr_ts=np.arange(0,int(.7*len(ts))); te_ts=np.arange(int(.7*len(ts)),len(ts))
    tr=np.r_[tr_ts, len(ts)+tr_ts]; te=np.r_[te_ts, len(ts)+te_ts]
    mu=X[tr].mean(0); sd=X[tr].std(0); sd[sd<1e-8]=1
    Xn=(X-mu)/sd
    wv=ridge_fit(Xn[tr],y[tr],lam=1.0)
    pred=np.sign(np.c_[Xn[te],np.ones(len(te))]@wv)
    acc=float((pred==y[te]).mean())
    out[name]={'dir_acc':acc,'n_train':len(tr),'n_test':len(te)}
    print(name, 'dir-acc', round(acc,3))
print('mean', round(float(np.mean([v['dir_acc'] for v in out.values()])),3))
json.dump(out,open('exp/r3_reversal_detect.json','w'),indent=1)
