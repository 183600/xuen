"""v9.0 PACT-R: residual-contract search over parameterized certificate trees.

The unit of output is not a boolean plus an optional witness, but a typed
judgement

    NO(pi)  |  YES(sigma)  |  OPEN(rho)

where rho is a *residual certificate*: a well-formed partition tree whose
closed leaves are Farkas/empty leaves and whose holes are labelled by the
box (h, F), the search depth and the remaining budget.  A residual has the
contract

    NO(h | F)  <=>  AND_{hole j} NO(h | F_j).

Thus UNKNOWN is no longer an untyped failure: it is a proof skeleton with a
precise missing set.  Resuming a residual expands holes only; closed work is
never recomputed.

Every certificate also carries a ledger

    (lp, cert_lp, nodes, expanded, closed_leaves, open_leaves, height)

which the independent audit recomputes from the tree.  The ledger is what
turns the empirical parameter k into a per-instance, checkable quantity.
"""
import sys
import time

sys.path[:0] = ['exp/v8p', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from sage import BranchProof, _elig_aware, _domain
from pact import _integral_schedule, _singleton_leaf, _assign_machines
from sdecc import SDLP
from cert import verify, integer_certificate
from rdf import check_schedule
from po import heads_tails


class RNode:
    """A node of a (possibly open) certificate tree."""

    __slots__ = ('tag', 'F', 'depth', 'children', 'i', 'mid',
                 'cert', 'job', 'bounds', 'reason', 'lp_done',
                 'starts', 'machines', 'cert_tries')

    def __init__(self, tag, F, depth, **kw):
        self.tag = tag
        self.F = F
        self.depth = depth
        self.children = None
        self.i = None
        self.mid = None
        self.cert = None
        self.job = None
        self.bounds = None
        self.reason = None
        self.lp_done = False
        self.starts = None
        self.machines = None
        self.cert_tries = 0
        for k, v in kw.items():
            setattr(self, k, v)


class ResidualProof(Proof):
    """A replayable residual (or closed) certificate tree with a ledger."""

    kind = 'residual'

    def __init__(self, inst, h, root, ledger=None, stats=None,
                 closed=False):
        super().__init__(inst, h)
        self.root = root
        self.ledger = dict(ledger or {})
        self.stats = dict(stats or {})
        self.closed = bool(closed)

    # ------------------------------------------------------------- audit
    def _allowed(self, i, F):
        lo, hi = _domain(self.inst, self.h, i)
        return [t for t in range(lo, hi + 1) if (i, t) not in F]

    def _check(self, node, F, depth):
        if node is None or node.F != F or node.depth != depth:
            return False
        if node.tag == 'open':
            if node.reason not in ('budget', 'depth', 'cert', 'lp',
                                   'choice', 'machine'):
                return False
            # An open hole must be a genuinely open, non-empty box.
            for i in range(self.inst['n']):
                if not self._allowed(i, F):
                    return False
            return True
        if node.tag == 'leaf':
            if node.cert is None:
                return False
            if node.cert.get('kind') == 'empty':
                return not self._allowed(node.cert['job'], F)
            return bool(verify(self.inst, self.h, node.cert, forbid=F))
        if node.tag == 'empty':
            return not self._allowed(node.job, F)
        if node.tag == 'yes':
            s, m = node.starts, node.machines
            if s is None or m is None:
                return False
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            return cmax <= self.h and check_schedule(self.inst, cmax, s, m)
        if node.tag != 'node' or node.children is None:
            return False
        i, mid = node.i, node.mid
        allowed = self._allowed(i, F)
        lo_t = [t for t in allowed if t > mid]
        hi_t = [t for t in allowed if t <= mid]
        if not lo_t or not hi_t:
            return False
        loF = F | {(i, t) for t in lo_t}
        hiF = F | {(i, t) for t in hi_t}
        return (self._check(node.children[0], loF, depth + 1)
                and self._check(node.children[1], hiF, depth + 1))

    def _measure(self, node, F, depth):
        if node is None or node.F != F or node.depth != depth:
            return None
        m = dict(nodes=1, expanded=0, closed_leaves=0, open_leaves=0,
                 cert_lp=0, lp=0, height=depth, holes=0)
        if node.tag == 'open':
            m['open_leaves'] = 1
            m['holes'] = 1
            m['expanded'] = 1 if node.lp_done else 0
            m['lp'] = 1 if node.lp_done else 0
            m['cert_lp'] = node.cert_tries
            m['height'] = max(m['height'], depth)
            return m
        if node.tag in ('leaf', 'empty'):
            m['closed_leaves'] = 1
            m['expanded'] = 1
            m['lp'] = 1 if node.lp_done else 0
            m['cert_lp'] = node.cert_tries
            return m
        if node.tag == 'yes':
            m['expanded'] = 1
            m['lp'] = 1 if node.lp_done else 0
            return m
        if node.tag != 'node' or node.children is None:
            return None
        i, mid = node.i, node.mid
        allowed = self._allowed(i, F)
        lo_t = [t for t in allowed if t > mid]
        hi_t = [t for t in allowed if t <= mid]
        if not lo_t or not hi_t:
            return None
        loF = F | {(i, t) for t in lo_t}
        hiF = F | {(i, t) for t in hi_t}
        a = self._measure(node.children[0], loF, depth + 1)
        b = self._measure(node.children[1], hiF, depth + 1)
        if a is None or b is None:
            return None
        for k in m:
            if k != 'height':
                m[k] += a[k] + b[k]
        m['expanded'] += 1
        m['lp'] += 1 if node.lp_done else 0
        m['height'] = max(a['height'], b['height'])
        return m

    def audit_rdf(self):
        try:
            if not self._check(self.root, frozenset(), 0):
                return False
            m = self._measure(self.root, frozenset(), 0)
            if m is None:
                return False
            for k in ('nodes', 'expanded', 'closed_leaves', 'open_leaves',
                      'cert_lp', 'lp', 'height'):
                if self.ledger.get(k) != m[k]:
                    return False
            if self.closed and m['open_leaves'] != 0:
                return False
            if not self.closed and m['open_leaves'] == 0:
                return False
            return True
        except Exception:
            return False

    def proof_complete(self):
        return self.closed and self.audit_rdf()

    # ---------------------------------------------------------- residual
    def holes(self):
        out = []

        def walk(n, path):
            if n.tag == 'open':
                out.append((n, path))
            elif n.tag == 'node':
                walk(n.children[0], path + (0,))
                walk(n.children[1], path + (1,))

        walk(self.root, ())
        return out

    def close_with(self, replacement):
        """Return a closed Proof after substituting every hole.

        replacement maps id(open_node) -> a closed RNode (or a proof tree
        in the same shape).  This is used only by the experiments; the
        search normally resumes the holes directly.
        """
        def walk(n):
            if n.tag != 'open':
                if n.tag == 'node':
                    return RNode('node', n.F, n.depth, i=n.i, mid=n.mid,
                                 children=(walk(n.children[0]),
                                           walk(n.children[1])),
                                 lp_done=n.lp_done)
                return n
            rep = replacement.get(id(n))
            if rep is None:
                raise ValueError('unclosed hole')
            return rep

        root = walk(self.root)
        m = self._measure(root, frozenset(), 0)
        if m is None or m['open_leaves']:
            raise ValueError('closure incomplete')
        led = dict(self.ledger)
        for k in ('nodes', 'expanded', 'closed_leaves', 'open_leaves',
                  'cert_lp', 'lp', 'height'):
            led[k] = m[k]
        return ClosedProof(self.inst, self.h, root, led, self.stats)


class ClosedProof(ResidualProof):
    kind = 'branch'

    def __init__(self, inst, h, root, ledger=None, stats=None):
        super().__init__(inst, h, root, ledger, stats, closed=True)

    def proof_complete(self):
        return self.audit_rdf()


# --------------------------------------------------------------- search
class ResidualSearch:
    """Depth- and budget-parameterized search that returns a residual."""

    def __init__(self, inst, h, policy=None):
        self.inst = inst
        self.h = h
        self.policy = dict(policy or {})
        self.n = inst['n']
        self.m = inst['m']
        self.p = inst['p']
        self.elig = _elig_aware(inst)
        self.est, self.q = heads_tails(inst, 0, [0] * self.n)
        self.lp = SDLP(inst, h, self.est, self.q, use_dom=True,
                       elig_aware=self.elig)
        self.base = [(0, 1)] * self.lp.N
        self.lp_used = 0
        self.cert_lp = 0
        self.stats = dict(nodes=0, leaves=0, depth=0, lp_solves=0,
                          cert_lp=0, holes=0, branch_jobs=[],
                          reason=dict())

    # ------------------------------------------------------------- utils
    def _allowed_times(self, i, bounds):
        return sorted({key[-1] for c, key in enumerate(self.lp.cols)
                       if key[0] == i and bounds[c] != (0, 0)})

    def _choose(self, z, bounds):
        cand = []
        for i in range(self.n):
            times = self._allowed_times(i, bounds)
            if len(times) <= 1:
                continue
            dist = []
            for tt in times:
                v = sum(z[c] for c, key in enumerate(self.lp.cols)
                        if key[0] == i and key[-1] == tt
                        and bounds[c] != (0, 0))
                dist.append((tt, v))
            frac = sum(v for _, v in dist if 1e-7 < v < 1 - 1e-7)
            if frac <= 1e-7:
                continue
            cand.append(((sum(v for _, v in dist), self.q[i],
                          len(self.inst['succ'][i]), -i), i, dist))
        if not cand:
            return None, None
        cand.sort(reverse=True)
        _, i, dist = cand[0]
        total = sum(v for _, v in dist)
        split = self.policy.get('split', 0.5)
        acc = 0.0
        mid = dist[0][0]
        for tt, v in dist:
            acc += v
            if acc >= split * total:
                mid = tt
                break
        times = [tt for tt, _ in dist]
        lo_t = [tt for tt in times if tt > mid]
        hi_t = [tt for tt in times if tt <= mid]
        if not lo_t or not hi_t:
            mid = times[len(times) // 2 - 1] if len(times) > 1 else times[0]
            lo_t = [tt for tt in times if tt > mid]
            hi_t = [tt for tt in times if tt <= mid]
        if not lo_t or not hi_t:
            return None, None
        return i, mid

    def _bound_side(self, bounds, i, mid, side):
        b = list(bounds)
        for c, key in enumerate(self.lp.cols):
            if key[0] != i:
                continue
            tt = key[-1]
            if (side == 'lo' and tt > mid) or (side == 'hi' and tt <= mid):
                b[c] = (0, 0)
        return b

    def _open(self, F, depth, reason, bounds=None):
        self.stats['holes'] += 1
        self.stats['reason'][reason] = self.stats['reason'].get(reason, 0) + 1
        return RNode('open', F, depth, reason=reason,
                     bounds=list(bounds) if bounds is not None else None)

    def _leaf_cert(self, F, depth):
        self.cert_lp += 1
        self.stats['cert_lp'] += 1
        cert = integer_certificate(self.inst, self.h, use_dom=True,
                                   elig_aware=self.elig, forbid=F)
        if cert is not None and verify(self.inst, self.h, cert, forbid=F):
            n = RNode('leaf', F, depth, cert=cert, cert_tries=1,
                      lp_done=True)
            return n
        for i in range(self.n):
            lo, hi = _domain(self.inst, self.h, i)
            if lo <= hi and all((i, t) in F for t in range(lo, hi + 1)):
                n = RNode('empty', F, depth, job=i, lp_done=True)
                n.cert_tries = 1
                return n
        n = self._open(F, depth, 'cert')
        n.cert_tries = 1
        n.lp_done = True
        return n

    # --------------------------------------------------------------- dfs
    def _dfs(self, bounds, F, depth, depthcap, nodecap):
        if depthcap is not None and depth > depthcap:
            return self._open(F, depth, 'depth', bounds)
        if nodecap is not None and self.lp_used >= nodecap:
            return self._open(F, depth, 'budget', bounds)
        self.lp_used += 1
        self.stats['nodes'] += 1
        self.stats['lp_solves'] += 1
        res = self.lp.solve(bounds)
        if res.status == 2:
            self.stats['leaves'] += 1
            return self._leaf_cert(F, depth)
        if res.status != 0:
            n = self._open(F, depth, 'lp', bounds)
            n.lp_done = True
            return n
        z = res.x
        frac = False
        for c, key in enumerate(self.lp.cols):
            if 1e-7 < z[c] < 1 - 1e-7 and bounds[c] != (0, 0):
                frac = True
                break
        if not frac:
            got = _integral_schedule(self.inst, self.lp, z, self.elig)
            if got is not None:
                n = RNode('yes', F, depth, starts=got[0],
                          machines=got[1], lp_done=True)
                return n
            single = _singleton_leaf(self.inst, self.h, F, self.lp, bounds)
            if single is not None:
                n = RNode('yes', F, depth, starts=single[1],
                          machines=single[2], lp_done=True)
                return n
            i = None
            mid = None
            for j in range(self.n):
                times = self._allowed_times(j, bounds)
                if len(times) > 1:
                    i = j
                    mid = times[len(times) // 2 - 1]
                    break
            if i is None:
                n = self._open(F, depth, 'machine', bounds)
                n.lp_done = True
                return n
        else:
            i, mid = self._choose(z, bounds)
            if i is None:
                n = self._open(F, depth, 'choice', bounds)
                n.lp_done = True
                return n
        self.stats['depth'] = max(self.stats['depth'], depth)
        self.stats['branch_jobs'].append((i, mid, depth))
        times = self._allowed_times(i, bounds)
        lo_t = [t for t in times if t > mid]
        hi_t = [t for t in times if t <= mid]
        if not lo_t or not hi_t:
            n = self._open(F, depth, 'choice', bounds)
            n.lp_done = True
            return n
        loF = F | {(i, t) for t in lo_t}
        hiF = F | {(i, t) for t in hi_t}
        lo = self._dfs(self._bound_side(bounds, i, mid, 'lo'), loF,
                       depth + 1, depthcap, nodecap)
        if lo.tag == 'yes':
            return lo
        hi = self._dfs(self._bound_side(bounds, i, mid, 'hi'), hiF,
                       depth + 1, depthcap, nodecap)
        if hi.tag == 'yes':
            return hi
        return RNode('node', F, depth, i=i, mid=mid,
                     children=(lo, hi), lp_done=True)

    # ------------------------------------------------------------- public
    def search(self, depthcap=None, nodecap=None):
        t0 = time.time()
        self.lp_used = 0
        self.cert_lp = 0
        self.stats = dict(nodes=0, leaves=0, depth=0, lp_solves=0,
                          cert_lp=0, holes=0, branch_jobs=[],
                          reason=dict())
        root = self._dfs(self.base, frozenset(), 0, depthcap, nodecap)
        if root.tag == 'yes':
            verdict, sched = True, (root.starts, root.machines)
            proof = None
        else:
            closed = self._is_closed(root)
            proof = (ClosedProof(self.inst, self.h, root,
                                 self._ledger(root), self.stats)
                     if closed else
                     ResidualProof(self.inst, self.h, root,
                                   self._ledger(root), self.stats))
            verdict = False if closed else None
            sched = None
        self.stats['t'] = round(time.time() - t0, 5)
        return dict(verdict=verdict, proof=proof, schedule=sched,
                    root=root, **self.stats)

    def _is_closed(self, node):
        if node.tag == 'open':
            return False
        if node.tag == 'node':
            return (self._is_closed(node.children[0])
                    and self._is_closed(node.children[1]))
        return True

    def _ledger(self, root):
        probe = ResidualProof(self.inst, self.h, root)
        m = probe._measure(root, frozenset(), 0)
        if m is None:
            return {}
        return dict(m)


def decide(inst, h, depthcap=None, nodecap=None, policy=None):
    return ResidualSearch(inst, h, policy=policy).search(
        depthcap=depthcap, nodecap=nodecap)


# ------------------------------------------------------------- resumption
def _copy_node(dst, src):
    for k in RNode.__slots__:
        setattr(dst, k, getattr(src, k))


def resume_proof(inst, h, proof, depthcap=None, nodecap=None):
    """Expand the holes of a residual without re-solving closed nodes.

    depthcap is absolute: a hole at depth d is solved when depthcap >= d;
    its children at depth d+1 are holes when depthcap == d.  nodecap is the
    number of new LP solves allowed in this call.
    """
    s = ResidualSearch(inst, h)
    s.lp_used = 0
    t0 = time.time()
    yes = None

    def walk(node):
        nonlocal yes
        if yes is not None:
            return
        if node.tag == 'open':
            if node.reason not in ('budget', 'depth'):
                return
            if node.bounds is None:
                return
            r = s._dfs(node.bounds, node.F, node.depth, depthcap, nodecap)
            _copy_node(node, r)
            if node.tag == 'yes':
                yes = (node.starts, node.machines)
            return
        if node.tag == 'node':
            walk(node.children[0])
            walk(node.children[1])

    walk(proof.root)
    if yes is not None:
        return dict(verdict=True, proof=None, schedule=yes, root=proof.root,
                    lp_solves=s.lp_used, cert_lp=s.cert_lp,
                    new_holes=0, t=round(time.time() - t0, 5))
    closed = _tree_closed(proof.root)
    new = (ClosedProof(inst, h, proof.root, None, proof.stats)
           if closed else
           ResidualProof(inst, h, proof.root, None, proof.stats))
    led = new._measure(new.root, frozenset(), 0)
    new.ledger = dict(led or {})
    if not new.audit_rdf():
        return dict(verdict=None, proof=None, schedule=None,
                    root=proof.root, lp_solves=s.lp_used,
                    cert_lp=s.cert_lp, new_holes=0, audit=False,
                    t=round(time.time() - t0, 5))
    return dict(verdict=False if closed else None, proof=new,
                schedule=None, root=proof.root, lp_solves=s.lp_used,
                cert_lp=s.cert_lp,
                new_holes=(led['open_leaves'] if led else None),
                audit=True, t=round(time.time() - t0, 5))


def _tree_closed(node):
    if node.tag == 'open':
        return False
    if node.tag == 'node':
        return _tree_closed(node.children[0]) and _tree_closed(node.children[1])
    return True
