"""Benchmarks for v9.2 BAT-ICF.

Run from the workspace directory:

    .venv/bin/python exp/v9bat/bench_bat.py live
    .venv/bin/python exp/v9bat/bench_bat.py random
    .venv/bin/python exp/v9bat/bench_bat.py capped
    .venv/bin/python exp/v9bat/bench_bat.py mcts
    .venv/bin/python exp/v9bat/bench_bat.py frontier

The live mode compares fixed ICF policies with BAT planners that use
the fold-specific priors selected by cross-validation.  The other modes
are ablations: a random planner (trust-boundary test), a capped-oracle
pilot, an MCTS/DP seed sweep, and a live multi-leaf frontier pilot.
"""
import collections
import json
import statistics
import sys
import time

sys.path[:0] = ['exp/v9bat', 'exp/v9mec', 'exp/v8u', 'exp/v8o',
                'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g',
                'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a',
                'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']

import bat
from icf import run_icf
from pact import pact_decide
from mec import run_frontier


ROWS = None
STATES = None


def rows():
    global ROWS
    if ROWS is None:
        ROWS = bat.load_bracket_rows()
    return ROWS


def states():
    global STATES
    if STATES is None:
        out = []
        for r in rows():
            kind = 'weak' if r['src'] == 'weak' else 'strong'
            init = bat.make_initial(r['inst'], kind)
            if init is None:
                out.append(None)
                continue
            L, U, s, m, proof, pin = init
            out.append((L, U, list(s), list(m), proof, int(r['pin'])))
        STATES = out
    return STATES


def load_selection(path):
    meta = json.load(open(path))
    return {int(s['fold']): s['cfg'] for s in meta['selected']}


def fold_models(folds, cfgs):
    models = {}
    for fi in range(len(folds)):
        train = [r for j, f in enumerate(folds) if j != fi for r in f]
        models[fi] = bat.fit_prior(train, cfgs[fi])
    return models


def summarize(rs, key='policy'):
    by = collections.defaultdict(list)
    for r in rs:
        by[(r.get('corpus', r.get('src', '?')), r[key])].append(r)
    out = {}
    for k, xs in sorted(by.items()):
        out['%s/%s' % k] = dict(
            n=len(xs),
            probes=sum(x.get('probes', 0) for x in xs),
            search_lp=sum(x.get('pact_lp', 0) for x in xs),
            cert_lp=sum(x.get('pact_cert_lp', 0) for x in xs),
            pin_lp=sum(x.get('pin_lp', 0) for x in xs),
            time=round(sum(x.get('t', 0.0) for x in xs), 2),
            certified=sum(bool(x.get('certified')) for x in xs),
            partial_fail=sum(x.get('partial_fail', 0) for x in xs),
            partial_final=sum(bool(x.get('partial_final')) for x in xs),
            unknown=sum(x.get('unknown', 0) for x in xs),
        )
    return out


def print_summary(tag, rs):
    print('\n==', tag)
    for k, v in summarize(rs).items():
        print('%-18s n=%3d q=%5d searchLP=%6d certLP=%6d '
              'pinLP=%5d t=%7.2f cert=%3d pf=%d' %
              (k, v['n'], v['probes'], v['search_lp'], v['cert_lp'],
               v['pin_lp'], v['time'], v['certified'],
               v['partial_fail']))


def run_live():
    rs = rows()
    st = states()
    folds = bat.make_folds(rs, k=5, seed=7)
    cfgs = load_selection('exp/v9bat/cv_prior_hpo.json')
    models = fold_models(folds, cfgs)
    fold_of = {r['group']: fi for fi, fold in enumerate(folds)
               for r in fold}

    policies = ['lower-first', 'binary', 'upper-first']
    out = []
    for pol in policies:
        t0 = time.time()
        for j, r in enumerate(rs):
            if st[j] is None:
                continue
            init = st[j]
            v = run_icf(r['inst'], r['opt'], r['name'], r['idx'],
                        policy=pol, initial=init[:5])
            v['src'] = r['src']
            v['policy'] = pol
            v['gap0'] = r['gap']
            v['pin_lp'] = r['pin']
            out.append(v)
        print('live %s wall %.2f' % (pol, time.time() - t0), flush=True)

    fixed = dict(feature_mode='full', l2=1e-3, cell_mode='prov',
                 support_k=1, fallback='interior', planner='dp',
                 dp_cap=24, uct_c=1.0, simulations=256)
    fixed_models = {fi: bat.fit_prior(
        [r for j, f in enumerate(folds) if j != fi for r in f], fixed)
        for fi in range(5)}
    t0 = time.time()
    for j, r in enumerate(rs):
        if st[j] is None:
            continue
        fi = fold_of[r['group']]
        v = bat.run_bat(r['inst'], r['opt'], r['name'], r['idx'],
                        initial=st[j], model=fixed_models[fi],
                        cfg=fixed, seed=fi)
        v['src'] = r['src']
        v['policy'] = 'BAT-fixed'
        v['gap0'] = r['gap']
        v['pin_lp'] = r['pin']
        out.append(v)
    print('live BAT-fixed wall %.2f' % (time.time() - t0), flush=True)

    t0 = time.time()
    for j, r in enumerate(rs):
        if st[j] is None:
            continue
        fi = fold_of[r['group']]
        v = bat.run_bat(r['inst'], r['opt'], r['name'], r['idx'],
                        initial=st[j], model=models[fi],
                        cfg=cfgs[fi], seed=fi)
        v['src'] = r['src']
        v['policy'] = 'BAT-HPO'
        v['gap0'] = r['gap']
        v['pin_lp'] = r['pin']
        out.append(v)
    print('live BAT-HPO wall %.2f' % (time.time() - t0), flush=True)

    json.dump(out, open('exp/v9bat/bench_live.json', 'w'), indent=1)
    print_summary('live all', out)
    for src in ('strong', 'weak', 'gap'):
        print_summary('live ' + src, [r for r in out if r['src'] == src])


