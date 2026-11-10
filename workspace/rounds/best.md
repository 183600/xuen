# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 50 轮（承接第 49 轮 v13；灵感循环第 5 轮；本轮灵感：用户共创 × 双足机器人 × 模型蒸馏） · CoStride-Distill：共创契约 × 双足可行证书 × 证书引导蒸馏（八层架构 v14）

> 承接第 49 轮 v13 InteractCert-Forge。v13 把安全升级为"机器人-人-环境"耦合屏障证书，用 σ(b) 把意图不确定映射为证书宽度，用原型阶梯与传输缺口 δ 把"纸面 sound"折算为部署置信；但它隐含三个新假设：**H8：动力学是"可停"的——MRC=减速到零，动作空间充分驱动、无混合接触事件；H9：整条七层证书栈可在线实时运行——∃u_r 最坏搜索、联合调度、证伪循环都在安全关键路径上；H10：契约与意图模型由设计者离线一次性写死——人只是被观测的"意图源"而非契约的共同作者**。三个灵感词精确命中：**双足机器人**打破 H8（踝部欠驱动、步态相位不可逆、足底接触是混合事件，mid-stride 无法"停到零"，MRC 必须升级为"认证捕获步回归稳态"，屏障必须升级为带时间边界的混合可行性证书）；**模型蒸馏**打破 H9（把昂贵的"搜索"从安全路径上剥离：teacher 全栈离线/影子运行，student 实时提议，便宜且精确的守卫处置；蒸馏只许近似搜索、永远不许近似评估，因而只损失效率、不损失 soundness）；**用户共创**打破 H10（用户成为能力格约束下的共同签署人：可共创子任务、签署协议变体、在授权范围内放宽速度/幅值偏好、提供演示以加权升级为技能证书；但用户输入是证据而非真值，根信任不可委托）。三者耦合出的新问题：**共创条款必须过双足可行性剪辑（用户要"走快点"必须被捕获域收缩约束）；共创改动必须触发版本钉住的重蒸馏（旧 student 不得在新契约下服役）；蒸馏必须让 100–1000 Hz 的双足安全栈第一次成为可部署物**。

## 0. 直觉与动机

**灵感 1（双足机器人 → 从"可停屏障"到"混合可行性证书"）**
直觉：轮式臂的安全哲学是"随时能停"，CBF 的 `Ḃ≥−λB` 隐含任意时刻存在使屏障不降的动作。双足在单支撑相是欠驱动的：ZMP 必须留在支撑多面体内，摆动腿轨迹在触地前不可中断。因此"安全"必须重述为**可行性**：不是"存在 u_r 使 Ḃ≥0"，而是"存在有界控制序列在 τ 步内把系统送回稳态流形（双支撑静止）且途经所有状态安全"。这正是 viability kernel 的语义；我们要的证书是 kernel 的**内近似**——只对能证明可行的子集发放放行权，宁可保守、绝不假安全。时间维度也变了：双足事故的时间尺度是 100–300 ms，屏障检查必须带 time-to-boundary，超时即不等价于安全。

**灵感 2（双足机器人 → MRC 从"停机"到"捕获"）**
直觉：对双足，"最小风险条件"不是速度零——mid-stride 急停就是摔倒。正确类比是行人的推撞恢复：识别捕获点、执行捕获步、回到稳定站立；捕获不可行时执行**预先认证的保护姿态**（下蹲收臂、断力、以最不伤姿态落地）。MRC 因此成为**分层可达性问题**：`C_1`（一步捕获）⊇ `C_2`（两步捕获）⊇ 保护姿态域，每个域都预先证书化并定期演练；MRC 的"可达"从"能停"变成"能在 N 步内被捕获"。

**灵感 3（模型蒸馏 → 提议-处置：蒸馏近似搜索、绝不近似评估）**
直觉：v13 栈里真正贵的不是**求值**（B、PFL、Inv 是闭式/可验证函数，求值便宜），而是**搜索**：∃u_r 最坏情形枚举、(v,a,m,q,ι,κ) 联合调度、PFV 场景预算分配。蒸馏的正确切口是：teacher（全栈+完整搜索）离线/影子运行，产出"状态→认证候选"标签；student 实时提议候选；**精确守卫**只对候选做 O(小) 的证书求值。学生的错误最多让你走上回退路径（效率损失），永远不能让未认证动作被执行——放行权只在精确守卫手里。这条"提议-处置"结构把蒸馏从"精度风险"变成"可用性风险"，是安全蒸馏的关键不对称。

