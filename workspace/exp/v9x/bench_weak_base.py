import sys,time,json
sys.path[:0]=['exp/v9x','exp/v91','exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from icf import run_icf
from hap import weak_rows
rows=[(c,n,i,inst,k,init) for c,n,i,inst,k,init in weak_rows(4)]
for limit in (40,160):
 out=[]
 t0=time.time()
 for c,n,i,inst,k,init in rows[:limit]:
  r=run_icf(inst,k,n,i,policy='lower-first',initial=init)
  r['corpus']=c; out.append(r)
 print('base first',limit,'q',sum(r['queries'] for r in out),
       'lp',sum(r['pact_lp'] for r in out),'certlp',sum(r['pact_cert_lp'] for r in out),
       't',round(sum(r['t'] for r in out),2),'ok',sum(r['ok'] for r in out),
       'cert',sum(r['certified'] for r in out),'pf',sum(r['partial_fail'] for r in out))
