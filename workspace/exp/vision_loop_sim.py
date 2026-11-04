"""Round-16 synthetic mechanism check: CV-ANCHOR.

NOT benchmark evidence.  Isolates ONE question about the cheap visual-encoder
adaptation loop proposed this round:

  When a frozen VLA is fine-tuned on a small in-distribution (ID) robot dataset,
  the visual encoder / action readout can latch onto *nuisance* features that are
  spuriously correlated with the action on ID (background, distractor, task
  shortcuts).  This lifts ID accuracy and destroys the out-of-distribution (OOD)
  behaviour inherited from pretraining.  Can a LOW-COST adaptation (frozen
  backbone + tiny low-rank adapter) plus an *unlabelled* validation signal
  (cross-view / counterfactual-nuisance consistency) pick a better adaptation
  strength than ID-only validation?

Generative model (declared, not fit):
  latent attribute z in R^rz      (background / spurious)
  latent attribute u in R^ru      (object attribute, benign, present in OOD)
  frozen feature f0 = [s ; b]
      s = z + sig_s * xi_s        (pretrained "generalizable" channel, noisy)
      b = B z + D u + sig_b*xi_b  (nuisance channel; carries BOTH z and u)
  true action a = C z + E u + sig_a * eps
  frozen readout M0 = [sz*C, 0], sz = 1/(1+sig_s^2): uses s only -> cannot see u.
  OOD: z is replaced by fresh z_alt (background decorrelated); u, s unchanged.

  The ID task rewards reading z from b (it predicts a) and u from b (genuinely
  useful).  OOD punishes reading z from b (now noise) and still rewards u.
  => an INTERIOR optimum adaptation strength exists.

  adaptation = action readout M (RA x d) fit with anchor lam*||M-M0||^2.
  A = I + UV^T low-rank encoder adapter leaking b into the action block is
  equivalent to M gaining nuisance weights, so we optimise M directly.

Unlabelled validation signal (NO action labels):
  CV_disagree(M) = E || M f - M f_cf ||^2 ,  f_cf swaps ONLY the z-part of b
  (background view-change) holding s and D u fixed.  It is large iff the policy
  relies on the spurious z-component of b.

Selectors:
  frozen    : exact M0
  oracle    : lam* = argmin true OOD MSE        (uses OOD labels)
  IDval     : lam* = argmin held-out ID MSE     (uses ID labels)
  CV-only   : lam* = argmin CV_disagree         (NO labels)
  CV-ANCHOR : lam* = argmin [ id_val_norm + mu * cv_norm ]   (NO labels)

Also: training-time variant that adds the CV penalty to the fit itself.

Run:  PYTHONPATH=<workspace>/.pylibs python3 exp/vision_loop_sim.py
"""
import json
import math
import os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RNG = np.random.default_rng(20261104)

RZ = 3      # spurious latent (background)
RU = 3      # benign latent (object attribute)
RB = 5      # nuisance channel dim
RA = 4      # action dim
SIG_S = 1.00
SIG_B = 0.30
SIG_A = 0.25
N_TRAIN = 5000
N_VAL = 1000
N_TEST = 5000


def make_params(seed=1):
    r = np.random.default_rng(seed)
    C = r.normal(size=(RA, RZ)) / math.sqrt(RZ)
    E = r.normal(size=(RA, RU)) / math.sqrt(RU)
    B = r.normal(size=(RB, RZ)) / math.sqrt(RZ)
    D = r.normal(size=(RB, RU)) / math.sqrt(RU)
    return C, E, B, D


def sample(n, ood, P, rng):
    C, E, B, D = P
    z = rng.normal(size=(n, RZ))
    if ood:
        z_b = rng.normal(size=(n, RZ))     # decorrelated background
    else:
        z_b = z
    u = rng.normal(size=(n, RU))
    s = z + SIG_S * rng.normal(size=(n, RZ))
    b = z_b @ B.T + u @ D.T + SIG_B * rng.normal(size=(n, RB))
    f = np.concatenate([s, b], axis=1)
    a = z @ C.T + u @ E.T + SIG_A * rng.normal(size=(n, RA))
    return z, u, f, a


def frozen_readout(P):
    C, E, B, D = P
    M0 = np.zeros((RA, RZ + RB))
    M0[:, :RZ] = C / (1.0 + SIG_S ** 2)
    return M0


def counterfactual(z, f, P):
    """swap only the spurious z-part of b (background view-change)."""
    C, E, B, D = P
    r = np.random.default_rng(987654321)
    z_alt = r.normal(size=z.shape)
    g = f.copy()
    g[:, RZ:] = f[:, RZ:] - z @ B.T + z_alt @ B.T
    return g


def fit_readout(z, f, a, P, lam, cv_pen=0.0):
    d = f.shape[1]
    M0 = frozen_readout(P)
    G = f.T @ f
    rhs = f.T @ a + lam * M0.T
    Areg = lam * np.eye(d)
    if cv_pen > 0:
        f_cf = counterfactual(z, f, P)
        Dcf = f - f_cf
        Areg = Areg + cv_pen * (Dcf.T @ Dcf)
    M = np.linalg.solve(G + Areg, rhs).T
    return M


def mse(M, f, a):
    return float(np.mean(np.sum((f @ M.T - a) ** 2, axis=1)))


def errs(M, f, a):
    return np.sum((f @ M.T - a) ** 2, axis=1)


def cv_disagree(M, z, f, P):
    g = counterfactual(z, f, P)
    return float(np.mean(np.sum((f @ M.T - g @ M.T) ** 2, axis=1)))


