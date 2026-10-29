"""v9.1 HAP-ICF: hash-consed adaptive parameterized ICF.

The v9.0 ICF state is unchanged:

    C = (L, U, s, m, pi),  pi : NO(L-1),  Cmax(s)=U,  L<=U.

The new object is the inner decision oracle.  A fixed-h PACT search is a
bounded search tree whose parameter is the certificate depth k:

    Decide_k(F,h) in {NO(pi), YES(s,m), UNKNOWN}.

HAP runs iterative deepening k = 0,1,2,... and stores every completed
node in a *hash-consed memo* keyed by the canonical subproblem

    key(F,h) = (h, canonical_forbidden_set(F)).

The memo has three roles:

  1. cross-depth reuse: a subtree completed at depth d is reused when the
     cap is raised to d+1; only the frontier of holes is expanded;
  2. LP reuse: the SDLP solution at a canonical node is solved once;
  3. horizon monotonicity at the root: NO(h') implies NO(h) for h <= h',
     and YES(h') with Cmax <= h' implies YES(h) for h >= h'.  These two
     facts are stored separately and can close a probe without search.

The outer ICF invariant is preserved by the same PROBE transition as in
v9.0.  The parameter k is explicit and adaptive: the driver raises it
only when the previous depth produced a hole.  The final NO proof is a
tree (the memo may share nodes internally); the outer partial/final
certificate formats are unchanged and independently audited.
"""
import sys
import time
import math

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from sage import BranchProof, SubsumptionProof, _domain
from sdecc import SDLP
from cert import verify, integer_certificate
from rdf import check_schedule
from po import heads_tails
from pact import (PACT, pact_decide, _assign_machines,
                  _integral_schedule, _singleton_leaf, _elig_aware)
from icf import (PartialCertificate, ICFCertificate, cmax, _choose_h,
                 corpora)


# --------------------------------------------------------------- memo
class HapMemo:
    """Canonical hash-cons table for a single instance.

    ``res`` stores only definitive results, so a hit is always a valid
    NO proof or YES schedule for the exact key.  ``lp`` caches the LP
    outcome.  ``no_root`` / ``yes_root`` are monotone horizon facts for
    the empty box (the outer probe).
    """

    def __init__(self, inst):
        self.inst = inst
        self.res = {}
        self.lp = {}
        self.no_root = []
        self.yes_root = []
        self.hits = 0
        self.lp_hits = 0
        self.lp_solves = 0
        self.nodes = 0
        self.holes = 0
        self.max_depth = 0

    def key(self, h, F):
        return (int(h), frozenset(F))


def _bounds_for(lp, F):
    b = [(0, 1)] * lp.N
    if F:
        for c, key in enumerate(lp.cols):
            if (key[0], key[-1]) in F:
                b[c] = (0, 0)
    return b


def _allowed_times(lp, i, F):
    return sorted({key[-1] for key in lp.cols
                   if key[0] == i and (key[0], key[-1]) not in F})


