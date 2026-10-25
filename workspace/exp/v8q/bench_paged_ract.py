"""Run PAGE-RACT on the 252-instance corpus."""
import json, sys, time, collections
sys.path[:0] = ['exp/v8q', 'exp/v8p', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from chip import base_corpus, pert_corpus, stress_corpus
from paged_ract import run_paged_ract

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
    rows = []
    t0 = time.time()
    for k, (tag, name, idx, inst, known) in enumerate(corpora()):
        r = run_paged_ract(inst, known, name, idx)
        r['corpus'] = tag
        rows.append(r)
        if k % 40 == 0:
            print(k, round(time.time() - t0, 1), flush=True)
    wall = round(time.time() - t0, 2)
    json.dump(rows, open('exp/v8q/bench_paged_ract.json', 'w'), indent=1)
    print('wall', wall)
    for c in ('base', 'pert', 'stress'):
        rs = [r for r in rows if r['corpus'] == c]
        print(c, 'n', len(rs), 'ok', sum(r['ok'] for r in rs),
              'cert', sum(r['certified'] for r in rs),
              'q', sum(r['queries'] for r in rs),
              'lp', sum(r['pact_lp'] for r in rs),
              'certlp', sum(r['pact_cert_lp'] for r in rs),
              'total', sum(r['total_audit'] for r in rs),
              'bytes', sum(r['paged_bytes'] for r in rs),
              't', round(sum(r['t'] for r in rs), 2))
    print('all ok', sum(r['ok'] for r in rows),
          'cert', sum(r['certified'] for r in rows),
          'q', sum(r['queries'] for r in rows),
          'lp', sum(r['pact_lp'] for r in rows),
          'certlp', sum(r['pact_cert_lp'] for r in rows),
          'total', sum(r['total_audit'] for r in rows),
          'bytes', sum(r['paged_bytes'] for r in rows),
          'paged_ok', sum(r['paged_ok'] for r in rows),
          't', round(sum(r['t'] for r in rows), 2))
    print('kinds', collections.Counter(r['proof_kind'] for r in rows))

if __name__ == '__main__':
    main()
