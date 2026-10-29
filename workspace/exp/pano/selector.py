import sys, json, math, statistics, collections
import numpy as np

sys.path[:0] = ['exp/pano']

ARMS = ['single-lower-first', 'single-lower-always',
        'single-geometric', 'single-binary']
SHORT = {'single-lower-first': 'lf', 'single-lower-always': 'la',
         'single-geometric': 'geo', 'single-binary': 'bin'}


def load_rows(path):
    d = json.load(open(path))
    by = collections.defaultdict(dict)
    for r in d['rows']:
        if r.get('arm') in ARMS:
            by[(r.get('name'), r.get('idx'), r.get('known'),
                tuple(r.get('features', [])))][r['arm']] = r
    out = []
    for key, dd in by.items():
        if all(a in dd for a in ARMS):
            out.append(dd)
    return out


def front(snaps):
    pts = [(int(s['U']) - int(s['L']), int(s['cost'])) for s in snaps]
    pts.sort()
    out = []
    best = 10 ** 9
    for g, c in pts:
        if c < best:
            out.append((g, c))
            best = c
    return out


def area_of(front_pts, cmax):
    f = sorted(front_pts, key=lambda x: x[1])
    a = 0.0
    for i, (g, c) in enumerate(f):
        nxt = f[i + 1][1] if i + 1 < len(f) else cmax
        a += max(0, nxt - c) * g
    return a


def labels(dd):
    ar = []
    co = []
    for a in ARMS:
        r = dd[a]
        f = front(r['snapshots'])
        g0 = max(1, int(r['ub0']) - int(r['lb0']))
        cmax = max(1, max(c for g, c in f))
        ar.append(area_of(f, cmax) / g0)
        co.append(int(r['cost']))
    return ar, co


def features(dd):
    return np.array(dd[ARMS[0]]['features'], dtype=float)


def train_mlp(X, Y, tr, seed, hidden=32, epochs=600, lr=1e-3):
    rng = np.random.default_rng(seed)
    Xs = X[tr]
    Ylog = np.log1p(Y)
    Ys = Ylog[tr]
    mu = Xs.mean(0)
    sd = Xs.std(0) + 1e-9
    ym = Ys.mean(0)
    ys = Ys.std(0) + 1e-9
    Xn = (X - mu) / sd
    Yn = (Ylog - ym) / ys
    W1 = rng.normal(0, 0.3, (X.shape[1], hidden))
    b1 = np.zeros(hidden)
    W2 = rng.normal(0, 0.3, (hidden, Y.shape[1]))
    b2 = np.zeros(Y.shape[1])
    params = [W1, b1, W2, b2]
    m = [np.zeros_like(p) for p in params]
    v = [np.zeros_like(p) for p in params]
    t = 0
    idx_all = np.where(tr)[0]
    for ep in range(epochs):
        idx = np.random.default_rng(seed * 10000 + ep).permutation(idx_all)
        for s in range(0, len(idx), 32):
            bi = idx[s:s + 32]
            x = Xn[bi]
            y = Yn[bi]
            h = np.maximum(0, x @ W1 + b1)
            out = h @ W2 + b2
            err = (out - y) / len(bi)
            gW2 = h.T @ err
            gb2 = err.sum(0)
            dh = (err @ W2.T) * (h > 0)
            gW1 = x.T @ dh
            gb1 = dh.sum(0)
            grads = [gW1, gb1, gW2, gb2]
            t += 1
            for j, (p, g) in enumerate(zip(params, grads)):
                m[j] = 0.9 * m[j] + 0.1 * g
                v[j] = 0.999 * v[j] + 0.001 * g * g
                p -= lr * (m[j] / (1 - 0.9 ** t)) / (
                    np.sqrt(v[j] / (1 - 0.999 ** t)) + 1e-8)
    return dict(W1=W1, b1=b1, W2=W2, b2=b2, mu=mu, sd=sd, ym=ym, ys=ys)


def predict(model, X):
    Xn = (X - model['mu']) / model['sd']
    out = np.maximum(0, Xn @ model['W1'] + model['b1']) @ model['W2'] + model['b2']
    return np.expm1(out * model['ys'] + model['ym'])


