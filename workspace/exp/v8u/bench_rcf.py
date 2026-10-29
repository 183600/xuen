import sys, json, time, collections, argparse
sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']
from icf import corpora
from rcf import run_rcf
from chip import base_bounds
from pact import PACT, pact_decide
from bench_ptb import init_weak


def run_normal(args):
    rows = list(corpora())
    out = []
    t0 = time.time()
    for j, (c, name, idx, inst, known) in enumerate(rows):
        r = run_rcf(inst, known, name, idx, policy=args.policy,
                    core_budget=(None if args.budget < 0 else args.budget),
                    use_primal=not args.no_primal,
                    split_mode=args.split, fallback=args.fallback,
                    seed=args.seed)
        r['corpus'] = c
        out.append(r)
        if j % 20 == 0 or j == len(rows) - 1:
            print(f'{j+1}/{len(rows)} {c}/{name}/{idx} ok={r.get("ok")} '
                  f'probes={r.get("probes")} splits={r.get("splits")} '
                  f'lp={r.get("total_lp")} leaves={r.get("leaves")}',
                  flush=True)
    return out, t0


def run_weak(args):
    rows = []
    for c, name, idx, inst, known in corpora():
        initial = init_weak(inst)
        if initial[1] - initial[0] < 4:
            continue
        rows.append((c, name, idx, inst, known, initial))
    out = []
    t0 = time.time()
    for j, (c, name, idx, inst, known, initial) in enumerate(rows):
        r = run_rcf(inst, known, name, idx, policy=args.policy,
                    core_budget=(None if args.budget < 0 else args.budget),
                    use_primal=not args.no_primal,
                    split_mode=args.split, fallback=args.fallback,
                    initial=initial, seed=args.seed)
        r['corpus'] = c
        out.append(r)
        if j % 20 == 0 or j == len(rows) - 1:
            print(f'{j+1}/{len(rows)} {c}/{name}/{idx} ok={r.get("ok")} '
                  f'probes={r.get("probes")} splits={r.get("splits")} '
                  f'lp={r.get("total_lp")} leaves={r.get("leaves")}',
                  flush=True)
    return out, t0


def summarize(out, path, t0):
    json.dump(out, open(path, 'w'))
    n = len(out)
    print('\nwrote', path, 'rows', n)
    print('ok', sum(bool(r.get('ok')) for r in out), '/', n)
    for key in ('probes', 'splits', 'yes', 'no', 'unknown',
                'primal_calls', 'primal_yes', 'primal_fail',
                'primal_lp', 'lp', 'cert_lp', 'total_lp',
                'core_probes', 'core_insufficient', 'leaves',
                'max_leaves', 'rank_fail', 'partial_fail'):
        print(key, sum((r.get(key) or 0) for r in out))
    print('core_status', collections.Counter(
        k for r in out for k, v in (r.get('core_status') or {}).items()
        for _ in range(v)))
    print('core_k max', max((r.get('core_k') or 0) for r in out),
          'mean', round(sum((r.get('core_k_mean') or 0) for r in out) / n, 3))
    print('proof', collections.Counter(
        'certified' if r.get('certified') else 'partial' for r in out))
    print('wall', round(time.time() - t0, 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['normal', 'weak'])
    ap.add_argument('--budget', type=int, default=-1,
                    help='core nodecap; -1 means complete core search')
    ap.add_argument('--no-primal', action='store_true')
    ap.add_argument('--split', default='core',
                    choices=['core', 'oracle', 'domain'])
    ap.add_argument('--fallback', default='none',
                    choices=['none', 'full'])
    ap.add_argument('--policy', default='lower',
                    choices=['lower', 'binary'])
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()
    fn = run_normal if args.mode == 'normal' else run_weak
    out, t0 = fn(args)
    if args.out is None:
        tag = f'{args.mode}_b{args.budget}'
        if args.no_primal:
            tag += '_noprimal'
        tag += f'_{args.split}_{args.fallback}'
        args.out = f'exp/v8u/rcf_{tag}.json'
    summarize(out, args.out, t0)


if __name__ == '__main__':
    main()
