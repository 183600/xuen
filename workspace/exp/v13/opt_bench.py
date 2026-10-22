import sys, pickle, time, json
sys.path.insert(0,'exp/v13')
import po

MODES=['plain','canon','front','sub','ladder','ladder_front']

def prep(inst):
    n=inst['n']; m=inst['m']
    inst.setdefault('full',(1<<n)-1)
    inst.setdefault('pmask',[sum(1<<j for j in inst['pred'][i]) for i in range(n)])
    inst.setdefault('elig',[list(range(m)) for _ in range(n)])
    return inst

def lb(inst):
    est,q=po.heads_tails(inst,0,[0]*inst['n'])
    return max(est[i]+inst['p'][i]+q[i] for i in range(inst['n']))

def find_opt(inst, cap=1_500_000):
    m=inst['m']; n=inst['n']
    lo=max(lb(inst), (sum(inst['p'])+m-1)//m, max(inst['p']))
    hi=sum(inst['p'])
    # linear from a greedy upper bound downward is not monotone-safe to find OPT;
    # scan up from lo (few steps in practice)
    last=None
    for h in range(lo, hi+1):
        (ok,_),st=po.decide(inst,h,mode='plain',nodecap=cap)
        if st.get('timeout'): return None
        last=st['nodes']
        if ok: return h
    return None

def bench(inst,h,cap=2_000_000):
    out={}
    for mode in MODES:
        t=time.time()
        (ok,_),st=po.decide(inst,h,mode=mode,nodecap=cap)
        dt=time.time()-t
        out[mode]=dict(ok=ok,t=round(dt,4),nodes=st['nodes'],memo=st['memo_hits'],
                       packfh=st['pack_front_hits'],subfh=st['sub_front_hits'],
                       tables=st['tables'],greedy=st['greedy_yes'],dff=st['dff_no'],
                       inserts=st['inserts'],
                       fmax=max(st['front_sizes']) if st['front_sizes'] else 0,
                       fmed=(sorted(st['front_sizes'])[len(st['front_sizes'])//2] if st['front_sizes'] else 0),
                       timeout=st.get('timeout',False))
        print('   ',mode,out[mode]['ok'],out[mode]['nodes'],out[mode]['t'],flush=True)
    return out

if __name__=='__main__':
    res={}
    for fam,fn in [('hard17','hard17.pkl'),('pool30','pool30.pkl')]:
        d=pickle.load(open(fn,'rb'))
        for idx,item in enumerate(d):
            if fam=='hard17':
                steps,inst,info=item; prep(inst)
            else:
                inst,H,steps=item; prep(inst)
            print(fam,idx,'n',inst['n'],'m',inst['m'],'orig',steps,flush=True)
            opt=find_opt(inst)
            print('  opt',opt,flush=True)
            if opt is None or opt-1 < max(inst['p']): 
                res[f'{fam}_{idx}']=dict(n=inst['n'],m=inst['m'],opt=opt,orig=steps)
                continue
            res[f'{fam}_{idx}']=dict(n=inst['n'],m=inst['m'],opt=opt,orig=steps,h=opt-1,
                                     bench=bench(inst,opt-1))
            json.dump(res,open('v13/opt_bench.json','w'),indent=1)
    print('saved')
