"""Round-44 toy mechanism check: multi-task certificate non-regression.

Setting
-------
A single shared backbone serves K tasks. Each task tau has a hidden safety
margin mu_tau (headroom above the guard threshold theta). Certifying task tau
means claiming mu_tau >= theta from a finite calibration set (noisy LCB).

Each round a new task arrives. Training it on the shared backbone perturbs
every *shared* task's margin (negative transfer / interference). Policies:

  naive     accept every update; never re-calibrate retained certificates
  gated     accept update, re-calibrate shared tasks, drop those below theta
  rollback  reject the whole update if any retained task's fresh LCB < theta
  isolate   all initially certified tasks live in frozen per-task adapters
            (zero transfer); every new task gets its own adapter
  hybrid    freeze only the most fragile fraction of certified tasks; the
            rest share the backbone under a per-update non-regression gate
            (the proposed IP-61 policy)

Reported: silent failures (claimed certified while true margin < theta),
retained certified count, new-task adoption, adapter count, recalibration cost.

Synthetic and small on purpose: this checks the *mechanism*, not the robot.
Fixed seeds for reproducibility.
"""
import json
import random

THETA = 0.35
K_OLD = 80
T_UPDATES = 60
N_CAL = 40
SIGMA = 0.10
Z = 1.64
FRAGILE_FRAC = 0.40


def lcb(true_mu, rng):
    obs = [true_mu + rng.gauss(0.0, SIGMA) for _ in range(N_CAL)]
    return sum(obs) / len(obs) - Z * SIGMA / (len(obs) ** 0.5)


def new_task_margin(rng):
    return rng.uniform(0.25, 1.0)


def run(policy, seed=44, transfer_mean=-0.004, transfer_std=0.030,
        common_std=0.012):
    rng = random.Random(seed)
    mu = [new_task_margin(rng) for _ in range(K_OLD)]
    certified = {i for i in range(K_OLD) if lcb(mu[i], rng) >= THETA}

    frozen = set()
    if policy == "isolate":
        frozen = set(certified)
    elif policy == "hybrid":
        order = sorted(certified, key=lambda i: mu[i])
        n_frag = int(len(order) * FRAGILE_FRAC)
        frozen = set(order[:n_frag])

    accepted = 0
    recals = 0
    for _ in range(T_UPDATES):
        common = rng.gauss(0.0, common_std)
        delta = [common + rng.gauss(transfer_mean, transfer_std)
                 for _ in range(len(mu))]
        shared = [i for i in certified if i not in frozen]

        if policy == "isolate":
            # shared backbone untouched for certified tasks; new task isolated
            m_new = new_task_margin(rng)
            recals += 1
            if lcb(m_new, rng) >= THETA:
                mu.append(m_new)
                certified.add(len(mu) - 1)
                frozen.add(len(mu) - 1)
                accepted += 1
            continue

        if policy == "naive":
            for i in shared:
                mu[i] += delta[i]
            m_new = new_task_margin(rng)
            mu.append(m_new)
            if lcb(m_new, rng) >= THETA:
                certified.add(len(mu) - 1)
                accepted += 1
            continue

        if policy == "gated":
            for i in shared:
                mu[i] += delta[i]
            kept = set(frozen)
            for i in shared:
                recals += 1
                if lcb(mu[i], rng) >= THETA:
                    kept.add(i)
            certified = kept
            m_new = new_task_margin(rng)
            recals += 1
            if lcb(m_new, rng) >= THETA:
                mu.append(m_new)
                certified.add(len(mu) - 1)
                accepted += 1
            continue

        if policy == "rollback":
            recals += len(shared) + 1
            if all(lcb(mu[i] + delta[i], rng) >= THETA for i in shared):
                for i in shared:
                    mu[i] += delta[i]
                m_new = new_task_margin(rng)
                if lcb(m_new, rng) >= THETA:
                    mu.append(m_new)
                    certified.add(len(mu) - 1)
                    accepted += 1
            continue

        if policy == "hybrid":
            # frozen tasks never regress; shared tasks pass a non-regression gate
            for i in shared:
                mu[i] += delta[i]
            kept = set(frozen)
            for i in shared:
                recals += 1
                if lcb(mu[i], rng) >= THETA:
                    kept.add(i)
            certified = kept
            m_new = new_task_margin(rng)
            recals += 1
            if lcb(m_new, rng) >= THETA:
                mu.append(m_new)
                certified.add(len(mu) - 1)
                accepted += 1
            continue

        raise ValueError(policy)

    silent = sum(1 for i in certified if mu[i] < THETA)
    return {
        "policy": policy,
        "certified_retained": len(certified),
        "new_tasks_adopted": accepted,
        "silent_failures": silent,
        "certified_silent_rate": round(silent / max(1, len(certified)), 4),
        "adapter_count": len(frozen),
        "recalibration_samples": recals * N_CAL,
    }


def main():
    seeds = list(range(44, 64))
    policies = ["naive", "gated", "rollback", "isolate", "hybrid"]
    out = {}
    for p in policies:
        rows = [run(p, seed=s) for s in seeds]
        keys = rows[0].keys() - {"policy"}
        out[p] = {k: round(sum(r[k] for r in rows) / len(rows), 2)
                  for k in keys}
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
