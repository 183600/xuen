import sys
sys.path[:0]=['exp/v9x','exp/v91','exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from icf import corpora
from tdc_proto import run_tdc
def summ(rows,tag):
 print(tag,'q',sum(r['queries'] for r in rows),'lp',sum(r['pact_lp'] for r in rows),
       'succ',sum(r['tdc_success'] for r in rows),'tdc_t',round(sum(r['tdc_t'] for r in rows),2),
       'pso_t',round(sum(r['pso_t'] for r in rows),2),'t',round(sum(r['t'] for r in rows),2),
       'ok',sum(r['ok'] for r in rows))
rows=list(corpora())
for tl in (0.002,0.005,0.01,0.02,0.05,None):
 out=[]
 for c,n,i,inst,k in rows:
  r=run_tdc(inst,k,n,i,width=20,nodecap=5000,use_pact_init=True,
            tdc_max_gap=1,tdc_timelimit=tl)
  r['corpus']=c; out.append(r)
 summ(out,'tl %s'%tl)
