import sys, json, time
sys.path[:0]=['exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from chip import base_corpus, pert_corpus, stress_corpus
from po import heads_tails

def corpora():
    for tag, rows in (('base', base_corpus()), ('pert', pert_corpus()), ('stress', stress_corpus())):
        for row in rows:
            if len(row)==4: name,idx,inst,known=row
            else: idx,known,inst=row; name=tag
            yield tag,name,idx,inst,known

def min_overlap(est,p,lst,a,b):
    def ov(s):
        return max(0, min(s+p,b)-max(s,a))
    return min(ov(est), ov(lst))

def energy_violation(inst,h):
    n,m,p=inst['n'],inst['m'],inst['p']
    est,q=heads_tails(inst,0,[0]*n)
    lst=[h-q[i]-p[i] for i in range(n)]
    best=(0,None)
    for a in range(0,h+1):
        for b in range(a+1,h+1):
            s=sum(min_overlap(est[i],p[i],lst[i],a,b) for i in range(n))
            slack=s-m*(b-a)
            if slack>best[0]: best=(slack,(a,b))
    return best

rows=list(corpora())
by={(t,nm,idx):(inst,known) for t,nm,idx,inst,known in rows}
bench=json.load(open('exp/v8i/bench_sage_full.json'))
branch=[r for r in bench if r['proof_kind']=='branch']
print('branch',len(branch))
catch=0; vals=[]
t0=time.time()
for r in branch:
    inst,known=by[(r['corpus'],r['name'],r['idx'])]
    h=known-1
    slack,win=energy_violation(inst,h)
    vals.append(slack)
    if slack>0:
        catch+=1
        print('CATCH',r['corpus'],r['name'],r['idx'],'known',known,'slack',slack,'win',win)
print('caught',catch,'/',len(branch),'max slack',max(vals),'t',round(time.time()-t0,2))
