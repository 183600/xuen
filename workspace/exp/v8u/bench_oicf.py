"""Benchmark O-ICF: order-online list scheduling and rolling lookahead.

The corpus has no release dates, so the online order is a topological
permutation of the known jobs.  The one-pass scheduler commits each job
immediately in that order.  The rolling scheduler keeps a lookahead
buffer, solves the buffered subproblem exactly with PACT, and commits one
job (receding horizon).  A full buffer (b = n) is exact by induction.
"""
import json
import sys
import time
import statistics
import collections

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from oicf import (corpora, random_topo_order, schedule_list,
                  run_rolling, check_schedule, cmax, lower_bound,
                  OnlinePartialCertificate)
from pact import pact_decide
from icf import ICFCertificate


class RegretCertificate:
    """Offline-audited regret interval: OPT proof + an online schedule."""

    kind = 'oicf-regret'

    def __init__(self, inst, opt, schedule, machine, proof):
        self.inst = inst
        self.opt = int(opt)
        self.schedule = list(schedule)
        self.machine = list(machine)
        self.proof = proof

    def audit_rdf(self):
        try:
            if self.proof is None or self.proof.h != self.opt - 1:
                return False
            if not self.proof.audit_rdf():
                return False
            c = cmax(self.inst, self.schedule)
            if c < self.opt:
                return False
            return bool(check_schedule(self.inst, c, self.schedule,
                                       self.machine))
        except Exception:
            return False


def summary(xs):
    xs = sorted(xs)
    return dict(n=len(xs), mean=round(statistics.mean(xs), 4),
                max=round(max(xs), 4),
                p95=round(xs[min(len(xs) - 1, int(0.95 * len(xs)))], 4))


def list_experiment(rows):
    keys = ('critical', 'random', 'lpt', 'est',
            'reverse-critical')
    out = {k: [] for k in keys}
    random20 = []
    for tag, name, idx, inst, known in rows:
        for key in keys:
            order = random_topo_order(inst, seed=12345, key=key)
            s, m, c = schedule_list(inst, order)
            out[key].append(dict(corpus=tag, name=name, idx=idx,
                                 known=known, opt=c,
                                 ratio=round(c / known, 6),
                                 ok=bool(check_schedule(inst, c, s, m))))
        rs = []
        for seed in range(20):
            order = random_topo_order(inst, seed=seed, key='random')
            s, m, c = schedule_list(inst, order)
            rs.append(c / known)
        random20.append(dict(corpus=tag, name=name, idx=idx,
                             known=known, mean=round(statistics.mean(rs), 6),
                             max=round(max(rs), 6),
                             opt=sum(1 for r in rs if r <= 1 + 1e-12)))
    summary_out = {}
    for key in keys:
        xs = [r['ratio'] for r in out[key]]
        summary_out[key] = summary(xs)
        summary_out[key]['opt'] = sum(1 for r in out[key]
                                      if r['opt'] == r['known'])
        summary_out[key]['ok'] = sum(1 for r in out[key] if r['ok'])
        by = collections.defaultdict(list)
        for r in out[key]:
            by[r['corpus']].append(r['ratio'])
        summary_out[key]['by_corpus'] = {
            k: round(statistics.mean(v), 4) for k, v in by.items()}
    xs = [r['mean'] for r in random20]
    summary_out['random20'] = summary(xs)
    summary_out['random20']['frac_opt'] = round(
        sum(r['opt'] for r in random20) / (20 * len(random20)), 4)
    summary_out['random20']['worst_inst_max'] = round(
        max(r['max'] for r in random20), 4)
    return dict(rows=out, random20=random20, summary=summary_out)


def pick_subset(rows):
    base = rows[:8]
    pert = rows[141:149]
    stress = rows[201:209]
    return base + pert + stress


