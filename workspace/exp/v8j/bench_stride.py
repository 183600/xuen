"""Benchmark v8.9 STRIDE-ALC: full corpus, latency sweep, stream audit."""
import copy
import json
import sys
import time
import collections
import random

sys.path[:0] = ['exp/v8j', 'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e',
                'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from stride import (STRIDE, StreamBranch, BoxProof, stream_events,
                    verify_stream, MonotoneStore, box_forbidden)
from sage import SAGE, run, lp_branch_decide
from po import heads_tails


def corpora():
    for tag, rows in (('base', base_corpus()),
                      ('pert', pert_corpus()),
                      ('stress', stress_corpus())):
        for row in rows:
            if len(row) == 4:
                name, idx, inst, known = row
            else:
                idx, known, inst = row
                name = tag
            yield tag, name, idx, inst, known


def summarize(rows):
    return dict(
        n=len(rows),
        ok=sum(bool(r['ok']) for r in rows),
        cert=sum(bool(r['certified']) for r in rows),
        q=sum(r['queries'] for r in rows),
        lpchd=sum(r['lp'] for r in rows),
        pin=sum(r['pin_lp'] for r in rows),
        bb=sum(r['bb_lp'] for r in rows),
        certlp=sum(r['cert_lp'] for r in rows),
        yn=sum(r['yes_nodes'] for r in rows),
        t=round(sum(r['t'] for r in rows), 2),
        bbyes=sum(r['stats2'].get('bb_yes', 0) for r in rows),
        bbno=sum(r['stats2'].get('bb_no', 0) for r in rows),
        bbopen=sum(r['stats2'].get('bb_open', 0) for r in rows),
        gayes=sum(r['stats2'].get('ga_yes', 0) for r in rows),
        gano=sum(r['stats2'].get('ga_no', 0) for r in rows),
        chd=sum(r['stats2'].get('chd_fallback', 0) for r in rows),
        holes=sum(r['stats2'].get('bb_holes', 0) for r in rows),
        rounds=sum(r['stats2'].get('bb_rounds', 0) for r in rows),
        maxfront=max((r['stats2'].get('bb_max_frontier', 0)
                      for r in rows), default=0),
        qpos=sum(1 for r in rows if r['queries'] > 0),
    )


def run_all(cls, tag, cases, **kw):
    rows = []
    t0 = time.time()
    for corpus, name, idx, inst, known in cases:
        r = run(cls, inst, known, name, idx, **kw)
        r['corpus'] = corpus
        rows.append(r)
    wall = round(time.time() - t0, 2)
    with open('/tmp/stride_%s.json' % tag, 'w') as f:
        json.dump(rows, f, indent=1)
    with open('exp/v8j/bench_stride_%s.json' % tag, 'w') as f:
        json.dump(rows, f, indent=1)
    print('\n==', tag, '== wall', wall, summarize(rows))
    for c in ('base', 'pert', 'stress'):
        rs = [r for r in rows if r['corpus'] == c]
        print(' ', c, summarize(rs))
    print(' kinds', dict(collections.Counter(
        r['proof_kind'] for r in rows)))
    return rows


