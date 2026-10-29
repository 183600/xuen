"""Benchmark DFR-ICF round policies on the 252 and weak-160 corpora."""
import collections
import json
import sys
import time

sys.path[:0] = ['exp/v9dfr', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from dfr import run_dfr, corpora
from hap import weak_rows


POLICIES = ('seq-lower-first', 'seq-binary', 'par:2', 'par:3', 'par:4',
            'par:8', 'adaptive-work', 'adaptive-round', 'adaptive-mix')


def normal_rows():
    for corpus, name, idx, inst, known in corpora():
        yield corpus, name, idx, inst, known, None


def weak160_rows():
    for corpus, name, idx, inst, known, initial in weak_rows(4):
        yield corpus, name, idx, inst, known, initial


def summarize(tag, policy, rows):
    n = len(rows)
    ok = sum(bool(r.get('ok')) for r in rows)
    cert = sum(bool(r.get('certified')) for r in rows)
    probes = sum(r.get('probes', 0) for r in rows)
    rounds = sum(r.get('rounds', 0) for r in rows)
    lp = sum(r.get('pact_lp', 0) for r in rows)
    cert_lp = sum(r.get('pact_cert_lp', 0) for r in rows)
    pf = sum(r.get('partial_fail', 0) for r in rows)
    pk = sum(r.get('partial_ok', 0) for r in rows)
    unknown = sum(r.get('unknown', 0) for r in rows)
    t = sum(r.get('t', 0.0) for r in rows)
    gaps = [r['gap0'] for r in rows if r.get('gap0', 0) > 0]
    ratio = (sum(r['probes'] for r in rows if r.get('gap0', 0) > 0) /
             sum(r['gap0'] for r in rows if r.get('gap0', 0) > 0)
             if gaps else 0.0)
    stored = sum(sum(r.get('batch_sizes', [])) for r in rows)
    it = {
        'tag': tag, 'policy': policy, 'n': n, 'ok': ok, 'certified': cert,
        'probes': probes, 'rounds': rounds, 'lp': lp,
        'cert_lp': cert_lp, 'partial_ok': pk, 'partial_fail': pf,
        'unknown': unknown, 't': round(t, 3),
        'probe_per_gap': round(ratio, 4),
        'stored_facts': stored,
    }
    print('%-8s %-16s n=%3d ok=%3d cert=%3d probes=%4d rounds=%4d '
          'lp=%5d certlp=%4d pf=%d unk=%d t=%.2f ratio=%.3f'
          % (tag, policy, n, ok, cert, probes, rounds, lp, cert_lp,
             pf, unknown, t, ratio))
    return it


def run_all(kind, policies=POLICIES, limit=None, path=None):
    rows = list(normal_rows() if kind == 'normal' else weak160_rows())
    if limit:
        rows = rows[:limit]
    out = []
    summary = []
    for pol in policies:
        t0 = time.time()
        rs = []
        for i, (corpus, name, idx, inst, known, initial) in enumerate(rows):
            r = run_dfr(inst, known, name, idx, policy=pol,
                        initial=initial, collect_facts=False)
            r['corpus'] = corpus
            rs.append(r)
        summary.append(summarize(kind, pol, rs))
        out.extend(rs)
        print('  wall %.2fs' % (time.time() - t0))
        if path:
            with open(path % (kind, pol.replace(':', '')), 'w') as f:
                json.dump(rs, f, indent=1)
    return out, summary


if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'weak'
    if which in ('weak', 'both'):
        run_all('weak', path='exp/v9dfr/bench_%s_%s.json')
    if which in ('normal', 'both'):
        run_all('normal', path='exp/v9dfr/bench_%s_%s.json')
