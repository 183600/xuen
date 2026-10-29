import sys,random,time,json
sys.path.insert(0,'v13')
import po
def gen(rng,n,m,pmax=10,ep=0.15):
    p=[rng.randint(2,pmax) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<ep: pred[j].append(i)
        if j>0 and not pred[j] and rng.random()<0.6: pred[j].append(rng.randrange(j))
    return po.make_inst(p,m,pred,[list(range(m)) for _ in range(n)])
def find_opt(inst,cap=1_000_000):
    est,q=po.heads_tails(inst,0,[0]*inst['n'])
    lo=max(max(est[i]+inst['p'][i]+q[i] for i in range(inst['n'])),max(inst['p']))
    for h in range(lo,lo+10):
        (ok,_),st=po.decide(inst,h,mode='sub',nodecap=cap)
        if st.get('timeout'): return None
        if ok: return h
    return None
if __name__=='__main__':
    rng=random.Random(999)
    out=[]
    for n in [18,20,22]:
        got=0
        while got<2:
            inst=gen(rng,n,3)
            opt=find_opt(inst)
            if opt is None: continue
            row={'n':n,'opt':opt,'bench':{}}
            print('n',n,'opt',opt,flush=True)
            for mode in ['sub','plain']:
                t=time.time(); (ok,_),st=po.decide(inst,opt-1,mode=mode,nodecap=5_000_000); dt=time.time()-t
                row['bench'][mode]=dict(nodes=st['nodes'],t=round(dt,3),tables=st['tables'],
                                        packfh=st['pack_front_hits'],subfh=st['sub_front_hits'],
                                        fmax=max(st['front_sizes']) if st['front_sizes'] else 0,
                                        timeout=st.get('timeout',False))
                print('  ',mode,ok,st['nodes'],round(dt,3),st.get('timeout'),flush=True)
            out.append(row); got+=1
            json.dump(out,open('v13/scale_n.json','w'),indent=1)
    print('saved')
