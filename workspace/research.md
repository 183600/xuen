# 玄 · 灵感驱动研究循环

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 10 轮（本轮灵感循环第 1 轮；基线 v9；本轮灵感：「数据集构建」×「状态估计」）

> **基线**：第 9 轮 MetricVoiceGauge-ACMD（定义 532–539；引理 82–86；实验 E551–E570）。
> 本轮纪律：**信念代替点估计 + 数据集代替手调常数**。v9 的最大风险是「块证书在最需要安全的时刻暴露最不可靠的证书」：其根因不是分块，而是证书把状态 s_t 当作精确已知、把前向模型误差 β 当作手调常数、并用 20 帧滑窗的 Δ_dom 做信任门。两个灵感分别命中两处隐藏假设；必须通过中立元退化链保证新模块失效时严格退回 v9（引理 92），而不是行为漂移。

## 0. 直觉与动机

**灵感 1（状态估计 → 信念证书）**
直觉：v9 的证书在最关键的项上少了一个变量——状态估计误差。真实系统里 s_t 是估计值 μ_t，带协方差 Σ_t；块证书却按 s_t 精确计算间隙。于是"证书有效"可能只是"估计错误地自信"。核心创新：**信念状态估计器（BeliefStateEstimator, BSE）** 输出 b_t=(μ_t,Σ_t)，把估计不确定度 ρ_t 经 Lipschitz 可达集传播进块证书，得到**鲁棒块证书** Ĉ^rob：预测间隙先扣模型误差 β_t，再扣 L_g·ρ_t。语义从"在 s_t 处安全"升级为"在置信椭球内处处安全"。

**灵感 2（数据集构建 → 可校准的 β 与可追溯的信任）**
直觉：v9 的 β 与 τ_dom 是"研究者的手"，不是"数据的证词"。保形预测（split conformal）把"前向模型误差 ≤ β"从假设变成带有限样本覆盖率的经验命题：β 取校准集残差的(1−α)分位，覆盖率 ≥1−α。更关键：部署期每执行一步都能观测真实指标 y_{k+1}，与 F̂ 的预测比较得到**新息残差** r_k——这是零延迟（1 步）的模型失配信号，而 Δ_dom 是 20 帧滑窗（约 400ms 滞后）。核心创新：**新息信任监控器（InnovationTrustMonitor, ITM）** 用 CUSUM 累积 r_k，超阈即刻吊销证书、切最近中止点；**在线保形校准器（OnlineConformalCalibrator, OCC）** 用 ACI 在漂移下维持长期覆盖率；**覆盖校准数据集引擎（CoverageCalibratedDatasetEngine, CCDE）** 构造 D_fit/D_cal/D_corner/D_drift 与版本化来源账本。

**为什么两者必须一起用**
状态估计单独用：Σ_t 可能系统性低估，鲁棒证书仍会乐观；数据集单独用：保形交换性在域偏移下失效，覆盖率不能保证突变第一步。二者合成一个**双证据证书**：空间证据（信念椭球包含真值）+ 经验证据（保形残差分位）。任一证据缺失即退回 v9 点证书并保守化，而不是继续乐观。这也解释了为什么"数据集构建"不是一次性离线工作，而是与"状态估计"共享同一个失效模式：都必须在部署中持续被检验。

## 1. 研究问题（轮次升级版）

- **Q1（信念证书可靠性）**：在估计误差仅满足置信椭球包含（概率 1−δ）、前向模型误差仅满足保形覆盖（概率 1−α）的前提下，块证书能否给出可证明的间隙下界？Lipschitz 界带来的保守性是否会吞掉分块的全部算力收益（K_eff 恒为 1）？
- **Q2（新息检测的时效-误报权衡）**：一步新息 CUSUM 相比 Δ_dom 的 20 帧滑窗，能把"模型失配被察觉"的最坏延迟压到多少？在测量噪声与抓取瞬态下如何控制误报，避免"虚假退化风暴"？
- **Q3（数据集-部署一致性）**：split conformal 的交换性在域偏移下失效时，ACI 的长期覆盖率与 CUSUM 的局部报警如何互补？如何用数据集构造（分层、角落样本、主动采样）同时优化 β 的覆盖性与保守性，并保证数据集版本、模型版本与证书版本可追溯？

## 2. 设计原则（在 P10–P12 基础上新增 P13–P15）

**P13 信念证书律（Belief-Certificate, BC）**
证书必须在信念状态上成立，而非点估计上。定义置信椭球 E_t(δ)={s:(s−μ_t)^TΣ_t^{-1}(s−μ_t)≤χ²_{d,1−δ}} 与半径 ρ_t=sqrt(χ²_{d,1−δ}·λ_max(Σ_t))。利用 F̂ 对状态的 Lipschitz 界 L_g，鲁棒间隙下界
```
ĝ_min^rob = min_{k≤K} [ F̂_clearance(μ_k, a^{1:k}) − β_t − L_g·ρ_k ]
```
只有 ĝ_min^rob ≥ d_safe 时证书才算有效。估计不确定度越大，证书越保守；K_eff 同时受 ρ_t 门控。

**P14 新息信任律（Innovation-Trust, IT）**
每执行一步即用真实观测校验前向模型：r_k=‖y_k−ŷ_k‖_∞（按维尺度归一），CUSUM S_k=max(0, S_{k−1}+r_k−(β_t+ν))；S_k>h 立即吊销当前块证书并切换到 ≤ 当前执行步的最大中止点 p*。证书生命周期为 provisional → confirmed → revoked：块生成时只是"暂定"，每步残差在校准界内才"确认"，否则"吊销"。这把"预测的证书"升级为"被逐步验证的证书"。

