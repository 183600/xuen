# 玄 · 灵感驱动研究循环

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 68 轮（承接第 67 轮「SimRAS 仿真增强闭环」IP-233~242；灵感循环第 1 轮；本轮灵感：「共情表达」×「行为克隆」）

> 第 65~67 轮把系统从「故障可归因」推到「情绪驱动闭环」再到「仿真预演 + 视觉问答审计」，能力一路加码，却始终默认了一件事：**策略先验是给定的，人类只是被感知、被归因、被审计的外部信号源**。翻遍前三轮，没有任何一个环节回答「机器人如何从人的示范里学到能力与关切」。
>
> 这正是行为克隆（BC）的位置，也是 BC 最深的裂缝：它学的是 `s→a`，丢掉的是「**为什么这样做、做的时候有多担心**」。而「共情表达」恰恰是示范者在做动作时免费泄漏出来的那一路信息：犹豫、紧张、注视、语调。
>
> 本轮提出 **EBC（Empathic Behavior Cloning，共情行为克隆）**：
>
> **把示范拆成「动作」与「关切」两条潜通道，用共情表达作为示范者关切潜变量的证据，而非标签；再以「共情只踩刹车、不踩油门」的单调守卫，把表达的可欺骗性隔离在安全边界之外。** EBC 不要求机器人表演情绪，只要求它学会「**示范者在担心什么，以及担心时会把动作收多少**」。

## 0. 直觉与动机

**灵感 1（行为克隆的冰山）**
直觉：BC 的目标是 `max_θ E_{(s,a)~D}[log π_θ(a|s)]`。但示范动作是潜变量 `c`（关切/紧迫）与状态 `s` 共同生成的：`a ~ π_H(a|s,c)`。对 `c` 边缘化后得到 `π_BC(a|s)=∫π_H(a|s,c)p(c|s)dc`。这在两种情形下直接致命：
- **模式平均**：同一 `s` 下，谨慎者给 `a_safe`、赶时间者给 `a_fast`，BC 学出 `0.5(a_safe+a_fast)`——一个谁也不曾示范、且常常正好越过安全边界的中庸动作；
- **协变量偏移**：误差复利把策略推到示范分布外，而 BC 没有任何信号判断「人到这里会不会介入」。

BC 真正缺的不是数据量，而是**把「关切」从「动作」里解耦出来的那个潜变量**。

**灵感 2（共情表达是免费但不可信的偏好标注）**
直觉：示范者说「这里要小心」往往不用嘴，而是皱眉、放慢、屏息、盯住目标。这些表达由 `c` 生成，因而携带关于 `c` 的信息。但它与标签有本质区别：
- **免费**：示范时人本来就在表达，无需额外标注；
- **不可信**：文化显示规则、职业性镇定、假笑、疲劳、刻意表演都会让表达偏离真实关切；
- **单向可掩蔽**：人很难在真正紧张时完全装出放松，却很容易在放松时装出紧张（或反之）。这提示我们只能把表达当作**有方向的证据**，不能当作对称的监督。

因此 EBC 把表达建模为似然 `p(e|s,a,c)`，而不是把 `e` 直接回归成 `c`。

**灵感 3（关键翻转：共情只踩刹车，不踩油门）**
直觉：第 66 轮 RAS 允许「表情安全」去**放宽**容差，这是整条脉络里最危险的一步——一旦表情被遮挡或表演，真实的几何故障会被误判为安全。EBC 把方向反过来：
> **表达只能增加谨慎，永远不能把谨慎降到行为基线以下。**

形式上，设行为基线给出 `c_base`，表达给出上置信界 `c_UC`（越大越谨慎），单调守卫取 `c_use = max(c_UC, c_base)`。于是对**任意**观测到的 `e`（包括对抗性伪造），`c_use ≥ c_base`，安全裕度单调不减。这是一个**分布无关**的保证：它不依赖「表情忠实」这一假设。表情是否可信只决定系统保守多少，不决定是否安全。

**灵感 4（care 与 urgency：恐惧的两种读法）**
直觉：皱眉后退可以读作「别靠近」（care），也可以读作「来不及了」（urgency）。二者对控制方向的要求相反：前者要收紧，后者要在安全前提下落块。若把二者混为一个「负面情绪」标量，EBC 会把紧急示范误判为鲁莽并降权，反而学到迟缓策略。因此潜变量必须是二维的：
- `c_care ∈ [0,1]`：风险厌恶 / 谨慎程度；
- `c_urg ∈ [0,1]`：时间压力 / 任务紧迫度。
表达提供高唤醒信号，动作运动学（速度、提前量、犹豫时长）提供方向性约束，二者共同辨识。

**灵感 5（与前三轮合流：EBC-RAS）**
EBC 不是一个孤立的模仿学习器，而是给 VISTA/RAS/SimRAS 补上「从人学」的前端：
1. **ELE（Empathic Latent Encoder）**：从 `(s,a,e)` 推断 `(c_care,c_urg)`，用 β-TC 解耦；
2. **CCP（Care-Conditioned Policy）**：`π_θ(a|s,c_use)`，在到边界时自动收动作；
3. **MEG（Monotone Empathy Guard）**：`c_use=max(c_UC,c_base)`，把可欺骗性挡在安全边界外；
4. **ECQ（Empathic Curation & Query）**：按示范者可靠性与表达一致性重加权；
5. **CST（Care-Surprise Trigger）**：当关切后验意外升高时触发 DAgger 查询或回退到保守前缀；
6. **EWM-E（Empathic World Model head）**：在 SimRAS 的世界模型上加一路「人类表达响应」预测，供 VQAuditor 做「示范者看到这条轨迹会不会担心」的反事实审计；
7. **J_EBC**：把 care 后验、示范覆盖率、校准误差、隐私预算写进证书。

**从直觉到严谨问题**：表达到底在什么条件下对 `c` 有信息增益？它什么时候会误导？单调守卫能否在不假设忠实性的前提下保住最坏情况安全？反事实共情是否可辨识？下面逐一形式化。

