import sys,time,json,pickle,statistics
sys.path[:0]=['exp/v41','exp/v30','exp/v29','exp/v13','exp/v15','exp/v16','exp/v20','exp/v24','exp/v25']
import root_v30, root_v41

def load(f):
    d=pickle.load(open(f,'rb'))
    return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]

def one(mod, inst, h):
    st={}
    t=time.time(); ok,st=mod.bb_solve(inst,h,stats=st); dt=time.time()-t
    return dt, ok, st

def bench(cases, hmod, reps=3, validate=False):
    rows=[[],[]]
    verdicts=[[],[]]
    for r in range(reps):
        for idx,(inst,opt) in enumerate(cases):
            for j,mod in enumerate((root_v30,root_v41)):
                dt,ok,st=one(mod,inst,opt+hmod)
                rows[j].append(dt); verdicts[j].append((ok,st.get('verdict'),st.get('os_nodes'),st.get('mpc_nodes'),st.get('t')))
                if False:
                    assert sgs.validate(inst,opt+hmod,st.get('sched') or {})[0] if False else True
    # collect per-rep totals
    out={}
    for j,name in enumerate(('v30','v41')):
        totals=[]
        for r in range(reps):
            seg=rows[j][r*len(cases):(r+1)*len(cases)]
            totals.append(sum(seg))
        out[name]={'med':statistics.median(totals),'totals':totals,
                   'verdicts':{v:sum(1 for x in verdicts[j][r*len(cases):(r+1)*len(cases)] if x[1]==v) for v in set(x[1] for x in verdicts[j])},
                   'os':sum(x[2] or 0 for x in verdicts[j][:len(cases)]),
                   'mpc':sum(x[3] or 0 for x in verdicts[j][:len(cases)])}
    out['same']=sum(1 for a,b in zip(verdicts[0][:len(cases)],verdicts[1][:len(cases)]) if bool(a[0])==bool(b[0]))
    out['n']=len(cases)
    return out

def main():
    cases={'holdout50':load('exp/v20/holdout_cases50.pkl'),
           'hard3':load('exp/v13/hard3.pkl'),'deep8':load('exp/v18/deep.pkl'),
           'large_a':load('exp/v14/large_a.pkl'),'large_b':load('exp/v14/large_b.pkl'),
           'large_het':load('exp/v14/large_het.pkl'),'synth45':load('exp/v28/synth2_45.pkl')}
    cases['residual5']=[cases['holdout50'][i] for i in [5,21,32,42,47]]
    res={}
    for name,cs in cases.items():
        res[name]=bench(cs,-1,3)
        print(name,json.dumps(res[name]),flush=True)
    res['_yes']={}
    for name in ['holdout50','hard3','deep8','residual5','synth45']:
        res['_yes'][name]=bench(cases[name],0,3)
        print(name+'_YES',json.dumps(res['_yes'][name]),flush=True)
    # 141 aggregate
    tot=0.0
    for name in ['holdout50','hard3','deep8','large_a','large_b','large_het','synth45']:
        tot+=res[name]['v41']['med']
    res['_total141']={'v30':sum(res[n]['v30']['med'] for n in ['holdout50','hard3','deep8','large_a','large_b','large_het','synth45']),
                      'v41':tot}
    print('TOTAL141',res['_total141'],flush=True)
    json.dump(res,open('exp/v41/res_final.json','w'),indent=1)

if __name__=='__main__': main()
