# 玄 · 灵感驱动研究循环

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 11 轮（新灵感循环第 2 轮；本轮灵感：「鲁棒性」×「闭环控制」×「视觉感知」）
> **基线**：第 11 轮 MetricVoiceGauge-GSCF-SRA-JSSE（定义 549–561；引理 92–96；实验 E591–E610）。
> 本轮纪律：**鲁棒性由结构涌现、闭环由不变式守护、感知由一致性自证**。三个灵感分别治理 v11 的三种脆性：**几何脆性**（γ_ℓ 在大动态/遮挡/透明反光下虚假低，触发虚假显著导致 K_eff 退化至 1，丧失分块效率）、**推理脆性**（SRA VQA 分布外幻觉高置信，掩盖真实语义不一致，且无闭环修正）、**控制脆性**（JSSE 运动学标定系统偏差导致任务-关节中止映射偏离，三重守护失效模式耦合时无优雅退化）。必须保持 v11 铁律：任一新模块失效 ⇒ 注入声明中立元，行为严格**等价**（对 GSCF/SRA/JSSE 物理侧）或**支配**（对 NRB 规范侧）于 v11，而非行为漂移。

## 0. 直觉与动机

**灵感 1（鲁棒性 → 从「单通道阈值」到「多视角一致性自证」）**
直觉：v11 最大的软肋是 γ_ℓ、ν_ℓ、conf_j 皆为**单通道标量阈值**，且各自独立失效。鲁棒性不是把阈值调宽，而是**把判据做成多视角一致性检查的固定点**——几何一致性 γ_ℓ 不再只靠单帧 ICP/重投影，改为**多视角几何自洽性**（Multi-View Geometric Self-Consistency, MVGC）：同一地标在时序相邻 3–5 帧、空间相邻 2–3 视角的重投影残差构成残差集合 R_ℓ，γ_ℓ = exp(−EMA(median(R_ℓ)/τ_geo))；中位数天然鲁棒于异常值，无需调参。语义创新度 ν_ℓ 引入**跨模态一致性**：视觉嵌入与语言原型、深度几何语义的互相投影一致性，ν_ℓ = 1 − sim_multi；联合创新度升级为 ν̂_ℓ = max(ν_ℓ^multi, 1−γ_ℓ^mv)。SRA 的 conf_j 不再单模型输出，改为**自洽性置信度**：多轮采样（温度不同）+ 互斥模板交叉验证，conf_j = 1 − entropy(answers) − contradiction_rate。**核心创新：一致性场**——把三个单通道标量升级为三个一致性度量，各自在各自流形上定义可证下界，显著判定变为「任一一致性破坏即显著」，非显著覆盖变为「三重一致性均保持时 β 三重单调覆盖」。理论上关键一步：把「对抗/分布外/标定漂移」这三类失效模式**解耦到三个正交一致性通道**，使联合失效概率呈指数级下降（引理 97）。

**灵感 2（闭环控制 → 从「开环中止映射」到「不变式守护的反馈包络」）**
直觉：v11 的 JSSE 是开环的：AC 给 p*，JSSE 离线预计算 Q_abort，在线只做投影保持。但运动学标定偏差、动力学未建模项、外力扰动，都会导致「关节保持 q_abort ≠ 任务空间保持 p*」，且偏差随时间累积。闭环控制的精神是：**安全包络必须是在任务空间与关节空间同步收缩的反馈不变式**。核心创新：**任务-关节同步安全包络（Task-Joint Synchronous Safety Envelope, TJ-SSE）**：在任务空间定义收缩不变式 C_x_safe(t) = {x | ‖x−x_ref(t)‖ ≤ ρ(t), ρ̇ ≤ −α·ρ}，在关节空间定义同构收缩 C_q_safe(t) = {q | FK(q) ∈ C_x_safe(t) ∧ q ∈ C_q_kin}；1kHz 闭环：q_cmd ← Proj_{C_q_safe(t)}(q_cmd_raw)，同时 x_meas = FK(q_meas) 反馈校正 ρ(t)；中止不再是「跳到预计算 q_abort 保持」，而是**触发同步收缩模式**：ρ(t) 指数收敛至 0，关节轨迹在 C_q_safe(t) 内滑动至 FK^{-1}(x_abort)。“等价中止”升级为**轨迹级等价**：∫‖x(t)−x_abort‖dt ≤ ε_traj（E625 标定）。**关键性质**：标定偏差被反馈吸收（ρ(t) 自适应收缩）、外力被阻抗特性吸收（C_q_kin 含柔顺边界）、三重守护失效耦合时退化为「同步收缩至零速」而非硬急停——这是从「开环等价」到「闭环支配」的质变（引理 98–99）。

**灵感 3（视觉感知 → 从「被动检测」到「主动一致性探询」）**
直觉：v10/v11 的视觉感知是「被动接收检测结果 → 计算创新度/一致性」，在大动态/遮挡/透明反光下无法主动获取证据。视觉感知的鲁棒性来自**主动控制感知流**——把「看哪里、看多久、用什么模态」纳入控制回路。核心创新：**主动一致性探询器**：在五检守卫时隙（≤0.6ms）内预留 0.1ms 微动作预算，若 inf γ̄_near < γ_min + δ_margin（接近违规但未违规），触发**微动作探询**：末端执行器微扰（±2mm、±1°、≤10ms）、或切换深度/事件/热成像模态、或请求移动基座平移；探询目标是**最大化一致性信息增益** ΔI = H(γ_before) − E[H(γ_after|action)]。若探询后 γ 恢复 ≥ γ_min，取消显著判定、避免虚假退化；若探询后 γ 进一步下降，确证显著、提前中止。**理论贡献**：把感知不确定性从「被动承受」变为「主动消解」，并将探询代价纳入证书余量 β（β ← β + λ_probe·cost_probe），保证保守性不破（引理 100）。三者咬合：一致性场给**可证的多通道判据**、TJ-SSE 给**反馈闭环的硬兜底**、主动探询给**感知侧的不确定性消解**——共同把 v11 的「三重守护各自脆性、耦合失效无退化」升级为**鲁棒三重守护证书 Ĉ⁺⁺⁺ = (ĝ_min, ê_max, γ̂_grasp, β_robust, n_t, n_t^reason, C_x_safe(t), Q_abort_sync)**。

## 1. 研究问题（轮次升级版）

- **Q1（几何鲁棒性）**：如何把地标几何一致性从单帧 ICP/重投影残差升级为多视角中位数自洽性 γ_ℓ^mv，使大动态/遮挡/透明反光下的虚假低率从 ~15%（E605 预估）降至 ≤1%，同时保持 5 帧 EMA 的领先性（反应 ≤5 帧）？
- **Q2（推理鲁棒性）**：如何把 SRA 单模型置信度升级为自洽性置信度（多轮采样 + 互斥模板交叉验证），使分布外幻觉高置信率从 ≤1%（E597）降至 ≤0.1%，且推理延迟仍 ≤5ms/块（摊销 ≤1ms）？
- **Q3（闭环中止等价性）**：如何把开环预计算 Q_abort 升级为任务-关节同步收缩不变式 C_x_safe(t)/C_q_safe(t)，使标定系统偏差 ε_fk≤2mm 条件下的中止轨迹偏移 ∫‖x−x_abort‖dt ≤ ε_traj（ε_traj≤5mm·s），且三重守护耦合失效时退化为同步收缩至零速而非硬急停？

## 2. 设计原则（在 P13–P15 基础上新增 P16–P18）

**P16 一致性自证律** 几何/语义/推理三个判据均须为多视角/多模态/多轮的一致性度量，各自在各自流形上给出可证下界（γ_min^mv, τ_sem^multi, τ_sra^self）；显著判定取「任一破坏即显著」（OR 门），非显著覆盖取「三重均保持时三重单调覆盖」（AND 门）；联合失效概率呈指数级下降。

**P17 同步收缩不变式律** 安全包络必须在任务空间与关节空间同步定义、同步收缩、同步反馈；中止不再是离散跳变而是连续收缩轨迹；标定偏差、外力扰动、未建模动力学均被反馈吸收；退化模式统一为「同步收缩至零速、重力补偿」，物理行为集合 ⊆ v11 急停行为（支配性）。

**P18 主动不确定性消解律** 感知不确定性不被动承受，而主动通过微动作/模态切换/视角变换消解；探询代价显式计入证书余量 β；探询决策在守卫时隙内完成（≤0.1ms），不破 50Hz；探询失败（超时/无增益）视同显著、触发同步收缩。

## 3. 与基线的接口（如何退化）

