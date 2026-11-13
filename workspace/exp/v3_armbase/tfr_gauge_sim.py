"""v3 arm-base round: gauge confound, contact drift, and relative task-frame estimator.

Run (workspace has vendored numpy): PYTHONPATH=.pylibs python exp/v3_armbase/tfr_gauge_sim.py
"""
import json, math
import numpy as np

rng = np.random.default_rng(0)

# ---------- helpers ----------
def yaw(x, y, th):
    c, s = math.cos(th), math.sin(th)
    R = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    return R, np.array([x, y, 0.0], dtype=float)

def project(pc, f=500.0, cx=320.0, cy=240.0):
    z = pc[:, 2]
    return np.stack([f * pc[:, 0] / z + cx, f * pc[:, 1] / z + cy], axis=1)

def cam_points(P, Rcw, tcw):
    # pc = Rcw^T (p - t)
    return (P - tcw) @ Rcw

# ---------- 1. Gauge confound: base moves g  vs  task moves g^{-1} ----------
P = np.array([[0.4, 0.0, 0.8], [0.5, 0.2, 0.9], [0.3, -0.2, 0.7],
              [0.2, 0.1, 1.0], [0.6, -0.1, 0.85]])
Rcw = np.eye(3)
tcw = np.zeros(3)

def cam_coords(P, R_wc, t_wc):
    # camera coords = R_wc^T (p - t); in row form = (p - t) @ R_wc
    return (P - t_wc) @ R_wc

# scenario A: whole robot (camera) moves by g=(0.05,-0.02,0.03rad)
Rg, tg = yaw(0.05, -0.02, 0.03)
R_wc_new = Rg @ Rcw.T
t_wc_new = Rg @ tcw + tg
imgA = project(cam_coords(P, R_wc_new, t_wc_new))

# scenario B: task moves by g^{-1}, camera fixed
P_B = (P - tg) @ Rg   # Rg^T (P - tg), row form
imgB = project(cam_coords(P_B, Rcw, tcw))
gauge_pix_diff = float(np.max(np.abs(imgA - imgB)))

# ---------- 2. Contact drift bound ----------
rates = [1, 4, 8, 16]
fps = 30.0
speeds = [0.01, 0.02, 0.05, 0.1, 0.5]
drift = {f"Ta{k}": {f"v{v}": round(v * k / fps * 1000, 2) for v in speeds} for k in rates}
eps_mm = [1, 2, 5, 10]
safe = {f"eps{e}mm": {f"Ta{k}": round((e / 1000.0) * fps / k, 4) for k in rates} for e in eps_mm}

# ---------- 3. Relative task-frame estimator (1-D) ----------
def run_estimator(push, trials=400):
    T = 120
    err_dr, err_vis, err_fuse = [], [], []
    for _ in range(trials):
        d = 0.0
        x_dr = 0.0
        Pcov = 1e-4; Q = 1e-6; Rv = (0.003 ** 2)
        x_f = 0.0
        for t in range(T):
            u_true = -0.002 if 20 <= t < 40 else 0.0
            if t == 60:
                d += push
            d += u_true + rng.normal(0, 0.0003)
            u_meas = u_true + rng.normal(0, 0.0005)
            x_dr += u_meas
            z = d + rng.normal(0, 0.003)
            Pcov += Q
            K = Pcov / (Pcov + Rv)
            x_f += K * (z - x_f)
            Pcov *= (1 - K)
            if t >= 80:
                err_dr.append((x_dr - d) ** 2)
                err_vis.append((z - d) ** 2)
                err_fuse.append((x_f - d) ** 2)
    return {k: round(math.sqrt(sum(v) / len(v)) * 1000, 2) for k, v in
            [("dead_reckoning_mm", err_dr), ("vision_only_mm", err_vis), ("fused_mm", err_fuse)]}

est = {f"push_{int(p*1000)}mm": run_estimator(p) for p in [0.0, 0.02, 0.06]}

out = {
    "gauge_equiv_max_pixel_diff": gauge_pix_diff,
    "contact_drift_mm": drift,
    "contact_safe_base_speed_mps": safe,
    "estimator_rmse": est,
    "notes": "1-D illustrative; gauge diff ~0 means base-move vs inverse task-move are observationally identical.",
}
with open(__file__.replace('.py', '.json'), 'w') as f:
    json.dump(out, f, indent=2)
print(json.dumps(out, indent=2))
