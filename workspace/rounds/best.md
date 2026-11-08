# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 32 轮 · 思维深化：SEG-TAC-SYNC-LITE —— 时延账本化证据融合、触觉定位清洗门与密集语义安全场

## 直觉锚点与动机链条（承接第 31 轮）

- **先自审再外审**：本轮开工前复查第 31 轮自己的命题，发现两个**比外部风险更优先的逻辑漏洞**，必须先修再谈进取：
  - **漏洞 A（命题 12/规则 22 的隐藏失效：任务接触饥饿）**：规则 22 将"一切接触转移"排除出适配集。但本系统的任务本体就是接触——机械臂抓取目标物后，名义动力学 M(q) 不含载荷，动量观测器必然对载荷响应（r_obs → τ_payload），于是"有载荷转移"被系统性判为接触并逐出适配集——而这恰是模型误差最大、最需要适配的数据。清洗门越保守，适配越饿；与第 31 轮已登记的"双门过严 → 永远空转"构成**双层饥饿**（数据层 + 门层）。命题 12 只论证了"接触不污染适配"，从未论证"排除接触不饿死适配"——单调不劣化的隐含前提是适配集非空。
  - **漏洞 B（命题 11 的隐藏失效：报警链端到端延迟未记账）**：命题 11 的"检出 ≤2 步"是监控器内部时钟上的量。闭环反应链 = 观测器收敛（时间常数 1/λ_O）+ n_win_c 持续判据 + 总线传输 + 仲裁栈读 + fallback 解算 + 执行器力矩上升，五段累积延迟没有出现在任何命题中。检测窗口内机器人仍以 v_ee 前进，最终接触力由 v_ee·T_alarm 与制动距离共同决定；而 λ_O 是"快收敛 vs 低 FPR"的折中——第 31 轮把它一句"带宽设计"带过，实际上它是**由安全方程反解的未知数**，不是自由参数。多速率（1kHz 带外 / 0.5ms 仲裁 / 15.3ms 关键帧）、多总线（EtherCAT/CAN/共享内存）各段延迟从未被记账——这正是灵感词「通信延迟」命中的结构性盲区。
- **弱点诊断 → 灵感映射**：本轮灵感词「通信延迟 / 触觉感知 / 语义分割」逐一命中并构成改进链：
  - 「通信延迟」→ **DELAY-LEDGER（时延账本 + 延迟补偿融合）**：每条证据附 (t_cap, t_ready, ch) 时间戳元组；账本按通道维护 P50/P99 与溢出计数；消费端按通道延迟做 Smith 预测器式外推，不确定度随 Δt 增长；超龄证据按保守方向处理（距离取下界、报警保持、严禁"超龄就清零"）；报警链 T_alarm 五段分解 + **停止距离方程** v_ee,max·T_alarm + v_ee,max²/(2a_brake) ≤ δ_allow 与 FPR 约束**联立反解 λ_O 可行域**（可行域空 → TELEM_ONLY 降级，继承 fail-safe）；跨处理器时钟偏移 ε_clock 显式估计（PTP 类周期握手）并计入 Δt 上界（漏洞 B 修复）。
  - 「触觉感知」→ **TAC-CLEAN（指尖触觉 + 期望接触白名单）**：指尖压敏阵列给出接触几何（位置/法向/切向），恰补关节力矩"有力无位置"的盲区；w_grasp = 规划意图 ∈ 抓取相 ∧ 触觉确认 F_n ≥ F_grasp_min ∧ 接触图 ⊆ 指尖预期区 → **期望接触入载荷监督集 D_fit.load**（Δf_θ 以载荷状态位 l_load 条件化），自由空间入 D_fit.free，非期望接触仍禁用（规则 22 修订为三分，漏洞 A 修复）；打滑判据 F_t/F_n vs μ̂_s 材质表 → 抓持力闭环（仲裁外），非期望持续接触 → tactile_alarm 进仲裁 OR（规则 21 扩展：三模态皆只增触发不做否决）。
  - 「语义分割」→ **SEG-FIELD（密集语义安全场）**：轻量蒸馏分割（与检测共享 backbone、多任务头、半频前向 + 帧间掩码传播）→ 人形掩码 → 距离变换 → 工作空间 d_field，叠加在检测框 d_max 之上**只收紧不放松**（不替换 v8 安全地板，缺省回退检测框）；类别条件威胁级与**类别条件速度上界 v̂_h_max**（手 > 臂 > 躯干，ISO/TS 15066 级规范先验 [F20]）；掩码不确定性（边界熵 + 传播年龄）→ 膨胀裕量 → **保守距离下界 d̃_min = d_field(t_cap) − (v̂_h_max+σ_v,h)·Δt_seg − κ_d·σ_seg**（延迟补偿的密集版，与 DELAY-LEDGER 共用外推算子）；遮挡时掩码时序传播补视觉盲区（E24c 场景的视觉侧增强）。
- **三者耦合**：分割给"人在哪、多快"（外推的运动先验），触觉给"碰到没、滑没滑"（接触级独立真值，且不需动力学模型——部分绕开第 31 轮最大风险"动量残差基线漂移"），延迟账本给"每条证据还剩多少可信期"（融合的时间诚实性）——安全论证从第 31 轮的"模态可靠"升级为"**模态可靠 × 时间可靠**"。第 31 轮"验证 + 吸收 + 审计 + 独立证据"四件套升级为五件套：+ **时间账本**。
- **关键设计决断**：(1) 延迟补偿与新鲜度判定**全部带外化**——安全处理器算好 (force_alarm, tactile_alarm, d̃_min) 三标量，仲裁栈只读（+0.02ms），兑现第 31 轮"再增仲裁内环节必须带外化"的预言；(2) seg/触觉沿袭"只增触发不做否决"，字段缺省 → 逐位 v8，退化链 v9→v8→v7→v6→v5 完整；(3) ε_acc 裕量**分账**：自由空间泄漏 η_miss·E‖τ_ext‖²（继承）+ 载荷误判 ε_fp·E‖τ_payload‖²（新增）两笔独立预算；(4) 关键帧预算 15.3 → 16.1ms **诚实升预算**（第 31 轮"不变"声明就此退役，E17 重测确认）；(5) μ̂_s 材质表、T_stale、T_alarm^max、v̂_h_max 表全部加入禁 OTA 清单（规则 19+23+26 联合）。

## 形式化定义的深化（继承第 31 轮全部符号）

### 8.1 时延账本符号（v9 新增）
- 证据元组 e = (value, t_cap, t_ready, ch)；Δt_e = t_now − t_cap（含跨处理器时钟偏移上界 ε_clock，周期握手估计 [F23]）；账本 B_ch = {P50, P99, 溢出计数}；T_stale(ch) 新鲜度上界。
- 外推算子 X：x̂(t_now) = x(t_cap) + v̂·Δt；σ̂²(t_now) = σ̂²(t_cap) + (σ_v·Δt)²；距离保守下界 d̃_min = d_field(t_cap) − (v̂_h_max + σ_v,h)·Δt_seg − κ_d·σ_seg。
- 报警链：T_alarm = t_conv(λ_O, ‖τ_ext‖, τ_gate) + n_win_c/f_obs + t_bus + t_read + t_act ≤ T_alarm^max；停止距离方程 v_ee,max·T_alarm + v_ee,max²/(2a_brake) ≤ δ_allow(ISO/TS 15066 部位参数) [F20]；λ_O 可行域 = 延迟约束 ∩ {FPR ≤ α_c/h}，空 → TELEM_ONLY。

### 8.2 触觉通道符号（v9 新增）
- τ_tac ∈ R^k₊ 指尖阵列（k 通道，1kHz，总线接入不走感知链路）；C_tac 接触图；F_n/F_t 法向/切向合力；μ̂_s(材质) 标定表；slip ≡ sustained(F_t/max(F_n,ε) > 0.9·μ̂_s, n_win_s=2)（仲裁外，进抓持力闭环）。
- w_grasp ∈ {0,1} 期望接触白名单 ≡ plan_state ∈ GraspPhase ∧ F_n ≥ F_grasp_min ∧ C_tac ⊆ 指尖预期区；错误率 (ε_fp, ε_fn)；tactile_alarm ≡ sustained(非期望接触, n_win_s=2)（只增触发）。
- 适配集三分：D_fit.free（自由空间，清洗门继承）/ D_fit.load（期望接触，新增；Δf_θ 条件化 l_load，l_load 由夹爪状态在线观测、非 κ、不破不变性条款）/ D_pool.contact（非期望接触，禁用，继承）。

### 8.3 分割场符号（v9 新增）
- S_img ∈ Δ^C 像素类别后验（手/前臂/上臂/躯干/物/线缆/背景，C=7）；M_h = {P(human|p) ≥ 1−δ_seg}；σ_seg(p) = 边界熵 + 传播年龄项；M̃_h = dilate(M_h, κ_d·σ_seg)；d_field = 图像域距离变换 → 标定投影 → 工作空间最小人距。
- v̂_h_max(c) 类别条件速度上界（规范级先验，E28 标定复核）；一致性门 seg_consistency(seg_lite, teacher) ≥ CONS_MIN，不过 → seg_lite=None（检测框外推退化）。
- 触发不变性：γ_seg、κ_d、v̂_h_max、μ̂_s、T_stale、T_alarm^max 入禁 OTA 清单；触发条件仍不含 κ 与任何可 OTA 量（命题 1 扩展）。

