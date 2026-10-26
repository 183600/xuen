"""v10.0 LV-GF: Las Vegas geometric frontier.

LV-GF keeps the v9.0 ICF invariant

    L <= OPT <= U,   pi : NO(L-1 | F),   Cmax(s)=U,

but makes the frontier live and adds two ideas from the round's
inspiration words:

  * a geometric horizon ladder H_k = floor(H_{k-1} (1+eps)) for the
    FPTAS-shaped anytime schedule: a geometric probe either lowers U to
    at most (1+eps) L_f or raises L_f by a factor (1+eps);
  * a Las Vegas arm: LP-guided randomized list schedules are sampled at
    a feasible horizon; only schedules accepted by check_schedule can
    lower U, and a failed sampling round falls back to the exact
    three-valued decision procedure.  Randomization changes work, never
    certificates.

The frontier itself is a certified interval heap: open boxes are kept in
a lazy binary heap keyed by (L_f, -width), splits inherit the parent's
NO proof, and every state is auditable as a partial frontier
certificate.  A small successor structure skips ladder rungs already
below the current local lower bound.

The implementation deliberately exposes the trusted kernel: only
`pact_decide` emits NO proofs, only `check_schedule` accepts schedules,
and `FrontierCertificate.audit_rdf` re-checks the tree.  The sampler and
the split coin are untrusted search heuristics.
"""
import sys
import time
import math
import random
import heapq
import bisect
import collections