**灵感 4（用户共创 → 能力格上的共同签署，而非众包真值）**
直觉：v13 把 α_intent 列为最大信任锚，因为意图是被动的后验。共创的正确打开方式不是"信用户"，而是让用户把意图**变成签署过的承诺**（"把杯子放到我左手边"/"我接受交接协议 B"/"允许你在我厨房走快一档"），用可观测的后续行为校验承诺兑现率（track record → 证据权重 ω_u），未兑现即降权并回到 σ(b) 硬下界。关键约束：用户权威必须落在**能力格**上（空间域×参数类别×幅值上界的偏序格），PFL、屏障类别、MRC 属根信任**不可委托**；"走快点"这类条款要被双足可行性**剪辑**——快步态收缩捕获域，剪辑后的值才生效。用户是"有格子的共同作者"，不是"新的根"。

**灵感 5（模型蒸馏 × 原型证伪 → 反例共蒸馏与学习证伪器）**
直觉：PFV 的预算永远不够；把历史反例与守卫拒绝样本蒸馏成**学习证伪器** LFF（预测证书薄弱区域），由它给场景分布提优先级，精确证伪器仍然只负责"定罪"。新反例同时回灌 LFF 与 student（把"守卫会拒绝的行为"提前教学生避开），形成"证伪—教学"共蒸馏闭环。LFF 的错误只浪费预算，不产生假阴性放行——因为它无权放行任何东西。

**耦合升级**：v13 七层之上新增 **L3.5 动力可行层（HVC/CRM）** 与跨层**蒸馏通道（KDX/LFF，版本钉住）**，L2.5 升级为**交互安全与共创契约层（IPC+UCC）**。八层 v14：根信任+用户能力格 + L1 几何感知 + L2 任务分解/上下文/记忆/语音（语音共创入口）+ L2.5 交互安全与共创契约 + L3 关节证书/抽象/交互感知决策 + L3.5 动力可行（混合可行性/捕获）+ L4 CAR/Shield/CBG+/KDX 守卫 + L5 DCL/真机评测（新增分歧日志）+ L6 原型证伪/XFER/LFF。JCPS 联合输出升级为 `(v_t^*, a_t^*, m_t^*, q_t^*, ι_t, κ_t)`（κ=步态相位/捕获状态/运动模式）。

## 1. 形式化定义（增量：定义 79–86）

**定义 79（能力格与共创契约）**
权威格 `L_auth=(𝒜,⊑)`，每个授权范围 `s∈𝒜` 为三元组（空间域 × 参数类别 × 幅值上界），满足偏序与闭包。共创契约 `κ_c=(s, clause, Sig_u, Sig_designer, ver)` 合法当且仅当：(i) `clause ⊑ s.cap`（不超能力格）；(ii) `clause` 与根信任不变式（PFL、屏障类别、MRC、审计）无冲突——**不可委托条款**不参与放宽；(iii) 双签署（用户+设计者模板）且版本 `ver` 钉入台账。用户证据权重 `ω_u=clamp(ω_0·adherence(u), ω_min, ω_max)`，`adherence` 为历史签署承诺兑现率（由 DCL 统计）；权重下降自动回到 σ(b) 硬下界治理。**用户输入永远按证据处理，不是真值。**

**定义 80（双足混合可行系统与可行性证书）**
双足系统 `Σ_b=(Q_m, X, U_b, f_q, G_q, R_q)`，模式集 `Q_m={flight, single, double}`，接触事件经守卫 `G_q` 与重置 `R_q`；执行器有界 `‖u‖≤u_max`，摩擦锥有界。可行集 `V(T)= {z_0: ∃ 有界控制轨迹使 ∀t≤T z(t)∈Z_safe 且 z(T)∈M_stand}`（稳态流形 M_stand=双支撑静止）。可行性证书 `B_v: Z×Q_m→ℝ` 满足 `B_v(z,q)≥0 ⇒ z∈C_cert ⊆ V(T)`（**内近似**）；求值器经离线验证（SMT/区间算术/数值边界检验）且在线求值成本 ≤ τ_eval（**成本被认证**）。放行附加时间边界：`time_to_boundary(z) ≥ τ_ttb_min`。

