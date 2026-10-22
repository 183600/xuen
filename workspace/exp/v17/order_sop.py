"""v1.5 SOP: Saturation-Order Packing certificate.

A root-level order certificate for DEC:

  (1) find a zero-slack precedence chain  C  (est[i1]+sum p+q[last]=h);
      every feasible schedule pins C to fixed start times;
  (2) in a tight window W (mandatory work = capacity) force every task whose
      overlap-minimising start is unique;
  (3) after subtracting the fixed blocks from capacity, try to place the
      remaining tasks that are wholly inside W into the free intervals;
      if no machine assignment admits a placement, FEAS=NO.

The search is exact but small: |F| fixed blocks, |I| residual items.
The checker recomputes (1)-(3) from the instance and replays the tree.
"""
import itertools
import sys
sys.path.insert(0, 'exp/v13')
import po


def ov(s, p, a, b):
    lo = s if s > a else a
    hi = s + p if s + p < b else b
    return hi - lo if hi > lo else 0


def ou(s, p, S):
    return sum(ov(s, p, a, b) for a, b in S)


def argmin(r, d, p, S):
    lo, hi = r, d - p
    if hi < lo:
        return []
    vals = [(ou(s, p, S), s) for s in range(lo, hi + 1)]
    m = min(v for v, _ in vals)
    return [s for v, s in vals if v == m]


def windows(r, d, p, h, forced):
    starts = set(r) | {d[i] - p[i] for i in range(len(p))} | {0}
    ends = set(d) | {r[i] + p[i] for i in range(len(p))} | {h}
    for i, s in forced.items():
        starts.add(s)
        ends.add(s + p[i])
    starts = sorted(x for x in starts if 0 <= x <= h)
    ends = sorted(x for x in ends if 0 <= x <= h)
    return [(a, b) for a in starts for b in ends if b > a]


def fits(occ, s, p):
    e = s + p
    for x, y in occ:
        if s < y and x < e:
            return False
    return True


def place(items, r, d, p, el, obs_by, m, a, b, nodecap=200000):
    """Exact placement of items into free intervals, left-shift candidates."""
    order = sorted(items, key=lambda i: (d[i], r[i]))
    nodes = [0]

    def dfs(pos, occ):
        nodes[0] += 1
        if nodes[0] > nodecap:
            raise TimeoutError
        if pos == len(order):
            return True
        i = order[pos]
        lo = max(r[i], a)
        hi = min(d[i] - p[i], b - p[i])
        for k in el[i]:
            blocks = occ[k] + obs_by[k]
            cand = {lo}
            for (x, y) in blocks:
                if lo <= y <= hi:
                    cand.add(y)
                if lo <= x - p[i] <= hi:
                    cand.add(x - p[i])
            for s in sorted(cand):
                if fits(blocks, s, p[i]):
                    occ[k].append((s, s + p[i]))
                    if dfs(pos + 1, occ):
                        return True
                    occ[k].pop()
        return False

    try:
        return dfs(0, [[] for _ in range(m)]), nodes[0]
    except TimeoutError:
        return None, nodes[0]




def free_intervals(obs, a, b):
    out = []
    cur = a
    for x, y in sorted(obs):
        if x > cur:
            out.append(x - cur)
        if y > cur:
            cur = y
    if cur < b:
        out.append(b - cur)
    return [z for z in out if z > 0]


def binpack(items, caps, nodecap=200000):
    items = sorted(items, reverse=True)
    caps = sorted(caps, reverse=True)
    bins = [0] * len(caps)
    nodes = [0]

    def dfs(i):
        nodes[0] += 1
        if nodes[0] > nodecap:
            raise TimeoutError
        if i == len(items):
            return True
        seen = set()
        for k in range(len(caps)):
            key = (bins[k], caps[k])   # only equal load AND equal capacity is symmetric
            if bins[k] + items[i] <= caps[k] and key not in seen:
                seen.add(key)
                bins[k] += items[i]
                if dfs(i + 1):
                    return True
                bins[k] -= items[i]
        return False

    try:
        return dfs(0), nodes[0]
    except TimeoutError:
        return None, nodes[0]