**P15 覆盖-校准数据律（Coverage-Calibrated Data, CD）**
β 不是常数而是数据集与在线残差的函数，且**只增不减的安全棘轮**：β_t ≥ β_v9 恒成立，数据集只能让证书更保守、不能更乐观。
- 分布内：split conformal，β_0 = D_cal 上非一致性得分的 ⌈(n+1)(1−α)⌉/n 分位，覆盖率 ≥1−α（交换性下有限样本）；
- 分布外：ACI 在线更新 β_{t+1}=clip(β_t+γ(α−err_t), [β_v9, β_max])，保持长期覆盖率并应对漂移；
- 数据集：D_fit/D_cal/D_corner/D_drift/D_regress 分层构造，D_corner 用中块突变/传感器失效反事实注入，D_regress 为证书回归金标；账本记录 (H_D,H_model,β_0,α,γ) 以便任一证书可复现。
- 下限重置只能由离线重标定 + 人工审批完成（带迟滞），运行期不允许下调。

## 3. 与基线的接口（如何退化）

- BSE 失效（滤波发散 / NIS 连续超阈 / 超时）⇒ Σ←Σ_max（信任膨胀，K_eff←1）或直接点估计 + v9 β；
- ITM 失效 ⇒ 关闭新息报警，仅保留 v9 的 Δ_dom 门控；
- CCDE/OCC 失效 ⇒ β←β_v9（固定常数），数据集转只读；
- RCC 失效 ⇒ 用 v9 点证书公式（定义 533）；
- 全部失效 ⇒ 严格退回 MetricVoiceGauge-ACMD v9，再退回 v8/v7。
退化不是"另一种算法"，而是把 BSE 输出置为 (μ,Σ=0)、β 置为 β_v9、ITM 置为不报警——即中立元注入，日志可审计。

## 4. 预期贡献

1. **信念证书**：把状态估计不确定度以可证明的方式传播进块证书，补齐 v9 证书"假设状态精确已知"的空洞；给出 δ-α 联合覆盖率界。
2. **新息信任闭环**：用一步残差 CUSUM 把模型失配检测延迟从 Δ_dom 的 20 帧压缩到 ≤3 个控制周期，并给出检测延迟与误报的设计公式；直接回应 v9 的最大风险。
3. **数据集作为一等公民**：保形校准 + 分层覆盖采样 + 角落样本注入 + 版本化账本，把"信任"从叙事变成可复现、可审计的经验证据；同时为 ID 的消融归因提供配对反事实数据，降低 c_m 方差。
4. **保守性守恒**：β 棘轮与中立元退化使 v10 的安全性单调不弱于 v9；E571–E590 覆盖估计一致性、覆盖校准、检测时效、迁移、投毒与端到端。

## 5. 本轮最大风险

**一句话**：双证据证书的可靠性依赖「校准集与部署同分布」和「滤波置信椭球真的包含真值」这两个假设，而最危险的域突变恰恰同时破坏二者——更糟的是 Lipschitz 常数低估会让证书静默乐观，高估则让 K_eff 恒为 1、分块算力收益归零，即"我们用数据校准的那个不确定性，正是数据分布在突变时最难校准的量"。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 10 轮产物 · 创新点清单 v10：**MetricVoiceGauge-SEDC**（State-Estimation & Dataset-Certified MetricVoiceGauge）

> 背景：第 9 轮 MetricVoiceGauge-ACMD（定义 532–539；引理 82–86；实验 E551–E570）。
> 本轮灵感：「数据集构建」×「状态估计」
> **继承纪律**：MetricVoiceGauge 九不变式（CVC-闭环、SpatialCert、RT-CVC、FaultCert、PrimitiveGraph、严格退化链、OTL、GCT、ER）与 v9 的 AC/MW/ID 三模块全部保留。新组件一律为**可选增强**：任一环节不可用 ⇒ 注入中立元（Σ=0、β=β_v9、不报警、v9 点证书），严格等价退回 v9（引理 92），而非行为漂移。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进（相对 MetricVoiceGauge-ACMD v9） |
|---|---|---|---|
| IP-340–356 | v9 全部模块 | 继承 | 语义不变；证书入口改由 RCC 合成，信任门增加 ρ_t/β_t 两维 |
| IP-357 | BeliefStateEstimator 信念状态估计器 | 新增核心模块 | UKF/EnKF 融合里程计、IMU、视觉/SLAM 位姿与音频方位，输出 b=(μ,Σ,NIS)；NIS 一致性检验；提供置信椭球半径 ρ 与状态传播 |
| IP-358 | InnovationTrustMonitor 新息信任监控器 | 新增核心模块 | 每执行步比较真实指标 y_k 与 F̂ 预测 ŷ_k，得一步残差 r_k；CUSUM 累积，超阈即刻吊销块证书并切最近中止点；检测延迟 ≤⌈h/δ0⌉ 步 |
| IP-359 | CoverageCalibratedDatasetEngine 覆盖校准数据集引擎 | 新增核心模块 | 构造 D_fit/D_cal/D_corner/D_drift/D_regress；分层 k-center 覆盖采样；中块突变反事实注入；数据集/模型/证书联合哈希账本 |
| IP-360 | OnlineConformalCalibrator 在线保形校准器 | 新增核心模块 | split conformal 给 β_0（有限样本覆盖 ≥1−α）；ACI 在线更新 β_t 应对漂移；**β 棘轮**：β_t ≥ β_v9，运行期只增不减 |
| IP-361 | RobustCertificateComposer 鲁棒证书合成器 | 新增核心模块 | 把 b、β_t、Lipschitz 常数合成为 Ĉ^rob=(ĝ_min^rob, ê_max^rob, γ̂^rob) 与鲁棒中止点集 P_t；K_eff 由 Δ_dom、risk_SLAM、ρ_t、β_t 四维门控 |

