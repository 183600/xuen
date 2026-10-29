import sys,json,time
sys.path[:0]=['exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from hap import weak_rows
from icf import run_icf
for pol in ['upper-first','binary','gap:4']:
 t0=time.time(); rs=[]
 for j,(c,name,idx,inst,known,initial) in enumerate(weak_rows(4)):
  r=run_icf(inst,known,name,idx,policy=pol,initial=initial);r['corpus']=c;rs.append(r)
 print(pol,'rows',len(rs),'ok',sum(r['ok'] for r in rs),'cert',sum(r['certified'] for r in rs),'probes',sum(r['probes'] for r in rs),'lp',sum(r['pact_lp'] for r in rs),'certlp',sum(r['pact_cert_lp'] for r in rs),'pin',sum(r['pin_lp'] for r in rs),'t',round(time.time()-t0,3),'unk',sum(r['unknown'] for r in rs))
 json.dump(rs,open('exp/v8u/bench_icf_weak_'+pol.replace(':','')+'.json','w'),indent=1)
