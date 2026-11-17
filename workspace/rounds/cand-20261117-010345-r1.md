# 玄 · 灵感驱动研究循环

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 10 轮（新灵感循环第 1 轮；本轮灵感：「社会规范理解」×「灵巧操作」×「因果推理」）
> **基线**：第 9 轮 MetricVoiceGauge-ACMD（定义 532–539；引理 82–86；实验 E551–E570）。
> 本轮纪律：**规范约束 + 接触灵巧 + 因果归因**。不推倒 v9：AC 分块、MW 契约、ID 蒸馏、v8 的 DA/SPR/Cal 与九不变式全部保留；三个新组件一律以**中立元**接入，失效即严格退回 v9（引理 93），再沿 v9 五级链退回 v8/v7/v6。本轮只做三件事：给"失礼"建模、给"接触"发证书、把"相关归因"升级为"因果归因"。

## 0. 直觉与动机

**灵感 1（社会规范理解 → 规范接地与规范盾）**
直觉：v9 的六层指标只覆盖物理安全、任务、情感，**没有"社会可接受性"**。真实家庭/服务场景的失败常常不是碰撞，而是失礼：侵入个人空间、插话、越序、未经同意递物、持续凝视。核心创新：**规范接地引擎（NormGroundingEngine, NGE）**。把规范写成 deontic-STL 约束 ν=(φ_ν, ψ_ν, κ_ν, ω_ν, θ_ν)；用规范 HMM 估计"此刻该规范是否适用"的信念 b_ν；用 STL 鲁棒度算违规风险；硬规范进入动作屏蔽 A_soc，软/礼仪规范进入奖励。规范不确定时**不硬闯也不僵硬**，而是执行认知恢复动作（停在安全距离、取得注意、询问）。规范参数还能从人类纠正反馈（缩手、皱眉、"借过"）中贝叶斯学习——是"理解"而非硬编码礼貌。

**灵感 2（灵巧操作 → 接触模式技能与接触证书）**
直觉：v9 的块内动作是低维末端位移，抓取只有二元 γ_grasp。灵巧操作是接触丰富、高 DOF、模型误差大的 regime，恰好是 v9 块证书最脆的地方。核心创新：**灵巧技能库（DexterousSkillLibrary, DSL）+ 接触证书（ContactCertifier, CC）**。技能是接触模式混合自动机上的阻抗/力控原语 π=(σ,u,K_p,K_d,f_max,τ_max)；块证书从单一代数扩展为三元组 (Ĉ_safety, Ĉ_contact, Ĉ_norm)；中止不再是"刹停"，而是接触安全不变式 I_c 下的 hold/regrasp/place。灵巧不是外挂一个抓取器，而是把"接触"提升为证书的一等公民。

**灵感 3（因果推理 → 因果世界模型与因果归因）**
直觉：v9 的 ID 用 with/without 消融做归因，但两臂上下文不同、人类意图 H 未观测——这是**相关不是因果**；v9 的前向模型是黑箱 LSTM，其误差在 Δ_dom 大时最大（v9 自己指出的最大风险）。核心创新：**因果世界模型（CausalWorldModel, CWM）+ 因果归因引擎（CausalAttributionEngine, CAE）**。对环境/模块/接触/结果建 SCM，用 do(·) 与后门调整或工具变量估计 ACE；用跨域不变机制（ICP）选出可迁移父集做预测。因果不是又一个模块，而是**直接修补 v9 最大风险**：把"域越陌生、黑箱越错"换成"只依赖跨域不变的因果机制"。

**三者如何统一**
把决策写成**规范约束下的因果灵巧规划**：在硬规范屏蔽 A_soc 内，用因果世界模型做 do(π) 反事实 rollout，选出接触证书与物理证书均有效的灵巧块；归因用因果效应替代相关消融。**规范回答"能不能做"，灵巧回答"怎么做"，因果回答"做了会怎样、为什么有效"**。三者共享同一份块级接口 ζ=(skills, Ĉ_safety, Ĉ_contact, Ĉ_norm, P)，因此不是三个独立补丁，而是一个约束-预测-归因闭环。

## 1. 研究问题（轮次升级版）

- **Q1（规范可执行性）**：如何把开放、歧义、文化相关的社会规范编译为可在线监测的 deontic-STL 约束，并在规范信念不确定时用一个可证明安全的认知恢复动作替代硬闯或僵死？
- **Q2（接触证书可靠性）**：如何让灵巧块在接触模式切换、力/力矩越界与滑移下仍具备与 v9 逐步执行统计等价的安全性？接触安全中止点如何替代导航语义下的"停车点"？
- **Q3（因果可识别与跨域迁移）**：在人类意图 H 未观测、上下文混杂的情况下，如何识别模块/技能的因果贡献，并让世界模型在 Δ_dom 增大时误差不随分布偏移发散？
- **Q4（三环耦合）**：规范盾会不会删掉唯一可行的灵巧技能而制造僵局？规范信念误差与因果模型误差同源（都来自 H）时，安全论证是否还成立？

## 2. 设计原则（在 P10–P12 基础上新增 P13–P15）

**P13 规范接地律（Norm Grounding, NGE）**
规范以 ν=(φ,ψ,κ,ω,θ) 声明；硬规范（κ=hard）定义动作屏蔽 A_soc，软规范与礼仪规范只进奖励；规范适用性用概率信念 b_ν 表示，禁止把"不确定"当成"不适用"。当 A_soc 为空或 b 熵过高时，必须执行预定义的认知恢复动作 a_ask，而不是选择违规动作。

**P14 接触证书律（Contact Certification, CC）**
任何灵巧块必须携带 Ĉ_contact=(f̂_max, τ̂_max, P̂_slip, γ̂_min, ĉ_mode)；只有全分量在安全界内且存在接触安全中止点 p∈P^c 才可执行。中止语义从"减速停驻"推广为"保持力闭合的 hold/regrasp/place"，接触模式切换必须由触觉后验确认。

