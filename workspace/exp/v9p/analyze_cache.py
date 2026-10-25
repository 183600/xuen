import sys, pickle, ast, math, collections, json
sys.path[:0]=['exp/v9p','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from chip import base_corpus, pert_corpus, stress_corpus
from po import heads_tails
from sdecc import SDLP
from pact import _elig_aware
D=pickle.load(open('exp/v9p/cache.pkl','rb'))
cases=D['cases']; R={ast.literal_eval(k):v for k,v in D['res'].items()}
pols=sorted(set(k[0] for k in R))
# recompute features
def corpora():
    for tag, rows in (('base', base_corpus()),('pert', pert_corpus()),('stress', stress_corpus())):
        for row in rows:
            if len(row)==4:
                name, idx, inst, known = row
            else:
                idx, known, inst = row
                name = tag
            yield tag,name,idx,inst,known
feat={}
for tag,name,idx,inst,known in corpora():
    for label,h in (('NO',known-1),('YES',known)):
        est,q=heads_tails(inst,0,[0]*inst['n'])
        elig=_elig_aware(inst)
        lp=SDLP(inst,h,est,q,use_dom=True,elig_aware=elig)
        res=lp.solve()
        if res.status==0:
            per={}
            for c,key in enumerate(lp.cols):
                i,t=key[0],key[-1]
                per.setdefault(i,{})[t]=per.setdefault(i,{}).get(t,0.0)+res.x[c]
            nfrac=sum(1 for i,d in per.items() if any(1e-7<v<1-1e-7 for v in d.values()))
            fracmass=sum(v for d in per.values() for v in d.values() if 1e-7<v<1-1e-7)
            widths=[len(d) for d in per.values()]
            maxw=max(widths) if widths else 0
            meanw=sum(widths)/max(1,len(widths))
        else:
            nfrac=fracmass=maxw=meanw=0
        key=(tag,name,idx,label)
        feat[key]=dict(n=inst['n'],m=inst['m'],h=h,root=res.status,nfrac=nfrac,fracmass=fracmass,maxw=maxw,meanw=meanw,
                       opt=known)
# join uid
rows=[]
for uid,c in enumerate(cases):
    k=(c['tag'],c['name'],c['idx'],c['label'])
    f=feat[k]
    vals={}
    for p in pols:
        r=R[(p,None)][uid]
        vals[p]=r
    best=min(pols,key=lambda p:(vals[p]['nodes'],vals[p]['t'],p))
    rows.append(dict(uid=uid,tag=c['tag'],name=c['name'],idx=c['idx'],label=c['label'],**f,best=best,
                     nodes={p:vals[p]['nodes'] for p in pols},depth={p:vals[p]['depth'] for p in pols},t={p:vals[p]['t'] for p in pols}))
print('rows',len(rows))
# only search cases: root feasible & nfrac>0
S=[r for r in rows if r['root']==0 and r['nfrac']>0]
print('search cases',len(S),collections.Counter(r['label'] for r in S))
print('best policy over all search cases',collections.Counter(r['best'] for r in S))
for lab in ('NO','YES'):
    SS=[r for r in S if r['label']==lab]
    print('\n',lab,len(SS),collections.Counter(r['best'] for r in SS))
    for p in ['default','split33','width','split25']:
        print(p,'nodes',sum(r['nodes'][p] for r in SS),'maxdepth',max(r['depth'][p] for r in SS),'t',round(sum(r['t'][p] for r in SS),3))
# oracle selector savings
for lab in ('NO','YES'):
    SS=[r for r in S if r['label']==lab]
    best_nodes=sum(r['nodes'][r['best']] for r in SS)
    def_nodes=sum(r['nodes']['default'] for r in SS)
    s33_nodes=sum(r['nodes']['split33'] for r in SS)
    print(lab,'default',def_nodes,'split33',s33_nodes,'oracle',best_nodes)
# print cases where split33 is worse than default / best differs
print('\nExamples where split33 worse than default:')
for r in S:
    if r['nodes']['split33']>r['nodes']['default']:
        print(r['tag'],r['name'],r['idx'],r['label'],'n',r['n'],'nfrac',r['nfrac'],'maxw',r['maxw'],'default',r['nodes']['default'],'s33',r['nodes']['split33'],'best',r['best'],r['nodes'][r['best']])
json.dump(rows,open('exp/v9p/features.json','w'))