## 1. 形式化定义（增量：定义 276–296）

- **定义 276（EBC 总览）**：`EBC = (EmD, ELE, CCP, MEG, ECQ, CST, EWM-E, ECA, J_EBC)`。定位：为 VISTA/RAS/SimRAS 补上「从人类示范学习策略与关切」的前端。不变式：表达只进入潜变量后验与保守化方向，实时流只做前向推断，零在线学习写操作。
- **定义 277（共情示范元组）**：`D_E = {(s_t^i, a_t^i, e_t^i, h_t^i)}`，`h_t` 为可选的示范者自报信心/风险（稀疏、可缺失）。`s` 为多模态观测，`a` 为连续/离散动作块，`e` 为共情表达观测。
- **定义 278（共情表达观测）**：`e_t = (e_face, e_voice, e_kin)`：面部动作单元与关键点、语调韵律、以及示范者的动作学特征（犹豫时长、减速、回撤、注视切换）。`e ∈ E`，允许整段缺失（遮挡、静音、不可见）。
- **定义 279（关切-紧迫潜变量）**：`c_t = (c_care, c_urg) ∈ [0,1]^2`。`c_care` 越大越风险厌恶；`c_urg` 越大时间压力越大。二者慢变：`c_{t+1}=c_t+η_t`，`||η_t||≤η_max`。
- **定义 280（示范者生成模型）**：结构因果模型
  ```
  s_{t+1} = f(s_t,a_t)
  c_t     ~ p(c|s_t)
  a_t     ~ π_H(a|s_t,c_t)
  e_t     ~ p_H(e|s_t,a_t,c_t)
  ```
  关键：`e` 与 `a` 都依赖 `c`，但 `e` 不是 `a` 的确定性函数——这正是额外信息的来源。
- **定义 281（忠实性/可辨识条件 A92–A94）**：
  - A92（无直接混杂）：给定 `(s,a)`，`c` 与 `e` 之间无未观测共同原因；
  - A93（单调似然比）：在关切类表达特征上，`p(e|c_care)` 关于 `c_care` 满足单调似然比序（MLR）；
  - A94（掩蔽不对称）：存在表达 `e*` 使 `p(e*|c_care^high) ≫ p(e*|c_care^low)`，但反向不成立。即「紧张很难完全伪装成放松」。
- **定义 282（关切后验编码器）**：变分后验 `q_φ(c|s,a,e)`，训练目标
  ```
  L_ELE = E_q[log p(a|s,c)] + λ_e E_q[log p(e|s,a,c)]
          - β·TC(q(c|s,a,e)) + λ_h E_q[log p(h|s,c)]
  ```
  其中 TC 为 total correlation，用于解耦 `c_care` 与 `c_urg`。
- **定义 283（关切上置信界）**：`c_UC = Q_{1-δ}(q_φ(c_care|s,a,e))`，用分位数网络或 conformal 校准给出覆盖率为 `1-δ` 的上界。方向约定：越大越谨慎。
- **定义 284（单调共情守卫 MEG）**：行为基线 `c_base = Q_{1-δ}(q_φ(c_care|s,a))`（仅用动作证据）。守卫输出
  ```
  c_use = max(c_UC, c_base)
  u     = c_use
  λ_EBC = clip(1 - α_E·u, 0.5, 1.0)
  ```
  不变式：`λ_total = λ_RAS · λ_EBC ≤ λ_RAS`。表达缺失时 `c_UC ← Q_{1-δ}^{prior}(c_care|s)`，只允许更保守。
- **定义 285（关切条件策略）**：`π_θ(a|s,c_use)`，以加权 BC 训练：`max_θ Σ_i w_i log π_θ(a_i|s_i,c_use,i)`。
- **定义 286（care-单调策略类）**：安全裕度 `M(s,a,c)` 对 `c_care` 单调不减：`c_1 ≥ c_2 ⇒ M(s,a,c_1) ≥ M(s,a,c_2)`。策略在满足任务约束下最大化 `M`。此单调性是把「共情」转成「保守」的结构性前提。
- **定义 287（共情数据整形 ECQ）**：示范者可靠性 `r_i ∈ [0,1]`，样本权重
  ```
  w_i = r_i · exp(-β_c·KL(q(c|s,a,e) || q(c|s,a)))
  ```
  可靠性由「自报—动作—表达」三方可复现性、跨示范者一致性、以及 `c_urg` 校正后的矛盾度估计。
- **定义 288（反事实表达模型）**：`g_ψ(e|s,a,c)`，训练自 `D_E` 与 Sim2Empathy 合成数据。反事实偏好
  ```
  Δ(a→a') = E_{c~q}[ D_KL( g(e|s,a',c) || g(e|s,a,c) ) ]
  ```
  仅在 top-k 候选内作为排序/过滤信号，**永不单独充当安全证明**。
- **定义 289（关切意外度与触发）**：`U_t = H(q(c|s_t,a_t,e_t))` 与 `KL(q(c|·,e_t) || q_pred(c|·))` 的加权和；`U_t > τ_cst ⇒` 触发 CST。触发动作：DAgger 查询（若人可介入）或回退到保守前缀（若不可介入）。
- **定义 290（共情查询规则）**：触发后以 `(s_t, a_t^CCP)` 请求示范者标注/接管，并将新样本并入 `D_E`。查询预算 `B_q` 与触发召回率共同决定协变量偏移的收敛速度。
- **定义 291（共情滚动）**：SimEngine 按 `c` 动力学与 `g_ψ` 生成 `{(s,a,c,e)_{t+i}}`；`e_{t+i}` 供 VQAuditor 做「示范者反应」审计，供 EWM-E 预训练。
- **定义 292（EBC-RAS 耦合）**：认证前缀
  ```
  k_EBC = max{k : ∀i≤k, M(s_{t+i}, a_{t+i}, c_use) · λ_total ≥ 0}
  k*    = min(k_VISTA, k_emo, k_wm, k_EBC, m_ras)
  ```
  且 `λ_total ≤ λ_RAS`、`k_EBC ≤ k_base`（表达缺失时）。
