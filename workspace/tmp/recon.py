import sys, pickle, time
sys.path[:0] = ['exp/v61','exp/v60','exp/v13']
from alc import ALC
FILES = {
 'holdout50': 'exp/v20/holdout_cases50.pkl',
 'synth45': 'exp/v28/synth2_45.pkl',
 'large_a': 'exp/v14/large_a.pkl','large_b': 'exp/v14/large_b.pkl',
 'large_het': 'exp/v14/large_het.pkl','hard3': 'exp/v13/hard3.pkl','deep8': 'exp/v18/deep.pkl'}
def load(f):
    d=pickle.load(open(f,'rb'))
    return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
for name,f in FILES.items():
    rows=load(f); yes=0; nodes=0; lps=0; t0=time.time(); mx=0
    for inst,opt in rows:
        a=ALC(inst,opt,cert_on=False); v,st=a.decide(nodecap=20000)
        if v is True: yes+=1
        nodes+=st['nodes']; lps+=st['lp_solves']; mx=max(mx,st['nodes'])
    print(name,'YES',yes,'/',len(rows),'nodes',nodes,'lp',lps,'max',mx,'t',round(time.time()-t0,2),flush=True)
