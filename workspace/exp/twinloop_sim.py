"""Mechanism check for TwinLoop (round 3): closed-loop vs one-shot repair.

NOT benchmark evidence. Declared generative model, one question per block:

A. Open-loop ToolGauge (one-shot amortized prior + single cross receipt)
   vs TwinLoop (shared-bias feedback + honest variance + sequential gate
   + dwell time + rollback) under the same total probe budget.
   Metrics: bad-accept rate, MAE of accepted contracts, interval coverage,
   probes used, contract changes per spot (chattering), bias-detect round.

B. P-Quarantine v1 (q consecutive same-sign shrink residuals) vs a
   magnitude-based CUSUM / FDI on squared innovations, under an
   alternating-sign correlated bias: v1 never latches, CUSUM does.

C. Naive twin-as-prior vs gap-inflated twin prior as the twin-reality gap
   grows: naive over-accepts; inflation restores coverage at the price of
   extra probes (which is the honest trade).

Model (declared, not fit):
  latent x_i ~ N(0,1); true u_i = 0.7 x_i + N(0,0.7^2)
  prior mean m_i = 0.7 x_i + b, shared bias b ~ N(0,0.8^2)  (cross-spot correlated)
  prior claimed sd 0.45 (overconfident); real receipt y = u_i + N(0,1)
  twin mean t_i = 0.7 x_i + b_twin, b_twin ~ N(0, gap^2)
"""
import json
import math
import numpy as np

OBS_SD = 1.0
PRIOR_CLAIM_SD = 0.45
BAD = 0.6


def _post(m, v, ys):
    prec = 1.0 / v + len(ys) / OBS_SD ** 2
    mean = (m / v + sum(ys) / OBS_SD ** 2) / prec
    return mean, 1.0 / prec


