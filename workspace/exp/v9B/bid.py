"""v9.1 BID-ICF: bidirectional, invariant-carrying frontier for scheduling.

The v9.0 ICF-PACT loop keeps a certified bracket

    (L, U, s, m, pi),  pi proves NO(L-1),  Cmax(s)=U,

and calls a complete fixed-h decision procedure at every probe.  This
round changes the *probe itself* and keeps the same certificate algebra:

  1. BIDIRECTIONAL PROBE.  A probe at horizon h first solves the root LP
     once.  If it is infeasible we have a Farkas NO at the root.  If it
     is feasible we run a bounded *forward* serial-SGS search whose
     priority ranks are sampled from the LP start-time marginals.  A
     forward success is a YES with a replayed schedule and needs no
     further LP.  Only if the forward search misses do we run the
     *backward* LP/Farkas branch search, reusing the root LP solve.

  2. RESUMABLE FRONTIER.  The backward search takes an LP node budget
     and returns either NO, YES, or a partial partition tree whose
     leaves are closed NO boxes and open sub-boxes.  The outer state
     replaces the probed leaf by this tree.  A budget cut therefore
     loses no completed work: the next round resumes on the open leaves
     instead of restarting the whole probe.

  3. SMT-STYLE LEMMAS.  Every closed box is stored as a horizon-tagged
     certificate lemma (C, h, pi).  A node whose box contains C and whose
     target is <= h is closed by a BoxSubsumption proof without an LP.
     Certificate lifting attempts to rebase a child NO proof onto the
     parent box (conflict-driven backjumping); this is sound and audited,
     but on the 252 corpus it almost never fires.  We keep it and report
     the negative ablation honestly.

  4. MDP PROBE SCHEDULER.  The outer loop is a finite-horizon MDP over
     the bracket [L,U].  A probe at h either proves NO (raise L) or
     returns YES (lower U); the two sides have different costs.  The
     exact DP is in mdp.py; the policy adapts to the prior induced by the
     LP relaxation (tight prior -> lower-first; diffuse prior -> binary).

The frontier invariant is the v9.0 multi-leaf invariant restricted to
the boxes actually visited.  The final certificate is a FrontierProof at
U-1; leaves proven at a larger horizon are wrapped in HorizonBoxProof,
which is the missing mixed-horizon rule flagged as risk #6 in v9.0.
"""
import sys
import time
import math
import random

