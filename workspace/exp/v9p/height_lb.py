import sys, time, json, collections
sys.path[:0]=['exp/v9p','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from chip import base_corpus, pert_corpus, stress_corpus
from po import heads_tails
from sdecc import SDLP
from pact import _elig_aware

def corpora():
    for tag, rows in (('base', base_corpus()),('pert', pert_corpus()),('stress', stress_corpus())):
        for row in rows:
            if len(row)==4:
                name, idx, inst, known = row
            else:
                idx, known, inst = row
                name = tag
            yield tag,name,idx,inst,known

def allowed_times(lp,bounds,i):
    return sorted({key[-1] for c,key in enumerate(lp.cols) if key[0]==i and bounds[c]!=(0,0)})

def children(lp,bounds,i,mid):
    L=list(bounds); R=list(bounds)
    for c,key in enumerate(lp.cols):
        if key[0]!=i: continue
        tt=key[-1]
        if tt>mid: L[c]=(0,0)
        else: R[c]=(0,0)
    return L,R

rows=[]; t00=time.time(); counts=collections.Counter()
for tag,name,idx,inst,known in corpora():
    h=known-1
    est,q=heads_tails(inst,0,[0]*inst['n'])
    elig=_elig_aware(inst)
    lp=SDLP(inst,h,est,q,use_dom=True,elig_aware=elig)
    res=lp.solve()
    if res.status!=0: continue
    # root feasible; is it fractional?
    frac=any(1e-7<res.x[c]<1-1e-7 and lp.cols[c][0]>=0 for c in range(lp.N))
    if not frac: continue
    base=[(0,1)]*lp.N
    found=None; tried=0
    for i in range(inst['n']):
        times=allowed_times(lp,base,i)
        if len(times)<=1: continue
        for t in times[:-1]:
            tried+=1
            L,R=children(lp,base,i,t)
            rl=lp.solve(L); rr=lp.solve(R)
            if rl.status==2 and rr.status==2:
                found=(i,t); break
        if found: break
    counts['height1' if found else 'no_height1']+=1
    rows.append(dict(tag=tag,name=name,idx=idx,h=h,n=inst['n'],m=inst['m'],
                     height1=bool(found),split=found,tried=tried,
                     root_status=res.status,t=round(time.time()-t00,3)))
    print(tag,name,idx,'height1',bool(found),found,'tried',tried,flush=True)
json.dump(rows,open('exp/v9p/height1.json','w'),indent=1)
print(counts,'total',len(rows),'time',round(time.time()-t00,2))