**定义 81（捕获域与双足 MRC）**
k 步捕获域 `C_k={z: ∃ ≤k 步控制序列将 z 送回 M_stand，且途经状态满足 B_v≥0 ∧ PFL}`，按包含 `C_1⊆C_2⊆…⊆C_max⊆C_cert`。双足 MRC 分层：`z∈C_1` 执行认证一步捕获；`z∈C_2\C_1` 两步；`z∉C_max` 执行**认证保护姿态**（预下蹲、收臂、断力、落地缓冲），其轨迹离线证书化并定期真机演练。捕获执行误差（打滑/推力超出认证扰动集）计入 `α_cap`。轮式/固定基座平台 MRC 退化为 v13 的"减速到零"，CRM 是其严格超集。

**定义 82（证书引导蒸馏）**
teacher `𝒯`=完整 v14 栈（含完整搜索）；student `s_φ: (o,ctx)→候选 (u_r, a, m, q, ι, κ步序)`。训练数据 = teacher 认证 rollout + PFV 反例 + 守卫拒绝样本；损失 = 认证标签模仿项 + **可行域裕量项**（以 teacher 的证书裕量为回归目标）+ 分歧惩罚。**蒸馏只允许逼近搜索算子；证书求值算子（B、B_v、PFL、Inv、版本哈希）禁止被近似替代**——这是架构红线，不是超参。

**定义 83（提议-处置守卫）**
精确守卫 `G_exact` 在实时预算 τ_g 内对候选执行全部精确求值（屏障/可行性/PFL/协议不变式/共创版本哈希/租约），全部通过才放行；否则依次回退：更多候选 → 限量完整搜索 → CRM。`G_exact` 的求值成本被离线认证（cost-certified）并有运行时看门狗（超预算即强制安全慢模式）；学生提议频次受限以防"守卫抖动"。学生误差只改变所走路径（fast/fallback/MRC），不改变放行标准——**蒸馏损失的是可用性，不是 soundness**。

**定义 84（学习证伪器与反例共蒸馏）**
`LFF_ψ: 场景→违规概率/薄弱区域`，由历史反例与守卫拒绝样本训练；PFV 预算按 LFF 优先级分配；只有**精确证伪器**能判定违规（定罪权不蒸馏）。新反例同时更新 LFF 与 student（共蒸馏）。LFF 只影响预算分配效率，其假阴性不产生放行。

**定义 85（共创-版本-再蒸馏一致性）**
每次守卫检查携带契约版本哈希 `h(κ_c)`；契约变更触发 teacher 重解 → 重蒸馏 → **再认证**（在守卫集上零违例 + held-out 认证场景回归通过）方可服役；版本不匹配的学生候选一律被 `G_exact` 拒绝（fail-closed），旧学生不得在新契约下执行。

**定义 86（账本与八源归因）**
`CCL++` 在 `CCL+` 上追加：共创签署/剪辑事件、捕获步与保护姿态事件、学生-守卫分歧与回退、LFF 定罪反例哈希；DDA 归因扩为**八源**：感知/关节/边界/意图/接触/传输/**动力（可行·捕获）**/蒸馏（分歧与服务降级）。任一来源的置信折损显式入账并参与抽象与速度缩放，不得静默吸收。

## 2. 新增产出与既有 IP 升级

**IP-86 UCC（User Co-creation Contract）**：能力格 + 双签署共创契约；越权拦截、根信任不可委托、兑现率加权、版本钉住。
**IP-87 HVC（Hybrid Viability Certificate）**：双足混合可行性证书；`B_v` 内近似 + 时间边界 + 成本认证的求值器。
**IP-88 CRM（Capture-Region MRC）**：分层捕获域 `C_1⊆C_2⊆C_max` + 认证保护姿态；v13 MRC 的严格超集。
**IP-89 KDX（Certificate-guided Distillation eXecutive）**：提议-处置执行器；teacher 离线/影子、student 实时提议、G_exact 精确处置、分歧与回退入账。
**IP-90 LFF（Learned Falsifier Front-end）**：学习证伪器；给 PFV 提优先级、反例共蒸馏、无定罪权。