**P15 因果归因律（Causal Attribution, CAE/CWM）**
归因与预测默认走因果量：ACE_m=E[Y|do(A_m=1)]−E[Y|do(A_m=0)]，用后门调整；H 不可观测时用安全上下文中的随机化激活作工具变量，并报告敏感性界。世界模型优先使用跨域不变父集 S*，禁止用随域漂移的相关特征做长时预测。

## 3. 与基线的接口（如何退化）

- NGE 失效 ⇒ 注入规范中立元 v^⊥=**allow-all**（b_ν≡0、A_soc=A、R_norm≡0），行为等价 v9；
- DSL/CC 失效 ⇒ 退回 v9 低维动作块与二元 γ_grasp，接触证书退化为 v9 抓取判据，等价 v9；
- CWM/CAE 失效 ⇒ 退回 v9 黑箱 F̂ 与相关消融 c_m，等价 v9；
- 三者全失效 ⇒ MetricVoiceGauge-ACMD v9，再按 v9 五级链退回 v8/v7/v6；
- **安全继承**：物理安全证书始终是合取项。规范盾只能删候选、CWM 只能重排序，新模块不能绕过任何 v9 适用证书（引理 95）。

## 4. 预期贡献

1. **规范接地框架**：deontic-STL + 规范 HMM 信念 + 硬规范盾 + 认知恢复 + 人类反馈贝叶斯学习，把"社会规范理解"变成可监测、可退化、可证明不僵死的在线组件；
2. **接触证书与灵巧中止**：把接触力/滑移/抓取质量提升为块证书的一等分量，并用接触安全不变式定义灵巧中止，覆盖 v9 完全未建模的接触安全性；
3. **因果归因与世界模型**：用 do(·)+后门/IV+ICP 替代相关消融与黑箱预测，直接缓解 v9 的"域越陌生预测越错"最大风险；
4. **三环统一的规范-因果灵巧规划**：E571–E588 覆盖规范接地、灵巧抓取/在手操作、因果归因真实性、跨域迁移、规范僵局与端到端任务。

## 5. 本轮最大风险

**一句话**：规范信念 b_ν 与因果模型共享同一个未观测混杂 H（人类真实意图），一旦 H 使两者同时出错，系统会以高置信度把"该出手时不出手"解释成"规范要求等待"、把虚假相关当成因果效应，即**自信地礼貌且因果错误**。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 10 轮产物 · 创新点清单 v10：**MetricVoiceGauge-NCD**（Metric Voice Gauge with Norm Grounding, Contact Dexterity & Causal Attribution）

> 背景：第 9 轮 MetricVoiceGauge-ACMD（定义 532–539；引理 82–86；实验 E551–E570），其基线为第 8 轮 MetricVoiceGauge-DA-SPR-Cal（定义 493–531；引理 69–81）。
> 本轮灵感：「社会规范理解」×「灵巧操作」×「因果推理」
> **继承纪律**：MetricVoiceGauge 九不变式（CVC-闭环、SpatialCert、RT-CVC、FaultCert、PrimitiveGraph、严格退化链、OTL、GCT、ER）全部保留；v9 的 AC/MW/ID 与 v8 的 DA-ML/SPR/Cal 原样保留。三个新组件均为**可选增强**：任一不可用 ⇒ 注入中立元，严格等价退回 v9（引理 93），再沿 v9 链退回 v8/v7/v6。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进（相对 MetricVoiceGauge-ACMD v9） |
|---|---|---|---|
| IP-340–356 | v9 全部模块 | 继承 | 语义不变；AC 的前向模型端口在 CWM 可用时改由 CWM 供数 |
| IP-354 | ActionChunkCertifier | 集成升级 | 块证书由单一代数升级为 (Ĉ_safety, Ĉ_contact, Ĉ_norm, P) 四元组；中止点分导航/接触两类 |
| IP-357 | NormGroundingEngine (NGE) | 新增核心模块 | deontic-STL 规范 ν=(φ,ψ,κ,ω,θ)；规范 HMM 信念 b_ν；硬规范盾 A_soc；认知恢复 a_ask；人类反馈贝叶斯学习 |
| IP-358 | DexterousSkillLibrary (DSL) | 新增核心模块 | 接触模式混合自动机上的阻抗/力控技能 π=(σ,u,K_p,K_d,f_max,τ_max,pre,post)；与 v9 原语兼容 |
| IP-359 | ContactCertifier (CC) | 新增核心模块 | 力/力矩/滑移/抓取质量/模式置信五元证书；接触安全中止与 hold/regrasp/place |
| IP-360 | CausalWorldModel (CWM) | 新增核心模块 | 因子化 SCM + ICP 不变父集 S*；替换 v9 黑箱 F̂ 做 do(π) 反事实 rollout |
| IP-361 | CausalAttributionEngine (CAE) | 新增核心模块 | do(·)+后门调整/工具变量的 ACE，替代 v9 相关消融 c_m，供 ID 使用 |
| IP-362 | NormativeCausalPlanner (NCP) | 新增核心模块 | 在 A_soc 内用 CWM 做反事实评分的统一块规划器；无可行块时转 a_ask |

