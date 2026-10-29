import sys, time, pickle
sys.path.insert(0,'/home/runner/work/xuen/xuen/workspace/exp')
import exp_da as E

# ---- deadline-aware list scheduling (online witness) ----
def greedy_lst(inst,S,A,c):
    n,p,pred=inst['n'],inst['p'],inst['pred']
    A=list(A); c=list(c)
    while True:
        est,q=E.heads_tails(inst,S,tuple(c))
        ready=[i for i in range(n) if not ((S>>i)&1) and all((S>>j)&1 for j in pred[i])]
        if not ready: break
        i=max(ready,key=lambda x:(p[x]+q[x],-x))
        base=max([c[j] for j in pred[i]]+[0])
        bk=min(range(len(A)),key=lambda k:(max(A[k],base)+p[i],k))
        st=max(A[bk],base); A[bk]=st+p[i]; c[i]=st+p[i]; S|=1<<i
    return max(A)

def all_greedy(inst,S,A,c,rules=('CP','LST','LPT','MWKR')):
    return {r:(greedy_lst(inst,S,A,c) if r=='LST' else E.greedy(inst,S,A,c,r)) for r in rules}

# ---- C2: energetic interval bound ----
def energetic_refute(inst,S,A,c,H):
    n,p=inst['n'],inst['p']
    est,q=E.heads_tails(inst,S,c)
    lct=[H-q[i] for i in range(n)]
    R=[i for i in range(n) if not ((S>>i)&1)]
    if not R: return False
    pts=set([0,H])
    for i in R:
        for x in (est[i],est[i]+p[i],lct[i]-p[i],lct[i]):
            if 0<=x<=H: pts.add(x)
    pts=sorted(pts)
    for ai in range(len(pts)):
        a=pts[ai]
        for bi in range(ai+1,len(pts)):
            b=pts[bi]
            cap=sum(max(0,b-max(a,Ak)) for Ak in A)
            if cap<=0: continue
            tot=0
            for i in R:
                lo=max(0,min(est[i]+p[i],b)-max(est[i],a))
                hi=max(0,min(lct[i],b)-max(lct[i]-p[i],a))
                tot+=min(lo,hi)
                if tot>cap: return True
    return False

# ---- C3: disjunctive conflict graph ----
def conflict_refute(inst,S,A,c,H):
    n,p,m=inst['n'],inst['p'],len(A)
    est,q=E.heads_tails(inst,S,c)
    R=[i for i in range(n) if not ((S>>i)&1)]
    lst={i:H-q[i]-p[i] for i in R}
    adj={i:set() for i in R}
    for x in range(len(R)):
        i=R[x]
        for y in range(x+1,len(R)):
            j=R[y]
            if est[i]+p[i]>lst[j] and est[j]+p[j]>lst[i]:
                adj[i].add(j); adj[j].add(i)
    # m=2: bipartite needed
    if m==2:
        col={}
        for s in R:
            if s in col: continue
            col[s]=0; st=[s]
            while st:
                u=st.pop()
                for v in adj[u]:
                    if v not in col: col[v]=1-col[u]; st.append(v)
                    elif col[v]==col[u]: return True
        return False
    # general: greedy clique > m
    for order in (R, list(reversed(R))):
        cl=[]
        for v in order:
            if all(v in adj[u] for u in cl): cl.append(v)
        if len(cl)>m: return True
    return False

def cert_refute(inst,S,A,c,H,use_e,use_k):
    if E.lower_L0(inst,S,A,c)>H: return True
    wins,est,q=E.make_windows(inst,S,A,c,H+1)
    if wins and E.infeasible_at(inst,S,A,c,H,est,q,wins): return True
    if use_e and energetic_refute(inst,S,A,c,H): return True
    if use_k and conflict_refute(inst,S,A,c,H): return True
    return False

def run2(inst,use_e=False,use_k=False,guide=('CP','LST','LPT','MWKR'),budget=2000,root_cert=True):
    n=inst['n']; full=(1<<n)-1
    S0,A0,c0=0,(0,0),(-1,)*n
    U=min(all_greedy(inst,S0,A0,c0,guide).values())
    L0=E.lower_L0(inst,S0,A0,c0)
    if root_cert and cert_refute(inst,S0,A0,c0,U-1,use_e,use_k):
        return {'steps':0,'U':U,'proved':True,'nodes_by':{}}
    F0=L0; root={'S':S0,'A':A0,'c':c0,'F':F0,'f':max(max(A0),F0),'id':0}
    Open=[root]; nxt=1; Dom={0:[(A0,c0)]}; steps=0; pruned={'avail':0,'ener':0,'conf':0}
    while Open and steps<budget:
        fmin=min(v['f'] for v in Open)
        if fmin>=U: return {'steps':steps,'U':U,'proved':True,'pruned':pruned}
        phi=[v for v in Open if v['f']<=fmin+2]; phi.sort(key=lambda v:(v['f'],v['id']))
        cand=phi[:32]; bestv=None; bestg=None
        for v in cand:
            g=min(all_greedy(inst,v['S'],v['A'],v['c'],guide).values())
            if g<U: U=g
            if bestv is None or (g,v['f'],v['id'])<(bestg,bestv['f'],bestv['id']): bestv,bestg=v,g
        v=bestv; Open.remove(v); steps+=1
        for (cs,ca,cc) in E.gen_children(inst,v['S'],v['A'],v['c']):
            if cs==full:
                if max(ca)<U: U=max(ca)
                continue
            if E.lower_L0(inst,cs,ca,cc)>=U: pruned['avail']+=1; continue
            wins,est,q=E.make_windows(inst,cs,ca,cc,U)
            if wins and E.infeasible_at(inst,cs,ca,cc,U-1,est,q,wins): pruned['avail']+=1; continue
            if use_e and energetic_refute(inst,cs,ca,cc,U-1): pruned['ener']+=1; continue
            if use_k and conflict_refute(inst,cs,ca,cc,U-1): pruned['conf']+=1; continue
            g=min(all_greedy(inst,cs,ca,cc,guide).values())
            if g<U: U=g
            Fw=max(v['F'],E.lower_L0(inst,cs,ca,cc)); fw=max(max(ca),Fw)
            if fw>=U: continue
            b=Dom.setdefault(cs,[])
            if any(E.dominates(A2,c2,ca,cc,cs) for (A2,c2) in b): continue
            b[:]=[(A2,c2) for (A2,c2) in b if not E.dominates(ca,cc,A2,c2,cs)]
            if len(b)<60: b.append((ca,cc))
            Open.append({'S':cs,'A':ca,'c':cc,'F':Fw,'f':fw,'id':nxt}); nxt+=1
    return {'steps':steps,'U':U,'proved':False,'pruned':pruned}

if __name__=='__main__':
    hard=pickle.load(open('exp/hard17.pkl','rb'))
    cfgs=[('base',dict()),('+E',dict(use_e=True)),('+K',dict(use_k=True)),('+EK',dict(use_e=True,use_k=True))]
    tot={c[0]:0 for c in cfgs}
    for st,inst,r in hard:
        line=[]
        for name,kw in cfgs:
            t0=time.time(); res=run2(inst,**kw); tot[name]+=res['steps']
            line.append(f"{name}={res['steps']}{'' if res['proved'] else '!'}")
        print(f"AG={st:4d} OPT={r['U']} | "+' '.join(line),flush=True)
    print('TOTALS',tot)
