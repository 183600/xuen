import sys, pickle, json, math
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v14')
import po

def load(path):
    d=pickle.load(open(path,'rb'))
    out=[]
    for x in d:
        if isinstance(x,tuple): out.append({'inst':x[0],'opt':x[1]})
        else: out.append(x)
    return out

def dff_lb(items, caps):
    """Lower bound on #bins needed: max over DFF family f_p and large-count.
    caps: list of per-machine capacities (heterogeneous). Returns (lb, witness)."""
    if not items: return 0,None
    C=max(caps)
    if C<=0: return 10**9,('cap',)
    best=0; bw=None
    tot=sum(items)
    lb=(tot + C -1)//C
    if lb>best: best,bw=lb,('vol',None)
    # f_p(x) = floor(p*x/C), f(C)=p  => sum floor(p s/C) <= p * #bins
    for p in range(1,41):
        s=sum((p*x)//C for x in items)
        rhs=sum((p*c)//C for c in caps)
        if rhs<=0: continue
        lb=(s + rhs -1)//rhs
        if lb>best: best,bw=lb,('fp',p)
    # large items: each > C/2 needs its own bin
    big=sum(1 for x in items if 2*x>C)
    if big>best: best,bw=big,('big',None)
    # > C - t for t in 1..C/2 : items > C-t cannot share with items > t
    for t in range(1,C//2+1):
        a=sum(1 for x in items if x>C-t)
        rest=[x for x in items if x<=C-t]
        # remaining items must share bins with the a large ones; count extra bins by volume of x>t
        big2=[x for x in rest if x>t]
        lb=a+max(0,(sum(big2)-(a*0))//C)  # crude
    return best,bw

def windows(inst, rem, A, est, q, h):
    p=inst['p']; m=inst['m']
    tasks=list(po.bititer(rem))
    r=[est[i] for i in tasks]; d=[h-q[i] for i in tasks]; ps=[p[i] for i in tasks]
    starts=set(r)|set(d[i]-ps[i] for i in range(len(tasks)))
    ends=set(d)|set(r[i]+ps[i] for i in range(len(tasks)))
    return tasks,r,ps,d,sorted(starts),sorted(ends)

def best_pack_cert(inst, rem, A, est, q, h, verbose=False):
    tasks,r,ps,d,starts,ends=windows(inst,rem,A,est,q,h)
    m=inst['m']; best=(0,None)
    for a in starts:
        if a<0: continue
        for b in ends:
            if b<=a or b>h+max(ps): continue
            C=b-a
            caps=[max(0,b-max(a,A[k])) for k in range(m)]
            idx=[i for i in range(len(tasks)) if r[i]>=a and d[i]<=b]
            if len(idx)<2: continue
            items=[ps[i] for i in idx]
            if sum(items)<=sum(caps): 
                pass
            lb,w=dff_lb(items,caps)
            if lb>m and lb>best[0]:
                best=(lb,(a,b,C,caps,[tasks[i] for i in idx],items,w))
    return best

for tag,path in [('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),
                 ('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]:
    data=load(path)
    for k,rec in enumerate(data):
        inst=rec['inst']; opt=rec['opt']; h=opt-1
        est0,q0=po.heads_tails(inst,0,[0]*inst['n'])
        lb,w=best_pack_cert(inst,inst['full'],(0,)*inst['m'],tuple(est0),q0,h)
        if lb>inst['m']:
            a,b,C,caps,tis,items,ww=w
            print(f"{tag}#{k} n={inst['n']} OPT={opt} CLOSED by pack: a={a} b={b} C={C} |omega|={len(tis)} sum={sum(items)} lb={lb} witness={ww}")
        else:
            print(f"{tag}#{k} n={inst['n']} OPT={opt} pack-lb max={lb} (no close)")
