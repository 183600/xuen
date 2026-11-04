"""PROTO-TAC: data-grounded check that proprioception carries a contact signal.

Runs on the public UniBot-V1 challenge dataset (unitreerobotics/G1_Dex1_*).
No learned model anywhere: every statistic is deterministic.

E1  temporal alignment between action[t] and observation[t+k] (lag of the arm)
E2  gripper stall readout: measured opening vs commanded opening during closes
E3  contact detection AUROC (holding vs empty) for
      - gripper stall          (g_obs - g_cmd)
      - joint residual  ||q_obs(t+k)-q_act(t)||
      - EE residual    ||p_obs(t+k)-p_act(t)||
E4  slip statistic: drift of the measured opening while the gripper is closed
E5  load proxy: joint residual while holding vs empty
E6  free-space baseline of every statistic

Usage:  python prototac_data.py <parquet> [<parquet> ...] [-o out.json]
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pyarrow.parquet as pq

COLS = [
    "observation.state.left_arm",
    "observation.state.right_arm",
    "observation.state.left_gripper",
    "observation.state.right_gripper",
    "observation.state.left_ee_pose_gripper_base",
    "observation.state.right_ee_pose_gripper_base",
    "action.left_arm",
    "action.right_arm",
    "action.left_gripper",
    "action.right_gripper",
    "action.left_ee_pose_gripper_base",
    "action.right_ee_pose_gripper_base",
    "episode_index",
]

OPEN_LVL = 4.50      # measured opening of a fully open gripper
CLOSED_LVL = 0.10    # measured opening of a fully closed gripper
STALL_EPS = 0.15     # measured-vs-commanded gap that counts as "blocked"


def load(path: str) -> dict:
    t = pq.read_table(path, columns=COLS)
    d = {}
    for name in COLS:
        d[name] = np.asarray(t.column(name).to_pylist(), dtype=np.float64)
    return d


def episode_slices(ep: np.ndarray):
    starts = [0]
    for i in range(1, len(ep)):
        if ep[i] != ep[i - 1]:
            starts.append(i)
    starts.append(len(ep))
    return [(starts[i], starts[i + 1]) for i in range(len(starts) - 1)]


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """P(score(pos) > score(neg)), ties count 1/2.  NaN-safe."""
    pos = pos[np.isfinite(pos)]
    neg = neg[np.isfinite(neg)]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    allv = np.concatenate([pos, neg])
    order = np.argsort(allv, kind="mergesort")
    ranks = np.empty(len(allv), dtype=np.float64)
    ranks[order] = np.arange(1, len(allv) + 1)
    s = allv[order]
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[j + 1] == s[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    rsum = ranks[:len(pos)].sum()
    return float((rsum - len(pos) * (len(pos) + 1) / 2.0) / (len(pos) * len(neg)))


def alignment(qo: np.ndarray, qa: np.ndarray, eps, max_k=25):
    ks = list(range(-5, max_k + 1))
    errs = []
    for k in ks:
        num = 0.0
        cnt = 0
        for s, e in eps[:300]:
            n = e - s
            i0 = max(s, s - k)
            j0 = i0 + k
            m = min(e - i0, e - j0)
            if m <= 5:
                continue
            num += float(np.abs(qa[i0:i0 + m] - qo[j0:j0 + m]).sum(axis=1).mean())
            cnt += m
        errs.append(num / max(cnt, 1))
    best = int(ks[int(np.argmin(errs))])
    return best, {str(k): float(v) for k, v in zip(ks, errs)}


def shifted_residual(obs: np.ndarray, act: np.ndarray, eps, k: int):
    """obs[t+k] - act[t] for every t inside an episode."""
    out = np.full_like(obs, np.nan)
    for s, e in eps:
        i0 = max(s, s - k)
        j0 = i0 + k
        m = min(e - i0, e - j0)
        if m <= 0:
            continue
        out[i0:i0 + m] = obs[j0:j0 + m] - act[i0:i0 + m]
    return out


def close_events(g_cmd: np.ndarray, g_obs: np.ndarray, eps):
    """Maximal runs where the commanded gripper is below 2.0 (closing/closed)."""
    evs = []
    for s, e in eps:
        gc = g_cmd[s:e]
        go = g_obs[s:e]
        close = gc < 2.0
        i = 0
        while i < len(close):
            if close[i]:
                j = i
                while j + 1 < len(close) and close[j + 1]:
                    j += 1
                cmd_min = float(gc[i:j + 1].min())
                meas_min = float(go[i:j + 1].min())
                meas_end = float(go[j])
                # stall = how much wider the measured opening stays than commanded
                gap = float(np.max(go[i:j + 1] - gc[i:j + 1]))
                evs.append(dict(ep=int(s), start=int(s + i), end=int(s + j),
                                cmd_min=cmd_min, meas_min=meas_min,
                                meas_end=meas_end, stall=max(0.0, gap)))
                i = j + 1
            else:
                i += 1
    return evs


def analyse(path: str) -> dict:
    d = load(path)
    ep = d["episode_index"]
    eps = episode_slices(ep)
    qo = d["observation.state.left_arm"]
    qa = d["action.left_arm"]
    go = d["observation.state.left_gripper"]
    ga = d["action.left_gripper"]
    eo = d["observation.state.left_ee_pose_gripper_base"]
    ea = d["action.left_ee_pose_gripper_base"]

    k_q, err_q = alignment(qo, qa, eps)
    k_e, err_e = alignment(eo[:, :3], ea[:, :3], eps)

    rq = shifted_residual(qo, qa, eps, k_q)
    re = shifted_residual(eo[:, :3], ea[:, :3], eps, k_e)
    valid = np.isfinite(rq[:, 0]) & np.isfinite(re[:, 0])

    # ---- E2 gripper ----
    evs = close_events(ga, go, eps)
    stalls = np.array([e["stall"] for e in evs]) if evs else np.zeros(0)
    empty = stalls <= STALL_EPS
    grip_open_mask = ga > 4.0
    free_gap = (go - ga)[grip_open_mask & valid]

    # ---- labels for E3: "holding" = a close event that stalled; "empty" = ----
    # a close event that closed on nothing; frames are labelled for 30 frames
    # after the close event ends.
    hold = np.zeros(len(go), dtype=bool)
    emp = np.zeros(len(go), dtype=bool)
    for e in evs:
        w = slice(e["end"], min(e["end"] + 30, len(go)))
        if e["stall"] > STALL_EPS:
            hold[w] = True
        else:
            emp[w] = True
    closed = ga < 2.0
    sel_hold = valid & closed & hold & (~emp)
    sel_emp = valid & closed & emp & (~hold)

    # ---- E4 slip: drift of measured opening while commanded closed ----
    dg = np.full(len(go), np.nan)
    dg[1:] = go[1:] - go[:-1]
    slip_hold = dg[sel_hold]
    slip_free = dg[valid & closed & ~hold & ~emp]

    out = {
        "file": os.path.basename(path),
        "n_rows": int(len(go)),
        "n_episodes": int(len(eps)),
        "E1_alignment": {
            "joint_k_star": k_q,
            "joint_err_at_k_star": err_q[str(k_q)],
            "joint_err_at_k0": err_q["0"],
            "joint_err_curve": err_q,
            "ee_k_star": k_e,
            "ee_err_at_k_star": err_e[str(k_e)],
            "ee_err_at_k0": err_e["0"],
        },
        "E2_gripper": {
            "measured_min": float(go.min()), "measured_max": float(go.max()),
            "commanded_min": float(ga.min()), "commanded_max": float(ga.max()),
            "n_close_events": len(evs),
            "stall_pct": {str(p): float(np.percentile(stalls, p)) for p in (10, 25, 50, 75, 90, 95, 99)} if len(stalls) else {},
            "frac_empty_stall_le_eps": float(np.mean(empty)) if len(stalls) else float("nan"),
            "frac_holding_stall_gt_eps": float(np.mean(~empty)) if len(stalls) else float("nan"),
            "stall_hist20": np.histogram(stalls, bins=20, range=(0.0, 4.5))[0].tolist() if len(stalls) else [],
            "free_gap_abs_p99": float(np.percentile(np.abs(free_gap), 99)) if len(free_gap) else float("nan"),
            "free_gap_abs_max": float(np.max(np.abs(free_gap))) if len(free_gap) else float("nan"),
        },
        "E3_contact_auc": {
            "n_hold": int(sel_hold.sum()), "n_empty": int(sel_emp.sum()),
            "gripper_stall": auc((go - ga)[sel_hold], (go - ga)[sel_emp]),
            "gripper_stall_abs": auc(np.abs(go - ga)[sel_hold], np.abs(go - ga)[sel_emp]),
            "joint_l2": auc(np.linalg.norm(rq[sel_hold], axis=1), np.linalg.norm(rq[sel_emp], axis=1)),
            "joint_abs_mean": auc(np.abs(rq[sel_hold]).mean(axis=1), np.abs(rq[sel_emp]).mean(axis=1)),
            "ee_l2": auc(np.linalg.norm(re[sel_hold], axis=1), np.linalg.norm(re[sel_emp], axis=1)),
            "joint_per_joint": [auc(np.abs(rq[sel_hold, j]), np.abs(rq[sel_emp, j])) for j in range(rq.shape[1])],
        },
        "E4_slip": {
            "dg_hold_p50": float(np.nanmedian(slip_hold)) if len(slip_hold) else float("nan"),
            "dg_hold_p99": float(np.nanpercentile(slip_hold, 99)) if len(slip_hold) else float("nan"),
            "dg_free_p50": float(np.nanmedian(slip_free)) if len(slip_free) else float("nan"),
            "dg_free_p99": float(np.nanpercentile(slip_free, 99)) if len(slip_free) else float("nan"),
            "frac_hold_frames_with_dg_gt_0": float(np.mean(slip_hold > 0)) if len(slip_hold) else float("nan"),
            "auc_dg_hold_vs_empty": auc(slip_hold, slip_free),
        },
        "E5_load": {
            "joint_l2_hold_p50": float(np.nanpercentile(np.linalg.norm(rq[sel_hold], axis=1), 50)) if sel_hold.any() else float("nan"),
            "joint_l2_empty_p50": float(np.nanpercentile(np.linalg.norm(rq[sel_emp], axis=1), 50)) if sel_emp.any() else float("nan"),
            "joint_l2_hold_mean": float(np.nanmean(np.linalg.norm(rq[sel_hold], axis=1))) if sel_hold.any() else float("nan"),
            "joint_l2_empty_mean": float(np.nanmean(np.linalg.norm(rq[sel_emp], axis=1))) if sel_emp.any() else float("nan"),
            "ee_l2_hold_p50": float(np.nanpercentile(np.linalg.norm(re[sel_hold], axis=1), 50)) if sel_hold.any() else float("nan"),
            "ee_l2_empty_p50": float(np.nanpercentile(np.linalg.norm(re[sel_emp], axis=1), 50)) if sel_emp.any() else float("nan"),
        },
    }
    return out


def main() -> None:
    outfile = None
    argv = list(sys.argv[1:])
    if "-o" in argv:
        i = argv.index("-o")
        outfile = argv[i + 1]
        del argv[i:i + 2]
    args = [a for a in argv if not a.startswith("-")]
    results = [analyse(p) for p in args]
    blob = {"results": results}
    txt = json.dumps(blob, indent=1)
    if outfile:
        with open(outfile, "w") as f:
            f.write(txt)
    # compact console summary
    for r in results:
        print(f"\n=== {r['file']}  rows={r['n_rows']} eps={r['n_episodes']}")
        e1 = r["E1_alignment"]
        print(f"  E1 joint k*={e1['joint_k_star']} err {e1['joint_err_at_k_star']:.5f} (k=0: {e1['joint_err_at_k0']:.5f}) | "
              f"ee k*={e1['ee_k_star']} err {e1['ee_err_at_k_star']:.5f} (k=0: {e1['ee_err_at_k0']:.5f})")
        e2 = r["E2_gripper"]
        print(f"  E2 closes={e2['n_close_events']} frac_empty={e2['frac_empty_stall_le_eps']:.3f} "
              f"frac_holding={e2['frac_holding_stall_gt_eps']:.3f} stall_p50={e2['stall_pct'].get('50',0):.3f} "
              f"free_gap_p99={e2['free_gap_abs_p99']:.4f}")
        print(f"     stall_hist20={e2['stall_hist20']}")
        e3 = r["E3_contact_auc"]
        print(f"  E3 AUROC hold-vs-empty: grip_stall={e3['gripper_stall']:.3f} grip_abs={e3['gripper_stall_abs']:.3f} "
              f"joint_l2={e3['joint_l2']:.3f} joint_abs={e3['joint_abs_mean']:.3f} ee_l2={e3['ee_l2']:.3f} "
              f"(n_hold={e3['n_hold']} n_empty={e3['n_empty']})")
        print(f"     per-joint AUROC={[round(x,3) for x in e3['joint_per_joint']]}")
        e4 = r["E4_slip"]
        print(f"  E4 slip dg: hold p50={e4['dg_hold_p50']:.5f} p99={e4['dg_hold_p99']:.5f} | "
              f"empty p50={e4['dg_free_p50']:.5f} p99={e4['dg_free_p99']:.5f} auc={e4['auc_dg_hold_vs_empty']:.3f}")
        e5 = r["E5_load"]
        print(f"  E5 load joint_l2 hold p50={e5['joint_l2_hold_p50']:.5f} vs empty p50={e5['joint_l2_empty_p50']:.5f} | "
              f"ee_l2 hold p50={e5['ee_l2_hold_p50']:.5f} vs empty p50={e5['ee_l2_empty_p50']:.5f}")


if __name__ == "__main__":
    main()
