"""Benchmark BICF-P: online buffered portfolio with ratio certificates.

Run from the workspace root:

    .venv/bin/python exp/v8u/bench_bicf.py

The main experiment is the 252-instance corpus, three commitment orders,
eight buffer sizes, and a portfolio of 6 structured + 16 random priority
rules.  A second experiment ablates the priority rules.  A third audits
the LP/Farkas lower-bound certificate on all 252 instances at b=8.  A
fourth audits every committed prefix on a 24-instance sample.  A fifth
compares against the exact receding-horizon batch oracle.
"""
import json
import statistics
import sys
import time
from collections import defaultdict

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

import bicf
from oicf import run_rolling


ROWS = list(bicf.corpora())
SUBSET = ROWS[:8] + ROWS[141:149] + ROWS[201:209]
B_VALUES = [1, 2, 3, 4, 5, 8, 16, None]
ORDERS = [('critical', 1), ('random', 2), ('reverse-critical', 3)]


def bname(b, n):
    return 'n' if b is None else str(b)


def summarize(xs):
    xs = list(xs)
    if not xs:
        return {}
    return dict(n=len(xs), mean=round(statistics.mean(xs), 4),
                max=round(max(xs), 4),
                p95=round(sorted(xs)[min(len(xs) - 1,
                                         int(0.95 * len(xs)))], 4))


def strong_bounds():
    """One LP/Farkas lower bound per instance, reused by all runs."""
    out = {}
    t0 = time.time()
    for j, (tag, name, idx, inst, known) in enumerate(ROWS):
        r = bicf.initial_lp_bound(inst)
        out[j] = r
        if j % 50 == 0 or j == len(ROWS) - 1:
            print('strong %d/%d %s/%s/%s L=%s U=%s t=%.2f'
                  % (j + 1, len(ROWS), tag, name, idx,
                     None if r is None else r['L'],
                     None if r is None else r['U'],
                     time.time() - t0), flush=True)
    return out


def main_experiment(strong):
    out = []
    t0 = time.time()
    for j, (tag, name, idx, inst, known) in enumerate(ROWS):
        n = inst['n']
        Lc = bicf.cheap_lb(inst)
        sb = strong.get(j)
        for okey, oseed in ORDERS:
            order = bicf.make_order(inst, seed=oseed, key=okey)
            rules = bicf.make_rules(n_random=16, seed=100)
            for b0 in B_VALUES:
                b = n if b0 is None else b0
                r = bicf.portfolio(inst, order, b, rules)
                cert = bicf.RatioCertificate(
                    inst, r['starts'], r['machine'], Lc,
                    label='%s/%s/%s' % (tag, name, idx))
                audit = bool(cert.audit_rdf())
                row = dict(corpus=tag, name=name, idx=idx, n=n,
                           order=okey, b=bname(b0, n), b_eff=b,
                           known=known, U=r['cmax'],
                           L_cheap=Lc, ratio=round(r['cmax'] / known, 6),
                           cert_ratio_cheap=round(cert.ratio, 6),
                           exact=bool(r['cmax'] == known),
                           audit_cheap=audit,
                           all_exact=bool(Lc == r['cmax'] == known))
                if sb is not None and b == 8:
                    cert2 = bicf.RatioCertificate(
                        inst, r['starts'], r['machine'], sb['L'],
                        lb_proof=sb['proof'], lb_mode='proof',
                        label='%s/%s/%s' % (tag, name, idx))
                    row['L_lp'] = sb['L']
                    row['cert_ratio_lp'] = round(cert2.ratio, 6)
                    row['audit_lp'] = bool(cert2.audit_rdf())
                    row['proof_kind'] = (sb['proof'].kind
                                         if sb['proof'] is not None
                                         else None)
                out.append(row)
        if j % 20 == 0 or j == len(ROWS) - 1:
            print('main %d/%d %s/%s/%s t=%.2f'
                  % (j + 1, len(ROWS), tag, name, idx,
                     time.time() - t0), flush=True)
    return out


def aggregate_main(rows):
    by_b = defaultdict(list)
    by_order = defaultdict(list)
    for r in rows:
        by_b[(r['order'], r['b'])].append(r)
        if r['b'] == '8':
            by_order[r['order']].append(r)
    tab = {}
    for key, rs in sorted(by_b.items()):
        order, b = key
        tab['%s/b%s' % (order, b)] = dict(
            n=len(rs),
            mean_ratio=round(statistics.mean(r['ratio'] for r in rs), 4),
            max_ratio=round(max(r['ratio'] for r in rs), 4),
            exact=sum(1 for r in rs if r['exact']),
            mean_cert=round(statistics.mean(r['cert_ratio_cheap']
                                            for r in rs), 4),
            max_cert=round(max(r['cert_ratio_cheap'] for r in rs), 4),
            audits=sum(1 for r in rs if r['audit_cheap']),
            audit_fail=sum(1 for r in rs if not r['audit_cheap']),
        )
    return dict(by_b=tab, by_order={k: summarize([r['ratio'] for r in v])
                                   for k, v in by_order.items()})


