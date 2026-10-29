"""Experiments for TRIAD-PACT.

Outputs
-------
bench_small.json : 252 original instances, complete oracle
bench_gap.json   : held-out instances with weakened L0 (synthetic gaps)
bench_budget.json: budgeted oracle, multi-cell vs stop-on-UNK
bench_io.json    : tamper and bus rejection tests
"""
from __future__ import annotations

import json
import sys
import time
import random

sys.path[:0] = ['exp/v9tri', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

import numpy as np

from icf import corpora
from tri import prepare, run_triad, decide, open_cells
from learn import (loo_predictions, train_predictor, predict_row,
                   error_stats)
from io_spec import Evidence, EvidenceBus


POLICIES = ('lower-first', 'binary', 'predicted', 'hybrid', 'oracle')


def row_key(corpus, name, idx, j):
    return (corpus, name, idx, j)


def run_small(rows):
    insts = [r[3] for r in rows]
    targets = [(inst, known - 1) for (_, _, _, inst, known) in rows]
    loo_pred, loo_mae, lam = loo_predictions(targets)
    print('LOO ridge lambda', lam, 'mae', round(loo_mae, 4), flush=True)
    out = []
    t0 = time.time()
    for j, (corpus, name, idx, inst, known) in enumerate(rows):
        ctx = prepare(inst)
        rec = dict(corpus=corpus, name=name, idx=idx, j=j, known=known,
                   L0=ctx['L0'], U0=ctx['U0'], pred=float(loo_pred[j]),
                   pred_err=float(loo_pred[j]) - (known - 1),
                   initial_gap=ctx['U0'] - ctx['L0'],
                   upper_slack=ctx['U0'] - known,
                   init_lp=ctx['init_lp'], init_t=ctx['init_t'])
        for pol in POLICIES:
            pred = float(loo_pred[j]) if pol in ('predicted', 'hybrid') else None
            if pol == 'oracle':
                pred = known - 1
            r = run_triad(inst, known, policy=pol, pred=pred,
                          prepare_ctx=ctx, max_probes=64)
            for k in ('probes', 'rounds', 'lp', 'cert_lp', 'nodes',
                      'L', 'U', 'gap', 'certified', 'final_audit',
                      'icf_audit', 'partial_ok', 'partial_fail',
                      'partial_final', 'unknown', 'no', 'yes', 't'):
                rec['%s_%s' % (pol, k)] = r[k]
            rec['%s_audits' % pol] = r['audits']
            if pol == 'hybrid':
                rec['steps'] = r['steps']
        out.append(rec)
        if (j + 1) % 50 == 0:
            print('small', j + 1, '/', len(rows), 'wall',
                  round(time.time() - t0, 2), flush=True)
    summary = summarize(out, POLICIES)
    summary['loo_mae'] = loo_mae
    summary['lambda'] = lam
    summary['init_lp'] = sum(r['init_lp'] for r in out)
    summary['init_t'] = round(sum(r['init_t'] for r in out), 3)
    summary['initial_gap'] = round(
        sum(r['initial_gap'] for r in out) / len(out), 4)
    summary['upper_slack_instances'] = sum(
        1 for r in out if r['upper_slack'] > 0)
    json.dump(dict(rows=out, summary=summary),
              open('exp/v9tri/bench_small.json', 'w'), indent=1)
    print('small summary', summary, flush=True)
    return out, loo_pred, lam


def summarize(rows, policies):
    s = {}
    for pol in policies:
        s[pol] = dict(
            probes=sum(r['%s_probes' % pol] for r in rows),
            lp=sum(r['%s_lp' % pol] for r in rows),
            cert_lp=sum(r['%s_cert_lp' % pol] for r in rows),
            nodes=sum(r['%s_nodes' % pol] for r in rows),
            certified=sum(r['%s_certified' % pol] for r in rows),
            audit=sum(r['%s_final_audit' % pol] for r in rows),
            partial_fail=sum(r['%s_partial_fail' % pol] for r in rows),
            unknown=sum(r['%s_unknown' % pol] for r in rows),
            t=round(sum(r['%s_t' % pol] for r in rows), 3),
            avg_gap=round(sum(r['%s_gap' % pol] for r in rows) / len(rows), 4),
        )
    return dict(n=len(rows), policies=s)


def split_rows(rows, seed=0, frac=0.2):
    idx = list(range(len(rows)))
    random.Random(seed).shuffle(idx)
    ntest = max(1, int(len(rows) * frac))
    test = set(idx[:ntest])
    train = [rows[i] for i in range(len(rows)) if i not in test]
    held = [rows[i] for i in range(len(rows)) if i in test]
    return train, held


def run_gap(rows, held, train, deltas=(2, 4, 8, 16)):
    model, lam = train_predictor(
        [(inst, known - 1) for (_, _, _, inst, known) in train])
    preds = {id(inst): predict_row(model, inst) for (_, _, _, inst, _)
             in held}
    tr_y = np.asarray([known - 1 for (_, _, _, _, known) in train])
    tr_p = model.predict(np.asarray([
        __import__('learn').matrix([inst])[0]
        for (_, _, _, inst, _) in train]))
    print('gap model lambda', lam, 'train mae',
          round(float(np.abs(tr_p - tr_y).mean()), 4), flush=True)
    out = []
    t0 = time.time()
    for hi, (corpus, name, idx, inst, known) in enumerate(held):
        pred = float(preds[id(inst)])
        for delta in deltas:
            L0 = max(1, known - delta)
            if L0 >= known:
                continue
            ctx = prepare(inst, L0=L0, U0=known)
            rec = dict(corpus=corpus, name=name, idx=idx, known=known,
                       L0=ctx['L0'], U0=ctx['U0'], delta=known - L0,
                       lower_delta=known - ctx['L0'],
                       init_gap=ctx['U0'] - ctx['L0'],
                       upper_slack=ctx['U0'] - known,
                       pred=pred, pred_err=pred - (known - 1),
                       proof_kind=ctx['proof_kind'])
            for pol in POLICIES:
                p = pred if pol in ('predicted', 'hybrid') else None
                if pol == 'oracle':
                    p = known - 1
                r = run_triad(inst, known, policy=pol, pred=p,
                              prepare_ctx=ctx, max_probes=64)
                for k in ('probes', 'rounds', 'lp', 'cert_lp', 'nodes',
                          'L', 'U', 'gap', 'certified', 'final_audit',
                          'icf_audit', 'partial_ok', 'partial_fail',
                          'partial_final', 'unknown', 'no', 'yes', 't'):
                    rec['%s_%s' % (pol, k)] = r[k]
            out.append(rec)
        if (hi + 1) % 10 == 0:
            print('gap', hi + 1, '/', len(held), 'wall',
                  round(time.time() - t0, 2), flush=True)
    summary = dict(n=len(out), model_lambda=lam,
                   train_mae=round(float(np.abs(tr_p - tr_y).mean()), 4),
                   initial_gap=round(
                       sum(r['init_gap'] for r in out) / len(out), 4),
                   upper_slack_instances=sum(
                       1 for r in out if r['upper_slack'] > 0),
                   by_delta={})
    for delta in deltas:
        xs = [r for r in out if r['delta'] == delta]
        if not xs:
            continue
        summary['by_delta'][str(delta)] = summarize(xs, POLICIES)
    json.dump(dict(rows=out, summary=summary),
              open('exp/v9tri/bench_gap.json', 'w'), indent=1)
    print('gap summary', json.dumps(summary, indent=1)[:2000], flush=True)
    return out, summary


def run_single_budget(inst, ctx, pred, nodecap, max_probes, policy='hybrid'):
    """ICF-like baseline: stop at the first UNKNOWN."""
    bus = EvidenceBus(
        inst, ctx['L0'], ctx['U0'], ctx['initial'],
        ctx['base_schedule'], ctx['base_machine'], scope=ctx['scope'])
    co = ctx['co']
    lp = cert_lp = nodes = 0
    probes = 0
    while bus.L < bus.U and probes < max_probes:
        from tri import choose_pivot
        cell, v = choose_pivot(bus, policy, pred)
        if v is None:
            break
        ev, st = decide(inst, v, co, nodecap=nodecap)
        probes += 1
        lp += st['lp']
        cert_lp += st['cert_lp']
        nodes += st['nodes']
        if ev.kind == 'UNK':
            break
        ok, why = bus.submit(ev)
        if not ok:
            break
    cert = bus.certificate()
    return dict(probes=probes, lp=lp, cert_lp=cert_lp, nodes=nodes,
                L=bus.L, U=bus.U, gap=bus.U - bus.L,
                certified=bool(bus.L == bus.U),
                audit=bool(cert.audit_rdf(require_final=(bus.L == bus.U))))


def run_budget(rows, held, train, delta=8, caps=(1, 2, 4),
               max_probes=8):
    model, lam = train_predictor(
        [(inst, known - 1) for (_, _, _, inst, known) in train])
    out = []
    t0 = time.time()
    for hi, (corpus, name, idx, inst, known) in enumerate(held):
        pred = predict_row(model, inst)
        L0 = max(1, known - delta)
        if L0 >= known:
            continue
        ctx = prepare(inst, L0=L0, U0=known)
        rec = dict(corpus=corpus, name=name, idx=idx, known=known,
                   L0=L0, U0=known, pred=float(pred))
        for cap in caps:
            # triangulated: keep probing after UNK
            r = run_triad(inst, known, policy='hybrid', pred=pred,
                          prepare_ctx=ctx, max_probes=max_probes,
                          nodecap=cap)
            s = run_single_budget(inst, ctx, pred, cap, max_probes,
                                  policy='hybrid')
            rec['tri_%s' % cap] = {k: r[k] for k in
                                   ('probes', 'lp', 'L', 'U', 'gap',
                                    'certified', 'final_audit',
                                    'partial_fail', 'unknown')}
            rec['single_%s' % cap] = s
        out.append(rec)
        if (hi + 1) % 10 == 0:
            print('budget', hi + 1, '/', len(held), 'wall',
                  round(time.time() - t0, 2), flush=True)
    summary = dict(n=len(out), delta=delta, max_probes=max_probes, caps=list(caps))
    for cap in caps:
        summary[str(cap)] = dict(
            tri_gap=round(sum(r['tri_%s' % cap]['gap'] for r in out) / len(out), 3),
            single_gap=round(sum(r['single_%s' % cap]['gap'] for r in out) / len(out), 3),
            tri_probes=sum(r['tri_%s' % cap]['probes'] for r in out),
            single_probes=sum(r['single_%s' % cap]['probes'] for r in out),
            tri_unknown=sum(r['tri_%s' % cap]['unknown'] for r in out),
            tri_cert=sum(r['tri_%s' % cap]['certified'] for r in out),
            single_cert=sum(r['single_%s' % cap]['certified'] for r in out),
            tri_fail=sum(r['tri_%s' % cap]['partial_fail'] for r in out),
            single_audit=sum(r['single_%s' % cap]['audit'] for r in out),
        )
    json.dump(dict(rows=out, summary=summary),
              open('exp/v9tri/bench_budget.json', 'w'), indent=1)
    print('budget summary', summary, flush=True)
    return out, summary


def run_batch(rows, held, train, delta=16, batch=4):
    model, lam = train_predictor(
        [(inst, known - 1) for (_, _, _, inst, known) in train])
    out = []
    for corpus, name, idx, inst, known in held:
        pred = predict_row(model, inst)
        L0 = max(1, known - delta)
        if L0 >= known:
            continue
        ctx = prepare(inst, L0=L0, U0=known)
        seq = run_triad(inst, known, policy='hybrid', pred=pred,
                        prepare_ctx=ctx, max_probes=16)
        par = run_triad(inst, known, policy='batch-pred', pred=pred,
                        prepare_ctx=ctx, max_probes=16, batch=batch)
        out.append(dict(corpus=corpus, name=name, idx=idx, known=known,
                        L0=L0, U0=known, pred=float(pred),
                        seq={k: seq[k] for k in ('probes', 'rounds', 'lp',
                                                 'gap', 'certified',
                                                 'final_audit')},
                        batch={k: par[k] for k in ('probes', 'rounds', 'lp',
                                                   'gap', 'certified',
                                                   'final_audit')}))
    summary = dict(n=len(out),
                   seq_probes=sum(r['seq']['probes'] for r in out),
                   batch_probes=sum(r['batch']['probes'] for r in out),
                   seq_rounds=sum(r['seq']['rounds'] for r in out),
                   batch_rounds=sum(r['batch']['rounds'] for r in out),
                   seq_lp=sum(r['seq']['lp'] for r in out),
                   batch_lp=sum(r['batch']['lp'] for r in out),
                   seq_cert=sum(r['seq']['certified'] for r in out),
                   batch_cert=sum(r['batch']['certified'] for r in out))
    json.dump(dict(rows=out, summary=summary),
              open('exp/v9tri/bench_batch.json', 'w'), indent=1)
    print('batch summary', summary, flush=True)
    return out, summary



def run_robust(rows, held, train, delta=16):
    """A stale/extreme prediction must not change soundness or complexity."""
    model, lam = train_predictor(
        [(inst, known - 1) for (_, _, _, inst, known) in train])
    cases = [('good', None), ('none', None), ('high', 1e9), ('low', -1e9),
             ('good-1', None), ('good+1', None)]
    out = []
    for corpus, name, idx, inst, known in held:
        L0 = max(1, known - delta)
        if L0 >= known:
            continue
        ctx = prepare(inst, L0=L0, U0=known)
        base = predict_row(model, inst)
        for label, p in cases:
            pred = {'good': base, 'none': None, 'high': 1e9,
                    'low': -1e9, 'good-1': base - 1,
                    'good+1': base + 1}[label]
            r = run_triad(inst, known, policy='hybrid', pred=pred,
                          prepare_ctx=ctx, max_probes=32)
            out.append(dict(corpus=corpus, name=name, idx=idx,
                            known=known, L0=ctx['L0'], U0=ctx['U0'],
                            pred=pred, label=label,
                            probes=r['probes'], gap=r['gap'],
                            certified=r['certified'],
                            audit=r['final_audit'],
                            partial_fail=r['partial_fail'],
                            L=r['L'], U=r['U']))
    summary = {}
    for label, _ in cases:
        xs = [r for r in out if r['label'] == label]
        if not xs:
            continue
        summary[label] = dict(
            n=len(xs),
            probes=sum(r['probes'] for r in xs),
            max_probes=max(r['probes'] for r in xs),
            certified=sum(r['certified'] for r in xs),
            audit=sum(r['audit'] for r in xs),
            partial_fail=sum(r['partial_fail'] for r in xs),
            avg_gap=round(sum(r['gap'] for r in xs) / len(xs), 3))
    json.dump(dict(rows=out, summary=summary),
              open('exp/v9tri/bench_robust.json', 'w'), indent=1)
    print('robust summary', summary, flush=True)
    return out, summary

def run_io(rows):
    """Tamper and rejection tests on a valid certificate."""
    # find a non-trivial final certificate
    cert = None
    for corpus, name, idx, inst, known in rows:
        ctx = prepare(inst, L0=max(1, known - 8), U0=known)
        r = run_triad(inst, known, policy='hybrid',
                      pred=known - 1, prepare_ctx=ctx, max_probes=16)
        if r['certified'] and r['L0'] < r['U0']:
            cert = r['cert']
            inst0 = inst
            break
    if cert is None:
        json.dump(dict(error='no non-trivial certificate'), open(
            'exp/v9tri/bench_io.json', 'w'), indent=1)
        return
    import copy
    tests = []

    def check(label, obj, final=True):
        tests.append(dict(label=label,
                          audit=bool(obj.audit_rdf(require_final=final))))

    check('valid', cert)
    c = copy.deepcopy(cert); c.L += 1
    check('wrong_L', c)
    c = copy.deepcopy(cert); c.U -= 1
    check('wrong_U', c)
    c = copy.deepcopy(cert)
    if c.vertices:
        v = c.vertices[0]
        if v.kind == 'NO':
            v.h += 1
    check('shifted_NO_h', c)
    c = copy.deepcopy(cert)
    if c.schedule:
        c.schedule[0] += 1
    check('bad_schedule', c)
    c = copy.deepcopy(cert)
    if c.vertices:
        c.vertices[0].scope = 'bad-scope'
    check('bad_scope', c)
    c = copy.deepcopy(cert)
    if c.vertices:
        c.vertices.append(Evidence('UNK', c.L, scope=c.scope))
    check('UNK_at_L', c)
    # bus-level rejections
    ctx = prepare(inst0, L0=max(1, cert.L0), U0=cert.U0)
    bus = ctx['bus']
    rej = []
    ok0, _ = bus.submit(Evidence('NO', bus.L0 - 1,
                                 proof=ctx['initial'].proof,
                                 scope=ctx['scope']))
    rej.append(bus.submit(Evidence('NO', bus.L0 - 1,
                                   proof=ctx['initial'].proof,
                                   scope=ctx['scope']))[0])
    rej.append(bus.submit(Evidence('UNK', bus.U0 + 1,
                                   scope=ctx['scope']))[0])
    rej.append(bus.submit(Evidence('YES', bus.U0 + 1,
                                   schedule=[0] * inst0['n'],
                                   machine=[0] * inst0['n'],
                                   cmax=bus.U0,
                                   scope='wrong'))[0])
    summary = dict(valid_audit=tests[0]['audit'],
                   tamper_rejected=sum(1 for t in tests[1:]
                                       if not t['audit']),
                   tamper_total=len(tests) - 1,
                   bus_rejected=sum(1 for x in rej if not x),
                   bus_total=len(rej),
                   tests=tests)
    json.dump(summary, open('exp/v9tri/bench_io.json', 'w'), indent=1)
    print('io summary', summary, flush=True)


def main(which='all'):
    rows = list(corpora())
    train, held = split_rows(rows, seed=0, frac=0.2)
    print('rows', len(rows), 'train', len(train), 'held', len(held),
          flush=True)
    if which in ('all', 'small'):
        run_small(rows)
    if which in ('all', 'gap'):
        run_gap(rows, held, train)
    if which in ('all', 'budget'):
        run_budget(rows, held, train)
    if which in ('all', 'batch'):
        run_batch(rows, held, train)
    if which in ('all', 'robust'):
        run_robust(rows, held, train)
    if which in ('all', 'io'):
        run_io(rows)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'all')
