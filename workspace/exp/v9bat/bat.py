"""v9.2 BAT-ICF: Bayesian Adaptive Tree search for certified bracketing.

The trusted object is the v9.0 ICF partial certificate

    C = (L, U, s, m, pi),   pi : NO(L-1),  Cmax(s)=U,  L<=U.

BAT adds only a *planner* that chooses the next probe horizon.  The
planner is deliberately untrusted: it may use a learned prior, a
multinomial classifier, root-sampling UCT, or even random actions.  It
never emits a proof and never changes the ICF transition rules.  Hence
a planner error can waste probes but cannot invalidate a bracket.

Planning model.  A probe at h is a threshold query on the hidden
t = OPT:

    NO  (t > h):  [L,U] -> [h+1,U]
    YES (t <= h): [L,U] -> [L,h]

The YES update is conservative: the real oracle returns a schedule of
makespan Cmax <= h, so the live update U <- Cmax can only be better.
No equality is assumed for soundness.

The belief is a three-hypothesis mixture

    beta = p_L * delta_L + p_U * delta_U + p_I * Unif(L+1,U-1),

where (p_L,p_U,p_I) come from a multinomial logistic model on observable
provenance features (gap, lp-pin count, n, m).  The model is fitted on a
calibration set of certified brackets and is guarded by a coverage
check: a prediction is used only if the calibration set has enough
examples in the same feature cell; otherwise a provenance default is
used (interior/binary for pin-free loose bounds, global otherwise).

The planner is exactly solved by dynamic programming on intervals when
the gap is small, and by root-sampling UCT otherwise.  Both use a safe
action skeleton: at depth d, h is allowed only if both abstract children
can still be closed by binary search in d-1 probes.  This gives a
worst-case probe bound of ceil(log2(g0+1))+1, independent of the prior
and the tree search.

The hyperparameters (feature set, L2, coverage cell, support threshold,
default, planner switch, UCT c, simulations) are selected by a
random-search HPO loop on calibration brackets.  HPO is also untrusted:
its output is only a planning prior.
"""
from __future__ import annotations

import collections
import functools
import hashlib
import json
import math
import random
import sys
import time

import numpy as np
from scipy.optimize import minimize

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from icf import (PartialCertificate, ICFCertificate, cmax, corpora,
                 _choose_h)
from pact import PACT, pact_decide
from chip import base_bounds
from rdf import check_schedule


# --------------------------------------------------------------- geometry
def ceil_log2(g):
    g = int(g)
    if g <= 1:
        return 0
    return (g - 1).bit_length()


def safe_depth(L, U):
    g = int(U) - int(L) + 1
    return 0 if g <= 1 else ceil_log2(g) + 1


@functools.lru_cache(maxsize=None)
def safe_actions(L, U, d):
    L, U, d = int(L), int(U), int(d)
    if U <= L:
        return ()
    if d <= 0 or ceil_log2(U - L + 1) > d:
        return ()
    out = []
    for h in range(L, U):
        if ceil_log2(h - L + 1) <= d - 1 and ceil_log2(U - h) <= d - 1:
            out.append(h)
    return tuple(out)


def gap_bucket(g):
    g = int(g)
    if g <= 1:
        return 0
    if g <= 3:
        return 1
    if g <= 7:
        return 2
    return 3


def pin_bucket(pin):
    pin = int(pin or 0)
    if pin <= 0:
        return 0
    if pin <= 2:
        return 1
    return 2


def n_bucket(n):
    return 0 if int(n) <= 10 else 1


# --------------------------------------------------------------- features
FEATURE_NAMES = ('bias', 'log_gap', 'log_pin', 'n', 'm', 'g0', 'g1',
                 'g_le3', 'gap_x_pin', 'prov_pin0_gap')


def raw_features(inst, L, U, pin, mode='full'):
    g = int(U) - int(L)
    pin = int(pin or 0)
    n = int(inst['n'])
    m = int(inst['m'])
    f = [1.0, math.log1p(g), math.log1p(pin), n / 10.0, m / 4.0,
         float(g == 0), float(g == 1), float(g <= 3),
         math.log1p(g) * math.log1p(pin),
         float(pin == 0 and g >= 2)]
    if mode == 'basic':
        return np.array(f[:5], dtype=float)
    if mode == 'gap':
        return np.array(f[:8], dtype=float)
    if mode == 'interact':
        return np.array(f[:9], dtype=float)
    if mode == 'prov':
        return np.array(f[:5] + [f[9]], dtype=float)
    if mode == 'full':
        return np.array(f, dtype=float)
    raise ValueError('unknown feature mode %r' % (mode,))


