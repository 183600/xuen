import json, sys, time
sys.path[:0] = ['exp/v10f', 'exp/v10b', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from qant import run_qant
from icf import corpora
from bench_qant import summarize
corpus=list(corpora()); cases=json.load(open('exp/v10c/gap_cases.json'))
variants=[
 ('qant_final_pilot83', dict(W=32,selector='astar',aco_gate='gap1',aco_gamma=0.0,aco_ants=24,aco_gens=8,aco_seed=0,aco_pilot=True,aco_pilot_ants=8)),
]
# pilot gens is fixed at 1 in qant; add gens via direct subclass? patch kw hack
for tag,kw in variants:
 out=[]; t0=time.time()
 for c,name,idx,inst,known in corpus:
  r=run_qant(inst,known,name,idx,**kw); r['corpus']=c; out.append(r)
 for d in cases:
  r=run_qant(d['inst'],d['opt'],d.get('case'),d.get('idx'),**kw)
  r['corpus']='gap'; r['gap_kind']=d.get('kind'); out.append(r)
 json.dump(out,open('exp/v10f/bench_%s.json'%tag,'w'),indent=1)
 summarize(out,tag+' wall '+str(round(time.time()-t0,2)))