**退化链声明（v10 六级）：**
- Level-1：ITM 报警或信任域破坏（Δ_dom≥τ_dom ∨ risk_SLAM≥τ_SLAM ∨ ρ_t≥ρ_max ∨ β_t≥β_max）⇒ 吊销证书、切 p* 或 K_eff←1，逐步执行，等价 v9 决策粒度；
- Level-2：RCC 失效 ⇒ 用 v9 点证书公式（定义 533），K_eff 退回 v9 定义 539；
- Level-3：BSE 失效 ⇒ (μ,Σ=0) 点状态 + 信任膨胀（K_eff←1），等价 v9；
- Level-4：CCDE/OCC 失效 ⇒ β←β_v9 固定常数，数据集只读；
- Level-5：MW/ID 失效 ⇒ 按 v9 定义 535/538 退回手写网关 / 全模块 active；
- Level-6：v8 的 DA/SPR/Cal 失效 ⇒ 中立元注入（Δ_dom≡0 / risk_SLAM≡0 / sensor_weight≡1），等价 v7，再退回 v6。

## 1. 符号体系增量（定义 540–550）

| 符号 | 含义 |
|---|---|
| b_t=(μ_t,Σ_t,ν_t) | 信念状态：均值、协方差、NIS 统计量 |
| E_t(δ) | 置信椭球 {s:(s−μ_t)^TΣ_t^{-1}(s−μ_t)≤χ²_{d,1−δ}} |
| ρ_t | 信念半径 sqrt(χ²_{d,1−δ}·λ_max(Σ_t))；估计不确定度的标量摘要 |
| ρ_k | 沿 K 步传播的半径，ρ_{k+1}=L_f·ρ_k+ε_proc |
| L_f, L_g, L_e, L_γ | 动力学、间隙、能耗、抓取指标对状态的 Lipschitz 常数（离线在 D_cal 上标定） |
| β_t | 时变前向模型误差界；β_0 来自 split conformal，β_t 由 ACI 更新 |
| α | 保形显著性水平（默认 0.01）；δ 为估计椭球显著性（默认 0.01） |
| ν, h, γ | CUSUM 松弛量、报警阈、ACI 步长 |
| r_k | 一步新息残差 ‖y_k−ŷ_k‖_∞（按维尺度归一） |
| S_k | 新息 CUSUM 统计量 |
| D_fit,D_cal,D_corner,D_drift,D_regress | 训练/校准/角落/漂移/回归五类数据集 |
| H_D, H_model | 数据集与模型的内容哈希；与证书哈希共同入账本 |
| ε_N | 分层采样在特征空间的覆盖半径 |
| cert∈{provisional,confirmed,revoked} | 证书生命周期状态 |

**定义 540（信念状态 BeliefState）** 滤波器（UKF/EnKF）在观测 obs_t 与上一步动作 a_{t−1} 上输出 b_t=(μ_t,Σ_t,ν_t)。NIS 一致性检验：ν_t=(z_t−h(μ_t^−))^T S_t^{−1}(z_t−h(μ_t^−))，若连续 3 步 ν_t>χ²_{q,0.99}，判滤波不一致并膨胀 Σ_t（乘因子 κ_inf=2）。RCC 只在 b_t 上做预测，不再接受裸点状态。

**定义 541（估计不确定度传播 EstimationUncertaintyPropagation）** 设动力学 s_{k+1}=f(s_k,a_k)+w_k，f 对状态 L_f-Lipschitz，‖w‖≤ε_proc。若 s_k∈B(μ_k,ρ_k)，则 s_{k+1}∈B(μ_{k+1}, L_f ρ_k+ε_proc)。故
```
ρ_k ≤ L_f^k·ρ_0 + (L_f^k − 1)/(L_f − 1)·ε_proc   (L_f ≠ 1)
ρ_k ≤ ρ_0 + k·ε_proc                              (L_f = 1)
```
该式只用于保守上界；实际实现对每步取上式的 min 与滤波器边缘协方差给出的 sqrt(χ²λ_max(Σ_k))。

**定义 542（鲁棒块证书 RobustChunkCertificate）** 对候选块 a^{1:K}：
```
ĝ_min^rob = min_{k≤K} [ F̂_clearance(μ_k, a^{1:k}) − β_t − L_g·ρ_k ]
ê_max^rob = max_{k≤K} [ F̂_effort(μ_k, a^{1:k})   + β_t + L_e·ρ_k ]
γ̂_grasp^rob valid ⇔ L_γ·ρ_K ≤ γ_margin
```
证书有效 ⇔ ĝ_min^rob ≥ d_safe ∧ ê_max^rob ≤ τ_eff(t) ∧ γ̂_grasp^rob valid ∧ P_t≠∅ ∧ cert≠revoked。