**退化链声明（v10 契约化九级，前三级为本轮新增）：**
- Level-0：NGE + DSL/CC + CWM/CAE 全激活，MetricVoiceGauge-NCD；
- Level-1：CWM/CAE 失效 ⇒ 预测退回 v9 黑箱 F̂、归因退回相关消融 c_m，**等价 v9 推理路径**；
- Level-2：DSL/CC 失效 ⇒ 技能集退回 v9 低维原语，接触证书退化为 γ_grasp 判据，**等价 v9 操作路径**；
- Level-3：NGE 失效 ⇒ 注入 allow-all 规范中立元（b≡0、A_soc=A、R_norm≡0），**等价 v9 行为**；
- Level-4：AC 失效 ⇒ K_eff←1，逐步执行，等价 v8 决策粒度；
- Level-5：MW 失效 ⇒ 切换 v8 手写网关代码路径，等价 v8 集成方式；
- Level-6：ID 失效 ⇒ 全模块 active、归因冻结，等价 v8；
- Level-7：v8 的 DA/SPR/Cal 任一失效 ⇒ 中立元注入（Δ_dom≡0 / risk_SLAM≡0 / sensor_weight≡1），等价 v7；
- Level-8：全失效 ⇒ 完整退回 v7，再退回 v6。

前三级作用于**互不相交的端口**（规范评分端口、技能集端口、预测/归因端口），其组合可交换至调度顺序；因此任意子集失效都落到 v9 的一个明确退化点，不存在"半失效"的灰色行为。

## 1. 符号体系增量（定义 540–553）

| 符号 | 含义 |
|---|---|
| ν=(φ_ν,ψ_ν,κ_ν,ω_ν,θ_ν) | 社会规范：适用谓词、deontic-STL 约束、类别（hard/soft/etiquette）、严重度权重、适用阈值 |
| b_ν(t) ∈ [0,1] | 规范信念：t 时刻 φ_ν 成立的后验概率 |
| ρ_ν(ξ) | deontic-STL 鲁棒度（正=满足，负=违反） |
| R_ν(a^{1:K}\|b_t) | 期望违规风险 |
| A_soc(b_t) | 硬规范屏蔽后的可行动作/技能块集合 |
| a_ask | 认知恢复动作（安全距离停驻、取得注意、询问/观察、escalate） |
| f_t | 人类纠正反馈信号（缩手、皱眉、侧身、"借过"、注视转移） |
| π=(σ,u,K_p,K_d,f_max,τ_max,pre,post) | 灵巧技能：接触模式调度、控制律与阻抗增益、力/力矩上限、前后置条件 |
| Σ={free,approach,contact,grasp,inhand,release} | 接触模式集 |
| I_c | 接触安全不变式（力闭合 + 抓取质量 + 无滑移 + 模式确认） |
| Ĉ_c=(f̂_max,τ̂_max,P̂_slip,γ̂_min,ĉ_mode) | 接触证书 |
| P^c | 接触安全中止点集 |
| M=⟨V,U,F,P(U)⟩ | 结构因果模型；V=(X,Z,H,A,C,Y) |
| H | 未观测混杂：人类真实意图/规范偏好 |
| Z | 可观测混杂：场景难度、物体质量、人的性格标签等 |
| W | 工具变量：安全上下文中的随机化模块激活/技能选择 |
| ACE_m | 模块/技能 m 的平均因果效应 |
| c_m^do(t) | 因果贡献（替代 v9 的 c_m(t)） |
| S* | 跨域不变因果父集（ICP 输出） |
| U_e | 环境/域集合；Δ_dom 为 v9 域偏移量 |

**定义 540（社会规范 Social Norm）** 一条规范是一个五元组 ν=(φ_ν,ψ_ν,κ_ν,ω_ν,θ_ν)。φ_ν 是定义在信念状态（场景图 G_t、人体状态 H_t、任务上下文）上的适用谓词；ψ_ν 是 deontic-STL 片段公式：
```
ψ ::= □_[0,K](g(x) ≥ 0) | ◇_[0,K](g(x) ≥ 0) | ψ₁ U_[a,b] ψ₂ | ψ₁ ∧ ψ₂
```
其中 g 是轨迹信号（个人空间距离、语音重叠、朝向、递物接受度等）。κ_ν∈{hard,soft,etiquette}；ω_ν>0 为严重度；θ_ν 为适用阈值。硬规范典型例：`□(dist(robot, human) ≥ d_personal)`；软规范：`◇_[0,2s](handover_accepted)`；礼仪规范：`□(speech_overlap = 0)`。

**定义 541（规范信念 Norm Belief）** b_ν(t)=P(φ_ν|o_{1:t})，由每规范一个 HMM 前向更新：b_ν(t)=τ_ν(b_ν(t−1),o_t)。规范上下文状态 q_t∈Q_ν（如 approach→greet→converse→handover→depart）由人类注视、手势、语音与距离驱动。b_ν 需在线校准，校准误差记 δ_cal。

**定义 542（规范风险 Norm Risk）** 对候选块轨迹 ξ=a^{1:K}：
```
ρ_ν(ξ) = STL 鲁棒度(ψ_ν, ξ)
R_ν(ξ|b_t) = b_ν(t) · σ(−ρ_ν(ξ)/s_ν)
```
σ 为 logistic，s_ν 为尺度。ρ_ν<0 表示违反；R_ν 是归一化期望违规风险。

**定义 543（规范盾 Norm Shield）** 给定硬规范集合 N_H={ν:κ_ν=hard}：
```
A_soc(b_t) = { ξ : ∀ν∈N_H, b_ν(t) ≥ θ_ν ⇒ R_ν(ξ|b_t) ≤ ε_ν }
```
软/礼仪规范不进入 A_soc，进入奖励：R_norm(ξ)=−Σ_{κ≠hard} ω_ν R_ν(ξ|b_t)。

**定义 544（认知恢复动作 Epistemic Recovery）** a_ask 是一个复合安全动作：减速至 d_social≥d_personal 处停驻 → 朝向人类并取得注意 → 发出规范询问/观察等待 → 若 T_ask 内仍高熵则 escalate 到人类确认。a_ask 由构造满足所有硬规范（不停入个人空间、不打断、不接触）。

