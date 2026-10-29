import sys, time, json, itertools, collections
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
 'mass_wide': {'weights': {'mass':1.0,'width':-0.5}},
}
cases=[]
for tag,name,idx,inst,known in corpora():
    for label,h in (('NO',known-1),('YES',known)):
        est,q=heads_tails(inst,0,[0]*inst['n'])
        elig=_elig_aware(inst)
        lp=SDLP(inst,h,est,q,use_dom=True,elig_aware=elig)
        res=lp.solve()
        cases.append(dict(tag=tag,name=name,idx=idx,label=label,h=h,inst=inst,lp=lp,res=res))
print('cases',len(cases))

def one(c,pname,cap=None):
    return pact_decide(c['inst'],c['h'],depthcap=cap,nodecap=None,policy=POLICIES[pname],root_lp=c['lp'],root_res=c['res'])

def run_port(p1,cap,p2):
    rows=[]; t0=time.time()
    for c in cases:
        r1=one(c,p1,cap)
        nodes=r1['nodes']; lp=r1['lp_solves']; cert=r1['cert_lp']; t=r1['t']; verdict=r1['verdict']; depth=r1['depth']
        used1=verdict is not None
        if used1:
            r=r1
        else:
            r2=one(c,p2,None)
            nodes+=r2['nodes']; lp+=r2['lp_solves']-1; cert+=r2['cert_lp']; t+=r2['t']; verdict=r2['verdict']; depth=max(depth,r2['depth'])
            r=r2
        rows.append(dict(tag=c['tag'],name=c['name'],idx=c['idx'],label=c['label'],h=c['h'],
                         verdict=verdict,depth=depth,nodes=nodes,lp=lp,cert=cert,t=t,used1=used1))
    return rows,round(time.time()-t0,2)

# baseline single complete
single={}
for p in POLICIES:
    rows,w=run_port(p,None,p)
    single[p]=(rows,w)
    for lab in ('NO','YES'):
        rs=[r for r in rows if r['label']==lab]
        print('single',p,lab,'nodes',sum(r['nodes'] for r in rs),'depthmax',max(r['depth'] for r in rs),'lp',sum(r['lp'] for r in rs),'t',round(sum(r['t'] for r in rs),2),'used1',sum(r['used1'] for r in rs))
    print('wall',w)

best=[]
for p1 in ['default','mass','q','width','split25','split33','split75','mass_succ','mass_wide']:
    for cap in [0,1,2]:
        for p2 in ['default','mass','q','width','split25','split33','split75','mass_succ','mass_wide']:
            rows,w=run_port(p1,cap,p2)
            no=[r for r in rows if r['label']=='NO']; yes=[r for r in rows if r['label']=='YES']
            # cost: all verdicts, nodes; ensure correctness
            ok=all(r['verdict'] is not None for r in rows)
            best.append((ok,sum(r['nodes'] for r in rows),sum(r['lp'] for r in rows),round(sum(r['t'] for r in rows),2),
                         max(r['depth'] for r in no),max(r['depth'] for r in yes),p1,cap,p2,
                         sum(r['nodes'] for r in no),sum(r['nodes'] for r in yes),
                         sum(r['cert'] for r in rows),sum(r['used1'] for r in rows)))
best.sort(key=lambda x:(not x[0],x[1],x[2]))
print('\nTOP by nodes')
for b in best[:25]: print(b)
print('\nTOP by time')
for b in sorted(best,key=lambda x:(not x[0],x[3],x[1]))[:20]: print(b)
