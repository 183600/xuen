# 玄 · 灵感驱动研究循环

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 1 轮（新灵感循环；基线 v5 InstructGauge-RTDI）

> **基线**：第 5 轮 InstructGauge-RTDI（IP-334–339；定义 468–492；引理 63–68；实验 E473–E492）。更早的 InstructGauge-WR / v3 / ToolGauge / LeanGauge / MODGAUGE 退化链全部继续继承不变。
> **本轮纪律**：**增量升级 + 严格退化**。力觉与可重构各沿一条新轴升级 v5，二者都是可选增强而非依赖项；任一环节不可用都必须能一键退回 v5，再沿既有退化链继续下落。

## 0. 直觉与动机

**灵感 1（力觉传感 → 可证伪的「接触证书」，而不是新的力控制通道）**
直觉：视觉回答「工具在哪里」，力觉回答「碰到了什么、有没有滑、是不是卡住了、力有没有越界」。人类装配时并不是盯着力传感器读数去做闭环力控，而是用「手感」判断接触是否建立、是否打滑、是否到位——力觉的第一价值是**证伪**，不是**授权**。因此正确接口不是 `力→动作`，而是 `力→带区间的接触证书 ContactCert→硬约束屏蔽`：证书只回答「当前接触状态属于哪个集合、真实力旋量落在哪个区间、证据是否足够」，屏蔽层只做一件事——**把预测力区间不落在力包线内的动作前缀截掉**。

关键纪律：**力觉只能收缩可行域或降低不确定性，绝不能扩张可行域**。这条纪律把「感知更丰富」与「权限更大」彻底解耦：新增一路传感器不应让系统获得任何它原先没有的工具、幅值或动作，只应让它更有资格否决某些动作。信息性探查（probe）可以主动降低不确定性，但探查动作本身也必须落在力包线内，因此它仍然只作用于「不确定性」这一维，而不作用于「可行域」这一维。

直觉风险：力/触觉是**局部**模态——只覆盖接触点附近；它**标定依赖**——零漂、温漂、工具负载都会污染读数；它**易饱和**——真正危险的大接触力往往恰好把传感器推入饱和区；它对物体类别、表面磨损、抓取姿态**分布漂移**。把力觉当 ground truth，会制造「接触已经确认」的错觉。

**灵感 2（可重构机构 → 构型索引的能力与证书，而不是多一个自由度）**
直觉：机器人换工具、换指、变刚度、换末端执行器之后，**身体已经变了**，但软件里的运动学链、碰撞体、力包线、共形阈值、甚至 WCET 还停留在旧身体。人类工程师的做法是：先换好工具、空载试一下、确认到位、再干活。所以可重构的核心不是「形态学优化」，而是**构型纪元（configuration epoch）**：每一次物理重构都必须让旧证书**整体失效**，新证书必须在新构型下重新签发；能力集合从常量 `T₀` 升级为构型索引的 `T(c)`，能力闭包升级为 `tools(ι) ⊆ T(c) ⊆ T_reg`。

直觉风险：重构本身是一个**原子且高风险**的动作——半到位、卡滞、错装工具都可能发生；而最危险的失败模式不是「重构没做成」，而是「重构做了一半，软件却以为做成了，继续带着旧证书执行」。

**灵感 3（两者耦合 → 接触门控的可重构，必须被「纪元」钉死）**
直觉：换工具必须在**没有接触载荷**时进行（否则夹持中的工件会飞、工具会撞、力矩会失控）；而换完之后是否真的换好，最可靠的证据又来自力觉指纹——空载重力矩签名、标准探针的柔顺按压响应、指间闭合的力-位移曲线。于是二者天然形成互锁：**ContactCert 门控 ReconfigBarrier**，**ReconfigBarrier 之后必须用 ContactFingerprint + 运动学自检重新认证**，然后才 bump epoch、重新签发证书、恢复执行。

最危险的耦合是「新身体 + 旧力包线 / 旧共形阈值」：力觉证书是按旧构型标定的，构型一变，它的覆盖保证就失效；若纪元检查不严，一次局部接触误判会沿新身体的全身尺度被放大成安全违约。

## 1. 研究问题（本轮要回答什么）

- **Q1（力觉的安全性）**：力/触觉能否成为可校准、可证伪、可拒答的「接触证书」，而不是新的控制通道、新的攻击面、新的虚假安全感来源？
- **Q2（可重构的证书一致性）**：如何在不破坏 v5 既有安全证书体系（SpatialCert / FaultCert / RT-CVC / 共形校准）的前提下，把能力集合从 `T₀` 推广到 `T(c)`，并保证旧构型的证书**不可能**被新构型复用？
- **Q3（耦合的可界性）**：当接触门控与构型纪元耦合，能否把「局部接触误差」与「半重构」两类失败都限制在局部、给出可计算的损害上界，而不是让它们沿时间轴与身体尺度级联放大？

## 2. 三条设计原则（雏形；正式化见产物区定义 493–499）

