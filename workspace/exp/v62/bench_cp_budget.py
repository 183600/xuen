"""Randomized CP energy budget vs LP work, on the 141 NO instances."""
import sys, pickle, json, time
sys.path[:0] = ['exp/v62', 'exp/v61', 'exp/v60', 'exp/v13']
from pss import PSS, verify_proof, count_leaves

FILES = {
 'holdout50': 'exp/v20/holdout_cases50.pkl',
 'synth45': 'exp/v28/synth2_45.pkl',
 'large_a': 'exp/v14/large_a.pkl',
 'large_b': 'exp/v14/large_b.pkl',
 'large_het': 'exp/v14/large_het.pkl',
 'hard3': 'exp/v13/hard3.pkl',
 'deep8': 'exp/v18/deep.pkl',
}


def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]


def count_cp(node):
    if node['kind'] == 'leaf':
        return 1 if node.get('reason') == 'cp' else 0
    return count_cp(node['children'][0]) + count_cp(node['children'][1])


def main():
    configs = [('no_cp', dict(cp_on=False)),
               ('cheap', dict(cp_budget=0)),
               ('K16', dict(cp_budget=16)),
               ('K32', dict(cp_budget=32)),
               ('K64', dict(cp_budget=64)),
               ('K128', dict(cp_budget=128)),
               ('K256', dict(cp_budget=256)),
               ('full', dict(cp_budget=None))]
    out = {}
    for name, kw in configs:
        t0 = time.time()
        n = no = ok = lp = certs = cpleaves = leaves = 0
        per = {}
        for fname, f in FILES.items():
            rows = load(f)
            a0 = dict(n=0, no=0, lp=0, certs=0, cp=0, ok=0)
            for idx, (inst, opt) in enumerate(rows):
                h = opt - 1
                a = PSS(inst, h, **kw)
                v, st = a.decide()
                good = verify_proof(inst, h, st['proof'],
                                    elig_aware=a.elig_aware)
                lv, _, _ = count_leaves(st['proof'])
                cp = count_cp(st['proof'])
                a0['n'] += 1; a0['no'] += (v is False); a0['lp'] += st['lp_solves']
                a0['certs'] += st['cert_calls']; a0['cp'] += cp
                a0['ok'] += good
                n += 1; no += (v is False); ok += good; lp += st['lp_solves']
                certs += st['cert_calls']; cpleaves += cp; leaves += lv
            per[fname] = a0
        out[name] = dict(total=dict(n=n, no=no, ok=ok, lp=lp, certs=certs,
                                    cp_leaves=cpleaves, leaves=leaves,
                                    t=time.time() - t0), per=per)
        print(name, out[name]['total'], flush=True)
    json.dump(out, open('exp/v62/cp_budget.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
