"""v9.2 TAMO: termination-aware multi-leaf optimization over ICF.

TAMO keeps the v9.0 ICF invariant

    pi : NO(L-1),  (s,m) : feasible with Cmax(s)=U,  L <= U,

and lifts it from one leaf to a live frontier.  The new state is

    (T, {(F_l, L_l, pi_l, st_l)}, s, m, U, rho)

where T is a partition tree of start-time boxes, st_l is open/closed, and
rho is a ranking certificate.  The three transitions that matter are

    PROBE-YES : probe an open leaf at h < U; a schedule of length c <= h
                replaces U by c (or leaves it unchanged if c >= U).
    PROBE-NO  : a replayed NO(h) proof raises the leaf's local bound to h+1.
    REFINE    : an UNKNOWN answer is never retried in place; the leaf is
                split into two strictly smaller boxes.  This is the step
                that makes a budgeted oracle total and gives termination
                without a cut loop.

The rank is

    rho = ( U,  sortdesc{ mu(F_l) : leaves l },  sum_{open l} (U - L_l) )

with mu(F) = sum_i |D_i(F, H0)| computed at the *fixed* initial horizon
H0 = U0-1.  PROBE-YES decreases U; PROBE-NO decreases the third
component; REFINE replaces one mu by two strictly smaller values, so the
sorted multiset decreases.  The rank is checked after every transition.

The certificate format is a *partial frontier*: open leaves carry proofs
at their local horizons L_l-1 (possibly below the target U-1), closed
leaves carry proofs at horizons >= U-1.  Partition checks project the
forbidden sets onto the current target horizon, because the target only
shrinks: a partition built for a larger horizon remains a partition for
every smaller one.

Module entry points:
    TamoFrontier           auditable tree (target, leaves, schedule)
    TamoPartialCertificate arbitrary intermediate state
    TamoCertificate        final L=U certificate
    run_tamo               one instance, one (B, policy, split) setting
    weak_initial           critical-path L + serial U for synthetic tests
"""
import sys
import time
import heapq

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from sage import _domain
from rdf import check_schedule
from icf import CertLeafProof, _proof_forbid, cmax
from pact import PACT, pact_decide
from po import heads_tails


# ------------------------------------------------------------------ boxes
def domain_times(inst, h, i):
    lo, hi = _domain(inst, h, i)
    return range(lo, hi + 1)


def allowed_times(inst, h, i, F):
    return [t for t in domain_times(inst, h, i) if (i, t) not in F]


def empty_job(inst, h, F):
    """A job with no allowed start at horizon h, or None."""
    for i in range(inst['n']):
        if not allowed_times(inst, h, i, F):
            return i
    return None


def project_forbid(inst, h, F):
    """Keep only forbidden pairs inside the horizon-h start domains."""
    out = set()
    for i, t in F:
        lo, hi = _domain(inst, h, i)
        if lo <= t <= hi:
            out.add((i, t))
    return frozenset(out)


def box_measure(inst, H0, F):
    return sum(len(allowed_times(inst, H0, i, F))
               for i in range(inst['n']))


# ------------------------------------------------------------------ live tree
class Leaf:
    __slots__ = ('F', 'L', 'proof', 'closed', 'h', 'mu',
                 'parent', 'side')

    def __init__(self, F, L, proof, mu, parent=None, side=None):
        self.F = frozenset(F)
        self.L = int(L)
        self.proof = proof
        self.closed = False
        self.h = None
        self.mu = int(mu)
        self.parent = parent
        self.side = side


class Split:
    __slots__ = ('F', 'i', 'mid', 'lo', 'hi')

    def __init__(self, F, i, mid):
        self.F = frozenset(F)
        self.i = int(i)
        self.mid = int(mid)
        self.lo = None
        self.hi = None


def collect_leaves(node, out):
    if isinstance(node, Leaf):
        out.append(node)
    else:
        collect_leaves(node.lo, out)
        collect_leaves(node.hi, out)


def tree_depth(node):
    if isinstance(node, Leaf):
        return 1
    return 1 + max(tree_depth(node.lo), tree_depth(node.hi))


def node_forbid(node):
    return node[1] if node[0] == 'leaf' else node[3]


