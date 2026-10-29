import sys, random
sys.path[:0]=['exp/v31','exp/v13']
import po, hec, ewos
from brute import feasible

def rand_inst(rng, n, m):
    p=[rng.randint(1,4) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<0.25: pred[j].append(i)
    elig=[]
    for i in range(n):
        k=rng.randint(1,m)
        elig.append(sorted(rng.sample(range(m),k)))
    inst=po.make_inst(p,m,pred,elig)
    return inst

def main():
    rng=random.Random(20261023)
    bad=0; tot=0; hecbad=0
    for trial in range(400):
        n=rng.randint(3,6); m=rng.randint(1,3)
        inst=rand_inst(rng,n,m)
        est,q=po.heads_tails(inst,0,[0]*n)
        opt=None
        for h in range(1,14):
            if feasible(inst,h,est,q): opt=h; break
        if opt is None: continue
        for h in [opt-1,opt]:
            if h<1: continue
            tot+=1
            bf=feasible(inst,h,est,q)
            hv = hec.check(inst,h,est,q)
            if (not hv) and bf:
                hecbad+=1; print('HEC FALSE NO',trial,n,m,h)
            ok,_=ewos.solve(inst,h,rem=inst['full'],est=est,q=q,nodecap=200000)
            if ok!=bf:
                bad+=1; print('EWOS MISMATCH',trial,n,m,h,'ewos',ok,'bf',bf)
    print('cases',tot,'ewos mismatches',bad,'hec false NO',hecbad)

if __name__=='__main__': main()