def main():
    P = make_params()
    ztr, utr, ftr, atr = sample(N_TRAIN, False, P, RNG)
    zval, uval, fval, aval = sample(N_VAL, False, P, RNG)
    zid, uid, fid, aid = sample(N_TEST, False, P, RNG)
    zood, uood, food, aood = sample(N_TEST, True, P, RNG)

    M0 = frozen_readout(P)
    id_err0 = errs(M0, fid, aid)
    ood_err0 = errs(M0, food, aood)
    id_tau = float(np.quantile(id_err0, 0.90))   # frozen ID success ~0.90
    ood_tau = float(np.quantile(ood_err0, 0.30))  # frozen OOD success ~0.30
    frozen = {
        "lam": float("inf"), "id": mse(M0, fid, aid), "ood": mse(M0, food, aood),
        "id_val": mse(M0, fval, aval), "cv": cv_disagree(M0, zval, fval, P),
        "id_succ": float(np.mean(id_err0 < id_tau)),
        "ood_succ": float(np.mean(ood_err0 < ood_tau)),
    }

    lam_grid = np.concatenate([[0.0], np.logspace(-3, 4, 56)])
    rows = [frozen]
    for lam in lam_grid:
        M = fit_readout(ztr, ftr, atr, P, lam)
        ie, oe = errs(M, fid, aid), errs(M, food, aood)
        rows.append({
            "lam": float(lam), "id": mse(M, fid, aid), "ood": mse(M, food, aood),
            "id_val": mse(M, fval, aval), "cv": cv_disagree(M, zval, fval, P),
            "id_succ": float(np.mean(ie < id_tau)),
            "ood_succ": float(np.mean(oe < ood_tau)),
        })

    def norm(x):
        x = np.asarray(x, float)
        return (x - x.min()) / (x.max() - x.min() + 1e-12)

    idn = norm([r["id_val"] for r in rows])
    cvn = norm([r["cv"] for r in rows])

    oracle = min(rows, key=lambda r: r["ood"])
    idval = min(rows, key=lambda r: r["id_val"])
    cvonly = min(rows, key=lambda r: r["cv"])
    picks = {}
    for mu in [0.0, 0.25, 0.5, 1.0, 2.0]:
        picks[mu] = rows[int(np.argmin(idn + mu * cvn))]

    # training-time CV penalty (no anchor, lam fixed small) ablation
    pen_rows = []
    for cv_pen in [0.0, 1.0, 10.0, 100.0, 1000.0]:
        M = fit_readout(ztr, ftr, atr, P, lam=0.0, cv_pen=cv_pen)
        ie, oe = errs(M, fid, aid), errs(M, food, aood)
        pen_rows.append({
            "cv_pen": cv_pen, "id": mse(M, fid, aid), "ood": mse(M, food, aood),
            "cv": cv_disagree(M, zval, fval, P),
            "id_succ": float(np.mean(ie < id_tau)),
            "ood_succ": float(np.mean(oe < ood_tau)),
        })

    # iterative validation: mu unknown; ramp until OOD proxy plateaus
    traj = []
    mu = 0.0
    prev = None
    for it in range(7):
        r = rows[int(np.argmin(idn + mu * cvn))]
        traj.append({"iter": it, "mu": mu, "lam": r["lam"], "id_succ": r["id_succ"],
                     "ood_succ": r["ood_succ"], "ood_mse": r["ood"], "cv": r["cv"]})
        if prev is not None and abs(r["ood"] - prev) < 1e-3:
            break
        prev = r["ood"]
        mu = 0.25 if mu == 0.0 else mu * 2.0

    def brief(r):
        return {k: r[k] for k in ("lam", "id", "ood", "id_val", "cv",
                                  "id_succ", "ood_succ")}

    out = {
        "config": {"RZ": RZ, "RU": RU, "RB": RB, "RA": RA, "SIG_S": SIG_S,
                   "SIG_B": SIG_B, "SIG_A": SIG_A, "N_TRAIN": N_TRAIN,
                   "N_VAL": N_VAL, "N_TEST": N_TEST, "id_tau": id_tau,
                   "ood_tau": ood_tau, "seed": 20261104},
        "note": "B-level synthetic mechanism check; not robot evidence",
        "curve": rows,
        "selectors": {
            "frozen": brief(frozen), "oracle_ood": brief(oracle),
            "idval": brief(idval), "cv_only": brief(cvonly),
            "cv_anchor": {str(m): brief(r) for m, r in picks.items()},
        },
        "cv_penalty_ablation": pen_rows,
        "iterative_trajectory": traj,
    }
    with open(os.path.join(HERE, "vision_loop_results.json"), "w") as fh:
        json.dump(out, fh, indent=1)

    print("id_tau=%.3f ood_tau=%.3f" % (id_tau, ood_tau))
    print("%-18s %9s %7s %8s %8s" % ("selector", "lam", "id_succ", "ood_succ", "cv"))
    for nm, r in [("frozen", frozen), ("oracle_ood", oracle), ("idval", idval),
                  ("cv_only", cvonly)] + [("cv_anchor(mu=%s)" % m, picks[m])
                                          for m in picks]:
        print("%-18s %9.3f %7.3f %8.3f %8.4f" % (nm, r["lam"], r["id_succ"],
                                                  r["ood_succ"], r["cv"]))
    print("-- training-time CV penalty (lam=0) --")
    for r in pen_rows:
        print("cv_pen=%-8g id=%.3f ood=%.3f cv=%.4f" %
              (r["cv_pen"], r["id_succ"], r["ood_succ"], r["cv"]))
    print("-- iterative trajectory --")
    for t in traj:
        print(t)


if __name__ == "__main__":
    main()