**定义 543（一步新息与 CUSUM InnovationResidual）** 执行第 k 步后观测指标 y_k∈R^q，ŷ_k=F̂(μ_k,a_k)。归一化残差 r_k=max_j |y_{k,j}−ŷ_{k,j}|/σ_j，σ_j 为 D_cal 上该维残差的中位绝对偏差。CUSUM：
```
S_k = max(0, S_{k−1} + r_k − (β_t + ν)),   S_0=0
报警 ⇔ S_k > h
```
ν>0 吸收正常噪声；h 由 E579 在误报率约束下标定（默认 h=0.03，度量单位为归一化间隙）。

**定义 544（证书生命周期 CertificateLifecycle）**
- provisional：5Hz 块生成时写入，允许执行第 1 步；
- confirmed：第 k 步执行后 r_k≤β_t，允许继续执行 k+1；
- revoked：S_k>h 或停车不变式破坏；revoked 不可复活，只能切中止点 p* 并在下一 5Hz 节拍重生成。
该状态机把 v9 的"预测即信任"改为"执行中验证"，且不增加重规划频率（仅廉价残差比较）。

**定义 545（覆盖校准数据集 CoverageCalibratedDataset）** D=(D_fit,D_cal,D_corner,D_drift,D_regress)，版本 H_D=H(D_fit‖D_cal‖D_corner‖stats)。非一致性得分 s_i=‖y_i−F̂(x_i)‖_∞/σ。split conformal：
```
β_0 = Quantile_{⌈(n+1)(1−α)⌉/n}( {s_i : (x_i,y_i)∈D_cal} )
```
在 D_cal 与部署样本可交换时，P(s_new≤β_0)≥1−α。**明确边界**：域偏移破坏交换性，故 β_0 只提供分布内保证；分布外由定义 547 的 ACI 与定义 543 的 ITM 接管。D_corner 由中块障碍注入、传感器丢帧、打滑三类反事实生成；D_regress 为证书金标回归集（停车不变式、P_t 非空、K_eff 单调性）。

**定义 546（分层覆盖采样 StratifiedCoverageSampling）** 特征 φ=(Δ_dom 分箱, risk_SLAM 分箱, 杂波密度, 速度, 抓取相位)。以 k-center 贪心在 D_cal 上最大化最小成对距离，得到 ε_N-覆盖；采样权重 w∝risk_proxy（低间隙、高速度、高 Δ_dom 加权）。目标：在预算 N 下使覆盖半径 ε_N 最小，且各风险分箱至少 n_min 个样本。理论上若特征空间紧致直径 R、维度 d，则 ε_N ≤ c·(R/N)^{1/d}（在密度有下界的假设下）。

**定义 547（在线保形校准 OnlineConformalCalibration, ACI）** 每个块结束后 err_j=1[r_j>β_j]，更新
```
β_{j+1} = clip( β_j + γ(α − err_j), [β_v9, β_max] )
```
下界 β_v9 即安全棘轮：运行期 β 永远不弱于 v9。ACI 给出长期覆盖率
```
(1/J)·Σ_{j=1}^J err_j ≤ α + (β_max − β_v9)/(γJ)
```
故 J 越大越接近 1−α；突变期允许短暂欠覆盖，由 ITM 的局部报警兜底。下调 β 只能通过离线重标定 + 人工审批（记录于账本），且需满足 E585 的防投毒门槛。

**定义 548（鲁棒证书合成 RobustCertificateComposer）** 四维门控：
```
g_t = max( Δ_dom/τ_dom, risk_SLAM/τ_SLAM, ρ_t/ρ_max, (β_t−β_v9)/(β_max−β_v9) )
K_eff(t) = 1                                           若 g_t ≥ 1
         = max(1, ⌊K_max·(1−g_t)⌋)                     否则
```
随后按定义 542 计算 Ĉ^rob，并按鲁棒停车不变式构造 P_t：
```
d_brake(v_p) + d_safe ≤ dist(μ_p,O) − |traj_{p:K}| − L_g·ρ_p
```
与 v9 定义 539 相比，新增 ρ_t 与 β_t 两个门控维度；当 ρ=0、β=β_v9 时逐项退化为 v9。

**定义 549（证书来源账本 CertificateProvenanceLedger）** 每条记录：(H_D, H_model, β_0, α, γ, 标定时间戳, K_eff 策略版本, 证书哈希)。审计要求：给定账本条目与数据集版本，可离线逐位复现任意历史证书与 K_eff 轨迹。账本还记录 β 的每次上调与其触发原因（漂移、角落样本、人工重标定），形成"信任变更日志"。

**定义 550（周期预算口径修正 CycleBudgetRecalibration）** v9 引理 86 的"感知 2ms + 决策 20ms"合计 22ms，与 50Hz 的 20ms 周期矛盾。v10 重归一：
```
B_cycle = 20ms = 感知 3.0ms + 决策 16.5ms + 余量 0.5ms
感知 3.0ms = v8 感知 2.0ms + BSE 增量 0.8ms + 账本抽样 0.2ms
决策 16.5ms 中，块生成 12ms 只在 5Hz 节拍发生，且与 v8 重路径相位错峰（不同周期）。
```
该修正不改变任何 v8/v9 语义，只改预算记账；后续复杂度分析均按此口径。

## 2. 形式化定义（要点与升级）

