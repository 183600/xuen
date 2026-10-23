import sys,time,json,pickle,statistics
sys.path[:0]=['exp/v41','exp/v30','exp/v29','exp/v13','exp/v15','exp/v16','exp/v20','exp/v24','exp/v25']
import root_v30, root_v41
def load(f):
    d=pickle.load(open(f,'rb'))
    return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
def run(mod,cs,hmod,**kw):
    rows=[]; t0=time.time()
    for idx,(inst,opt) in enumerate(cs):
        st={}; ok,st=mod.bb_solve(inst,opt+hmod,stats=st,**kw)
        rows.append(dict(idx=idx,n=inst['n'],m=inst['m'],ok=ok,verdict=st.get('verdict'),
                         os=st.get('os_nodes'),mpc=st.get('mpc_nodes'),t=st.get('t',0.0)))
    return rows,dict(t=round(time.time()-t0,4),os=sum(r['os'] or 0 for r in rows),
                     yes=sum(1 for r in rows if r['ok']),
                     verdicts={v:sum(1 for r in rows if r['verdict']==v) for v in sorted(set(r['verdict'] for r in rows))})
def main():
    cases={'holdout50':load('exp/v20/holdout_cases50.pkl'),
           'hard3':load('exp/v13/hard3.pkl'),'deep8':load('exp/v18/deep.pkl'),
           'large_a':load('exp/v14/large_a.pkl'),'large_b':load('exp/v14/large_b.pkl'),
           'large_het':load('exp/v14/large_het.pkl'),'synth45':load('exp/v28/synth2_45.pkl')}
    cases['residual5']=[cases['holdout50'][i] for i in [5,21,32,42,47]]
    out={}
    for name,cs in cases.items():
        r30,a30=run(root_v30,cs,-1); r41,a41=run(root_v41,cs,-1)
        out[name]=dict(v30=a30,v41=a41,rows30=r30,rows41=r41,
                       same=sum(1 for x,y in zip(r30,r41) if bool(x['ok'])==bool(y['ok'])))
        print(name,'v30',a30,'| v41',a41,'| same',out[name]['same'],flush=True)
    out['_yes']={}
    for name in ['holdout50','hard3','deep8','residual5','synth45']:
        r30,a30=run(root_v30,cases[name],0); r41,a41=run(root_v41,cases[name],0)
        out['_yes'][name]=dict(v30=a30,v41=a41,rows30=r30,rows41=r41,
                               same=sum(1 for x,y in zip(r30,r41) if bool(x['ok'])==bool(y['ok'])))
        print(name+'_YES','v30',a30,'| v41',a41,flush=True)
    json.dump(out,open('exp/v41/res_v41.json','w'),indent=1)
if __name__=='__main__': main()