def cell_of(inst, L, U, pin, mode):
    g = int(U) - int(L)
    pin = int(pin or 0)
    n = int(inst['n'])
    if mode == 'none':
        return ()
    if mode == 'gap':
        return (gap_bucket(g),)
    if mode == 'gap_pin':
        return (gap_bucket(g), pin_bucket(pin))
    if mode == 'prov':
        if pin == 0:
            return ('z', gap_bucket(g), n_bucket(n))
        return ('p', pin_bucket(pin))
    if mode == 'prov_gap':
        if pin == 0:
            return ('z', gap_bucket(g), n_bucket(n))
        return ('p', gap_bucket(g), pin_bucket(pin))
    raise ValueError('unknown cell mode %r' % (mode,))


# --------------------------------------------------------------- prior
class PriorModel:
    """A fitted three-class side prior with a coverage guard."""

    def __init__(self, W, mu, sd, cfg, cell_counts, global_probs,
                 n_train=0):
        self.W = W
        self.mu = mu
        self.sd = sd
        self.cfg = dict(cfg)
        self.cell_counts = dict(cell_counts)
        self.global_probs = tuple(global_probs)
        self.n_train = int(n_train)

    def _logits(self, inst, L, U, pin):
        x = raw_features(inst, L, U, pin, self.cfg['feature_mode'])
        if self.W is None:
            return None
        z = x.copy()
        z[1:] = (z[1:] - self.mu) / self.sd
        return z @ self.W

    def probs(self, inst, L, U, pin):
        if int(U) <= int(L):
            return 0.0, 0.0, 1.0
        W = self.W
        if W is None:
            p = self.global_probs
        else:
            logits = self._logits(inst, L, U, pin)
            logits = logits - logits.max()
            e = np.exp(logits)
            p = tuple(float(x) for x in e / e.sum())
        cell = cell_of(inst, L, U, pin, self.cfg['cell_mode'])
        if self.cell_counts.get(cell, 0) < int(self.cfg['support_k']):
            fb = self.cfg['fallback']
            if fb == 'interior':
                p = (0.0, 0.0, 1.0)
            elif fb == 'global':
                p = self.global_probs
            elif fb == 'lower':
                p = (1.0, 0.0, 0.0)
            elif fb == 'uniform':
                p = (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0)
        z = p[0] + p[1] + p[2]
        if z <= 1e-15:
            return 1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0
        return p[0] / z, p[1] / z, p[2] / z


def _fit_logistic(X, y, l2):
    n, d = X.shape
    K = 3
    mu = X[:, 1:].mean(axis=0)
    sd = X[:, 1:].std(axis=0)
    sd[sd < 1e-9] = 1.0
    Z = X.copy()
    Z[:, 1:] = (Z[:, 1:] - mu) / sd
    Y = np.zeros((n, K))
    Y[np.arange(n), y] = 1.0

    def obj(w):
        W = w.reshape(d, K)
        logits = Z @ W
        logits = logits - logits.max(axis=1, keepdims=True)
        E = np.exp(logits)
        P = E / E.sum(axis=1, keepdims=True)
        nll = -np.log(P[np.arange(n), y] + 1e-15).mean()
        reg = 0.5 * l2 * np.sum(W[1:] ** 2)
        g = Z.T @ (P - Y) / n
        g[1:] += l2 * W[1:]
        return nll + reg, g.ravel()

    res = minimize(obj, np.zeros(d * K), jac=True, method='L-BFGS-B',
                   options={'maxiter': 300})
    return res.x.reshape(d, K), mu, sd


