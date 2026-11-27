"""Round-3 (产学研合作 x 轮足机器人) data-grounded probe.

Audits the official 32-task UniBot challenge datasets for how much of the
platform's exposed action space is actually exercised by the demonstrations.

The submission interface exposes `action.pivot[7]` in BOTH control spaces:
    [vx, vy, angle_z, pivot_3, pivot_4, pivot_5, height]
and the datasets additionally store `action.base_command[4] = [vx, vy,
angle_z, height]`.  This probe reads only the small `meta/stats.json` and
`meta/info.json` files (no parquet/video download) and reports, per task:

  * episode / frame counts and height range,
  * height std and span (is the base height actively used?),
  * max |vx|, |vy|, |yaw| and std/max ratio (are translations sparse bursts?),
  * the fixed value of pivot_4 (likely a waist/lean parameter).

Caveat: min/max/mean/std are aggregate over frames, not frame-exact usage
fractions.  Treat the numbers as a directional audit; a full parquet pass is
the next step.  Results are written next to this script as JSON.
"""
import concurrent.futures
import json
import os
import urllib.request

COLLECTION = (
    "https://huggingface.co/api/collections/unitreerobotics/"
    "unibot-v1-challenge-dataset-6a3138a00ea492d60df023c8"
)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "base_usage_audit.json")


def fetch_json(url, timeout=30):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def audit_one(repo_id):
    name = repo_id.split("/")[-1]
    stats = fetch_json(
        f"https://huggingface.co/datasets/{repo_id}/resolve/main/meta/stats.json"
    )
    info = fetch_json(
        f"https://huggingface.co/datasets/{repo_id}/resolve/main/meta/info.json"
    )
    p = stats.get("action.pivot") or stats.get("action.base_command")
    out = {
        "id": name,
        "eps": info.get("total_episodes"),
        "frames": info.get("total_frames"),
    }
    if p:
        mn, mx, mean, std = p["min"], p["max"], p["mean"], p["std"]
        if len(mn) == 7:  # pivot: vx,vy,angle_z,p3,p4,p5,height
            out.update(
                hmin=mn[6], hmax=mx[6], hmean=mean[6], hstd=std[6],
                p3mean=mean[3], p4mean=mean[4], p5mean=mean[5],
                vxmax=mx[0], vymax=mx[1], yawmax=mx[2],
                vxstd=std[0], vystd=std[1], yawstd=std[2],
            )
        else:  # base_command: vx,vy,angle_z,height
            out.update(
                hmin=mn[3], hmax=mx[3], hmean=mean[3], hstd=std[3],
                vxmax=mx[0], vymax=mx[1], yawmax=mx[2],
                vxstd=std[0], vystd=std[1], yawstd=std[2],
            )
    return out


def main():
    coll = fetch_json(COLLECTION)
    ids = [it["id"] for it in coll["items"]]
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        rows = list(ex.map(audit_one, ids))
    rows = [r for r in rows if "hstd" in r]
    rows.sort(key=lambda r: r["id"])
    json.dump(rows, open(OUT, "w"), indent=1)

    frames = sum(r["frames"] for r in rows)
    eps = sum(r["eps"] for r in rows)
    print(f"tasks={len(rows)} eps={eps} frames={frames} hours={frames/30/3600:.2f}")
    print("height min/max:", min(r["hmin"] for r in rows), max(r["hmax"] for r in rows))
    print("height std>=0.005:", sum(r["hstd"] >= 0.005 for r in rows))
    print("height span>0.05:", sum(r["hmax"] - r["hmin"] > 0.05 for r in rows))
    for th in (0.01, 0.05, 0.1):
        print(
            f"translation>{th}: "
            f"{sum(max(abs(r['vxmax']), abs(r['vymax'])) > th for r in rows)}"
        )
    print("pivot_3 nonzero:", sum(abs(r.get("p3mean", 0)) > 1e-9 for r in rows))
    print("pivot_5 nonzero:", sum(abs(r.get("p5mean", 0)) > 1e-9 for r in rows))


if __name__ == "__main__":
    main()
