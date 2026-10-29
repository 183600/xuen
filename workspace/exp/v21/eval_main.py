"""v2.1 (rigid DPL) vs v2.0 (DHD) on the 38 + deep 8 benchmarks."""
import sys,pickle,json,time,statistics
sys.path[:0]=['exp/v13','exp/v14','exp/v15','exp/v16','exp/v17','exp/v18','exp/v19','exp/v20','exp/v21']
import po,pace_v20,pace_v21
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
def fe(inst): return all(len(set(inst['elig'][i]))==inst['m'] for i in range(inst['n']))
def load(path):
    d=pickle.load(open(path,'rb'))
    return [x if isinstance(x,dict) else {'inst':x[0],'opt':x[1]} for x in d]
def run(mod,inst,h,**kw):
    return mod.decide(inst,h,odom=False,dcd=True,hpack_on=True,omd=fe(inst),**CFG,**kw)
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
out={}
SETS=[('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),
      ('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]
tot={k:0 for k in ('v20','v21')}; tab={k:0 for k in ('v20','v21')}
tt={k:0.0 for k in ('v20','v21')}; rows=[]; diff=0
for tag,path in SETS:
    for k,rec in enumerate(load(path)):
        inst,h=rec['inst'],rec['opt']-1
        for v in ('v20','v21'):
            t=time.time()
            if v=='v20': (b,o),st=run(pace_v20,inst,h,dhd=True)
            else: (b,o),st=run(pace_v21,inst,h,dhd=True,dpl=True)
            tt[v]+=time.time()-t
            assert b is False,(tag,k,v)
            tot[v]+=st['nodes']; tab[v]+=st['tables']
        (ok,o),_=run(pace_v21,inst,rec['opt'],dhd=True,dpl=True); assert ok
        validate(inst,rec['opt'],o)
        s20=run(pace_v20,inst,h,dhd=True)[1]; s21=run(pace_v21,inst,h,dhd=True,dpl=True)[1]
        if s20['nodes']!=s21['nodes']: diff+=1
        rows.append(dict(tag=tag,idx=k,n=inst['n'],v20=s20['nodes'],v21=s21['nodes'],
                         edges=s21.get('dpl_edges',0),probes=s21.get('dpl_probes',0)))
out['bench38']=dict(nodes=tot,tables=tab,time={k:round(v,4) for k,v in tt.items()},
                    ratio=round(tot['v20']/max(1,tot['v21']),4),diff=diff,
                    rows=[r for r in rows if r['v20']!=r['v21']])
print('38',tot,tab,out['bench38']['time'],out['bench38']['ratio'],'diff',diff,flush=True)
D=pickle.load(open('exp/v18/deep.pkl','rb'))
tot={k:0 for k in ('v20','v21')}; tab={k:0 for k in ('v20','v21')}
tt={k:0.0 for k in ('v20','v21')}; rows=[]; diff=0
for idx,(inst,opt,*_) in enumerate(D):
    h=opt-1
    for v in ('v20','v21'):
        t=time.time()
        if v=='v20': (b,o),st=run(pace_v20,inst,h,dhd=True)
        else: (b,o),st=run(pace_v21,inst,h,dhd=True,dpl=True)
        tt[v]+=time.time()-t
        assert b is False,(idx,v)
        tot[v]+=st['nodes']; tab[v]+=st['tables']
    (ok,o),_=run(pace_v21,inst,opt,dhd=True,dpl=True); assert ok; validate(inst,opt,o)
    s20=run(pace_v20,inst,h,dhd=True)[1]; s21=run(pace_v21,inst,h,dhd=True,dpl=True)[1]
    if s20['nodes']!=s21['nodes']: diff+=1
    rows.append(dict(idx=idx,n=inst['n'],v20=s20['nodes'],v21=s21['nodes'],
                     edges=s21.get('dpl_edges',0),probes=s21.get('dpl_probes',0)))
out['deep']=dict(nodes=tot,tables=tab,time={k:round(v,4) for k,v in tt.items()},
                 ratio=round(tot['v20']/max(1,tot['v21']),4),diff=diff,rows=rows)
print('deep',tot,tab,out['deep']['time'],out['deep']['ratio'],'diff',diff,flush=True)
for r in rows: print(' ',r)
json.dump(out,open('exp/v21/res_main.json','w'),indent=1)