- **定义 293（J_EBC 证书）**：`J_EBC = (J_SimRAS, care_posterior, care_UCB, demo_coverage, care_calibration_ECE, privacy_budget, clone_safety_margin, empathic_consistency)`。`Valid ⇔ Valid(J_SimRAS) ∧ ECE ≤ 0.05 ∧ demo_coverage ≥ 0.9 ∧ privacy_ok`。
- **定义 294（AIC-EBC 干扰集）**：`ℰ_EBC = ℰ_SimRAS × ℰ_empathy × ℰ_clone`，其中 `ℰ_empathy = {掩蔽, 表演, 文化显示规则, 疲劳, 对抗伪造}`，`ℰ_clone = {分布偏移, 模式平均, 虚假相关, 示范者错误}`。
- **定义 295（示范者可靠性）**：`r_i = σ(α_1·consistency_i + α_2·calibration_i - α_3·contradiction_i)`，`contradiction_i` 在 `c_urg` 高时自动降权（紧急时的反常动作不一定是错误）。
- **定义 296（在线不变式与隐私）**：表达数据只在设备端编码，`e` 不出端；对外只发布 `(c_use, λ_EBC, k_EBC)` 与证书哈希。若隐私预算耗尽或表达缺失，则退回 `c^prior_UC`，行为可用性下降但安全裕度不降。

## 2. 关键算法骨架

```python
class EmpathicLatentEncoder:
    def __init__(self, beta_tc=4.0, delta=0.05):
        self.beta_tc, self.delta = beta_tc, delta

    def encode(self, s, a, e=None):
        if e is None:
            q = self.prior(s, a)            # 仅行为证据
            return q, self.ucb(q, self.delta)
        q_care, q_urg = self.split(self.net(s, a, e))
        return (q_care, q_urg), self.ucb(q_care, self.delta)

    def ucb(self, q, delta):
        return self.quantile(q, 1 - delta)  # 越大越谨慎


class MonotoneEmpathyGuard:
    def __init__(self, alpha_e=0.5):
        self.alpha_e = alpha_e

    def guard(self, c_uc, c_base):
        c_use = max(c_uc, c_base)           # 只升不降
        lam = max(0.5, min(1.0, 1 - self.alpha_e * c_use))
        return c_use, lam                   # lam <= 1.0，永远只收紧


def EBC_round(M, s, e, a_last, base_prefix):
    # 1) 关切后验 + 单调守卫
    (q_care, q_urg), c_uc = M.ele.encode(s, a_last, e)
    c_base = M.ele.ucb(M.ele.prior(s, a_last), M.delta)
    c_use, lam_ebc = M.meg.guard(c_uc, c_base)

    # 2) 关切条件策略（仅在保守前缀内选块）
    A = M.ccp.propose(s, c_use)
    k = M.certify_prefix(A, c_use, min(base_prefix, len(A)))

    # 3) 关切意外 -> 查询或回退
    U = M.cst.surprise(q_care, q_urg, a_last)
    if U > M.tau_cst:
        if M.human_available:
            M.query_human(s, A[:k]); M.ele.update_offline()
        else:
            k = min(k, M.fallback_prefix(s, c_use))

    # 4) 与 RAS 链路耦合（只收紧）
    lam = M.ras.lambda_risk * lam_ebc
    return A[:k], c_use, lam, U
```

## 3. 推导（本轮新增：引理 13–15，定理 14–17）

**引理 13（共情信息恒等式）**
```
I(c; a,e | s) = I(c; a | s) + I(c; e | s,a)
```
第二项 `I(c;e|s,a) ≥ 0`，当且仅当 `e ⟂ c | (s,a)` 时取 0。故表达在 A92 下**只可能增加**关于 `c` 的信息。这条引理给出 EBC 的"免费午餐"边界：若表达与关切无关，EBC 退化为普通 BC，不会更差（见引理 14）。

**引理 14（单调守卫的最坏情况安全）**
设安全裕度 `M(s,a,c)` 对 `c_care` 单调不减（定义 286），则对任意观测 `e`（含对抗伪造），`c_use=max(c_UC,c_base) ≥ c_base`，于是
```
M(s, a, c_use) ≥ M(s, a, c_base)
```
即**表达的任何欺骗都无法把认证裕度降到纯行为基线以下**。该结论不依赖 A93/A94，也不依赖 `e` 的分布，是分布无关的。这是 EBC 与 RAS 最根本的区别：RAS 让表情能放宽 `λ`，EBC 让表情只能收紧。

**引理 15（去模式平均）**
设 `c ∈ {c_low,c_high}`，`c_low<c_high`，对应示范动作 `a_low,a_high`。BC 边缘策略产生 `ā = ½(a_low+a_high)`。若 `M(s,·,c)` 在动作上凹且对 `c` 单调，则 `M(s,ā,c_high) ≤ ½[M(s,a_low,c_high)+M(s,a_high,c_high)]`；当 `a_low` 是唯一满足 `M≥0` 的动作时，条件化 `c_use≥c_high-δ` 可把 `ā` 替换回安全侧，避免模式平均越界。

**定理 14（共情触发下的协变量偏移）**
设普通 BC 的累计代价界为 `J(π_BC) ≤ J(π_H) + O(εT²)`。若 CST 对「会离开示范分布」的状态具有召回率 `1-δ_trig`，且触发后最多查询 `B_q` 次，则
```
J(π_EBC) ≤ J(π_H) + O(ε·T) + O(δ_trig·T²) + O(B_q·T·ε_prior)
```
当 `δ_trig` 小到 `O(1/T)` 时，主导项从 `T²` 降为 `T`。代价是 `δ_trig` 依赖 `U_t` 的质量：**触发器的召回率而非精度决定该定理是否成立**。

