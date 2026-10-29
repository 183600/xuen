"""v9.0 QUC-GRSC benchmark: 201 NO + 141 YES.

Protocol
  NO  (h = OPT-1): QUC with LP budget 6, nodecap 5000.
  YES (h = OPT):   QUC budget 6; if UNKNOWN, GRSC (est/mixed/rand,
                   nodecap 4000, 96 restarts); if GRSC fails, QUC full.
Every YES schedule is replayed by grsc.check_schedule.
Every NO verdict is checked by quc.audit_quc().
"""
import sys, pickle, json, time
sys.setrecursionlimit(100000)
sys.path[:0] = ['exp/v90', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from quc import QUC
from grsc import GRSC, check_schedule

FILES = {
    'holdout': 'exp/v20/holdout_cases50.pkl',
    'synth': 'exp/v28/synth2_45.pkl',
    'large_a': 'exp/v14/large_a.pkl',
    'large_b': 'exp/v14/large_b.pkl',
    'large_het': 'exp/v14/large_het.pkl',
    'hard3': 'exp/v13/hard3.pkl',
    'deep': 'exp/v18/deep.pkl'}


def load(name, f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]


def corpus(h_delta=0):
    out = []
    for name, f in FILES.items():
        for idx, (inst, opt) in enumerate(load(name, f)):
            out.append((name, idx, inst, opt + h_delta))
    return out


def no_corpus():
    out = corpus(-1)
    pert = pickle.load(open('exp/v71/perturb60.pkl', 'rb'))
    for (name, k, inst, opt, an, al) in pert:
        out.append((name, k, inst, opt - 1))
    return out


def main():
    no = []
    t0 = time.time()
    for name, idx, inst, h in no_corpus():
        t = time.time()
        q = QUC(inst, h)
        v, st = q.decide(budget=6, nodecap=5000)
        no.append(dict(case=name, idx=idx, v=v, lp=st['lp_solves'],
                       nodes=st['nodes'], t=time.time() - t,
                       audit=q.audit_quc()))
    no_t = time.time() - t0

    yes = []
    t0 = time.time()
    for name, idx, inst, h in corpus(0):
        t = time.time()
        q = QUC(inst, h)
        v, st = q.decide(budget=6, nodecap=5000)
        row = dict(case=name, idx=idx, v=v, quc6_lp=st['lp_solves'],
                   quc6_nodes=st['nodes'], quc6_t=time.time() - t,
                   quc6_audit=q.audit_quc(),
                   grsc=None, grsc_ok=None, grsc_t=0.0, fallback=None)
        if v is None:
            t2 = time.time()
            g = GRSC(inst, h, nodecap=4000, restarts=96, seed=0,
                     modes=('est', 'mixed', 'rand'))
            ok = g.solve()
            row['grsc'] = g.stats()
            row['grsc_ok'] = ok
            row['grsc_t'] = time.time() - t2
            if ok:
                if not check_schedule(inst, h, g.schedule, g.machine):
                    raise AssertionError((name, idx, 'bad schedule'))
                row['v'] = True
            else:
                t3 = time.time()
                q2 = QUC(inst, h)
                v2, st2 = q2.decide(budget=100000, nodecap=5000)
                row['fallback'] = dict(v=v2, lp=st2['lp_solves'],
                                       nodes=st2['nodes'],
                                       t=time.time() - t3,
                                       audit=q2.audit_quc())
                row['v'] = v2
        row['t'] = time.time() - t
        yes.append(row)
    yes_t = time.time() - t0

    out = dict(
        no=no, yes=yes,
        summary=dict(
            no_n=len(no), no_no=sum(r['v'] is False for r in no),
            no_unknown=sum(r['v'] is None for r in no),
            no_lp=sum(r['lp'] for r in no),
            no_nodes=sum(r['nodes'] for r in no),
            no_t=no_t, no_audit=sum(r['audit'] for r in no),
            yes_n=len(yes), yes_yes=sum(r['v'] is True for r in yes),
            yes_unknown=sum(r['v'] is None for r in yes),
            yes_quc6_lp=sum(r['quc6_lp'] for r in yes),
            yes_quc6_audit=sum(r['quc6_audit'] for r in yes),
            yes_fallback_lp=sum((r['fallback'] or {}).get('lp', 0) for r in yes),
            yes_grsc_calls=sum(r['grsc'] is not None for r in yes),
            yes_grsc_ok=sum(r['grsc_ok'] is True for r in yes),
            yes_grsc_nodes=sum((r['grsc'] or {}).get('nodes', 0) for r in yes),
            yes_grsc_t=sum(r['grsc_t'] for r in yes),
            yes_t=yes_t,
            total_t=no_t + yes_t))
    json.dump(out, open('exp/v90/hybrid.json', 'w'), indent=1)
    print(json.dumps(out['summary'], indent=1))
    print('fallbacks', [(r['case'], r['idx'], r['fallback'])
                        for r in yes if r['fallback']])


if __name__ == '__main__':
    main()
