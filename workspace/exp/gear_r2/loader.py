import json, glob, os, collections
import numpy as np

CACHE = 'exp/duo_rows_cache'

def parse(r):
    return r if isinstance(r, dict) else eval(r, {'__builtins__': {}}, {})

def flat(v):
    if isinstance(v, (list, tuple)): return [float(x) for x in v]
    if isinstance(v, np.ndarray): return [float(x) for x in v.tolist()]
    return [float(v)]

STATE_KEYS = ['observation.state.left_ee_pose_gripper_base','observation.state.right_ee_pose_gripper_base',
              'observation.state.left_gripper','observation.state.right_gripper',
              'observation.state.left_arm','observation.state.right_arm']
ACTION_KEYS = ['action.left_ee_pose_gripper_base','action.right_ee_pose_gripper_base',
               'action.left_gripper','action.right_gripper',
               'action.left_arm','action.right_arm']

def load_episodes(min_len=60):
    fs = sorted(glob.glob(os.path.join(CACHE, '*.json')))
    buckets = collections.defaultdict(list)
    for f in fs:
        task = os.path.basename(f)[:-5].rsplit('_', 1)[0]
        d = json.load(open(f))
        for rr in d['rows']:
            r = parse(rr['row'])
            try:
                ep = int(r['episode_index']); fr = int(r['frame_index'])
            except Exception:
                continue
            buckets[(task, ep)].append((fr, r))
    eps = []
    for (task, ep), items in buckets.items():
        items.sort(key=lambda z: z[0])
        seen = set(); rows = []
        for fr, r in items:
            if fr in seen: continue
            seen.add(fr); rows.append(r)
        if len(rows) < min_len: continue
        try:
            X = np.array([sum((flat(r[k]) for k in STATE_KEYS), []) for r in rows], dtype=np.float64)
            Y = np.array([sum((flat(r[k]) for k in ACTION_KEYS), []) for r in rows], dtype=np.float64)
        except Exception:
            continue
        if not np.isfinite(X).all() or not np.isfinite(Y).all(): continue
        eps.append(dict(task=task, ep=ep, X=X, Y=Y, n=len(rows)))
    return eps

if __name__ == '__main__':
    eps = load_episodes()
    print('episodes', len(eps), 'frames', sum(e['n'] for e in eps))
    print(collections.Counter(e['task'] for e in eps))
    lens = [e['n'] for e in eps]
    print('ep len min/med/max', min(lens), int(np.median(lens)), max(lens))
    X = np.concatenate([e['X'] for e in eps]); Y = np.concatenate([e['Y'] for e in eps])
    print('X', X.shape, 'Y', Y.shape)
    print('gripper ranges L/R', round(X[:,12].min(),3), round(X[:,12].max(),3), round(X[:,13].min(),3), round(X[:,13].max(),3))