def ablation():
    out = {}
    for b in (1, 2, 5, 8, None):
        key = bname(b, 0)
        t0 = time.time()
        rows = []
        for tag, name, idx, inst, known in ROWS:
            n = inst['n']
            bb = n if b is None else b
            order = bicf.make_order(inst, seed=1, key='critical')
            Lc = bicf.cheap_lb(inst)
            est, q = bicf.heads_tails(inst)
            cands = {}
            for rule in ('critical', 'hlf', 'lpt', 'spt', 'est', 'mixed'):
                rr = bicf.schedule(inst, order, bb, rule, None, est, q)
                cands[rule] = rr['cmax']
            for K in (16,):
                rng_rules = bicf.make_rules(n_random=K, seed=100)
                best = None
                for rule, rank in rng_rules:
                    rr = bicf.schedule(inst, order, bb, rule, rank, est, q)
                    if best is None or rr['cmax'] < best:
                        best = rr['cmax']
                cands['random16'] = best
            for label, rules in (
                    ('portfolio6', bicf.make_rules(n_random=0)),
                    ('portfolio22', bicf.make_rules(n_random=16, seed=100)),
                    ('portfolio38', bicf.make_rules(n_random=32, seed=100))):
                rr = bicf.portfolio(inst, order, bb, rules)
                cands[label] = rr['cmax']
            for label, c in cands.items():
                rows.append(dict(corpus=tag, name=name, idx=idx, n=n,
                                 known=known, b=key, policy=label,
                                 U=c, ratio=round(c / known, 6),
                                 exact=bool(c == known)))
        summ = {}
        for label in sorted(set(r['policy'] for r in rows)):
            rs = [r for r in rows if r['policy'] == label]
            summ[label] = dict(
                n=len(rs),
                mean=round(statistics.mean(r['ratio'] for r in rs), 4),
                max=round(max(r['ratio'] for r in rs), 4),
                exact=sum(1 for r in rs if r['exact']))
        out[key] = dict(summary=summ, t=round(time.time() - t0, 3))
        print('ablation b=%s t=%.2f' % (key, time.time() - t0), flush=True)
    return out


def prefix_audits(strong):
    out = []
    t0 = time.time()
    for j, (tag, name, idx, inst, known) in enumerate(SUBSET):
        n = inst['n']
        order = bicf.make_order(inst, seed=1, key='critical')
        rules = bicf.make_rules(n_random=16, seed=100)
        Lc = bicf.cheap_lb(inst)
        sb = strong.get(ROWS.index((tag, name, idx, inst, known)))
        best = None
        best_rule = None
        for rule, rank in rules:
            est, q = bicf.heads_tails(inst)
            rr = bicf.schedule(inst, order, 8, rule, rank, est, q,
                               snapshots=True)
            if best is None or rr['cmax'] < best['cmax']:
                best = rr
                best_rule = (rule, rank)
        final_starts = list(best['starts'])
        final_machine = list(best['machine'])
        okc = okp = 0
        badc = badp = 0
        for st in best['states']:
            committed = {}
            for i in st['committed']:
                committed[i] = (final_starts[i], final_machine[i])
            cc = bicf.RatioCertificate(
                inst, final_starts, final_machine, Lc,
                committed=committed, lb_mode='cheap')
            if cc.audit_rdf():
                okc += 1
            else:
                badc += 1
            if sb is not None:
                cp = bicf.RatioCertificate(
                    inst, final_starts, final_machine, sb['L'],
                    committed=committed, lb_proof=sb['proof'],
                    lb_mode='proof')
                if cp.audit_rdf():
                    okp += 1
                else:
                    badp += 1
        out.append(dict(corpus=tag, name=name, idx=idx, n=n,
                        rule=best_rule[0], U=best['cmax'], known=known,
                        ratio=round(best['cmax'] / known, 6),
                        prefixes=len(best['states']),
                        cheap_ok=okc, cheap_fail=badc,
                        lp_ok=okp, lp_fail=badp))
        if j % 4 == 0 or j == len(SUBSET) - 1:
            print('prefix %d/%d t=%.2f' % (j + 1, len(SUBSET),
                                           time.time() - t0), flush=True)
    return out


