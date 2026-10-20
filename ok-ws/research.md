# 玄 · t

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 想法区 · 第 1 轮

## 0. 本轮对任务 "t" 的解读

任务只给了 "t"。我把它理解为 **trajectory / test-time**：不研究某个具体领域问题的答案，而研究「研究循环这条轨迹本身」怎样在不确定性下前进。选择这个解读的理由是：当前工作区就是 xuen 的研究循环，守卫机制已有雏形，适合做可验证、可复现的元研究。

## 1. 直觉（先不给定义）

当前轮次守卫的本质是「单次评审 + 阈值晋升」：候选先写出来，评审再看，分数过线就晋升。直觉上有两个漏洞：

1. **事后合理化**：评审在看到候选之后才打分，容易奖励长文、术语密度和自信语气，而不是奖励「更接近事实」。
2. **没有可证伪承诺**：候选只被问「好不好」，没被要求对任何未观测事实下注。于是文本可以高度自洽、却不可检验；循环可能在「更漂亮的空话」上单调改进。

一个自然的类比是**预测市场**：如果研究者必须先以概率形式承诺「哪个实验会得到什么结果」，再揭盲，那么「说得好」和「预测得准」就被分开了。把每一轮看成轨迹上的一步 t，候选不只是 (想法, 产物)，还应附带一张**预测卡**；先承诺、后揭盲，用适当评分规则和序贯推断决定是否晋升。

## 2. 研究问题

- R1：在无自动测试、只能靠文本评审的任务里，commit-reveal 预测卡能否降低「差候选被晋升」的概率？
- R2：与单次 AI 评分相比，序贯 e-value 能否在相同预算下更早识别真实改进？
- R3：该机制会不会把研究引向「容易验证的小问题」，从而牺牲新颖性？

## 3. 假设

- H1：在合成已知真值的任务上，FGRL 的误晋升率（FPR）≤ α，而当前阈值评审的 FPR 显著更高。
- H2：对真实改进的检测延迟（轮数 / probe 数）低于固定阈值 Brier 基线。
- H3：加入新颖性准入后，预测卡的「可验证性偏好」不会显著降低盲评新颖度。

## 4. 方法概要：FGRL（Forecast-Guarded Research Loop）

每轮候选附带预测卡 P = {(claim_j, p_j, probe_j)}；守卫先把 P 的规范化哈希写入只增日志（commit），**承诺落盘之后**才执行 probe 或等待用户揭盲（reveal）；用候选与当前最佳的配对 Brier 差构造 e-value，Ville 不等式控制「任意时刻」误晋升；晋升还需通过结构完整、测试（若有）、新颖性与成本四道闸。失败候选只留快照，不污染下一轮起点。

## 5. 与已有思想的关系

- **适当评分规则**（Brier / log score）：诚实报告信念是最优策略，抑制「嘴硬」。
- **anytime-valid inference / e-values**：允许跨轮连续监控，不必预先固定样本量。
- **机制设计中的 commit-reveal**：抑制事后诸葛和选择性报告。
- **可证伪性**：把「研究品味」的一部分外包给可复现的 probe，而不是完全交给评审员。

## 6. 待解决问题

- probe 由谁执行？agent 自报不可信，守卫必须自己跑命令或只接受用户揭盲。
- 预测卡会退化成「明天太阳升起」式 trivial claims，需要信息量 / 难度闸门。
- 多 claim 相关、非独立采样时 e-value 仍有效，但功效会下降。
- 新颖性与可验证性存在真实张力，需要显式多目标而不是假装统一成一个分数。

## 7. 下一轮计划

先做最小可行实验：合成「真实改进 / 零差异 / 退化 / 空洞长文」四类候选，比较当前 AI 阈值评审与 FGRL 的 FPR、功效和检测延迟；同时把新颖性度量落到可操作定义（嵌入距离 vs 相对最佳的信息增益）。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 产物区 · 第 1 轮：FGRL 协议 v0.1

> FGRL = Forecast-Guarded Research Loop。目标：把「候选是否更好」从单次主观评分，改成「先承诺、后揭盲、按未见事实的预测准确度做序贯推断」。

## 1. 形式定义