**定义 545（规范反馈学习 Norm Feedback Update）** 把人类反馈 f_t 视为潜变量 θ_ν（规范参数）的带噪观测，后验 P(θ_ν|f_{1:t})∝P(θ_ν)Π_i P(f_i|θ_ν,a_i)。机器人安全上下文中的随机化动作提供 do(a_i) 变异，使规范偏好的效应可识别（与定义 550 的工具变量共用机制）。

**定义 546（灵巧技能与接触模式自动机 Dexterous Skill）** 技能 π 是在接触模式混合自动机上运行的原语：σ:[0,T_π]→Σ 为模式调度，u 为阻抗/力控律，K_p/K_d 为刚度/阻尼，f_max/τ_max 为力/力矩硬上限，pre/post 为模式相关前后置条件。模式切换由触觉后验 ĉ_mode 触发；不允许在未确认接触时进入 grasp/inhand。

**定义 547（接触证书 Contact Certificate）** 由接触模型与触觉预测：
```
Ĉ_c = ( max_k ‖f_k‖ + β_f, max_k ‖τ_k‖ + β_τ,
        max_k P_slip,k + β_s, min_k γ_k − β_g, min_k ĉ_mode,k )
```
有效 ⇔ f̂_max≤f_max ∧ τ̂_max≤τ_max ∧ P̂_slip≤ε_slip ∧ γ̂_min≥γ_grasp_min ∧ ĉ_mode≥1−δ_mode。β_f,β_τ,β_s,β_g 为接触模型误差余量，由 E579 标定。

**定义 548（接触安全中止 Contact-Safe Abort）** 中止点 p∈P^c 满足接触安全不变式 I_c(p)：存在从 p 开始的 hold/regrasp/place 序列，使
```
Σ_i f_i = −m g（力闭合） ∧ γ_p ≥ γ_grasp_min ∧ P_slip,p ≤ ε_slip ∧ 模式后验 ≥ 1−δ_mode
```
且序列结束于释放或稳定放置。导航语义的停车不变式 d_stop（定义 534）是 I_c 在 free 模式下的特例。

**定义 549（结构因果模型 SCM）** M=⟨V,U,F,P(U)⟩，V=(X,Z,H,A,C,Y)：X 环境/物体、Z 可观测混杂、H 未观测人类意图/规范偏好、A 模块或技能激活变量、C 接触模式、Y 结果向量（任务进展、物理安全余量、规范违规量）。干预 do(A_m=a) 替换 A_m 的结构方程；反事实 Y_{do(a)} 由修正后的 M 前向计算。

**定义 550（因果效应与识别 Causal Effect）** ACE_m=E[Y|do(A_m=1)]−E[Y|do(A_m=0)]。若 Z 对 (A_m,Y) 满足后门准则，则
```
ACE_m = Σ_z ( E[Y|A_m=1,Z=z] − E[Y|A_m=0,Z=z] ) P(z)
```
若 H 不可观测但 W 满足工具变量条件（相关性 W↛Y 除经 A；排他性 W⊥Y|do(A),Z；单调性），用 IV 估计 ACE_m。二者都不满足时，报告敏感性界 |ACE_obs−ACE|≤B_Γ(Γ)。

**定义 551（不变因果机制与因果世界模型 Invariant Causal Model）** 在环境集 U_e 上，若机制 P(Y|do(a),pa(Y)) 对 e∈U_e 不变，则 S* 为 ICP 选出的稳定父集。CWM 只用 S* 做 rollout：
```
F̂_causal(s,a^{1:K}) = E_{M̂}[Y_{1:K}|do(a^{1:K}), X_{S*}, Z]
```
并输出认知不确定性 u_c。S* 之外的域敏感特征不得进入长时预测，只允许进入一步观测修正。

**定义 552（规范-因果灵巧块目标 Normative-Causal Objective）** 对候选 ζ=(π^{1:K},Ĉ_safety,Ĉ_contact,Ĉ_norm,P)：
```
J(ζ|s,b) = E_{M̂}[ Σ_{k≤K} γ^k R_task(s_k,π_k) − Σ_{κ≠hard} ω_ν R_ν(ξ|b) ]
subject to  Ĉ_safety valid（v9 定义 533/534）
          ∧ Ĉ_contact valid（定义 547）
          ∧ ζ ∈ A_soc(b)（定义 543）
          ∧ u_c ≤ ε_u（认知不确定性预算）
```
ζ*=argmax J；若可行集为空，返回 a_ask。

**定义 553（v10 中立元表 Neutral-Element Table）**

| 新组件 | v^⊥ | 等价退化点 |
|---|---|---|
| NGE 规范信念/盾 | b_ν≡0；A_soc=A；R_norm≡0；a_ask 不触发 | Level-3（v9） |
| DSL 技能集 | Π←Π_v9（低维末端原语） | Level-2（v9） |
| CC 接触证书 | 仅保留 γ_grasp（v9 判据），其余分量恒真 | Level-2（v9） |
| CWM 前向模型 | F̂←F̂_v9（黑箱 LSTM-MPC） | Level-1（v9） |
| CAE 归因 | c_m^do←c_m（v9 相关消融） | Level-1（v9） |
| AC/MW/ID/DA/SPR/Cal | 沿用 v9 定义 536 的中立元 | Level-4…8 |

## 2. 形式化定义（要点与升级）

**定义 493（六层指标层级）** 继承 v8/v9：M=(M₀,M₁,M₂,M₃,M_dom,M_SLAM) 不变。
**定义 495/524（MetaWeight/情感）** 继承不变。
**定义 521（DA-OTL）** 继承；τᵢ(t) 仍可被块证书替代逐层复核。
**升级定义 496（软证书，v10）** 触发条件在 v9 五条件（σ<τ_safe ∧ γ_grasp ∧ Δ_dom<τ_dom ∧ risk_SLAM<τ_SLAM ∧ Ĉ_t valid）上增加两条：
```
∧ (Ĉ_contact valid) ∧ (硬规范盾未删去当前块)
```
块内任一条件失效 ⇒ 立即按定义 548 切换接触安全中止点或 a_ask，不等块边界。