def main():
    syn = load_rows('exp/pano/arms_synth.json')
    syn.sort(key=lambda dd: (dd[ARMS[0]]['idx'], dd[ARMS[0]]['known']))
    X = np.array([features(dd) for dd in syn])
    Yarea = np.array([labels(dd)[0] for dd in syn])
    Ycost = np.array([labels(dd)[1] for dd in syn])
    seeds = np.array([dd[ARMS[0]]['idx'] for dd in syn])
    folds = seeds % 5
    mu0 = X.mean(0)
    sd0 = X.std(0) + 1e-9
    Xs0 = (X - mu0) / sd0
    loo = []
    for i in range(len(Xs0)):
        dist = np.linalg.norm(Xs0 - Xs0[i], axis=1)
        dist[i] = 1e9
        loo.append(float(dist.min()))
    loo = np.array(loo)
    ood_thr = float(np.percentile(loo, 95))

    oof = np.zeros_like(Yarea)
    models = []
    for fold in range(5):
        tr = folds != fold
        te = ~tr
        ps = []
        for s in range(3):
            m = train_mlp(X, Yarea, tr, 100 + fold + 1000 * s)
            ps.append(predict(m, X[te]))
        oof[te] = np.mean(ps, axis=0)
    pick = oof.argmin(1)
    best = Yarea.argmin(1)
    metrics = dict(
        n=len(syn),
        oof_area=float(Yarea[np.arange(len(syn)), pick].mean()),
        oracle_area=float(Yarea.min(1).mean()),
        oof_cost=float(Ycost[np.arange(len(syn)), pick].mean()),
        oracle_cost=float(Ycost.min(1).mean()),
        top1=float((pick == best).mean()),
        picks={SHORT[ARMS[i]]: int((pick == i).sum()) for i in range(len(ARMS))},
        fixed_area={SHORT[a]: float(Yarea[:, i].mean()) for i, a in enumerate(ARMS)},
        fixed_cost={SHORT[a]: float(Ycost[:, i].mean()) for i, a in enumerate(ARMS)},
        oracle_total_cost=float(Ycost.min(1).sum()),
        oof_total_cost=float(Ycost[np.arange(len(syn)), pick].sum()),
    )

    lin = np.zeros_like(Yarea)
    for fold in range(5):
        tr = folds != fold
        te = ~tr
        mu = X[tr].mean(0)
        sd = X[tr].std(0) + 1e-9
        A = np.c_[((X[tr] - mu) / sd), np.ones(tr.sum())]
        w = np.linalg.lstsq(A, Yarea[tr], rcond=None)[0]
        lin[te] = np.c_[((X[te] - mu) / sd), np.ones(te.sum())] @ w
    lp = lin.argmin(1)
    metrics['linear_area'] = float(Yarea[np.arange(len(syn)), lp].mean())
    metrics['linear_cost'] = float(Ycost[np.arange(len(syn)), lp].mean())
    metrics['linear_top1'] = float((lp == best).mean())

    knn = np.zeros_like(Yarea)
    for fold in range(5):
        tr = folds != fold
        te = ~tr
        mu = X[tr].mean(0)
        sd = X[tr].std(0) + 1e-9
        Xs = (X - mu) / sd
        for i in np.where(te)[0]:
            dist = np.linalg.norm(Xs[tr] - Xs[i], axis=1)
            nn = np.argsort(dist)[:11]
            knn[i] = Yarea[tr][nn].mean(0)
    kp = knn.argmin(1)
    metrics['knn_area'] = float(Yarea[np.arange(len(syn)), kp].mean())
    metrics['knn_cost'] = float(Ycost[np.arange(len(syn)), kp].mean())
    metrics['knn_top1'] = float((kp == best).mean())

    gap = X[:, 12] * 100
    rule_pick = np.where(gap >= 5, 2, 0)
    metrics['rule_area'] = float(Yarea[np.arange(len(syn)), rule_pick].mean())
    metrics['rule_cost'] = float(Ycost[np.arange(len(syn)), rule_pick].mean())
    metrics['rule_top1'] = float((rule_pick == best).mean())

    final = []
    for s in range(5):
        final.append(train_mlp(X, Yarea, np.ones(len(syn), bool), 5000 + s))
    np.savez('exp/pano/selector_weights.npz',
             **{f'{k}_{i}': final[i][k] for i in range(len(final))
                for k in ('W1', 'b1', 'W2', 'b2', 'mu', 'sd', 'ym', 'ys')})
    with open('exp/pano/selector_synth.json', 'w') as f:
        json.dump(dict(metrics=metrics, oof=oof.tolist(),
                       yarea=Yarea.tolist(), ycost=Ycost.tolist(),
                       seeds=seeds.tolist(),
                       gap=(X[:, 12] * 100).tolist(), ood=loo.tolist(),
                       ood_threshold=ood_thr), f, indent=1)
    print(json.dumps(metrics, indent=1))

    # zero-shot on deduplicated corpus, excluding synth rows
    cor = load_rows('exp/pano/arms_252.json')
    held = []
    for dd in cor:
        if dd[ARMS[0]].get('name') == 'synth':
            continue
        held.append(dd)
    held.sort(key=lambda dd: (dd[ARMS[0]].get('name', ''),
                              dd[ARMS[0]].get('idx', 0),
                              dd[ARMS[0]].get('known', 0)))
    Xh = np.array([features(dd) for dd in held])
    Yha = np.array([labels(dd)[0] for dd in held])
    Yhc = np.array([labels(dd)[1] for dd in held])
    ph = np.mean([predict(m, Xh) for m in final], axis=0)
    hp = ph.argmin(1)
    Xhs0 = (Xh - mu0) / sd0
    oodh = np.array([float(np.linalg.norm(Xs0 - Xhs0[i], axis=1).min())
                     for i in range(len(Xhs0))])
    hbest = Yha.argmin(1)
    hm = dict(
        n=len(held),
        selector_area=float(Yha[np.arange(len(held)), hp].mean()),
        oracle_area=float(Yha.min(1).mean()),
        selector_cost=float(Yhc[np.arange(len(held)), hp].mean()),
        oracle_cost=float(Yhc.min(1).mean()),
        top1=float((hp == hbest).mean()),
        picks={SHORT[ARMS[i]]: int((hp == i).sum()) for i in range(len(ARMS))},
        fixed_area={SHORT[a]: float(Yha[:, i].mean()) for i, a in enumerate(ARMS)},
        fixed_cost={SHORT[a]: float(Yhc[:, i].mean()) for i, a in enumerate(ARMS)},
        selector_total_cost=float(Yhc[np.arange(len(held)), hp].sum()),
        oracle_total_cost=float(Yhc.min(1).sum()),
    )
    with open('exp/pano/selector_corpus.json', 'w') as f:
        json.dump(dict(metrics=hm, pred=ph.tolist(),
                       yarea=Yha.tolist(), ycost=Yhc.tolist(),
                       gap=(Xh[:, 12] * 100).tolist(), ood=oodh.tolist(),
                       ood_threshold=ood_thr), f, indent=1)
    print(json.dumps(hm, indent=1))


if __name__ == '__main__':
    main()
