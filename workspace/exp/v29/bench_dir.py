"""Forward/backward direction probe and doubling-race accounting."""
import sys, json, pickle
sys.path[:0] = ['exp/v29', 'exp/v13']
import po, os_pack


def rev(inst):
    n = inst['n']; z = dict(inst)
    z['pred'] = [list(inst['succ'][i]) for i in range(n)]
    z['succ'] = [list(inst['pred'][i]) for i in range(n)]
    return z


def race(F, B, start=64):
    b = start; spent = 0
    while True:
        spent += b
        if F <= b:
            return spent, 'f'
        spent += b
        if B <= b:
            return spent, 'b'
        b *= 2


def main():
    d = pickle.load(open('exp/v20/holdout_cases50.pkl', 'rb'))
    rows = []
    for idx, (inst, opt) in enumerate(d):
        h = opt - 1; n = inst['n']
        est, q = po.heads_tails(inst, 0, [0] * n)
        s = {}
        os_pack.sgs_solve(inst, h, rem=inst['full'], A=(0,) * inst['m'],
                          est=est, q=q, nodecap=300000, stats=s)
        r = rev(inst); s2 = {}
        os_pack.sgs_solve(r, h, rem=r['full'], A=(0,) * r['m'],
                          est=q, q=est, nodecap=300000, stats=s2)
        rows.append(dict(idx=idx, n=n, m=inst['m'], h=h,
                         S=h - max(est[i] + inst['p'][i] + q[i] for i in range(n)),
                         sump=sum(inst['p']), maxest=max(est), maxq=max(q),
                         sumest=sum(est), sumq=sum(q),
                         fwd=s['nodes'], bwd=s2['nodes']))
    tot_f = sum(r['fwd'] for r in rows)
    tot_b = sum(r['bwd'] for r in rows)
    tot_o = sum(min(r['fwd'], r['bwd']) for r in rows)
    tot_r = sum(race(r['fwd'], r['bwd'])[0] for r in rows)
    agg = dict(fwd=tot_f, bwd=tot_b, oracle=tot_o, race=tot_r,
               bwd_wins=sum(1 for r in rows if r['bwd'] < r['fwd']))
    print(json.dumps(agg, indent=1))
    json.dump(dict(agg=agg, rows=rows), open('exp/v29/res_dir.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