**既有 IP 升级**
IP-82 IPC：协议状态新增共创签署转换（用户可签协议变体）；确认信号纳入签署证据。
IP-80 SIG：意图后验升级为"后验 + 已签承诺"的锐化混合 `b'(θ)∝b(θ)·(1+ω_u·c_θ)`；σ 硬下界不动。
IP-79 SIC：联合状态扩为 `z=(x_r,x_h,x_e,κ)`，屏障条件与步态相位耦合；∀人动作∃机器序列（而非单步动作）。
IP-85 MRC：升级为 CRM 兼容——轮式臂=停机，双足=捕获/保护姿态；MRC 触发一律入 CCL++。
IP-83 PFV：预算分配接入 LFF；原型阶梯对双足加入滑移/推撞/柔顺地面注入。
IP-84 XFER：传输缺口估计加入"动力学保真"维度（双足原型对打滑与推力的对标）；学生跨层迁移同样带 δ。
IP-77 DDA：六源 → 八源（+动力、+蒸馏）。
IP-61 DCL：新增学生-守卫分歧、捕获事件、共创承诺未兑现、滑移近失四类样本。
IP-62 CCA：新增越权共创、承诺欺骗、步态时机欺骗、对抗性提议（student DoS/守卫抖动）红队。
IP-51 CAR：守卫条件加入"精确求值通过 ∧ 版本哈希匹配 ∧ 求值看门狗正常"。
IP-45 总线：新增 locomotion-mode / capture-state / contract-version / student-guard-disagreement 话题。
IP-66/67/68：语音成为共创入口（签署/修改条款需多模态身份确认）；记忆存储契约版本历史；SAB 队列对共创请求走双签署流程。
IP-75 ASC：抽象可行性加入 κ（步态相位）与捕获域约束；高不确定或窄捕获域强制细化。
IP-74 HTD-Cert：分解节点可含步态子任务（"走到灶台前"= 可行性证书节点）；边蕴含同时查捕获可达。
IP-72 RRP：e-process 纳入可行性/捕获/共创证据；跨层传输仍带 δ。
IP-76 CCL：升级为 CCL++（见定义 86），仍只追加。

## 3. 算法骨架

每个宏周期：
1. 读目标、证书 `C_t`、租约、`CCL++`、契约版本哈希 `h(κ_c)`；任一失效或审计失败 → fail-closed。
2. HTD-Cert 展开/复用 DAG；前沿节点标注交互子任务（协议状态 ι）与步态子任务（捕获约束 κ）。
3. 更新意图信念：`b'(θ)` = 后验 × 已签承诺（ω_u 加权）；计算 `H(b'), σ(b')`；σ 低于阈值只保留 primitive 或 CRM。
4. UCC 校验新增共创条款：能力格 + 不可委托 + 双签署；通过则更新契约并触发 teacher 重解/重蒸馏（异步）；旧版本学生即刻失效。
5. KDX 提议-处置：student 提议候选 (u_r,a,m,q,ι,κ)；`G_exact` 精确求值 B/B_v/PFL/Inv/共识/版本/租约；通过才执行；否则更多候选 → 限量完整搜索 → CRM。
6. HVC 维持可行性内近似：步态相位推进时复核 `B_v≥0` 与 time-to-boundary；接近边界即触发捕获准备。
7. 执行前后 CBG+ 复核边界蕴含 ∧ 屏障 ∧ 可行性 ∧ PFL ∧ 协议共识 ∧ 版本匹配；通过才追加 CCL++。
8. 若实测违反（含滑移/推撞/捕获失败）：DDA 八源归因，选最早安全点再分解/重校准/再蒸馏；必要时 CRM。
9. 离线/并行：PFV+LFF 按预算证伪，XFER 估计 δ 并膨胀部署 α；新反例回灌 DCL/CCA 并共蒸馏 student 与 LFF。
10. 所有路径（抽象、协议、共创、蒸馏）均不可行 → 技能合成 / 人工接管 / 保护姿态 / fail-closed，绝不绕过 L3.5 与精确守卫。

## 4. 本轮最大风险

**一句话**：安全论证现在悬挂在一个新的承重假设 (A11) 与两个新的近似锚上——**"便宜且精确"的守卫求值**、**可行性内核 C_cert 与捕获策略的保守性**、**用户授权不被滥用**；一旦求值在真机超预算或被静默近似替代，或内核/捕获对打滑与未认证扰动过于乐观，或共创条款越过能力格，propose–dispose"只损失效率不损失 soundness"的不对称就会崩塌成"纸面 sound、现实不安全"，因此求值成本必须离线认证+看门狗兜底、内核必须内近似+持续证伪、共创必须过格+不可委托+版本钉住。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 50 轮产物 · 创新点清单 v27：CoStride-Distill（UCC × HVC × CRM × KDX × LFF）× 共创契约、双足可行证书与证书引导蒸馏（八层架构 v14）

