"""v9.1 IPF-PACT: in-place frontier search with a streaming script certificate.

The v9.0 ICF state is

    C = (L, U, s, m, pi),   pi : NO(L-1),  Cmax(s) = U,  L <= U.

IPF keeps this state and adds a *space-bounded* way to grow the frontier.
Instead of materialising the partition tree, it walks it depth-first with

  * one mutable forbidden-time bitmap over n x (U0) bits,
  * an undo trail, and
  * a stack of split frames (i, mid, phase, inherited L, inherited proof).

The live search therefore uses O(depth * (n U0 + |pi|)) space, not
O(leaves * (n U0 + |pi|)).  The frontier invariant is represented by the
current path: every pending sibling on the stack is an open leaf with a
proof at its local L-1; closed subtrees have been popped.  The same path
is also a valid partial certificate at every moment.

The final NO(U-1) proof is a *script*:

    ('S', i, mid)            split the current box on start time of job i
    ('T',)                   switch from the <= mid child to the > mid child
    ('X',)                   close the split
    ('L', h, proof_or_cert)  closed leaf, h >= U-1
    ('EM', U-1, job)         closed empty leaf (job has no allowed start)

The verifier replays the script with the same mutable box and a stack of
split frames.  It never stores a forbidden set per leaf and never stores
a partition tree.  Its working memory is O(depth * n U0) plus the leaf
proofs, and it checks the tree shape with a small state machine.

The search strategy is lower-first: probe each leaf first at its local L,
then binary-search the remaining interval.  An UNKNOWN from a budgeted
node oracle causes a REFINE (split); NO lifts the local bound; YES lowers
the global U and can prune leaves whose local L is already >= U.
"""
import sys
import time

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from sage import _domain
from cert import verify
from rdf import check_schedule
from po import heads_tails
from pact import PACT, pact_decide
from icf import cmax, _proof_forbid, CertLeafProof


