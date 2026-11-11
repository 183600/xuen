# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 53 轮（承接第 52 轮 v16 GroundEdge-GenSim；灵感循环第 4 轮；本轮灵感：「鲁棒性层级化」×「反向解释」）

> 灵感循环第 4 轮聚焦 **「鲁棒性层级化」×「反向解释」**。第 52 轮已把证书从"单任务真理"升级为"带适用域、迁移风险、仿真保真的可判定证书"；但它仍隐有 **H18：鲁棒性是整体量词、不是任务层面的可组合资源**——不同任务/策略/组合的鲁棒性如何从部件中合成仍是黑箱；**H19：仿真只能否决，不能解释为何失败**——当下只有"通过"/"不通过"的单向信号，缺乏反向解释（failure explanation）导致局部改进动力弱。

## 0. 直觉与动机

**灵感 1（鲁棒性层级化 → 把鲁棒性从"黑盒容差"变为"可组合并标量化的资源"）**

直觉：v16 的 `δ_tr(T)` 把迁移风险压缩成一个标量，掩盖了**鲁棒性在不同维度上的脆弱结构**：某个任务在关节力矩上鲁棒，在刚性变形上却脆弱；某个技能组合在抓握姿态上稳，在转换瞬间因共地变化失效。若鲁棒性是不可拆解的整体，复用时只能靠经验；若能**层级化、可组件化**，就能在任务族里做"鲁棒拼图"：取 A 技能在 `d_A` 维度的鲁棒性 `ρ_A(d_A)`，取 B 技能在 `d_B` 的鲁棒性 `ρ_B(d_B)`，组合时得到交叉风险 `ρ_AB(d_A,d_B) = max(ρ_A(d_A) + Δ_AB, ρ_B(d_B))` 或更复杂的耦合函数。这样，**迁移的每一步都能给出可解释的鲁棒性缺口**，而不是只说"风险太大/太小"。

**灵感 2（反向解释 → 仿真不是"找反例器"，而是"教科书"）**

直觉：当前 v16 的 FDR 只做单向判决——仿真找到反例就收缩域/拒绝，听说了知道。用户和调度器想知道的是：**为什么失败？在哪几条支撑关系上脆弱？该怎么改造技能、调参或约束？**这需要 **反向解释（reverse explanation）**：从仿真的失效轨迹 `π_fail` 挖出**因果链**（哪个接触、哪个假设、哪个参数突破了安全界），并映射回任务描述符与技能声明。这样，迁移/组合/蒸馏的每一步都不是盲目试用/错，用仿真的"失败案例"直接当作**改进的蓝图**。

**灵感 3（层级化鲁棒性的形式化 → 鲁棒性维度格 + 可传递的鲁棒性证书）**

直觉：把鲁棒性抽象为 **维度化谓词**：每个技能/任务都有 **鲁棒性谱 `ρ = {ρ_1, ρ_2, ..., ρ_k}`**，对应动力学/几何/感知/控制/K 的不同维度。不同维度的鲁棒性可以独立分析，也可以在组合时按耦合矩阵叠加。**鲁棒性证书 `R = (ρ, D_R, ε_B)`** 声明：在适用域 `D_R` 内，维度谱 `ρ` 以容差 `ε_B` 成立；跨域迁移时，新的 `ρ'` 需要计算 **耦合修正 `γ(ρ, φ)`**。这样，**鲁棒性不再是整体的噤声声誉，而是可以检索、组合、传递的结构化资源**。

**灵感 4（从仿真到技能：反向仿真解释器）**

直觉：设想一个 **反向解释器 `Explain(sim_result)`**：输入仿真器跑出的失败轨迹，输出 **失败根因分布**（P(因果根因 = c_i)）和 **局部修正建议**（Δ 参数 / 约束 / 技能子模块）。这个解释器不是神经网络的黑箱，而是基于 **结构化仿真模型 + 形式语义学**：把仿真过程切片、建模、抽象成逻辑命题。这样，**每一次仿真的失败都成为技能的进化反馈**，蒸馏过程从"挑最好的"变成"把失败的教训写进新技能"。

