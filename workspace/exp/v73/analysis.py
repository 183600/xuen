"""Post-hoc analysis for v7.3: proof shape and root+first-clause cover."""
import sys, pickle, json, statistics
from collections import Counter
sys.path[:0] = ['exp/v73', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from qcc import QCC

BR = pickle.load(open('exp/v81/h5h47_branch.pkl', 'rb'))
HO = pickle.load(open('exp/v20/holdout_cases50.pkl', 'rb'))


def first_leaf(inst, h):
    q = QCC(inst, h, case_on=False, use_cover=False)
    q.decide(budget=30000, nodecap=10000)
    return q, (q.leaves[0] if q.leaves else None)


def root_cover(inst, h):
    q0, leaf = first_leaf(inst, h)
    if leaf is None:
        return None
    F, E, cert = leaf
    q = QCC(inst, h, case_on=False, use_cover=False)
    q.budget = 30000
    q._solve([(0, 1)] * q.lp.base.N, 60, 100)
    q._add_clause(E, cert, F)
    got = q._cover_lp()
    return None if got is None else got[0]


def main():
    taus, ks, sizes, jobcount = [], [], [], []
    for r in BR:
        q = QCC(r['inst'], r['h'], case_on=True, use_cover=True)
        q.decide(budget=30000, nodecap=10000)
        if q.cover_proof:
            clauses, res = q.cover_proof
            taus.append(q.cover_tau)
            ks.append(len(clauses))
            sizes += [len(E) for E in clauses]
        if q.clause_db:
            jobcount.append(len(q.clause_db[0]))
    roots = [root_cover(r['inst'], r['h']) for r in BR]
    ho_idx = {i: root_cover(HO[i][0], HO[i][1] - 1) for i in [5, 47]}
    out = dict(
        branch_cover_hits=len(taus),
        tau=dict(n=len(taus), min=min(taus), median=statistics.median(taus),
                 max=max(taus),
                 counts=dict(Counter(round(t, 3) for t in taus))),
        clauses_at_cover=dict(min=min(ks), median=statistics.median(ks),
                              max=max(ks), counts=dict(Counter(ks))),
        literal_sizes=dict(min=min(sizes), median=statistics.median(sizes),
                           max=max(sizes)),
        first_clause_jobs=dict(counts=dict(Counter(jobcount))),
        root_first_clause=dict(
            n=len([x for x in roots if x is not None]),
            infeasible=sum(1 for x in roots if x is not None and x < 1 - 1e-6),
            tau_counts=dict(Counter(
                None if x is None else round(x, 3) for x in roots))),
        holdout_idx=ho_idx)
    json.dump(out, open('exp/v73/analysis.json', 'w'), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
