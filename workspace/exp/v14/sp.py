"""v1.3 prototype: shortest-path flavoured DEC with an energetic potential.

Adds to v1.2:
  * ENERGY(rem,A,est,h): mandatory-energy (energetic reasoning) necessary
    condition over time windows; sound NO certificate when it fires.
  * an optional best-first / potential-ordered DFS.
  * normalised est (inactive releases raised to min eligible A) before
    dominance tests.
"""
import sys, time
sys.path.insert(0, 'exp/v13')
import po
from po import bititer, tails, node_elig, pack_exact, pack_greedy, pack_dff

NEG = -1

def energy_ok(inst, rem, A, est, q, h, stats=None):
    """Return False only if some interval is energetically overloaded."""
    p, m = inst['p'], inst['m']
    tasks = list(bititer(rem))
    n = len(tasks)
    if n == 0:
        return True
    caps = [h - A[k] for k in range(m)]
    if min(caps) < 0:
        return False
    slack = sum(caps) - sum(p[i] for i in tasks)
    if slack > inst.get('_eslack', 24):
        return True
    r = [est[i] for i in tasks]
    d = [h - q[i] for i in tasks]          # latest completion
    ps = [p[i] for i in tasks]
    starts = sorted(set(r) | {d[i] - ps[i] for i in range(n)})
    ends = sorted(set(d) | {r[i] + ps[i] for i in range(n)})
    for a in starts:
        for b in ends:
            L = b - a
            if L <= 0:
                continue
            tot = 0
            cap = m * L
            for i in range(n):
                # mandatory overlap of task i with [a,b]
                mand = ps[i]
                t = r[i] + ps[i] - a
                if t < mand: mand = t
                t = b - (d[i] - ps[i])
                if t < mand: mand = t
                if L < mand: mand = L
                if mand > 0:
                    tot += mand
                    if tot > cap:
                        if stats is not None:
                            stats['energy_prunes'] = stats.get('energy_prunes', 0) + 1
                        return False
    return True


def norm_est(inst, rem, A, est):
    """Raise inactive releases to min eligible availability (equivalent state)."""
    out = list(est)
    for i in bititer(rem):
        mn = min(A[k] for k in inst['elig'][i])
        if out[i] < mn:
            out[i] = mn
    return tuple(out)


def decide(inst, h, mode='sp', nodecap=2_000_000, K=48, stats=None,
           energy=True, depth_gate=0, order='slack', slack_cap=24):
    """mode: plain / canon / sub (v1.2) / sp (this round)."""
    n, p, m = inst['n'], inst['p'], inst['m']
    full = inst['full']
    if stats is None:
        stats = {}
    st = {'nodes': 0, 'memo_hits': 0, 'pack_calls': 0, 'pack_front_hits': 0,
          'tables': 0, 'sub_front_hits': 0, 'energy_prunes': 0,
          'front_sizes': [], 'inserts': 0}
    inst = dict(inst); inst['_eslack'] = slack_cap
    use_canon = mode in ('canon', 'front', 'sub', 'sp')
    use_pack_front = mode in ('front', 'sub', 'sp')
    use_sub_front = mode in ('sub', 'sp')
    use_energy = energy and mode == 'sp'
    bad = {}
    F_pack = {}
    F_sub = {}
    twin_cache = {}

    def twins(rem):
        if rem in twin_cache: return twin_cache[rem]
        groups = {}
        for k in range(m):
            col = tuple(sorted(i for i in bititer(rem) if k in inst['elig'][i]))
            groups.setdefault(col, []).append(k)
        blocks = [g for g in groups.values() if len(g) > 1]
        twin_cache[rem] = blocks
        return blocks

    def canonA(rem, A):
        blocks = twins(rem)
        if not blocks: return A
        out = list(A)
        for g in blocks:
            vals = sorted((out[k] for k in g), reverse=True)
            for k, v in zip(g, vals):
                out[k] = v
        return tuple(out)

    def rec(rem, A, est, sump):
        st['nodes'] += 1
        if st['nodes'] > nodecap:
            raise TimeoutError
        if rem == 0: return []
        q = tails(inst, rem)
        estt0 = norm_est(inst, rem, A, est) if use_sub_front else est
        estt = tuple(estt0[i] for i in bititer(rem))
        Af = canonA(rem, A) if use_canon else A
        key = (rem, Af, estt)
        if bad.get(key, NEG) >= h:
            st['memo_hits'] += 1; return None
        for i in bititer(rem):
            if estt0[i] + p[i] + q[i] > h:
                bad[key] = h; return None
        if (sump + sum(A) + m - 1)//m > h:
            bad[key] = h; return None
        if use_sub_front:
            fr = F_sub.setdefault((rem, h), [])
            for e2, a2 in fr:
                if po.dominates(a2, Af) and all(e2[t] <= estt[t] for t in range(len(estt))):
                    st['sub_front_hits'] += 1; bad[key] = h; return None
        st['pack_calls'] += 1
        if use_pack_front:
            fr = F_pack.setdefault((rem, h), [])
            if po.front_query(fr, Af):
                st['pack_front_hits'] += 1; bad[key] = h; return None
        st['tables'] += 1
        ok = pack_exact(inst, rem, A, estt0, q, h)
        if not ok:
            if use_pack_front:
                fr = F_pack.setdefault((rem, h), [])
                if po.front_insert(fr, Af, K): st['inserts'] += 1
                st['front_sizes'].append(len(fr))
            bad[key] = h; return None
        if use_energy and (rem.bit_count()) >= depth_gate:
            if not energy_ok(inst, rem, A, estt0, q, h, st):
                if use_pack_front:
                    fr = F_pack.setdefault((rem, h), [])
                    if po.front_insert(fr, Af, K): st['inserts'] += 1
                    st['front_sizes'].append(len(fr))
                bad[key] = h; return None
        ready = [i for i in bititer(rem) if not (inst['pmask'][i] & rem)]
        if order == 'slack':
            ready.sort(key=lambda i: (h - q[i] - p[i]) - estt0[i])
        elif order == 'late':
            ready.sort(key=lambda i: -q[i])
        for i in ready:
            for k in range(m):
                t = max(A[k], estt0[i])
                if t + p[i] + q[i] > h: continue
                if k not in inst['elig'][i]: continue
                nA = list(A); nA[k] = t + p[i]; nA = tuple(nA)
                nest = list(estt0)
                for j in inst['succ'][i]:
                    if (rem >> j) & 1 and t + p[i] > nest[j]:
                        nest[j] = t + p[i]
                sub = rec(rem & ~(1 << i), nA, tuple(nest), sump - p[i])
                if sub is not None:
                    return [(i, k, t)] + sub
        if use_sub_front:
            fr = F_sub.setdefault((rem, h), [])
            hit = any(po.dominates(a2, Af) and all(e2[t] <= estt[t] for t in range(len(estt)))
                      for e2, a2 in fr)
            if not hit:
                fr.append((estt, Af))
                if K and len(fr) > K:
                    fr.sort(key=lambda ea: -sum(ea[0])); del fr[K:]
        bad[key] = h; return None

    try:
        est0, _ = po.heads_tails(inst, 0, [0]*n)
        out = rec(full, tuple([0]*m), tuple(est0), sum(p))
        res = (out is not None, out)
    except TimeoutError:
        res = (None, None); st['timeout'] = True
    return res, st
