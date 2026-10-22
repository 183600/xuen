"""Independent validation: no TENT false positives vs exact bounded DFS."""
import sys, random, time, json
sys.path.insert(0,'.')
import exp_da as E
from proto_tent import tent_infeasible, tent_windows
from proto_tent_root import tent_thresh

def exists_completion(inst,S,A,c,H):
    n=inst['n']; full=(1<<n)-1
    memo=set()
    def rec(S,A,c):
        if max(A)>H: return False
        if S==full: return True
        key=(S,A,c)
        if key in memo: return False
        memo.add(key)
        for (cs,ca,cc) in E.gen_children(inst,S,A,c):
            if max(ca)<=H and rec(cs,ca,cc): return True
        return False
    return rec(S,tuple(A),tuple(c))

def main():
    rng=random.Random(90210)
    stats=dict(inst=0,states=0,claims=0,bad=0,thresh_ok=0,thresh_n=0,root_new_ge_old=0,root_new_gt_old=0)
    bads=[]
    for it in range(40):
        n=rng.choice([7,8])
        inst=E.gen_instance(n,rng.choice([0.2,0.3,0.4]),rng.choice([6,8,10]),rng,2)
        opt,nd,ok=E.exact_opt(inst,cap=2_000_000)
        if not ok: continue
        stats['inst']+=1
        # root comparison
        S0,A0,c0=0,(0,0),(-1,)*n
        L0=E.lower_L0(inst,S0,A0,c0); U=E.guide(inst,S0,A0,c0)
        old,_=E.thresh(inst,S0,A0,c0,U,L0,'full')
        new,_,_=tent_thresh(inst,S0,A0,c0,U,L0)
        stats['thresh_n']+=1
        if new>=old: stats['root_new_ge_old']+=1
        if new>old: stats['root_new_gt_old']+=1
        if new<=opt: stats['thresh_ok']+=1
        else: bads.append(('root',it,new,opt))
        for trial in range(3):
            S,A,c=E.random_prefix(inst,rng,rng.choice([0.3,0.5,0.7]))
            est,q=E.heads_tails(inst,S,c)
            L0s=E.lower_L0(inst,S,A,c)
            if L0s>=opt: continue
            # test all H in [L0s, opt-1] with a random subset
            Hs=list(range(L0s,opt))
            if len(Hs)>8: Hs=rng.sample(Hs,8)
            for H in Hs:
                wins=tent_windows(inst,S,A,c,H,est,q)
                claim=any(tent_infeasible(inst,S,A,c,H,a,b,est,q) for (a,b) in wins)
                stats['states']+=1
                if claim:
                    stats['claims']+=1
                    # exhaustive: is there a completion <= H?
                    if exists_completion(inst,S,A,c,H):
                        stats['bad']+=1
                        bads.append(('state',it,trial,S,A,c,H))
                        print('FALSE POSITIVE',bads[-1],flush=True)
                        return
        if it%5==0: print('inst',it,'ok',stats,flush=True)
    print('DONE',stats)
    print('bads',bads[:5])
    json.dump(stats,open('validate_tent.json','w'),indent=1)

if __name__=='__main__':
    main()
