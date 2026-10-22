"""v0.7: Global-Exact certificate with H-threshold memo + UF contraction."""
import sys, time
sys.path.insert(0, '..'); sys.path.insert(0, '.')
import exp_da as E
from kern import bits

NEG = -1


def head_bound(inst, S, A, c):
    """A-HEAD: admissible machine-availability-aware refinement of L0."""
    est, q = E.heads_tails(inst, S, c)
    n, p = inst['n'], inst['p']
    R = ((1 << n) - 1) ^ S
    C = max(A)
    a0 = min(A)
    best = C
    for i in bits(R):
        t = max(a0, est[i]) + p[i] + q[i]
        if t > best:
            best = t
    return best


def symmetry_classes(inst, S):
    n = inst['n']
    R = ((1 << n) - 1) ^ S
    groups = {}
    for i in bits(R):
        sig = (inst['p'][i], tuple(inst['pred'][i]), tuple(inst['succ'][i]))
        groups.setdefault(sig, []).append(i)
    return [g for g in groups.values() if len(g) > 1]


def decide(inst, S, A, c, H, nodecap=200_000, use_sym=True, memo=None, use_energy=True):
    """Exact decision with a *threshold* memo: bad[key]=h means infeasible for
    every h<=h; good[key]=h means feasible for every h>=h.
    Returns (status, sched, stats) with status in {True, False, None}."""
    n, p, m = inst['n'], inst['p'], len(A)
    full = (1 << n) - 1
    R = full ^ S
    if R == 0:
        return (max(A) <= H, [], {})
    est, q = E.heads_tails(inst, S, c)
    if max(A) > H:
        return (False, None, {})
    if memo is None:
        memo = {'bad': {}, 'epoch': 0, 'reuse': 0, 'internal': 0}
    bad = memo['bad']
    memo['epoch'] = memo.get('epoch', 0) + 1
    ep = memo['epoch']
    memo.setdefault('ent_ep', {})
    cls = {}
    if use_sym:
        for g in symmetry_classes(inst, S):
            for i in g:
                cls[i] = g[0]
    nodes = [0]
    hits = [0]
    stat = {'bars0': 0, 'bars': 0}

    ps = [0] * (1 << 0)
    sump_all = sum(p[i] for i in bits(R))

    def rec(rem, A, est, h, sump=None):
        if sump is None:
            sump = sump_all
        nodes[0] += 1
        if nodes[0] > nodecap:
            raise TimeoutError
        if rem == 0:
            return []
        key = (rem, A) + tuple(est[i] for i in bits(rem))
        b = bad.get(key, NEG)
        if h <= b:
            hits[0] += 1
            memo['internal'] = memo.get('internal', 0) + 1
            if memo['ent_ep'].get(key, ep) < ep:
                memo['reuse'] = memo.get('reuse', 0) + 1
            return None
        for i in bits(rem):
            if est[i] + p[i] + q[i] > h:
                if h > bad.get(key, NEG):
                    bad[key] = h
                    memo['ent_ep'][key] = ep
                return None
        if use_energy and (sump + sum(A) + m - 1) // m > h:
            if h > bad.get(key, NEG):
                bad[key] = h
                memo['ent_ep'][key] = ep
            return None
        ready = [i for i in bits(rem) if not (inst['pmask'][i] & rem)]
        ready.sort(key=lambda i: (h - q[i] - p[i]) - est[i])
        seen = set()
        for i in ready:
            r = cls.get(i, i)
            if use_sym and r in seen:
                continue
            seen.add(r)
            for k in range(m):
                t = max(A[k], est[i])
                if t + p[i] + q[i] > h:
                    continue
                nA = list(A); nA[k] = t + p[i]; nA = tuple(nA)  # keep machine identity
                nest = list(est)
                for j in inst['succ'][i]:
                    if (rem >> j) & 1 and t + p[i] > nest[j]:
                        nest[j] = t + p[i]
                sub = rec(rem & ~(1 << i), nA, tuple(nest), h, sump - p[i])
                if sub is not None:
                    return [(i, k, t)] + sub
        if h > bad.get(key, NEG):
            bad[key] = h
            memo['ent_ep'][key] = ep
        return None

    try:
        out = rec(R, tuple(A), tuple(est), H)
    except TimeoutError:
        return (None, None, {'nodes': nodes[0], 'hits': hits[0], 'timeout': True})
    if out is not None:
        return (True, out, {'nodes': nodes[0], 'hits': hits[0]})
    return (False, None, {'nodes': nodes[0], 'hits': hits[0]})