**P4 证据只收缩（Evidence Shrinks, Never Expands）**
力觉/触觉证据只允许两种作用：其一，**否决**——预测力区间不在力包线内的动作被截断；其二，**降不确定**——探查动作在包线内主动缩小接触状态集合。形式化方向：`ContactShield(π, cert) ⊆ π`，且当证书区间变大或力包线变小时，被接受的动作集合**单调不增**。结合 v3 的能力闭包，得到「传感器不扩权」的双重保证：工具不扩、动作也不扩。

**P5 构型纪元（Configuration Epoch）**
每一份运行时证书都携带作用域标签 `(e, c)`：`e` 是构型纪元，`c` 是已自证的物理构型。任何重构提交都使 `e ← e+1`，并使所有旧证书立即失效；任何 gate（SpatialCert 校验、CVC 前置、RT 任务、共形阈值选择）在使用证书前必须先检查 `valid(cert, t)`。跨纪元使用证书是**类型错误**，不是精度问题。

**P6 接触门控重构（Contact-Gated Reconfiguration）**
重构仅在 `ContactCert.M ⊆ {FREE, FIXTURED}`、储能受限、目标构型已注册、且块长强制 `K=1` 时允许；重构完成后必须通过 `ContactFingerprint`（力指纹）与运动学自检（FK/视觉已知位姿比对）双重认证，才允许 bump epoch 并恢复接触承载动作。认证失败进入 `SAFE_HOLD` 并尝试回退，绝不「带着不确定继续干」。

## 3. 与基线的接口（如何退化）

- F/T 或触觉不可用 / `ContactCert = UNKNOWN` / 某标定层样本不足 ⇒ 关闭 ContactShield，退回 v5 的 SpatialCert + 接触邻接动作强制 `K=1`；
- 重构执行器不可用 / 目标构型 `c' ∉ C_reg` / 工具未注册 ⇒ 固定 `c = c₀, e ≡ 0`，行为等价 v5 RTDI；
- 接触指纹样本不足 / 探测协议无法执行 / OOD 物体 ⇒ 使用数据手册保守包线 `F_safe(c)` + 人工确认，成功率为代价换取确定性安全上界；
- 纪元检查失败或认证失败 ⇒ `SAFE_HOLD`（这是**有意的失效安全**，不等价于 v5；它比 v5 更保守，必须在报告中单列）；
- v5 失效 ⇒ InstructGauge-WR ⇒ InstructGauge v3 ⇒ ToolGauge ⇒ LeanGauge ⇒ MODGAUGE，原退化链不变。

> 注意区分两种「退化」：**关闭增强**（编译期/配置期禁用）应逐字等价于 v5；**增强故障**（运行期失效）则进入 `SAFE_HOLD` 或保守包线，是**失效安全偏离**而非等价。把这两者混为一谈是常见的评测作弊。

## 4. 预期贡献

1. 一个「力觉只证伪、不授权」的接触证书口径，配以**单调收缩**与**分层共形覆盖**两条可证明性质，把力觉从控制通道降格为安全屏蔽的证据源；
2. 一个**构型纪元 + 证书作用域**机制，把「换身体」变成可类型检查的状态迁移，从结构上排除「新身体 + 旧证书」；
3. 一个**接触指纹自证**方案，用力响应签名 + 运动学自检检测半重构/错装工具，并给出误接受的概率界；
4. 一个**接触门控重构屏障**，把带载重构与半重构的损害限制在保守力包线内；
5. 一条完整可证伪路径：E493–E512 覆盖接触覆盖、包线违约、滑移检测、纪元拒绝、指纹辨识、耦合任务、对抗注入与 50Hz 时序保全。

## 5. 本轮最大风险

**一句话**：力觉证据的局部性、标定漂移与构型纪元的全局失效互相耦合——最危险的不是单次力误判或单次重构失败，而是「重构后仍用旧力包线/旧共形阈值」的**纪元错配**，它会把一次局部接触误差沿新身体的全身尺度放大成安全违约；因此纪元一致性检查必须优先于任何精度指标，宁可 `SAFE_HOLD`，不可带旧证书继续。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 6 轮产物 · 创新点清单 v6：**InstructGauge-TC**（Touch & Configure）

> 背景：第 5 轮 InstructGauge-RTDI（IP-334–339；定义 468–492；引理 63–68；实验 E473–E492）。
> 本轮灵感：「力觉传感」×「可重构机构」
> **继承纪律**：InstructGauge-RTDI 的 RT-CVC、FaultCert、RecoveryRegistry、PrimitiveGraph、RTDI-7C、五不变式与严格退化链全部保留。新组件一律为**可选增强**：任一环节不可用 ⇒ 退回 InstructGauge-RTDI ⇒ 退回 InstructGauge-WR ⇒ 退回 InstructGauge v3 ⇒ 退回 ToolGauge。
> **非目标（明确不做）**：不做自由力控制、不做在线形态学优化、不做「力觉驱动的新工具生成」、不让重构改变预注册工具集 `T_reg` 的成员资格。本轮只做「接触证据的保守化」与「构型变更的证书一致性」。