**灵感 5（层级化 + 反向解释 的耦合 → 可解释的鲁棒性金字塔）**

直觉：构筑一个 **可解释的鲁棒性金字塔**：
- **底层**：物理/动力学鲁棒性（刚体、接触、摩擦）——用最保守的数值/形式化界；
- **中层**：控制/规划鲁棒性（HVAC、PSC、ACC）——从仿真反向解释提取关键约束；
- **顶层**：系统级/任务鲁棒性（CAR、SHIELD、CBG+）——由下而上拼合、校准。
每层都有 **可判定的鲁棒性谓词** 与 **反向解释机制**；跨层迁移时，需要 **跨层鲁棒性传递证书**。这把 v16 从"全局风险预算"提升为**可结构化、可解释、可传递的鲁棒性体系**。

## 1. 形式化定义（增量：定义 107–114）

**定义 107（鲁棒性维度与谱）**
鲁棒性维度 `d ∈ 𝔇_ρ = {dynamics, geometry, force, friction, cable, compliance, perception, control, latency, human, ...}`。技能 `S` 的**鲁棒性谱** `ρ_S : 𝔇_ρ → [0,1]`，其中 `ρ_S(d) = 1` 表示在维度 `d` 上具备完美鲁棒性，`ρ_S(d) = 0` 表示完全脆弱。**鲁棒性是局部的、条件化的**：`ρ_S(d)(θ)` 随参数向量 `θ` 变化。

**定义 108（鲁棒性证书）**
鲁棒性证书 `R = (ρ, D_R, ε_B, evidence)`：
- `ρ` 为鲁棒性谱；
- `D_R ⊆ ℱ` 为**鲁棒性适用域**，由谓词 `dom_R : 𝔇 → {in,out,unknown}` 判定；
- `ε_B` 为**容差包**，说明在域内 `ρ` 的实际值可能出现的下游漂移；
- `evidence` 为依据：E0=仿真反例；E1=仿真校准+锚点；E2=真实认证。
**迁移时**：若 `φ` 为任务态射，需计算 `ρ' = ρ ∘ φ` 并给出 **耦合修正 `γ(ρ, φ)`**；若 `|ρ' - ρ| > ε_B` 或 `dom_R(φ(T)) = out`，则迁移失效。

**定义 109（鲁棒性耦合修正）**
给定技能族 `{S_i}` 及其跨维度耦合矩阵 `K ∈ [0,1]^{k×k}`（`K_{ij}` 表示维度 `j` 的脆弱性如何放大/抑制维度 `i`），组合技能 `S_⊗` 的鲁棒性谱：
```
ρ_{S⊗}(d_i) = min_{j} [ ρ_{S_i}(d_j) / (1 + K_{ij}·(1 - ρ_{S_i}(d_j))) ] · ∏_c f_c(adjacent_d)
```
其中 `f_c` 为组合约束的折扣因子，`adjacent_d` 为相邻维度的鲁棒性。**组合时必须给出新的 `γ` 或接受 `α_int` 风险**。

**定义 110（反向仿真解释器）**
反向解释器 `Explain : (sim_result, model) → (RootCauseSet, Confidence, Suggestion)`：
- **输入**：仿真结果 `sim_result = (π, failure_mode, violation_set)`；
- **模型**：结构化仿真模型 `ℳ = (states, actions, assumptions, constraints)`；
- **输出**：
  - `RootCauseSet ⊆ assumptions` 为**概率加权的根因集合**；
  - `Confidence ∈ [0,1]` 为解释可信度；
  - `Suggestion` 为**局部修正动作**（参数调小/大、约束 tighten、子技能 replace）。
解释器必须满足 **结构一致性**：根因必须可追溯到仿真轨迹的具体时刻、假设、约束。

**定义 111（鲁棒性金字塔）**
鲁棒性金字塔 `𝕃 = (𝕃_0, 𝕃_1, ..., 𝕃_h)`：
- **底层 `𝕃_0`**：物理/动力学鲁棒性，用最保守的数值/形式化界界定；
- **中层 `𝕃_i (i≥1)`**：控制/规划/系统鲁棒性，由 `Explain` 从下层反馈构造；
- **顶层 `𝕃_h`**：任务/策略鲁棒性，由自上而下的约束传播 + 下而上的校准闭合。
**跨层传递**：`L_i → L_j` 必须通过 **跨层鲁棒性传递证书**，说明 `ρ(L_j)` 相对于 `ρ(L_i)` 的变化界。

