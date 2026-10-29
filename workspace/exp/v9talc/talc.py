"""TALC: typed affine low-space certificates for fixed-h scheduling.

A NO(h) proof is represented as a prefix-free event stream in DFS
preorder.  The forbidden set of a node is not stored; it is the box
implicitly determined by the split path.  A verifier replays the stream
with a trail (add / undo), so peak live forbidden cells are O(nT), not
O(nodes * nT).  The stream is typed by the usual partition-tree rule

    Leaf  : No(h, F)
    Split : No(h, F | {i > m}) x No(h, F | {i <= m}) -> No(h, F)

and the runtime kernel refuses to build a bracket unless both the lower
and the upper witness have the right type.
"""
import sys

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from sage import _domain
from cert import verify
from rdf import check_schedule


def cmax(inst, starts):
    return max(starts[i] + inst['p'][i] for i in range(inst['n']))


def allowed_times(inst, h, i, F):
    lo, hi = _domain(inst, h, i)
    return [t for t in range(lo, hi + 1) if (i, t) not in F]


class Trail:
    """A set with an undo log; peak size is the live forbidden box."""

    def __init__(self):
        self.s = set()
        self.log = []
        self.peak = 0
        self.adds = 0

    def mark(self):
        return len(self.log)

    def add_many(self, elems):
        elems = list(elems)
        self.log.append(elems)
        self.s.update(elems)
        self.adds += len(elems)
        if len(self.s) > self.peak:
            self.peak = len(self.s)

    def undo(self, mark):
        while len(self.log) > mark:
            for e in self.log.pop():
                self.s.discard(e)


class StreamProof(Proof):
    """A NO(h) certificate as a flat DFS event stream."""

    kind = 'talc-stream'

    def __init__(self, inst, h, events, forbid0=frozenset(), stats=None):
        super().__init__(inst, h)
        self.events = list(events)
        self.forbid0 = frozenset(forbid0)
        self.stats = dict(stats or {})

    def _parse(self, pos, trail, depth, stat):
        if pos >= len(self.events):
            return pos, False
        ev = self.events[pos]
        tag = ev[0]
        if tag == 'leaf':
            cert = ev[1]
            stat['cert_calls'] += 1
            stat['cert_entries'] += _cert_entries(cert)
            if cert.get('kind') == 'empty':
                i = cert['job']
                ok = not allowed_times(self.inst, self.h, i, trail.s)
            else:
                ok = bool(verify(self.inst, self.h, cert,
                                 forbid=trail.s))
            stat['max_depth'] = max(stat['max_depth'], depth)
            return pos + 1, ok
        if tag == 'empty':
            i = ev[1]
            stat['max_depth'] = max(stat['max_depth'], depth)
            return pos + 1, not allowed_times(self.inst, self.h, i,
                                              trail.s)
        if tag != 'split':
            return pos, False
        _, i, mid = ev
        times = allowed_times(self.inst, self.h, i, trail.s)
        lo_t = [t for t in times if t > mid]
        hi_t = [t for t in times if t <= mid]
        if not lo_t or not hi_t:
            return pos, False
        stat['splits'] += 1
        stat['max_depth'] = max(stat['max_depth'], depth + 1)
        mark = trail.mark()
        trail.add_many((i, t) for t in lo_t)
        pos, ok = self._parse(pos + 1, trail, depth + 1, stat)
        trail.undo(mark)
        if not ok:
            return pos, False
        mark = trail.mark()
        trail.add_many((i, t) for t in hi_t)
        pos, ok = self._parse(pos, trail, depth + 1, stat)
        trail.undo(mark)
        return pos, ok

    def audit_rdf(self):
        try:
            trail = Trail()
            trail.add_many(self.forbid0)
            stat = dict(splits=0, cert_calls=0, cert_entries=0,
                        max_depth=0)
            pos, ok = self._parse(0, trail, 0, stat)
            stat['events'] = len(self.events)
            stat['peak_forbid'] = trail.peak
            stat['trail_adds'] = trail.adds
            stat['leftover'] = len(self.events) - pos
            self.stats.update(stat)
            return bool(ok and pos == len(self.events))
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def _cert_entries(cert):
    n = 0
    if not isinstance(cert, dict):
        return 0
    for k, v in cert.items():
        if k == 'kind' or isinstance(v, str):
            continue
        try:
            n += len(v)
        except TypeError:
            pass
    return n


