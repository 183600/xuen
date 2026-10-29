import sys,pickle,random
sys.path[:0]=['exp/v33','exp/v31','exp/v30','exp/v29','exp/v13','exp/v15','exp/v16','exp/v20','exp/v25']
import turn, po, wos
from brute import feasible

def validate_full(inst,h,sched):
    n=inst['n']; m=inst['m']; p=inst['p']
    assert set(sched)==set(range(n)), (len(sched),n)
    for i,t in sched.items():
        assert t>=0 and t+p[i]<=h, (i,t,p[i],h)
    for i in range(n):
        for j in inst['pred'][i]:
            assert sched[j]+p[j]<=sched[i], ('prec',i,j)
    # capacity count
    for t in range(h):
        c=sum(1 for i in range(n) if sched[i]<=t<sched[i]+p[i])
        assert c<=m, ('cap',t,c,m)
    return True

def rand_full(rng,n,m):
    p=[rng.randint(1,4) for _ in range(n)]
    pred=[[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random()<0.25: pred[j].append(i)
    return po.make_inst(p,m,pred)

def brute_opt(inst,hmax=25):
    n=inst['n']; est,q=po.heads_tails(inst,0,[0]*n)
    for h in range(1,hmax+1):
        if feasible(inst,h,est,q): return h
    return None

if __name__=='__main__':
    # 141 NO
    CASES=[('holdout50','exp/v20/holdout_cases50.pkl'),('hard3','exp/v13/hard3.pkl'),
           ('deep8','exp/v18/deep.pkl'),('large_a','exp/v14/large_a.pkl'),
           ('large_b','exp/v14/large_b.pkl'),('large_het','exp/v14/large_het.pkl'),
           ('synth45','exp/v28/synth2_45.pkl')]
    def load(f):
        d=pickle.load(open(f,'rb')); out=[]
        for x in d:
            if isinstance(x,tuple): out.append((x[0],x[1]))
            else: out.append((x['inst'],x['opt']))
        return out
    bad=0; tot=0
    for name,f in CASES:
        for inst,opt in load(f):
            st={}; ok,_=turn.bb_solve(inst,opt-1,stats=st,icc_util_gate=0.9); tot+=1
            if ok: bad+=1; print('FALSE YES',name)
    print('141 NO: false YES',bad,'/',tot)
    # holdout YES schedules
    D=pickle.load(open('exp/v20/holdout_cases50.pkl','rb')); bady=0; badv=0
    for inst,opt in D:
        st={}; ok,_=turn.bb_solve(inst,opt,stats=st,icc_util_gate=0.9)
        if not ok: bady+=1; print('FALSE NO YES-side')
        # reconstruct schedule via solve_dir chosen
        est,q=po.heads_tails(inst,0,[0]*inst['n'])
        p=st.get('p_bwd',0.0); backward=st.get('dir')=='B'
        ok2,sched=turn.solve_dir(inst,opt,est,q,backward,200000)
        if ok2:
            try: validate_full(inst,opt,sched)
            except AssertionError as e: badv+=1; print('BAD SCHED',e)
    print('holdout YES: false NO',bady,'bad sched',badv)
    # random brute
    rng=random.Random(20261023); mism=0; false_no=0; badsch=0; ncase=0
    for trial in range(300):
        n=rng.randint(3,7); m=rng.randint(1,3)
        inst=rand_full(rng,n,m)
        opt=brute_opt(inst)
        if opt is None: continue
        for h in (opt-1,opt):
            if h<1: continue
            bf=feasible(inst,h,*po.heads_tails(inst,0,[0]*n))
            st={}; ok,_=turn.bb_solve(inst,h,stats=st,icc_util_gate=0.9)
            ncase+=1
            if bool(ok)!=bool(bf):
                mism+=1
                if bf and not ok: false_no+=1
                if mism<=5: print('MISMATCH',trial,n,m,h,ok,bf,st.get('verdict'))
    print('random',ncase,'mismatch',mism,'falseNO',false_no)