def run_random():
    all_rs = rows()
    st = states()
    pos = {r['group']: j for j, r in enumerate(all_rs)}
    rs = [r for r in all_rs if r['src'] in ('strong', 'weak')]
    rs += [r for r in all_rs if r['src'] == 'gap'][:8]
    out = []
    t0 = time.time()
    cfg = dict(fallback_policy='random')
    for j, r in enumerate(rs):
        init = st[pos[r['group']]]
        if init is None:
            continue
        v = bat.run_bat(r['inst'], r['opt'], r['name'], r['idx'],
                        initial=init, model=None, cfg=cfg,
                        max_probes=64, seed=j)
        v['src'] = r['src']
        v['policy'] = 'random'
        v['pin_lp'] = r['pin']
        out.append(v)
    print('random wall %.2f' % (time.time() - t0))
    json.dump(out, open('exp/v9bat/bench_random.json', 'w'), indent=1)
    print_summary('random planner', out)


def run_capped():
    rs = [r for r in rows() if r['src'] == 'gap'][:12]
    rs += [r for r in rows() if r['src'] == 'weak'][:12]
    out = []
    t0 = time.time()
    for r in rs:
        L, U = int(r['L']), int(r['U'])
        for h in sorted(set([L, U - 1])):
            if not (L <= h < U):
                continue
            for d in (0, 1, 2, None):
                t = time.time()
                v = pact_decide(r['inst'], h, depthcap=d,
                                nodecap=None)
                out.append(dict(
                    src=r['src'], name=r['name'], idx=r['idx'],
                    L=L, U=U, h=h, depthcap=d,
                    verdict=(None if v['verdict'] is None
                             else bool(v['verdict'])),
                    lp=v.get('lp_solves', 0),
                    nodes=v.get('nodes', 0),
                    t=round(time.time() - t, 4)))
    json.dump(out, open('exp/v9bat/bench_capped.json', 'w'), indent=1)
    print('capped wall %.2f' % (time.time() - t0))
    by = collections.defaultdict(list)
    for r in out:
        by[(r['depthcap'], r['verdict'])].append(r)
    for k in sorted(by, key=lambda x: (str(x[0]), str(x[1]))):
        xs = by[k]
        print('cap', k[0], 'verdict', k[1], 'n', len(xs),
              'lp', sum(x['lp'] for x in xs),
              'meanLP', round(statistics.mean(x['lp'] for x in xs), 2))


def run_mcts():
    rs = rows()
    cfg0 = dict(feature_mode='full', l2=1e-3, cell_mode='prov',
                support_k=1, fallback='interior', planner='dp',
                dp_cap=64, uct_c=1.0, simulations=256)
    model = bat.fit_prior(rs, cfg0)
    base = []
    for r in rs:
        s = bat.simulate_row(r, model, cfg0)
        base.append(s)
    print('DP fixed', sum(x['probes'] for x in base))
    out = []
    for N in (64, 256, 1024):
        for c in (0.3, 1.0):
            for seed in (0, 1, 2):
                cfg = dict(cfg0, planner='mcts', dp_cap=0,
                           simulations=N, uct_c=c)
                xs = []
                t0 = time.time()
                for r in rs:
                    s = bat.simulate_row(r, model, cfg, seed=seed)
                    xs.append(s)
                out.append(dict(N=N, c=c, seed=seed,
                                probes=sum(x['probes'] for x in xs),
                                fails=sum(not x['ok'] for x in xs),
                                wall=round(time.time() - t0, 3)))
                print('mcts N', N, 'c', c, 'seed', seed,
                      'probes', out[-1]['probes'],
                      'fails', out[-1]['fails'], flush=True)
    json.dump(out, open('exp/v9bat/bench_mcts_sweep.json', 'w'), indent=1)


def run_frontier():
    rs = [r for r in rows() if r['src'] == 'gap']
    out = []
    t0 = time.time()
    for r in rs:
        for sp in (0, 1):
            for pol in ('binary', 'upper-first'):
                v = run_frontier(r['inst'], r['opt'], r['name'],
                                 r['idx'], split_rounds=sp,
                                 policy=pol)
                v['case'] = r['case']
                v['split_rounds'] = sp
                v['policy'] = pol
                out.append(v)
        print('frontier', r['case'], flush=True)
    json.dump(out, open('exp/v9bat/bench_frontier.json', 'w'), indent=1)
    print('frontier wall %.2f' % (time.time() - t0))
    for sp in (0, 1):
        for pol in ('binary', 'upper-first'):
            xs = [x for x in out if x['split_rounds'] == sp and
                  x['policy'] == pol]
            print('sp', sp, pol, 'ok', sum(x['ok'] for x in xs),
                  'cert', sum(x['certified'] for x in xs),
                  'q', sum(x['probes'] for x in xs),
                  'lp', sum(x['pact_lp'] + x['pact_cert_lp']
                            for x in xs),
                  'leaves', sum(x['leaves'] for x in xs),
                  'fallbacks', sum(x.get('fallbacks', 0) for x in xs))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'live'
    if mode == 'live':
        run_live()
    elif mode == 'random':
        run_random()
    elif mode == 'capped':
        run_capped()
    elif mode == 'mcts':
        run_mcts()
    elif mode == 'frontier':
        run_frontier()
    else:
        raise SystemExit('unknown mode %r' % (mode,))


if __name__ == '__main__':
    main()
