"""v1.3 PACE: Potential-Augmented Certificate Engine.

A shortest-path view of DEC.  Each state sigma=(R,A,est) gets an admissible
potential Phi(sigma): a lower bound on the completion time of any schedule
extending sigma.  Phi is built from *interval certificates*:

  energy[a,b] : mandatory work in [a,b] must fit on m machines
  clique[a,b] : tasks with mandatory overlap > (b-a)/2 need distinct machines
  subset[a,b] : tasks whose eligibility is inside S must fit on |S| machines

If Phi(sigma) > h, or an interval is overloaded for horizon h, sigma is dead.
Every rejection carries the interval (a,b) and the mandatory vector, which the
checker recomputes in O(n) -- no search is trusted.

The potential is also used as the A* priority of a child (best-first order).
Finally, v1.2's est-vector is normalised: an inactive release (est_i below
min_{k in E_i} A_k) is raised to that min, which is an equivalent state and
removes spurious front incomparability.
"""
import sys, time
sys.path.insert(0, 'exp/v13')
sys.path.insert(0, 'exp/v15')
import po, mint
import order_sop as sop
from po import bititer, tails, pack_exact, dominates

NEG = -1


# ------------------------------------------------------------------ potential
def _windows(inst, rem, A, est, q, h):
    p, m = inst['p'], inst['m']
    tasks = list(bititer(rem))
    r = [est[i] for i in tasks]
    ps = [p[i] for i in tasks]
    d = [h - q[i] for i in tasks]
    el = [inst['elig'][i] for i in tasks]
    return tasks, r, ps, d, el


