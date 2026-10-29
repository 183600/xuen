import sys, time, json, pickle
sys.path[:0] = ['exp/v31','exp/v30','exp/v29','exp/v28','exp/v25','exp/v24',
                'exp/v20','exp/v16','exp/v15','exp/v13']
import root_bb, root_v30, root_v31

def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt']) for x in d]

def run(mod, cases, hmod, **kw):
    rows=[]; t0=time.time()
    for idx,(inst,opt) in enumerate(cases):
        st={}
        ok,st=mod.bb_solve(inst,opt+hmod,stats=st,**kw)
        rows.append(dict(idx=idx,n=inst['n'],m=inst['m'],ok=ok,verdict=st.get('verdict'),
                         t=st.get('t',0.0),os=st.get('os_nodes'),het=st.get('het_nodes')))
    return rows, dict(n=len(rows),t=round(time.time()-t0,4),
                      yes=sum(1 for r in rows if r['ok']),
                      verdicts={v:sum(1 for r in rows if r['verdict']==v) for v in sorted(set(r['verdict'] for r in rows))})

CASES = {
 'holdout50': 'exp/v20/holdout_cases50.pkl',
 'hard3': 'exp/v13/hard3.pkl',
 'deep8': 'exp/v18/deep.pkl',
 'large_a': 'exp/v14/large_a.pkl',
 'large_b': 'exp/v14/large_b.pkl',
 'large_het': 'exp/v14/large_het.pkl',
 'synth45': 'exp/v28/synth2_45.pkl',
}

def main():
    cases={k:load(v) for k,v in CASES.items()}
    cases['residual5']=[cases['holdout50'][i] for i in [5,21,32,42,47]]
    out={}
    for name,cs in cases.items():
        r5,a5=run(root_bb,cs,-1); r3,a3=run(root_v30,cs,-1); r1,a1=run(root_v31,cs,-1)
        out[name]=dict(v25=a5,v30=a3,v31=a1,rows31=r1,
                       same30=sum(1 for x,y in zip(r5,r3) if bool(x['ok'])==bool(y['ok'])),
                       same31=sum(1 for x,y in zip(r5,r1) if bool(x['ok'])==bool(y['ok'])))
        print(name,'v25',a5['t'],'v30',a3['t'],'v31',a1['t'],a1['verdicts'],flush=True)
    json.dump(out,open('exp/v31/res.json','w'),indent=1)

if __name__=='__main__':
    main()