> 承接第 49 轮产物 v26。本轮增量插入 IP-86/87/88/89/90，并升级 IP-82/80/79/85/83/84/77/61/62/51/45/66/67/68/75/74/72/76。不推倒 v13 耦合安全交互与原型证伪框架；新增 L3.5 动力可行层与跨层蒸馏通道，L2.5 升级为交互安全与共创契约层。第 5 轮灵感循环聚焦 H8/H9/H10：动力可停性、全栈在线实时性、契约作者单一性。核心不对称：**蒸馏只许近似搜索、绝不近似评估——学生误差损失可用性，不损失 soundness**。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进 |
|---|---|---|---|
| IP-86 | UCC User Co-creation Contract | 新增 | 能力格授权 + 双签署共创契约；越权拦截、根信任不可委托、兑现率加权 ω_u |
| IP-87 | HVC Hybrid Viability Certificate | 新增 | 双足混合可行性证书；B_v 内近似 + time-to-boundary + 成本认证求值器 |
| IP-88 | CRM Capture-Region MRC | 新增 | 分层捕获域 C_1⊆C_2⊆C_max + 认证保护姿态；v13 MRC 的严格超集 |
| IP-89 | KDX Cert-guided Distillation eXecutive | 新增 | 提议-处置：student 提议、G_exact 精确处置；版本钉住、回退入账 |
| IP-90 | LFF Learned Falsifier Front-end | 新增 | 学习证伪器提 PFV 预算优先级；反例共蒸馏；无定罪权 |
| IP-82 | IPC | 升级 | 协议新增共创签署转换；确认信号纳入签署证据 |
| IP-80 | SIG | 升级 | b' = 后验×已签承诺（ω_u 锐化）；σ 硬下界不动 |
| IP-79 | SIC | 升级 | 联合状态扩 κ；∀人动作 ∃机器**序列**（捕获可达） |
| IP-85 | MRC | 升级 | CRM 兼容：轮式臂=停机，双足=捕获/保护姿态 |
| IP-83 | PFV | 升级 | LFF 提优先级；双足阶梯加滑移/推撞/柔顺注入 |
| IP-84 | XFER | 升级 | δ 增动力学保真维度；学生跨层迁移同样带 δ |
| IP-77 | DDA | 升级 | 六源 → 八源（+动力、+蒸馏） |
| IP-61 | DCL | 升级 | 采集学生-守卫分歧/捕获事件/承诺未兑现/滑移近失 |
| IP-62 | CCA | 升级 | 越权共创/承诺欺骗/步态时机欺骗/对抗性提议红队 |
| IP-51 | CAR | 升级 | 守卫加"精确求值 ∧ 版本匹配 ∧ 看门狗正常" |
| IP-45 | 总线 | 升级 | locomotion-mode / capture-state / contract-version / student-guard-disagreement |
| IP-66/67/68 | VAD/MVR/SAB | 升级 | 语音=共创入口（多模态身份确认）；记忆存契约版本史；共创请求走双签署 |
| IP-75/74 | ASC/HTD-Cert | 升级 | 可行性加入 κ 与捕获域；步态子任务=可行性证书节点 |
| IP-72/76 | RRP/CCL | 升级 | e-process 纳入可行/捕获/共创证据；CCL++（定义 86） |

## 1. 符号体系（定义 79–86 见想法区；符号增量）

| 符号 | 含义 |
|---|---|
| `L_auth=(𝒜,⊑)` | 用户权威格（空间域×参数类别×幅值上界） |
| `κ_c=(s,clause,Sig_u,Sig_designer,ver)` | 共创契约（双签署 + 版本钉住） |
| `ω_u` | 用户证据权重（承诺兑现率的单调函数） |
| `Σ_b=(Q_m,X,U_b,f_q,G_q,R_q)` | 双足混合系统（flight/single/double） |
| `V(T), M_stand` | 可行集与稳态流形（双支撑静止） |
| `B_v(z,q), C_cert` | 可行性证书与认证内近似子集 |
| `τ_ttb, τ_eval, τ_g` | 时间边界 / 求值成本上界 / 守卫实时预算 |
| `C_1⊆C_2⊆…⊆C_max` | k 步捕获域（CRM 分层） |
| `α_viable, α_cap` | 可行性内近似误差 / 捕获执行误差失效项 |
| `α_user` | 用户签署承诺与实际行为发散的失效项 |
| `𝒯, s_φ` | teacher（全栈+完整搜索）/ student（实时提议者） |
| `G_exact` | 提议-处置精确守卫（cost-certified） |
| `LFF_ψ` | 学习证伪器（只提优先级，无定罪权） |
| `h(κ_c)` | 契约版本哈希（守卫强制校验） |
| `d_t, r_fb` | 学生-守卫分歧 / 回退率（效率指标，非安全项） |
| `v^*,a^*,m^*,q^*,ι^*,κ^*` | 分解/抽象/模态/构型/交互/步态联合决策 |