def potential(inst, rem, A, est, q, h, slack_cap=10**9, use_subset=True,
              use_clique=True, cap_mode='machine', stats=None, depth=0,
              mint_on=True, mint_tau=1, mint_depth=10**9,
              packset_on=True, packset_maxslack=10, packset_depth=0,
              sop_on=False, sop_nodecap=200000, nondelay=False):
    """Return (ok, phi, witness).  ok=False means sigma cannot meet h.

    witness = (kind, a, b, mandatory_list, rhs) with mandatory aligned to tasks.
    """
    p, m = inst['p'], inst['m']
    tasks, r, ps, d, el = _windows(inst, rem, A, est, q, h)
    n = len(tasks)
    if n == 0:
        return True, 0, None
    tight = []
    pack_list = []
    min_slack = 10**18
    caps = [h - A[k] for k in range(m)]
    if min(caps) < 0:
        return False, h + 1, ('cap', 0, h, [], 0)
    slack = sum(caps) - sum(ps)
    if slack > slack_cap:
        return True, 0, None
    # scalar lower bound: deadline / tails
    phi = 0
    for i in range(n):
        v = r[i] + ps[i] + q[tasks[i]]
        if v > phi:
            phi = v
    starts = set(r)
    ends = set(d)
    for i in range(n):
        starts.add(d[i] - ps[i])
        ends.add(r[i] + ps[i])
    starts = sorted(x for x in starts if x < h)
    ends = sorted(x for x in ends if x > 0)
    # subsets of machines (m small)
    subs = []
    if use_subset and m <= 4:
        for S in range(1, 1 << m):
            subs.append((S, bin(S).count('1')))
    for a in starts:
        for b in ends:
            L = b - a
            if L <= 0:
                continue
            if cap_mode == 'machine':
                cap = 0
                for k in range(m):
                    avail = b - (a if a > A[k] else A[k])
                    if avail > 0: cap += avail
            else:
                cap = m * L
            mand = [0] * n
            tot = 0
            for i in range(n):
                v = ps[i]
                t = r[i] + ps[i] - a
                if t < v: v = t
                t = b - (d[i] - ps[i])
                if t < v: v = t
                if L < v: v = L
                if v > 0:
                    mand[i] = v
                    tot += v
            # scalar makespan bound
            v = a + (tot * L + cap - 1) // cap if cap > 0 else h + 1
            if v > phi:
                phi = v
            sl = cap - tot
            if sl < min_slack:
                min_slack = sl
            if sl <= mint_tau and len(tight) < 200:
                tight.append((a, b, sl))
            if sl <= packset_maxslack and len(pack_list) < 400:
                pack_list.append((a, b, sl))
            if tot > cap:
                return False, max(phi, b + 1), ('energy', a, b, mand, cap)
            if use_clique:
                cl = [i for i in range(n) if 2 * mand[i] > L]
                if len(cl) > m:
                    return False, max(phi, b + 1), ('clique', a, b, mand, m)
                if use_subset and subs:
                    # eligibility-aware clique: clique tasks confined to S
                    for S, sc in subs:
                        if sc >= len(cl):
                            continue
                        cnt = 0
                        for i in cl:
                            okS = True
                            for k in el[i]:
                                if not (S >> k) & 1:
                                    okS = False; break
                            if okS:
                                cnt += 1
                                if cnt > sc:
                                    return False, max(phi, b + 1), ('eclique', a, b, mand, sc)
            if use_subset and subs:
                for S, sc in subs:
                    ws = 0
                    for i in range(n):
                        if mand[i]:
                            okS = True
                            for k in el[i]:
                                if not (S >> k) & 1:
                                    okS = False; break
                            if okS:
                                ws += mand[i]
                    if ws > sc * L:
                        return False, max(phi, b + 1), ('subset', a, b, mand, sc * L)
    # ---- tier 1.3: MINT (multi-window integral certificate) -------------
    if mint_on and depth <= mint_depth and len(tight) >= 2:
        _tm = time.time()
        best, npair = mint.mint_pairs(tight, n, ps, r, d, A, m)
        if stats is not None:
            stats['mint_time'] = stats.get('mint_time', 0.0) + (time.time() - _tm)
        if stats is not None:
            stats['mint_calls'] = stats.get('mint_calls', 0) + 1
            stats['mint_pairs'] = stats.get('mint_pairs', 0) + npair
        if best[0] > 0:
            S, W, cp = best[1]
            if stats is not None:
                stats['mint_prunes'] = stats.get('mint_prunes', 0) + 1
            return False, max(phi, max(b for (_, b) in S) + 1), ('mint', S, W, cp)
    # ---- tier 1.35: PACK-SET (non-preemptive bin packing) ---------------
    if (packset_on and depth <= packset_depth and pack_list
            and min_slack <= 1):
        _tp = time.time()
        for (a, b, sl) in sorted(pack_list, key=lambda t: t[2])[:24]:
            if sl > packset_maxslack:
                continue
            bad, info, tn = mint.packset_window(n, ps, r, d, el, a, b, A, m)
            if stats is not None:
                stats['packset_calls'] = stats.get('packset_calls', 0) + 1
                stats['packset_nodes'] = stats.get('packset_nodes', 0) + tn
            if bad:
                if stats is not None:
                    stats['packset_prunes'] = stats.get('packset_prunes', 0) + 1
                    stats['packset_time'] = stats.get('packset_time', 0.0) + (time.time() - _tp)
                if depth == 0:
                    cert = mint.packset_tree(n, ps, r, d, el, a, b, A, m)
                    if cert is not None:
                        return False, max(phi, b + 1), ('packset', cert)
                return False, max(phi, b + 1), ('packset', info)
        if stats is not None:
            stats['packset_time'] = stats.get('packset_time', 0.0) + (time.time() - _tp)
    # ---- tier 1.4: SOP (saturation-order packing, zero-slack spines) ----
    if sop_on and depth == 0:
        _ts = time.time()
        verdict, sst = sop.root_gate(inst, h, nodecap=sop_nodecap)
        if stats is not None:
            stats['sop_calls'] = stats.get('sop_calls', 0) + 1
            stats['sop_time'] = stats.get('sop_time', 0.0) + (time.time() - _ts)
            stats['sop_chains'] = stats.get('sop_chains', 0) + sst.get('chains', 0)
            stats['sop_pack_nodes'] = stats.get('sop_pack_nodes', 0) + sst.get('pack_nodes', 0)
        if verdict == 'NO':
            if stats is not None:
                stats['sop_prunes'] = stats.get('sop_prunes', 0) + 1
            return False, h + 1, ('sop', sst['cert'])
    return True, phi, None