- 研究状态：S_r = (I_r, A_r)，分别为想法区与产物区。
- 候选：c = (I_c, A_c, P, h)，其中 P 是预测卡，h 是承诺哈希。
- 预测卡：P = {(x_j, p_j, π_j)}_{j=1..m}。
  - x_j：一条可判真假的 claim；
  - p_j ∈ [0,1]：候选对「x_j 为真」的概率；
  - π_j：probe，可由守卫执行的命令 / 可查询数据 / 用户按协议揭盲。
- 揭盲结果：y_j ∈ {0,1}。
- Brier 分：b(p, y) = (p − y)²。
- 与当前最佳 b 的配对差：
  d_j = (p^b_j − y_j)² − (p^c_j − y_j)² ∈ [−1, 1]。
- 效应量：Δ = E[d_j]。Δ > 0 表示候选在未见事实上更准；Δ ≤ 0 表示没有证据更好。

注意：d_j 是**配对**的，同一个 probe 同时问最佳卡与候选卡，能消掉题目难度带来的方差。这是后续功效的关键。

## 2. 承诺—揭盲协议（commit-reveal）

1. 候选写完后，守卫解析 P，做 canonical JSON（键排序、浮点定精度、UTF-8）。
2. 计算 h = SHA-256(canonical(P) || best.id || round || nonce)。
3. 在 `rounds/evidence.jsonl` 追加 commit 记录；**fsync 成功之后**才允许执行 probe。
4. 守卫亲自执行 π_j（子进程、超时、工作目录隔离），或等待用户按预注册协议揭盲；**禁止**采信 agent 自报的 y_j。
5. 追加 reveal 记录，再计算 d_j 与 e-value。

不变量：任何 reveal 记录之前，必须存在对应的 commit 记录且哈希可验证；否则该轮判为 pending，不参与晋升。

## 3. 序贯晋升检验

原假设 H0: Δ ≤ 0；备择 H1: Δ > 0。允许跨轮连续监控，因此不能用固定样本的 t 检验，而要用 anytime-valid 的 e-value。

### 3.1 保守版：Hoeffding 混合 e-value

对固定 λ ∈ [0,1]，令 S_n = Σ_{j=1}^n d_j。由于 d_j ∈ [−1,1]，

  M_n(λ) = exp(λ S_n − n λ² / 2)

在 H0 下是非负上鞅（Hoeffding 引理，mgf ≤ exp(λ²/2)）。取先验 π 在 λ 上，混合

  E_n = ∫_0^1 M_n(λ) π(dλ)

仍是上鞅。由 Ville 不等式，在 H0 下

  P(∃n: E_n ≥ 1/α) ≤ α。

晋升规则：当 E_n ≥ 1/α（等价 log E_n ≥ log(1/α)）时晋升。实现时用离散网格 λ ∈ {0.05, 0.10, …, 1.00} 均匀加权，log-sum-exp 稳定计算。

**不要**用观测到的 S_n/n 直接代入 λ：那会破坏上鞅性，失去任意时刻保证。若要用自适应的 λ，见 3.2。

### 3.2 功效版：可预测下注的 e-value

令 K_0 = 1，λ_t ∈ [0,1] 只依赖 t 之前的观测（predictable），

  K_n = ∏_{t=1}^n (1 + λ_t d_t)。

因为 d_t ∈ [−1,1]，每个因子非负；在 H0 下 E[d_t | F_{t−1}] ≤ 0，所以

  E[K_n | F_{n−1}] = K_{n−1} (1 + λ_t E[d_t | F_{n−1}]) ≤ K_{n−1}，

K_n 是非负上鞅，Ville 不等式同样给出 P(∃n: K_n ≥ 1/α) ≤ α。

取 λ_t = clip(μ̂_{t−1} / (2 σ̂²_{t−1} + ε), 0, 1)，其中 μ̂、σ̂² 只用前 t−1 个 d 估计。若真实效应为 Δ、方差为 σ²，对数资本增长率约为 Δ²/(2σ²)，达到 log(1/α) 所需样本量约为

  n ≈ 2 σ² log(1/α) / Δ² = 6 σ² / Δ²   （α = 0.05）。

### 3.3 功效对照（说明为什么不能承诺「小效应快速检测」）

