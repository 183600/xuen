"""v9.1 MCTS-BC: bracket-certificate planning for ICF-PACT.

The trusted object is v9.0's partial certificate

    C = (L, U, s, m, pi),   pi : NO(L-1),  Cmax(s)=U,  L<=U.

This module adds only a *planner* that chooses the next probe horizon h.
The planner never emits a proof and never changes the certificate rules.
It is therefore untrusted: a wrong belief or a wrong MCTS value can only
waste probes, not invalidate a bracket.

Planning model.  We abstract a probe at h as a threshold query:

    NO  (t > h):  [L,U] -> [h+1,U]
    YES (t <= h): [L,U] -> [L,h]

where t = OPT.  The YES side is conservative: the real oracle returns a
schedule of makespan Cmax <= h, so the real update U <- Cmax can only be
better than the abstract U <- h.  No equality is assumed for soundness.

The belief is a three-hypothesis mixture

    beta = p_L * delta_L + p_U * delta_U + p_I * Unif(L+1,U-1),

with (p_L,p_U,p_I) estimated from a provenance bucket.  The bucket is
(gap, pin LP count), which is observable before the first probe.  The
mixture is updated by truncation after each observation.

The safety skeleton restricts actions to

    A_d(L,U) = { h : ceil_log2(h-L+1) <= d-1
                     and ceil_log2(U-h) <= d-1 }.

Starting with d0 = ceil_log2(U0-L0+1) + 1, every branch can be finished
by a binary search inside the remaining depth.  This gives a worst-case
probe bound of d0, within a factor 2 of the comparison lower bound
ceil_log2(g0).  The bound is independent of the belief and of MCTS.

The exact planner for small games is a dynamic program over intervals
(for a fixed belief).  The scalable planner is root-sampling UCT.  Both
are implemented; the live scheduler uses DP when g <= dp_cap and MCTS
otherwise, with a binary gate when the posterior interior mass is high.
"""
from __future__ import annotations

import collections
import functools
import hashlib
import json
import math
import random
import sys

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']


def ceil_log2(g):
    """ceil(log2(g)) for integer g >= 1, with ceil_log2(1)=0."""
    g = int(g)
    if g <= 1:
        return 0
    return (g - 1).bit_length()


def safe_depth(L, U):
    """Global probe budget: one above the comparison lower bound."""
    g = int(U) - int(L) + 1
    return 0 if g <= 1 else ceil_log2(g) + 1


@functools.lru_cache(maxsize=None)
def safe_actions(L, U, d):
    """Horizons whose two abstract children fit in d-1 remaining probes."""
    L, U, d = int(L), int(U), int(d)
    if U <= L:
        return ()
    if d <= 0 or ceil_log2(U - L + 1) > d:
        return ()
    out = []
    for h in range(L, U):
        a = h - L + 1
        b = U - h
        if ceil_log2(a) <= d - 1 and ceil_log2(b) <= d - 1:
            out.append(h)
    return tuple(out)


def _ceil_half(g):
    return (g + 1) // 2


def median_action(L, U):
    return (int(L) + int(U)) // 2


# --------------------------------------------------------------- belief
def gap_bucket(gap):
    gap = int(gap)
    if gap <= 1:
        return 1
    if gap <= 3:
        return 2
    return 3


def pin_bucket(pin):
    pin = int(pin or 0)
    if pin <= 0:
        return 0
    if pin == 1:
        return 1
    return 2


class Prior:
    """Dirichlet-smoothed provenance prior over L / U / interior."""

    def __init__(self, rows, exclude_group=None, alpha=1.0):
        self.alpha = float(alpha)
        self.counts = collections.defaultdict(collections.Counter)
        self.global_counts = collections.Counter()
        for r in rows:
            if exclude_group is not None and r['group'] == exclude_group:
                continue
            if r['L'] == r['U']:
                continue
            lab = row_label(r)
            self.counts[(pin_bucket(r.get('pin', 0)),
                         gap_bucket(r['U'] - r['L']))][lab] += 1
            self.global_counts[lab] += 1

    def probs(self, pin, gap):
        c = self.counts.get((pin_bucket(pin), gap_bucket(gap)))
        if not c or not sum(c.values()):
            c = self.global_counts
        a = self.alpha
        nL = c.get('L', 0) + a
        nU = c.get('U', 0) + a
        nI = c.get('I', 0) + a
        z = nL + nU + nI
        return nL / z, nU / z, nI / z

    def probs_row(self, r):
        return self.probs(r.get('pin', 0), r['U'] - r['L'])


