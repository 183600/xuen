# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 55 轮（承接第 54 轮 v31 GroundEdge-GenSim+++；灵感循环第 6 轮；本轮灵感：「差异化定位」×「Gazebo」）

> 第 54 轮把技能组合约束到动作剖面 `α_S`、组合图 `G_S`、云边映射 `γ_ce` 与联合证书 `J`。本轮抓住「差异化定位」的双关，同时补两个致命缺口：其一，v31 的全部证书都是**绝对**的——它只说"系统能成"，从不说"相对最强基线，差异是什么、是否可归因"，于是整套体系可能被审稿人一句"增量集成"击穿；其二，机器人的**差分/相对定位**误差会直接吃掉第 54 轮的云边动作对齐预算 `δ_a`，而 Gazebo 产生的绝对仿真证据并不能支撑竞争性主张。核心矛盾——**H22：无差异化证书的绝对成功率是不可证伪的，堆叠越多层，可发表的新颖性反而越稀释；H23：相对定位协方差经 `γ_ce` 放大后侵入 `δ_a`，使"仿真里更好"在真机动作空间里退化为"更差或不可区分"。**

## 0. 直觉与动机

**灵感 1（差异不是形容词，而是可判定的证书）**
直觉："创新"不是"我加了模块"，而是"在最强的基线包络 `𝔅` 上，我至少在一个能力维度上有**可归因、可复现、下界为正**的差值"。因此必须把"差异化定位"写成一个四元主张 `D = (𝔅, m, Δ, A)`：基线集、度量、差值、归因机制；再加见证集 `W`（能把本方法与基线区分开的具体场景）。没有 `W` 的差异只是叙事，不是证据。

**灵感 2（"定位"的第二种读法：差分/相对定位）**
直觉：相对位姿 `T_ij` 来自**差分观测**（差分 GPS/RTK、双目光束法、机器人间测距），其协方差 `Σ_ij` 不是外围工程细节，而是直接进入第 54 轮动作对齐容差：`δ_a ≥ c_loc·‖Σ_ij^{1/2}‖₂ + v_max·τ_loop + b_sys`。**定位漂移一旦超预算，云端的粗动作 `A_c` 在边端就会被映射到错误细动作，`γ_ce` 再 Lipschitz 也救不回来。** 这把"定位"从感知模块提升为组合可部署性的第一性约束。

**灵感 3（Gazebo 是仪器 + 差分放大器，不是真理）**
直觉：绝对仿真证据被引擎保真度 `φ_g` 打折；但**配对差分**能消掉共模偏差。若让方法与基线共享同一随机数流 `ω`（同一初始位姿、同一扰动序列、同一传感噪声种子），则 `Δ̂ = E[m(M;ω) - m(b;ω)]` 中引擎的系统偏差被相减抵消，只剩**方法差异 + 配对残差**。这比"各自跑 100 次取均值"方差小一到两个数量级，是低预算下获得可信差异化结论的关键。

**灵感 4（诚实零结果：找不到差异就承认）**
直觉：差异化研究最常见的自欺是"多重比较 + 挑指标"。应以**区分性实例搜索**（discriminating instance test）主动寻找最难区分的场景：若在预注册度量与足够功效下仍找不到 `Δ_LB ≥ δ_min`，则输出 `null_result`，明确宣称"无可测差异"，而不是换一个指标继续挖。可证伪的零结果，比不可证伪的正结果更有价值。

**灵感 5（双钥匙部署：`J` 管能不能，`DPC` 管值不值）**
直觉：把第 54 轮联合证书 `J`（可部署性）与本轮差异化定位证书 `DPC`（创新性/价值）并联：`deploy ⟺ J.ok ∧ DPC.ok`。这防止"能跑但毫无差异化"的系统被包装成创新，也防止"指标好看但动作不可对齐"的系统被部署。差异化不是事后写 related work，而是**部署门禁的一把钥匙**。