def stream_from_branch(proof):
    events = []

    def walk(node):
        tag = node[0]
        if tag == 'leaf':
            events.append(('leaf', node[2]))
            return
        if tag == 'empty':
            events.append(('empty', node[2]))
            return
        _, i, mid, parent_F, lo, hi = node
        events.append(('split', i, mid))
        walk(lo)
        walk(hi)

    walk(proof.tree)
    return StreamProof(proof.inst, proof.h, events,
                       forbid0=proof.forbid0)


def branch_space(proof):
    """Materialized and path-space counters for a BranchProof tree."""
    st = dict(nodes=0, leaves=0, splits=0, stored_forbid=0,
              peak_path_forbid=0, cert_entries=0, depth=0,
              events=0, path_len=0)

    def walk(node, F, depth, pathsum):
        tag = node[0]
        if tag in ('leaf', 'empty'):
            st['leaves'] += 1
            st['stored_forbid'] += len(node[1])
            st['path_len'] += depth
            st['depth'] = max(st['depth'], depth)
            st['peak_path_forbid'] = max(st['peak_path_forbid'],
                                         pathsum + len(node[1]))
            if tag == 'leaf':
                st['cert_entries'] += _cert_entries(node[2])
            return
        _, i, mid, parent_F, lo, hi = node
        st['nodes'] += 1
        st['splits'] += 1
        st['stored_forbid'] += len(parent_F)
        times = allowed_times(proof.inst, proof.h, i, parent_F)
        lo_t = [t for t in times if t > mid]
        hi_t = [t for t in times if t <= mid]
        loF = parent_F | {(i, t) for t in lo_t}
        hiF = parent_F | {(i, t) for t in hi_t}
        walk(lo, loF, depth + 1, pathsum + len(parent_F))
        walk(hi, hiF, depth + 1, pathsum + len(parent_F))

    walk(proof.tree, frozenset(proof.forbid0), 0, 0)
    st['events'] = 2 * st['splits'] + st['leaves']
    return st


def compare_space(proof):
    old = branch_space(proof)
    sp = stream_from_branch(proof)
    ok = sp.audit_rdf()
    new = dict(sp.stats)
    new['ok'] = ok
    new['stored_forbid'] = len(proof.forbid0)
    new['cert_entries'] = old['cert_entries']
    return old, new, sp


def check_bracket(inst, L, U, schedule, machine, lb_proof,
                  schedule_checked=True):
    """Type-check a bracket; return (ok, reason)."""
    if not isinstance(L, int) or not isinstance(U, int):
        return False, 'non-integer-bounds'
    if L > U:
        return False, 'L>U'
    if lb_proof is None:
        return False, 'missing-no-proof'
    if getattr(lb_proof, 'h', None) != L - 1:
        return False, 'wrong-no-horizon'
    if not lb_proof.audit_rdf():
        return False, 'invalid-no-proof'
    if schedule is None or machine is None:
        return False, 'missing-yes-witness'
    if len(schedule) != inst['n'] or len(machine) != inst['n']:
        return False, 'wrong-schedule-arity'
    c = cmax(inst, schedule)
    if c != U:
        return False, 'wrong-upper'
    if schedule_checked and not check_schedule(inst, c, schedule, machine):
        return False, 'invalid-schedule'
    return True, 'ok'


def typed_transition(inst, L, U, schedule, machine, lb_proof, h,
                     result):
    """Apply a probe result only if the resulting bracket type-checks."""
    if not (L <= h < U):
        return None, 'probe-out-of-range'
    v = result.get('verdict')
    if v is False:
        p = result.get('proof')
        if p is None or getattr(p, 'h', None) != h or not p.audit_rdf():
            return None, 'bad-no-witness'
        L2, U2, proof2 = h + 1, U, p
        s2, m2 = schedule, machine
    elif v is True:
        s2, m2 = result.get('schedule'), result.get('machine')
        if s2 is None or m2 is None:
            return None, 'bad-yes-witness'
        c = cmax(inst, s2)
        if c > h or not check_schedule(inst, c, s2, m2):
            return None, 'invalid-yes-witness'
        L2, U2, proof2 = L, min(U, c), lb_proof
        if c >= U and U != c:
            return None, 'non-improving-yes'
    else:
        return (L, U, schedule, machine, lb_proof), 'unknown'
    ok, why = check_bracket(inst, L2, U2, s2, m2, proof2)
    if not ok:
        return None, why
    return (L2, U2, s2, m2, proof2), 'ok'