def row_label(r):
    L, U, o = r['L'], r['U'], r['opt']
    if L == U:
        return 'both'
    if o == L:
        return 'L'
    if o == U:
        return 'U'
    return 'I'


class Belief:
    """A categorical distribution over integer OPT in [L0,U0]."""

    def __init__(self, L, U, pL, pU, pI):
        self.L = int(L)
        self.U = int(U)
        self.pL = float(pL)
        self.pU = float(pU)
        self.pI = float(pI)
        g = self.U - self.L + 1
        mass = {}
        if g <= 1:
            mass[self.L] = 1.0
        else:
            if g == 2:
                z = self.pL + self.pU
                if z <= 1e-15:
                    mass[self.L] = mass[self.U] = 0.5
                else:
                    mass[self.L] = self.pL / z
                    mass[self.U] = self.pU / z
            else:
                mass[self.L] = self.pL
                mass[self.U] = self.pU
                for t in range(self.L + 1, self.U):
                    mass[t] = self.pI / (g - 2)
        self.mass = mass
        self.prefix = []
        s = 0.0
        for t in range(self.L, self.U + 1):
            s += mass.get(t, 0.0)
            self.prefix.append(s)

    def total(self, l, u):
        if u < self.L or l > self.U:
            return 0.0
        l = max(l, self.L)
        u = min(u, self.U)
        if l > u:
            return 0.0
        return self.prefix[u - self.L] - (self.prefix[l - 1 - self.L]
                                          if l > self.L else 0.0)

    def conditional_yes(self, l, u, h):
        den = self.total(l, u)
        if den <= 1e-15:
            return 0.5
        return self.total(l, min(h, u)) / den

    def sample(self, rng, l=None, u=None):
        l = self.L if l is None else int(l)
        u = self.U if u is None else int(u)
        ts = []
        ws = []
        for t in range(l, u + 1):
            w = self.mass.get(t, 0.0)
            if w > 0:
                ts.append(t)
                ws.append(w)
        if not ts:
            return (l + u) // 2
        return rng.choices(ts, weights=ws, k=1)[0]

    def distribution(self, l, u):
        out = {}
        den = self.total(l, u)
        if den <= 1e-15:
            return out
        for t in range(l, u + 1):
            w = self.mass.get(t, 0.0)
            if w > 0:
                out[t] = w / den
        return out


# ------------------------------------------------------------- exact DP
class DPPlanner:
    """Exact finite-horizon planner for one belief on [L0,U0]."""

    def __init__(self, belief, depth_budget):
        self.belief = belief
        self.d0 = int(depth_budget)
        self._memo = {}

    def value(self, L, U, d):
        key = (int(L), int(U), int(d))
        if key in self._memo:
            return self._memo[key]
        L, U, d = key
        if L >= U:
            self._memo[key] = (0.0, None)
            return self._memo[key]
        if d <= 0 or ceil_log2(U - L + 1) > d:
            self._memo[key] = (float('inf'), None)
            return self._memo[key]
        best = (float('inf'), None)
        for h in safe_actions(L, U, d):
            py = self.belief.conditional_yes(L, U, h)
            va, _ = self.value(L, h, d - 1)
            vb, _ = self.value(h + 1, U, d - 1)
            if not math.isfinite(va) or not math.isfinite(vb):
                continue
            val = 1.0 + py * va + (1.0 - py) * vb
            if val < best[0] - 1e-12:
                best = (val, h)
        self._memo[key] = best
        return best

    def action(self, L, U, d=None):
        d = self.d0 if d is None else int(d)
        _, h = self.value(L, U, d)
        return median_action(L, U) if h is None else h


# --------------------------------------------------------------- MCTS
class UCTNode:
    __slots__ = ('N', 'Q', 'Ns', 'children')

    def __init__(self):
        self.N = 0
        self.Q = collections.defaultdict(float)
        self.Ns = collections.defaultdict(int)
        self.children = {}