**灵感 6（差异化定位指数驱动研究搜索）**
直觉：研究本身是可优化的。定义 `DPI = min_{m∈M} margin_m / (σ_m·√(1/N) + ε)`，即**最弱维度上的标准化差异下界**，再乘基线包络覆盖与归因强度。用 `DPI` 而不是绝对 SOTA 引导下一轮想法选择：宁可在一个维度上有 3σ 的清晰差异，也不要五个维度上各 0.2σ 的模糊领先。

## 1. 形式化定义（增量：定义 121–128）

**定义 121（基线包络）**
基线包络 `𝔅 = {b_1,…,b_k}` 是一组竞争者，满足：对每个 `b`，其在 `(性能, 资源成本, 假设强度)` 三维上不被本方法严格支配；且 `𝔅` 至少含一个"强基线"（同信息量、同算力预算下的最佳已知方法）。**反稻草人审计** `audit(𝔅)=1` 当且仅当 `∀b∈𝔅` 存在文献/复现证据表明 `b` 在其适用域内接近 Pareto 前沿；否则差异化主张视为**空真**（vacuous），拒绝签发。

**定义 122（差异化主张）**
差异化主张 `D = (𝔅, m, Δ, A, W)`：
- `m` 为**预注册**度量（分析前固定，不得事后挑选）；
- `Δ = m(M) - max_{b∈𝔅} m(b)` 为差值；
- `A` 为归因证据：消融实验显示移除机制 `c` 后 `Δ` 显著塌缩；
- `W` 为见证集：一组能把 `M` 与所有 `b` 区分开的具体实例（`∃w∈W, ∀b, m_w(M)>m_w(b)`）。
`D` **可证伪**当且仅当 `m` 预注册、`W` 非空、且给出拒绝阈值 `δ_min`。

**定义 123（可归因差异）**
称差异 `Δ` 可归因于机制 `c`，若 `Δ_c = Δ - Δ_{¬c} ≥ δ_attr`，其中 `Δ_{¬c}` 为移除 `c` 后的差值。仅当 `audit(𝔅)=1 ∧ Δ_c ≥ δ_attr` 时，`D` 才从"相关"升级为"机制性差异化"。

**定义 124（Gazebo 仪器剖面与证据折扣）**
物理维度集 `𝔇_phys = {contact, friction, restitution, inertia, actuator, sensor, latency}`。仿真器 `g` 的保真度剖面 `φ_g: 𝔇_phys → [0,1]`，复合保真度 `Φ_g = min_{d∈𝔇_phys} φ_g(d)`（木桶原则）。**绝对证据**打折为 `Ev_g(e) = Φ_g·e`；**差分证据**仅对**声明维度**要求 `φ_g(d) ≥ φ_min`，其共模偏差由配对相减消除。

**定义 125（同源随机数差分估计）**
对共享随机源 `ω_i` 的配对样本 `(m_i(M;ω_i), m_i(b;ω_i))`，差分估计
```
Δ̂ = (1/N) Σ_{i=1}^{N} [ m_i(M;ω_i) - m_i(b;ω_i) ],   Var(Δ̂) ≈ σ_Δ²/N
```
若配对差近似 `σ_Δ`-sub-Gaussian，则单侧置信下界
```
Δ_LB(α) = Δ̂ - σ_Δ · sqrt(2 ln(1/α) / N)
```
**差异化成立**当且仅当 `Δ_LB(α) ≥ δ_min`。配对化把方差从 `σ_M²+σ_b²` 降到 `σ_Δ² = σ_M²+σ_b²-2Cov`，在共模相关强时收益可达一个数量级。

**定义 126（差分/相对定位证书）**
系统在激励轨迹 `u_{1:T}` 下的相对位姿 `T_ij`，差分观测模型 `z_t = h(o_i,t, o_j,t) + η_t`。经验相对可观测 Gramian `W_ij = Σ_t Φ_tᵀ R_η^{-1} Φ_t`，**相对定位可观测性** `obs_rel = λ_min(W_ij)`。相对定位协方差上界 `Σ_ij ⪯ W_ij^{-1}`。证书成立当且仅当 `obs_rel ≥ obs_min`（持续激励，避免共线/静止退化）且 `‖Σ_ij^{1/2}‖₂ ≤ δ_loc`。

