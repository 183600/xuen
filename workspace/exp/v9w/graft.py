"""v9.0 GRAFT-ALC: graph-renaming forest decomposition of proof trees.

GRAFT keeps PACT's outer bracket, complete certificate search, STAB store
and total trace.  It adds a graph layer above the fixed-h decision:

  * interaction graph G_I: jobs are vertices; i~j if i precedes j or
    elig_i and elig_j share a machine;
  * connected components of G_I have pairwise disjoint machine sets, so
    they are independent subproblems: I is feasible at h iff every
    component is feasible at h;
  * isomorphic components are identified by a colour-refinement
    signature and an explicit verified bijection.  One representative is
    solved; its NO proof is reused by a renaming lemma, and its YES
    schedule is mapped to every copy and replayed by check_schedule;
  * the proof object is a component lemma (ComponentProof).  It stores
    the component's global job/machine sets, the representative proof and
    an explicit target->representative bijection.  The checker recomputes
    the decomposition and the bijection; it never trusts the generator.

The layer is sound independently of the quality of the signature: a
false signature match is rejected by the explicit bijection check; a
missed match only loses sharing.  When G_I is connected, GRAFT is exactly
PACT and inherits PACT's exponential worst case.

This module is deliberately additive: it calls pact_decide on the
components and returns the same verdict/proof/schedule triple, so the
PACT outer loop and TotalTrace need no changes.
"""
import sys
import time
import hashlib

