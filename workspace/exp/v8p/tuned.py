"""v8.10 TUNED-PACT: parameter-tuned, locally-improved closing certificates.

This is an incremental layer on v8.9 PACT-ALC.  The outer bracket, LP pin,
SAGE bracketing, STAB closure and TotalTrace are inherited.  Only the
closing probe (lb < ub = OPT, hence h = lb is a NO instance) is changed:

  1. run the complete certificate search with a tuned split quantile q*;
  2. if the resulting NO tree has height >= 2, run a local search over a
     small split neighbourhood and keep the lexicographically shortest
     audited tree (height, nodes, LP solves);
  3. otherwise keep the default tree.

Every candidate is a full PACT certificate search and every accepted tree
is audited by BranchProof.audit_rdf().  Tuning therefore changes the
search order, never the semantics of the certificate.  If tuning fails,
the default complete search (and finally CHD) remains the fallback.
"""
import sys
import time
import random

sys.path[:0] = ['exp/v8p', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from pact import PACT, pact_decide


DEFAULT_SPLITS = (0.2, 0.25, 1.0 / 3.0, 0.4)
FEATURES = ('frac', 'mass', 'q', 'p', 'succ', 'pred', 'slack', 'width',
            'peak', 'entropy', 'spread', 'lo', 'hi')


def _tree_stats(node):
    tag = node[0]
    if tag in ('leaf', 'empty', 'yes'):
        return 0, 1
    _, i, mid, parent_F, lo, hi = node
    hl, nl = _tree_stats(lo)
    hr, nr = _tree_stats(hi)
    return 1 + max(hl, hr), 1 + nl + nr


def proof_stats(proof):
    if proof is None:
        return None, None, None
    kind = getattr(proof, 'kind', None)
    if kind == 'branch':
        try:
            h, n = _tree_stats(proof.tree)
            return kind, h, n
        except Exception:
            return kind, None, None
    if kind == 'lb-no':
        return proof_stats(getattr(proof, 'source', None))
    return kind, 0, 1


class TunedPACT(PACT):
    """PACT-F with a tuned/local-search closing probe."""

    def __init__(self, inst, split=1.0 / 3.0, tune_splits=DEFAULT_SPLITS,
                 tune_trigger=1, tune_weights=None, weight_budget=0,
                 weight_seed=0, **kw):
        kw.setdefault('pact_mode', 'closing')
        super().__init__(inst, **kw)
        self.split = split
        self.tune_splits = tuple(tune_splits)
        self.tune_trigger = tune_trigger
        self.tune_weights = tune_weights or ()
        self.weight_budget = weight_budget
        self.weight_seed = weight_seed
        self.tune_calls = 0
        self.tune_accepts = 0
        self.weight_calls = 0
        self.weight_accepts = 0
        self.tune_stats = []

    def _search(self, h, policy):
        r = pact_decide(self.inst, h, depthcap=None, nodecap=None,
                        policy=policy)
        self.pact_lp += r['lp_solves']
        self.pact_cert_lp += r.get('cert_lp', 0)
        self.pact_nodes += r['nodes']
        return r

    @staticmethod
    def _key(r):
        return (r['depth'], r['nodes'], r['lp_solves'])

    def _closing_search(self, h):
        base = self._search(h, {'split': self.split})
        self.tune_calls += 1
        if base['verdict'] is not False:
            return base, base
        if base['depth'] < self.tune_trigger:
            return base, base
        best = base
        tried = []
        for q in self.tune_splits:
            if abs(q - self.split) < 1e-12:
                continue
            r = self._search(h, {'split': q})
            self.tune_calls += 1
            tried.append((q, r['verdict'], r['depth'], r['nodes'],
                          r['lp_solves']))
            if r['verdict'] is False and self._key(r) < self._key(best):
                best = r
        for w, q in self.tune_weights:
            r = self._search(h, {'weights': w, 'split': q})
            self.tune_calls += 1
            tried.append((q, r['verdict'], r['depth'], r['nodes'],
                          r['lp_solves']))
            if r['verdict'] is False and self._key(r) < self._key(best):
                best = r
        if self.weight_budget > 0 and best['depth'] >= 1:
            rng = random.Random((self.weight_seed * 1000003)
                                ^ (h * 9176) ^ len(tried))
            for _ in range(self.weight_budget):
                w = {k: rng.choice((-2, -1, 0, 1, 2)) for k in FEATURES}
                q = rng.choice((0.2, 0.25, 1.0 / 3.0, 0.4, 0.5,
                                0.6, 2.0 / 3.0, 0.75))
                r = self._search(h, {'weights': w, 'split': q})
                self.weight_calls += 1
                self.tune_calls += 1
                tried.append(('w', r['verdict'], r['depth'], r['nodes'],
                              r['lp_solves']))
                if r['verdict'] is False and self._key(r) < self._key(best):
                    best = r
                    self.weight_accepts += 1
                    if best['depth'] == 0:
                        break
        if best is not base:
            self.tune_accepts += 1
        self.tune_stats.append(dict(h=h, base=(base['depth'], base['nodes']),
                                    best=(best['depth'], best['nodes']),
                                    tried=tried))
        return best, base

    def _probe(self, h):
        # Bracketing probes: unchanged SAGE engine (PACT-F semantics).
        if self.opt - self.lb > 1:
            return super()._probe(h)
        # Closing probe: h = lb < opt, therefore the verdict is NO.
        r, base = self._closing_search(h)
        if r['verdict'] is False:
            self.pact_no += 1
            self.stats['pact_no'] += 1
            self._record_proof(r['proof'])
            self.steps.append(dict(h=h, v=False, proof=r['proof'],
                                   engine='tuned-close',
                                   tune_base=(base['depth'], base['nodes']),
                                   tune_best=(r['depth'], r['nodes'])))
            return False, r['proof']
        if r['verdict'] is True:
            self.pact_yes += 1
            self.stats['pact_yes'] += 1
            s, m = r['schedule'], r['machine']
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='tuned-close'))
            return True, (s, m, cmax)
        # No complete certificate: fall back to the inherited closing path
        # (which itself ends in CHD).
        return super()._probe(h)

    def _result(self):
        r = super()._result()
        r['tune_calls'] = self.tune_calls
        r['tune_accepts'] = self.tune_accepts
        r['tune_stats'] = self.tune_stats
        return r