**升级定义 531（软硬约束衔接）** M₀ 硬检查增加规范入口：硬规范 R_ν>ε_ν 的预测直接进入 M₀ 硬违规判定；软规范只进奖励。物理 M₀ 判据不因规范模块存在而放宽。

**新增定义 534'（双语义中止点）** P_t = P_t^nav ∪ P_t^c：导航中止点沿用定义 534；接触中止点按定义 548。块可执行的必要条件从"P_t 非空"升级为"当前模式对应的中止点集非空"。

## 3. 关键算法骨架

```python
# IP-357 NormGroundingEngine
class NormGroundingEngine:
    def __init__(self, norms, hmms, eps, tau_ask=2.0):
        self.norms, self.hmm, self.eps = norms, hmms, eps
        self.b = {nu.id: 0.0 for nu in norms}
        self.tau_ask = tau_ask

    def update_belief(self, obs):
        for nu in self.norms:                      # 定义 541：每规范一个 HMM
            self.b[nu.id] = self.hmm[nu.id].forward(self.b[nu.id], obs)

    def risk(self, nu, traj):
        rho = stl_robustness(nu.psi, traj)         # 定义 540 的 deontic-STL
        return self.b[nu.id] * sigmoid(-rho / nu.scale)

    def shield(self, candidates, b):
        admissible = []
        for z in candidates:
            hard_ok = all(
                self.risk(nu, z.traj) <= self.eps[nu.id]
                for nu in self.norms
                if nu.kappa == 'hard' and b[nu.id] >= nu.theta)
            if hard_ok:
                admissible.append(z)
        return admissible if admissible else [self.epistemic_recovery()]

    def epistemic_recovery(self):
        return SkillChunk.ask_then_observe(             # 定义 544
            stop_at='d_social', face_human=True,
            query='proceed?', escalate_after=self.tau_ask)

    def learn_from_feedback(self, f, a):
        for nu in self.norms:                      # 定义 545：贝叶斯更新 + IV
            self.hmm[nu.id].posterior_update(f, a)


# IP-358/359 DexterousSkillLibrary + ContactCertifier
class ContactCertifier:
    def __init__(self, beta_f, beta_tau, beta_s, beta_g, eps_slip,
                 gamma_min, delta_mode):
        self.b = (beta_f, beta_tau, beta_s, beta_g)
        self.eps_slip, self.gamma_min = eps_slip, gamma_min
        self.delta_mode = delta_mode

    def certify(self, skill_seq, tactile, state):
        wrench = predict_wrench(skill_seq, tactile)
        slip   = slip_model(tactile, wrench, state.friction)
        gamma  = grasp_quality(skill_seq.final_grasp)
        mode   = contact_mode_posterior(tactile)
        cert = ContactCert(
            f_max=wrench.f.max() + self.b[0],
            tau_max=wrench.tau.max() + self.b[1],
            p_slip=slip.max() + self.b[2],
            gamma_min=gamma - self.b[3],
            mode_conf=mode.min())
        valid = (cert.f_max <= skill_seq.f_max
                 and cert.tau_max <= skill_seq.tau_max
                 and cert.p_slip <= self.eps_slip
                 and cert.gamma_min >= self.gamma_min
                 and cert.mode_conf >= 1 - self.delta_mode)
        return cert if valid else None

    def contact_safe_abort_points(self, skill_seq, pred, state):
        pts = []
        for p in range(1, len(skill_seq)):
            if self._invariant_Ic_holds(p, skill_seq, pred, state):  # 定义 548
                pts.append(p)
        return pts


# IP-360/361 CausalWorldModel + CausalAttributionEngine
class CausalWorldModel:
    def __init__(self, scm, invariant_parents):
        self.M, self.S_star = scm, invariant_parents

    def rollout(self, state, skill_seq, z):
        return counterfactual_rollout(               # 定义 551：只沿 S* 前向
            self.M, state, do={'skills': skill_seq}, parents=self.S_star, z=z)

    def uncertainty(self, state, skill_seq):
        return epistemic_std(self.M, state, skill_seq, self.S_star)


class CausalAttributionEngine:
    def __init__(self, scm, observed_confounders, instrument=None):
        self.M, self.Z, self.W = scm, observed_confounders, instrument

    def estimate_ace(self, module, data):
        if self.W is not None and iv_conditions_hold(data, self.W):
            return iv_estimate(data, module, self.W)          # 定义 550
        if backdoor_admissible(self.M, module, self.Z):
            return backdoor_adjust(data, module, self.Z)      # 定义 550
        return sensitivity_bound(data, module)                # 报告 B_Γ


# IP-362 NormativeCausalPlanner：三环统一
class NormativeCausalPlanner:
    def __init__(self, dsl, cc, nge, cwm, K_max=10, eps_u=0.05):
        self.dsl, self.cc, self.nge, self.cwm = dsl, cc, nge, cwm
        self.K_max, self.eps_u = K_max, eps_u

    def plan(self, state, belief, delta_dom, tau_dom, trust_ok):
        K = effective_K(delta_dom, tau_dom, trust_ok)         # v9 定义 539
        cands = self.dsl.sample_skill_sequences(state, K, n=64)
        # 1) 物理与接触证书（灵巧块必须两证齐全）
        cands = [z for z in cands
                 if physical_cert_valid(z) and (self.cc.certify(
                     z.skills, state.tactile, state) is not None)]
        # 2) 硬规范盾（只删不加；空集转认知恢复）
        cands = self.nge.shield(cands, belief)
        if len(cands) == 1 and cands[0].is_recovery:
            return cands[0]
        # 3) 因果反事实评分
        best = None
        for z in cands:
            pred = self.cwm.rollout(state, z.skills, z.z)
            if self.cwm.uncertainty(state, z.skills) > self.eps_u:
                continue                                        # 认知不确定性预算
            score = expected_task_return(pred) - norm_penalty(z, belief)
            if best is None or score > best.score:
                best, z.score = z, score
        return best or self.nge.epistemic_recovery()


# 主闭环集成：MetricVoiceGauge-NCD
def metricvoicegauge_round_10(M, s, obs, audio_stream=None, ell=None, ...):
    # ---- v9 MW 感知侧契约路径（≤2ms）原样保留 ----
    results = middleware.run_cycle(runners={...}, ctx=ctx)
    ctx.delta_dom, ctx.tau_dom = results['DA_ML'], M.tau_dom

    # ---- NGE：规范信念更新与人类反馈学习（≤0.1ms）----
    nge.update_belief(obs)
    if obs.human_feedback is not None:
        nge.learn_from_feedback(obs.human_feedback, last_action)

    # ---- 5Hz：接触/物理双证书 + 规范盾 + 因果反事实块生成 ----
    if current_chunk is None or current_chunk.exhausted:
        current_chunk = planner.plan(
            ctx.state, nge.b, ctx.delta_dom, ctx.tau_dom,
            trust_ok=(ctx.delta_dom < ctx.tau_dom
                      and ctx.risk_slam < M.tau_slam))

    # ---- 50Hz：v9 守卫 + 接触守卫 + 规范守卫（合计 ≤0.6ms）----
    verdict, k_next = chunk_guard(current_chunk, k_exec, live_obs, nge.b)
    if verdict == 'abort':
        current_chunk.execute_contact_safe_abort(k_next)     # 定义 548
        current_chunk = None
    elif verdict == 'recover':
        execute_recovery(nge.epistemic_recovery())            # 定义 544
    else:
        execute(current_chunk.skills[k_next])

    # ---- v8 继承路径（GCT/ER/5 维风险/奖励）与 v9 块证书复核 ----
    C, spatial_cert, claims, metrics, rewards = M.inherited_v9_path(ctx)

    # ---- CAE → ID：因果贡献替代相关消融，仍受 v9 双阈迟滞约束 ----
    if cycle_idx % T_abl == 0:
        for m in eligible_modules:
            c_m_do[m] = cae.estimate_ace(m, ablation_buffer)
        distiller.step_with_causal(c_m_do, ctx)
    return C, spatial_cert, claims, metrics, rewards
```

