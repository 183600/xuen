"""Round-1 (闭环控制 x 抓取规划) data-grounded probe.

Reads the cached HF datasets-server rows (exp/duo_rows_cache, LeRobot rows for
G1_Dex1_<Task>) and measures, from the official demonstrations only:

  * open -> close -> open gripper cycles per hand,
  * settled minimum opening after a close: near 0 (jaws empty) vs > 0 (object),
  * close duration and closed dwell (frames @30 fps),
  * close cycles per episode (natural re-grasps / multi-object sequences).

Purpose: ground I10 (grasp-phase closed loop) and I12 (T_a as control knob)
in measured demonstration statistics rather than intuition. The cached rows
are a 3000-frame window per task (not full episodes), so treat the numbers as
a lower-bound probe, not a census.
"""
import glob
import json
import os
from collections import defaultdict
from statistics import median, mean

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "duo_rows_cache")
FPS = 30.0
OPEN = 3.5       # Dex1 opening: ~5.5 fully open, ~0 fully closed
PRE_OPEN = 4.2   # require a genuinely open gripper before a close cycle
EMPTY = 0.35     # settled opening below this = jaws met with nothing between them


def load_task(ds):
    by_ep = defaultdict(list)
    for f in glob.glob(os.path.join(CACHE, f"{ds}_*.json")):
        try:
            d = json.load(open(f))
        except (OSError, ValueError):
            continue
        for rr in d.get("rows", []):
            by_ep[rr["row"]["episode_index"]].append(rr["row"])
    out = []
    for ep, rows in by_ep.items():
        rows.sort(key=lambda r: r["frame_index"])
        out.append((ep, rows))
    return out


def cycles(rows, side):
    """Open->close->open gripper cycles with a settled minimum."""
    g = [float(r[f"observation.state.{side}_gripper"]) for r in rows]
    n = len(g)
    out = []
    t = 1
    while t < n:
        if g[t - 1] >= OPEN and g[t] < OPEN:
            pre = max(g[max(0, t - 10):t])
            if pre < PRE_OPEN:
                t += 1
                continue
            # minimum within the next 2 s = the grasp/settle point
            hi = min(n, t + int(2.0 * FPS))
            seg = g[t:hi]
            lo = min(seg)
            j = t + seg.index(lo)
            # must reopen to a real open state to count as a complete cycle
            r = j + 1
            while r < n and g[r] <= OPEN:
                r += 1
            if r >= n:
                break  # cycle not complete inside the cached window
            out.append({
                "t": t,
                "min_width": float(lo),
                "close_frames": j - t + 1,       # crossing -> minimum
                "closed_frames": r - t,          # crossing -> reopened past OPEN
                "empty": lo < EMPTY,
            })
            t = r
        else:
            t += 1
    return out


def main():
    tasks = sorted({os.path.basename(f).rsplit("_", 1)[0]
                    for f in glob.glob(os.path.join(CACHE, "*.json"))})
    report = {}
    for ds in tasks:
        eps = load_task(ds)
        if not eps:
            continue
        agg = {"episodes": len(eps), "frames": sum(len(r) for _, r in eps)}
        for side in ("left", "right"):
            evs = [e for _, rows in eps for e in cycles(rows, side)]
            if not evs:
                continue
            grasp = [e for e in evs if not e["empty"]]
            empty = [e for e in evs if e["empty"]]
            per_ep = [len(cycles(rows, side)) for _, rows in eps]
            agg[side] = {
                "cycles": len(evs),
                "object_cycles": len(grasp),
                "empty_cycles": len(empty),
                "empty_frac": round(len(empty) / len(evs), 3),
                "min_width_med": round(median([e["min_width"] for e in grasp]), 3) if grasp else None,
                "close_frames_med": round(median([e["close_frames"] for e in grasp]), 1) if grasp else None,
                "closed_frames_med": round(median([e["closed_frames"] for e in grasp]), 1) if grasp else None,
                "cycles_per_ep_mean": round(mean(per_ep), 2) if per_ep else 0.0,
                "cycles_per_ep_max": max(per_ep) if per_ep else 0,
                "episodes_with_2plus": sum(1 for x in per_ep if x >= 2),
            }
        report[ds] = agg

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grasp_loop_stats.json")
    with open(out, "w") as f:
        json.dump(report, f, indent=2)

    hdr = (f"{'task':22s} {'eps':>3s} {'side':>5s} {'cyc':>3s} {'empty%':>6s} "
           f"{'minw':>5s} {'close_f':>7s} {'dwell_f':>7s} {'cyc/ep':>6s} {'ep>=2':>5s}")
    print(hdr)
    for ds in tasks:
        a = report.get(ds, {})
        for side in ("left", "right"):
            d = a.get(side)
            if not d:
                continue
            print(f"{ds:22s} {a.get('episodes',0):3d} {side:>5s} {d['cycles']:3d} "
                  f"{d['empty_frac']:6.0%} {str(d['min_width_med']):>5s} "
                  f"{str(d['close_frames_med']):>7s} {str(d['closed_frames_med']):>7s} "
                  f"{d['cycles_per_ep_mean']:6.2f} {d['episodes_with_2plus']:5d}")

    # aggregate over all object-cycles
    mins = [d[s]["min_width_med"] for d in report.values() for s in ("left", "right")
            if d.get(s) and d[s]["min_width_med"] is not None]
    print(f"\ntasks with cached rows: {len(report)}")
    print(f"median of per-task median object-close width: {median(mins):.2f} (range {min(mins):.2f}-{max(mins):.2f})")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