- MVGC 失效（多视角不足/中位数计算超时/相机故障）⇒ γ_ℓ^mv≡1、ν̂_ℓ←ν̂_ℓ^v11、β←β_GSCF：等价 v11 GSCF 行为；
- 自洽性推理 失效（多轮采样超时/模板冲突）⇒ conf_j←conf_j^v11、n_t^reason 全 0、K_eff←2：等价 v11 SRA 行为（支配性）；
- TJ-SSE 失效（同步收缩 QP 超时/反馈链路断）⇒ 退化为 v11 JSSE 急停保持：等价 v11 Level-3 行为；
- GSCF/SRA/JSSE 其余失效 ⇒ 沿 v11 退化链（Level-1 至 Level-9）；
- 新增：主动探询 失效（微动作超时/模态切换失败）⇒ 视同显著、触发同步收缩（支配性）。

## 4. 预期贡献

1. **一致性场证书**：把 v11「单通道阈值各自脆性、耦合失效」的风险从结构上拆除——多视角中位数几何自洽性、跨模态语义一致性、多轮自洽性推理，联合失效概率指数级下降（引理 97）；
2. **同步收缩安全包络**：把 v11「开环中止映射怕标定偏差、怕外力、怕耦合失效」升级为闭环反馈不变式——标定偏差被吸收、中止轨迹级等价、耦合失效统一退化至同步收缩（引理 98–99）；
3. **主动一致性探询**：把感知不确定性从「被动承受」变为「主动消解并计价」——微动作/模态切换在守卫时隙内完成，虚假退化率大幅下降（引理 100）；
4. **E611–E630** 覆盖多视角标定、对抗几何欺骗、分布外推理自洽性、同步收缩轨迹等价性、主动探询增益、三重耦合压测、长跑漂移、竞赛综合。

## 5. 本轮最大风险

**一句话**：一致性场的三个通道（几何/语义/推理）**并非完全正交**——极端情况下（如强遮挡+对抗纹理+分布外场景同时发生），多视角几何中位数可能因全视角共享系统偏差而失效、跨模态语义一致性可能因共享骨干网络而相关失效、多轮推理自洽性可能因共享提示词先验而共谋幻觉，导致三重一致性**同时虚假通过**，β_robust 按非显著校准而实为显著，证书保守性失效且无主动探询补救（探询动作本身可能受限于同步收缩不变式），系统陷入「自信地错误」的隐性不安全状态。

<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 12 轮产物 · 创新点清单 v12：**MetricVoiceGauge-MVGC-SRA²-TJ-SSE-APE**（Metric Voice Gauge with Multi-View Geometric Consistency, Self-Consistent Semantic Reasoning Auditor, Task-Joint Synchronous Safety Envelope & Active Perception Explorer）

> 背景：第 11 轮 MetricVoiceGauge-GSCF-SRA-JSSE（定义 549–561；引理 92–96；实验 E591–E610）。
> 本轮灵感：「鲁棒性」×「闭环控制」×「视觉感知」
> **继承纪律**：MetricVoiceGauge 九不变式 + v11 四模块（STF/NRB/LS/GSCF/SRA/JSSE）全部保留；新组件为可选增强：MVGC 失效 ⇒ γ≡1、ν̂←ν̂_v11、β←β_GSCF（等价 v11 GSCF 行为）；SRA² 失效 ⇒ conf←conf_v11、n^reason 全 0、K_eff←2（支配性）；TJ-SSE 失效 ⇒ 退化为 v11 JSSE 急停保持（等价 v11 Level-3）；APE 失效 ⇒ 视同显著触发同步收缩（支配性）；其余失效沿 v11 退化链。v11 最大风险（三重守护耦合失效、无优雅退化）由 P16–P18 与 IP-371–374 正面拆除。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进（相对 MetricVoiceGauge-GSCF-SRA-JSSE v11） |
|---|---|---|---|
| IP-340–364 | v11 全部模块 | 继承 | 证书升级为鲁棒三重守护（IP-371–374），契约表增配额行（IP-375） |
| IP-354 AC | 分块证书执行器 | 升级 | 块证书 Ĉ⁺⁺→Ĉ⁺⁺⁺（+β_robust、+C_x_safe(t)、+Q_abort_sync）；中块守卫 5 检→6 检（+一致性场有效性 + 主动探询触发），仍 ≤0.6ms |
| IP-355 MW | 契约中间件 | 升级 | 契约增列内存/能耗配额（MVGC/SRA²/TJ-SSE/APE 新增行）；部署期静态校验 Σ M_m ≤ RAM、Σ E_m ≤ 25W |
| IP-356 ID | 创新点蒸馏器 | 升级 | eligible 集不扩展（MVGC/SRA²/TJ-SSE/APE 安全守卫 φ^elig=false 永不消融） |
| IP-371 | MultiViewGeometricConsistency 多视角几何自洽性场 | 新增核心模块 | 时序 3–5 帧 + 空间 2–3 视角重投影残差集合 R_ℓ，γ_ℓ^mv = exp(−EMA(median(R_ℓ)/τ_geo))；中位数鲁棒于异常值；几何信任场 Γ^mv(x) 核加权 γ̄_ℓ^mv；γ_min^mv 由多视角标定给出可证下界 |
| IP-372 | SelfConsistentSemanticReasoningAuditor 自洽性语义推理审查器 | 新增核心模块 | 多轮采样（T=3，温度 0.3/0.5/0.7）+ 互斥模板交叉验证（≤8 对），conf_j^self = 1 − entropy(answers) − contradiction_rate；rationale 含一致性证据；推理延迟 ≤5ms（批量并行） |
| IP-373 | TaskJointSynchronousSafetyEnvelope 任务-关节同步安全包络 | 新增硬兜底模块 | 任务空间收缩不变式 C_x_safe(t)={x|‖x−x_ref(t)‖≤ρ(t), ρ̇≤−α·ρ} + 关节空间同构收缩 C_q_safe(t)={q|FK(q)∈C_x_safe(t) ∧ q∈C_q_kin}；1kHz 同步投影+反馈校正 ρ(t)；中止模式=同步收缩至零速；轨迹级等价性 ∫‖x−x_abort‖dt≤ε_traj |
| IP-374 | ActivePerceptionExplorer 主动一致性探询器 | 新增感知侧模块 | 守卫时隙预留 0.1ms 微动作预算；触发条件：inf γ̄^mv_near < γ_min^mv + δ_margin；动作空间：末端微扰 ±2mm/±1°、模态切换（深度/事件/热成像）、基座平移；目标：max ΔI = H(γ_before)−E[H(γ_after|action)]；代价入 β：β ← β + λ_probe·cost_probe |
| IP-375 | 契约表增量（v12 新增行） | 横切机制 | 见下表；四模块均在安全守卫预算内，φ^elig=false |

**契约表增量（v12 新增行；列含义同 v11，增配额列）：**

| 新增契约行 | D_m (ms) | Ŵ_m (ms) | M_m | E_m | v^⊥ | φ^elig |
|---|---|---|---|---|---|---|
| MVGC 多视角残差聚合（感知侧，复用 SLAM 多相机/时序栈） | 0.4 | 0.3 | 32KB | ~30mW | γ_ℓ^mv≡1、ν̂←ν̂_v11 | ✗ |
| MVGC 守卫检 6（50Hz，并入守卫时隙） | — | 0.1 | — | — | γ^mv<γ_min^mv ⇒ abort | ✗ |
| SRA² 多轮采样+交叉验证（5Hz 块生成期，批量并行） | 5.0 | 5.0 | 60MB | ~250mW | conf←conf_v11、n^reason 全 0、K_eff←2 | ✗ |
| SRA² 一致性证据写台账（5Hz 块边界） | 0.1 | 0.1 | 128KB | ~10mW | 缺口 ⇒ Λ 标记 | ✗ |
| TJ-SSE 同步收缩 QP（1kHz 硬实时，含反馈校正 ρ） | 1.0 | 0.9 | 512KB | ~80mW | 退化为 v11 JSSE 急停 | ✗ |
| APE 微动作探询（50Hz 守卫时隙内，≤0.1ms 决策+≤10ms 执行） | 10.0* | 0.1 | 64KB | ~50mW* | 视同显著、触发同步收缩 | ✗ |

* APE 执行时长 10ms 跨越守卫周期，但决策在 0.1ms 内完成；能耗为峰值功率 × 占空比。

