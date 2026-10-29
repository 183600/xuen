"""PACE-PiA v2.1: v2.0 plus tier 0.10 MAP (Machine-Aware Partition).

MAP compiles, for every machine k, the single-machine postcondition table

    f_k[0] = A_k
    f_k[S] = min_{i in sink(S), k in E_i} max(f_k[S-i], est_i) + p_i
             subject to completion <= h - q_i.

It then asks whether R can be partitioned into blocks, each block assigned to a
*distinct* eligible machine with f_k[block] < INF.  If not, the state is NO.

This is strictly stronger than the block-count partition number beta when
eligibility or machine availability is heterogeneous: beta only counts blocks,
MAP also matches blocks to machines.  MAP is a relaxation, so MAP=YES is
"unknown", never a proof of feasibility.

The C kernel is exp/v24/map_lib.c (ctypes wrapper map_lib.py).  The search
layers of v2.0 (DHD, DCD, HPACK, ...) are unchanged.
"""
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

v1.9 PACE-R adds tier 0.25 RHD (release-horizon dominance): before DCD, keep
only ready tasks released strictly before the earliest possible completion
v(sigma) = min_i (est_i + p_i).  This is the minimal-element quotient of the
strict partial order  j < i  iff  est_j + p_j <= est_i.  Because an RHD-dropped
task can never DCD-dominate an RHD-kept one, the two quotients commute:

    K = Max_DCD( Min_RHD(READY) ).

v1.8 PACE-D adds tier 0.3 DCD (descendant-closure dominance): branch only on
the maximal ready tasks under

    p_i=p_j, E_i=E_j, D_i subset D_j, est_j <= est_i

