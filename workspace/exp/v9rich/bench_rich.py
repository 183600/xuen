"""Benchmark the RICH ledger: live frontier, durable certificates,
suffix-array proof archive, corruption recovery, and family retrieval.

Run from workspace/:
    .venv/bin/python exp/v9rich/bench_rich.py
"""
import collections
import json
import sys
import time

sys.path[:0] = [
    'exp/v9rich', 'exp/v9acf', 'exp/v9ai', 'exp/v9a', 'exp/v10d',
    'exp/v10b', 'exp/v9y', 'exp/v9z', 'exp/v9m', 'exp/v8u', 'exp/v8o',
    'exp/v8i', 'exp/v8h', 'exp/v8j', 'exp/v8f', 'exp/v8e', 'exp/v8g',
    'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
    'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13', 'exp/v9f']

from icf import (PACT, _choose_h, cmax, corpora, ICFCertificate,
                 PartialCertificate)
from pact import pact_decide
from rdf import check_schedule
from suffix_store import sa_doubling, lcp_kasai
import aidf
from ledger import (StateLedger, ProofLeafArchive, FrontierStateCertificate,
                    encode_state, decode_state, dumps, instance_fp,
                    leaf_certs, mutate_semantic, short_digest)


# --------------------------------------------------------------- capture
def capture_icf(inst, policy='lower-first', max_probes=64):
    """One ICF run that returns the final object and every committed state."""
    t0 = time.time()
    co = PACT(inst, pact_mode='complete', use_ga=False)
    lb, ub, sched, mach = co.initial_bounds()
    if ub is None or sched is None:
        return dict(ok=False, error='no-initial-ub', t=0.0)
    L, U = int(lb), int(ub)
    sched = list(sched)
    mach = list(mach)
    proof = co._ensure_lb_proof(L)
    if proof is None:
        r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            proof = r['proof']
    if proof is None:
        return dict(ok=False, error='no-lb-proof', t=0.0)
    states = []
    probes = lp = cert_lp = nodes = unknown = 0
    first = True
    steps = []

    def snap():
        C = PartialCertificate(inst, L, U, sched, mach, proof,
                               probe=probes)
        states.append(C)
        return C.audit_rdf()

    if not snap():
        return dict(ok=False, error='initial-audit', t=0.0)
    while L < U and probes < max_probes:
        h = _choose_h(policy, L, U, first)
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        probes += 1
        first = False
        lp += r.get('lp_solves', 0)
        cert_lp += r.get('cert_lp', 0)
        nodes += r.get('nodes', 0)
        if r['verdict'] is False:
            L = h + 1
            proof = r['proof']
            co._record_proof(proof)
            steps.append(dict(h=h, v=False, L=L, U=U))
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                sched, mach = list(s2), list(m2)
            steps.append(dict(h=h, v=True, L=L, U=U, cmax=c2))
        else:
            unknown += 1
            steps.append(dict(h=h, v=None, L=L, U=U))
            break
        if not snap():
            return dict(ok=False, error='state-audit', t=0.0)
    final = ICFCertificate(inst, U, sched, mach, proof) if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    dt = time.time() - t0
    return dict(ok=bool(final_ok), L=L, U=U, probes=probes, lp=lp,
                cert_lp=cert_lp, nodes=nodes, unknown=unknown,
                states=states, final=final,
                audit=final_ok, steps=steps,
                t=round(dt, 4), proof_kind=getattr(proof, 'kind', None))


def resume_icf(inst, state, max_probes=64):
    """Continue from a decoded PartialCertificate and audit every step."""
    L, U = state.L, state.U
    sched, mach = list(state.schedule), list(state.machine)
    proof = state.lb_proof
    probes = 0
    first = state.probe == 0
    t0 = time.time()
    while L < U and probes < max_probes:
        h = _choose_h('lower-first', L, U, first)
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        probes += 1
        first = False
        if r['verdict'] is False:
            L = h + 1
            proof = r['proof']
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                sched, mach = list(s2), list(m2)
        else:
            break
        C = PartialCertificate(inst, L, U, sched, mach, proof,
                               probe=state.probe + probes)
        if not C.audit_rdf():
            return dict(ok=False, error='resume-audit', probes=probes)
    final = (ICFCertificate(inst, U, sched, mach, proof)
             if L == U else None)
    return dict(ok=bool(final is not None and final.audit_rdf()),
                L=L, U=U, probes=probes, final=final,
                t=round(time.time() - t0, 4))


