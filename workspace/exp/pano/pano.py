"""PANO-ICF: Pareto archive + neural portfolio over certified ICF arms."""
import sys
import time
import json
import math
import copy
import random
import collections

sys.path[:0] = ['exp/pano', 'exp/v9i', 'exp/v9m', 'exp/v8u', 'exp/v8o',
                'exp/v8i', 'exp/v8h', 'exp/v8j', 'exp/v8f', 'exp/v8e',
                'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

import numpy as np

import rafa
from rafa import (Node, leaves, open_leaves, global_L, rank_of,
                  RankLedger, choose_split, arbitrary_split,
                  lower_proof, FrontierCertificate, choose_h)
from prism import root_box, box_forbid
from chip import chip_bounds
from apex import bound_lb
from pact import PACT, pact_decide
from icf import PartialCertificate, ICFCertificate, cmax
from rdf import check_schedule
from po import heads_tails


def _tighten_U(inst, U, s, m):
    if s is None or m is None:
        return int(U), s, m
    c = cmax(inst, s)
    if c < U and check_schedule(inst, c, s, m):
        return int(c), list(s), list(m)
    return int(U), list(s), list(m)


def chip_init_state(inst, mode='chip'):
    b = chip_bounds(inst)
    if not b.get('ok'):
        return None
    U, s, m = _tighten_U(inst, b['ub'], b['schedule'], b['machine'])
    L = int(b['lb'])
    if L > U:
        L = int(b['lb'])
    p, co = lower_proof(inst, L)
    if p is None:
        return None
    lo, hi = root_box(inst, U)
    root = Node(lo, hi, L, p)
    if L >= U:
        root.dead = True
    return dict(root=root, U=U, schedule=list(s), machine=list(m),
                L0=L, U0=U, co=co)


def _initial_bounds(inst, init='chip'):
    if init == 'chip':
        b = chip_bounds(inst)
        if not b.get('ok'):
            return None
        U, s, m = _tighten_U(inst, b['ub'], b['schedule'], b['machine'])
        return int(b['lb']), U, s, m
    co = PACT(inst, pact_mode='complete', use_ga=False)
    lb, ub, s, m = co.initial_bounds()
    U, s, m = _tighten_U(inst, ub, s, m)
    return int(lb), U, s, m


def run_single(inst, known, name, idx, policy='geometric', eps=0.1,
               max_probes=64, cap=None, init='chip', audit=True):
    t0 = time.time()
    ib = _initial_bounds(inst, init)
    if ib is None:
        return dict(name=name, idx=idx, known=known, arm='single-' + policy,
                    init=init, ok=False, error='init', t=0.0)
    L, U, s, m = ib
    p, co = lower_proof(inst, L)
    if p is None:
        return dict(name=name, idx=idx, known=known, arm='single-' + policy,
                    init=init, ok=False, error='no-lb-proof', t=0.0)
    probes = lp = cert_lp = nodes = 0
    partial_ok = partial_fail = 0
    phase = 0
    snapshots = []
    steps = []

    def add_snapshot():
        snapshots.append(dict(L=L, U=U, cost=lp + cert_lp,
                              probes=probes, leaves=1,
                              exact=bool(L == U)))

    def audit_state():
        nonlocal partial_ok, partial_fail
        pc = PartialCertificate(inst, L, U, s, m, p, probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1

    add_snapshot()
    if audit:
        audit_state()
    while L < U and probes < max_probes:
        h = choose_h(policy, L, U, phase, eps)
        h = max(L, min(U - 1, int(h)))
        r = pact_decide(inst, h, depthcap=cap, nodecap=None)
        probes += 1
        phase += 1
        lp += r.get('lp_solves', 0)
        cert_lp += r.get('cert_lp', 0)
        nodes += r.get('nodes', 0)
        changed = False
        if r['verdict'] is False:
            pr = r['proof']
            if pr is None or pr.h != h:
                break
            L = h + 1
            p = pr
            co._record_proof(pr)
            changed = True
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                s, m = list(s2), list(m2)
                changed = True
        else:
            break
        steps.append(dict(h=h, L=L, U=U, v=r['verdict'],
                          lp=r.get('lp_solves', 0)))
        add_snapshot()
        if audit:
            audit_state()
        if not changed:
            break
    final = ICFCertificate(inst, U, s, m, p) if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, L, U, s, m, p, probe=probes)
    partial_final = bool(partial.audit_rdf())
    return dict(
        name=name, idx=idx, known=known, arm='single-' + policy,
        init=init, L=L, U=U, opt=U, lb=L, lb0=ib[0], ub0=ib[1],
        certified=bool(L == U and final_ok), audit=final_ok,
        exact=bool(L == U), partial_final=partial_final,
        partial_ok=partial_ok, partial_fail=partial_fail,
        probes=probes, lp=lp, cert_lp=cert_lp, nodes=nodes,
        cost=lp + cert_lp, leaves=1,
        snapshots=snapshots, steps=steps,
        stop_reason=('exact' if L == U else
                     ('budget' if probes >= max_probes else 'stuck')),
        t=round(time.time() - t0, 4),
        ok=bool(L == U and U == known and final_ok and
                partial_fail == 0 and partial_final),
    )


def run_frontier(inst, known, name, idx, policy='geometric', eps=0.1,
                 max_probes=64, max_leaves=64, cap=0, init='chip',
                 audit=False):
    t0 = time.time()
    old = rafa.init_state
    if init == 'chip':
        rafa.init_state = chip_init_state
    try:
        row = rafa.run_rafa(
            inst, known, name, idx, policy=policy, eps=eps, cap=cap,
            max_probes=max_probes, max_leaves=max_leaves,
            mode=('chip' if init == 'chip' else 'pact'),
            audit_states=audit)
    finally:
        rafa.init_state = old
    row['arm'] = 'frontier-%s-%s' % (policy, 'cap' if cap is not None
                                     else 'full')
    row['init'] = init
    row['cost'] = int(row.get('lp', 0)) + int(row.get('cert_lp', 0))
    row['snapshots'] = [dict(L=row.get('L', 0), U=row.get('U', 0),
                             cost=row['cost'], probes=row.get('probes', 0),
                             leaves=row.get('leaves', 1),
                             exact=bool(row.get('exact')))]
    row['t'] = round(time.time() - t0, 4)
    return row


_FEAT_CACHE = {}


def instance_features(inst):
    key = id(inst)
    if key in _FEAT_CACHE:
        return _FEAT_CACHE[key]
    n, m, p = inst['n'], inst['m'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    cp = max(est[i] + p[i] + q[i] for i in range(n))
    sp = sum(p)
    edges = sum(len(x) for x in inst['pred'])
    maxe = n * (n - 1) / 2.0 if n > 1 else 1.0
    elig = sum(len(set(e)) for e in inst['elig']) / max(1.0, n * m)
    restricted = sum(1 for e in inst['elig']
                     if len(set(e)) < m) / max(1.0, n)
    b = chip_bounds(inst)
    lb = float(b.get('lb', 0))
    ub = float(b.get('ub', 0))
    gap = max(0.0, ub - lb)
    v = np.array([
        n / 20.0, m / 4.0, sp / 200.0, cp / 100.0,
        max(p) / 10.0, (sp / max(1, n)) / 10.0,
        edges / maxe, elig, restricted,
        cp / max(1.0, sp / max(1, m)),
        lb / 100.0, ub / 100.0, gap / 100.0,
        (ub / max(1.0, lb)) - 1.0,
    ], dtype=float)
    _FEAT_CACHE[key] = v
    return v


class ParetoArchive:
    def __init__(self, cap=64):
        self.items = []
        self.cap = int(cap)

    @staticmethod
    def _key(r):
        return (int(r['L']), int(r['U']), int(r['cost']))

    def add(self, row):
        r = dict(row)
        L, U, c = int(r['L']), int(r['U']), int(r['cost'])
        for it in self.items:
            if (it['L'], it['U']) == (L, U):
                if c < it['cost']:
                    it.update(r)
                return
        for it in self.items:
            if (it['L'] >= L and it['U'] <= U and
                    it['cost'] <= c and
                    (it['L'] > L or it['U'] < U or it['cost'] < c)):
                return
        self.items = [
            it for it in self.items
            if not (L >= it['L'] and U <= it['U'] and c <= it['cost'] and
                    (L > it['L'] or U < it['U'] or c < it['cost']))
        ]
        self.items.append(r)
        if len(self.items) > self.cap:
            exact = [x for x in self.items if x['L'] == x['U']]
            exact.sort(key=lambda x: x['cost'])
            rest = [x for x in self.items if x['L'] != x['U']]
            rest.sort(key=lambda x: (x['U'] - x['L'], x['cost']))
            self.items = exact[:max(1, self.cap // 2)] + rest
            self.items = self.items[:self.cap]

    def front(self):
        return sorted(self.items, key=lambda x: (x['cost'], x['U'] - x['L']))

    def best_exact(self):
        ex = [x for x in self.items if x['L'] == x['U']]
        return min(ex, key=lambda x: x['cost']) if ex else None

    def best_partial(self):
        return min(self.items, key=lambda x: (x['U'] - x['L'], x['cost']))


def run_arm(inst, known, name, idx, arm, max_probes=64, max_leaves=64,
            eps=0.1, init='chip', audit=False):
    if arm.startswith('single-'):
        pol = arm[len('single-'):]
        return run_single(inst, known, name, idx, policy=pol, eps=eps,
                          max_probes=max_probes, init=init, audit=audit)
    if arm.startswith('frontier-'):
        rest = arm[len('frontier-'):]
        cap = None
        if rest.endswith('-cap'):
            rest = rest[:-4]
            cap = 0
        elif rest.endswith('-full'):
            rest = rest[:-5]
            cap = None
        return run_frontier(inst, known, name, idx, policy=rest, eps=eps,
                            max_probes=max_probes, max_leaves=max_leaves,
                            cap=cap, init=init, audit=audit)
    raise ValueError('unknown arm %r' % (arm,))


def simulate_portfolio(arm_rows, selection, name='', idx=0, known=None,
                       cap=64):
    archive = ParetoArchive(cap=cap)
    runs = []
    cum = 0
    for a in selection:
        r = dict(arm_rows[a])
        base = cum
        arm_cost = int(r.get('cost', 0))
        for snap in r.get('snapshots') or [r]:
            sr = dict(r)
            sr.update(L=snap.get('L'), U=snap.get('U'),
                      cost=base + int(snap.get('cost', 0)),
                      probes=snap.get('probes', r.get('probes', 0)),
                      leaves=snap.get('leaves', r.get('leaves', 1)),
                      exact=bool(snap.get('exact', False)))
            archive.add(sr)
        cum += arm_cost
        r['arm_cost'] = arm_cost
        r['cost'] = cum
        runs.append(r)
        if r.get('exact') or r.get('certified'):
            break
    exact_runs = [r for r in runs if r.get('exact')]
    if exact_runs:
        best = min(exact_runs, key=lambda x: x['cost'])
    else:
        best = archive.best_partial()
    return dict(
        name=name, idx=idx, known=known,
        selection=list(selection), runs=runs,
        n_runs=len(runs), total_cost=cum,
        L=best['L'], U=best['U'], exact=bool(best['L'] == best['U']),
        certified=bool(best['L'] == best['U'] and
                       best.get('certified', True)),
        archive=archive.front(),
        archive_size=len(archive.items),
        best_arm=best.get('arm'),
        t=round(sum(r.get('t', 0.0) for r in runs), 4),
        audit=all(r.get('partial_final', r.get('audit', False))
                  for r in runs),
    )


def synthetic_corpus():
    d = json.load(open('exp/v9i/synthetic.json'))
    for r in d['rows']:
        yield ('synth', 'synth', r['seed'], r['inst'], r['opt'])


def corpora():
    from icf import corpora as inner
    for tag, name, idx, inst, known in inner():
        yield tag, name, idx, inst, known
