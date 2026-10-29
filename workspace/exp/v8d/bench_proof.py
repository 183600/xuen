import sys, json, time
sys.path[:0] = ['exp/v8d', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']
from chip import base_corpus, pert_corpus, stress_corpus
from proof import ProofCRISP

def run(corpus, oracle):
    rows=[]
    for name,idx,inst,opt in corpus:
        t0=time.time(); co=ProofCRISP(inst, oracle=oracle); r=co.optimize(); dt=time.time()-t0
        rows.append(dict(name=name,idx=idx,known=opt,t=round(dt,4),q=r['queries'],
                         lp=r['lp'],yn=r['yes_nodes'],mc=r['mc_evals'],
                         certified=r['certified'],opt=r['opt'],audit=r['audit'],
                         proof=r['proof'],cert_h=r['cert_h'],unknown=r['unknown']))
    return rows

def agg(rows):
    return dict(n=len(rows),cert=sum(r['certified'] for r in rows),
                q=sum(r['q'] for r in rows),lp=sum(r['lp'] for r in rows),
                yn=sum(r['yn'] for r in rows),mc=sum(r['mc'] for r in rows),
                t=round(sum(r['t'] for r in rows),3),
                ok=sum(bool(r['certified'] and r['audit'] and r['proof']
                            and r['cert_h']==r['known']-1 and r['opt']==r['known'])
                       for r in rows))

if __name__=='__main__':
    corp=list(base_corpus())+list(pert_corpus())+[('stress',i,inst,opt) for i,(idx,opt,inst) in enumerate(stress_corpus())]
    out={}
    for oracle in ['chd','race']:
        rows=run(corp,oracle); out[oracle]=rows
        print(oracle,agg(rows),flush=True)
    json.dump(out,open('exp/v8d/bench_proof.json','w'))
