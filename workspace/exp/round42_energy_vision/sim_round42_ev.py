#!/usr/bin/env python3
"""Round 42 toy checks: battery/energy reserve x visual-localization evidence.

Stdlib only, fixed seeds. These are mechanism checks, not robot benchmarks.

E79 energy reserve vs point-estimate battery management (incl. SoH aging)
E80 decision-sufficient visual localization under perceptual aliasing
E81 joint reserve: relocalization must be paid from the *return* budget
"""
import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "res_round42_ev.json")


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def e79_energy(seed=20261110, cycles=30000):
    """Repeated task/return cycles with a slowly aging battery.

    Baseline  : point SoC, fixed nameplate capacity, 2% margin.
    Proposed  : lower-confidence SoC, health-aware capacity, worst-case
                task+return estimate plus reserve. No stranding by design
                when the true consumption lies inside the interval.
    """
    rng = random.Random(seed)
    s = 1.0
    health0 = 1.0
    health1 = 0.82
    sigma_s = 0.012

    def cycle(mode, h):
        nonlocal s
        # true consumption in capacity units; spread + rare tail fault
        task = (0.045 + 0.055 * rng.random()) * (0.6 + 0.8 * rng.random())
        ret = (0.020 + 0.030 * rng.random())
        tail = 1.8 if rng.random() < 0.08 else 1.0
        true_task = task / h * tail
        true_ret = ret / h * tail
        # onboard estimates (relative error)
        est_err = 0.10
        task_hat = task / (h if mode == "prop" else health0)
        ret_hat = ret / (h if mode == "prop" else health0)

        if mode == "base":
            s_hat = s + rng.gauss(0.0, sigma_s)
            depart = s_hat > task_hat + ret_hat + 0.02
        else:
            s_lo = max(0.0, s - 2.0 * sigma_s)
            u = est_err + (1.0 - h) * 0.6
            depart = s_lo > (task_hat + ret_hat) * (1.0 + u) + 0.02
        if not depart:
            s = 1.0
            return "recharge", False, 0.0
        # execute task
        s -= true_task
        if s < 0.0:
            s = 0.0
            return "strand_task", True, true_task
        # return
        s -= true_ret
        if s < 0.0:
            s = 0.0
            return "strand_return", True, true_task + true_ret
        spend = true_task + true_ret
        if s < 0.10:
            s = 1.0
            return "done+recharge", False, spend
        return "done", False, spend

    out = {}
    for mode in ("base", "prop"):
        s = 1.0
        rng = random.Random(seed)
        first = {"n": 0, "strand": 0, "done": 0, "recharge": 0, "spend": 0.0}
        second = {"n": 0, "strand": 0, "done": 0, "recharge": 0, "spend": 0.0}
        for i in range(cycles):
            h = health0 + (health1 - health0) * i / (cycles - 1)
            tag, strand, spend = cycle(mode, h)
            bucket = first if i < cycles // 2 else second
            bucket["n"] += 1
            bucket["strand"] += int(strand)
            bucket["done"] += int(tag.startswith("done"))
            bucket["recharge"] += int("recharge" in tag)
            bucket["spend"] += spend
        out[mode] = {
            "first_half": _rate(first),
            "second_half": _rate(second),
            "all": _rate({
                k: first[k] + second[k] for k in first
            }),
        }
    return out


def _rate(b):
    n = max(1, b["n"])
    return {
        "cycles": b["n"],
        "strand_rate": b["strand"] / n,
        "task_complete_rate": b["done"] / n,
        "recharge_rate": b["recharge"] / n,
        "mean_energy_per_cycle": b["spend"] / n,
    }