| 方法 | 所需 claim 数 n | Δ=0.1, σ=0.2 | Δ=0.2, σ=0.2 | Δ=0.3, σ=0.3 |
|---|---|---|---|---|
| Hoeffding 混合（最坏情形） | ≈ 6/Δ² | 600 | 150 | 67 |
| 下注 e-value（σ 已知） | ≈ 6σ²/Δ² | 24 | 6 | 6 |

结论：Hoeffding 版安全但保守；下注版在方差可控时强得多，但依赖对 σ 的在线估计。实验必须同时报告两者，不能只报有利的那个。

## 4. 准入闸门（不进入 e-value，避免污染统计保证）

1. **结构闸**：IDEA / ARTIFACT 标记完整；否则拒绝并还原最佳。
2. **测试闸**：若 `rounds.repo` 有可运行测试套件，全绿才继续；测试失败直接拒绝。
3. **卡片质量闸**：
   - m ≥ 3；
   - 至少 2 条 claim 的 p ∈ [0.2, 0.8]（防止全押 0/1 的 trivial claims）；
   - probe 必须在 1 轮内可观测、成本 ≤ 预算；
   - 至少 1 条 claim 的 probe 不与最佳卡已揭盲的 probe 重复。
4. **新颖性闸**：N(c) = 1 − cos(e(A_c), e(A_best))，e 为固定嵌入模型；低成本 fallback 用字符 n-gram Jaccard。要求 N ≥ ν_min，或在 Δ 很大时由人工复核豁免。
5. **预算闸**：本轮 probe 总成本 ≤ `rounds.probe_budget`。

新颖性与统计检验**分开报告**：新颖性决定「允不允许参赛」，e-value 决定「赢没赢」，不把两者塞进同一个分数。

## 5. 晋升伪代码

```python
def finish_round(cand, best, state):
    if not structure_intact(cand):
        return reject_and_restore("structure")

    card = parse_prediction_card(cand)
    if not card_ok(card):
        return pending("invalid_card")

    h = sha256(canonical(card) + best.id + state.round + nonce())
    evidence.append({"type": "commit", "round": state.round,
                     "cand_id": cand.id, "card_hash": h,
                     "claims": card.claims, "prev_best": best.id})
    fsync(evidence.path)                      # 先落盘，再揭盲

    outcomes = execute_probes(card, timeout=..., sandbox=...)
    if outcomes is None:
        return pending("probe_unavailable")
    evidence.append({"type": "reveal", "cand_id": cand.id,
                     "outcomes": outcomes, "source": "guard"})

    for y in outcomes:
        d = brier(best.card.p, y) - brier(cand.card.p, y)
        lam = clip(mu_hat / (2 * var_hat + EPS), 0.0, 1.0)
        logK += log1p(lam * d)
        update_running_stats(d)

    if tests_available and not tests_pass():
        return reject_and_restore("tests")
    if novelty(cand, best) < NU_MIN:
        return reject_and_restore("novelty")

    evidence.append({"type": "verdict", "cand_id": cand.id,
                     "logK": logK, "threshold": log(1 / ALPHA),
                     "decision": "promote" if logK >= log(1 / ALPHA) else "reject"})

    if logK >= log(1 / ALPHA):
        adopt(cand, card_hash=h, logK=logK)   # 更新 best.md / best.json
        return promoted()
    return reject_and_restore("not_enough_evidence")
```

## 6. 数据模式（append-only）

`rounds/evidence.jsonl`：

```json
{"type":"commit","round":7,"cand_id":"20261020-101500-r7","card_hash":"sha256:...","prev_best":"...","claims":[{"id":"c1","p":0.7,"probe":"pytest -q tests/test_x.py::test_y","horizon":"round"}],"ts":"..."}
{"type":"reveal","cand_id":"20261020-101500-r7","outcomes":{"c1":1},"source":"guard","ts":"..."}
{"type":"verdict","cand_id":"20261020-101500-r7","logK":3.41,"threshold":2.996,"decision":"promote","ts":"..."}
```

`rounds/best.json` 增加字段：`card`（已揭盲的预测卡）、`card_hash`、`logK_at_adoption`、`n_claims`。旧字段保持兼容；缺失 card 的旧最佳按「无预测卡」处理，只参与文本比较，不参与 d 的计算。

