"""v9.1 ASTRAL: A* / proof-number search with preconditioned intervals.

ASTRAL keeps PACT's fixed-h LP, leaf certificates and BranchProof format.
It changes the *shape of the search*:

  * every state is an interval box [lo_i, hi_i] per job (not a raw set F);
  * a state is expanded only if four checkable preconditions hold
    (domain, LP status, proper split, leaf certificate);
  * the frontier is an AND-OR best-first search.  For a NO node both
    children are needed, so proof number pn = pn_L + pn_R; for a YES
    node one child is enough, so disproof number dn = min(dn_L, dn_R).
  * the search first spends a small proof budget (NO-first), then
    switches to disproof mode (YES-first).  A node that fails a
    precondition gets pn = dn = infinity and can never close a NO node.

The first experiment in this round is deliberately a negative control:
plain A* on the same tree (f = depth, h = 0) is also implemented as
mode='bfs'.  It visits the same AND closure but with heap overhead.
"""
import sys
import time
import math
import heapq

sys.path[:0] = ['exp/v8q', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from sage import BranchProof, _elig_aware, _domain
from apex import EnergyProof
from scale import energy_cert, verify_prep
from pact import (_assign_machines, _integral_schedule,
                  _singleton_leaf)
from sdecc import SDLP
from cert import verify, integer_certificate
from rdf import check_schedule
from po import heads_tails


INF = float('inf')


class Node:
    __slots__ = ('state', 'F', 'bounds', 'depth', 'parent', 'children',
                 'status', 'kind', 'proof', 'schedule', 'machine',
                 'split', 'pn', 'dn', 'expanded', 'pre_fail', 'lp_calls',
                 'guide_t', 'guide_conf', 'guide_side', 'id')

    def __init__(self, nid, state, F, bounds, depth, parent=None):
        self.id = nid
        self.state = state
        self.F = F
        self.bounds = bounds
        self.depth = depth
        self.parent = parent
        self.children = []
        self.status = None          # None | 'no' | 'yes' | 'unknown'
        self.kind = None
        self.proof = None
        self.schedule = None
        self.machine = None
        self.split = None
        self.pn = 1
        self.dn = 1
        self.expanded = False
        self.pre_fail = 0
        self.lp_calls = 0
        self.guide_t = None
        self.guide_conf = 0.0
        self.guide_side = -1


def _state_bounds(lp, lo, hi):
    return [(0, 1) if lo[key[0]] <= key[-1] <= hi[key[0]] else (0, 0)
            for key in lp.cols]


def _state_F(base_lo, base_hi, lo, hi):
    out = []
    for i in range(len(lo)):
        for t in range(base_lo[i], base_hi[i] + 1):
            if t < lo[i] or t > hi[i]:
                out.append((i, t))
    return frozenset(out)


def _state_key(lo, hi):
    return (tuple(lo), tuple(hi))


class PNSResult(dict):
    pass


def pns_decide(inst, h, mode='pns', nodecap=None, proof_budget=None,
               precondition=True, transposition=False, policy=None,
               lookahead=0, root_lp=None, root_res=None, guide=None):
    """Three-valued fixed-h decision by AND-OR best-first search.

    mode:
      'pns'       proof-number first for proof_budget expansions, then
                  disproof-number (YES) first;
      'proof'     only proof-number (find NO);
      'disproof'  only disproof-number (find YES);
      'bfs'       plain A* with f = depth (h = 0);
      'dfs'       depth-first (PACT-like control).
    """
    t0 = time.time()
    n, m, p = inst['n'], inst['m'], inst['p']
    if precondition:
        cert = energy_cert(inst, h)
        if cert is not None and verify_prep(inst, h, cert):
            return PNSResult(verdict=False, proof=EnergyProof(inst, h, cert),
                             schedule=None, machine=None, nodes=0,
                             expanded=0, depth=0, lp_solves=0, cert_lp=0,
                             pre_fail=0, trans_hits=0, pn=0, dn=INF,
                             t=time.time() - t0, mode=mode,
                             pre_energy=1, proof_kind=cert.get('kind'),
                             root_key=())
    elig = _elig_aware(inst)
    est, q = heads_tails(inst, 0, [0] * n)
    if root_lp is not None and root_res is not None and root_lp.inst is inst:
        lp = root_lp
    else:
        lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig)

    base_lo = [10 ** 9] * n
    base_hi = [-1] * n
    for key in lp.cols:
        i, t = key[0], key[-1]
        base_lo[i] = min(base_lo[i], t)
        base_hi[i] = max(base_hi[i], t)
    for i in range(n):
        if base_hi[i] < base_lo[i]:
            # no LP column: empty domain is already a NO leaf
            F = frozenset((i, t) for t in range(_domain(inst, h, i)[0],
                                                _domain(inst, h, i)[1] + 1))
            proof = ('empty', F, i)
            bp = BranchProof(inst, h, proof)
            return PNSResult(verdict=False, proof=bp, schedule=None,
                             machine=None, nodes=0, expanded=0, depth=0,
                             lp_solves=0, cert_lp=0, pre_fail=0,
                             trans_hits=0, pn=0, dn=INF, t=0.0,
                             mode=mode, root_key=_state_key(base_lo, base_hi))

    policy = policy or {}
    guide_starts = guide[0] if guide is not None else None
    stats = dict(nodes=0, expanded=0, depth=0, lp_solves=0, cert_lp=0,
                 pre_fail=0, trans_hits=0, unknown=False, holes=0,
                 root_reused=0, split_fail=0, leaf_fail=0,
                 insufficient=False, yes_depth=None)
    table = {}
    counter = [0]

    def new_node(state, F, depth, parent=None, bounds=None):
        if bounds is None:
            bounds = _state_bounds(lp, state[0], state[1])
        nd = Node(counter[0], state, F, bounds, depth, parent)
        counter[0] += 1
        if transposition:
            k = (h, _state_key(*state))
            hit = table.get(k)
            if hit is not None:
                stats['trans_hits'] += 1
                return hit
            table[k] = nd
        return nd

    def allowed_times(i, state):
        lo, hi = state
        return list(range(lo[i], hi[i] + 1)) if lo[i] <= hi[i] else []

    def choose(z, state):
        lo, hi = state
        cand = []
        for i in range(n):
            times = allowed_times(i, state)
            if len(times) <= 1:
                continue
            dist = []
            for t in times:
                v = 0.0
                for c, key in enumerate(lp.cols):
                    if key[0] == i and key[-1] == t and z[c] > 1e-12:
                        v += z[c]
                dist.append((t, v))
            mass = sum(v for _, v in dist)
            frac = sum(v for _, v in dist if 1e-7 < v < 1 - 1e-7)
            if frac <= 1e-7:
                continue
            cand.append((i, dist, mass))
        if not cand:
            return None, None
        weights = policy.get('weights')
        if weights:
            # optional scorer; only affects order, never soundness
            def score(c):
                i, dist, mass = c
                feats = dict(
                    mass=mass, q=float(q[i]), p=float(p[i]),
                    succ=float(len(inst['succ'][i])),
                    pred=float(len(inst['pred'][i])),
                    width=float(len(dist)),
                    slack=float(h - q[i] - p[i] - est[i]))
                return sum(weights.get(k, 0.0) * v for k, v in feats.items())
            cand.sort(key=lambda c: (-score(c), c[0]))
        else:
            cand.sort(key=lambda c: (-c[2], -q[c[0]],
                                     -len(inst['succ'][c[0]]), c[0]))
        i, dist, mass = cand[0]
        split = policy.get('split', 0.5)
        acc = 0.0
        mid = dist[0][0]
        for t, v in dist:
            acc += v
            if acc >= split * mass:
                mid = t
                break
        times = [t for t, _ in dist]
        if not any(t > mid for t in times) or not any(t <= mid for t in times):
            mid = times[len(times) // 2 - 1]
        if not any(t > mid for t in times) or not any(t <= mid for t in times):
            return None, None
        t_star = max(dist, key=lambda tv: (tv[1], -tv[0]))[0]
        if all(v <= 1e-12 for _, v in dist):
            t_star = mid
        left_mass = sum(v for t, v in dist if t <= mid)
        right_mass = mass - left_mass
        side = 1 if right_mass > left_mass + 1e-12 else 0
        conf = max(left_mass, right_mass) / max(mass, 1e-12)
        return i, mid, t_star, conf, side

    def leaf_cert(F):
        stats['cert_lp'] += 1
        cert = integer_certificate(inst, h, use_dom=True,
                                   elig_aware=elig, forbid=F)
        if cert is not None and verify(inst, h, cert, forbid=F):
            return ('leaf', F, cert)
        for i in range(n):
            l, u = _domain(inst, h, i)
            if l <= u and all((i, t) in F for t in range(l, u + 1)):
                return ('empty', F, i)
        return None

    def mark(nd, status, kind=None, proof=None, schedule=None,
             machine=None):
        nd.status = status
        nd.kind = kind
        nd.proof = proof
        nd.schedule = schedule
        nd.machine = machine
        if status == 'no':
            nd.pn, nd.dn = 0, INF
        elif status == 'yes':
            nd.pn, nd.dn = INF, 0
        else:
            nd.pn = nd.dn = INF

    def expand(nd):
        if nd.expanded:
            return
        nd.expanded = True
        stats['expanded'] += 1
        stats['depth'] = max(stats['depth'], nd.depth)
        res = None
        if (nd.depth == 0 and root_res is not None):
            res = root_res
            stats['root_reused'] += 1
        else:
            if nodecap is not None and stats['nodes'] >= nodecap:
                stats['unknown'] = True
                stats['holes'] += 1
                mark(nd, 'unknown', 'cap')
                return
            stats['nodes'] += 1
            stats['lp_solves'] += 1
            nd.lp_calls += 1
            res = lp.solve(nd.bounds)
        if res is None or res.status not in (0, 2):
            if precondition:
                nd.pre_fail += 1
                stats['pre_fail'] += 1
            else:
                stats['unknown'] = True
            mark(nd, 'unknown', 'lp')
            return
        if res.status == 2:
            proof = leaf_cert(nd.F)
            if proof is None:
                stats['leaf_fail'] += 1
                if precondition:
                    stats['pre_fail'] += 1
                mark(nd, 'unknown', 'leaf')
                return
            mark(nd, 'no', proof[0], proof)
            return
        z = res.x
        lo, hi = nd.state
        frac = False
        for c, key in enumerate(lp.cols):
            if 1e-7 < z[c] < 1 - 1e-7 and nd.bounds[c] != (0, 0):
                frac = True
                break
        if not frac:
            got = _integral_schedule(inst, lp, z, elig)
            if got is not None:
                stats['yes_depth'] = nd.depth
                mark(nd, 'yes', 'integral', schedule=got[0],
                     machine=got[1])
                return
            singleton = _singleton_leaf(inst, h, nd.F, lp, nd.bounds)
            if singleton is not None:
                stats['yes_depth'] = nd.depth
                mark(nd, 'yes', 'singleton', schedule=singleton[1],
                     machine=singleton[2])
                return
            i = None
            mid = None
            for j in range(n):
                times = allowed_times(j, nd.state)
                if len(times) > 1:
                    i = j
                    mid = times[len(times) // 2 - 1]
                    break
            if i is None:
                if precondition:
                    stats['pre_fail'] += 1
                    nd.pre_fail += 1
                stats['insufficient'] = True
                mark(nd, 'unknown', 'insufficient')
                return
            nd.guide_t = mid
            nd.guide_conf = 0.0
            nd.guide_side = -1
        else:
            chosen = choose(z, nd.state)
            if chosen[0] is None:
                if precondition:
                    stats['pre_fail'] += 1
                    nd.pre_fail += 1
                stats['insufficient'] = True
                mark(nd, 'unknown', 'insufficient')
                return
            i, mid, nd.guide_t, nd.guide_conf, nd.guide_side = chosen
        lo, hi = nd.state
        if not (lo[i] <= mid < hi[i]):
            # proper-split precondition
            if precondition:
                stats['pre_fail'] += 1
                nd.pre_fail += 1
            stats['split_fail'] += 1
            mark(nd, 'unknown', 'split')
            return
        # BranchProof convention: first child forbids the > mid half
        # (allowed times <= mid), second child forbids the <= mid half.
        loL, hiL = list(lo), list(hi)
        hiL[i] = mid
        loR, hiR = list(lo), list(hi)
        loR[i] = mid + 1
        # both children nonempty by construction
        FL = _state_F(base_lo, base_hi, loL, hiL)
        FR = _state_F(base_lo, base_hi, loR, hiR)
        left = new_node((tuple(loL), tuple(hiL)), FL, nd.depth + 1, nd)
        right = new_node((tuple(loR), tuple(hiR)), FR, nd.depth + 1, nd)
        left.parent = nd
        right.parent = nd
        nd.children = [left, right]
        nd.split = (i, mid)

    def backprop(nd):
        while nd is not None:
            if nd.status == 'no':
                nd.pn, nd.dn = 0, INF
            elif nd.status == 'yes':
                nd.pn, nd.dn = INF, 0
            elif nd.children:
                pn = 0.0
                dn = INF
                for ch in nd.children:
                    if ch.pn >= INF:
                        pn = INF
                    elif pn < INF:
                        pn += ch.pn
                    if ch.dn < dn:
                        dn = ch.dn
                nd.pn, nd.dn = pn, dn
                if pn == 0:
                    nd.status = 'no'
                    nd.kind = 'branch'
                    nd.proof = ('node', nd.split[0], nd.split[1],
                                nd.F, nd.children[0].proof,
                                nd.children[1].proof)
                elif dn == 0:
                    nd.status = 'yes'
                    nd.kind = 'branch'
                    for ch in nd.children:
                        if ch.dn == 0:
                            nd.schedule = ch.schedule
                            nd.machine = ch.machine
                            break
                else:
                    nd.status = None
            else:
                if nd.status == 'unknown':
                    nd.pn = nd.dn = INF
                else:
                    nd.pn = nd.dn = 1
            nd = nd.parent

    def guide_dist(nd):
        if guide_starts is None:
            return 0
        lo, hi = nd.state
        return sum(1 for i in range(n)
                   if not (lo[i] <= guide_starts[i] <= hi[i]))

    def select(root, goal):
        nd = root
        while nd.children and nd.status is None:
            cand = [ch for ch in nd.children if ch.status is None]
            if not cand:
                return nd
            if goal == 'no':
                nd = min(cand, key=lambda c: (c.pn, c.dn, c.depth, c.id))
            else:
                nd = min(cand, key=lambda c: (c.dn, guide_dist(c),
                                              c.pn, c.depth, c.id))
        return nd

    def guided_children(nd):
        left, right = nd.children
        i = nd.split[0]
        if guide_starts is not None:
            g = guide_starts[i]
        elif nd.guide_side >= 0:
            if nd.guide_side == 1:
                need = policy.get('guide_conf_right',
                                  policy.get('guide_conf', 0.0))
            else:
                need = policy.get('guide_conf_left',
                                  policy.get('guide_conf', 0.0))
            if nd.guide_conf < need:
                return [left, right]
            if nd.guide_side == 1:
                return [right, left]
            return [left, right]
        else:
            return [left, right]
        if g > nd.split[1]:
            return [right, left]
        return [left, right]

    def guide_dfs(nd):
        if nd.status is not None:
            return
        expand(nd)
        if nd.status is not None or not nd.children:
            return
        for ch in guided_children(nd):
            guide_dfs(ch)
            if ch.status == 'yes':
                backprop(ch)
                return
        backprop(nd)

    root_state = (tuple(base_lo), tuple(base_hi))
    root = new_node(root_state, frozenset(), 0, None)
    # root bound precheck: if a job has no allowed start, empty leaf
    if any(root_state[0][i] > root_state[1][i] for i in range(n)):
        for i in range(n):
            if root_state[0][i] > root_state[1][i]:
                F = frozenset((i, t) for t in range(
                    _domain(inst, h, i)[0], _domain(inst, h, i)[1] + 1))
                proof = ('empty', F, i)
                bp = BranchProof(inst, h, proof)
                return PNSResult(verdict=False, proof=bp,
                                 schedule=None, machine=None,
                                 **stats, pn=0, dn=INF, t=0.0,
                                 mode=mode, root_key=root_state)
    expand(root)
    backprop(root)
    if proof_budget is None:
        proof_budget = min(16, nodecap) if nodecap is not None else 16
    phase = 'no'
    while root.status is None:
        if nodecap is not None and stats['expanded'] >= nodecap:
            stats['unknown'] = True
            break
        if mode in ('proof', 'pns') and phase == 'no':
            goal = 'no'
        elif mode in ('disproof',):
            goal = 'yes'
        elif mode == 'guide_dfs':
            guide_dfs(root)
            break
        elif mode == 'bfs':
            # plain A* with f = depth (h = 0) is just shallow-first
            leaf = None
            stack = [root]
            while stack:
                x = stack.pop()
                if not x.children and x.status is None:
                    if leaf is None or (x.depth, x.id) < (leaf.depth, leaf.id):
                        leaf = x
                elif x.status is None:
                    stack.extend(x.children)
            if leaf is None:
                break
            expand(leaf)
            backprop(leaf)
            continue
        elif mode == 'dfs':
            leaf = None
            stack = [root]
            while stack:
                x = stack.pop()
                if not x.children and x.status is None:
                    leaf = x
                    break
                elif x.status is None:
                    stack.extend(x.children)
            if leaf is None:
                break
            expand(leaf)
            backprop(leaf)
            continue
        else:
            goal = 'yes' if phase == 'yes' else 'no'
        if goal == 'yes' and mode == 'pns':
            # switch only once, after the proof budget is spent
            pass
        leaf = select(root, goal)
        if leaf is None or leaf.status is not None:
            # no unsolved leaf in this mode; if proof phase and root is
            # still open, switch to disproof
            if mode == 'pns' and phase == 'no':
                phase = 'yes'
                continue
            break
        expand(leaf)
        backprop(leaf)
        if (mode == 'pns' and phase == 'no'
                and stats['expanded'] >= proof_budget):
            phase = 'yes'
        if (mode == 'pns' and phase == 'no'
                and root.pn >= INF):
            phase = 'yes'
    stats['t'] = round(time.time() - t0, 5)
    stats['root_key'] = root_state
    if root.status == 'no':
        bp = BranchProof(inst, h, root.proof)
        if not bp.audit_rdf():
            stats['unknown'] = True
            stats['audit_fail'] = True
            stats['raw_proof'] = root.proof
            return PNSResult(verdict=None, proof=None, schedule=None,
                             machine=None, **stats, pn=root.pn,
                             dn=root.dn, mode=mode)
        return PNSResult(verdict=False, proof=bp, schedule=None,
                         machine=None, **stats, pn=root.pn, dn=root.dn,
                         mode=mode)
    if root.status == 'yes':
        s, mach = root.schedule, root.machine
        cmax = max(s[i] + p[i] for i in range(n))
        if s is not None and mach is not None and check_schedule(
                inst, h, s, mach):
            return PNSResult(verdict=True, proof=None, schedule=s,
                             machine=mach, **stats, pn=root.pn,
                             dn=root.dn, mode=mode)
    return PNSResult(verdict=None, proof=None, schedule=None, machine=None,
                     **stats, pn=root.pn, dn=root.dn, mode=mode)
