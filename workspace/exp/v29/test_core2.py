"""Greedy deletion-minimal cores + tree sizes on the core."""
import sys, pickle, time, json
sys.path[:0] = ['exp/v29', 'exp/v13', 'exp/v20', 'exp/v25']
import po, os_pack
from test_core import subinst, feas

def main():
    d = pickle.load(open('exp/v20/holdout_cases50.pkl', 'rb'))
    out = []; t0 = time.time(); total_full = total_core = 0
    for idx, (inst, opt) in enumerate(d):
        h = opt - 1; n = inst['n']; S = set(range(n))
        # original tree size
        est, q = po.heads_tails(inst, 0, [0] * n)
        s0 = {}
        os_pack.sgs_solve(inst, h, rem=inst['full'], A=(0,) * inst['m'],
                          est=est, q=q, nodecap=200000, stats=s0)
        changed = True
        while changed:
            changed = False
            for i in sorted(S, key=lambda z: (inst['p'][z], z)):
                T = set(S); T.discard(i)
                if not T:
                    continue
                if feas(inst, T, h) is False:
                    S = T; changed = True
                    break
        z = subinst(inst, S)
        est2, q2 = po.heads_tails(z, 0, [0] * z['n'])
        s1 = {}
        v, _ = os_pack.sgs_solve(z, h, rem=z['full'], A=(0,) * z['m'],
                                 est=est2, q=q2, nodecap=200000, stats=s1)
        out.append(dict(idx=idx, n=n, core=len(S), members=sorted(S),
                        full_nodes=s0['nodes'], core_nodes=s1['nodes'],
                        ok=(v is False)))
        total_full += s0['nodes']; total_core += s1['nodes']
        print(idx, n, '->', len(S), 'nodes', s0['nodes'], '->', s1['nodes'], flush=True)
    agg = dict(n=len(out), full_nodes=total_full, core_nodes=total_core,
               mean_core=sum(r['core'] for r in out) / len(out),
               max_core=max(r['core'] for r in out),
               min_core=min(r['core'] for r in out),
               all_no=all(r['ok'] for r in out),
               t=round(time.time() - t0, 3))
    print(agg)
    json.dump(dict(agg=agg, rows=out), open('exp/v29/res_core2.json', 'w'), indent=1)

if __name__ == '__main__':
    main()
