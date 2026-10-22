import sys, pickle, time, json
sys.path.insert(0,'exp/v13')
import po

MODES=['plain','canon','front','sub','ladder','ladder_front']

def find_opt(inst, lo, hi, cap=1_500_000):
    # smallest h with YES
    for h in range(lo, hi+1):
        (ok,_),st = po.decide(inst, h, mode='plain', nodecap=cap)
        if ok: return h, st
    return None, None

def bench(inst, h, cap=2_000_000):
    out={}
    for mode in MODES:
        t=time.time()
        (ok,_),st = po.decide(inst, h, mode=mode, nodecap=cap)
        dt=time.time()-t
        out[mode]=dict(ok=ok, t=round(dt,4), nodes=st['nodes'],
                       memo=st['memo_hits'], packfh=st['pack_front_hits'],
                       subfh=st['sub_front_hits'], tables=st['tables'],
                       greedy=st['greedy_yes'], dff=st['dff_no'],
                       inserts=st['inserts'],
                       fmax=max(st['front_sizes']) if st['front_sizes'] else 0,
                       fmed=(sorted(st['front_sizes'])[len(st['front_sizes'])//2] if st['front_sizes'] else 0),
                       timeout=st.get('timeout',False))
    return out

if __name__=='__main__':
    res={}
    d=pickle.load(open('hard17.pkl','rb'))
    for idx,(steps,inst,info) in enumerate(d):
        print('hard17',idx,'n',inst['n'],'m',inst['m'],'steps',steps, flush=True)
        opt,st0=find_opt(inst, info['L'], info['U'])
        print('  opt',opt, flush=True)
        h=opt-1 if opt is not None else info['U']
        res['hard17_%d'%idx]=dict(n=inst['n'],m=inst['m'],opt=opt,h=h,orig_steps=steps,
                                  bench=bench(inst,h))
        print('   ') 
    d2=pickle.load(open('pool30.pkl','rb'))
    for idx,(inst,H,steps) in enumerate(d2):
        print('pool30',idx,'n',inst['n'],'m',inst['m'],'H',H,'steps',steps, flush=True)
        if 'full' not in inst:
            inst['full']=(1<<inst['n'])-1
        if 'pmask' not in inst:
            inst['pmask']=[sum(1<<j for j in inst['pred'][i]) for i in range(inst['n'])]
        res['pool30_%d'%idx]=dict(n=inst['n'],m=inst['m'],H=H,orig_steps=steps,
                                  bench=bench(inst,H))
    json.dump(res,open('v13/hard.json','w'),indent=1)
    print('saved')
