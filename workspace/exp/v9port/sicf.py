"""SICF-P: streaming invariant-carrying frontier with portable certificates.

v9.0 ICF-PACT keeps a partial certificate

    C = (L, U, s, m, pi),   pi : NO(L-1), Cmax(s)=U, L<=U.

SICF-P adds a *portable* certificate layer for a stream of instances.
For two instances I and I' with the same job set and machine set write

    I' >= I   iff   p'_i >= p_i,  pred'_i superset pred_i,
                    elig'_i subset elig_i  for all i.

Every feasible schedule of I' is feasible for I.  Therefore

    NO_I(h)  =>  NO_{I'}(h)          (lower-bound lifting)
    YES_I(h) =>  YES_{I'}(h)         (upper-bound lifting, I' <= I)

A cached certificate can thus certify a bound for a later instance
without re-running the oracle.  The cache is a stream summary; each
entry stores a local or lifted proof and a verified schedule.  A target
first takes the strongest lifted lower bound and upper bound, then runs
the ordinary ICF loop on the residual bracket.  The probe order depends
on which side was reused: lower-first for a lifted L, upper-first for a
lifted U.

The stream state is

    (I_t, L_t, U_t, s_t, m_t, pi_t, K_t, prov_t)

where K_t is the cache and prov_t records the reused sides.  The
invariant is the ICF invariant plus cache soundness plus provenance.
Every intermediate state is a valid partial certificate; L=U is an
optimality certificate.  The amortized theorem is a chain bound: in a
dominance chain with constant OPT, the seed pays the full solve and each
later instance pays at most one probe for the missing side.
"""
import sys
import time
import random
import collections