## 4. 推导

**引理 87（规范盾可靠性）** 设 (A1) 规范适用性信念校准：对实际适用的硬规范 b_ν≥θ_ν−δ_cal；(A2) 在信任域内 STL 鲁棒度预测误差 |ρ̂_ν−ρ_ν|≤β_ν；(A3) 阈值满足 ε_ν+L_νβ_ν+δ_cal≤ε_target，其中 L_ν 为 σ 的 Lipschitz 常数。则规范盾放行的块实际硬规范违规风险 ≤ε_target。证明：盾只放行 R̂_ν=b_νσ(−ρ̂_ν/s_ν)≤ε_ν 的块；由 Lipschitz 与误差界，R_ν≤R̂_ν+L_νβ_ν/s_ν+δ_cal；取阈值条件即得。无模型误差且信念精确时违规风险为 0。∎

**引理 88（认知恢复的活性/无僵死）** 若 a_ask 按定义 544 构造，则 (i) a_ask 始终∈A_soc；(ii) 每次 a_ask 的期望信息增益非负，且 T_ask 内若信念熵未下降则 escalate，故系统不会无限期自主僵持。证明：(i) a_ask 停驻于 d_social≥d_personal，不接触、不打断、不越序，硬规范鲁棒度均为正；(ii) 观测模型对 q_t 的更新使后验熵单调不增（贝叶斯更新性质），若连续 T_ask 无下降则触发人工确认这一预定义出口。安全性无条件成立；活性以人类响应为前提。∎

**引理 89（接触证书安全性）** 设接触模型误差满足 ‖f̂−f‖≤β_f、|P̂_slip−P_slip|≤β_s、|γ̂−γ|≤β_g、模式后验校准。若接触证书有效且每个执行步的模式切换均经触觉确认，则执行任意 p∈P^c 的 hold/regrasp/place 期间，真实力/力矩不超 f_max/τ_max、滑移概率≤ε_slip、抓取质量≥γ_grasp_min，且力闭合保持到安全释放。证明：对接触模式序列做归纳。free/approach 由 v9 证书覆盖；进入 contact/grasp 时证书用保守上界 f̂=f+β_f 检查，故真实值不越界；若任一时刻 I_c 被破坏，定义 548 保证存在 p 使 hold/regrasp/place 序列以力闭合为前提，归纳假设保持 I_c 到释放。∎

**引理 90（因果效应可识别性与敏感性）** 若 Z 满足 (A_m,Y) 的后门准则，定义 550 的调整式无偏估计 ACE_m；若 H 未观测而 W 满足 IV 条件，则 IV 估计一致；若二者均不满足，则 |ACE_obs−ACE|≤B_Γ(Γ)，Γ 为未观测混杂强度。证明：前两式为标准后门/IV 定理；第三式由 Rosenbaum 敏感性模型逐项展开得到。故 CAE 的输出必须附带识别假设标签，禁止把不可识别估计当因果真值。∎