## 7. 实验设计（下一轮可执行）

### 7.1 数据

- **合成任务 20 个**：每个任务预置 8 条 claim 与真值，覆盖事实、数值区间、方法效果三类。
- **半真实任务 10 个**：取自 xuen 的历史 round 产物，人工标注 claim 真值。
- 候选生成四类：
  - T（真实改进）：ΔBrier ≈ +0.15；
  - N（零差异）：Δ ≈ 0；
  - D（退化）：Δ ≈ −0.15；
  - V（空洞长文）：长度 +80%，claim 多为 trivial，p 集中在 0/1。

### 7.2 基线

- B0：当前 AI 评分 + 阈值 8 晋升。
- B1：揭盲后固定阈值 Brier 比较。
- B2：FGRL-Hoeffding。
- B3：FGRL-下注（主推）。

### 7.3 指标

- 误晋升率 FPR（D、N 被判晋升）；
- 功效 power（T 被判晋升）；
- 检测延迟（claim 数 / 轮数）；
- 校准 ECE（p 与 y 的一致性）；
- 新颖度（嵌入距离）与盲评质量；
- 每轮 token / 时间成本；
- 评审与人工判断的一致性（仅 B0）。

### 7.4 预注册成功标准

- B3 在 20 个合成任务上的 FPR ≤ 0.05；
- 相对 B0，FPR 至少下降 50%，且 power 下降不超过 20%；
- 检测 Δ=0.2 的中位 claim 数 ≤ 10（σ≈0.2）。

未达到则先改 probe 设计或方差控制，不直接改生产循环。

### 7.5 消融

- 去掉 commit-reveal（先看结果再写 p）；
- Brier vs log score；
- 固定 λ vs 可预测下注；
- 新颖性闸开 / 关；
- 单一 claim vs 多 claim 相关族。

## 8. 与 xuen 的集成方案

- 新增 `xuen/forecast.py`：`PredictionCard`、`canonical_hash`、`hedged_logK`、`mixture_evalue`、`parse_card`。
- `xuen/rounds.py`：保留现有快照 / 最佳 / 还原框架，新增 `mode=forecast` 分支；任何解析或执行异常回退 legacy 评分，遵守「守卫失败一律降级」。
- 配置新增：
  - `rounds.mode: legacy|forecast`
  - `rounds.alpha: 0.05`
  - `rounds.min_claims: 3`
  - `rounds.novelty_min: 0.15`
  - `rounds.probe_budget: 60`
- 测试：
  - 单元：零效应模拟 10^4 次，验证 FPR ≤ α + 蒙特卡洛误差；
  - 顺序：reveal 早于 commit 必须被拒绝；
  - 安全：probe 超时 / 非零退出 / 沙箱逃逸尝试；
  - 回归：结构损坏时仍还原最佳；旧 best.json 无 card 时兼容。

## 9. 失败模式与对策

| 失败模式 | 后果 | 对策 |
|---|---|---|
| trivial claims | 高分但无信息 | p 区间约束 + 难度闸 + 随机审计 |
| agent 自报结果 | 直接造假 | 守卫执行 probe；禁止自报 |
| probe 可被候选选择 | 挑简单题 | 最佳/候选同题配对；probe 由守卫抽样 |
| 小效应 + 高方差 | 功效极低 | 下注 e-value；增加 claim 数；方差缩减 |
| claim 相关 | 有效样本虚高 | 按族聚类，保守取族内均值 |
| 非平稳世界 | p 失效 | horizon 限制在一轮内；过期 claim 作废 |
| 新颖度与可验证性冲突 | 研究变保守 | 新颖性单独报告；定期人工复核 |
| 多候选多重比较 | FPR 膨胀 | 每轮 α/k 或分层 α 分配 |

## 10. 本轮结论与下一轮动作

FGRL 的核心不是「再加一个评分器」，而是把晋升条件改成**可审计的预测承诺 + 任意时刻有效的错误控制**。理论上 FPR 可由 Ville 不等式控制；工程上必须先验证 commit 时序、probe 执行可信度和下注 e-value 的实际功效。下一轮优先做第 7 节的离线模拟，不直接改生产循环。
<!-- ARTIFACT:END -->
