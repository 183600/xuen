#!/usr/bin/env python3
"""HEAT-RAS synthetic mechanism checks.

Four independent toy models, NOT benchmark evidence:
  A. thermal governor vs naive / static-derate duty cycles
  B. temperature-dependent backlash: cold calibration used hot
  C. value of a pre-load / take-up internal probe before precision insertion
  D. thermo-mechanical fingerprint separating bias / expansion / wear / grease

Run: PYTHONPATH=../.pylibs python3 heat_sim.py
"""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 20261114


# ---------------------------------------------------------------- A: thermal
def exp_a():
    rng = np.random.default_rng(SEED)
    C, R, T_amb, T_max, tau_peak = 8.0, 1.0, 25.0, 90.0, 30.0
    a_q = 0.09                      # W per (Nm)^2, copper + friction proxy
    n_task = 80
    dwell = 0.05
    k_move = 9.0                    # task time = k_move / tau

    def heat(tau):
        return a_q * tau * tau

    # static: pick a torque whose steady temperature keeps a 15 C margin
    q_ss = (T_max - 15.0 - T_amb) / R
    tau_static = float(np.sqrt(q_ss / a_q))

    def predict_peak(T0, tau, horizon=4.0):
        """Receding-horizon peak temperature for a repeated tau duty cycle."""
        duty = (k_move / tau) / (k_move / tau + dwell)
        q_avg = a_q * tau * tau * duty
        t_ss = T_amb + R * q_avg
        return T0 + (t_ss - T0) * (1.0 - np.exp(-horizon / (R * C)))

    def simulate(policy):
        T = T_amb
        t = 0.0
        done = 0
        over_time = 0.0
        peak = T
        taus = []
        while done < n_task and t < 300.0:
            if policy == "naive":
                tau = tau_peak
                cool = False
            elif policy == "static":
                tau = tau_static
                cool = False
            else:  # heat: pick the hottest tau whose 4 s peak stays <= 86 C
                cand = np.linspace(tau_peak, 12.0, 19)
                feasible = [x for x in cand if predict_peak(T, x) <= 86.0]
                tau = float(feasible[0]) if feasible else 0.0
                cool = tau == 0.0
            if tau == 0.0:
                dt = 0.05
                Q = 0.0
                active = False
            else:
                dt = k_move / tau
                Q = heat(tau)
                active = True
            # integrate thermal dynamics on a fine grid for stability
            steps = max(1, int(np.ceil(dt / 0.01)))
            h = dt / steps
            for _ in range(steps):
                T = T + h * (Q / C - (T - T_amb) / (R * C))
                peak = max(peak, T)
                if T > T_max:
                    over_time += h
            taus.append(tau)
            if active:
                done += 1
                dt += dwell
            t += dt
        return dict(tasks=done, time_s=round(t, 2), peak_C=round(peak, 2),
                    overtemp_s=round(over_time, 2),
                    tau_last_Nm=round(taus[-1], 2),
                    tau_mean_Nm=round(float(np.mean(taus)), 2),
                    cooldown_steps=int(sum(1 for x in taus if x == 0.0)))

    out = {
        "params": dict(C=C, R=R, T_amb=T_amb, T_max=T_max,
                       tau_peak=tau_peak, n_task=n_task),
        "static_torque_Nm": round(tau_static, 2),
        "naive": simulate("naive"),
        "static": simulate("static"),
        "heat": simulate("heat"),
    }
    # throughput of the finite mission; naive is disqualified if it overheats
    for name in ("naive", "static", "heat"):
        r = out[name]
        r["mean_task_s"] = round(r["time_s"] / max(1, r["tasks"]), 4)
    out["heat"]["speedup_vs_static_pct"] = round(
        100.0 * (1.0 - out["heat"]["time_s"] / out["static"]["time_s"]), 1)
    out["naive"]["speedup_vs_heat_pct"] = round(
        100.0 * (1.0 - out["naive"]["time_s"] / out["heat"]["time_s"]), 1)
    return out


