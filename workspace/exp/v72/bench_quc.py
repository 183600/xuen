"""Benchmark v7.2 QUC against v7.1 QNC on the 201 NO cases."""
import sys, pickle, json, time
sys.path[:0] = ['exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from quc import QUC

FILES = {
 'holdout50': 'exp/v20/holdout_cases50.pkl',
 'synth45': 'exp/v28/synth2_45.pkl',
 'large_a': 'exp/v14/large_a.pkl',
 'large_b': 'exp/v14/large_b.pkl',
 'large_het': 'exp/v14/large_het.pkl',
 'hard3': 'exp/v13/hard3.pkl',
 'deep8': 'exp/v18/deep.pkl'}


def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]


def main():
    base = json.load(open('exp/v71/ablation.json'))
    brow = {}
    for r in base['corpus']['rows']:
        brow[(r['name'], r['idx'], 'base')] = r
    for r in base['perturbed']['rows']:
        brow[(r['name'], r['k'], 'pert')] = r

    out = {'corpus': [], 'perturbed': []}
    t0 = time.time()
    for name, f in FILES.items():
        for idx, (inst, opt) in enumerate(load(f)):
            h = opt - 1
            q = QUC(inst, h, unit_budget=6)
            ts = time.time()
            v, st = q.decide()
            dt = time.time() - ts
            br = brow[(name, idx, 'base')]
            row = dict(name=name, idx=idx, v=v, lp=st['lp_solves'],
                       nodes=st['nodes'], t=dt,
                       root_frac=st['root_frac'], probes=st['unit_probes'],
                       forced=st['unit_forced'], fail=st['unit_fail'],
                       trap=st['trap'], cross=st['cross'],
                       units=st['units'], unit_certs=st['unit_certs'],
                       audit=q.audit_quc(),
                       qnc_v=br['qnc_v'], qnc_lp=br['qnc_lp'],
                       qnc_nodes=br['qnc_nodes'], alc_lp=br['alc_lp'],
                       alc_nodes=br['alc_nodes'],
                       why=st['why'])
            out['corpus'].append(row)
    print('corpus done', len(out['corpus']), time.time() - t0, flush=True)

    pert = pickle.load(open('exp/v71/perturb60.pkl', 'rb'))
    for (name, k, inst, opt, an, al) in pert:
        h = opt - 1
        q = QUC(inst, h, unit_budget=6)
        ts = time.time()
        v, st = q.decide()
        dt = time.time() - ts
        br = brow[(name, k, 'pert')]
        row = dict(name=name, k=k, opt=opt, v=v, lp=st['lp_solves'],
                   nodes=st['nodes'], t=dt,
                   root_frac=st['root_frac'], probes=st['unit_probes'],
                   forced=st['unit_forced'], fail=st['unit_fail'],
                   trap=st['trap'], cross=st['cross'],
                   units=st['units'], unit_certs=st['unit_certs'],
                   audit=q.audit_quc(),
                   qnc_v=br['qnc_v'], qnc_lp=br['qnc_lp'],
                   qnc_nodes=br['qnc_nodes'], alc_lp=br['alc_lp'],
                   alc_nodes=br['alc_nodes'],
                   why=st['why'])
        out['perturbed'].append(row)
    print('perturbed done', len(out['perturbed']), time.time() - t0, flush=True)

    for sec in ('corpus', 'perturbed'):
        rows = out[sec]
        out[sec + '_total'] = dict(
            n=len(rows), no=sum(r['v'] is False for r in rows),
            yes=sum(r['v'] is True for r in rows),
            unknown=sum(r['v'] is None for r in rows),
            lp=sum(r['lp'] for r in rows),
            nodes=sum(r['nodes'] for r in rows),
            qnc_lp=sum(r['qnc_lp'] for r in rows),
            qnc_nodes=sum(r['qnc_nodes'] for r in rows),
            alc_lp=sum(r['alc_lp'] for r in rows),
            alc_nodes=sum(r['alc_nodes'] for r in rows),
            probes=sum(r['probes'] for r in rows),
            forced=sum(r['forced'] for r in rows),
            traps=sum(r['trap'] is not None for r in rows),
            cross=sum(r['cross'] is not None for r in rows),
            root_frac=sum(r['root_frac'] for r in rows),
            audit=sum(r['audit'] for r in rows),
            t=sum(r['t'] for r in rows))
        print(sec, out[sec + '_total'], flush=True)

    rows = out['corpus'] + out['perturbed']
    out['all_total'] = dict(
        n=len(rows), no=sum(r['v'] is False for r in rows),
        unknown=sum(r['v'] is None for r in rows),
        lp=sum(r['lp'] for r in rows), nodes=sum(r['nodes'] for r in rows),
        qnc_lp=sum(r['qnc_lp'] for r in rows),
        qnc_nodes=sum(r['qnc_nodes'] for r in rows),
        alc_lp=sum(r['alc_lp'] for r in rows),
        alc_nodes=sum(r['alc_nodes'] for r in rows),
        probes=sum(r['probes'] for r in rows),
        traps=sum(r['trap'] is not None for r in rows),
        root_frac=sum(r['root_frac'] for r in rows),
        audit=sum(r['audit'] for r in rows),
        t=sum(r['t'] for r in rows))
    print('ALL', out['all_total'], flush=True)

    # branch subset (ALC needed branching)
    br = [r for r in rows if r['alc_nodes'] > 1]
    out['branch'] = sorted(br, key=lambda r: (r['name'], r.get('idx', r.get('k'))))
    print('BRANCH', [(r['name'], r.get('idx', r.get('k')),
                      r['qnc_lp'], r['qnc_nodes'], r['lp'], r['nodes'],
                      r['trap']) for r in out['branch']], flush=True)

    # anytime: verdict LP index
    anyrows = []
    for r in rows:
        anyrows.append(r['lp'])
    out['anytime'] = {k: sum(1 for x in anyrows if x <= k) for k in range(0, 11)}
    print('ANYTIME', out['anytime'], flush=True)
    json.dump(out, open('exp/v72/quc_stats.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
