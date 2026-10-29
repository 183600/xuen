"""v1.8 PACE-D bench: 38 cases + deep suite + easy suite.

Configs
  base : v1.6 engine (no order dominance, no HPACK)
  odom : + v1.7 ODOM (equal (p,E,Succ_R) classes)
  dcd  : + v1.8 DCD  (descendant-closure dominance)
  full : DCD + HPACK        <- v1.8 PACE-D
"""
import sys, pickle, json, time
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v14')
sys.path.insert(0,'exp/v15'); sys.path.insert(0,'exp/v16')
sys.path.insert(0,'exp/v17'); sys.path.insert(0,'exp/v18'); sys.path.insert(0,'exp/v19')
import po, pace_v18

SETS=[('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),
      ('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]
CFG=dict(mode='pot',mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)

def load(path):
    d=pickle.load(open(path,'rb'))
    return [x if isinstance(x,dict) else {'inst':x[0],'opt':x[1]} for x in d]

def full_elig(inst):
    return all(len(set(inst['elig'][i]))==inst['m'] for i in range(inst['n']))

def run(inst,h,odom=False,dcd=False,hp=False,cap=3_000_000):
    t=time.time()
    (ok,out),st=pace_v18.decide(inst,h,odom=odom,dcd=dcd,hpack_on=hp,
                                nodecap=cap,omd=full_elig(inst),**CFG)
    return ok,st,time.time()-t

def bench():
    rows=[]; tot={k:0 for k in ('base','odom','dcd','full')}
    tab={k:0 for k in ('base','full')}; tt={k:0.0 for k in ('base','full')}
    for tag,path in SETS:
        for k,rec in enumerate(load(path)):
            inst,h=rec['inst'],rec['opt']-1
            b,sb,tb=run(inst,h)
            o,so,_=run(inst,h,odom=True)
            d,sd,_=run(inst,h,dcd=True)
            f,sf,tf=run(inst,h,dcd=True,hp=True)
            assert b==o==d==f==False,(tag,k)
            (oko,_,_)=run(inst,rec['opt'],dcd=True,hp=True)
            assert oko,(tag,k,'false NO at OPT')
            for key,s in [('base',sb),('odom',so),('dcd',sd),('full',sf)]:
                tot[key]+=s['nodes']
            tab['base']+=sb['tables']; tab['full']+=sf['tables']
            tt['base']+=tb; tt['full']+=tf
            if len({sb['nodes'],so['nodes'],sd['nodes'],sf['nodes']})>1:
                rows.append(dict(tag=tag,idx=k,n=inst['n'],m=inst['m'],
                                 opt=rec['opt'],all_elig=full_elig(inst),
                                 base=sb['nodes'],odom=so['nodes'],
                                 dcd=sd['nodes'],full=sf['nodes'],
                                 base_t=sb['tables'],full_t=sf['tables']))
    out=dict(rows=rows,totals=tot,tables=tab,
             time={k:round(v,4) for k,v in tt.items()},
             node_ratio=round(tot['base']/tot['full'],3),
             dcd_vs_odom=round(tot['odom']/tot['dcd'],3))
    json.dump(out,open('exp/v19/res_v18.json','w'),indent=1)
    print('BENCH',json.dumps(out,indent=1))
    return out

def deep():
    D=pickle.load(open('exp/v18/deep.pkl','rb'))
    rows=[]; tot={k:0 for k in ('base','odom','dcd','full')}
    tt={k:0.0 for k in ('base','full')}; tab={k:0 for k in ('base','full')}
    for idx,(inst,opt,bn,qn,bt,qt) in enumerate(D):
        h=opt-1
        b,sb,tb=run(inst,h)
        o,so,_=run(inst,h,odom=True)
        d,sd,_=run(inst,h,dcd=True)
        f,sf,tf=run(inst,h,dcd=True,hp=True)
        assert b==o==d==f==False,(idx,b,o,d,f)
        (oko,_,_)=run(inst,opt,dcd=True,hp=True)
        assert oko,(idx,'false NO at OPT')
        for key,s in [('base',sb),('odom',so),('dcd',sd),('full',sf)]:
            tot[key]+=s['nodes']
        tab['base']+=sb['tables']; tab['full']+=sf['tables']
        tt['base']+=tb; tt['full']+=tf
        rows.append(dict(idx=idx,n=inst['n'],m=inst['m'],opt=opt,
                         base=sb['nodes'],odom=so['nodes'],dcd=sd['nodes'],
                         full=sf['nodes'],base_t=sb['tables'],full_t=sf['tables'],
                         fan_max_before=sd['dcd_fan_max_before'],
                         fan_max_after=sd['dcd_fan_max_after'],
                         fan_sum_before=sd['dcd_fan_before'],
                         fan_sum_after=sd['dcd_fan_after'],
                         sink_skips=sd['dcd_sink_skips'],
                         strict_skips=sd['dcd_strict_skips'],
                         eq_skips=sd['dcd_eq_skips']))
    out=dict(rows=rows,totals=tot,tables=tab,
             time={k:round(v,4) for k,v in tt.items()},
             node_ratio=round(tot['base']/tot['full'],3),
             dcd_vs_odom=round(tot['odom']/tot['dcd'],3))
    json.dump(out,open('exp/v19/res_deep_v18.json','w'),indent=1)
    print('DEEP',json.dumps(out,indent=1))
    return out

def easy():
    """Same generator/seed as exp/v18/easy_q.py (60 instances, h=OPT+5)."""
    import random
    def gen(rng,n,m,pmax=10,ep=0.22):
        p=[rng.randint(2,pmax) for _ in range(n)]
        pred=[[] for _ in range(n)]
        for j in range(n):
            for i in range(j):
                if rng.random()<ep: pred[j].append(i)
            if j>0 and not pred[j] and rng.random()<0.7:
                pred[j].append(rng.randrange(j))
        return po.make_inst(p,m,pred)
    rng=random.Random(8080)
    tot={k:0 for k in ('base','full')}; tt={k:0.0 for k in ('base','full')}
    n_inst=0; rows=[]
    while n_inst<60:
        n=rng.randint(10,14); inst=gen(rng,n,3)
        est,q=po.heads_tails(inst,0,[0]*n)
        lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(n)),
               (sum(inst['p'])+2)//3,max(inst['p']))
        opt=None
        for h in range(lo,lo+10):
            ok,st,_=run(inst,h,odom=True)
            if ok: opt=h; break
        if opt is None: continue
        h=opt+5
        b,sb,tb=run(inst,h,odom=True)
        f,sf,tf=run(inst,h,dcd=True,hp=True)
        assert b==f==True
        tot['base']+=sb['nodes']; tot['full']+=sf['nodes']
        tt['base']+=tb; tt['full']+=tf
        rows.append((n,sb['nodes'],sf['nodes']))
        n_inst+=1
    out=dict(n=n_inst,nodes=tot,time={k:round(v,4) for k,v in tt.items()},
             ratio=round(tot['base']/max(1,tot['full']),4),
             time_ratio=round(tt['base']/tt['full'],4))
    json.dump(out,open('exp/v19/res_easy_v18.json','w'),indent=1)
    print('EASY',out)
    return out

if __name__=='__main__':
    which=sys.argv[1] if len(sys.argv)>1 else 'all'
    if which in ('all','bench'): bench()
    if which in ('all','deep'): deep()
    if which in ('all','easy'): easy()