**定义 112（可传递鲁棒性迁移证书）**
跨层迁移证书 `TRC = (S_source, L_target, γ, δ_ρ, D_TR, evidence)`：
- `γ` 为**鲁棒性传递函数**，说明如何从源层谱 `ρ_source` 计算目标层谱 `ρ_target`；
- `δ_ρ` 为**鲁棒性迁移间隙**，满足 `|ρ_target - γ(ρ_source)| ≤ δ_ρ`；
- `D_TR` 为**传递适用域**；
- `evidence` 至少 E1。
若 `dom_TR(T) = in` 且 `δ_ρ < THETA_ρ`，则迁移可接受。

**定义 113（反向解释化验锚点）**
反向解释 **锚点集** `A_E = {e_1, ..., e_q}`：每个锚点是 **(场景, 期望根因, 验证方法)** 的三元组。锚点必须**事前预注册**，验证 `Explain` 的根因识别是否覆盖 `failure_mode`。若 `|{e : Explain(sim(e)) = e_root}| / q < 1 - β_E`，则解释器失效，迁移/复用受限。

**定义 114（鲁棒性更新规则）**
给定历史 `H = {T_k, S_k, ρ_k, Explain_k, residual_k}`，**鲁棒性更新规则**：
```
ρ_{new} = (1 - λ) · ρ_{old} + λ · update_rule(H, d_ρ)
```
其中 `λ ∈ (0,1)` 为**学习率**；`update_rule` 可以是 **指数加权** 或 **贝叶斯更新**。更新必须通过 **反向解释化验锚点** 验证，防止**负迁移的鲁棒性泄漏**。

## 2. 关键算法 伪代码

### IP-107 TRO（Robustness Spectrum & Certificate）

```python
def robustness_spectrum(skill, dimensions):
    """计算技能在鲁棒性维度上的谱"""
    rho = {}
    for d in dimensions:
        if d == 'dynamics':
            rho[d] = assess_lyapunov_robustness(skill.dynamics)
        elif d == 'geometry':
            rho[d] = assess_collision_margin(skill.geometry)
        elif d == 'force':
            rho[d] = assess_force_torque_safety(skill.force_model)
        elif d == 'friction':
            rho[d] = assess_sliding_stability(skill.friction_model)
        elif d == 'control':
            rho[d] = assess_control_barrier_robustness(skill.controller)
        else:
            rho[d] = assess_via_sim_benchmarks(skill, d)
    return rho

def domain_check_robust(R, d):
    """鲁棒性域判定：unknown→out，fail-closed"""
    if R.dom_predicate(d) == 'unknown':
        return 'out'
    return R.dom_predicate(d)

def robust_certificate(rho, domain, epsilon_B, evidence):
    return RobustCert(rho, domain, epsilon_B, evidence)
```

### IP-110 REX（Reverse Explanation Engine）

```python
def explain_failure(sim_result, model):
    """从仿真失败轨迹生成反向解释"""
    π, fail_mode, violations = sim_result
    
    # 1. 构建原因图
    causes = []
    for t, state in enumerate(π):
        for v in violations:
            if violated_at(v, state):
                c = causal_trace(v, state, model)
                causes.append((c.root_cause, c.confidence * time_decay(t, len(π))))
    
    # 2. 聚合 & 归一化
    cause_dist = aggregate_causes(causes)
    
    # 3. 生成修正建议
    suggestions = []
    for c, p in top_k(cause_dist, k=3):
        if c.type == 'parameter':
            suggestions.append(('tighten', c.param, delta=c.violation - margin))
        elif c.type == 'constraint':
            suggestions.append(('add', c.constraint, scope=c.region))
        elif c.type == 'subskill':
            suggestions.append(('replace', c.subskill, alternatives=c.viable_alt))
    
    return Explanation(
        root_causes=sorted(cause_dist, key=lambda x: -x[1]),
        confidence=max(p for _, p in cause_dist),
        suggestions=suggestions
    )
```

