"""Mechanism check for UniBot-DART (dynamics-aware reference trajectory).

Toy 7-joint first-order plant with pure input delay, matching the two robust
facts measured on the official cache: ~3-frame (100 ms) action->state lag and
a closed-loop tracking-error settling time of ~0.5 s.

Compares, under fixed chunk length T_a and latency d:
  raw      : send the policy's desired positions as-is
  lead     : invert the identified first-order model (lead compensation)
  lead_fb  : lead compensation + feedback from a model-predicted state
Metrics are relative to the desired minimum-jerk trajectory.

This is a mechanism check, not a UniBot benchmark result.
"""
import json
import numpy as np

FPS = 30.0
DT = 1.0 / FPS
RNG = np.random.default_rng(0)


def min_jerk(n, x0, x1):
    t = np.linspace(0.0, 1.0, n)
    s = 10 * t**3 - 15 * t**4 + 6 * t**5
    return x0[None, :] + (x1 - x0)[None, :] * s[:, None]


def make_episode(n_pre=10, n_move=30, n_hold=20, nj=7):
    x0 = RNG.uniform(-0.5, 0.5, nj)
    x1 = RNG.uniform(-0.8, 0.8, nj)
    x = np.vstack([np.repeat(x0[None], n_pre, 0), min_jerk(n_move, x0, x1),
                   np.repeat(x1[None], n_hold, 0)])
    return x


def run(Ta=8, delay=3, tau=0.15, strategy="raw", K=0.6, model_err=0.0,
        n_ep=200, n_pre=10, n_move=60, n_hold=40):
    errs, peaks, jerks, settle = [], [], [], []
    alpha = 1.0 - np.exp(-DT / tau)
    alpha_hat = 1.0 - np.exp(-DT / (tau * (1.0 + model_err)))
    for ep in range(n_ep):
        xstar = make_episode(n_pre, n_move, n_hold)
        n = len(xstar)
        x = xstar[0].copy()
        u_hist = []
        xs = [x.copy()]
        x_hat = x.copy()
        for block in range(0, n, Ta):
            idx = np.arange(block, min(block + Ta, n))
            for i in idx:
                if strategy == "raw":
                    u = xstar[i]
                else:
                    # command at time i affects state at i+delay; invert model
                    j = min(i + delay, n - 1)
                    jn = min(j + 1, n - 1)
                    u = xstar[j] + (xstar[jn] - xstar[j]) / max(alpha_hat, 1e-6)
                    if strategy == "lead_fb":
                        u = u + K * (xstar[i] - x_hat)
                u_hist.append(u.copy())
                # plant: state update from delayed command
                d = len(u_hist) - 1 - delay
                if d >= 0:
                    x = x + alpha * (u_hist[d] - x)
                # one-step predicted state (for feedback)
                x_hat = x_hat + alpha_hat * (u - x_hat)
                xs.append(x.copy())
        x = np.array(xs[1:])
        # only score after the pre-roll, and after the delay has flushed
        lo = n_pre + delay + 2
        e = x[lo:] - xstar[lo:]
        errs.append(float(np.sqrt(np.mean(e**2))))
        peaks.append(float(np.max(np.abs(e))))
        du = np.diff(np.array(u_hist), axis=0)
        jerks.append(float(np.sqrt(np.mean(du**2))))
        settle.append(float(np.mean(np.abs(x[-n_hold + 5:] - xstar[-n_hold + 5:]))))
    return {"rmse": float(np.mean(errs)), "peak": float(np.mean(peaks)),
            "cmd_rms_step": float(np.mean(jerks)), "settle": float(np.mean(settle))}


def main():
    out = {"settings": {"fps": FPS, "n_ep": 200, "tau_s": 0.15}, "sweep": {}, "tau_sweep": {}}
    for delay in (0, 3):
        for Ta in (1, 2, 4, 8, 16):
            row = {}
            for strat in ("raw", "lead", "lead_fb"):
                row[strat] = run(Ta=Ta, delay=delay, strategy=strat)
            row["lead_gain"] = 1.0 - row["lead"]["rmse"] / row["raw"]["rmse"]
            row["lead_fb_gain"] = 1.0 - row["lead_fb"]["rmse"] / row["raw"]["rmse"]
            out["sweep"][f"d{delay}_Ta{Ta}"] = row
            print(f"d={delay} Ta={Ta:2d} raw={row['raw']['rmse']:.4f} "
                  f"lead={row['lead']['rmse']:.4f} ({row['lead_gain']*100:+.0f}%) "
                  f"lead_fb={row['lead_fb']['rmse']:.4f} ({row['lead_fb_gain']*100:+.0f}%)")
    # sensitivity to the dominant tracking time constant.  The measured 0.5 s
    # is a residual-error decay time; velocity feedforward makes the effective
    # tracking pole faster, so bracket it instead of fixing one value.
    for tau in (0.10, 0.15, 0.25, 0.50):
        row = {}
        for strat in ("raw", "lead", "lead_fb"):
            row[strat] = run(Ta=8, delay=3, tau=tau, strategy=strat)
        row["lead_gain"] = 1.0 - row["lead"]["rmse"] / row["raw"]["rmse"]
        row["lead_fb_gain"] = 1.0 - row["lead_fb"]["rmse"] / row["raw"]["rmse"]
        out["tau_sweep"][str(tau)] = row
        print(f"tau={tau:.2f} raw={row['raw']['rmse']:.4f} lead={row['lead']['rmse']:.4f} "
              f"({row['lead_gain']*100:+.0f}%) fb={row['lead_fb']['rmse']:.4f} "
              f"({row['lead_fb_gain']*100:+.0f}%)")
    # robustness to model error
    out["model_err"] = {}
    for me in (0.0, 0.2, 0.5, 1.0):
        out["model_err"][str(me)] = {
            "raw": run(Ta=8, delay=3, strategy="raw"),
            "lead": run(Ta=8, delay=3, strategy="lead", model_err=me),
            "lead_fb": run(Ta=8, delay=3, strategy="lead_fb", model_err=me),
        }
    json.dump(out, open("exp/dart_sim_results.json", "w"), indent=2)
    print("model error:")
    for k, v in out["model_err"].items():
        print(k, "lead_gain", 1 - v["lead"]["rmse"] / v["raw"]["rmse"],
              "fb_gain", 1 - v["lead_fb"]["rmse"] / v["raw"]["rmse"])


if __name__ == "__main__":
    main()