**定理 15（反事实共情的可辨识边界）**
若 `g_ψ` 校准误差 `≤ ε_cal` 且排序 AUC `≥ 1-δ_rank`，则经反事实过滤保留的动作，其真实风险不超过 `(1-δ_rank)` 分位加 `ε_cal`。但当动作对 `(a,a')` 在示范数据中**无重叠（positivity 失败）**时，`g_ψ(e|s,a')` 是不可辨识的外推，此时上述保证失效。故 EBC 规定反事实共情只做 top-k 重排，不做安全证明——这是对「不可证伪」的工程承认。

**定理 16（EBC-RAS 端到端风险一致性）**
在 A87–A94 与定理 11 下，EBC-RAS 输出满足：
1. `P(|τ_cmd-τ*|>ε) ≤ α_chunk + δ_fi + α_emotion + α_wm + α_vqa + α_clone`；
2. `λ_total ≤ λ_RAS`（表达永不放宽）；
3. `e` 缺失 `⇒ c_use = c^prior_UC ≥ c_base ⇒ k*_EBC ≤ k*_base`（只降可用性，不降安全）；
4. 若 `ECE>0.05` 或 `demo_coverage<0.9`，`J_EBC` 判为 `Invalid`，系统退化到 `J_SimRAS` 并使用 `c_base`。

**定理 17（表达缺失的可用性—安全权衡）**
设表达对 `c` 的 Fisher 信息为 `I_e`，缺失概率为 `p_miss`，则有效信息降为 `(1-p_miss)I_e`，后验方差放大约 `1/(1-p_miss)`，认证前缀长度单调不增，但安全裕度下界不变。即：**遮挡只该让机器人变慢，不该让它变冒险**。

## 4. 实验设计 E271–E290

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E271 care/urgency 可辨识 | 两轴能否从表达+运动学中解耦 | 轴间互信息 < 0.1 nat，反事实重构 R² > 0.8 |
| E272 后验校准 | `c_UC` 的覆盖率是否可靠 | ECE < 0.05，95% 覆盖误差 < 2% |
| E273 CCP vs BC | 意图歧义任务下的安全与成功率 | 越界率 −60%，成功率不降 |
| E274 模式平均 | 边界附近是否仍学出中庸动作 | 危险中庸动作出现率 < 3% |
| E275 MEG 对抗表达 | 伪造/表演能否降低认证裕度 | 任意伪装下 `M ≥ M_base`，违规 = 0 |
| E276 ECQ 数据整形 | 含 30% 低质量示范时 | 安全率 +25%，不误删紧急示范 |
| E277 CST 触发 | OOD/关切意外的召回率 | 召回 > 92%，误触发 < 8% |
| E278 共情 DAgger | 查询预算下的样本效率 | 达到同安全水平所需查询 −50% |
| E279 反事实共情 | 排序与校准 | AUC > 0.8，ECE < 0.08 |
| E280 EWM-E 表达滚动 | 5 步表达预测误差 | 单步 KL < 0.1，5 步 < 0.4 |
| E281 ECA 审计一致性 | VQA 审计与人类专家判断 | 一致性 κ > 0.7 |
| E282 Sim2Empathy | 合成表达迁移到真人 | 跨文化风格下退化 < 20% |
| E283 端到端 EBC-RAS | 对比 BC/RAS/SimRAS | 越界 false-safe −70%，误降级不升 |
| E284 表达缺失 | 30s 全遮挡 | 仅前缀变短，`M` 下界不变 |
| E285 隐私 | 设备端 DP 编码的效用损失 | `ε_dp=2` 时 care 误差 < 0.1 |
| E286 公平性 | 不同人群的表达分布偏移 | 各族群误刹率差 < 5% |
| E287 表演/伪造攻击 | 刻意表演"放松"或"紧张" | 系统不因放松而放宽；因紧张仅更保守 |
| E288 实时性 | ELE+MEG+CCP 是否进预算 | 端到端 < 3ms |
| E289 长时程复利 | 1h 连续任务的累积误差 | 漂移 < 2× 普通 BC |
| E290 消融 | ELE/MEG/ECQ/CST/反事实各自贡献 | 每项可单独归因，去掉 MEG 风险显著上升 |

## 5. 本轮最大风险

**一句话**：EBC 的全部安全收益依赖「共情表达是示范者真实关切的可辨识代理」这一假设——而文化显示规则、职业性镇定、刻意表演与示范者自身"自信地做错"会系统性地让表达偏离真实关切；单调守卫能保证 EBC 不比行为基线更冒险，却无法阻止它**忠实地克隆错误**（学到一个"安全但无用"或"带着偏见"的策略），而反事实共情又因反事实表达不可观测而本质上不可证伪——这是本轮所有理论依赖的核心假设：**示范者的表达与其真实风险偏好之间存在可学习的单向一致性，且示范者本身是可靠的**。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 68 轮产物 · 创新点清单 v1：EBC（Empathic Behavior Cloning，共情行为克隆；EmD×ELE×CCP×MEG×ECQ×CST×EWM-E×ECA）