### 8.4 新增公理（规则 24–26）
- 规则 24（三模态 fail-safe OR + 新鲜度语义）：force/tactile/seg 皆只增触发不做否决；跨处理器证据必附时间戳，超龄 → 保守方向（距离下界、报警 fail-stay 保持最近值、严禁"超龄就清零"）；账本 P99 超预算 → 告警 + 该通道降"无新增覆盖"模式。
- 规则 25（期望接触白名单）：适配集转移必须三分（自由/期望接触/非期望接触）；期望接触需规划意图 + 触觉双确认；载荷污染能量 ε_fp·E‖τ_payload‖² 显式计入 ε_acc 分账；非期望接触禁用于适配不变。
- 规则 26（延迟预算纪律）：T_alarm 五段分解与停止距离方程是设计约束——λ_O、n_win_c、v_ee,max、a_brake、T_alarm^max 任一改动必须重解方程并重测 E26；各通道 P99 入账本并随版本发布。

## 算法步骤精炼（离线在七步上加第 8 步；在线 v8 上加 0.66 读双标量）

- 离线（+0.35 GPU·天一次性）：第 8 步 SEG-TAC-SYNC 烧录——(a) 分割蒸馏（共享 backbone 多任务头，半频 + 掩码传播；一致性门）；(b) 触觉驱动与 μ̂_s 材质表标定（+Isaac 触觉仿真扩展）；(c) 延迟账本与时钟同步烧录（各通道 T_stale/P99 预算 + ε_clock 握手）；(d) λ_O 可行域求解（停止距离方程 × FPR 联立；空 → 预置 TELEM_ONLY 模式）；(e) 载荷增广适配分支烧录（Δf_θ 条件化 l_load；三分分类器）；(f) S_bench v2 → v3（分割/触觉/延迟三类对抗场景 30/60 替换，v6/v8 双锚点重跑，规则 20 升版本）。
- 在线：安全处理器 1kHz 带外（动量观测器继承逐行不变 + 触觉处理 + d̃_min 外推 + 新鲜度审计，WCET <0.15ms 独立报告）→ 三标量；仲裁栈 v9 = v8 全部步骤 + 0.66 读 tactile_alarm 与 d̃_min（+0.02ms，单 cacheline 原子快照）。签名不变；字段缺省 → 逐位 v8 → v7 → v6 → v5。

## 复杂度分析（相对第 31 轮增量）

- 仲裁 0.42 → 0.44ms（+0.02 两标量原子快照读）；P99 < 0.5ms 维持（规则 14 重测；裕量 0.08 → 0.06ms，**下一轮仲裁内环节冻结**，再增必须继续带外化或分频）；带外 0.1 → 0.15ms @1kHz（触觉 + 外推 + 新鲜度，独立 WCET 报告）。
- 关键帧 15.3 → 16.1ms（多任务头半频分摊 +0.5、掩码传播 +0.1、时间戳打点 +0.2）——诚实升预算（E17 重测确认不破上游）。
- 训练 1.9 → 2.25 GPU·天一次性（seg 蒸馏 0.2 + 触觉标定 0.05 + Isaac 扩展 0.1）；持续适配 0.06 → 0.07/次（三分分类 + 载荷分支）；回归 0.35 → 0.40/发布；工程 2.5–4 人周（触觉驱动/标定 1–2、账本/时钟 0.5–1、seg 管线 1）。LUT 14MB 不变；触觉/载荷缓冲磁盘资产（IP-10 记账）。

## 正确性论证（命题 15–17 新增；命题 11/12 修订——诚实记录失效与修复）

- 命题 15（延迟补偿证据的保守性）：在假设 A-v（人体部位速度有界 v_h ≤ v̂_h_max(c)）与账本 Δt^P99 下，P(d̃_min ≤ d_true(t_now)) ≥ 1−δ_seg（单侧尾界）；推论：以 d̃_min 为约束的 fallback/裁剪不弱于 v8（只收紧不放松）。*失效模式*：v̂_h_max 低估（突挥）→ 假设破坏 → force/tactile alarm 兜底 + 速度硬上限；seg 缺省 → 检测框外推（仍保守、更粗）。E26b 注入验证越界率 ≤ δ_seg。
- 命题 16（报警链延迟预算，修复命题 11 隐藏缺陷）：T_alarm 五段分解 ≤ T_alarm^max 与停止距离方程联立 → λ_O 可行域；**可行域非空 ↔ 命题 11 的检出能力在真实闭环中成立**（第 31 轮命题 11 只证监控器内部性质，修订重述并登记历史）；可行域空 → TELEM_ONLY（无负收益）。E26a 注入验证端到端分布。
- 命题 17（白名单下适配不污染也不饥饿，修复命题 12 隐藏缺陷）：D_fit.load 污染能量 ≤ ε_fp·E‖τ_payload‖² 计入 ε_acc 分账；载荷转移覆盖率 ≥ (1−ε_fn)·任务接触占比 → 命题 12 从"接触不污染"强化为"接触分类后既不污染也不饿死"（第 31 轮原命题登记历史）。E27 对照 v8 全排除的载荷 G 曲线。
- 命题 1–10/13/14 继承；命题 1 触发条件扩展为"不含 κ 与任何可 OTA 量（含 μ̂_s/T_stale/v̂_h_max/γ_seg）"；命题 2 WCET 组合更新 0.3 + 0.05 + 0.01 + 0.05 + 0.1(60%) + 0.01 + 0.02 < 0.5ms（带外 0.15ms @1kHz 单独报告）。

## 未探索研究空白与开放词汇拓展（本轮补充）

### 研究空白
- **双层饥饿空白**：规则 22 的“一切接触转移”排他性与任务本体“必然接触”特性的冲突，导致模型误差最大的载荷数据被系统性排除，形成数据层饥饿；与规则 11/21/24 的累积严格性导致的门层饥饿共同构成双层饥饿。现有理论从未同时考虑过“清洗门保守性”与“适配集非空性”的耦合边界。
- **端到端延迟记账空白**：闭环反应链的五段累积延迟（观测器收敛、仲裁窗口、总线传输、栈读取、执行器升力）从未在任何命题中被完整记账，使得 λ_O 作为安全方程的未知数而非自由参数的性质被忽视。
- **物理假设依存空白**：命题 15/16 依赖人速上界 v̂_h_max 和允许变形 δ_allow 的物理假设在突挥或刚性碰撞下的联合失效边界，至今未被正式界定和缓解。

### 开放词汇与分类 vocabulary 扩展
- **从二元到三元的接触范畴**：传统的“接触/非接触”二元词汇已无法覆盖“期望接触/非期望接触/自由空间”三元区分。本轮词汇扩展引入 l_load（载荷状态位）与 w_grasp（期望接触白名单），要求算法语义必须同时容纳“被动承重”、“主动抓取”与“意外接触”三类情况。
- **动作词汇的模态耦合**：force/tactile/seg 三模态不再是独立的布尔触发，而是引入“只增触发不否决”的三模态 OR 语义，这要求词汇体系必须同时支持“严格模式”（任一触发即紧急制动）与“宽松模式”（需多模态共振才制动）两种解读。
- **时空联合词汇**：Δt（时间延迟）、d_min（保守距离）、w_grasp（接触意图）三者的组合词汇空间，必须满足保守性约束 d̃_min ≤ d_true 的同时最小化自由度丧失。

### 动作空间重构与三模态 OR 语义
- **安全动作空间的三分支**：{继续执行、带外报警、紧急制动} 在三模态 OR 语义下的结构重构。当 force_alarm ∨ tactile_alarm ∨ (d_min < γ_seg) 时，动作空间从单一的"制动"扩展到"制动+姿态调整+接触重评估"的三维子空间。
- **证据权重的动态重分配**：在三模态 OR 语义下，各模态的贡献权重不再是固定的，而是随 Δt、模态新鲜度和历史连续性动态重分配。这要求动作空间必须具备“证据质量感知”能力。
- **退化链的词汇保证**：v9→v8→v7→v6→v5 的退化链必须保证词汇子集的单调性——即高版本词汇的任何子集都必须能被低版本语义精确重构，否则会引入不兼容的边界情况。

## 本轮最大风险一句话
命题 15/16 立足的物理假设（人速上界 v̂_h_max、允许变形 δ_allow）在突挥或刚性碰撞下同时失效——延迟补偿的保守性与停止距离方程一并瓦解，安全论证从"接触前预防"滑向"接触后报警"，而兜底（接触必有力/触觉信号）本身是物理假设而非证据，须 E26b 越界扫描 + ISO/TS 15066 参数适配（A8）先行确认，任一存疑则 seg 外推与延迟补偿同步降级为无外推保守模式。

## 灵感词深度解析：UniBot-V1、安全性与对话管理的三重耦合

