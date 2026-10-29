import sys, time, json
sys.path[:0] = ['exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e',
                'exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b',
                'exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61',
                'exp/v60','exp/v13']
from chip import base_corpus, pert_corpus, stress_corpus
from po import heads_tails
from sdecc import SDLP
from sage import _elig_aware
from pact import pact_decide
from cert import integer_certificate, verify
from rdf import check_schedule

def corpora():
    for tag, fn in (('base', base_corpus), ('pert', pert_corpus),
                    ('stress', stress_corpus)):
        for row in fn():
            if len(row) == 4:
                name, idx, inst, known = row
            else:
                idx, known, inst = row
                name = tag
            yield tag, name, idx, inst, known

def root_info(inst, h):
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    elig = _elig_aware(inst)
    lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig)
    base = [(0, 1)] * lp.N
    res = lp.solve(base)
    dist = {}
    for c, key in enumerate(lp.cols):
        i, t = key[0], key[-1]
        dist.setdefault(i, {})[t] = dist.setdefault(i, {}).get(t, 0.0) + float(res.x[c]) if res.status == 0 else 0.0
    times = {}
    for c, key in enumerate(lp.cols):
        times.setdefault(key[0], set()).add(key[-1])
    return lp, base, res, est, q, dist, times

def select_jobs(inst, lp, res, dist, times, policy, k):
    n = inst['n']
    if res.status != 0:
        return []
    frac = []
    for i in range(n):
        d = dist.get(i, {})
        vals = list(d.values())
        fm = sum(v for v in vals if 1e-7 < v < 1 - 1e-7)
        mass = sum(vals)
        peak = max(vals) if vals else 0.0
        width = len(times.get(i, ()))
        frac.append((fm, mass, peak, -width, -i, i))
    if policy == 'frac_mass':
        frac.sort(reverse=True)
        return [x[-1] for x in frac[:k]]
    if policy == 'frac_peak':
        frac.sort(key=lambda x: (x[0], x[2], x[1], x[3], x[4]), reverse=True)
        return [x[-1] for x in frac[:k]]
    if policy == 'wide':
        frac.sort(key=lambda x: (x[3], x[0], x[1]), reverse=True)
        return [x[-1] for x in frac[:k]]
    if policy == 'all':
        return list(range(n))[:k]
    return []

def probe_start(inst, h, lp, base, i, t, times):
    b = list(base)
    for c, key in enumerate(lp.cols):
        if key[0] == i and key[-1] != t:
            b[c] = (0, 0)
    rr = lp.solve(b)
    return rr.status

def probe_decide(inst, h, budget=8, policy='frac_mass', n_jobs=4,
                 start_policy='all', forbid0=None):
    t0 = time.time()
    lp, base, res, est, q, dist, times = root_info(inst, h)
    out = dict(probes=0, forbid=0, root=res.status, verdict=None,
               nodes=0, lp_solves=0, cert_lp=0, depth=0, t=0.0,
               pre_t=0.0, jobs=[], start_policy=start_policy)
    if res.status == 2:
        cert = integer_certificate(inst, h, forbid=forbid0)
        if cert is not None and verify(inst, h, cert, forbid=forbid0):
            out.update(verdict=False, cert=cert)
        out['t'] = round(time.time() - t0, 5)
        return out
    if res.status != 0:
        out['t'] = round(time.time() - t0, 5)
        return out
    jobs = select_jobs(inst, lp, res, dist, times, policy, n_jobs)
    out['jobs'] = jobs
    F = set(forbid0 or ())
    for i in jobs:
        ts = sorted(times.get(i, ()))
        d = dist.get(i, {})
        if start_policy == 'zero':
            ts = [t for t in ts if d.get(t, 0.0) <= 1e-9]
        elif start_policy == 'support':
            ts = [t for t in ts if d.get(t, 0.0) > 1e-9]
        elif start_policy == 'edge':
            ts = [t for t in ts if d.get(t, 0.0) <= 1e-9] + [t for t in ts if d.get(t, 0.0) > 1e-9]
        for t in ts:
            if out['probes'] >= budget:
                break
            st = probe_start(inst, h, lp, base, i, t, times)
            out['probes'] += 1
            if st == 2:
                F.add((i, t))
        if out['probes'] >= budget:
            break
    out['forbid'] = len(F)
    out['pre_t'] = round(time.time() - t0, 5)
    if F:
        lp2 = SDLP(inst, h, est, q, use_dom=True, elig_aware=_elig_aware(inst),
                   forbid=F)
        rr = lp2.solve()
        if rr.status == 2:
            cert = integer_certificate(inst, h, forbid=F)
            if cert is not None and verify(inst, h, cert, forbid=F):
                out.update(verdict=False, cert=cert, lp_solves=1,
                           nodes=1, cert_lp=1, root=2)
                out['t'] = round(time.time() - t0, 5)
                return out
        r = pact_decide(inst, h, depthcap=None, nodecap=None,
                        forbid0=F, root_lp=lp2, root_res=rr)
    else:
        r = pact_decide(inst, h, depthcap=None, nodecap=None,
                        root_lp=lp, root_res=res)
    out.update(verdict=r['verdict'], nodes=r['nodes'],
               lp_solves=r['lp_solves'] + 1, cert_lp=r['cert_lp'],
               depth=r['depth'], search_t=r['t'])
    if r['proof'] is not None:
        out['audit'] = r['proof'].audit_rdf()
    out['t'] = round(time.time() - t0, 5)
    return out

if __name__ == '__main__':
    rows = list(corpora())
    which = sys.argv[1] if len(sys.argv) > 1 else 'stress'
    budget = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    policy = sys.argv[3] if len(sys.argv) > 3 else 'frac_mass'
    n_jobs = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    start_policy = sys.argv[5] if len(sys.argv) > 5 else 'all'
    sel = [r for r in rows if r[0] == which]
    print('selected', len(sel), 'budget', budget, 'policy', policy,
          'jobs', n_jobs, 'starts', start_policy)
    agg = dict(base_lp=0, base_nodes=0, base_t=0, lp=0, nodes=0, cert=0,
               t=0, probes=0, forbid=0, ok=0, n=0)
    for tag, name, idx, inst, known in sel:
        for h, label in ((known - 1, 'NO'), (known, 'YES')):
            b = pact_decide(inst, h, depthcap=None, nodecap=None)
            p = probe_decide(inst, h, budget, policy, n_jobs, start_policy)
            agg['base_lp'] += b['lp_solves'] + 1
            agg['base_nodes'] += b['nodes']
            agg['lp'] += p['lp_solves']
            agg['nodes'] += p['nodes']
            agg['cert'] += p['cert_lp']
            agg['probes'] += p['probes']
            agg['forbid'] += p['forbid']
            if p['verdict'] == b['verdict']:
                agg['ok'] += 1
            agg['n'] += 1
            print(f'{name:10s} {idx:2d} {label} base={b["nodes"]:3d}/{b["lp_solves"]+1:3d} '
                  f'probe={p["probes"]:2d} F={p["forbid"]:3d} '
                  f'new={p["nodes"]:3d}/{p["lp_solves"]:3d} '
                  f't={p["pre_t"]:.2f}+{p["t"]:.2f} v={p["verdict"]} vs {b["verdict"]}')
    print('AGG', agg)
