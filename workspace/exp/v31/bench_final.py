import sys, time, json, pickle, statistics
sys.path[:0] = ['exp/v31','exp/v30','exp/v29','exp/v28','exp/v25','exp/v24',
                'exp/v20','exp/v16','exp/v15','exp/v13']
import root_bb, root_v30, root_v31

def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt']) for x in d]

def run(mod, cases, hmod=0, **kw):
    t=0.0; rows=[]
    for inst,opt in cases:
        st={}
        ok,s=mod.bb_solve(inst,opt+hmod,stats=st,**kw)
        t+=s.get('t',0.0); rows.append((ok,s.get('verdict'),s.get('os_nodes'),s.get('het_nodes')))
    return t,rows

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
    out={}
    for name,cs in cases.items():
        ts={'v25':[],'v30':[],'v31':[]}
        for rep in range(3):
            for tag,mod in [('v25',root_bb),('v30',root_v30),('v31',root_v31)]:
                t,_=run(mod,cs,-1); ts[tag].append(t)
        out[name]={k:round(statistics.median(v),4) for k,v in ts.items()}
        print(name,out[name],flush=True)
    tot={k:round(sum(out[n][k] for n in out),4) for k in ('v25','v30','v31')}
    print('TOTAL141',tot,'v31/v25=%.2f v31/v30=%.2f'%(tot['v25']/tot['v31'],tot['v30']/tot['v31']))
    out['_total']=tot
    # YES side agreement
    yesbad=0
    for name,cs in cases.items():
        _,r25=run(root_bb,cs,0); _,r31=run(root_v31,cs,0)
        for a,b in zip(r25,r31):
            if bool(a[0])!=bool(b[0]): yesbad+=1
    print('YES verdict disagreements',yesbad)
    out['_yesbad']=yesbad
    json.dump(out,open('exp/v31/res_final.json','w'),indent=1)

if __name__=='__main__': main()
