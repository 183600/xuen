import json
import glob
import numpy as np

files = sorted(glob.glob('duo_rows_cache/*.json'))
byds = {}
for f in files:
    ds = f.rsplit('_', 1)[0]
    d = json.load(open(f))
    for it in d.get('rows', []):
        byds.setdefault(ds, []).append(it['row'])

for ds, rows in sorted(byds.items()):
    gl = np.array([r['action.left_gripper'] for r in rows])
    gr = np.array([r['action.right_gripper'] for r in rows])
    L = np.array([r['action.left_ee_pose_gripper_base'] for r in rows])
    R = np.array([r['action.right_ee_pose_gripper_base'] for r in rows])
    d = R[:, :3] - L[:, :3]
    dd = np.abs(np.diff(d, axis=0)).sum(axis=1)
    print(
        f"{ds:22s} n={len(rows):5d} "
        f"gripL[min,p10,p50]={gl.min():.2f},{np.percentile(gl,10):.2f},{np.percentile(gl,50):.2f} "
        f"gripR={gr.min():.2f},{np.percentile(gr,10):.2f},{np.percentile(gr,50):.2f} "
        f"|d|mean={np.linalg.norm(d,axis=1).mean():.3f} "
        f"d_drift_med={np.median(dd):.4f} frac_drift<0.002={np.mean(dd<0.002):.3f}"
    )