def rolling_experiment(rows):
    sel = pick_subset(rows)
    out = []
    for tag, name, idx, inst, known in sel:
        order = random_topo_order(inst, seed=1, key='critical')
        n = inst['n']
        for policy, place in (('R', 'optimal'), ('G', 'greedy')):
            for b in (1, 2, 3, 4, 5, n):
                t0 = time.time()
                r = run_rolling(inst, order, b, commit_rule='earliest',
                                place=place, audit=True)
                dt = time.time() - t0
                row = dict(corpus=tag, name=name, idx=idx, known=known,
                           n=n, policy=policy, b=b,
                           opt=r.get('opt'),
                           ratio=round(r['opt'] / known, 6)
                           if r.get('opt') else None,
                           ok=bool(r.get('ok')),
                           exact_all=bool(r.get('exact_all')),
                           calls=r.get('calls'), lp=r.get('lp'),
                           cert_ok=r.get('cert_ok', 0),
                           cert_fail=r.get('cert_fail', 0),
                           proof_ok=r.get('proof_ok', 0),
                           bound_ok=r.get('bound_ok', 0),
                           states=len(r.get('states', [])),
                           state_opts=[s['opt_cond']
                                       for s in r.get('states', [])],
                           t=round(dt, 4))
                if b == n and r.get('ok'):
                    fp = r.get('full_proof')
                    cert = ICFCertificate(inst, known,
                                          r['starts'], r['machine'], fp)
                    row['final_cert'] = bool(fp is not None
                                             and cert.audit_rdf())
                out.append(row)
    summ = {}
    for policy, place in (('R', 'optimal'), ('G', 'greedy')):
        for b in (1, 2, 3, 4, 5, None):
            rs = [r for r in out if r['policy'] == policy
                  and (r['b'] == b if b is not None else r['b'] == r['n'])]
            if not rs:
                continue
            key = '%s-b%s' % (policy, 'n' if b is None else b)
            summ[key] = dict(
                n=len(rs),
                mean_ratio=round(statistics.mean(r['ratio'] for r in rs), 4),
                max_ratio=round(max(r['ratio'] for r in rs), 4),
                opt=sum(1 for r in rs if r['ratio'] <= 1 + 1e-12),
                ok=sum(1 for r in rs if r['ok']),
                exact=sum(1 for r in rs if r['exact_all']),
                calls=sum(r['calls'] for r in rs),
                lp=sum(r['lp'] for r in rs),
                cert_ok=sum(r['cert_ok'] for r in rs),
                cert_fail=sum(r['cert_fail'] for r in rs),
                proof_ok=sum(r['proof_ok'] for r in rs),
                bound_ok=sum(r['bound_ok'] for r in rs),
                t=round(sum(r['t'] for r in rs), 3),
            )
    return dict(rows=out, summary=summ)


def certificate_sample(rows):
    sel = rows[:4] + rows[141:145] + rows[201:205]
    out = []
    for tag, name, idx, inst, known in sel:
        order = random_topo_order(inst, seed=1, key='critical')
        s, m, c = schedule_list(inst, order)
        t0 = time.time()
        r = pact_decide(inst, known - 1, depthcap=None, nodecap=None)
        proof = r.get('proof') if r.get('verdict') is False else None
        cert = RegretCertificate(inst, known, s, m, proof)
        pc = OnlinePartialCertificate(
            inst, {}, s, m, lower_bound(inst),
            state={'lb_mode': 'global'})
        out.append(dict(corpus=tag, name=name, idx=idx, known=known,
                        opt=c, ratio=round(c / known, 6),
                        schedule_ok=bool(check_schedule(inst, c, s, m)),
                        proof=bool(proof is not None),
                        regret_audit=bool(cert.audit_rdf()),
                        partial_audit=bool(pc.audit_rdf()),
                        lb=lower_bound(inst),
                        gap=c - known,
                        t=round(time.time() - t0, 4)))
    return dict(rows=out,
                n=len(out),
                regret_ok=sum(1 for r in out if r['regret_audit']),
                partial_ok=sum(1 for r in out if r['partial_audit']),
                schedule_ok=sum(1 for r in out if r['schedule_ok']),
                gap=sum(r['gap'] for r in out))


def main():
    rows = list(corpora())
    t0 = time.time()
    le = list_experiment(rows)
    with open('exp/v8u/bench_oicf_list.json', 'w') as f:
        json.dump(le, f, indent=1)
    print('LIST', json.dumps(le['summary'], sort_keys=True))
    print('list wall', round(time.time() - t0, 2))

    t0 = time.time()
    re = rolling_experiment(rows)
    with open('exp/v8u/bench_oicf_rolling.json', 'w') as f:
        json.dump(re, f, indent=1)
    print('ROLL', json.dumps(re['summary'], sort_keys=True))
    print('rolling wall', round(time.time() - t0, 2))

    t0 = time.time()
    ce = certificate_sample(rows)
    with open('exp/v8u/bench_oicf_cert.json', 'w') as f:
        json.dump(ce, f, indent=1)
    print('CERT', {k: v for k, v in ce.items() if k != 'rows'})
    print('cert wall', round(time.time() - t0, 2))


if __name__ == '__main__':
    main()
