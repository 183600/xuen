"""v3.0 Pi-bound vs v2.0 DHD on 38 + deep 8."""
import sys,pickle,json,time,statistics
sys.path[:0]=['exp/v13','exp/v14','exp/v15','exp/v16','exp/v17','exp/v18','exp/v19','exp/v20','exp/v23']
import po,pace_v20,pace_v23
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
PICFG=dict(pi=True,pi_depth=0,pi_ncap=16,pi_tau=4,pi_gap=4,pi_wcap=15)
def load(path):
    d=pickle.load(open(path,'rb'))
    return [x if isinstance(x,dict) else {'inst':x[0],'opt':x[1]} for x in d]
def fe(inst): return all(len(set(inst['elig'][i]))==inst['m'] for i in range(inst['n']))
def run(ver,inst,h,**kw):
    base=dict(odom=False,dcd=True,dhd=True,hpack_on=True,omd=fe(inst),**CFG,**kw)
    if ver=='v20': return pace_v20.decide(inst,h,**base)
    return pace_v23.decide(inst,h,**base,**PICFG)
def validate(inst,h,out):
    n=inst['n']; seen=[False]*n; bym={k:[] for k in range(inst['m'])}; end=[None]*n
    for i,k,t in out:
        assert 0<=i<n and not seen[i]; seen[i]=True
        assert k in inst['elig'][i]; assert t>=0 and t+inst['p'][i]<=h
        bym[k].append((t,t+inst['p'][i])); end[i]=t
    assert all(seen)
    for i in range(n):
        for j in inst['pred'][i]: assert end[j]+inst['p'][j]<=end[i]
    for k,v in bym.items():
        v.sort()
        for a,b in zip(v,v[1:]): assert a[1]<=b[0]
    return True
SETS=[('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),
      ('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]
tot={k:0 for k in ('v20','v23')}; tab={k:0 for k in ('v20','v23')}
tt={k:0.0 for k in ('v20','v23')}; rows=[]
for tag,path in SETS:
    for k,rec in enumerate(load(path)):
        inst,h=rec['inst'],rec['opt']-1
        for v in ('v20','v23'):
            ts=[]; r=None
            for _ in range(3):
                t=time.time(); r=run(v,inst,h); ts.append(time.time()-t)
            tt[v]+=statistics.median(ts)
            assert r[0][0] is False,(tag,k,v)
            tot[v]+=r[1]['nodes']; tab[v]+=r[1]['tables']
        ((ok,o),st)=run('v23',inst,rec['opt']); assert ok; validate(inst,rec['opt'],o)
        s20=run('v20',inst,h)[1]; s23=run('v23',inst,h)[1]
        rows.append(dict(tag=tag,idx=k,n=inst['n'],v20=s20['nodes'],v23=s23['nodes'],
                         pi=s23.get('pi_beta'),pi_time=round(s23.get('pi_time',0),4),
                         calls=s23.get('pi_calls',0)))
out=dict(nodes=tot,tables=tab,time={k:round(v,4) for k,v in tt.items()},
         ratio=round(tot['v20']/max(1,tot['v23']),4),
         rows=[r for r in rows if r['v20']!=r['v23']])
print('38', {k:v for k,v in out.items() if k!='rows'},flush=True)
for r in out['rows']: print(' ',r,flush=True)
json.dump(out,open('exp/v23/res_main.json','w'),indent=1)
D=pickle.load(open('exp/v18/deep.pkl','rb'))
tot={k:0 for k in ('v20','v23')}; tab={k:0 for k in ('v20','v23')}
tt={k:0.0 for k in ('v20','v23')}; rows=[]
for idx,(inst,opt,*_) in enumerate(D):
    h=opt-1
    for v in ('v20','v23'):
        ts=[]; r=None
        for _ in range(3):
            t=time.time(); r=run(v,inst,h); ts.append(time.time()-t)
        tt[v]+=statistics.median(ts); assert r[0][0] is False
        tot[v]+=r[1]['nodes']; tab[v]+=r[1]['tables']
    ((ok,o),st)=run('v23',inst,opt); assert ok; validate(inst,opt,o)
    s20=run('v20',inst,h)[1]; s23=run('v23',inst,h)[1]
    rows.append(dict(idx=idx,n=inst['n'],v20=s20['nodes'],v23=s23['nodes'],
                     pi=s23.get('pi_beta'),pi_time=round(s23.get('pi_time',0),4),
                     calls=s23.get('pi_calls',0)))
outd=dict(nodes=tot,tables=tab,time={k:round(v,4) for k,v in tt.items()},
          ratio=round(tot['v20']/max(1,tot['v23']),4),rows=rows)
print('deep', {k:v for k,v in outd.items() if k!='rows'},flush=True)
for r in rows: print(' ',r,flush=True)
json.dump(outd,open('exp/v23/res_deep.json','w'),indent=1)