### IP-109 RCO（Robustness Coupling & Composition）

```python
def compose_robustness(rho1, rho2, coupling_matrix, constraints):
    """组合技能的鲁棒性耦合计算"""
    rho_new = {}
    
    for d in rho1.keys():
        # 基本保守上界
        rho_new[d] = min(rho1[d], rho2[d])
        
        # 耦合矩阵修正
        for j in rho1.keys():
            if coupling_matrix.get((d, j), 0) > 0:
                coupling_effect = coupling_matrix[(d, j)] * (1 - rho1[j])
                rho_new[d] = max(0, rho_new[d] - coupling_effect)
        
        # 约束折扣
        if d in constraints:
            rho_new[d] *= constraints[d].discount_factor
    
    return rho_new

def coupling_correction(rho_source, coupling_matrix, phi):
    """态射 φ 带来的鲁棒性耦合修正"""
    rho_target = {}
    for d_target in rho_source.keys():
        # 传递函数：基于 φ 在 d_target 维度上的失配
        loss = coupling_mismatch(coupling_matrix, phi, d_target)
        rho_target[d_target] = max(0, rho_source.get(d_target, 0) - loss)
    return rho_target
```

### IP-112 TRC（Transfer Robustness Certificate）

```python
def transfer_robustness_certify(S_source, L_target, phi, delta_ρ_budget):
    """跨层迁移鲁棒性证书生成"""
    rho_source = S_source.robustness_spectrum
    
    # 1. 计算传递函数 γ
    gamma = lambda rho: coupling_correction(rho, COUPLING_MAT, phi)
    
    rho_target = gamma(rho_source)
    
    # 2. 计算迁移间隙 δ_ρ
    delta_ρ = {d: max(0, rho_source[d] - rho_target[d]) for d in rho_source}
    
    # 3. 判定
    if sum(delta_ρ.values()) > delta_ρ_budget:
        return ('reject', 'robustness_budget_exceeded', delta_ρ)
    
    # 4. 生成域与证据
    domain = compute_transfer_domain(S_source, phi, L_target)
    if domain_check_robust(S_source.R, domain) != 'in':
        return ('reject', 'domain_mismatch')
    
    evidence = collect_evidence_for_transfer(S_source, L_target, phi)
    if evidence.level < E1:
        return ('reject', 'insufficient_evidence')
    
    return ('ok', TRC(
        S_source=S_source.id,
        L_target=L_target,
        gamma=gamma,
        delta_ρ=delta_ρ,
        D_TR=domain,
        evidence=evidence
    ))
```

### IP-114 RUR（Robustness Update Rule）

```python
def update_robustness_spectrum(rho_old, H, lambda_lr, explanation_anchors):
    """基于历史数据和反向解释更新鲁棒性谱"""
    rho_new = {}
    
    # 1. 计算每个维度的残差
    for d in rho_old.keys():
        residuals = [residual(Explainer(T, S, rho) for T, S in H if d in S.claimed_dims]
        
        # 2. 贝叶斯更新
        prior = rho_old[d]
        likelihood = exp(-mean(residuals))
        posterior = (1 - lambda_lr) * prior + lambda_lr * likelihood
        
        rho_new[d] = max(0, min(1, posterior))
    
    # 3. 验证解释锚点
    for anchor in explanation_anchors:
        if not validate_explanation(rho_new, anchor):
            # 锚点失败，减缓更新
            rho_new = conservative_blend(rho_old, rho_new, factor=0.5)
            break
    
    return rho_new
```

### IP-108 RXC（Robustness Exchange Protocol）

