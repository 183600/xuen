import sys,json,time
sys.path[:0]=['exp/v9x','exp/v91','exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from icf import corpora
from tdc_proto import run_tdc

def summarize(rows,tag):
 print(tag,'q',sum(r['queries'] for r in rows),'lp',sum(r['pact_lp'] for r in rows),
       'tdc_succ',sum(r['tdc_success'] for r in rows),'tdc_calls',sum(r['tdc_calls'] for r in rows),
       'tdc_t',round(sum(r['tdc_t'] for r in rows),2),'pso_t',round(sum(r['pso_t'] for r in rows),2),
       't',round(sum(r['t'] for r in rows),2),'ok',sum(r['ok'] for r in rows))

def main():
 rows=list(corpora())
 for width,cap in [(8,1000),(10,2000),(15,3000),(20,5000),(20,20000),(30,10000)]:
  out=[]
  for corpus,name,idx,inst,known in rows:
   r=run_tdc(inst,known,name,idx,width=width,nodecap=cap,
             use_pact_init=True,tdc_max_gap=1)
   r['corpus']=corpus; out.append(r)
  summarize(out,'strong w%d cap%d'%(width,cap))

if __name__=='__main__': main()