**定义 127（定位-动作对齐耦合不等式）**
云边动作对齐容差必须吸收相对定位与通信时延：
```
δ_a ≥ c_loc·‖Σ_ij^{1/2}‖₂ + v_max·τ_loop + b_sys
```
`c_loc` 为 `γ_ce` 在 `A_core` 上的 Lipschitz 常数（承接第 54 轮 A27），`v_max` 为最大任务速度，`b_sys` 为标定系统误差。**若该不等式违反，则必须收缩 `A_core` 或重标定 `γ_ce`，不得以调高 `δ_a` 预算的方式掩盖定位退化。**

**定义 128（差异化定位证书 DPC）**
`DPC = (𝔅, Δ_LB, A, W, φ_g|_{𝔇_claim}, Σ_ij, δ_a, null_result)`。签发条件：
```
audit(𝔅)=1 ∧ Δ_LB(α) ≥ δ_min ∧ Δ_c ≥ δ_attr
∧ W ≠ ∅ ∧ φ_g(d) ≥ φ_min ∀d∈𝔇_claim
∧ δ_a ≥ c_loc·‖Σ_ij^{1/2}‖₂ + v_max·τ_loop + b_sys
```
若功效不足（`N` 小或 `σ_Δ` 大）而 `Δ_LB < δ_min`，**不得**判为"方法更差"，只能输出 `null_result = insufficient_power`；若功效足够且 `Δ_LB ≤ -δ_min`，则诚实地判定"本方法被强基线显著超越"，触发研究方向回退。

## 2. 关键算法 伪代码

### IP-121 BEA（Baseline Envelope Audit，反稻草人）

```python
def audit_baseline_envelope(baselines, method, domains):
    for b in baselines:
        if dominated(b, method):                 # 基线被严格支配
            return ('reject', 'weak_baseline', b)
        if not pareto_near_front(b, domains):    # 不在适用域 Pareto 前沿附近
            return ('reject', 'straw_man', b)
    return ('ok', baseline_cover(baselines, domains))
```

### IP-122 GIP（Gazebo Instrument Profile，仪器标定）

```python
def gazebo_instrument_profile(gazebo, real_logs, dims=PHYS_DIMS):
    phi = {}
    for d in dims:
        sim_dist = gazebo.sweep(d)               # 受控扫参
        real_dist = empirical(real_logs, d)
        phi[d] = distribution_agreement(sim_dist, real_dist)
    return FidelityProfile(phi, Phi=min(phi.values()))  # 木桶原则
```

### IP-123 CRD（Common-Random-number Differential test）

```python
def crn_differential_test(method, baseline, instances, omega_stream, alpha, delta_min):
    diffs = []
    for inst, omega in paired(instances, omega_stream):   # 共享随机源
        a = evaluate(method,   inst, omega)
        b = evaluate(baseline, inst, omega)
        diffs.append(a - b)
    d_hat = mean(diffs)
    sigma = robust_std(diffs)                            # MAD/Huber，抗离群
    n = len(diffs)
    d_lb = d_hat - sigma * sqrt(2 * log(1/alpha) / n)
    if d_lb >= delta_min:
        return ('differentiated', d_lb, diffs)
    if paired_power(diffs, delta_min, alpha) < 0.8:
        return ('null_insufficient_power', d_lb, diffs)
    return ('not_differentiated', d_lb, diffs)
```

### IP-124 RLC（Relative Localization Certificate）