class MCTSPlanner:
    """Root-sampling UCT over the abstract bracket game."""

    def __init__(self, belief, depth_budget, simulations=2048, c=1.0,
                 seed=0):
        self.belief = belief
        self.d0 = int(depth_budget)
        self.N = int(simulations)
        self.c = float(c)
        self.seed = int(seed)
        self.last_visits = None
        self.last_root = None

    def _simulate(self, rng, t, root, depth0):
        L, U = self.belief.L, self.belief.U
        # The MCTS tree is always rooted at the caller's state, not at
        # the belief support.  This is set by plan().
        L, U = root
        d = self.d0 - depth0
        node = self._tree
        path = []
        while L < U:
            acts = safe_actions(L, U, d)
            if not acts:
                break
            node.N += 1
            unvisited = [h for h in acts if node.Ns[h] == 0]
            if unvisited:
                h = unvisited[0]
            else:
                total = sum(node.Ns[x] for x in acts)
                logt = math.log(max(2, total))
                h = max(acts, key=lambda x: (node.Q[x] +
                                             self.c * math.sqrt(
                                                 logt / node.Ns[x]), -x))
            path.append((node, h))
            if h < t:
                L = h + 1
            else:
                U = h
            d -= 1
            node = node.children.setdefault(h, UCTNode())
        reward = -len(path)
        for nd, h in path:
            nd.Ns[h] += 1
            nd.Q[h] += reward
        return len(path)

    def plan(self, L, U, depth0=0):
        L, U = int(L), int(U)
        d = self.d0 - int(depth0)
        acts = safe_actions(L, U, d)
        if not acts:
            return median_action(L, U)
        self._tree = UCTNode()
        rng = random.Random(self.seed + 1000003 * L + 9176 * U +
                            37 * int(depth0))
        for _ in range(self.N):
            t = self.belief.sample(rng, L, U)
            self._simulate(rng, t, (L, U), depth0)
        root = self._tree
        self.last_visits = {h: root.Ns[h] for h in acts}
        self.last_root = (L, U, d)
        # Most-visited child is the robust root action.  Max-Q is used as
        # a tie-break (it has lower variance when visits are tied).
        h = max(acts, key=lambda x: (root.Ns[x], root.Q[x] / max(1, root.Ns[x])))
        return h


# ------------------------------------------------------------ policies
def base_action(kind, L, U, first):
    g = U - L
    if kind == 'lower-first':
        return L if first else (L + U) // 2
    if kind == 'upper-first':
        return U - 1
    if kind == 'binary':
        return (L + U) // 2
    if kind == 'pact':
        return L if g <= 4 else (L + U) // 2
    raise ValueError(kind)


def base_trajectory(kind, L, U, t, cap=128):
    n = 0
    first = True
    while L < U and n < cap:
        h = base_action(kind, L, U, first)
        first = False
        n += 1
        if h < t:
            L = h + 1
        else:
            U = h
    return n, L, U


def safe_plan(planner, L, U, depth0, gate=0.5, prior_probs=None):
    """DP/MCTS planner with a binary gate and a median fallback.

    planner is 'dp' or 'mcts'.  prior_probs=(pL,pU,pI) for this state.
    If pI >= gate, binary is used: the posterior says the target is not
    at an endpoint, so the safe balanced split is the right default.
    """
    d = safe_depth_remaining = planner.d0 - int(depth0)
    if safe_depth_remaining <= 0 or U <= L:
        return median_action(L, U)
    acts = safe_actions(L, U, safe_depth_remaining)
    if not acts:
        return median_action(L, U)
    if prior_probs is not None and prior_probs[2] >= gate:
        h = median_action(L, U)
    elif planner == 'dp':
        h = DPPlanner(planner_belief, planner.d0).action(
            L, U, safe_depth_remaining)
    else:
        h = planner.plan(L, U, depth0)
    if h not in acts:
        h = median_action(L, U)
    return h


# ------------------------------------------------------------- corpus
def instance_key(inst):
    s = json.dumps([inst['n'], inst['m'], inst['p'], inst['pred'],
                   inst['elig']], sort_keys=True)
    return hashlib.sha1(s.encode()).hexdigest()[:12]


def load_bracket_rows():
    """441 certified initial brackets from three benchmark families.

    strong : the 252 PACT-strong brackets of v9.0
    weak   : the 160 weak-initialization brackets of bench_ptb
    gap    : the 29 large-gap brackets of v10b/v10c
    """
    from icf import corpora
    imap = {}
    for corpus, name, idx, inst, known in corpora():
        imap[(name, idx)] = (inst, known, corpus)
    rows = []
    for r in json.load(open('exp/v8u/bench_icf_lower-first.json')):
        inst, known, _ = imap[(r['name'], r['idx'])]
        rows.append(dict(src='strong', name=r['name'], idx=r['idx'],
                         case=None, inst=inst, group=instance_key(inst),
                         L=int(r['lb0']), U=int(r['ub0']),
                         opt=int(r['known']), pin=int(r.get('pin_lp', 0)),
                         gap=int(r['ub0']) - int(r['lb0'])))
    for r in json.load(open('exp/v10c/bench_pamc.json'))['weak']['lower-first']:
        inst, known, _ = imap[(r['name'], r['idx'])]
        rows.append(dict(src='weak', name=r['name'], idx=r['idx'],
                         case=None, inst=inst, group=instance_key(inst),
                         L=int(r['lb0']), U=int(r['ub0']),
                         opt=int(r['known']), pin=int(r.get('pin_lp', 0)),
                         gap=int(r['ub0']) - int(r['lb0'])))
    gc = {d['case']: d for d in json.load(open('exp/v10c/gap_cases.json'))}
    for r in json.load(open('exp/v9mec/bench_gap.json')):
        if r['policy'] != 'lower-first':
            continue
        d = gc[r['case']]
        rows.append(dict(src='gap', name=r['name'], idx=r['idx'],
                         case=r['case'], inst=d['inst'],
                         group=instance_key(d['inst']),
                         L=int(r['lb0']), U=int(r['ub0']),
                         opt=int(r['known']), pin=int(r.get('pin_lp', 0)),
                         gap=int(r['ub0']) - int(r['lb0'])))
    return rows


