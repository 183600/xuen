import sys,pickle
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v15')
import po

def reach(inst):
    n=inst['n']; R=[[False]*n for _ in range(n)]
    for i in range(n):
        for j in inst['succ'][i]: R[i][j]=True
    for k in range(n):
        for i in range(n):
            if R[i][k]:
                for j in range(n):
                    if R[k][j]: R[i][j]=True
    return R

def ov(s,p,a,b):
    lo=max(s,a); hi=min(s+p,b); return max(0,hi-lo)

def gamma(chain,S,ps,r,d,h):
    # integer-time DP; returns min total overlap
    INF=10**9
    prev=None; prevp=0
    for idx in chain:
        p=ps[idx]; lo=r[idx]; hi=d[idx]-p
        cur=[INF]*(h+1)
        if hi<lo: return INF
        for s in range(lo,hi+1):
            v=sum(ov(s,p,a,b) for a,b in S)
            if prev is None:
                cur[s]=v
            else:
                best=INF
                lim=min(h, s-prevp)
                for sp in range(0, lim+1):
                    if prev[sp]<best: best=prev[sp]
                if best<INF: cur[s]=v+best
        prev=cur; prevp=p
    return min(prev) if prev else INF

def alpha(S,ps,r,d,i):
    v=ps[i]
    for a,b in S:
        v=min(v, b-a)
    # formula requires single interval; for union use min over starts
    lo=r[i]; hi=d[i]-ps[i]
    if hi<lo: return 0
    best=10**9
    for s in range(lo,hi+1):
        best=min(best,sum(ov(s,ps[i],a,b) for a,b in S))
    return best

def chains(inst,cap=300000):
    n=inst['n']; succ=inst['succ']; R=reach(inst)
    out=[]; cnt=[0]
    def dfs(cur):
        cnt[0]+=1
        if cnt[0]>cap: raise RuntimeError('cap')
        out.append(tuple(cur))
        for j in range(n):
            if R[cur[-1]][j]:
                dfs(cur+[j])
    for i in range(n):
        try: dfs([i])
        except RuntimeError: return out,True
    return out,False

SETS=[('hard3','exp/v13/hard3.pkl',[2,5]),('large_het','exp/v14/large_het.pkl',[1])]
for tag,path,idxs in SETS:
    d=pickle.load(open(path,'rb'))
    for k in idxs:
        rec=d[k]
        inst,opt=(rec[0],rec[1]) if isinstance(rec,tuple) else (rec['inst'],rec['opt'])
        n,m,p=inst['n'],inst['m'],inst['p']; h=opt-1
        est,q=po.heads_tails(inst,0,[0]*n)
        r=list(est); dd=[h-q[i] for i in range(n)]
        ch,capped=chains(inst)
        print('='*60); print(tag,k,'h',h,'chains',len(ch),'capped',capped)
        # tight single intervals from all a,b
        starts=sorted(set(r+[dd[i]-p[i] for i in range(n)]))
        ends=sorted(set(dd+[r[i]+p[i] for i in range(n)]))
        cands=[]
        for a in starts:
            for b in ends:
                if b<=a: continue
                c=m*(b-a)
                tot=sum(alpha([(a,b)],p,r,dd,i) for i in range(n))
                cands.append((c-tot,a,b,tot,c))
        cands.sort()
        print('best single',cands[0])
        # test chain gains on top-3 tight intervals
        for (sl,a,b,tot,c) in cands[:3]:
            S=[(a,b)]
            base=sum(alpha(S,p,r,dd,i) for i in range(n))
            best=(0,None)
            for C in ch:
                sa=sum(alpha(S,p,r,dd,i) for i in C)
                g=gamma(C,S,p,r,dd,h)-sa
                if g>best[0]: best=(g,C)
            print('  [%d,%d] slack %d base %d cap %d maxgain %d chain %s'%(a,b,sl,base,c,best[0],best[1]))

print('\n### union pairs + chains')
for tag,path,idxs in SETS:
    d=pickle.load(open(path,'rb'))
    for k in idxs:
        rec=d[k]
        inst,opt=(rec[0],rec[1]) if isinstance(rec,tuple) else (rec['inst'],rec['opt'])
        n,m,p=inst['n'],inst['m'],inst['p']; h=opt-1
        est,q=po.heads_tails(inst,0,[0]*n)
        r=list(est); dd=[h-q[i] for i in range(n)]
        ch,_=chains(inst)
        starts=sorted(set(r+[dd[i]-p[i] for i in range(n)]+[0]))
        ends=sorted(set(dd+[r[i]+p[i] for i in range(n)]+[h]))
        ivs=[]
        for a in starts:
            for b in ends:
                if b<=a: continue
                cap=m*(b-a)
                W=sum(min(sum(ov(s,p[i],a,b) for s in [0]) for _ in [0]) for i in [])  # placeholder
                # exact beta for single
                W=0
                for i in range(n):
                    best=min(sum(ov(s,p[i],a,b) for a2,b2 in [(a,b)]) for s in range(r[i],dd[i]-p[i]+1)) if dd[i]-p[i]>=r[i] else 0
                    W+=best
                sl=cap-W
                if sl<=2: ivs.append((sl,a,b,W,cap))
        ivs.sort()
        best=(0,None)
        for x in range(len(ivs)):
            for y in range(x+1,len(ivs)):
                s1,a1,b1,_,_=ivs[x]; s2,a2,b2,_,_=ivs[y]
                if not (b1<=a2 or b2<=a1): continue
                S=[(a1,b1),(a2,b2)]
                cap=m*((b1-a1)+(b2-a2))
                base=0
                for i in range(n):
                    lo,hi=r[i],dd[i]-p[i]
                    if hi<lo: base+=0
                    else: base+=min(sum(ov(s,p[i],a,b) for a,b in S) for s in range(lo,hi+1))
                if base<=cap: continue
                for C in ch:
                    sa=sum(min(sum(ov(s,p[i],a,b) for a,b in S) for s in range(r[i],dd[i]-p[i]+1)) for i in C)
                    g=gamma(C,S,p,r,dd,h)-sa
                    if g>best[0]: best=(g,(S,base,cap,C))
        print(tag,k,'best chain-gain pair',best[0], best[1] if best[1] else '')