def e80_localization(seed=20261110, episodes=6000):
    """Drive toward a goal before an obstacle; a persistent perceptual-aliasing
    zone returns a second hypothesis displaced by 3 m.

    Baseline trusts the top-1 visual hypothesis. Proposed requires all
    remaining hypotheses to agree on the guard sign; if not, it spends one
    step to relocalize (85% resolves to truth) or degrades to stop.
    """
    limit = 7.65          # largest believed position at which motion is safe
    goal = 7.45
    unsafe = 7.75
    step = 0.05
    p_alias = 0.60
    alias_wrong_top = 0.35
    reloc_success = 0.85

    stats = {}
    for mode in ("base", "prop"):
        rng = random.Random(seed)
        succ = uns = 0
        steps = 0
        relocs = 0
        false_safe_steps = 0
        for _ in range(episodes):
            p = 0.0
            resolved = False
            has_zone = rng.random() < p_alias
            z0 = rng.uniform(3.0, 5.5)
            z1 = z0 + 4.5
            direction = -1.0 if rng.random() < 0.5 else 1.0
            alias_top = rng.random() < alias_wrong_top
            for _t in range(400):
                steps += 1
                noise = rng.gauss(0.0, 0.03)
                true_h = p + noise
                in_zone = has_zone and (z0 <= p <= z1) and not resolved
                if in_zone:
                    alias_h = p + direction * 3.0 + rng.gauss(0.0, 0.03)
                    hyps = [true_h, alias_h]
                    top = alias_h if alias_top else true_h
                else:
                    hyps = [true_h]
                    top = true_h

                if mode == "base":
                    decision = top <= limit
                else:
                    signs = [h <= limit for h in hyps]
                    if all(signs):
                        decision = True
                    elif not any(signs):
                        decision = False
                    else:
                        relocs += 1
                        if rng.random() < reloc_success:
                            decision = true_h <= limit
                            resolved = True
                        else:
                            decision = False

                if decision:
                    if p > unsafe:
                        false_safe_steps += 1
                        uns += 1
                        break
                    p += step
                    if p > unsafe:
                        false_safe_steps += 1
                        uns += 1
                        break
                else:
                    if p >= goal and p <= unsafe:
                        succ += 1
                    break
            if not (goal <= p <= unsafe):
                pass
        stats[mode] = {
            "success_rate": succ / episodes,
            "unsafe_rate": uns / episodes,
            "false_safe_steps": false_safe_steps,
            "relocalizations_per_episode": relocs / episodes,
            "mean_steps": steps / episodes,
        }
    return stats


def e81_joint(seed=20261110, cycles=30000):
    """Relocalization is an energy consumer. Baseline budgets task+return
    from the point estimate and lets relocalization eat the reserve; the
    proposed one adds a worst-case relocalization charge to the reserve.
    """
    rng = random.Random(seed)
    reloc_cost = 0.012
    sigma_s = 0.012
    out = {}
    for mode in ("base", "prop"):
        rng = random.Random(seed)
        s = 1.0
        strand = 0
        completed = 0
        extra_reloc = 0
        for _ in range(cycles):
            task = (0.035 + 0.045 * rng.random()) * (0.6 + 0.8 * rng.random())
            ret = 0.020 + 0.030 * rng.random()
            tail = 1.6 if rng.random() < 0.06 else 1.0
            true_task, true_ret = task * tail, ret * tail
            # expected number of relocalizations in this cycle
            k = 0
            while rng.random() < 0.35:
                k += 1
            true_reloc = k * reloc_cost
            s_lo = max(0.0, s - 2.0 * sigma_s)

            if mode == "base":
                depart = s_lo > true_task + true_ret + 0.015
            else:
                # worst-case relocalization charge is reserved up front
                depart = s_lo > (true_task + true_ret) * 1.12 + k * reloc_cost + 0.02
            if not depart:
                s = 1.0
                continue
            s -= true_reloc
            extra_reloc += true_reloc
            s -= true_task
            if s < 0.0:
                s = 0.0
                strand += 1
                continue
            s -= true_ret
            if s < 0.0:
                s = 0.0
                strand += 1
                continue
            completed += 1
            if s < 0.10:
                s = 1.0
        out[mode] = {
            "strand_rate": strand / cycles,
            "task_complete_rate": completed / cycles,
            "mean_reloc_energy": extra_reloc / cycles,
        }
    return out


def main():
    res = {
        "E79_energy_reserve": e79_energy(),
        "E80_visual_localization": e80_localization(),
        "E81_joint_reserve": e81_joint(),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
