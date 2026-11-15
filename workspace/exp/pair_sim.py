"""Synthetic mechanism check for PAIR-RAS (round 71).

NOT benchmark evidence. Isolates the mechanism behind the proposal.

A joint drive has Coulomb friction. The R70 / BELIEF-RAS nominal observation
model is viscous-only, so slow passive task data can look well explained while
the gain and viscous coefficient absorb the Coulomb term: a narrow but biased
posterior, i.e. "confidently wrong". Gazebo can host the richer model and run
a structure test offline; the PAIR layer then uses the Coulomb-augmented model
and one bounded, simulated-Fisher-information-ranked chirp on the real joint.

Part A measures parameter-functional error, 90% credible coverage, credible
width, and a "confidently wrong" rate, plus the AUC of a sign-asymmetric twin
disagreement score for detecting the stale nominal model.

Part B is the adversarial question: a twin safety certificate is only valid
if the sim-real gap is exchangeable. The conformal margin is calibrated at
delta=0 and then deployed under a negative gain bias (the twin under-estimates
the plant). The numbers are a stress test of the certificate, not a Gazebo
benchmark.

Forward model (declared, not fit):
  I q'' = k u - f_c sign(v) - f_v v
  controller: PD on a slow reference + optional chirp torque, u clipped.
  nominal model (R70): f_c = 0.  PAIR model: free (k, f_c, f_v).
"""
import json
import math
import os
import random

DT = 0.02
T = 2.5
NT = int(T / DT)
I_INERTIA = 0.5
KP, KD = 8.0, 2.0
U_CLIP = 3.0
V_MAX, Q_MAX = 3.0, 1.2
V_CERT = 0.58
WEAR_MAX = 2.0
SIG_V = 0.001

K_GRID = [0.70 + 0.060 * i for i in range(11)]
FC_GRID = [0.00 + 0.04 * i for i in range(11)]
FV_GRID = [0.00 + 0.04 * i for i in range(11)]
F_BASE = [-0.20 + 0.07 * i for i in range(11)]


def ref(t):
    return 0.15 * math.sin(2.0 * math.pi * 0.10 * t)


def ref_v(t):
    return 0.15 * 2.0 * math.pi * 0.10 * math.cos(2.0 * math.pi * 0.10 * t)


def sgn(x):
    # smooth Coulomb (regularised sign); avoids the discontinuity at v=0
    return math.tanh(x / 0.01)