def run_loop(policy, seed, n=60, T=8, budget=4 * 60, eps_cross=1.96,
             dwell=1, twin_gap=0.0):
    rng = np.random.default_rng(seed)
    x = rng.normal(0, 1, n)
    u = 0.7 * x + rng.normal(0, 0.7, n)
    b = rng.normal(0, 0.8)
    m = 0.7 * x + b
    b_twin = rng.normal(0, twin_gap) if twin_gap > 0 else 0.0
    twin_mean = 0.7 * x + b_twin

    est = m.copy()
    var = np.full(n, PRIOR_CLAIM_SD ** 2)
    ys = [[] for _ in range(n)]
    cross = [None] * n
    accepted = np.zeros(n, bool)
    accept_round = -np.ones(n, int)
    last_switch = np.full(n, -10 ** 9)
    changes = np.zeros(n, int)
    used = 0
    b_hat = 0.0
    b_var = 0.8 ** 2
    bias_detect_round = -1
    prior_corrected = False

    def do_probe(i):
        nonlocal used
        used += 1
        y = u[i] + rng.normal(0, OBS_SD)
        ys[i].append(y)
        return y

    if policy == "open":
        for i in range(n):
            if used + 4 > budget:
                break
            for _ in range(3):
                do_probe(i)
            cross[i] = u[i] + rng.normal(0, OBS_SD)
            used += 1
            pm, pv = _post(m[i], PRIOR_CLAIM_SD ** 2, ys[i])
            z = (cross[i] - pm) / math.sqrt(pv + OBS_SD ** 2)
            est[i], var[i] = pm, pv
            if abs(z) <= eps_cross:
                accepted[i] = True
                accept_round[i] = 0
                changes[i] = 1
                last_switch[i] = 0
        return _metrics(u, est, var, accepted, used, changes, bias_detect_round, n)

    # ---------------- TwinLoop: closed loop ----------------
    for t in range(T):
        # --- feedback: after first probe wave, estimate the shared bias ---
        if t == 0:
            order = rng.permutation(n)[:min(n, budget // 6)]
            for i in order:
                if used >= budget:
                    break
                do_probe(i)
                pm, pv = _post(m[i] + b_hat, PRIOR_CLAIM_SD ** 2 + b_var, ys[i])
                est[i], var[i] = pm, pv
            # innovation mean estimates the shared bias (y - m = -b + noise)
            resid = [ys[i][0] - m[i] for i in range(n) if ys[i]]
            if resid:
                # E[y - m] = -b, so adding mean(resid) removes the shared bias
                b_hat = float(np.mean(resid))
                b_var = 1.0 / len(resid) + float(np.var(resid)) / len(resid)
                prior_corrected = True
        # --- dual control: value of information per remaining probe ---
        need = np.where(~accepted)[0]
        if len(need) == 0 or used >= budget:
            break
        value = var[need] + 0.15 * np.abs(est[need] - twin_mean[need])
        order = need[np.argsort(-value)]
        wave = min(len(order), 24, budget - used)
        for i in order[:wave]:
            if used >= budget:
                break
            do_probe(i)
            pm, pv = _post(m[i] + b_hat, PRIOR_CLAIM_SD ** 2 + b_var, ys[i])
            est[i], var[i] = pm, pv
        # --- V: sequential / power-calibrated gate ---
        for i in need:
            if accepted[i] or len(ys[i]) < 2:
                continue
            pm, pv = _post(m[i] + b_hat, PRIOR_CLAIM_SD ** 2 + b_var, ys[i])
            est[i], var[i] = pm, pv
            sd = math.sqrt(pv)
            if sd > 0.38:
                continue
            # paired cross-check: hold out nothing, use latest residual as anchor
            r = ys[i][-1] - pm
            z = abs(r) / math.sqrt(pv + OBS_SD ** 2)
            if z > 2.2:
                continue
            if t - last_switch[i] < dwell:
                continue
            # hysteresis: only switch if materially better than the prior model
            if abs(pm - (m[i] + b_hat)) < 0.15 and not prior_corrected:
                continue
            accepted[i] = True
            accept_round[i] = t
            changes[i] += 1
            last_switch[i] = t
        # --- rollback: post-swap audit on a random subset ---
        acc = np.where(accepted & (accept_round == t))[0]
        for i in acc[:2]:
            if used >= budget:
                break
            y = do_probe(i)
            pm, pv = _post(m[i] + b_hat, PRIOR_CLAIM_SD ** 2 + b_var, ys[i])
            if abs(y - pm) / math.sqrt(pv + OBS_SD ** 2) > 2.6:
                accepted[i] = False
                accept_round[i] = -1
                changes[i] += 1
                est[i], var[i] = pm, pv * 1.5
        if prior_corrected and bias_detect_round < 0:
            bias_detect_round = 0
    return _metrics(u, est, var, accepted, used, changes, bias_detect_round, n)


def _metrics(u, est, var, accepted, used, changes, bias_round, n):
    acc = np.where(accepted)[0]
    if len(acc) == 0:
        return dict(accepted=0, bad_accept=np.nan, mae=np.nan,
                    coverage=np.nan, probes=used, chatter=np.nan,
                    bias_detect_round=bias_round)
    err = np.abs(est[acc] - u[acc])
    sd = np.sqrt(var[acc])
    cov = float(np.mean(err <= 1.96 * sd))
    return dict(accepted=int(len(acc)),
                bad_accept=float(np.mean(err > BAD)),
                mae=float(np.mean(err)),
                coverage=cov,
                probes=int(used),
                chatter=float(np.mean(changes[acc])),
                bias_detect_round=int(bias_round))


def exp_a(seeds=range(40)):
    rows = {"open": [], "closed": []}
    for s in seeds:
        for pol in ("open", "closed"):
            rows[pol].append(run_loop(pol, s))
    out = {}
    for pol, rr in rows.items():
        out[pol] = {k: float(np.nanmean([r[k] for r in rr]))
                    for k in ("accepted", "bad_accept", "mae", "coverage",
                              "probes", "chatter")}
    return out


def exp_b(seeds=range(200), T=30, onset=10, alt=2.0):
    """P-Quarantine v1 (3 consecutive same-sign) vs CUSUM on squared residual.

    Metrics separate false alarms on the clean prefix from post-onset delay.
    """
    v1_fa, v1_det, cusum_fa, cusum_det = [], [], [], []
    for s in seeds:
        rng = np.random.default_rng(s)
        r = rng.normal(0, 1, T)
        r[onset:] = alt * ((-1) ** np.arange(onset, T))
        # v1: q=3 consecutive same-sign, monitored from t=0
        sign, run, alarm = 0, 0, None
        for t, v in enumerate(r):
            sg = 1 if v > 0 else -1
            run = run + 1 if sg == sign else 1
            sign = sg
            if run >= 3:
                alarm = t
                break
        v1_fa.append(float(alarm is not None and alarm < onset))
        v1_det.append(float(alarm is not None and alarm >= onset))
        # CUSUM on (r^2 - 1), drift k=0.5, threshold h=12
        S, alarm = 0.0, None
        for t, v in enumerate(r):
            S = max(0.0, S + (v * v - 1.0) - 0.5)
            if S > 12.0:
                alarm = t
                break
        cusum_fa.append(float(alarm is not None and alarm < onset))
        cusum_det.append(float(alarm is not None and alarm >= onset))
    return {"v1_false_alarm": float(np.mean(v1_fa)),
            "v1_post_onset_detect": float(np.mean(v1_det)),
            "cusum_false_alarm": float(np.mean(cusum_fa)),
            "cusum_post_onset_detect": float(np.mean(cusum_det))}


def exp_c(seeds=range(40)):
    out = {}
    for gap in (0.0, 0.3, 0.6, 1.0):
        naive, infl = [], []
        for s in seeds:
            # both policies share the twin mean; only variance treatment differs
            rng = np.random.default_rng(10_000 + s)
            n = 60
            x = rng.normal(0, 1, n)
            u = 0.7 * x + rng.normal(0, 0.7, n)
            b = rng.normal(0, 0.8)
            m = 0.7 * x + b
            bt = rng.normal(0, gap) if gap > 0 else 0.0
            twin = 0.7 * x + bt
            for mode, arr in (("naive", naive), ("inflated", infl)):
                est = np.empty(n)
                var = np.empty(n)
                acc = np.zeros(n, bool)
                for i in range(n):
                    ys = [u[i] + rng.normal(0, OBS_SD) for _ in range(3)]
                    v0 = PRIOR_CLAIM_SD ** 2 if mode == "naive" else PRIOR_CLAIM_SD ** 2 + gap ** 2
                    pm, pv = _post(twin[i], v0, ys)
                    est[i], var[i] = pm, pv
                    z = abs(u[i] + rng.normal(0, OBS_SD) - pm) / math.sqrt(pv + OBS_SD ** 2)
                    acc[i] = z <= 1.96
                err = np.abs(est - u)
                sd = np.sqrt(var)
                arr.append((float(np.mean(err[acc] > BAD)) if acc.any() else np.nan,
                            float(np.mean(err[acc] <= 1.96 * sd[acc])) if acc.any() else np.nan))
        out[str(gap)] = {
            "naive_bad_accept": float(np.nanmean([a[0] for a in naive])),
            "naive_coverage": float(np.nanmean([a[1] for a in naive])),
            "inflated_bad_accept": float(np.nanmean([a[0] for a in infl])),
            "inflated_coverage": float(np.nanmean([a[1] for a in infl])),
        }
    return out


if __name__ == "__main__":
    res = {
        "declared_model": __doc__.strip().splitlines()[0],
        "A_closed_vs_open": exp_a(),
        "B_pquarantine_vs_cusum": exp_b(),
        "C_twin_gap_inflation": exp_c(),
    }
    with open("exp/twinloop_results.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print(json.dumps(res, indent=2, ensure_ascii=False))
