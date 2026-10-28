import sys,time,json
sys.path[:0]=['exp/v9x','exp/v91','exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from tdc_proto import run_tdc
from hap import weak_rows
from icf import corpora

def summ(rows,tag):
 print(tag,'n',len(rows),'ok',sum(r['ok'] for r in rows),
       'cert',sum(r['certified'] for r in rows),'pf',sum(r['partial_fail'] for r in rows),
       'q',sum(r['queries'] for r in rows),'lp',sum(r['pact_lp'] for r in rows),
       'certlp',sum(r['pact_cert_lp'] for r in rows),
       'tdc_succ',sum(r['tdc_success'] for r in rows),'tdc_calls',sum(r['tdc_calls'] for r in rows),
       'tdc_t',round(sum(r['tdc_t'] for r in rows),2),'pso_t',round(sum(r['pso_t'] for r in rows),2),
       't',round(sum(r['t'] for r in rows),2))

rows=[(c,n,i,inst,k) for c,n,i,inst,k,_ in weak_rows(4)]
print('weak rows',len(rows))
for limit in (40,):
 for width,tl in [(20,0.02),(30,0.05)]:
  out=[]; t0=time.time()
  for c,n,i,inst,k in rows[:limit]:
   r=run_tdc(inst,k,n,i,width=width,nodecap=5000,use_pact_init=False,
             tdc_max_gap=99,tdc_timelimit=tl,policy='lower-first')
   r['corpus']=c; out.append(r)
  summ(out,'weak first%d w%d tl%s'%(limit,width,tl))