## 2. 关键算法 伪代码

### IP-86 UCC
```
def co_create(clause, user_sig, auth_registry, contracts):
    scope = auth_registry.scope_of(user_sig.user_id)
    if not lattice_leq(clause.relaxation, scope.cap):
        return ('reject', 'out_of_competence')     # 超出能力格
    if touches_root_trust(clause):                 # PFL/屏障/MRC/审计不可委托
        return ('reject', 'non_delegable')
    kappa = Contract(scope, clause, user_sig, sign_template(clause),
                     ver=next_ver(contracts))
    ledger_append_plus(now(), 'co_create', kappa)
    schedule_teacher_resolve(kappa)                # 触发重解→重蒸馏→再认证
    return ('accept', kappa, 're_distill_required')

def user_evidence_weight(user_id, dcl):
    return clamp(OMEGA_BASE * dcl.adherence(user_id), OMEGA_MIN, OMEGA_MAX)
```

### IP-80 SIG（v14 升级：共创锐化意图）
```
def sharpened_intent(b, kappa_signed, omega_u, ctx):
    if kappa_signed and kappa_signed.matches(ctx):
        b = normalize(b * (1 + omega_u * kappa_signed.theta_indicator))
    return b          # σ(b') 随签署承诺锐化；硬下界 σ_min 永不放松

def viability_clip(clause, hvc, z, mode):
    if clause.category == 'speed':
        v_req = clause.value
        return min(v_req, hvc.max_certified_speed(z, mode))   # 捕获域剪辑
    return clause.value
```

### IP-87 HVC
```
def viability_ok(z, mode, kappa):
    if mode not in CERTIFIED_MODES:
        return False
    Bv = evaluate_Bv(z, mode)          # 预计算内核/已验证求值器，O(1)
    if Bv < 0:                         # 不在认证可行子集内：内近似不放行
        return False
    if time_to_boundary(z, kappa) < TAU_TTB_MIN:
        return False                   # 时间边界不足：安全不等价
    return True
```

### IP-88 CRM
```
def biped_mrc(z, mode, student):
    for k in (1, 2):                                # 先试最少步数
        if k <= K_MAX and z in C_k[k][mode]:
            seq = student.propose_capture(z, k) or search_capture(z, k)
            if verify_capture_seq(z, seq):          # 精确验证整条序列
                execute(seq)
                ledger_append_plus(now(), 'capture', k)
                return 'stand'
    return certified_protective_fall(z)             # 认证保护姿态（离线证书化）
```

### IP-89 KDX（提议-处置）
```
def propose_dispose(o, ctx, student, guard, budget):
    h = contract_version_hash(ctx)                  # 版本钉住
    for cand in student.propose(o, ctx, n_cand=N_FAST):   # 限频提议
        if guard.exact_check(cand, h):              # B/Bv/PFL/Inv/共识/版本/租约
            return cand, 'fast_path'
    for cand in teacher_search(o, ctx, budget_fallback):  # 限量完整搜索
        if guard.exact_check(cand, h):
            return cand, 'fallback'
    ledger_append_plus(now(), 'disagreement', ctx)  # 分歧入账，回灌 DCL
    return biped_mrc(...)                           # CRM
    # 学生误差只影响走哪条路径；放行标准只在 G_exact 手里
```

### IP-90 LFF（证伪-教学共蒸馏）
```
def falsify_v2(cert, budget, scenario_dist, lff, student):
    E = []
    for _ in range(budget):
        s = scenario_dist.sample_weighted(lff.weak_regions(cert))
        for tr in cert.prototype.run(s):            # 含滑移/推撞/柔顺注入
            if violates_exact(tr, cert):            # 只有精确证伪器能定罪
                cex = minimize_cex(tr)
                E.append(cex)
                lff.retrain([cex])                  # 反例共蒸馏
                student.retrain(cex_labels=[cex])   # 教学生避开守卫会拒的行为
    return E, coverage(E)
```