---

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进（相对 InstructGauge-RTDI） |
|---|---|---|---|
| IP-340 | ContactCert 接触证书 | 核心模块 | 力/力矩/触觉/关节力矩 → 带区间与拒答的接触状态证书；分 `(c, m, o)` 层共形校准；OOD 时退保守包线 |
| IP-341 | ContactShield 接触屏蔽 | 核心模块 | 预测力区间 ⊆ 力包线才放行；只截断、不新增动作；接触承载动作额外要求 `M ⊆ {STABLE}` 且 `ood=0` |
| IP-342 | BodySchema / ConfigRegistry 构型注册表 | 核心模块 | 能力从 `T₀` 升级为 `T(c)`；每构型携带运动学链、碰撞体、力包线、WCET 模型、指纹分布 |
| IP-343 | EpochCert 纪元证书作用域 | 核心模块 | 所有运行时证书带 `(e,c)`；重构 bump `e`；跨纪元使用是类型错误；所有 gate 先验 `valid` |
| IP-344 | ReconfigBarrier 重构屏障 | 核心模块 | 接触门控 + `K=1` + 两阶段原子重构 + 重构后双认证 + `SAFE_HOLD` 回退 |
| IP-345 | ContactFingerprint 接触指纹 | 核心模块 | 空载重力矩签名 + 标准探针力响应 → 构型自证；给出误接受概率界 |
| IP-346 | TC-9C 闭环 | 设计模式 | `W→R→C→E(rt-chunk)→Contact-C→Reconfig→Epoch/Recert→V→U`，在 v5 闭环上插入接触证书与纪元重认证 |
| IP-347 | InstructGauge-TC 主闭环 | 集成 | 力觉失败可退 v5；重构失败 `SAFE_HOLD`；纪元一致性可证；50Hz WCET 增量 ≤ 1ms |

**退化链声明**：
```
ContactCert 不可用/UNKNOWN      ⇒ 关闭 ContactShield，接触邻接动作 K=1        （≈ v5）
某校准层样本不足                ⇒ 全局保守阈值 + F_safe                      （保守 v5）
ConfigRegistry 不可用/目标未注册 ⇒ 固定 c₀, e≡0                              （逐字 v5 RTDI）
ContactFingerprint 不可用        ⇒ 重构后仅运动学自检 + 人工确认              （降级重构）
Epoch 检查失败/认证失败          ⇒ SAFE_HOLD（失效安全偏离，非等价退化）
全部增强关闭                    ⇒ InstructGauge-RTDI → … 原退化链
```

---

## 1. 符号体系增量（定义 493–499）

| 符号 | 含义 |
|---|---|
| `y_t = (f_t, m_t, p_t, τ_t, i_t)` | 时刻 `t` 的力/力矩、触觉阵列、关节力矩、电流测量 |
| `M = {FREE, STABLE, SLIP, JAM, UNKNOWN}` | 接触模式集合 |
| `w_t ∈ R⁶` | 真实接触力旋量（不可直接观测） |
| `W_t = ∏_k [w_k^−, w_k^+]` | 真实力旋量的保证区间（轴对齐盒） |
| `ContactCert_t = (M_t, W_t, e_t, c_t, κ_t, ood_t)` | 接触证书：模式集合、力区间、纪元、构型、覆盖水平、OOD 标志 |
| `σ = (c, m, o)` | 共形校准层：构型 × 接触模式 × 物体类 |
| `F_env(c, o) ⊆ R⁶` | 构型 `c`、物体类 `o` 下允许的力包线 |
| `F_safe(c) ⊆ F_env(c, o)` | 未知物体类时由数据手册/最坏工况得到的保守内近似 |
| `C_reg = C_disc × C_cont` | 已注册构型空间（离散模式 × 有界连续参数） |
| `BodySchema(c) = (K_c, G_c, T(c), F_env(c,·), W_c, φ_c)` | 构型 `c` 的运动学链、碰撞体、工具集、力包线、WCET 模型、指纹分布 |
| `E(t) ∈ N` | 构型纪元；物理重构提交时单调递增 |
| `CertScope = (e, c, h)` | 证书作用域：纪元、构型、内容哈希 |
| `valid(cert, t) ⇔ cert.e = E(t) ∧ attested(c, t)` | 证书在当前时刻可用 |
| `SafeReconfig(s, cert, c')` | 重构前置谓词（见定义 497） |
| `φ_c : ProbeProtocol → Dist(R^d)` | 构型 `c` 对标准探针协议的力响应分布 |
| `z ∈ R^d` | 一次指纹探测的观测向量 |
| `d_min = min_{c≠c'} TV(φ_c, φ_c')` | 构型指纹可辨识下界（全变差距离） |

---

## 2. 形式化定义（要点）

**定义 493（接触证书 ContactCert）**
设测量历史 `y_{1:t}` 与当前构型纪元 `(e, c)`。接触证书定义为
```
ContactCert_t = (M_t, W_t, e, c, κ_t, ood_t)
M_t ⊆ M                      // 集合值：证据不足时含 UNKNOWN，绝不强行单值分类
W_t = ∏_{k=1..6} [w_k^-, w_k^+]   // 保证区间：真值 w_t ∈ W_t 的概率 ≥ κ_t
κ_t ∈ (0,1]                  // 覆盖水平（来自分层共形校准）
ood_t ∈ {0,1}                // 是否落在已校准的 (c,m,o) 支撑集之外
```
构造语义：用带界标定误差 `Θ`、测量噪声与短时动力学界做区间传播；对每层 `σ=(c,m,o)` 用共形分位数 `q_{1-α}(σ)` 扩张预测区间。若 `|D_cal(σ)| < n_min` 或 `ood_t=1`，令 `W_t ← F_safe(c)`（确定性保守包线），并置 `M_t ← M`（全集合，即拒答），绝不输出过度自信的单值模式。