# --------------------------------------------------------------- trail box
class TrailBox:
    """A mutable forbidden-time bitmap with an undo trail.

    Bits are indexed by i * (H0+1) + t.  A split at (i, mid) forbids
    *all* times in [0, H0] on one side, not just the times allowed at the
    current horizon.  This makes the split horizon-independent: the same
    two children partition the parent's allowed set at every target
    H <= H0.
    """

    __slots__ = ('n', 'H0', 'W', 'bits', 'trail')

    def __init__(self, n, H0):
        self.n = int(n)
        self.H0 = int(H0)
        self.W = self.H0 + 1
        self.bits = bytearray(self.n * self.W)
        self.trail = []

    def mark(self):
        return len(self.trail)

    def add(self, i, lo, hi):
        lo = max(0, int(lo))
        hi = min(self.H0, int(hi))
        if lo > hi:
            return
        base = i * self.W
        bits = self.bits
        trail = self.trail
        for t in range(lo, hi + 1):
            idx = base + t
            if not bits[idx]:
                bits[idx] = 1
                trail.append(idx)

    def undo(self, mark):
        bits = self.bits
        trail = self.trail
        while len(trail) > mark:
            idx = trail.pop()
            bits[idx] = 0

    def has(self, i, t):
        return bool(self.bits[i * self.W + t])

    def size(self):
        return len(self.trail)

    def as_frozenset(self):
        W = self.W
        return frozenset((idx // W, idx % W) for idx in self.trail)


def domain_times(inst, h, i):
    lo, hi = _domain(inst, h, i)
    return range(max(0, lo), hi + 1)


def allowed_times(inst, h, i, box):
    lo, hi = _domain(inst, h, i)
    lo = max(0, lo)
    base = i * box.W
    bits = box.bits
    return [t for t in range(lo, hi + 1) if not bits[base + t]]


def empty_job(inst, h, box):
    for i in range(inst['n']):
        if not allowed_times(inst, h, i, box):
            return i
    return None


def cheap_lb(inst):
    """Critical path, average load, and eligibility-restricted load."""
    n, m, p, elig = inst['n'], inst['m'], inst['p'], inst['elig']
    est, q = heads_tails(inst, 0, [0] * n)
    lb = max(est[i] + p[i] + q[i] for i in range(n))
    lb = max(lb, (sum(p) + m - 1) // m)
    if m <= 8:
        for mask in range(1, 1 << m):
            cnt = bin(mask).count('1')
            load = sum(p[i] for i in range(n)
                       if all((mask >> k) & 1 for k in elig[i]))
            lb = max(lb, (load + cnt - 1) // cnt)
    return int(lb)


def choose_h(policy, L, U, first):
    if U - L <= 0:
        return L
    if policy == 'lower-first':
        h = L if first else (L + U) // 2
    elif policy == 'binary':
        h = (L + U) // 2
    elif policy == 'upper-first':
        h = U - 1
    elif policy == 'pact':
        h = L if U - L <= 4 else (L + U) // 2
    else:
        raise ValueError('unknown policy %r' % (policy,))
    if h >= U:
        h = U - 1
    if h < L:
        h = L
    return h


# ------------------------------------------------------------- certificate
class ScriptCertificate(Proof):
    """A partition-tree certificate stored as a flat DFS script.

    The script stores splits (i, mid) and leaf witnesses only.  The
    verifier reconstructs every box from the path.  In particular, no
    forbidden set is stored per node and no tree object is materialised.
    """

    kind = 'ipf-script'

    def __init__(self, inst, H0, target, events, schedule, machine):
        super().__init__(inst, target)
        self.H0 = int(H0)
        self.target = int(target)
        self.events = list(events)
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.L = None
        self.n_open = None
        self.n_closed = None

    def _leaf_ok(self, proof, h, F):
        if hasattr(proof, 'audit_rdf'):
            if proof.h != h:
                return False
            if not proof.audit_rdf():
                return False
            return set(_proof_forbid(proof)) <= set(F)
        if not isinstance(proof, dict):
            return False
        return bool(verify(self.inst, h, proof, forbid=F))

    def _schedule_ok(self):
        if self.schedule is None or self.machine is None:
            return False
        U = self.target + 1
        if cmax(self.inst, self.schedule) != U:
            return False
        return bool(check_schedule(self.inst, U, self.schedule,
                                   self.machine))

    def audit_rdf(self, partial=False):
        try:
            n, H0, target = self.inst['n'], self.H0, self.target
            box = TrailBox(n, H0)
            stack = []
            mode = 'live'
            Lmin = 10 ** 18
            n_open = 0
            n_closed = 0
            for ev in self.events:
                tag = ev[0]
                if tag == 'S':
                    if mode != 'live':
                        return False
                    _, i, mid = ev
                    if not (0 <= i < n and 0 <= mid < H0):
                        return False
                    mark = box.mark()
                    box.add(i, mid + 1, H0)
                    stack.append([i, mid, mark, 'lo'])
                    mode = 'live'
                elif tag == 'T':
                    if mode != 'done' or not stack or stack[-1][3] != 'lo':
                        return False
                    fr = stack[-1]
                    box.undo(fr[2])
                    box.add(fr[0], 0, fr[1])
                    fr[3] = 'hi'
                    mode = 'live'
                elif tag == 'X':
                    if mode != 'done' or not stack or stack[-1][3] != 'hi':
                        return False
                    fr = stack.pop()
                    box.undo(fr[2])
                    mode = 'done'
                elif tag == 'EM':
                    if mode != 'live':
                        return False
                    _, h, job = ev
                    if h != target:
                        return False
                    F = box.as_frozenset()
                    if any((job, t) not in F
                           for t in domain_times(self.inst, h, job)):
                        return False
                    Lmin = min(Lmin, h + 1)
                    n_closed += 1
                    mode = 'done'
                elif tag in ('L', 'O'):
                    if mode != 'live':
                        return False
                    _, h, proof = ev
                    if tag == 'L' and h < target:
                        return False
                    if tag == 'O' and h >= target:
                        return False
                    F = box.as_frozenset()
                    if not self._leaf_ok(proof, h, F):
                        return False
                    Lmin = min(Lmin, h + 1)
                    if tag == 'O':
                        n_open += 1
                    else:
                        n_closed += 1
                    mode = 'done'
                else:
                    return False
            if mode != 'done' or stack:
                return False
            if Lmin > target + 1:
                return False
            if not partial and (n_open != 0 or Lmin != target + 1):
                return False
            if not self._schedule_ok():
                return False
            self.L = int(Lmin)
            self.n_open = n_open
            self.n_closed = n_closed
            return True
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class _Stop(Exception):
    pass


# ------------------------------------------------------------------- solver
class IPFSolver:
    def __init__(self, inst, L, U, schedule, machine, proof, H0,
                 policy='lower-first', nodecap=1, max_probes=4096,
                 audit_every=False, debug=False):
        self.inst = inst
        self.L0 = int(L)
        self.U0 = int(U)
        self.U = int(U)
        self.schedule = list(schedule)
        self.machine = list(machine)
        self.root_proof = proof
        self.H0 = int(H0)
        self.policy = policy
        self.nodecap = nodecap
        self.max_probes = int(max_probes)
        self.audit_every = bool(audit_every)
        self.debug = bool(debug)

        self.box = TrailBox(inst['n'], self.H0)
        self.frames = []
        self.events = []
        self.probes = 0
        self.lp = 0
        self.nodes = 0
        self.cert_lp = 0
        self.splits = 0
        self.closes = 0
        self.unknown = 0
        self.max_depth = 0
        self.max_open = 1
        self.max_pairs = 0
        self.max_trail = 0
        self.partial_checks = 0
        self.partial_fail = 0
        self.cur_L = self.L0
        self.cur_proof = proof
        self.stop_reason = None

    # -- state / metrics -------------------------------------------------
    def _update_metrics(self):
        self.max_depth = max(self.max_depth, len(self.frames))
        self.max_trail = max(self.max_trail, self.box.size())
        open_leaves = 1 + sum(1 for fr in self.frames
                              if fr['phase'] == 'lo')
        pairs = self.box.size()
        for fr in self.frames:
            if fr['phase'] == 'lo':
                pairs += fr['sibling_size']
        self.max_open = max(self.max_open, open_leaves)
        self.max_pairs = max(self.max_pairs, pairs)

    def _audit(self):
        if not self.audit_every:
            return
        ev = self.snapshot_events()
        cert = ScriptCertificate(self.inst, self.H0, self.U - 1, ev,
                                 self.schedule, self.machine)
        self.partial_checks += 1
        if not cert.audit_rdf(partial=True):
            self.partial_fail += 1
            if self.debug:
                print('PARTIAL AUDIT FAIL at L', self.cur_L, 'U', self.U,
                      'events', len(ev))

    def snapshot_events(self):
        """Serialize the current frontier (path plus pending siblings)."""
        if self.cur_L >= self.U:
            cur = [('L', self.cur_L - 1, self.cur_proof)]
        else:
            H = self.U - 1
            job = empty_job(self.inst, H, self.box)
            if job is not None:
                cur = [('EM', H, job)]
            else:
                cur = [('O', self.cur_L - 1, self.cur_proof)]
        for fr in reversed(self.frames):
            if fr['phase'] == 'lo':
                sL = fr['child_L']
                sp = fr['proof']
                if sL >= self.U:
                    sib = [('L', sL - 1, sp)]
                else:
                    sib = [('O', sL - 1, sp)]
                cur = ([('S', fr['i'], fr['mid'])] + cur +
                       [('T',)] + sib + [('X',)])
            else:
                lo = list(self.events[fr['lo_start']:fr['lo_end']])
                cur = ([('S', fr['i'], fr['mid'])] + lo +
                       [('T',)] + cur + [('X',)])
        return cur

    # -- helpers ---------------------------------------------------------
    def _empty_job(self, H):
        return empty_job(self.inst, H, self.box)

    def _allowed(self, H, i):
        return allowed_times(self.inst, H, i, self.box)

    def _choose_split(self, r, H):
        for bj in r.get('branch_jobs') or []:
            i, mid = int(bj[0]), int(bj[1])
            times = self._allowed(H, i)
            if times and any(t > mid for t in times) \
                    and any(t <= mid for t in times):
                return i, mid
        best = None
        for i in range(self.inst['n']):
            times = self._allowed(H, i)
            if len(times) >= 2:
                mid = times[len(times) // 2 - 1]
                if best is None or len(times) > best[0]:
                    best = (len(times), i, mid)
        if best is None:
            return None
        return best[1], best[2]

    def _probe(self, h):
        F = self.box.as_frozenset()
        r = pact_decide(self.inst, h, depthcap=None, nodecap=self.nodecap,
                        forbid0=F)
        self.probes += 1
        self.lp += r.get('lp_solves', 0)
        self.nodes += r.get('nodes', 0)
        self.cert_lp += r.get('cert_lp', 0)
        return r

    def _accept_yes(self, r):
        s, m = r['schedule'], r['machine']
        c = cmax(self.inst, s)
        if c < self.U and check_schedule(self.inst, c, s, m):
            self.U = c
            self.schedule = list(s)
            self.machine = list(m)
            return True
        return False

    # -- DFS -------------------------------------------------------------
    def _dfs(self, L, proof):
        first = True
        while True:
            self.cur_L = L
            self.cur_proof = proof
            self._update_metrics()
            self._audit()
            if L >= self.U:
                self.events.append(('L', L - 1, proof))
                self.closes += 1
                return
            H = self.U - 1
            i = self._empty_job(H)
            if i is not None:
                self.events.append(('EM', H, i))
                self.closes += 1
                return
            if self.probes >= self.max_probes:
                self.stop_reason = 'probe-budget'
                raise _Stop()
            h = choose_h(self.policy, L, self.U, first)
            r = self._probe(h)
            first = False
            if r['verdict'] is False:
                L = h + 1
                proof = r['proof']
                if self.debug:
                    print('NO at', h, '-> L', L, 'U', self.U)
                continue
            if r['verdict'] is True:
                if self.debug:
                    print('YES at', h, 'cmax', cmax(self.inst,
                                                   r['schedule']),
                          'U', self.U)
                self._accept_yes(r)
                continue
            self.unknown += 1
            pair = self._choose_split(r, H)
            if pair is None:
                # Last resort: let the complete oracle decide this box.
                r2 = pact_decide(self.inst, h, depthcap=None, nodecap=None,
                                 forbid0=self.box.as_frozenset())
                self.probes += 1
                self.lp += r2.get('lp_solves', 0)
                self.nodes += r2.get('nodes', 0)
                self.cert_lp += r2.get('cert_lp', 0)
                if r2['verdict'] is False:
                    L = h + 1
                    proof = r2['proof']
                    continue
                if r2['verdict'] is True:
                    self._accept_yes(r2)
                    continue
                self.stop_reason = 'unknown-no-split'
                raise _Stop()
            i, mid = pair
            mark = self.box.mark()
            parent_size = self.box.size()
            self.box.add(i, mid + 1, self.H0)
            new_hi = sum(1 for t in range(0, mid + 1)
                         if not self.box.bits[i * self.box.W + t])
            sibling_size = parent_size + new_hi
            fr = dict(i=i, mid=mid, mark=mark, phase='lo',
                      child_L=L, proof=proof,
                      lo_start=len(self.events), lo_end=None,
                      sibling_size=sibling_size)
            self.frames.append(fr)
            self.splits += 1
            self.events.append(('S', i, mid))
            self._update_metrics()
            self._dfs(L, proof)
            fr['lo_end'] = len(self.events)
            self.box.undo(mark)
            self.events.append(('T',))
            self.box.add(i, 0, mid)
            fr['phase'] = 'hi'
            self._dfs(L, proof)
            self.box.undo(mark)
            self.events.append(('X',))
            self.frames.pop()
            self._update_metrics()
            return

    def run(self):
        status = 'complete'
        try:
            self._dfs(self.L0, self.root_proof)
        except _Stop:
            status = 'partial'
        target = self.U - 1
        final = None
        final_ok = False
        if status == 'complete':
            final = ScriptCertificate(self.inst, self.H0, target,
                                      self.events, self.schedule,
                                      self.machine)
            final_ok = bool(final.audit_rdf())
        ev = self.snapshot_events() if status != 'complete' else self.events
        part = ScriptCertificate(self.inst, self.H0, target, ev,
                                 self.schedule, self.machine)
        part_ok = bool(part.audit_rdf(partial=True))
        Lfinal = part.L if part.L is not None else None
        return dict(
            status=status, L0=self.L0, U0=self.U0, L=Lfinal, U=self.U,
            opt=self.U, certified=bool(final_ok and status == 'complete'),
            audit=final_ok, partial_final=part_ok,
            probes=self.probes, lp=self.lp, nodes=self.nodes,
            cert_lp=self.cert_lp, splits=self.splits, closes=self.closes,
            unknown=self.unknown, events=len(self.events),
            max_depth=self.max_depth, max_open=self.max_open,
            max_pairs=self.max_pairs, max_trail=self.max_trail,
            partial_checks=self.partial_checks,
            partial_fail=self.partial_fail,
            stop_reason=self.stop_reason,
            schedule=self.schedule, machine=self.machine,
            n_open=(part.n_open if part.n_open is not None else None),
            cert_h=(self.U - 1 if final_ok else None),
        )


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


def weak_initial(inst, U=None, schedule=None, machine=None):
    """Cheap valid L plus a feasible U, with replayable witnesses."""
    n = inst['n']
    L = cheap_lb(inst)
    r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
    if r['verdict'] is not False:
        raise RuntimeError('cheap lower bound is not NO: %r'
                           % (r['verdict'],))
    proof = r['proof']
    if U is None or schedule is None or machine is None:
        co = PACT(inst, pact_mode='complete', use_ga=False)
        lb, ub, sched, mach = co.initial_bounds()
        if ub is None:
            raise RuntimeError('no initial upper bound')
        U, schedule, machine = int(ub), list(sched), list(mach)
    if not check_schedule(inst, U, schedule, machine):
        raise RuntimeError('bad initial schedule')
    return L, int(U), list(schedule), list(machine), proof


def run_ipf(inst, known, name, idx, policy='lower-first', nodecap=1,
            max_probes=4096, initial=None, weak=False,
            audit_every=False, debug=False):
    t0 = time.time()
    try:
        if initial is None:
            if weak:
                L, U, s, m, proof = weak_initial(inst)
            else:
                L, U, s, m, proof = pact_initial(inst)
        else:
            L, U, s, m, proof = initial
            L, U = int(L), int(U)
            s, m = list(s), list(m)
        if L > U:
            raise RuntimeError('bad bracket')
        H0 = U - 1
        solver = IPFSolver(inst, L, U, s, m, proof, H0,
                           policy=policy, nodecap=nodecap,
                           max_probes=max_probes,
                           audit_every=audit_every, debug=debug)
        out = solver.run()
        out.update(name=name, idx=idx, known=known, policy=policy,
                   nodecap=nodecap, weak=weak,
                   t=round(time.time() - t0, 4))
        out['ok'] = bool(out['certified'] and out['U'] == known
                         and out['partial_fail'] == 0
                         and out['partial_final'])
        return out
    except Exception as e:
        return dict(name=name, idx=idx, known=known, policy=policy,
                    nodecap=nodecap, weak=weak, ok=False,
                    certified=False, error=repr(e),
                    t=round(time.time() - t0, 4))


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
