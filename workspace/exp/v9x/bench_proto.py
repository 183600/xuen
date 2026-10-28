import sys,json,time,collections
sys.path[:0]=['exp/v9x','exp/v91','exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from icf import corpora
from tdc_proto import run_tdc
from hap import weak_rows

def summarize(rows,tag):
 print(tag,'n',len(rows),'ok',sum(r['ok'] for r in rows),
       'cert',sum(r['certified'] for r in rows),
       'partial_fail',sum(r['partial_fail'] for r in rows),
       'q',sum(r['queries'] for r in rows),
       'lp',sum(r['pact_lp'] for r in rows),
       'certlp',sum(r['pact_cert_lp'] for r in rows),
       'pin',sum(r['pin_lp'] for r in rows),
       'tdc_calls',sum(r['tdc_calls'] for r in rows),
       'tdc_succ',sum(r['tdc_success'] for r in rows),
       'tdc_nodes',sum(r['tdc_nodes'] for r in rows),
       'tdc_roll',sum(r['tdc_rollouts'] for r in rows),
       'tdc_t',round(sum(r['tdc_t'] for r in rows),2),
       'pso_t',round(sum(r['pso_t'] for r in rows),2),
       't',round(sum(r['t'] for r in rows),2))

def main():
 rows=list(corpora())
 for width in (20,30,50):
  out=[]
  for corpus,name,idx,inst,known in rows:
   r=run_tdc(inst,known,name,idx,width=width,nodecap=20000,
             use_pact_init=True,tdc_max_gap=1)
   r['corpus']=corpus; out.append(r)
  summarize(out,'strong width %d'%width)
  json.dump(out,open('exp/v9x/proto_strong_%d.json'%width,'w'),indent=1)

if __name__=='__main__': main()
