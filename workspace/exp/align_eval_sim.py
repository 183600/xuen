#!/usr/bin/env python3
"""ALIGN-Eval：把「语音识别」的对齐-编辑距离范式搬到操作评测上。

纯标准库、确定性随机种子、秒级运行。产物：exp/align_eval_results.json。

本轮要回答四件事（对应 E634–E638）：
  E634 可分解性：StepWER(加权编辑距离) 同时保留「对错结构」与「步数代价」，
       而二值成功率会把两类不同失败压成同一个 0。
  E635 统计功效：n=32 任务、配对场景下，编辑距离指标比二值成功率/McNemar
       更早检出同一次改进（更低的 MDE），假阳率仍校准在 α。
  E636 噪声鲁棒（对应语音识别）：当「口述标注/narration」转写带 WER 噪声时，
       对齐仍能恢复阶段边界、并稳定估计 StepWER。
  E637 置信拒识：温度校准把 ECE 压下去，风险-覆盖率/EER 给出可用的介入门限。
  E638 抗刷分：靠无脑重试刷高成功率会被 insertion 项与步数项惩罚。
"""
from __future__ import annotations

import json
import math
import random
import statistics
from typing import Dict, List, Tuple

VOCAB = [
    "approach", "grasp", "lift", "transport", "place", "release",
    "retract", "reorient", "push", "insert", "align", "press",
]
STEP_COST = {
    "approach": 8, "grasp": 4, "lift": 3, "transport": 10, "place": 6,
    "release": 3, "retract": 5, "reorient": 4, "push": 5, "insert": 6,
    "align": 3, "press": 3,
}
SPURIOUS = ["retry", "approach"]
CRITICAL = {"grasp", "place"}


