"""v2.1 (Pi-bound gate) vs v2.0 (DHD) on 38 + deep + held-out."""
import sys,pickle,json,time,statistics,random
sys.path[:0]=['exp/v13','exp/v14','exp/v15','exp/v16','exp/v17','exp/v18','exp/v19','exp/v20','exp/v22']
import po,pace_q,pace_v20,pace_v22
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
def load(path):
    d=pickle.load(open(path,'rb'))
    return [x if isinstance(x,dict) else {'inst':x[0],'opt':x[1]} for x in d]
def fe(inst): return all(len(set(inst['elig'][i]))==inst['m'] for i in range(inst['n']))
def run(ver,inst,h,**kw):
    base=dict(odom=False,dcd=True,dhd=True,hpack_on=True,omd=fe(inst),**CFG,**kw)
    if ver=='v20': return pace_v20.decide(inst,h,**base)
    return pace_v22.decide(inst,h,pi=True,pi_check=False,**base)
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

def bench38():
    SETS=[('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),
          ('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]
    tot={k:0 for k in ('v20','v21')}; tab={k:0 for k in ('v20','v21')}
    tt={k:0.0 for k in ('v20','v21')}; rows=[]
    for tag,path in SETS:
        for k,rec in enumerate(load(path)):
            inst,h=rec['inst'],rec['opt']-1
            for v in ('v20','v21'):
                ts=[]; r=None
                for _ in range(3):
                    t=time.time(); r=run(v,inst,h); ts.append(time.time()-t)
                tt[v]+=statistics.median(ts)
                assert r[0][0] is False,(tag,k,v)
                tot[v]+=r[1]['nodes']; tab[v]+=r[1]['tables']
            ((ok,o),st)=run('v21',inst,rec['opt']); assert ok; validate(inst,rec['opt'],o)
            s20=run('v20',inst,h)[1]; s21=run('v21',inst,h)[1]
            rows.append(dict(tag=tag,idx=k,n=inst['n'],v20=s20['nodes'],v21=s21['nodes'],
                             pi=s21.get('pi_beta'),pi_time=s21.get('pi_time',0),
                             calls=s21.get('pi_calls',0)))
    out=dict(nodes=tot,tables=tab,time={k:round(v,4) for k,v in tt.items()},
             ratio=round(tot['v20']/max(1,tot['v21']),4),
             rows=[r for r in rows if r['v20']!=r['v21']])
    return out

def bench_deep():
    D=pickle.load(open('exp/v18/deep.pkl','rb'))
    tot={k:0 for k in ('v20','v21')}; tab={k:0 for k in ('v20','v21')}
    tt={k:0.0 for k in ('v20','v21')}; rows=[]
    for idx,(inst,opt,*_) in enumerate(D):
        h=opt-1
        for v in ('v20','v21'):
            ts=[]; r=None
            for _ in range(3):
                t=time.time(); r=run(v,inst,h); ts.append(time.time()-t)
            tt[v]+=statistics.median(ts)
            assert r[0][0] is False
            tot[v]+=r[1]['nodes']; tab[v]+=r[1]['tables']
        ((ok,o),st)=run('v21',inst,opt); assert ok; validate(inst,opt,o)
        s20=run('v20',inst,h)[1]; s21=run('v21',inst,h)[1]
        rows.append(dict(idx=idx,n=inst['n'],v20=s20['nodes'],v21=s21['nodes'],
                         pi=s21.get('pi_beta'),pi_time=round(s21.get('pi_time',0),4)))
    return dict(nodes=tot,tables=tab,time={k:round(v,4) for k,v in tt.items()},
                ratio=round(tot['v20']/max(1,tot['v21']),4),rows=rows)

def gen_hold(rng,n,m):
    p=[rng.randint(2,9) for _ in range(n)]; pred=[[] for _ in range(n)]
    ep=rng.choice([0.18,0.22,0.28,0.35])
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j and not pred[j]: pred[j].append(rng.randrange(j))
    return po.make_inst(p,m,pred)

def bench_hold():
    rng=random.Random(424242); held=[]; tried=0
    while len(held)<50 and tried<3000:
        tried+=1; n=rng.randint(12,16); inst=gen_hold(rng,n,3)
        est,q=po.heads_tails(inst,0,[0]*n)
        lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),(sum(inst['p'])+2)//3)
        opt=None
        for h in range(lo,lo+18):
            (ok,_),_=pace_q.decide(inst,h,odom=False,hpack_on=False,omd=True,**CFG)
            if ok: opt=h; break
        if opt is None: continue
        (b,_),sb=pace_q.decide(inst,opt-1,odom=False,hpack_on=False,omd=True,**CFG)
        if sb['nodes']<15: continue
        held.append((inst,opt))
    tot={k:0 for k in ('v20','v21')}; tt={k:0.0 for k in ('v20','v21')}
    rows=[]
    for i,(inst,opt) in enumerate(held):
        h=opt-1
        for v in ('v20','v21'):
            ts=[]; r=None
            for _ in range(2):
                t=time.time(); r=run(v,inst,h); ts.append(time.time()-t)
            tt[v]+=statistics.median(ts)
            assert r[0][0] is False
            tot[v]+=r[1]['nodes']
        ((ok,o),st)=run('v21',inst,opt); assert ok; validate(inst,opt,o)
        s20=run('v20',inst,h)[1]; s21=run('v21',inst,h)[1]
        rows.append(dict(idx=i,n=inst['n'],v20=s20['nodes'],v21=s21['nodes'],
                         pi=s21.get('pi_beta'),pi_time=round(s21.get('pi_time',0),4)))
    out=dict(nodes=tot,time={k:round(v,4) for k,v in tt.items()},
             ratio=round(tot['v20']/max(1,tot['v21']),4),
             wins=sum(1 for r in rows if r['v21']<r['v20']),
             ties=sum(1 for r in rows if r['v21']==r['v20']),
             losses=sum(1 for r in rows if r['v21']>r['v20']),
             rows=rows)
    return out

if __name__=='__main__':
    out={}
    out['bench38']=bench38(); print('38',{k:v for k,v in out['bench38'].items() if k!='rows'},flush=True)
    for r in out['bench38']['rows']: print(' ',r,flush=True)
    out['deep']=bench_deep(); print('deep',{k:v for k,v in out['deep'].items() if k!='rows'},flush=True)
    for r in out['deep']['rows']: print(' ',r,flush=True)
    out['holdout']=bench_hold(); print('hold',{k:v for k,v in out['holdout'].items() if k!='rows'},flush=True)
    for r in out['holdout']['rows']: print(' ',r,flush=True)
    json.dump(out,open('exp/v22/res_pi.json','w'),indent=1)
