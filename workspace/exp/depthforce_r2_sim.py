"""Round-2 mechanism experiment (NOT a benchmark).

1-D lateral peg-in-hole with a chamfer, depth estimate, position-tracking
residual ("force shadow"), and a position-space compliance gain beta.

The model is deliberately explicit and small. It is used only to generate
hypotheses about (a) when depth alone is enough, (b) when contact feedback
is needed, and (c) whether compliance helps or hurts. It does not fit any
leaderboard number.
"""
import numpy as np

DT = 0.001
T = 1.2
M = 0.5
B = 5.0
K = 2000.0          # nominal position-controller stiffness (N/m)
F_AX = 10.0         # axial insertion force (N)
ALPHA = np.deg2rad(30.0)
MU = 0.20
F_JAM = 40.0
X_MAX = 0.05


def one_episode(rng, e, e_d, c, beta, contact_servo, n_probe=12, probe=0.0015,
                p_detect=1.0, p_flip=0.0):
    """Return (success, final_abs_error, n_contacts, jammed)."""
    x = e
    v = 0.0
    k_eff = max(1e-6, (1.0 - beta) * K)
    tan_a = np.tan(ALPHA)
    # net lateral force coefficient available from the chamfer, toward centre
    f_ch = F_AX * max(0.0, tan_a - MU)
    ref = e_d
    n_contact = 0
    jammed = False
    probes = 0
    for _ in range(int(T / DT)):
        if abs(x) <= c:
            return True, abs(x), n_contact, False
        # controller pulls x toward the current reference
        f_ctrl = -k_eff * (x - ref)
        # chamfer pushes toward the hole centre (sign of x)
        f_cham = -f_ch * np.sign(x)
        f_net = f_ctrl + f_cham
        # If the controller is winning, the peg is pressed into the wall.
        if abs(f_ctrl) > f_ch and abs(x) > c:
            n_contact += 1
            if contact_servo and probes < n_probe:
                # imperfect force shadow: may miss or flip the contact side
                if rng.random() < p_detect:
                    sgn = np.sign(x) * (-1.0 if rng.random() < p_flip else 1.0)
                    ref -= sgn * probe
                    probes += 1
            elif not contact_servo and abs(f_ctrl) > F_JAM:
                jammed = True
                return False, abs(x), n_contact, jammed
        a = (f_net - B * v) / M
        v += a * DT
        x += v * DT
        if abs(x) > X_MAX:
            return False, abs(x), n_contact, True
    return abs(x) <= c, abs(x), n_contact, False


def run(sigma_e=0.006, sigma_d=0.003, c=0.001, beta=0.0,
        contact_servo=False, p_detect=1.0, p_flip=0.0, n_probe=12,
        n=20000, seed=0):
    rng = np.random.default_rng(seed)
    ok = 0
    errs = []
    contacts = 0
    jams = 0
    for _ in range(n):
        e = rng.normal(0.0, sigma_e)
        e_d = e + rng.normal(0.0, sigma_d)
        s, err, nc, j = one_episode(rng, e, e_d, c, beta, contact_servo,
                                        n_probe=n_probe, p_detect=p_detect, p_flip=p_flip)
        ok += int(s)
        errs.append(err)
        contacts += nc
        jams += int(j)
    return dict(success=ok / n, mean_err=float(np.mean(errs)),
                mean_contacts=contacts / n, jam_rate=jams / n)


if __name__ == "__main__":
    print("== A. clearance x policy (sigma_e=6mm, sigma_d=2mm) ==")
    print(f"{'c(mm)':>6} {'rigid':>8} {'comp0.6':>8} {'comp0.8':>8} "
          f"{'servo':>8} {'servo+0.8':>10}")
    for c_mm in [0.5, 1.0, 2.0, 5.0]:
        c = c_mm / 1000.0
        a = run(c=c, beta=0.0)
        b = run(c=c, beta=0.6)
        d = run(c=c, beta=0.8)
        e = run(c=c, beta=0.0, contact_servo=True)
        f = run(c=c, beta=0.8, contact_servo=True)
        print(f"{c_mm:6.1f} {a['success']:8.3f} {b['success']:8.3f} "
              f"{d['success']:8.3f} {e['success']:8.3f} {f['success']:10.3f}")

    print("\n== B. depth noise x policy (sigma_e=6mm, c=1mm) ==")
    print(f"{'sd(mm)':>6} {'rigid':>8} {'comp0.6':>8} {'comp0.8':>8} "
          f"{'servo':>8} {'servo+0.8':>10}")
    for sd_mm in [0.0, 1.0, 2.0, 4.0, 8.0]:
        sd = sd_mm / 1000.0
        a = run(sigma_d=sd, beta=0.0)
        b = run(sigma_d=sd, beta=0.6)
        d = run(sigma_d=sd, beta=0.8)
        e = run(sigma_d=sd, beta=0.0, contact_servo=True)
        f = run(sigma_d=sd, beta=0.8, contact_servo=True)
        print(f"{sd_mm:6.1f} {a['success']:8.3f} {b['success']:8.3f} "
              f"{d['success']:8.3f} {e['success']:8.3f} {f['success']:10.3f}")

    print("\n== C. force-shadow quality x policy (sigma_e=6mm, sigma_d=4mm, c=1mm) ==")
    print(f"{'p_det':>6} {'p_flip':>7} {'servo':>8} {'servo+0.8':>10}")
    for pd in [0.5, 0.7, 0.85, 1.0]:
        for pf in [0.0, 0.1]:
            a = run(sigma_d=0.004, c=0.001, beta=0.0, contact_servo=True,
                    p_detect=pd, p_flip=pf)
            b = run(sigma_d=0.004, c=0.001, beta=0.8, contact_servo=True,
                    p_detect=pd, p_flip=pf)
            print(f"{pd:6.2f} {pf:7.2f} {a['success']:8.3f} {b['success']:10.3f}")

    print("\n== D. probe budget x policy (sigma_e=6mm, sigma_d=4mm, c=1mm) ==")
    print(f"{'n_probe':>8} {'T_a=4':>7} {'T_a=8':>7} {'servo':>8} {'servo+0.8':>10}")
    for npb in [2, 4, 6, 9, 12, 20]:
        a = run(sigma_d=0.004, c=0.001, beta=0.0, contact_servo=True, n_probe=npb)
        b = run(sigma_d=0.004, c=0.001, beta=0.8, contact_servo=True, n_probe=npb)
        print(f"{npb:8d} {npb*4*33.3:7.0f} {npb*8*33.3:7.0f} {a['success']:8.3f} {b['success']:10.3f}")

    print("\n== E. beta sweep (sigma_e=6mm, sigma_d=3mm, c=1mm) ==")
    for beta in [0.0, 0.2, 0.4, 0.6, 0.8, 0.9, 0.95]:
        a = run(sigma_d=0.003, c=0.001, beta=beta, contact_servo=True)
        print(f"beta={beta:4.2f}  success={a['success']:.3f} "
              f"mean_err={a['mean_err']*1000:.2f}mm "
              f"contacts={a['mean_contacts']:.2f}")