> 承接第 65~67 轮（VISTA → RAS → SimRAS）。前三轮把「故障可归因」「情绪驱动闭环」「仿真预演 + 视觉问答审计」依次补齐，却始终默认策略先验是给定的，人类只是被感知与审计的外部信号源。本轮补上缺失的「从人学」前端：**用共情表达作为示范者关切潜变量的证据，用行为克隆把动作与关切一起学下来，用单调守卫保证表达的可欺骗性不侵入安全边界。**
>
> IP 编号：IP-243~IP-252（共 10 个）。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进（相对第 67 轮） |
|---|---|---|---|
| IP-243 | EmD Empathic Demonstration Corpus | 新增 | 示范元组 `(s,a,e,h)`；表达含面部/语调/运动学三路，允许整段缺失 |
| IP-244 | ELE Empathic Latent Encoder | 新增 | 从 `(s,a,e)` 推断二维潜变量 `(c_care,c_urg)`；β-TC 解耦 + 分位上置信界 |
| IP-245 | CCP Care-Conditioned Policy | 新增 | `π_θ(a|s,c_use)`，以加权 BC 训练；在边界附近随 care 自动收动作 |
| IP-246 | MEG Monotone Empathy Guard | 新增 | `c_use=max(c_UC,c_base)`，`λ_EBC≤1`；**表达只收紧，永不放宽** |
| IP-247 | ECQ Empathic Curation & Query | 新增 | 按示范者可靠性与表达-动作一致性重加权；紧急语境下不误删反常规示范 |
| IP-248 | CST Care-Surprise Trigger | 新增 | 关切意外度超阈值 → DAgger 查询或保守前缀回退；直接压制 BC 协变量偏移 |
| IP-249 | EWM-E Empathic World Model head | 升级 WM | 在世界模型上加「人类表达响应」预测头，供 SimRAS 滚动与审计使用 |
| IP-250 | ECA Empathic Consistency Auditor | 升级 VQA | 增加反事实提问「示范者看到这条轨迹会不会担心」，结构化输出关切证据 |
| IP-251 | J_EBC Certificate | 升级 J | 增 `care_posterior, care_UCB, demo_coverage, ECE, privacy_budget, clone_safety_margin` |
| IP-252 | Sim2Empathy Pipeline | 新增 | 用 SimEngine 合成 `(s,a,c,e)`，解决共情表达数据稀缺与跨文化风格覆盖 |

## 1. 符号体系增量（定义 276–296）

| 符号 | 含义 |
|---|---|
| `EBC = (EmD, ELE, CCP, MEG, ECQ, CST, EWM-E, ECA, J_EBC)` | 共情行为克隆 |
| `D_E = {(s_t,a_t,e_t,h_t)}` | 共情示范数据集 |
| `e = (e_face,e_voice,e_kin) ∈ E` | 共情表达观测（可缺失） |
| `c = (c_care,c_urg) ∈ [0,1]^2` | 关切-紧迫潜变量 |
| `a ~ π_H(a|s,c)`，`e ~ p_H(e|s,a,c)` | 示范者生成模型 |
| `q_φ(c|s,a,e)` | 变分关切后验 |
| `c_UC = Q_{1-δ}(q_φ(c_care|s,a,e))` | 关切上置信界（越大越谨慎） |
| `c_use = max(c_UC, c_base)` | 单调守卫输出 |
| `λ_EBC = clip(1-α_E·c_use, 0.5, 1.0)` | 共情收紧系数（≤1） |
| `π_θ(a|s,c_use)` | 关切条件策略 |
| `M(s,a,c)` | 安全裕度，对 `c_care` 单调不减 |
| `w_i = r_i·exp(-β_c·KL(q(c|s,a,e)||q(c|s,a)))` | 共情数据权重 |
| `g_ψ(e|s,a,c)` | 反事实表达模型 |
| `U_t` | 关切意外度（熵 + KL） |
| `k_EBC` | 共情认证前缀 |
| `J_EBC` | 共情证书 |
| `ℰ_EBC = ℰ_SimRAS × ℰ_empathy × ℰ_clone` | 扩充干扰集 |

## 2. 形式化定义（完整版）

**定义 276（EBC 总览）**
```
EBC = (EmD, ELE, CCP, MEG, ECQ, CST, EWM-E, ECA, J_EBC)
```
定位：为 VISTA/RAS/SimRAS 补上「从人类示范学习策略与关切」的前端，而非替换其在线安全闭环。不变式：表达只进入潜变量后验与保守化方向；实时流只做前向推断，零在线学习写操作；表达原始数据不出端。

**定义 277（共情示范元组）** 示范数据 `D_E = {(s_t^i,a_t^i,e_t^i,h_t^i)}_{i,t}`。`h_t∈[0,1]` 为可选的示范者自报信心/风险，允许缺失；训练时以 `λ_h` 加权。

**定义 278（共情表达观测）** `e_t=(e_face,e_voice,e_kin)`：
- `e_face`：面部动作单元、68 关键点、瞬目/注视；
- `e_voice`：基频、能量、语速、停顿；
- `e_kin`：犹豫时长、减速、回撤、视线切换等运动学线索。
允许 `e_t=∅`（遮挡、静音、不可见）。

**定义 279（关切-紧迫潜变量）** `c_t=(c_care,c_urg)∈[0,1]^2`，慢变：`c_{t+1}=c_t+η_t`，`||η_t||≤η_max`。`c_care` 越大越风险厌恶；`c_urg` 越大时间压力越大。

**定义 280（示范者生成模型）**
```
s_{t+1} = f(s_t,a_t)
c_t     ~ p(c|s_t)
a_t     ~ π_H(a|s_t,c_t)
e_t     ~ p_H(e|s_t,a_t,c_t)
```
`e` 与 `a` 同为 `c` 的下游，但 `e` 不是 `a` 的确定性函数——这是表达提供额外信息的结构来源。

**定义 281（可辨识条件 A92–A94）**
- A92（无直接混杂）：给定 `(s,a)`，`c` 与 `e` 间无未观测共同原因；
- A93（单调似然比）：`p(e|c_care)` 在关切类特征上满足 MLR；
- A94（掩蔽不对称）：存在 `e*` 使 `p(e*|c_care^high)≫p(e*|c_care^low)`，反向不成立。

**定义 282（关切后验编码器）** 变分后验 `q_φ(c|s,a,e)`，训练目标
```
L_ELE = E_q[log p(a|s,c)] + λ_e·E_q[log p(e|s,a,c)]
        - β·TC(q(c|s,a,e)) + λ_h·E_q[log p(h|s,c)]
```
`TC` 为 total correlation，用于解耦 care 与 urgency；`λ_e` 使表达成为辅助似然而非硬标签。

**定义 283（关切上置信界）** `c_UC = Q_{1-δ}(q_φ(c_care|s,a,e))`，由分位数网络或 split-conformal 校准，覆盖率目标 `1-δ`。方向约定：`c_UC` 越大越谨慎。

