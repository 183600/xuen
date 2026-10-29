"""Benchmark PSS against ALC on the 141 NO instances."""
import sys, pickle, json, time
sys.path[:0] = ['exp/v62', 'exp/v61', 'exp/v60', 'exp/v13']
from pss import PSS, verify_proof, count_leaves
from alc import ALC

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


def pnodes(n):
    if n['kind'] == 'leaf':
        return 1
    return 1 + pnodes(n['children'][0]) + pnodes(n['children'][1])


def walk(node, acc):
    if node['kind'] == 'leaf':
        c = node.get('cert')
        acc['leaves'] += 1
        acc['leaf_status'].append(node['status'])
        if c:
            acc['scales'].append(c.get('scale'))
            acc['support'].append(len(c.get('beta', [])) + len(c.get('dom', [])))
        return
    acc['splits'] += 1
    acc['split_info'].append(dict(i=node['i'], mid=node['mid'],
                                  cross=node.get('cross'),
                                  calls=node.get('calls'),
                                  left_inf=node.get('left_inf'),
                                  right_inf=node.get('right_inf')))
    walk(node['children'][0], acc)
    walk(node['children'][1], acc)


def run_one(cls, inst, h, **kw):
    t0 = time.time()
    a = cls(inst, h, **kw)
    v, st = a.decide()
    dt = time.time() - t0
    return a, v, st, dt


def main():
    out = {}
    tot = dict(n=0, no=0, ok=0, lp=0, nodes=0, leaves=0, certs=0,
               t=0.0, cert_t=0.0, verify_t=0.0)
    base_tot = dict(n=0, no=0, lp=0, nodes=0, certs=0, t=0.0, cert_t=0.0)
    for name, f in FILES.items():
        rows = load(f)
        agg = dict(n=0, no=0, ok=0, lp=0, nodes=0, leaves=0, certs=0,
                   t=0.0, cert_t=0.0, verify_t=0.0, max_leaves=0,
                   max_splits=0)
        bagg = dict(n=0, no=0, lp=0, nodes=0, certs=0, t=0.0, cert_t=0.0)
        detail = []
        for idx, (inst, opt) in enumerate(rows):
            h = opt - 1
            a, v, st, dt = run_one(PSS, inst, h)
            t1 = time.time()
            ok = verify_proof(inst, h, st['proof'], elig_aware=a.elig_aware)
            vt = time.time() - t1
            lv, noleaf, yesleaf = count_leaves(st['proof'])
            walk_acc = dict(leaves=0, splits=0, leaf_status=[], scales=[],
                            support=[], split_info=[])
            walk(st['proof'], walk_acc)
            agg['n'] += 1; agg['no'] += (v is False); agg['ok'] += ok
            agg['lp'] += st['lp_solves']; agg['nodes'] += pnodes(st['proof'])
            agg['leaves'] += lv; agg['certs'] += st['cert_calls']
            agg['t'] += dt; agg['cert_t'] += st['cert_t']; agg['verify_t'] += vt
            agg['max_leaves'] = max(agg['max_leaves'], lv)
            agg['max_splits'] = max(agg['max_splits'], walk_acc['splits'])
            detail.append(dict(idx=idx, v=v, ok=ok, lp=st['lp_solves'],
                               nodes=pnodes(st['proof']), leaves=lv,
                               certs=st['cert_calls'], time=dt,
                               cert_t=st['cert_t'], verify_t=vt,
                               splits=walk_acc['split_info'],
                               scales=walk_acc['scales'],
                               support=walk_acc['support']))
            b = ALC(inst, h)
            bv, bst = b.decide()
            bagg['n'] += 1; bagg['no'] += (bv is False)
            bagg['lp'] += bst['lp_solves']; bagg['nodes'] += bst['nodes']
            bagg['certs'] += bst['cert_calls']; bagg['cert_t'] += bst['cert_t']
            # time ALC in a separate loop below? Here st['cert_t'] only.
        # rerun ALC for timing (keeps the PSS timing clean)
        t0 = time.time()
        for inst, opt in rows:
            b = ALC(inst, opt - 1)
            b.decide()
        bagg['t'] = time.time() - t0
        agg['t'] = agg['t']
        out[name] = dict(pss=agg, alc=bagg, rows=detail)
        print(name, 'PSS', agg, flush=True)
        print(name, 'ALC', bagg, flush=True)
        for k in ['n', 'no', 'ok', 'lp', 'nodes', 'leaves', 'certs', 't',
                  'cert_t', 'verify_t']:
            tot[k] += agg[k]
        for k in ['n', 'no', 'lp', 'nodes', 'certs', 't', 'cert_t']:
            base_tot[k] += bagg[k]
    out['_total'] = dict(pss=tot, alc=base_tot)
    json.dump(out, open('exp/v62/pss_stats.json', 'w'), indent=1)
    print('TOTAL PSS', tot)
    print('TOTAL ALC', base_tot)


if __name__ == '__main__':
    main()
