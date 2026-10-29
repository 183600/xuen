"""Benchmark DIP on the 252 corpus and on composed instances.

Usage (from workspace root):
    .venv/bin/python exp/v10d/bench_dip.py

The composed suite is deliberately structural: serial stacks are built
by adding sink->source edges, parallel stacks by disjoint machine sets.
The monolithic baseline is v9.0 ICF-PACT on the same instance.  A wall
clock cap turns a runaway monolithic probe into a reported timeout.
"""
import sys
import json
import time
import collections
import multiprocessing as mp

sys.path[:0] = ['exp/v10d', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from icf import corpora, run_icf
from po import make_inst
from dip import run_dip, build_tree, plan_cost


# ---------------------------------------------------------------- corpora
def corpus_rows():
    return list(corpora())


def concat_serial(insts):
    p, pred, elig = [], [], []
    off = 0
    blocks = []
    for inst in insts:
        n = inst['n']
        blocks.append((off, n, inst))
        p += list(inst['p'])
        for j in range(n):
            pred.append([i + off for i in inst['pred'][j]])
            elig.append(list(inst['elig'][j]))
        off += n
    for b in range(len(insts) - 1):
        o1, n1, i1 = blocks[b]
        o2, n2, i2 = blocks[b + 1]
        sinks = [j for j in range(n1) if not i1['succ'][j]]
        srcs = [j for j in range(n2) if not i2['pred'][j]]
        for a in sinks:
            for b2 in srcs:
                pred[o2 + b2].append(o1 + a)
    return make_inst(p, max(i['m'] for i in insts), pred, elig)


def concat_parallel(insts):
    p, pred, elig = [], [], []
    off = 0
    m0 = max(i['m'] for i in insts)
    for b, inst in enumerate(insts):
        n = inst['n']
        p += list(inst['p'])
        for j in range(n):
            pred.append([i + off for i in inst['pred'][j]])
            elig.append([k + b * m0 for k in inst['elig'][j]])
        off += n
    return make_inst(p, m0 * len(insts), pred, elig)


def _mono_worker(q, ci, known, name, idx, max_probes):
    try:
        r = run_icf(ci, known, name, idx, policy='lower-first',
                    max_probes=max_probes)
        q.put(r)
    except Exception as e:
        q.put({'error': repr(e)})


def run_mono(ci, known, name, idx, cap=30.0, max_probes=64):
    ctx = mp.get_context('fork')
    q = ctx.Queue()
    p = ctx.Process(target=_mono_worker,
                    args=(q, ci, known, name, idx, max_probes))
    t0 = time.time()
    p.start()
    p.join(cap)
    if p.is_alive():
        p.terminate()
        p.join(2)
        return dict(status='timeout', t=round(cap, 3), known=known,
                    opt=None, lb=None, certified=False, ok=False,
                    queries=0, pact_lp=0)
    try:
        r = q.get_nowait()
    except Exception:
        return dict(status='crash', t=round(time.time() - t0, 3),
                    known=known, opt=None, lb=None, certified=False,
                    ok=False, queries=0, pact_lp=0)
    r['status'] = 'done'
    return r


# ---------------------------------------------------------------- suites
def make_cases(rows):
    base = {(t, nm, ix): (inst, k) for t, nm, ix, inst, k in rows}
    A = base[('base', 'holdout', 0)]
    B = base[('base', 'holdout', 1)]
    C = base[('base', 'large_het', 7)]
    D = base[('base', 'large_a', 3)]
    cases = []
    for tag, blocks in [
            ('serial_k2', [A, B]),
            ('serial_k3', [A, B, C]),
            ('serial_k4', [A, B, C, D]),
            ('serial_k4_rep', [C, C, C, C])]:
        cases.append((tag, concat_serial([x[0] for x in blocks]),
                      sum(x[1] for x in blocks)))
    for tag, blocks in [
            ('parallel_k3', [A, B, C]),
            ('parallel_k4', [A, B, C, D]),
            ('parallel_k4_rep', [C, C, C, C])]:
        cases.append((tag, concat_parallel([x[0] for x in blocks]),
                      max(x[1] for x in blocks)))
    # mixed: (A||B) ; (C||D)
    left = concat_parallel([A[0], B[0]])
    right = concat_parallel([C[0], D[0]])
    cases.append(('mixed_ser_of_par', concat_serial([left, right]),
                  max(A[1], B[1]) + max(C[1], D[1])))
    return cases


def summarize_corpus(rows):
    for tag in ('base', 'pert', 'stress'):
        rs = [r for r in rows if r['corpus'] == tag]
        print(tag, len(rs), 'ok', sum(r['ok'] for r in rs),
              'cert', sum(r['certified'] for r in rs),
              'q', sum(r['probes'] for r in rs),
              'lp', sum(r['pact_lp'] for r in rs),
              't', round(sum(r['t'] for r in rs), 2))
    print('all', len(rows), 'ok', sum(r['ok'] for r in rows),
          'cert', sum(r['certified'] for r in rows),
          'q', sum(r['probes'] for r in rows),
          'lp', sum(r['pact_lp'] for r in rows),
          't', round(sum(r['t'] for r in rows), 2))
    print('leaves/series/parallel',
          sum(r['leaves'] for r in rows),
          sum(r['series'] for r in rows),
          sum(r['parallel'] for r in rows))
    print('kinds', dict(collections.Counter(r['tree_kind']
                                            for r in rows)))


def main():
    rows = corpus_rows()
    out = {'corpus_auto': [], 'corpus_full': [], 'composed': []}
    t0 = time.time()
    for auto in (True, False):
        key = 'corpus_auto' if auto else 'corpus_full'
        for c, (tag, name, idx, inst, known) in enumerate(rows):
            r = run_dip(inst, known, name, idx, auto=auto)
            r.pop('root', None)
            r['corpus'] = tag
            out[key].append(r)
        print('\n== corpus auto=%s wall %.2f' % (auto,
                                                 time.time() - t0))
        summarize_corpus(out[key])
        with open('exp/v10d/bench_dip_%s.json' %
                  ('auto' if auto else 'full'), 'w') as f:
            json.dump(out[key], f, indent=1)

    cases = make_cases(rows)
    for tag, ci, known in cases:
        plan = build_tree(ci, auto=True)
        full = build_tree(ci, auto=False)
        row = dict(case=tag, n=ci['n'], m=ci['m'], known=known,
                   auto_tree=plan['kind'], full_tree=full['kind'],
                   auto_ratio=round(plan_cost(plan) /
                                    plan_cost(dict(kind='leaf',
                                                   inst=ci)), 4),
                   full_ratio=round(plan_cost(full) /
                                    plan_cost(dict(kind='leaf',
                                                   inst=ci)), 4))
        t = time.time()
        ra = run_dip(ci, known, tag, 0, auto=True)
        ra.pop('root', None)
        row['dip_auto'] = dict(opt=ra['opt'], lb=ra['lb'],
                               certified=ra['certified'],
                               audit=ra['audit'], ok=ra['ok'],
                               probes=ra['probes'],
                               lp=ra['pact_lp'],
                               t=round(time.time() - t, 3),
                               leaves=ra['leaves'],
                               series=ra['series'],
                               parallel=ra['parallel'])
        t = time.time()
        rf = run_dip(ci, known, tag, 0, auto=False)
        rf.pop('root', None)
        row['dip_full'] = dict(opt=rf['opt'], lb=rf['lb'],
                               certified=rf['certified'],
                               audit=rf['audit'], ok=rf['ok'],
                               probes=rf['probes'],
                               lp=rf['pact_lp'],
                               t=round(time.time() - t, 3),
                               leaves=rf['leaves'],
                               series=rf['series'],
                               parallel=rf['parallel'])
        rm = run_mono(ci, known, tag, 0, cap=30.0)
        row['icf'] = dict(status=rm.get('status'),
                          opt=rm.get('opt'), lb=rm.get('lb'),
                          certified=rm.get('certified', False),
                          audit=rm.get('audit', False),
                          ok=rm.get('ok', False),
                          queries=rm.get('queries', 0),
                          lp=rm.get('pact_lp', 0),
                          t=rm.get('t'))
        out['composed'].append(row)
        print('\n==', tag, 'n', ci['n'], 'm', ci['m'],
              'known', known, 'trees', plan['kind'], full['kind'])
        print('  DIP auto ', row['dip_auto'])
        print('  DIP full ', row['dip_full'])
        print('  ICF      ', row['icf'], flush=True)

    with open('exp/v10d/bench_dip_composed.json', 'w') as f:
        json.dump(out, f, indent=1)
    print('\nwall', round(time.time() - t0, 2))


if __name__ == '__main__':
    main()