**定义 284（单调共情守卫 MEG）**
```
c_base = Q_{1-δ}(q_φ(c_care|s,a))        # 仅动作证据
c_use  = max(c_UC, c_base)               # 只升不降
λ_EBC  = clip(1 - α_E·c_use, 0.5, 1.0)   # ≤ 1，只收紧
```
表达缺失时 `c_UC ← Q_{1-δ}^{prior}(c_care|s)`。不变式：`λ_total = λ_RAS·λ_EBC ≤ λ_RAS`，且 `k_EBC ≤ k_base`。

**定义 285（关切条件策略）** `π_θ(a|s,c_use)`，目标
```
max_θ Σ_i w_i·log π_θ(a_i|s_i,c_use,i) - λ_reg·R_reg(θ)
```
训练中 `c_use` 由定义 284 生成，故策略只在「不低于行为基线谨慎度」的区域采样。

**定义 286（care-单调策略类）** 安全裕度 `M(s,a,c)` 满足
```
c_care^1 ≥ c_care^2  ⇒  M(s,a,c^1) ≥ M(s,a,c^2)
```
策略在满足任务约束下最大化 `M`。该单调性是「共情→保守」可组合的结构前提。

**定义 287（共情数据整形 ECQ）** 可靠性 `r_i = σ(α_1·consistency_i + α_2·calibration_i - α_3·contradiction_i)`，样本权重
```
w_i = r_i · exp(-β_c·KL(q(c|s_i,a_i,e_i) || q(c|s_i,a_i)))
```
`contradiction_i` 在 `c_urg` 高时按 `(1-c_urg)` 衰减，避免把紧急示范当错误样本删除。

**定义 288（反事实表达模型与偏好）** `g_ψ(e|s,a,c)` 训练自 `D_E` 与 Sim2Empathy。反事实偏好
```
Δ(a→a') = E_{c~q}[ D_KL( g(e|s,a',c) || g(e|s,a,c) ) ]
```
`Δ` 仅用于 top-k 候选重排/过滤，**永不单独充当安全证明**（见定理 15）。

**定义 289（关切意外度与 CST 触发）**
```
U_t = H(q(c|s_t,a_t,e_t)) + η·KL(q(c|s_t,a_t,e_t) || q_pred(c|s_t,a_t))
U_t > τ_cst  ⇒  CST = ON
```
触发后：人可介入则 DAgger 查询；不可介入则回退 `k ← min(k, k_fallback)` 并保持 `c_use`。

**定义 290（共情查询规则）** 以 `(s_t, a_t^CCP)` 请求示范者接管/标注，新样本并入 `D_E`。查询预算 `B_q` 与触发召回率共同决定定理 14 的收敛项。

**定义 291（共情滚动）** SimEngine 依 `c` 动力学与 `g_ψ` 生成 `{(s,a,c,e)_{t+i}}`；`e_{t+i}` 供 EWM-E 训练、供 ECA 做「示范者看到轨迹是否担心」的审计。

**定义 292（EBC-RAS 耦合）**
```
k_EBC = max{k : ∀i≤k, M(s_{t+i},a_{t+i},c_use)·λ_total ≥ 0}
k*    = min(k_VISTA, k_emo, k_wm, k_EBC, m_ras)
λ_total = λ_RAS·λ_EBC,  λ_EBC ≤ 1
```
表达缺失时 `c_use=c^prior_UC`，`k_EBC` 单调不增。

**定义 293（J_EBC 证书）**
```
J_EBC = (J_SimRAS, care_posterior, care_UCB, demo_coverage,
         care_calibration_ECE, privacy_budget, clone_safety_margin,
         empathic_consistency)
Valid ⇔ Valid(J_SimRAS) ∧ ECE ≤ 0.05 ∧ demo_coverage ≥ 0.9 ∧ privacy_ok
```

**定义 294（AIC-EBC 干扰集）**
```
ℰ_EBC = ℰ_SimRAS × ℰ_empathy × ℰ_clone
ℰ_empathy = {掩蔽, 表演, 文化显示规则, 疲劳, 对抗伪造}
ℰ_clone   = {分布偏移, 模式平均, 虚假相关, 示范者错误}
```

**定义 295（示范者可靠性）** 见定义 287 的 `r_i`；另设跨示范者一致性 `consistency_i` 与自报校准 `calibration_i`。可靠性低于 `r_min` 的示范只进入预训练、不进入安全证书覆盖统计。

**定义 296（在线不变式与隐私）** 表达只在设备端编码，原始 `e` 不出端；对外只发布 `(c_use, λ_EBC, k_EBC, J_EBC)` 与哈希。隐私预算耗尽或表达缺失时退回先验保守界：可用性下降、安全裕度不降。

## 3. 关键算法伪代码

