import sys, time, json, collections
sys.path[:0]=['exp/v9p','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from chip import base_corpus, pert_corpus, stress_corpus
from po import heads_tails
from sdecc import SDLP
from pact import pact_decide, _elig_aware

def corpora():
    for tag, rows in (('base', base_corpus()),('pert', pert_corpus()),('stress', stress_corpus())):
        for row in rows:
            if len(row)==4:
                name, idx, inst, known = row
            else:
                idx, known, inst = row
                name = tag
            yield tag,name,idx,inst,known

POLICIES = {
 'default': {},
 'mass': {'weights': {'mass':1.0}},
 'q': {'weights': {'q':1.0}},
 'slack': {'weights': {'slack':1.0}},
 'width': {'weights': {'width':1.0}},
 'entropy': {'weights': {'entropy':1.0}},
 'spread': {'weights': {'spread':1.0}},
 'mass_q': {'weights': {'mass':1.0,'q':0.5}},
 'mass_succ': {'weights': {'mass':1.0,'succ':0.5}},
 'mass_slack': {'weights': {'mass':1.0,'slack':0.5}},
 'mass_wide': {'weights': {'mass':1.0,'width':-0.5}},
 'frac_peak': {'weights': {'frac':1.0,'peak':1.0}},
 'split25': {'split':0.25},
 'split75': {'split':0.75},
 'split33': {'split':1/3},
}

cases=[]
for tag,name,idx,inst,known in corpora():
    for label,h in (('NO',known-1),('YES',known)):
        est,q=heads_tails(inst,0,[0]*inst['n'])
        elig=_elig_aware(inst)
        lp=SDLP(inst,h,est,q,use_dom=True,elig_aware=elig)
        res=lp.solve()
        cases.append((tag,name,idx,label,h,inst,est,q,elig,lp,res))
print('cases',len(cases))

def run(pol):
    rows=[]; t0=time.time()
    for tag,name,idx,label,h,inst,est,q,elig,lp,res in cases:
        r=pact_decide(inst,h,depthcap=None,nodecap=None,policy=pol,root_lp=lp,root_res=res)
        rows.append(dict(tag=tag,name=name,idx=idx,label=label,h=h,
                         verdict=r['verdict'],depth=r['depth'],nodes=r['nodes'],
                         lp=r['lp_solves'],cert=r['cert_lp'],t=r['t'],
                         branch_jobs=r.get('branch_jobs',[])))
    wall=round(time.time()-t0,2)
    return rows,wall

out={}
for pname,pol in POLICIES.items():
    rows,wall=run(pol)
    out[pname]=rows
    for lab in ('NO','YES'):
        rs=[r for r in rows if r['label']==lab]
        print(pname,lab,'n',len(rs),'nodes',sum(r['nodes'] for r in rs),'depthmax',max(r['depth'] for r in rs),'lp',sum(r['lp'] for r in rs),'cert',sum(r['cert'] for r in rs),'t',round(sum(r['t'] for r in rs),2))
    print(' wall',wall)
json.dump(out,open('exp/v9p/pilot.json','w'))
