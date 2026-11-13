"""Round-v3 mechanism check: chunked visual servo under action delay.

Inspiration word: 「视觉伺服」 (visual servoing).

The evaluator executes a whole action chunk open-loop and only then sends the
next observation.  So the servo loop has a delay of about one chunk.  This
script asks a narrow question:

    Does a Smith-style predictor (integrate the commands issued during the
    delay) keep a chunked image-based servo stable when the gain is high and
    the delay is large, and does it still help when the image Jacobian is
    estimated online (uncalibrated IBVS)?

THIS IS A MECHANISM CHECK ON A SYNTHETIC 3-D POINT, NOT A BENCHMARK RESULT.
The plant is x_{t+1} = x_t + u_t with bounded |u_t|; features are the point
itself plus Gaussian noise.  No real camera, robot, or task is involved.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

EXP = Path("/home/runner/work/xuen/xuen/workspace/exp")
OUT = EXP / "visc_ibvs_delay_results.json"

DIM = 3
T_HORIZON = 80
TOL = 0.01
U_MAX = 0.15
NOISE = 0.004
N_SEEDS = 200
SEED = 20261113
MU = 1e-4  # Broyden damping


def run_episode(rng, delay: int, gain: float, predictor: bool,
                estimated_jacobian: bool) -> dict:
    x = rng.normal(0.0, 0.18, size=DIM)
    target = np.zeros(DIM)
    xs = [x.copy()]
    fs = []       # observed features (delayed, noisy)
    us = []       # commands actually applied
    j_hat = (0.6 * np.eye(DIM) if estimated_jacobian else np.eye(DIM))
    f_prev = None
    u_prev = None
    settled_at = None
    errors = []
    for t in range(T_HORIZON):
        obs_idx = max(0, t - delay)
        f = xs[obs_idx] + rng.normal(0.0, NOISE, size=DIM)
        # Smith predictor: reconstruct the state at decision time by adding
        # the commands that were applied after the observed state.
        if predictor and delay > 0:
            start = max(0, len(us) - delay)
            f_hat = f + np.sum(us[start:], axis=0)
        else:
            f_hat = f
        e = f_hat - target
        # online rank-1 (Broyden) update of the image Jacobian from the
        # previously observed pair (u_prev, f_prev -> f).
        if estimated_jacobian and f_prev is not None and u_prev is not None:
            df = f - f_prev
            du = u_prev
            denom = float(du @ du) + MU
            j_hat = j_hat + np.outer(df - j_hat @ du, du) / denom
            # keep the estimate bounded; an ill-conditioned J is worse than
            # no update at all
            if not np.all(np.isfinite(j_hat)) or np.linalg.cond(j_hat) > 50:
                j_hat = 0.6 * np.eye(DIM)
        try:
            u = -gain * (np.linalg.pinv(j_hat) @ e)
        except np.linalg.LinAlgError:
            u = -gain * e
        n = float(np.linalg.norm(u))
        if n > U_MAX:
            u *= U_MAX / n
        errors.append(float(np.linalg.norm(x - target)))
        if settled_at is None and errors[-1] < TOL:
            settled_at = t
        fs.append(f)
        us.append(u)
        f_prev = f
        u_prev = u
        x = x + u
        xs.append(x.copy())
    final = float(np.linalg.norm(xs[-1] - target))
    # total variation of the commanded path, a proxy for jitter/oscillation
    path = np.asarray(xs)
    tv = float(np.sum(np.linalg.norm(np.diff(path, axis=0), axis=1)))
    return {
        "settled": settled_at is not None,
        "settle_step": settled_at,
        "final_error": final,
        "path_length": tv,
        "overshoot": float(max(errors) / max(errors[0], 1e-9)),
    }


def main() -> None:
    rng = np.random.default_rng(SEED)
    results = []
    for estimated in (False, True):
        for predictor in (False, True):
            for delay in range(0, 5):
                for gain in (0.1, 0.15, 0.2, 0.3, 0.4, 0.6, 0.8):
                    rows = [run_episode(rng, delay, gain, predictor, estimated)
                            for _ in range(N_SEEDS)]
                    results.append({
                        "estimated_jacobian": estimated,
                        "predictor": predictor,
                        "delay_chunks": delay,
                        "gain": gain,
                        "settle_rate": round(float(np.mean([r["settled"] for r in rows])), 4),
                        "mean_settle_step": round(float(np.mean([
                            r["settle_step"] if r["settle_step"] is not None else T_HORIZON
                            for r in rows])), 2),
                        "mean_final_error": round(float(np.mean([r["final_error"] for r in rows])), 5),
                        "mean_path_length": round(float(np.mean([r["path_length"] for r in rows])), 4),
                        "mean_overshoot": round(float(np.mean([r["overshoot"] for r in rows])), 3),
                    })
    best = {}
    for est in (False, True):
        for pred in (False, True):
            key = f"est={est},pred={pred}"
            sub = [r for r in results if r["estimated_jacobian"] == est
                   and r["predictor"] == pred]
            # highest delay with overall settle rate >= 0.9 at the best gain
            ok = []
            for d in range(0, 5):
                rows_d = [r for r in sub if r["delay_chunks"] == d]
                best_d = max(rows_d, key=lambda r: (r["settle_rate"], -r["mean_final_error"]))
                ok.append((d, best_d["gain"], best_d["settle_rate"],
                           best_d["mean_path_length"]))
            best[key] = [
                {"delay": d, "best_gain": g, "settle_rate": s, "mean_path_length": pl}
                for d, g, s, pl in ok
            ]
    out = {
        "note": "synthetic 3-D point; not a benchmark result",
        "params": {
            "dim": DIM, "horizon": T_HORIZON, "tol": TOL, "u_max": U_MAX,
            "noise": NOISE, "n_seeds": N_SEEDS, "seed": SEED,
        },
        "frontier": best,
        "rows": results,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")
    for key, rows in best.items():
        print(key)
        for r in rows:
            print(f"  delay={r['delay']} gain={r['best_gain']:.1f} "
                  f"settle={r['settle_rate']:.3f} path={r['mean_path_length']:.2f}")


if __name__ == "__main__":
    main()
