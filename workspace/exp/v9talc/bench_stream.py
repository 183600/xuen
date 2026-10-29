import sys
import json
import time
import collections

sys.path[:0] = ['exp/v9talc', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from loose import rows
from pact import pact_decide
from sage import _domain
from talc import (StreamProof, compare_space, branch_space,
                  allowed_times, cmax)


def corpus_replay():
    out = []
    t0 = time.time()
    for tag, name, idx, inst, known in rows():
        r = pact_decide(inst, known - 1, depthcap=None, nodecap=None)
        if r['verdict'] is not False:
            out.append(dict(corpus=tag, name=name, idx=idx,
                            verdict=r['verdict']))
            continue
        p = r['proof']
        old, new, sp = compare_space(p)
        out.append(dict(corpus=tag, name=name, idx=idx, verdict=False,
                        n=inst['n'], m=inst['m'], h=known - 1,
                        old=old, new=new))
    path = 'exp/v9talc/stream_replay.json'
    with open(path, 'w') as f:
        json.dump(out, f)
    ok = [r for r in out if r.get('verdict') is False]
    print('instances', len(out), 'NO', len(ok),
          'stream_audit', sum(r['new']['ok'] for r in ok),
          'elapsed', round(time.time() - t0, 2))
    print('stored_forbid', sum(r['old']['stored_forbid'] for r in ok),
          '->', sum(r['new']['stored_forbid'] for r in ok))
    print('peak_path_forbid', sum(r['old']['peak_path_forbid'] for r in ok),
          '->', sum(r['new']['peak_forbid'] for r in ok))
    print('events', sum(r['new']['events'] for r in ok),
          'cert_entries', sum(r['new']['cert_entries'] for r in ok))
    return out


def synth_stream(inst, h, cert, base_F, depth):
    """Build a deliberately deep but valid NO tree by redundant splits.

    Every leaf reuses a Farkas certificate from a sub-box of base_F.  A
    certificate valid for F stays valid for any superset, so arbitrary
    redundant splits preserve soundness.  This is a space-scaling
    microbenchmark, not a search result.
    """
    materialized = [0]
    cert_calls = [0]

    def build(F, d):
        if d == 0:
            materialized[0] += len(F)
            return ('leaf', cert)
        best = None
        for i in range(inst['n']):
            ts = allowed_times(inst, h, i, F)
            if len(ts) >= 2 and (best is None or len(ts) > best[0]):
                best = (len(ts), i, ts)
        if best is None:
            materialized[0] += len(F)
            return ('leaf', cert)
        _, i, times = best
        mid = times[len(times) // 2 - 1]
        lo_t = [t for t in times if t > mid]
        hi_t = [t for t in times if t <= mid]
        materialized[0] += len(F)
        loF = F | {(i, t) for t in lo_t}
        hiF = F | {(i, t) for t in hi_t}
        return ('split', i, mid, build(loF, d - 1), build(hiF, d - 1))

    tree = build(base_F, depth)
    events = []

    def walk(node):
        if node[0] == 'leaf':
            events.append(('leaf', node[1]))
            return
        events.append(('split', node[1], node[2]))
        walk(node[3])
        walk(node[4])

    walk(tree)
    sp = StreamProof(inst, h, events, forbid0=base_F)
    ok = sp.audit_rdf()
    sp.stats['materialized_stored'] = materialized[0]
    sp.stats['leaves'] = 1 << depth
    return sp, ok


def synthetic_scaling():
    target = None
    for tag, name, idx, inst, known in rows():
        if name == 'large_a' and idx == 2:
            target = (inst, known)
            break
    inst, known = target
    r = pact_decide(inst, known - 1, depthcap=None, nodecap=None)
    p = r['proof']
    node = p.tree
    while node[0] not in ('leaf', 'empty'):
        node = node[4]
    cert = node[2]
    base_F = frozenset(node[1]) if node[0] == 'leaf' else frozenset()
    out = []
    for d in (2, 4, 6, 8, 10):
        sp, ok = synth_stream(inst, known - 1, cert, base_F, d)
        st = sp.stats
        out.append(dict(depth=d, ok=ok, events=st['events'],
                        leaves=st['leaves'],
                        peak_forbid=st['peak_forbid'],
                        materialized_stored=st['materialized_stored'],
                        cert_entries=st['cert_entries'],
                        splits=st['splits']))
        print('depth', d, 'ok', ok, 'events', st['events'],
              'peak', st['peak_forbid'],
              'mat_stored', st['materialized_stored'], flush=True)
    with open('exp/v9talc/stream_scaling.json', 'w') as f:
        json.dump(out, f, indent=1)
    return out


if __name__ == '__main__':
    corpus_replay()
    synthetic_scaling()
