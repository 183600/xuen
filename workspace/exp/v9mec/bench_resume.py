"""Budget-doubling residual convergence and paged one-pass audit.

For every gap case we solve the NO(h=OPT-1) decision with

  * a complete residual search (baseline K LP nodes);
  * a geometric restart-free schedule: nodecap=1,2,4,... on the same
    residual tree, using residual.resume_proof;

then serialize the final tree with PAGE-ALC's compact stream and audit
it with a block reader.  The point is to measure the convergence rate of
the budget and the external-memory audit, not to claim a speedup on a
tiny corpus.
"""
import sys
import json
import time

sys.path[:0] = ['exp/v9mec', 'exp/v8q', 'exp/v8p', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from residual import decide, resume_proof
from paged import encode_compact, audit_compact
from bench_paged import tree_stats


def complete(inst, h):
    t0 = time.time()
    r = decide(inst, h, nodecap=None)
    return r, time.time() - t0


def doubling(inst, h, max_phases=40):
    t0 = time.time()
    b = 1
    total_lp = total_cert = total_nodes = 0
    proof = None
    phases = []
    while True:
        if proof is None:
            r = decide(inst, h, nodecap=b)
        else:
            r = resume_proof(inst, h, proof, nodecap=b)
        total_lp += r.get('lp_solves', 0)
        total_cert += r.get('cert_lp', 0)
        total_nodes += r.get('nodes', 0)
        phases.append(dict(b=b, verdict=r['verdict'],
                           lp=r.get('lp_solves', 0),
                           cert=r.get('cert_lp', 0),
                           holes=r.get('new_holes')))
        if r['verdict'] is not None:
            proof = r['proof']
            break
        proof = r['proof']
        b *= 2
        if len(phases) >= max_phases:
            break
    return dict(phases=phases, total_lp=total_lp,
                total_cert=total_cert, total_nodes=total_nodes,
                proof=proof, t=time.time() - t0)


def main():
    cases = json.load(open('exp/v10c/gap_cases.json'))
    rows = []
    for d in cases:
        inst, h = d['inst'], int(d['opt']) - 1
        c, tc = complete(inst, h)
        g = doubling(inst, h)
        root = c['root']
        stats = tree_stats(root)
        cb = encode_compact(root, inst, h)
        aud = {}
        for B in (64, 256, 1024):
            a = audit_compact(inst, h, data=cb, block=B)
            aud[str(B)] = dict(ok=a['ok'], reads=a['reads'],
                               bytes=a['bytes'], max_stack=a['max_stack'],
                               t=round(a['t'], 6))
        rec_ok = bool(c['proof'] is not None and
                      c['proof'].audit_rdf())
        d_ok = bool(g['proof'] is not None and
                    g['proof'].audit_rdf())
        row = dict(case=d['case'], src=d['src'], kind=d['kind'],
                   opt=d['opt'], h=h, nodes=stats[0], leaves=stats[1],
                   height=stats[2], splits=stats[4],
                   complete_lp=c['lp_solves'],
                   complete_cert=c['cert_lp'],
                   complete_t=round(tc, 4), rec_ok=rec_ok,
                   phases=len(g['phases']), phase_rows=g['phases'],
                   double_lp=g['total_lp'],
                   double_cert=g['total_cert'],
                   double_t=round(g['t'], 4), double_ok=d_ok,
                   compact_bytes=len(cb), audit=aud)
        rows.append(row)
        print(d['case'], 'K', stats[0], 'compLP', c['lp_solves'],
              'phases', len(g['phases']), 'doubleLP', g['total_lp'],
              'bytes', len(cb), 'rec', rec_ok, 'dbl', d_ok, flush=True)
    json.dump(rows, open('exp/v9mec/bench_resume.json', 'w'), indent=1)
    print('\n== summary')
    print('cases', len(rows), 'rec_ok', sum(r['rec_ok'] for r in rows),
          'double_ok', sum(r['double_ok'] for r in rows))
    print('completeLP', sum(r['complete_lp'] for r in rows),
          'doubleLP', sum(r['double_lp'] for r in rows),
          'ratio', round(sum(r['double_lp'] for r in rows) /
                         max(1, sum(r['complete_lp'] for r in rows)), 3))
    print('phases max', max(r['phases'] for r in rows),
          'mean', round(sum(r['phases'] for r in rows) / len(rows), 2))
    print('compact_bytes', sum(r['compact_bytes'] for r in rows))
    for B in ('64', '256', '1024'):
        print(' B', B, 'ok', sum(r['audit'][B]['ok'] for r in rows),
              'reads', sum(r['audit'][B]['reads'] for r in rows),
              'stackmax', max(r['audit'][B]['max_stack'] for r in rows))


if __name__ == '__main__':
    main()
