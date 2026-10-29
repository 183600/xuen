"""v9.0 PACT-W: PACT-R with a frontier-width first phase and resume.

The first phase stops after a node budget 2B-1, which is exactly the
number of nodes of a complete NO tree with frontier width B.  If the
residual still has holes, the second phase resumes those holes without
re-solving any closed node.  The default B=5 covers every NO tree in the
252-instance corpus; larger B is used only when the caller asks for it.
"""
import sys
import time

sys.path[:0] = ['exp/v8p', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from sage import SAGE
from rdf import check_schedule
from residual import decide, resume_proof
from pact_r import PACT_R, run_pact_r


class PACT_W(PACT_R):
    def __init__(self, inst, width_budget=5, **kw):
        super().__init__(inst, **kw)
        self.width_budget = width_budget
        self.res_resumed = 0
        self.stats.update(res_resumed=0)

    def _accept_res(self, r, h, engine):
        if r['verdict'] is False:
            p = r.get('proof')
            if not isinstance(p, Proof) or not p.audit_rdf():
                return None
            self.res_no += 1
            self.stats['res_no'] += 1
            self._record_proof(p)
            self.steps.append(dict(h=h, v=False, proof=p,
                                   engine=engine,
                                   ledger=dict(p.ledger)))
            return False, p
        if r['verdict'] is True:
            s, m = r['schedule']
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            if not check_schedule(self.inst, cmax, s, m):
                return None
            self.res_yes += 1
            self.stats['res_yes'] += 1
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine=engine))
            return True, (s, m, cmax)
        return None

    def _probe_inner(self, h):
        if self.mode == 'sage':
            return super()._probe_inner(h)
        B = self.width_budget
        r = self._record_res(decide(self.inst, h, nodecap=2 * B - 1))
        got = self._accept_res(r, h, 'width')
        if got is not None:
            return got
        if r['verdict'] is not None:
            return self._fallback(h, r)
        z = resume_proof(self.inst, h, r['proof'],
                         depthcap=None, nodecap=None)
        self.res_resumed += 1
        self.stats['res_resumed'] += 1
        self.res_lp += z.get('lp_solves', 0)
        self.res_cert_lp += z.get('cert_lp', 0)
        self.res_nodes += z.get('lp_solves', 0)
        self.res_holes += z.get('new_holes', 0) or 0
        if z.get('proof') is not None:
            self.res_ledgers.append(z['proof'].ledger)
        got = self._accept_res(z, h, 'resume')
        if got is not None:
            return got
        return self._fallback(h, z)

    def _result(self):
        r = super()._result()
        r['res_resumed'] = self.res_resumed
        r['width_budget'] = self.width_budget
        return r


def run_pact_w(inst, known, name, idx, **kw):
    t0 = time.time()
    co = PACT_W(inst, **kw)
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
    r['proof_kind'] = getattr(getattr(co, 'lb_proof', None),
                              'kind', None)
    r['stats2'] = getattr(co, 'stats', {})
    r['lns'] = getattr(co, 'lns_stats', None)
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof'] and r['total_audit']
                   and r['cert_h'] == known - 1)
    return r