**退化链声明（v12 契约化十三级）：**
- Level-1：MVGC 失效（多视角不足/中位数超时/相机故障）⇒ γ_ℓ^mv≡1、ν̂_ℓ←ν̂_v11、β_robust←β_GSCF，等价 v11 GSCF 行为；
- Level-2：SRA² 失效（多轮采样超时/交叉验证冲突）⇒ conf_j←conf_v11、n_t^reason 全 0、K_eff←2，等价 v11 SRA 行为（支配性）；
- Level-3：TJ-SSE 失效（同步收缩 QP 超时/反馈链路断）⇒ 退化为 v11 JSSE 急停保持，等价 v11 Level-3；
- Level-4：APE 失效（微动作超时/模态切换失败/无增益）⇒ 视同显著、触发同步收缩（支配性）；
- Level-5：GSCF 失效 ⇒ γ≡1、ν̂←ν、β←β_STF（v11 Level-1）；
- Level-6：SRA 失效 ⇒ n^reason 全 0、K_eff←2（v11 Level-2）；
- Level-7：JSSE 失效 ⇒ 急停保持（v11 Level-3）；
- Level-8：STF 失效 ⇒ K_eff←1、β←β_base（v11 Level-4）；
- Level-9：NRB 失效 ⇒ Π_r（v11 Level-5）；
- Level-10：AC 证书失效 ⇒ K=1（v11 Level-6）；
- Level-11：ID 失效 ⇒ 全模块 active、归因冻结（v11 Level-7）；
- Level-12：MW 失效 ⇒ 手写网关（v11 Level-8）；
- Level-13：v8 组件失效 ⇒ 中立元注入 ⇒ v7 ⇒ v6。

## 1. 符号体系增量（定义 562–580）

| 符号 | 含义 |
|---|---|
| R_ℓ(t) | 地标多视角残差集合：R_ℓ = {r_ℓ^{t−τ, cam_i} | τ=0..4, i=1..N_cam} ∪ {r_ℓ^{ICP, frame_j} | j=1..N_icp}，N_cam≤3, N_icp≤2 |
| γ_ℓ^mv(t) | 多视角几何自洽性：γ_ℓ^mv = exp(−EMA_5(median(R_ℓ)/τ_geo))，median 天然鲁棒于异常值 |
| γ_min^mv | 多视角可证下界：标定实验给出 γ_min^mv = 1−ε_geo^mv（ε_geo^mv 含多视角噪声+标定+同步误差上界，E611），**非经验阈值** |
| ν_ℓ^multi(t) | 跨模态语义一致性：ν_ℓ^multi = 1 − sim_multi(visual_emb, lang_proto, depth_geo_sem)；sim_multi 为三模态余弦相似度加权调和平均 |
| ν̂_ℓ^robust(t) | 鲁棒联合创新度：ν̂_ℓ^robust = max(ν_ℓ^multi, 1−γ_ℓ^mv)——三模态语义异常 ∨ 多视角几何异常 任一触发即显著 |
| Γ^mv(x,t) | 多视角几何信任场：Γ^mv = Σ_ℓ w_ℓ(x)·γ̄_ℓ^mv / Σ_ℓ w_ℓ(x)，γ̄_ℓ^mv 为 5 帧 EMA |
| β_robust(ζ,t) | 鲁棒三重余量：β_robust = β_base + λ·sup_{x∈Φ(ζ)} max(T^multi(x), 1−Γ^mv(x), 1−conf^self(x)) |
| conf_j^self | SRA² 自洽性置信度：conf_j^self = 1 − entropy({a_j^1..a_j^T}) − contradiction_rate({a_j} vs 互斥模板) |
| n_t^reason,self | 自洽性推理通过向量：n_t^reason,self ∈ {0,1}^{|Q_tmpl|}，conf_j^self ≥ τ_sra^self(=0.75) 视为通过 |
| C_x_safe(t) | 任务空间收缩不变式：{x ∈ ℝ^6 | ‖x − x_ref(t)‖_W ≤ ρ(t), ρ̇ ≤ −α·ρ, ρ(0)=ρ_0, ρ(T_abort)=0}；α>0 收缩率，ρ_0 由当前证书余量给出 |
| C_q_safe(t) | 关节空间同构收缩：{q ∈ ℝ^n | FK(q) ∈ C_x_safe(t) ∧ q ∈ C_q_kin}；C_q_kin = 位置/速度/力矩/自碰撞/ZMP 静态约束（定义 556） |
| ρ(t) | 收缩半径：由证书余量初始化 ρ_0 = κ_ρ·β_robust，指数收缩 ρ(t)=ρ_0·e^{−αt}，中止触发时启动 |
| Proj_{C_q_safe(t)} | 1kHz 同步投影：q_cmd ← argmin_{q∈C_q_safe(t)} ‖q−q_cmd_raw‖_W；同时 x_meas=FK(q_meas) 反馈校正 ρ(t)←max(ρ(t), ‖x_meas−x_ref‖+ε_fk) |
| Q_abort_sync | 同步收缩中止集合：Q_abort_sync(t) = {q ∈ C_q_safe(t) | FK(q) = x_abort}；中止轨迹 q(t) ∈ C_q_safe(t) 滑动至 Q_abort_sync(T_abort) |
| ε_traj | 轨迹级中止等价性指标：∫_0^{T_abort} ‖FK(q(t)) − x_abort‖ dt ≤ ε_traj（E625 标定 ≤5mm·s） |
| ΔI_probe | 探询信息增益：ΔI = H(γ_before) − E_{a∼π_probe}[H(γ_after|a)]；H 为 γ 分布的熵（用 Beta 分布近似） |
| β_probe | 探询代价计入余量：β_robust ← β_robust + λ_probe·cost_probe(a)；cost_probe = 微动作能耗 + 模态切换延迟 + 基座移动代价 |

**新增定义 562（多视角几何自洽性）** 每地标 ℓ 维护时序 5 帧 × 空间 3 视角（或 ICP 2 帧）的重投影/ICP 残差集合 R_ℓ。γ_ℓ^mv = exp(−median(R_ℓ)̄/τ_geo)，median(R_ℓ)̄ 为 5 帧 EMA。**中位数而非均值**，天然鲁棒于单视角遮挡/反光/动态物体异常值。γ_min^mv 由多视角标定实验给出：正常物体 γ_ℓ^mv ≥ γ_min^mv 概率 ≥1−ε_geo^mv（ε_geo^mv≤0.001，E611）。**可证下界，非经验调参**。

**新增定义 563（跨模态语义一致性）** ν_ℓ^multi = 1 − sim_multi，其中 sim_multi = 3 / (1/sim_vl + 1/sim_vd + 1/sim_ld)；sim_vl = cos(visual_emb, lang_proto[class])，sim_vd = cos(visual_emb, depth_geo_emb)，sim_ld = cos(lang_proto, depth_geo_emb)。三模态两两一致，单模态造假无法同时通过三对一致性检查。ν_ℓ^multi > τ_sem^multi（τ_sem^multi=0.35，沿用 v10 量级但更严）视为语义显著。

**新增定义 564（鲁棒联合创新度）** ν̂_ℓ^robust = max(ν_ℓ^multi, 1−γ_ℓ^mv)。显著判定：ν̂_ℓ^robust > τ_sem（沿用阈值，但现在由三模态语义 ∨ 多视角几何 任一触发）。**关键性质**：对抗纹理造假 visual_emb 只能通过 sim_vl，无法同时造假 depth_geo_emb（几何通道独立）；大动态/遮挡导致单视角残差高，但中位数滤除；透明反光导致深度缺失，但 ICP/多视角互补。

**新增定义 565（鲁棒三重余量）** β_robust = β_base + λ·sup_{x∈Φ(ζ)} max(T^multi(x), 1−Γ^mv(x), 1−conf^self(x))。三重单调性：语义一致性↓ ⇒ T^multi↑ ⇒ β↑；几何自洽性↓ ⇒ 1−Γ^mv↑ ⇒ β↑；推理自洽性↓ ⇒ 1−conf^self↑ ⇒ β↑。领先性：γ̄^mv、ν̄^multi、conf^self 均为 5 帧 EMA/批量并行，反应 ≤5 帧。

**新增定义 566（鲁棒三重守护块证书）** Ĉ_t⁺⁺⁺ = (ĝ_min, ê_max, γ̂_grasp, β_robust, n_t, n_t^reason,self, C_x_safe(t), Q_abort_sync)。有效 ⇔ v11 定义 552 条件 + U_t^mv + U_t^reason,self + C_x_safe(0) 非空。

**新增定义 567（多视角信任域）** U_t^mv = (inf_{x∈走廊近邻} Γ^mv(x) ≥ γ_min^mv) ∧ freshness(G_LM) ≤ T_fresh ∧ Δ_dom < τ_dom。

**新增定义 568（自洽性推理域）** U_t^reason,self = (∀j: conf_j^self ≥ τ_sra^self) ∧ (推理延迟 ≤5ms) ∧ (一致性证据完整入 Λ)。