def stream_audit(cases, rows):
    branch = {(r['corpus'], r['name'], r['idx'])
              for r in rows if r['proof_kind'] == 'branch'}
    out = []
    tamper = collections.Counter()
    for corpus, name, idx, inst, known in cases:
        if (corpus, name, idx) not in branch:
            continue
        sb = StreamBranch(inst, known - 1, nodecap=96, depthcap=24)
        while True:
            st = sb.run(1)
            if st != 'paused':
                break
        if st != 'no':
            out.append(dict(corpus=corpus, name=name, idx=idx,
                            status=st))
            continue
        bp = BoxProof(inst, known - 1, sb.final,
                      sb.root_lo, sb.root_hi)
        ev = list(stream_events(sb.final))
        ok, stack, mx = verify_stream(inst, known - 1, ev,
                                      sb.root_lo, sb.root_hi)
        rec = dict(corpus=corpus, name=name, idx=idx,
                   status='ok' if (ok and bp.audit_rdf()) else 'bad',
                   events=len(ev), max_stack=mx,
                   nodes=sb.nodes, leaves=sb.leaves,
                   cert_lp=sb.cert_lp)
        out.append(rec)
        if not ok or not bp.audit_rdf():
            tamper['base_reject'] += 1
            continue
        # structural tamper: shift the first split midpoint
        ev2 = copy.deepcopy(ev)
        for k, e in enumerate(ev2):
            if e[0] == 'split':
                ev2[k] = ('split', e[1], e[2] + 1)
                break
        ok2, _, _ = verify_stream(inst, known - 1, ev2,
                                  sb.root_lo, sb.root_hi)
        tamper['mid_reject' if not ok2 else 'mid_accept'] += 1
        # truncation
        ok3, _, _ = verify_stream(inst, known - 1, ev[:-1],
                                  sb.root_lo, sb.root_hi)
        tamper['trunc_reject' if not ok3 else 'trunc_accept'] += 1
        # leaf certificate tamper
        ev4 = copy.deepcopy(ev)
        for k, e in enumerate(ev4):
            if e[0] == 'leaf':
                c = ev4[k][3]
                if c.get('alpha'):
                    c['alpha'][0] += 1
                else:
                    c['scale'] = c.get('scale', 1) + 1
                break
        ok4, _, _ = verify_stream(inst, known - 1, ev4,
                                  sb.root_lo, sb.root_hi)
        tamper['cert_reject' if not ok4 else 'cert_accept'] += 1
    with open('exp/v8j/bench_stride_stream.json', 'w') as f:
        json.dump(dict(proofs=out, tamper=dict(tamper)), f, indent=1)
    print('\n== stream audit ==', len(out),
          'ok', sum(1 for r in out if r['status'] == 'ok'),
          'events', sum(r.get('events', 0) for r in out),
          'max_stack', max((r.get('max_stack', 0) for r in out),
                           default=0),
          'tamper', dict(tamper))
    return out, tamper


def _box_from_F(inst, h, F):
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    lo, hi = [], []
    for i in range(n):
        last = h - q[i] - inst['p'][i]
        allowed = [t for t in range(est[i], last + 1)
                   if (i, t) not in F]
        if not allowed:
            lo.append(1)
            hi.append(0)
        else:
            if any((i, t) in F for t in range(min(allowed),
                                             max(allowed) + 1)):
                return None
            lo.append(min(allowed))
            hi.append(max(allowed))
    return lo, hi


def _convert_tree(inst, h, tree):
    tag = tree[0]
    if tag == 'leaf':
        b = _box_from_F(inst, h, tree[1])
        return ('leaf', b[0], b[1], tree[2])
    if tag == 'empty':
        b = _box_from_F(inst, h, tree[1])
        return ('empty', b[0], b[1], tree[2])
    if tag == 'node':
        _, i, mid, F, left, right = tree
        b = _box_from_F(inst, h, F)
        return ('no', i, mid, b[0], b[1],
                _convert_tree(inst, h, left),
                _convert_tree(inst, h, right))
    raise ValueError(tag)


def stream_audit_sage(cases, rows):
    branch = {(r['corpus'], r['name'], r['idx'])
              for r in rows if r['proof_kind'] == 'branch'}
    out = []
    for corpus, name, idx, inst, known in cases:
        if (corpus, name, idx) not in branch:
            continue
        r = lp_branch_decide(inst, known - 1, nodecap=96, depthcap=24)
        if r['verdict'] is not False:
            out.append(dict(corpus=corpus, name=name, idx=idx,
                            status='not-no'))
            continue
        tree = _convert_tree(inst, known - 1, r['proof'].tree)
        root = _box_from_F(inst, known - 1, frozenset())
        bp = BoxProof(inst, known - 1, tree, root[0], root[1])
        ev = list(stream_events(tree))
        ok, stack, mx = verify_stream(inst, known - 1, ev,
                                      root[0], root[1])
        out.append(dict(corpus=corpus, name=name, idx=idx,
                        status='ok' if (ok and bp.audit_rdf()) else 'bad',
                        events=len(ev), max_stack=mx))
    with open('exp/v8j/bench_stride_stream_sage.json', 'w') as f:
        json.dump(out, f, indent=1)
    print('\n== stream audit (SAGE BranchProof converted) ==',
          len(out), 'ok', sum(1 for r in out if r['status'] == 'ok'),
          'events', sum(r.get('events', 0) for r in out),
          'max_stack', max((r.get('max_stack', 0) for r in out),
                           default=0))
    return out


