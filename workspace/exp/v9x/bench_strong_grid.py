import sys,json
sys.path[:0]=['exp/v9x','exp/v9d','exp/v9c','exp/v9b','exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from icf import corpora
from tdc import run_tdc_icf
rows=list(corpora())
def run(width,tl,nr,np_,it):
 out=[]
 for c,n,i,inst,k in rows:
  r=run_tdc_icf(inst,k,n,i,width=width,nodecap=20000,timelimit=tl,
                n_ranks=nr,n_particles=np_,iters=it,tdc_max_gap=5)
  r['corpus']=c; out.append(r)
 print('w%d tl%s nr%d pso%dx%d'%(width,tl,nr,np_,it),
       'q',sum(r['queries'] for r in out),'lp',sum(r['pact_lp'] for r in out),
       'cert',sum(r['pact_cert_lp'] for r in out),
       'succ',sum(r['tdc_success'] for r in out),
       'tdc_t',round(sum(r['tdc_t'] for r in out),2),
       'pso_t',round(sum(r['pso_t'] for r in out),2),
       't',round(sum(r['t'] for r in out),2),'ok',sum(r['ok'] for r in out))
 return out
for cfg in [(20,0.02,1,8,12),(50,0.05,1,8,12),(50,0.05,2,8,12),(100,0.1,2,8,12),(50,0.05,2,16,20)]:
 run(*cfg)