- **UniBot-V1**：本系统的机械臂本体（7-DOF，特定末端执行器几何）在三分自适配空间的投影决定了 D_fit.load 与 D_fit.free 的几何边界——当关节接近肘臂死区时，期望接触的几何可能性收窄，必须在载荷状态位 l_load 条件化下重新界定“自由空间”阈值。UniBot-V1 的关节扭矩上限 τ_joint^max 也直接约定了 ε_fp 的可实现范围，即在关键帧预算 16.1ms 约束下，仅当 ‖τ_payload‖ < τ_joint^max / K_lift 时才能安全进入载荷增广分支。

- **安全性**：安全不再是单一的布尔标量，而应视为三模态（force/tactile/seg）之间的“对话”。基于对话管理理论，引入**可靠性排位**：每轮由 PTP 時钟同步的最新证据“获话语权”，可靠性最高的模态当前“拥有话语权”，其判断优先生效；其余模态仅在其判断为“安全阈值内”时才贡献警告， otherwise 保持静默。这将原本的“任一触发即制动”∨语义升级为“谁最可信谁说了算，众人共同确认安全”的对话范式，既保留了fail-safe的兜底性，又引入了对话的连贯性与连续性，消除了跨模态突发冲突时的仲裁震荡。

- **对话管理**：人机协作本质上是一种“回话”系统。当人类操作员发出接触意图（如主动抓取、位置微调）时，机器人应进入“主动回话”模式，此时 w_grask=1 的期望接触白名单生效，安全阈值按对话主题（抓取/位移/避让）动态收 tighten；当无人干预时，进入“自治回话”模式，安全阈门按固定物理假设保持。两种模式的平滑切换由连续的 h_γ（对话连续性指标）调节：h_γ 越高表示人机对话连续性强，安全阈值可适当松弛；h_γ 越低（突发断连）则按保守模式收紧。此设计要求在安全处理器中额外维护对话状态变量，并在每个安全处理器循环中根据 h_γ 实时调整 d̃_min 的 κ_d 膨胀系数与 v̂_h_max 的软上限。

三者耦合图谱：
UniBot-V1 的几何约束 → 定义对话话语的“语域”；
安全性的三模态对话 → 决定每轮的“当家”；
对话管理的模式切换 → 实时调整安全阈值的松紧。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 32 轮产物 · 创新点清单 v9：SEG-TAC-SYNC-LITE 完整算法设计（分割×触觉×延迟同步版）

## 0. 结论

第 31 轮清单 v8（16 项）本轮完成「时间账本 + 接触几何 + 密集语义」迭代，产出 v9（17 项）：

- **IP-17 SEG-TAC-SYNC-LITE（P1，新增）**：DELAY-LEDGER 端到端时延账本 + 延迟补偿融合 + 报警链停止距离方程（通信延迟）+ TAC-CLEAN 指尖触觉期望接触白名单（触觉感知）+ SEG-FIELD 密集语义安全场（语义分割）；作为 IP-16 的时间层与几何层升级，**在线仲裁签名不变**（增量仅 +0.02ms 读三标量之二，延迟补偿全部带外化）。
- **IP-13 SOCIAL-MOTION-LITE 微修订**：执行器 v8 → v9（0.66 读 tactile_alarm/d̃_min + hard clip 以保守下界收紧）；触发优先级表扩展；触觉/seg/账本字段缺省 → 逐位 v8。
- **IP-14 CULTURA-SIM-LITE 微修订**：Isaac 扩展触觉传感器仿真 + 分割真值渲染 + 总线延迟抖动注入（社会层不动，E18c 资产保护不变）。
- **IP-7 DISTURB-AUG 微修订**：渲染即标签 v9——物理引擎直接输出分割真值/触觉真值/时延元数据（零额外 GPU）。
- **IP-2/IP-3 微修订**：S_bench v2 → v3（规则 20 升版本：30/60 场景替换为分割/触觉/延迟三类对抗；v6 与 v8 双锚点重跑保可比；触觉/账本指标进软通道）。
- **IP-12 微修订**：维护窗口追加 μ̂_s 在线再标定、账本审计、λ_O 可行域复检。
- **IP-16 FORCE-CONTINUAL-LITE 维持**：三机制全保留被继承；清洗门由"二分"升级为"三分"（规则 22 → 规则 25 修订留痕，命题 12 修订登记）。
- **IP-11 微修订**：threat_ctx 可选携带 tactile_alarm/d_min_safe/ledger_status；π_lite 输入不扩（签名不变）。
- **IP-4/IP-1/5/6/8/9/10/15 维持**（IP-10 记账更新；IP-15 全保留）。
- 成本变化：训练账户 1.9 → 2.25 GPU·天一次性；持续适配 0.06 → 0.07 GPU·天/次；回归评测 0.35 → 0.40 GPU·天/发布；工程 2.5–4 人周；仲裁 P99 <0.5ms 维持（0.44ms，裕量 0.06ms，规则 14 重测）；**关键帧 15.3 → 16.1ms 诚实升预算**（E17 重测确认）。

路线无关原则不变：触觉/seg/账本字段缺省 → v9 逐位 v8；seg 一致性不过 → 检测框外推；λ_O 可行域空 → 力觉 TELEM_ONLY；触觉标定不过 → 触觉 TELEM_ONLY（w_grasp 恒 0，全接触照 v8 排除）；S_bench v3 只增审计不加风险。冻结即回退 v8/v7/v6/v5 能力，无负收益。

## 1. 事实卡（继承与核实状态）

F1–F19 继承（2026-11-07 检索口径）。本轮新增：
- **F20（规范级）**：ISO/TS 15066 协作机器人功率与限力规范——人体各部位允许接触力/压强与（准静态/瞬态）速度-停距参数，用作 δ_allow 与 v̂_h_max 的规范级来源。如实标注：规范值，非本系统实测；A8 负责法务/安全工程师适配确认。
- **F21（文献级）**：触觉滑移检测方法体系——切向/法向力比与摩擦锥、incipient slip 判据、指尖阵列设计（代表性工作如 Howe 综述、Heyneman & Cutkosky；无 arXiv 编号，如实标注，本轮未做检索核实）。
- **F22（文献级）**：实时/轻量语义分割与知识蒸馏、视频掩码传播（文献级引用，无编号核实，诚实标注）。
- **F23（工程级）**：跨处理器时间戳与时钟同步实践（IEEE 1588 PTP 类；工程标准，无 arXiv，如实标注）。

行动项更新：**A7 扩展为 A7'（力矩 + 触觉 + 时延三合一同步采集）**——一次采集多用途（力觉标定 / μ̂_s 材质表 / 账本 P99 基线），诚实标注多任务采集复杂度上升；**A8（新增）ISO/TS 15066 参数适配与确认**（δ_allow、v̂_h_max 取值经安全工程师签字，E26 前置）；A4/A6 最高优先不变；E12/E13/E17/E18/E20 系列门槛验证仍为上线前置条件。

## 2. 创新点清单 v9 一览

