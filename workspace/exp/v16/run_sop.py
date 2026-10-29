import sys,pickle,json,time
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v14'); sys.path.insert(0,'exp/v15'); sys.path.insert(0,'exp/v16')
import po, pace_i, pace_sop

SETS=[('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),
      ('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]

def load(p):
    d=pickle.load(open(p,'rb'))
    return [x if isinstance(x,dict) else {'inst':x[0],'opt':x[1]} for x in d]

def run(module, cfg, h_off=-1, reps=1):
    rows=[]; T=0.0
    for tag,path in SETS:
        for k,rec in enumerate(load(path)):
            inst=rec['inst']; h=rec['opt']+h_off
            best=None
            for _ in range(reps):
                t=time.time()
                (ok,out),st=module.decide(inst,h,mode='pot',nodecap=2_000_000,**cfg)
                dt=time.time()-t
                if best is None or dt<best[2]: best=(ok,st,dt)
            ok,st,dt=best; T+=dt
            rows.append(dict(tag=tag,idx=k,n=inst['n'],m=inst['m'],opt=rec['opt'],
                             ok=ok,nodes=st['nodes'],time=round(dt,4),tables=st.get('tables',0),
                             sop_calls=st.get('sop_calls',0),sop_prunes=st.get('sop_prunes',0),
                             sop_time=st.get('sop_time',0.0),sop_pack_nodes=st.get('sop_pack_nodes',0),
                             wit=(st.get('root_wit') or [None])[0] if st.get('root_wit') else None))
    return rows,T

CFG=dict(mint_on=True,mint_depth=0,packset_on=True,packset_depth=0)
if __name__=='__main__':
    rows14,T14=run(pace_i,CFG)
    rows15,T15=run(pace_sop,dict(CFG,sop_on=True))
    print('v14 nodes',sum(r['nodes'] for r in rows14),'time',round(T14,4))
    print('v15 nodes',sum(r['nodes'] for r in rows15),'time',round(T15,4))
    for a,b in zip(rows14,rows15):
        if a['nodes']!=b['nodes'] or a['ok']!=b['ok']:
            print('CHANGE',a['tag'],a['idx'],'nodes',a['nodes'],'->',b['nodes'],
                  'time',a['time'],'->',b['time'],'sop',b['sop_calls'],b['sop_prunes'],b['sop_pack_nodes'])
    # h=OPT: no false NO
    bad=0
    for tag,path in SETS:
        for k,rec in enumerate(load(path)):
            inst=rec['inst']; h=rec['opt']
            (ok,out),st=pace_sop.decide(inst,h,mode='pot',nodecap=2_000_000,sop_on=True,**CFG)
            if not ok: bad+=1; print('FALSE NO at OPT',tag,k,st.get('root_wit'))
    print('false NO at OPT:',bad)
    json.dump({'v14':rows14,'v15':rows15,'T14':T14,'T15':T15},
              open('exp/v16/res_sop.json','w'),default=str,indent=0)
