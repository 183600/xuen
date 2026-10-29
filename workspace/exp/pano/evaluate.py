import sys, json, collections
import numpy as np
sys.path[:0] = ['exp/pano']
import pano
import selector

ARMS = selector.ARMS


def load_models():
    z = np.load('exp/pano/selector_weights.npz')
    out = []
    for i in range(5):
        out.append({k: z[f'{k}_{i}'] for k in
                    ('W1', 'b1', 'W2', 'b2', 'mu', 'sd', 'ym', 'ys')})
    return out


def load_synth():
    d = json.load(open('exp/pano/arms_synth.json'))
    by = collections.defaultdict(dict)
    for r in d['rows']:
        if r['arm'] in ARMS:
            by[r['idx']][r['arm']] = r
    return by


def load_corpus():
    d = json.load(open('exp/pano/arms_252.json'))
    by = collections.defaultdict(dict)
    for r in d['rows']:
        if r['arm'] in ARMS:
            key = (r.get('name'), r.get('idx'), r.get('known'),
                   tuple(r.get('features', [])))
            by[key][r['arm']] = r
    out = []
    for key, dd in by.items():
        if all(a in dd for a in ARMS):
            out.append((key, dd))
    return out


def area_of(front_pts, cmax):
    f = sorted(front_pts, key=lambda x: x[1])
    a = 0.0
    for i, (g, c) in enumerate(f):
        nxt = f[i + 1][1] if i + 1 < len(f) else cmax
        a += max(0, nxt - c) * g
    return a


def prune(pts):
    pts = sorted(pts)
    out = []
    best = 10 ** 9
    for g, c in pts:
        if c < best:
            out.append((g, c))
            best = c
    return out


def front_area(dd, arm, cmax):
    pts = [(int(s['U']) - int(s['L']), int(s['cost']))
           for s in dd[arm]['snapshots']]
    g0 = max(1, int(dd[arm]['ub0']) - int(dd[arm]['lb0']))
    return area_of(prune(pts), cmax) / g0


def oracle_area(dd, cmax):
    pts = []
    for a in ARMS:
        pts += [(int(s['U']) - int(s['L']), int(s['cost']))
                for s in dd[a]['snapshots']]
    g0 = max(1, int(dd[ARMS[0]]['ub0']) - int(dd[ARMS[0]]['lb0']))
    return area_of(prune(pts), cmax) / g0


def pick_synth(gap, oof, ood, thr):
    if ood > thr:
        return 0
    return int(np.argmin(oof))


def pick_corpus(gap, pred, ood, thr):
    if ood > thr:
        return 0
    return int(np.argmin(pred))


def main():
    models = load_models()
    syn = load_synth()
    sd = json.load(open('exp/pano/selector_synth.json'))
    oof = np.array(sd['oof'])
    sgap = np.array(sd['gap'])
    sood = np.array(sd['ood'])
    sthr = float(sd['ood_threshold'])
    sids = sd['seeds']
    rows = []
    for i, seed in enumerate(sids):
        dd = syn[seed]
        a = ARMS[pick_synth(sgap[i], oof[i], sood[i], sthr)]
        out = pano.simulate_portfolio(dd, [a], name='synth', idx=seed,
                                      known=dd[a]['known'])
        cmax = max(1, max(int(r['cost']) for r in dd.values()))
        rows.append(dict(idx=seed, arm=a, cost=out['total_cost'],
                         exact=out['exact'], audit=out['audit'],
                         archive=out['archive_size'],
                         area=front_area(dd, a, cmax),
                         oracle_area=oracle_area(dd, cmax),
                         lf_cost=dd['single-lower-first']['cost'],
                         bin_cost=dd['single-binary']['cost'],
                         best_cost=min(dd[x]['cost'] for x in ARMS)))
    sm = dict(
        n=len(rows),
        total_cost=sum(r['cost'] for r in rows),
        mean_cost=float(np.mean([r['cost'] for r in rows])),
        lf_total=sum(r['lf_cost'] for r in rows),
        bin_total=sum(r['bin_cost'] for r in rows),
        oracle_total=sum(r['best_cost'] for r in rows),
        area=float(np.mean([r['area'] for r in rows])),
        oracle_area=float(np.mean([r['oracle_area'] for r in rows])),
        exact=sum(r['exact'] for r in rows),
        audit=sum(r['audit'] for r in rows),
        mean_archive=float(np.mean([r['archive'] for r in rows])),
        picks=dict(collections.Counter(r['arm'] for r in rows)),
    )

    cor = load_corpus()
    cd = json.load(open('exp/pano/selector_corpus.json'))
    pred = np.array(cd['pred'])
    cgap = np.array(cd['gap'])
    cood = np.array(cd['ood'])
    cthr = float(cd['ood_threshold'])
    held = [dd for key, dd in cor
            if dd[ARMS[0]].get('name') != 'synth']
    held.sort(key=lambda dd: (dd[ARMS[0]].get('name', ''),
                              dd[ARMS[0]].get('idx', 0),
                              dd[ARMS[0]].get('known', 0)))
    rows2 = []
    for i, dd in enumerate(held):
        a = ARMS[pick_corpus(cgap[i], pred[i], cood[i], cthr)]
        out = pano.simulate_portfolio(dd, [a], name=dd[a].get('name', ''),
                                      idx=dd[a].get('idx', 0),
                                      known=dd[a].get('known'))
        rows2.append(dict(name=dd[a].get('name'), idx=dd[a].get('idx'),
                          arm=a, cost=out['total_cost'], exact=out['exact'],
                          audit=out['audit'], archive=out['archive_size'],
                          lf_cost=dd['single-lower-first']['cost'],
                          best_cost=min(dd[x]['cost'] for x in ARMS)))
    cm = dict(
        n=len(rows2),
        total_cost=sum(r['cost'] for r in rows2),
        mean_cost=float(np.mean([r['cost'] for r in rows2])),
        lf_total=sum(r['lf_cost'] for r in rows2),
        oracle_total=sum(r['best_cost'] for r in rows2),
        exact=sum(r['exact'] for r in rows2),
        audit=sum(r['audit'] for r in rows2),
        mean_archive=float(np.mean([r['archive'] for r in rows2])),
        picks=dict(collections.Counter(r['arm'] for r in rows2)),
    )
    with open('exp/pano/eval.json', 'w') as f:
        json.dump(dict(synth=sm, corpus=cm, synth_rows=rows,
                       corpus_rows=rows2), f, indent=1)
    print(json.dumps(dict(synth=sm, corpus=cm), indent=1))

    # live end-to-end spot check on a few synthetic instances
    live = []
    for seed in [10, 55, 57, 202]:
        r = [x for x in json.load(open('exp/v9i/synthetic.json'))['rows']
             if x['seed'] == seed][0]
        i = sids.index(seed)
        a = ARMS[pick_synth(sgap[i], oof[i], sood[i], sthr)]
        lr = pano.run_arm(r['inst'], r['opt'], 'synth', seed, a,
                          max_probes=64, max_leaves=64, init='chip',
                          audit=True)
        out = pano.simulate_portfolio({a: lr}, [a], name='synth', idx=seed,
                                      known=r['opt'])
        live.append(dict(seed=seed, arm=a, cost=out['total_cost'],
                         exact=out['exact'], audit=out['audit'],
                         archive=out['archive_size'], known=r['opt'],
                         L=out['L'], U=out['U']))
    with open('exp/pano/eval_live.json', 'w') as f:
        json.dump(live, f, indent=1)
    print('live', json.dumps(live, indent=1))


if __name__ == '__main__':
    main()