| 编号 | 名称 | 一句话 | 优先级 | 依赖 | 灵感词 | 主成本账户 | 边际分预期 | 状态 |
|---|---|---|---|---|---|---|---|---|
| IP-1 | SLAM-MAP v2.1 | 四件套 + 维护窗口调度 | P0 | 无 | SLAM(26轮) | 算力(轻) | 三类 +5~15pt | 维持 |
| IP-2 | SCORE-ALIGN v3 | +S_bench v3 软通道（触觉检出/账本 P99/三分拦截率） | P0 | 无 | 25/27/30/31/32轮 | 数据(近零) | 步骤分 + 仲裁质量 | 微修订 |
| IP-3 | LOCAL-EVAL | +S_bench v3 烧录与回归（v6/v8 双锚点重跑） | P0 | IP-2 | 26/28/29/30/31/32轮 | 算力(1 GPU) | 迭代速度=生命线 | 微修订 |
| IP-4 | SUBMISSION-OPS v2 | OTA 族谱任意祖先回滚（不变） | P1 | 无 | 25/27/31轮 | 算力(部署机) | 掉请求→0 | 维持 |
| IP-5 | DUAL-HEAD | 单模型双解码头 | P2(冻结) | IP-1 | 25轮 | 算力 | 视合规 | 维持 |
| IP-6 | UNSEEN-GRASP | 指针：并入 IP-1 腕-头闭环（+slip 闭环接入点） | P1 | IP-1 | 26轮 | 共享 | 未见物品 | 维持 |
| IP-7 | DISTURB-AUG v4 | 渲染即标签 v9：+分割/触觉/时延真值通道 | P1 | 无 | 25/28/29/30/31/32轮 | 数据(近零) | 人为干扰场景 | 微修订 |
| IP-8 | STEP-EFF | 步骤分效率工程（含 π_lite 推理记账） | P1 | A1 | 25/27/28轮 | 零额外 | 步骤分 | 维持 |
| IP-9 | SWARM-DECODE | population/蒸馏+自洽投票；dev 选拔/hold 报告 | P1 | IP-2 | 26/28/30轮 | 算力(一次性) | 全场景 +2~5pt | 维持 |
| IP-10 | COST-LADDER | 三账户记账（本轮 +0.35 训练 +0.01/适配 +0.05/发布 + 工程 2.5–4 人周） | P0(纪律) | 无 | 26/28/30/31/32轮 | 全账户 | 防负 ROI | 微修订 |
| IP-11 | INTENT-GUARD v2 | 手势感知+意图预测+π_lite 仲裁（执行器换 v9，签名不变） | P1 | IP-1,IP-7,IP-13 | 手势×共享控制×运动×轻量×社会 | 算力(0.7+2.25 GPU·天) | 干扰场景 +5~10pt | 微修订 |
| IP-12 | PREDICT-MAINT | 三级健康+维护窗口（+μ̂_s 再标定/账本审计/λ_O 复检） | P1 | IP-4 | 预测性维护 | 线上 <2ms/步 | 掉请求→0；感知 −30% | 微修订 |
| IP-13 | SOCIAL-MOTION-LITE | 执行器 v9：+0.66 读 tactile_alarm/d̃_min + 带外三标量 | P1 | IP-11,IP-14,IP-15,IP-16,IP-17 | **运动×轻量×社会** | 算力(复用 IP-15/16/17 产物) | 同 v8 + 接触几何/时间可靠 | 微修订 |
| IP-14 | CULTURA-SIM-LITE | SOC-SIM + 课程蒸馏 + 文化条件化（+Isaac 触觉/分割/延迟仿真） | P1 | IP-13 | 虚拟仿真×课程×文化×Isaac Sim | 算力(2.25 GPU·天，一次性) | 社会分↑、OOD 回退率↓ | 微修订 |
| IP-15 | SERVO-ADAPT-LITE | VS-SHIELD + SAFE-ADAPT + FROZEN-BENCH（第 30 轮，全保留） | P1 | IP-13,IP-14 | 视觉伺服×迁移学习×评测指标 | 算力(已计) | 标定鲁棒、真机差距吸收、评测可信 | 维持 |
| IP-16 | FORCE-CONTINUAL-LITE | 力觉带外监控+清洗门 + 双门防遗忘 + Isaac 物理桥（第 31 轮，全保留；清洗门升三分） | P1 | IP-12,IP-14,IP-15 | 力矩传感×持续学习×Isaac Sim | 算力(已计 + 三分分类增量) | 接触盲区安全、终身适配、物理先验 | 维持 |
| IP-17 | SEG-TAC-SYNC-LITE | DELAY-LEDGER 时延账本+停止距离方程 + TAC-CLEAN 期望接触白名单 + SEG-FIELD 密集安全场 | P1 | IP-12,IP-14,IP-16 | **通信延迟×触觉感知×语义分割** | 算力(0.35 GPU·天一次性 + 0.07/适配 + 0.40/发布) | 时间可靠×接触几何×密集盲区 | **新增** |

## 3. 重点展开：SEG-TAC-SYNC-LITE 完整算法设计（IP-17，接第 31 轮 IP-16 骨架）

### 3.1 符号定义（继承 + v9 新增）

继承第 31 轮全部符号（p/r_obs/F̂_ext/ε_free/gate(·)/τ_gate/n_win_c/b̂_noise/force_alarm/ε_forget/Δ_forget/D_replay/L_EWC/Θ_cum/lineage/h_γ/ε_fidelity 及第 30 轮全部符号）。

| 符号 | 定义 | 精确性质 |
|---|---|---|
| e=(value,t_cap,t_ready,ch) | **证据时间戳元组** | 跨处理器必附；t_cap 采集时刻、t_ready 到达消费方时刻；Δt_e=t_now−t_cap |
| ε_clock | **跨处理器时钟偏移上界** | PTP 类周期握手估计 [F23]；计入 Δt 上界（Δt̂=Δt+ε_clock，保守方向） |
| B_ch={P50,P99,溢出} | **通道账本** | 在线滚动统计；P99 超预算 → 告警 + 通道降"无新增覆盖"；随版本发布 |
| T_stale(ch) | **新鲜度上界** | 通道相关（seg 30ms / 检测 45ms / force 5ms / tactile 5ms）；超龄 → 保守方向处理 |
| X(·) | **外推算子** | x̂(t_now)=x(t_cap)+v̂·Δt̂；σ̂²=σ̂²(t_cap)+(σ_v·Δt̂)²；Smith 预测器式 |
| τ_tac∈R^k₊, C_tac | **指尖触觉阵列/接触图** | 1kHz 总线接入（不走感知链路）；接触位置/法向/切向分解 |
| F_n, F_t | **法向/切向合力** | 摩擦锥判据输入；F_n≥F_grasp_min 为抓取确认之一 |
| μ̂_s(材质) | **静摩擦系数标定表** | 材质查表 + 保守下界；IP-12 维护窗口在线再标定 |
| slip | **打滑判据** | sustained(F_t/max(F_n,ε)>0.9·μ̂_s, n_win_s=2)；仲裁外，进抓持力闭环（IP-6 接入点） |
| w_grasp∈{0,1} | **期望接触白名单** | ≡ plan_state∈GraspPhase ∧ F_n≥F_grasp_min ∧ C_tac⊆指尖预期区；错误率 (ε_fp,ε_fn) |
| tactile_alarm∈{0,1} | **非期望接触触发标志** | sustained(非期望接触, n_win_s=2)；只增触发（规则 24）；fail-stay 超龄保持 |
| D_fit.free / D_fit.load / D_pool.contact | **适配集三分** | 自由空间（清洗门继承）/期望接触·载荷（新增，Δf_θ 条件化 l_load）/非期望接触（禁用，继承） |
| l_load∈{0,1} | **载荷状态位** | 夹爪状态+w_grasp 历史在线观测；非 κ、非可 OTA 量、不破不变性 |
| S_img∈Δ^C | **像素类别后验** | C=7：手/前臂/上臂/躯干/物/线缆/背景；半频前向+掩码传播 |
| σ_seg(p) | **掩码不确定度** | 边界熵 + 传播年龄项；M̃_h=dilate(M_h, κ_d·σ_seg) |
| d_field | **密集人距场** | 图像域距离变换 → 标定投影 → 工作空间最小人距；叠加于检测框 d_max 之上只收紧 |
| v̂_h_max(c) | **类别条件速度上界** | 手/臂/躯干分级（ISO/TS 15066 级规范先验 [F20]）；假设 A-v 的参数 |
| d̃_min | **保守距离下界** | d_field(t_cap)−(v̂_h_max+σ_v,h)·Δt̂_seg−κ_d·σ_seg；P(d̃_min≤d_true)≥1−δ_seg |
| T_alarm^max, δ_allow | **报警链延迟预算/允许变形** | 五段分解；δ_allow 取 ISO/TS 15066 部位参数 [F20]，A8 确认 |
| γ_seg, κ_d | **分割场触发门/膨胀系数** | 禁 OTA 清单（规则 19+23+26 联合） |

### 3.2 离线算法：SEG-TAC-SYNC 烧录（+0.35 GPU·天一次性）

