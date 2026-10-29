import sys
import copy
import json
import time

sys.path[:0] = ['exp/v9talc', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from loose import rows, init_loose
from pact import pact_decide
from talc import (check_bracket, typed_transition, stream_from_branch,
                  cmax)
from rdf import check_schedule


def corruptions(inst, z):
    L, U = z['L'], z['U']
    s, m, p = z['schedule'], z['machine'], z['proof']
    out = []
    out.append(('L+1', dict(L=L + 1, U=U, schedule=s, machine=m,
                            lb_proof=p)))
    out.append(('U-1', dict(L=L, U=U - 1, schedule=s, machine=m,
                            lb_proof=p)))
    out.append(('L>U', dict(L=U + 1, U=U, schedule=s, machine=m,
                            lb_proof=p)))
    out.append(('no-proof', dict(L=L, U=U, schedule=s, machine=m,
                                 lb_proof=None)))
    q = copy.copy(p)
    q.h = p.h + 1
    out.append(('proof-h+1', dict(L=L, U=U, schedule=s, machine=m,
                                  lb_proof=q)))
    s2 = list(s)
    s2[0] += 1
    out.append(('schedule-shift', dict(L=L, U=U, schedule=s2, machine=m,
                                       lb_proof=p)))
    s3 = list(s)
    s3[0] = -1
    out.append(('schedule-negative', dict(L=L, U=U, schedule=s3,
                                          machine=m, lb_proof=p)))
    m2 = list(m)
    m2[0] = (m2[0] + 1) % inst['m']
    out.append(('machine-flip', dict(L=L, U=U, schedule=s, machine=m2,
                                     lb_proof=p)))
    q2 = copy.deepcopy(p)
    if q2.kind == 'branch' and q2.tree[0] in ('leaf', 'empty'):
        c = q2.tree[2]
        if isinstance(c, dict):
            if c.get('alpha'):
                c['alpha'][0] += 1
            elif c.get('beta'):
                c['beta'] = []
    out.append(('proof-payload', dict(L=L, U=U, schedule=s, machine=m,
                                      lb_proof=q2)))
    return out


def main():
    t0 = time.time()
    init_ok = init_bad = 0
    trans_ok = trans_bad = 0
    probes = 0
    for k, (tag, name, idx, inst, known) in enumerate(rows()):
        z = init_loose(inst)
        if z is None:
            init_bad += 1
            continue
        ok, why = check_bracket(inst, z['L'], z['U'], z['schedule'],
                                z['machine'], z['proof'])
        if ok:
            init_ok += 1
        else:
            init_bad += 1
        if k % 5 == 0 and z['L'] < z['U']:
            h = z['L']
            r = pact_decide(inst, h, depthcap=None, nodecap=None)
            probes += 1
            new, why = typed_transition(
                inst, z['L'], z['U'], z['schedule'], z['machine'],
                z['proof'], h, r)
            if why == 'ok' or why == 'unknown':
                trans_ok += 1
            else:
                trans_bad += 1
    print('initial typed', init_ok, 'bad', init_bad)
    print('typed transitions', trans_ok, 'bad', trans_bad,
          'probes', probes)

    mut_total = mut_reject = weak_accept = 0
    valid_alt = noop = 0
    for tag, name, idx, inst, known in list(rows())[:40]:
        z = init_loose(inst)
        if z is None:
            continue
        for label, kw in corruptions(inst, z):
            if label == 'machine-flip':
                if check_schedule(inst, kw['U'], kw['schedule'],
                                  kw['machine']):
                    valid_alt += 1
                    continue
            if label == 'proof-payload':
                q = kw['lb_proof']
                if not (getattr(q, 'kind', None) == 'branch'
                        and q.tree[0] in ('leaf', 'empty')
                        and isinstance(q.tree[2], dict)
                        and (q.tree[2].get('alpha')
                             or q.tree[2].get('beta'))):
                    noop += 1
                    continue
            mut_total += 1
            ok, why = check_bracket(inst, **kw)
            mut_reject += (not ok)
            weak_accept += (kw['L'] <= kw['U'])
    print('targeted mutations', mut_total, 'typed_reject', mut_reject,
          'weak_accept', weak_accept,
          'rate', round(mut_reject / max(1, mut_total), 3),
          'valid_alt', valid_alt, 'noop', noop)

    sm_total = sm_reject = 0
    for tag, name, idx, inst, known in list(rows())[:30]:
        r = pact_decide(inst, known - 1, depthcap=None, nodecap=None)
        if r['verdict'] is not False:
            continue
        sp = stream_from_branch(r['proof'])
        if not sp.audit_rdf():
            continue
        h = sp.h
        ev = list(sp.events)
        cases = []
        if ev:
            cases.append(('truncate', ev[:-1], sp.forbid0, h))
            cases.append(('duplicate', ev + [ev[-1]], sp.forbid0, h))
        if any(e[0] == 'split' for e in ev):
            ev2 = list(ev)
            for j, e in enumerate(ev2):
                if e[0] == 'split':
                    ev2[j] = ('split', e[1], -10 ** 6)
                    break
            cases.append(('bad-split', ev2, sp.forbid0, h))
        cases.append(('bad-h', ev, sp.forbid0, h + 1))
        ev3 = copy.deepcopy(ev)
        for j, e in enumerate(ev3):
            if e[0] == 'leaf':
                c = e[1]
                if isinstance(c, dict):
                    if c.get('alpha'):
                        c['alpha'][0] += 1
                    elif c.get('beta'):
                        c['beta'] = []
                break
        cert_noop = False
        for e in ev3:
            if e[0] == 'leaf' and isinstance(e[1], dict):
                cert_noop = not (e[1].get('alpha') or e[1].get('beta'))
                break
        if cert_noop:
            cases = [c for c in cases if c[0] != 'bad-cert']
        else:
            cases.append(('bad-cert', ev3, sp.forbid0, h))
        for label, events, F0, hh in cases:
            sm_total += 1
            q = type(sp)(sp.inst, hh, events, forbid0=F0)
            if not q.audit_rdf():
                sm_reject += 1
    print('stream mutations', sm_total, 'reject', sm_reject,
          'rate', round(sm_reject / max(1, sm_total), 3))
    print('elapsed', round(time.time() - t0, 2))
    out = dict(init=[init_ok, init_bad], transitions=[trans_ok, trans_bad],
               mutation=[mut_total, mut_reject, weak_accept],
               valid_alt=valid_alt, noop=noop,
               stream_mutation=[sm_total, sm_reject])
    with open('exp/v9talc/typed_eval.json', 'w') as f:
        json.dump(out, f, indent=1)


if __name__ == '__main__':
    main()
