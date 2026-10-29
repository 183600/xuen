import json, sys, time, collections
sys.path[:0] = ['exp/v9z', 'exp/v9y', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from chip import base_corpus, pert_corpus, stress_corpus
from pact_narrow import run_narrow

def corpora():
    for tag, rows in (('base', base_corpus()), ('pert', pert_corpus()), ('stress', stress_corpus())):
        for row in rows:
            if len(row) == 4: name, idx, inst, known = row
            else: idx, known, inst = row; name = tag
            yield tag, name, idx, inst, known

def run_all(tag, **kw):
    rows=[]; t0=time.time()
    for corpus,name,idx,inst,known in corpora():
        r=run_narrow(inst,known,name,idx,**kw)
        r['corpus']=corpus; rows.append(r)
    wall=round(time.time()-t0,2)
    with open('exp/v9z/bench_narrow_%s.json'%tag,'w') as f: json.dump(rows,f,indent=1)
    print('\n==',tag,'== wall',wall)
    for c in ('base','pert','stress'):
        rs=[r for r in rows if r['corpus']==c]
        print(c,'n',len(rs),'ok',sum(r['ok'] for r in rs),'cert',sum(r['certified'] for r in rs),
              'q',sum(r['queries'] for r in rs),'search',sum(r['pact_lp'] for r in rs),
              'root',sum(r['root_lp'] for r in rs),'round_yes',sum(r['round_yes'] for r in rs),
              'karst_yes',sum(r['karst_yes'] for r in rs),'trials',sum(r['karst_trials'] for r in rs),
              'narrow',sum(r['narrow_calls'] for r in rs),'n_yes',sum(r['narrow_yes'] for r in rs),
              'n_no',sum(r['narrow_no'] for r in rs),'n_fail',sum(r['narrow_fail'] for r in rs),
              'cert_lp',sum(r['pact_cert_lp'] for r in rs),'total',sum(r['total_audit'] for r in rs),
              't',round(sum(r['t'] for r in rs),2))
    print('all ok',sum(r['ok'] for r in rows),'cert',sum(r['certified'] for r in rows),
          'q',sum(r['queries'] for r in rows),'search',sum(r['pact_lp'] for r in rows),
          'root',sum(r['root_lp'] for r in rows),'round_yes',sum(r['round_yes'] for r in rows),
          'karst_yes',sum(r['karst_yes'] for r in rows),'trials',sum(r['karst_trials'] for r in rows),
          'narrow',sum(r['narrow_calls'] for r in rows),'n_no',sum(r['narrow_no'] for r in rows),
          'n_fail',sum(r['narrow_fail'] for r in rows),
          't',round(sum(r['t'] for r in rows),2))
    print('kinds',dict(collections.Counter(r['proof_kind'] for r in rows)))

if __name__=='__main__':
    run_all('b4', narrow_attempts=4)
    run_all('b1', narrow_attempts=1)