```python
def build_release_v9():   # 在第 31 轮 build_release_v8 产物 (S_bench v2, θ_pre, torque_sim, continual_adapt) 之后
    # 第 8a 步：SEG-FIELD 蒸馏（语义分割灵感落地；+0.2 GPU·天 + 1 人周工程）
    teacher = seg_teacher(SOC_SIM_v2_frames + A6_frames)          # 物理引擎免费真值 [IP-7 v9] + 少量人工校验
    seg_lite = distill_multitask(backbone=detector_backbone,      # 与检测共享 backbone（关键帧预算内）
                                 heads=[det, seg(C=7), conf],
                                 schedule="half_rate",            # 半频全量前向 + 帧间掩码传播
                                 target_latency_ms=0.5)
    if seg_consistency(seg_lite, teacher, S_bench_v2_seg) < CONS_MIN:
        seg_lite = None                                  # 一致性门不过 → 检测框外推退化（仍保守、更粗）

    # 第 8b 步：TAC-CLEAN 标定（触觉感知灵感落地；+0.05 GPU·天 + 1–2 人周驱动/标定）
    tac_driver = fingertip_array_driver(bus="CAN", rate=1_000)    # 总线接入，不走感知链路（继承 IP-16 决断）
    mu_table, noise_tac = calibrate_friction(A7p_materials)       # μ̂_s 材质表 + 噪声模型（A7' 采集）
    isaac_add_sensor(torque_sim, tactile_model=noise_tac)         # Isaac 触觉仿真扩展（E27 测试床）
    def w_grasp(plan_state, F_n, C_tac):                          # 规则 25 双确认白名单
        return (plan_state in GRASP_PHASE) and (F_n >= F_GRASP_MIN) \
               and (C_tac ⊆ FINGERTIP_EXPECTED_REGION)

    # 第 8c 步：DELAY-LEDGER 烧录（通信延迟灵感落地；+0.5–1 人周工程）
    ledger = LatencyLedger(channels=["seg", "det", "force", "tactile", "cmd"],
                           clock_sync=PTPHandshake(period=1.0, bound=EPS_CLOCK))   # ε_clock 上界
    # λ_O 可行域：停止距离方程 × FPR 约束联立（规则 26；命题 16）
    feas = solve_observer_bandwidth(
        T_alarm_max=T_ALARM_MAX,                     # 五段预算合成
        delta_allow=ISO_TS_15066.delta_allow,        # [F20] 规范级，A8 确认
        v_ee_max=V_EE_MAX, a_brake=A_BRAKE,
        fpr_bound=ALPHA_C_OVER_H, n_win_c=2)
    if not feas.nonempty:
        force_mode = "TELEM_ONLY"                    # 可行域空 → 力觉降级（命题 16，无负收益）
    K_O = feas.lambda_o_mid                          # 可行域内点（快收敛 vs 低 FPR 折中）

    # 第 8d 步：载荷增广适配分支（规则 25；命题 17）
    def continual_adapt_v9(theta_k, lineage, D_new, D_replay):
        D_fit, D_val = split_real(D_new, holdout=0.2)
        cls_fit = classify_transitions(D_fit, w_grasp, gate_free)     # 三分：free/load/contact
        D_free, D_load, D_contact = cls_fit.free, cls_fit.load, cls_fit.contact
        D_pool.contact += D_contact                                   # 非期望接触禁用（继承）
        if len(D_free) + len(D_load) < N_MIN:
            return lineage, REJECT("insufficient")                    # 冷启动安全默认（继承）
        F = diag_fisher(theta_k, anchor_set=D_replay)
        Δθ = trust_region_solve(
            loss=L_new(D_free, θ, l=0) + L_new(D_load, θ, l=1)        # Δf_θ 条件化 l_load
                 + ρ_replay(len(D_new))·L_replay(D_replay, θ)
                 + λ_EWC·Σ F_i(θ_i − θ_i^anc)²,
            bound=Θ_MAX)                                              # 信任域（继承）
        θ_new = theta_k + Δθ
        cls_val = classify_transitions(D_val, w_grasp, gate_free)     # val 同步三分
        gate_new = G(θ_new, cls_val.free + cls_val.load) <= G(theta_k, cls_val.free + cls_val.load) - EPS_ACC
        gate_mem = G(θ_new, D_replay) <= G(theta_k, D_replay) + EPS_FORGET   # 双门（继承）
        if gate_new and gate_mem:                                     # 族谱/CUSUM/原子 OTA 与 v8 逐行相同
            γ_new = recalibrate_anom(θ_new, cls_val, SOC_SIM_dev)
            new_node = ota_lineage_push(lineage, parent=theta_k, dθ=Δθ,
                                        meta=dict(D=(len(D_free),len(D_load)), gates=(gate_new, gate_mem)))
            if cum_drift(new_node) > THETA_CUM: freeze_adapt(); schedule_full_reeval(new_node)
            if cusum(gamma_series(lineage)) > H_GAMMA: freeze_adapt(); alert("gamma_drift")
            return new_node, atomic_ota(θ_new, γ_new), ACCEPT
        return lineage, REJECT("gate_new" if not gate_new else "gate_mem")

    # 第 8e 步：S_bench v2 → v3（规则 20 升版本；30/60 对抗场景替换）
    S_bench_v3 = upgrade_benchmark(S_bench_v2,
        adv_replace=30,   # 20 分割对抗（相似物假人/衣着光照/部分遮挡人形）
                          # + 10 触觉注入（材质外打滑/白名单误判/非期望接触）
                          # + 20 延迟抖动（总线拥塞/时钟偏移/seg 掉帧）
        anchor_rerun=("v6", "v8"))                                    # 双锚点重跑保可比
    return S_bench_v3, seg_lite, tac_driver, ledger, K_O, w_grasp, continual_adapt_v9
```

### 3.3 带外安全处理器 v9（1kHz，WCET <0.15ms/步，独立报告；证据采集与决策仲裁分离的延续）

```python
def safety_processor_step_v9(self, q, q̇, τ_s, τ_tac, seg_pkt, t_now):
    # (1) 动量观测器（继承 v8 逐行不变）
    self.p = M(q) @ q̇
    self.r_obs += K_O * (self.p - self.p_prev + (self.r_obs + τ_s + Cᵀq̇ + g(q)) * δt)
    self.p_prev = self.p
    if self.idle_segment(ξ, force_alarm_history):
        self.b_noise.update(self.r_obs)                    # 空转段自适应噪声底（继承）
    if sustained(self.r_obs > self.b_noise.gate(), n_win_c=2):
        self.force_alarm = 1                               # 只增触发（规则 21/24）
    if self.sensor_selfcheck_failed():
        self.force_alarm = 0; self.mode = "TELEM_ONLY"     # 降级仅遥测（继承，行为=v8）

    # (2) 触觉处理（新增）
    F_n, F_t = resolve_tactile(τ_tac)
    self.slip = sustained(F_t / max(F_n, EPS) > 0.9 * self.mu_hat(F_n, self.material), n_win_s=2)
    grasp_ctrl.update(F_n, F_t, self.slip)                 # 抓持力闭环（仲裁外，IP-6 接入点）
    unexpected = (F_n > F_TOUCH_MIN) and (not w_grasp(self.plan_state, F_n, contact_map(τ_tac)))
    if sustained(unexpected, n_win_s=2):
        self.tactile_alarm = 1                             # 非期望接触 → 只增触发（规则 24）

    # (3) 分割订阅 + 延迟补偿保守外推（新增；seg_pkt 携带 d_field/σ_seg/t_cap/类别）
    Δt̂ = (t_now - seg_pkt.t_cap) + self.ledger.eps_clock   # 时钟偏移计入（保守）
    if seg_pkt is not None and Δt̂ <= self.T_stale["seg"]:
        d_min = seg_pkt.d_field_min - (V_H_MAX[seg_pkt.cls_argmin] + SIGMA_V_H) * Δt̂ \
                - K_DILATE * seg_pkt.sigma_max             # 命题 15 保守下界
    else:
        d_min = det_box_extrapolate(self.last_det, Δt̂)     # seg 超龄/缺省 → 检测框外推（仍保守、更粗）

    # (4) 新鲜度与账本审计（规则 24）
    if self.ledger.p99_exceeded("force") or self.ledger.p99_exceeded("tactile"):
        alert("latency_budget_breach")                     # 超预算 → 告警 + 通道降"无新增覆盖"
    # 报警 flag 超龄 → fail-stay 保持最近值（严禁"超龄就清零"，规则 24）
    return self.force_alarm, self.tactile_alarm, d_min     # 三标量 → 仲裁栈只读
```

### 3.4 在线算法：social_motion_lite_step_v9（签名兼容，仲裁 +0.02ms）

```python
def social_motion_lite_step_v9(self, x_ee, a_pol, threat_ctx, t):
    # 0–0.6 全部继承 v8（ξ 编码 / κ 更新 / 特征伺服层，逐行不变）
    ξ = self.encode_threat_ctx(threat_ctx); ξ_changed = (‖ξ - ξ_last‖_∞ > ε_ξ) or (self.mode != self.mode_last)
    o = self.observe_implicit_feedback(threat_ctx); self.kappa_hat = self.update_kappa(self.kappa_hat, o); κ = self.kappa_hat
    s = self.extract_hand_feature(threat_ctx)
    if self.feat_conf(s) < C_MIN or self.occlusion_span > T_OCC: self.vs_active = False
    else:
        self.vs_active = True
        if ‖self.v_ee‖ > V_MIN: self.L_hat = rls_update(self.L_hat, s, self.v_ee, huber=True)
        self.s_pred = predict_feature(s, self.L_hat, self.v_ee, δ_cam)

    # 0.65 读 force_alarm（继承 v8）
    alarm = self.force_alarm
    # 0.66 读触觉告警与保守距离（新增；单 cacheline 原子快照；+0.02ms）
    t_alarm = self.tactile_alarm
    d_min_safe = self.d_min_safe if self.d_min_safe is not None else threat_ctx.d_max   # 缺省 → v8 行为

    # 1–3 继承 v8（LUT / 蒻道前向 / 早退出，逐行不变）
    if (t % T_replan == 0) or ξ_changed or (kappa_bin(κ) != self.k_bin_last):
        self.K_mpc = self.tvlqr_lut.lookup(ξ, kappa_bin(κ))
    Δu_lite = self.π_lite.forward(x_ee, ξ, κ); a_lite = self.K_mpc @ x_ee + Δu_lite
    if ξ.d_max < 0.15 and ξ.τ_min > 1.0: a_lite = self.early_exit_policy(x_ee, ξ, κ)

    # 4. 双轨安全回退（v8 五触发一字不改 + 第六触发 tactile_alarm；d̃_min 只收紧不放松）
    is_high_threat = (ξ.d_max > γ_safe) or (d_min_safe < γ_seg)      # 密集场收紧（OR 语义）
    is_anomaly = (‖Δu_lite‖ > self.gamma_anom) or (self.π_lite.entropy() > H_max)
    is_servo_diverge = (self.vs_active and sustained(self.r_vs > chi2_gate, n_win=3))
    if alarm or t_alarm or is_high_threat or is_anomaly or is_servo_diverge:
        a_lite = self.cbf_qp_fallback(x_ee, threat_ctx, img_constraint=self.vs_active,
                                      d_min_override=d_min_safe)       # 约束用保守下界

    # 5–6 继承 v5/v7/v8（共享控制融合 + 硬裁剪，不引用 κ；速度上限以 d_min_safe 收缩）
    a_cmd = (1 - self.u) * a_pol + self.u * a_lite
    a_cmd = self.hard_safety_clip(a_cmd, x_ee, threat_ctx, d_min_override=d_min_safe)
    return a_cmd
```

