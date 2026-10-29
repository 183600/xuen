"""Benchmarks for v9.2 GCC-ICF."""
import sys
import json
import time
import argparse

sys.path[:0] = ['exp/v9f', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from pact import pact_decide
from icf import corpora
from gcc import cut_probe, run_gcc


def fixed_h(out, max_cuts=12):
    cases = json.load(open('exp/v10c/gap_cases.json'))
    rows = []
    tot_base = tot_cut = 0
    closed = 0
    for d in cases:
        inst, h = d['inst'], int(d['opt']) - 1
        t0 = time.time()
        base = pact_decide(inst, h, depthcap=None, nodecap=None)
        tb = time.time() - t0
        base_lp = base.get('lp_solves', 0) + base.get('cert_lp', 0)
        t0 = time.time()
        cut = cut_probe(inst, h, max_cuts=max_cuts)
        tc = time.time() - t0
        cut_lp = cut.get('lp_solves', 0) + cut.get('cert_lp', 0)
        ok = bool(cut.get('verdict') is False and
                  cut.get('proof') is not None and
                  cut['proof'].audit_rdf())
        base_ok = bool(base.get('verdict') is False and
                       base.get('proof') is not None and
                       base['proof'].audit_rdf())
        closed += bool(cut.get('closed'))
        tot_base += base_lp
        tot_cut += cut_lp
        rows.append(dict(
            case=d['case'], kind=d['kind'], gap=d['opt_gap'],
            opt=d['opt'], h=h, lb0=d['lb0'], ub0=d['ub0'],
            base_ok=base_ok, base_lp=base.get('lp_solves', 0),
            base_cert=base.get('cert_lp', 0), base_total=base_lp,
            base_t=round(tb, 3),
            cut_ok=ok, cut_lp=cut.get('lp_solves', 0),
            cut_cert=cut.get('cert_lp', 0), cut_total=cut_lp,
            cut_cuts=cut.get('cuts', 0), cut_closed=bool(cut.get('closed')),
            cut_reason=cut.get('reason'), cut_t=round(tc, 3)))
        print(rows[-1]['case'], 'gap', rows[-1]['gap'],
              'base', base_lp, round(tb, 3),
              '| cut', cut_lp, cut.get('cuts', 0),
              cut.get('reason'), ok, round(tc, 3), flush=True)
    summary = dict(
        cases=len(rows), max_cuts=max_cuts,
        base_total=tot_base, cut_total=tot_cut,
        saved=tot_base - tot_cut,
        base_ok=sum(r['base_ok'] for r in rows),
        cut_ok=sum(r['cut_ok'] for r in rows),
        closed=closed,
        cut_time=sum(r['cut_t'] for r in rows),
        base_time=sum(r['base_t'] for r in rows),
        rows=rows)
    json.dump(summary, open(out, 'w'), indent=1)
    print(json.dumps({k: v for k, v in summary.items() if k != 'rows'},
                     indent=1))
    print('saved', out)


def corpus(out, gate='deep', max_cuts=12, limit=0):
    rows = []
    t0 = time.time()
    n = 0
    for tag, name, idx, inst, known in corpora():
        if limit and n >= limit:
            break
        n += 1
        r = run_gcc(inst, known, name, idx, policy='lower-first',
                    max_cuts=max_cuts, cut_gate=gate)
        r['corpus'] = tag
        rows.append(r)
        print(tag, name, idx, 'opt', r.get('opt'), 'lb', r.get('lb'),
              'probes', r.get('probes'), 'cut_probes', r.get('cut_probes'),
              'cut_closed', r.get('cut_closed'), 'lp', r.get('total_lp'),
              't', r.get('t'), 'ok', r.get('ok'), flush=True)
    summary = dict(
        gate=gate, max_cuts=max_cuts, n=len(rows),
        ok=sum(bool(r.get('ok')) for r in rows),
        certified=sum(bool(r.get('certified')) for r in rows),
        partial_fail=sum(r.get('partial_fail', 0) for r in rows),
        probes=sum(r.get('probes', 0) for r in rows),
        cut_probes=sum(r.get('cut_probes', 0) for r in rows),
        cut_closed=sum(r.get('cut_closed', 0) for r in rows),
        cut_total=sum(r.get('cut_total', 0) for r in rows),
        pin_lp=sum(r.get('pin_lp', 0) for r in rows),
        search_lp=sum(r.get('search_lp', 0) for r in rows),
        search_cert_lp=sum(r.get('search_cert_lp', 0) for r in rows),
        total_lp=sum(r.get('total_lp', 0) for r in rows),
        t=round(time.time() - t0, 3),
        rows=rows)
    json.dump(summary, open(out, 'w'), indent=1)
    print(json.dumps({k: v for k, v in summary.items() if k != 'rows'},
                     indent=1))
    print('saved', out)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', default='fixed')
    ap.add_argument('--gate', default='deep')
    ap.add_argument('--max-cuts', type=int, default=12)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--out', default='exp/v9f/bench_gcc.json')
    args = ap.parse_args()
    if args.mode == 'fixed':
        fixed_h(args.out, max_cuts=args.max_cuts)
    else:
        corpus(args.out, gate=args.gate, max_cuts=args.max_cuts,
               limit=args.limit)