def fit_prior(rows, cfg):
    X, y = [], []
    label = {'L': 0, 'U': 1, 'I': 2}
    for r in rows:
        L, U = int(r['L']), int(r['U'])
        if L >= U:
            continue
        lab = ('L' if int(r['opt']) == L else
               'U' if int(r['opt']) == U else 'I')
        X.append(raw_features(r['inst'], L, U, r.get('pin', 0),
                              cfg['feature_mode']))
        y.append(label[lab])
    counts = collections.Counter()
    for r in rows:
        cell = cell_of(r['inst'], r['L'], r['U'], r.get('pin', 0),
                       cfg['cell_mode'])
        counts[cell] += 1
    glob = collections.Counter()
    for r in rows:
        if int(r['L']) < int(r['U']):
            L, U, o = int(r['L']), int(r['U']), int(r['opt'])
            glob['L' if o == L else 'U' if o == U else 'I'] += 1
    z = sum(glob.values()) + 1.0
    gp = (glob.get('L', 0) / z, glob.get('U', 0) / z, glob.get('I', 0) / z)
    if len(X) < 6 or len(set(y)) < 2:
        return PriorModel(None, None, None, cfg, counts, gp, len(X))
    W, mu, sd = _fit_logistic(np.array(X), np.array(y), cfg['l2'])
    return PriorModel(W, mu, sd, cfg, counts, gp, len(X))


# --------------------------------------------------------------- belief
class Belief:
    """A categorical distribution over one initial integer bracket."""

    def __init__(self, L, U, pL, pU, pI):
        self.L = int(L)
        self.U = int(U)
        g = self.U - self.L + 1
        mass = {}
        if g <= 1:
            mass[self.L] = 1.0
        elif g == 2:
            s = pL + pU
            if s <= 1e-15:
                mass[self.L] = mass[self.U] = 0.5
            else:
                mass[self.L] = pL / s
                mass[self.U] = pU / s
        else:
            mass[self.L] = pL
            mass[self.U] = pU
            if pI > 0:
                for t in range(self.L + 1, self.U):
                    mass[t] = pI / (g - 2)
        s = sum(mass.values())
        if s <= 1e-15:
            mass = {t: 1.0 / g for t in range(self.L, self.U + 1)}
            s = 1.0
        self.mass = {t: v / s for t, v in mass.items()}
        self.prefix = [0.0]
        acc = 0.0
        for t in range(self.L, self.U + 1):
            acc += self.mass.get(t, 0.0)
            self.prefix.append(acc)

    def total(self, l, u):
        l, u = int(l), int(u)
        if u < self.L or l > self.U or l > u:
            return 0.0
        l = max(l, self.L)
        u = min(u, self.U)
        return self.prefix[u - self.L + 1] - self.prefix[l - self.L]

    def prob_yes(self, l, u, h):
        den = self.total(l, u)
        if den <= 1e-15:
            return 0.5
        return self.total(l, min(h, u)) / den

    def sample(self, rng, l, u):
        l, u = int(l), int(u)
        ts, ws = [], []
        for t in range(l, u + 1):
            w = self.mass.get(t, 0.0)
            if w > 0:
                ts.append(t)
                ws.append(w)
        if not ts:
            return (l + u) // 2
        return rng.choices(ts, weights=ws, k=1)[0]

    def distribution(self, l, u):
        den = self.total(l, u)
        if den <= 1e-15:
            return {}
        out = {}
        for t in range(l, u + 1):
            w = self.mass.get(t, 0.0)
            if w > 0:
                out[t] = w / den
        return out