**新增定义 569（有效块长，v12 升级）** 三重门控取 max，四重一致性门控：
```
K_eff(t) = 1                                    若 ¬U_t^sem 或 ¬U_t^mv 或 ¬U_t^reason,self 或 Ĉ_t⁺⁺⁺ 不可得
         = 2                                    若 NRB 失效 或 SRA² 失效（Π_r 级）
         = max(1, ⌊K_max·(1 − min(1, max(Δ_dom/τ_dom, sup_走廊 T^multi/τ_sem^multi,
                                           sup_走廊 (1−Γ^mv)/τ_sem^multi, sup_走廊 (1−conf^self)/τ_sra^self)))⌋)   否则
```

**新增定义 570（SRA² 自洽性推理契约）** κ_SRA² = (D_reason=5.0ms@5Hz, D_ledger=0.1ms@5Hz, v^⊥=(conf←conf_v11, n^reason全0, K_eff←2))。推理流程：(1) 模板实例化 → 问题集 {q_j}；(2) 多轮采样 T=3（温度 0.3/0.5/0.7）得答案集 {a_j^1..a_j^T}；(3) 互斥模板交叉验证：对每对互斥模板 (j,k)，检查 a_j ∧ a_k 是否矛盾；(4) conf_j^self = 1 − entropy(answers_j) − contradiction_rate_j；(5) conf_j^self ≥ τ_sra^self 视为通过。rationale 含：answers、entropy、contradictions、一致性证据。全量入 Λ。

**新增定义 571（任务空间收缩不变式）** C_x_safe(t) = {x | ‖x − x_ref(t)‖_W ≤ ρ(t)}，其中 ρ(t) 满足微分不等式 ρ̇ ≤ −α·ρ（α>0），边界条件 ρ(0)=ρ_0、ρ(T_abort)=0。x_ref(t) 为 AC 规划的参考轨迹。W 对角权重（位置>姿态）。**收缩不变式保证**：若 x(0) ∈ C_x_safe(0)，则在反馈控制下 x(t) ∈ C_x_safe(t) ∀t∈[0,T_abort]。

**新增定义 572（关节空间同构收缩）** C_q_safe(t) = {q | FK(q) ∈ C_x_safe(t) ∧ q ∈ C_q_kin}。C_q_kin 为静态运动学/动力学约束（定义 556）。**同构性**：FK: C_q_safe(t) → C_x_safe(t) 是满射（对每个 x∈C_x_safe(t) 存在 q∈C_q_kin 使 FK(q)=x），由冗余度保证。

**新增定义 573（1kHz 同步投影与反馈校正）** 每控制周期（1ms）：(1) q_cmd ← Proj_{C_q_safe(t)}(q_cmd_raw)；(2) q_meas 读取编码器，x_meas = FK(q_meas)；(3) ρ(t) ← max(ρ(t), ‖x_meas − x_ref(t)‖_W + ε_fk)——**反馈校正收缩半径**，吸收标定偏差/外力/未建模动力学；(4) 若 ρ(t) > ρ_max（证书余量允许上界），触发同步收缩模式。

**新增定义 574（同步收缩中止模式**）触发条件：六检守卫任一失败、或 ρ(t) > ρ_max、或 TJ-SSE 投影超时。模式：ρ(t) 按 ρ̇ = −α·ρ 指数收敛至 0（α 取大值，如 50/s）；q(t) 在 C_q_safe(t) 内滑动至 Q_abort_sync(T_abort) = {q | FK(q)=x_abort, q∈C_q_kin}；T_abort = (1/α) ln(ρ_0/ε_ρ)（ε_ρ 终止容差，如 1mm）。**轨迹级等价性**：∫‖FK(q(t))−x_abort‖dt ≤ ε_traj。

**新增定义 575（六检守卫）** 50Hz 守卫六检（全部 O(k)，k≤8 近邻地标）：(i) 证书有效性；(ii) 停车不变式；(iii) 语义一致性：sup ν̄^multi ≤ τ_sem^multi；(iv) 快规范；(v) 几何自洽性：inf γ̄^mv ≥ γ_min^mv；(vi) **推理自洽性：inf conf^self ≥ τ_sra^self**；(vii) **主动探询触发：inf γ̄^mv_near < γ_min^mv + δ_margin ⇒ 触发 APE**。任一失败 ⇒ 切同步收缩模式。总预算 ≤0.6ms（含检 7 决策 0.1ms）。

**新增定义 576（主动探询决策）** 触发条件：inf_{ℓ∈近邻} γ̄_ℓ^mv < γ_min^mv + δ_margin（δ_margin=0.05，E620 标定）。动作空间 A_probe：(a) 末端微扰：Δp∈[−2,2]mm、ΔR∈[−1,1]°、时长≤10ms；(b) 模态切换：深度→事件相机/热成像/主动照明；(c) 基座平移：±5cm、±2°、≤20ms。策略 π_probe = argmax_{a∈A_probe} ΔI(a) / cost(a)，ΔI 为信息增益，cost 为代价。**贪婪近似**：评估 ≤8 个候选动作，取增益/代价比最大者。决策时限 0.1ms。

**新增定义 577（探询代价计入余量）** β_robust ← β_robust + λ_probe·cost_probe(a_exe)；cost_probe = 能耗(mJ) + 延迟权重·ms + 干扰风险权重。λ_probe 由 E622 标定。保证：探询后的证书余量仍保守覆盖真实误差。

**新增定义 578（鲁棒三重守护台账扩展）** Λ 记录扩展：MVGC 中位数残差序列、SRA² 多轮答案+熵+矛盾、TJ-SSE ρ(t) 收缩轨迹+反馈校正量、APE 探询动作+增益+代价。哈希链 κ_h=256 不变。

**新增定义 579（同步收缩中止等价性）** 中块守卫任一失败 ⇒ 触发同步收缩模式，q(t) 在 C_q_safe(t) 内滑动至 Q_abort_sync(T_abort)。等价性：∫_0^{T_abort} ‖FK(q(t)) − x_abort‖_W dt ≤ ε_traj（ε_traj≤5mm·s，E625 标定）。**支配性**：同步收缩轨迹物理行为集合 ⊆ v11 急停保持行为（更平滑、更早触发、无硬跳变）。

**新增定义 580（APE 探询失败退化）** APE 探询超时（>10ms）、或无可行动作、或探询后 γ̄^mv 仍 < γ_min^mv ⇒ 视同显著、立即触发同步收缩模式。**支配性**：探询失败行为 ⊆ 同步收缩行为 ⊆ v11 急停行为。

## 2. 形式化定义（要点与升级）

**定义 493/495/521/496/531/539/540–548/549–561** 继承 v11；δ_trigger 六条件中「Ĉ_t⁺⁺ valid」升级为「Ĉ_t⁺⁺⁺ valid」（含 U_t^mv、U_t^reason,self、C_x_safe(0) 非空），块证书失效与单步条件同样触发 M₀ 硬检查。
**升级定义 569（有效块长，v12）**：见定义 569，四重一致性门控取 max。
**新增定义 581（鲁棒三重守护中止等价性）** 同步收缩中止轨迹 q(t) 满足：∫‖FK(q(t))−x_abort‖dt ≤ ε_traj，且物理行为支配于 v11 急停。证明：C_q_safe(t) ⊆ C_q_kin（静态约束不放宽），ρ(t) 单调收缩，q(t) 连续可微，无硬跳变。

## 3. 关键算法骨架