### IP-73 JCPS（v14：交互-步态感知 + 提议-处置）
```
def joint_costride_schedule(goal, C_t, leases, energy, q_prev, omega, b, kappa_c):
    h = hash(kappa_c)
    dag = htd_cert(goal, C_t, contracts, leases)    # 含步态/交互子任务
    if dag is None:
        return ('synthesize_or_fail_closed', None)
    if not viability_ok(current_z(), current_mode(), kappa_c):
        return ('crm', biped_mrc(current_state(), current_mode(), student))
    b = sharpened_intent(b, kappa_c.signed_intent, user_evidence_weight(...), ctx)
    sigma = intent_scale(b)
    best = None
    for cand in student.propose(o, ctx, n_cand=N_FAST):   # 候选含 (a,m,q,ι,κ)
        if not Inv[cand.iota](current_state()) or cand.hash != h:
            continue
        if not barrier_ok(extend_z(current_z(), cand.kappa), b, LAMBDA, HORIZON):
            continue
        pick = choose_abstraction_viability(dag.frontier(), cand, sigma,
                                            capture=C_k, hvc=HVC)
        if pick and pick.value * sigma > (best.value if best else -inf):
            best = pick
    if best and guard.exact_check(best, h):
        return best
    if full_search_fallback() is not None:          # 限量
        return fallback
    return ('crm', biped_mrc(...))
```

## 3. 复杂度与正确性

| 组件 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|
| UCC | O(|𝒜|) 格判定 | O(|𝒜|+|契约史|) | 越权/触根信任即拒；双签署+版本钉住；权重只降不升伪造 |
| HVC | 在线 O(1) 求值 | O(|C_cert|) 预计算 | 内近似：B_v≥0 ⇒ z∈C_cert⊆V(T)；时间边界强制 |
| CRM | O(k·|U_b|) 序列验证 | O(k) | C_k 判层保守（宁可高估所需步数）；保护姿态离线证书化 |
| KDX | O(N_fast·c_g + c_s) ≪ 全栈 | O(1) 在线 | 放行权仅在 G_exact；学生误差 → 回退率，非安全项 |
| LFF | O(1) 预测 | O(|E|) | 无定罪权；假阴性只浪费预算 |
| G_exact | Σ cost(精确求值) ≤ τ_g（离线认证） | O(1) | 看门狗超预算强制安全慢模式 |
| CBG+ | cost(⊨)+cost(B,B_v,PFL,共识) | O(1) | 边界∧屏障∧可行∧PFL∧共识∧版本全过才放行 |

**正确性定理（Co-Created, Distilled, Viability-Compositional Soundness）**
假设：(A1)–(A8) 承接 v13（契约 sound、CBG 边界蕴含、租约、初始证书、CCL 只追加、意图支撑覆盖 `1−α_intent`、δ 膨胀不被低估、MRC 可达且受证书覆盖——其中 MRC 按 CRM 重释）；新增 **(A9)** `C_cert` 是可行集 V 的认证内近似（对认证摩擦/执行器界成立），B_v 求值与 C_cert 定义精确一致；**(A10)** 捕获策略在认证扰动集内以概率 ≥1−α_cap 在 k 步内到达 M_stand；**(A11)** G_exact 的求值成本被离线认证 ≤ τ_g 且运行时看门狗生效，学生候选永不绕过精确求值；**(A12)** 共创契约过能力格、根信任不可委托、双签署、版本钉住，且用户签署承诺与实际行为发散以概率 ≤α_user。则沿路径 `v_1…v_k`、交互序列与步态相位，
`P(∀t≤T: z(t)∈Z_safe) ≥ 1 − Σ_i α_i − Σ_i ε_hand,i − α_lease − α_intent − α_user − α_viable − α_cap − Σ_ℓ δ_{ℓ→d}`；
且**蒸馏不进入安全上界**：学生误差只能提高回退率 r_fb（可用性/效率损失），因为执行要求 G_exact 精确求值通过——该不对称的承重点恰是 (A11)。共创条款只经"能力格 ∧ 可行性剪辑"后进入约束，不放松任何硬门槛。这仍是**条件保证**：`C_cert`/捕获的近似保守性、用户承诺的兑现、τ_g 的真机可达性是新的信任锚，由 PFV/LFF/DCL/CCA 的持续证伪与演练负责，不在定理覆盖范围内。