def snapshot(node):
    if isinstance(node, Leaf):
        h = node.h if node.closed else node.L - 1
        return ('leaf', frozenset(node.F), bool(node.closed),
                int(node.L), int(h), node.proof)
    return ('split', node.i, node.mid, frozenset(node.F),
            snapshot(node.lo), snapshot(node.hi))


def close_empty(inst, leaf, H):
    """Close a leaf because some job has no allowed start at H."""
    i = empty_job(inst, H, leaf.F)
    if i is None:
        return False
    leaf.closed = True
    leaf.h = int(H)
    leaf.proof = CertLeafProof(inst, H, leaf.F, {'kind': 'empty', 'job': i})
    return True


def split_leaf(inst, leaf, i, mid, H, H0):
    """Replace leaf by the two boxes {s_i <= mid} and {s_i > mid}.

    The split is performed on the *current target* H, so both children
    partition the parent's start domain at H.  The parent proof is
    inherited: both children are more restricted than the parent.
    Returns the new split node, or None if a side would be empty.
    """
    times = allowed_times(inst, H, i, leaf.F)
    le = [t for t in times if t <= mid]
    gt = [t for t in times if t > mid]
    if not le or not gt:
        return None
    F_le = leaf.F | frozenset((i, t) for t in gt)
    F_gt = leaf.F | frozenset((i, t) for t in le)
    sp = Split(leaf.F, i, mid)
    sp.lo = Leaf(F_le, leaf.L, leaf.proof,
                 box_measure(inst, H0, F_le), sp, 'lo')
    sp.hi = Leaf(F_gt, leaf.L, leaf.proof,
                 box_measure(inst, H0, F_gt), sp, 'hi')
    if leaf.parent is None:
        pass
    elif leaf.side == 'lo':
        leaf.parent.lo = sp
    else:
        leaf.parent.hi = sp
    return sp


# ------------------------------------------------------------------ certificates
class TamoFrontier:
    """Partial or closed frontier certificate.

    Node forms (tuples):
      ('leaf', F, closed, L, h, proof)
      ('split', i, mid, F, lo, hi)

    For an open leaf, h = L-1 and the proof is NO(h).  For a closed leaf,
    h >= target and the proof is NO(h).  A split is checked on the
    projection of F onto the start domains at ``target``; times outside
    that horizon are irrelevant and may have been forbidden when the
    split was made at a larger horizon.
    """

    kind = 'tamo-frontier'

    def __init__(self, inst, target, tree):
        self.inst = inst
        self.target = int(target)
        self.tree = tree
        self.L = None
        self.n_open = None

    def _leaf_ok(self, F, closed, L, h, proof):
        if proof is None or proof.h != h:
            return False
        if not proof.audit_rdf():
            return False
        relF = project_forbid(self.inst, self.target, F)
        relP = project_forbid(self.inst, self.target,
                              _proof_forbid(proof))
        if not relP <= relF:
            return False
        if closed:
            return h >= self.target
        return h == L - 1

    def _check(self, node, F):
        tag = node[0]
        if tag == 'leaf':
            _, leaf_F, closed, L, h, proof = node
            if set(leaf_F) != set(F):
                return None
            if not self._leaf_ok(leaf_F, closed, L, h, proof):
                return None
            return (int(L) if not closed else int(h) + 1,
                    not closed)
        if tag == 'split':
            _, i, mid, parent_F, lo, hi = node
            if set(parent_F) != set(F):
                return None
            times = allowed_times(self.inst, self.target, i, F)
            relF = project_forbid(self.inst, self.target, F)
            exp_lo = relF | frozenset((i, t) for t in times if t > mid)
            exp_hi = relF | frozenset((i, t) for t in times if t <= mid)
            if project_forbid(self.inst, self.target,
                               node_forbid(lo)) != exp_lo:
                return None
            if project_forbid(self.inst, self.target,
                               node_forbid(hi)) != exp_hi:
                return None
            a = self._check(lo, node_forbid(lo))
            b = self._check(hi, node_forbid(hi))
            if a is None or b is None:
                return None
            return (min(a[0], b[0]), a[1] or b[1])
        return None

    def audit_rdf(self):
        try:
            r = self._check(self.tree, frozenset())
            if r is None:
                return False
            self.L = r[0]
            out = [0]
            self._count_open(self.tree, out)
            self.n_open = out[0]
            return True
        except Exception:
            return False

    def _count_open(self, node, out):
        if node[0] == 'leaf':
            if not node[2]:
                out[0] += 1
            return
        self._count_open(node[4], out)
        self._count_open(node[5], out)

    def proof_complete(self):
        return self.audit_rdf()