```python
def robustness_exchange_request(T_new, candidate_certs, graph, constraints):
    """任务新鲜性请求：检查鲁棒性迁移可行性"""
    d_T = interpretable_descriptors(T_new)
    
    # 1. 域判定
    viable_certs = [C for C in candidate_certs 
                   if domain_check_robust(C.R, d_T) == 'in']
    
    # 2. 鲁棒性传递检查
    transfers = []
    for C in viable_certs:
        for phi in possible_morphisms(T_new, C.domain):
            trc = transfer_robustness_certify(C.S, L_TASK, phi, DELTA_RHO_BUDGET)
            if trc[0] == 'ok':
                transfers.append(trc[1])
    
    if not transfers:
        # 3. 生成反向解释建议
        suggestions = []
        for C in candidate_certs:
            failure_pred = predict_robustness_gap(T_new, C, graph)
            if failure_pred:
                exp = explain_failure(failure_pred, SIM_MODEL)
                suggestions.extend(exp.suggestions)
        
        return ('rejected', 'no_suitable_robustness', need_suggestions=suggestions)
    
    return ('ok', transfers, auto_aggregate_constraints(transfers))
```

## 3. 复杂度与正确性

| 组件 | 时间复杂度 | 空间复杂度 | 正确性关键 |
|---|---|---|---|
| TRO | O(|𝔇_ρ|) | O(|𝔇_ρ|) | 维度谱完整、容差包闭合 |
| REX | O(|π|·|violations|) | O(|causes|) | 结构一致性、锚点验证 |
| RCO | O(|𝔇_ρ|²) | O(|𝔇_ρ|²) | 耦合矩阵正确、约束折扣合理 |
| TRC | O(|𝔇_ρ|) | O(|𝔇_ρ|) | 传递函数 γ sound、δ_ρ 预算 |
| RUR | O(|H|·|𝔇_ρ|) | O(|H|) | 锚点验证、负迁移防护 |

**正确性定理（Layerwise Robustness Soundness）**
假设 (A17)–(A21) 承接 v16；
**(A22)** 鲁棒性谱 `ρ` 由结构化仿真模型支持，维度 `d` 的 `ρ(d)` 基于形式语义学或可验证的物理模型；
**(A23)** 耦合矩阵 `K` 由红队测评与跨层实验校准，`γ(ρ, φ)` 在给定 `K` 下单调；
**(A24)** 反向解释器 `Explain` 通过锚点验证，`P(Explain(sim) = true_root) ≥ 1 - β_E`；
**(A25)** 鲁棒性更新规则 conservatively 更新，防止负迁移。
则：`P(∀t≤T: ρ(z(t), d) ≥ ρ_min ∀ d ∈ 𝔇_ρ) ≥ 1 - Σ_d (1 - ρ_min(d)) - α_δ - β_E`。

## 4. 实验设计 E151–E156

| 实验 | 指标 | 目标 |
|---|---|---|
| E151 鲁棒性谱度量 | 各维度 `ρ(d)` 可重复性；K 估计误差 | ρ(d) CI 宽度 ≤ 0.05；K 估计 R² ≥ 0.8 |
| E152 耦合矩阵校准 | 跨维度脆弱性放大率；RCO 预测准确 | `|ρ_composed - ρ_actual| ≤ 0.1`；Pearson r ≥ 0.85 |
| E153 反向解释驱动改进 | Explain 正确率；改进后成功率提升 | 解释正确率 ≥ 90%；改进后成功率 Δ ≥ 15% |
| E154 迁移鲁棒性传递 | TRC 迁移成功率 vs 本地认证 | 迁移成功率 ≥ 80% 本地认证的 90% |
| E155 金字塔层级传递 | 跨层传递 δ_ρ 误差；漂移检测延迟 | δ_ρ 误差 ≤ 0.05；延迟 ≤ τ_shift |
| E156 负迁移防护 | 误用旧 R 的放行次数；回退触发率 | 放行 0 次；回退率 100% 检出负迁移 |

## 5. 风险与缓解

