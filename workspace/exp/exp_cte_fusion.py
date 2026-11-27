"""Toy in-silico validation for Contact-Terrain Estimator (CTE) fusion.

Claim under test:
  With no force/tactile channel, fusing (a) proprioceptive tracking residual
  and (b) visual object-vs-gripper relative motion disambiguates contact
  states better than either channel alone, and stays usable when one channel
  is corrupted (vision occlusion / proprio calibration bias).

Generative sanity check, NOT a robot experiment: it only probes whether the
information geometry of the two signals is complementary.
"""
import numpy as np

rng = np.random.default_rng(20261127)
FREE, GRASP, SLIP, JAM = 0, 1, 2, 3
PRIOR = np.array([0.35, 0.30, 0.20, 0.15])
MU = np.array([[0.00, 0.00],   # FREE
               [0.08, 0.00],   # GRASP
               [0.12, 0.20],   # SLIP
               [0.35, 0.00]])  # JAM
SD = np.array([[0.040, 0.015],
               [0.050, 0.020],
               [0.070, 0.070],
               [0.120, 0.030]])


def sample(n):
    z = rng.choice(4, size=n, p=PRIOR)
    return z, MU[z] + SD[z] * rng.standard_normal((n, 2))


def auroc(score, pos):
    order = np.argsort(score, kind="mergesort")
    ranks = np.empty(len(score), float)
    ranks[order] = np.arange(1, len(score) + 1)
    s = score[order]
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[j + 1] == s[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + j + 2) / 2.0
        i = j + 1
    npos, nneg = pos.sum(), (~pos).sum()
    return (ranks[pos].sum() - npos * (npos + 1) / 2) / (npos * nneg)


def fit_gauss(x, z, cols=(0, 1)):
    mu, sd = {}, {}
    for c in range(4):
        xc = x[z == c][:, cols]
        mu[c] = xc.mean(0)
        sd[c] = xc.std(0) + 1e-6
    return mu, sd


def ll_of(x, mu, sd, cols):
    out = np.zeros((len(x), 4))
    for c in range(4):
        d = (x[:, cols] - mu[c]) / sd[c]
        out[:, c] = -0.5 * np.sum(d ** 2 + np.log(2 * np.pi * sd[c] ** 2), 1)
    return out


def four_class_acc(x, z, mu, sd, cols):
    return (ll_of(x, mu, sd, cols).argmax(1) == z).mean()


def main():
    ztr, xtr = sample(40000)
    zte, xte = sample(40000)
    mu2, sd2 = fit_gauss(xtr, ztr, (0, 1))
    mu1p, sd1p = fit_gauss(xtr, ztr, (0,))
    mu1v, sd1v = fit_gauss(xtr, ztr, (1,))

    # 5% FPR threshold on proprio for "abnormal" (SLIP/JAM), fit on train
    normal_tr = xtr[np.isin(ztr, [FREE, GRASP]), 0]
    tau = np.quantile(normal_tr, 0.95)

    print("=== CTE fusion toy experiment (40k train / 40k test) ===")
    print("clean 4-class acc:  proprio-only={:.3f}  vision-only={:.3f}  fused={:.3f}".format(
        four_class_acc(xte, zte, mu1p, sd1p, (0,)),
        four_class_acc(xte, zte, mu1v, sd1v, (1,)),
        four_class_acc(xte, zte, mu2, sd2, (0, 1))))

    def report(label, bias=0.0, occlude=0.0, auto_cal=False, seed=7):
        r = np.random.default_rng(seed)
        x = xte.copy()
        x[:, 0] += bias
        if auto_cal:
            # estimate the deployment-time free-space offset from FREE samples
            est = x[zte == FREE, 0].mean() - MU[FREE, 0]
            x[:, 0] -= est
        if occlude:
            m = r.random(len(x)) < occlude
            x[m, 1] = r.normal(0.0, 0.20, m.sum())
        fpr = (x[np.isin(zte, [FREE, GRASP]), 0] > tau).mean()
        sel = np.isin(zte, [GRASP, SLIP])
        post = np.exp(ll_of(x, mu2, sd2, (0, 1)) + np.log(PRIOR))
        s_slip = post[:, SLIP] / (post[:, SLIP] + post[:, GRASP] + 1e-12)
        slip_fuse = auroc(s_slip[sel], zte[sel] == SLIP)
        slip_vis = auroc(np.abs(x[sel, 1]), zte[sel] == SLIP)
        print(f"[{label}]")
        print(f"  fused 4-class acc : {four_class_acc(x, zte, mu2, sd2, (0,1)):.3f}")
        print(f"  proprio FPR@5%    : {fpr:.3f}  (tau fixed on clean train)")
        print(f"  slip AUROC        : fuse={slip_fuse:.3f}  vision-only={slip_vis:.3f}")

    report("clean")
    report("proprio bias +0.08 (uncalibrated)", bias=0.08)
    report("proprio bias +0.08 (auto-calibrated)", bias=0.08, auto_cal=True)
    report("vision occluded 30%", occlude=0.30)
    report("bias + occlusion (auto-calibrated)", bias=0.08, occlude=0.30, auto_cal=True)


if __name__ == "__main__":
    main()