sys.path[:0] = ['exp/v9B', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from sage import BranchProof, _domain, _elig_aware
from cert import verify, integer_certificate
from rdf import check_schedule, _insert, _earliest
from pact import PACT, pact_decide, _integral_schedule, _singleton_leaf
from sdecc import SDLP
from po import heads_tails
from icf import FrontierProof

INF = 10 ** 12


def cmax(inst, starts):
    return max(starts[i] + inst['p'][i] for i in range(inst['n']))


def proof_box(p):
    """Root forbidden box exposed by a proof (empty for global proofs)."""
    seen = set()
    while p is not None and id(p) not in seen:
        seen.add(id(p))
        f = getattr(p, 'forbid0', None)
        if f is not None:
            return frozenset(f)
        p = getattr(p, 'source', None)
    return frozenset()


def _times(inst, h, i, F):
    lo, hi = _domain(inst, h, i)
    return [t for t in range(lo, hi + 1) if (i, t) not in F]


def _cut_box(inst, h, F):
    """Drop forbidden literals that are outside the horizon domain."""
    out = set()
    for (i, t) in F:
        lo, hi = _domain(inst, h, i)
        if lo <= t <= hi:
            out.add((i, t))
    return frozenset(out)


# --------------------------------------------------------------- proofs
class HorizonBoxProof(Proof):
    """NO(h_source | src_box) used as NO(target | target_box).

    target <= h_source, and target_box is exactly src_box restricted to
    the target domain.  Any target schedule avoiding target_box also
    avoids src_box, so the source refutation applies.
    """

    kind = 'horizon-box'

    def __init__(self, inst, target, source, src_box, target_box):
        super().__init__(inst, target)
        self.source = source
        self.src_box = frozenset(src_box)
        self.forbid0 = frozenset(target_box)

    def audit_rdf(self):
        try:
            if self.source is None or self.source.h < self.h:
                return False
            if self.src_box != proof_box(self.source):
                return False
            if self.forbid0 != _cut_box(self.inst, self.h, self.src_box):
                return False
            return bool(self.source.audit_rdf())
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def _audit_bid_tree(inst, h, node, F):
    tag = node[0]
    if tag == 'leaf':
        if frozenset(node[1]) != F:
            return False
        cert = node[2]
        if cert.get('kind') == 'empty':
            i = cert['job']
            return not _times(inst, h, i, F)
        return bool(verify(inst, h, cert, forbid=F))
    if tag == 'sub':
        if frozenset(node[1]) != F:
            return False
        src = node[2]
        src_box = node[3]
        if src is None or src.h < h:
            return False
        if src_box != proof_box(src) or not (src_box <= F):
            return False
        return bool(src.audit_rdf())
    if tag == 'split':
        _, i, mid, nF, lo, hi = node
        if frozenset(nF) != F:
            return False
        ts = _times(inst, h, i, F)
        lo_t = [t for t in ts if t > mid]
        hi_t = [t for t in ts if t <= mid]
        if not lo_t or not hi_t:
            return False
        loF = F | {(i, t) for t in lo_t}
        hiF = F | {(i, t) for t in hi_t}
        return (_audit_bid_tree(inst, h, lo, loF)
                and _audit_bid_tree(inst, h, hi, hiF))
    return False


class BIDProof(Proof):
    """A replayable NO(h | box) proof with box-subsumption nodes."""

    kind = 'bid'

    def __init__(self, inst, h, tree, box):
        super().__init__(inst, h)
        self.tree = tree
        self.forbid0 = frozenset(box)

    def audit_rdf(self):
        try:
            return _audit_bid_tree(self.inst, self.h, self.tree,
                                   self.forbid0)
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class BIDCertificate:
    """Final multi-leaf frontier + schedule at U."""

    kind = 'bid-opt'

    def __init__(self, inst, opt, schedule, machine, frontier):
        self.inst = inst
        self.opt = int(opt)
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.frontier = frontier

    def audit_rdf(self):
        try:
            if self.frontier is None or not self.frontier.audit_rdf():
                return False
            if self.schedule is None or self.machine is None:
                return False
            if cmax(self.inst, self.schedule) != self.opt:
                return False
            return bool(check_schedule(self.inst, self.opt,
                                       self.schedule, self.machine))
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


# --------------------------------------------------------------- lemmas
class Lemma:
    __slots__ = ('box', 'h', 'proof')

    def __init__(self, box, h, proof):
        self.box = frozenset(box)
        self.h = int(h)
        self.proof = proof


class LemmaStore:
    """Certificate-carrying nogoods, newest/highest horizon first."""

    def __init__(self, cap=4000, max_lits=64):
        self.items = []
        self.cap = cap
        self.max_lits = max_lits
        self.used = 0
        self.added = 0

    def add(self, box, h, proof):
        box = frozenset(box)
        if not box or len(box) > self.max_lits:
            return
        if len(self.items) >= self.cap:
            return
        self.items.append(Lemma(box, h, proof))
        self.items.sort(key=lambda z: (-z.h, len(z.box)))
        self.added += 1

    def find(self, F, h):
        for lem in self.items:
            if lem.h >= h and lem.box <= F:
                self.used += 1
                return lem
        return None


# --------------------------------------------------------- forward search
def _sgs_dfs(inst, h, rank, nodecap, F0, latest):
    n, m, p = inst['n'], inst['m'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    starts = [None] * n
    machs = [None] * n
    busy = [[] for _ in range(m)]
    rem = [len(inst['pred'][i]) for i in range(n)]
    predfin = [0] * n
    done = [False] * n
    nodes = [0]

    def rec():
        nodes[0] += 1
        if nodes[0] > nodecap:
            return False
        if all(done):
            return True
        av = [i for i in range(n) if not done[i] and rem[i] == 0]
        if not av:
            return False
        av.sort(key=lambda i: (rank.get(i, est[i]), i))
        for i in av:
            base = max(est[i], predfin[i])
            opts = []
            for k in inst['elig'][i]:
                tt = _earliest(busy[k], base, p[i])
                if tt <= latest[i] and (i, tt) not in F0:
                    opts.append((tt, k))
            opts.sort()
            for tt, k in opts:
                starts[i] = tt
                machs[i] = k
                done[i] = True
                _insert(busy, k, tt, tt + p[i])
                old = [(j, predfin[j]) for j in inst['succ'][i]]
                for j in inst['succ'][i]:
                    predfin[j] = max(predfin[j], tt + p[i])
                    rem[j] -= 1
                if rec():
                    return True
                for j, v in old:
                    predfin[j] = v
                    rem[j] += 1
                busy[k].remove((tt, tt + p[i]))
                done[i] = False
                starts[i] = None
                machs[i] = None
                if nodes[0] > nodecap:
                    return False
        return False

    ok = rec()
    if ok and check_schedule(inst, h, starts, machs):
        return starts, machs, nodes[0]
    return None, None, nodes[0]


def _marginals(inst, lp, z):
    n = inst['n']
    dist = {}
    for i in range(n):
        d = {}
        mass = 0.0
        for c, key in enumerate(lp.cols):
            if key[0] == i:
                v = float(z[c])
                if v > 1e-9:
                    t = key[-1]
                    d[t] = d.get(t, 0.0) + v
                    mass += v
        if mass <= 1e-12:
            d = {lp.est[i]: 1.0}
            mass = 1.0
        dist[i] = [(t, v / mass) for t, v in sorted(d.items())]
    return dist


def _sample_rank(dist, rng):
    rank = {}
    for i, d in dist.items():
        u = rng.random()
        acc = 0.0
        t = d[-1][0]
        for tt, v in d:
            acc += v
            if u <= acc:
                t = tt
                break
        rank[i] = t + rng.random() * 1e-6
    return rank


def forward_search(inst, h, lp, z, F0, stats, cap=100, trials=11,
                   seed=20261026):
    """Bounded primal SGS search with LP-marginal ranks.

    Returns (starts, machine) or None.  A failure is not a NO proof.
    """
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    latest = [h - q[i] - inst['p'][i] for i in range(n)]
    if any(est[i] > latest[i] for i in range(n)):
        return None
    dist = _marginals(inst, lp, z)
    fixed = [
        {i: est[i] + 1e-6 * i for i in range(n)},
        {i: -q[i] + 1e-6 * i for i in range(n)},
        {i: est[i] - 0.5 * q[i] + 1e-6 * i for i in range(n)},
        {i: latest[i] + 1e-6 * i for i in range(n)},
    ]
    rng = random.Random(seed)
    ranks = list(fixed)
    for _ in range(max(0, trials - len(fixed))):
        ranks.append(_sample_rank(dist, rng))
    for r in ranks:
        got, mach, nodes = _sgs_dfs(inst, h, r, cap, F0, latest)
        stats['fwd_nodes'] = stats.get('fwd_nodes', 0) + nodes
        stats['fwd_trials'] = stats.get('fwd_trials', 0) + 1
        if got is not None:
            return got, mach
    return None


# --------------------------------------------------------- backward search
def _choose_split(inst, lp, z, bounds, F):
    n = inst['n']
    cand = []
    for i in range(n):
        times = sorted({key[-1] for c, key in enumerate(lp.cols)
                        if key[0] == i and bounds[c] != (0, 0)})
        if len(times) <= 1:
            continue
        dist = []
        for tt in times:
            v = sum(z[c] for c, key in enumerate(lp.cols)
                    if key[0] == i and key[-1] == tt
                    and bounds[c] != (0, 0))
            dist.append((tt, v))
        frac = sum(v for _, v in dist if 1e-7 < v < 1 - 1e-7)
        if frac <= 1e-7:
            continue
        mass = sum(v for _, v in dist)
        cand.append(((mass, len(inst['succ'][i]), -i), i, dist))
    if not cand:
        return None, None
    cand.sort(reverse=True)
    _, i, dist = cand[0]
    total = sum(v for _, v in dist)
    acc = 0.0
    mid = dist[0][0]
    for tt, v in dist:
        acc += v
        if acc >= 0.5 * total:
            mid = tt
            break
    times = [tt for tt, _ in dist]
    lo_t = [tt for tt in times if tt > mid]
    hi_t = [tt for tt in times if tt <= mid]
    if not lo_t or not hi_t:
        return None, None
    return i, mid


def _bound_side(lp, bounds, i, mid, side):
    b = list(bounds)
    for c, key in enumerate(lp.cols):
        if key[0] != i:
            continue
        tt = key[-1]
        if (side == 'lo' and tt > mid) or (side == 'hi' and tt <= mid):
            b[c] = (0, 0)
    return b


def _leaf_cert(inst, h, F, stats, elig):
    stats['cert_lp'] = stats.get('cert_lp', 0) + 1
    cert = integer_certificate(inst, h, use_dom=True,
                               elig_aware=elig, forbid=F)
    if cert is not None and verify(inst, h, cert, forbid=F):
        return ('leaf', frozenset(F), cert)
    for i in range(inst['n']):
        if not _times(inst, h, i, F):
            return ('empty', frozenset(F), i)
    return None


def _as_sub(node, F, h):
    """Use a tree/proof at core node[3] as a NO proof at box F."""
    core = node[3]
    if core == F:
        return node[2]
    return ('sub', frozenset(F), node[2], frozenset(core))


def _rebase_tree(inst, h, node, F):
    tag = node[0]
    if tag == 'leaf':
        return ('leaf', frozenset(F), node[2])
    if tag == 'sub':
        src = node[2]
        if not (proof_box(src) <= F):
            return None
        return ('sub', frozenset(F), src, frozenset(proof_box(src)))
    if tag == 'split':
        _, i, mid, _, lo, hi = node
        ts = _times(inst, h, i, F)
        lo_t = [t for t in ts if t > mid]
        hi_t = [t for t in ts if t <= mid]
        if not lo_t or not hi_t:
            return None
        loF = F | {(i, t) for t in lo_t}
        hiF = F | {(i, t) for t in hi_t}
        a = _rebase_tree(inst, h, lo, loF)
        b = _rebase_tree(inst, h, hi, hiF)
        if a is None or b is None:
            return None
        return ('split', i, mid, frozenset(F), a, b)
    return None


def try_lift(inst, h, node, target_F):
    """Try to turn a NO proof at node[3] into a NO proof at target_F.

    If the proof's box is already contained in target_F the lift is free
    (subsumption).  Otherwise we rebase the whole proof tree to the
    smaller box and audit it; the audit is the only source of truth.
    """
    core = node[3]
    if core <= target_F:
        return ('sub', frozenset(target_F), node[2], frozenset(core))
    if not (target_F <= core):
        return None
    tree = _rebase_tree(inst, h, node[2], target_F)
    if tree is None:
        return None
    proof = BIDProof(inst, h, tree, target_F)
    if not proof.audit_rdf():
        return None
    return ('no', frozenset(target_F), tree, frozenset(target_F))


def bid_decide(inst, h, F0=frozenset(), nodecap=64, lemmas=None,
               backjump=True, forward=True, fwd_cap=100, fwd_trials=11,
               seed=20261026):
    """One bidirectional probe.

    Returns dict(verdict in {False,True,None}, proof, box, schedule,
    machine, tree, stats).  verdict None means a budgeted partial
    frontier; tree is a mixed ('open'|'no'|'node'|'yes') tree.
    """
    t0 = time.time()
    n, m, p = inst['n'], inst['m'], inst['p']
    elig = _elig_aware(inst)
    est, q = heads_tails(inst, 0, [0] * n)
    F0 = frozenset(F0)
    stats = dict(lp_solves=0, cert_lp=0, nodes=0, lemmas_used=0,
                 lifts=0, backjumps=0, fwd_nodes=0, fwd_trials=0,
                 forward_yes=0, root_lemmas=0)

    if lemmas is not None:
        lem = lemmas.find(F0, h)
        if lem is not None and lem.h >= h:
            src_box = proof_box(lem.proof)
            sub = ('sub', F0, lem.proof, src_box)
            proof = BIDProof(inst, h, sub, F0)
            stats['root_lemmas'] += 1
            stats['t'] = round(time.time() - t0, 5)
            return dict(verdict=False, proof=proof, box=F0,
                        schedule=None, machine=None, tree=None,
                        stats=stats)

    lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig,
              forbid=F0)
    base = [(0, 1)] * lp.N

    def solve(bounds):
        stats['lp_solves'] += 1
        return lp.solve(bounds)

    stats['lp_solves'] += 1
    root_res = lp.solve(base)
    if root_res.status == 2:
        node = _leaf_cert(inst, h, F0, stats, elig)
        if node is None:
            stats['t'] = round(time.time() - t0, 5)
            return dict(verdict=None, proof=None, box=F0, schedule=None,
                        machine=None, tree=('open', F0), stats=stats)
        proof = BIDProof(inst, h, node, F0)
        if not proof.audit_rdf():
            stats['t'] = round(time.time() - t0, 5)
            return dict(verdict=None, proof=None, box=F0, schedule=None,
                        machine=None, tree=('open', F0), stats=stats)
        stats['t'] = round(time.time() - t0, 5)
        return dict(verdict=False, proof=proof, box=F0, schedule=None,
                    machine=None, tree=None, stats=stats)
    if root_res.status != 0:
        stats['t'] = round(time.time() - t0, 5)
        return dict(verdict=None, proof=None, box=F0, schedule=None,
                    machine=None, tree=('open', F0), stats=stats)

    if forward:
        got = forward_search(inst, h, lp, root_res.x, F0, stats,
                             cap=fwd_cap, trials=fwd_trials, seed=seed)
        if got is not None:
            starts, machs = got
            stats['forward_yes'] = 1
            stats['t'] = round(time.time() - t0, 5)
            return dict(verdict=True, proof=None, box=F0,
                        schedule=starts, machine=machs,
                        tree=('yes', starts, machs), stats=stats)

    def dfs(bounds, F, depth):
        if lemmas is not None:
            lem = lemmas.find(F, h)
            if lem is not None and lem.h >= h:
                src_box = proof_box(lem.proof)
                tree = ('sub', frozenset(F), lem.proof, src_box)
                stats['lemmas_used'] += 1
                return ('no', frozenset(F), tree, src_box)
        if depth > 0 and stats['lp_solves'] >= nodecap:
            return ('open', frozenset(F))
        if depth == 0:
            res = root_res
        else:
            res = solve(bounds)
        if res is None:
            return ('open', frozenset(F))
        if res.status == 2:
            node = _leaf_cert(inst, h, F, stats, elig)
            if node is None:
                return ('open', frozenset(F))
            return ('no', frozenset(F), node, frozenset(F))
        if res.status != 0:
            return ('open', frozenset(F))
        z = res.x
        frac = False
        for c, key in enumerate(lp.cols):
            if 1e-7 < z[c] < 1 - 1e-7 and bounds[c] != (0, 0):
                frac = True
                break
        if not frac:
            got = _integral_schedule(inst, lp, z, elig)
            if got is None:
                got = _singleton_leaf(inst, h, F, lp, bounds)
            if got is not None:
                return ('yes', got[0], got[1])
            i = None
            mid = None
            for j in range(n):
                ts = sorted({key[-1] for c, key in enumerate(lp.cols)
                             if key[0] == j and bounds[c] != (0, 0)})
                if len(ts) > 1:
                    i = j
                    mid = ts[len(ts) // 2 - 1]
                    break
            if i is None:
                return ('open', frozenset(F))
        else:
            i, mid = _choose_split(inst, lp, z, bounds, F)
            if i is None:
                return ('open', frozenset(F))
        ts = sorted({key[-1] for c, key in enumerate(lp.cols)
                     if key[0] == i and bounds[c] != (0, 0)})
        lo_t = [t for t in ts if t > mid]
        hi_t = [t for t in ts if t <= mid]
        if not lo_t or not hi_t:
            return ('open', frozenset(F))
        loF = F | {(i, t) for t in lo_t}
        hiF = F | {(i, t) for t in hi_t}
        stats['nodes'] += 1
        lo = dfs(_bound_side(lp, bounds, i, mid, 'lo'), loF, depth + 1)
        if lo[0] == 'yes':
            return lo
        if lo[0] == 'no' and backjump:
            lifted = try_lift(inst, h, lo, F)
            if lifted is not None:
                stats['backjumps'] += 1
                return lifted
        hi = dfs(_bound_side(lp, bounds, i, mid, 'hi'), hiF, depth + 1)
        if hi[0] == 'yes':
            return hi
        if hi[0] == 'no' and backjump:
            lifted = try_lift(inst, h, hi, F)
            if lifted is not None:
                stats['backjumps'] += 1
                return lifted
        if lo[0] == 'no' and hi[0] == 'no':
            lo_node = _as_sub(lo, loF, h)
            hi_node = _as_sub(hi, hiF, h)
            tree = ('split', i, mid, frozenset(F), lo_node, hi_node)
            proof = BIDProof(inst, h, tree, F)
            if not proof.audit_rdf():
                return ('open', frozenset(F))
            if backjump:
                # certificate core minimisation: try to drop root literals
                core = F
                for lit in list(F):
                    cand = core - {lit}
                    t2 = _rebase_tree(inst, h, tree, cand)
                    if t2 is not None:
                        p2 = BIDProof(inst, h, t2, cand)
                        if p2.audit_rdf():
                            tree, core = t2, cand
                if core != F:
                    stats['lifts'] += 1
                    return ('no', frozenset(F), tree, frozenset(core))
            return ('no', frozenset(F), tree, frozenset(F))
        # at least one child is open: keep the closed child and the open box
        lo_part = (_as_sub(lo, loF, h) if lo[0] == 'no'
                   else ('open', frozenset(loF)))
        hi_part = (_as_sub(hi, hiF, h) if hi[0] == 'no'
                   else ('open', frozenset(hiF)))
        return ('node', i, mid, frozenset(F), lo_part, hi_part)

    tree = dfs(base, F0, 0)
    stats['t'] = round(time.time() - t0, 5)
    if tree[0] == 'yes':
        return dict(verdict=True, proof=None, box=F0, schedule=tree[1],
                    machine=tree[2], tree=tree, stats=stats)
    if tree[0] == 'no':
        proof = BIDProof(inst, h, tree[2], tree[3])
        if not proof.audit_rdf():
            return dict(verdict=None, proof=None, box=F0, schedule=None,
                        machine=None, tree=('open', F0), stats=stats)
        return dict(verdict=False, proof=proof, box=tree[3],
                    schedule=None, machine=None, tree=None, stats=stats)
    return dict(verdict=None, proof=None, box=F0, schedule=None,
                machine=None, tree=tree, stats=stats)


# --------------------------------------------------------------- frontier
class FNode:
    __slots__ = ('kind', 'F', 'Lf', 'proof', 'h', 'i', 'mid', 'lo', 'hi')

    def __init__(self, kind, F, Lf=None, proof=None, h=None,
                 i=None, mid=None, lo=None, hi=None):
        self.kind = kind
        self.F = frozenset(F)
        self.Lf = Lf
        self.proof = proof
        self.h = h
        self.i = i
        self.mid = mid
        self.lo = lo
        self.hi = hi


def fnode_open(F, Lf, proof):
    return FNode('open', F, Lf=Lf, proof=proof)


def fnode_sat(F, h, proof):
    return FNode('sat', F, h=h, proof=proof)


def part_to_fnode(inst, node, parent, U, h):
    tag = node[0]
    if tag == 'open':
        return fnode_open(node[1], parent.Lf, parent.proof)
    if tag == 'no':
        F, tree, core = node[1], node[2], node[3]
        proof = BIDProof(inst, h, tree, core)
        Lf = min(U, proof.h + 1)
        if Lf >= U:
            return fnode_sat(F, proof.h, proof)
        return fnode_open(F, Lf, proof)
    if tag == 'node':
        _, i, mid, F, lo, hi = node
        return FNode('split', F, i=i, mid=mid,
                     lo=part_to_fnode(inst, lo, parent, U, h),
                     hi=part_to_fnode(inst, hi, parent, U, h))
    raise ValueError('bad partial tree %r' % (tag,))


def leaves_of(node):
    if node.kind == 'split':
        for x in leaves_of(node.lo):
            yield x
        for x in leaves_of(node.hi):
            yield x
    else:
        yield node


def global_L(root, U):
    vals = []
    for leaf in leaves_of(root):
        if leaf.kind == 'open':
            vals.append(min(leaf.Lf, U))
        else:
            vals.append(U)
    return min(vals) if vals else U


def select_leaf(inst, root, L, U):
    """Most constrained open leaf: fewest allowed starts at the target."""
    best = None
    for leaf in leaves_of(root):
        if leaf.kind != 'open' or leaf.Lf > L:
            continue
        size = sum(len(_times(inst, U - 1, i, leaf.F))
                   for i in range(inst['n']))
        key = (size, len(leaf.F), -leaf.Lf)
        if best is None or key < best[0]:
            best = (key, leaf)
    return best[1] if best else None


def _norm_tree(inst, target, node, F, proofs):
    """Normalise a frontier tree to the target horizon."""
    if node.kind == 'split':
        ts = _times(inst, target, node.i, F)
        lo_t = [t for t in ts if t > node.mid]
        hi_t = [t for t in ts if t <= node.mid]
        if not lo_t:
            return _norm_tree(inst, target, node.hi, F, proofs)
        if not hi_t:
            return _norm_tree(inst, target, node.lo, F, proofs)
        loF = F | {(node.i, t) for t in lo_t}
        hiF = F | {(node.i, t) for t in hi_t}
        return ('split', node.i, node.mid, frozenset(F),
                _norm_tree(inst, target, node.lo, loF, proofs),
                _norm_tree(inst, target, node.hi, hiF, proofs))
    # leaf
    src_box = proof_box(node.proof)
    tbox = _cut_box(inst, target, src_box)
    proof = HorizonBoxProof(inst, target, node.proof, src_box, tbox)
    proofs.append(proof)
    return ('leaf', frozenset(F), target, proof)


def finalize(inst, root, U, schedule, machine):
    target = U - 1
    proofs = []
    tree = _norm_tree(inst, target, root, frozenset(), proofs)
    frontier = FrontierProof(inst, target, tree)
    return BIDCertificate(inst, U, schedule, machine, frontier)


def _probe_leaf(inst, leaf, h, nodecap, lemmas, cur_lp, cfg):
    r = bid_decide(inst, h, leaf.F, nodecap=nodecap, lemmas=lemmas,
                   backjump=cfg.get('backjump', True),
                   forward=cfg.get('forward', True),
                   fwd_cap=cfg.get('fwd_cap', 100),
                   fwd_trials=cfg.get('fwd_trials', 11),
                   seed=cfg.get('seed', 20261026))
    return r


def run_bid(inst, known, name, idx, policy='lower-first', max_probes=256,
            nodecap=64, total_lp=None, cfg=None):
    """Run the bidirectional invariant-carrying frontier."""
    cfg = dict(cfg or {})
    t0 = time.time()
    co = PACT(inst, pact_mode='complete', use_ga=False)
    lb, ub, sched, mach = co.initial_bounds()
    if policy in ('mdp', 'mdp-mm') and 'pin' not in cfg:
        pin = getattr(co, 'pin', None) or {}
        if pin.get('lb') is not None:
            cfg['pin'] = int(pin['lb'])
    if ub is None:
        return dict(name=name, idx=idx, known=known, policy=policy,
                    ok=False, error='no-initial-ub', t=0.0)
    L, U = int(lb), int(ub)
    sched = list(sched)
    mach = list(mach)
    lb_proof = co._ensure_lb_proof(L)
    if lb_proof is None:
        r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            lb_proof = r['proof']
    if lb_proof is None:
        return dict(name=name, idx=idx, known=known, policy=policy,
                    ok=False, error='no-lb-proof', t=0.0)
    lemmas = LemmaStore()
    root = fnode_open(frozenset(), L, lb_proof)
    probes = 0
    lp = 0
    cert_lp = 0
    fwd_nodes = 0
    lemma_uses = 0
    lifts = 0
    multi = 0
    partial_checks = 0
    partial_fail = 0
    first = True
    steps = []
    status = 'open'

    def audit_partial():
        nonlocal partial_checks, partial_fail
        partial_checks += 1
        try:
            Lc = global_L(root, U)
            for leaf in leaves_of(root):
                if leaf.kind == 'open':
                    if leaf.proof.h != leaf.Lf - 1:
                        partial_fail += 1
                        return False
                    if not leaf.proof.audit_rdf():
                        partial_fail += 1
                        return False
                else:
                    if leaf.proof.h < U - 1:
                        partial_fail += 1
                        return False
                    if not leaf.proof.audit_rdf():
                        partial_fail += 1
                        return False
            if Lc > U:
                partial_fail += 1
                return False
            if cmax(inst, sched) != U:
                partial_fail += 1
                return False
            if not check_schedule(inst, U, sched, mach):
                partial_fail += 1
                return False
            return True
        except Exception:
            partial_fail += 1
            return False

    while probes < max_probes:
        L = global_L(root, U)
        if L >= U:
            status = 'closed'
            break
        leaf = select_leaf(inst, root, L, U)
        if leaf is None:
            status = 'stuck'
            break
        if total_lp is not None and lp >= total_lp:
            status = 'budget'
            break
        from mdp import choose_h
        h = choose_h(policy, L, U, first, cfg)
        if h < leaf.Lf:
            h = leaf.Lf
        if h >= U:
            h = U - 1
        r = _probe_leaf(inst, leaf, h, nodecap, lemmas, lp, cfg)
        probes += 1
        first = False
        st = r['stats']
        lp += st['lp_solves']
        cert_lp += st.get('cert_lp', 0)
        fwd_nodes += st.get('fwd_nodes', 0)
        lemma_uses += st.get('lemmas_used', 0)
        lifts += st.get('lifts', 0) + st.get('backjumps', 0)
        if r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            oldL, oldU = L, U
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U, sched, mach = c2, list(s2), list(m2)
            steps.append(dict(h=h, v=True, cmax=c2, lp=st['lp_solves'],
                              fwd=st.get('fwd_nodes', 0),
                              forward=st.get('forward_yes', 0),
                              L0=oldL, U0=oldU,
                              L1=global_L(root, U), U1=U))
        elif r['verdict'] is False:
            proof = r['proof']
            Lf = proof.h + 1
            if Lf >= U:
                new = fnode_sat(leaf.F, proof.h, proof)
            else:
                new = fnode_open(leaf.F, Lf, proof)
            _replace(root, leaf, new)
            lemmas.add(proof_box(proof), proof.h, proof)
            steps.append(dict(h=h, v=False, lp=st['lp_solves'],
                              fwd=st.get('fwd_nodes', 0),
                              L0=L, U0=U, L1=global_L(root, U), U1=U))
        else:
            tree = r.get('tree')
            if tree is None:
                steps.append(dict(h=h, v=None, lp=st['lp_solves'],
                                  L0=L, U0=U, L1=L, U1=U))
                status = 'unknown'
                break
            new = part_to_fnode(inst, tree, leaf, U, h)
            _replace(root, leaf, new)
            _harvest(inst, new, h, lemmas)
            steps.append(dict(h=h, v=None, lp=st['lp_solves'],
                              fwd=st.get('fwd_nodes', 0),
                              L0=L, U0=U, L1=global_L(root, U), U1=U))
        nleaves = sum(1 for x in leaves_of(root))
        if nleaves > 1:
            multi += 1
        audit_partial()

    L = global_L(root, U)
    final = None
    final_ok = False
    if L >= U:
        try:
            final = finalize(inst, root, U, sched, mach)
            final_ok = bool(final.audit_rdf())
        except Exception:
            final_ok = False
    dt = time.time() - t0
    ok = bool(L >= U and U == known and final_ok
              and partial_fail == 0)
    return dict(
        name=name, idx=idx, known=known, policy=policy,
        opt=U, lb=L, lb0=lb, ub0=ub,
        certified=bool(L >= U and final_ok), audit=final_ok,
        proof=final_ok, queries=probes, probes=probes,
        lp=lp, cert_lp=cert_lp, fwd_nodes=fwd_nodes,
        lemma_uses=lemma_uses, lifts=lifts,
        partial_checks=partial_checks, partial_fail=partial_fail,
        multi_states=multi, status=status, steps=steps,
        t=round(dt, 4), ok=ok,
        leaves=sum(1 for x in leaves_of(root)),
    )


def _replace(root, target, new):
    if root is target:
        # singleton root: copy fields
        root.kind = new.kind
        root.F = new.F
        root.Lf = new.Lf
        root.proof = new.proof
        root.h = new.h
        root.i = new.i
        root.mid = new.mid
        root.lo = new.lo
        root.hi = new.hi
        return
    for child in ('lo', 'hi'):
        node = getattr(root, child)
        if node is target:
            setattr(root, child, new)
            return
        if node is not None:
            _replace(node, target, new)


def _harvest(inst, node, h, lemmas):
    if node.kind == 'split':
        _harvest(inst, node.lo, h, lemmas)
        _harvest(inst, node.hi, h, lemmas)
    elif node.kind in ('open', 'sat') and node.proof is not None:
        if node.proof.h == h:
            lemmas.add(proof_box(node.proof), h, node.proof)


def corpora():
    from chip import base_corpus, pert_corpus, stress_corpus
    for tag, rows in (('base', base_corpus()),
                      ('pert', pert_corpus()),
                      ('stress', stress_corpus())):
        for row in rows:
            if len(row) == 4:
                name, idx, inst, known = row
            else:
                idx, known, inst = row
                name = tag
            yield tag, name, idx, inst, known