| 风险 | 等级 | 缓解措施 |
|---|---|---|
| 鲁棒性维度划分不完整 | 高 | 动态扩维 + 红队发现 + 元学习发现隐藏维度 |
| 耦合矩阵 K 误估 | 高 | 红队对抗 + 多仿真器交叉 + 实时在线校准 |
| 反向解释器产生误导性根因 | 高 | 多模型投票 + 结构一致性检查 + 锚点验证 |
| 迁移 δ_ρ 超预算 | 高 | 保守传递函数 + 负迁移即拒 + 费用归因 |
| 鲁棒性更新导致漂移 | 中 | 锚点验证 + 保守学习率 λ + 红队监测 |
| 解释器锚点不足 | 中 | 多场景锚点 + 交叉验证 + 持续补充 |
| 金字塔传递信息丢失 | 中 | 跨层映射函数闭合 + 信息保持约束 |
| 维度谱过度稀疏 | 低 | 稀疏正则化 + 维度激活门控 |

## 6. 本轮最大风险

**一句话**：层级化鲁棒性与反向解释将 v16 的"全局风险"拆解为可传递的维度谱，却引入了 **K 耦合矩阵、Explain 解释器、锚点验证三重自指估计**；一旦耦合矩阵误算、解释器对抗欺骗或锚点不足，**鲁棒性的"可传递性"就变成了"可误传播性"**——局部检查均衡，却在真实任务族的维度交叉脆弱处系统性失效，故必须以**跨仿真器校准、红队对抗解释、负迁移绊线+预注册锚点**双重验证，宁可保守维度，绝不把结构化的"安全外衣"当作底层防护。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 53 轮产物 · 创新点清单 v30：GroundEdge-GenSim++（TIX×XFR×CRC×SFE×FDR×RAB×DST×SBC×TRO×REX×RCO×TRC×RUR）

> 承接第 52 轮产物 v29。本轮在 v16 基础上插入 **「层级化鲁棒性」** 与 **「反向解释」** 两大算子：
> - **TRO（Robustness Spectrum）**：把鲁棒性从标量 `δ_tr` 解构为可维度化的谱 `ρ`；
> - **REX（Reverse Explanation Engine）**：从仿真失败生成结构化根因 + 修正建议；
> - **RCO（Robustness Coupling）**：提供耦合矩阵 `K`，实现鲁棒性的可组合标量化；
> - **TRC（Transfer Robustness Certificate）**：跨域/跨层迁移的鲁棒性传递证书；
> - **RUR（Robustness Update Rule）**：贝叶斯式更新鲁棒性谱，防止负迁移。
>
> IP 编号：IP-107~IP-114（共 8 个新增），并升级 IP-51/85/96/45/72 以纳入鲁棒性维度与反向证据。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进 |
|---|---|---|---|
| IP-107 | TRO Robustness Spectrum | 新增 | 维度化鲁棒性谱 `ρ:𝔇_ρ→[0,1]`；域判定 `dom_R`；`unknown=fail-closed` |
| IP-108 | RXC Robustness Exchange | 新增 | 任务鲁棒性查询 → 传递检查 → 反向解释建议 |
| IP-109 | RCO Robustness Coupling | 新增 | 维度耦合矩阵 `K`；组合鲁棒性标量化 `ρ_{S⊗}(d)` |
| IP-110 | REX Reverse Explanation | 新增 | 仿真失败 → 根因分布 + 置信度 + 局部修正建议 |
| IP-111 | RTA Robustness Tower | 新增 | 金字塔结构 `𝕃=(𝕃_0,...,𝕃_h)`；跨层传递证书 |
| IP-112 | TRC Transfer Robustness | 新增 | 跨层鲁棒性传递证书 `TRC=(S, L, γ, δ_ρ, D, E)` |
| IP-113 | REX-A Explanation Anchor | 新增 | 反向解释化验锚点集，验证解释正确率 |
| IP-114 | RUR Robustness Update | 新增 | 贝叶斯/指数更新 `ρ_{new} = (1-λ)·ρ_{old} + λ·update` |

## 1. 符号体系增量（新增定义 107–114）