```python
def relative_localization_certificate(obs_i, obs_j, u, R_eta, obs_min, delta_loc):
    W = empirical_relative_gramian(obs_i, obs_j, u, R_eta)  # Σ Φ^T R^-1 Φ
    obs_rel = min_eig(W)
    if obs_rel < obs_min:                                   # 共线/静止退化
        return ('reject', 'insufficient_excitation', obs_rel)
    Sigma_ij = inv(W)
    if spectral_norm_sqrt(Sigma_ij) > delta_loc:
        return ('reject', 'localization_budget', Sigma_ij)
    return ('ok', Sigma_ij, obs_rel)
```

### IP-125 DPC（Differential Positioning Certificate）

```python
def differential_positioning_certificate(M, B, metrics, instances, phi_g, Sigma_ij,
                                         gamma_lip, v_max, tau_loop, b_sys,
                                         delta_min, delta_attr, delta_a, alpha):
    ok, cover = audit_baseline_envelope(B, M, metrics)
    if not ok: return ('reject', 'straw_man_envelope')
    claims = []
    for m in preregistered(metrics):                       # 预注册，禁止事后挑
        worst_lb = +inf
        for base in B:
            res = crn_differential_test(M, base, instances, CRN, alpha, delta_min)
            if res[0] != 'differentiated':
                return ('null', m, res[0])                 # 诚实零结果
            worst_lb = min(worst_lb, res[1])
        witnesses = find_discriminating_witnesses(M, B, m)  # W ≠ ∅
        if not witnesses: return ('reject', 'no_witness', m)
        if ablation_delta(M, m) < delta_attr:              # 可归因
            return ('reject', 'not_attributable', m)
        claims.append(DiffClaim(m, worst_lb, witnesses))
    lhs = delta_a
    rhs = gamma_lip * spectral_norm_sqrt(Sigma_ij) + v_max * tau_loop + b_sys
    if lhs < rhs:                                          # 定义 127 耦合
        return ('reject', 'alignment_localization_violation', lhs, rhs)
    for d in claimed_dims(metrics):
        if phi_g[d] < PHI_MIN:
            return ('reject', 'fidelity_underclaim', d)
    return ('ok', DPC(claims, cover, phi_g, Sigma_ij, delta_a))
```

### IP-126 DPI（Differentiation-guided Search）

```python
def differentiation_index(candidates, B, power_fn):
    scored = []
    for cand in candidates:
        margins = [power_fn(cand, b) for b in B]           # 标准化下界
        dpi = min(margins) * coverage_bonus(B) * attribution_strength(cand)
        scored.append((dpi, cand))
    return max(scored)                                     # 最弱维度最优
```

## 3. 复杂度与正确性

| 组件 | 时间复杂度 | 空间复杂度 | 正确性关键 |
|---|---|---|---|
| BEA | O(|𝔅|·|𝔇|·|metric|) | O(|𝔅|) | 基线 Pareto 前沿、反稻草人 |
| GIP | O(|𝔇_phys|·N_real) | O(|𝔇_phys|) | 每维受控辨识、木桶短板 |
| CRD | O(N·(|M|+|b|)) | O(N) | 共享随机源、配对可交换 |
| RLC | O(T·n²) | O(n²) | 持续激励、Gramian 满秩 |
| DPC | O(|𝔅|·N·|m|) | O(N) | 预注册度量、诚实零结果 |
| DPI | O(|C|·|𝔅|) | O(|C|) | 最弱维度 min 聚合 |

**正确性定理（Differential Positioning Soundness）**
假设 (A29) 配对差 `σ_Δ`-sub-Gaussian 且随机源可交换；(A30) 声明维度上 `φ_g(d) ≥ φ_min`；(A31) 相对定位满足 `obs_rel ≥ obs_min` 且定义 127 不等式成立。则对签发通过的 `DPC`，其"相对 `𝔅` 存在正差异"的误报率
```
P(false differentiation) ≤ α + P(Φ_g < φ_min) + P(δ_a overrun)
```
且与第 54 轮联合证书 `J` 并联后，部署成功概率仍满足
```
P_success ≥ 1 - Σ_d(1-ρ_min(d)) - β_E - P(δ_a > Θ_a) - P(false differentiation)
```
**关键**：差异化主张不替代可部署性，而是与之正交；`J.ok ∧ DPC.ok` 才同时保证"能跑"与"值得跑"。

