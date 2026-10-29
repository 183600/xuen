import sys
sys.path[:0]=['exp/v9x','exp/v9d','exp/v9c','exp/v9b','exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from icf import corpora
from hap import weak_rows
from tdc import run_tdc_icf
strong=list(corpora())
weak=[(c,n,i,inst,k,init) for c,n,i,inst,k,init in weak_rows(4)]
for suite,rows,use_pact in [('strong',[(c,n,i,inst,k,None) for c,n,i,inst,k in strong],True),
                            ('weak',weak,False)]:
 for trie in (True,False):
  out=[]
  for c,n,i,inst,k,init in rows:
   r=run_tdc_icf(inst,k,n,i,width=20,nodecap=5000,timelimit=0.02,
                 use_pact_init=use_pact,initial=init,use_trie=trie,
                 tdc_max_gap=99 if suite=='weak' else 5)
   r['corpus']=c; out.append(r)
  print(suite,'trie',trie,'q',sum(r['queries'] for r in out),
        'lp',sum(r['pact_lp'] for r in out),
        'cert',sum(r['pact_cert_lp'] for r in out),
        'succ',sum(r['tdc_success'] for r in out),
        'tdc_t',round(sum(r['tdc_t'] for r in out),2),
        't',round(sum(r['t'] for r in out),2),
        'adm',sum(r['trie_admitted'] for r in out),
        'mer',sum(r['trie_merged'] for r in out),
        'ok',sum(r['ok'] for r in out))