where D_t = desc(t) & R is the residual descendant set.  The exchange lemma
is proved in research.md (theorem 1); the skyline + same-est eviction is in
dcd_branch_set() below.
"""
import sys, time
sys.path.insert(0, 'exp/v13')
sys.path.insert(0, 'exp/v15')
import po, mint
sys.path.insert(0, 'exp/v24')
import map_lib
import cps_lib
import order_sop as sop
from po import bititer, tails, pack_exact, dominates

NEG = -1
SOUND_FRONT = True   # False reproduces the v1.5 A-only PACK front bug


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
              sop_on=False, sop_nodecap=200000, omd=False,
              hpack_on=False, hpack_tau=2, hpack_nodecap=4000):
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
            # ---- tier 1.36: HPACK (non-preemptive obligatory packing) ----
            if hpack_on and sl <= hpack_tau and tot > 0:
                caps2 = [max(0, b - (a if a > A[k] else A[k])) for k in range(m)]
                items = [(mand[i], i) for i in range(n) if mand[i] > 0]
                items.sort(reverse=True)
                rem = caps2[:]
                uni = all(el[i] == list(range(m)) for _, i in items)
                hp_nodes = [0]
                def _hp(pos):
                    hp_nodes[0] += 1
                    if hp_nodes[0] > hpack_nodecap:
                        raise TimeoutError
                    if pos == len(items):
                        return True
                    sz, idx = items[pos]
                    seen = set()
                    for k in el[idx]:
                        if rem[k] < sz:
                            continue
                        if uni and rem[k] in seen:
                            continue
                        if uni:
                            seen.add(rem[k])
                        rem[k] -= sz
                        if _hp(pos + 1):
                            rem[k] += sz
                            return True
                        rem[k] += sz
                    return False
                try:
                    hp_ok = _hp(0)
                except TimeoutError:
                    hp_ok = True          # cap hit: do not claim a certificate
                if stats is not None:
                    stats['hpack_calls'] = stats.get('hpack_calls', 0) + 1
                    stats['hpack_nodes'] = stats.get('hpack_nodes', 0) + hp_nodes[0]
                if not hp_ok:
                    if stats is not None:
                        stats['hpack_prunes'] = stats.get('hpack_prunes', 0) + 1
                    return False, max(phi, b + 1), ('hpack', a, b, mand, caps2)
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


def check_hpack(inst, rem, A, est, q, h, a, b, mand, caps):
    """Independent recheck of an HPACK witness.

    Recompute the obligatory overlaps and capacities, then run a *different*
    search (increasing item order + memo on the sorted remaining-capacity
    tuple) to confirm that the items cannot be packed.  Returns True iff the
    witness is a valid refutation.
    """
    p, m = inst['p'], inst['m']
    tasks = list(bititer(rem))
    n = len(tasks)
    r = [est[i] for i in tasks]
    ps = [p[i] for i in tasks]
    d = [h - q[i] for i in tasks]
    el = [inst['elig'][i] for i in tasks]
    L = b - a
    if L <= 0:
        return False
    calc = [0] * n
    for i in range(n):
        v = ps[i]
        t = r[i] + ps[i] - a
        if t < v: v = t
        t = b - (d[i] - ps[i])
        if t < v: v = t
        if L < v: v = L
        if v > 0: calc[i] = v
    if calc != list(mand):
        return False
    caps2 = [max(0, b - (a if a > A[k] else A[k])) for k in range(m)]
    if caps2 != list(caps):
        return False
    items = [(mand[i], i) for i in range(n) if mand[i] > 0]
    items.sort()                       # ascending: different order than solver
    k = len(items)
    memo = {}
    def dfs(pos, remcaps):
        if pos == k:
            return True
        key = (pos, remcaps)
        if key in memo:
            return memo[key]
        sz, idx = items[pos]
        for mach in el[idx]:
            if remcaps[mach] >= sz:
                nr = list(remcaps); nr[mach] -= sz
                # keep machine-indexed capacities: eligibility may differ
                if dfs(pos + 1, tuple(nr)):
                    memo[key] = True; return True
        memo[key] = False
        return False
    return not dfs(0, tuple(caps2))


def check_potential_witness(inst, rem, A, est, q, h, wit):
    """Independent O(n) recheck of a POT witness (the certificate checker)."""
    if wit[0] == 'sop':
        return sop.check_cert(inst, h, wit[1])
    if wit[0] == 'hpack':
        return check_hpack(inst, rem, A, est, q, h, wit[1], wit[2], wit[3], wit[4])
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
def dcd_branch_set(ready, p, elig, fut, est):
    """Maximal elements of the descendant-closure dominance preorder.

    i is dominated by j iff p_i=p_j, E_i=E_j, D_i subset D_j, est_j <= est_i.
    `fut(t)` returns D(t) (a bitmask); `ready` is a list of task ids.

    Returns (keep, drop).  keep is exactly the set of maximal elements.
    """
    ordered = sorted(ready, key=lambda i: (est[i], i))
    keep = []
    drop = set()
    eq_drop = set()
    for i in ordered:
        di = fut(i)
        dominated = False
        for j in keep:
            if p[j] != p[i] or elig[j] != elig[i]:
                continue
            if (di & ~fut(j)) == 0:          # D_i subset D_j
                dominated = True
                if di == fut(j):
                    eq_drop.add(i)
                break
        if dominated:
            drop.add(i)
            continue
        # i can dominate a kept j only when est is equal: D_j is a strict
        # subset of D_i.  Keeping only prefix maximal elements is WRONG here.
        nk = []
        for j in keep:
            dj = fut(j)
            if (p[j] == p[i] and elig[j] == elig[i] and est[j] == est[i]
                    and dj != di and (dj & ~di) == 0):
                drop.add(j)
            else:
                nk.append(j)
        keep = nk
        keep.append(i)
    return keep, drop, eq_drop


def dhd_branch_set(ready, p, est, q, rem, h):
    """Dual-horizon dominance: keep only tasks with est_i <= mu, where

        mu = min( min_{ready}(est_i+p_i) - 1,  min_{rem}(h - p_i - q_i) ).

    The second term is the *latest-start* horizon lambda: in any feasible
    schedule s_i <= lst_i = h - p_i - q_i, so a ready j with est_j > lambda
    always starts strictly after the minimiser i*.  Hence j is never the
    earliest task and may be dropped from the first-position branch set.
    """
    v = min(est[i] + p[i] for i in ready)
    lam = h
    for i in bititer(rem):
        t = h - p[i] - q[i]
        if t < lam:
            lam = t
    mu = v - 1
    if lam < mu:
        mu = lam
    keep = [i for i in ready if est[i] <= mu]
    if not keep:                      # cannot happen: mu >= est_min
        keep = [min(ready, key=lambda i: est[i])]
    return keep, set(ready) - set(keep)


def rhd_branch_set(ready, p, est):
    """Minimal elements of the release-completion order.

    j < i  iff  est_j + p_j <= est_i.  The minimal elements are exactly

        { i : est_i < min_j (est_j + p_j) },

    because the minimiser of est_j+p_j can never be dropped by itself
    (est_i < est_i + p_i) and every other task with est_i >= v has that
    minimiser as a witness.  O(d) time, O(d) space.
    """
    v = min(est[i] + p[i] for i in ready)
    keep = [i for i in ready if est[i] < v]
    return keep, set(ready) - set(keep)


def decide(inst, h, mode='pot', nodecap=2_000_000, K=48, stats=None,
           slack_cap=10**9, pot_depth=10**9, pot=True, use_subset=False,
           use_clique=False, order='slack', pot_order=False, normalize=True,
           online_gate=None, use_estcut=False, cap_mode='machine', gate_slack=None,
           mint_on=True, mint_tau=1, mint_depth=10**9,
           packset_on=True, packset_maxslack=10, packset_depth=0,
           sop_on=False, sop_nodecap=200000, omd=False,
           odom=False, dcd=False, dcd_direct=False, rhd=False, dhd=False,
           hpack_on=False, hpack_tau=2,
           hpack_nodecap=4000, map_on=False, map_depth=10**9,
           map_ncap=16, map_tau=4, map_slack_cap=10**9, map_wit=0,
           cps_on=False, cps_tau=4, cps_depth=0, cps_ncap=16,
           cps_nodecap=300000, cps_gate_fan=1, A0=None, est_init=None):
    n, p, m = inst['n'], inst['p'], inst['m']
    full = inst['full']
    if rhd or dhd:
        # the RHD face of DHD (the v-1 term) needs the NORM invariant
        #   est_i >= min_{k in E_i} A_k  for every remaining i.
        normalize = True
    if stats is None:
        stats = {}
    st = {'nodes': 0, 'memo_hits': 0, 'pack_calls': 0, 'pack_front_hits': 0,
          'tables': 0, 'sub_front_hits': 0, 'pot_calls': 0, 'pot_prunes': 0,
          'pot_prunes_root': 0, 'front_sizes': [], 'inserts': 0,
          'pot_time': 0.0, 't_run': 0.0, 'root_wit': None,
          'pot_misses': 0, 'gate_off_at': None,
          'estcut_hits': 0, 'estcut_inserts': 0, 'wits': [],
          'sop_calls': 0, 'sop_prunes': 0, 'sop_time': 0.0,
          'sop_chains': 0, 'sop_pack_nodes': 0,
          'hpack_calls': 0, 'hpack_prunes': 0, 'hpack_nodes': 0,
          'odom_skips': 0, 'dcd_skips': 0,
          'rhd_calls': 0, 'rhd_drops': 0, 'rhd_fan_before': 0, 'rhd_fan_after': 0,
          'dcd_fan_before': 0, 'dcd_fan_after': 0,
          'dcd_fan_max_before': 0, 'dcd_fan_max_after': 0,
          'dcd_sink_skips': 0, 'dcd_strict_skips': 0, 'dcd_eq_skips': 0,
          'map_calls': 0, 'map_prunes': 0, 'map_time': 0.0,
          'cps_calls': 0, 'cps_prunes': 0, 'cps_time': 0.0,
          'cps_placements': 0, 'cps_res_nodes': 0, 'cps_memo': 0}
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

    def front_hit(fr, estt, Af):
        if SOUND_FRONT:
            return any(dominates(a2, Af) and
                       all(e2[t] <= estt[t] for t in range(len(estt)))
                       for e2, a2 in fr)
        return any(dominates(a2, Af) for _, a2 in fr)

    def front_put(fr, estt, Af):
        fr.append((estt, Af))
        if K and len(fr) > K:
            fr.sort(key=lambda ea: -sum(ea[0]))
            del fr[K:]

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
                                      sop_on=sop_on, sop_nodecap=sop_nodecap,
                                      hpack_on=hpack_on, hpack_tau=hpack_tau,
                                      hpack_nodecap=hpack_nodecap)
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
                    front_put(fr, estt, Af)
                    st['inserts'] += 1
                    st['front_sizes'].append(len(fr))
                bad[key] = h; return None
            if pok:
                st['pot_misses'] += 1
        st['pack_calls'] += 1
        if use_pack_front:
            fr = F_pack.setdefault((rem, h), [])
            if front_hit(fr, estt, Af):
                st['pack_front_hits'] += 1; bad[key] = h; return None
        st['tables'] += 1
        ok = pack_exact(inst, rem, A, est, q, h)
        if not ok:
            if use_pack_front:
                fr = F_pack.setdefault((rem, h), [])
                front_put(fr, estt, Af)
                st['inserts'] += 1
                st['front_sizes'].append(len(fr))
            bad[key] = h; return None
        # ---- tier 0.10 MAP: machine-aware partition certificate ----
        nrem = bin(rem).count('1')
        if map_on and depth <= map_depth and (nrem <= map_ncap or map_wit):
            lb0 = max(max(est[i] + p[i] + q[i] for i in bititer(rem)),
                      (sump + m - 1) // m, max(p[i] for i in bititer(rem)))
            if h - lb0 <= map_tau:
                _tm = time.time()
                ok_map = True
                if nrem <= map_ncap:
                    ok_map = map_lib.map_check(inst, rem, A, est, q, h)
                elif map_wit:
                    tasks = list(bititer(rem))
                    tasks.sort(key=lambda i: -(p[i] / max(1, h - q[i] - est[i])))
                    W = 0
                    for i in tasks[:map_wit]:
                        W |= 1 << i
                    ok_map = map_lib.map_check(inst, W, A, est, q, h)
                st['map_time'] += time.time() - _tm
                st['map_calls'] += 1
                if not ok_map:
                    st['map_prunes'] += 1
                    bad[key] = h
                    return None
        ready = [i for i in bititer(rem) if not (inst['pmask'][i] & rem)]
        if order == 'slack':
            ready.sort(key=lambda i: (h - q[i] - p[i]) - est[i])
        elif order == 'late':
            ready.sort(key=lambda i: -q[i])
        elif order == 'loss':
            mn = min(A)
            ready.sort(key=lambda i: (max(mn, est[i]) + p[i] + q[i], -q[i]))
        ready_all = list(ready)
        if rhd or dhd:
            if dhd:
                ready, rhd_drop = dhd_branch_set(ready, p, est, q, rem, h)
            else:
                ready, rhd_drop = rhd_branch_set(ready, p, est)
            st['rhd_calls'] += 1
            st['rhd_drops'] += len(rhd_drop)
            st['rhd_fan_before'] += len(ready_all)
            st['rhd_fan_after'] += len(ready)
            if not ready:
                # cannot happen: argmin est_i+p_i always survives
                st['rhd_empty'] = st.get('rhd_empty', 0) + 1
                ready = ready_all[:1]
        drop = set()
        if odom:
            cls = {}
            for i in ready:
                sig = (p[i], tuple(inst['elig'][i]),
                       tuple(sorted(j for j in inst['succ'][i] if (rem >> j) & 1)))
                cls.setdefault(sig, []).append(i)
            for g in cls.values():
                if len(g) > 1:
                    g.sort(key=lambda i: (est[i], i))
                    for i in g[1:]:
                        drop.add(i)
            st['odom_skips'] += len(drop)
        if dcd:
            # ---- v1.8 descendant-closure dominance (DCD), tier 0.3 ----
            if dcd_direct:
                sm = {}
                for t in ready:
                    msk = 0
                    for j in inst['succ'][t]:
                        if (rem >> j) & 1:
                            msk |= 1 << j
                    sm[t] = msk
                fut = lambda t: sm[t]
            else:
                fut = lambda t: inst['desc'][t] & rem
            keep2, drop2, eq_drop = dcd_branch_set(ready, p, inst['elig'], fut, est)
            drop = drop | drop2
            keep = keep2
            for i in drop2:
                di = fut(i)
                if di == 0:
                    st['dcd_sink_skips'] += 1
                else:
                    st['dcd_strict_skips'] += 1
            st['dcd_eq_skips'] += len(eq_drop)
            st['dcd_skips'] += len(drop2)
            st['dcd_fan_before'] += len(ready)
            st['dcd_fan_after'] += len(keep)
            st['dcd_fan_max_before'] = max(st['dcd_fan_max_before'], len(ready))
            st['dcd_fan_max_after'] = max(st['dcd_fan_max_after'], len(keep))
        # ---- tier 0.15 CPS: critical-path skeleton certificate ----
        if cps_on and depth <= cps_depth and nrem <= cps_ncap:
            eff_n = sum(1 for i in ready if i not in drop)
            if eff_n > cps_gate_fan:
                cp = max(est[i] + p[i] + q[i] for i in bititer(rem))
                if h - cp <= cps_tau:
                    _tc = time.time()
                    verdict = cps_lib.cps_certify(
                        inst, rem, A, est, q, h, tau=cps_tau,
                        nodecap=cps_nodecap, stats=st)
                    st['cps_time'] += time.time() - _tc
                    st['cps_calls'] += 1
                    if verdict is False:
                        st['cps_prunes'] += 1
                        bad[key] = h
                        return None
        if pot_order and use_pot:
            # A*: order candidates by the potential of the resulting child
            cand = []
            for i in ready:
                if i in drop:
                    continue
                ks = [machine_choice(i, A, est)] if omd else inst['elig'][i]
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
                                         use_subset=use_subset, use_clique=use_clique,
                                         hpack_on=hpack_on, hpack_tau=hpack_tau,
                                         hpack_nodecap=hpack_nodecap)
                    cand.append((ph, i, k, t, tuple(nA), tuple(nest)))
            cand.sort(key=lambda x: x[0])
            children = [(i, k, t, nA, nest) for _, i, k, t, nA, nest in cand]
        else:
            children = []
            for i in ready:
                if i in drop:
                    continue
                ks = [machine_choice(i, A, est)] if omd else inst['elig'][i]
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
        if est_init is not None:
            est0 = list(est_init)
        A_start = tuple(A0) if A0 is not None else tuple([0]*m)
        out = rec(full, A_start, tuple(est0), sum(p), 0)
        res = (out is not None, out)
    except TimeoutError:
        res = (None, None); st['timeout'] = True
    st['t_run'] = time.time() - t0
    return res, st
