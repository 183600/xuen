"""Round-3 analysis: how far can state-conditioned imitation extrapolate before
aliasing dominates?  Uses only cached 30 Hz G1_Dex1 trajectory slices (B-level)."""
import json, glob, os
import numpy as np

HS = [1, 2, 4, 8, 16, 32, 64]
TASKS = {
 'G1_Dex1_ArrangeTestTubes':'T13','G1_Dex1_ConveyorSorting':'T24',
 'G1_Dex1_FoldTowel':'T16','G1_Dex1_HangCup':'T01',
 'G1_Dex1_OrganizeTools':'T15','G1_Dex1_PackDoll':'T03',
 'G1_Dex1_PlugInEthernet':'T26','G1_Dex1_SpellRobot':'T22',
 'G1_Dex1_StackBowls':'T27','G1_Dex1_ToolboxStorage':'T09',
 'G1_Dex1_Unlock':'T12','G1_Dex1_ZipUp':'T19',
}

def vec(x):
    S = np.concatenate([x['observation.state.left_ee_pose_gripper_base'],
                        x['observation.state.right_ee_pose_gripper_base'],
                        x['observation.state.left_gripper'][:,None],
                        x['observation.state.right_gripper'][:,None]], axis=1)
    A = np.concatenate([x['action.left_ee_pose_gripper_base'],
                        x['action.right_ee_pose_gripper_base'],
                        x['action.left_gripper'][:,None],
                        x['action.right_gripper'][:,None]], axis=1)
    return S.astype(np.float64), A.astype(np.float64)

def z(v):
    m = v.mean(0); s = v.std(0); s[s < 1e-8] = 1
    return (v-m)/s

def nn_errors(S, A, h, mode, rng=None):
    """Return normalized action-chunk RMSE for each anchor t."""
    N = len(S)
    if mode == 'state':
        F = z(S)
    elif mode == 'state+vel':
        V = np.zeros_like(S); V[2:] = S[2:]-S[:-2]
        F = np.concatenate([z(S), z(V)], 1)
    elif mode == 'oracle-phase':
        F = z(S)
    ast = A.std(0); ast[ast < 1e-8] = 1
    errs, phase_gap = [], []
    valid_t = np.arange(0, N-h, 1)
    for t in valid_t:
        d = np.sqrt(((F - F[t])**2).sum(1))
        ok = np.ones(N, bool); ok[max(0,t-h-10):min(N,t+h+11)] = False
        ok[N-h:] = False
        if mode == 'oracle-phase':
            prog = np.divide(np.arange(N), N, dtype=float)
            ok &= np.abs(prog - prog[t]) <= 0.05
        if not ok.any():
            continue
        d[~ok] = np.inf
        j = int(np.argmin(d))
        delta = A[j:j+h] - A[t:t+h]
        errs.append(np.sqrt((((delta)/ast)**2).mean()))
        if mode == 'oracle-phase':
            phase_gap.append(abs(j-t)/N)
    return np.array(errs)

out = {'horizons': HS, 'tasks': {}}
for p in sorted(glob.glob('exp/unibot_states/*.npz')):
    name = os.path.splitext(os.path.basename(p))[0]
    if name not in TASKS:
        continue
    d = np.load(p, allow_pickle=True)['contig'].item()
    S, A = vec(d)
    row = {}
    for mode in ['state', 'state+vel', 'oracle-phase']:
        row[mode] = {str(h): float(np.mean(nn_errors(S, A, h, mode))) for h in HS}
    # effective horizon: first h where state-only error > 0.5
    eff = HS[-1]
    for h in HS:
        if row['state'][str(h)] > 0.5:
            eff = h; break
    row['h_star'] = eff
    out['tasks'][name] = {'task_id': TASKS[name], **row}
    print(name, TASKS[name], 'h*=', eff, {k: round(row['state'][str(k)],3) for k in HS})
json.dump(out, open('exp/r3_imitation_horizon.json','w'), indent=1)