def check_potential_witness(inst, rem, A, est, q, h, wit):
    """Independent O(n) recheck of a POT witness (the certificate checker)."""
    if wit[0] == 'sop':
        return sop.check_cert(inst, h, wit[1])
    kind, a, b, mand, rhs = wit
    if kind == 'cap':
        return min(h - A[k] for k in range(inst['m'])) < 0
    tasks, r, ps, d, el = _windows(inst, rem, A, est, q, h)
    L = b - a
    if L <= 0:
        return False
    m = inst['m']
    tot = 0
    for i in range(len(tasks)):
        v = ps[i]
        t = r[i] + ps[i] - a
        if t < v: v = t
        t = b - (d[i] - ps[i])
        if t < v: v = t
        if L < v: v = L
        if v < 0: v = 0
        if v != mand[i]:
            return False
        tot += v
    if kind == 'energy':
        if rhs == m * L:
            return tot > rhs
        cap = 0
        for k in range(m):
            avail = b - (a if a > A[k] else A[k])
            if avail > 0: cap += avail
        return tot > rhs and rhs == cap
    if kind == 'clique':
        return sum(1 for x in mand if 2 * x > L) > rhs and rhs == m
    if kind == 'eclique':
        return sum(1 for i in range(len(tasks)) if 2 * mand[i] > L) > rhs and rhs < m
    if kind == 'subset':
        return tot > rhs
    if kind == 'phi':
        # recompute the scalar potential at this state
        _, ph, _ = potential(inst, rem, A, est, q, h, slack_cap=10**9)
        return ph > h
    return False



def min_interval_slack(inst, rem, A, est, q, h, cap_mode='machine'):
    """Minimum (capacity - mandatory work) over intervals; <0 means overload."""
    p, m = inst['p'], inst['m']
    tasks, r, ps, d, el = _windows(inst, rem, A, est, q, h)
    n = len(tasks)
    if n == 0:
        return 0
    starts = set(r); ends = set(d)
    for i in range(n):
        starts.add(d[i] - ps[i]); ends.add(r[i] + ps[i])
    starts = sorted(x for x in starts if x < h); ends = sorted(x for x in ends if x > 0)
    best = 10**18
    for a in starts:
        for b in ends:
            L = b - a
            if L <= 0:
                continue
            if cap_mode == 'machine':
                cap = sum(max(0, b - (a if a > A[k] else A[k])) for k in range(m))
            else:
                cap = m * L
            tot = 0
            for i in range(n):
                v = ps[i]
                t = r[i] + ps[i] - a
                if t < v: v = t
                t = b - (d[i] - ps[i])
                if t < v: v = t
                if L < v: v = L
                if v > 0: tot += v
            if cap - tot < best:
                best = cap - tot
    return best


def norm_est(inst, rem, A, est):
    out = list(est)
    for i in bititer(rem):
        mn = min(A[k] for k in inst['elig'][i])
        if out[i] < mn:
            out[i] = mn
    return tuple(out)