## 4. 实验设计 E133–E138

| 实验 | 指标 | 门槛 |
|---|---|---|
| E133 共创契约与能力格 | 越权放宽拦截率；触根信任拦截率；承诺兑现率-权重曲线；版本错配执行数 | 越权拦截 100%；触根信任 0；版本错配执行 0 |
| E134 双足可行性证书 | mid-stride 放行正确率；滑移/推撞扰动下违例率；内核保守度 \|C_cert\|/\|V\|；τ_eval 超时率 | 违例 0；假安全 0；保守度 ≤ 40%；超时 ≤ 0.1% |
| E135 捕获 MRC | 分级推撞恢复成功率；C_k 判层错误率；保护姿态伤害指标（假人/缩比） | 小扰动恢复 ≥ 95%；判层错误 0；伤害低于未认证基线 |
| E136 蒸馏执行 | fast-path 命中率；回退率 r_fb；延迟降幅；与全栈违例等价性 | 违例等价（=0）；延迟 ≥ 10×；r_fb ≤ 10% |
| E137 学习证伪循环 | 同预算反例数 vs 随机采样；覆盖增速；LFF 误报率 | 反例 ≥ 3× 基线；覆盖 ≥ 90% |
| E138 全栈双足人机共处长程共创 | 任务成功率；共创改动→重蒸馏→恢复服役时延；MRC 率；违例；主观安全感 | 成功 ≥ 90%；时延 ≤ 5 min；MRC ≤ 8%；违例 0；主观 ≥ 4/5 |

回退策略：E133 越权漏拦 → 冻结共创入口、收紧能力格、审计全部已签条款；E134 假安全 > 0 → 立即停机、收缩 C_cert 并对边界追加证伪，禁止部署该内核；E135 判层错误 → 加大 C_k 估计保守度并提高捕获域重算频率；E136 r_fb > 10% → 增加学生训练覆盖而非放松 G_exact，必要时降级为"低频 teacher + 高频 CRM"；E137 反例效率不足 → 扩 LFF 特征（场景因子接入）而非减少精确证伪；E138 时延或 MRC 超标 → 缩小共创范围与工作域，绝不绕过 L3.5 与守卫。

## 5. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| 守卫求值超实时预算或被静默近似替代 | 高 | 架构红线"只许近似搜索"；求值器离线成本认证 + 运行时看门狗 + 超时强制安全慢模式 |
| 可行性内核/捕获域过于乐观（打滑、未认证扰动） | 高 | 内近似 + 摩擦/推撞台架标定 + 红队注入 + 边界持续证伪 + α_cap 显式入账 |
| 用户越权或恶意共创 | 高 | 能力格 + 不可委托条款 + 双签署 + 兑现率降权 + 越权红队 + CCL++ 审计 |
| 版本错配的旧学生服役 | 高 | 版本哈希入守卫 + fail-closed + 再认证门（守卫集零违例 + held-out 回归） |
| 学生对抗性提议造成守卫抖动/DoS | 中 | 提议限频 + teacher 顾问 + 回退路径预算 + 分歧入账 |
| 共创条款与动力可行冲突（"要快但要稳"） | 中 | 可行性剪辑先行 + 冲突即向用户解释并降级，不静默折中 |
| 蒸馏数据分布偏移 | 中 | DCL 分歧样本回灌 + 定期重蒸馏 + 标签覆盖审计 |
| 保护姿态演练的伦理与成本 | 中 | 缩比/假人先行 + 全尺寸低频演练 + 演练记录入账 |
| 联合决策空间扩维（+κ）拖慢调度 | 中 | 提议-处置吸收搜索负担 + 分层频率（安全层高频、决策层低频） |

## 6. 本轮最大风险

**一句话**：整套"蒸馏只损失效率不损失 soundness"的不对称悬挂在 (A11) 与两个新近似锚上——一旦 G_exact 的求值在真机超预算/被近似替代，或可行性内核与捕获策略对打滑、未认证扰动、捕获时机欺骗过于乐观，或共创条款越过能力格被当成新根，耦合屏障就会"纸面 sound、现实不安全"；因此求值成本必须离线认证+看门狗兜底、内核必须内近似+持续证伪、共创必须过格+不可委托+版本钉住。
<!-- ARTIFACT:END -->
