"""Round probe: wrist-vs-head gauge ambiguity + open-loop chunk safety law.
D-level geometry/kinematics only; no robot, no images."""
import json, math, os
import numpy as np

# ---------- P1: gauge ambiguity of wrist-mounted camera ----------
f = 500.0
cx, cy = 320.0, 240.0
box = 0.02
corners = np.array([[sx*box, sy*box, sz*box] for sx in (-1,1) for sy in (-1,1) for sz in (-1,1)])

def proj(points, C):
    q = points - C
    z = np.maximum(q[:,2], 1e-6)
    return np.stack([f*q[:,0]/z + cx, f*q[:,1]/z + cy], 1)

def rms(a,b):
    return float(np.sqrt(np.mean(np.sum((a-b)**2, axis=1))))

obj0 = np.array([0.0, 0.0, 0.60])
grip0 = np.array([0.0, 0.0, 0.40])
head0 = np.array([0.35, 0.0, 0.25])
# wrist camera rigidly attached to gripper
wrist0 = grip0 + np.array([0.0, 0.0, 0.02])

scen = {}
for dmm in (1,2,5,10):
    d = dmm/1000.0
    # relative motion: object moves, gripper fixed
    rel_obj = obj0 + np.array([d,0,0])
    base_w = proj(corners+obj0, wrist0); base_h = proj(corners+obj0, head0)
    rel_w = proj(corners+rel_obj, wrist0); rel_h = proj(corners+rel_obj, head0)
    # common mode: object and gripper move together
    cm_obj = obj0 + np.array([d,0,0]); cm_g = grip0 + np.array([d,0,0]); cm_w = cm_g + np.array([0,0,0.02])
    cm_w_img = proj(corners+cm_obj, cm_w); cm_h_img = proj(corners+cm_obj, head0)
    scen[str(dmm)] = {
        "relative_wrist_px": round(rms(base_w, rel_w),3),
        "relative_head_px": round(rms(base_h, rel_h),3),
        "commonmode_wrist_px": round(rms(base_w, cm_w_img),3),
        "commonmode_head_px": round(rms(base_h, cm_h_img),3),
    }

# ---------- P2: chunk-level safe speed law ----------
dt = 1.0/30.0
eps_mm = [1,2,5,10]
chunks = [1,2,4,8,16]
law = {}
for eps in eps_mm:
    law[str(eps)] = {str(T): round((eps/1000.0)/(T*dt), 4) for T in chunks}

# worst-case overshoot of a chunk at fixed speed v, for reference
v_ref = 0.10
travel = {str(T): round(v_ref*T*dt*1000,2) for T in chunks}

# ---------- P3: position-only force ambiguity ----------
K = [500.0, 2000.0, 10000.0]
band_N = [0.5, 5.0]
pen_for_band = {str(int(k)): [round(band_N[0]/k*1000,3), round(band_N[1]/k*1000,3)] for k in K}
ratio = band_N[1]/K[0] / (band_N[0]/K[-1])

out = {"note":"D-level geometry/kinematics only; no robot evidence",
       "P1_gauge_ambiguity":{"note":"pixel RMS of 8 box corners; wrist is gripper-mounted",
                              "f_px":f,"box_m":2*box,"scenarios_mm":scen},
       "P2_chunk_speed_law":{"note":"v_max = eps/(T_a*dt) [m/s], dt=1/30",
                              "v_max_mps":law,"travel_at_0.1mps_mm":travel},
       "P3_force_ambiguity":{"note":"penetration band for force band 0.5..5N under stiffness sweep",
                              "penetration_mm":pen_for_band,"max_ratio":round(ratio,1)}}
print(json.dumps(out, indent=2))
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "wise_contact_probe.json"), "w").write(json.dumps(out, indent=2))