def state_threshold(inst, S, A, c, U, nodecap=200_000, use_sym=True):
    """Find max H in [L0A, U-1] with infeasible decision; returns (LB, stats).
    Binary search with per-call memo (the union of calls shares H-monotone
    information only inside each call; `decide` already memoizes thresholds)."""
    lo = max(E.lower_L0(inst, S, A, c), head_bound(inst, S, A, c))
    hi = U - 1
    memo = {'bad': {}, 'epoch': 0, 'reuse': 0, 'internal': 0, 'ent_ep': {}}
    if lo > hi:
        return lo, {'nodes': 0, 'calls': 0, 'hits': 0, 'time': 0.0}
    nodes = 0; hits = 0; calls = 0
    t0 = time.time()
    hstar = None
    while lo <= hi:
        mid = (lo + hi) // 2
        calls += 1
        st, sched, s = decide(inst, S, A, c, mid, nodecap=nodecap, use_sym=use_sym, memo=memo)
        nodes += s.get('nodes', 0); hits += s.get('hits', 0)
        if st is False:
            hstar = mid; lo = mid + 1
        elif st is True:
            hi = mid - 1
        else:
            break
    lb = max(E.lower_L0(inst, S, A, c), head_bound(inst, S, A, c))
    if hstar is not None:
        lb = max(lb, hstar + 1)
    return lb, {'nodes': nodes, 'calls': calls, 'hits': hits,
                'memo_bad': len(memo['bad']), 'reuse': memo.get('reuse', 0), 'internal': memo.get('internal', 0), 'time': time.time() - t0}


def make_memo():
    return {'bad': {}, 'epoch': 0, 'reuse': 0, 'internal': 0, 'ent_ep': {}}


def ge_step(inst, S, A, c, U, memo, nodecap=200_000, max_rounds=8,
            use_sym=True, use_energy=True):
    """One exact-decision oracle call at H=U-1, iterated while it yields a
    better witness.  Returns (proved, U, stats).  proved=True means the
    decision at U-1 was infeasible, hence U is optimal *for this state*."""
    st = {'nodes': 0, 'calls': 0, 'proved': False, 'witness': False,
          'internal': 0, 'reuse': 0, 'timeout': False}
    t0 = time.time()
    for _ in range(max_rounds):
        h = U - 1
        if h < max(A):
            return True, U, st
        before = (memo.get('internal', 0), memo.get('reuse', 0))
        r, sched, s = decide(inst, S, A, c, h, nodecap=nodecap, memo=memo, use_sym=use_sym, use_energy=use_energy)
        st['nodes'] += s.get('nodes', 0)
        st['calls'] += 1
        st['internal'] += memo.get('internal', 0) - before[0]
        st['reuse'] += memo.get('reuse', 0) - before[1]
        if r is False:
            st['proved'] = True
            st['time'] = time.time() - t0
            return True, U, st
        if r is True:
            mk = U
            for (i, k, t) in sched:
                mk = max(mk, t + inst['p'][i]) if False else mk
            mk = max([max(A)] + [t + inst['p'][i] for (i, k, t) in sched])
            if mk < U:
                U = mk
                st['witness'] = True
                continue
            st['time'] = time.time() - t0
            return False, U, st
        st['timeout'] = True
        break
    st['time'] = time.time() - t0
    return False, U, st