**定义 494（力包线 ForceEnvelope 与接触屏蔽 ContactShield）**
力包线是任务后置条件 `ψ_post` 在接触力学上的可行集：
```
F_env(c, o) = { w : g_fric(w) ≤ 0, g_mat(w) ≤ 0, g_grasp(w) ≤ 0 }
```
分别为摩擦锥、材料强度、抓取稳定性约束的保守内近似（标定 + 数据手册取交）。对块 `C=(a₁…a_K)` 与前缀 `a₁…a_{t−1}`，用集合值预测器给出动作 `a_t` 的力区间 `W(a_t | prefix)`。定义屏蔽
```
ContactShield(C, cert) = a₁…a_j*,  j* = max{ j : ∀t≤j, W(a_t | a₁…a_{t−1}) ⊆ F_env(c, o) }
```
若 `j*=0` 则整块拒绝。**接触承载动作**（预测接触集非空）额外要求 `M_t ⊆ {STABLE}` 且 `ood_t = 0`，否则强制 `K=1` 并要求逐动作回执。

**定义 495（构型注册表与 BodySchema）**
`C_reg ⊆ C_disc × C_cont` 为预注册构型集合（离散工具/指型/刚度模式 × 有界连续参数）。每个 `c ∈ C_reg` 定义
```
BodySchema(c) = (K_c, G_c, T(c), F_env(c,·), W_c, φ_c)
K_c : 运动学链（DH/URDF + 关节限位）     G_c : 碰撞几何
T(c) : 该构型可用工具集，T(c) ⊆ T_reg     W_c : 该构型的 WCET 模型
φ_c : 指纹分布（见定义 498）
```
**构型能力闭包**：在构型 `c` 下执行的任意指令序列 `ι_seq` 满足
```
tools(ι_seq) ⊆ ⋃_{ι∈ι_seq} tools(ι) ⊆ T(c) ⊆ T_reg
```
重构不得用于绕过注册：目标构型的工具集必须在 `T_reg` 中已注册。

**定义 496（构型纪元与证书作用域）**
`E : Time → N` 为单调非减阶梯函数。物理重构提交（成功认证）时 `E(t⁺) = E(t) + 1`。每份运行时证书（SpatialCert、FaultCert、RT 任务、共形阈值、ContactCert）携带
```
CertScope = (e, c, h),  h = Hash(cert_body)
```
证书可用性：
```
valid(cert, t) ⇔ cert.e = E(t) ∧ attested(c, t) ∧ h = Hash(cert_body)
```
所有 gate 在使用证书前必须先求值 `valid`；失败即拒绝该证书对应的动作。**跨纪元复用证书是类型错误**，而非数值误差。

**定义 497（重构屏障 ReconfigBarrier）**
重构请求 `c → c'` 的前置谓词：
```
SafeReconfig(s, cert, c') ⇔
    cert.M ⊆ {FREE, FIXTURED}
  ∧ cert.ood = 0 ∧ valid(cert, t)
  ∧ stored_energy(s) ≤ E_max
  ∧ c' ∈ C_reg ∧ tools(c') ⊆ T_reg
  ∧ ¬∃ pending contact-bearing block
```
执行语义（两阶段、原子、`K=1`）：
```
1. release   : 释放接触载荷，进入 FIXTURED 或 FREE；置 SAFE_HOLD
2. actuate   : 执行构型切换（单步、不可分块）
3. dwell     : 等待机械稳定（有界时间）
4. attest    : ContactFingerprint + 运动学自检（FK/视觉已知位姿）
5. commit    : 认证通过 ⇒ E ← E+1；重新签发 BodySchema(c') 相关证书
6. resume    : 重新做 SpatialCert 预检与 RT-CVC 建模后才恢复
任意一步失败 ⇒ 保持 SAFE_HOLD，尝试回退到 c；回退失败 ⇒ 请求人工
```

**定义 498（接触指纹 ContactFingerprint 与构型自证）**
标准探针协议 `P` 由两段组成：(P1) 空载、重力补偿下的自由空间慢速扫掠；(P2) 对标准柔顺参照物的一次受控按压。观测向量 `z ∈ R^d` 汇总关节力矩签名、末端力-位移曲线、触觉压力中心轨迹。对每个 `c ∈ C_reg` 预采集 `φ_c`。认证采用共形两样本检验：
```
Attest(z, c') = 1  ⇔  p_value(z | φ_{c'}) ≥ γ
```
可辨识条件：`d_min = min_{c≠c'} TV(φ_c, φ_{c'}) > 0`。若 `d_min` 过小（两个构型力签名不可分），该对构型被标记为「不可自证」，必须依赖独立硬件 ID/视觉标签，否则禁止自动重构。

