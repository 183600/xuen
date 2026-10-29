"""Microbenchmark: R-ACT frontier on the 504 fixed-h probes.

For every instance we solve h=known-1 (NO) and h=known (YES) with
  * PACT complete DFS,
  * R-ACT complete DFS (bound leaves),
  * R-ACT anytime checkpoints at depth 1,2,3,4.
The output is used for the cost/quality table in the artifact.
"""
import json, sys, time, collections
sys.path[:0] = ['exp/v8p', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']
from chip import base_corpus, pert_corpus, stress_corpus
from pact import pact_decide
from ract import ract_decide
from anytime import AnytimeSearch

def corpora():
    for tag, rows in (('base', base_corpus()), ('pert', pert_corpus()),
                      ('stress', stress_corpus())):
        for row in rows:
            if len(row) == 4:
                name, idx, inst, known = row
            else:
                idx, known, inst = row
                name = tag
            yield tag, name, idx, inst, known

def main():
    out = []
    t0 = time.time()
    for k, (tag, name, idx, inst, known) in enumerate(corpora()):
        for lab, h in (('NO', known - 1), ('YES', known)):
            p = pact_decide(inst, h, depthcap=None, nodecap=None)
            q = ract_decide(inst, h, depthcap=None, nodecap=None)
            s = AnytimeSearch(inst, h, policy='dfs')
            trace = []
            for d in (1, 2, 3, 4):
                a = s.run(depth_limit=d)
                trace.append(dict(d=d, status=a['status'], L=a['L'],
                                  U=a['U'], lp=a['lp'], open=a['open'],
                                  audit=bool(a['proof'].audit_rdf())))
            out.append(dict(
                tag=tag, name=name, idx=idx, known=known, h=h, label=lab,
                pact=dict(verdict=p['verdict'], lp=p['lp_solves'],
                          nodes=p['nodes'], cert=p.get('cert_lp', 0)),
                ract=dict(verdict=q['verdict'], lp=q['lp_solves'],
                          nodes=q['nodes'], cert=q.get('cert_lp', 0),
                          bound=q.get('bound', 0), empty=q.get('empty', 0)),
                trace=trace))
        if k % 50 == 0:
            print(k, round(time.time() - t0, 2), flush=True)
    with open('exp/v8p/bench_frontier.json', 'w') as f:
        json.dump(out, f, indent=1)
    print('done', round(time.time() - t0, 2))
    for lab in ('NO', 'YES'):
        rs = [r for r in out if r['label'] == lab]
        print(lab, len(rs),
              'pact_lp', sum(r['pact']['lp'] for r in rs),
              'ract_lp', sum(r['ract']['lp'] for r in rs),
              'bound', sum(r['ract']['bound'] for r in rs),
              'better', sum(r['ract']['lp'] < r['pact']['lp'] for r in rs),
              'worse', sum(r['ract']['lp'] > r['pact']['lp'] for r in rs),
              'status', collections.Counter(str(r['ract']['verdict'])
                                            for r in rs))
        for d in (1, 2, 3, 4):
            cs = [c for r in rs for c in r['trace'] if c['d'] == d]
            print('  d', d, 'probes', len(cs),
                  'resolved', sum(c['status'] in ('no', 'yes') for c in cs),
                  'audit', sum(c['audit'] for c in cs),
                  'lp', sum(c['lp'] for c in cs),
                  'status', collections.Counter(c['status'] for c in cs))

if __name__ == '__main__':
    main()
