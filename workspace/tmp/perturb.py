import sys, random, pickle, copy, time
sys.path[:0]=['exp/v71','exp/v61','exp/v60','exp/v13']
sys.setrecursionlimit(20000)
from alc import ALC
from po import heads_tails
from scope import load

rng=random.Random(4242)
base=[('h5',load('exp/v20/holdout_cases50.pkl')[5][0]),
      ('h47',load('exp/v20/holdout_cases50.pkl')[47][0])]
out=[]; t0=time.time()
for name,inst0 in base:
    for k in range(30):
        inst=copy.deepcopy(inst0)
        i=rng.randrange(inst['n'])
        inst['p'][i]=max(1,inst['p'][i]+rng.choice([-1,1]))
        # rebuild derived fields
        import po
        inst=po.make_inst(inst['p'],inst['m'],inst['pred'],inst['elig'])
        est,q=heads_tails(inst,0,[0]*inst['n'])
        lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(inst['n'])),
               (sum(inst['p'])+inst['m']-1)//inst['m'],max(inst['p']))
        opt=None
        for h in range(lo,lo+12):
            a=ALC(inst,h,cert_on=False)
            try: v,st=a.decide(nodecap=800)
            except RecursionError: v=None
            if v is True: opt=h; break
            if v is None: break
        if opt is None: continue
        a=ALC(inst,opt-1,cert_on=False)
        try: v,st=a.decide(nodecap=800)
        except RecursionError: continue
        if v is not False: continue
        rec=(name,k,inst,opt,st['nodes'],st['lp_solves'])
        out.append(rec)
        print(name,k,'opt',opt,'nodes',st['nodes'],'lp',st['lp_solves'],flush=True)
pickle.dump(out,open('tmp/perturb.pkl','wb'))
print('n',len(out),'branch>=2',sum(1 for r in out if r[4]>=2),'t',round(time.time()-t0,1))
