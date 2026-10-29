"""PTB-ICF: Pareto tight-bound neighborhood certificates for PACT.

The v9.0 ICF state is kept unchanged:

    C = (L, U, s, m, pi),   pi : NO(L-1), Cmax(s)=U, L<=U.

PTB adds a verified Pareto archive A of schedules.  Every schedule in A
has passed check_schedule.  The archive is non-dominated in

    (Cmax, sum_i C_i).

A *tight-bound probe* at horizon h solves the root SD LP once, then
tries to realise h by LP-guided serial SGS, randomized rounding, and
destroy/repair neighborhoods.  A candidate with Cmax <= h is a YES
witness; a candidate with Cmax < U but > h still improves the upper
bound and is retained in A.  If the primal attempt fails, the same root
LP is handed to PACT, so the exact decision oracle pays no duplicate
root solve.

The important safety rule is unchanged: only a check_schedule-verified
schedule updates U, and only an audited PACT NO proof updates L.
"""

import sys
import random
import math
import time

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from pact import PACT, pact_decide, _integral_schedule
from icf import (PartialCertificate, ICFCertificate, cmax, corpora,
                 _choose_h)
from sage import _elig_aware
from sdecc import SDLP
from po import heads_tails
from cab import _greedy_rank
from lns import greedy_repair
from rdf import check_schedule


class ParetoArchive:
    """Verified schedules, non-dominated in (Cmax, total completion)."""

    def __init__(self, inst, pareto=True):
        self.inst = inst
        self.pareto = bool(pareto)
        self.items = []
        self.seen = set()
        self.added = 0
        self.rejected = 0

    def _key(self, starts, machs):
        return (tuple(starts), tuple(machs))

    def add(self, starts, machs, source='primal', h=None):
        if starts is None or machs is None:
            return None
        if not check_schedule(self.inst, cmax(self.inst, starts),
                              starts, machs):
            self.rejected += 1
            return None
        key = self._key(starts, machs)
        if key in self.seen:
            return None
        cm = cmax(self.inst, starts)
        flow = sum(starts[i] + self.inst['p'][i]
                   for i in range(self.inst['n']))
        if not self.pareto:
            if self.items:
                b = self.items[0]
                if b[0] <= cm and b[3][1] <= flow:
                    self.rejected += 1
                    return None
                if cm <= b[0] and flow <= b[3][1]:
                    self.seen.discard(self._key(b[1], b[2]))
                    self.items = []
            item = (cm, list(starts), list(machs), (cm, flow))
            self.items = [item]
            self.seen.add(key)
            self.added += 1
            return item
        for _, _, _, b in self.items:
            if b[0] <= cm and b[1] <= flow:
                self.rejected += 1
                return None
        keep = []
        for a, s, m, b in self.items:
            if cm <= b[0] and flow <= b[1]:
                self.seen.discard(self._key(s, m))
                continue
            keep.append((a, s, m, b))
        item = (cm, list(starts), list(machs), (cm, flow))
        keep.append(item)
        keep.sort(key=lambda x: (x[0], x[3][1], x[1], x[2]))
        self.items = keep
        self.seen.add(key)
        self.added += 1
        return item

    def best(self):
        if not self.items:
            return None
        return self.items[0]

    def top(self, k):
        out = []
        for _, s, m, _ in self.items[:max(0, k)]:
            out.append((s, m))
        return out

    def audit(self):
        for _, s, m, _ in self.items:
            if not check_schedule(self.inst, cmax(self.inst, s), s, m):
                return False
        return True


def _lp_root(inst, h, forbid0=None):
    est, q = heads_tails(inst, 0, [0] * inst['n'])
    lp = SDLP(inst, h, est, q, use_dom=True,
              elig_aware=_elig_aware(inst), forbid=forbid0)
    if lp.N == 0:
        return lp, None, 2
    res = lp.solve()
    return lp, res, res.status


def _dist(lp, z):
    out = {}
    for i in range(lp.n):
        d = {}
        mass = 0.0
        for c, key in enumerate(lp.cols):
            if key[0] == i:
                v = float(z[c])
                if v > 1e-9:
                    d[key[-1]] = d.get(key[-1], 0.0) + v
                    mass += v
        if mass <= 1e-12:
            out[i] = [(lp.est[i], 1.0)]
        else:
            out[i] = [(t, v / mass) for t, v in sorted(d.items())]
    return out


def _rank_mean(dist):
    return {i: sum(t * v for t, v in d) for i, d in dist.items()}