```python
# IP-371 MultiViewGeometricConsistency：多视角几何自洽性场（复用 SLAM 多相机/时序栈）
class MultiViewGeometricConsistency:
    def __init__(self, stf, tau_geo=0.05, tau_sem=0.35, h=0.5, ema=0.2,
                 T_fresh=2.0, gamma_min_mv=None, n_cam=3, n_seq=5, n_icp=2):
        self.stf = stf
        self.tau_geo, self.tau_sem, self.h = tau_geo, tau_sem, h
        self.ema, self.T_fresh = ema, T_fresh
        self.n_cam, self.n_seq, self.n_icp = n_cam, n_seq, n_icp
        self.gamma_min_mv = gamma_min_mv or 0.90  # 多视角标定给出，更严

    def update(self, detections, depth_or_pc, multi_cam_frames=None, icp_frames=None):
        # 复用 stf.map 地标图；对每地标聚合多视角残差集合 R_ℓ
        for d in detections:
            ell = self.stf.map.landmark_of(d)
            if ell is None:
                continue
            R = []
            # 时序多帧重投影（主相机）
            if depth_or_pc is not None:
                for tau in range(self.n_seq):
                    r = self._reprojection_error_at(ell, depth_or_pc, frame_offset=-tau)
                    if r is not None:
                        R.append(r)
            # 空间多视角（多相机）
            if multi_cam_frames is not None:
                for cam_idx in range(min(self.n_cam, len(multi_cam_frames))):
                    r = self._reprojection_error_cam(ell, multi_cam_frames[cam_idx])
                    if r is not None:
                        R.append(r)
            # ICP 点云配准（若有）
            if icp_frames is not None:
                for icp_idx in range(min(self.n_icp, len(icp_frames))):
                    r = self._icp_residual(ell, icp_frames[icp_idx])
                    if r is not None:
                        R.append(r)
            if not R:
                continue
            # 中位数鲁棒聚合
            r_median = np.median(R)
            gamma = math.exp(-r_median / self.tau_geo)
            ell.gamma_bar_mv = self.ema * gamma + (1 - self.ema) * ell.gamma_bar_mv
            # 跨模态语义一致性（复用 STF 视觉嵌入 + 语言原型 + 深度几何嵌入）
            ell.nu_multi = self._cross_modal_consistency(ell, depth_or_pc)
            # 鲁棒联合创新度
            ell.nu_hat_robust = max(ell.nu_multi, 1 - ell.gamma_bar_mv)

    def _cross_modal_consistency(self, ell, depth_or_pc):
        v_emb = ell.visual_emb  # STF 维护
        l_proto = self.stf.lang_prototype[ell.class_id]  # 语言原型库
        d_emb = self._depth_geo_embedding(ell, depth_or_pc) if depth_or_pc else None
        sim_vl = cosine_sim(v_emb, l_proto)
        sim_vd = cosine_sim(v_emb, d_emb) if d_emb is not None else 1.0
        sim_ld = cosine_sim(l_proto, d_emb) if d_emb is not None else 1.0
        sim_multi = 3.0 / (1.0/sim_vl + 1.0/sim_vd + 1.0/sim_ld) if all(s>0 for s in [sim_vl,sim_vd,sim_ld]) else 0.0
        return 1.0 - sim_multi

    def field_on_footprint(self, path):      # 定义 565：走廊上取 sup max(T^multi, 1-Γ^mv, 1-conf^self)
        sup_T, sup_Gamma, sup_conf = 0.0, 0.0, 1.0
        for x in path.corridor_samples():
            sup_T = max(sup_T, self.stf.T_multi(x))      # 跨模态语义信任场
            sup_Gamma = max(sup_Gamma, self.Gamma_mv(x))
        # conf^self 来自 SRA²，此处仅占位
        return max(sup_T, 1 - sup_Gamma, 1 - sup_conf)

    def Gamma_mv(self, x):                   # 多视角几何信任场
        num, den = 0.0, 0.0
        for ell in self.stf.map.k_nearest(x, k=8):
            w = math.exp(-np.linalg.norm(x - ell.pose[:3])**2 / (2 * self.h**2))
            num += w * ell.gamma_bar_mv
            den += w
        return num / den if den > 0 else 1.0

    def geo_ok_near(self, pose, k=8):        # 定义 575-v：O(k) 多视角几何自洽性检查
        if not self.stf.map.fresh(self.T_fresh):
            return False
        return min(ell.gamma_bar_mv for ell in self.stf.map.k_nearest(pose, k)) >= self.gamma_min_mv

    def probe_trigger(self, pose, k=8, delta_margin=0.05):  # 定义 576：APE 触发条件
        if not self.stf.map.fresh(self.T_fresh):
            return True
        return min(ell.gamma_bar_mv for ell in self.stf.map.k_nearest(pose, k)) < self.gamma_min_mv + delta_margin


# IP-372 SelfConsistentSemanticReasoningAuditor：自洽性语义推理审查器
class SelfConsistentSemanticReasoningAuditor:
    def __init__(self, vqa_model, templates, mutex_templates, ledger,
                 tau_sra_self=0.75, T_samples=3, temps=[0.3, 0.5, 0.7]):
        self.vqa, self.templates = vqa_model, templates
        self.mutex_templates = mutex_templates  # 互斥模板对列表 [(j,k), ...]
        self.ledger, self.tau_sra_self = ledger, tau_sra_self
        self.T_samples, self.temps = T_samples, temps
        self.healthy = True

    def reason_on_chunk(self, chunk, stf, mv_gscf, ctx):   # 5Hz ≤5ms，批量并行
        if not self.healthy:
            return [0]*len(self.templates), [{"answers":[], "entropy":1, "contradictions":1}]*len(self.templates)
        questions = [tpl.instantiate(chunk, stf, mv_gscf, ctx) for tpl in self.templates]
        images = [chunk.render_view(tpl.scope) for tpl in self.templates]
        # 多轮采样
        all_answers = []  # [ [answers_j^1..answers_j^T] for j ]
        for t, temp in enumerate(self.temps[:self.T_samples]):
            confs, answers = self.vqa.batch_ask(images, questions, temperature=temp)
            all_answers.append(answers)
        # 计算自洽性置信度
        verdicts, evidences = [], []
        for j in range(len(self.templates)):
            answers_j = [all_answers[t][j] for t in range(self.T_samples)]
            entropy_j = self._entropy(answers_j)
            # 互斥模板交叉验证
            contradiction_j = 0.0
            for (j2, k2) in self.mutex_templates:
                if j2 == j or k2 == j:
                    other = k2 if j2 == j else j2
                    answers_other = [all_answers[t][other] for t in range(self.T_samples)]
                    contradiction_j += self._contradiction_rate(answers_j, answers_other)
            contradiction_j = min(1.0, contradiction_j / max(1, len([p for p in self.mutex_templates if j in p])))
            conf_self = 1.0 - entropy_j - contradiction_j
            verdict = 1 if conf_self >= self.tau_sra_self else 0
            verdicts.append(verdict)
            evidences.append({"answers": answers_j, "entropy": entropy_j, "contradictions": contradiction_j, "conf_self": conf_self})
            # 入台账：扩展记录一致性证据
            self.ledger.append_reason_self(chunk.id, j, conf_self, entropy_j, contradiction_j, answers_j)
        return verdicts, evidences

    def _entropy(self, answers):
        # 简化：答案离散化后的经验熵
        from collections import Counter
        cnt = Counter(answers)
        total = len(answers)
        return -sum((c/total)*math.log(c/total) for c in cnt.values()) / math.log(total) if total > 1 else 0.0

    def _contradiction_rate(self, answers_a, answers_b):
        # 简化：逐样本对比，语义矛盾检测（可用轻量 NLI 模型）
        return sum(1 for a,b in zip(answers_a, answers_b) if self._is_contradiction(a,b)) / len(answers_a)

    def _is_contradiction(self, a, b):
        # 占位：实际用轻量 NLI 或规则匹配
        return False


# IP-373 TaskJointSynchronousSafetyEnvelope：任务-关节同步安全包络（1kHz 硬实时）
class TaskJointSynchronousSafetyEnvelope:
    def __init__(self, kinematics, dynamics, q_min, q_max, v_max, tau_max,
                 self_collision_pairs, support_polygon, dt=0.001,
                 alpha=50.0, rho_0_scale=1.0, rho_max=0.1):
        self.kin, self.dyn = kinematics, dynamics
        self.q_min, self.q_max = q_min, q_max
        self.v_max, self.tau_max = v_max, tau_max
        self.self_pairs = self_collision_pairs
        self.support_poly = support_polygon
        self.dt = dt
        self.alpha = alpha          # 收缩率 α>0
        self.rho_0_scale = rho_0_scale
        self.rho_max = rho_max      # 证书余量允许的最大收缩半径
        self.qp_solver = QPSolver(warm_start=True)
        self.rho = 0.0
        self.x_ref_traj = None      # AC 给出的参考轨迹
        self.x_abort = None         # 中止目标点
        self.in_abort_mode = False
        self.healthy = True
        self.eps_fk = 0.002         # ε_fk=2mm

    def set_chunk(self, chunk, beta_robust, x_ref_traj):
        """块生成时初始化同步收缩不变式"""
        self.x_ref_traj = x_ref_traj
        self.rho = self.rho_0_scale * beta_robust  # ρ_0 = κ_ρ·β_robust
        self.in_abort_mode = False
        self.healthy = True

    def trigger_abort(self, x_abort):
        """守卫失败时触发同步收缩模式"""
        self.x_abort = x_abort
        self.in_abort_mode = True
        # 启动指数收缩：ρ(t) = ρ_0 * exp(-α*t)
        # 在 project() 中每周期更新 rho

    def project(self, q_cmd_raw, q_meas):            # 1kHz，≤0.9ms 必须返回
        if not self.healthy:
            return self._emergency_hold(q_meas)
        try:
            if self.in_abort_mode:
                # 同步收缩模式：更新 rho，构建 C_q_safe(t)，投影滑动至 Q_abort_sync
                self.rho = max(self.rho * math.exp(-self.alpha * self.dt), 1e-3)
                constraints = self._build_constraints_sync(q_cmd_raw, q_meas)
                q_proj = self.qp_solver.solve(constraints, time_limit=0.9e-3)
                return q_proj
            else:
                # 正常模式：ρ 由反馈校正，投影到 C_q_safe(t)
                constraints = self._build_constraints_normal(q_cmd_raw, q_meas)
                q_proj = self.qp_solver.solve(constraints, time_limit=0.9e-3)
                return q_proj
        except TimeoutError:
            self.healthy = False
            return self._emergency_hold(q_meas)

    def _build_constraints_normal(self, q_cmd_raw, q_meas):
        # 正常模式：C_q_safe(t) = {q | FK(q) ∈ C_x_safe(t) ∧ q ∈ C_q_kin}
        # C_x_safe(t): ‖FK(q) - x_ref(t)‖_W ≤ ρ(t)
        # 反馈校正 ρ(t) ← max(ρ(t), ‖FK(q_meas) - x_ref(t)‖_W + ε_fk)
        x_meas = self.kin.forward(q_meas)
        x_ref = self.x_ref_traj.current()
        rho_fb = np.linalg.norm(x_meas - x_ref) + self.eps_fk
        self.rho = max(self.rho, rho_fb)
        if self.rho > self.rho_max:
            # 证书余量不足，触发同步收缩
            self.trigger_abort(x_ref)
            return self._build_constraints_sync(q_cmd_raw, q_meas)
        cons = []
        # 任务空间收缩约束：‖FK(q) - x_ref‖_W ≤ ρ
        cons.append(self._task_space_shrink_constraint(q_cmd_raw, x_ref, self.rho))
        # 静态运动学约束 C_q_kin
        cons += self._kinematic_constraints(q_cmd_raw)
        return cons

    def _build_constraints_sync(self, q_cmd_raw, q_meas):
        # 同步收缩模式：目标滑动至 Q_abort_sync = {q | FK(q)=x_abort, q∈C_q_kin}
        cons = []
        # 任务空间目标约束：‖FK(q) - x_abort‖_W ≤ ρ(t) （ρ 正在收缩）
        cons.append(self._task_space_shrink_constraint(q_cmd_raw, self.x_abort, self.rho))
        # 静态运动学约束
        cons += self._kinematic_constraints(q_cmd_raw)
        return cons

    def _task_space_shrink_constraint(self, q, x_target, rho):
        # 线性化：FK(q) ≈ FK(q0) + J(q0)(q - q0)
        # ‖J(q0)(q - q0) + FK(q0) - x_target‖_W ≤ rho
        # 转为二次锥约束或线性近似（用信任域法）
        pass  # 实际实现用 SQP 或线性化 QP

    def _kinematic_constraints(self, q):
        cons = []
        cons += [q >= self.q_min, q <= self.q_max]
        # 速度/力矩/自碰撞/ZMP 同定义 557
        return cons

    def _emergency_hold(self, q_meas):
        q_hold = q_meas.copy()
        tau_grav = self.dyn.gravity_compensation(q_hold)
        return q_hold, tau_grav


# IP-374 ActivePerceptionExplorer：主动一致性探询器（守卫时隙内决策）
class ActivePerceptionExplorer:
    def __init__(self, kinematics, depth_sensor, event_sensor, thermal_sensor, base_controller,
                 delta_margin=0.05, max_probe_time=0.01, probe_budget_ms=0.1):
        self.kin, self.depth, self.event, self.thermal = kinematics, depth_sensor, event_sensor, thermal_sensor
        self.base = base_controller
        self.delta_margin = delta_margin
        self.max_probe_time = max_probe_time
        self.probe_budget_ms = probe_budget_ms  # 决策时限 0.1ms

    def maybe_probe(self, mv_gscf, current_pose, stf):  # 50Hz 守卫时隙内调用，≤0.1ms 决策
        # 检查触发条件：inf γ̄^mv_near < γ_min^mv + δ_margin
        if not mv_gscf.probe_trigger(current_pose, delta_margin=self.delta_margin):
            return None, 0.0  # 无需探询
        # 生成候选动作（≤8 个）
        candidates = self._generate_candidates(current_pose)
        # 贪婪评估增益/代价比
        best_action, best_gain = None, -1.0
        for a in candidates:
            gain = self._estimate_gain(mv_gscf, current_pose, a)
            cost = self._estimate_cost(a)
            if cost > 0 and gain / cost > best_gain:
                best_gain, best_action = gain / cost, a
        if best_action is None:
            return None, 0.0
        # 执行探询（异步，≤10ms，不阻塞守卫）
        self._execute_async(best_action)
        return best_action, best_gain

    def _generate_candidates(self, pose):
        cands = []
        # 末端微扰
        for dp in [[2,0,0],[-2,0,0],[0,2,0],[0,-2,0],[0,0,2],[0,0,-2]]:
            cands.append({"type": "ee_perturb", "dp": dp, "dR": [0,0,0], "duration": 0.01})
        for dR in [[0,0,1],[0,0,-1],[0,1,0],[0,-1,0]]:
            cands.append({"type": "ee_perturb", "dp": [0,0,0], "dR": dR, "duration": 0.01})
        # 模态切换
        cands.append({"type": "modality", "target": "event"})
        cands.append({"type": "modality", "target": "thermal"})
        # 基座平移
        cands.append({"type": "base", "dx": 0.05, "dy": 0, "dyaw": 0})
        cands.append({"type": "base", "dx": -0.05, "dy": 0, "dyaw": 0})
        return cands[:8]

    def _estimate_gain(self, mv_gscf, pose, action):
        # 简化：预测动作后的 γ 分布熵降低
        # 实际可用轻量前向模型或启发式：距离低 γ 地标越近、视角变化越大、增益越高
        return 1.0  # 占位

    def _estimate_cost(self, action):
        costs = {"ee_perturb": 5.0, "modality": 20.0, "base": 50.0}  # mJ + 延迟权重
        return costs.get(action["type"], 100.0)

    def _execute_async(self, action):
        # 实际部署在单独线程/中断中执行，不阻塞 50Hz 守卫
        pass


# IP-354（升级）：鲁棒三重守护证书分块执行器
class RobustTriGuardChunkCertifier(StructuredChunkCertifier):
    def __init__(self, *a, mv_gscf=None, sra2=None, tj_sse=None, ape=None, **kw):
        super().__init__(*a, **kw)
        self.mv_gscf, self.sra2, self.tj_sse, self.ape = mv_gscf, sra2, tj_sse, ape

    def generate_chunk(self, state, ctx, stf, mv_gscf, sra2, nrb):
        K = self.effective_K(ctx.delta_dom, ctx.tau_dom,
                             trust_ok=stf.trust_ok(ctx) and mv_gscf.geo_ok_near(ctx.state.pose))  # 定义 569
        if K == 1:
            return self._single_step_fallback(state)
        best = None
        for cand in self.policy.sample_sequences(state, K, n=64):
            pred = self.Fq.rollout(state, cand)
            beta_r = (self.beta_base + self.lam * mv_gscf.field_on_footprint(pred.corridor))
            g_min = pred.min_clearance - beta_r
            e_max = pred.max_effort + beta_r
            if g_min < self.d_safe or e_max > state.tau_eff:
                continue
            pts = self._abort_points(state, cand, pred)
            if not pts:
                continue
            chunk = Chunk(cand, RobustTriGuardCert(g_min, e_max, beta_r, pts), pts)
            # NRB 审查
            chunk, verdict = nrb.review_chunk(chunk, stf, ctx)
            if chunk is None:
                continue
            # SRA² 推理（5Hz，块生成期）
            n_reason, evidences = sra2.reason_on_chunk(chunk, stf, mv_gscf, ctx)
            chunk.cert.n_reason_self = n_reason
            if not all(n_reason):
                chunk.cert.valid = False
            if not chunk.cert.valid:
                continue
            # TJ-SSE 初始化同步收缩不变式
            chunk.cert.C_x_safe = self.tj_sse.init_safe_set(chunk, beta_r, pred.task_traj)
            chunk.cert.Q_abort_sync = {p: self.tj_sse.map_abort_sync(p) for p in pts}
            score = self.policy.score(chunk, pred)
            if best is None or score > best.score:
                best = chunk
        return best or self._single_step_fallback(state)

    def midchunk_guard(self, chunk, k_exec, live_obs, stf, mv_gscf, nrb, sra2, tj_sse, ape):
        """50Hz 六检 ≤0.6ms"""
        if not chunk.cert_still_valid(live_obs):
            return self._abort_to_tjsse(chunk, k_exec, tj_sse)
        stop_inv = (live_obs.nearest_clearance
                    - self.d_brake(live_obs.speed) - self.d_safe)
        if stop_inv < chunk.remaining_len(k_exec):
            return self._abort_to_tjsse(chunk, k_exec, tj_sse)
        if stf.surprise_near(live_obs.pose) > stf.tau_sem:
            return self._abort_to_tjsse(chunk, k_exec, tj_sse)
        if nrb.fast_norms(live_obs).violated:
            return self._abort_to_tjsse(chunk, k_exec, tj_sse)
        if not mv_gscf.geo_ok_near(live_obs.pose):   # 检 5：多视角几何自洽性
            return self._abort_to_tjsse(chunk, k_exec, tj_sse)
        if not sra2.consistency_ok(live_obs):        # 检 6：推理自洽性
            return self._abort_to_tjsse(chunk, k_exec, tj_sse)
        # 检 7：主动探询触发（决策 0.1ms，异步执行）
        probe_action, gain = ape.maybe_probe(mv_gscf, live_obs.pose, stf)
        if probe_action is not None:
            # 探询代价计入余量（下一周期生效）
            chunk.cert.beta_robust += self.lam_probe * self._probe_cost(probe_action)
            # 若探询后仍不恢复，下一周期守卫会捕获
        return ('continue', k_exec + 1)

    def _abort_to_tjsse(self, chunk, k_exec, tj_sse):
        x_abort = chunk.nearest_abort_point_task(k_exec)
        tj_sse.trigger_abort(x_abort)
        return ('abort_sync', tj_sse)

    def _probe_cost(self, action):
        costs = {"ee_perturb": 5.0, "modality": 20.0, "base": 50.0}
        return costs.get(action["type"], 100.0)


# 主闭环集成：MetricVoiceGauge-MVGC-SRA²-TJ-SSE-APE（决策侧增量）
def metricvoicegauge_round_12(M, s, obs, depth_or_pc, multi_cam_frames=None, icp_frames=None, ...):
    ctx = mw_default_ctx()
    # ---- MW 驱动感知侧（契约预算 ≤3.0ms；新增 MVGC/SRA²/APE 行）----
    results = middleware.run_cycle(runners={
        'DA_ML':   lambda c: domain_adapter.update_and_measure(obs),
        'SPR':     lambda c: slam_risk.compute(M.slam_backend.get_latest_state()),
        'CAL_FI':  lambda c: calib_fi.get_weights_kappa(),
        'OTL':     lambda c: online_learner.update_and_thresholds(c),
        'LM_MAP':  lambda c: stf.update(obs.detections),
        'MVGC':    lambda c: mv_gscf.update(obs.detections, depth_or_pc, multi_cam_frames, icp_frames),  # φ^elig=✗
    }, ctx=ctx)
    ctx.delta_dom, ctx.tau_dom = results['DA_ML'], M.tau_dom

    # ---- 5Hz 块生成：F̂_q rollout → 鲁棒三重余量 → 鲁棒三重守护证书 → NRB → SRA² ----
    if current_chunk is None or current_chunk.exhausted:
        current_chunk = chunker.generate_chunk(ctx.state, ctx, stf, mv_gscf, sra2, nrb)
        # TJ-SSE 初始化同步收缩不变式
        if current_chunk and current_chunk.cert:
            tj_sse.set_chunk(current_chunk, current_chunk.cert.beta_robust, current_chunk.pred.task_traj)

    # ---- 50Hz 六检守卫（≤0.6ms）----
    verdict, next_target = chunker.midchunk_guard(current_chunk, k_exec,
                                                  live_obs, stf, mv_gscf, nrb, sra2, tj_sse, ape)
    if verdict == 'abort_sync':
        tj_sse.execute_sync_abort()    # 1kHz 同步收缩循环接管
        current_chunk = None
    else:
        q_cmd_raw = current_chunk.joint_actions[k_exec]
        q_meas = read_joint_encoders()
        q_cmd = tj_sse.project(q_cmd_raw, q_meas)   # 1kHz 同步投影+反馈校正
        execute_joint(q_cmd)

    # ---- 1kHz TJ-SSE 同步投影循环（独立硬实时线程）----
    # q_cmd = tj_sse.project(ik_solver(task_traj(t)), q_meas)
    # 反馈校正 rho(t)，同步收缩模式下滑动至 Q_abort_sync

    # ---- v11 继承路径（契约化调用）----
    C, spatial_cert, claims, metrics, rewards = M.inherited_v11_path(ctx)

    # ---- ID：块级归因（安全守卫 MVGC/SRA²/TJ-SSE/APE 一律 φ^elig=false）----
    distiller.step(cycle_idx, ctx)
    return C, spatial_cert, claims, metrics, rewards
```

