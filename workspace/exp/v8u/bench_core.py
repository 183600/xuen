import sys, json, time, collections
sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']
from core_icf import run_core_icf
from icf import corpora

def main(policy='lower-first'):
    rows = list(corpora())
    out = []
    t0 = time.time()
    for j, (c, name, idx, inst, known) in enumerate(rows):
        r = run_core_icf(inst, known, f'{c}/{name}', idx, policy=policy)
        r['corpus'] = c
        out.append(r)
        if j % 20 == 0 or j == len(rows) - 1:
            print(f'{j+1}/{len(rows)} {c}/{name}/{idx} ok={r.get("ok")} '
                  f'probes={r.get("probes")} lp={r.get("total_lp")} '
                  f'fb={r.get("fallbacks")} k={r.get("core_k")}', flush=True)
    path = f'exp/v8u/bench_core_{policy}.json'
    json.dump(out, open(path, 'w'))
    n = len(out)
    ok = sum(bool(r.get('ok')) for r in out)
    print('\nwrote', path)
    print('ok', ok, '/', n)
    for key in ('probes', 'pact_lp', 'root_lp', 'pact_cert_lp',
                'total_lp', 'pact_nodes', 'fallbacks', 'core_cert_lp',
                'pin_lp', 'partial_fail'):
        print(key, sum(r.get(key, 0) or 0 for r in out))
    print('root status', collections.Counter(
        k for r in out for k, v in (r.get('core_status') or {}).items()
        for _ in range(v)))
    print('k distribution', collections.Counter(
        r.get('core_k') for r in out if r.get('core_k')))
    print('proof kinds', collections.Counter(r.get('proof_kind') for r in out))
    print('core_audit', collections.Counter(r.get('core_audit') for r in out))
    print('branch_ok', collections.Counter(r.get('core_branch_ok') for r in out))
    print('fallback rows', [(r['corpus'], r['name'], r['idx'], r['fallbacks'])
                            for r in out if r.get('fallbacks')])
    print('wall', round(time.time() - t0, 2))
    return out

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'lower-first')
