import sys, time, json, pickle, os
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
 'width': {'weights': {'width':1.0}},
 'split25': {'split':0.25},
 'split33': {'split':1/3},
 'split75': {'split':0.75},
 'mass_succ': {'weights': {'mass':1.0,'succ':0.5}},
}
CAPS=[0,1,2,None]
cases=[]
for tag,name,idx,inst,known in corpora():
    for label,h in (('NO',known-1),('YES',known)):
        est,q=heads_tails(inst,0,[0]*inst['n'])
        elig=_elig_aware(inst)
        lp=SDLP(inst,h,est,q,use_dom=True,elig_aware=elig)
        res=lp.solve()
        cases.append(dict(uid=len(cases),tag=tag,name=name,idx=idx,label=label,h=h,inst=inst,lp=lp,res=res))
print('cases',len(cases),flush=True)
out={}
t00=time.time()
for pname in POLICIES:
    for cap in CAPS:
        key=(pname,cap)
        rows=[]; t0=time.time()
        for c in cases:
            r=pact_decide(c['inst'],c['h'],depthcap=cap,nodecap=None,policy=POLICIES[pname],root_lp=c['lp'],root_res=c['res'])
            rows.append(dict(uid=c['uid'],verdict=r['verdict'],depth=r['depth'],nodes=r['nodes'],
                             lp=r['lp_solves'],cert=r['cert_lp'],t=r['t'],holes=r.get('holes',0)))
        out[str(key)]=rows
        print(key,'wall',round(time.time()-t0,2),'sum_t',round(sum(r['t'] for r in rows),2),flush=True)
pickle.dump(dict(cases=[{k:v for k,v in c.items() if k not in ('inst','lp','res')} for c in cases],res=out),open('exp/v9p/cache.pkl','wb'))
print('total',round(time.time()-t00,2),flush=True)
