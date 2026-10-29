"""CABS: cost-asymmetric bracket search for ICF-PACT.

The outer loop of ICF-PACT is a threshold search for OPT in [L,U].  A
probe at h costs c_N(h) when h < OPT (NO) and c_Y(h) when h >= OPT
(YES).  On the weak corpus these costs are strongly asymmetric: a NO
below OPT is usually one root LP, while a YES may explore a deep
schedule tree.  CABS transforms the bracket search into an interval
decision tree with outcome-dependent costs and solves it by dynamic
programming under a prior over OPT.  The certificate layer is unchanged:
every probe still preserves the ICF partial-certificate invariant.

Policies:
  cabs-dp    : use the Bayes-optimal asymmetric-cost probe at every step.
  cabs-1     : use it for the first probe, then linear from L.
  cabs-guard : cabs-1 with a cap on the posterior probability of YES.
  linear/binary/lower-first/upper-first/pact : baselines.
"""
import collections
import math

from icf import PartialCertificate, ICFCertificate, cmax
from pact import pact_decide
from rdf import check_schedule

INF = 1e18


def fit_prior(rows, eps=0.5, shrinkage=0.0):
    """Fit P(OPT-L0=d | gap=g) with Laplace smoothing."""
    tab = collections.defaultdict(collections.Counter)
    glob = collections.Counter()
    for r in rows:
        g = int(r['U']) - int(r['L'])
        d = int(r['known']) - int(r['L'])
        if 0 <= d <= g:
            tab[g][d] += 1
            glob[d] += 1
    out = {}
    for g, c in tab.items():
        w = [c.get(d, 0) + eps for d in range(g + 1)]
        z = sum(w)
        out[g] = [x / z for x in w]
    if shrinkage > 0 and out:
        gw = {}
        for g in out:
            n = sum(tab[g].values())
            base = [glob.get(d, 0) + eps for d in range(g + 1)]
            z = sum(base)
            base = [x / z for x in base]
            w = [(n * a + shrinkage * b) / (n + shrinkage)
                 for a, b in zip(out[g], base)]
            z = sum(w)
            gw[g] = [x / z for x in w]
        out = gw
    return out


def prior_weights(table, g):
    """Return weights over d=0..g, interpolating missing gaps."""
    if g in table:
        return list(table[g])
    if g <= 0:
        return [1.0]
    lo = max([x for x in table if x <= g], default=None)
    hi = min([x for x in table if x >= g], default=None)
    if lo is not None and hi is not None and lo != hi:
        a = table[lo]
        b = table[hi]
        al = (g - lo) / float(hi - lo)
        w = [(1 - al) * a[min(len(a) - 1, d)]
             + al * b[min(len(b) - 1, d)] for d in range(g + 1)]
        z = sum(w)
        return [x / z for x in w]
    w = [0.01 + 0.4 * (d == 0) + 0.4 * (d == g) for d in range(g + 1)]
    z = sum(w)
    return [x / z for x in w]


def fit_cost(rows):
    """Fit c_N and c_Y(d)=a+b*d from probe profiles."""
    no = []
    yes = []
    for x in rows:
        profile = x.get('profile', {})
        for hs, v in profile.items():
            h = int(hs)
            if v['verdict'] is False:
                no.append((h - int(x['known']), v['lp']))
            elif v['verdict'] is True:
                yes.append((h - int(x['known']), v['lp']))
    cN = sum(c for _, c in no) / max(1, len(no))
    ys = [(d, c) for d, c in yes if d >= 0]
    n = len(ys)
    sx = sum(d for d, _ in ys)
    sy = sum(c for _, c in ys)
    sxx = sum(d * d for d, _ in ys)
    sxy = sum(d * c for d, c in ys)
    if n and n * sxx - sx * sx > 0:
        b = (n * sxy - sx * sy) / (n * sxx - sx * sx)
        a = (sy - b * sx) / n
    else:
        a, b = 4.0, 0.8
    return cN, max(0.0, a), max(0.0, b)


def build_dp(w, cN, a, b, floor=0.0, blocked=()):
    """Bayes-optimal interval decision tree with asymmetric node costs."""
    n = len(w)
    if n <= 1:
        return [[-1]], [[0.0]]
    if floor > 0:
        w = [(1 - floor) * x / sum(w) + floor / n for x in w]
    pre = [0.0]
    prek = [0.0]
    for d, x in enumerate(w):
        pre.append(pre[-1] + x)
        prek.append(prek[-1] + d * x)
    V = [[0.0] * n for _ in range(n)]
    C = [[-1] * n for _ in range(n)]
    blocked = set(blocked)
    for ln in range(2, n + 1):
        for i in range(n - ln + 1):
            j = i + ln - 1
            tot = pre[j + 1] - pre[i]
            best = INF
            bh = -1
            for h in range(i, j):
                if h in blocked:
                    continue
                wy = pre[h + 1] - pre[i]
                py = wy / tot if tot > 0 else 0.0
                ey = ((prek[h + 1] - prek[i]) / wy) if wy > 0 else h
                cY = a + b * max(0.0, h - ey)
                val = (py * cY + (1 - py) * cN
                       + py * V[i][h] + (1 - py) * V[h + 1][j])
                if val < best - 1e-12:
                    best = val
                    bh = h
            if bh < 0:
                V[i][j] = INF
                C[i][j] = -1
            else:
                V[i][j] = best
                C[i][j] = bh
    return C, V


