"""Benchmark v8.2 HALO-ALC against v8.1 CRISP-ALC on the 252-case corpus."""
import sys
import json
import time
from collections import Counter

sys.path[:0] = ['exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from chip import CRISP, base_corpus, pert_corpus, stress_corpus
from halo import HALO, verify_hall, hall_intervals, replay, hall_cert


CORPORA = [('base', base_corpus()), ('pert', pert_corpus()),
           ('stress', stress_corpus())]


def corpus_rows():
    out = []
    for lab, rows in CORPORA:
        for row in rows:
            if len(row) == 4:
                name, idx, inst, opt = row
            else:
                idx, h, inst = row
                name = 'stress'
                opt = h
            out.append((lab, name, idx, inst, opt))
    return out


def run_one(cls, inst, known, mode=None, engine=None):
    t0 = time.time()
    if engine is not None:
        co = cls(inst, mode=mode, engine=engine)
    elif mode is not None:
        co = cls(inst, mode=mode)
    else:
        co = cls(inst)
    r = co.optimize()
    dt = time.time() - t0
    r['t'] = dt
    r['known'] = known
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof']
                   and r['cert_h'] == known - 1)
    r['replay'], r['replay_why'] = replay(inst, r, co)
    r['co'] = co
    return r


def aggregate(rows):
    return dict(
        n=len(rows),
        cert=sum(bool(r['certified']) for r in rows),
        ok=sum(bool(r['ok']) for r in rows),
        replay=sum(bool(r.get('replay')) for r in rows),
        q=sum(r['queries'] for r in rows),
        lp=sum(r['lp'] for r in rows),
        yn=sum(r['yes_nodes'] for r in rows),
        mc=sum(r['mc_evals'] for r in rows),
        t=round(sum(r['t'] for r in rows), 3),
        zero=sum(r.get('zero', 0) for r in rows),
        hall_final=sum(r.get('hall_final', 0) for r in rows),
        probe_yes=sum(r.get('probe_yes', 0) for r in rows),
        probe_no=sum(r.get('probe_no', 0) for r in rows),
        flow=sum(r.get('flow_calls', 0) for r in rows),
        unk=sum(r['unknown'] for r in rows),
        qdist={k: sum(1 for r in rows if r['queries'] == k)
               for k in range(0, 8)},
        kinds=dict(Counter(r.get('proof_kind') for r in rows)),
    )