sys.path[:0] = ['exp/v9w', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from pact import PACT, pact_decide
from po import make_inst, heads_tails
from rdf import check_schedule


# ------------------------------------------------------------ decomposition
def _uf(n):
    par = list(range(n))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            par[rb] = ra
    return find, union


def component_jobs(inst):
    """Connected components of precedence + shared-eligibility graph."""
    n = inst['n']
    find, union = _uf(n)
    for i in range(n):
        for j in inst['succ'][i]:
            union(i, j)
    owner = {}
    for i in range(n):
        for k in inst['elig'][i]:
            if k in owner:
                union(i, owner[k])
            else:
                owner[k] = i
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return sorted((sorted(g) for g in groups.values()),
                  key=lambda g: (g[0], len(g)))


def subinstance(inst, jobs):
    """Extract a component as an independent instance with local indices."""
    jobs = sorted(jobs)
    jmap = {j: i for i, j in enumerate(jobs)}
    machines = sorted({k for j in jobs for k in inst['elig'][j]})
    mmap = {k: i for i, k in enumerate(machines)}
    p = [inst['p'][j] for j in jobs]
    pred = []
    for j in jobs:
        row = []
        for x in inst['pred'][j]:
            if x not in jmap:
                raise ValueError('predecessor outside component')
            row.append(jmap[x])
        pred.append(row)
    elig = [[mmap[k] for k in inst['elig'][j]] for j in jobs]
    return make_inst(p, len(machines), pred, elig), jobs, machines


def same_instance(a, b):
    if a is None or b is None:
        return False
    if a.get('n') != b.get('n') or a.get('m') != b.get('m'):
        return False
    return (list(a['p']) == list(b['p'])
            and [list(x) for x in a['pred']] == [list(x) for x in b['pred']]
            and [list(x) for x in a['elig']] == [list(x) for x in b['elig']])


# ------------------------------------------------------------ graph labels
def _h(x):
    return hashlib.sha1(repr(x).encode('utf-8')).hexdigest()[:16]


def refine_colors(inst, rounds=5):
    """Colour refinement on the bipartite job-machine/precedence graph."""
    n, m, p = inst['n'], inst['m'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    jc = [_h(('J', p[i], q[i], len(inst['pred'][i]),
              len(inst['succ'][i]), len(inst['elig'][i])))
          for i in range(n)]
    mc = [_h(('M', sum(1 for i in range(n) if k in inst['elig'][i])))
          for k in range(m)]
    jobs_on = [[i for i in range(n) if k in inst['elig'][i]]
               for k in range(m)]
    for _ in range(rounds):
        nj = []
        for i in range(n):
            nb = (tuple(sorted(('p', jc[j]) for j in inst['pred'][i]))
                  + tuple(sorted(('s', jc[j]) for j in inst['succ'][i]))
                  + tuple(sorted(('m', mc[k]) for k in inst['elig'][i])))
            nj.append(_h((jc[i], nb)))
        nm = []
        for k in range(m):
            nb = tuple(sorted(jc[i] for i in jobs_on[k]))
            nm.append(_h((mc[k], nb)))
        jc, mc = nj, nm
    return jc, mc


def signature(inst):
    jc, mc = refine_colors(inst)
    return (tuple(sorted(jc)), tuple(sorted(mc)))


def verify_iso(rep, mem, jmap, mmap):
    """Check that (jmap, mmap): rep -> mem is an instance isomorphism."""
    n, m = rep['n'], rep['m']
    if set(jmap) != set(range(n)) or set(jmap.values()) != set(range(n)):
        return False
    if len(set(jmap.values())) != n:
        return False
    if set(mmap) != set(range(m)) or set(mmap.values()) != set(range(m)):
        return False
    if len(set(mmap.values())) != m:
        return False
    est_r, q_r = heads_tails(rep, 0, [0] * n)
    est_m, q_m = heads_tails(mem, 0, [0] * n)
    for i in range(n):
        j = jmap[i]
        if rep['p'][i] != mem['p'][j]:
            return False
        if q_r[i] != q_m[j]:
            return False
        if set(jmap[x] for x in rep['succ'][i]) != set(mem['succ'][j]):
            return False
        if set(mmap[k] for k in rep['elig'][i]) != set(mem['elig'][j]):
            return False
    return True


def find_isomorphism(rep, mem, nodecap=200000):
    """Return (job_map, machine_map): rep local -> mem local, or None."""
    if signature(rep) != signature(mem):
        return None
    n, m = rep['n'], rep['m']
    if n != mem['n'] or m != mem['m']:
        return None
    jc_r, mc_r = refine_colors(rep)
    jc_m, mc_m = refine_colors(mem)
    if sorted(jc_r) != sorted(jc_m) or sorted(mc_r) != sorted(mc_m):
        return None
    est_r, q_r = heads_tails(rep, 0, [0] * n)
    est_m, q_m = heads_tails(mem, 0, [0] * n)
    cand = []
    for i in range(n):
        row = []
        for j in range(n):
            if jc_r[i] != jc_m[j]:
                continue
            if rep['p'][i] != mem['p'][j] or q_r[i] != q_m[j]:
                continue
            if len(rep['elig'][i]) != len(mem['elig'][j]):
                continue
            if len(rep['pred'][i]) != len(mem['pred'][j]):
                continue
            if len(rep['succ'][i]) != len(mem['succ'][j]):
                continue
            row.append(j)
        if not row:
            return None
        cand.append(row)
    order = sorted(range(n), key=lambda i: (len(cand[i]), -len(rep['succ'][i]), i))
    jmap = {}
    used = set()
    nodes = [0]

    def compatible(i, j):
        for x in rep['pred'][i]:
            if x in jmap and jmap[x] not in mem['pred'][j]:
                return False
        for x in rep['succ'][i]:
            if x in jmap and jmap[x] not in mem['succ'][j]:
                return False
        for x in jmap:
            if i in rep['pred'][x] and j not in mem['pred'][jmap[x]]:
                return False
            if i in rep['succ'][x] and j not in mem['succ'][jmap[x]]:
                return False
        return True

    def rec(pos):
        nodes[0] += 1
        if nodes[0] > nodecap:
            return False
        if pos == n:
            return True
        i = order[pos]
        for j in cand[i]:
            if j in used:
                continue
            if not compatible(i, j):
                continue
            jmap[i] = j
            used.add(j)
            if rec(pos + 1):
                return True
            used.remove(j)
            del jmap[i]
        return False

    if not rec(0):
        return None
    # derive machine map from eligibility sets
    rep_sets = [frozenset(i for i in range(n) if k in rep['elig'][i])
                for k in range(m)]
    mem_sets = [frozenset(j for j in range(n) if k in mem['elig'][j])
                for k in range(m)]
    mmap = {}
    usedm = set()
    for k in range(m):
        target = frozenset(jmap[i] for i in rep_sets[k])
        hit = None
        for mk in range(m):
            if mk in usedm:
                continue
            if mem_sets[mk] == target:
                hit = mk
                break
        if hit is None:
            return None
        mmap[k] = hit
        usedm.add(hit)
    if not verify_iso(rep, mem, jmap, mmap):
        return None
    return jmap, mmap


# --------------------------------------------------------------- proof object
class ComponentProof(Proof):
    """NO(h) for a component, or for a component isomorphic to a solved one.

    If rep_jobs is None the component itself was solved: sub_proof is a
    proof for subinstance(inst, jobs).  Otherwise sub_proof solves
    subinstance(inst, rep_jobs) and job_map/machine_map are explicit
    target->representative bijections.
    """
    kind = 'component'

    def __init__(self, inst, h, jobs, rep_jobs=None, sub_proof=None,
                 job_map=None, machine_map=None, stats=None):
        super().__init__(inst, h)
        self.jobs = tuple(sorted(jobs))
        self.rep_jobs = tuple(sorted(rep_jobs)) if rep_jobs is not None else None
        self.sub_proof = sub_proof
        self.job_map = dict(job_map or {})
        self.machine_map = dict(machine_map or {})
        self.stats = stats or {}

    def _component(self, jobs):
        comps = component_jobs(self.inst)
        for c in comps:
            if tuple(c) == tuple(sorted(jobs)):
                return c
        return None

    def audit_rdf(self):
        try:
            target = self._component(self.jobs)
            if target is None:
                return False
            tsub, tjobs, tmachs = subinstance(self.inst, target)
            if self.rep_jobs is None:
                if self.sub_proof is None or self.sub_proof.h != self.h:
                    return False
                if not same_instance(self.sub_proof.inst, tsub):
                    return False
                return bool(self.sub_proof.audit_rdf())
            rep = self._component(self.rep_jobs)
            if rep is None or rep == target:
                return False
            rsub, rjobs, rmachs = subinstance(self.inst, rep)
            if self.sub_proof is None or self.sub_proof.h != self.h:
                return False
            if not same_instance(self.sub_proof.inst, rsub):
                return False
            if not self.sub_proof.audit_rdf():
                return False
            jm = self.job_map
            mm = self.machine_map
            if set(jm) != set(tjobs) or set(jm.values()) != set(rjobs):
                return False
            if len(set(jm.values())) != len(jm):
                return False
            if set(mm) != set(tmachs) or set(mm.values()) != set(rmachs):
                return False
            if len(set(mm.values())) != len(mm):
                return False
            # local target -> rep maps
            t2r_j = {tj: jm[tj] for tj in tjobs}
            t2r_m = {tm: mm[tm] for tm in tmachs}
            # convert to local indices and verify on the extracted instances
            tl = {j: i for i, j in enumerate(tjobs)}
            rl = {j: i for i, j in enumerate(rjobs)}
            mt = {k: i for i, k in enumerate(tmachs)}
            mr = {k: i for i, k in enumerate(rmachs)}
            jl = {tl[tj]: rl[jm[tj]] for tj in tjobs}
            ml = {mt[tm]: mr[mm[tm]] for tm in tmachs}
            return verify_iso(tsub, rsub, jl, ml)
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


# --------------------------------------------------------------- decision
def graft_decide(inst, h, depthcap=None, nodecap=None, iso_on=True,
                 decompose_on=True, seed=0, root_lp=None, root_res=None):
    """Fixed-h decision with component decomposition and isomorphism sharing.

    Returns the same dict shape as pact_decide plus component statistics.
    """
    t0 = time.time()
    comps = component_jobs(inst) if decompose_on else [list(range(inst['n']))]
    stats = dict(nodes=0, leaves=0, depth=0, lp_solves=0, cert_lp=0,
                 components=len(comps), iso_classes=0, iso_saved=0,
                 iso_checks=0, unknown=False)
    if len(comps) <= 1:
        r = pact_decide(inst, h, depthcap=depthcap, nodecap=nodecap,
                        seed=seed, root_lp=root_lp, root_res=root_res)
        for k in ('nodes', 'leaves', 'depth', 'lp_solves', 'cert_lp'):
            stats[k] = r.get(k, 0)
        stats['unknown'] = r.get('unknown', False)
        r.update(stats)
        r['t'] = round(time.time() - t0, 5)
        return r

    data = []
    for jobs in comps:
        sub, gjobs, gmachs = subinstance(inst, jobs)
        data.append(dict(sub=sub, jobs=gjobs, machines=gmachs,
                         sig=signature(sub)))
    classes = []
    for cd in data:
        hit = None
        for cl in classes:
            if cl['sig'] != cd['sig']:
                continue
            stats['iso_checks'] += 1
            got = find_isomorphism(cl['rep']['sub'], cd['sub'])
            if got is not None:
                hit = (cl, got)
                break
        if hit is None:
            classes.append(dict(rep=cd, members=[], sig=cd['sig']))
            classes[-1]['members'].append((cd, None))
        else:
            cl, got = hit
            cl['members'].append((cd, got))
    stats['iso_classes'] = len(classes)
    stats['iso_saved'] = len(data) - len(classes)

    results = {}
    for ci, cl in enumerate(classes):
        rep = cl['rep']
        r = pact_decide(rep['sub'], h, depthcap=depthcap,
                        nodecap=nodecap, seed=seed)
        results[ci] = r
        for k in ('nodes', 'leaves', 'depth', 'lp_solves', 'cert_lp'):
            stats[k] += r.get(k, 0)
        if r.get('unknown'):
            stats['unknown'] = True
        if r['verdict'] is False:
            # any NO component proves the whole instance NO
            target, got = cl['members'][0]
            if got is None or target is rep:
                proof = ComponentProof(inst, h, target['jobs'],
                                       sub_proof=r['proof'], stats=stats)
            else:
                # got is rep -> target; invert to target -> rep
                j_rt, m_rt = got
                j_t2r = {target['jobs'][j]: rep['jobs'][i]
                         for i, j in j_rt.items()}
                m_t2r = {target['machines'][mk]: rep['machines'][k]
                         for k, mk in m_rt.items()}
                proof = ComponentProof(inst, h, target['jobs'],
                                       rep_jobs=rep['jobs'],
                                       sub_proof=r['proof'],
                                       job_map=j_t2r,
                                       machine_map=m_t2r,
                                       stats=stats)
            if not proof.audit_rdf():
                stats['unknown'] = True
                return dict(verdict=None, proof=None, schedule=None,
                            machine=None, **stats,
                            t=round(time.time() - t0, 5))
            return dict(verdict=False, proof=proof, schedule=None,
                        machine=None, **stats,
                        t=round(time.time() - t0, 5))

    # no NO component: combine YES components
    starts = [None] * inst['n']
    machs = [None] * inst['n']
    all_yes = True
    for ci, cl in enumerate(classes):
        r = results[ci]
        if r['verdict'] is not True:
            all_yes = False
            continue
        rep = cl['rep']
        s_rep = r['schedule']
        m_rep = r['machine']
        for target, got in cl['members']:
            if got is None:
                # representative itself
                j_rt = {i: i for i in range(rep['sub']['n'])}
                m_rt = {k: k for k in range(rep['sub']['m'])}
            else:
                j_rt, m_rt = got
            inv_j = {j: i for i, j in j_rt.items()}
            for j_local, gj in enumerate(target['jobs']):
                i_local = inv_j[j_local]
                starts[gj] = s_rep[i_local]
                mk_local = m_rt[m_rep[i_local]]
                machs[gj] = target['machines'][mk_local]
    if all_yes:
        cmax = max(starts[i] + inst['p'][i] for i in range(inst['n']))
        if cmax <= h and check_schedule(inst, h, starts, machs):
            return dict(verdict=True, proof=None, schedule=starts,
                        machine=machs, **stats,
                        t=round(time.time() - t0, 5))
        stats['unknown'] = True
    return dict(verdict=None, proof=None, schedule=None, machine=None,
                **stats, t=round(time.time() - t0, 5))


# --------------------------------------------------------------- GRAFT-ALC
class GRAFT(PACT):
    def __init__(self, inst, graft_on=True, graft_iso=True,
                 graft_decompose=True, **kw):
        super().__init__(inst, **kw)
        self.graft_on = graft_on
        self.graft_iso = graft_iso
        self.graft_decompose = graft_decompose
        self.graft_stats = []
        self.stats.update(graft_calls=0, graft_no=0, graft_yes=0,
                          graft_unknown=0, graft_iso_saved=0,
                          graft_components=0)

    def _probe(self, h):
        if not self.graft_on:
            return super()._probe(h)
        r = graft_decide(self.inst, h,
                         depthcap=self.pact_depth if self.pact_mode == 'param' else None,
                         nodecap=self.pact_nodecap,
                         iso_on=self.graft_iso,
                         decompose_on=self.graft_decompose)
        self.stats['graft_calls'] += 1
        self.stats['graft_iso_saved'] += r.get('iso_saved', 0)
        self.stats['graft_components'] += r.get('components', 1)
        self.pact_lp += r.get('lp_solves', 0)
        self.pact_cert_lp += r.get('cert_lp', 0)
        self.pact_nodes += r.get('nodes', 0)
        self.graft_stats.append({k: r.get(k) for k in
                                 ('components', 'iso_classes', 'iso_saved',
                                  'iso_checks', 'nodes', 'lp_solves',
                                  'cert_lp', 'depth', 't')})
        if r['verdict'] is False:
            self.pact_no += 1
            self.stats['pact_no'] += 1
            self.stats['graft_no'] += 1
            self._record_proof(r['proof'])
            self.steps.append(dict(h=h, v=False, proof=r['proof'],
                                   engine='graft'))
            return False, r['proof']
        if r['verdict'] is True:
            self.pact_yes += 1
            self.stats['pact_yes'] += 1
            self.stats['graft_yes'] += 1
            s, m = r['schedule'], r['machine']
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='graft'))
            return True, (s, m, cmax)
        self.pact_unknown += 1
        self.stats['pact_unknown'] += 1
        self.stats['graft_unknown'] += 1
        # fall back to the complete PACT engine on the whole instance
        return super()._probe(h)


def run_graft(inst, known, name, idx, **kw):
    t0 = time.time()
    co = GRAFT(inst, **kw)
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
    r['graft'] = getattr(co, 'graft_stats', [])
    r['lns'] = getattr(co, 'lns_stats', None)
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof'] and r['total_audit']
                   and r['cert_h'] == known - 1)
    return r
