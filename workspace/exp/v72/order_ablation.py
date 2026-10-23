"""Ordering ablation for v7.2 QUC on the 7 root-fractional cases.

Compares the online span-first order with a pure support-size/mass order.
The lower bound is root LP + 2 probes per case.  The offline EA result is in
ea_order.json; this script only checks the deterministic orders.
"""
import sys, pickle, json
sys.path[:0] = ['exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from quc import QUC, _support_mass

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


class QUCSupport(QUC):
    """QUC with support-size/mass order (no span-first)."""

    def _scan_units(self, z):
        S = _support_mass(self.lp, z)
        jobs = [i for i in range(self.n) if len(S[i]) >= 2]
        jobs.sort(key=lambda i: (len(S[i]),
                                 -round(max(S[i].values()), 6), i))
        probes = 0
        for i in jobs:
            ts = sorted(S[i])
            order = sorted(ts, key=lambda t: (-S[i][t], t))
            for t in order:
                if probes >= self.unit_budget:
                    return None
                if (i, t) in self.unit_certs:
                    continue
                ok, cert = self._probe_unit(i, t)
                probes += 1
                if not ok:
                    continue
                self.unit_certs[(i, t)] = cert
                self.units.append((i, t, cert))
                self.leaves.append((frozenset({(i, t)}),
                                    frozenset({(i, t)}), cert))
                if self.cert is None:
                    self.cert, self.cert_ok = cert, True
                con = self._unit_conflict()
                if con is not None:
                    if con[0] == 'trap':
                        self.trap = (con[1], con[2], con[3])
                    else:
                        self.cross = con
                    return con
            if probes >= self.unit_budget:
                return None
        return None


def cases():
    for idx in (5, 47):
        inst, opt = load(FILES['holdout50'])[idx]
        yield ('holdout50', idx, inst, opt)
    pert = pickle.load(open('exp/v71/perturb60.pkl', 'rb'))
    for (name, k, inst, opt, an, al) in pert:
        if an > 1:
            yield (name, k, inst, opt)


def run(cls):
    rows = []
    for name, idx, inst, opt in cases():
        q = cls(inst, opt - 1, unit_budget=6)
        v, st = q.decide()
        rows.append(dict(name=name, idx=idx, v=v, lp=st['lp_solves'],
                         nodes=st['nodes'], probes=st['unit_probes'],
                         trap=st['trap'], audit=q.audit_quc()))
    total = dict(lp=sum(r['lp'] for r in rows),
                 nodes=sum(r['nodes'] for r in rows),
                 probes=sum(r['probes'] for r in rows),
                 no=sum(r['v'] is False for r in rows),
                 audit=sum(r['audit'] for r in rows))
    return dict(total=total, rows=rows)


def main():
    out = dict(span=run(QUC), support=run(QUCSupport))
    json.dump(out, open('exp/v72/order_ablation.json', 'w'), indent=1)
    for k, v in out.items():
        print(k, v['total'], [(r['name'], r['idx'], r['lp'], r['probes'])
                              for r in v['rows']])


if __name__ == '__main__':
    main()