def _rank_argmax(dist):
    return {i: max(d, key=lambda x: x[1])[0] for i, d in dist.items()}


def _sample_rank(dist, rng):
    rank = {}
    for i, d in dist.items():
        u = rng.random()
        acc = 0.0
        t = d[-1][0]
        for tt, v in d:
            acc += v
            if u <= acc:
                t = tt
                break
        rank[i] = t + rng.random() * 1e-6
    return rank


def _violators(inst, h, starts):
    p = inst['p']
    _, q = heads_tails(inst, 0, [0] * inst['n'])
    return [i for i in range(inst['n'])
            if starts[i] + p[i] + q[i] > h]


def _neighborhood(inst, h, starts, lp, dist, kmax, rng):
    p = inst['p']
    n = inst['n']
    viol = _violators(inst, h, starts)
    R = set(viol)
    pool = []
    for i in range(n):
        if i in R:
            continue
        frac = 0.0
        for t, v in dist.get(i, []):
            if 1e-7 < v < 1 - 1e-7:
                frac += v
        crit = starts[i] + p[i] - h
        pool.append((frac, crit, p[i], rng.random(), i))
    pool.sort(reverse=True)
    need = max(0, min(kmax, n) - len(R))
    for _, _, _, _, i in pool[:need]:
        R.add(i)
    return R


def primal_probe(inst, h, archive, forbid0=None, samples=48,
                 repairs=6, kmax=14, seed=0, harvest=True):
    t0 = time.time()
    lp, res, status = _lp_root(inst, h, forbid0)
    stats = dict(lp=1, status=status, samples=0, greedy=0,
                 feasible=0, repairs=0, archive=0, yes=False)
    if archive is not None:
        for s, m in archive.top(3):
            if cmax(inst, s) <= h:
                stats['yes'] = True
                stats['archive_hit'] = True
                return dict(kind='yes', lp=lp, res=res,
                            schedule=s, machine=m, stats=stats,
                            t=round(time.time() - t0, 4))
    if status == 2:
        return dict(kind='no_root', lp=lp, res=res, schedule=None,
                    machine=None, stats=stats,
                    t=round(time.time() - t0, 4))
    if status != 0:
        return dict(kind='fail', lp=lp, res=res, schedule=None,
                    machine=None, stats=stats,
                    t=round(time.time() - t0, 4))
    elig = _elig_aware(inst)
    got = _integral_schedule(inst, lp, res.x, elig)
    if got is not None:
        s, m = got
        cm = cmax(inst, s)
        if cm <= h:
            stats['yes'] = True
            stats['integral_yes'] = True
            if archive is not None:
                archive.add(s, m, 'integral', h)
            return dict(kind='yes', lp=lp, res=res, schedule=s,
                        machine=m, stats=stats,
                        t=round(time.time() - t0, 4))
        if archive is not None and harvest:
            archive.add(s, m, 'integral', h)
    dist = _dist(lp, res.x)
    rng = random.Random(20261026 + seed * 100003 + h * 7919)
    ranks = [_rank_mean(dist), _rank_argmax(dist)]
    ranks += [_sample_rank(dist, rng) for _ in range(samples)]
    for rank in ranks:
        stats['samples'] += 1
        g = _greedy_rank(inst, rank)
        if g is None:
            continue
        s, m = g[0], g[1]
        stats['greedy'] += 1
        cm = cmax(inst, s)
        if archive is not None and harvest:
            archive.add(s, m, 'greedy', h)
        if cm <= h and check_schedule(inst, h, s, m):
            stats['yes'] = True
            stats['greedy_yes'] = True
            return dict(kind='yes', lp=lp, res=res, schedule=s,
                        machine=m, stats=stats,
                        t=round(time.time() - t0, 4))
    seeds = []
    if archive is not None:
        for s, m in archive.top(repairs):
            if cmax(inst, s) > h:
                seeds.append((s, m))
    for s0, m0 in seeds:
        for _ in range(2):
            R = _neighborhood(inst, h, s0, lp, dist, kmax, rng)
            if not R:
                continue
            stats['repairs'] += 1
            s, m = greedy_repair(inst, h, R, s0, m0, rng)
            if s is None:
                continue
            if archive is not None and harvest:
                archive.add(s, m, 'repair', h)
            if cmax(inst, s) <= h and check_schedule(inst, h, s, m):
                stats['yes'] = True
                stats['repair_yes'] = True
                return dict(kind='yes', lp=lp, res=res, schedule=s,
                            machine=m, stats=stats,
                            t=round(time.time() - t0, 4))
    if archive is not None:
        stats['archive'] = len(archive.items)
    return dict(kind='fail', lp=lp, res=res, schedule=None,
                machine=None, stats=stats,
                t=round(time.time() - t0, 4))


