"""LNS ablation on the 45 PACT-tight gap-1 cases (L=OPT, U=OPT+1).

Modes:
  probe       : one pact_decide at h=L (the lower-first probe)
  lns         : LNS on every case, probe only on LNS failure
  gated       : LNS only when the root LP at h=L has >= frac fractional
                variables; probe otherwise or on LNS failure
"""
import sys, json, time, argparse, collections
sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']
import bench_balance as bb
from pact import PACT, pact_decide
from lns import lns_drop, greedy_repair
from sage import _elig_aware
from sdecc import SDLP
from po import heads_tails
from rdf import check_schedule
from balance import cmax


def root_lp(inst, h):
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    lp = SDLP(inst, h, est, q, use_dom=True,
              elig_aware=_elig_aware(inst))
    res = lp.solve()
    frac = (sum(1 for v in res.x if 1e-7 < v < 1 - 1e-7)
            if res.status == 0 else -1)
    return lp, res, frac


def cases():
    out = []
    for tag, name, idx, inst, known in bb.corpora():
        co = PACT(inst, pact_mode='complete', use_ga=False)
        L, U, s, m = co.initial_bounds()
        if U is None or not (L == known and U == known + 1):
            continue
        out.append(dict(tag=tag, name=name, idx=idx, inst=inst,
                        known=known, L=L, U=U, s=list(s), m=list(m)))
    return out


def run_case(r, mode='gated', frac_th=30, budget=24, kmax=14,
             tlim=0.2, stall=6):
    inst, L, U = r['inst'], r['L'], r['U']
    h = L
    lp, res, frac = root_lp(inst, h)
    t0 = time.time()
    lns_used = False
    lns_ok = False
    lns_time = 0.0
    lns_checks = 0
    if mode == 'lns' or (mode == 'gated' and frac >= frac_th):
        lns_used = True
        nU, ns, nm, st = lns_drop(inst, U, r['s'], r['m'],
                                  budget=budget, kmax=min(kmax, inst['n']),
                                  tlim=tlim, stall=stall, seed=0)
        lns_time = st['t']
        lns_checks = st['checks']
        if nU <= h and ns is not None and check_schedule(inst, nU, ns, nm):
            lns_ok = True
            return dict(frac=frac, probes=0, lp=1, cert_lp=0,
                        lns_used=lns_used, lns_ok=lns_ok,
                        lns_time=lns_time, lns_checks=lns_checks,
                        t=round(time.time() - t0, 4),
                        verdict='LNS', final=cmax(inst, ns))
    rr = pact_decide(inst, h, depthcap=None, nodecap=None,
                     root_lp=lp, root_res=res)
    probes = 1
    lp_total = 1 + rr.get('lp_solves', 0)
    ok = bool(rr['verdict'] is True and
              cmax(inst, rr['schedule']) <= h)
    return dict(frac=frac, probes=probes, lp=lp_total,
                cert_lp=rr.get('cert_lp', 0),
                lns_used=lns_used, lns_ok=lns_ok,
                lns_time=lns_time, lns_checks=lns_checks,
                t=round(time.time() - t0, 4),
                verdict=rr['verdict'], final=(cmax(inst, rr['schedule'])
                                              if rr['verdict'] is True else None),
                ok=ok)


def summarize(rows, label):
    print('%-12s cases %2d probes %2d lp %3d cert %2d lns %2d ok %2d '
          'lns_t %5.2f t %5.2f'
          % (label, len(rows), sum(r['probes'] for r in rows),
             sum(r['lp'] for r in rows), sum(r['cert_lp'] for r in rows),
             sum(r['lns_used'] for r in rows), sum(r['lns_ok'] for r in rows),
             sum(r['lns_time'] for r in rows),
             sum(r['t'] for r in rows)))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', default='gated')
    ap.add_argument('--frac', type=int, default=30)
    ap.add_argument('--kmax', type=int, default=14)
    args = ap.parse_args()
    cs = cases()
    print('cases', len(cs), flush=True)
    rows = []
    t0 = time.time()
    for r in cs:
        x = run_case(r, mode=args.mode, frac_th=args.frac, kmax=args.kmax)
        x.update(tag=r['tag'], name=r['name'], idx=r['idx'],
                 known=r['known'], L=r['L'], U=r['U'])
        rows.append(x)
    summarize(rows, args.mode)
    print('wall', round(time.time() - t0, 2))
    out = 'exp/v8u/bench_balance_lns_%s.json' % args.mode
    json.dump(rows, open(out, 'w'), indent=1)
    print('saved', out)
