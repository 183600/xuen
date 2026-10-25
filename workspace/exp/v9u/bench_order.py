import json,sys,time
sys.path[:0]=['exp/v9u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from chip import base_corpus, pert_corpus, stress_corpus
from scope import run_scope

def corpora():
    for tag, rows in (('base', base_corpus()),('pert', pert_corpus()),('stress', stress_corpus())):
        for row in rows:
            if len(row)==4: name,idx,inst,known=row
            else: idx,known,inst=row; name=tag
            yield tag,name,idx,inst,known

def run(tag,order):
    rows=[]; t0=time.time()
    for corpus,name,idx,inst,known in corpora():
        r=run_scope(inst,known,name,idx,pact_depth=None,use_ga=False,scope_mode='complete',scope_budget=3,scope_order=order); r['corpus']=corpus; rows.append(r)
    wall=round(time.time()-t0,2)
    with open('exp/v9u/bench_scope_%s.json'%tag,'w') as f: json.dump(rows,f,indent=1)
    print('==',tag,'order',order,'wall',wall,'ok',sum(r['ok'] for r in rows),'pact_lp',sum(r['pact_lp'] for r in rows),'round_lp',sum(r.get('round_lp',0) for r in rows),'round_yes',sum(r.get('round_yes',0) for r in rows),'round_res',sum(r.get('round_restricted',0) for r in rows),'t',round(sum(r['t'] for r in rows),2))
if __name__=='__main__':
    run('order_thr_first',('thr02','top2','support'))
    run('order_top2_first',('top2','thr02','support'))
    run('order_thr_support',('thr02','support','top2'))