## 4. 实验设计 E162–E166

| 实验 | 指标 | 目标 |
|---|---|---|
| E162 Gazebo 仪器标定 | 每维 `|φ_g(d)-φ_real(d)|` | MAE ≤ 0.05，`Φ_g` 可复现 |
| E163 CRN 方差缩减 | `Var_unpaired / Var_paired` | 缩减 ≥ 8×（共模强时 ≥ 20×） |
| E164 差异化下界覆盖率 | `Δ_LB` 的实证覆盖率 / 误报率 | 覆盖 ≥ 95%，误报 ≤ 5% |
| E165 定位-对齐耦合 | `δ_a` 违反率 vs `obs_rel` | 违反率 ≤ 2%，且与定义 127 预测一致 |
| E166 DPI 引导的研究搜索 | 10 轮后最佳可区分候选的 `DPI` | 相对随机搜索提升 ≥ 25% |

## 5. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| 稻草人基线使差异空真 | 高 | BEA 审计 + 强基线复现 + 预注册基线集 |
| 预注册后偷换度量（p-hacking） | 高 | 度量锁 + 见证集先行 + 零结果登记 |
| CRN 配对在域随机化下失效 | 高 | 分块 CRN（按域参数配对）+ 交换性检验 |
| 相对定位退化（共线/静止） | 高 | 持续激励轨迹 + `obs_rel` 否决 + 主动激励 |
| 把 `δ_a` 当垃圾桶吸收定位误差 | 高 | 定义 127 硬约束 + 定位退化绊线 |
| 诚实零结果被误读为失败 | 中 | 零结果作为一等产物 + 功效报告 |

## 6. 本轮最大风险

**一句话**：把"差异化定位"升格为可判定证书并让 Gazebo 以同源随机数充当差分放大器，确实能把"增量集成"的指责转化为可证伪的机制性主张，但其 soundness **同时依赖基线包络的真实性、配对随机源的可交换性、以及相对定位-动作对齐耦合不等式的成立**；一旦基线被无意识地选成稻草人、或域随机化破坏 CRN 配对、或相对定位在弱激励下协方差爆炸而 `δ_a` 被悄悄调大，我们就会得到"统计上显著但机制上虚假"的差异化结论，故必须以 **BEA 反稻草人 + 分块 CRN 交换性检验 + 定义 127 硬约束** 三重护栏，宁可诚实地报告零结果，也绝不把"仿真里赢了弱基线"当作创新已成立。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 55 轮产物 · 创新点清单 v32：GroundEdge-GenSim++++（DPC×CRD×RLC×BEA×DPI×DIT）

