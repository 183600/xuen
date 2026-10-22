import sys, pickle, json, time
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v14'); sys.path.insert(0,'exp/v15')
import po, pace, pace_i

def load(p):
    d=pickle.load(open(p,'rb'))
    return [{'inst':x[0],'opt':x[1]} if isinstance(x,tuple) else x for x in d]

SETS=[('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),
      ('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]

CONFIGS={
 'v13':      dict(mint_on=False,packset_on=False),
 'rootM':    dict(mint_on=True,mint_depth=0,packset_on=False),
 'rootMP':   dict(mint_on=True,mint_depth=0,packset_on=True,packset_depth=0),
 'd2':       dict(mint_on=True,mint_depth=2,packset_on=True,packset_depth=0),
 'd4p2':     dict(mint_on=True,mint_depth=4,packset_on=True,packset_depth=2),
}

def run_all(cfg, reps=1):
    rows=[]; T=0.0
    for tag,path in SETS:
        for k,rec in enumerate(load(path)):
            inst=rec['inst']; h=rec['opt']-1
            best=None
            for _ in range(reps):
                t=time.time()
                (ok,out),st=pace_i.decide(inst,h,mode='pot',nodecap=2_000_000,**cfg)
                dt=time.time()-t
                if best is None or dt<best[2]: best=(ok,st,dt)
            ok,st,dt=best
            T+=dt
            rows.append(dict(tag=tag,idx=k,n=inst['n'],m=inst['m'],opt=rec['opt'],
                             ok=ok,nodes=st['nodes'],time=round(dt,4),
                             tables=st.get('tables',0),
                             pot_calls=st.get('pot_calls',0),
                             pot_prunes=st.get('pot_prunes',0),
                             mint_calls=st.get('mint_calls',0),
                             mint_pairs=st.get('mint_pairs',0),
                             mint_prunes=st.get('mint_prunes',0),
                             pack_calls=st.get('packset_calls',0),
                             pack_nodes=st.get('packset_nodes',0),
                             pack_prunes=st.get('packset_prunes',0),
                             wit=(st.get('root_wit') or [None])[0],
                             timeout=st.get('timeout',False)))
    return rows,T

if __name__=='__main__':
    out={}
    for name,cfg in CONFIGS.items():
        rows,T=run_all(cfg)
        out[name]=rows
        print(f"== {name}: nodes={sum(r['nodes'] for r in rows)} time={T:.3f}s "
              f"tables={sum(r['tables'] for r in rows)} "
              f"mint_calls={sum(r['mint_calls'] for r in rows)} "
              f"mint_prunes={sum(r['mint_prunes'] for r in rows)} "
              f"pack_calls={sum(r['pack_calls'] for r in rows)} "
              f"pack_prunes={sum(r['pack_prunes'] for r in rows)}",flush=True)
        print('   per-set nodes:',{t:sum(r['nodes'] for r in rows if r['tag']==t) for t,_ in SETS},flush=True)
        for r in rows:
            if r['nodes']>1:
                print(f"   residual {r['tag']}#{r['idx']} n={r['n']} nodes={r['nodes']} t={r['time']} wit={r['wit']} mint={r['mint_calls']}/{r['mint_prunes']} pack={r['pack_calls']}/{r['pack_prunes']}",flush=True)
    json.dump(out,open('exp/v15/res_i.json','w'),default=str,indent=0)
    print('saved')