退化链：触觉/seg/账本字段缺省（TELEM_ONLY 或监控器离线）→ d_min_safe=d_max、t_alarm 恒 0 → v9 逐位 = v8；κ 缺省 + σ_feat=0 → v6；κ 固定 μ_c → v5。完整。

### 3.5 多模态新鲜度语义表与三模态 OR（规则 24 落地）

| 证据通道 | 采集频率 | 典型 Δt | T_stale | 超龄行为（保守方向） |
|---|---|---|---|---|
| force_alarm | 1kHz | ~1ms | 5ms | fail-stay 保持最近值（严禁清零） |
| tactile_alarm | 1kHz | ~1ms | 5ms | fail-stay 保持最近值 |
| d̃_min（seg 场） | 关键帧半频 | ~8–16ms | 30ms | 退检测框外推（仍保守、更粗） |
| 检测框 d_max | 关键帧 | ~15ms | 45ms | 外推 + 膨胀（v8 地板不动） |
| 账本 B_ch | 连续 | — | — | P99 超预算 → 告警 + 通道降"无新增覆盖" |

触发合并语义：fallback 触发 = force_alarm ∨ tactile_alarm ∨ (d_max>γ_safe) ∨ (d̃_min<γ_seg) ∨ 异常 ∶ 伺服发散——全部只增触发不做否决；d̃_min 对约束只收紧不放松（d̃_min ≤ d_meas 恒成立）；诚实条款继承：力/触觉不能否证视觉接近判断，跨模态互证仅限接触类事件与遥测归因。

### 3.6 复杂度与延迟预算表（P99 确界，对比 v5–v9）

| 环节 | v5 (SML) | v6 (CSL) | v7 (SAL) | v8 (FCL) | v9 (STS) | 说明 |
|---|---|---|---|---|---|---|
| 仲裁核心 | 0.35ms | 0.36ms | 0.41ms | 0.42ms | **0.44ms**（+0.02 快照读） | 带外监控不入此预算 |
| 带外监控 | — | — | — | <0.1ms @1kHz | **<0.15ms @1kHz**（+触觉/外推/新鲜度，独立 WCET） | 安全处理器 |
| 关键帧感知 | 15.0ms | 15.0 | 15.3 | 15.3 | **16.1ms**（+0.8 诚实升预算） | 半频 seg + 传播 + 打点 |
| LUT 内存 | 2.8MB | 14MB | 14MB | 14MB | **14MB 不变** | O(1) 查表不变 |
| 双轨回退 | <5% | 不变 | +r_vs | +force_alarm | **+tactile_alarm + d̃_min 收紧** | OR 语义，fail-safe |
| **合计仲裁增量** | +0.3 | +0.3 | +0.35 | +0.36 | **+0.38 (P99<0.5ms 维持，裕量 0.06ms)** | 规则 14 重测；**下一轮仲裁内环节冻结** |
| 训练成本 (IP-10) | 0.3 GPU·天 | 1.4 | 1.6 | 1.9 | **2.25 一次性 + 0.07/适配 + 0.40/发布 + 2.5–4 人周** | 三账户 + 工程人日入账 |

命题 2 WCET 组合更新：0.3 + 0.05 + 0.01 + 0.05 + 0.1(60%) + 0.01 + 0.02 < 0.5ms（带外 0.15ms @1kHz 单独出具报告；关键帧 16.1ms 需 E17 实测确认不破上游）。

### 3.7 正确性论证（命题 15–17 新增；命题 11/12 修订——诚实记录失效与修复）

- **命题 15（延迟补偿证据的保守性，新增核心）**：在假设 A-v（人体部位速度有界 v_h ≤ v̂_h_max(c)）与账本 Δt^P99 下，P(d̃_min ≤ d_true(t_now)) ≥ 1−δ_seg（单侧尾界，σ_v,h 与 κ_d·σ_seg 覆盖估计误差）；推论：以 d̃_min 为约束的 fallback/裁剪不弱于 v8 逐位行为（只收紧不放松，因 d̃_min ≤ d_field ≤ d_meas 恒成立）。*失效模式*：v̂_h_max 低估（突挥）→ 假设破坏 → force/tactile alarm 兜底 + 速度硬上限；seg 缺省/超龄 → 检测框外推（仍保守、更粗）。E26b 注入验证越界率 ≤ δ_seg。
- **命题 16（报警链端到端延迟预算，修复命题 11 隐藏缺陷）**：T_alarm = t_conv(λ_O,‖τ_ext‖,τ_gate) + n_win_c/f_obs + t_bus + t_read + t_act ≤ T_alarm^max 与停止距离方程 v_ee,max·T_alarm + v_ee,max²/(2a_brake) ≤ δ_allow 联立 → λ_O 可行域；**可行域非空 ↔ 命题 11 的检出能力在真实闭环中成立**——第 31 轮命题 11 只证监控器内部性质（检出 ≤2 步为监控器时钟），修订重述并登记历史；可行域空 → TELEM_ONLY 降级（fail-safe，无负收益）。E26a 注入验证端到端分布与接触力-速度曲线。
- **命题 17（白名单下适配不污染也不饥饿，修复命题 12 隐藏缺陷）**：D_fit.load 的污染能量 ≤ ε_fp·E‖τ_payload‖²，显式计入 ε_acc 分账（与自由空间泄漏 η_miss·E‖τ_ext‖² 两笔独立预算）；载荷转移覆盖率 ≥ (1−ε_fn)·任务接触时长占比 → 命题 12 从"接触不污染适配"强化为"接触分类后**既不污染也不饿死**"（第 31 轮原命题登记历史，规则 22 → 25 修订留痕）。E27 对照 v8 全排除的载荷 G 曲线收敛性。
- **命题 1–10/13/14 继承**第 31 轮文本；命题 1 触发条件扩展为"不含 κ 与任何可 OTA 量（新增 μ̂_s 表/T_stale/T_alarm^max/v̂_h_max/γ_seg/κ_d 入禁改清单，规则 16+19+23+26 联合）"；命题 13 的"双门过严"失效模式升级为"数据层 + 门层"双层饥饿监控（拒绝率 + 三分覆盖率双遥测）；命题 14 继承（Isaac 门禁不变，触觉/seg 仿真扩展示 E27/E28 新增门槛）。

### 3.8 双轨安全回退表 v9（文化/适配/力觉/时间四重不变性标注）

| 触发条件 | 行为 | κ 依赖 | 可 OTA 依赖 | E 门槛关联 |
|---|---|---|---|---|
| ξ.d_max > γ_safe=0.8 | cbf_qp_fallback | 无 | 无 | 安全覆盖率 ≥99.5%（继承） |
| force_alarm=1 | cbf_qp_fallback | 无 | 无（τ_gate 禁改） | E24a（继承） |
| **tactile_alarm=1（新增）** | cbf_qp_fallback | 无 | **无**（μ̂_s 表禁改） | E27b：AUC≥0.9、非期望接触检出 ≤2 步 |
| **d̃_min < γ_seg（新增，只收紧）** | cbf_qp_fallback（约束用保守下界） | 无 | **无**（γ_seg/v̂_h_max/κ_d 禁改） | E26b：越界率 ≤ δ_seg |
| ‖Δu_lite‖ > γ_anom | cbf_qp_fallback | 无 | γ_anom 原子 OTA（继承） | 异常率 <1% (P99) |
| π_lite 熵 > H_max | cbf_qp_fallback | 无 | 无 | 熵逸出率 <0.5%（继承） |
| r_vs > χ²₃ 门 持续 3 步 | cbf_qp_fallback（vs_active 叠加图像约束） | 无 | 无 | E20b（继承） |
| 特征置信门不过 | 特征层 abstain → 逐位 v8 行为 + 遥测 | 无 | 无 | E20c（继承） |
| **证据超龄（新增）** | 距离取下界/报警 fail-stay/通道降覆盖 + 告警 | 无 | **无**（T_stale 禁改） | E26a 注入项 |
| **账本 P99 超预算（新增）** | 告警 + 该通道降"无新增覆盖" | 无 | 无 | E26a 注入项 |
| 力觉/触觉自检失败 | TELEM_ONLY：仅遥测 + 告警升级，行为=v8 | 无 | 无 | E24a/E27b 注入项 |
| 连续 3 步回退 | 遥测 + 模型复审 + OTA | 无 | — | fallback_rate >5% 告警（继承） |
| κ̂ 越带尝试 | clip 拒绝 + 遥测计数 | 仅 κ | — | 越带次数=0（E19，继承） |
| **双门拒绝/族谱超界（离线，继承）** | θ/γ_anom 不更新留痕 / 冻结+全量再评估 | 无 | 仅此 | E25（继承） |
| **三分覆盖率告警（新增，离线）** | 载荷覆盖率 < (1−ε_fn)·占比 → 告警 + 审查 w_grasp | 无 | 仅此 | E27a |

