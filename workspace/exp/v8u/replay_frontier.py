"""Replay PACT's fixed-h NO trees as ICF frontier certificates.

This is a certificate-format check, not a new search: for every instance
we obtain the NO(OPT-1) BranchProof, convert its tree to a FrontierProof,
and audit the partition/leaf conditions.
"""
import json
import sys
import collections

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from icf import corpora, branch_to_frontier
from pact import pact_decide


def leaves(node):
    if node[0] == 'leaf':
        return 1
    return leaves(node[4]) + leaves(node[5])


def main():
    rows = []
    hist = collections.Counter()
    ok = 0
    for corpus, name, idx, inst, known in corpora():
        r = pact_decide(inst, known - 1, depthcap=None, nodecap=None)
        proof = r.get('proof')
        if r['verdict'] is not False or proof is None:
            rows.append(dict(corpus=corpus, name=name, idx=idx,
                             known=known, ok=False, reason='no-proof'))
            continue
        fp = branch_to_frontier(proof)
        audit = bool(fp.audit_rdf())
        nleaf = leaves(fp.tree)
        hist[nleaf] += 1
        ok += bool(audit)
        rows.append(dict(corpus=corpus, name=name, idx=idx,
                         known=known, ok=audit, h=fp.h,
                         leaves=nleaf, kind=proof.kind,
                         cert=proof.kind))
    out = dict(instances=len(rows), frontier_ok=ok,
               leaf_hist={str(k): v for k, v in sorted(hist.items())},
               nontrivial=sum(v for k, v in hist.items() if k > 1),
               leaves=sum(k * v for k, v in hist.items()),
               nontrivial_leaves=sum(k * v for k, v in hist.items()
                                     if k > 1),
               rows=rows)
    with open('exp/v8u/frontier_replay.json', 'w') as f:
        json.dump(out, f, indent=1)
    print({k: v for k, v in out.items() if k != 'rows'})


if __name__ == '__main__':
    main()
