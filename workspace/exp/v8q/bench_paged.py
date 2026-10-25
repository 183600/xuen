"""Measure PAGE-ALC's compact proof and one-pass external-memory audit.

Data:
  * 58 NO probes (closed residual proofs),
  * 252 YES probes (the search tree that reaches the first YES),
  * 58 x budgets 1..9 (open residual frontier certificates).

The F-carrying encoding is a logical wire format with the forbidden set
at every node, i.e. the information the PACT/R-ACT proof tree stores.
The compact encoding stores only split decisions and leaf payloads.
"""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v8q', 'exp/v8p', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from residual import decide, ResidualProof
from paged import encode_compact, encode_fbased, audit_compact


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


def tree_stats(node):
    """(nodes, leaves, height, F pairs, splits, cert bytes)."""
    if node.tag == 'node':
        a = tree_stats(node.children[0])
        b = tree_stats(node.children[1])
        return (1 + a[0] + b[0], a[1] + b[1], 1 + max(a[2], b[2]),
                len(node.F) + a[3] + b[3], 1 + a[4] + b[4],
                a[5] + b[5])
    cert = 0
    if node.tag == 'leaf':
        from paged import _cert_bytes
        cert = len(_cert_bytes(node.cert))
    return (1, 1, 0, len(node.F), 0, cert)


def one(inst, h, label, tag, name, idx, known, budget=None, uid=None):
    r = decide(inst, h, nodecap=budget)
    root = r['root']
    if root is None:
        return None
    nodes, leaves, height, fpair, splits, certb = tree_stats(root)
    cb = encode_compact(root, inst, h)
    fb = encode_fbased(root, inst, h)
    out = dict(uid=uid, tag=tag, name=name, idx=idx, known=known, label=label,
               h=h, budget=budget, verdict=r['verdict'],
               nodes=nodes, leaves=leaves, height=height,
               fpair=fpair, splits=splits, cert_bytes=certb,
               compact_bytes=len(cb), fbased_bytes=len(fb),
               compact_node_bytes=4 * splits + len(
                   [1 for x in [root] if x.tag in ('open', 'leaf', 'empty',
                                                   'yes', 'bound')]),
               lp=r['lp_solves'], cert_lp=r['cert_lp'])
    # compact audit at several block sizes
    aud = {}
    for B in (64, 256, 1024):
        a = audit_compact(inst, h, data=cb, block=B)
        aud[str(B)] = dict(ok=a['ok'], L=a['L'], U=a['U'],
                           max_stack=a['max_stack'], reads=a['reads'],
                           bytes=a['bytes'], t=round(a['t'], 6),
                           ledger=a['ledger'],
                           reason=a['reason'])
    out['audit'] = aud
    # recursive audit of the same tree (if wrapped as a Proof)
    if r['verdict'] is not None or root.tag != 'yes':
        p = r['proof']
        if p is None:
            p = ResidualProof(inst, h, root)
        t0 = time.time()
        out['rec_ok'] = bool(p.audit_rdf())
        out['t_rec'] = round(time.time() - t0, 6)
        out['ledger'] = (dict(p.ledger) if getattr(p, 'ledger', None)
                         else None)
    else:
        t0 = time.time()
        p = ResidualProof(inst, h, root)
        out['rec_ok'] = bool(p.audit_rdf())
        out['t_rec'] = round(time.time() - t0, 6)
        out['ledger'] = dict(p.ledger or {})
    return out


def main():
    probe_rows = json.load(open('exp/v8p/bench_pact_r.json'))
    by_uid = {r.get('uid'): r for r in probe_rows}
    inst_by_uid = {}
    out = []
    t0 = time.time()
    for k, (tag, name, idx, inst, known) in enumerate(corpora()):
        inst_by_uid[k] = (tag, name, idx, inst, known)
        row = by_uid.get(k)
        # NO probes: every logged probe with v=False
        if row is not None:
            for p in row.get('probe_log') or []:
                if p.get('v') is False:
                    x = one(inst, p['h'], 'NO', tag, name, idx, known,
                            uid=k)
                    if x is not None:
                        out.append(x)
        # YES probes: partial residual trees (schedule-only YES has no tree)
        for b in range(1, 9):
            x = one(inst, known, 'YESOPEN', tag, name, idx, known,
                    budget=b, uid=k)
            if x is not None and (x['verdict'] is None
                                  or x['splits'] > 0):
                out.append(x)
        if k % 40 == 0:
            print(k, round(time.time() - t0, 1), flush=True)
    # budgeted residuals for the 58 NO probes
    no_rows = [r for r in out if r['label'] == 'NO']
    for r in no_rows:
        tag, name, idx, inst, known = inst_by_uid[r['uid']]
        for b in range(1, 10):
            x = one(inst, r['h'], 'OPEN', tag, name, idx, known,
                    budget=b, uid=r['uid'])
            if x is not None:
                out.append(x)
    wall = round(time.time() - t0, 2)
    json.dump(dict(rows=out, wall=wall), open('exp/v8q/bench_paged.json', 'w'),
              indent=1)
    print('wall', wall, 'rows', len(out))
    for lab in ('NO', 'YESOPEN', 'OPEN'):
        rs = [r for r in out if r['label'] == lab]
        if not rs:
            continue
        print('\n==', lab, len(rs))
        print('nodes', sum(r['nodes'] for r in rs),
              'leaves', sum(r['leaves'] for r in rs),
              'height_max', max(r['height'] for r in rs),
              'fpair', sum(r['fpair'] for r in rs),
              'splits', sum(r['splits'] for r in rs))
        print('compact', sum(r['compact_bytes'] for r in rs),
              'fbased', sum(r['fbased_bytes'] for r in rs),
              'cert', sum(r['cert_bytes'] for r in rs),
              'ratio', round(sum(r['fbased_bytes'] for r in rs) /
                             max(1, sum(r['compact_bytes'] for r in rs)), 3))
        print('state_compact', sum(4 * r['splits'] + 2 * r['leaves']
                                   for r in rs),
              'state_fbased', sum(4 * r['fpair'] + 8 * r['nodes']
                                  for r in rs),
              'state_ratio', round(sum(4 * r['fpair'] + 8 * r['nodes']
                                       for r in rs) /
                                   max(1, sum(4 * r['splits'] + 2 * r['leaves']
                                              for r in rs)), 3))
        for B in ('64', '256', '1024'):
            print(' B', B, 'ok', sum(r['audit'][B]['ok'] for r in rs),
                  'reads', sum(r['audit'][B]['reads'] for r in rs),
                  'stack_max', max(r['audit'][B]['max_stack'] for r in rs),
                  't_stream', round(sum(r['audit'][B]['t'] for r in rs), 3))
        print(' rec_ok', sum(r['rec_ok'] for r in rs),
              't_rec', round(sum(r['t_rec'] for r in rs), 3),
              't_stream', round(sum(r['audit']['256']['t'] for r in rs), 3))
        print(' verdicts', collections.Counter(str(r['verdict']) for r in rs))
        print(' ledgers_match', sum(
            1 for r in rs if r['ledger'] is not None
            and r['audit']['256']['ledger'] == r['ledger']), '/', len(rs))


if __name__ == '__main__':
    main()