**定义 499（TC-9C 闭环扩展）**
```
W        : 感知（WristCam + F/T + 触觉阵列 + 关节力矩）
R        : 推理（Hypothesis + Γ_parse）
C        : 契约规划（IAC + Kinematic-Loop + RT-CVC-TaskModel + ContactShield）
E        : 执行（rt-chunk，在 PP_C 处可抢占，实时更新 ContactCert）
Contact-C: 接触认证（ContactCert 生成、力包线校验、滑移/卡死检测）
Reconfig : 重构（SafeReconfig 门控 + ReconfigBarrier 两阶段执行）
Epoch    : 纪元提交（bump E、旧证书整体失效、按 BodySchema(c') 重签）
V        : 验证（CVC + SpatialCert + FaultCert + ContactCert 闭环）
U        : 更新（Dbox + 主张绑定 + 指纹/包线统计）
```
与 v5 的 RTDI-7C 相比，新增的 `Contact-C / Reconfig / Epoch` 全部是**可旁路**的：旁路后消息流与 v5 逐字一致。

---

## 3. 关键算法骨架

```python
# IP-340 ContactCert 构造：集合值 + 分层共形 + 拒答
class ContactCertBuilder:
    def __init__(self, calib, ood_detector, datasheet_envelope, n_min=200):
        self.calib = calib                  # {sigma: conformal quantile}
        self.ood = ood_detector
        self.f_safe = datasheet_envelope
        self.n_min = n_min
        self.hist = []

    def update(self, y_t, c, e):
        self.hist.append(y_t)
        sigma = (c, self._mode_hint(y_t), self._object_class())
        W_pred = self._interval_propagate(self.hist, c, sigma)
        if self.calib.size(sigma) < self.n_min or self.ood.is_ood(y_t, sigma):
            # 拒答 + 确定性保守包线：不输出过度自信的接触结论
            return ContactCert(M=set(M_ALL), W=self.f_safe(c), e=e, c=c,
                               kappa=1.0, ood=1)
        q = self.calib.quantile(sigma, alpha=0.05)
        W = self._expand(W_pred, q)
        modes = self._set_valued_classify(self.hist, sigma)  # 可为 {UNKNOWN}
        return ContactCert(M=modes, W=W, e=e, c=c, kappa=0.95, ood=0)

    def _interval_propagate(self, hist, c, sigma):
        # 带界标定误差 + 噪声 + 短时动力学界 -> 力旋量盒
        return interval_box(hist, c, sigma)

    def _set_valued_classify(self, hist, sigma):
        # 证据不足时保留 UNKNOWN，避免“强制单值分类”带来的虚假确信
        return classify_with_abstain(hist, sigma)


# IP-341 ContactShield：只截断、不新增
class ContactShield:
    def __init__(self, schema_registry, predictor):
        self.schemas = schema_registry
        self.pred = predictor

    def filter(self, block, cert, t_now):
        if not valid(cert, t_now):
            return block.truncate(0)                 # 纪元不符：整块拒绝
        env = self.schemas.env(cert.c, cert.object_class)
        j_star = 0
        for t, a in enumerate(block.actions, start=1):
            W_a = self.pred.interval(a, block.prefix(t - 1), cert.c)
            if not subset(W_a, env):
                break
            if a.is_contact_bearing:
                # 接触承载动作要求单值稳定且非 OOD；否则退化为单步
                if not (cert.M <= {STABLE} and cert.ood == 0):
                    return block.truncate(max(j_star, 0))
            j_star = t
        return block.truncate(j_star)


# IP-342/343 BodySchema + Epoch：证书作用域
class EpochManager:
    def __init__(self, c0):
        self.epoch = 0
        self.config = c0
        self.attested = True

    def scope(self, cert_body):
        return CertScope(e=self.epoch, c=self.config, h=sha256(cert_body))

    def is_valid(self, cert):
        return (cert.scope.e == self.epoch
                and cert.scope.c == self.config
                and self.attested
                and cert.scope.h == sha256(cert.body))

    def commit_reconfig(self, c_prime, attest_ok):
        if not attest_ok:
            raise SafeHold("attestation failed; refuse epoch bump")
        self.config = c_prime
        self.epoch += 1                 # 旧证书在这一行之后全部失效
        self.attested = True


# IP-344 ReconfigBarrier：接触门控 + 两阶段 + 失效安全
class ReconfigBarrier:
    def __init__(self, registry, epoch_mgr, attestor, energy_monitor):
        self.reg = registry
        self.epoch = epoch_mgr
        self.attest = attestor
        self.energy = energy_monitor

    def run(self, s, cert, c_prime, t_now):
        if not self._safe(s, cert, c_prime, t_now):
            return REJECT
        enter_safe_hold()
        release_contact_load(s)                    # step 1
        actuate_once(c_prime)                      # step 2, K=1
        wait_settled(self.reg.body(c_prime).settle_time)  # step 3
        z = self.attest.probe(c_prime)             # step 4
        kin_ok = self._kinematic_self_check(c_prime)
        fp_ok = self.attest.verify(z, c_prime)
        if not (kin_ok and fp_ok):
            if try_revert(c_prime, self.epoch.config):
                return SAFE_HOLD_REVERTED
            return SAFE_HOLD_NEED_HUMAN
        self.epoch.commit_reconfig(c_prime, attest_ok=True)  # step 5: bump
        reissue_body_certs(c_prime)                # 按新 BodySchema 重签
        return REISSUED                              # step 6: caller 再跑预检

    def _safe(self, s, cert, c_prime, t_now):
        return (cert.M <= {FREE, FIXTURED}
                and cert.ood == 0 and self.epoch.is_valid(cert)
                and self.energy.stored(s) <= self.energy.E_max
                and c_prime in self.reg
                and self.reg.tools(c_prime) <= self.reg.T_reg
                and not s.has_pending_contact_block)


# IP-345 ContactFingerprint：构型自证 + 可辨识性前置检查
class ContactFingerprint:
    def __init__(self, phi_lib, gamma=0.05, n_probe=64):
        self.phi = phi_lib
        self.gamma = gamma
        self.n = n_probe

    def verify(self, z, c_prime):
        p = conformal_two_sample_pvalue(z, self.phi[c_prime])  # 两样本共形检验
        return p >= self.gamma

    def identifiable(self, c, c_prime):
        return total_variation(self.phi[c], self.phi[c_prime]) >= self.d_min


# IP-346/347 TC-9C 主闭环（在 v5 instructgauge_rtdi 外侧包一层）
def instructgauge_tc(M, s, ell=None, reconfig_req=None):
    # 0. 若存在重构请求：先接触门控，再做原子重构
    if reconfig_req is not None:
        cert = M.contact.update(M.ft.latest(), M.epoch.config, M.epoch.epoch)
        r = M.barrier.run(s, cert, reconfig_req, M.env.time())
        if r in (SAFE_HOLD_REVERTED, SAFE_HOLD_NEED_HUMAN):
            return HOLD
        # REISSUED: 继续走 v5 预检

    # 1. 调用 v5 RTDI 完成接地、分块、RT-CVC、执行
    C, sp_cert, claims = instructgauge_rtdi(M, s, ell)

    # 2. 执行尾端接触证书 + 屏蔽（对已执行块做事后核验，驱动下一轮规划）
    cert = M.contact.update(M.ft.latest(), M.epoch.config, M.epoch.epoch)
    if not valid(cert, M.env.time()):
        return SAFE_HOLD                      # 纪元错配：拒绝复用
    safe_prefix = M.shield.filter(C, cert, M.env.time())
    if len(safe_prefix) < len(C):
        M.dbox.record_truncation(C.id, safe_prefix, cert)  # 证据入 Dbox
    # 3. ContactCert 参与主张绑定，形成可审计链
    M.tcv.bind_contact_claim(C.id, cert)
    return safe_prefix, sp_cert, claims
```