```python
# IP-243/244 EmD + ELE
class EmpathicLatentEncoder:
    def __init__(self, net, prior_net, beta_tc=4.0, delta=0.05):
        self.net, self.prior_net = net, prior_net
        self.beta_tc, self.delta = beta_tc, delta

    def encode(self, s, a, e=None):
        if e is None:
            q = self.prior_net(s, a)
            return q, self.ucb(q, self.delta), True
        q_care, q_urg = self.net(s, a, e)
        return (q_care, q_urg), self.ucb(q_care, self.delta), False

    def ucb(self, q, delta):
        return self.quantile(q, 1.0 - delta)     # 越大越谨慎

    def loss(self, s, a, e, h=None):
        q = self.net(s, a, e)
        rec_a = -log_lik(q, a)
        rec_e = -log_lik_expr(q, s, a, e)
        tc = total_correlation(q)                 # 解耦 care/urg
        aux = -log_lik_h(q, h) if h is not None else 0.0
        return rec_a + 1.0*rec_e + self.beta_tc*tc + 0.5*aux


# IP-246 MEG
class MonotoneEmpathyGuard:
    def __init__(self, alpha_e=0.5, lam_lo=0.5):
        self.alpha_e, self.lam_lo = alpha_e, lam_lo

    def guard(self, c_uc, c_base):
        c_use = max(c_uc, c_base)                 # 表达只升不降
        lam = max(self.lam_lo, min(1.0, 1.0 - self.alpha_e*c_use))
        return c_use, lam


# IP-245 CCP
class CareConditionedPolicy:
    def __init__(self, policy_net):
        self.policy = policy_net

    def propose(self, s, c_use, n_chunks=8):
        scores = [self.policy.chunk_score(s, a, c_use) for a in self.policy.candidates(s)]
        return self.policy.decode(sorted(scores, key=lambda x: x.margin, reverse=True)[:n_chunks])

    def train(self, D_E, ele, weights):
        for (s, a, e, h), w in zip(D_E, weights):
            _, c_uc, _ = ele.encode(s, a, e)
            c_base = ele.ucb(ele.prior_net(s, a), ele.delta)
            c_use, _ = MEG().guard(c_uc, c_base)
            loss = -w * self.policy.log_prob(a, s, c_use)
            self.policy.backward(loss)


# IP-247 ECQ
def empathic_curation(D_E, ele, r_min=0.3):
    weights = []
    for (s, a, e, h) in D_E:
        q_full, _, missing = ele.encode(s, a, e)
        q_act, _, _ = ele.encode(s, a, None)
        kl = KL(q_full, q_act) if not missing else 0.0
        r = estimator_reliability(s, a, e, h)          # 定义 287/295
        w = 0.0 if r < r_min else r * math.exp(-0.5*kl)
        weights.append(w)
    return weights


# IP-248 CST
class CareSurpriseTrigger:
    def __init__(self, tau=0.6, eta=0.5):
        self.tau, self.eta = tau, eta

    def surprise(self, q_c, q_urg, a_prev):
        H = entropy(q_c) + entropy(q_urg)
        kl = KL(q_c, self.q_pred(a_prev))
        return H + self.eta*kl

    def step(self, s, a, U, human_available, k, c_use, M):
        if U <= self.tau:
            return k, False
        if human_available:
            M.query_human(s, a)
            return k, True
        return min(k, M.fallback_prefix(s, c_use)), True


# IP-249 EWM-E
class EmpathicWorldModelHead:
    def __init__(self, trunk, expr_head):
        self.trunk, self.expr_head = trunk, expr_head

    def rollout(self, z_t, act_seq, k=5):
        preds = []
        for a in act_seq[:k]:
            z_t = self.trunk.step(z_t, a)
            preds.append({'e': self.expr_head(z_t), 'z': z_t})
        return preds


# IP-251/252 EBC 在线环路
def EBC_round(M, s, e, a_prev, base_prefix):
    # 1) 关切后验 + 单调守卫
    q_c, c_uc, missing = M.ele.encode(s, a_prev, e)
    c_base = M.ele.ucb(M.ele.prior_net(s, a_prev), M.ele.delta)
    c_use, lam_ebc = M.meg.guard(c_uc, c_base)

    # 2) 关切条件策略
    A = M.ccp.propose(s, c_use)
    k = M.certify_prefix(A, c_use, min(base_prefix, len(A)))

    # 3) 关切意外 -> 查询 / 回退
    U = M.cst.surprise(q_c[0], q_c[1], a_prev)
    if U > M.cst.tau:
        if M.human_available:
            M.cst.step(s, A[:k], U, True, k, c_use, M)
        else:
            k = M.cst.step(s, A[:k], U, False, k, c_use, M)[0]

    # 4) 与 RAS 链路耦合（只收紧）
    lam = M.ras.lambda_risk * lam_ebc
    return A[:k], c_use, lam, U, missing
```

## 4. 推导

**引理 13（共情信息恒等式）**
```
I(c; a,e | s) = I(c; a | s) + I(c; e | s,a)
```
证明：链式法则直接展开，`I(c;e|s,a)=E[log p(e|s,a,c)/p(e|s,a)]≥0`。故表达在 A92 下只可能增加关于 `c` 的信息；若 `e` 与 `c` 条件独立，则 EBC 精确退化为普通 BC，不会更差。

**引理 14（单调守卫的最坏情况安全）**
设 `M(s,a,c)` 对 `c_care` 单调不减（定义 286）。对任意 `e`（含对抗伪造），`c_use=max(c_UC,c_base)≥c_base`，故
```
M(s,a,c_use) ≥ M(s,a,c_base)
```
证明：由 `max(·,·)` 的下界与单调性直接得到。该结论不依赖 A93/A94 与 `e` 的分布，是分布无关保证；表达是否忠实只决定保守程度，不决定安全下界。

**引理 15（去模式平均）**
设 `c∈{c_low,c_high}`，`c_low<c_high`，对应示范动作 `a_low,a_high`。BC 边缘策略给出 `ā=½(a_low+a_high)`。若 `M(s,·,c)` 关于动作凹且对 `c` 单调，则
```
M(s,ā,c_high) ≤ ½[M(s,a_low,c_high)+M(s,a_high,c_high)]
```
当 `a_low` 是唯一满足 `M≥0` 的动作时，条件化 `c_use≥c_high-δ` 可把动作拉回安全侧，避免模式平均越界。

**定理 14（共情触发下的协变量偏移）**
设普通 BC 累计代价界 `J(π_BC) ≤ J(π_H)+O(εT²)`；CST 对「将离开示范分布」状态召回率 `1-δ_trig`；触发后查询预算 `B_q`。则
```
J(π_EBC) ≤ J(π_H) + O(εT) + O(δ_trig·T²) + O(B_q·T·ε_prior)
```
证明思路：标准 BC 的 `T²` 项来自每一步 `O(ε)` 的 OOD 概率累积；CST 以 `1-δ_trig` 概率在该步插入专家纠正，使该步之后的误差重置为 `O(ε)`，仅剩漏检的 `δ_trig` 部分继续按 `T²` 累积；查询预算项来自纠正样本的估计误差。当 `δ_trig=O(1/T)` 时主导项降为 `T`。**触发召回率而非精度**是该定理成立的关键。