# ------------------------------------------------------------------ DEC
def decide(inst, h, mode='pot', nodecap=2_000_000, K=48, stats=None,
           slack_cap=10**9, pot_depth=10**9, pot=True, use_subset=False,
           use_clique=False, order='slack', pot_order=False, normalize=True,
           online_gate=None, use_estcut=False, cap_mode='machine', gate_slack=None,
           mint_on=True, mint_tau=1, mint_depth=10**9,
           packset_on=True, packset_maxslack=10, packset_depth=0,
           sop_on=False, sop_nodecap=200000, nondelay=False):
    n, p, m = inst['n'], inst['p'], inst['m']
    full = inst['full']
    if stats is None:
        stats = {}
    st = {'nodes': 0, 'memo_hits': 0, 'pack_calls': 0, 'pack_front_hits': 0,
          'tables': 0, 'sub_front_hits': 0, 'pot_calls': 0, 'pot_prunes': 0,
          'pot_prunes_root': 0, 'front_sizes': [], 'inserts': 0,
          'pot_time': 0.0, 't_run': 0.0, 'root_wit': None,
          'pot_misses': 0, 'gate_off_at': None,
          'estcut_hits': 0, 'estcut_inserts': 0, 'wits': [],
          'sop_calls': 0, 'sop_prunes': 0, 'sop_time': 0.0,
          'sop_chains': 0, 'sop_pack_nodes': 0}
    t0 = time.time()
    use_canon = mode != 'plain'
    use_pack_front = mode in ('front', 'sub', 'pot')
    use_sub_front = mode in ('sub', 'pot')
    use_pot = pot and mode == 'pot'
    bad = {}
    F_pack = {}
    F_sub = {}
    H_est = {}
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

    def machine_choice(i, A, est):
        # non-delay / earliest-start dominance: among eligible machines pick
        # the one minimising the start time; ties -> largest A (keep idle
        # capacity on the other machines).
        best = None
        for k in inst['elig'][i]:
            t = A[k] if A[k] > est[i] else est[i]
            key = (t, -A[k], k)
            if best is None or key < best[0]:
                best = (key, k)
        return best[1]

    def rec(rem, A, est, sump, depth):
        st['nodes'] += 1
        if st['nodes'] > nodecap:
            raise TimeoutError
        if rem == 0: return []
        q = tails(inst, rem)
        est = norm_est(inst, rem, A, est) if normalize else est
        estt = tuple(est[i] for i in bititer(rem))
        Af = canonA(rem, A) if use_canon else A
        key = (rem, Af, estt)
        if bad.get(key, NEG) >= h:
            st['memo_hits'] += 1; return None
        for i in bititer(rem):
            if est[i] + p[i] + q[i] > h:
                bad[key] = h; return None
        if (sump + sum(A) + m - 1)//m > h:
            bad[key] = h; return None
        if use_sub_front:
            fr = F_sub.setdefault((rem, h), [])
            for e2, a2 in fr:
                if dominates(a2, Af) and all(e2[t] <= estt[t] for t in range(len(estt))):
                    st['sub_front_hits'] += 1; bad[key] = h; return None
        # tier 1.25: potential
        phi = 0
        if (use_pot and depth <= pot_depth and
                (online_gate is None or st['pot_misses'] < online_gate)):
            tp = time.time()
            pok, phi, wit = potential(inst, rem, A, est, q, h,
                                      slack_cap=slack_cap,
                                      use_subset=use_subset, use_clique=use_clique,
                                      cap_mode=cap_mode, stats=st, depth=depth,
                                      mint_on=mint_on, mint_tau=mint_tau,
                                      mint_depth=mint_depth,
                                      packset_on=packset_on,
                                      packset_maxslack=packset_maxslack,
                                      packset_depth=packset_depth,
                                      sop_on=sop_on, sop_nodecap=sop_nodecap)
            st['pot_time'] += time.time() - tp
            st['pot_calls'] += 1
            if not pok:
                st['pot_misses'] = 0
                st['pot_prunes'] += 1
                if depth == 0: st['root_wit'] = wit
                if len(st['wits']) < 200: st['wits'].append((rem, A, est, wit))
                if depth == 0: st['pot_prunes_root'] += 1
                if use_pack_front:
                    fr = F_pack.setdefault((rem, h), [])
                    fr.append((estt, Af))
                    if K and len(fr) > K:
                        fr.sort(key=lambda ea: -sum(ea[0])); del fr[K:]
                    st['inserts'] += 1
                    st['front_sizes'].append(len(fr))
                bad[key] = h; return None
            if pok:
                st['pot_misses'] += 1
        st['pack_calls'] += 1
        if use_pack_front:
            fr = F_pack.setdefault((rem, h), [])
            if any(dominates(a2, Af) and
                   all(e2[t] <= estt[t] for t in range(len(estt)))
                   for e2, a2 in fr):
                st['pack_front_hits'] += 1; bad[key] = h; return None
        st['tables'] += 1
        ok = pack_exact(inst, rem, A, est, q, h)
        if not ok:
            if use_pack_front:
                fr = F_pack.setdefault((rem, h), [])
                fr.append((estt, Af))
                if K and len(fr) > K:
                    fr.sort(key=lambda ea: -sum(ea[0])); del fr[K:]
                st['inserts'] += 1
                st['front_sizes'].append(len(fr))
            bad[key] = h; return None
        ready = [i for i in bititer(rem) if not (inst['pmask'][i] & rem)]
        if order == 'slack':
            ready.sort(key=lambda i: (h - q[i] - p[i]) - est[i])
        elif order == 'late':
            ready.sort(key=lambda i: -q[i])
        if pot_order and use_pot:
            # A*: order candidates by the potential of the resulting child
            cand = []
            for i in ready:
                ks = [machine_choice(i, A, est)] if nondelay else inst['elig'][i]
                for k in ks:
                    t = max(A[k], est[i])
                    if t + p[i] + q[i] > h: continue
                    nA = list(A); nA[k] = t + p[i]
                    nest = list(est)
                    for j in inst['succ'][i]:
                        if (rem >> j) & 1 and t + p[i] > nest[j]:
                            nest[j] = t + p[i]
                    _, ph, _ = potential(inst, rem & ~(1 << i), tuple(nA),
                                         tuple(nest), q, h, slack_cap=slack_cap,
                                         use_subset=use_subset, use_clique=use_clique)
                    cand.append((ph, i, k, t, tuple(nA), tuple(nest)))
            cand.sort(key=lambda x: x[0])
            children = [(i, k, t, nA, nest) for _, i, k, t, nA, nest in cand]
        else:
            children = []
            for i in ready:
                ks = [machine_choice(i, A, est)] if nondelay else inst['elig'][i]
                for k in ks:
                    t = max(A[k], est[i])
                    if t + p[i] + q[i] > h: continue
                    nA = list(A); nA[k] = t + p[i]
                    nest = list(est)
                    for j in inst['succ'][i]:
                        if (rem >> j) & 1 and t + p[i] > nest[j]:
                            nest[j] = t + p[i]
                    children.append((i, k, t, tuple(nA), tuple(nest)))
            if order == 'astar':
                def key(ch):
                    _, _, _, nA, nest = ch
                    v = max(nA)
                    for j in bititer(rem & ~(1 << ch[0])):
                        w = nest[j] + p[j] + q[j]
                        if w > v: v = w
                    kk = (sump - p[ch[0]] + sum(nA) + m - 1) // m
                    return max(v, kk)
                children.sort(key=key)
        for i, k, t, nA, nest in children:
            sub = rec(rem & ~(1 << i), nA, nest, sump - p[i], depth + 1)
            if sub is not None:
                return [(i, k, t)] + sub
        if use_sub_front:
            fr = F_sub.setdefault((rem, h), [])
            hit = any(dominates(a2, Af) and all(e2[t] <= estt[t] for t in range(len(estt)))
                      for e2, a2 in fr)
            if not hit:
                fr.append((estt, Af))
                if K and len(fr) > K:
                    fr.sort(key=lambda ea: -sum(ea[0])); del fr[K:]
        bad[key] = h; return None

    if gate_slack is not None:
        est0, q0 = po.heads_tails(inst, 0, [0]*n)
        sl = min_interval_slack(inst, full, tuple([0]*m), tuple(est0), q0, h, cap_mode)
        if sl > gate_slack:
            pot_depth = 0
    try:
        est0, _ = po.heads_tails(inst, 0, [0]*n)
        out = rec(full, tuple([0]*m), tuple(est0), sum(p), 0)
        res = (out is not None, out)
    except TimeoutError:
        res = (None, None); st['timeout'] = True
    st['t_run'] = time.time() - t0
    return res, st
