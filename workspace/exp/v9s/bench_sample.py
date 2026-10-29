"""Coverage and ablation of the deterministic sampler at h=OPT."""
import sys, json, time, collections
sys.path[:0]=['exp/v9s','exp/v8o','exp/v8i','exp/v8c','exp/v8a','exp/v60','exp/v13','exp/v9d','exp/v9c','exp/v9b']
from chip import base_corpus, pert_corpus, stress_corpus
from dsc import sample_yes
from po import heads_tails
from cab import _greedy_rank

def corpora():
    for tag, rows in (('base',base_corpus()),('pert',pert_corpus()),('stress',stress_corpus())):
        for row in rows:
            if len(row)==4: name, idx, inst, known = row
            else: idx, known, inst = row; name=tag
            yield tag,name,idx,inst,known

def run(tag, B=256, **kw):
    rows=[]; t0=time.time()
    for corp,name,idx,inst,known in corpora():
        r=sample_yes(inst,known,budget=B,**kw)
        rows.append(dict(corpus=corp,name=name,idx=idx,n=inst['n'],h=known,
                         hit=r['hit'],samples=r['samples'],best=r['best'],
                         root=r['root'],t=r['t']))
    wall=round(time.time()-t0,2)
    hits=[r for r in rows if r['hit'] is not None]
    print('\n==',tag,'B',B,'wall',wall)
    print(' hits',len(hits),'/252','miss',252-len(hits),
          'med_hit',sorted(r['hit'] for r in hits)[len(hits)//2] if hits else None,
          'max_hit',max((r['hit'] for r in hits),default=None),
          'sum_samples',sum(r['samples'] for r in rows),
          'time',round(sum(r['t'] for r in rows),2))
    for c in ('base','pert','stress'):
        rs=[r for r in rows if r['corpus']==c]
        print('  ',c,'hits',sum(1 for r in rs if r['hit'] is not None),'/',len(rs),
              'sum_samples',sum(r['samples'] for r in rs))
    json.dump(rows,open('exp/v9s/sample_%s.json'%tag,'w'))
    return rows

if __name__=='__main__':
    which=sys.argv[1] if len(sys.argv)>1 else 'halton_div'
    if which=='halton_div': run(which,256)
    elif which=='halton_nodiv': run(which,256,diversify=False)
    elif which=='uniform': run(which,256,source='uniform')
    elif which=='random0': run(which,256,mode='random',seed=0)
    elif which=='random1': run(which,256,mode='random',seed=1)
    elif which=='random2': run(which,256,mode='random',seed=2)
    elif which=='mix4': run(which,256,uniform_mix=4)
    elif which=='mix16': run(which,256,uniform_mix=16)
    elif which=='b32': run(which,32)
    elif which=='b64': run(which,64)
    elif which=='b128': run(which,128)
    elif which=='b512': run(which,512)