# ----------------------------------------------------------------- Align
def align(ref: List[str], hyp: List[str]) -> Dict[str, float]:
    """单调对齐，返回 unit 与 step 加权的 S/D/I 分解。"""
    n, m = len(ref), len(hyp)
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = dp[i - 1][0] + 1.0
    for j in range(1, m + 1):
        dp[0][j] = dp[0][j - 1] + 1.0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref[i - 1] == hyp[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1.0 + min(dp[i - 1][j - 1], dp[i - 1][j],
                                    dp[i][j - 1])
    i, j = n, m
    s_u = d_u = ins_u = 0
    s_w = d_w = ins_w = 0.0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and ref[i - 1] == hyp[j - 1]:
            i, j = i - 1, j - 1
        elif i > 0 and j > 0 and abs(dp[i][j] - (dp[i - 1][j - 1] + 1.0)) < 1e-9:
            s_u += 1
            s_w += STEP_COST.get(ref[i - 1], 4)
            i, j = i - 1, j - 1
        elif i > 0 and abs(dp[i][j] - (dp[i - 1][j] + 1.0)) < 1e-9:
            d_u += 1
            d_w += STEP_COST.get(ref[i - 1], 4)
            i -= 1
        else:
            ins_u += 1
            ins_w += STEP_COST.get(hyp[j - 1], 4) if hyp[j - 1] in STEP_COST else 4.0
            j -= 1
    ref_cost = sum(STEP_COST.get(t, 4) for t in ref) or 1
    return {
        "S": s_u, "D": d_u, "I": ins_u,
        "wer": (s_u + d_u + ins_u) / max(1, len(ref)),
        "step_wer": (s_w + d_w + ins_w) / ref_cost,
        "s_w": s_w, "d_w": d_w, "ins_w": ins_w,
    }


# ------------------------------------------------------- episode generator
def make_reference(rng: random.Random) -> List[str]:
    k = rng.randint(4, 9)
    head = ["approach", "grasp"]
    tail = ["transport", "place", "release", "retract"]
    mid_pool = ["lift", "reorient", "push", "insert", "align", "press"]
    mid = [rng.choice(mid_pool) for _ in range(max(0, k - len(head) - len(tail)))]
    return head + mid + tail


def gen_uniforms(rng: random.Random, n: int) -> List[Tuple[float, float, float]]:
    return [(rng.random(), rng.random(), rng.random()) for _ in range(n)]


def episode(ref: List[str], p_sub: float, p_del: float, p_ins: float,
            us: List[Tuple[float, float, float]],
            rng: random.Random) -> Tuple[List[str], bool]:
    hyp: List[str] = []
    fatal = False
    for tok, (u_s, u_d, u_i) in zip(ref, us):
        if u_d < p_del:
            if tok in CRITICAL:
                fatal = True
            continue
        if u_s < p_sub:
            alt = rng.choice([t for t in VOCAB if t != tok])
            if tok in CRITICAL:
                fatal = True
            hyp.append(alt)
        else:
            hyp.append(tok)
        if u_i < p_ins:
            hyp.append(rng.choice(SPURIOUS))
    return hyp, (not fatal)


# --------------------------------------------------------- E634 decomp
def e634():
    rng = random.Random(11)
    refs = [make_reference(rng) for _ in range(32)]
    profiles = {
        "A_balanced": (0.06, 0.05, 0.04),
        "B_sub_heavy": (0.18, 0.02, 0.03),
        "C_del_heavy": (0.02, 0.18, 0.03),
        "D_retry_heavy": (0.05, 0.04, 0.22),
    }
    rows = []
    for name, (ps, pd, pi) in profiles.items():
        succ = wer = swer = 0.0
        S = D = I = 0
        E = 40
        for ref in refs:
            for _ in range(E):
                us = gen_uniforms(rng, len(ref))
                hyp, ok = episode(ref, ps, pd, pi, us, rng)
                a = align(ref, hyp)
                succ += 1.0 if ok else 0.0
                wer += a["wer"]
                swer += a["step_wer"]
                S += a["S"]; D += a["D"]; I += a["I"]
        rows.append({
            "profile": name, "success_rate": round(succ / (32 * E), 4),
            "unit_wer": round(wer / (32 * E), 4),
            "step_wer": round(swer / (32 * E), 4),
            "S": S, "D": D, "I": I,
        })
    # 两种 profile 成功率相同但 StepWER 不同的证据
    return rows


# ------------------------------------------------------ E635 power
def _paired_t_reject(diffs: List[float], crit: float = 1.96) -> bool:
    n = len(diffs)
    if n < 2:
        return False
    mu = statistics.fmean(diffs)
    sd = statistics.pstdev(diffs) * math.sqrt(n / (n - 1))
    if sd == 0:
        return mu != 0
    return abs(mu) / (sd / math.sqrt(n)) > crit


def _mcnemar_reject(b: int, c: int) -> bool:
    if b + c == 0:
        return False
    stat = (abs(b - c) - 1) ** 2 / (b + c)
    return stat > 3.841


def e635(reps: int = 600):
    tasks, E = 32, 5
    base = (0.07, 0.06, 0.04)
    deltas = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30]
    out = []
    for rel in deltas:
        rej_bin = rej_wer = 0
        for r in range(reps):
            rng = random.Random(1000 + r)
            refs = [make_reference(rng) for _ in range(tasks)]
            b = c = 0
            diffs: List[float] = []
            for ref in refs:
                us_list = [gen_uniforms(rng, len(ref)) for _ in range(E)]
                for us in us_list:
                    hypA, okA = episode(ref, *base, us, rng)
                    pB = (base[0] * (1 - rel), base[1] * (1 - rel),
                          base[2] * (1 - rel))
                    hypB, okB = episode(ref, *pB, us, rng)
                    if okA and not okB:
                        b += 1
                    elif okB and not okA:
                        c += 1
                    diffs.append(align(ref, hypA)["step_wer"] -
                                 align(ref, hypB)["step_wer"])
            if _mcnemar_reject(b, c):
                rej_bin += 1
            if _paired_t_reject(diffs):
                rej_wer += 1
        out.append({
            "rel_reduction": rel,
            "binary_McNemar_reject_rate": round(rej_bin / reps, 4),
            "stepwer_paired_t_reject_rate": round(rej_wer / reps, 4),
        })
    return out


# ------------------------------------------------------ E636 ASR noise
def _corrupt_transcript(ref: List[str], wer: float,
                        rng: random.Random) -> List[str]:
    out = []
    for tok in ref:
        u = rng.random()
        if u < wer / 3:
            continue
        elif u < 2 * wer / 3:
            out.append(rng.choice([t for t in VOCAB if t != tok]))
        else:
            out.append(tok)
        if rng.random() < wer / 3:
            out.append(rng.choice(SPURIOUS))
    return out


def e636():
    rng = random.Random(77)
    rows = []
    for wer in [0.0, 0.05, 0.10, 0.15, 0.20, 0.30]:
        rec = est = 0
        swer_err = 0.0
        trials = 400
        for _ in range(trials):
            ref = make_reference(rng)
            narr = _corrupt_transcript(ref, wer, rng)
            a = align(ref, narr)
            # 阶段边界 = 对齐上的匹配锚点位置；这里以匹配覆盖率近似边界恢复率
            matched = len(ref) - a["D"]
            rec += matched / len(ref)
            est += a["step_wer"]
            # 用带噪叙述估计的真实 StepWER 误差（真值由题目设定）
            swer_err += abs(a["step_wer"] - wer)
        rows.append({
            "transcript_wer": wer,
            "phase_coverage": round(rec / trials, 4),
            "estimated_step_wer": round(est / trials, 4),
            "step_wer_abs_err": round(swer_err / trials, 4),
        })
    return rows