# --------------------------------------------------- B: cold calibration hot
def exp_b():
    T_amb = 25.0
    hw0 = 0.020                     # full backlash width at 25 C (rad)
    beta = 0.004                    # width shrinks per C above ambient
    temps = np.linspace(T_amb, 75.0, 11)

    def hw(T):
        return hw0 * (1.0 - beta * (T - T_amb))

    cold = hw(T_amb)
    err_cold = np.abs(cold - hw(temps)) / 2.0 * 1e3          # mrad
    # thermal-aware estimate: temperature observer error ~2 C (1 sigma)
    rng = np.random.default_rng(SEED + 1)
    T_hat = temps + rng.normal(0.0, 2.0, size=temps.shape)
    err_heat = np.abs(hw(T_hat) - hw(temps)) / 2.0 * 1e3
    return {
        "temps_C": [float(x) for x in temps],
        "true_hw_mrad": [float(x * 1e3) for x in hw(temps)],
        "cold_cal_error_mrad": [round(float(x), 3) for x in err_cold],
        "heat_est_error_mrad": [round(float(x), 3) for x in err_heat],
        "cold_cal_max_mrad": round(float(err_cold.max()), 3),
        "heat_est_p95_mrad": round(float(np.percentile(err_heat, 95)), 3),
    }


# ------------------------------------------------------------- C: probe value
def exp_c():
    rng = np.random.default_rng(SEED + 2)
    n = 4000
    hw0 = 0.020
    base_sigma = 0.0005             # 0.5 mrad irreducible noise
    wrong = rng.random(n) < 0.5
    width = rng.uniform(0.5, 1.5, n) * hw0
    side_cost = np.where(wrong, width, 0.0)
    noise = rng.normal(0.0, base_sigma, n)

    no_probe = np.abs(side_cost + noise) * 1e3
    # a pre-load takes up the unknown side at low torque; residual 10%
    probe = np.abs(0.10 * side_cost + noise) * 1e3
    probe_time_s = 0.15
    probe_torque = 12.0
    probe_heat_J = 0.09 * probe_torque ** 2 * probe_time_s

    # crude economic rule: probe iff expected squared error gain > tau-cost
    # cost of one mrad^2-equivalent is calibrated to 0.5 J
    gain = np.mean(no_probe ** 2 - probe ** 2)
    threshold = 0.5 * probe_heat_J
    decide_probe = gain > threshold

    return {
        "n": n,
        "no_probe_p95_mrad": round(float(np.percentile(no_probe, 95)), 3),
        "probe_p95_mrad": round(float(np.percentile(probe, 95)), 3),
        "no_probe_mean_mrad": round(float(no_probe.mean()), 3),
        "probe_mean_mrad": round(float(probe.mean()), 3),
        "p95_reduction_pct": round(float(
            100.0 * (1.0 - np.percentile(probe, 95) / np.percentile(no_probe, 95))), 1),
        "probe_time_s": probe_time_s,
        "probe_heat_J": round(probe_heat_J, 2),
        "expected_sq_gain_mrad2": round(float(gain), 2),
        "decision_threshold": round(float(threshold), 2),
        "economic_decision_probe": bool(decide_probe),
    }


# ------------------------------------------------------- D: fingerprint classes
def exp_d():
    rng = np.random.default_rng(SEED + 3)
    # features: [zero offset, loop area, d(loop area)/dT]
    classes = {
        "sensor_bias": [1.0, 0.00, 0.00],
        "thermal_expansion": [0.30, 0.10, 0.80],
        "wear": [0.50, 1.00, 0.10],
        "grease_degradation": [0.20, 0.70, 1.00],
    }
    names = list(classes)
    means = np.array([classes[k] for k in names])
    mus = means.mean(axis=0)
    sds = means.std(axis=0) + 1e-9
    Z = (means - mus) / sds
    n_per = 600
    X, y = [], []
    for i, k in enumerate(names):
        X.append((means[i] + rng.normal(0.0, 0.30, size=(n_per, 3)) - mus) / sds)
        y.append(np.full(n_per, i))
    X = np.vstack(X)
    y = np.concatenate(y)
    # nearest centroid (standardized); leave prints a simple, auditable rule
    d = ((X[:, None, :] - Z[None, :, :]) ** 2).sum(axis=2)
    pred = d.argmin(axis=1)
    acc = float((pred == y).mean())
    cm = np.zeros((len(names), len(names)), dtype=int)
    for t, p in zip(y, pred):
        cm[t, p] += 1
    return {
        "classes": names,
        "n_per_class": n_per,
        "noise_sigma_std": 0.30,
        "accuracy": round(acc, 4),
        "confusion": cm.tolist(),
    }


def main():
    out = {
        "seed": SEED,
        "note": "synthetic mechanism check, NOT benchmark evidence",
        "A_thermal_governor": exp_a(),
        "B_cold_calibration_hot": exp_b(),
        "C_internal_probe": exp_c(),
        "D_fingerprint": exp_d(),
    }
    path = os.path.join(HERE, "heat_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
