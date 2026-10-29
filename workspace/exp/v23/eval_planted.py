import sys,pickle,random,json,time
sys.path[:0]=['exp/v13','exp/v14','exp/v15','exp/v16','exp/v17','exp/v18','exp/v19','exp/v20','exp/v23']
import po,pace_v20,pace_v23
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
PI=dict(pi=True,pi_depth=0,pi_ncap=16,pi_tau=4,pi_gap=4,pi_wcap=15)
def add_decoys(inst,k,seed):
    rng=random.Random(seed); n=inst['n']; m=inst['m']
    p=list(inst['p'])+[rng.randint(1,3) for _ in range(k)]
    pred=[list(x) for x in inst['pred']]+[[] for _ in range(k)]
    elig=[list(x) for x in inst['elig']]+[[kk for kk in range(m)] for _ in range(k)]
    J=po.make_inst(p,m,pred); J['elig']=elig
    return J
bases=[]
d=pickle.load(open('exp/v13/hard3.pkl','rb')); x=d[5]; bases.append(('hard3#5',x['inst'] if isinstance(x,dict) else x[0],x['opt'] if isinstance(x,dict) else x[1]))
D=pickle.load(open('exp/v18/deep.pkl','rb'))
for k in [1,3,4,5,6,7]: bases.append((f'deep#{k}',D[k][0],D[k][1]))
rows=[]
for name,inst,opt in bases:
    for k in [4,6,8]:
        J=add_decoys(inst,k,seed=100+k)
        h=opt-1
        t=time.time(); (b,o),s20=pace_v20.decide(J,h,odom=False,hpack_on=True,omd=True,dcd=True,dhd=True,**CFG); t20=time.time()-t
        t=time.time(); (b2,o2),s23=pace_v23.decide(J,h,odom=False,hpack_on=True,omd=True,dcd=True,dhd=True,**CFG,**PI); t23=time.time()-t
        assert b is False and b2 is False
        rows.append(dict(base=name,decoy=k,n=J['n'],v20=s20['nodes'],v23=s23['nodes'],
                         pi=s23.get('pi_beta'),wsize=s23.get('pi_wit_size'),
                         t20=round(t20,4),t23=round(t23,4)))
        print(rows[-1],flush=True)
out=dict(nodes={k:sum(r['v20'] if k=='v20' else r['v23'] for r in rows) for k in ('v20','v23')},
         wins=sum(1 for r in rows if r['v23']<r['v20']),
         ties=sum(1 for r in rows if r['v23']==r['v20']),
         losses=sum(1 for r in rows if r['v23']>r['v20']),rows=rows)
print({k:v for k,v in out.items() if k!='rows'})
json.dump(out,open('exp/v23/res_planted.json','w'),indent=1)