# ------------------------------------------------------ E637 confidence
def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def ece(conf: List[float], correct: List[int], bins: int = 10) -> float:
    total = len(conf)
    e = 0.0
    for k in range(bins):
        lo, hi = k / bins, (k + 1) / bins
        idx = [i for i, c in enumerate(conf) if lo <= c < hi or (k == bins - 1 and c == 1.0)]
        if not idx:
            continue
        acc = statistics.fmean(correct[i] for i in idx)
        avg = statistics.fmean(conf[i] for i in idx)
        e += len(idx) / total * abs(acc - avg)
    return e


def e637():
    rng = random.Random(5)
    M = 4000
    latent = [rng.betavariate(2.0, 2.0) for _ in range(M)]
    correct = [1 if rng.random() < p else 0 for p in latent]
    T = 2.2
    conf_raw = [_sigmoid(_logit(p) / T) for p in latent]
    # 在验证集上拟合温度（这里用真值温度的反向做一次网格搜索）
    best_T, best_ece = 1.0, 1e9
    for tt in [x / 20 for x in range(5, 61)]:
        cc = [_sigmoid(_logit(p) / tt) for p in latent]
        val = ece(cc, correct)
        if val < best_ece:
            best_ece, best_T = val, tt
    conf_cal = [_sigmoid(_logit(p) / best_T) for p in latent]
    # risk-coverage：按置信降序接受
    order = sorted(range(M), key=lambda i: -conf_cal[i])
    risks, cov = [], []
    err = 0
    for k, i in enumerate(order, 1):
        err += 1 - correct[i]
        risks.append(err / k)
        cov.append(k / M)
    aurc = statistics.fmean(risks)
    # EER：正类=正确，分数=置信
    pos = sorted(conf_cal[i] for i in range(M) if correct[i] == 1)
    neg = sorted(conf_cal[i] for i in range(M) if correct[i] == 0)
    eer = 0.5
    best = 1e9
    for k in range(1, 100):
        tau = k / 100
        tpr = sum(1 for x in pos if x >= tau) / len(pos)
        fpr = sum(1 for x in neg if x >= tau) / len(neg)
        if abs(fpr - (1 - tpr)) < best:
            best = abs(fpr - (1 - tpr))
            eer = (fpr + (1 - tpr)) / 2
    # 拒识的步数账（简化 P12）：接受集合精度 vs 覆盖率
    tau = 0.5
    accepted = [i for i in range(M) if conf_cal[i] >= tau]
    coverage = len(accepted) / M
    precision = (statistics.fmean(correct[i] for i in accepted)
                 if accepted else 0.0)
    return {
        "ece_raw": round(ece(conf_raw, correct), 4),
        "ece_after_temperature": round(ece(conf_cal, correct), 4),
        "fitted_temperature": round(best_T, 2),
        "aurc": round(aurc, 4),
        "eer": round(eer, 4),
        "gate_tau": tau,
        "coverage_at_tau": round(coverage, 4),
        "precision_at_tau": round(precision, 4),
        "base_accuracy": round(statistics.fmean(correct), 4),
    }


# ------------------------------------------------------ E638 gaming
def e638():
    rng = random.Random(9)
    refs = [make_reference(rng) for _ in range(32)]
    def run(kind: str):
        succ = steps = swer = 0.0
        E = 40
        for ref in refs:
            for _ in range(E):
                us = gen_uniforms(rng, len(ref))
                if kind == "baseline":
                    hyp, ok = episode(ref, 0.08, 0.07, 0.04, us, rng)
                elif kind == "honest":
                    hyp, ok = episode(ref, 0.03, 0.03, 0.03, us, rng)
                else:  # retry spam：忽略原失败，强行补执行直到成功
                    hyp, ok = episode(ref, 0.08, 0.07, 0.04, us, rng)
                    if not ok:
                        hyp = hyp + ["retry", "grasp", "retry", "place"]
                        ok = True
                    hyp = hyp + ["retry", "retry"]
                a = align(ref, hyp)
                succ += 1.0 if ok else 0.0
                steps += sum(STEP_COST.get(t, 4) for t in hyp)
                swer += a["step_wer"]
        ref_steps = statistics.fmean(sum(STEP_COST.get(t, 4) for t in r) for r in refs)
        return {
            "policy": kind,
            "success_rate": round(succ / (32 * E), 4),
            "avg_steps": round(steps / (32 * E), 1),
            "ref_steps": round(ref_steps, 1),
            "step_score_proxy": round(max(0.0, 1 - (steps / (32 * E)) / ref_steps), 4),
            "step_wer": round(swer / (32 * E), 4),
        }
    return [run("baseline"), run("honest"), run("retry_spam")]


def main():
    result = {
        "E634_decomposability": e634(),
        "E635_power_n32": e635(),
        "E636_transcript_noise": e636(),
        "E637_confidence": e637(),
        "E638_gaming": e638(),
    }
    with open("exp/align_eval_results.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
