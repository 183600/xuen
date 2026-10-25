"""Measure the one-pass residual audit and the exact frontier identity."""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v8p', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from residual import decide
from stream_audit import audit_stream


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


def no_probes(main):
    for k, (tag, name, idx, inst, known) in enumerate(corpora()):
        for p in main[k]['probe_log']:
            if p['v'] is False:
                yield k, tag, name, idx, inst, known, p['h']


def main():
    main_rows = json.load(open('exp/v8p/bench_pact_r.json'))
    out = []
    agg = collections.Counter()
    for uid, tag, name, idx, inst, known, h in no_probes(main_rows):
        for B in (None, 1, 2, 3, 4, 5, 6, 8, 9):
            r = decide(inst, h, nodecap=B)
            p = r['proof']
            if p is None:
                continue
            t0 = time.time()
            ok_rec = p.audit_rdf()
            t_rec = time.time() - t0
            t0 = time.time()
            ok_st, led, mx, ne = audit_stream(inst, h, p.root, p.ledger)
            t_st = time.time() - t0
            L = p.ledger
            W = L.get('closed_leaves', 0) + L.get('open_leaves', 0)
            identity = (L.get('nodes') == 2 * W - 1)
            rec = dict(uid=uid, corpus=tag, name=name, idx=idx, known=known,
                       h=h, budget=B, verdict=r['verdict'],
                       nodes=L.get('nodes'), lp=L.get('lp'),
                       cert_lp=L.get('cert_lp'), closed=L.get('closed_leaves'),
                       open=L.get('open_leaves'), W=W,
                       height=L.get('height'), identity=identity,
                       audit_rec=ok_rec, audit_stream=ok_st,
                       ledger_match=(led == p.ledger),
                       max_stack=mx, events=ne,
                       t_rec=round(t_rec, 6), t_stream=round(t_st, 6))
            out.append(rec)
            agg['n'] += 1
            agg['rec_ok'] += int(ok_rec)
            agg['stream_ok'] += int(ok_st)
            agg['ledger_ok'] += int(led == p.ledger)
            agg['identity'] += int(identity)
            agg['events'] += ne
            agg['max_stack'] = max(agg['max_stack'], mx)
            agg['t_rec'] += t_rec
            agg['t_stream'] += t_st
            if B is None:
                agg['closed'] += int(r['verdict'] is False)
                agg['residual'] += int(r['verdict'] is None)
    # tamper tests on one non-trivial closed proof
    tamper = []
    picked = None
    for uid, tag, name, idx, inst, known, h in no_probes(main_rows):
        p = decide(inst, h)['proof']
        if p.ledger.get('closed_leaves', 0) >= 2:
            picked = (inst, h, p)
            break
    if picked is not None:
        inst, h, p = picked
        ok, _, _, _ = audit_stream(inst, h, p.root, p.ledger)
        tamper.append(dict(mutation='none', result=ok))
        old = p.ledger['nodes']
        p.ledger['nodes'] = old + 1
        ok, _, _, _ = audit_stream(inst, h, p.root, p.ledger)
        tamper.append(dict(mutation='ledger-nodes+1', result=ok))
        p.ledger['nodes'] = old
        leaf = None
        def walk(n):
            nonlocal leaf
            if leaf is not None:
                return
            if n.tag == 'leaf':
                leaf = n
            elif n.tag == 'node':
                walk(n.children[0])
                walk(n.children[1])
        walk(p.root)
        if leaf is not None:
            old_kind = leaf.cert.get('kind')
            leaf.cert['kind'] = 'empty'
            ok, _, _, _ = audit_stream(inst, h, p.root, p.ledger)
            tamper.append(dict(mutation='leaf-kind', result=ok))
            leaf.cert['kind'] = old_kind
        node = p.root
        while node.tag == 'node' and node.children[0].tag == 'node':
            node = node.children[0]
        if node.tag == 'node':
            old_mid = node.mid
            node.mid = old_mid + 1
            ok, _, _, _ = audit_stream(inst, h, p.root, p.ledger)
            tamper.append(dict(mutation='split-mid+1', result=ok))
            node.mid = old_mid
    with open('exp/v8p/bench_stream.json', 'w') as f:
        json.dump(dict(rows=out, aggregate=dict(agg), tamper=tamper), f,
                  indent=1)
    print('n', agg['n'], 'rec_ok', agg['rec_ok'], 'stream_ok',
          agg['stream_ok'], 'ledger_ok', agg['ledger_ok'], 'identity',
          agg['identity'], 'max_stack', agg['max_stack'],
          'events', agg['events'])
    print('t_rec', round(agg['t_rec'], 4), 't_stream',
          round(agg['t_stream'], 4), 'speed',
          round(agg['t_rec'] / max(1e-9, agg['t_stream']), 2))
    print('tamper', tamper)
    print('W complete', collections.Counter(
        x['W'] for x in out if x['budget'] is None))
    print('W by budget', {B: collections.Counter(
        x['W'] for x in out if x['budget'] == B) for B in
        (1, 2, 3, 4, 5, 6, 8, 9)})


if __name__ == '__main__':
    main()