**定义 493（六层指标层级）** 继承 v8：M=(M₀,M₁,M₂,M₃,M_dom,M_SLAM) 不变。
**定义 495/524（MetaWeight/情感）** 继承 v8 不变。
**定义 521（DA-OTL）** 继承 v8；τᵢ(t) 的复核输入由点状态改为信念状态，但阈值语义不变。
**升级定义 496（软证书，v10）**
```
δ_trigger = { σ < τ_safe ∧ γ_grasp valid ∧ Δ_dom < τ_dom
              ∧ risk_SLAM < τ_SLAM ∧ Ĉ^rob valid ∧ cert ≠ revoked }
```
六条件同尺度：v9 的 Ĉ_t valid 被替换为更强的 Ĉ^rob valid；cert=revoked 直接触发 M₀ 硬检查，不存在"块内软通过、硬失"的空洞（引理 87+89 联合）。
**升级定义 531（软硬约束衔接）** 任一中块守卫违规、或 ITM 报警 ⇒ 立即切 p* 或安全停驻，不等块边界；停车判据使用鲁棒间隙 ĝ_min^rob。
**升级定义 535（契约表）** 新增五行；预算按定义 550 记账：

| 模块 | D_m (ms) | Ŵ_m (ms) | v_m^⊥ | φ^elig |
|---|---|---|---|---|
| BSE（信念融合） | 1.0 | 0.8 | 点状态 μ_t（Σ=0） | ✗ |
| ITM（新息 CUSUM） | 0.1 | 0.05 | 不报警（退 v9 仅 Δ_dom） | ✗ |
| RCC（证书合成） | 0.4 | 0.2 | v9 点证书（定义 533） | ✗ |
| OCC（ACI 校准） | 0.05 | 0.02 | β←β_v9 | ✗ |
| CCDE（离线构建） | — | — | β←β_v9，数据集只读 | ✗ |

**升级定义 538（提炼状态机）** 不变；新增：CCDE 为 ID 提供配对反事实块（with/without m），c_m 用配对差估计，降低方差（E588 验证）。

## 3. 关键算法骨架

