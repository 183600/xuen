"""v9.1 GARF-PACT: geometric anytime ranking frontier.

The state is a live partition tree of interval boxes.  Every leaf is
either

  * open:  a proof NO(L_f - 1 | box) with L_f < U, or
  * dead:  a proof NO(h | box) with h >= U - 1.

The global lower bound is min L_f over open leaves (or U if none).  The
incumbent (s,m) gives Cmax(s)=U.  Thus every state is a certified
bracket [L,U]; if L=U it is an optimality certificate.  The loop
invariant is checked by PartialFrontierCertificate.audit_rdf().

There are three transitions:

  PROBE  : decide(f,h); NO -> L_f=h+1, YES -> lower U.
  SPLIT  : replace an open leaf by two interval children.
  CLOSE  : mark a leaf dead when L_f >= U.

Termination is certified by the lexicographic ranking function

  rho = (U, sorted_desc{width(f): f open}, sum_{f open}(U-L_f)).

A SPLIT replaces one width by two strictly smaller widths; a NO on an
open leaf decreases the third component; a YES decreases U; CLOSE
removes an open width.  exp/v9i/rafa.py logs every rho transition and
audits strict decrease.

The geometric policy h = min(U-1, floor((1+eps)L)) gives an anytime
approximation guarantee: a YES answers with Cmax <= (1+eps)L <=
(1+eps)OPT; a NO raises one open leaf above (1+eps)L.  Once all leaves
at the current L-level are raised, L itself grows by the same factor.
"""
import sys
import time
import math
import collections

sys.path[:0] = ['exp/v9i', 'exp/v9m', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8j', 'exp/v8f', 'exp/v8e', 'exp/v8g',
                'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a',
                'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']

from apex import Proof, bound_lb
from chip import chip_bounds
from pact import PACT, pact_decide
from sage import BranchProof, SubsumptionProof, _elig_aware, _domain
from sdecc import SDLP
from po import heads_tails
from cert import verify
from rdf import check_schedule
from prism import root_box, box_forbid
from icf import cmax, _proof_forbid


# ------------------------------------------------------------------ node
class Node:
    __slots__ = ('lo', 'hi', 'L', 'proof', 'dead', 'children', 'split')

    def __init__(self, lo, hi, L, proof):
        self.lo = tuple(int(x) for x in lo)
        self.hi = tuple(int(x) for x in hi)
        self.L = int(L)
        self.proof = proof
        self.dead = False
        self.children = None
        self.split = None

    def width(self):
        return sum(max(0, self.hi[i] - self.lo[i] + 1)
                   for i in range(len(self.lo)))

    def copy(self):
        n = Node(self.lo, self.hi, self.L, self.proof)
        n.dead = self.dead
        n.children = self.children
        n.split = self.split
        return n


def leaves(root):
    out = []
    stack = [root]
    while stack:
        nd = stack.pop()
        if nd.children is None:
            out.append(nd)
        else:
            stack.append(nd.children[1])
            stack.append(nd.children[0])
    return out


def open_leaves(root, U):
    return [nd for nd in leaves(root) if not nd.dead and nd.L < U]


def global_L(root, U):
    vals = [nd.L for nd in open_leaves(root, U)]
    return min(vals) if vals else U


# --------------------------------------------------------------- ranking
def rank_of(root, U):
    """Lexicographic termination measure (U, widths_desc, sum(U-L_f))."""
    widths = []
    s = 0
    for nd in open_leaves(root, U):
        widths.append(nd.width())
        s += U - nd.L
    widths.sort(reverse=True)
    return (int(U), tuple(widths), int(s))


class RankLedger:
    """Runtime audit of the termination ranking."""

    def __init__(self):
        self.last = None
        self.steps = 0
        self.fail = 0
        self.kinds = collections.Counter()
        self.first = None
        self.bad = []

    def check(self, root, U, kind):
        r = rank_of(root, U)
        if self.first is None:
            self.first = r
        if self.last is not None and not (r < self.last):
            self.fail += 1
            if len(self.bad) < 8:
                self.bad.append((kind, self.last, r))
        self.last = r
        self.steps += 1
        self.kinds[kind] += 1
        return r

    def summary(self):
        return dict(steps=self.steps, fail=self.fail,
                    kinds=dict(self.kinds), first=self.first,
                    last=self.last, bad=self.bad)