> 承接第 54 轮产物 v31。本轮不继续堆叠"能力模块"，而是为整个体系补上**可证伪的差异化定位层**，并把「定位」落回机器人语义：
> - **DPC（Differential Positioning Certificate）**：差异化定位证书，把"相对强基线的可归因优势"写成可签发/可拒绝的证书；
> - **CRD（Common-Random-number Differential test）**：Gazebo 同源随机数配对 A/B，抵消物理引擎共模偏差、方差缩减；
> - **RLC（Relative Localization Certificate）**：差分/相对定位证书，输出 `Σ_ij` 与可观测性下界；
> - **BEA（Baseline Envelope Audit）**：反稻草人基线审计，杜绝"空真差异"；
> - **DPI（Differentiation Positioning Index）**：最弱维度标准化差异下界，驱动研究搜索；
> - **DIT（Discriminating Instance Test）**：主动生成区分性实例（见证集 `W`），支持诚实零结果。
>
> IP 编号：IP-121~IP-126（共 6 个新增）。升级第 54 轮 `J` 为**双钥匙部署门禁** `J ⊓ DPC`；`δ_a` 由定义 127 硬约束，不再是无约束预算。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进 |
|---|---|---|---|
| IP-121 | BEA Baseline Envelope Audit | 新增 | 基线 Pareto 前沿审计，拒绝稻草人与被支配基线 |
| IP-122 | GIP Gazebo Instrument Profile | 新增 | 逐物理维保真度 `φ_g`，复合 `Φ_g=min`，绝对证据打折 |
| IP-123 | CRD Common-Random-number Differential test | 新增 | 共享随机源配对差分 `Δ_LB`，共模偏差相消，方差降 8–20× |
| IP-124 | RLC Relative Localization Certificate | 新增 | 相对位姿可观测 Gramian `W_ij`，协方差界 `Σ_ij ⪯ W_ij^{-1}` |
| IP-125 | DPC Differential Positioning Certificate | 新增 | `(𝔅,Δ_LB,A,W,φ_g,Σ_ij,δ_a,null_result)` 可签发/可拒绝 |
| IP-126 | DPI Differentiation Positioning Index | 新增 | `DPI = min_m margin_m · cover · attribution`，引导研究搜索 |
| 升级 | JTC→双钥匙 | 升级 | 部署门禁 `J.ok ∧ DPC.ok`；`δ_a` 受定义 127 约束 |
| 升级 | J (IP-118) | 升级 | 并入 `Σ_ij` 与定位-动作耦合项 |

## 1. 符号体系增量（新增定义 121–128）

| 符号 | 含义 |
|---|---|
| `𝔅 = {b_1,…,b_k}` | 基线包络（含至少一个强基线） |
| `D = (𝔅,m,Δ,A,W)` | 差异化主张：基线/度量/差值/归因/见证 |
| `Δ_LB(α)` | 同源随机数配对差分的单侧置信下界 |
| `σ_Δ²` | 配对差方差，`= σ_M²+σ_b²-2Cov` |
| `φ_g(d), Φ_g` | Gazebo 逐维保真度与木桶复合保真度 |
| `𝔇_claim` | 差分主张所依赖的物理维度子集 |
| `T_ij, Σ_ij` | 相对位姿及其协方差上界 |
| `W_ij, obs_rel` | 相对可观测 Gramian 与其最小特征值 |
| `δ_loc` | 相对定位误差预算 |
| `c_loc` | `γ_ce` 在 `A_core` 上的 Lipschitz 常数 |
| `δ_a` | 云边动作对齐容差（受定义 127 硬约束） |
| `null_result` | 诚实零结果：`insufficient_power` / `not_differentiated` |
| `DPI` | 差异化定位指数 |

## 2. 关键算法 伪代码

### IP-121 BEA（Baseline Envelope Audit）

```python
def audit_baseline_envelope(baselines, method, domains):
    cover = {}
    for b in baselines:
        if dominated(b, method):
            return ('reject', 'weak_baseline', b)
        if not pareto_near_front(b, domains):
            return ('reject', 'straw_man', b)
        cover[b.id] = domain_coverage(b)
    return ('ok', cover)
```

### IP-122 GIP（Gazebo Instrument Profile）

```python
def gazebo_instrument_profile(gazebo, real_logs, dims=PHYS_DIMS):
    phi = {}
    for d in dims:
        sim_dist  = gazebo.sweep(d)                # 受控扫参
        real_dist = empirical(real_logs, d)
        phi[d]    = distribution_agreement(sim_dist, real_dist)
    return FidelityProfile(phi, Phi=min(phi.values()))   # 木桶原则
```

### IP-123 CRD（Common-Random-number Differential test）

```python
def crn_differential_test(method, baseline, instances, omega_stream, alpha, delta_min):
    diffs = []
    for inst, omega in paired(instances, omega_stream):    # 共享初始位姿/扰动/噪声种子
        diffs.append(evaluate(method, inst, omega) - evaluate(baseline, inst, omega))
    d_hat = mean(diffs)
    sigma = robust_std(diffs)                              # MAD/Huber
    n     = len(diffs)
    d_lb  = d_hat - sigma * sqrt(2 * log(1 / alpha) / n)
    if d_lb >= delta_min:
        return ('differentiated', d_lb, diffs)
    if paired_power(diffs, delta_min, alpha) < 0.8:
        return ('null_insufficient_power', d_lb, diffs)
    return ('not_differentiated', d_lb, diffs)
```