def run_bracket_row(r, kind, rows, simulations=2048, gate=0.5, seed=0,
                    exact_belief=False, confidence=1.0, c=1.0):
    """Simulate one bracket trajectory under a known OPT.

    This is a planner experiment: the oracle is the threshold model, not
    the LP.  The live LP validation is in mcts_icf.py.
    """
    L, U, t = int(r['L']), int(r['U']), int(r['opt'])
    D0 = safe_depth(L, U)
    probes = 0
    decisions = []
    prior = None
    pL = pU = pI = None
    if kind in ('dp', 'mcts', 'portfolio'):
        prior = Prior(rows, exclude_group=(None if exact_belief else r['group']))
        pL, pU, pI = prior.probs(r.get('pin', 0), r['U'] - r['L'])
    while L < U and probes < 128:
        belief = None
        if kind in ('dp', 'mcts', 'portfolio'):
            belief = Belief(L, U, pL, pU, pI)
        drem = D0 - probes
        acts = safe_actions(L, U, drem)
        if kind == 'binary':
            h = median_action(L, U)
        elif kind in ('lower-first', 'upper-first', 'pact'):
            h = base_action(kind, L, U, probes == 0)
        elif kind == 'dp':
            if not acts:
                h = median_action(L, U)
            elif pI >= gate:
                h = median_action(L, U)
            else:
                h = DPPlanner(belief, D0).action(L, U, drem)
        elif kind == 'mcts':
            if not acts:
                h = median_action(L, U)
            elif pI >= gate:
                h = median_action(L, U)
            else:
                h = MCTSPlanner(belief, D0, simulations=simulations,
                                c=c, seed=seed + 17 * probes).plan(L, U, probes)
        elif kind == 'portfolio':
            h = _portfolio_action(L, U, belief, D0, probes,
                                  simulations, seed)
        else:
            raise ValueError(kind)
        if kind in ('dp', 'mcts', 'portfolio') and h not in acts:
            h = median_action(L, U)
        decisions.append(dict(L=L, U=U, h=h, pL=pL, pU=pU, pI=pI))
        probes += 1
        if h < t:
            L = h + 1
        else:
            U = h
    return dict(probes=probes, L=L, U=U, ok=bool(L == U == t),
                D0=D0, decisions=decisions)


def _portfolio_action(L, U, belief, D0, depth0, simulations, seed):
    """Monte-Carlo policy portfolio: evaluate base policies by rollouts."""
    rng = random.Random(seed + 7919 * L + 104729 * U + 13 * depth0)
    acts = safe_actions(L, U, D0 - depth0)
    if not acts:
        return median_action(L, U)
    best = None
    for kind in ('lower-first', 'upper-first', 'binary', 'pact'):
        h0 = base_action(kind, L, U, True)
        if h0 not in acts:
            continue
        total = 0
        for _ in range(max(32, simulations // 8)):
            t = belief.sample(rng, L, U)
            n, _, _ = base_trajectory(kind, L, U, t)
            total += n
        val = total / max(1, simulations // 8)
        if best is None or val < best[0]:
            best = (val, h0)
    return median_action(L, U) if best is None else best[1]


def summarize(rows, label=''):
    out = dict(n=len(rows))
    for key in ('probes',):
        vals = [r[key] for r in rows]
        if not vals:
            continue
        out.update(mean=sum(vals) / len(vals), total=sum(vals),
                   max=max(vals),
                   p90=sorted(vals)[max(0, int(0.9 * len(vals)) - 1)])
    out['ok'] = sum(bool(r['ok']) for r in rows)
    return out