def pact_decide_hc(inst, h, depthcap, memo, nodecap=None):
    """Memoized fixed-h PACT DFS at depth cap ``depthcap``.

    The memo is shared across calls with the same instance; keys include
    h, so different probe horizons do not alias.  Definitive results are
    cached even when they were obtained at a smaller cap, because a
    certificate does not expire when the cap is raised.
    """
    t0 = time.time()
    n, m, p = inst['n'], inst['m'], inst['p']
    elig = _elig_aware(inst)
    est, q = heads_tails(inst, 0, [0] * n)
    if not hasattr(memo, '_lp_by_h'):
        memo._lp_by_h = {}
    lp = memo._lp_by_h.get(h)
    if lp is None:
        lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig)
        memo._lp_by_h[h] = lp

    stats = dict(nodes=0, leaves=0, depth=0, yes_depth=None,
                 lp_solves=0, cert_lp=0, unknown=False, holes=0,
                 memo_hits=0, lp_hits=0, insufficient=False)
    start_lp = memo.lp_solves
    start_hits = memo.hits
    start_lp_hits = memo.lp_hits
    start_nodes = memo.nodes

    def choose(z, F):
        cand = []
        for i in range(n):
            times = _allowed_times(lp, i, F)
            if len(times) <= 1:
                continue
            dist = []
            for tt in times:
                v = sum(z[c] for c, key in enumerate(lp.cols)
                        if key[0] == i and key[-1] == tt
                        and (key[0], key[-1]) not in F)
                dist.append((tt, v))
            frac = sum(v for _, v in dist if 1e-7 < v < 1 - 1e-7)
            if frac <= 1e-7:
                continue
            mass = sum(v for _, v in dist)
            cand.append(((mass, q[i], len(inst['succ'][i]), -i),
                         i, dist))
        if not cand:
            return None, None
        cand.sort(reverse=True)
        _, i, dist = cand[0]
        total = sum(v for _, v in dist)
        times = [tt for tt, _ in dist]
        acc = 0.0
        mid = times[0]
        for tt, v in dist:
            acc += v
            if acc >= 0.5 * total:
                mid = tt
                break
        lo_t = [tt for tt in times if tt > mid]
        hi_t = [tt for tt in times if tt <= mid]
        if not lo_t or not hi_t:
            mid = times[max(0, len(times) // 2 - 1)]
            lo_t = [tt for tt in times if tt > mid]
            hi_t = [tt for tt in times if tt <= mid]
        if not lo_t or not hi_t:
            return None, None
        return i, mid

    def leaf_cert(F):
        stats['cert_lp'] += 1
        cert = integer_certificate(inst, h, use_dom=True,
                                   elig_aware=elig, forbid=F)
        if cert is not None and verify(inst, h, cert, forbid=F):
            return ('leaf', frozenset(F), cert)
        for i in range(n):
            lo, hi = _domain(inst, h, i)
            if lo <= hi and all((i, t) in F for t in range(lo, hi + 1)):
                return ('empty', frozenset(F), i)
        return None

    def dfs(F, depth):
        key = memo.key(h, F)
        if key in memo.res:
            memo.hits += 1
            stats['memo_hits'] += 1
            return memo.res[key]
        if depthcap is not None and depth > depthcap:
            memo.holes += 1
            stats['holes'] += 1
            stats['unknown'] = True
            return None
        if nodecap is not None and memo.nodes - start_nodes >= nodecap:
            stats['unknown'] = True
            return None

        memo.nodes += 1
        memo.max_depth = max(memo.max_depth, depth)
        stats['depth'] = max(stats['depth'], depth)

        if key in memo.lp:
            memo.lp_hits += 1
            stats['lp_hits'] += 1
            status, res = memo.lp[key]
        else:
            memo.lp_solves += 1
            stats['lp_solves'] += 1
            res = lp.solve(_bounds_for(lp, F))
            status = res.status
            memo.lp[key] = (status, res)

        if status == 2:
            stats['leaves'] += 1
            node = leaf_cert(F)
            if node is None:
                stats['unknown'] = True
                return None
            memo.res[key] = node
            return node
        if status != 0:
            stats['unknown'] = True
            return None

        z = res.x
        frac = False
        for c, ck in enumerate(lp.cols):
            if (1e-7 < z[c] < 1 - 1e-7
                    and (ck[0], ck[-1]) not in F):
                frac = True
                break
        if not frac:
            got = _integral_schedule(inst, lp, z, elig)
            if got is None:
                got = _singleton_leaf(inst, h, F, lp,
                                      _bounds_for(lp, F))
            if got is not None:
                stats['yes_depth'] = depth
                node = ('yes', got[0], got[1])
                memo.res[key] = node
                return node
            i = None
            mid = None
            for j in range(n):
                times = _allowed_times(lp, j, F)
                if len(times) > 1:
                    i = j
                    mid = times[len(times) // 2 - 1]
                    break
            if i is None:
                stats['unknown'] = True
                return None
        else:
            i, mid = choose(z, F)
            if i is None:
                stats['unknown'] = True
                return None

        times = _allowed_times(lp, i, F)
        lo_t = [t for t in times if t > mid]
        hi_t = [t for t in times if t <= mid]
        if not lo_t or not hi_t:
            stats['unknown'] = True
            return None
        loF = F | frozenset((i, t) for t in lo_t)
        hiF = F | frozenset((i, t) for t in hi_t)
        lo = dfs(loF, depth + 1)
        if lo is not None and lo[0] == 'yes':
            memo.res[key] = lo
            return lo
        hi = dfs(hiF, depth + 1)
        if hi is not None and hi[0] == 'yes':
            memo.res[key] = hi
            return hi
        if lo is None or hi is None:
            stats['unknown'] = True
            return None
        node = ('node', i, mid, frozenset(F), lo, hi)
        memo.res[key] = node
        return node

    tree = dfs(frozenset(), 0)
    stats['memo_hits'] = memo.hits - start_hits
    stats['lp_hits'] = memo.lp_hits - start_lp_hits
    stats['lp_solves'] = memo.lp_solves - start_lp
    stats['nodes'] = memo.nodes - start_nodes
    stats['t'] = round(time.time() - t0, 5)
    if tree is None:
        stats['verdict'] = None
        stats['proof'] = None
        stats['schedule'] = None
        stats['machine'] = None
        return stats
    if tree[0] == 'yes':
        stats['verdict'] = True
        stats['proof'] = None
        stats['schedule'] = tree[1]
        stats['machine'] = tree[2]
        return stats
    proof = BranchProof(inst, h, tree, stats)
    if not proof.audit_rdf():
        stats['unknown'] = True
        stats['verdict'] = None
        stats['proof'] = None
        stats['schedule'] = None
        stats['machine'] = None
        return stats
    stats['verdict'] = False
    stats['proof'] = proof
    stats['schedule'] = None
    stats['machine'] = None
    return stats


# --------------------------------------------------------------- driver
def _next_depth(d, mode, holes):
    if mode == 'plus1':
        return d + 1
    if mode == 'double':
        return 1 if d == 0 else 2 * d
    if mode == 'adaptive':
        if d < 3:
            return d + 1
        if holes <= 1:
            return d + 1
        return d + max(1, d // 2)
    raise ValueError(mode)


def decide_hat(inst, h, memo, mode='plus1', dmax=64):
    """Iterative-deepening driver with cross-depth memo reuse.

    ``hybrid:K`` runs the increasing-depth loop only through cap K and
    then falls back to the complete search with the same memo.  The
    fallback is exact; the memo makes the already-completed shallow
    subtrees free.  This preserves the shallow-YES win of iterative
    deepening without paying its deep-YES blow-up.
    """
    # Root monotone caches: close the probe without search when possible.
    for h0, proof in memo.no_root:
        if h0 >= h:
            p = SubsumptionProof(inst, h, proof)
            if p.audit_rdf():
                return dict(verdict=False, proof=p, schedule=None,
                            machine=None, lp_solves=0, memo_hits=0,
                            lp_hits=0, nodes=0, cert_lp=0, holes=0,
                            levels=[], horizon_hit='no',
                            t=0.0), []
    for h0, c0, s0, m0 in memo.yes_root:
        if h0 >= h and c0 <= h:
            return dict(verdict=True, proof=None, schedule=s0,
                        machine=m0, lp_solves=0, memo_hits=0,
                        lp_hits=0, nodes=0, cert_lp=0, holes=0,
                        levels=[], horizon_hit='yes', t=0.0), []

    hybrid_cap = None
    if mode.startswith('hybrid:'):
        hybrid_cap = int(mode.split(':', 1)[1])
        loop_mode = 'plus1'
    else:
        loop_mode = mode

    if mode == 'full':
        r = pact_decide_hc(inst, h, None, memo)
        r['levels'] = []
        r['horizon_hit'] = None
        if r['verdict'] is False:
            memo.no_root.append((h, r['proof']))
        elif r['verdict'] is True:
            c = cmax(inst, r['schedule'])
            memo.yes_root.append((h, c, list(r['schedule']),
                                  list(r['machine'])))
        return r, []

    levels = []
    total = dict(lp_solves=0, memo_hits=0, lp_hits=0, nodes=0,
                 cert_lp=0, holes=0)
    d = 0
    limit = hybrid_cap if hybrid_cap is not None else dmax
    while d <= limit:
        r = pact_decide_hc(inst, h, d, memo)
        for k in total:
            total[k] += r.get(k, 0)
        levels.append(dict(cap=d, verdict=r['verdict'],
                           lp=r['lp_solves'], hit=r['lp_hits'],
                           memo=r['memo_hits'], holes=r['holes'],
                           nodes=r['nodes'], t=r['t']))
        if r['verdict'] is not None:
            for k in total:
                r[k] = total[k]
            r['levels'] = levels
            r['horizon_hit'] = None
            if r['verdict'] is False and not r.get('proof'):
                pass
            elif r['verdict'] is False:
                memo.no_root.append((h, r['proof']))
            elif r['verdict'] is True:
                c = cmax(inst, r['schedule'])
                memo.yes_root.append((h, c, list(r['schedule']),
                                      list(r['machine'])))
            return r, levels
        d = _next_depth(d, loop_mode, r['holes'])
    if hybrid_cap is not None:
        r = pact_decide_hc(inst, h, None, memo)
        for k in total:
            total[k] += r.get(k, 0)
        for k in total:
            r[k] = total[k]
        levels.append(dict(cap='full', verdict=r['verdict'],
                           lp=r['lp_solves'], hit=r['lp_hits'],
                           memo=r['memo_hits'], holes=r['holes'],
                           nodes=r['nodes'], t=r['t']))
        r['levels'] = levels
        r['horizon_hit'] = None
        if r['verdict'] is False:
            memo.no_root.append((h, r['proof']))
        elif r['verdict'] is True:
            c = cmax(inst, r['schedule'])
            memo.yes_root.append((h, c, list(r['schedule']),
                                  list(r['machine'])))
        return r, levels
    return dict(verdict=None, proof=None, schedule=None, machine=None,
                lp_solves=0, memo_hits=0, lp_hits=0, nodes=0,
                cert_lp=0, holes=0, levels=levels, horizon_hit=None,
                t=0.0), levels


# --------------------------------------------------------------- outer loop
def run_hap(inst, known, name, idx, policy='lower-first', mode='plus1',
            oracle='hap', max_probes=64, initial=None):
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
    else:
        L, U, sched, mach, lb_proof = initial
        L, U = int(L), int(U)
        sched = list(sched) if sched is not None else None
        mach = list(mach) if mach is not None else None
        co = None

    memo = HapMemo(inst)
    if lb_proof is None:
        r, _ = decide_hat(inst, L - 1, memo, mode=mode)
        if r['verdict'] is False:
            lb_proof = r['proof']
    if lb_proof is None:
        return dict(name=name, idx=idx, known=known, policy=policy,
                    ok=False, error='no-lb-proof', t=0.0)

    probes = 0
    pact_lp = pact_nodes = pact_cert = 0
    memo_hits = lp_hits = 0
    unknown = 0
    partial_ok = partial_fail = 0
    levels_total = 0
    steps = []
    first = True
    lb0, ub0 = L, U

    def audit_state():
        nonlocal partial_ok, partial_fail
        pc = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1

    audit_state()
    while L < U and probes < max_probes:
        L0, U0 = L, U
        h = _choose_h(policy, L, U, first)
        if oracle == 'pact':
            r = pact_decide(inst, h, depthcap=None, nodecap=None)
            levels = []
        else:
            r, levels = decide_hat(inst, h, memo, mode=mode)
        probes += 1
        first = False
        levels_total += len(levels)
        pact_lp += r.get('lp_solves', 0)
        pact_nodes += r.get('nodes', 0)
        pact_cert += r.get('cert_lp', 0)
        memo_hits += r.get('memo_hits', 0)
        lp_hits += r.get('lp_hits', 0)

        if r['verdict'] is False:
            proof = r['proof']
            L = h + 1
            lb_proof = proof
            if co is not None:
                co._record_proof(proof)
            steps.append(dict(h=h, v=False, kind=proof.kind,
                              lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L0, U0=U0, L1=L, U1=U,
                              levels=len(levels),
                              horizon=r.get('horizon_hit')))
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                sched, mach = list(s2), list(m2)
            steps.append(dict(h=h, v=True, cmax=c2,
                              lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L0, U0=U0, L1=L, U1=U,
                              levels=len(levels),
                              horizon=r.get('horizon_hit')))
        else:
            unknown += 1
            steps.append(dict(h=h, v=None, lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L0, U0=U0, L1=L, U1=U,
                              levels=len(levels)))
            break
        audit_state()

    final = ICFCertificate(inst, U, sched, mach, lb_proof) \
        if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                 probe=probes)
    partial_final = bool(partial.audit_rdf())
    dt = time.time() - t0
    return dict(
        name=name, idx=idx, known=known, policy=policy, mode=mode,
        opt=U, lb=L, lb0=lb0, ub0=ub0, gap0=ub0 - lb0,
        certified=bool(L == U and final_ok),
        audit=final_ok, proof=final_ok,
        cert_h=(U - 1 if L == U else None),
        queries=probes, probes=probes,
        pact_lp=pact_lp, pact_nodes=pact_nodes,
        pact_cert_lp=pact_cert,
        memo_hits=memo_hits, lp_hits=lp_hits,
        levels_total=levels_total,
        partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_final, unknown=unknown,
        steps=steps,
        proof_kind=(final.lb_proof.kind if final is not None else
                    getattr(lb_proof, 'kind', None)),
        t=round(dt, 4),
        ok=bool(L == U and U == known and final_ok and
                partial_fail == 0 and partial_final),
    )


# --------------------------------------------------------------- weak init
def init_weak(inst):
    from chip import base_bounds
    lb, ub, sched, mach, est, q = base_bounds(inst)
    co = PACT(inst, use_lp=False, use_lns=False, use_lp_sched=False,
              pact_mode='complete', use_ga=False)
    proof = co._ensure_lb_proof(lb)
    if proof is None:
        r = pact_decide(inst, lb - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            proof = r['proof']
    return lb, ub, sched, mach, proof


def weak_rows(min_gap=4):
    out = []
    for c, name, idx, inst, known in corpora():
        initial = init_weak(inst)
        if initial[1] - initial[0] >= min_gap:
            out.append((c, name, idx, inst, known, initial))
    return out
