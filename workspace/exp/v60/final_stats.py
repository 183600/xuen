import sys, pickle, time, json, statistics
sys.path[:0] = ['exp/v60', 'exp/v13']
import sdecc, cert

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
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt']) for x in d]

def main():
    out = {}
    all_certs = []
    t00 = time.time()
    for name, f in FILES.items():
        cs = load(f)
        rows = []
        t0 = time.time()
        for idx, (inst, opt) in enumerate(cs):
            h = opt - 1
            t1 = time.time()
            v, st = sdecc.sdecc_no(inst, h)
            dt = time.time() - t1
            certs = []
            cert_forbids = []
            if st['root'] == 'infeasible':
                c = cert.integer_certificate(inst, h)
                certs.append(c); cert_forbids.append(None)
            elif v is False and st['branches']:
                i, mid, _ = st['branches'][0]
                for forbid in ({ (i, t) for t in range(mid + 1, h + 1) },
                               { (i, t) for t in range(0, mid + 1) }):
                    certs.append(cert.integer_certificate(inst, h, forbid=forbid))
                    cert_forbids.append(forbid)
            ok = all(c is not None and cert.verify(inst, h, c, forbid=fb)
                     for c, fb in zip(certs, cert_forbids))
            rows.append(dict(idx=idx, v=v, root=st['root'], nodes=st['nodes'],
                             t=dt, certs=len(certs), cert_ok=ok,
                             branch=st['branches'][:1]))
            for c in certs:
                if c is not None:
                    all_certs.append(c)
        root_no = sum(1 for r in rows if r['root'] == 'infeasible')
        nodes = sum(r['nodes'] for r in rows)
        out[name] = dict(n=len(cs), root_no=root_no,
                         branch_cases=sum(1 for r in rows if r['root'] != 'infeasible'),
                         branch_nodes=nodes - len(cs), nodes=nodes,
                         t=time.time() - t0,
                         certs=sum(r['certs'] for r in rows),
                         cert_fail=sum(1 for r in rows if not r['cert_ok']),
                         rows=rows)
        print(name, 'root', root_no, '/', len(cs), 'branch', out[name]['branch_cases'],
              'bnodes', out[name]['branch_nodes'], 'totalnodes', nodes,
              'certs', out[name]['certs'], 'certfail', out[name]['cert_fail'],
              't', round(out[name]['t'], 3), flush=True)
    # certificate statistics
    packs = [c for c in all_certs if c.get('kind') == 'packing']
    cps = [c for c in all_certs if c.get('kind') == 'cp']
    sc = [c['scale'] for c in packs]
    cuts = [len(c['beta']) + len(c['dom']) for c in packs]
    doms = [len(c['dom']) for c in packs]
    betas = [len(c['beta']) for c in packs]
    stats = dict(total_certs=len(all_certs), packings=len(packs), cp=len(cps),
                 scale_max=max(sc), scale_median=statistics.median(sc),
                 scale_mean=round(statistics.mean(sc), 1),
                 cuts_max=max(cuts), cuts_median=statistics.median(cuts),
                 cuts_mean=round(statistics.mean(cuts), 1),
                 beta_max=max(betas), dom_max=max(doms),
                 dom_median=statistics.median(doms))
    out['_stats'] = stats
    out['_wall'] = time.time() - t00
    json.dump(out, open('exp/v60/final_stats.json', 'w'), indent=1)
    print('STATS', stats, 'wall', round(out['_wall'], 3))

if __name__ == '__main__':
    main()
