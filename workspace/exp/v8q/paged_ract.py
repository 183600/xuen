"""v9.0 PAGE-RACT: R-ACT search with a paged compact proof store.

The search is exactly ract_decide's complete DFS (bound leaves included).
The difference is the proof object: every NO proof is serialised to a
compact preorder stream and audited by PAGE's one-pass checker.  The
outer bracket and TotalTrace are inherited from PACT/R-ACT.
"""
import sys
import time

sys.path[:0] = ['exp/v8q', 'exp/v8p', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from paged import (encode_compact, audit_compact, PagedProof)
from ract import RACT, ract_decide, run_ract
from pact import pact_decide


class PNode:
    __slots__ = ('tag', 'i', 'mid', 'children', 'cert', 'job', 'lb',
                 'reason', 'starts', 'machines')
    def __init__(self, tag):
        self.tag = tag
        self.i = None
        self.mid = None
        self.children = None
        self.cert = None
        self.job = None
        self.lb = None
        self.reason = None
        self.starts = None
        self.machines = None


def to_pnode(t):
    tag = t[0]
    x = PNode(tag)
    if tag == 'node':
        _, i, mid, F, lo, hi = t
        x.i, x.mid = i, mid
        x.children = (to_pnode(lo), to_pnode(hi))
    elif tag == 'leaf':
        x.cert = t[2]
    elif tag == 'empty':
        x.job = t[2]
    elif tag == 'bound':
        x.lb = int(t[2])
    elif tag == 'open':
        x.lb = int(t[2])
        x.reason = 'budget'
    elif tag == 'yes':
        x.starts, x.machines = t[2], t[3]
    else:
        raise ValueError(tag)
    return x


class PagedRACT(RACT):
    """R-ACT + PAGE proof store."""

    def __init__(self, inst, **kw):
        super().__init__(inst, ract_mode='complete', **kw)
        self.paged_bytes = 0
        self.paged_audits = 0
        self.paged_ok = 0
        self.stats.update(paged_bytes=0, paged_audits=0, paged_ok=0)

    def _probe(self, h):
        r = ract_decide(self.inst, h, depthcap=None, nodecap=None)
        self.pact_calls += 1
        self.pact_lp += r['lp_solves']
        self.pact_cert_lp += r.get('cert_lp', 0)
        self.pact_nodes += r['nodes']
        self.ract_bound += r.get('bound', 0)
        self.ract_empty += r.get('empty', 0)
        self.stats['ract_bound'] += r.get('bound', 0)
        self.stats['ract_empty'] += r.get('empty', 0)
        if r['verdict'] is False:
            root = to_pnode(r['proof'].tree)
            data = encode_compact(root, self.inst, h)
            pp = PagedProof(self.inst, h, data,
                            dict(bytes=len(data), engine='paged-ract'))
            self.paged_bytes += len(data)
            self.paged_audits += 1
            if pp.audit_rdf():
                self.paged_ok += 1
            else:
                # never hand a bad proof to the outer trace
                self.pact_unknown += 1
                self.stats['pact_unknown'] += 1
                return None, None
            self.stats['paged_bytes'] = self.paged_bytes
            self.stats['paged_audits'] = self.paged_audits
            self.stats['paged_ok'] = self.paged_ok
            self.pact_no += 1
            self.stats['pact_no'] += 1
            self._record_proof(pp)
            self.steps.append(dict(h=h, v=False, proof=pp,
                                   engine='paged-ract'))
            return False, pp
        if r['verdict'] is True:
            self.pact_yes += 1
            self.stats['pact_yes'] += 1
            s, m = r['schedule'], r['machine']
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='paged-ract'))
            return True, (s, m, cmax)
        # fall back to PACT's complete search, then CHD
        self.pact_unknown += 1
        self.stats['pact_unknown'] += 1
        r = pact_decide(self.inst, h, depthcap=None, nodecap=None)
        self.pact_lp += r['lp_solves']
        self.pact_cert_lp += r.get('cert_lp', 0)
        self.pact_nodes += r['nodes']
        if r['verdict'] is False:
            self.pact_no += 1
            self.stats['pact_no'] += 1
            self._record_proof(r['proof'])
            self.steps.append(dict(h=h, v=False, proof=r['proof'],
                                   engine='pact'))
            return False, r['proof']
        if r['verdict'] is True:
            self.pact_yes += 1
            self.stats['pact_yes'] += 1
            s, m = r['schedule'], r['machine']
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='pact'))
            return True, (s, m, cmax)
        self.stats['chd_fallback'] += 1
        v, st, rdf = self._decide(h)
        self.queries += 1
        self._absorb(st)
        self._record(h, v, st)
        if v is False:
            self.steps.append(dict(h=h, v=False, proof=rdf, engine='chd'))
        elif v is True:
            s, m = rdf.schedule, rdf.machine
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='chd'))
        else:
            self.steps.append(dict(h=h, v=None, engine='chd'))
        return v, rdf

    def _result(self):
        r = super()._result()
        r['paged_bytes'] = self.paged_bytes
        r['paged_audits'] = self.paged_audits
        r['paged_ok'] = self.paged_ok
        return r


def run_paged_ract(inst, known, name, idx, **kw):
    t0 = time.time()
    co = PagedRACT(inst, **kw)
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
    r['paged_bytes'] = getattr(co, 'paged_bytes', 0)
    r['paged_audits'] = getattr(co, 'paged_audits', 0)
    r['paged_ok'] = getattr(co, 'paged_ok', 0)
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof'] and r['total_audit']
                   and r['cert_h'] == known - 1)
    return r