def capture_frontier(inst, budget=1024):
    """Live AID frontier at the true optimum, plus a valid final proof."""
    t0 = time.time()
    base = capture_icf(inst)
    if not base.get('ok') or base.get('final') is None:
        return dict(ok=False, error='no-icf-opt', t=0.0)
    U = int(base['U'])
    s = aidf.search(inst, U - 1, budget=budget)
    if s.verdict is not False:
        return dict(ok=False, error='aid-not-closed', L=s.local_L(),
                    U=U, t=round(time.time() - t0, 4))
    fp = s.proof()
    C = FrontierStateCertificate(inst, U, U, base['final'].schedule,
                                 base['final'].machine, fp)
    ok = bool(C.audit_rdf())
    certs = [] if fp is None else leaf_certs(fp)
    dt = time.time() - t0
    return dict(ok=ok, L=U, U=U, target=U - 1,
                leaves=len(aidf.leaves(fp.tree)) if fp else 0,
                certs=certs, cert=C,
                lp=s.stats.get('lp_solves', 0),
                cert_lp=s.stats.get('cert_lp', 0),
                splits=s.stats.get('splits', 0),
                probes=s.stats.get('nodes', 0),
                audit=ok, t=round(dt, 4))


# --------------------------------------------------------------- index
def profile_string(inst):
    toks = []
    for i in range(inst['n']):
        toks.append('p%d.e%s.p%s.s%s' % (
            inst['p'][i],
            ''.join(map(str, sorted(inst['elig'][i]))),
            ''.join(map(str, sorted(inst['pred'][i]))),
            ''.join(map(str, sorted(inst['succ'][i])))))
    return '|'.join(sorted(toks))


def family(inst):
    return (inst['n'], inst['m'], tuple(map(tuple, inst['pred'])),
            tuple(map(tuple, inst['elig'])))


def neighbour_index(rows):
    strings = [profile_string(inst) for _, _, _, inst, _ in rows]
    seq, starts, owner = [], [], []
    for k, s in enumerate(strings):
        starts.append(len(seq))
        for ch in s:
            seq.append(ord(ch))
            owner.append(k)
        seq.append(1000 + k)
        owner.append(k)
    seq.append(0)
    owner.append(-1)
    sa = sa_doubling(seq)
    lcp = lcp_kasai(seq, sa)
    rank = [0] * len(seq)
    for r, p in enumerate(sa):
        rank[p] = r
    hits = collections.Counter()
    tot = collections.Counter()
    rows_out = []
    for k, (corp, name, idx, inst, known) in enumerate(rows):
        pos = starts[k]
        r = rank[pos]
        best = (0, None)
        for nr in (r - 1, r + 1):
            if 0 <= nr < len(sa):
                h = lcp[min(r, nr)]
                src = owner[sa[nr]]
                if src != k and src >= 0 and h > best[0]:
                    best = (h, src)
        tot[corp] += 1
        same = bool(best[1] is not None
                    and family(inst) == family(rows[best[1]][3]))
        if same:
            hits[corp] += 1
        rows_out.append(dict(corpus=corp, name=name, idx=idx,
                             lcp=best[0], donor=best[1], same_family=same))
    return (dict(total=dict(tot), family_hits=dict(hits),
                 n=len(rows), sa_len=len(seq)), rows_out)


