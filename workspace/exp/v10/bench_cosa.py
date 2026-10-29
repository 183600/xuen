import sys
import json
import time
import statistics
import os

sys.path[:0] = ['exp/v10']
from cosa import run_cosa
from icf import corpora


def summarize(rows, label):
    n = len(rows)
    ok = sum(r.get('ok', False) for r in rows)
    cert = sum(r.get('certified', False) for r in rows)
    probes = sum(r.get('probes', 0) for r in rows)
    lp = sum(r.get('pact_lp', 0) for r in rows)
    pin = sum(r.get('pin_lp', 0) for r in rows)
    sa_dec = sum(r.get('sa_decodes', 0) for r in rows)
    sa_hit = sum(r.get('sa_hits', 0) for r in rows)
    sa_gain = sum(r.get('sa_gain', 0) for r in rows)
    t = sum(r.get('t', 0.0) for r in rows)
    print('%s n=%d ok=%d cert=%d probes=%d pact_lp=%d pin_lp=%d '
          'sa_dec=%d sa_hit=%d sa_gain=%d t=%.2f'
          % (label, n, ok, cert, probes, lp, pin, sa_dec, sa_hit,
             sa_gain, t), flush=True)
    return dict(n=n, ok=ok, cert=cert, probes=probes, pact_lp=lp,
                pin_lp=pin, sa_dec=sa_dec, sa_hit=sa_hit,
                sa_gain=sa_gain, t=round(t, 3))


def main():
    out = []
    t0 = time.time()
    for k, (corp, name, idx, inst, known) in enumerate(corpora()):
        row = run_cosa(inst, known, name, idx, policy='lower-first',
                       sa_budget=20000, sa_seeds=(0, 1, 2, 3),
                       sa_gate=2, spark=int(os.environ.get('COSA_SPARK_N', '150')),
                       mode=os.environ.get('COSA_MODE', 'mixed'),
                       spark_mode=os.environ.get('COSA_SPARK', 'mixed'))
        row['corpus'] = corp
        out.append(row)
        if (k + 1) % 20 == 0:
            print('.. %d/%d t=%.1f' % (k + 1, len(out),
                                       time.time() - t0), flush=True)
    suffix = os.environ.get('COSA_SUFFIX', '')
    json.dump(out, open('exp/v10/bench_cosa_252%s.json' % suffix, 'w'),
              indent=1)
    summary = summarize(out, 'COSA-ICF 252')
    summary['wall'] = round(time.time() - t0, 3)
    print('wall', summary['wall'])
    json.dump(summary, open('exp/v10/summary_cosa_252%s.json' % suffix, 'w'),
              indent=1)


if __name__ == '__main__':
    main()