class TamoPartialCertificate:
    """A certified bracket at any intermediate state."""

    kind = 'tamo-partial'

    def __init__(self, inst, target, frontier, schedule, machine,
                 probe=0):
        self.inst = inst
        self.target = int(target)
        self.frontier = frontier
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.probe = int(probe)

    def audit_rdf(self):
        try:
            if not self.frontier.audit_rdf():
                return False
            L = self.frontier.L
            U = self.target + 1
            if L is None or L > U:
                return False
            if self.schedule is None or self.machine is None:
                return False
            if cmax(self.inst, self.schedule) != U:
                return False
            return bool(check_schedule(self.inst, U, self.schedule,
                                       self.machine))
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class TamoCertificate:
    """Final certificate: an all-closed frontier at U-1 plus a schedule."""

    kind = 'tamo-opt'

    def __init__(self, inst, target, frontier, schedule, machine):
        self.inst = inst
        self.target = int(target)
        self.frontier = frontier
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None

    def audit_rdf(self):
        try:
            if not self.frontier.audit_rdf():
                return False
            if self.frontier.n_open != 0:
                return False
            U = self.target + 1
            if self.frontier.L != U:
                return False
            if self.schedule is None or self.machine is None:
                return False
            if cmax(self.inst, self.schedule) != U:
                return False
            return bool(check_schedule(self.inst, U, self.schedule,
                                       self.machine))
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


# ------------------------------------------------------------------ rank
def rank_of(inst, H0, U, root, Mmax, recompute=False):
    """Count-vector encoding of the multiset of box measures.

    The second component is (c_Mmax, c_{Mmax-1}, ..., c_0), where c_v is
    the number of leaves with mu(F)=v.  Replacing one mu=x by two values
    < x strictly decreases this vector in lexicographic order; this is
    the standard multiset (Dershowitz-Manna) order over a finite ground
    set, so it is well-founded.
    """
    leaves = []
    collect_leaves(root, leaves)
    counts = [0] * (Mmax + 1)
    for l in leaves:
        m = box_measure(inst, H0, l.F) if recompute else l.mu
        if m < 0 or m > Mmax:
            raise ValueError('box measure out of range')
        counts[m] += 1
    kappa = tuple(counts[v] for v in range(Mmax, -1, -1))
    sum_open = sum(U - l.L for l in leaves if not l.closed)
    return (int(U), kappa, int(sum_open))


def rank_lt(a, b):
    return a < b