**引理 91（不变因果模型的跨域误差界）** 设真实结果机制 P(Y|do(a),pa(Y)) 在 U_e 上不变，且 S* 包含真实父集、各环境在 S* 上支撑重叠。则 CWM 在新环境 e' 的预测风险
```
Err_{e'}(CWM) ≤ Err_e(CWM) + O(√(log(1/δ)/n)) + ε_overlap
```
与 Δ_dom 无显式依赖；而 v9 黑箱 F̂ 的误差界 β_bb(Δ_dom) 随分布偏移增大。证明：因机制不变，P(Y|do(a),X_{S*}) 不随 P(X) 改变，风险差仅来自有限样本泛化与支撑不重叠；域敏感但非父集的特征被 ICP 排除，故不进入误差项。∎
**推论 91.1**：当 Δ_dom≥τ_dom 时，v9 的 K_eff 门控仍把 K 收缩到 1（保守），CWM 在此区间提供比黑箱更紧的证书余量，从而缓解"分块在最需要安全时最不可靠"的 v9 最大风险；但前提是 S* 确实不变——见第 8 节风险。

**引理 92（因果归因去偏改善 ID）** 设 v9 的观测消融估计 c_m^obs 与真 ACE 的偏差为 B_H（由未观测 H 造成）。CAE 在后门/IV 可识别时给出一致估计，故 |c_m^do−ACE|→0；在不可识别时给出保守界并阻止迁移到 dormant。结合 v9 引理 85（Schmitt 迟滞），ID 的虚假休眠率不高于 v9，且无 Zeno 抖振。证明：c_m^obs=ACE+B_H；去偏估计消除 B_H；不可识别时用界 B_Γ 作为下限保护，只有 ACE 的上置信界仍低于 τ_off 才允许休眠。∎

**引理 93（中立元退化等价 v9）** 将定义 553 的三个中立元分别注入 NGE/DSL+CC/CWM+CAE 端口，则 NCP 的可行集与评分退化为 v9 AC 的候选集与评分，主闭环调用序列与 v9 逐位一致（仅调度顺序可交换）。证明：规范中立元使 A_soc=A 且 R_norm=0，盾为空操作；技能中立元使 Π=Π_v9、接触证书退化为 γ_grasp，与 v9 块定义相同；因果中立元使 F̂=F̂_v9、c_m^do=c_m。三个端口互不相交，逐端口代入即得 v9 程序；再由 v9 引理 83 继续退回 v8/v7/v6。∎

**引理 94（预算守恒）** 新增在线成本上界：NGE 信念+鲁棒度 ≤0.1ms（|N|≤12、STL 片段深度≤3、K≤10）；规范盾 ≤0.2ms（n=64）；接触证书 ≤0.3ms（K·d_t）；CWM rollout 5Hz 摊销 ≤1ms；CAE 每 T_abl 一回合、均摊 ≤0.1ms。总决策 p99 仍 ≤20ms，50Hz 保持。证明：逐项代入复杂度表并做静态 EDF 校验 ΣŴ_m≤B_dec 即得。∎

**引理 95（安全继承与无绕过）** v10 的执行管线为"物理证书 ∧ 接触证书 → 规范盾 → 因果评分"，其中规范盾只删候选、CWM 只重排序、CAE 只改归因，均不能使未通过证书的块被执行。对 v9 技能子集，接触证书退化为 γ_grasp，执行集是 v9 安全集的子集；对灵巧技能，引理 89 独立覆盖新接触谓词。因此不存在绕过 v9 适用证书的执行路径，v9 引理 80–81 的物理安全在 v9 子集上继续成立。∎

## 5. 复杂度分析

| 组件 | 域 | 时间 | 空间 | 正确性锚 |
|---|---|---|---|---|
| NGE 信念更新 + STL 鲁棒度 | 在线 50Hz | O(\|N\|·K·\|ψ\|)，≤0.1ms | O(\|N\|·\|Q\|) | 定义 540–542 |
| 规范盾 | 在线 5Hz | O(n_cand·\|N_H\|·K)，≤0.2ms | O(n_cand) | 定义 543 |
| DSL 技能采样 | 在线 5Hz | O(n·K·d_skill)，≤3ms/次（摊销 0.3ms） | O(n·K·d_skill) | 定义 546 |
| CC 接触证书 | 在线 5Hz | O(K·d_t)，≤0.3ms | O(K) | 定义 547–548 |
| CWM 反事实 rollout | 在线 5Hz | O(n·K·d_V·\|S*\|)，≤5ms/次（摊销 1ms） | O(n·K·d_V) | 定义 549–551 |
| CAE 归因 | 每 T_abl 回合 | O(\|Z\|·n_ep + IV)，均摊 ≤0.1ms | O(n_ep) | 定义 550，引理 90/92 |
| v9 继承路径（AC/MW/ID/6 层指标） | 在线 | ≤4ms | 不变 | v9 定义 532–539 |
| 决策侧合计 | 在线 | 典型 ≤9ms，p99 ≤20ms | — | 引理 94 |