# --------------------------------------------------------------- splitting
def _decode(inst, lp, z):
    n = inst['n']
    elig = _elig_aware(inst)
    starts = [None] * n
    machs = [None] * n
    for c, key in enumerate(lp.cols):
        if z[c] > 1 - 1e-7:
            i, t = key[0], key[-1]
            if starts[i] is not None:
                return None
            starts[i] = t
            if elig:
                machs[i] = key[1]
    if any(x is None for x in starts):
        return None
    if not elig:
        from pact import _assign_machines
        machs = _assign_machines(inst, starts)
        if machs is None:
            return None
    if check_schedule(inst, cmax(inst, starts), starts, machs):
        return starts, machs
    return None


def choose_split(inst, h, lo, hi):
    """Choose an LP-guided interval split, or a YES/NO outcome.

    Returns ('split',(i,mid)) / ('yes',(s,m)) / ('no',None) /
    ('unknown',None).  The split is always inside the current box and
    both children contain at least one allowed start time at h.
    """
    n = inst['n']
    F = box_forbid(inst, h, lo, hi)
    est, q = heads_tails(inst, 0, [0] * n)
    lp = SDLP(inst, h, est, q, use_dom=True,
              elig_aware=_elig_aware(inst), forbid=F)
    if lp.N == 0:
        return ('no', None)
    res = lp.solve()
    if res.status == 2:
        return ('no', None)
    if res.status != 0:
        return ('unknown', None)
    z = res.x
    frac = any(1e-7 < z[c] < 1 - 1e-7 for c in range(lp.N))
    if not frac:
        got = _decode(inst, lp, z)
        if got is not None:
            return ('yes', got)
        for i in range(n):
            times = sorted({key[-1] for c, key in enumerate(lp.cols)
                            if key[0] == i and z[c] > 1e-7})
            if len(times) > 1:
                mid = times[len(times) // 2 - 1]
                return ('split', (i, mid))
        return ('unknown', None)
    best = None
    for i in range(n):
        dist = []
        mass = 0.0
        for c, key in enumerate(lp.cols):
            if key[0] == i:
                v = z[c]
                if v > 1e-9:
                    dist.append((key[-1], v))
                    mass += v
        if len(dist) <= 1:
            continue
        f = sum(v for _, v in dist if 1e-7 < v < 1 - 1e-7)
        if f <= 1e-7:
            continue
        key = (mass, f, -i)
        if best is None or key > best[0]:
            best = (key, i, dist)
    if best is None:
        return ('unknown', None)
    _, i, dist = best
    dist.sort()
    total = sum(v for _, v in dist)
    acc = 0.0
    mid = dist[0][0]
    for t, v in dist:
        acc += v
        if acc >= 0.5 * total:
            mid = t
            break
    times = [t for t, _ in dist]
    lo_t = [t for t in times if t > mid]
    hi_t = [t for t in times if t <= mid]
    if not lo_t or not hi_t:
        mid = times[len(times) // 2 - 1]
    return ('split', (i, mid))


def arbitrary_split(inst, h, lo, hi):
    """Fallback split when the LP cannot produce a certificate.

    Picks the job with the largest box width that has at least two
    allowed start times at h, and splits at the median allowed time.
    This is sound for the same reason as an LP-guided split; it simply
    ignores the fractional solution.
    """
    n = inst['n']
    best = None
    for i in range(n):
        a, b = _domain(inst, h, i)
        times = [t for t in range(max(a, lo[i]), min(b, hi[i]) + 1)]
        if len(times) < 2:
            continue
        w = times[-1] - times[0] + 1
        key = (w, len(times), -i)
        if best is None or key > best[0]:
            best = (key, i, times)
    if best is None:
        return None
    _, i, times = best
    mid = times[len(times) // 2 - 1]
    return (i, mid)


# ------------------------------------------------------- lower-bound set-up
def lower_proof(inst, L):
    """A proof of NO(L-1), reusing PACT's store when possible."""
    co = PACT(inst, pact_mode='complete', use_ga=False)
    p = co._ensure_lb_proof(L)
    if p is not None and p.h == L - 1 and p.audit_rdf():
        return p, co
    r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
    if r['verdict'] is False and r['proof'] is not None \
            and r['proof'].h == L - 1 and r['proof'].audit_rdf():
        return r['proof'], co
    return None, co


def init_state(inst, mode='weak'):
    """Return (root,U,s,m,L0,co,stats).

    mode='pact'  uses PACT's initial lower bound.
    mode='weak'  keeps PACT's incumbent but starts from the certified
                 critical-path + eligibility-load bound.  This creates
                 the large-gap regime that the 252-instance corpus lacks.
    """
    co = PACT(inst, pact_mode='complete', use_ga=False)
    lb, ub, s, m = co.initial_bounds()
    if ub is None:
        return None
    U = int(ub)
    L = int(lb) if mode == 'pact' else int(bound_lb(inst))
    if L > U:
        L = int(lb)
    p, co = lower_proof(inst, L)
    if p is None:
        return None
    lo, hi = root_box(inst, U)
    root = Node(lo, hi, L, p)
    if L >= U:
        root.dead = True
    return dict(root=root, U=U, schedule=list(s), machine=list(m),
                L0=L, U0=U, co=co)


# ---------------------------------------------------------- certificate
def _box_ok(inst, U, lo, hi):
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    for i in range(n):
        if lo[i] > hi[i]:
            return False
        if lo[i] > est[i]:
            return False
        if hi[i] < U - q[i] - inst['p'][i]:
            return False
    return True


class FrontierCertificate(Proof):
    """A partial or exact bracket carried by a live interval frontier.

    For an open leaf f: proof = NO(L_f-1 | box_f), L_f < U.
    For a dead leaf f: proof = NO(h | box_f), h >= U-1.
    The certificate asserts L = min open L_f (or U) and Cmax(s)=U.
    If L=U it is an optimality certificate.
    """

    kind = 'rafa-frontier'

    def __init__(self, inst, L, U, schedule, machine, root,
                 rank=None):
        super().__init__(inst, U)
        self.L = int(L)
        self.U = int(U)
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.root = root
        self.rank = rank

    def _leaf_ok(self, nd):
        inst = self.inst
        U = self.U
        if nd.children is not None:
            return False
        if nd.proof is None:
            return False
        if not nd.dead:
            if nd.L >= U:
                return False
            h = nd.L - 1
        else:
            if nd.L < U:
                return False
            h = nd.proof.h
            if h < U - 1:
                return False
        if nd.proof.h != h:
            return False
        if not nd.proof.audit_rdf():
            return False
        F = box_forbid(inst, h, nd.lo, nd.hi)
        return set(_proof_forbid(nd.proof)) <= set(F)

    def _tree_ok(self, nd):
        if nd.children is None:
            return self._leaf_ok(nd)
        if nd.split is None:
            return False
        i, mid = nd.split
        lo, hi = nd.lo, nd.hi
        if not (0 <= i < len(lo) and lo[i] <= mid < hi[i]):
            return False
        left, right = nd.children
        lhi = list(hi)
        lhi[i] = mid
        rlo = list(lo)
        rlo[i] = mid + 1
        if tuple(left.lo) != tuple(lo) or tuple(left.hi) != tuple(lhi):
            return False
        if tuple(right.lo) != tuple(rlo) or tuple(right.hi) != tuple(hi):
            return False
        return self._tree_ok(left) and self._tree_ok(right)

    def audit_rdf(self):
        try:
            inst = self.inst
            if self.schedule is None or self.machine is None:
                return False
            if cmax(inst, self.schedule) != self.U:
                return False
            if not check_schedule(inst, self.U, self.schedule,
                                  self.machine):
                return False
            if not _box_ok(inst, self.U, self.root.lo, self.root.hi):
                return False
            if not self._tree_ok(self.root):
                return False
            opens = [nd for nd in leaves(self.root)
                     if not nd.dead and nd.L < self.U]
            L = min([nd.L for nd in opens], default=self.U)
            if L != self.L:
                return False
            if self.L > self.U:
                return False
            if self.L == self.U:
                # Every leaf must prove NO(U-1), either directly or via
                # monotonicity from a stronger horizon.
                for nd in leaves(self.root):
                    if nd.proof is None or nd.proof.h < self.U - 1:
                        return False
            return True
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


# --------------------------------------------------------------- policies
def choose_h(policy, L, U, phase, eps):
    if U - L <= 0:
        return L
    if policy == 'lower-first':
        return L if phase == 0 else (L + U) // 2
    if policy == 'lower-always':
        return L
    if policy == 'binary':
        return (L + U) // 2
    if policy == 'upper-first':
        return U - 1
    if policy == 'two-sided':
        if phase == 0:
            return L
        if phase == 1:
            return U - 1
        return (L + U) // 2
    if policy == 'pact':
        return L if U - L <= 4 else (L + U) // 2
    if policy == 'geometric':
        return min(U - 1, int(math.floor((1.0 + eps) * L)))
    raise ValueError('unknown policy %r' % (policy,))


# ------------------------------------------------------------------ main
def run_rafa(inst, known, name, idx, policy='geometric', eps=0.1,
             cap=0, max_probes=256, max_leaves=512, mode='weak',
             audit_states=False, timelimit=None, stop_at_approx=False):
    t0 = time.time()
    st = init_state(inst, mode=mode)
    if st is None:
        return dict(name=name, idx=idx, known=known, policy=policy,
                    ok=False, error='init')
    root = st['root']
    U = st['U']
    sched, mach = st['schedule'], st['machine']
    L0, U0 = st['L0'], st['U0']
    co = st['co']
    ledger = RankLedger()
    ledger.check(root, U, 'init')

    probes = 0
    lp = 0
    cert_lp = 0
    nodes = 0
    splits = 0
    yes = no = unknown = 0
    phase = 0
    state_audits = 0
    state_fail = 0
    approx_steps = None
    exact_steps = None
    best_ratio = None
    stop_reason = 'budget'

    def current_L():
        return global_L(root, U)

    def cleanup_dead():
        for nd in leaves(root):
            if nd.children is None and not nd.dead and nd.L >= U:
                nd.dead = True

    def audit_now():
        nonlocal state_audits, state_fail
        if not audit_states:
            return
        L = current_L()
        cert = FrontierCertificate(inst, L, U, sched, mach, root)
        state_audits += 1
        if not cert.audit_rdf():
            state_fail += 1

    def split_node(f, i, mid):
        if not (f.lo[i] <= mid < f.hi[i]):
            return False
        left_hi = list(f.hi)
        left_hi[i] = mid
        right_lo = list(f.lo)
        right_lo[i] = mid + 1
        left = Node(f.lo, left_hi, f.L, f.proof)
        right = Node(right_lo, f.hi, f.L, f.proof)
        f.children = (left, right)
        f.split = (i, mid)
        return True

    audit_now()
    while probes < max_probes:
        if timelimit is not None and time.time() - t0 > timelimit:
            stop_reason = 'time'
            break
        L = current_L()
        if L >= U:
            stop_reason = 'exact'
            break
        if L > 0:
            ratio = U / L
            best_ratio = ratio if best_ratio is None else min(best_ratio,
                                                             ratio)
            if approx_steps is None and ratio <= 1.0 + eps + 1e-12:
                approx_steps = probes
            if stop_at_approx and ratio <= 1.0 + eps + 1e-12:
                stop_reason = 'approx'
                break
        if len([1 for nd in leaves(root) if nd.children is None and
                not nd.dead]) > max_leaves:
            stop_reason = 'leaves'
            break
        opens = open_leaves(root, U)
        if not opens:
            stop_reason = 'exact'
            break
        # best-first: smallest local lower bound, largest box on ties
        f = min(opens, key=lambda nd: (nd.L, -nd.width(), id(nd)))
        Lf = f.L
        h = choose_h(policy, L, U, phase, eps)
        if h < Lf:
            h = Lf
        if h >= U:
            h = U - 1
        phase += 1
        F = box_forbid(inst, h, f.lo, f.hi)
        r = pact_decide(inst, h, depthcap=cap, nodecap=None,
                        forbid0=F)
        probes += 1
        lp += r.get('lp_solves', 0)
        cert_lp += r.get('cert_lp', 0)
        nodes += r.get('nodes', 0)
        changed = False
        if r['verdict'] is False:
            no += 1
            proof = r['proof']
            if proof is None or proof.h != h:
                stop_reason = 'bad-no'
                break
            f.L = h + 1
            f.proof = proof
            if f.L >= U:
                f.dead = True
                changed = True
                ledger.check(root, U, 'close-no')
            else:
                changed = True
                ledger.check(root, U, 'lift')
        elif r['verdict'] is True:
            yes += 1
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                sched, mach = list(s2), list(m2)
                changed = True
                cleanup_dead()
                ledger.check(root, U, 'drop-U')
            else:
                unknown += 1
                changed = True
        else:
            unknown += 1
            sp = choose_split(inst, h, f.lo, f.hi)
            handled = False
            if sp[0] == 'no':
                rr = pact_decide(inst, h, depthcap=None, nodecap=None,
                                 forbid0=F)
                lp += rr.get('lp_solves', 0)
                cert_lp += rr.get('cert_lp', 0)
                nodes += rr.get('nodes', 0)
                if rr['verdict'] is False and rr['proof'] is not None:
                    f.L = h + 1
                    f.proof = rr['proof']
                    if f.L >= U:
                        f.dead = True
                        ledger.check(root, U, 'close-no')
                    else:
                        ledger.check(root, U, 'lift')
                    changed = handled = True
                elif rr['verdict'] is True:
                    c2 = cmax(inst, rr['schedule'])
                    if c2 < U and check_schedule(inst, c2,
                                                 rr['schedule'],
                                                 rr['machine']):
                        U = c2
                        sched, mach = list(rr['schedule']), \
                            list(rr['machine'])
                        cleanup_dead()
                        ledger.check(root, U, 'drop-U')
                        changed = handled = True
            elif sp[0] == 'yes':
                s2, m2 = sp[1]
                c2 = cmax(inst, s2)
                if c2 < U and check_schedule(inst, c2, s2, m2):
                    U = c2
                    sched, mach = list(s2), list(m2)
                    cleanup_dead()
                    ledger.check(root, U, 'drop-U')
                    changed = handled = True
            elif sp[0] == 'split':
                i, mid = sp[1]
                if split_node(f, i, mid):
                    splits += 1
                    changed = handled = True
                    ledger.check(root, U, 'split')
            if not handled:
                fb = arbitrary_split(inst, h, f.lo, f.hi)
                if fb is None:
                    stop_reason = 'unknown'
                    break
                i, mid = fb
                if not split_node(f, i, mid):
                    stop_reason = 'bad-split'
                    break
                splits += 1
                changed = True
                ledger.check(root, U, 'split')
        if not changed:
            stop_reason = 'no-progress'
            break
        audit_now()

    L = current_L()
    exact = bool(L == U)
    if exact:
        exact_steps = probes
    if exact and approx_steps is None:
        approx_steps = probes
    if L > 0:
        ratio = U / L
        best_ratio = ratio if best_ratio is None else min(best_ratio, ratio)
    cert = FrontierCertificate(inst, L, U, sched, mach, root)
    final_ok = bool(cert.audit_rdf())
    dt = time.time() - t0
    return dict(
        name=name, idx=idx, known=known, policy=policy, eps=eps,
        mode=mode, cap=cap,
        L=L, U=U, L0=L0, U0=U0, known_ok=bool(U == known and L == known),
        certified=bool(exact and final_ok),
        audit=final_ok, proof_kind=cert.kind,
        exact=exact, approx=(L > 0 and U / L <= 1.0 + eps + 1e-12),
        ratio=(U / L if L > 0 else None),
        probes=probes, lp=lp, cert_lp=cert_lp, nodes=nodes,
        yes=yes, no=no, unknown=unknown, splits=splits,
        leaves=len(leaves(root)), max_leaves=len(leaves(root)),
        max_open=len(open_leaves(root, U)),
        rank_steps=ledger.steps, rank_fail=ledger.fail,
        rank_kinds=dict(ledger.kinds), rank_bad=ledger.bad,
        state_audits=state_audits, state_fail=state_fail,
        approx_steps=approx_steps, exact_steps=exact_steps,
        stop_reason=stop_reason,
        t=round(dt, 4),
        ok=bool(exact and U == known and final_ok and ledger.fail == 0
                and state_fail == 0),
    )


def corpora():
    from icf import corpora as inner
    for tag, name, idx, inst, known in inner():
        yield tag, name, idx, inst, known