def exact_baseline():
    out = []
    t0 = time.time()
    for j, (tag, name, idx, inst, known) in enumerate(SUBSET):
        n = inst['n']
        order = bicf.make_order(inst, seed=1, key='critical')
        for b0 in (2, 5, None):
            b = n if b0 is None else b0
            t1 = time.time()
            r = run_rolling(inst, order, b, commit_rule='earliest',
                            place='optimal', audit=True)
            out.append(dict(corpus=tag, name=name, idx=idx, n=n,
                            b=bname(b0, n), known=known,
                            U=r.get('opt'), ratio=round(
                                (r.get('opt') or 0) / known, 6),
                            exact=bool(r.get('opt') == known),
                            calls=r.get('calls'), lp=r.get('lp'),
                            nodes=r.get('nodes'),
                            cert_fail=r.get('cert_fail'),
                            ok=bool(r.get('ok')),
                            t=round(time.time() - t1, 4)))
        if j % 4 == 0 or j == len(SUBSET) - 1:
            print('exact %d/%d t=%.2f' % (j + 1, len(SUBSET),
                                          time.time() - t0), flush=True)
    summ = {}
    for b in ('2', '5', 'n'):
        rs = [r for r in out if r['b'] == b]
        summ[b] = dict(n=len(rs),
                       mean=round(statistics.mean(r['ratio'] for r in rs), 4),
                       max=round(max(r['ratio'] for r in rs), 4),
                       exact=sum(1 for r in rs if r['exact']),
                       calls=sum(r['calls'] or 0 for r in rs),
                       lp=sum(r['lp'] or 0 for r in rs),
                       t=round(sum(r['t'] for r in rs), 3))
    return dict(rows=out, summary=summ)


def portfolio_subset_for_exact():
    out = []
    for tag, name, idx, inst, known in SUBSET:
        n = inst['n']
        order = bicf.make_order(inst, seed=1, key='critical')
        rules = bicf.make_rules(n_random=16, seed=100)
        for b0 in (2, 5, None):
            b = n if b0 is None else b0
            r = bicf.portfolio(inst, order, b, rules)
            out.append(dict(corpus=tag, name=name, idx=idx, n=n,
                            b=bname(b0, n), known=known, U=r['cmax'],
                            ratio=round(r['cmax'] / known, 6),
                            exact=bool(r['cmax'] == known)))
        # b=8, not in the exact sweep
        r = bicf.portfolio(inst, order, 8, rules)
        out.append(dict(corpus=tag, name=name, idx=idx, n=n, b='8',
                        known=known, U=r['cmax'],
                        ratio=round(r['cmax'] / known, 6),
                        exact=bool(r['cmax'] == known)))
    summ = {}
    for b in ('2', '5', '8', 'n'):
        rs = [r for r in out if r['b'] == b]
        summ[b] = dict(n=len(rs),
                       mean=round(statistics.mean(r['ratio'] for r in rs), 4),
                       max=round(max(r['ratio'] for r in rs), 4),
                       exact=sum(1 for r in rs if r['exact']))
    return dict(rows=out, summary=summ)


def main():
    t0 = time.time()
    print('loading strong bounds', flush=True)
    strong = strong_bounds()
    print('strong wall', round(time.time() - t0, 2), flush=True)

    t1 = time.time()
    main_rows = main_experiment(strong)
    main_agg = aggregate_main(main_rows)
    print('MAIN', json.dumps(main_agg['by_b'], sort_keys=True)[:3000])
    print('main wall', round(time.time() - t1, 2), flush=True)

    t2 = time.time()
    abl = ablation()
    print('ABLATION', json.dumps({k: v['summary'] for k, v in abl.items()},
                                 sort_keys=True)[:3000])
    print('ablation wall', round(time.time() - t2, 2), flush=True)

    t3 = time.time()
    pref = prefix_audits(strong)
    print('PREFIX', json.dumps(dict(
        n=len(pref),
        cheap_ok=sum(r['cheap_ok'] for r in pref),
        cheap_fail=sum(r['cheap_fail'] for r in pref),
        lp_ok=sum(r['lp_ok'] for r in pref),
        lp_fail=sum(r['lp_fail'] for r in pref),
        prefixes=sum(r['prefixes'] for r in pref)), sort_keys=True))
    print('prefix wall', round(time.time() - t3, 2), flush=True)

    t4 = time.time()
    exact = exact_baseline()
    print('EXACT', json.dumps(exact['summary'], sort_keys=True))
    port_sub = portfolio_subset_for_exact()
    print('PORT-SUBSET', json.dumps(port_sub['summary'], sort_keys=True))
    print('exact wall', round(time.time() - t4, 2), flush=True)

    with open('exp/v8u/bench_bicf.json', 'w') as f:
        json.dump(dict(main=main_rows, main_agg=main_agg,
                       ablation=abl), f)
    with open('exp/v8u/bench_bicf_strong.json', 'w') as f:
        json.dump(dict(
            rows=[r for r in main_rows if r.get('L_lp') is not None],
            strong=strong), f, default=str)
    with open('exp/v8u/bench_bicf_prefix.json', 'w') as f:
        json.dump(pref, f)
    with open('exp/v8u/bench_bicf_exact.json', 'w') as f:
        json.dump(dict(exact=exact, portfolio=port_sub), f)
    print('ALL wall', round(time.time() - t0, 2))


if __name__ == '__main__':
    main()