# ------------------------------------------------------------------ initial states
def weak_initial(inst):
    """Critical-path lower bound, serial schedule on machine 0, NO(L-1)."""
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    L = max(1, max(est[i] + inst['p'][i] + q[i] for i in range(n)))
    indeg = [len(inst['pred'][i]) for i in range(n)]
    dq = [i for i in range(n) if indeg[i] == 0]
    order = []
    while dq:
        i = dq.pop(0)
        order.append(i)
        for j in inst['succ'][i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                dq.append(j)
    t = 0
    sched = [0] * n
    for i in order:
        sched[i] = t
        t += inst['p'][i]
    mach = [0] * n
    r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
    if r['verdict'] is not False:
        raise RuntimeError('weak lower bound is not NO: %r' % (r['verdict'],))
    return int(L), int(t), sched, mach, r['proof']


def pact_initial(inst):
    co = PACT(inst, pact_mode='complete', use_ga=False)
    lb, ub, sched, mach = co.initial_bounds()
    if ub is None:
        raise RuntimeError('no initial upper bound')
    L, U = int(lb), int(ub)
    proof = co._ensure_lb_proof(L)
    if proof is None:
        r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            proof = r['proof']
    if proof is None:
        raise RuntimeError('no lower-bound proof')
    return L, U, list(sched), list(mach), proof


# ------------------------------------------------------------------ main loop
def _choose_split(inst, leaf, H, r, split_mode):
    """Pick (i, mid) for REFINE; the oracle's root branch is the default."""
    bj = r.get('branch_jobs') or []
    cand = None
    if split_mode == 'oracle' and bj:
        cand = bj[0]
    if cand is not None:
        i, mid = int(cand[0]), int(cand[1])
        times = allowed_times(inst, H, i, leaf.F)
        if times and any(t > mid for t in times) and any(t <= mid for t in times):
            return i, mid
    best = None
    for i in range(inst['n']):
        times = allowed_times(inst, H, i, leaf.F)
        if len(times) >= 2 and (best is None or len(times) > best[0]):
            best = (len(times), i, times[len(times) // 2 - 1])
    if best is None:
        return None
    return best[1], best[2]


def run_tamo(inst, known, name, idx, B=1, policy='lower',
             split_mode='oracle', max_probes=200000,
             initial=None, audit_every=True, include_tree=False,
             debug=False):
    """Run TAMO.  ``initial`` is None for PACT bounds, or a tuple
    (L, U, s, m, proof)."""
    t0 = time.time()
    if initial is None:
        L0, U0, s, m, proof0 = pact_initial(inst)
    else:
        L0, U0, s, m, proof0 = initial
    L0, U0 = int(L0), int(U0)
    s, m = list(s), list(m)
    if not check_schedule(inst, cmax(inst, s), s, m):
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='bad-initial-schedule', t=0.0)

    H0 = U0 - 1
    Mmax = box_measure(inst, H0, frozenset())
    root = Leaf(frozenset(), L0, proof0, Mmax)
    holder = [root]
    U = U0
    H = U - 1
    leaves = []
    collect_leaves(root, leaves)
    heap = [(l.L, -l.mu, id(l)) for l in leaves]
    heapq.heapify(heap)
    live = set(id(l) for l in leaves)
    byid = {id(l): l for l in leaves}

    probes = splits = closes_lift = closes_empty = 0
    yes = no = unknown = 0
    lp = nodes = cert_lp = 0
    max_leaves = len(leaves)
    rank_checks = rank_fail = 0
    partial_checks = partial_fail = 0
    final_ok = False
    rho = rank_of(inst, H0, U, holder[0], Mmax, recompute=True)

    def state_audit():
        nonlocal partial_checks, partial_fail
        if not audit_every:
            return
        fp = TamoFrontier(inst, U - 1, snapshot(holder[0]))
        pc = TamoPartialCertificate(inst, U - 1, fp, s, m, probe=probes)
        partial_checks += 1
        if not pc.audit_rdf():
            partial_fail += 1
            if debug:
                print('AUDIT FAIL probes', probes, 'U', U,
                      'tree', snapshot(holder[0]))

    state_audit()

    while True:
        while heap and (heap[0][2] not in live or
                        byid.get(heap[0][2]) is None):
            heapq.heappop(heap)
        if not heap:
            break
        Lmin, _, lid = heap[0]
        leaf = byid.get(lid)
        if leaf is None:
            heapq.heappop(heap)
            continue
        if leaf.L != Lmin:
            heapq.heappop(heap)
            continue
        if leaf.L >= U:
            break
        if probes >= max_probes:
            break
        h = leaf.L if policy == 'lower' else (leaf.L + U) // 2
        if h >= U:
            h = U - 1
        r = pact_decide(inst, h, depthcap=None, nodecap=B,
                        forbid0=frozenset(leaf.F))
        probes += 1
        lp += r.get('lp_solves', 0)
        nodes += r.get('nodes', 0)
        cert_lp += r.get('cert_lp', 0)
        before = rho
        kind = None

        if r['verdict'] is False:
            no += 1
            leaf.proof = r['proof']
            leaf.L = h + 1
            kind = 'probe-no'
            if leaf.L >= U:
                leaf.closed = True
                leaf.h = leaf.L - 1
                live.discard(id(leaf))
                byid.pop(id(leaf), None)
                closes_lift += 1
            else:
                heapq.heappush(heap, (leaf.L, -leaf.mu, id(leaf)))
        elif r['verdict'] is True:
            yes += 1
            c = cmax(inst, r['schedule'])
            if c < U and check_schedule(inst, c, r['schedule'],
                                        r['machine']):
                U = c
                H = U - 1
                s = list(r['schedule'])
                m = list(r['machine'])
                kind = 'probe-yes'
                leaves_now = []
                collect_leaves(holder[0], leaves_now)
                for x in leaves_now:
                    if x.closed:
                        continue
                    if close_empty(inst, x, H):
                        live.discard(id(x))
                        byid.pop(id(x), None)
                        closes_empty += 1
                    elif x.L >= U:
                        x.closed = True
                        x.h = x.L - 1
                        live.discard(id(x))
                        byid.pop(id(x), None)
                        closes_lift += 1
                if not live:
                    break
            else:
                kind = 'probe-yes-stale'
        else:
            unknown += 1
            pair = _choose_split(inst, leaf, H, r, split_mode)
            if pair is None:
                break
            i, mid = pair
            if debug:
                ts = allowed_times(inst, H, i, leaf.F)
                print('SPLIT probe-h', h, 'H', H, 'i', i, 'mid', mid,
                      'F', sorted(leaf.F), 'times', ts,
                      'branch_jobs', r.get('branch_jobs'))
            sp = split_leaf(inst, leaf, i, mid, H, H0)
            if sp is None:
                if debug:
                    print('SPLIT FAILED')
                break
            splits += 1
            if leaf.parent is None:
                holder[0] = sp
            live.discard(id(leaf))
            byid.pop(id(leaf), None)
            for c in (sp.lo, sp.hi):
                if close_empty(inst, c, H):
                    closes_empty += 1
                else:
                    live.add(id(c))
                    byid[id(c)] = c
                    heapq.heappush(heap, (c.L, -c.mu, id(c)))
            kind = 'refine'
            leaves = []
            collect_leaves(holder[0], leaves)
            max_leaves = max(max_leaves, len(leaves))

        if kind in ('probe-no', 'probe-yes', 'refine'):
            rho2 = rank_of(inst, H0, U, holder[0], Mmax,
                           recompute=True)
            rank_checks += 1
            if not rank_lt(rho2, before):
                rank_fail += 1
            rho = rho2
        state_audit()

    # close any remaining open leaves for the final certificate
    leaves = []
    collect_leaves(holder[0], leaves)
    for x in leaves:
        if not x.closed:
            x.closed = True
            x.h = x.L - 1
    fp = TamoFrontier(inst, U - 1, snapshot(holder[0]))
    cert = TamoCertificate(inst, U - 1, fp, s, m)
    final_ok = bool(cert.audit_rdf())
    L = fp.L
    partial = TamoPartialCertificate(inst, U - 1,
                                     TamoFrontier(inst, U - 1,
                                                  snapshot(holder[0])),
                                     s, m, probe=probes)
    partial_final = bool(partial.audit_rdf())
    dt = time.time() - t0
    out = dict(
        name=name, idx=idx, known=known, B=B, policy=policy,
        split_mode=split_mode, L0=L0, U0=U0, L=L, U=U,
        opt=U, probes=probes, splits=splits,
        yes=yes, no=no, unknown=unknown,
        closes_lift=closes_lift, closes_empty=closes_empty,
        lp=lp, nodes=nodes, cert_lp=cert_lp,
        leaves=len(leaves), open=sum(1 for x in leaves if not x.closed),
        max_leaves=max_leaves, depth=tree_depth(holder[0]),
        rank_checks=rank_checks, rank_fail=rank_fail,
        partial_checks=partial_checks, partial_fail=partial_fail,
        certified=bool(L == U and final_ok),
        audit=final_ok, proof=final_ok,
        partial_final=partial_final,
        cert_h=(U - 1 if L == U else None),
        t=round(dt, 4),
        ok=bool(L == U == known and final_ok and partial_fail == 0
                and rank_fail == 0),
    )
    if include_tree:
        out['tree'] = snapshot(holder[0])
        out['schedule'] = s
        out['machine'] = m
    return out
