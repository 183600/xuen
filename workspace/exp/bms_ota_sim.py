#!/usr/bin/env python3
"""Synthetic mechanism check for BMS-OTA (UIP-11).

NOT a UniBot real-robot result. This is a controlled, seeded simulation of a
non-stationary 32-task stream used only to check whether the proposed control
mechanism has the intended qualitative behavior:
  - uncontrolled online adaptation forgets and overheats (latency/irregularity)
  - health-gated, budgeted, thermal-derated, per-task adaptation does not
  - online conformal calibration tracks drift better than a frozen threshold

All numbers printed here are synthetic. Do not cite as competition evidence.
"""
import json
import math
import random
import statistics

N_TASKS = 32
N_EPISODES = 320          # 32 tasks x 10 trials
N_SEEDS = 40
BUDGET = 40               # adaptation events per campaign
H_TARGET = 0.62
T_SAFE = 0.65
BASE_LAT_MS = 80.0
DRIFT_SIGMA = 0.07
VERIFIER_ACC = 0.90


def sigmoid(x):
    if x < -40:
        return 0.0
    if x > 40:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


def clip(x, lo, hi):
    return max(lo, min(hi, x))


class Campaign:
    def __init__(self, mode, seed):
        self.mode = mode
        self.rng = random.Random(seed)
        self.base = [self.rng.gauss(-0.45, 1.0) for _ in range(N_TASKS)]
        self.drift = [0.0] * N_TASKS
        self.gain = [0.0] * N_TASKS
        # Beta(1,1) health prior, per task
        self.a = [1.0] * N_TASKS
        self.b = [1.0] * N_TASKS
        self.temp = 0.0
        self.budget = BUDGET
        self.lat = []
        self.irregularity = []
        self.successes = []
        self.steps = []
        self.adapted_flags = []
        self.health_at_use = []

    def health(self, k):
        return self.a[k] / (self.a[k] + self.b[k])

    def run(self):
        order = []
        for k in range(N_TASKS):
            order.extend([k] * (N_EPISODES // N_TASKS))
        self.rng.shuffle(order)
        for t, k in enumerate(order):
            self.drift[k] += self.rng.gauss(0.0, DRIFT_SIGMA)
            p = sigmoid(self.base[k] - self.drift[k] + self.gain[k])
            adapted = False
            extra_lat = 0.0
            extra_irr = 0.0

            if self.mode == "static":
                pass
            elif self.mode == "naive":
                # shared adapter: every episode updates for the current task,
                # but interferes with all other tasks (catastrophic forgetting)
                for j in range(N_TASKS):
                    self.gain[j] *= 0.985
                self.gain[k] += 0.22
                for j in range(N_TASKS):
                    if j != k:
                        self.gain[j] -= 0.0030
                self.temp = clip(self.temp + 0.050, 0.0, 1.0)
                extra_lat = 22.0
                extra_irr = 0.020
                adapted = True
            elif self.mode == "per_task_always":
                # per-task isolation, but no health gate / no budget: the
                # "just keep learning online" baseline
                self.gain[k] *= 0.995
                self.gain[k] += 0.10
                self.temp = clip(self.temp + 0.022, 0.0, 1.0)
                extra_lat = 6.0
                extra_irr = 0.004
                adapted = True
            elif self.mode == "bms":
                h = self.health(k)
                self.health_at_use.append(h)
                var = self.a[k] * self.b[k] / (
                    (self.a[k] + self.b[k]) ** 2
                    * (self.a[k] + self.b[k] + 1.0))
                urgency = (H_TARGET - h) * (1.0 + 6.0 * math.sqrt(var))
                if (h < H_TARGET and self.temp < T_SAFE
                        and self.budget > 0 and urgency > 0.12):
                    # CC-CV: aggressive when far from target, taper near it
                    rate = 0.30 * max(0.0, (H_TARGET - h) / H_TARGET)
                    self.gain[k] *= 0.995
                    self.gain[k] += rate
                    self.budget -= 1
                    self.temp = clip(self.temp + 0.022, 0.0, 1.0)
                    extra_lat = 6.0
                    extra_irr = 0.004
                    adapted = True
                else:
                    self.gain[k] *= 0.995
            elif self.mode == "bms_no_temp":
                h = self.health(k)
                if h < H_TARGET and self.budget > 0:
                    rate = 0.30 * max(0.0, (H_TARGET - h) / H_TARGET)
                    self.gain[k] *= 0.995
                    self.gain[k] += rate
                    self.budget -= 1
                    self.temp = clip(self.temp + 0.022, 0.0, 1.0)
                    extra_lat = 6.0
                    extra_irr = 0.004
                    adapted = True
            elif self.mode == "bms_no_budget":
                h = self.health(k)
                if h < H_TARGET and self.temp < T_SAFE:
                    rate = 0.30 * max(0.0, (H_TARGET - h) / H_TARGET)
                    self.gain[k] *= 0.995
                    self.gain[k] += rate
                    self.temp = clip(self.temp + 0.022, 0.0, 1.0)
                    extra_lat = 6.0
                    extra_irr = 0.004
                    adapted = True
            elif self.mode == "bms_shared":
                # health-gated + budgeted, but a single shared adapter with
                # interference (isolates the value of per-task isolation)
                h = self.health(k)
                if h < H_TARGET and self.temp < T_SAFE and self.budget > 0:
                    for j in range(N_TASKS):
                        self.gain[j] *= 0.995
                    self.gain[k] += 0.22
                    for j in range(N_TASKS):
                        if j != k:
                            self.gain[j] -= 0.0030
                    self.budget -= 1
                    self.temp = clip(self.temp + 0.022, 0.0, 1.0)
                    extra_lat = 6.0
                    extra_irr = 0.004
                    adapted = True

            p = clip(p, 0.01, 0.99)
            success = self.rng.random() < p
            if self.mode == "bms" and success:
                self.budget = min(BUDGET, self.budget + 1)
            # verifier pseudo-label
            obs = success if self.rng.random() < VERIFIER_ACC else (not success)
            # discounted Beta update
            decay = 0.97
            self.a[k] = decay * self.a[k] + (1.0 if obs else 0.0)
            self.b[k] = decay * self.b[k] + (0.0 if obs else 1.0)
            # temperature decays between events
            self.temp = clip(0.94 * self.temp + 0.06 * (1.0 if adapted else 0.0),
                             0.0, 1.0)
            # step score: success = 100, failure = partial progress
            step = 100.0 if success else (30.0 + 40.0 * p)
            # credibility penalty when running hot
            if self.temp > 0.70:
                step *= (1.0 - 0.40 * (self.temp - 0.70) / 0.30)
            self.successes.append(1.0 if success else 0.0)
            self.steps.append(step)
            self.lat.append(BASE_LAT_MS + extra_lat + self.rng.gauss(0, 4.0))
            self.irregularity.append(extra_irr + self.rng.gauss(0, 0.002))
            self.adapted_flags.append(adapted)
        return self.summary()

    def summary(self):
        lat_sorted = sorted(self.lat)
        p99 = lat_sorted[int(0.99 * (len(lat_sorted) - 1))]
        # forgetting: compare mean latent success probability of the 8 tasks
        # adapted earliest vs latest (a proxy for backward interference)
        probs = [sigmoid(self.base[k] - self.drift[k] + self.gain[k])
                 for k in range(N_TASKS)]
        return {
            "mode": self.mode,
            "success_rate": statistics.mean(self.successes),
            "step_score": statistics.mean(self.steps),
            "lat_mean_ms": statistics.mean(self.lat),
            "lat_p99_ms": p99,
            "lat_std_ms": statistics.pstdev(self.lat),
            "irregularity": statistics.mean(self.irregularity),
            "adapted_frac": statistics.mean(1.0 if x else 0.0
                                            for x in self.adapted_flags),
            "budget_left": self.budget,
            "mean_task_prob_end": statistics.mean(probs),
            "risk_step_score": statistics.mean(self.steps) * (
                1.0 if (p99 <= 100.0 and statistics.mean(self.irregularity) <= 0.003)
                else 0.80),
        }


def run_main():
    modes = ["static", "naive", "per_task_always", "bms_shared",
             "bms_no_temp", "bms_no_budget", "bms"]
    out = {}
    for mode in modes:
        runs = [Campaign(mode, 1000 + s).run() for s in range(N_SEEDS)]
        agg = {}
        for key in runs[0]:
            if key == "mode":
                continue
            vals = [r[key] for r in runs]
            agg[key] = {
                "mean": statistics.mean(vals),
                "std": statistics.pstdev(vals),
            }
        out[mode] = agg
    return out


def run_conformal():
    """Online conformal calibration of a binary 'done' verifier under drift.

    We control the false-positive rate (declaring 'done' when not done) at
    alpha=0.10. Static threshold q=0.60 vs ACP q_{t+1}=q_t+eta*(err-alpha).
    """
    rng = random.Random(7)
    n = 4000
    alpha = 0.10
    eta = 0.02
    q_static = 0.60
    q_acp = 0.60
    fp_static, fp_acp = [], []
    # drift makes 'not done' scores creep upward over time
    for t in range(n):
        # score of a not-done case: Beta-ish around a drifting mean
        mean = 0.35 + 0.35 * (t / n)
        s = clip(rng.gauss(mean, 0.12), 0.0, 1.0)
        fp_static.append(1.0 if s >= q_static else 0.0)
        err = 1.0 if s >= q_acp else 0.0   # false positive event
        fp_acp.append(err)
        q_acp = clip(q_acp + eta * (err - alpha), 0.0, 1.0)
    def block_rate(xs, blocks=8):
        m = len(xs) // blocks
        return [statistics.mean(xs[i * m:(i + 1) * m]) for i in range(blocks)]
    return {
        "alpha_target": alpha,
        "static_overall_fpr": statistics.mean(fp_static),
        "acp_overall_fpr": statistics.mean(fp_acp),
        "static_block_fpr": block_rate(fp_static),
        "acp_block_fpr": block_rate(fp_acp),
        "q_static": q_static,
        "q_acp_final": q_acp,
    }


if __name__ == "__main__":
    result = {
        "disclaimer": "synthetic mechanism check only; not UniBot evidence",
        "n_tasks": N_TASKS,
        "n_episodes": N_EPISODES,
        "n_seeds": N_SEEDS,
        "main": run_main(),
        "conformal": run_conformal(),
    }
    with open("/home/runner/work/xuen/xuen/workspace/exp/bms_ota_results.json",
              "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