---

## 4. 推导

**引理 69（ContactShield 的单调收缩性）**
设两份接触证书 `cert, cert'` 满足 `W_t ⊆ W'_t`（`cert` 更紧）且 `F ⊆ F'`（`cert` 的包线更小），则被接受的动作集合满足 `Acc(cert') ⊆ Acc(cert)`。特别地，力觉证据**永远不能新增**被接受的动作。
证明：接受条件为逐动作 `W(a_t) ⊆ F_env`。固定预测器时，收紧 `W` 或缩小 `F_env` 都只会使满足包含关系的动作集合变小；接触承载动作还额外要求 `M ⊆ {STABLE}, ood=0`，这也是与门条件。取交集不增。∎
推论：结合 v3 引理 66（能力闭包 `tools(ι) ⊆ T(c) ⊆ T_reg`），得到「传感器不扩权」的双重保证：**工具集不扩，动作集也不扩**。

**引理 70（分层共形覆盖与分布漂移）**
(i) 若在固定校准层 `σ=(c,m,o)` 内样本可交换，则共形扩张给出 `P(w_t ∈ W_t) ≥ 1−α`。
(ii) 若测试样本来自不同层 `σ'≠σ`，则上述覆盖保证**不成立**，最坏可降至 0。
(iii) 若 `ood_t=1` 时强制 `W_t ← F_safe(c)` 且 `F_safe` 由数据手册的最坏工况构造，则 `w_t ∈ F_safe(c)` 是确定性成立（覆盖 1），代价是包线保守、可通过动作变少。
证明：(i) 是标准分裂共形结论；(ii) 由可交换性被破坏直接构造反例；(iii) 由 `F_safe` 的构造性包含关系。∎
这条引理把 v3 的教训（条件化破坏可交换性）推进到「构型条件化」：**换构型 = 换分布 = 旧阈值失效**，必须靠纪元切换校准层，而不是靠在线自适应硬撑。