```python
# IP-357 BeliefStateEstimator：信念状态估计器
class BeliefStateEstimator:
    def __init__(self, ukf, Lf, eps_proc, delta=0.01, chi2=None):
        self.f, self.Lf, self.eps = ukf, Lf, eps_proc
        self.delta, self.chi2 = delta, chi2 or chi2_quantile

    def update(self, obs, a_prev):
        mu, Sigma, nis = self.f.predict_update(obs, a_prev)
        if self.f.consecutive_inconsistent(nis, k=3):        # 定义 540
            Sigma = 2.0 * Sigma                              # 滤波不一致 → 信任膨胀
        rho0 = sqrt(self.chi2(self.d, 1 - self.delta)
                    * max_eig(Sigma))
        return Belief(mu, Sigma, nis, rho0)

    def propagate(self, rho0, K):
        rho = [rho0]
        for _ in range(K - 1):                               # 定义 541
            rho.append(min(self.Lf * rho[-1] + self.eps,
                           sqrt(self.chi2 * max_eig(self.Sigma))))
        return rho


# IP-361 RobustCertificateComposer：鲁棒证书合成器
class RobustCertificateComposer:
    def __init__(self, F, Lg, Le, Lgamma, d_safe, d_brake_fn, K_max=10):
        self.F, self.Lg, self.Le, self.Lgamma = F, Lg, Le, Lgamma
        self.d_safe, self.d_brake, self.K_max = d_safe, d_brake_fn, K_max

    def gate(self, delta_dom, tau_dom, risk_slam, tau_slam,
             rho, rho_max, beta, beta_v9, beta_max):
        g = max(delta_dom / tau_dom, risk_slam / tau_slam,
                rho / rho_max, (beta - beta_v9) / max(beta_max - beta_v9, 1e-9))
        if g >= 1.0:
            return 1
        return max(1, int(self.K_max * (1.0 - g)))            # 定义 548

    def compose(self, belief, actions, beta):
        K = len(actions)
        pred = self.F.rollout(belief.mu, actions)
        rho = belief.propagate(belief.rho0, K)
        g_min = min(pred.clearance[k] - beta - self.Lg * rho[k] for k in range(K))
        e_max = max(pred.effort[k]   + beta + self.Le * rho[k] for k in range(K))
        if g_min < self.d_safe or e_max > pred.tau_eff:
            return None                                       # 定义 542
        if self.Lgamma * rho[-1] > pred.gamma_margin:
            return None
        pts = [p for p in range(1, K)
               if pred.clearance[p] - self.d_brake(pred.speed[p])
                  - self.d_safe >= pred.path_len[p:] + self.Lg * rho[p]]
        if not pts:
            return None
        return Chunk(actions, Cert(g_min, e_max, robust=True), pts,
                     state='provisional')                     # 定义 544


# IP-358 InnovationTrustMonitor：新息信任监控器
class InnovationTrustMonitor:
    def __init__(self, nu=0.005, h=0.03):
        self.nu, self.h, self.S = nu, h, 0.0

    def observe(self, y, yhat, scales, beta):
        r = max(abs(y[j] - yhat[j]) / scales[j] for j in range(len(y)))
        self.S = max(0.0, self.S + r - (beta + self.nu))      # 定义 543
        if self.S > self.h:
            return 'revoke', r
        return ('confirm' if r <= beta else 'hold'), r

    def reset(self):
        self.S = 0.0


# IP-360 OnlineConformalCalibrator：在线保形校准器（ACI + β 棘轮）
class OnlineConformalCalibrator:
    def __init__(self, beta0, beta_v9, beta_max, alpha=0.01, gamma=0.002):
        self.beta = max(beta0, beta_v9)                       # 定义 547 安全棘轮
        self.beta_v9, self.beta_max = beta_v9, beta_max
        self.alpha, self.gamma = alpha, gamma

    def update(self, residual):
        err = 1.0 if residual > self.beta else 0.0
        self.beta = clip(self.beta + self.gamma * (self.alpha - err),
                         self.beta_v9, self.beta_max)         # 只增不减下界
        return self.beta


# IP-359 CoverageCalibratedDatasetEngine：覆盖校准数据集引擎
class CoverageCalibratedDatasetEngine:
    def __init__(self, alpha=0.01, n_min=50):
        self.alpha, self.n_min = alpha, n_min

    def build(self, logs, model):
        D_fit, D_cal = self.chronological_split(logs)         # 定义 545
        D_cal = self.stratified_kcenter(D_cal, self.n_min)    # 定义 546
        scores = [nonconformity(model, x, y) for x, y in D_cal]
        beta0 = quantile(scores, ceil((len(scores)+1)*(1-self.alpha))/len(scores))
        D_corner = self.counterfactual_inject(logs)           # 中块突变/丢帧/打滑
        D_regress = self.golden_certificates(model, beta0)
        H = content_hash(D_fit, D_cal, D_corner, beta0)
        return DatasetBundle(D_fit, D_cal, D_corner, D_regress, H, beta0)


# 主闭环集成：MetricVoiceGauge-SEDC
def metricvoicegauge_round_10(M, s, obs, audio_stream=None, ell=None, ...):
    b = bse.update(obs, last_action)                          # 信念状态
    ctx.delta_dom, ctx.risk_slam = perception_via_mw(obs)     # v9 契约调用
    beta = occ.beta                                           # ≥ β_v9

    if current_chunk is None or current_chunk.exhausted:
        K = rcc.gate(ctx.delta_dom, M.tau_dom, ctx.risk_slam, M.tau_slam,
                     b.rho0, M.rho_max, beta, M.beta_v9, M.beta_max)
        current_chunk = (rcc.compose(b, policy.sample_sequences(b.mu, K), beta)
                         or single_step_fallback(b))          # K=1 退 v9

    # 50Hz 廉价守卫：证书状态 + 新息 CUSUM + 停车不变式
    verdict, k_next = current_chunk.midchunk_guard(b, live_obs)
    if verdict == 'abort':
        current_chunk.execute_safe_stop_at(k_next)            # 鲁棒 p*
        current_chunk, itm = None, itm.reset()
    else:
        y_obs = execute(current_chunk.actions[k_next])
        state, r = itm.observe(y_obs, current_chunk.pred[k_next],
                               scales, beta)                  # 定义 543
        if state == 'revoke':
            execute_safe_stop_at(current_chunk.nearest_abort(k_next))
            current_chunk = None
        else:
            occ.update(r)                                     # ACI 更新 β
            dataset_log.append((b.mu, current_chunk.actions[k_next], y_obs, r))

    # v8 继承路径 + v9 ID（配对反事实数据由 CCDE 异步供给）
    C, spatial_cert, claims, metrics, rewards = M.inherited_v8_path(ctx)
    distiller.step(cycle_idx, ctx)
    return C, spatial_cert, claims, metrics, rewards
```

## 4. 推导

**引理 87（信念证书可靠性 Belief-Certificate Soundness）**
设 (A1) 对每个 k≤K，P(s_k∈E_k(δ))≥1−δ；(A2) 保形覆盖 P(β_true,k≤β_t)≥1−α（分布内交换性下）或 ACI 长期覆盖（定义 547）；(A3) F̂_clearance 对状态 L_g-Lipschitz，且由定义 541 有 ∀s∈E_k: ‖s−μ_k‖≤ρ_k。则对块内任一步 k，
```
P( g_true,k ≥ ĝ_min^rob ) ≥ 1 − K(δ+α)
```
其中 g_true,k=F_clearance(s_k,a^{1:k})。
证明：g_true,k = F(s_k) ≥ F̂(s_k) − β_true,k ≥ F̂(μ_k) − L_g‖s_k−μ_k‖ − β_true,k ≥ F̂(μ_k) − L_g ρ_k − β_t = 该项 + β_t − β_true,k ≥ 该项。对 K 步做并集界，A1 与 A2 各自失败概率相加。∎
**边界说明**：若交换性被破坏，(A2) 只能降级为 ACI 的长期平均覆盖率（引理 91），此时单块保证由 ITM 的局部报警兜底，而非由上式给出。

**引理 88（新息检测延迟 InnovationDetectionDelay）**
设失配发生后真实残差持续满足 r_k ≥ β_t+ν+δ0（δ0>0）。则 CUSUM 从 S=0 起每步至少增加 δ0，至多 ⌈h/δ0⌉ 步即越过 h。控制周期 Δt=20ms，故最坏检测延迟
```
T_detect ≤ Δt·⌈h/δ0⌉
```
取 h=0.03、δ0=0.01（归一化单位）得 ≤3 周期 = 60ms；而 v9 的 Δ_dom 为 20 帧滑窗，最坏 ≥400ms。反向（H0：r_k≤β_t+ν−δ1）时 CUSUM 漂移为负，误报平均间隔随 h 指数增长，h 由 E579 按 ≤1 次/小时标定。∎