sys.path[:0] = ['exp/v9port', 'exp/v8u', 'exp/v8c', 'exp/v8o',
                'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e',
                'exp/v8g', 'exp/v60', 'exp/v13', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61']

from icf import (corpora, cmax, run_icf, PartialCertificate,
                 ICFCertificate)
from chip import base_bounds, order_portfolio
from cab import _greedy_rank
from apex import Proof, BoundProof
from rdf import check_schedule


def instance_key(inst):
    return (inst['n'], inst['m'],
            tuple(tuple(sorted(x)) for x in inst['pred']),
            tuple(tuple(sorted(x)) for x in inst['elig']))


def dominates(hard, easy):
    """True iff every feasible schedule of ``hard`` is feasible for ``easy``."""
    if hard['n'] != easy['n'] or hard['m'] != easy['m']:
        return False
    if any(x < y for x, y in zip(hard['p'], easy['p'])):
        return False
    for i in range(hard['n']):
        if not set(easy['pred'][i]) <= set(hard['pred'][i]):
            return False
        if not set(hard['elig'][i]) <= set(easy['elig'][i]):
            return False
    return True


def strictly_dominates(hard, easy):
    return dominates(hard, easy) and not dominates(easy, hard)


def equivalent(a, b):
    return dominates(a, b) and dominates(b, a)


class DominanceNO(Proof):
    """NO(h) for a target instance, lifted from an easier source."""

    kind = 'dom-no'

    def __init__(self, target, source, h, source_proof):
        super().__init__(target, h)
        self.source = source
        self.source_proof = source_proof
        self.forbid0 = frozenset()

    def audit_rdf(self):
        try:
            if self.source_proof is None:
                return False
            if self.source_proof.h != self.h:
                return False
            if not dominates(self.inst, self.source):
                return False
            return bool(self.source_proof.audit_rdf())
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class DominanceYES:
    """A schedule for a target instance, lifted from a harder source."""

    kind = 'dom-yes'

    def __init__(self, target, source, h, schedule, machine):
        self.inst = target
        self.source = source
        self.h = int(h)
        self.schedule = list(schedule)
        self.machine = list(machine)

    def audit_rdf(self):
        try:
            if not dominates(self.source, self.inst):
                return False
            return bool(check_schedule(self.source, self.h,
                                       self.schedule, self.machine))
        except Exception:
            return False


class CacheEntry:
    def __init__(self, inst, L, U, schedule, machine, proof,
                 base_inst, base_proof, corpus='', name='', idx=0,
                 known=None):
        self.inst = inst
        self.L = int(L)
        self.U = int(U)
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.proof = proof
        self.base_inst = base_inst
        self.base_proof = base_proof
        self.corpus = corpus
        self.name = name
        self.idx = idx
        self.known = known

    def key(self):
        return (self.corpus, self.name, self.idx)


class StreamCache:
    def __init__(self):
        self.entries = []
        self.lb_hits = 0
        self.ub_hits = 0
        self.checks = 0

    def best_lb(self, inst):
        best = None
        for e in self.entries:
            if dominates(inst, e.inst):
                self.checks += 1
                if best is None or e.L > best.L:
                    best = e
        if best is not None:
            self.lb_hits += 1
        return best

    def best_ub(self, inst):
        best = None
        for e in self.entries:
            if dominates(e.inst, inst):
                self.checks += 1
                if best is None or e.U < best.U:
                    best = e
        if best is not None:
            self.ub_hits += 1
        return best

    def add(self, inst, L, U, schedule, machine, proof,
            base_inst=None, base_proof=None, **kw):
        if base_inst is None:
            base_inst = inst
        if base_proof is None:
            base_proof = proof
        self.entries.append(CacheEntry(inst, L, U, schedule, machine,
                                       proof, base_inst, base_proof,
                                       **kw))

    def prune(self):
        """Keep the Pareto front of entries for lower and upper reuse."""
        keep = []
        for i, e in enumerate(self.entries):
            dominated = False
            for j, f in enumerate(self.entries):
                if i == j:
                    continue
                lower_kills = (dominates(f.inst, e.inst)
                               and f.L >= e.L
                               and (f.L > e.L or f.U <= e.U))
                upper_kills = (dominates(e.inst, f.inst)
                               and f.U <= e.U
                               and (f.U < e.U or f.L >= e.L))
                if lower_kills or upper_kills:
                    dominated = True
                    break
            if not dominated:
                keep.append(e)
        self.entries = keep
        return len(keep)


def local_init(inst):
    """Cheap certified initialization: bound proof + greedy portfolio."""
    lb, ub, s, m, est, q = base_bounds(inst)
    if ub is None:
        return None
    for _, rank in order_portfolio(inst, est, q, ub):
        g = _greedy_rank(inst, rank)
        if g is not None and g[2] < ub:
            ub, s, m = g[2], g[0], g[1]
    proof = BoundProof(inst, lb - 1, lb)
    if not proof.audit_rdf():
        return None
    if not check_schedule(inst, ub, s, m):
        return None
    return int(lb), int(ub), list(s), list(m), proof


def _policy(prov, policy_mode):
    if policy_mode == 'lower':
        return 'lower-first'
    if policy_mode == 'upper':
        return 'upper-first'
    if 'ub' in prov and 'lb' not in prov:
        return 'upper-first'
    return 'lower-first'


def _run_strong_instance(inst, known, name, idx, cache, corpus,
                         policy_mode, max_probes):
    t0 = time.time()
    pol = _policy([], policy_mode)
    row = run_icf(inst, known, name, idx, policy=pol,
                  max_probes=max_probes, collect_proof=True)
    row['corpus'] = corpus
    row['loc_lb'] = None
    row['loc_ub'] = None
    row['prov'] = []
    row['policy_used'] = pol
    final_proof = row.get('lb_proof')
    if isinstance(final_proof, DominanceNO):
        cache_base_inst = final_proof.source
        cache_base_proof = final_proof.source_proof
    else:
        cache_base_inst = inst
        cache_base_proof = final_proof
    if row.get('lb') is not None and row.get('opt') is not None:
        cache.add(inst, row['lb'], row['opt'], row.get('schedule'),
                  row.get('machine'), final_proof,
                  base_inst=cache_base_inst, base_proof=cache_base_proof,
                  corpus=corpus, name=name, idx=idx, known=known)
    return row


def run_instance(inst, known, name, idx, cache, corpus='',
                 policy_mode='prov', max_probes=64,
                 fallback_strong=False, init_mode='local'):
    if init_mode == 'strong':
        return _run_strong_instance(inst, known, name, idx, cache,
                                    corpus, policy_mode, max_probes)
    t0 = time.time()
    loc = local_init(inst)
    if loc is None:
        return dict(corpus=corpus, name=name, idx=idx, known=known,
                    ok=False, certified=False, audit=False,
                    partial_fail=1, error='no-local', t=0.0)
    L0, U0, s0, m0, p0 = loc
    lb_src = cache.best_lb(inst)
    ub_src = cache.best_ub(inst)

    L, U = L0, U0
    s, m, proof = s0, m0, p0
    base_inst, base_proof = inst, p0
    prov = []

    if lb_src is not None and lb_src.L > L0:
        L = lb_src.L
        base_inst = lb_src.base_inst
        base_proof = lb_src.base_proof
        proof = DominanceNO(inst, base_inst, L - 1, base_proof)
        prov.append('lb')

    if ub_src is not None and ub_src.U < U0:
        if check_schedule(inst, ub_src.U, ub_src.schedule,
                          ub_src.machine):
            U = ub_src.U
            s = list(ub_src.schedule)
            m = list(ub_src.machine)
            prov.append('ub')

    if L > U:
        return dict(corpus=corpus, name=name, idx=idx, known=known,
                    ok=False, certified=False, audit=False,
                    partial_fail=1, error='L>U', L=L, U=U,
                    t=round(time.time() - t0, 4))

    if L == U:
        cert = ICFCertificate(inst, U, s, m, proof)
        ok = bool(cert.audit_rdf())
        row = dict(corpus=corpus, name=name, idx=idx, known=known,
                   opt=U, lb=L, lb0=L0, ub0=U0,
                   loc_lb=L0, loc_ub=U0,
                   certified=ok, audit=ok, proof=ok,
                   cert_h=U - 1, queries=0, probes=0,
                   pact_lp=0, pact_nodes=0, pact_cert_lp=0,
                   pin_lp=0, partial_ok=1, partial_fail=0,
                   partial_final=ok, unknown=0, steps=[],
                   proof_kind=getattr(proof, 'kind', None),
                   total_audit=ok, t=round(time.time() - t0, 4),
                   schedule=list(s), machine=list(m),
                   lb_proof=proof, prov=prov,
                   policy_used=None,
                   ok=bool(ok and U == known))
    else:
        pol = _policy(prov, policy_mode)
        row = run_icf(inst, known, name, idx, policy=pol,
                      max_probes=max_probes,
                      initial=(L, U, s, m, proof),
                      collect_proof=True)
        row['corpus'] = corpus
        row['loc_lb'] = L0
        row['loc_ub'] = U0
        row['prov'] = prov
        row['policy_used'] = pol

    if fallback_strong and not row.get('certified'):
        fb = run_icf(inst, known, name, idx, policy='lower-first',
                     max_probes=max_probes, collect_proof=True)
        fb['corpus'] = corpus
        fb['loc_lb'] = L0
        fb['loc_ub'] = U0
        fb['prov'] = list(prov) + ['fallback']
        fb['policy_used'] = 'strong-fallback'
        row = fb

    final_proof = row.get('lb_proof')
    if isinstance(final_proof, DominanceNO):
        cache_base_inst = final_proof.source
        cache_base_proof = final_proof.source_proof
    else:
        cache_base_inst = inst
        cache_base_proof = final_proof
    cache.add(inst, row.get('lb', L), row.get('opt', U),
              row.get('schedule'), row.get('machine'),
              final_proof, base_inst=cache_base_inst,
              base_proof=cache_base_proof, corpus=corpus, name=name,
              idx=idx, known=known)
    return row


def group_rows(rows):
    groups = collections.defaultdict(list)
    for r in rows:
        groups[instance_key(r[3])].append(r)
    return groups


def order_sweep(rows, seed_rule='min_gap'):
    locs = [(local_init(r[3]), r) for r in rows]
    locs = [(l, r) for l, r in locs if l is not None]
    if not locs:
        return list(rows)

    def coverage(r):
        return sum(1 for _, x in locs
                   if x is not r and (dominates(x[3], r[3])
                                      or dominates(r[3], x[3])))

    if seed_rule == 'min_gap':
        seed = min(locs, key=lambda x: (x[0][1] - x[0][0],
                                        sum(x[1][3]['p'])))
    elif seed_rule == 'max_cov':
        seed = max(locs, key=lambda x: (coverage(x[1]),
                                        -(x[0][1] - x[0][0])))
    elif seed_rule == 'median':
        seed = sorted(locs, key=lambda x: sum(x[1][3]['p']))[
            len(locs) // 2]
    else:
        raise ValueError(seed_rule)

    (_, _, _, _, _), sr = seed
    hard = [r for _, r in locs if r is not sr
            and strictly_dominates(r[3], sr[3])]
    easy = [r for _, r in locs if r is not sr
            and strictly_dominates(sr[3], r[3])]
    equal = [r for _, r in locs if r is not sr
             and equivalent(r[3], sr[3])]
    other = [r for _, r in locs if r is not sr
             and not dominates(r[3], sr[3])
             and not dominates(sr[3], r[3])]
    hard.sort(key=lambda r: (sum(r[3]['p']), r[4], r[2]))
    easy.sort(key=lambda r: (-sum(r[3]['p']), r[4], r[2]))
    return [sr] + hard + easy + equal + other


def run_stream(rows, order='arrival', seed_rule='min_gap',
               policy_mode='prov', seed=0, max_probes=64,
               do_prune=False, fallback_strong=True):
    t0 = time.time()
    cache = StreamCache()
    out = []
    if order == 'arrival':
        ordered = list(rows)
    elif order == 'random':
        ordered = list(rows)
        random.Random(seed).shuffle(ordered)
    elif order == 'sweep':
        groups = group_rows(rows)
        ordered = []
        for _, rs in sorted(groups.items(),
                            key=lambda kv: (-len(kv[1]), kv[0])):
            ordered.extend(order_sweep(rs, seed_rule=seed_rule))
    else:
        raise ValueError(order)
    for corpus, name, idx, inst, known in ordered:
        out.append(run_instance(inst, known, name, idx, cache,
                                corpus=corpus,
                                policy_mode=policy_mode,
                                max_probes=max_probes,
                                fallback_strong=fallback_strong))
        if do_prune:
            cache.prune()
    wall = time.time() - t0
    return out, cache, wall


def run_hybrid(rows, policy_mode='upper', seed_rule='min_gap',
               max_probes=64, fallback_strong=True,
               seed_policy_mode=None):
    if seed_policy_mode is None:
        seed_policy_mode = policy_mode
    t0 = time.time()
    cache = StreamCache()
    out = []
    groups = group_rows(rows)
    for _, rs in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        srs = order_sweep(rs, seed_rule=seed_rule)
        for j, r in enumerate(srs):
            corpus, name, idx, inst, known = r
            out.append(run_instance(
                inst, known, name, idx, cache, corpus=corpus,
                policy_mode=(seed_policy_mode if j == 0 else policy_mode),
                max_probes=max_probes,
                fallback_strong=fallback_strong,
                init_mode='strong' if j == 0 else 'local'))
    return out, cache, time.time() - t0


def run_from_scratch(rows, policy='lower-first', max_probes=64,
                     fallback_strong=True):
    t0 = time.time()
    out = []
    for corpus, name, idx, inst, known in rows:
        init = local_init(inst)
        r = run_icf(inst, known, name, idx, policy=policy,
                    max_probes=max_probes, initial=init,
                    collect_proof=True)
        if fallback_strong and not r.get('certified'):
            r = run_icf(inst, known, name, idx, policy=policy,
                        max_probes=max_probes, collect_proof=True)
            r['prov'] = ['fallback']
        else:
            r['prov'] = []
        r['corpus'] = corpus
        r['loc_lb'] = init[0] if init is not None else None
        r['loc_ub'] = init[1] if init is not None else None
        r['policy_used'] = policy
        out.append(r)
    return out, time.time() - t0


def run_strong(rows, policy='lower-first', max_probes=64):
    t0 = time.time()
    out = []
    for corpus, name, idx, inst, known in rows:
        r = run_icf(inst, known, name, idx, policy=policy,
                    max_probes=max_probes, collect_proof=True)
        r['corpus'] = corpus
        r['prov'] = []
        r['policy_used'] = policy
        out.append(r)
    return out, time.time() - t0


def summarize(rows, wall=None):
    prov = collections.Counter(tuple(r.get('prov', [])) for r in rows)
    return dict(
        n=len(rows),
        ok=sum(bool(r.get('ok')) for r in rows),
        certified=sum(bool(r.get('certified')) for r in rows),
        audit=sum(bool(r.get('audit')) for r in rows),
        partial_fail=sum(int(r.get('partial_fail', 0)) for r in rows),
        partial_ok=sum(int(r.get('partial_ok', 0)) for r in rows),
        queries=sum(int(r.get('queries', 0)) for r in rows),
        search_lp=sum(int(r.get('pact_lp', 0)) for r in rows),
        cert_lp=sum(int(r.get('pact_cert_lp', 0)) for r in rows),
        pin_lp=sum(int(r.get('pin_lp', 0)) for r in rows),
        total_lp=sum(int(r.get('pact_lp', 0)) +
                     int(r.get('pact_cert_lp', 0)) +
                     int(r.get('pin_lp', 0)) for r in rows),
        nodes=sum(int(r.get('pact_nodes', 0)) for r in rows),
        t=round(wall, 3) if wall is not None else
          round(sum(float(r.get('t', 0.0)) for r in rows), 3),
        prov={str(k): v for k, v in sorted(prov.items())},
        zero_probe=sum(1 for r in rows if int(r.get('queries', 0)) == 0),
    )


def all_rows():
    return [(c, name, idx, inst, known)
            for c, name, idx, inst, known in corpora()]
