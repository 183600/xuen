"""v1.7 PACE-Q: 38-case benchmark + deep random suite + easy suite.

Compares
  base : v1.6 PACE-O with the sound PACK front (odom=False, hpack=False)
  odom : + order dominance on exchange classes
  hpack: + obligatory-overlap packing
  q    : both
Writes exp/v18/res_q.json and exp/v18/res_deep.json.
"""
import sys, pickle, json, time
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v14')
sys.path.insert(0,'exp/v15'); sys.path.insert(0,'exp/v16')
sys.path.insert(0,'exp/v17'); sys.path.insert(0,'exp/v18')
import po, pace_q

SETS=[('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),
      ('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)

def load(path):
    d=pickle.load(open(path,'rb'))
    return [x if isinstance(x,dict) else {'inst':x[0],'opt':x[1]} for x in d]

def full_elig(inst):
    return all(len(set(inst['elig'][i]))==inst['m'] for i in range(inst['n']))

def run(inst,h,o,hp,cap=3_000_000):
    t=time.time()
    (ok,out),st=pace_q.decide(inst,h,odom=o,hpack_on=hp,
                              nodecap=cap,**{k:v for k,v in CFG.items() if k!='nodecap'},
                              **{'omd':full_elig(inst)})
    return ok,st,time.time()-t

def bench():
    rows=[]; tot={'base':0,'odom':0,'hpack':0,'q':0}
    tab={'base':0,'q':0}; tt={'base':0.0,'q':0.0}
    for tag,path in SETS:
        for k,rec in enumerate(load(path)):
            inst,h=rec['inst'],rec['opt']-1
            b,sb,tb=run(inst,h,False,False)
            d1,s1,_=run(inst,h,True,False)
            d2,s2,_=run(inst,h,False,True)
            q,sq,tq=run(inst,h,True,True)
            assert b==d1==d2==q==False,(tag,k)
            for key,st in [('base',sb),('odom',s1),('hpack',s2),('q',sq)]:
                tot[key]+=st['nodes']
            tab['base']+=sb['tables'];tab['q']+=sq['tables']
            tt['base']+=tb;tt['q']+=tq
            (oko,_,_)=run(inst,rec['opt'],True,True)
            assert oko,(tag,k,'false NO at OPT')
            if len({sb['nodes'],s1['nodes'],s2['nodes'],sq['nodes']})>1:
                rows.append(dict(tag=tag,idx=k,n=inst['n'],m=inst['m'],
                                 opt=rec['opt'],full=full_elig(inst),
                                 base=sb['nodes'],odom=s1['nodes'],
                                 hpack=s2['nodes'],q=sq['nodes'],
                                 base_t=sb['tables'],q_t=sq['tables']))
    out=dict(rows=rows,totals=tot,tables=tab,
             time={k:round(v,4) for k,v in tt.items()},
             node_ratio=round(tot['base']/tot['q'],3),
             time_ratio=round(tt['base']/tt['q'],3))
    json.dump(out,open('exp/v18/res_q.json','w'),indent=1)
    print('BENCH',out)
    return out

def deep():
    D=pickle.load(open('exp/v18/deep.pkl','rb'))
    rows=[]; tot={'base':0,'odom':0,'hpack':0,'q':0}
    tt={'base':0.0,'q':0.0}; tab={'base':0,'q':0}
    for idx,(inst,opt,bn,qn,bt,qt) in enumerate(D):
        h=opt-1
        b,sb,tb=run(inst,h,False,False)
        d1,s1,_=run(inst,h,True,False)
        d2,s2,_=run(inst,h,False,True)
        q,sq,tq=run(inst,h,True,True)
        assert b==d1==d2==q==False
        (oko,_,_)=run(inst,opt,True,True)
        assert oko,(idx,'false NO at OPT')
        for key,st in [('base',sb),('odom',s1),('hpack',s2),('q',sq)]:
            tot[key]+=st['nodes']
        tab['base']+=sb['tables'];tab['q']+=sq['tables']
        tt['base']+=tb;tt['q']+=tq
        rows.append(dict(idx=idx,n=inst['n'],m=inst['m'],opt=opt,
                         base=sb['nodes'],odom=s1['nodes'],hpack=s2['nodes'],
                         q=sq['nodes'],base_t=sb['tables'],q_t=sq['tables']))
    out=dict(rows=rows,totals=tot,tables=tab,
             time={k:round(v,3) for k,v in tt.items()},
             node_ratio=round(tot['base']/tot['q'],3))
    json.dump(out,open('exp/v18/res_deep.json','w'),indent=1)
    print('DEEP',out)
    return out

if __name__=='__main__':
    bench(); deep()