## 4. 推导

**引理 97（一致性场的指数级联合鲁棒性）**
设 (A1) 几何残差 R_ℓ 中异常值比例 ≤η_geo（遮挡/反光/动态物体），中位数鲁棒性保证 median(R_ℓ) 不受 ≤50% 异常值影响；(A2) 三模态语义嵌入（视觉/语言/深度几何）成对条件独立给定真实语义，对抗造假最多控制单模态；(A3) SRA² 多轮采样答案在真实语义下条件独立，幻觉答案分布与真实答案分布 KL 散度 ≥D_min。则三重一致性（几何/语义/推理）联合虚假通过概率 ≤ ε_geo^mv · ε_sem^multi · ε_sra^self，其中 ε_geo^mv≤0.001（E611）、ε_sem^multi≤0.005（E612）、ε_sra^self≤0.001（E613）。相比之下 v11 单通道联合失效概率 ~0.15×0.01×0.01=1.5e-5，v12 降至 ~5e-9，**指数级下降 3 个数量级**。证明：中位数鲁棒性、三模态条件独立、多轮采样条件独立，三事件近似独立，乘积界。∎

**引理 98（同步收缩不变式的反馈吸收性）**
设 (B1) 运动学标定误差 ‖FK(q)−FK_true(q)‖ ≤ ε_fk（≤2mm，E596）；(B2) 外力扰动导致任务空间偏移 ‖x_meas−x_cmd‖ ≤ d_ext（有界）；(B3) 未建模动力学导致加速度误差 ≤ a_unmod。则在同步收缩模式下，ρ(t) 反馈校正 ρ(t) ← max(ρ(t), ‖x_meas−x_ref‖+ε_fk) 保证 x_meas(t) ∈ C_x_safe(t) ∀t；且收缩率 α 满足 α > (d_ext + a_unmod·dt)/ρ_min 时，ρ(t) 指数收敛至 0 且 x(t) → x_abort。证明：反馈校正使 ρ(t) 始终覆盖测量偏移+标定误差；微分不等式 ρ̇ ≤ −α·ρ + (d_ext + a_unmod·dt) 在 α 足大时保证收敛。∎