# --------------------------------------------------------------- main
def main():
    rows = list(corpora())
    out = {}

    # ---- 252 corpus: ICF states and final certificates
    t0 = time.time()
    icf = []
    ledger = StateLedger()
    archive = ProofLeafArchive()
    state_audits = state_fail = unsupported = 0
    for j, (corp, name, idx, inst, known) in enumerate(rows):
        r = capture_icf(inst)
        r['corpus'] = corp
        r['name'] = name
        r['idx'] = idx
        r['known'] = known
        if not r.get('states'):
            unsupported += 1
            icf.append(r)
            continue
        idxs = []
        for C in r['states']:
            try:
                obj = encode_state(inst, C)
                k = ledger.commit(obj)
                ok = ledger.audit_entry(inst, k)
                state_audits += 1
                if not ok:
                    state_fail += 1
                idxs.append(k)
            except Exception:
                unsupported += 1
        r['ledger_ids'] = idxs
        if r.get('final') is not None:
            for c in leaf_certs(r['final'].lb_proof):
                archive.add(c)
        icf.append(r)
        if (j + 1) % 64 == 0:
            print('icf', j + 1, '/', len(rows), flush=True)
    out['icf'] = dict(
        n=len(icf), ok=sum(bool(r.get('ok')) for r in icf),
        probes=sum(r.get('probes', 0) for r in icf),
        lp=sum(r.get('lp', 0) for r in icf),
        cert_lp=sum(r.get('cert_lp', 0) for r in icf),
        nodes=sum(r.get('nodes', 0) for r in icf),
        states=sum(len(r.get('states', [])) for r in icf),
        state_audits=state_audits, state_fail=state_fail,
        unsupported=unsupported,
        wall=round(time.time() - t0, 2))

    # ---- 16 gap-stress instances: live BAM frontier
    gap = json.load(open('exp/v10b/gap_stress.json'))
    frontier = []
    fence_ledger = StateLedger()
    f_audit = f_fail = f_unsupported = 0
    t0 = time.time()
    for rec in gap:
        inst = rec['inst']
        try:
            r = capture_frontier(inst)
        except Exception as e:
            r = dict(ok=False, error=repr(e), t=0.0)
        r['idx'] = rec['idx']
        r['known'] = rec['opt']
        if r.get('cert') is not None:
            try:
                obj = encode_state(inst, r['cert'])
                k = fence_ledger.commit(obj)
                r['audit'] = fence_ledger.audit_entry(inst, k)
                f_audit += 1
                if not r['audit']:
                    f_fail += 1
                r['ledger_id'] = k
            except Exception:
                f_unsupported += 1
            for c in r.get('certs', []):
                archive.add(c)
        frontier.append(r)
        print('frontier', rec['idx'], r.get('L'), r.get('U'),
              r.get('leaves'), r.get('t'), flush=True)
    out['frontier'] = dict(
        n=len(frontier), ok=sum(bool(r.get('ok')) for r in frontier),
        certified=sum(bool(r.get('audit')) for r in frontier),
        leaves=sum(r.get('leaves', 0) for r in frontier),
        lp=sum(r.get('lp', 0) for r in frontier),
        cert_lp=sum(r.get('cert_lp', 0) for r in frontier),
        probes=sum(r.get('probes', 0) for r in frontier),
        splits=sum(r.get('splits', 0) for r in frontier),
        audits=f_audit, audit_fail=f_fail,
        unsupported=f_unsupported,
        wall=round(time.time() - t0, 2))

    # ---- archive compression over all leaf certificates
    t0 = time.time()
    ast = archive.build()
    recon_bad = archive.reconstruct_all()
    out['archive'] = dict(certs=len(archive.certs),
                          original=ast.get('original', 0),
                          stored=ast.get('stored', 0),
                          refs=ast.get('refs', 0),
                          matches=ast.get('matches', 0),
                          ratio=round(ast.get('stored', 0)
                                      / max(1, ast.get('original', 1)), 4),
                          build=ast.get('build_t', 0.0),
                          reconstruct_bad=recon_bad,
                          wall=round(time.time() - t0, 2))

    # ---- corruption / recovery on every committed ICF state
    corrupt = dict(total=0, detected=0, missed=0,
                   restore_ok=0, restore_bad=0,
                   byte_total=0, byte_fail=0)
    for j, (corp, name, idx, inst, known) in enumerate(rows):
        r = icf[j]
        if not r.get('ledger_ids'):
            continue
        k = r['ledger_ids'][-1]
        obj = ledger.get(k)
        bad = mutate_semantic(inst, obj)
        corrupt['total'] += 1
        try:
            ok = decode_state(inst, bad).audit_rdf()
        except Exception:
            ok = False
        if ok:
            corrupt['missed'] += 1
        else:
            corrupt['detected'] += 1
        # A valid copy is still recoverable from the chain.
        back = ledger.latest_verified(inst)
        if back is not None and ledger.audit_entry(inst, back):
            corrupt['restore_ok'] += 1
        else:
            corrupt['restore_bad'] += 1
        # Raw-byte corruption: mutate one character of the JSON text.
        text = ledger.entries[k]
        pos = len(text) // 2
        ch = '0' if text[pos] != '0' else '1'
        raw = text[:pos] + ch + text[pos + 1:]
        corrupt['byte_total'] += 1
        try:
            ok2 = decode_state(inst, json.loads(raw)).audit_rdf()
        except Exception:
            ok2 = False
        if not ok2:
            corrupt['byte_fail'] += 1
    out['corruption'] = corrupt

    # ---- tiny-hash collision stress
    tiny = StateLedger(hash_bits=8)
    for j, (corp, name, idx, inst, known) in enumerate(rows[:120]):
        r = icf[j]
        if not r.get('ledger_ids'):
            continue
        tiny.commit(ledger.get(r['ledger_ids'][-1]))
    exact = 0
    for j, (corp, name, idx, inst, known) in enumerate(rows[:120]):
        r = icf[j]
        if not r.get('ledger_ids'):
            continue
        obj = ledger.get(r['ledger_ids'][-1])
        got = tiny.lookup(obj)
        if got is not None and tiny.entries[got] == dumps(obj):
            exact += 1
    out['tiny_hash'] = dict(commits=tiny.stats['commits'],
                            hits=tiny.stats['hits'],
                            collisions=tiny.stats['collisions'],
                            exact_lookups=exact)

    # ---- interruption / resume on gap instances
    inter = []
    for rec in gap:
        inst = rec['inst']
        base = capture_icf(inst)
        if not base.get('states') or len(base['states']) < 2:
            continue
        cut = max(1, min(base['probes'],
                         (base['probes'] + 1) // 2))
        obj = encode_state(inst, base['states'][cut])
        restored = decode_state(inst, obj)
        rr = resume_icf(inst, restored)
        inter.append(dict(idx=rec['idx'], base_probes=base['probes'],
                          resume_probes=rr['probes'],
                          saved=base['probes'] - rr['probes'],
                          ok=bool(rr['ok'])))
    out['resume'] = dict(
        n=len(inter), ok=sum(r['ok'] for r in inter),
        saved=sum(r['saved'] for r in inter),
        base_probes=sum(r['base_probes'] for r in inter),
        resume_probes=sum(r['resume_probes'] for r in inter),
        rows=inter)

    # ---- suffix-array family retrieval
    idx_sum, idx_rows = neighbour_index(rows)
    # gap instances are not in the 252 family index; include them as a
    # separate batch of 16 impossible-to-identify singletons.
    out['index'] = idx_sum
    out['index']['gap_singletons'] = len(gap)

    # ---- summaries
    out['summary'] = dict(
        icf=out['icf'], frontier=out['frontier'],
        archive=out['archive'], corruption=out['corruption'],
        tiny_hash=out['tiny_hash'], resume={k: v for k, v in
                                            out['resume'].items()
                                            if k != 'rows'},
        index={k: v for k, v in out['index'].items()})
    with open('exp/v9rich/bench_rich.json', 'w') as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out['summary'], indent=1, default=str))


if __name__ == '__main__':
    main()