class TunedCompletePACT(TunedPACT):
    """PACT-C with the same split neighbourhood on every complete probe."""

    def __init__(self, inst, **kw):
        kw.setdefault('pact_depth', None)
        kw.setdefault('use_ga', False)
        kw.setdefault('complete_fallback', True)
        super().__init__(inst, **kw)

    def _probe(self, h):
        r, base = self._closing_search(h)
        if r['verdict'] is False:
            self.pact_no += 1
            self.stats['pact_no'] += 1
            self._record_proof(r['proof'])
            self.steps.append(dict(h=h, v=False, proof=r['proof'],
                                   engine='tuned-complete',
                                   tune_base=(base['depth'], base['nodes']),
                                   tune_best=(r['depth'], r['nodes'])))
            return False, r['proof']
        if r['verdict'] is True:
            self.pact_yes += 1
            self.stats['pact_yes'] += 1
            s, m = r['schedule'], r['machine']
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='tuned-complete'))
            return True, (s, m, cmax)
        return super()._probe(h)


def run_tuned(inst, known, name, idx, **kw):
    t0 = time.time()
    co = TunedPACT(inst, **kw)
    r = co.optimize()
    dt = time.time() - t0
    r.update(name=name, idx=idx, known=known, t=round(dt, 4))
    b = getattr(co, 'chip', None) or {}
    p = getattr(co, 'pin', None) or {}
    r['chip_lb'] = b.get('lb')
    r['chip_ub'] = b.get('ub')
    r['pin_lb'] = p.get('lb')
    r['pin_solves'] = p.get('solves')
    r['pin_lp'] = getattr(co, 'pin_lp', 0)
    r['bb_lp'] = getattr(co, 'bb_lp', 0)
    r['cert_lp'] = getattr(co, 'cert_lp_total', 0)
    r['ga_stats'] = getattr(co, 'ga_stats', [])
    r['proof_kind'] = getattr(getattr(co, 'lb_proof', None), 'kind', None)
    r['stats2'] = getattr(co, 'stats', {})
    r['lns'] = getattr(co, 'lns_stats', None)
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof'] and r['total_audit']
                   and r['cert_h'] == known - 1)
    kind, ph, pn = proof_stats(getattr(co, 'lb_proof', None))
    r['final_proof_kind'], r['final_k'], r['final_nodes'] = kind, ph, pn
    r['weight_calls'] = getattr(co, 'weight_calls', 0)
    r['weight_accepts'] = getattr(co, 'weight_accepts', 0)
    return r


def run_tuned_complete(inst, known, name, idx, **kw):
    t0 = time.time()
    co = TunedCompletePACT(inst, **kw)
    r = co.optimize()
    dt = time.time() - t0
    r.update(name=name, idx=idx, known=known, t=round(dt, 4))
    b = getattr(co, 'chip', None) or {}
    p = getattr(co, 'pin', None) or {}
    r['chip_lb'] = b.get('lb')
    r['chip_ub'] = b.get('ub')
    r['pin_lb'] = p.get('lb')
    r['pin_solves'] = p.get('solves')
    r['pin_lp'] = getattr(co, 'pin_lp', 0)
    r['bb_lp'] = getattr(co, 'bb_lp', 0)
    r['cert_lp'] = getattr(co, 'cert_lp_total', 0)
    r['ga_stats'] = getattr(co, 'ga_stats', [])
    r['proof_kind'] = getattr(getattr(co, 'lb_proof', None), 'kind', None)
    r['stats2'] = getattr(co, 'stats', {})
    r['lns'] = getattr(co, 'lns_stats', None)
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof'] and r['total_audit']
                   and r['cert_h'] == known - 1)
    kind, ph, pn = proof_stats(getattr(co, 'lb_proof', None))
    r['final_proof_kind'], r['final_k'], r['final_nodes'] = kind, ph, pn
    r['weight_calls'] = getattr(co, 'weight_calls', 0)
    r['weight_accepts'] = getattr(co, 'weight_accepts', 0)
    return r