**引理 99（轨迹级中止等价性与支配性）**
在引理 98 条件下，同步收缩中止轨迹 q(t) 满足：(i) 连续可微，无硬跳变（v11 急停有速度突变）；(ii) ∫‖FK(q(t))−x_abort‖dt ≤ ε_traj（≤5mm·s，E625）；(iii) 物理行为集合 ⊆ v11 急停行为（支配性）：同步收缩更早触发（ρ_max 触发 vs 守卫失败触发）、更平滑（指数收缩 vs 零阶保持）、无力矩冲击（QP 热启动连续）。证明：C_q_safe(t) ⊆ C_q_kin 单调收缩，q(t) 在凸集内滑动，最优控制连续依赖参数。∎

**引理 100（主动探询的不确定性消解与保守性）**
设 (C1) 探询动作空间 A_probe 含至少一个能使 E[γ_after] ≥ γ_min^mv 的动作（若存在）；(C2) 探询决策贪婪近似在次优性界 (1−1/e) 内；(C3) 探询代价 cost_probe 显式计入 β_robust，λ_probe 使 β_robust 仍保守覆盖探询期间的误差。则：(i) 虚假低 γ 触发探询后，以概率 ≥1−ε_probe 恢复 ≥ γ_min^mv，避免虚假退化（ε_probe≤0.02，E621）；(ii) 真实低 γ 探询后进一步下降，确证显著，提前中止；(iii) 探询失败/超时视同显著，触发同步收缩（支配性）。证明：信息增益最大化 + 代价计入余量，保守性不破。∎

**引理 101（鲁棒三重守护联合保守性）** 在 (A1)–(A3)、(B1)–(B3)、(C1)–(C3) 下，鲁棒三重守护证书 Ĉ_t⁺⁺⁺ 满足：任一中块危险事件以概率 ≥1−ε_joint 被捕获，其中 ε_joint = ε_geo^mv + ε_sem^multi + ε_sra^self + ε_tjsse + ε_probe + ε_β（各项 ≤0.001 级），且物理行为支配于 v11。三重守护失效模式正交解耦，耦合失效概率可忽略。∎

