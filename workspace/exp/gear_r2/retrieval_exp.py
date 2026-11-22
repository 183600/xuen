import numpy as np, collections, json, time
from scipy.stats import spearmanr
from scipy.cluster.vq import kmeans2
from loader import load_episodes

rng = np.random.default_rng(0)
H = 10          # horizon (frames, 30fps -> 0.33s)
VEL_LAG = 3
BANK_STRIDE = 2
QUERY_STRIDE = 3
K = 12

def build(eps):
    Xs, Ys, groups = [], [], []
    for e in eps:
        X, Y, n = e['X'], e['Y'], e['n']
        if n <= H + VEL_LAG: continue
        V = np.zeros_like(X); V[VEL_LAG:] = X[VEL_LAG:] - X[:-VEL_LAG]
        F = np.concatenate([X, V], axis=1)                     # state+velocity features
        t = np.arange(VEL_LAG, n - H)
        Xs.append(F[t]); Ys.append(Y[t + H] - Y[t]); groups.append([(e['task'], e['ep'])] * len(t))
    return np.concatenate(Xs), np.concatenate(Ys), np.concatenate(groups)

def split_episodes(eps, test_tasks=None, frac=0.2):
    tr, te = [], []
    if test_tasks is not None:
        for e in eps:
            (te if e['task'] in test_tasks else tr).append(e)
        return tr, te
    bytask = collections.defaultdict(list)
    for e in eps: bytask[e['task']].append(e)
    for t, es in bytask.items():
        es = list(es); rng.shuffle(es)
        nte = max(1, int(round(len(es) * frac)))
        te += es[:nte]; tr += es[nte:]
    return tr, te

def standardize(Ftr, Fte):
    mu = Ftr.mean(0); sd = Ftr.std(0) + 1e-6
    return (Ftr - mu) / sd, (Fte - mu) / sd

def knn_predict(Fb, Yb, Fq, Yq, clusters_b=None, clusters_q=None, K=K):
    d = ((Fq[:, None, :] - Fb[None, :, :]) ** 2).sum(-1)
    if clusters_b is not None:
        mask = clusters_q[:, None] != clusters_b[None, :]
        d = np.where(mask, np.inf, d)
    idx = np.argpartition(d, K, axis=1)[:, :K]
    dd = np.take_along_axis(d, idx, axis=1)
    w = np.exp(-(dd - dd[:, :1]) / (dd[:, :1] + 1e-6))      # scale-free softmax
    w = w / w.sum(1, keepdims=True)
    yhat = np.einsum('qk,qkd->qd', w, Yb[idx])
    var = np.einsum('qk,qkd->qd', w, (Yb[idx] - yhat[:, None, :]) ** 2).sum(1)
    return yhat, var, idx

def r2(Y, P):
    mse = ((Y - P) ** 2).sum(1).mean()
    base = (Y ** 2).sum(1).mean()
    return 1 - mse / base, mse, base

def ridge_fit(F, Y, lam=1.0):
    A = np.concatenate([F, np.ones((len(F), 1))], 1)
    W = np.linalg.solve(A.T @ A + lam * np.eye(A.shape[1]), A.T @ Y)
    return W

def ridge_pred(W, F):
    return np.concatenate([F, np.ones((len(F), 1))], 1) @ W

def run(name, tr_eps, te_eps):
    Ftr, Ytr, _ = build(tr_eps)
    Fte, Yte, gte = build(te_eps)
    Ftr, Fte = standardize(Ftr, Fte)
    Ftr_b = Ftr[::BANK_STRIDE]; Ytr_b = Ytr[::BANK_STRIDE]
    Fte_q = Fte[::QUERY_STRIDE]; Yte_q = Yte[::QUERY_STRIDE]; gq = gte[::QUERY_STRIDE]
    # ridge
    W = ridge_fit(Ftr, Ytr)
    Pr = ridge_pred(W, Fte_q)
    # kmeans gesture vocab
    km = kmeans2(Ftr_b, 24, minit='++', seed=0)
    cb, cq = km[1], km[1][np.argmin(((Fte_q[:, None, :] - km[0][None]) ** 2).sum(-1), 1)]
    # knn variants (chunked)
    def run_knn(cl=False):
        Ps, Vs = [], []
        for s in range(0, len(Fte_q), 400):
            sl = slice(s, s + 400)
            P, V, _ = knn_predict(Ftr_b, Ytr_b, Fte_q[sl], Yte_q[sl],
                                  cb if cl else None, cq[sl] if cl else None)
            Ps.append(P); Vs.append(V)
        return np.concatenate(Ps), np.concatenate(Vs)
    Pk, Vk = run_knn(False)
    Pg, Vg = run_knn(True)
    res = {'split': name, 'n_train_frames': int(len(Ftr)), 'n_query': int(len(Fte_q)),
           'mean': r2(Yte_q, np.zeros_like(Yte_q))[0],
           'ridge': r2(Yte_q, Pr)[0],
           'knn': r2(Yte_q, Pk)[0],
           'gesture_knn': r2(Yte_q, Pg)[0]}
    # uncertainty calibration for gesture-knn
    err = ((Yte_q - Pg) ** 2).sum(1)
    rho = spearmanr(Vg, err).statistic
    res['unc_err_spearman'] = float(rho)
    # task purity of top-1 raw knn
    idx = np.argpartition(((Fte_q[:800, None, :] - Ftr_b[None]) ** 2).sum(-1), 1, axis=1)[:, :1].ravel()
    _, _, gtr = build(tr_eps)
    gtr_b = gtr[::BANK_STRIDE]
    res['top1_task_purity'] = float(np.mean([gtr_b[j][0] == gq[i][0] for i, j in enumerate(idx)]))
    # contact subset: either gripper closed (<2.0); recover from raw state not in F; use Y? approximate via abs action? skip
    return res

def main():
    t0 = time.time()
    eps = load_episodes()
    tr, te = split_episodes(eps)
    out = [run('ID-episode-split', tr, te)]
    for held in [('PlugInEthernet','Unlock','DisconnectEthernet'), ('HangCup','ZipUp','FoldTowel')]:
        tr, te = split_episodes(eps, test_tasks=set(held))
        out.append(run('OOD-holdout:'+'+'.join(held), tr, te))
    print(json.dumps(out, indent=2))
    print('elapsed', round(time.time()-t0,1), 's')
    json.dump(out, open('exp/gear_r2/results.json','w'), indent=2)

if __name__ == '__main__':
    main()