def capacity_pack(n, m, p, r, d, el, forced, a, b, nodecap=200000):
    """Sound residual certificate: after fixing the forced blocks, the tasks
    wholly inside [a,b] must occupy the free intervals.  Ignoring release and
    deadline *inside* the window only relaxes; if even the bin packing of
    sizes into free-interval lengths is impossible for every assignment of
    forced blocks to machines, no schedule exists."""
    obs = []
    for i, s in forced.items():
        x, y = max(s, a), min(s + p[i], b)
        if x < y:
            obs.append((i, x, y))
    items = [i for i in range(n)
             if i not in forced and r[i] >= a and d[i] <= b]
    nodes = 0
    for ass in itertools.product(range(m), repeat=len(obs)):
        good = True
        per = [[] for _ in range(m)]
        for (i, x, y), k in zip(obs, ass):
            if k not in el[i]:
                good = False
                break
            for (x2, y2) in per[k]:
                if x < y2 and x2 < y:
                    good = False
                    break
            if not good:
                break
            per[k].append((x, y))
        if not good:
            continue
        bins = []
        for k in range(m):
            bins += free_intervals(per[k], a, b)
        ok, nd = binpack([p[i] for i in items], bins, nodecap)
        nodes += nd
        if ok:
            return 'YES', {'reason': 'feasible', 'obs': obs, 'items': items,
                           'bins': bins, 'nodes': nodes}
        if ok is None:
            return 'UNKNOWN', {'reason': 'nodecap', 'obs': obs, 'items': items,
                               'bins': bins, 'nodes': nodes}
    return 'NO', {'reason': 'packing', 'obs': obs, 'items': items,
                  'bins': None, 'nodes': nodes}


def residual_pack(n, m, p, r, d, el, forced, a, b, nodecap=200000):
    """Return (verdict, info). verdict: 'NO' (all assignments fail), 'YES'
    (one assignment+placement found), 'UNKNOWN' (node cap)."""
    obs = []
    for i, s in forced.items():
        x, y = max(s, a), min(s + p[i], b)
        if x < y:
            obs.append((i, x, y))
    items = [i for i in range(n)
             if i not in forced and r[i] >= a and d[i] <= b]
    # aggregate necessary condition (cheap)
    if sum(p[i] for i in items) + sum(y - x for _, x, y in obs) > m * (b - a):
        return 'NO', {'reason': 'capacity', 'obs': obs, 'items': items, 'nodes': 0}
    if not items:
        return 'YES', {'reason': 'no-items', 'obs': obs, 'items': items, 'nodes': 0}
    total_nodes = 0
    saw_unknown = False
    for ass in itertools.product(range(m), repeat=len(obs)):
        good = True
        ob = [[] for _ in range(m)]
        for (i, x, y), k in zip(obs, ass):
            if k not in el[i]:
                good = False
                break
            for (x2, y2) in ob[k]:
                if x < y2 and x2 < y:
                    good = False
                    break
            if not good:
                break
            ob[k].append((x, y))
        if not good:
            continue
        res, nd = place(items, r, d, p, el, ob, m, a, b, nodecap)
        total_nodes += nd
        if res is None:
            saw_unknown = True
        elif res:
            return 'YES', {'reason': 'feasible', 'obs': obs, 'items': items,
                           'nodes': total_nodes}
    if saw_unknown:
        return 'UNKNOWN', {'reason': 'nodecap', 'obs': obs, 'items': items,
                           'nodes': total_nodes}
    return 'NO', {'reason': 'packing', 'obs': obs, 'items': items,
                  'nodes': total_nodes}


def tight_chains(inst, h, cap=200):
    n, p = inst['n'], inst['p']
    est, q = po.heads_tails(inst, 0, [0] * n)
    slack = [h - (est[i] + p[i] + q[i]) for i in range(n)]
    zero = {i for i in range(n) if slack[i] == 0}
    succ = {i: [j for j in inst['succ'][i]
                if j in zero and est[j] == est[i] + p[i] and q[i] == p[j] + q[j]]
            for i in zero}
    chains = []

    def dfs(path):
        if len(chains) >= cap:
            return
        i = path[-1]
        if not succ[i]:
            chains.append(tuple(path))
            return
        for j in succ[i]:
            dfs(path + [j])

    for i in zero:
        if not any(i in succ[j] for j in zero):
            dfs([i])
    return chains, est, q, slack


