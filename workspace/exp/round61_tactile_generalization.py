"""TACT-G round-61 synthetic mechanism check.

NOT benchmark evidence / NOT real-robot data. This is a declared generative
model used only to (a) check the sign and magnitude of the claims made in
research.md round 61, and (b) expose the failure regime that motivates TND-T.
See artifact section 5.

Model
  true slip margin        m = mu - f
  tactile slip precursor  y = g * (-m/tau) + eps,  eps ~ N(0, sigma(mu))
  tactile estimate        m_hat = -tau * y / g_hat
  conformal bound         m_lb = m_hat - q_{1-alpha}
  certificate             m* = m_hat - q - L_T*d_T - lambda_u*u
  u (epistemic)           std over W repeated tactile frames of the same contact

Three distribution regimes (InDist / moderate OOD / severe OOD), a cross-finger
gain-shift test with 5-shot calibration, and an anchor-growth curve.
"""
import json
import numpy as np

TAU = 0.10
rng = np.random.default_rng(0)


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def q_hi(x, q):
    return np.quantile(x, q, method="higher")


def gen(n, mu_lo, mu_hi, rho_lo=0.1, rho_hi=1.0, sigma_lo=0.05, sigma_hi=0.05):
    mu = rng.uniform(mu_lo, mu_hi, n)
    rho = rng.uniform(rho_lo, rho_hi, n)
    k = rng.uniform(1.0, 8.0, n)
    sig = rng.uniform(sigma_lo, sigma_hi, n)
    f = rng.uniform(0.05, 0.95, n)
    return mu, rho, k, sig, f


def obs_multi(mu, rho, k, sig, f, W=8, gain=1.0):
    """Return per-contact mean slip-logit, true margin, and epistemic std u."""
    m = mu - f
    ys = np.stack([gain * (-m / TAU) + rng.normal(0, sig / TAU) for _ in range(W)], 1)
    y = ys.mean(1)
    u = TAU * ys.std(1)                 # std in margin units
    h = rho + rng.normal(0, 0.04)
    A = 1.0 + 0.45 / k + rng.normal(0, 0.02)
    return dict(m=m, y=y, u=u, h=h, A=A, f=f)


def obs_single(mu, rho, k, sig, f):
    o = obs_multi(mu, rho, k, sig, f, W=1)
    return o


def stats(safe, slip):
    return dict(
        cov=round(float(safe.mean()), 4),
        viol=round(float(slip[safe].mean()) if safe.any() else 0.0, 4),
        n=int(safe.sum()),
    )


def frontier(sev, alpha=0.05, ncal=200, ntest=800):
    global rng
    rng = np.random.default_rng(101 + sev)
    mu, rho, k, sig, f = gen(ncal, 0.55, 0.95, 0.15, 1.0, 0.05, 0.07)
    o = obs_multi(mu, rho, k, sig, f)   # W=8 gives a meaningful epistemic std u
    mh = -TAU * o["y"]
    q = q_hi(mh - o["m"], 1 - alpha)
    mu0 = mu.mean()
    zcal = np.stack([mh, o["u"]], 1)
    zmed = np.median(zcal, 0)
    zmad = np.median(np.abs(zcal - zmed), 0) + 1e-6
    zc = (zcal - zmed) / zmad

    if sev == 0:
        lohi = (0.55, 0.95, 0.15, 1.0, 0.05, 0.07)
    elif sev == 1:
        lohi = (0.35, 0.66, 0.05, 0.50, 0.07, 0.14)
    else:
        lohi = (0.15, 0.40, 0.00, 0.30, 0.12, 0.28)
    mu, rho, k, sig, f = gen(ntest, *lohi)
    o = obs_multi(mu, rho, k, sig, f)
    m, mh, u = o["m"], -TAU * o["y"], o["u"]
    z = (np.stack([mh, u], 1) - zmed) / zmad
    d = np.sqrt(((z[:, None, :] - zc[None, :, :]) ** 2).sum(-1)).min(1)
    slip = m < 0
    out = dict(
        sev=sev,
        base=stats(mu0 - f > 0.15, slip),
        conf=stats(mh - q > 0, slip),
        d_med=round(float(np.median(d)), 3),
        u_med=round(float(np.median(u)), 3),
        err=round(float(np.abs(mh - m).mean()), 4),
        err_base=round(float(np.abs(mu0 - mu).mean()), 4),
    )
    for L in (0.15, 0.30):
        out[f"geom_{L}"] = stats(mh - q - L * d > 0, slip)
    for lam in (0.5, 1.0, 1.5):
        out[f"unc_{lam}"] = stats(mh - q - lam * u > 0, slip)
    return out