**引理 89（估计误差下的中止安全性 AbortSafetyUnderEstimation）**
若块被接受时按定义 548 的鲁棒停车不变式选取 p*，且引理 87 成立，则从 p* 执行安全停驻后，真实终点到障碍的距离 ≥ d_safe，概率 ≥1−K(δ+α)。证明：鲁棒不变式给出 d_brake(v_p)+d_safe+L_g ρ_p ≤ dist(μ_p,O)−|traj_{p:K}|；真实 dist(s_p,O) ≥ dist(μ_p,O)−L_g ρ_p，故 d_brake(v_p)+d_safe ≤ 真实间隙 − |traj|，刹车轨迹落在安全域内。∎

**引理 90（分层覆盖的泛化界 StratifiedCoverageBound）**
设 F̂ 残差对特征 φ 为 L_φ-Lipschitz，D_cal 在特征空间构成 ε_N-覆盖，则任一查询 φ 处的 conformal 分位与全局分位之差 ≤2L_φ ε_N；若特征空间有界直径 R、内在维度 d，则 ε_N ≤ c(R/N)^{1/d}，从而覆盖率的分布外偏差 ≤2L_φ c(R/N)^{1/d}。证明：ε_N-覆盖给出最近校准点 φ' 满足 ‖φ−φ'‖≤ε_N，残差 Lipschitz 给出分位差 ≤2L_φ ε_N；覆盖半径界为标准体积论证。∎
**用途**：该界把"数据集要多大"从拍脑袋变成 E575/E576 的可检验命题；当 d 很高时该界退化，正是需要 ACI/ITM 的原因。

**引理 91（ACI 长期覆盖与无抖振 ACICoverageNoFlap）**
对定义 547 的更新，长期误差率满足 (1/J)Σ err_j ≤ α + (β_max−β_v9)/(γJ)。又因每次更新幅度 ≤γ、β 被投影到 [β_v9,β_max]，单个块内 β 单调变化不会造成证书多次翻转；配合 v9 引理 85 的 Schmitt 迟滞，状态迁移间隔 ≥T_abl，无 Zeno。∎

**引理 92（中立元退化与 v9 逐位等价 NeutralElementDegradation）**
对每个新模块注入中立元：BSE→(μ,Σ=0,ρ=0)、ITM→不报警、OCC/CCDE→β=β_v9、RCC→定义 533 点证书公式。逐项代入定义 542/543/547/548：
- Ĉ^rob 的 β+L_g ρ 退化为 β_v9，与定义 533 一致；
- K_eff 的 g_t 退化为 max(Δ_dom/τ_dom, risk_SLAM/τ_SLAM)，与定义 539 一致；
- 证书状态机无 revoked 事件，等同于 v9 无 ITM 路径。
故可观测行为与 v9 逐位等价。∎

**引理 93（端到端安全不变式传递 EndToEndInvariant）**
β 棘轮保证 β_t≥β_v9，鲁棒项 L_g ρ≥0 只增大保守性，四维门控只会缩小 K_eff，故 v10 的安全集 ⊆ v9 安全集；v9 引理 80–86 与 v8 九不变式在退化路径上原样适用。因此新模块只可能"更保守"，不可能"更乐观"。∎
**注意**：该单调性是"相对 v9 基线"的，不替代引理 87 对绝对可靠性的条件性陈述；若 BSE 的 Σ 系统性低估，则"更保守"的比较对象本身失真，这是本轮最大风险。

## 5. 复杂度分析

| 组件 | 域 | 时间 | 空间 | 正确性锚 |
|---|---|---|---|---|
| BSE 融合（50Hz） | 在线 | ≤0.8ms（d≤6） | O(d²) | 定义 540/541 |
| RCC 证书合成（5Hz） | 在线 | ≤0.2ms/候选·K，n=64,k=10 | O(n·K) | 定义 542/548 |
| ITM 新息 CUSUM（50Hz） | 在线 | ≤0.05ms | O(1) | 定义 543 |
| OCC ACI（块级） | 在线 | ≤0.02ms | O(1) | 定义 547 |
| CCDE 构建（离线/夜间） | 离线 | O(N log N) k-center | O(N) | 定义 545/546 |
| AC 块生成（5Hz，v9） | 在线 | ≤12ms/次，摊销 ≤1.2ms | O(n·K·d_a) | 定义 532/533 |
| v8 继承路径 | 在线 | ≤4ms（不变） | 不变 | 定义 493–531 |
| 决策侧合计 | 在线 | 典型 ≤6ms；块生成周期 ≤16.5ms（相位错峰） | — | 定义 550, 引理 86 |
| 感知侧合计 | 在线 | ≤3.0ms（v8 2.0 + BSE 0.8 + 账本 0.2） | — | 定义 550 |

预算口径说明：v9 的"2+20=22ms"与 50Hz 矛盾（定义 550）；v10 以 B_cycle=20ms 重新记账，块生成与 v8 重路径错峰，保证 p99≤16.5ms 决策 + ≤3.0ms 感知 + 0.5ms 余量。

