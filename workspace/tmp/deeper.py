import sys, pickle, time
sys.path[:0] = ['exp/v61','exp/v60','exp/v13']
from alc import ALC
FILES = {
 'holdout50': 'exp/v20/holdout_cases50.pkl','synth45': 'exp/v28/synth2_45.pkl',
 'large_a': 'exp/v14/large_a.pkl','large_b': 'exp/v14/large_b.pkl',
 'large_het': 'exp/v14/large_het.pkl','hard3': 'exp/v13/hard3.pkl','deep8': 'exp/v18/deep.pkl'}
def load(f):
    d=pickle.load(open(f,'rb'))
    return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
for gap in [2,3,4]:
    tot=dict(nodes=0,lp=0,n=0,branch=0,mx=0,unk=0); t0=time.time()
    for name,f in FILES.items():
        for inst,opt in load(f):
            a=ALC(inst,opt-gap,cert_on=False)
            try: v,st=a.decide(nodecap=3000)
            except RecursionError: 
                tot['unk']+=1; continue
            tot['n']+=1
            if v is None: tot['unk']+=1; continue
            tot['nodes']+=st['nodes']; tot['lp']+=st['lp_solves']
            tot['mx']=max(tot['mx'],st['nodes'])
            if st['nodes']>1: tot['branch']+=1
    print('gap',gap,tot,'t',round(time.time()-t0,2),flush=True)