## 6. 实验设计 E571–E588

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E571 | 规范接地精度（个人空间/轮流/递物同意） | 与人类标注一致率 ≥0.9；硬规范 F1 ≥0.95 |
| E572 | 社会导航硬规范违规率 | 个人空间侵入 0 次、插话 0 次（100 回合） |
| E573 | 规范盾僵局/活性 | 任务完成率不降；自主僵持 >T_ask 的比例 ≤2% |
| E574 | 认知恢复有效性 | 询问/观察后恢复决策成功率 ≥85%，人类评分 ≥4/5 |
| E575 | 跨文化/跨家庭规范迁移 | 两套规范画像下适应回合数 ≤50；负迁移 ≤5% |
| E576 | 人类反馈学习收敛 | 规范偏好估计误差 10 回合内 ↓≥50% |
| E577 | 灵巧抓取成功率 | YCB 20 物体 ≥90%，对比二指基线 +15% |
| E578 | 在手重定向成功率 | 3 类物体 ≥80%，掉落 ≤2% |
| E579 | 接触力/滑移安全 | 力越界 0 次；滑移率 ≤3%；β 标定覆盖 ≥99% |
| E580 | 接触中块突变中止 | 扰动注入中止成功 ≥99%，0 掉落、0 碰撞 |
| E581 | 因果归因 vs 随机对照真值 | ACE 相关性 ≥0.85；偏差 ≤0.1 |
| E582 | 未观测混杂 H 压力测试 | 敏感性界覆盖真值 ≥95%；不把不可识别当因果 |
| E583 | 跨域泛化：CWM vs v9 黑箱 | 新域 Δ_dom 大时误差 ↓≥40%（直接检验 v9 最大风险） |
| E584 | 因果 vs 相关 ID | 虚假休眠率 ↓≥50%，任务不降；无抖振 |
| E585 | 规范-因果耦合（意图推断助规范） | 递物时机/等待决策人类满意度 ≥4/5 |
| E586 | 全模块 WCET/背压 | p99 ≤20ms，0 丢拍；感知风暴下仍 0 丢拍 |
| E587 | 8h 社会-灵巧长跑 | 规范违规趋势稳定；中止命中率、休眠占比统计 |
| E588 | 端到端家庭任务/竞赛模拟 | ≥ v9 + 10%（预注册主指标） |

## 7. 预注册判据

| 判据 | 门槛（预注册） | 若未达标的处置 |
|---|---|---|
| 规范接地（E571） | 一致率 ≥0.9、硬规范 F1 ≥0.95 | 扩充规范谓词、提高 HMM 观测特征、人工审核规范库 |
| 社会违规（E572） | 0 次硬违规 | 收紧 d_personal、增大 ε 保守裕度、加规范盾冗余 |
| 僵局（E573） | 自主僵持 ≤2% | 提前 a_ask、降低 θ_ν、增加 escalate 出口 |
| 认知恢复（E574） | 成功率 ≥85%、评分 ≥4/5 | 改询问措辞/时机、增加观察步 |
| 跨文化（E575） | 适应 ≤50 回合、负迁移 ≤5% | 规范参数分层先验、加入文化画像开关 |
| 反馈学习（E576） | 误差 ↓≥50% | 增大随机化探索、改后验更新模型 |
| 灵巧抓取（E577） | ≥90%、+15% | 增加技能原语、调阻抗增益、扩触觉特征 |
| 在手操作（E578） | ≥80%、掉落 ≤2% | 降低重定向速度、加强接触证书裕度 |
| 接触安全（E579） | 0 越界、滑移 ≤3% | 收紧 f_max、重标 β_f/β_s、加触觉滤波 |
| 接触中止（E580） | ≥99%、0 掉落/碰撞 | 提高 P^c 密度、缩短 K_max、细化 I_c |
| 因果归因（E581） | 相关 ≥0.85、偏差 ≤0.1 | 增随机化臂、改后门集、换 IV |
| 混杂压力（E582） | 覆盖 ≥95% | 只报告界、禁止休眠依赖不可识别 ACE |
| 跨域（E583） | 误差 ↓≥40% | 重估 S*、缩回黑箱+更小 K、检查不变性前提 |
| 因果 ID（E584） | 虚假休眠 ↓≥50% | 提高 τ_off、用 ACE 下置信界、冻结迁移 |
| 规范-因果（E585） | 满意度 ≥4/5 | 联合建模 H、增加意图观测特征 |
| WCET/背压（E586） | p99 ≤20ms、0 丢拍 | CWM 移离线/异步、规范盾预筛、缩 n_cand |
| 长跑（E587） | 违规趋势稳定 | 周期性重标定 β 与 b_ν、复盘规范库漂移 |
| 端到端（E588） | ≥ v9 +10% | 综合调参、按消融定位瓶颈 |

## 8. 已知风险与失效模式

1. **规范误设与文化差异**：ν 库不可能穷尽；错误规范会制造"过度礼貌"或"隐性冒犯"。缓解：规范分层（hard 最小化）、人类反馈学习、可解释日志、离线文化画像验证。
2. **规范信念校准失败**：b_ν 假阴性（该适用却判不适用）比假阳性更危险；缓解：保守 θ_ν、校准误差 δ_cal 计入引理 87 裕度、假阴性专项实验。
3. **规范僵局与对抗利用**：人类可故意维持歧义让机器人一直等待；缓解：T_ask 后 escalate、任务级超时、把"等待成本"纳入 J。
4. **接触模型 sim-to-real 差距**：β_f/β_s 标定不足会使引理 89 失效；缓解：保守 β、在线触觉自适应、接触中止优先。
5. **因果假设不成立**：无未观测混杂、排他性、单调性、机制不变都可能被人类意图 H 破坏；缓解：报告识别假设与敏感性界，不可识别时禁止休眠/迁移，E582/E583 专项压力测试。
6. **规范-因果同源误差**：b_ν 与 CWM 都可能被 H 同时误导，产生"自信地礼貌且因果错误"；缓解：独立证据通道（语音/手势/触觉）、显式不确定性、必要时 a_ask 把这个误差转化为人类可纠正的询问。
7. **算力与实时性**：CWM/ICP 若在线更新会挤占预算；缓解：ICP 离线/低频、CWM 5Hz 摊销、静态 EDF 校验。

## 9. 本轮最大风险

**一句话**：规范信念 b_ν 与因果模型共享同一个未观测混杂 H（人类真实意图），一旦 H 使两者同时出错，系统会以高置信度把"该出手时不出手"解释成"规范要求等待"、把虚假相关当成因果效应，即**自信地礼貌且因果错误**。
<!-- ARTIFACT:END -->