**引理 71（纪元一致性 / 无陈旧证书）**
假设：(a) 纪元单调，只有 `commit_reconfig` 能改变 `(E, c)`；(b) 认证无假接受（`Attest=1 ⇒ c_actual=c'`）；(c) 每个 gate 在使用证书前检查 `valid`。则不存在任何动作在「物理构型 `c_actual`」与「证书所绑定构型 `cert.c`」不一致时被执行。
证明：对事件序列归纳。初始 `E=0, c=c_actual=c₀`，成立。非重构事件不改变 `c_actual` 也不改变证书的 `(e,c)`，归纳保持。重构事件中，`commit_reconfig` 先要求 `attest_ok`，由 (b) 得 `c_actual=c'`，随后 `E←E+1` 使一切旧证书 `valid=0`；新证书以 `(E+1, c')` 签发。任何在新证书签发前使用旧证书的 gate 都会因 `cert.e ≠ E` 被拒。∎
这条引理是 v6 的核心：它把「新身体 + 旧证书」从工程纪律变成**不可达状态**。

**引理 72（重构损害的界）**
在 `SafeReconfig` 成立、重构以 `K=1` 执行、且认证机制满足 `P(false accept) ≤ δ` 的前提下，从重构开始到恢复接触承载动作之间，发生「超出 `F_safe` 的接触载荷」的概率满足
```
P(damage) ≤ P(contact-gate miss) + δ · P(contact-bearing action | 恢复)
```
证明：重构期间接触载荷被 `release` 步骤卸除；若认证拒绝，系统停留 `SAFE_HOLD`，不执行接触承载动作，因此唯一的两条损害路径是：(1) 接触门控误判 `FREE/FIXTURED`（`M` 错分类或 OOD 未检出）；(2) 认证假接受后带着错误构型恢复接触动作。两条路径互斥计数，故并集界成立。∎
注意：这不是「零损害」定理，而是把损害归因到两个**可测量**的失效率上，便于预注册实验直接检验。

**引理 73（接触指纹的可辨识性与误接受界）**
设 `z_1…z_n` 为 i.i.d. 探针样本，二分类 `(φ_c, φ_{c'})` 满足 `TV(φ_c, φ_{c'}) ≥ d_min`。则最小错误概率满足
```
P_e ≤ 2 · exp(−n · d_min² / 2)
```
对 `|C_reg|` 个候选做并集界，取
```
n ≥ 2 ln(2|C_reg|/δ) / d_min²
```
即可保证误接受 ≤ δ。
证明：Pinsker 不等式给出 `TV ≤ sqrt(KL/2)`，标准两假设检验界 `P_e ≤ 2 exp(−n·KL/2)`，代入 `KL ≥ 2·TV² ≥ 2 d_min²` 即得。多类用并集界。∎
工程含义：**指纹可分性 `d_min` 是重构自动化的硬前提**；不可分的构型对必须降级到硬件 ID/视觉标签，不能靠「多按几次」蒙混。

**引理 74（退化等价性与失效安全偏离）**
- 关闭 ContactShield（配置期） ⇒ 执行路径与 v5 RTDI 逐字一致，`diff=0`；
- 关闭 ReconfigBarrier（配置期） ⇒ `C_reg={c₀}, E≡0`，所有证书在 `c₀` 下有效，退化为 v5；
- 运行期 F/T 掉线且 `ood` 不可判定 ⇒ `ContactCert=M_ALL, W=F_safe`，ContactShield 只允许 `W⊆F_safe` 的动作，接触承载动作 `K=1`；这是**保守 v5**，不保证逐字相同；
- 运行期纪元检查失败/认证失败 ⇒ `SAFE_HOLD`。这是**失效安全偏离**：比 v5 更保守，必须在实验 E503/E510 中单列为独立分支，不能计入「等价」。
证明：前两条由旁路开关直接构造；第三条由定义 493 的拒答分支与引理 70(iii)；第四条由定义 497 的失败处理。∎

---

## 5. 复杂度分析

| 组件 | 域 | 时间 | 空间 | 正确性锚 |
|---|---|---|---|---|
| ContactCert 更新 | 在线 @1kHz | `O(d)`，`d≤32`（力/力矩/触觉特征） | `O(d + |hist|)`（可用滑动窗 `O(d·H)`） | 定义 493, 引理 70 |
| ContactShield 过滤 | 每块 | `O(K·d)` | `O(d)` | 定义 494, 引理 69 |
| 力包线构造 | 离线/每构型 | `O(|G|)` 约束求交 | `O(|G|)` | 定义 494/495 |
| ConfigRegistry 查询 | 在线 | `O(1)`（哈希） | `O(|C_reg|)` | 定义 495 |
| Epoch 校验 | 每 gate | `O(1)` + 哈希 `O(|cert|)` | `O(1)` | 定义 496, 引理 71 |
| ReconfigBarrier 编排 | 每次重构 | `O(1)` 逻辑 + 物理 settle/probe 时间 | `O(1)` | 定义 497, 引理 72 |
| ContactFingerprint 认证 | 每次重构 | `O(n·d)`，`n≤64` | `O(n·d)` | 定义 498, 引理 73 |
| TC-9C 主路径增量 | 在线 | `≤ 1ms`（不含重构物理时间） | 不变 | 引理 74 |