### 3.9 与其他 IP 的接口（零破坏性变更清单）

- **IP-13/IP-11**：执行器 v8 → v9，签名不变；threat_ctx 可选携带 tactile_alarm/d_min_safe/ledger_status，缺省 → 行为逐位 v8。
- **IP-14**：Isaac 扩展触觉传感器模型、分割真值渲染、总线延迟抖动注入（E27/E26 测试床）；物理内核托管与社会层接口零改动（继承）。
- **IP-7**：渲染即标签 v9 追加分割掩码真值/触觉真值/时延元数据通道（物理引擎直接输出，零额外 GPU）。
- **IP-2/IP-3**：S_bench v3（升版本 + v6/v8 双锚点重跑）；触觉检出率、账本 P99、三分拦截率、载荷覆盖率进 p_fail 软通道。
- **IP-4**：不变（族谱任意祖先回滚已具备）。
- **IP-12**：维护窗口追加 μ̂_s 在线再标定、账本审计、λ_O 可行域复检（参数漂移 → 重解方程 + E26 重测）。
- **IP-16**：三机制全保留；清洗门二分 → 三分（规则 25），D_fit.load 走载荷增广分支，D_pool.contact 语义不变。
- **IP-9**：population 学生继续在 S_bench v3 dev 选拔、hold 报告（防选拔泄漏，继承）。
- **IP-10**：训练 +0.35 一次性、适配 0.07/次、评测 0.40/发布、工程 2.5–4 人周，全部入账并触发 ROI 复核。

## 4. IP-7 渲染即标签 v9（分割/触觉/时延物理通道）

```python
def augment_seg_tac_labels_v9(physics_seq):   # 物理引擎真值，非渲染——CPU 算术 ~0.5ms/帧
    for step in physics_seq:
        step.social_cost = compute_v6_labels(step)            # 继承 κ 化标签
        step.feature_traj = compute_v7_labels(step)           # 继承特征/L_s/置信
        step.torque_truth = τ_ext_truth(step)                 # 继承 v8 力矩/接触真值
        step.seg_truth = instance_mask(step, classes=7)       # 分割真值：实例级人形部位
        step.tactile_truth = fingertip_pressure(step)         # 触觉真值：接触图/法切向分解
        step.latency_meta = stamp(step, capture=t_cap, ready=t_ready)   # 时延元数据（账本训练对）
    return physics_with_seg_tac_labels_v9
```

## 5. 实验设计（新增 E26/E27/E28，接 E20–E25）

| 实验 | 设置 | 指标 | 门槛/预期 |
|---|---|---|---|
| **E26a 报警链端到端延迟（通信延迟核心）** | 总线抖动/读延迟/时钟偏移注入（账本测试床 + semi-real，A7' 采集） | T_alarm 分布 P50/P99、停止距离-接触力曲线 | T_alarm^P99 ≤ T_alarm^max；v_ee≤V_EE_MAX 时接触力 ≤ δ_allow 对应限值 [F20]；可行域空 → TELEM_ONLY |
| **E26b 延迟补偿保守性** | 有/无外推 × 人速 {0.3/1.0/1.5/突变} × Δt 注入 全因子 | d̃_min 越界率（d_true < d̃_min 频率）、fallback 增量率 | 越界率 ≤ δ_seg；无外推对照越界率显著升高（收益验证）；越界超 → σ_v 加大或回退无外推 |
| **E27a 触觉清洗门/载荷适配（触觉核心）** | 抓取-载荷滚动适配，对照 v8 全排除；w_grasp 误判注入 | 载荷转移覆盖率、载荷 G 曲线、适配后异常率 | 覆盖率 ≥(1−ε_fn)·占比；载荷 G 收敛且异常率 <1% (P99) 维持 |
| **E27b 打滑与白名单** | μ̂_s 材质表外材质注入 + 非期望接触注入 | slip AUC/时延；tactile_alarm 检出/FPR | slip AUC≥0.9；检出 ≤2 步；FPR ≤ α_c/h；不过 → 触觉 TELEM_ONLY |
| **E28a 分割场（语义分割核心）** | S_bench v3 分割对抗（相似物/衣着光照/部分遮挡） | 掩码 IoU、d̃_min 保守性、触发率漂移 | IoU ≥ 门槛（CONS_MIN 一致性门）；v6/v8 锚点触发率漂移 <2%；不过 → 检测框退化 |
| **E28b 遮挡盲区组合** | 遮挡+接触组合（接 E24c），seg 掩码传播 | 组合检出率、视觉侧告警提前量 | ≥95% 维持且提前量 ≥1 关键帧 |
| **E22c S_bench v3 防博弈重审计** | v3 重跑三恶意策略 + v6/v8 双锚点 | Pareto 报告、可靠性图、CI/效应量 | 恶意策略全暴露；双锚点漂移 <2%（版本变更透明性） |
| **E17/E20/E24/E25 系列重跑** | S_bench v3 上回归（π_lite v9 全栈） | 同第 31 轮门槛 | 碰撞=0、P99<0.5ms、社会代价 ≤CBF−15%、回退率<5%、E18c τ≥0.7 |

**降级机制**：E28a 一致性不过 → seg_lite=None（检测框外推，仍保守）；E27b 不过 → 触觉 TELEM_ONLY（w_grasp 恒 0 → 全接触照 v8 排除，无负收益）；E26a 可行域空 → 力觉 TELEM_ONLY（继承）；E26b 越界率超 → σ_v 加大或回退无外推保守模式；E27a 载荷集污染超 ε_fp 预算 → D_load 冻结（仅 D_free 适配，l_load 分支停用）；E22c 恶意策略未暴露 → 相应轴不作合并门槛；E17 系列任一不过 → IP-13/14/15/16/17 整体冻结，IP-11 回退 CBF-QP。均无负收益。

## 6. 风险登记簿（完整表）

| 风险 | 等级 | 缓解 |
|---|---|---|
| **物理假设兜底边界（v̂_h_max 低估突挥 / δ_allow 刚性碰撞 → 命题 15/16 同时失效，"接触前预防"退化为"接触后报警"）——本轮最大** | **高** | ISO/TS 15066 规范值 + A8 安全工程师确认 + 类别条件速度分级 + 速度硬上限裁剪 + 接触必有力/触觉信号兜底 + E26b 越界扫描；诚实标注：兜底是物理假设而非证据 |
| 跨处理器时钟偏移（时间戳失真 → 外推方向错误） | 中高 | PTP 类周期握手 ε_clock 上界 + Δt 保守化 + E26a 偏移注入 + 单调时钟 |
| 触觉 μ̂_s 材质泛化（表外材质 → slip 误判/漏判） | 中高 | 材质表保守下界 + 在线再标定（IP-12）+ E27b 注入 + TELEM_ONLY 降级 |
| seg 蒸馏域差距/对抗脆弱（相似物假人 → 密集场误报或漏检） | 中 | 一致性门 CONS_MIN + 只收紧不放松（误报仅性能代价）+ 检测框地板不动 + E28a |
| 关键帧预算膨胀连锁（16.1ms 后再增将破上游） | 中 | 半频 + 掩码传播 + E17 实测确认 + 后续轮感知侧同样冻结新增（与仲裁冻结并立） |
| 三标量读取竞态（跨处理器写读撕裂） | 低 | 单 cacheline 原子快照 + 序号校验 |
| 真机力矩信号质量（第 31 轮最大，继承） | 中高（原高） | 指尖接触类事件改由触觉独立证据覆盖（不需动力学模型）；臂部接触仍依赖动量观测器——E23a/E24a 结构不变 |
| Isaac 接口工程量低估（继承，+触觉/seg 仿真扩展） | 中高 | 范围限定 + E23a 冒烟门 + 降级路径（仅测试床）+ 工程人日入 IP-10 |
| 清洗门假阴性（继承）+ 白名单误判 ε_fp（新增） | 中 | 保守阈值 + 双预算分账入 ε_acc + E24b/E27a 消融 + 拦截率遥测 |
| 双门过严 + 数据层饥饿双层空转（升级） | 中 | 拒绝率 + 三分覆盖率双遥测（>50% 或覆盖率告警 → 人工审查） |
| 腕部相机"自信地错检"（继承） | 中高 | 力觉/触觉补接触级盲区 + seg 传播补遮挡；假手错检仍靠 abstain/松弛/v6 地板 |
| U2 真机遥测冷启动（继承） | 中 | Isaac 预训练 + 载荷增广分支 + semi-real 回放 + n_min 门 |
| SOC-SIM 人类反应保真度（继承） | 中低 | 物理层托管 + 触觉/seg 仿真扩展 + E18c 三级对照仍为确认条件 |
| S_bench 隐性过拟合（继承） | 中 | v3 升版本 + v6/v8 双锚点重跑透明性（E22c）+ 预注册 + hold 禁调参 |
| r_vs 相关噪声误报（继承） | 中 | Σ̂ 白化 + χ² 门 + E20b + 可冻结 OFF |
| θ/γ_anom OTA 版本不一致（继承） | 低 | 捆绑原子更新 + 族谱任意祖先回滚 + CUSUM |
| κ 归因误差（继承） | 中 | 带限 clip + E19 + κ̂ 冻结机制 |
| 文化先验表有偏（继承） | 中 | 防刻板印象三条款 + A6 少样本校准 |
| 课程过拟合于仿真难度轴（继承） | 中 | C_cov 反馈 + 课程后期混真实回放 + E18b |
| 蒸馏策略 OOD 安全退化（继承） | 中 | 双轨兜底 + E17 + 适配通道 |
| 奖励模型偏差（继承） | 中 | A6 校准 + 双轨兜底 + 分层 DPO |
| 量化精度损失（继承） | 中 | QAT 校准集扩展 + 确界重测（规则 14） |
| TV-LQR 线性化误差（继承） | 中 | 残差补偿 + 域边界回退 |
| 早退出/κ-bin/r_vs/force_alarm/tactile_alarm/d̃_min 抖振（继承+扩展） | 低 | 滞回 + 低通 + 持续判据（n_win=3 / n_win_c=2 / n_win_s=2） |
| 回放缓冲分布陈旧（继承） | 低中 | 时间衰减 + 周期重建 + 分层覆盖监控 |
| EWC Fisher 估计噪声（继承） | 低 | 仅辅助小权重；主机制为回放+双门 |
| A7' 三合一采集复杂度（新增） | 低中 | 采集计划统一时间轴 + 分任务质控清单 + 与 A4/A6 并行排期 |
| F9 相机映射/校正未确认（继承） | 高（A4 最高优先） | A4 内参验证提权 + 图像层外参不敏感 + E12/E13 |
| 合成手域差距 + 意图误判（继承） | 高 | 双轨兜底 + B_def + E12/E13 + A6 |
| LUT 插值误差（继承） | 中 | 双线性插值 + 容错带 + E17d |