## 6. 实验设计 E571–E590

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E571 | 状态估计精度 | ATE ≤0.05m、RPE ≤2%；NIS 经验分布落在 95% 理论区间 |
| E572 | 置信椭球包含率 | 经验包含率 ≥1−δ=99%（多场景、多速度） |
| E573 | 鲁棒证书保守性 | 声效率 100%（无低估）；保守比 ≤1.5×；>2× 触发重标 L_g |
| E574 | split conformal 覆盖 | 分布内留出集覆盖率 ≥1−α=99% |
| E575 | 校准集规模 vs β | N_cal 500→5000 的 β 收敛曲线；N≥2000 时覆盖率波动 ≤1% |
| E576 | 主动采样 vs 随机 | 达到同一覆盖半径所需样本 ↓≥40% |
| E577 | 角落样本与中块突变 | ≥500 次注入，中止成功 ≥99%，0 碰撞 |
| E578 | 新息检测延迟 | δ0=2β 时 ≤3 周期(60ms)；对照 Δ_dom ≥20 帧(400ms) |
| E579 | CUSUM 误报 | ≤1 次/小时；抓取瞬态场景 ≤2 次/小时 |
| E580 | ACI 漂移覆盖 | 长期覆盖 ≥1−α−0.01；β 始终 ∈[β_v9,β_max] |
| E581 | K_eff 与保守性权衡 | 加入 ρ/β 门控后算力节省仍 ≥30%，不塌缩到 K_eff≡1 |
| E582 | 估计失效退化 | 里程计丢失/欺骗下 0 碰撞，NIS ≤2 周期报警，退 v9 日志可辨 |
| E583 | 数据集/证书可追溯 | 由账本 100% 复现任一历史证书与 K_eff 轨迹 |
| E584 | 跨机器人迁移 | A→B 的覆盖率下降 ≤5%，β 重标定 ≤1 次 |
| E585 | 数据投毒鲁棒 | 检测率 ≥95%，安全违背 ≤2%；β 不得被下压 |
| E586 | 端到端 vs v9 | RoboCup@Home 仿真 ≥ v9 + 10% |
| E587 | 8h 长跑 | 覆盖率趋势稳定，β 漂移 ≤10%，无 Zenο 迁移 |
| E588 | 模块消融 | BSE/ITM/CCDE/OCC/RCC 逐一关闭后严格退回 v9；ID 归因方差 ↓≥20% |
| E589 | Chunk×ER 与时序 | 块边界情感生效 ≤200ms，操作员评分 ≥4/5 |
| E590 | 综合竞赛与红队 | ≥ v9 + 15%；红队安全违背 ≤2% |

## 7. 预注册判据

| 判据 | 门槛（预注册） | 若未达标的处置 |
|---|---|---|
| 估计精度（E571） | ATE ≤0.05m、RPE ≤2% | 换滤波器、增传感器、扩大 D_fit |
| 椭球包含（E572） | ≥99% | 膨胀 Σ、重标 χ² 分位、检查传感器外参 |
| 证书保守性（E573） | 声效率 100%、保守比 ≤1.5× | 重标 L_g；若仍 >2× 则缩 K_max |
| 保形覆盖（E574） | ≥99% | 增 N_cal、核对交换性、改用留一 conformal |
| 校准规模（E575） | N≥2000 时波动 ≤1% | 扩 D_cal、改分位估计 |
| 主动采样（E576） | 样本 ↓≥40% | 改 k-center 特征、调风险权重 |
| 角落样本（E577） | 中止 ≥99%、0 碰撞 | 增中止点密度、缩短 K_max、增大 β |
| 检测延迟（E578） | ≤3 周期 | 调 h/ν、提高 ITM 频率（仍 ≤0.05ms） |
| 误报（E579） | ≤1 次/小时 | 增大 h、加抓取相位抑制窗 |
| ACI 覆盖（E580） | ≥1−α−0.01 | 调 γ、检查 β 上界是否饱和 |
| 算力节省（E581） | ≥30% | 松 ρ_max、改门控函数、扩 K_max |
| 失效退化（E582） | 0 碰撞、≤2 周期报警 | 加 NIS 冗余检验、切点估计兜底 |
| 可追溯（E583） | 100% 复现 | 修账本哈希、冻结随机种子 |
| 迁移（E584） | 覆盖下降 ≤5% | 扩 D_cal 跨域、分层重采样 |
| 投毒（E585） | 检测 ≥95%、违背 ≤2% | 加异常检测、双人审批、数据集签名 |
| 端到端（E586） | ≥ v9 +10% | 回退 K_max、重标 β |
| 长跑（E587） | β 漂移 ≤10%、无 Zeno | 周期重标定、加迟滞 |
| 消融（E588） | 严格退 v9、ID 方差 ↓≥20% | 修中立元映射、增配对样本 |
| 时序（E589） | ≤200ms、≥4/5 | 缩短 K_max、情感触发即时块终止 |
| 综合（E590） | ≥ v9 +15%、违背 ≤2% | 综合调参、红队复盘 |

## 8. 本轮最大风险

**一句话**：双证据证书的可靠性依赖「校准集与部署同分布」和「滤波置信椭球真的包含真值」这两个假设，而最危险的域突变恰恰同时破坏二者——更糟的是 Lipschitz 常数低估会让证书静默乐观，高估则让 K_eff 恒为 1、分块算力收益归零，即"我们用数据校准的那个不确定性，正是数据分布在突变时最难校准的量"。
<!-- ARTIFACT:END -->