时序口径：力觉更新跑在 1kHz 的独立实时线程，向 50Hz 主闭环发布**最新已认证**的 `ContactCert`；主闭环只读快照，不阻塞。重构是低频事件，允许 `SAFE_HOLD` 期间主闭环停摆，但 `SAFE_HOLD` 必须可观测、可超时升级到人工。

---

## 6. 实验设计 E493–E512

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E493 | 接触证书区间覆盖 | 固定 `(c,m,o)` 层，`P(w_t∈W_t) ≥ 95%`（`α=0.05`） |
| E494 | 力包线违约率 | 执行动作中超出 `F_env` 的比例 ≤ 0.1% |
| E495 | 滑移/卡死检测 | SLIP/JAM 检测 recall ≥ 0.95，precision ≥ 0.90 |
| E496 | 物体类漂移的 OOD 检出 | 新物体上 OOD 检出 ≤ 2 个控制周期，检出后 0 次超包线动作 |
| E497 | 屏蔽单调性 | 10,000 组随机证书序，`Acc` 随证据变化单调不增，0 反例 |
| E498 | 接触门控互锁 | 1,000 次带载/接触中重构请求，0 次被放行 |
| E499 | 纪元陈旧证书拒绝 | 注入时序故障/延迟提交，0 次跨纪元证书被使用 |
| E500 | 半重构检测 | 工具半锁、错装、指型未到位，认证拒绝率 ≥ 99% |
| E501 | 指纹误接受/误拒绝 | FAR ≤ 1%，FRR ≤ 5%（`d_min` 满足可辨识条件的构型对） |
| E502 | 重认证时延 | settle 后重认证 + 重签 + 预检 ≤ 40ms（2 周期）；`SAFE_HOLD` 可观测 |
| E503 | 耦合任务 | 「接触—重构—再接触」任务完成率 ≥ 85%，0 次超 `F_safe` 损害 |
| E504 | 错配力包线检测 | 故意用旧构型包线驱动新构型，纪元检查拦截率 100% |
| E505 | 对抗力注入 | 伪造 F/T 信号/重放旧读数，0 次错误授权，`ood` 或区间扩张可检出 ≥ 95% |
| E506 | 传感器掉线/饱和 | 1 周期内退保守分支，0 次接触承载动作在 `UNKNOWN` 下执行 |
| E507 | 50Hz WCET 保全 | 接触证书快照 + 屏蔽检查增量 ≤ 1ms，主路径 WCET 仍 ≤ 20ms |
| E508 | 长时漂移 | 1 小时连续运行，零漂可检出，误触发重构 ≤ 1 次/小时 |
| E509 | 实机 sim-to-real | 实机耦合任务完成率 ≥ 80%，包线违约 ≤ 0.5% |
| E510 | 消融 | 仅力觉 / 仅可重构 / 两者，配对比较；`SAFE_HOLD` 分支单列 |
| E511 | 未知物体保守退化 | 用 `F_safe` 时 0 损害，成功率下降 ≤ 15% |
| E512 | 形式化验证 | UPPAAL/NuSMV 验证纪元自动机：无「跨纪元使用」可达态、无「接触中重构」可达态 |

---

## 7. 预注册判据

| 判据 | 门槛（预注册） | 若未达标的处置 |
|---|---|---|
| 接触覆盖（E493） | ≥ 95% @ α=0.05 | 增广标定数据；改用更保守的 `F_safe` 分支并报告覆盖率-保守性曲线 |
| 包线违约（E494） | ≤ 0.1% | 收缩 `F_env` 内近似；接触承载动作强制 `K=1` |
| OOD 检出（E496） | ≤ 2 周期 | 降低 OOD 阈值（宁误报不漏报）；未知物体一律 `F_safe` |
| 单调性（E497） | 0 反例 | 视为实现缺陷，阻断发布；回查区间传播器 |
| 门控互锁（E498） | 0 放行 | 视为安全缺陷，阻断发布；回查 `SafeReconfig` 谓词 |
| 纪元拒绝（E499） | 0 跨纪元使用 | 视为安全缺陷，阻断发布；加硬件级互锁 |
| 半重构检测（E500） | ≥ 99% | 增加探针协议段数；不可分构型对禁用自动重构 |
| 指纹误接受（E501） | FAR ≤ 1% | 增大 `n`（按引理 73）或改用硬件 ID |
| 耦合完成率（E503） | ≥ 85% 且 0 损害 | 降低任务复杂度；增加人工确认节点 |
| WCET 增量（E507） | ≤ 1ms | 把力觉更新移出主线程，只发布快照；必要时降低更新率 |
| 实机迁移（E509） | ≥ 80% | 域随机化 + 实机重标定力包线；扩大 `F_safe` |

---

## 8. 本轮最大风险

**一句话**：力觉证书的**局部性 + 标定漂移**与构型纪元的**全局失效**相互耦合——最危险的不是单次力误判或单次重构失败，而是「重构后仍用旧力包线/旧共形阈值」的**纪元错配**：它会把一次局部接触误差沿新身体的全身尺度放大成安全违约；因此 `valid(cert,t)` 必须在每一个 gate 前无条件求值，宁可 `SAFE_HOLD`，不可带旧证书继续。
<!-- ARTIFACT:END -->