| 符号 | 含义 |
|---|---|
| `𝔇_ρ` | 鲁棒性维度格：`{dynamics, geometry, force, friction, cable, compliance, perception, control, latency, human}` |
| `ρ_S(d)` | 技能 `S` 在维度 `d` 上的鲁棒性值 `[0,1]` |
| `R = (ρ, D_R, ε_B, evidence)` | 鲁棒性证书：谱、适用域、容差包、证据 |
| `K ∈ [0,1]^{k×k}` | 鲁棒性耦合矩阵：`K_{ij}` 表示 `j` 脆弱性如何放大 `i` |
| `Explain(sim_result)` | 反向解释器：从失败轨迹生成根因分布 + 修正建议 |
| `𝕃 = (𝕃_0,...,𝕃_h)` | 鲁棒性金字塔：从物理到任务的层级结构 |
| `TRC = (S, L, γ, δ_ρ, D, E)` | 跨层鲁棒性传递证书 |
| `A_E = {e_1,...,e_q}` | 反向解释化验锚点集 |
| `ρ_{new}` | 更新后的鲁棒性谱 |
| `λ` | 鲁棒性更新学习率 `(0,1)` |

## 2. 关键算法 伪代码

### IP-107 TRO（Robustness Spectrum & Certificate）

```python
def robustness_spectrum(skill, dimensions=DEFAULT_DIMENSIONS):
    rho = {}
    for d in dimensions:
        if d == 'dynamics':
            rho[d] = assess_lyapunov_robustness(skill.dynamics)
        elif d == 'geometry':
            rho[d] = assess_collision_margin(skill.geometry)
        elif d == 'force':
            rho[d] = assess_force_torque_safety(skill.force_model)
        elif d == 'friction':
            rho[d] = assess_sliding_stability(skill.friction_model)
        elif d == 'control':
            rho[d] = assess_control_barrier_robustness(skill.controller)
        else:
            rho[d] = assess_via_sim_benchmarks(skill, d)
    return rho

def domain_check_robust(R, d):
    if R.dom_predicate(d) == 'unknown':
        return 'out'
    return R.dom_predicate(d)
```

### IP-110 REX（Reverse Explanation Engine）

```python
def explain_failure(sim_result, model):
    π, fail_mode, violations = sim_result
    causes = []
    for t, state in enumerate(π):
        for v in violations:
            if violated_at(v, state):
                c = causal_trace(v, state, model)
                causes.append((c.root_cause, c.confidence * time_decay(t, len(π))))
    
    cause_dist = aggregate_causes(causes)
    suggestions = generate_suggestions(top_k(cause_dist, k=3))
    
    return Explanation(
        root_causes=sorted(cause_dist, key=lambda x: -x[1]),
        confidence=max(p for _, p in cause_dist),
        suggestions=suggestions
    )
```

### IP-109 RCO（Robustness Coupling & Composition）

```python
def compose_robustness(rho1, rho2, coupling_matrix, constraints):
    rho_new = {}
    for d in rho1:
        rho_new[d] = min(rho1[d], rho2[d])
        for j in rho1:
            if coupling_matrix.get((d, j), 0) > 0:
                coupling_effect = coupling_matrix[(d, j)] * (1 - rho1[j])
                rho_new[d] = max(0, rho_new[d] - coupling_effect)
        if d in constraints:
            rho_new[d] *= constraints[d].discount_factor
    return rho_new

def coupling_correction(rho_source, coupling_matrix, phi):
    rho_target = {}
    for d_target in rho_source:
        loss = coupling_mismatch(coupling_matrix, phi, d_target)
        rho_target[d_target] = max(0, rho_source.get(d_target, 0) - loss)
    return rho_target
```

### IP-112 TRC（Transfer Robustness Certificate）

```python
def transfer_robustness_certify(S_source, L_target, phi, delta_ρ_budget):
    rho_source = S_source.robustness_spectrum
    gamma = lambda rho: coupling_correction(rho, COUPLING_MAT, phi)
    rho_target = gamma(rho_source)
    delta_ρ = {d: max(0, rho_source[d] - rho_target[d]) for d in rho_source}
    
    if sum(delta_ρ.values()) > delta_ρ_budget:
        return ('reject', 'robustness_budget_exceeded', delta_ρ)
    
    domain = compute_transfer_domain(S_source, phi, L_target)
    if domain_check_robust(S_source.R, domain) != 'in':
        return ('reject', 'domain_mismatch')
    
    evidence = collect_evidence_for_transfer(S_source, L_target, phi)
    if evidence.level < E1:
        return ('reject', 'insufficient_evidence')
    
    return ('ok', TRC(S_source.id, L_target, gamma, delta_ρ, domain, evidence))
```