def excitation(idx, t):
    amps = (0.25, 0.45, 0.65, 0.85)
    f0s = (1.0, 2.0, 3.0)
    a = amps[idx // len(f0s)]
    f0 = f0s[idx % len(f0s)]
    beta = 1.5
    return a * math.sin(2.0 * math.pi * (f0 * t + 0.5 * beta * t * t))


def simulate(theta, exc_idx=None, rng=None, add_noise=True, sim_bias=0.0):
    k, fc, fv = theta
    k *= (1.0 + sim_bias)
    fc *= (1.0 + sim_bias)
    fv *= (1.0 + sim_bias)
    q, v = 0.0, 0.0
    U, V = [], []
    peak_v, wear = 0.0, 0.0
    for i in range(NT):
        t = i * DT
        u = KP * (ref(t) - q) + KD * (ref_v(t) - v)
        if exc_idx is not None:
            u += excitation(exc_idx, t)
        u = max(-U_CLIP, min(U_CLIP, u))
        # log the state BEFORE the update so U[i], V[i] are time-aligned
        U.append(u)
        V.append(v if (not add_noise or rng is None)
                 else v + rng.gauss(0.0, SIG_V))
        a = (k * u - fc * sgn(v) - fv * v) / I_INERTIA
        v = v + DT * a
        q = q + DT * v
        peak_v = max(peak_v, abs(v))
        wear += u * u * DT
    return {"u": U, "v": V, "peak_v": peak_v, "wear": wear}


def loglik(log, k, fc, fv):
    ll = 0.0
    u, v = log["u"], log["v"]
    for i in range(NT - 1):
        pred = v[i] + DT * (k * u[i] - fc * sgn(v[i]) - fv * v[i]) / I_INERTIA
        r = (v[i + 1] - pred) / SIG_V
        ll -= 0.5 * r * r
    return ll


def loglik_nominal(log, k, f):
    ll = 0.0
    u, v = log["u"], log["v"]
    for i in range(NT - 1):
        pred = v[i] + DT * (k * u[i] - f * v[i]) / I_INERTIA
        r = (v[i + 1] - pred) / SIG_V
        ll -= 0.5 * r * r
    return ll


def posterior_rich(log):
    lls, mx = {}, -1e300
    for ik, k in enumerate(K_GRID):
        for ic, fc in enumerate(FC_GRID):
            for iv, fv in enumerate(FV_GRID):
                ll = loglik(log, k, fc, fv)
                lls[(ik, ic, iv)] = ll
                mx = max(mx, ll)
    post, Z = {}, 0.0
    for key, ll in lls.items():
        p = math.exp(ll - mx)
        post[key] = p
        Z += p
    return {key: p / Z for key, p in post.items()}, mx


def posterior_nominal(log):
    lls, mx = {}, -1e300
    for ik, k in enumerate(K_GRID):
        for iff, f in enumerate(F_BASE):
            ll = loglik_nominal(log, k, f)
            lls[(ik, iff)] = ll
            mx = max(mx, ll)
    post, Z = {}, 0.0
    for key, ll in lls.items():
        p = math.exp(ll - mx)
        post[key] = p
        Z += p
    return {key: p / Z for key, p in post.items()}, mx


def quantiles(ys):
    ys = sorted(ys)
    cum, q05, q50, q95 = 0.0, ys[-1][0], ys[-1][0], ys[-1][0]
    mean = 0.0
    for val, p in ys:
        mean += val * p
        prev = cum
        cum += p
        if prev < 0.05 <= cum:
            q05 = val
        if prev < 0.50 <= cum:
            q50 = val
        if prev < 0.95 <= cum:
            q95 = val
    return mean, q05, q50, q95


def functional(post, rich):
    ys = []
    for key, p in post.items():
        if p < 1e-9:
            continue
        if rich:
            k, fc, fv = K_GRID[key[0]], FC_GRID[key[1]], FV_GRID[key[2]]
            tau = k * 0.5 - fc - fv * 0.2
        else:
            k, f = K_GRID[key[0]], F_BASE[key[1]]
            tau = k * 0.5 - f * 0.2
        ys.append((tau, p))
    return quantiles(ys)


def stats(post, theta, rich):
    k, fc, fv = theta
    mean, q05, q50, q95 = functional(post, rich)
    tau_true = k * 0.5 - fc - fv * 0.2
    width = q95 - q05
    ent = -sum(p * math.log(p) for p in post.values() if p > 1e-300)
    if rich:
        ik, ic, iv = max(post, key=post.get)
        est = (K_GRID[ik], FC_GRID[ic], FV_GRID[iv])
    else:
        ik, iff = max(post, key=post.get)
        est = (K_GRID[ik], F_BASE[iff])
    return {"mean": mean, "true": tau_true, "err": abs(mean - tau_true),
            "width": width, "covered": bool(q05 <= tau_true <= q95),
            "entropy": ent, "est": est, "cwm": None}


def twin_disagreement(log, post, rich):
    """Sign-asymmetric residual: a viscous-only model cannot fit a Coulomb
    term, so the mean residual on +v and -v segments separates."""
    if rich:
        k, fc, fv = post["est"]
    else:
        k, f = post["est"]
        fc, fv = 0.0, f
    u, v = log["u"], log["v"]
    rp, rm = [], []
    for i in range(NT - 1):
        pred = v[i] + DT * (k * u[i] - fc * sgn(v[i]) - fv * v[i]) / I_INERTIA
        r = v[i + 1] - pred
        if v[i] > 0.05:
            rp.append(r)
        elif v[i] < -0.05:
            rm.append(r)
    if not rp or not rm:
        return 0.0
    mp, mm = sum(rp) / len(rp), sum(rm) / len(rm)
    sp = math.sqrt(sum((x - mp) ** 2 for x in rp) / max(1, len(rp) - 1))
    sm = math.sqrt(sum((x - mm) ** 2 for x in rm) / max(1, len(rm) - 1))
    return abs(mp - mm) / (0.5 * (sp + sm) + SIG_V)


def fisher_score(theta_sim, exc_idx, sigma=SIG_V):
    eps = 1e-3
    k, fc, fv = theta_sim
    base = simulate(theta_sim, exc_idx, add_noise=False)
    sk = simulate((k + eps, fc, fv), exc_idx, add_noise=False)
    sc = simulate((k, fc + eps, fv), exc_idx, add_noise=False)
    sv = simulate((k, fc, fv + eps), exc_idx, add_noise=False)

    def sens(s):
        return [(b - a) / eps for a, b in zip(base["v"], s["v"])]
    S = [sens(sk), sens(sc), sens(sv)]
    J = [[sum(x * y for x, y in zip(S[i], S[j])) / (sigma * sigma)
          for j in range(3)] for i in range(3)]
    # log det of the (ridge-stabilised) 3x3 Fisher matrix
    a, b, c = J[0][0], J[0][1], J[0][2]
    d, e, f = J[1][1], J[1][2], J[2][2]
    det = (a * (d * f - e * e) - b * (b * f - e * c)
           + c * (b * e - d * c))
    return math.log(max(1e-9, det)), base


def choose_excitation(theta_sim, margin=1.0, v_limit=V_CERT):
    best = None
    fallback = None
    for idx in range(12):
        score, pred = fisher_score(theta_sim, idx)
        if fallback is None:
            fallback = (idx, pred["peak_v"])
        if pred["peak_v"] * margin > v_limit or pred["wear"] > WEAR_MAX:
            continue
        if best is None or score > best[0]:
            best = (score, idx, pred["peak_v"])
    if best is None:
        return fallback
    return best[1], best[2]


def sample_theta(rng):
    # draw true plants on the inference grid: this isolates model-structure
    # error from grid discretisation error.
    return (rng.choice(K_GRID[1:-1]), rng.choice(FC_GRID[1:-1]),
            rng.choice(FV_GRID[1:-1]))


def run_episode(rng, sim_bias=0.0, margin=1.0):
    theta = sample_theta(rng)
    passive = simulate(theta, None, rng=rng)
    theta_sim = tuple(x * (1.0 + sim_bias) for x in theta)
    idx, peak_pred = choose_excitation(theta_sim, margin)
    active = simulate(theta, idx, rng=rng)

    out = {"theta": theta, "active": {}}
    for tag, log in (("passive", passive), ("active", active)):
        post_n, mx_n = posterior_nominal(log)
        post_r, mx_r = posterior_rich(log)
        for name, post, rich, mx in ((f"nominal_{tag}", post_n, False, mx_n),
                                     (f"rich_{tag}", post_r, True, mx_r)):
            st = stats(post, theta, rich)
            # held-in one-step NLL of the deployed model: a stale model that
            # omits a real joint-drive term cannot drive this low
            st["cwm"] = -mx / (NT - 1)
            out[name] = st
    out["active"]["peak_real"] = active["peak_v"]
    out["active"]["peak_pred"] = peak_pred
    out["active"]["wear"] = active["wear"]
    return out


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def rate(xs):
    return sum(1 for x in xs if x) / len(xs) if xs else 0.0


def auc(scores, labels):
    pos = [s for s, y in zip(scores, labels) if y]
    neg = [s for s, y in zip(scores, labels) if not y]
    if not pos or not neg:
        return 0.0
    c = 0.0
    for p in pos:
        for n in neg:
            c += 1.0 if p > n else (0.5 if p == n else 0.0)
    return c / (len(pos) * len(neg))


def summarize(rows, name):
    rs = [r[name] for r in rows]
    cw = [(r["width"] < 0.12 and not r["covered"]) for r in rs]
    return {"tau_err": mean([r["err"] for r in rs]),
            "coverage90": rate([r["covered"] for r in rs]),
            "ci_width": mean([r["width"] for r in rs]),
            "entropy": mean([r["entropy"] for r in rs]),
            "confidently_wrong": rate(cw),
            "cwm_auc": auc([r["cwm"] for r in rs], cw)}


def param_recovery(rows, name):
    errs = []
    for r in rows:
        est = r[name]["est"]
        k, fc, fv = r["theta"]
        if len(est) == 3:
            errs.append(abs(est[0] - k) + abs(est[1] - fc) + abs(est[2] - fv))
        else:
            errs.append(abs(est[0] - k) + abs(est[1] - fv))
    return mean(errs)


def part_a(n=50, seed=7):
    rng = random.Random(seed)
    rows = [run_episode(rng) for _ in range(n)]
    out = {"n": n}
    for name in ("nominal_passive", "nominal_active",
                 "rich_passive", "rich_active"):
        out[name] = summarize(rows, name)
        out[name]["param_err"] = param_recovery(rows, name)
    scores, labels = [], []
    for name in ("nominal_passive", "nominal_active",
                 "rich_passive", "rich_active"):
        for r in rows:
            st = r[name]
            scores.append(st["cwm"])
            labels.append(st["width"] < 0.12 and not st["covered"])
    out["cwm_auc_pooled"] = auc(scores, labels)
    acts = [r["active"] for r in rows]
    out["oracle_chirp"] = {"peak_v_p95": sorted(
        [a["peak_real"] for a in acts])[max(0, int(0.95 * n) - 1)],
        "wear_max": max(a["wear"] for a in acts)}
    return out


def part_b(n_cal=40, n_test=40, seed=11, v_limit=0.28, v_safe=0.24):
    rng = random.Random(seed)
    cal_delta = 0.10
    resid = []
    for _ in range(n_cal):
        theta = sample_theta(rng)
        theta_cal = (theta[0], theta[1] * (1.0 + cal_delta), theta[2])
        idx, peak_pred = choose_excitation(theta_cal, v_limit=v_limit)
        real = simulate(theta, idx, rng=rng)
        resid.append(real["peak_v"] - peak_pred)
    resid.sort()
    q = resid[min(len(resid) - 1,
                  int(math.ceil(0.95 * len(resid))) - 1)]
    out = []
    for delta in (0.0, 0.10, 0.20, 0.35):
        nom_v, bound_v, cert_v, accepted, peaks = [], [], [], [], []
        for _ in range(n_test):
            theta = sample_theta(rng)
            # twin over-estimates friction: it under-predicts the real peak
            theta_sim = (theta[0], theta[1] * (1.0 + delta), theta[2])
            idx, peak_pred = choose_excitation(theta_sim, v_limit=v_limit)
            real = simulate(theta, idx, rng=rng)
            y = real["peak_v"]
            peaks.append(y)
            nom_v.append(y > v_safe)
            bound_v.append(y > peak_pred + q)
            ok = (peak_pred + q) <= v_safe
            accepted.append(ok)
            cert_v.append(ok and y > v_safe)
        out.append({"test_delta": delta,
                    "nominal_violation": rate(nom_v),
                    "bound_violation": rate(bound_v),
                    "certified_violation": rate(cert_v),
                    "acceptance": rate(accepted),
                    "real_peak_mean": mean(peaks)})
    return {"calibration_delta": cal_delta, "conformal_q": q,
            "v_safe": v_safe, "rows": out}


if __name__ == "__main__":
    res = {"part_a": part_a(), "part_b": part_b()}
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "pair_results.json"), "w") as f:
        json.dump(res, f, indent=2)
    print(json.dumps(res, indent=2))
