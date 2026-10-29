"""Prototype TDC-PACT: trie-guided decrease-and-conquer probe filter."""
import sys, time, collections
sys.path[:0]=['exp/v9x','exp/v91','exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from icf import PartialCertificate, ICFCertificate, cmax, _choose_h, corpora
from po import heads_tails
from rdf import check_schedule, _earliest
from pact import PACT, pact_decide
from sparc import Swarm


def _avail(inst, mask):
    return [i for i in range(inst['n'])
            if not (mask >> i) & 1
            and all((mask >> j) & 1 for j in inst['pred'][i])]


def _static_q(inst):
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    return q


def _lb_fast(inst, mask, predfin, cm, q):
    n, p = inst['n'], inst['p']
    est = list(predfin)
    # topological propagation for unscheduled jobs
    for i in range(n):
        if (mask >> i) & 1:
            continue
        e = est[i]
        for j in inst['pred'][i]:
            if not (mask >> j) & 1:
                v = est[j] + p[j]
                if v > e:
                    e = v
        est[i] = e
    lb = cm
    for i in range(n):
        if not (mask >> i) & 1:
            v = est[i] + p[i] + q[i]
            if v > lb:
                lb = v
    return lb


def _lb(inst, mask, starts, cm):
    n, p = inst['n'], inst['p']
    fin = [(starts[i] + p[i]) if (mask >> i) & 1 else 0 for i in range(n)]
    est, q = heads_tails(inst, mask, fin)
    lb = cm
    for i in range(n):
        if not (mask >> i) & 1:
            v = est[i] + p[i] + q[i]
            if v > lb:
                lb = v
    return lb


def _key(st):
    mask, starts, machs, busy, predfin, cm = st
    return (mask, tuple(tuple(x) for x in busy), tuple(predfin))


class Trie:
    def __init__(self):
        self.best = {}
        self.nodes = 0
        self.dups = 0

    def admit(self, st):
        k = _key(st)
        old = self.best.get(k)
        if old is not None:
            self.dups += 1
            if old[0] <= st[5]:
                return False
        self.best[k] = (st[5], st)
        self.nodes += 1
        return True


def _expand(inst, st, target, q=None):
    n, p = inst['n'], inst['p']
    mask, starts, machs, busy, predfin, cm = st
    out = []
    for i in _avail(inst, mask):
        base = predfin[i]
        best = None
        for k in inst['elig'][i]:
            t = _earliest(busy[k], base, p[i])
            cand = (t + p[i], t, k)
            if best is None or cand < best:
                best = cand
        if best is None:
            continue
        ft, t, k = best
        if ft > target:
            continue
        nm = mask | (1 << i)
        ns = list(starts); ns[i] = t
        nmach = list(machs); nmach[i] = k
        nb = [list(x) for x in busy]; nb[k].append((t, ft)); nb[k].sort()
        npf = list(predfin)
        for j in inst['succ'][i]:
            if ft > npf[j]:
                npf[j] = ft
        lb = _lb_fast(inst, nm, npf, max(cm, ft), q) if q is not None else _lb(inst, nm, ns, max(cm, ft))
        if lb > target:
            continue
        out.append((nm, ns, nmach, nb, npf, max(cm, ft)))
    return out


def _complete(inst, st, rank, target):
    n, p = inst['n'], inst['p']
    mask, starts, machs, busy, predfin, cm = st
    starts = list(starts); machs = list(machs)
    busy = [list(x) for x in busy]; predfin = list(predfin)
    while mask != (1 << n) - 1:
        av = _avail(inst, mask)
        if not av:
            return None
        av.sort(key=lambda i: (rank[i], i))
        i = av[0]
        base = predfin[i]
        best = None
        for k in inst['elig'][i]:
            t = _earliest(busy[k], base, p[i])
            cand = (t + p[i], t, k)
            if best is None or cand < best:
                best = cand
        if best is None:
            return None
        ft, t, k = best
        if ft > target:
            return None
        mask |= 1 << i
        starts[i] = t; machs[i] = k
        busy[k].append((t, ft)); busy[k].sort()
        for j in inst['succ'][i]:
            if ft > predfin[j]:
                predfin[j] = ft
        cm = max(cm, ft)
    return starts, machs, cm


class TDC:
    def __init__(self, inst, U, s, m, width=30, tau=4, npart=8,
                 iters=12, seed=7, nodecap=20000, stall=4):
        self.inst = inst
        self.swarm = Swarm(inst, U, s, m, n_particles=npart,
                           iters=iters, seed=seed, stall=stall)
        self.width = width
        self.tau = tau
        self.nodecap = nodecap
        self.trie = Trie()
        self.calls = 0
        self.success = 0
        self.nodes = 0
        self.rollouts = 0
        self.t = 0.0
        self.pso_evals = 0
        self.pso_t = 0.0
        self.best_cmax = U
        self.best_sched = None
        self.ranks = None
        self.q = _static_q(inst)

    def _ensure_ranks(self):
        if self.ranks is not None:
            return
        best, st = self.swarm.run()
        self.pso_evals += st['evals']
        self.pso_t += st['t']
        c, s2, m2 = best
        rank = {i: s2[i] + 1e-6 * i for i in range(self.inst['n'])}
        est, q = heads_tails(self.inst, 0, [0] * self.inst['n'])
        rank2 = {i: est[i] + 1e-6 * i for i in range(self.inst['n'])}
        self.ranks = [rank, rank2]
        self.best_cmax = min(self.best_cmax, c)
        if c <= self.best_cmax:
            self.best_sched = (list(s2), list(m2), int(c))

    def probe(self, h, timelimit=None):
        t0 = time.time()
        self.calls += 1
        self._ensure_ranks()
        if self.best_sched is not None and self.best_cmax <= h:
            self.success += 1
            self.t += time.time() - t0
            return self.best_sched
        n = self.inst['n']
        root = (0, [None] * n, [None] * n,
                [[] for _ in range(self.inst['m'])], [0] * n, 0)
        beam = [root]
        nodes = 0
        rollouts = 0
        for depth in range(n):
            if timelimit is not None and time.time() - t0 > timelimit:
                break
            cand = []
            for st in beam:
                ch = _expand(self.inst, st, h, self.q)
                nodes += len(ch)
                if nodes > self.nodecap:
                    break
                for c in ch:
                    if self.trie.admit(c):
                        cand.append(c)
            if nodes > self.nodecap or not cand:
                break
            cand.sort(key=lambda s: (_lb_fast(self.inst, s[0], s[4], s[5], self.q),
                                     s[5], s[0]))
            cand = cand[:self.width]
            for c in cand:
                for rank in self.ranks[:1]:
                    r = _complete(self.inst, c, rank, h)
                    rollouts += 1
                    if r is not None:
                        ss, mm, cc = r
                        if check_schedule(self.inst, cc, ss, mm):
                            self.success += 1
                            self.nodes += nodes
                            self.rollouts += rollouts
                            self.t += time.time() - t0
                            self.best_cmax = min(self.best_cmax, cc)
                            return ss, mm, cc
            beam = cand
        self.nodes += nodes
        self.rollouts += rollouts
        self.t += time.time() - t0
        return None


def run_tdc(inst, known, name, idx, policy='lower-first', width=30,
            tau=4, npart=8, iters=12, seed=7, nodecap=20000,
            tdc_min_gap=0, tdc_max_gap=99, max_probes=64,
            use_tdc=True, use_pact_init=True, pretest=False,
            tdc_timelimit=None):
    t0 = time.time()
    co = None
    if use_pact_init:
        co = PACT(inst, pact_mode='complete', use_ga=False)
        L, U, sched, mach = co.initial_bounds()
        L, U = int(L), int(U)
        lb_proof = co._ensure_lb_proof(L)
        pin_lp = getattr(co, 'pin_lp', 0)
    else:
        from hap import init_weak
        L, U, sched, mach, lb_proof = init_weak(inst)
        L, U = int(L), int(U)
        pin_lp = 0
    if lb_proof is None:
        r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            lb_proof = r['proof']
    if lb_proof is None or U is None:
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='no-init', t=0.0, corpus=None)
    sched = list(sched); mach = list(mach)
    tdc = TDC(inst, U, sched, mach, width=width, tau=tau,
              npart=npart, iters=iters, seed=seed, nodecap=nodecap) \
        if use_tdc else None
    probes = 0; pact_lp = 0; cert_lp = 0; nodes = 0
    partial_ok = 0; partial_fail = 0
    tdc_success = 0; tdc_calls = 0
    first = True
    lb0, ub0 = L, U
    steps = []

    def audit():
        nonlocal partial_ok, partial_fail
        pc = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1
        return pc

    audit()
    while L < U and probes < max_probes:
        L0, U0 = L, U
        h = _choose_h(policy, L, U, first)
        used_tdc = False
        r0 = None
        if pretest:
            r0 = pact_decide(inst, h, depthcap=None, nodecap=1)
            pact_lp += r0.get('lp_solves', 0)
            cert_lp += r0.get('cert_lp', 0)
            nodes += r0.get('nodes', 0)
            if r0['verdict'] is False:
                proof = r0['proof']; L = h + 1; lb_proof = proof
                if co is not None: co._record_proof(proof)
                probes += 1; first = False
                steps.append(dict(h=h, v=False, kind=proof.kind,
                                  lp=r0.get('lp_solves', 0), pre=True,
                                  L0=L0, U0=U0, L1=L, U1=U))
                audit(); continue
            if r0['verdict'] is True:
                s2, m2 = r0['schedule'], r0['machine']
                c2 = cmax(inst, s2)
                if c2 < U and check_schedule(inst, c2, s2, m2):
                    U = c2; sched = list(s2); mach = list(m2)
                probes += 1; first = False
                steps.append(dict(h=h, v=True, cmax=c2,
                                  lp=r0.get('lp_solves', 0), pre=True,
                                  L0=L0, U0=U0, L1=L, U1=U))
                audit(); continue
        if tdc is not None and (U - L) >= tdc_min_gap and (U - L) <= tdc_max_gap:
            tdc_calls += 1
            r = tdc.probe(h, timelimit=tdc_timelimit)
            if r is not None:
                s2, m2, c2 = r
                if c2 < U and check_schedule(inst, c2, s2, m2):
                    U = int(c2); sched = list(s2); mach = list(m2)
                    tdc_success += 1
                    used_tdc = True
                    steps.append(dict(h=h, v=True, cmax=c2, tdc=True,
                                      L0=L0, U0=U0, L1=L, U1=U))
                    audit()
                    first = False
                    continue
        probes += 1
        first = False
        rr = pact_decide(inst, h, depthcap=None, nodecap=None)
        pact_lp += rr.get('lp_solves', 0)
        cert_lp += rr.get('cert_lp', 0)
        nodes += rr.get('nodes', 0)
        if rr['verdict'] is False:
            proof = rr['proof']
            L = h + 1
            lb_proof = proof
            if co is not None:
                co._record_proof(proof)
            steps.append(dict(h=h, v=False, kind=proof.kind,
                              lp=rr.get('lp_solves', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
        elif rr['verdict'] is True:
            s2, m2 = rr['schedule'], rr['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2; sched = list(s2); mach = list(m2)
            steps.append(dict(h=h, v=True, cmax=c2,
                              lp=rr.get('lp_solves', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
        else:
            steps.append(dict(h=h, v=None, lp=rr.get('lp_solves', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
            audit()
            break
        audit()
    final = ICFCertificate(inst, U, sched, mach, lb_proof) if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                 probe=probes)
    partial_final = bool(partial.audit_rdf())
    dt = time.time() - t0
    return dict(
        name=name, idx=idx, known=known, policy=policy,
        opt=U, lb=L, lb0=lb0, ub0=ub0,
        certified=bool(L == U and final_ok), audit=final_ok,
        proof=final_ok, cert_h=(U - 1 if L == U else None),
        queries=probes, probes=probes,
        pact_lp=pact_lp, pact_nodes=nodes, pact_cert_lp=cert_lp,
        pin_lp=pin_lp, partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_final, tdc_calls=tdc_calls,
        tdc_success=tdc_success,
        tdc_nodes=(tdc.nodes if tdc else 0),
        tdc_rollouts=(tdc.rollouts if tdc else 0),
        tdc_t=round(tdc.t, 4) if tdc else 0.0,
        pso_evals=(tdc.pso_evals if tdc else 0),
        pso_t=round(tdc.pso_t, 4) if tdc else 0.0,
        steps=steps, total_audit=final_ok,
        t=round(dt, 4),
        ok=bool(L == U and U == known and final_ok and
                partial_fail == 0 and partial_final),
    )
