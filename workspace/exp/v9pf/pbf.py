"""v9.2 PBF-PACT: Pareto best-case frontier.

BAM explores a certified frontier and, at a fractional leaf, asks one LP
at ``f.L``.  PBF adds a *best-case split test*: before committing to the
LP-mass split, it evaluates a small Pareto set of candidate domain splits
at the current target ``H = U-1``.  If one split makes both children
infeasible at H, the parent is closed immediately by a height-1 branch
proof (one STRONG action) instead of expanding two leaves and proving
them separately.  Otherwise the split with the best Pareto score is used.

The only change with respect to BAM is the split rule; every lower bound
is still a certified LP/Farkas fact, and every certificate is audited by
the same frontier checker.
"""
import sys

sys.path[:0] = ['exp/v10b', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13', 'exp/v9pf']

from bam import (BAM, Node, BAMCertificate, _forbid_box, _effective,
                 _root_box, _empty_proof)
from icf import CertLeafProof, FrontierProof, cmax
from sage import BranchProof, _elig_aware
from sdecc import SDLP
from po import heads_tails
from cert import integer_certificate, verify


class PBF(BAM):
    """BAM with a Pareto best-case split test at the target horizon."""

    def __init__(self, *args, strong_k=6, strong_mode='H',
                 strong_min_gap=2, **kw):
        super().__init__(*args, **kw)
        self.strong_k = int(strong_k)
        self.strong_mode = strong_mode
        self.strong_min_gap = int(strong_min_gap)
        self.stats.update(strong_calls=0, strong_evals=0, strong_lp=0,
                          strong_cert_lp=0, strong_double=0,
                          strong_single=0, strong_none=0,
                          strong_fallbacks=0, strong_best=0)

    # ---------------------------------------------------------- child LP
    def _eval_child(self, lo, hi, H):
        """Classify a child box at H: closed / open(score) / unknown."""
        inst = self.inst
        eff = _effective(inst, H, lo, hi)
        if eff is None:
            F = _forbid_box(inst, H, lo, hi)
            pr = _empty_proof(inst, H, F, lo, hi)
            if pr is None:
                return ('unknown', None, None, None, 0.0)
            cert = {'kind': 'empty', 'job': pr.cert['job']}
            return ('closed', cert, pr, F, 1.0)
        a, b = eff
        F = _forbid_box(inst, H, a, b)
        n = inst['n']
        est, q = heads_tails(inst, 0, [0] * n)
        elig = _elig_aware(inst)
        try:
            lp = SDLP(inst, H, est, q, use_dom=True, elig_aware=elig,
                      forbid=F)
            self.stats['lp'] += 1
            self.stats['strong_lp'] += 1
            res = lp.solve() if lp.N else None
        except Exception:
            return ('unknown', None, None, None, 0.0)
        if lp.N == 0 or res is None or res.status == 2:
            cert = integer_certificate(inst, H, use_dom=True,
                                       elig_aware=elig, forbid=F)
            self.stats['cert_lp'] += 1
            self.stats['strong_cert_lp'] += 1
            if cert is not None and verify(inst, H, cert, forbid=F):
                pr = CertLeafProof(inst, H, F, cert)
                return ('closed', cert, pr, F, 1.0)
            pr = _empty_proof(inst, H, F, a, b)
            if pr is not None:
                cert = {'kind': 'empty', 'job': pr.cert['job']}
                return ('closed', cert, pr, F, 1.0)
            return ('unknown', None, None, None, 0.0)
        if res.status == 0:
            total = 0.0
            frac = 0.0
            for c, key in enumerate(lp.cols):
                v = float(res.x[c])
                if v > 1e-9:
                    total += v
                    if 1e-7 < v < 1 - 1e-7:
                        frac += v
            near = 1.0 - (frac / total if total > 1e-12 else 0.0)
            return ('open', None, None, F, near)
        return ('unknown', None, None, None, 0.0)

    # --------------------------------------------------------- candidates
    def _strong_candidates(self, f, lp, z, a, b):
        H = self.U - 1
        eff = self._effective_leaf(f, H)
        if eff is None:
            return [], None, None
        aH, bH = eff
        n = self.inst['n']
        fm = [0.0] * n
        if lp is not None and z is not None:
            for c, key in enumerate(lp.cols):
                i, t = key[0], key[-1]
                if i >= n or not (aH[i] <= t <= bH[i]):
                    continue
                v = float(z[c])
                if 1e-7 < v < 1 - 1e-7:
                    fm[i] += v
        order = sorted(range(n),
                       key=lambda i: (fm[i], bH[i] - aH[i], -i),
                       reverse=True)
        out = []
        seen = set()
        for i in order:
            if bH[i] <= aH[i] or b[i] <= a[i]:
                continue
            mid = (aH[i] + bH[i]) // 2
            if not (aH[i] <= mid < bH[i]):
                continue
            # the actual split is made at h=f.L, so keep a valid h-mid
            midh = min(max(mid, a[i]), b[i] - 1)
            key = (i, midh)
            if key in seen:
                continue
            seen.add(key)
            out.append((i, mid, midh))
            if len(out) >= self.strong_k:
                break
        # include BAM's own candidate when it is not already present
        try:
            ji, jm = self._choose_split(lp, z, a, b)
            if ji is not None and a[ji] <= jm < b[ji]:
                key = (ji, jm)
                if key not in seen:
                    out.append((ji, (aH[ji] + bH[ji]) // 2, jm))
        except Exception:
            pass
        return out, aH, bH

    # ------------------------------------------------------------- split
    def _split(self, f, lp, z, a, b):
        if self.U - f.L < self.strong_min_gap:
            return super()._split(f, lp, z, a, b)
        H = self.U - 1
        cand, aH, bH = self._strong_candidates(f, lp, z, a, b)
        if not cand or aH is None:
            self.stats['strong_fallbacks'] += 1
            return super()._split(f, lp, z, a, b)
        self.stats['strong_calls'] += 1
        rows = []
        for i, mid, midh in cand:
            lo1 = list(aH); hi1 = list(bH); hi1[i] = mid
            lo2 = list(aH); hi2 = list(bH); lo2[i] = mid + 1
            l = self._eval_child(lo1, hi1, H)
            r = self._eval_child(lo2, hi2, H)
            self.stats['strong_evals'] += 2
            cl = 1 if l[0] == 'closed' else 0
            cr = 1 if r[0] == 'closed' else 0
            nl = l[4] if l[0] != 'unknown' else -1.0
            nr = r[4] if r[0] != 'unknown' else -1.0
            rows.append(dict(i=i, mid=mid, midh=midh, cl=cl, cr=cr,
                             nl=nl, nr=nr, lo1=lo1, hi1=hi1,
                             lo2=lo2, hi2=hi2, l=l, r=r))
            if cl and cr:
                F = _forbid_box(self.inst, H, aH, bH)
                tree = ('split', i, mid, F,
                        ('leaf', l[3], l[1]),
                        ('leaf', r[3], r[1]))
                try:
                    bp = BranchProof(self.inst, H, tree, forbid0=F)
                except Exception:
                    bp = None
                if bp is not None and bp.audit_rdf():
                    f.L = H + 1
                    f.proof = bp
                    f.children = None
                    f.split = None
                    self.stats['strong_double'] += 1
                    self.stats['strong_best'] += 1
                    self._refresh_dead()
                    return True
        # Pareto filter on (left-closed, right-closed, near-left,
        # near-right) with equal evaluation cost (two child LPs).
        def dom(u, v):
            return (u['cl'] >= v['cl'] and u['cr'] >= v['cr']
                    and u['nl'] >= v['nl'] and u['nr'] >= v['nr']
                    and (u['cl'] > v['cl'] or u['cr'] > v['cr']
                         or u['nl'] > v['nl'] or u['nr'] > v['nr']))
        front = [u for u in rows if not any(dom(v, u) for v in rows
                                           if v is not u)]
        best = max(front, key=lambda u: (u['cl'] + u['cr'],
                                         min(u['nl'], u['nr']),
                                         -u['i']))
        if best['cl'] + best['cr'] > 0:
            self.stats['strong_single'] += 1
        else:
            self.stats['strong_none'] += 1
        # commit the chosen job; keep BAM's standard child boxes at h
        i, midh = best['i'], best['midh']
        if not (a[i] <= midh < b[i]):
            self.stats['strong_fallbacks'] += 1
            return super()._split(f, lp, z, a, b)
        lo1 = list(a); hi1 = list(b); hi1[i] = midh
        lo2 = list(a); hi2 = list(b); lo2[i] = midh + 1
        c0 = self._make_child(f, lo1, hi1)
        c1 = self._make_child(f, lo2, hi2)
        f.children = (c0, c1)
        f.split = (i, midh)
        self.stats['splits'] += 1
        self.stats['max_depth'] = max(self.stats['max_depth'], c0.depth)
        self._refresh_dead()
        return True


def run_pbf(inst, known, name, idx, **kw):
    co = PBF(inst, **kw)
    co.name, co.idx, co.known = name, idx, known
    r = co.run()
    r.update(name=name, idx=idx, known=known)
    return r