def propagate(n, m, p, r, d, el, forced0, nodecap=200000, maxit=40):
    """Saturation loop: energy -> force unique argmin -> repeat.

    Returns (status, forced, trace, tight_window). status in
    {'NO-ENERGY','CONFLICT','FIX'}.
    """
    forced = dict(forced0)
    trace = []
    for it in range(maxit):
        Ws = windows(r, d, p, max(d) if d else 0, forced)
        rows = []
        for (a, b) in Ws:
            cap = m * (b - a)
            fov = sum(ov(s, p[i], a, b) for i, s in forced.items())
            rem = [i for i in range(n) if i not in forced]
            W = 0
            for i in rem:
                ar = argmin(r[i], d[i], p[i], [(a, b)])
                W += min(ou(s, p[i], [(a, b)]) for s in ar) if ar else 0
            rows.append((cap - fov - W, a, b, cap, fov, W))
        rows.sort()
        trace.append(('energy', it, rows[:4], dict(forced)))
        if rows[0][0] < 0:
            return 'NO-ENERGY', forced, trace, (rows[0][1], rows[0][2])
        added = []
        for (sl, a, b, cap, fov, W) in rows:
            if sl != 0:
                continue
            for i in range(n):
                if i in forced:
                    continue
                ar = argmin(r[i], d[i], p[i], [(a, b)])
                if len(ar) == 1:
                    if i in forced and forced[i] != ar[0]:
                        return 'CONFLICT', forced, trace, (a, b)
                    if i not in forced:
                        forced[i] = ar[0]
                        added.append((i, ar[0], a, b))
        trace.append(('tight', it, added))
        if added:
            continue
        # pick a zero-slack window with the largest fixed work
        cand = [x for x in rows if x[0] == 0]
        if not cand:
            return 'FIX', forced, trace, None
        cand.sort(key=lambda x: (-x[4], x[1]))
        return 'FIX', forced, trace, (cand[0][1], cand[0][2])
    return 'FIX', forced, trace, None


def root_gate(inst, h, nodecap=200000, verbose=False):
    """Try zero-slack chains; return ('NO', cert) or ('UNKNOWN', stats)."""
    n, m, p, el = inst['n'], inst['m'], inst['p'], inst['elig']
    chains, est, q, slack = tight_chains(inst, h)
    stats = {'chains': len(chains), 'tried': 0, 'pack_nodes': 0,
             'sop_time': 0.0, 'cert': None}
    if not chains:
        return 'UNKNOWN', stats
    import time
    t0 = time.time()
    for C in chains:
        # fixed start times from the zero-slack chain
        forced = {}
        t = est[C[0]]
        for i in C:
            forced[i] = t
            t += p[i]
        status, F, trace, W = propagate(n, m, p, list(est),
                                        [h - q[i] for i in range(n)], el, forced,
                                        nodecap=nodecap)
        stats['tried'] += 1
        if status in ('NO-ENERGY', 'CONFLICT'):
            cert = {'chain': C, 'forced': F, 'trace': trace, 'window': W,
                    'reason': status, 'pack': None}
            stats['cert'] = cert
            stats['sop_time'] = time.time() - t0
            return 'NO', stats
        if status == 'FIX' and W is not None:
            a, b = W
            verdict, info = capacity_pack(n, m, p, list(est),
                                          [h - q[i] for i in range(n)], el,
                                          F, a, b, nodecap=nodecap)
            stats['pack_nodes'] += info.get('nodes', 0)
            if verdict == 'NO':
                cert = {'chain': C, 'forced': F, 'trace': trace, 'window': W,
                        'reason': 'PACK', 'pack': info}
                stats['cert'] = cert
                stats['sop_time'] = time.time() - t0
                return 'NO', stats
    stats['sop_time'] = time.time() - t0
    return 'UNKNOWN', stats


def check_cert(inst, h, cert, nodecap=200000):
    """Independent replay: verify the chain, the forcing trace and the packing."""
    n, m, p, el = inst['n'], inst['m'], inst['p'], inst['elig']
    chains, est, q, slack = tight_chains(inst, h)
    C = cert['chain']
    if C not in chains:
        return False
    forced = {}
    t = est[C[0]]
    for i in C:
        forced[i] = t
        t += p[i]
    if forced != {i: s for i, s in cert['forced'].items() if i in C}:
        return False
    # replay propagation
    status, F, trace, W = propagate(n, m, p, list(est),
                                    [h - q[i] for i in range(n)], el, forced,
                                    nodecap=nodecap)
    if F != cert['forced'] or status != cert['reason'] and cert['reason'] != 'PACK':
        return False
    if cert['reason'] in ('NO-ENERGY', 'CONFLICT'):
        return True
    a, b = cert['window']
    verdict, info = capacity_pack(n, m, p, list(est),
                                  [h - q[i] for i in range(n)], el, F, a, b,
                                  nodecap=nodecap)
    return verdict == 'NO'