# --------------------------------------------------------------- planners
class DPPlanner:
    """Exact finite-horizon planner for one belief on one bracket."""

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
        acts = safe_actions(L, U, d)
        if not acts:
            self._memo[key] = (float('inf'), None)
            return self._memo[key]
        best = (float('inf'), None)
        for h in acts:
            py = self.belief.prob_yes(L, U, h)
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
        if h is None:
            acts = safe_actions(L, U, d)
            return acts[len(acts) // 2] if acts else (int(L) + int(U)) // 2
        return h


class UCTNode:
    __slots__ = ('N', 'Ns', 'Q', 'children')

    def __init__(self):
        self.N = 0
        self.Ns = collections.defaultdict(int)
        self.Q = collections.defaultdict(float)
        self.children = {}


class MCTSPlanner:
    """Root-sampling UCT on the abstract bracket game."""

    def __init__(self, belief, depth_budget, simulations=256, c=1.0,
                 seed=0):
        self.belief = belief
        self.d0 = int(depth_budget)
        self.N = int(simulations)
        self.c = float(c)
        self.seed = int(seed)
        self.last_visits = None

    def _rollout(self, rng, t, L, U, d):
        cost = 0
        while L < U and d > 0:
            acts = safe_actions(L, U, d)
            if not acts:
                break
            h = acts[len(acts) // 2]
            cost += 1
            if t <= h:
                U = h
            else:
                L = h + 1
            d -= 1
        return cost

    def plan(self, L, U, d=None):
        L, U = int(L), int(U)
        d = self.d0 if d is None else int(d)
        acts = safe_actions(L, U, d)
        if not acts:
            return (L + U) // 2
        if len(acts) == 1:
            self.last_visits = {acts[0]: self.N}
            return acts[0]
        root = UCTNode()
        rng = random.Random(self.seed + 1000003 * L + 9176 * U +
                            37 * int(d))
        for _ in range(self.N):
            t = self.belief.sample(rng, L, U)
            node = root
            path = []
            l, u, dd = L, U, d
            while l < u and dd > 0:
                aacts = safe_actions(l, u, dd)
                if not aacts:
                    break
                unvisited = [h for h in aacts if node.Ns[h] == 0]
                if unvisited:
                    h = unvisited[rng.randrange(len(unvisited))]
                else:
                    logn = math.log(max(2, sum(node.Ns[x] for x in aacts)))
                    h = max(aacts, key=lambda x: (
                        node.Q[x] / node.Ns[x] +
                        self.c * math.sqrt(logn / node.Ns[x]), -x))
                path.append((node, h))
                if t <= h:
                    u = h
                else:
                    l = h + 1
                dd -= 1
                node = node.children.setdefault(h, UCTNode())
            r = self._rollout(rng, t, l, u, dd)
            k = len(path)
            for i, (nd, h) in enumerate(path):
                nd.N += 1
                nd.Ns[h] += 1
                nd.Q[h] += -((k - i) + r)
        self.last_visits = {h: root.Ns[h] for h in acts}
        h = max(acts, key=lambda x: (root.Ns[x],
                                     root.Q[x] / max(1, root.Ns[x])))
        return h


# --------------------------------------------------------------- simulation
PLANNER_DEFAULTS = dict(planner='hybrid', dp_cap=24, uct_c=1.0,
                        simulations=256)


def _make_belief(model, row):
    pL, pU, pI = model.probs(row['inst'], row['L'], row['U'],
                            row.get('pin', 0))
    return Belief(row['L'], row['U'], pL, pU, pI)


def simulate_row(row, model, cfg, seed=0):
    """Play the abstract bracket game with known t; return probe cost."""
    L, U, t = int(row['L']), int(row['U']), int(row['opt'])
    if L >= U:
        return dict(probes=0, calls=0, ok=True, violations=0)
    D0 = safe_depth(L, U)
    belief = _make_belief(model, row)
    planner = cfg.get('planner', 'hybrid')
    dp_cap = int(cfg.get('dp_cap', 24))
    sims = int(cfg.get('simulations', 256))
    uct_c = float(cfg.get('uct_c', 1.0))
    dp = DPPlanner(belief, D0) if planner in ('dp', 'hybrid') else None
    probes = calls = viol = 0
    for step in range(128):
        if L >= U:
            break
        d = D0 - step
        acts = safe_actions(L, U, d)
        if not acts:
            acts = (max(L, min(U - 1, (L + U) // 2)),)
            viol += 1
        if planner == 'dp' or (planner == 'hybrid' and U - L <= dp_cap):
            h = dp.action(L, U, d)
        else:
            mp = MCTSPlanner(belief, D0, sims, uct_c,
                             seed + 17 * step + 1000003 * L + 9176 * U)
            h = mp.plan(L, U, d)
        calls += 1
        if h not in acts:
            h = acts[len(acts) // 2]
            viol += 1
        probes += 1
        if h < t:
            L = h + 1
        else:
            U = h
    return dict(probes=probes, calls=calls, ok=bool(L == U == t),
                violations=viol)


# --------------------------------------------------------------- live ICF
def _cmax(inst, starts):
    return max(starts[i] + inst['p'][i] for i in range(inst['n']))


def make_initial(inst, kind='strong', pin=0):
    """Return (L,U,schedule,machine,proof,pin) for one instance."""
    if kind == 'weak':
        lb, ub, sched, mach, est, q = base_bounds(inst)
        r = pact_decide(inst, int(lb) - 1, depthcap=None, nodecap=None)
        if r['verdict'] is not False:
            return None
        return (int(lb), int(ub), list(sched), list(mach), r['proof'], 0)
    co = PACT(inst, pact_mode='complete', use_ga=False)
    lb, ub, sched, mach = co.initial_bounds()
    if ub is None:
        return None
    lb_proof = co._ensure_lb_proof(int(lb))
    if lb_proof is None:
        r = pact_decide(inst, int(lb) - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            lb_proof = r['proof']
    if lb_proof is None:
        return None
    return (int(lb), int(ub), list(sched), list(mach), lb_proof,
            getattr(co, 'pin_lp', pin))


def run_bat(inst, known, name, idx, initial=None, model=None, cfg=None,
            max_probes=64, seed=0, audit=True):
    """Run the BAT-ICF loop with an untrusted planner."""
    t0 = time.time()
    if cfg is None:
        cfg = dict(PLANNER_DEFAULTS)
    if initial is None:
        initial = make_initial(inst, 'strong')
    if initial is None:
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='no-initial-state', t=0.0)
    L, U, sched, mach, lb_proof, pin = initial
    L, U = int(L), int(U)
    sched = list(sched) if sched is not None else None
    mach = list(mach) if mach is not None else None
    probes = 0
    lp = cert_lp = nodes = 0
    partial_ok = partial_fail = 0
    unknown = 0
    steps = []
    bad_actions = set()
    lb0, ub0 = L, U

    def audit_state():
        nonlocal partial_ok, partial_fail
        if not audit:
            return
        pc = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1

    audit_state()
    if L < U and model is not None:
        pL, pU, pI = model.probs(inst, L, U, pin)
        belief = Belief(L, U, pL, pU, pI)
        D0 = safe_depth(L, U)
        planner = cfg.get('planner', 'hybrid')
        dp_cap = int(cfg.get('dp_cap', 24))
        dp = DPPlanner(belief, D0) if planner in ('dp', 'hybrid') else None
    else:
        belief = dp = None
        D0 = 0
    while L < U and probes < max_probes:
        L0, U0 = L, U
        if model is None or belief is None:
            pol = cfg.get('fallback_policy', 'binary')
            if pol == 'random':
                h = random.Random(seed + 1000003 * L + 9176 * U +
                                  probes).randrange(L, U)
            else:
                h = _choose_h(pol, L, U, probes == 0)
        else:
            d = D0 - probes
            acts = tuple(a for a in safe_actions(L, U, d)
                         if a not in bad_actions)
            if not acts:
                break
            if planner == 'dp' or (planner == 'hybrid' and
                                   U - L <= dp_cap):
                h = dp.action(L, U, d)
            else:
                mp = MCTSPlanner(belief, D0,
                                 cfg.get('simulations', 256),
                                 cfg.get('uct_c', 1.0),
                                 seed + 17 * probes + 1000003 * L +
                                 9176 * U)
                h = mp.plan(L, U, d)
            if h not in acts:
                h = acts[len(acts) // 2]
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        probes += 1
        lp += r.get('lp_solves', 0)
        nodes += r.get('nodes', 0)
        cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False:
            lb_proof = r['proof']
            L = h + 1
            steps.append(dict(h=h, v=False, L0=L0, U0=U0, L1=L, U1=U,
                              lp=r.get('lp_solves', 0),
                              kind=getattr(lb_proof, 'kind', None)))
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = _cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                sched, mach = list(s2), list(m2)
            steps.append(dict(h=h, v=True, L0=L0, U0=U0, L1=L, U1=U,
                              cmax=c2, lp=r.get('lp_solves', 0)))
        else:
            unknown += 1
            bad_actions.add(h)
            steps.append(dict(h=h, v=None, L0=L0, U0=U0, L1=L, U1=U,
                              lp=r.get('lp_solves', 0)))
            continue
        audit_state()

    final = ICFCertificate(inst, U, sched, mach, lb_proof) \
        if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                 probe=probes)
    partial_final = bool(partial.audit_rdf())
    return dict(
        name=name, idx=idx, known=known, opt=U, lb=L, lb0=lb0, ub0=ub0,
        certified=bool(L == U and final_ok),
        audit=final_ok, cert_h=(U - 1 if L == U else None),
        probes=probes, queries=probes,
        pact_lp=lp, pact_nodes=nodes, pact_cert_lp=cert_lp,
        pin_lp=pin, partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_final, unknown=unknown,
        proof_kind=(final.lb_proof.kind if final is not None else
                    getattr(lb_proof, 'kind', None)),
        steps=steps, t=round(time.time() - t0, 4),
        ok=bool(L == U and U == known and final_ok and
                partial_fail == 0 and partial_final),
    )


# --------------------------------------------------------------- rows
def _inst_key(inst):
    s = json.dumps([inst['n'], inst['m'], inst['p'], inst['pred'],
                   inst['elig']], sort_keys=True)
    return hashlib.sha1(s.encode()).hexdigest()[:12]


def load_bracket_rows():
    """Three certified-bracket families used for planning experiments.

    strong : 252 v9.0 initial brackets (LP pin tight)
    weak   : 160 weak-initialization brackets (no LP pin)
    gap    : 29 large-gap cases (primal optimal, loose lower bound)
    """
    imap = {}
    for corpus, name, idx, inst, known in corpora():
        imap[(name, idx)] = (inst, known, corpus)
    rows = []
    for r in json.load(open('exp/v8u/bench_icf_lower-first.json')):
        inst, known, corpus = imap[(r['name'], r['idx'])]
        rows.append(dict(src='strong', name=r['name'], idx=r['idx'],
                         case=None, inst=inst, group=_inst_key(inst),
                         L=int(r['lb0']), U=int(r['ub0']),
                         opt=int(r['known']), pin=int(r.get('pin_lp', 0)),
                         gap=int(r['ub0']) - int(r['lb0'])))
    for r in json.load(open('exp/v10c/bench_pamc.json'))['weak']['lower-first']:
        inst, known, corpus = imap[(r['name'], r['idx'])]
        rows.append(dict(src='weak', name=r['name'], idx=r['idx'],
                         case=None, inst=inst, group=_inst_key(inst),
                         L=int(r['lb0']), U=int(r['ub0']),
                         opt=int(r['known']), pin=0,
                         gap=int(r['ub0']) - int(r['lb0'])))
    gc = {d['case']: d for d in json.load(open('exp/v10c/gap_cases.json'))}
    for r in json.load(open('exp/v9mec/bench_gap.json')):
        if r['policy'] != 'lower-first':
            continue
        d = gc[r['case']]
        rows.append(dict(src='gap', name=r['name'], idx=r['idx'],
                         case=r['case'], inst=d['inst'],
                         group=_inst_key(d['inst']),
                         L=int(r['lb0']), U=int(r['ub0']),
                         opt=int(r['known']),
                         pin=int(r.get('pin_lp', 0)),
                         gap=int(r['ub0']) - int(r['lb0'])))
    return rows


def make_folds(rows, k=5, seed=0):
    """Group folds stratified by source and maximum bracket gap."""
    groups = collections.defaultdict(list)
    for r in rows:
        groups[r['group']].append(r)
    strata = collections.defaultdict(list)
    for g, rs in groups.items():
        src = 'gap' if any(r['src'] == 'gap' for r in rs) else 'sw'
        mg = max(int(r['U']) - int(r['L']) for r in rs)
        strata[(src, gap_bucket(mg))].append(g)
    rng = random.Random(seed)
    folds = [[] for _ in range(k)]
    for key in sorted(strata):
        gs = sorted(strata[key])
        rng.shuffle(gs)
        for i, g in enumerate(gs):
            folds[i % k].extend(groups[g])
    return folds


def hpo_configs(seed=0, n=80):
    """Random-search grid over prior and planner hyperparameters."""
    rng = random.Random(seed)
    feature_modes = ['basic', 'gap', 'interact', 'prov', 'full']
    cell_modes = ['none', 'gap', 'gap_pin', 'prov', 'prov_gap']
    fallbacks = ['interior', 'global', 'uniform']
    planners = ['dp', 'hybrid', 'mcts']
    cfgs = []
    seen = set()
    while len(cfgs) < n:
        cfg = dict(
            feature_mode=rng.choice(feature_modes),
            l2=rng.choice([1e-4, 1e-3, 1e-2, 1e-1, 1.0]),
            cell_mode=rng.choice(cell_modes),
            support_k=rng.choice([1, 3, 5, 10, 20]),
            fallback=rng.choice(fallbacks),
            planner=rng.choice(planners),
            dp_cap=rng.choice([0, 8, 16, 24, 48]),
            uct_c=rng.choice([0.3, 0.7, 1.0, 1.5]),
            simulations=rng.choice([64, 128, 256, 512]),
        )
        key = tuple(sorted(cfg.items(), key=lambda kv: kv[0]))
        if key in seen:
            continue
        seen.add(key)
        cfgs.append(cfg)
    return cfgs


def eval_config(train_rows, val_rows, cfg, seed=0):
    model = fit_prior(train_rows, cfg)
    probes = 0
    calls = 0
    viol = 0
    fails = 0
    for r in val_rows:
        s = simulate_row(r, model, cfg, seed=seed)
        probes += s['probes']
        calls += s['calls']
        viol += s['violations']
        fails += 0 if s['ok'] else 1
    return dict(probes=probes, calls=calls, violations=viol,
                fails=fails, n=len(val_rows), cfg=cfg)


def select_config(train_rows, cfgs, inner_folds=3, seed=0):
    """Select by mean probes on inner group folds; tie-break by simplicity."""
    groups = sorted(set(r['group'] for r in train_rows))
    rng = random.Random(seed + 991)
    rng.shuffle(groups)
    folds = [[] for _ in range(inner_folds)]
    for i, g in enumerate(groups):
        folds[i % inner_folds].append(g)
    gmap = collections.defaultdict(list)
    for r in train_rows:
        gmap[r['group']].append(r)
    best = None
    prior_cache = {}
    for cfg in cfgs:
        pkey = (cfg['feature_mode'], cfg['l2'], cfg['cell_mode'],
                cfg['support_k'], cfg['fallback'])
        tot = collections.Counter()
        for fi in range(inner_folds):
            vg = set(folds[fi])
            val = [r for r in train_rows if r['group'] in vg]
            tr = [r for r in train_rows if r['group'] not in vg]
            ck = (tuple(sorted(r['group'] for r in tr)), pkey)
            model = prior_cache.get(ck)
            if model is None:
                model = fit_prior(tr, cfg)
                prior_cache[ck] = model
            for r in val:
                s = simulate_row(r, model, cfg, seed=seed)
                tot['probes'] += s['probes']
                tot['calls'] += s['calls']
                tot['violations'] += s['violations']
                tot['fails'] += 0 if s['ok'] else 1
        score = (tot['fails'], tot['violations'] / max(1, len(train_rows)),
                 tot['probes'] / max(1, len(train_rows)),
                 0.001 * tot['calls'] / max(1, len(train_rows)),
                 1 if cfg['planner'] == 'mcts' else 0)
        if best is None or score < best[0]:
            best = (score, cfg, tot)
    return best


def cross_validate(rows, cfgs, k=5, seed=0, inner_folds=3):
    folds = make_folds(rows, k=k, seed=seed)
    out = []
    selected = []
    for fi in range(k):
        test = folds[fi]
        train = [r for j, f in enumerate(folds) if j != fi for r in f]
        score, cfg, tot = select_config(train, cfgs,
                                        inner_folds=inner_folds,
                                        seed=seed + 101 * fi)
        selected.append(dict(fold=fi, cfg=cfg, inner=tot))
        model = fit_prior(train, cfg)
        for r in test:
            s = simulate_row(r, model, cfg, seed=seed + fi)
            s['fold'] = fi
            s['src'] = r['src']
            s['group'] = r['group']
            s['L'] = r['L']
            s['U'] = r['U']
            s['opt'] = r['opt']
            s['gap'] = r['gap']
            s['cfg'] = cfg
            out.append(s)
    return out, selected, folds