### IP-124 RLC（Relative Localization Certificate）

```python
def relative_localization_certificate(obs_i, obs_j, u, R_eta, obs_min, delta_loc):
    W = empirical_relative_gramian(obs_i, obs_j, u, R_eta)  # Σ_t Φ_t^T R_eta^{-1} Φ_t
    obs_rel = min_eig(W)
    if obs_rel < obs_min:
        return ('reject', 'insufficient_excitation', obs_rel)   # 共线/静止退化
    Sigma_ij = inv(W)                                       # Σ_ij ⪯ W^{-1}
    if spectral_norm_sqrt(Sigma_ij) > delta_loc:
        return ('reject', 'localization_budget', Sigma_ij)
    return ('ok', Sigma_ij, obs_rel)
```

### IP-125 DPC（Differential Positioning Certificate）

```python
def differential_positioning_certificate(M, B, metrics, instances, phi_g, Sigma_ij,
                                         gamma_lip, v_max, tau_loop, b_sys,
                                         delta_min, delta_attr, delta_a, alpha):
    ok, cover = audit_baseline_envelope(B, M, metrics)
    if not ok:
        return ('reject', 'straw_man_envelope')

    claims = []
    for m in preregistered(metrics):                   # 度量锁：禁止事后挑选
        worst_lb = float('inf')
        for base in B:
            res = crn_differential_test(M, base, instances, CRN, alpha, delta_min)
            if res[0] != 'differentiated':
                return ('null', m, res[0])             # 诚实零结果，不换指标
            worst_lb = min(worst_lb, res[1])
        W = find_discriminating_witnesses(M, B, m)     # 见证集非空
        if not W:
            return ('reject', 'no_witness', m)
        if ablation_delta(M, m) < delta_attr:          # 机制归因
            return ('reject', 'not_attributable', m)
        claims.append(DiffClaim(m, worst_lb, W))

    lhs = delta_a
    rhs = gamma_lip * spectral_norm_sqrt(Sigma_ij) + v_max * tau_loop + b_sys
    if lhs < rhs:                                      # 定义 127 硬约束
        return ('reject', 'alignment_localization_violation', lhs, rhs)

    for d in claimed_dims(metrics):
        if phi_g[d] < PHI_MIN:
            return ('reject', 'fidelity_underclaim', d)  # 绝对证据被高估

    return ('ok', DPC(claims, cover, phi_g, Sigma_ij, delta_a))
```

### IP-126 DIT + DPI（区分性实例搜索与研究搜索）

```python
def discriminating_instance_test(M, B, m, budget):
    # 主动搜索使 max_b m(b) - m(M) 最小（最难区分）的实例
    frontier = generate_hard_instances(M, B, m, budget)
    W = [x for x in frontier if all(m_eval(M, x) > m_eval(b, x) for b in B)]
    return W            # 空集 -> 触发 no_witness / null_result

def differentiation_index(candidates, B, power_fn):
    scored = []
    for cand in candidates:
        margins = [power_fn(cand, b) for b in B]        # 标准化差异下界
        dpi = min(margins) * coverage_bonus(B) * attribution_strength(cand)
        scored.append((dpi, cand))
    return max(scored)    # 最弱维度最优，而非平均领先
```

## 3. 复杂度与正确性