def exact_with_root(inst, h, lp, res, forbid0=None):
    return pact_decide(inst, h, depthcap=None, nodecap=None,
                       root_lp=lp, root_res=res, forbid0=forbid0)


def run_ptb(inst, known, name, idx, policy='ptb', max_probes=64,
            use_upper=False, upper_min_gap=8,
            samples=48, upper_samples=8,
            repairs=0, upper_repairs=0, kmax=14,
            pareto=True, harvest=True, initial=None, seed=0):
    t0 = time.time()
    if initial is None:
        co = PACT(inst, pact_mode='complete', use_ga=False)
        lb, ub, sched, mach = co.initial_bounds()
        if ub is None:
            return dict(name=name, idx=idx, known=known, policy=policy,
                        ok=False, error='no-initial-ub', t=0.0)
        L, U = int(lb), int(ub)
        sched = list(sched) if sched is not None else None
        mach = list(mach) if mach is not None else None
        lb_proof = co._ensure_lb_proof(L)
        if lb_proof is None:
            r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
            if r['verdict'] is False:
                lb_proof = r['proof']
        pin_lp = getattr(co, 'pin_lp', 0)
    else:
        L, U, sched, mach, lb_proof = initial
        L, U = int(L), int(U)
        sched = list(sched) if sched is not None else None
        mach = list(mach) if mach is not None else None
        pin_lp = 0
    if lb_proof is None or sched is None or mach is None:
        return dict(name=name, idx=idx, known=known, policy=policy,
                    ok=False, error='bad-initial-state', t=0.0)

    archive = ParetoArchive(inst, pareto=pareto)
    archive.add(sched, mach, 'initial', U)
    probes = 0
    primal_calls = 0
    primal_lp = 0
    pact_lp = 0
    pact_nodes = 0
    pact_cert_lp = 0
    primal_yes = 0
    primal_no_root = 0
    primal_fail = 0
    upper_calls = 0
    upper_drops = 0
    archive_drops = 0
    archive_yes = 0
    integral_yes = 0
    greedy_yes = 0
    repair_yes = 0
    primal_samples = 0
    primal_repairs = 0
    partial_ok = 0
    partial_fail = 0
    steps = []
    lb0, ub0 = L, U
    first = True
    upper_fail = 0
    max_upper_fail = 2
    unknown_heights = set()

    def audit_state():
        nonlocal partial_ok, partial_fail
        pc = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1

    def update_from_archive():
        nonlocal U, sched, mach, archive_drops
        b = archive.best()
        if b is None:
            return False
        cm, s, m, _ = b
        if cm < U:
            U = cm
            sched = list(s)
            mach = list(m)
            archive_drops += 1
            return True
        return False

    def absorb(r):
        nonlocal U, sched, mach
        if r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if check_schedule(inst, c2, s2, m2):
                archive.add(s2, m2, 'exact', c2)
                if c2 < U:
                    U = c2
                    sched, mach = list(s2), list(m2)
            return 'yes'
        return 'unknown'

    audit_state()
    while L < U and probes < max_probes:
        update_from_archive()
        if L == U:
            break
        gap = U - L
        action = 'lower'
        h = L
        if use_upper and gap >= upper_min_gap \
                and upper_fail < max_upper_fail \
                and (U - 1) not in unknown_heights:
            action = 'upper'
            h = U - 1
            upper_calls += 1
        elif L in unknown_heights:
            cand = [t for t in range(L, U)
                    if t not in unknown_heights]
            if not cand:
                break
            h = cand[len(cand) // 2]
        r = primal_probe(inst, h, archive,
                         samples=(samples if action == 'lower'
                                  else upper_samples),
                         repairs=(repairs if action == 'lower'
                                  else upper_repairs),
                         kmax=kmax, seed=seed + probes,
                         harvest=harvest)
        primal_calls += 1
        primal_lp += r['stats']['lp']
        primal_samples += r['stats'].get('samples', 0)
        primal_repairs += r['stats'].get('repairs', 0)
        if r['kind'] == 'yes':
            primal_yes += 1
            if r['stats'].get('archive_hit'):
                archive_yes += 1
            if r['stats'].get('integral_yes'):
                integral_yes += 1
            if r['stats'].get('greedy_yes'):
                greedy_yes += 1
            if r['stats'].get('repair_yes'):
                repair_yes += 1
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                if action == 'upper':
                    upper_drops += 1
                U = c2
                sched, mach = list(s2), list(m2)
                archive.add(s2, m2, 'primal', c2)
            steps.append(dict(h=h, action=action, v=True,
                              primal=True, cmax=c2, L1=L, U1=U))
            audit_state()
            continue
        if r['kind'] == 'no_root':
            primal_no_root += 1
            rr = exact_with_root(inst, h, r['lp'], r['res'])
            probes += 1
            pact_lp += rr.get('lp_solves', 0)
            pact_nodes += rr.get('nodes', 0)
            pact_cert_lp += rr.get('cert_lp', 0)
            if rr['verdict'] is False:
                L = h + 1
                lb_proof = rr['proof']
            elif rr['verdict'] is True:
                absorb(rr)
            else:
                unknown_heights.add(h)
            steps.append(dict(h=h, action=action, v=rr['verdict'],
                              primal=False, lp=rr.get('lp_solves', 0),
                              L1=L, U1=U))
            audit_state()
            continue
        primal_fail += 1
        if action == 'upper':
            update_from_archive()
            upper_fail += 1
            if U <= h:
                upper_fail = 0
            if gap == 1:
                rr = exact_with_root(inst, h, r['lp'], r['res'])
                probes += 1
                pact_lp += rr.get('lp_solves', 0)
                pact_nodes += rr.get('nodes', 0)
                pact_cert_lp += rr.get('cert_lp', 0)
                if rr['verdict'] is False:
                    L = h + 1
                    lb_proof = rr['proof']
                elif rr['verdict'] is True:
                    absorb(rr)
                steps.append(dict(h=h, action=action, v=rr['verdict'],
                                  primal=False,
                                  lp=rr.get('lp_solves', 0),
                                  L1=L, U1=U))
            else:
                steps.append(dict(h=h, action=action, v=None,
                                  primal=False, L1=L, U1=U))
            audit_state()
            continue
        upper_fail = 0
        rr = exact_with_root(inst, h, r['lp'], r['res'])
        probes += 1
        pact_lp += rr.get('lp_solves', 0)
        pact_nodes += rr.get('nodes', 0)
        pact_cert_lp += rr.get('cert_lp', 0)
        if rr['verdict'] is False:
            L = h + 1
            lb_proof = rr['proof']
        elif rr['verdict'] is True:
            absorb(rr)
        else:
            unknown_heights.add(h)
        steps.append(dict(h=h, action=action, v=rr['verdict'],
                          primal=False, lp=rr.get('lp_solves', 0),
                          L1=L, U1=U))
        audit_state()

    update_from_archive()
    final = ICFCertificate(inst, U, sched, mach, lb_proof) \
        if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                 probe=probes)
    partial_ok_final = bool(partial.audit_rdf())
    dt = time.time() - t0
    return dict(
        name=name, idx=idx, known=known, policy=policy,
        opt=U, lb=L, lb0=lb0, ub0=ub0,
        certified=bool(L == U and final_ok),
        audit=final_ok, proof=final_ok,
        cert_h=(U - 1 if L == U else None),
        queries=probes, probes=probes,
        primal_calls=primal_calls,
        primal_lp=primal_lp,
        primal_yes=primal_yes,
        primal_no_root=primal_no_root,
        primal_fail=primal_fail,
        upper_calls=upper_calls,
        upper_drops=upper_drops,
        archive_drops=archive_drops,
        archive_yes=archive_yes,
        integral_yes=integral_yes,
        greedy_yes=greedy_yes,
        repair_yes=repair_yes,
        primal_samples=primal_samples,
        primal_repairs=primal_repairs,
        pact_lp=pact_lp, pact_nodes=pact_nodes,
        pact_cert_lp=pact_cert_lp,
        total_lp=primal_lp + pact_lp + pact_cert_lp,
        pin_lp=pin_lp,
        archive=len(archive.items),
        archive_audit=archive.audit(),
        partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_ok_final,
        unknown=len(unknown_heights), steps=steps,
        proof_kind=(final.lb_proof.kind if final is not None else
                    getattr(lb_proof, 'kind', None)),
        t=round(dt, 4),
        ok=bool(L == U and U == known and final_ok and
                partial_fail == 0 and partial_ok_final and
                archive.audit()),
    )