def main():
    corp = corpus_rows()
    out = {}
    for label, cls, mode, engine in [
            ('crisp', CRISP, None, None),
            ('halo_energy', HALO, 'proof', 'energy'),
            ('halo_proof', HALO, 'proof', 'hall'),
            ('halo_probe', HALO, 'probe', 'hall')]:
        rows = []
        t0 = time.time()
        for lab, name, idx, inst, opt in corp:
            r = run_one(cls, inst, opt, mode, engine)
            r['lab'] = lab
            r['name'] = name
            r['idx'] = idx
            rows.append(r)
        wall = time.time() - t0
        agg = aggregate(rows)
        agg['wall'] = round(wall, 3)
        out[label] = agg
        print('==', label, {k: v for k, v in agg.items()
                            if k not in ('qdist', 'kinds')})
        print('   qdist', agg['qdist'], 'kinds', agg['kinds'])
        for lab in ['base', 'pert', 'stress']:
            sub = [r for r in rows if r['lab'] == lab]
            a = aggregate(sub)
            print('  ', lab, {k: a[k] for k in
                              ('n', 'cert', 'ok', 'replay', 'q', 'lp',
                               'yn', 't', 'zero', 'hall_final',
                               'probe_yes', 'probe_no', 'flow')})
        bad = [r for r in rows if not r['ok'] or not r.get('replay')]
        if bad:
            print('   BAD', [(r['lab'], r['name'], r['idx'], r['opt'],
                             r['known'], r['ok'], r.get('replay_why'))
                            for r in bad[:8]])
        out[label + '_rows'] = [
            {k: r.get(k) for k in
             ('lab', 'name', 'idx', 'known', 'opt', 'lb', 'lb0', 'ub0',
              'queries', 'lp', 'yes_nodes', 'unknown', 'certified',
              'audit', 'proof', 'cert_h', 'proof_kind', 'zero',
              'hall_final', 'probe_yes', 'probe_no', 'flow_calls',
              'replay', 't', 'ok')}
            for r in rows]

    # certificate / threshold audit over a fresh HALO proof run
    certs = 0
    cert_bad = 0
    noncontig = 0
    interval_hist = Counter()
    kind_counts = Counter()
    empty_b = 0
    nonempty_b = 0
    rows = []
    for lab, name, idx, inst, opt in corp:
        r = run_one(HALO, inst, opt, 'proof')
        rows.append((lab, name, idx, inst, opt, r))
    for lab, name, idx, inst, opt, r in rows:
        co = r['co']
        for h, c in co.certs.items():
            certs += 1
            kind_counts[c.get('kind')] += 1
            if not verify_hall(inst, h, c):
                cert_bad += 1
            iv = hall_intervals(c)
            interval_hist[len(iv)] += 1
            if len(iv) > 1:
                noncontig += 1
            if c.get('kind') == 'hall':
                if c.get('B'):
                    nonempty_b += 1
                else:
                    empty_b += 1
    out['cert_audit'] = dict(total=certs, bad=cert_bad,
                             noncontiguous=noncontig,
                             interval_hist=dict(interval_hist),
                             kinds=dict(kind_counts),
                             hall_empty_b=empty_b,
                             hall_nonempty_b=nonempty_b)
    print('== cert audit', out['cert_audit'])

    # bracket / threshold / trace stats
    stats = dict(n=0, cert_hminus=0, cert_h=0, h_lt_u=0,
                 cert_umminus=0, same_trace=0, prefix_trace=0,
                 other_trace=0, saved_q=0, saved_lp=0, saved_yn=0,
                 zero_by_lab=Counter(), hall_final_by_lab=Counter(),
                 gap_opt=Counter(), gap_ub=Counter(), width=Counter())
    for lab, name, idx, inst, opt, r in rows:
        co = r['co']
        H = r['chip']['lb']
        U = r['chip']['ub']
        stats['n'] += 1
        stats['gap_opt'][opt - H] += 1
        stats['gap_ub'][U - H] += 1
        stats['width'][U - H] += 1
        stats['zero_by_lab'][lab] += r.get('zero', 0)
        stats['hall_final_by_lab'][lab] += r.get('hall_final', 0)
        if H - 1 in co.certs and verify_hall(inst, H - 1, co.certs[H - 1]):
            stats['cert_hminus'] += 1
        if hall_cert(inst, H) is None:
            stats['cert_h'] += 1
        if H < U:
            stats['h_lt_u'] += 1
            if hall_cert(inst, U - 1) is None:
                stats['cert_umminus'] += 1
        a = CRISP(inst).optimize()
        ta = [(s['h'], s['v']) for s in a['trace']]
        tb = [(s['h'], s['v']) for s in r['trace']]
        if ta == tb:
            stats['same_trace'] += 1
        elif tb == ta[:len(tb)] and len(ta) == len(tb) + 1:
            stats['prefix_trace'] += 1
            stats['saved_q'] += a['queries'] - r['queries']
            stats['saved_lp'] += a['lp'] - r['lp']
            stats['saved_yn'] += a['yes_nodes'] - r['yes_nodes']
        else:
            stats['other_trace'] += 1
    for k in ('zero_by_lab', 'hall_final_by_lab', 'gap_opt', 'gap_ub',
              'width'):
        stats[k] = dict(stats[k])
    out['stats'] = stats
    print('== stats', stats)

    json.dump(out, open('exp/v8g/bench_halo.json', 'w'), indent=1)
    print('wrote exp/v8g/bench_halo.json')


if __name__ == '__main__':
    main()