sys.path[:0] = ['exp/v10d', 'exp/v9i', 'exp/v9y', 'exp/v9m', 'exp/v8u',
                'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8j', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from rafa import (Node, leaves, open_leaves, global_L, rank_of,
                  RankLedger, FrontierCertificate, init_state,
                  arbitrary_split)
from sage import _elig_aware, _domain
from sdecc import SDLP
from po import heads_tails
from prism import box_forbid
from icf import cmax
from cert import verify
from rdf import check_schedule
from pact import pact_decide
from karst import karst_sample


# --------------------------------------------------------------- ladder
class RungLadder:
    """Geometric integer horizons, plus a bisect successor query.

    Rungs are strictly increasing and satisfy H_{k+1} >= (1+eps) H_k
    whenever the +1 guard does not dominate.  `next_ge(x)` is the first
    rung >= x; it is the data-structure query used by every probe.
    """

    def __init__(self, lo, hi, eps=0.1):
        lo = max(1, int(lo))
        hi = max(lo, int(hi))
        eps = max(1e-3, float(eps))
        xs = [lo]
        x = lo
        guard = 0
        while x < hi and guard < 100000:
            y = max(x + 1, int(math.floor(x * (1.0 + eps))))
            if y <= x:
                y = x + 1
            xs.append(y)
            x = y
            guard += 1
        self.rungs = xs
        self.eps = eps

    def next_ge(self, x):
        j = bisect.bisect_left(self.rungs, int(x))
        if j >= len(self.rungs):
            return self.rungs[-1]
        return self.rungs[j]

    def index(self, x):
        return bisect.bisect_left(self.rungs, int(x))


class FrontierHeap:
    """Lazy heap over open leaves, optionally with randomized priorities.

    Entries are invalidated by comparing the stored L with the live L,
    and by the node's dead/children flags.  This gives O(log K) insert
    and amortized O(log K) extract without a decrease-key operation.
    """

    def __init__(self, randomized=False, seed=0):
        self.h = []
        self.serial = 0
        self.randomized = bool(randomized)
        self.rng = random.Random(seed)

    def push(self, nd):
        noise = self.rng.expovariate(1.0) if self.randomized else 0.0
        prio = nd.L + noise
        entry = (prio, nd.L, -nd.width(), self.serial, nd)
        self.serial += 1
        heapq.heappush(self.h, entry)

    def pop(self, U):
        while self.h:
            prio, L_at_push, negw, ser, nd = self.h[0]
            if (nd.children is not None or nd.dead or nd.L >= U
                    or nd.L != L_at_push):
                heapq.heappop(self.h)
                continue
            heapq.heappop(self.h)
            return nd
        return None

    def __len__(self):
        return len(self.h)


# --------------------------------------------------------------- helpers
def _make_lp(inst, h, F):
    est, q = heads_tails(inst, 0, [0] * inst['n'])
    lp = SDLP(inst, h, est, q, use_dom=True,
              elig_aware=_elig_aware(inst), forbid=F)
    if lp.N == 0:
        return lp, None
    res = lp.solve()
    return lp, res


def _frac_jobs(lp, res):
    """Per-job fractional start-time distributions at a feasible LP."""
    n = lp.inst['n']
    out = []
    for i in range(n):
        dist = []
        mass = 0.0
        frac = 0.0
        for c, key in enumerate(lp.cols):
            if key[0] != i:
                continue
            v = res.x[c]
            if v > 1e-9:
                dist.append((key[-1], v))
                mass += v
                if 1e-7 < v < 1 - 1e-7:
                    frac += v
        if len(dist) > 1 and frac > 1e-7:
            out.append((i, dist, mass, frac))
    return out


def _decoded(lp, res):
    """Return (starts, machine) if the LP vertex is integral."""
    starts = [None] * lp.inst['n']
    machs = [None] * lp.inst['n']
    elig = lp.elig_aware
    for c, key in enumerate(lp.cols):
        if res.x[c] > 1 - 1e-7:
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
        machs = _assign_machines(lp.inst, starts)
        if machs is None:
            return None
    if check_schedule(lp.inst, max(starts[i] + lp.inst['p'][i]
                                   for i in range(lp.inst['n'])),
                      starts, machs):
        return starts, machs
    return None


def _split_from_lp(lp, res, randomized, rng, quantile=0.5):
    """Choose a fractional split (i, mid) from the current LP vertex.

    This is the Las Vegas choice: every returned split is a valid
    partition of the box; randomness only changes the shape of the tree.
    """
    cand = _frac_jobs(lp, res)
    if not cand:
        return None
    if randomized:
        weights = [c[3] for c in cand]
        total = sum(weights)
        u = rng.random() * total
        acc = 0.0
        pick = cand[-1]
        for c in cand:
            acc += c[3]
            if acc >= u:
                pick = c
                break
        q = quantile + rng.uniform(-0.2, 0.2)
    else:
        pick = max(cand, key=lambda c: (c[2], c[3], -c[0]))
        q = quantile
    i, dist, mass, _ = pick
    dist = sorted(dist)
    total = sum(v for _, v in dist)
    acc = 0.0
    mid = dist[0][0]
    for t, v in dist:
        acc += v
        if acc >= max(0.05, min(0.95, q)) * total:
            mid = t
            break
    times = [t for t, _ in dist]
    lo_t = [t for t in times if t > mid]
    hi_t = [t for t in times if t <= mid]
    if not lo_t or not hi_t:
        mid = times[len(times) // 2 - 1]
    if not any(t > mid for t in times) or not any(t <= mid for t in times):
        return None
    return i, mid


def _global_L(root, U):
    return global_L(root, U)


# ------------------------------------------------------------------ main
def run_lvgf(inst, known, name, idx, eps=0.1, cap=0, mode='weak',
             lv=True, lv_budgets=(8, 16, 32), randomized_split=False,
             randomized_leaf=False, seed=20261026, max_probes=512,
             max_leaves=512, audit_every=1, timelimit=None,
             hybrid_binary=True):
    """Run LV-GF and return a benchmark row.

    cap=None means complete pact_decide.  cap=k uses a depth cap and
    turns UNKNOWN leaves into splits.  lv=False ablates the Las Vegas
    sampler.  randomized_split=False uses deterministic LP-mass splits.
    """
    t0 = time.time()
    st = init_state(inst, mode=mode)
    if st is None:
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='init', t=0.0)
    root = st['root']
    U = st['U']
    sched, mach = st['schedule'], st['machine']
    L0, U0 = st['L0'], st['U0']
    co = st['co']
    # PACT sometimes returns an upper bound that is one or more units above
    # the Cmax of the accompanying schedule.  The ICF invariant needs
    # Cmax(s)=U, so tighten U to the schedule's actual Cmax.
    if sched is not None and mach is not None:
        c0 = cmax(inst, sched)
        if c0 < U and check_schedule(inst, c0, sched, mach):
            U = c0
            U0 = c0
            if root.L >= U:
                root.dead = True

    heap = FrontierHeap(randomized=randomized_leaf, seed=seed + 17)
    heap.push(root)
    ladder = RungLadder(L0, U0, eps)
    ledger = RankLedger()
    ledger.check(root, U, 'init')
    rng = random.Random(seed + 104729)

    probes = 0
    lp_solves = 0
    cert_lp = 0
    nodes = 0
    splits = 0
    yes = no = unknown = 0
    lv_trials = 0
    lv_hits = 0
    lv_global_hits = 0
    state_audits = 0
    state_fail = 0
    stop_reason = 'budget'
    approx_steps = None
    best_ratio = None

    def audit_now():
        nonlocal state_audits, state_fail
        if audit_every <= 0:
            return
        if state_audits % audit_every != 0:
            state_audits += 1
            return
        L = _global_L(root, U)
        cert = FrontierCertificate(inst, L, U, sched, mach, root)
        state_audits += 1
        if not cert.audit_rdf():
            state_fail += 1

    def cleanup_dead():
        for nd in leaves(root):
            if nd.children is None and not nd.dead and nd.L >= U:
                nd.dead = True

    def split_at(f, i, mid):
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
        heap.push(left)
        heap.push(right)
        return True

    audit_now()
    while probes < max_probes:
        if timelimit is not None and time.time() - t0 > timelimit:
            stop_reason = 'time'
            break
        L = _global_L(root, U)
        if L >= U:
            stop_reason = 'exact'
            break
        if len([nd for nd in leaves(root)
                if nd.children is None and not nd.dead]) > max_leaves:
            stop_reason = 'leaves'
            break
        if L > 0:
            ratio = U / L
            best_ratio = ratio if best_ratio is None else min(best_ratio,
                                                             ratio)
            if approx_steps is None and ratio <= 1.0 + eps + 1e-12:
                approx_steps = probes

        f = heap.pop(U)
        if f is None:
            stop_reason = 'heap-empty'
            break
        Lf = f.L
        # Geometric (FPTAS-shaped) horizon: anchored at the current
        # local lower bound, so a NO raises L_f by at least a factor
        # (1+eps) unless the binary fallback is active.
        h = max(Lf + 1, int(math.floor(Lf * (1.0 + eps))))
        if hybrid_binary and (h >= U or U - Lf <= 4):
            h = (Lf + U) // 2
        h = max(Lf, min(U - 1, h))
        F = box_forbid(inst, h, f.lo, f.hi)
        lp, res = _make_lp(inst, h, F)
        lp_solves += 1
        feasible_lp = res is not None and res.status == 0

        # ---- Las Vegas arm ------------------------------------------------
        if lv and feasible_lp:
            got = karst_sample(inst, h, lp, res,
                               budgets=tuple(lv_budgets),
                               seed0=seed + 1009 * probes + 97 * h)
            lv_trials += got['trials']
            if got['schedule'] is not None:
                s2, m2 = got['schedule'], got['machine']
                c2 = cmax(inst, s2)
                if c2 < U and check_schedule(inst, c2, s2, m2):
                    U = c2
                    sched, mach = list(s2), list(m2)
                    cleanup_dead()
                    ledger.check(root, U, 'lv-drop-U')
                    lv_global_hits += 1
                    if all((i, s2[i]) not in F for i in range(inst['n'])):
                        lv_hits += 1
                        yes += 1
                    probes += 1
                    audit_now()
                    if Lf < U and not f.dead and f.children is None:
                        heap.push(f)
                    continue

        # ---- exact three-valued decision ---------------------------------
        reuse = res is not None and res.status in (0, 2) and lp.N > 0
        r = pact_decide(inst, h, depthcap=cap, nodecap=None,
                        forbid0=F,
                        root_lp=lp if reuse else None,
                        root_res=res if reuse else None)
        probes += 1
        lp_solves += r.get('lp_solves', 0)
        cert_lp += r.get('cert_lp', 0)
        nodes += r.get('nodes', 0)

        changed = False
        if r['verdict'] is False:
            proof = r['proof']
            if proof is None or proof.h != h:
                stop_reason = 'bad-no'
                break
            f.L = h + 1
            f.proof = proof
            no += 1
            if f.L >= U:
                f.dead = True
                ledger.check(root, U, 'close-no')
            else:
                ledger.check(root, U, 'lift')
                heap.push(f)
            changed = True
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                sched, mach = list(s2), list(m2)
                cleanup_dead()
                ledger.check(root, U, 'drop-U')
                yes += 1
                changed = True
                if Lf < U and not f.dead and f.children is None:
                    heap.push(f)
            else:
                unknown += 1
        else:
            unknown += 1

        if not changed:
            # UNKNOWN, a non-improving YES, or a probe that changed
            # nothing: split the box.  If the LP is integral but no
            # schedule was accepted, fall back to an arbitrary split.
            sp = _split_from_lp(lp, res, randomized_split, rng) \
                if feasible_lp else None
            if sp is None:
                sp = arbitrary_split(inst, h, f.lo, f.hi)
            if sp is None:
                stop_reason = 'no-split'
                break
            i, mid = sp
            if not split_at(f, i, mid):
                stop_reason = 'bad-split'
                break
            splits += 1
            ledger.check(root, U, 'split')
        audit_now()

    L = _global_L(root, U)
    exact = bool(L == U)
    if exact and approx_steps is None:
        approx_steps = probes
    if L > 0:
        ratio = U / L
        best_ratio = ratio if best_ratio is None else min(best_ratio, ratio)
    cert = FrontierCertificate(inst, L, U, sched, mach, root)
    final_ok = bool(cert.audit_rdf())
    dt = time.time() - t0
    return dict(
        name=name, idx=idx, known=known, eps=eps, cap=cap, mode=mode,
        lv=lv, randomized_split=randomized_split,
        randomized_leaf=randomized_leaf, seed=seed,
        L=L, U=U, L0=L0, U0=U0, known_ok=bool(U == known and L == known),
        certified=bool(exact and final_ok), audit=final_ok,
        exact=exact, ratio=(U / L if L > 0 else None),
        probes=probes, lp=lp_solves, cert_lp=cert_lp, nodes=nodes,
        pin_lp=getattr(co, 'pin_lp', 0),
        total_lp=int(lp_solves + cert_lp + getattr(co, 'pin_lp', 0)),
        splits=splits, yes=yes, no=no, unknown=unknown,
        lv_trials=lv_trials, lv_hits=lv_hits,
        lv_global_hits=lv_global_hits,
        leaves=len(leaves(root)),
        max_open=len(open_leaves(root, U)),
        rank_steps=ledger.steps, rank_fail=ledger.fail,
        rank_kinds=dict(ledger.kinds), rank_bad=ledger.bad,
        state_audits=state_audits, state_fail=state_fail,
        approx_steps=approx_steps, best_ratio=best_ratio,
        stop_reason=stop_reason, t=round(dt, 4),
        ok=bool(exact and U == known and final_ok and ledger.fail == 0
                and state_fail == 0),
    )


def synthetic_corpus():
    import json
    d = json.load(open('exp/v9i/synthetic.json'))
    for r in d['rows']:
        yield ('synth', 'synth', r['seed'], r['inst'], r['opt'])


def corpora():
    from icf import corpora as inner
    for tag, name, idx, inst, known in inner():
        yield tag, name, idx, inst, known