| 组件 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|
| BEA | O(|𝔅|·|𝔇|·|metric|) | O(|𝔅|) | 基线近 Pareto 前沿，无稻草人 |
| GIP | O(|𝔇_phys|·N_real) | O(|𝔇_phys|) | 逐维受控辨识，木桶短板 |
| CRD | O(N·(|M|+|b|)) | O(N) | 共享随机源可交换，配对差 sub-Gaussian |
| RLC | O(T·n²) | O(n²) | 持续激励，`W_ij` 满秩，`Σ_ij ⪯ W^{-1}` |
| DPC | O(|𝔅|·N·|m| + |m|·|Abl|) | O(N) | 度量预注册，诚实零结果，双钥匙门禁 |
| DPI | O(|C|·|𝔅|) | O(|C|) | 最弱维度 min 聚合，反平均掩盖 |

**正确性定理（Differential Positioning Soundness）**
假设第 54 轮 (A22)–(A28) 成立；新增
**(A29)** 配对差 `σ_Δ`-sub-Gaussian 且共享随机源在实例间可交换；
**(A30)** 对 `d∈𝔇_claim`，`φ_g(d) ≥ φ_min`；
**(A31)** `obs_rel ≥ obs_min` 且定义 127 不等式成立。
则任一经 `DPC` 签发的差异化主张，其误报率满足
```
P(false differentiation) ≤ α + P(Φ_g < φ_min) + P(δ_a overrun)
```
并与第 54 轮 `J` 并联后：
```
P_success = P(J.ok ∧ DPC.ok)
          ≥ 1 - Σ_d(1-ρ_min(d)) - β_E - P(δ_a > Θ_a) - P(false differentiation)
```
**要点**：`J` 与 `DPC` 正交——前者是"能跑"的必要条件，后者是"值得跑/构成创新"的必要条件；二者任一不成立即拒绝部署或拒绝发表。

## 4. 集成更新：v16++ → v16++++ 体系

```
根信任 + 能力格
│
├─ L0   分布式底座与执行边 (GPC/SEN/TBC)
├─ L0.5 任务迁移与仿真证据 (TIX,XFR,CRC,SFE,FDR,RAB,DST,SBC)
├─ L0.5+  鲁棒性层 (TRO,RXC,RCO,REX,RTA,TRC,RUR)          ← v53
├─ L0.5++ 动作-协同层 (ACS,SCOM,CEC,AEC,JTC)              ← v54
├─ L0.5+++ 差异化定位层 (BEA,GIP,CRD,RLC,DPC,DPI,DIT)     ← v55 新增
│     └─ 双钥匙门禁：J.ok ∧ DPC.ok，δ_a 由定义 127 硬约束
├─ L1 几何感知
├─ L2 任务/上下文/记忆/语音
...
└─ L6 原型证伪/XFER/LFF/IXD
```

**JCPS 输出扩展**为：
`(v,a,m,q,ι,κ,g,λ,τ,σ,ρ,Explain,RUR_state,α_S,A_cert,γ_ce,δ_a, Σ_ij, obs_rel, φ_g, Δ_LB, W, DPI)`

其中新增：
- `Σ_ij`、`obs_rel` 相对定位协方差与可观测性；
- `φ_g` Gazebo 仪器保真度；
- `Δ_LB` 差异化置信下界；
- `W` 区分性见证集；
- `DPI` 差异化定位指数；
- `null_result` 诚实零结果登记。

## 5. 本轮最大风险

**一句话**：把"差异化定位"升格为可判定证书并让 Gazebo 以同源随机数充当差分放大器，确实能把"增量集成"的指责转化为可证伪的机制性主张，但其 soundness **同时依赖基线包络的真实性、配对随机源的可交换性、以及相对定位-动作对齐耦合不等式的成立**；一旦基线被无意识地选成稻草人、或域随机化破坏 CRN 配对、或相对定位在弱激励下协方差爆炸而 `δ_a` 被悄悄调大，我们就会得到"统计上显著但机制上虚假"的差异化结论，故必须以 **BEA 反稻草人 + 分块 CRN 交换性检验 + 定义 127 硬约束** 三重护栏，宁可诚实地报告零结果，也绝不把"仿真里赢了弱基线"当作创新已成立。
<!-- ARTIFACT:END -->