### IP-114 RUR（Robustness Update Rule）

```python
def update_robustness_spectrum(rho_old, H, lambda_lr, explanation_anchors):
    rho_new = {}
    for d in rho_old:
        residuals = [evaluate_residual(T, S, rho_old) for T, S in H]
        prior = rho_old[d]
        likelihood = exp(-mean(residuals))
        posterior = (1 - lambda_lr) * prior + lambda_lr * likelihood
        rho_new[d] = max(0, min(1, posterior))
    
    for anchor in explanation_anchors:
        if not validate_explanation(rho_new, anchor):
            rho_new = conservative_blend(rho_old, rho_new, factor=0.5)
            break
    
    return rho_new
```

## 3. 复杂度与正确性

| 组件 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|
| TRO | O(|𝔇_ρ|) | O(|𝔇_ρ|) | 维度谱可观测、容差包闭合 |
| REX | O(|π|·|violations|) | O(|causes|) | 根因结构一致、锚点验证 ≥ 90% |
| RCO | O(|𝔇_ρ|²) | O(|𝔇_ρ|²) | 耦合矩阵单调、组合上界有效 |
| TRC | O(|𝔇_ρ|) | O(|𝔇_ρ|) | 传递函数γ sound、δ_ρ 预算 |
| RUR | O(|H|·|𝔇_ρ|) | O(|H|) | 负迁移防护、锚点闭环 |

**正确性定理（Layerwise & Explainable Robustness Soundness）**
假设 (A17)–(A25) 成立。则：
```
P(∀t≤T: ρ(z(t), d) ≥ ρ_min ∀ d ∈ 𝔇_ρ) ≥ 1 - Σ_d(1-ρ_min(d)) - α_δ - β_E
```
关键：**跨层传递的每一步都有可解释的δ_ρ + 负迁移绊线**；**仿真的每一次否决都有结构化的原因分布**；**更新经过锚点验证，防止负迁移**。

## 4. 集成更新：v16 → v16+ 体系

```
根信任 + 能力格
│
├─ L0 分布式底座与执行边 (v15 GPC/SEN/TBC)
├─ L0.5 任务迁移与仿真证据 (TIX, XFR, CRC, SFE, FDR, RAB, DST, SBC)
├─ L0.5+ 鲁棒性层 (TRO, RXC, RCO, REX, RTA, TRC, REX-A, RUR)  ← 新增
├─ L1 几何感知
├─ L2 任务/上下文/记忆/语音
├─ L2.5 交互共地与共创契约
├─ L3 关节证书/抽象/决策
├─ L3.5 动力可行 (HVC/CRM)
├─ L4 CAR/Shield/CBG+/KDX
├─ L5 DCL/真机/HCI 评测
└─ L6 原型证伪/XFER/LFF/IXD
```

JCPS 输出扩展为：
`(v, a, m, q, ι, κ, g, λ, τ, σ, ρ, Explain, RUR_state)`

其中：
- `ρ`：当前任务的鲁棒性谱；
- `Explain`：最近一次仿真的反向解释；
- `RUR_state`：鲁棒性谱的贝叶斯更新状态。

## 5. 本轮最大风险

**一句话**：层级化鲁棒性让 v16 从"全局风险"变为"可传递的维度谱"，但这套体系的 soundness 现在**三位一体地依赖 K 矩阵精准性、Explain 解释器的因果识别、以及锚点的充分覆盖**；一旦耦合矩阵漏算关键维度、解释器在对抗场景下误判根因，或锚点集在真实任务族边缘不足，**鲁棒性的"可传递性"就退化为"可误传播的幻象"**——局部鲁棒性检查均衡，却在真任务的维度交叉脆弱处系统性失效，故必须以**跨仿真器校准 + 红队对抗解释 + 负迁移绊线 + 预注册锚点**的四重护栏，宁可保守每维，绝不把"可解释的鲁棒性金字塔"当作最终防御。
<!-- ARTIFACT:END -->