def natural(h, L, U, blocked):
    """Nearest non-blocked horizon in [L,U-1]."""
    if h is not None and h not in blocked and L <= h < U:
        return h
    cands = [z for z in range(L, U) if z not in blocked]
    if not cands:
        return None
    if h is None:
        return cands[0]
    cands.sort(key=lambda z: (abs(z - h), z))
    return cands[0]


class ProbeCache:
    def __init__(self):
        self.d = {}
        self.hits = 0
        self.misses = 0

    def get(self, inst, h):
        key = (id(inst), int(h))
        if key in self.d:
            self.hits += 1
            return self.d[key]
        self.misses += 1
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        self.d[key] = r
        return r


class Policy:
    def __init__(self, name, weights=None, cN=1.0, a=4.0, b=0.8,
                 floor=0.0, yes_cap=None, fallback='linear'):
        self.name = name
        self.weights = list(weights) if weights is not None else None
        self.cN = cN
        self.a = a
        self.b = b
        self.floor = floor
        self.yes_cap = yes_cap
        self.fallback = fallback
        self.tables = {}
        self.used_dp = 0

    def _table(self, blocked_rel):
        key = tuple(sorted(blocked_rel))
        if key not in self.tables:
            self.tables[key] = build_dp(self.weights, self.cN, self.a,
                                        self.b, self.floor, key)
        return self.tables[key]

    def _dp_choice(self, L, U, blocked, L0):
        i, j = L - L0, U - L0
        if self.weights is None or i < 0 or j >= len(self.weights):
            return None
        rel = [h - L0 for h in blocked if L0 <= h <= L0 + len(self.weights)]
        C, _ = self._table(rel)
        if i > j or C[i][j] < 0:
            return None
        return L0 + C[i][j]

    def choose(self, L, U, blocked, first, L0):
        if U <= L:
            return L
        h = None
        if self.weights is not None:
            if self.name in ('cabs-dp', 'cabs-1', 'cabs-guard'):
                if self.name == 'cabs-dp' or first:
                    h = self._dp_choice(L, U, blocked, L0)
                    if h is not None and self.name == 'cabs-guard' \
                            and self.yes_cap is not None:
                        h = self._guard(h, L, U, L0)
        if h is None:
            if self.name in ('linear', 'cabs-1', 'cabs-guard'):
                h = L
            elif self.name == 'binary':
                h = (L + U) // 2
            elif self.name == 'lower-first':
                h = L if first else (L + U) // 2
            elif self.name == 'upper-first':
                h = U - 1
            elif self.name == 'pact':
                h = L if U - L <= 4 else (L + U) // 2
            elif self.name == 'cabs-dp':
                h = (L + U) // 2
            else:
                h = L
        return natural(h, L, U, blocked)

    def _guard(self, h, L, U, L0):
        i, j = L - L0, U - L0
        tot = sum(self.weights[i:j + 1])
        if tot <= 0:
            return L
        while h > L:
            wy = sum(self.weights[i:h - L0 + 1])
            if wy / tot <= self.yes_cap + 1e-12:
                return h
            h -= 1
        return L


def _audit(inst, L, U, s, m, pi):
    pc = PartialCertificate(inst, L, U, s, m, pi)
    return pc.audit_rdf()


def run_case(inst, known, init, policy, cache, max_probes=64):
    L, U, s, m, pi = init
    L, U = int(L), int(U)
    s = list(s) if s is not None else None
    m = list(m) if m is not None else None
    L0, U0 = L, U
    blocked = set()
    probes = lp = cert = nodes = 0
    partial_ok = partial_fail = 0
    steps = []
    first = True
    t0 = __import__('time').time()

    def audit():
        nonlocal partial_ok, partial_fail
        if _audit(inst, L, U, s, m, pi):
            partial_ok += 1
        else:
            partial_fail += 1

    audit()
    while L < U and probes < max_probes:
        L1, U1 = L, U
        h = policy.choose(L, U, blocked, first, L0)
        if h is None:
            break
        r = cache.get(inst, h)
        probes += 1
        lp += r.get('lp_solves', 0)
        cert += r.get('cert_lp', 0)
        nodes += r.get('nodes', 0)
        v = r['verdict']
        if v is None:
            blocked.add(h)
            steps.append(dict(h=h, v=None, kind='unknown',
                              lp=r.get('lp_solves', 0),
                              L0=L1, U0=U1, L1=L, U1=U))
            continue
        first = False
        if v is False:
            L = h + 1
            pi = r['proof']
            steps.append(dict(h=h, v=False, kind=pi.kind,
                              lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L1, U0=U1, L1=L, U1=U))
        else:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                s, m = list(s2), list(m2)
            steps.append(dict(h=h, v=True, cmax=c2,
                              lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L1, U0=U1, L1=L, U1=U))
        audit()
    final = ICFCertificate(inst, U, s, m, pi) if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial_final = _audit(inst, L, U, s, m, pi)
    return dict(corpus=None, name=None, idx=None, known=known,
                policy=policy.name, opt=U, lb=L, lb0=L0, ub0=U0,
                certified=bool(L == U and final_ok), audit=final_ok,
                proof=final_ok, cert_h=(U - 1 if L == U else None),
                queries=probes, probes=probes, pact_lp=lp,
                pact_nodes=nodes, pact_cert_lp=cert,
                partial_ok=partial_ok, partial_fail=partial_fail,
                partial_final=partial_final, unknown=0,
                steps=steps,
                proof_kind=(pi.kind if pi is not None else None),
                total_audit=final_ok,
                t=round(__import__('time').time() - t0, 4),
                ok=bool(L == U and U == known and final_ok
                        and partial_fail == 0 and partial_final))