def case_study():
    inst = None
    for corpus, name, idx, x, known in corpora():
        if name == 'large_het' and idx == 7:
            inst, known = x, known
            break
    rec = dict(name='large_het 7', known=known)
    for label, h in (('no_side', known - 1), ('yes_side', known)):
        sage = lp_branch_decide(inst, h, nodecap=96, depthcap=24)
        sb = StreamBranch(inst, h, nodecap=96, depthcap=24)
        while True:
            st = sb.run(1)
            if st != 'paused':
                break
        rec[label] = dict(
            h=h,
            sage=dict(verdict=sage['verdict'], nodes=sage['nodes'],
                      leaves=sage['leaves'],
                      branch_jobs=sage['branch_jobs'],
                      unknown=sage['unknown']),
            stride=dict(verdict=st, nodes=sb.nodes, leaves=sb.leaves,
                        branch_jobs=sb.branch_jobs,
                        holes=[r for _, _, r in sb.holes]),
        )
    with open('exp/v8j/bench_stride_case.json', 'w') as f:
        json.dump(rec, f, indent=1)
    print('\n== case ==', rec)
    return rec


def strict_cap(cases):
    out = {}
    for C in (1, 2, 4, 8):
        rows = []
        for corpus, name, idx, inst, known in cases:
            r = run(STRIDE, inst, known, name, idx,
                    round_budget=1, bb_total_nodecap=C,
                    bb_depthcap=24)
            r['corpus'] = corpus
            rows.append(r)
        out[C] = summarize(rows)
        print('\n== strict total cap', C, '==', out[C])
    with open('exp/v8j/bench_stride_strict.json', 'w') as f:
        json.dump(out, f, indent=1)
    return out


def monotone_micro():
    rng = random.Random(7)
    out = []
    for N in (1000, 10000, 100000):
        store = MonotoneStore()
        for h in range(N):
            store.add(type('P', (), {'h': h})())
        qs = [rng.randrange(N) for _ in range(20000)]
        t0 = time.time()
        for q in qs:
            store.stronger(q)
        t1 = time.time()
        by_h = store.by_h
        t2 = time.time()
        for q in qs[:2000]:
            best = None
            for h in by_h:
                if h >= q and (best is None or h < best):
                    best = h
        t3 = time.time()
        out.append(dict(N=N,
                        stride_us=round((t1 - t0) / len(qs) * 1e6, 4),
                        scan_us=round((t3 - t2) / 2000 * 1e6, 2),
                        scans=2000))
    with open('exp/v8j/bench_stride_monotone.json', 'w') as f:
        json.dump(out, f, indent=1)
    print('\n== monotone store ==', out)
    return out


if __name__ == '__main__':
    cases = list(corpora())
    sage_rows = run_all(SAGE, 'sage_full', cases,
                        bb_nodecap=96, bb_depthcap=24)
    stride_rows = run_all(STRIDE, 'full', cases,
                          round_budget=1, bb_total_nodecap=96,
                          bb_depthcap=24)
    summary = {}
    for C in (1, 2, 4, 8):
        sr = run_all(SAGE, 'sage_c%d' % C, cases,
                     bb_nodecap=C, bb_depthcap=24)
        tr = run_all(STRIDE, 'stride_c%d' % C, cases,
                     round_budget=C, bb_total_nodecap=96,
                     bb_depthcap=24)
        summary[C] = dict(sage=summarize(sr), stride=summarize(tr))
    with open('exp/v8j/bench_stride_sweep.json', 'w') as f:
        json.dump(summary, f, indent=1)
    stream_audit(cases, stride_rows)
    stream_audit_sage(cases, sage_rows)
    case_study()
    strict_cap(cases)
    monotone_micro()
