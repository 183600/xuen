"""Pilot: lift a local NO proof into a global NO(h) cut.

At a fixed horizon h, a leaf box F can be infeasible while the root LP is
feasible.  The v9.1 GAC code can turn that leaf NO proof into globally
valid no-good cuts.  This pilot asks: if we first solve the root LP, pick
a root branch, and probe one child with a one-node oracle, can the child's
cut replace the full root search?

The pilot is offline: it uses known-1 as h.  It reports
search LP + certificate LP + cut LP for both methods.  It is not part of
the main benchmark; the frontier and cut lift are integrated only in the
next round.

Run from the workspace root:

    .venv/bin/python exp/v8u/pilot_localcut.py --suite normal
    .venv/bin/python exp/v8u/pilot_localcut.py --suite weak
"""
import argparse
import json
import sys
import time

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from icf import corpora
from hap import weak_rows
from pact import pact_decide, _elig_aware
from sdecc import SDLP
from po import heads_tails
from gac import candidate_cuts, CutProof


def root_lp(inst, h):
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=_elig_aware(inst))
    res = lp.solve([(0, 1)] * lp.N)
    return lp, res, q


def choose_branch(inst, h, lp, res, q):
    """Mass split of the root LP; same heuristic as the PACT branch."""
    if res is None or res.status != 0:
        return None
    n = inst['n']
    z = res.x
    cand = []
    for i in range(n):
        times = sorted({key[-1] for c, key in enumerate(lp.cols)
                        if key[0] == i})
        if len(times) <= 1:
            continue
        dist = []
        for tt in times:
            v = sum(z[c] for c, key in enumerate(lp.cols)
                    if key[0] == i and key[-1] == tt)
            dist.append((tt, v))
        frac = sum(v for _, v in dist if 1e-7 < v < 1 - 1e-7)
        if frac <= 1e-7:
            continue
        mass = sum(v for _, v in dist)
        cand.append(((mass, q[i], len(inst['succ'][i]), -i), i, dist))
    if not cand:
        return None
    cand.sort(reverse=True)
    _, i, dist = cand[0]
    total = sum(v for _, v in dist)
    acc = 0.0
    mid = dist[0][0]
    for tt, v in dist:
        acc += v
        if acc >= 0.5 * total:
            mid = tt
            break
    times = [tt for tt, _ in dist]
    hi = [t for t in times if t > mid]
    lo = [t for t in times if t <= mid]
    if not hi or not lo:
        mid = times[len(times) // 2 - 1]
        hi = [t for t in times if t > mid]
        lo = [t for t in times if t <= mid]
    if not hi or not lo:
        return None
    return (i, mid, frozenset((i, t) for t in hi),
            frozenset((i, t) for t in lo), len([1 for _, v in dist
                                                if 1e-7 < v < 1 - 1e-7]))


def local_cut(inst, h):
    t0 = time.time()
    lp, res, q = root_lp(inst, h)
    slp, scert = 1, 0
    if res is None or res.status == 2:
        return True, slp, scert, 'root-infeasible', 0, 0.0
    if res.status != 0:
        return False, slp, scert, 'root-unknown', 0, 0.0
    ch = choose_branch(inst, h, lp, res, q)
    if ch is None:
        return False, slp, scert, 'no-branch', 0, 0.0
    i, mid, Fhi, Flo, nfrac = ch
    for tag, F in (('lo', Flo), ('hi', Fhi)):
        r = pact_decide(inst, h, depthcap=None, nodecap=1, forbid0=F)
        slp += r.get('lp_solves', 0)
        scert += r.get('cert_lp', 0)
        if r['verdict'] is False:
            cuts = candidate_cuts(inst, h, r['proof'])
            if not cuts:
                continue
            cp = CutProof(inst, h, cuts)
            ok = cp.audit_rdf()
            slp += cp.audit_lp
            if ok:
                return True, slp, scert, 'cut-' + tag, nfrac, round(time.time() - t0, 4)
    return False, slp, scert, 'no-cut', nfrac, round(time.time() - t0, 4)


def full_root(inst, h):
    r = pact_decide(inst, h, depthcap=None, nodecap=None)
    return r, r.get('lp_solves', 0), r.get('cert_lp', 0)


def run_suite(which, limit=None):
    if which == 'normal':
        items = [(c, name, idx, inst, known) for c, name, idx, inst,
                 known in corpora()]
    elif which == 'weak':
        items = [(c, name, idx, inst, known) for c, name, idx, inst,
                 known, initial in weak_rows(4)]
    else:
        raise ValueError(which)
    if limit:
        items = items[:limit]

    rows = []
    for c, name, idx, inst, known in items:
        h = known - 1
        r, fa, fb = full_root(inst, h)
        if r['verdict'] is not False or fa <= 1:
            continue
        ok, sa, sb, detail, nfrac, t = local_cut(inst, h)
        rows.append(dict(
            corpus=c, name=name, idx=idx, known=known,
            full_search=fa, full_cert=fb, full_total=fa + fb,
            local_search=sa, local_cert=sb, local_total=sa + sb,
            cut_ok=bool(ok), detail=detail, root_frac_jobs=nfrac,
            local_t=t,
            win=bool(ok and sa + sb < fa + fb),
            fallback_total=(sa + sb + fa + fb) if not ok else sa + sb,
        ))
        print('%-8s %-3d full %d+%d local %d+%d %-10s frac %d win %s'
              % (name, idx, fa, fb, sa, sb, detail, nfrac,
                 rows[-1]['win']), flush=True)

    n = len(rows)
    wins = [r for r in rows if r['win']]
    print('\nSUMMARY %s n %d cut_ok %d wins %d'
          % (which, n, sum(r['cut_ok'] for r in rows), len(wins)))
    if rows:
        print('full total %d local total %d fallback total %d'
              % (sum(r['full_total'] for r in rows),
                 sum(r['local_total'] for r in rows),
                 sum(r['fallback_total'] for r in rows)))
        print('win full %d win local %d'
              % (sum(r['full_total'] for r in wins),
                 sum(r['local_total'] for r in wins)))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--suite', choices=('normal', 'weak'), default='normal')
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()
    rows = run_suite(args.suite, args.limit)
    out = args.out or 'exp/v8u/pilot_localcut_%s.json' % args.suite
    with open(out, 'w') as f:
        json.dump(rows, f, indent=1)
    print('->', out)


if __name__ == '__main__':
    main()
