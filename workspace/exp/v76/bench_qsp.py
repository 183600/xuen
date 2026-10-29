"""Benchmark v7.3 QSP against v7.1 QNC and v7.2 QUC.

Subsets: the 141-case corpus, the 60 perturbations, and the 51-case
h5/h47 branch stress set.  For every case we run QNC, QUC(unit_budget=6)
and QSP(node_budget=4, internal_budget=1, probe_budget=24) in the same
process and record LP solves, nodes, probes, force events, audit and
wall-clock time, plus verdict anytime curves.
"""
import sys, pickle, json, time

sys.path[:0] = ['exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']
from qnc import QNC
from quc import QUC
from qsp import QSP

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


def cases():
    out = []
    for name, f in FILES.items():
        for idx, (inst, opt) in enumerate(load(f)):
            out.append(('base', name, idx, inst, opt - 1))
    for (name, k, inst, opt, an, al) in pickle.load(
            open('exp/v71/perturb60.pkl', 'rb')):
        out.append(('pert', name, k, inst, opt - 1))
    for n, r in enumerate(pickle.load(open('exp/v81/h5h47_branch.pkl',
                                           'rb'))):
        out.append(('stress', 'h5h47', n, r['inst'], r['h']))
    return out


def one(inst, h):
    t0 = time.time(); a = QNC(inst, h); va, sa = a.decide()
    ta = time.time() - t0
    t0 = time.time(); b = QUC(inst, h, unit_budget=6); vb, sb = b.decide()
    tb = time.time() - t0
    t0 = time.time(); c = QSP(inst, h, probe_budget=24, node_budget=4,
                              internal_budget=1); vc, sc = c.decide()
    tc = time.time() - t0
    t0 = time.time(); e = QSP(inst, h, probe_budget=24, node_budget=2,
                              internal_budget=0); ve, se = e.decide()
    te = time.time() - t0
    return dict(qnc=dict(v=va, lp=sa['lp_solves'], nodes=sa['nodes'], t=ta,
                         audit=a.audit()),
                quc=dict(v=vb, lp=sb['lp_solves'], nodes=sb['nodes'], t=tb,
                         probes=sb['unit_probes'], traps=sb['trap'] is not None,
                         cross=sb['cross'] is not None,
                         root_frac=sb['root_frac'], audit=b.audit_quc()),
                qsp2=dict(v=ve, lp=se['lp_solves'], nodes=se['nodes'], t=te,
                          probes=se['probes_total'],
                          events=len(e.force_events),
                          re_solves=se['re_solves'], why=se['why'],
                          traps=e.trap is not None,
                          conflict=e.conflict is not None,
                          audit=e.audit_qsp()),
                qsp=dict(v=vc, lp=sc['lp_solves'], nodes=sc['nodes'], t=tc,
                         probes=sc['probes_total'], events=len(c.force_events),
                         re_solves=sc['re_solves'],
                         why=sc['why'],
                         depths0=sum(1 for d in c.force_depths if d == 0),
                         depthsP=sum(1 for d in c.force_depths if d > 0),
                         traps=c.trap is not None, cross=c.cross is not None,
                         conflict=c.conflict is not None,
                         root_frac=sc['root_frac'], mine_fail=sc['mine_fail'],
                         audit=c.audit_qsp()))


def total(rows):
    o = {}
    for m in ('qnc', 'quc', 'qsp', 'qsp2'):
        o[m] = dict(
            no=sum(r[m]['v'] is False for r in rows),
            yes=sum(r[m]['v'] is True for r in rows),
            unk=sum(r[m]['v'] is None for r in rows),
            lp=sum(r[m]['lp'] for r in rows),
            nodes=sum(r[m]['nodes'] for r in rows),
            t=round(sum(r[m]['t'] for r in rows), 3),
            audit=sum(r[m]['audit'] for r in rows))
    for m in ('qsp', 'qsp2'):
        o[m]['probes'] = sum(r[m]['probes'] for r in rows)
        o[m]['events'] = sum(r[m]['events'] for r in rows)
        o[m]['traps'] = sum(r[m]['traps'] for r in rows)
    o['qsp']['probes'] = sum(r['qsp']['probes'] for r in rows)
    o['qsp']['events'] = sum(r['qsp']['events'] for r in rows)
    o['qsp']['depthsP'] = sum(r['qsp']['depthsP'] for r in rows)
    o['quc']['probes'] = sum(r['quc']['probes'] for r in rows)
    o['quc']['traps'] = sum(r['quc']['traps'] for r in rows)
    o['qsp']['traps'] = sum(r['qsp']['traps'] for r in rows)
    o['n'] = len(rows)
    return o


def anytime(rows, k=12):
    return {m: {i: sum(1 for r in rows if r[m]['lp'] <= i)
                for i in range(k + 1)}
            for m in ('qnc', 'quc', 'qsp', 'qsp2')}


def main():
    rows = []
    for sec, name, idx, inst, h in cases():
        r = one(inst, h)
        r.update(sec=sec, name=name, idx=idx,
                 n=len(inst['p']), m=inst['m'])
        rows.append(r)
    out = dict(rows=rows)
    for sec in ('base', 'pert', 'stress'):
        sub = [r for r in rows if r['sec'] == sec]
        out[sec] = total(sub)
        out[sec + '_anytime'] = anytime(sub)
        print(sec, {k: v for k, v in out[sec].items() if k != 'n'},
              flush=True)
    out['all'] = total(rows)
    out['all_anytime'] = anytime(rows)
    print('ALL', out['all'], flush=True)

    diff = [r for r in rows if r['qsp']['lp'] != r['quc']['lp']]
    out['diff'] = [dict(sec=r['sec'], name=r['name'], idx=r['idx'],
                        qnc_lp=r['qnc']['lp'], quc_lp=r['quc']['lp'],
                        quc_nodes=r['quc']['nodes'],
                        qsp_lp=r['qsp']['lp'], qsp_nodes=r['qsp']['nodes'],
                        qsp_probes=r['qsp']['probes'],
                        qsp_events=r['qsp']['events'])
                   for r in diff]
    print('DIFF', len(diff), flush=True)
    for r in out['diff']:
        print(r, flush=True)
    json.dump(out, open('exp/v76/qsp_bench.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
