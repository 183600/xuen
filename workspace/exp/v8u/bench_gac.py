"""Benchmark GAC compression of ICF final NO proofs on the 252 corpus."""
import json
import sys
import time
from collections import Counter

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from icf import corpora, run_icf, ICFCertificate, PartialCertificate
from gac import compress_branch_proof
from sage import BranchProof


def shape(proof):
    """(branch nodes, leaves, depth) of a BranchProof tree."""
    nodes = leaves = depth = 0

    def walk(node, d):
        nonlocal nodes, leaves, depth
        if not isinstance(node, tuple) or not node:
            return
        tag = node[0]
        if tag in ('leaf', 'empty'):
            leaves += 1
            depth = max(depth, d)
        elif tag in ('node', 'split'):
            nodes += 1
            _, i, mid, F, lo, hi = node
            walk(lo, d + 1)
            walk(hi, d + 1)

    walk(getattr(proof, 'tree', None), 0)
    return nodes, leaves, depth


def main():
    t0 = time.time()
    rows = []
    branch = 0
    compressed = 0
    cut_ok = 0
    final_ok = 0
    cut_hist = Counter()
    leaf_hist = Counter()
    fallbacks = []
    for ci, (tag, name, idx, inst, known) in enumerate(corpora()):
        r = run_icf(inst, known, name, idx, policy='lower-first',
                    collect_proof=True)
        row = dict(tag=tag, name=name, idx=idx, known=known,
                   ok=r['ok'], opt=r['opt'], lb=r['lb'],
                   proof_kind=r['proof_kind'], t=r['t'],
                   pact_lp=r['pact_lp'], probes=r['probes'])
        proof = r.get('lb_proof')
        if isinstance(proof, BranchProof):
            branch += 1
            bn, lv, dp = shape(proof)
            row.update(branch_nodes=bn, leaves=lv, depth=dp,
                       cut_ok=False, cuts=None)
            cp = compress_branch_proof(inst, proof.h, proof)
            if cp is not None:
                stats = dict(cp.stats)
                cok = bool(cp.audit_rdf())
                row.update(cut_ok=cok,
                           cuts=stats.get('selected_cuts'),
                           candidate_cuts=stats.get('candidate_cuts'),
                           cut_lp=stats.get('lp_solves'),
                           cut_t=stats.get('t'),
                           audit_lp=cp.audit_lp,
                           audit_t=cp.audit_t,
                           cut_stats=stats)
                if cok:
                    compressed += 1
                    cut_ok += 1
                    cut_hist[stats.get('selected_cuts')] += 1
                    leaf_hist[lv] += 1
                    cert = ICFCertificate(inst, r['opt'], r['schedule'],
                                          r['machine'], cp)
                    row['final_cut_ok'] = bool(cert.audit_rdf())
                    if row['final_cut_ok']:
                        final_ok += 1
                    pc = PartialCertificate(inst, r['opt'], r['opt'],
                                            r['schedule'], r['machine'], cp)
                    row['partial_cut_ok'] = bool(pc.audit_rdf())
            else:
                fallbacks.append((tag, name, idx, 'no-minimal-cut'))
        rows.append(row)
        if (ci + 1) % 50 == 0:
            print('done', ci + 1, 'time', round(time.time() - t0, 1),
                  flush=True)

    out = dict(
        n=len(rows), branch_proofs=branch, compressed=compressed,
        cut_audit_ok=cut_ok, final_cut_ok=final_ok,
        cut_hist=dict(sorted(cut_hist.items())),
        leaf_hist=dict(sorted(leaf_hist.items())),
        fallbacks=fallbacks, rows=rows,
        t=round(time.time() - t0, 2),
    )
    with open('exp/v8u/bench_gac.json', 'w') as f:
        json.dump(out, f, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != 'rows'},
                     indent=2))
    print('wrote exp/v8u/bench_gac.json')


if __name__ == '__main__':
    main()