**定理 15（反事实共情的可辨识边界）**
若 `g_ψ` 校准误差 `≤ε_cal`、排序 AUC `≥1-δ_rank`，则反事实过滤保留动作的真实风险 `≤ (1-δ_rank)` 分位 `+ε_cal`。但当 `(a,a')` 在示范数据中无重叠（positivity 失败）时，`g_ψ(e|s,a')` 为不可辨识外推，保证失效。故 EBC 规定反事实共情只做 top-k 重排，不做安全证明。

**定理 16（EBC-RAS 端到端风险一致性）**
在 A87–A94 与定理 11（SimRAS）下：
1. `P(|τ_cmd-τ*|>ε) ≤ α_chunk+δ_fi+α_emotion+α_wm+α_vqa+α_clone`；
2. `λ_total=λ_RAS·λ_EBC ≤ λ_RAS`；
3. `e` 缺失 `⇒ c_use=c^prior_UC≥c_base ⇒ k*_EBC≤k*_base`；
4. `ECE>0.05 ∨ demo_coverage<0.9 ⇒ J_EBC=Invalid`，退化到 `J_SimRAS` 且沿用 `c_base`。
证明：由引理 14 得 `λ_total` 永不超过 RAS 上界；由定义 284/292 得缺失时前缀单调不增；其余项由定理 11 的误差分解逐项继承，`α_clone` 来自 CCP 的加权 BC 泛化误差。

**定理 17（表达缺失的可用性—安全权衡）**
设表达对 `c` 的 Fisher 信息为 `I_e`，缺失概率 `p_miss`，则有效信息 `≤(1-p_miss)I_e`（数据处理不等式），后验方差放大约 `1/(1-p_miss)`，认证前缀长度单调不增，但由引理 14 安全裕度下界不变。即：**遮挡只该让机器人变慢，不该让它变冒险。**

## 5. 复杂度分析

| 组件 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|
| ELE 前向（`(s,a,e)` 编码 + 分位头） | <0.4ms | 20MB | 引理 13、定理 17 |
| MEG | O(1) <0.01ms | O(1) | 引理 14：分布无关安全下界 |
| CCP（8 候选块打分） | <0.2ms | 15MB | 引理 15、定理 14 |
| CST 触发 | <0.1ms | O(1) | 定理 14：召回率决定偏移界 |
| EWM-E（共享 WM 主干，k=5） | <0.5ms | 50MB | 定理 15：仅排序不外推 |
| ECQ（离线） | 一次 O(N) | O(N) | 定义 287/295 |
| ECA（VQA 异步） | 50ms/次（后台） | 200MB | 定义 291、定理 15 |
| Sim2Empathy（离线） | 10^6 轨迹 | 500GB | 定义 291 |
| 实时环路总计 | ELE+MEG+CCP+CST <1ms；含 WM 共享 <3ms | — | 定理 16：风险一致性 |

## 6. 实验设计 E271–E290

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E271 care/urgency 可辨识 | 两轴能否从表达+运动学中解耦 | 轴间互信息 <0.1 nat，反事实重构 R² >0.8 |
| E272 后验校准 | `c_UC` 覆盖率是否可靠 | ECE <0.05，95% 覆盖误差 <2% |
| E273 CCP vs BC | 意图歧义任务下的安全与成功率 | 越界率 −60%，成功率不降 |
| E274 模式平均 | 边界附近是否仍学出中庸动作 | 危险中庸动作出现率 <3% |
| E275 MEG 对抗表达 | 伪造/表演能否降低认证裕度 | 任意伪装下 `M≥M_base`，违规 =0 |
| E276 ECQ 数据整形 | 含 30% 低质量示范 | 安全率 +25%，紧急示范不被误删 |
| E277 CST 触发 | OOD/关切意外的召回 | 召回 >92%，误触发 <8% |
| E278 共情 DAgger | 查询预算下的样本效率 | 同安全水平所需查询 −50% |
| E279 反事实共情 | 排序与校准 | AUC >0.8，ECE <0.08 |
| E280 EWM-E 表达滚动 | 5 步表达预测误差 | 单步 KL <0.1，5 步 <0.4 |
| E281 ECA 审计一致性 | VQA 与人类专家判断 | 一致性 κ >0.7 |
| E282 Sim2Empathy | 合成表达迁移到真人 | 跨文化风格退化 <20% |
| E283 端到端 EBC-RAS | 对比 BC/RAS/SimRAS | false-safe −70%，误降级不升 |
| E284 表达缺失 | 30s 全遮挡 | 仅前缀变短，`M` 下界不变 |
| E285 隐私 | 设备端 DP 编码的效用损失 | `ε_dp=2` 时 care 误差 <0.1 |
| E286 公平性 | 不同人群表达分布偏移 | 各族群误刹率差 <5% |
| E287 表演/伪造攻击 | 刻意表演放松或紧张 | 放松不放宽；紧张仅更保守 |
| E288 实时性 | ELE+MEG+CCP+CST 是否进预算 | 端到端 <3ms |
| E289 长时程复利 | 1h 连续任务累积误差 | 漂移 <2× 普通 BC |
| E290 消融 | ELE/MEG/ECQ/CST/反事实贡献 | 各项可单独归因；去 MEG 风险显著上升 |

## 7. 本轮最大风险

**一句话**：EBC 的全部安全收益依赖「共情表达是示范者真实关切的可辨识代理」这一假设——文化显示规则、职业性镇定、刻意表演与示范者自身"自信地做错"会系统性让表达偏离真实关切；单调守卫能保证 EBC 不比行为基线更冒险，却无法阻止它**忠实地克隆错误**（学到"安全但无用"或"带着群体偏见"的策略），而反事实共情又因反事实表达不可观测而本质上不可证伪——这是本轮所有理论依赖的核心假设：**示范者的表达与其真实风险偏好之间存在可学习的单向一致性，且示范者本身可靠**。
<!-- ARTIFACT:END -->