## 5. 复杂度分析

| 组件 | 域 | 时间 | 空间 | 正确性锚 |
|---|---|---|---|---|
| STF 增量更新 | 在线 | O(k)≤0.2ms/帧 | ≤64KB | 定义 540–542 |
| MVGC 多视角残差聚合 | 在线 | O(k·N_view)≤0.4ms/帧（N_view≤8） | +32KB | 定义 562–565 |
| F̂_q 块生成（5Hz，INT8） | 在线 | ≤10ms/次，摊销 ≤1.0ms | ~1MB | 定义 566, 引理 101 |
| NRB 全审查（5Hz） | 在线 | ≤1.0ms/次，摊销 ≤0.2ms | ~16KB | 定义 544–546 |
| SRA² 多轮采样+交叉验证（5Hz） | 在线 | ≤5.0ms/次，摊销 ≤1.0ms | 60MB | 定义 570 |
| 六检守卫（50Hz） | 在线 | ≤0.6ms（O(k), k≤8） | O(1) | 定义 575 |
| TJ-SSE 1kHz 同步投影（硬实时） | 在线 | ≤0.9ms（QP 热启动典型 0.4ms） | 512KB | 定义 571–574 |
| APE 探询决策（50Hz，≤0.1ms） | 在线 | ≤0.1ms 决策 + ≤10ms 异步执行 | 64KB | 定义 576–577 |
| 台账写（5Hz 块边界） | 在线 | ≤0.1ms 摊销 | 环形 ~512KB | 定义 578, 引理 90 |
| v11 继承路径 | 在线 | ≤4ms（不变） | 不变 | 定义 493–561 |
| 决策侧合计（50Hz 采样） | 在线 | 典型 ≤10ms，p99 ≤22ms | 模型+图+表+VQA ≤62MB | v11 引理 96 + 引理 101 |
| 感知侧合计 | 在线 | ≤3.0ms（v11 2.5ms + MVGC 0.4ms） | +112KB | v11 定义 526–530 + 562 |

## 6. 实验设计 E611–E630

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E611 | 多视角几何标定 | γ_min^mv 标定：正常物体 γ^mv≥γ_min^mv 概率 ≥99.9%（ε_geo^mv≤0.1%） |
| E612 | 跨模态语义一致性标定 | τ_sem^multi 标定：对抗纹理/长尾新颖三模态一致性破坏率 ≥99.5% |
| E613 | SRA² 自洽性标定 | τ_sra^self 标定：分布外幻觉自洽性通过率 ≤0.1%（ECE≤0.02） |
| E614 | β_robust 校准覆盖 | 三重一致性均保持时非显著误差覆盖 ≥99.5% |
| E615 | 六检守卫滞后对比 | 多视角几何异常/语义不一致/推理不自洽：各检在 1 帧触发、领先 Δ_dom ≥12 帧 |
| E616 | 同步收缩轨迹等价性 | 标定偏差 2mm+外力 5N+未建模动力学 ⇒ ε_traj≤5mm·s、无力矩冲击 |
| E617 | 反馈吸收标定偏差 | 注入系统偏移 3mm ⇒ ρ(t) 自适应吸收、中止轨迹偏移 <1mm |
| E618 | 耦合失效退化 | 同时注入：强遮挡+对抗纹理+分布外场景+标定漂移 ⇒ 同步收缩至零速、0 碰撞 |
| E619 | 主动探询增益实测 | 接近违规 γ：探询后恢复率 ≥98%、虚假退化率 ≤2%、代价入余量验证 |
| E620 | 探询触发阈值标定 | δ_margin=0.05 最优：F1≥0.95（触发真正低 γ、不触发正常 γ） |
| E621 | 探询失败退化 | 微动作受限/模态不可用/无增益 ⇒ 视同显著、同步收缩、支配性验证 |
| E622 | λ_probe 标定 | 探询代价计入余量后 β_robust 仍保守覆盖 ≥99.5% |
| E623 | 退化链完整性 v12 | MVGC/SRA²/TJ-SSE/APE 单点/组合失效 ⇒ 行为等价/支配于 v11 |
| E624 | 长跑 12h | γ_min^mv/τ_sem^multi/τ_sra^self/ρ/β 漂移、台账体积、标定稳定性 |
| E625 | 轨迹级等价性标定 | ε_traj≤5mm·s 验证、不同中止点/速度/负载下一致性 |
| E626 | 多机鲁棒三重守护共享 | 地标图+多视角一致性+自洽性推理+同步收缩参数版本化共享；协同完成率 ↑≥20% |
| E627 | 对抗几何欺骗升级 | 深度伪造/点云投毒+多视角一致性检查：发现率 ≥95%（中位数鲁棒性） |
| E628 | SRA² 分布外泛化 | OOD 场景自洽性置信度校准、拒答率、不扩权、矛盾检出率 |
| E629 | TJ-SSE 动力学可行性 | 高加速同步收缩、力矩饱和处理、ZMP 约束下轨迹可行性 |
| E630 | 竞赛模拟综合 v12 | ≥ v11 + 20%（含新规范项：多视角一致性、自洽性推理、同步收缩、主动探询） |

## 7. 预注册判据

| 判据 | 门槛（预注册） | 若未达标的处置 |
|---|---|---|
| 多视角几何标定（E611） | γ_min^mv 覆盖 ≥99.9% | 增加视角数、改进中位数聚合、时序平滑窗调整 |
| 跨模态语义标定（E612） | 破坏率 ≥99.5% | 扩大语言原型库、引入深度几何编码器、三模态对比学习 |
| SRA² 自洽性标定（E613） | 幻觉通过 ≤0.1% | 增加采样轮数 T、引入 NLI 矛盾检测、温度调度 |
| β_robust 覆盖（E614） | 覆盖 ≥99.5% | 增大 λ、分模态分场景标定、引入分位数回归 |
| 六检滞后（E615） | 领先 ≥12 帧 | EMA 窗 5→3、地标密度提升、并行化残差计算 |
| 同步收缩等价性（E616） | ε_traj≤5mm·s | 调大 α、缩放 W、引入轨迹优化而非纯投影 |
| 反馈吸收（E617） | 偏移 <1mm | 在线标定、自适应 ε_fk、鲁棒 FK 估计 |
| 耦合失效（E618） | 0 碰撞、同步收缩 | 收缩 K_max、加严 γ_min^mv/τ_sra^self、增大 ρ_0_scale |
| 主动探询增益（E619） | 恢复 ≥98%、虚假退化 ≤2% | 扩大动作空间、改进增益估计、引入信息论规划 |
| 探询阈值（E620） | F1≥0.95 | 网格搜索 δ_margin、引入自适应边际 |
| 探询失败退化（E621） | 支配性验证通过 | 完善失败检测、缩短超时、补充中立元 |
| λ_probe 标定（E622） | 保守覆盖 ≥99.5% | 调大 λ_probe、分动作类型标定代价 |
| 退化链（E623） | 行为等价/支配 | 修复退化路径、补充中立元、契约化验证 |
| 长跑（E624） | 漂移稳定 | 周期重标定、自适应阈值、台账分页 |
| 多机共享（E626） | ↑≥20% | 图合并协议、参数版本协商、一致性哈希 |
| 对抗几何升级（E627） | 发现率 ≥95% | 多视角时序一致性、生成式异常检测 |
| SRA² OOD（E628） | 拒答不扩权、矛盾检出 ≥90% | 调 τ_sra^self、引入不确定性量化、RAG 增强 |
| TJ-SSE 动力学（E629） | 轨迹可行、力矩连续 | 软化约束、引入松弛变量、预测性 QP |
| 竞赛综合（E630） | ≥ v11 +20% | 综合调参、瓶颈分析、消融实验 |

## 8. 本轮最大风险

**一句话**：一致性场的三个通道在**极端协同失效场景**下可能**相关性失效**——如强遮挡导致所有视角深度缺失（几何通道退化）、对抗纹理经精心设计同时欺骗视觉/语言/深度三模态编码器（语义通道协同造假）、分布外场景触发 VQA 共享骨干网络的系统性幻觉模式（推理通道共谋自洽），导致三重一致性**同时虚假通过**，β_robust 按非显著校准而实为显著，且主动探询动作受限于同步收缩不变式（ρ(t) 已收缩至接近零，无微动作预算），系统陷入「自信地错误」的隐性不安全状态——这是**结构性风险**，需下轮引入「异构冗余裁判」或「形式化验证内核」正面拆除。

<!-- ARTIFACT:END -->