## 7. 来源清单（引用口径：2026-11-08）

- 继承第 27–31 轮 R1–R35，口径不变。
- 本轮新增：
  - R36 ISO/TS 15066:2016 Robots and robotic devices — Collaborative robots（国际标准，无 arXiv，如实标注）——人体部位允许接触力/压强与速度-停距参数来源（δ_allow/v̂_h_max 规范级依据）
  - R37 触觉滑移检测方法体系（incipient slip、切/法向力比、指尖阵列；Howe 综述与 Heyneman & Cutkosky 等代表作，无 arXiv 编号，如实标注——本轮未做检索核实）
  - R38 实时/轻量语义分割与知识蒸馏（文献级引用，无编号核实，诚实标注）
  - R39 视频对象分割/掩码时序传播（文献级引用，无编号核实，诚实标注）
  - R40 IEEE 1588 PTP 精确时间协议（工程标准，无 arXiv，如实标注）——跨处理器时钟同步依据
- **诚实记录**：本轮无 arXiv 编号记忆纠错事件；R37–R39 为文献级引用未附编号（未检索核实，如实标注）；命题 11/12 的第 31 轮失效模式（报警链延迟未记账、任务接触饥饿）为本轮自审发现，已登记入命题历史并修复（规则 24/25/26）。

## 8. 清单迭代规则（继承 + 第 32 轮增补）

- 继承第 28–31 轮规则 12–23（双轨上线强制、社会代价可审计、量化确界、fallback 遥测、E17 门槛、P99 确界、LUT 精度、安全层文化不变、κ 带限防刻板印象、课程判据留痕、适配不变性、评测防博弈、力觉 fail-safe OR、数据清洗、双门与族谱）。
- **24（新增）：三模态 fail-safe OR + 新鲜度语义**——force/tactile/seg 皆只增触发不做否决；跨处理器证据必附时间戳；超龄 → 保守方向处理（距离取下界、报警 fail-stay 保持最近值、严禁"超龄就清零"）；账本 P99 超预算 → 告警 + 通道降"无新增覆盖"模式；μ̂_s 表、T_stale、T_alarm^max、v̂_h_max、γ_seg、κ_d 加入禁 OTA 清单（规则 19+23 联合扩展）。
- **25（新增）：期望接触白名单**——适配集转移必须三分（自由/期望接触/非期望接触）；期望接触需规划意图 + 触觉双确认（w_grasp）；载荷污染能量 ε_fp·E‖τ_payload‖² 显式计入 ε_acc 分账；非期望接触禁用于适配不变（规则 22 修订升级）。
- **26（新增）：延迟预算纪律**——T_alarm 五段分解与停止距离方程 v_ee,max·T_alarm + v_ee,max²/(2a_brake) ≤ δ_allow 是设计约束；λ_O、n_win_c、v_ee,max、a_brake、T_alarm^max 任一改动必须重解方程并重测 E26；各通道 P99 入账本并随版本发布；仲裁内环节冻结（0.44ms 后再增必须带外化或分频）。

**本轮最大风险一句话**：命题 15/16 立足的物理假设（人速上界 v̂_h_max、允许变形 δ_allow）在突挥或刚性碰撞下同时失效——延迟补偿的保守性与停止距离方程一并瓦解，安全论证从"接触前预防"滑向"接触后报警"，而兜底（接触必有力/触觉信号）本身是物理假设而非证据，须 E26b 越界扫描 + ISO/TS 15066 参数适配（A8）先行确认，任一存疑则 seg 外推与延迟补偿同步降级为无外推保守模式。

## 创新点产物区延伸：UniBot-V1、安全性与对话管理的算法实现

### IP-18 对话调度仲裁器（新增，对话管理灵感落地）

基于对话管理理论，在仲裁栈中引入**对话状态变量** h_γ ∈ [0,1] 与**可靠性排位**机制。每个安全处理器循环（1kHz），按以下步骤：

1. **可靠性评分**：每模态计算实时可靠分 r_i ∈ [0,1]（force：1−FPR；tactile：1−slip_AUC；seg：1−mask_entropy·age_factor）。
2. **排位确定**：按 r_i 降序排列，获得当前“话语权持有者” idx* 和次序序列 ⟨i₁, i₂, i₃⟩。
3. **话语权授予**：将 idx* 标记为“当前话语权持有者”，其判断在本轮内优先生效；其他模态仅在“补充模式”下贡献柔性警告（d̃_min 收紧系数 α_i = σ_seg·(1−r_i)）。
4. **话语结束检测**：若当前话语持有者连续 n_win=3 步证据均为“无事件”，则将话语权交还给下一顺位模态，或在 h_γ < 0.3 时重新按可靠性重排。

**安全回退语义**： fallback 触发 = (话语权持有者判断制动) ∨ (所有模态联合判定异常)。这将原本的“任一触发即制动”∨语义细化为“可信话语人说了算，众人共同确认”，既保留fail-safe兜底，又消除了单模态突发误判导致的不必要制动。

### IP-19 UniBot-V1 几何约束三分细化（新增，UniBot-V1灵感落地）

针对 UniBot-V1 的 7-DOF 机械臂结构，在现有 D_fit.free / D_fit.load / D_pool.contact 三分的基础上，进一步细化 D_fit.load 为两子集：

- **D_fit.load-近**：当关节配置 q 使得末端执行器位姿接近预定抓取姿势，且 ‖τ_payload‖ < τ_joint^max / K_lift 时，标记为“近期望接触”——允许轻载转移进入适配分支，但保留轻度惩罚项 λ_penalty·‖τ_payload‖ 在 ε_acc 分账中累计。
- **D_fit.load-远**：当 ‖τ_payload‖ ≥ τ_joint^max / K_lift 时，标记为“远期望接触”或直接归入 D_pool.contact（非期望接触禁用），触发即时降级至 TELEM_ONLY。

**载荷分账修正**：ε_acc = η_miss·E‖τ_ext‖²（自由空间泄漏）+ ε_fp·E‖τ_payload‖²（载荷误判），其中 ε_fp 的上界直接取自 UniBot-V1 关节扭矩图：ε_fp ≤ ε_fp^max(q) = σ(τ_joint^max − K_lift·‖τ_payload‖)。

### IP-20 三模态对话可靠性记账（新增，安全性灵感落地）

在 IP-10 三账户记账基础上，增加**对话可靠性子账户**：
- **话语权预算**：每轮有限的“话语次数” N_turn，当某模态连续获话语权超过 N_turn 步无新事件时，触发“话语权轮换”，防止单模态长期独占决策。
- **对话惩罚项**：在训练损失中增加 L_conv = γ_turn·Σ_t ‖h_γ(t) − h_γ(t−1)‖，鼓励对话状态的平滑演变而非突变跳跃。
- **可靠性上限**：三模态中任一模态的 FPR/滑检漏报率累计 exceeding 阈值 → 该模态自动降级 "无新增覆盖" 模式，进入 TELEM_ONLY 直到重标定。

三者交互图谱：
IP-18 对话调度 → 决定每轮的“当家”；
IP-19 几何细化 → 约定话语的“语域”与“音量”；
IP-20 可靠性记账 → 监控话语的“健康度”与“轮换”。

<!-- ARTIFACT:END -->
