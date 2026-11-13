#!/usr/bin/env python3
"""SEXTANT 第 66 轮玩具级压力仿真（synthetic, 给数量级而非真实机器人结论）。

A. 多视点语义归因：H_lang / H_perc / H_map 能否随视点数可分。
B. 信息-风险视点规划 vs 最近优先/最大信息优先。
C. 撤退证书：静态 vs 动态阻挡下的 dead-end 率（含证书依赖地图的残余风险）。
D. 指令污点防火墙：环境文本注入的目标劫持率。
E. 语义谄媚：自评 vs 独立验证器对已证伪声明的误判。
"""
import json
import numpy as np

rng = np.random.default_rng(20261113 + 66)

# ---------------------------------------------------------------- A
def sim_attribution(n_ep=20000, ks=(1, 2, 3, 5, 8, 12)):
    """语义声明与观测冲突时，判 H_lang / H_perc / H_map。

    观测 o=1 支持该声明，o=0 反驳。三种故障的**视点/时间签名**不同：
      H_lang : 声明错；世界一致反驳，任意视点 P(支持)=0.10；
      H_perc : 声明对；每个视点以 0.25 概率被本视点特有的遮挡/反光带偏，
               带偏时 P(支持)=0.10，否则 0.90，视点间独立 -> 平稳 0.70；
      H_map  : 声明对但地图陈旧；越晚的视点越可能“新鲜”，
               P(支持 | t)=0.10+0.80·f_t（f_t 已知）-> 从反驳到支持的**趋势**。
    H_lang 无变化、H_perc 平稳、H_map 有趋势，K 增大时三者可分。
    """
    def freshness(t, k):
        return t / max(k - 1, 1)

    def support_prob(h, t, k):
        if h == 'H_lang':
            return 0.10
        if h == 'H_perc':
            return 0.70
        return 0.10 + 0.80 * freshness(t, k)   # H_map

    hyps = ('H_lang', 'H_perc', 'H_map')
    rows = []
    for k in ks:
        correct = {h: 0 for h in hyps}
        n = {h: 0 for h in hyps}
        for _ in range(n_ep // len(ks)):
            true_h = hyps[rng.integers(0, 3)]
            obs = np.array([int(rng.random() < support_prob(true_h, t, k))
                            for t in range(k)])
            scores = {}
            for h in hyps:
                p = np.array([support_prob(h, t, k) for t in range(k)])
                scores[h] = float(np.sum(obs * np.log(p + 1e-12)
                                         + (1 - obs) * np.log(1 - p + 1e-12)))
            pred = max(scores, key=scores.get)
            n[true_h] += 1
            correct[true_h] += int(pred == true_h)
        rows.append(dict(k=k,
                         acc_lang=correct['H_lang'] / n['H_lang'],
                         acc_perc=correct['H_perc'] / n['H_perc'],
                         acc_map=correct['H_map'] / n['H_map'],
                         acc_overall=sum(correct.values()) / sum(n.values())))
    return rows


# ---------------------------------------------------------------- B
def sim_vantage(n_task=4000, n_vantage=12, budget=4):
    """随机任务：若干声明各有重要度/需访问视点；比较选择策略。"""
    def one(strategy):
        # 关键声明数 1-3，每个由随机视点集合可分辨
        n_claim = int(rng.integers(1, 4))
        claims = []
        for _ in range(n_claim):
            vset = rng.choice(n_vantage, size=int(rng.integers(1, 4)), replace=False)
            weight = float(rng.uniform(0.5, 1.0))
            claims.append((set(vset.tolist()), weight))
        # 视点属性
        cost = rng.uniform(0.5, 3.0, size=n_vantage)
        risk = rng.uniform(0.0, 0.5, size=n_vantage)   # 碰撞/失去撤退风险
        resolved = set()
        chosen = []
        spent = 0.0
        risk_spent = 0.0
        for _ in range(budget):
            best, best_score = None, -np.inf
            for i in range(n_vantage):
                if i in chosen:
                    continue
                info = sum(w for vs, w in claims
                           if i in vs and not (vs & resolved))
                if strategy == 'nearest':
                    score = -cost[i]
                elif strategy == 'info':
                    score = info
                else:  # sextant: info / (cost + lambda*risk)
                    score = info / (cost[i] + 2.0 * risk[i] + 1e-6)
                # 预算/风险硬约束（只有 sextant 显式执行）
                if strategy == 'sextant' and (risk_spent + risk[i] > 1.0):
                    continue
                if score > best_score:
                    best, best_score = i, score
            if best is None:
                break
            chosen.append(best)
            spent += cost[best]
            risk_spent += risk[best]
            for j, (vs, w) in enumerate(claims):
                if best in vs:
                    resolved.add(j)
        value = sum(w for j, (vs, w) in enumerate(claims) if j in resolved)
        critical = all(j in resolved for j in range(n_claim))
        return value, spent, risk_spent, critical

    out = {}
    for strat in ('nearest', 'info', 'sextant'):
        vals, costs, risks, crit = [], [], [], []
        for _ in range(n_task):
            v, c, r, ok = one(strat)
            vals.append(v); costs.append(c); risks.append(r); crit.append(ok)
        out[strat] = dict(
            resolved_value=float(np.mean(vals)),
            spent=float(np.mean(costs)),
            value_per_cost=float(np.mean(vals) / max(np.mean(costs), 1e-9)),
            risk=float(np.mean(risks)),
            critical_resolved=float(np.mean(crit)),
        )
    return out


# ---------------------------------------------------------------- C
def sim_retreat(n_ep=20000):
    """进入走廊前是否有撤退证书；动态阻挡以 p_block 到来。"""
    p_arrive = 0.25            # 撤退路径被动态障碍失效的概率
    static_unsafe = 0.20       # 无证书时进入实际为死角的概率
    out = {}
    for name, cert in (('no_cert', False), ('cert', True)):
        dead = 0
        blocked_safe = 0
        for _ in range(n_ep):
            unsafe = rng.random() < static_unsafe
            if cert:
                # 证书用几何地图验证撤退；静态死角被拦下
                if unsafe:
                    blocked_safe += 1
                    continue
                # 但动态阻挡可让已证明的撤退失效（证书依赖地图）
                if rng.random() < p_arrive:
                    dead += 1
            else:
                if unsafe or rng.random() < p_arrive:
                    dead += 1
        out[name] = dict(dead_end_rate=dead / n_ep,
                         safe_reject_rate=blocked_safe / n_ep)
    return out


# ---------------------------------------------------------------- D
def sim_taint(n_ep=5000):
    """环境文本注入：无污点系统 vs 有 provenance 类型系统。"""
    p_inject_present = 0.30
    p_hijack_if_reached = 0.55
    no_fw = 0
    fw = 0
    for _ in range(n_ep):
        if rng.random() < p_inject_present:
            if rng.random() < p_hijack_if_reached:
                no_fw += 1
            # firewall: 场景文本只能成为 claim，不能成为 command -> 0
            fw += 0
    return dict(no_firewall_hijack=no_fw / n_ep,
                firewall_hijack=fw / n_ep,
                injected_present=p_inject_present)


# ---------------------------------------------------------------- E
def sim_sycophancy(n_ep=20000):
    """声明被证据证伪后，让同一 LLM 自评 vs 独立验证器判定。"""
    p_claim_true = 0.5
    p_refute_if_false = 0.9
    p_rationalize = 0.55       # 自评时把证伪重新解释为真
    verifier_acc = 0.90
    self_err = 0
    ver_err = 0
    for _ in range(n_ep):
        true = rng.random() < p_claim_true
        if true:
            ev = 1 if rng.random() < p_refute_if_false else 0
            self_err += 0
            ver_err += int((rng.random() > verifier_acc))
        else:
            ev = 0
            # 自评：以 p_rationalize 坚持原声明为真
            self_err += int(rng.random() < p_rationalize)
            ver_err += int(rng.random() > verifier_acc)
    return dict(self_eval_error=self_err / n_ep,
                independent_verifier_error=ver_err / n_ep,
                rationalize_rate=p_rationalize)


if __name__ == '__main__':
    out = {
        'A_attribution': sim_attribution(),
        'B_vantage': sim_vantage(),
        'C_retreat': sim_retreat(),
        'D_taint': sim_taint(),
        'E_sycophancy': sim_sycophancy(),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    with open('/tmp/sextant_results.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
