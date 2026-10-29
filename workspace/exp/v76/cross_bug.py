"""Reproduce the v7.2 audit_quc cross-precedence bug (fixed in v7.3).

QUC stores a precedence cross as ('prec', i, t, j, u) but audit_quc
unpacks self.cross[:4], which shifts every field by one, so a correct
cross certificate fails the audit.  QSC with unit_budget=3 reaches that
path on the h5h47 stress set; v7.3's audit_qsp/audit check uses
self.cross[:5] and passes the same certificate.
"""
import sys, pickle, json

sys.path[:0] = ['exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']
from qsc import QSC
from cert import verify


def fixed_cross_ok(q):
    if q.cross is None:
        return None
    if q.cross[0] == 'cap':
        _, tau, c, m = q.cross
        U = {i: t for (i, t) in q.unit_certs}
        cnt = sum(1 for j, u in U.items()
                  if u <= tau < u + q.inst['p'][j])
        return cnt == c and cnt > m
    _, i, t, j, u = q.cross[:5]
    if (i, t) not in q.unit_certs or (j, u) not in q.unit_certs:
        return False
    if j not in q.inst['succ'][i] or not (u < t + q.inst['p'][i]):
        return False
    return all(verify(q.inst, q.h, c, forbid={(a, b)}, elig_aware=q.elig)
               for (a, b), c in q.unit_certs.items())


def main():
    stress = pickle.load(open('exp/v81/h5h47_branch.pkl', 'rb'))
    found = []
    for n, r in enumerate(stress):
        q = QSC(r['inst'], r['h'], unit_budget=3, mine_budget=12,
                node_budget=2)
        v, st = q.decide()
        if q.cross is not None and q.cross[0] != 'cap':
            found.append(dict(idx=n, cross=q.cross, verdict=v, why=st['why'],
                              audit_quc=q.audit_quc(),
                              audit_qsc=q.audit_qsc(),
                              fixed=fixed_cross_ok(q),
                              units=[(i, t) for i, t, _ in q.units]))
    print('precedence-cross cases', len(found), flush=True)
    for f in found:
        print(f, flush=True)
    json.dump(dict(found=found), open('exp/v76/cross_bug.json', 'w'),
              indent=1)


if __name__ == '__main__':
    main()
