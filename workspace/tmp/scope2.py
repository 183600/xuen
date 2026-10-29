import sys, pickle
sys.path[:0] = ['exp/v61','exp/v60','exp/v13']
import numpy as np
from alc import ALC
import cert as v60cert
from scope import slacks, load

for f,idxs in [('exp/v20/holdout_cases50.pkl',[5,47])]:
    for idx in idxs:
        inst,opt=load(f)[idx]
        a=ALC(inst,opt-1,cert_on=True)
        rec=[]
        orig=a._extract
        def patched(bounds=None):
            c,ok=orig(bounds)
            if c is None or not ok: return c,ok
            F=set()
            bd=list(bounds) if bounds is not None else [(0,1)]*a.lp.base.N
            for cc,b in enumerate(bd):
                if b==(0,0):
                    key=a.lp.cols[cc]; F.add((key[0],key[-1]))
            sl=slacks(inst,a.h,c,a.elig_aware)
            E={cc for cc in F if sl.get(cc,-1)<0}
            rec.append((sorted(F),sorted(E),c))
            return c,ok
        a._extract=patched
        v,st=a.decide()
        print('=== idx',idx,'v',v,'nodes',st['nodes'],'lp',st['lp_solves'])
        for F,E,c in rec:
            print(' F',F,'\n E',E,'\n beta',[(k,t,w) for k,t,w in c['beta']],'dom',c['dom'],'scale',c['scale'])
