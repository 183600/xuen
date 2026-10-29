"""v10.0 COSA-ICF: cache-oblivious simulated annealing amplifier for ICF.

The trusted state remains the v9.0 partial certificate

    (L, U, s, m, pi),   pi : NO(L-1),   Cmax(s)=U,   L <= U.

COSA adds an untrusted multiscale primal search.  A proposal is decoded to
a feasible schedule, checked, and only then allowed to lower U.  A proposal
at Cmax=L closes the bracket.  The annealer can never move L or pi.

The neighborhood is a scale-free mixture of aligned dyadic blocks in time
and in priority rank.  At level l the block has size min(n, 2^l), and l is
drawn from a geometric distribution.  The level distribution is fixed
before seeing the cache, so the search schedule is cache-oblivious.
"""
import sys
import time
import math
import random

sys.path[:0] = ['exp/v9sail', 'exp/v9d', 'exp/v8u', 'exp/v8o',
                'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e',
                'exp/v8g', 'exp/v8c', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from sail import decode_dsu, topo_order
from rdf import check_schedule
from pact import PACT, pact_decide
from icf import (PartialCertificate, ICFCertificate, cmax, _choose_h,
                 corpora)


class COSAStats:
    __slots__ = ('decodes', 'iters', 'chains', 'hits', 'improvements',
                 'best', 'time', 'levels', 'blocks')

    def __init__(self):
        self.decodes = 0
        self.iters = 0
        self.chains = 0
        self.hits = 0
        self.improvements = 0
        self.best = None
        self.time = 0.0
        self.levels = {}
        self.blocks = 0


def _level_weights(maxlev, p):
    w = [p * (1.0 - p) ** l for l in range(maxlev + 1)]
    w[-1] += (1.0 - p) ** maxlev
    z = sum(w)
    return [x / z for x in w]


def cosa_anneal(inst, init_s, target, budget=20000, seed=7,
                alpha=0.999, T0_scale=0.5, p_level=0.7,
                mode='mixed', stats=None):
    """One annealing chain.  Returns (s, m, c, decodes, hit, stats)."""
    rng = random.Random(seed)
    n = inst['n']
    H = max(1, sum(inst['p']))
    st = stats if stats is not None else COSAStats()
    st.chains += 1
    t_start = time.time()
    keys = [float(init_s[i]) + rng.random() * 0.5 for i in range(n)]
    order = topo_order(keys, inst)
    res = decode_dsu(order, inst, H)
    st.decodes += 1
    st.iters += 1
    if res is None:
        st.time += time.time() - t_start
        return None, None, 10 ** 9, 0, False, st
    s, m, c = res
    best_s, best_m, best_c = list(s), list(m), c
    if best_c <= target:
        st.hits += 1
        st.best = best_c
        st.time += time.time() - t_start
        return best_s, best_m, best_c, 1, True, st
    T0 = max(1.0, c - target) * T0_scale
    T = T0
    Tend = 0.05
    maxlev = max(0, (n - 1).bit_length())
    levels = list(range(maxlev + 1))
    weights = _level_weights(maxlev, p_level)
    for it in range(1, budget):
        T = max(Tend, T * alpha)
        lev = rng.choices(levels, weights=weights, k=1)[0]
        st.levels[lev] = st.levels.get(lev, 0) + 1
        typ = rng.random()
        if mode == 'flat':
            pflat, ptime = 1.0, 1.0
        elif mode == 'time':
            pflat, ptime = 0.5, 1.0
        elif mode == 'rank':
            pflat, ptime = 0.5, 0.5
        else:
            pflat, ptime = 0.45, 0.75
        nk = keys[:]
        if typ < pflat or maxlev == 0:
            u, v = rng.sample(range(n), 2)
            nk[u], nk[v] = nk[v], nk[u]
            st.blocks += 1
        elif typ < ptime:
            ww = min(H, 1 << lev)
            a = rng.randrange(max(1, H - ww + 1))
            b = a + ww
            seg = [i for i in range(n) if a <= s[i] < b]
            if len(seg) >= 2:
                vals = sorted(keys[i] for i in seg)
                rng.shuffle(vals)
                for i, v in zip(seg, vals):
                    nk[i] = v
            else:
                u, v = rng.sample(range(n), 2)
                nk[u], nk[v] = nk[v], nk[u]
            st.blocks += 1
        else:
            bs = min(n, 1 << lev)
            start = rng.randrange(max(1, n - bs + 1))
            seg = order[start:start + bs]
            if len(seg) >= 2:
                vals = sorted(keys[i] for i in seg)
                rng.shuffle(vals)
                for i, v in zip(seg, vals):
                    nk[i] = v
            else:
                u, v = rng.sample(range(n), 2)
                nk[u], nk[v] = nk[v], nk[u]
            st.blocks += 1
        no = topo_order(nk, inst)
        rr = decode_dsu(no, inst, H)
        st.decodes += 1
        st.iters += 1
        if rr is None:
            continue
        ns, nm, nc = rr
        if nc < best_c:
            best_s, best_m, best_c = list(ns), list(nm), nc
            st.improvements += 1
            if best_c <= target:
                st.hits += 1
                st.best = best_c
                st.time += time.time() - t_start
                return best_s, best_m, best_c, st.decodes, True, st
        if nc <= c or rng.random() < math.exp(-(nc - c) / max(1e-9, T)):
            keys, s, m, c, order = nk, ns, nm, nc, no
    st.best = best_c
    st.time += time.time() - t_start
    return best_s, best_m, best_c, st.decodes, False, st


def cosa_portfolio(inst, init_s, init_m, init_c, target, budget=20000,
                   seeds=(0, 1, 2, 3), alpha=0.999, T0_scale=0.5,
                   p_level=0.7, mode='mixed'):
    """Run chains from the incumbent, stopping at the first certified hit."""
    best_s = list(init_s)
    best_m = list(init_m)
    best_c = int(init_c)
    st = COSAStats()
    hit = False
    per = max(1, budget // max(1, len(seeds)))
    for sd in seeds:
        s, m, c, dec, h, st = cosa_anneal(
            inst, best_s, target, budget=per, seed=sd, alpha=alpha,
            T0_scale=T0_scale, p_level=p_level, mode=mode, stats=st)
        if s is not None and c < best_c:
            if check_schedule(inst, c, s, m):
                best_s, best_m, best_c = s, m, c
        if h:
            hit = True
            break
    return best_s, best_m, best_c, hit, st


def run_cosa(inst, known, name, idx, policy='lower-first', max_probes=64,
             use_pact_init=True, initial=None, sa_budget=20000,
             sa_seeds=(0, 1, 2, 3), sa_gate=2, spark=100,
             alpha=0.999, T0_scale=0.5, p_level=0.7,
             mode='mixed', spark_mode='mixed', collect_proof=False):
    """Run COSA-ICF and return a benchmark row."""
    t0 = time.time()
    if initial is not None:
        L, U, sched, mach, lb_proof = initial
        L, U = int(L), int(U)
        sched = list(sched) if sched is not None else None
        mach = list(mach) if mach is not None else None
        co = None
    else:
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
    if lb_proof is None:
        return dict(name=name, idx=idx, known=known, policy=policy,
                    ok=False, error='no-lb-proof', t=0.0)

    probes = 0
    pact_lp = 0
    pact_nodes = 0
    pact_cert_lp = 0
    unknown = 0
    partial_ok = 0
    partial_fail = 0
    steps = []
    first = True
    lb0, ub0 = L, U
    sa = COSAStats()
    sa_rounds = 0
    sa_hits = 0
    sa_gain = 0

    def audit_state():
        nonlocal partial_ok, partial_fail
        pc = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1
        return pc

    audit_state()
    while L < U and probes < max_probes:
        L0, U0 = L, U
        gap = U - L
        if gap >= sa_gate and sa_budget > 0:
            s, m, c, hit, st = cosa_portfolio(
                inst, sched, mach, U, L, budget=sa_budget,
                seeds=sa_seeds, alpha=alpha, T0_scale=T0_scale,
                p_level=p_level, mode=mode)
            sa_rounds += 1
            for k in st.levels:
                sa.levels[k] = sa.levels.get(k, 0) + st.levels[k]
            sa.decodes += st.decodes
            sa.iters += st.iters
            sa.chains += st.chains
            sa.blocks += st.blocks
            sa.time += st.time
            if s is not None and c < U:
                if check_schedule(inst, c, s, m):
                    sa_gain += U - c
                    U, sched, mach = c, list(s), list(m)
            if hit and L == U:
                sa_hits += 1
        elif gap == 1 and spark > 0:
            s, m, c, dec, hit, st = cosa_anneal(
                inst, sched, L, budget=spark, seed=0,
                alpha=alpha, T0_scale=T0_scale, p_level=p_level,
                mode=spark_mode, stats=sa)
            sa_rounds += 1
            if s is not None and c < U:
                if check_schedule(inst, c, s, m):
                    sa_gain += U - c
                    U, sched, mach = c, list(s), list(m)
            if hit and L == U:
                sa_hits += 1
        if L == U:
            break
        h = _choose_h(policy, L, U, first)
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        probes += 1
        first = False
        pact_lp += r.get('lp_solves', 0)
        pact_nodes += r.get('nodes', 0)
        pact_cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False:
            proof = r['proof']
            L = h + 1
            lb_proof = proof
            if co is not None:
                co._record_proof(proof)
            steps.append(dict(h=h, v=False, kind=proof.kind,
                              lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                sched, mach = list(s2), list(m2)
            steps.append(dict(h=h, v=True, cmax=c2,
                              lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
        else:
            unknown += 1
            steps.append(dict(h=h, v=None, lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
            break
        audit_state()

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
        pact_lp=pact_lp, pact_nodes=pact_nodes,
        pact_cert_lp=pact_cert_lp,
        pin_lp=getattr(co, 'pin_lp', 0),
        partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_ok_final,
        unknown=unknown, steps=steps,
        proof_kind=(final.lb_proof.kind if final is not None else
                    getattr(lb_proof, 'kind', None)),
        total_audit=final_ok,
        sa_decodes=sa.decodes, sa_chains=sa.chains,
        sa_rounds=sa_rounds, sa_hits=sa_hits, sa_gain=sa_gain,
        sa_time=round(sa.time, 4), sa_blocks=sa.blocks,
        sa_levels=dict(sa.levels),
        t=round(dt, 4),
        schedule=list(sched) if sched is not None else None,
        machine=list(mach) if mach is not None else None,
        lb_proof=(lb_proof if collect_proof else None),
        ok=bool(L == U and U == known and final_ok and
                partial_fail == 0 and partial_ok_final),
    )