def cross_sensor(alpha=0.05, ncal=200, ntest=600):
    global rng
    rng = np.random.default_rng(202)
    out = []
    for g in (1.15, 1.35, 1.60):
        mu, rho, k, sig, f = gen(ncal, 0.55, 0.95, 0.15, 1.0, 0.05, 0.07)
        o = obs_single(mu, rho, k, sig, f)
        mh = -TAU * o["y"]
        q = q_hi(mh - o["m"], 1 - alpha)

        mu, rho, k, sig, f = gen(ntest, 0.55, 0.95, 0.15, 1.0, 0.05, 0.07)
        ot = obs_multi(mu, rho, k, sig, f, W=1, gain=g)  # same objects, new pad
        slip = ot["m"] < 0
        mh_naive = -TAU * ot["y"]
        safe_naive = (mh_naive - q) > 0

        # 5-shot: deliberately well-separated, safely loaded contacts
        m5, r5, k5, s5, f5 = gen(5, 0.70, 0.95, 0.15, 1.0, 0.05, 0.07)
        f5 = rng.uniform(0.05, 0.30, 5)
        o5 = obs_multi(m5, r5, k5, s5, f5, W=8, gain=g)
        x5 = -o5["m"] / TAU
        g_hat = float((x5 @ o5["y"]) / (x5 @ x5))   # LS slope through origin
        mh_tce = -TAU * ot["y"] / g_hat
        safe_tce = (mh_tce - q) > 0
        out.append(
            dict(
                gain=g,
                g_hat=round(g_hat, 3),
                naive=stats(safe_naive, slip),
                tce=stats(safe_tce, slip),
                err_naive=round(float(np.abs(mh_naive - ot["m"]).mean()), 4),
                err_tce=round(float(np.abs(mh_tce - ot["m"]).mean()), 4),
            )
        )
    return out


def anchor_growth(alpha=0.05, npool=1200):
    global rng
    rng = np.random.default_rng(303)
    mu, rho, k, sig, f = gen(npool, 0.30, 0.95, 0.05, 1.0, 0.05, 0.10)
    o = obs_single(mu, rho, k, sig, f)
    m, mh = o["m"], -TAU * o["y"]
    out = []
    for n in (4, 8, 16, 32, 64, 128, 256, 512):
        qs, covs, viols = [], [], []
        for _ in range(40):
            idx = rng.choice(npool, n, replace=False)
            q = q_hi(mh[idx] - m[idx], 1 - alpha)
            safe = (mh - q) > 0
            st = stats(safe, m < 0)
            qs.append(q); covs.append(st["cov"]); viols.append(st["viol"])
        out.append(dict(n_anchors=n, q=round(float(np.mean(qs)), 4),
                        cov=round(float(np.mean(covs)), 4),
                        viol=round(float(np.mean(viols)), 4)))
    return out


if __name__ == "__main__":
    res = dict(
        frontier=[frontier(s) for s in (0, 1, 2)],
        cross_sensor=cross_sensor(),
        anchor_growth=anchor_growth(),
    )
    print(json.dumps(res, indent=2, ensure_ascii=False))
    with open("round61_tactile_generalization.json", "w") as fh:
        json.dump(res, fh, indent=2, ensure_ascii=False)
