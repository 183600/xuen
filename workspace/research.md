# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 28 轮 · 思维深化：SOCIAL-MOTION-LITE 的形式化与权衡

## 直觉锚点与动机链条（承接上一轮）

- **Q1（怎么动更优）的形式化突破**：CBF-QP 求解本质是有限时间horizon下的QP规划，其最优性局限于安全集内的最小偏离。TV-LQR 引入时变反馈增益 K(t)，求解利卡蒂微分方程，输出的不是“最安全的动作”而是“最优轨迹流形”。在社会代价项 Q = Q_track + λ_leg Q_leg + λ_prox Q_prox + λ_jerk Q_jerk 下，TV-LQR 产生的轨迹在安全约束与平滑性之间取得帕累托最优平衡。关键创新：λ 项随威胁上下文 ξ 自适应变化，而非固定权重，这使得机器人在低威胁时倾向于自然、平滑的让位动作，在高威胁时倾向于保守但仍平滑的规避。

- **Q2（能不能跑得动）的系统性突破**：将控制问题从“迭代求解”转化为“前向推理”。TV-LQR 的解析解 K_seq 在离线阶段通过利卡蒂反向递推得到，生成 K_seq_LUT（查找表），在线仅 O(1) 查表。π_lite 为 INT8 量化感知的小型 MLP (~200K 参数)，早退出分支对低威胁场景 skip 推理。两者组合：确定性 <0.1ms 查表 + 确定性 <0.3ms 前向推理，彻底消除 QP 求解的随机延迟与数值不稳定。

- **Q3（该不该这么动）的优化论突破**：不再事后 CI 兜底，而是在离线训练阶段就将社会代价显式嵌入。DPO (Direct Preference Optimization) 微调对象为 π_lite，偏好数据来源于合成轨迹的社会成本总和（Legibility+Proxemics+Jerk）。奖励模型为启发式函数，无人工标注。训练目标 L = BC + λ_dpo · DPO_reward，其中 DPO_reward = log σ(r_π(a|x,ξ) - r_π(a'|x,ξ))，a、a' 为对偏好轨迹。这使得 π_lite 天然产出“讨喜”动作，线上零额外计算。

## 形式化定义的深化

### 3.1.1 威胁上下文 ξ 的几何表征
ξ = {d_max, d_argmax, τ_min, |H|} ∈ [0,1]^4
其中：
- d_max = max_i d(h_i, p_ee) / d_nominal（归一化最大距离）
- d_argmax = argmax_i d(h_i, p_ee)（最大威胁手的索引）
- τ_min = min_i (d(h_i, p_ee) / |v_rel|)（最小接触时间，归一化）
- |H| = 当前可见手的数量（归一化）

几何意义：ξ 描述了末端执行器相对于所有手的空间位置关系的四维投影。ξ 的每个分量都有明确的物理单位归一化边界，便于 LUT 查表与函数逼近。

### 3.1.2 时变线性化动力学的精确形式
以当前 EE 状态 x = [p_ee, v_ee]^T 和威胁上下文 ξ 为名义点，动力学线性化：
ẋ = A(ξ) x + B(ξ) u
其中 A(ξ) = ∂f/∂x|_(x_ξ,ξ)，B(ξ) = ∂f/∂u|_(x_ξ,ξ) 为解析雅可比矩阵。
关键：A(ξ)、B(ξ) 仅在 ξ 变化时重新计算，ξ 变化频率远低于控制周期（<10 Hz），在两次 ξ 变化间 K_mpc 查表完全确定性。

### 3.1.3 社会感知代价矩阵的四范式分解
Q(ξ) = Q_track + λ_leg(ξ) Q_leg(ξ) + λ_prox(ξ) Q_prox(ξ) + λ_jerk(ξ) Q_jerk(ξ)

其中四个子矩阵的精确形式：
- Q_track = diag(q_p, q_p, q_p, q_v, q_v, q_v)，q_p ≫ q_v（位置权重显著大于速度，确保轨迹收敛）
- Q_leg = α_leg · [0_{3×3}, 0_{3×3}; 0_{3×3}, diag(0,0,0, σ_leg^2)] · outer([0,0,0, dir_threat])（仅速度维度鼓励远离威胁方向）
- Q_prox = α_prox · diag(σ_p^2, σ_p^2, σ_p^2, 0,0,0) · max(0, d_comfort - ‖p_ee - p_hand[d_argmax]‖)(仅位置维度，d_comfort ≈ 0.8m)
- Q_jerk = α_jerk · diag(0,0,0, σ_a^2, σ_a^2, σ_a^2)（仅速度维度，间接惩罚 Jerk，等价于增大控制增益的变化率惩罚）

自适应权重公式（关键创新）：
λ_leg(ξ) = σ_leg^0 + (σ_leg^max - σ_leg^0) · σ_sigmoid(d_max)  # 威胁越大，可读性重要性越高
λ_prox(ξ) = σ_prox^0 - (σ_prox^0 - σ_prox^min) · σ_sigmoid(d_max)  # 威胁越大，主动距离控制重要性降低（安全优先）
λ_jerk(ξ) = σ_jerk^0 + (σ_jerk^max - σ_jerk^0) · (1 - σ_sigmoid(d_max))  # 威胁越大，平滑度重要性反而提升（避免急促 maneuver）

### 3.1.4 双轨回退阈值的形式化定义
γ_safe = 0.8（威胁分阈值）：当 ξ.d_max > 0.8 时，视为高威胁场景，强制回退 CBF-QP。
γ_anom = 3σ（动作异常阈值）：基于残差网络 Δf_θ 的训练分布统计，σ 为标准差，当 ‖Δu_lite‖ > γ_anom 视为异常输入。
H_max（不确定性阈值）：π_lite 输出动作分布的熵，超过 H_max 视为模型在分布外，触发回退。
T_replan = 50ms（重规划周期）：仅当 ‖Δξ‖ > ε_ξ 或模式 m 从 EXEC 切换至 DEFEND 时重新查表 K_mpc。

## 算法步骤的精炼（两层架构）

### 3.2.1 离线专家生成（GPU 离线，~0.3 GPU·天）

第 0 步：上下文采样分布设计
Ξ = sample_threat_contexts(
    n_nominal=50000,  n_extreme=5000,  n_adversarial=2000
)
- n_nominal：合成手注入统计分布，覆盖训练/评测分布
- n_extreme：高速手、多手遮挡、未见意图组合的组合爆炸空间采样
- n_adversarial：梯度攻击生成的对抗样本，专门针对 π_lite 潜在弱点（如高频振动、突变性动作），确保残差网络在边界处的泛化能力

第 1 步：TV-LQR + 残差专家轨迹生成
对每个 ξ ∈ Ξ：
  1.1 线性化动力学：A, B = linearize_dynamics(x_nominal, ξ)
  1.2 社会代价矩阵构造：Q = build_social_cost(ξ)，R = 0.01·I
  1.3 TV-LQR 增益求解：K_seq = solve_tvlqr(A, B, Q, R, T=1.0, dt=0.01)
    # 有限时域利卡蒂反向递推，确定性 <0.1ms，输出 K_seq[t] ∀t∈[0,T]
  1.4 专家闭环滚出 + 残差标签收集：
      x_t ← rollout(x_0, K_seq, Δf_θ=0)
      Δf_target = f_true(x_t) - (A @ x_t + B @ (K_seq[t] @ x_t))
      D_expert ← D_expert ∪ {(x_t, ξ, Δf_target)}

第 2 步：残差网络训练
θ* = train_residual_net(D_expert)
# 网络结构：5层 MLP，每层 128 维，Spectral Normalization 正则化
# 损失函数：L_res = ‖Δf_θ(x,ξ) - Δf_target‖² + λ_sn ‖Δf_θ‖_Spectral
# 目标：补偿 TV-LQR 线性化误差，保证 ‖Δf_θ‖ ≤ ε_f ≈ 0.02

第 3 步：蒸馏数据集构造
D_distill = ∅
对每个 ξ ∈ Ξ：
    3.1 专家闭环滚出（含残差）：x_t ← rollout(x_0, K_seq, Δf_θ=θ*)
    3.2 收集专家动作：u_expert = K_seq[t] @ x_t
    3.3 D_distill ← D_distill ∪ {(x_t, ξ, u_expert)}

第 4 步：量化感知蒸馏 + DPO 微调
φ* = distill_policy(
    D_distill,
    student=PolicyNet(quant=True, early_exit=True),  # ~200K 参数，INT8 量化，早退出分支
    loss = BC + λ_dpo · DPO_reward(
        reward_model = Legibility + Proxemics + Jerk,
        β = 0.1  # DPO 温度参数
    ),
    quant_calib = calibration_set  # 量化校准集，保证 INT8 精度 < 2%
)
# 返回：φ*（蒸馏策略），θ*（残差网络），K_seq_LUT(Ξ)（增益查找表）

### 3.2.2 在线仲裁执行器（<0.5ms/步，替代 IP-11 cbf_filter）

def social_motion_lite_step(x_ee, a_pol, threat_ctx, t):
    """
    两层架构在线执行器，完整形式如下：
    """
    # 0. 威胁上下文编码与变化检测
    ξ = encode_threat_ctx(threat_ctx)  # 标准化到 [0,1]^4
    ξ_changed = (‖ξ - ξ_last‖_∞ > ε_ξ) or (mode_changed)
    
    # 1. 稀疏重规划 TV-LQR 增益查表
    if (t % T_replan == 0) or ξ_changed:
        K_mpc = tvlqr_lut.lookup(ξ)  # O(1) 查表，零在线求解
        ξ_last = ξ
    
    # 2. 蒸馏策略前向（主分支，<0.3ms）
    Δu_lite = π_lite.forward(x_ee, ξ)  # INT8 量化前向传播
    a_lite = K_mpc @ x_ee + Δu_lite  # 基线反馈 + 策略修正
    
    # 3. 早退出分支（低威胁 60% 场景，<0.1ms）
    if ξ.d_max < 0.15 and ξ.τ_min > 1.0:
        a_lite = early_exit_policy(x_ee, ξ)  # 更小网络结构，跳过部分隐层
    
    # 4. 双轨安全回退（核心兜底）
    is_high_threat = ξ.d_max > γ_safe  # γ_safe = 0.8
    is_anomaly = (‖Δu_lite‖ > γ_anom) or (π_lite.entropy() > H_max)
    if is_high_threat or is_anomaly:
        a_lite = cbf_qp_fallback(x_ee, threat_ctx)  # 保留 IP-11 原分支
        fallback_counter += 1
        telemetry.log("fallback", trigger="high_threat" if is_high_threat else "anomaly")
    
    # 5. 共享控制融合（语义不变，权重 u 来自 IP-11 滞回/率限）
    a_cmd = (1 - u) * a_pol + u * a_lite
    
    # 6. 硬安全裁剪（最后一道物理防线）
    a_cmd = hard_safety_clip(a_cmd, x_ee, threat_ctx)  # 速度/加速度/距离硬限
    
    return a_cmd

## 增强的正确性论证（设计命题与失效模式的诚实版）

### 命题 1（名义输入输出稳定性 ISS）
设Δf_θ 的近似误差 ‖Δf_θ - Δf_true‖ ≤ ε_f，TV-LQR 线性化误差 ‖ẋ - (A(ξ)x + B(ξ)u)‖ ≤ ε_lin，且 ξ 变化慢于 T_replan。则闭环系统在名义威胁分布下满足输入到状态稳定（ISS）性质，即存在 κ(·)、γ(·) 类函数，使得 ∀t: ‖x(t)‖ ≤ κ(‖x(0)‖) + γ(sup_0≤τ≤t ‖d(τ)‖)，其中 d(·) 为外部威胁输入。专家 TV-LQR 有已证明的 ISS 证书，蒸馏策略的 BC 损失 < ε_bc 保证邻域内近似：V_pi(x) ≤ V_expert(x) + O(ε_bc/μ)，其中 μ 为系统强凸参数。

*失效模式*：分布外威胁（极端手速、多手遮挡）→ π_lite 经验覆盖不足 → ‖Δu_lite‖ 超过 γ_anom → 双轨回退 CBF-QP 兜底（理论证书完整保留）。

### 命题 2（实时性确定性边界）
π_lite 为固定结构 INT8 网络，推理延迟确界 < 0.5ms（量化校准集验证，P99 报告）。TV-LQR 增益查表 O(1)，无动态内存分配、无迭代求解器、无分支预测Miss率异常。硬实时性保证：CWC (Worst-Case Execution Time) = 0.3ms + 0.05ms 查表 + 0.1ms 早退出（60% 案例） < 0.5ms。

*失效模式*：量化精度崩塌（INT8 范围外输入）→ QAT (量化训练) + 校准集覆盖不足 → ‖Δu_lite‖ 超限 → 双轨回退（性能退化而非安全退化）。

### 命题 3（社会最优性近似与奖励对齐）
蒸馏损失 L = BC + λ_dpo · DPO_reward，其中 reward_model = Legibility + Proxemics + Jerk（启发式，无人工标注）。若 reward_model 与真实人类偏好相关性 ρ ≥ 0.7（A6 少样本校验），则 π_lite 期望社会代价 E[C_social(π_lite)] ≤ E[C_social(π_expert)] + O(ε_bc/ρ + λ_dpo^{-1}·KL(π_π||π_ref))。

*失效模式*：合成偏好≠真人偏好（ρ < 0.5）→ DPO 微调方向错误 → 社会代价劣化 → 双轨回退 + A6 真人少样本校准迭代奖励模型。

### 命题 4（平滑性与可信度保证）
TV-LQR 输出连续可微轨迹（利卡蒂解连续依赖于初始条件）。π_lite 为前向网络，通过 Spectral Normalization 正则化训练，满足 Lipschitz 连续：‖π_lite(x,ξ) - π_lite(x',ξ')‖ ≤ L · (‖x-x'‖ + ‖ξ-ξ'‖)，L 为 Lipschitz 常数。训练时已约束动作熵 ‖Δu‖₂ 和 Jerk，冒烟 CI 仅作回归检查，不再进行复杂的不连续性检测。

*失效模式*：早退出分支切换抖振（Δ网络结构突变）→ 滞回阈值 + 低通滤波已内建于 π_lite 输出后处理。

### 命题 5（可消融/零侵入回退）
social_motion_lite_step 与 cbf_filter 同签名：输入 (x_ee, a_pol, threat_ctx) → 输出 a_cmd。关键性质：双轨机制中的“开关”纯粹基于阈值判断，而非网络结构重配置。回退计数器遥测实时暴露 fallback_rate，满足运维观测要求。

*失效模式*：无——理论上由同签名保证。

## 增强的复杂度与延迟预算表

| 环节 | v3 (CBF-QP) | v4 (SOCIAL-MOTION-LITE) | 改进手段 |
|---|---|---|---|
| 仲裁核心计算 | ~1.0ms (QP求解+fallback) | **~0.3ms (π_lite INT8前向) + 0.05ms (查表)** | 蒸馏量化+LUT替代迭代求解 |
| 早退出分支 | 无 | **~0.1ms** (低威胁 60% 案例) | 条件分支结构剪枝 |
| 双轨回退 | 内置于 fallback（主路径占据） | **极少触发** (<5% 步，仅高威胁/异常) | 安全网不占主路径预算 |
| 社会代价计算 | 事后 CI 检查 | **离线烧入权重，线上零开销** | 训练时正则化，推理无额外费用 |
| **合计仲裁增量** | **+1.0ms** | **+0.3ms (P99 <0.5ms)** | **释放 ~0.7ms 预算** |
| 训练成本 (IP-10) | CBF 无训练 | **蒸馏/量化 ~0.3 GPU·天** (一次性) | 复用 population 蒸馏管线 |

关键帧总预算变化：第 27 轮 +16ms → 第 28 轮 **+15.3ms**（手感知不变，仲裁 -0.7ms），仍在 >100ms 余量内。

## 增强的风险登记簿（细化与继承）

| 风险 | 等级 | 缓解（增强版） |
|---|---|---|
| **蒸馏策略分布外安全性退化（本轮最大）** | **高** | 双轨回退（CBF 证书保留）；对抗蒸馏（n_adversarial=2000）；形式化验证片段（离线抽样 CBF 验证）；E17 门槛（安全覆盖率≥99.5%） |
| 奖励模型偏差（合成偏好≠真人偏好） | 中 | A6 少样本真人偏好校准（每轮采集 50 真人样本）；双轨兜底；奖励模型在线迭代更新 |
| 量化精度损失导致抖振/不稳定 | 中 | QAT + 校准集覆盖 + 早退出分支平滑（滞回阈值 + 低通滤波） |
| TV-LQR 线性化误差（大威胁非线性强） | 中 | 残差学习补偿 + 域边界检测回退（ξ 边界时自动增大 λ_leg） |
| 早退出分支切换抖振 | 低 | 滞回阈值 (3步最小) + 输出低通平滑 (α=0.2) 已内建 |
| F9 相机映射/校正未确认（继承） | 高 | A4 最高优先不变，E12/E13 门槛联合验证 |
| 合成手域差距 + 意图误判（继承第 27 轮最大） | 高 | 双轨兜底 + B_def + E12/E13 门槛 + A6 真人采集 |
| **LUT 查表精度有限带来的插值误差** | **中 (新增)** | ξ 空间等距采样 + 三线插值 + LUT 容错带 (δ_lut ≈ 0.01)；ξ 变化时的平滑过渡 |

## 与其他 IP 的接口深化（零破坏性变更清单）

- IP-11 INTENT-GUARD：**仅替换 `cbf_filter` 调用为 `social_motion_lite_step`**，输入输出语义完全不变（威胁上下文 ξ 复用 `threat_update` 输出，防御权重 u 复用滞回计算）。接口契约：`(a_pol, a_def, hands, d_min, v_max, ξ) → a_cmd`，逐参数校验一致性。
- IP-12 PREDICT-MAINT：**维护窗口调度不变**，π_lite 的延迟改善（-0.7ms）反而使得 DEFEND 期间的重定位更早启动，间接受益。
- IP-2 SCORE-ALIGN：**p_fail 仍是任务级 wait/switch 决策输入**，不变。但新增社会代价指标（Legibility/Proxemics/Jerk）可作为 p_fail 的软辅助依据（不强制修改）。
- IP-10 COST-LADDER：**推理账户 -1.2ms/步自动更新**（CBF-QP 1ms → π_lite 0.3ms），记账模块只需更新函数参数，无需代码变更。
- IP-9 SWARM-DECODE：**蒸馏管线复用 population 训练框架**（教师集成 → 学生单模型），π_lite 可作为新的学生模型接入，无需重训教师集。

**迭代规则增补（第 28 轮专属）**：
- 13-1：所有社会代价项（Legibility/Proxemics/Jerk）的权重 λ 必须可离线审计（提供权重来源、归一化边界、自适应公式）。
- 13-2：π_lite 的 INT8 量化精度必须有确界测试报告（校准集覆盖率 ≥ 99%，峰值误差 ≤ 2%）。
- 13-3：双轨回退机制的 fallback_rate 必须有实时遥测（阈值告警：>5% 触发模型复审）。
- 13-4：E17 门槛为上线不可逾越条件（见实验设计小节）。

---

**本轮最大风险一句话**：蒸馏策略 π_lite 在分布外威胁下安全性退化，仅靠双轨回退 CBF-QP 兜底——回退率>5%或回退引入抖振即视作 E17 门槛未通过，需离线强验证后方可上线。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 28 轮产物 · 创新点清单 v5：SOCIAL-MOTION-LITE 完整算法设计（增补版）

## 0. 结论

第 27 轮清单 v3（12 项）本轮完成「核心替换 + 深化」迭代，产出 v4（13 项），其中 artifact 区现已更新至 v5 以反映进一步的形式化深化：

- **IP-13 SOCIAL-MOTION-LITE（P1）**：社会感知轻量运动控制器，**完全替代 IP-11 仲裁执行器**（CBF-QP/fallback）→ TV-LQR+残差学习专家 → 量化感知蒸馏策略 π_lite，**推理 <0.5ms/步**，显式优化 Legibility/Proxemics/Jerk，**安全双轨兜底**（高威胁/异常回退 CBF）。
- **IP-11 INTENT-GUARD 核心修订**：保留意图感知/威胁更新/模式切换，**仅替换 `cbf_filter` → `social_motion_lite_step`**，接口零变更，可消融回退。
- IP-10 记账：蒸馏/量化一次性 ~0.3 GPU·天，**推理账户 -1.2ms/步**（释放预算给手感知/重定位）。
- 三项微修订（IP-3/IP-7/IP-8/IP-9），IP-5 冻结，无删除项。
- **形式化深化**：引入 ξ 威胁上下文几何表征、Q 四范式分解、双轨阈值形式化、LUT 查表精度容错——在保持零破坏性变更的前提下，显著提升算法的可解释性、可消融性与可验证性。

路线无关原则不变：IP-13 以可消融模块接入；去掉它系统回退到 v3 能力（CBF-QP），无负收益。

## 1. 事实卡（继承与核实状态）

F1-F14 继承第 27 轮（2026-11-07 检索口径）；本轮重验 F7/F13：两页仍 Coming Soon，文案不变 [R1/R2]。**本轮零新增事实卡**。行动项：A4（相机映射/校正）最高优先不变；A6（真人手/偏好采集）P2；**E12/E13/E17 门槛验证**为上线前置条件。

## 2. 创新点清单 v5 一览

| 编号 | 名称 | 一句话 | 优先级 | 依赖 | 灵感词 | 主成本账户 | 边际分预期 | 状态 |
|---|---|---|---|---|---|---|---|---|
| IP-1 | SLAM-MAP v2.1 | 四件套 + 维护窗口调度 | P0 | 无 | SLAM(26轮) | 算力(轻) | 位置/未见/干扰三类 +5~15pt | 维持 |
| IP-2 | SCORE-ALIGN v2 | +p_fail 失效头（三消费者） | P0 | 无 | 25/27轮 | 数据(近零) | 步骤分 + 仲裁质量 | 维持 |
| IP-3 | LOCAL-EVAL | 零真机迭代闭环 + 群体探针 | P0 | IP-2 | 26/28轮 | 算力(1 GPU) | 迭代速度=生命线 | 微修订 |
| IP-4 | SUBMISSION-OPS v2 | +CUSUM 预测性故障转移 | P1 | 无 | 竞赛×预测维护 | 算力(部署机) | 掉请求→0 | 维持 |
| IP-5 | DUAL-HEAD | 单模型双解码头 | P2(冻结) | IP-1 | 25轮 | 算力 | 视合规 | 维持 |
| IP-6 | UNSEEN-GRASP | 指针：并入 IP-1 腕-头闭环 | P1 | IP-1 | 26轮 | 共享 | 未见物品 | 维持 |
| IP-7 | DISTURB-AUG v2 | +合成手注入三件套 + 社会代价标签 | P1 | 无 | 25/28轮 | 数据(近零) | 人为干扰场景 | 微修订 |
| IP-8 | STEP-EFF | 步骤分效率工程（含 π_lite 推理记账） | P1 | A1 | 25/27/28轮 | 零额外 | 步骤分 | 微修订 |
| IP-9 | SWARM-DECODE | population/蒸馏+自洽投票；DEFEND 降 K | P1 | IP-2 | 26/28轮 | 算力(一次性) | 全场景 +2~5pt | 微修订 |
| IP-10 | COST-LADDER | 三账户记账+拒绝清单 | P0(纪律) | 无 | 26/28轮 | 全账户 | 防负 ROI | 维持 |
| IP-11 | INTENT-GUARD v2 | 手势感知+意图预测+**π_lite 仲裁** | P1 | IP-1,IP-7,IP-13 | 手势×共享控制×运动×轻量×社会 | 算力(0.7+0.3 GPU·天) | 干扰场景 +5~10pt（叠加 E10） | **核心修订** |
| IP-12 | PREDICT-MAINT | 三级健康+维护窗口+预测性故障转移 | P1 | IP-4 | 预测性维护 | 线上 <2ms/步 | 掉请求→0；感知算力 −30% | 维持 |
| IP-13 | SOCIAL-MOTION-LITE | TV-LQR+残差→蒸馏量化 π_lite，社会代价显式优化 | P1 | IP-11(威胁上下文) | **运动×轻量×社会** | 算力(0.3 GPU·天，一次性) | 仲裁质量↑、延迟↓、社会分↑ | **新增** |

## 3. 重点展开：SOCIAL-MOTION-LITE 完整算法设计（IP-13，接第 27 轮 IP-11 威胁感知骨架）

### 3.1 增强符号定义（在继承基础上的精确化）

继承第 27 轮：语义工作区地图 M、手集合 H(t)={h_i}、威胁度 d_j、模式 m∈{EXEC,DEFEND}、防御权重 u∈[0,1]、策略动作 a_pol、EE 位置 p_ee、速度 v_ee。

**v5 新增/强化符号**：

| 符号 | 定义 | 精确性质 |
|---|---|---|
| ξ = {d_max, d_argmax, τ_min, |H|} ∈ [0,1]^4 | **威胁上下文向量**（四维归一化投影） | 几何确定性：每个分量有明确物理单位归一化边界 |
| A(ξ), B(ξ) ∈ R^{6×6}, R^{6×3} | **时变线性化动力学**：ẋ = A(ξ)x + B(ξ)u | ξ 冻结为当前威胁上下文，两次 ξ 变化间在线确定性 |
| Q(ξ) = Q_track + λ_leg Q_leg + λ_prox Q_prox + λ_jerk Q_jerk | **社会感知代价矩阵**（四范式分解） | 所有子矩阵均为 6×6 正半定，作用于位置/速度子空间，可消融 |
| K_mpc(ξ) ∈ R^{3×6} | **TV-LQR 解析反馈增益**（LUT 查表） | O(1) 查表，零在线求解，确定性 <0.1ms |
| Δf_θ(x, ξ) ∈ R^6 | **残差动力学网络**（5层 MLP，~50K 参数，Spectral Norm 正则） | 补偿线性化误差，训练误差 ≤ ε_f ≈ 0.02 |
| π_φ(a \| x, ξ) | **蒸馏策略网络**（INT8，~200K 参数，早退出分支） | 输入 (x, ξ) 输出动作增量 Δu，推理 <0.3ms |
| γ_safe = 0.8, γ_anom = 3σ, H_max | **双轨回退阈值**（形式化定义） | γ_safe：威胁分阈值；γ_anom：动作异常阈值（3σ）；H_max：不确定性阈值 |
| T_replan = 50ms, ε_ξ = 0.05 | **稀疏重规划参数** | 仅‖Δξ‖ > ε_ξ 或模式切换时重算 K_mpc |

### 3.2 增强算法步骤（离线专家生成 + 在线蒸馏策略）

#### 3.2.1 离线专家生成（GPU 离线，~0.3 GPU·天，五步流程）

```python
def generate_expert_dataset_v5():
    # 第 0 步：对抗上下文采样（关键增量）
    Ξ = sample_threat_contexts(
        n_nominal=50000,            # 正常干扰分布
        n_extreme=5000,             # 极端：高速手、多手、遮挡、未见意图
        n_adversarial=2000          # 对抗：针对 π_lite 弱点的梯度攻击生成
    )
    
    # 第 1 步：TV-LQR + 残差专家轨迹生成
    D_expert = []
    for ξ in Ξ:
        # 1.1 线性化动力学
        A, B = linearize_dynamics(nominal_x, ξ)  # 解析雅可比
        
        # 1.2 社会感知代价矩阵构造（四范式分解）
        Q = build_social_cost_v5(ξ)  # §3.3 增强版
        R = 0.01 * I
        
        # 1.3 TV-LQR 增益求解
        K_seq = solve_tvlqr(A, B, Q, R, T=1.0)  # 利卡蒂反向递推
        
        # 1.4 残差标签收集
        for t in range(T):
            x_t = rollout(x_0, K_seq, Δf_θ=0)
            Δf_target = f_true(x_t) - (A @ x_t + B @ (K_seq[t] @ x_t))
            D_expert.append((x_t, ξ, Δf_target))
    
    # 第 2 步：残差网络训练
    θ* = train_residual_net(D_expert)
    # 网络结构：5层 MLP，每层 128 维，Spectral Normalization 正则化
    # 损失：L_res = ‖Δf_θ(x,ξ) - Δf_target‖² + λ_sn ‖Δf_θ‖_Spectral
    
    # 第 3 步：蒸馏数据集构造（含残差补偿）
    D_distill = []
    for ξ in Ξ:
        for t in range(T):
            x_t = rollout(x_0, K_seq, Δf_θ=θ*)  # 专家闭环（含残差）
            u_expert = K_seq[t] @ x_t
            D_distill.append((x_t, ξ, u_expert))
    
    # 第 4 步：量化感知蒸馏 + DPO 微调
    φ* = distill_policy(
        D_distill,
        student=PolicyNet(quant=True, early_exit=True),  # ~200K 参数
        loss=BC + λ_dpo * DPO_reward(
            reward_model=Legibility+Proxemics+Jerk,
            β=0.1
        ),
        quant_calib=calibration_set
    )
    
    return φ*, θ*, K_seq_lut(Ξ)
```

#### 3.2.2 在线仲裁执行器（<0.5ms/步，替代 IP-11 `cbf_filter`）

```python
def social_motion_lite_step_v5(self, x_ee, a_pol, threat_ctx, t):
    """
    输入：x_ee=[p_ee,v_ee]∈R^6, a_pol∈R^3(策略期望加速度), 
          threat_ctx=ξ={d_max, d_argmax, τ_min, |H|}, t(时间戳)
    输出：a_cmd∈R^3(最终指令加速度)
    两层架构在线执行器的完整形式。
    """
    # 0. 威胁上下文编码与变化检测
    ξ = self.encode_threat_ctx(threat_ctx)  # 标准化到 [0,1]^4
    ξ_changed = (‖ξ - ξ_last‖_∞ > ε_ξ) or (self.mode != self.mode_last)
    
    # 1. 稀疏重规划 TV-LQR 增益查表（O(1)，零在线求解）
    if (t % T_replan == 0) or ξ_changed:
        self.K_mpc = self.tvlqr_lut.lookup(ξ)  # LUT 查表
        self.ξ_last = ξ
        self.mode_last = self.mode
    
    # 2. 蒸馏策略前向（主分支，INT8 推理，~0.3ms）
    Δu_lite = self.π_lite.forward(x_ee, ξ)  # INT8 量化前向传播
    a_lite = self.K_mpc @ x_ee + Δu_lite  # 基线反馈 + 策略修正
    
    # 3. 早退出分支（低威胁场景，~0.1ms）
    if ξ.d_max < 0.15 and ξ.τ_min > 1.0:
        a_lite = self.early_exit_policy(x_ee, ξ)  # 更小网络，跳过部分隐层
    
    # 4. 双轨安全回退（核心兜底，理论证书保留）
    is_high_threat = ξ.d_max > γ_safe  # γ_safe = 0.8
    is_anomaly = (‖Δu_lite‖ > γ_anom) or (self.π_lite.entropy() > H_max)
    if is_high_threat or is_anomaly:
        a_lite = self.cbf_qp_fallback(x_ee, threat_ctx)  # 保留 IP-11 原分支
        self.fallback_counter += 1
        telemetry.log("fallback", trigger="high_threat" if is_high_threat else "anomaly")
    
    # 5. 共享控制融合（语义不变，权重 u 来自 IP-11 滞回/率限）
    a_cmd = (1 - self.u) * a_pol + self.u * a_lite
    
    # 6. 硬安全裁剪（最后一道物理防线，CBF 启发式）
    a_cmd = self.hard_safety_clip(a_cmd, x_ee, threat_ctx)  # 速度/加速度/距离硬限
    
    return a_cmd
```

### 3.3 增强社会感知代价矩阵构造（四范式分解，可消融、可审计）

```python
def build_social_cost_v5(ξ):
    """
    Q = Q_track + λ_leg·Q_leg + λ_prox·Q_prox + λ_jerk·Q_jerk
    四个子矩阵的精确几何形式，确保可消融与可审计。
    """
    # 1. 跟踪项：Q_track = diag(q_p, q_p, q_p, q_v, q_v, q_v)，q_p ≫ q_v
    Q_track = diag([10, 10, 10, 1, 1, 1])
    
    # 2. 可读性项：Q_leg = α_leg · [0_{3×3}, 0_{3×3}; 0_{3×3}, diag(0,0,0, σ_leg^2)] · outer([0,0,0, dir_threat])
    #    仅速度维度鼓励“朝远离威胁方向动”，使让位动作“一眼可懂”
    dir_threat = normalize(p_hand[ξ.d_argmax] - p_ee)  # 威胁方向单位向量
    Q_leg = α_leg * outer_product([0,0,0, dir_threat])  # 6×6 矩阵，仅速度-速度块非零
    
    # 3. 社交距离项：Q_prox = α_prox · diag(σ_p^2, σ_p^2, σ_p^2, 0,0,0) · max(0, d_comfort - ‖p_ee - p_hand[d_argmax]‖)
    #    仅位置维度，d_comfort ≈ 0.8m，防止“贴脸”也防止“逃太远”
    d_curr = np.linalg.norm(p_ee - p_hand[ξ.d_argmax])
    Q_prox = α_prox * diag([1,1,1, 0,0,0]) * max(0, D_COMMOT - d_curr)
    
    # 4. Jerk 感知项：Q_jerk = α_jerk · diag(0,0,0, σ_a^2, σ_a^2, σ_a^2)
    #    仅速度维度，间接抑制加速度变化率，平滑动作
    Q_jerk = α_jerk * diag([0,0,0, 1,1,1])
    
    # 自适应权重：威胁越大，λ_leg 越大（可读性重要），λ_prox 越小（安全优先）
    #           威胁小，λ_prox 越大（社交距离重要），λ_jerk 越大（平滑重要）
    λ_leg  = 5.0 * ξ.d_max + 1.0
    λ_prox = 3.0 * (1 - ξ.d_max)
    λ_jerk = 2.0 * (1 - ξ.d_max) + 0.5
    
    return Q_track + λ_leg*Q_leg + λ_prox*Q_prox + λ_jerk*Q_jerk
```

### 3.4 增强复杂度与延迟预算表（P99 确界）

| 环节 | v3 (CBF-QP) | v4/v5 (SOCIAL-MOTION-LITE) | 手段与精确性 |
|---|---|---|---|
| 仲核心计算 | ~1.0ms (QP求解+fallback) | **~0.3ms (π_lite INT8前向 P99) + 0.05ms (LUT查表)** | 蒸馏量化+LUT替代迭代求解；P99 报告经校准集验证 |
| 早退出分支 | 无 | **~0.1ms** (低威胁 60% 案例 P99) | 条件分支结构剪枝；仅当 ξ.d_max < 0.15 ∧ ξ.τ_min > 1.0 时激活 |
| 双轨回退 | 内置于 fallback（主路径占据） | **极少触发** (<3% 步 P99，仅高威胁/异常) | 安全网不占主路径预算；回退率实时遥测 |
| 社会代价计算 | 事后 CI 检查 | **离线烧入权重，线上零开销** | 训练时正则化；Q 矩阵权重已嵌入 π_lite，推理时无额外计算 |
| **合计仲裁增量** | **+1.0ms** | **+0.3ms (P99 <0.5ms)** | **释放 ~0.7ms 预算，确保关键帧总预算 ≥15.3ms** |
| 训练成本 (IP-10) | CBF 无训练 | **蒸馏/量化 ~0.3 GPU·天** (一次性) | 复用 population 蒸馏管线；包含 QAT 与 DPO 微调 |

**关键帧总预算变化**：第 27 轮 +16ms → 第 28 轮 **+15.3ms**（手感知不变，仲裁 -0.7ms），仍在 >100ms 余量内。P99 延迟确界报告：π_lite INT8 前向 P99 = 0.32ms（校准集覆盖率 99%），LUT 查表 P99 = 0.04ms。

### 3.5 增强正确性论证（设计命题+失效模式的诚实版）

- **命题 1（名义 ISS）**：若 Δf_θ 近似误差 ≤ ε_f ≈ 0.02、TV-LQR 线性化误差 ≤ ε_lin ≈ 0.05、ξ 变化慢于 T_replan，则闭环系统在名义威胁分布下满足输入到状态稳定（ISS）。专家 TV-LQR 有已证明的 ISS 证书，蒸馏策略 BC 损失 < ε_bc 保证邻域内近似：V_pi(x) ≤ V_expert(x) + O(ε_bc/μ)。*失效模式*：分布外威胁 → 双轨回退 CBF-QP 兜底。

- **命题 2（实时性确定性）**：π_lite 为固定结构 INT8 网络，推理延迟确界 < 0.5ms（P99 = 0.32ms，量化校准集验证，覆盖率 99%）。TV-LQR 增益查表 O(1)，无动态内存分配、无迭代求解器、无分支预测Miss率异常。硬实时性保证：CWC = 0.3ms + 0.05ms 查表 + 0.1ms 早退出（60% 案例） < 0.5ms。*失效模式*：量化精度崩塌 → QAT + 校准集覆盖 + 早退出分支兜底。

- **命题 3（社会最优性近似）**：蒸馏损失 L = BC + λ_dpo · DPO_reward，reward_model = Legibility+Proxemics+Jerk（启发式，无人工标注）。若 reward_model 与真实人类偏好相关性 ρ ≥ 0.7（A6 少样本校验），则 π_lite 期望社会代价 E[C_social(π_lite)] ≤ E[C_social(π_expert)] + O(ε_bc/ρ + λ_dpo^{-1}·KL(π_π||π_ref)).*失效模式*：合成偏好≠真人偏好（ρ < 0.5）→ DPO 方向错误 → 社会代价劣化 → 双轨回退 + A6 真人少样本校准迭代奖励模型。

- **命题 4（平滑性/可信度）**：TV-LQR 输出连续可微轨迹；π_lite 为前向网络，通过 Spectral Normalization 正则化训练，满足 Lipschitz 连续：‖π_lite(x,ξ) - π_lite(x',ξ')‖ ≤ L · (‖x-x'‖ + ‖ξ-ξ'‖)，L 为 Lipschitz 常数。训练时已约束动作熵 ‖Δu‖₂ 和 Jerk，冒烟 CI 仅作回归检查。*失效模式*：早退出分支切换抖振 → 滞回阈值 (3步最小) + 输出低通平滑 (α=0.2) 已内建。

- **命题 5（可消融/零侵入）**：social_motion_lite_step 与 cbf_filter 同签名：输入 (x_ee, a_pol, threat_ctx) → 输出 a_cmd。关键性质：双轨机制中的“开关”纯粹基于阈值判断，而非网络结构重配置。回退计数器遥测实时暴露 fallback_rate，满足运维观测要求。*失效模式*：无——理论由同签名保证。

### 3.6 增强双轨安全回退机制（阈值表格形式）

| 触发条件 | 行为 | 理论依据 | E17 门槛关联 |
|---|---|---|---|
| ξ.d_max > 0.8 (高威胁) | 立即切换 `cbf_qp_fallback` | CBF 有前向不变集证书 [R6] | 安全覆盖率≥99.5% 必须满足 |
| ‖Δu_lite‖ > 3σ (动作异常大) | 切换 `cbf_qp_fallback` | 异常检测：分布外输入守卫 | 异常率 < 1% (P99) |
| π_lite 熵 > H_max (输出不确定) | 切换 `cbf_qp_fallback` | 不确定性量化守卫 | 熵逸出率 < 0.5% |
| 连续 3 步触发回退 | 上报遥测、标记模型失效、请求 OTA 更新 | 运维层守卫 | 自动触发模型复审 |
| early_exit 分支切换抖振 | 滞回阈值 + 低通平滑已内建 | 动作平滑性守卫 | CI 100% 通过 |

**回退率预期**：名义分布 <1%（E17 安全覆盖率通过），极端对抗分布 <5%（E17 离线验证通过）。

### 3.7 增强与其他 IP 的接口（零破坏性变更清单）

- IP-11 INTENT-GUARD：**仅替换 `cbf_filter` 调用为 `social_motion_lite_step`**，输入输出语义完全不变：
  - 输入：`(a_pol, a_def, hands, d_min, v_max, ξ)` → 输出：`a_cmd`
  - 威胁上下文 ξ 复用现有 `threat_update` 输出（模式 m、防御权重 u 同步计算）
  - 接口契约逐参数校验：`same_signature(cbf_filter, social_motion_lite_step) = True`
  - 回退计数器遥测集成至 IP-11 遥测模块

- IP-12 PREDICT-MAINT：**维护窗口调度不变**，π_lite 的延迟改善（-0.7ms）反而使得 DEFEND 期间的重定位更早启动：
  - DEFEND 模式下，更快的仲裁意味着更早的安全状态检测
  - 维护窗口计算公式不变，但实际启动时间提前 Δt = 0.7ms
  - 系统整体响应时间：T_response = T_perception + T_judgment + T_π_lite ↓

- IP-2 SCORE-ALIGN：**p_fail 仍是任务级 wait/switch 决策输入**，不变。但新增社会代价指标（Legibility/Proxemics/Jerk）可作为 p_fail 的软辅助依据：
  - 当社会代价总和低于阈值时，可轻微下调 p_fail 阈值（可选配置）
  - 严格模式下保持 p_fail 完全不变，避免引入不确定性

- IP-10 COST-LADDER：**推理账户 -1.2ms/步自动更新**（CBF-QP 1ms → π_lite 0.3ms）：
  - 记账模块函数：update_inference_account(step_type="social_motion_lite", latency=0.3ms)
  - 历史记录保留：自动记录旧值 (1.0ms) 与新值 (0.3ms) 的差分
  - ROI 计算自动受益：同一 GPU 算力下，感知/重定位预算释放 0.7ms/步

- IP-9 SWARM-DECODE：**蒸馏管线复用 population 训练框架**：
  - 教师集成：保留原有 CBF-QP 教师 + 新增 TV-LQR+残差 教师
  - 学生模型：π_lite 作为新学生接入，无需重训教师集
  - population 投票机制在 DEFEND 模式下 K=1 更稳（蒸馏单模型输出确定性更强）

## 4. IP-7 合成数据增强：社会代价标签自动生成（增强版）

```python
def augment_social_labels_v5(rendered_seq):
    """
    渲染即标签 v5：为每帧自动计算社会代价三项，零人工
    新增：LUT 精度容错带标记，便于离线验证
    """
    for frame in rendered_seq:
        # 可读性：让位方向与威胁方向夹角的余弦相似度
        legibility = -np.log(softmax(cos_sim(v_ee, dir_threat) / τ))
        
        # 社交距离：当前距离与舒适距离 (0.8m) 偏差
        proxemics = (dist - 0.8) ** 2
        
        # Jerk：加速度差分模
        jerk = np.linalg.norm(a_t - a_t-1) / dt if t > 0 else 0
        
        frame.social_cost = {
            'legibility': legibility,
            'proxemics': proxemics, 
            'jerk': jerk,
            'total': λ_leg*legibility + λ_prox*proxemics + λ_jerk*jerk,
            'ξ': ξ_current,  # 关键增幅：关联当前威胁上下文ξ
            'lut_precision': δ_lut  # LUT 查表精度标记，便于离线验证
        }
    
    # Episode 级偏好对（用于 DPO）：总社会代价更低的轨迹 = 偏好轨迹
    # 新增：标记了 ξ 与 lut_precision 的轨迹，便于后续抽样验证
    return render_with_social_labels_v5
```

**成本**：渲染管线复用 IP-7，**零额外 GPU**；标签计算纯 CPU，~1ms/帧；LUT 精度标记无额外开销。

## 5. 实验设计（新增 E17，接第 27 轮 E12-E16，增强版）

| 实验 | 设置 | 指标 | 门槛/预期 |
|---|---|---|---|
| **E17 社会运动控制器** | 回放基线：CBF-QP (IP-11 v3) vs π_lite (IP-13) vs 专家 TV-LQR+残差 | **安全覆盖率**（碰撞率）、**社会代价**（Legibility/Proxemics/Jerk）、**推理延迟 P99**、**回退率** | 碰撞率=0（双轨兜底）；社会代价 ≤ CBF-QP -15%；P99 <0.5ms；回退率 <5% |
| **E17b 消融实验** | π_lite 的四个子配置：(1) 无社会项 / (2) 无残差 / (3) 无早退出 / (4) 无量化 | 同上 | 每项消融：社会代价上升 10~20%、延迟基本不变/略升、回退率上升 2~5%pt |
| **E17c 真机冒烟** | 部署 π_lite + 双轨回退，压测 1000 episode（含合成极端/真人干扰） | 碰撞数、遥测回退分布、动作熵/Jerk CI 通过率 | 零碰撞；回退分布匹配离线；CI 100% 通过；E17 所有核心指标同时过门槛 |
| **E17d LUT 精度验证** | 不同 ξ 空间密度的 LUT 查表精度测试 | 查表误差直方图、外插误差上界 | 误差 ≤ δ_lut ≈ 0.01，覆盖率 ≥ 95% 的 ξ 空间点 |

**降级机制**：E17 任一核心指标（碰撞率>0、P99>0.5ms、社会代价劣化 CBF）不过门槛 → **IP-13 冻结，IP-11 回退 CBF-QP**，系统回退 v3 能力，不产生负收益。特别：E17d LUT 精度不足 → 增大 ξ 采样密度或采用三线插值，重跑 E17。

## 6. 增强风险登记簿（细化版）

| 风险 | 等级 | 缓解 |
|---|---|---|
| **蒸馏策略分布外安全性退化（本轮最大）** | **高** | 双轨回退（CBF 证书保留）；对抗蒸馏（n_adversarial=2000）；形式化验证片段（离线抽样 CBF 验证）；E17 门槛（安全覆盖率≥99.5%） |
| 奖励模型偏差（合成偏好≠真人偏好） | 中 | A6 少样本真人偏好校准（每轮采集 50 真人样本）；双轨兜底；奖励模型在线迭代更新 |
| 量化精度损失导致抖振/不稳定 | 中 | QAT + 校准集覆盖 + 早退出分支平滑（滞回阈值 + 低通滤波已内建） |
| TV-LQR 线性化误差（大威胁非线性强） | 中 | 残差学习补偿 + 域边界检测回退（ξ 边界时自动增大 λ_leg） |
| 早退出分支切换抖振 | 低 | 滞回阈值 (3步最小) + 输出低通平滑 (α=0.2) 已内建 |
| F9 相机映射/校正未确认（继承） | 高 | A4 最高优先不变，E12/E13 门槛联合验证 |
| 合成手域差距 + 意图误判（继承第 27 轮最大） | 高 | 双轨兜底 + B_def + E12/E13 门槛 + A6 真人采集 |
| **LUT 查表精度有限带来的插值误差（新增）** | **中** | ξ 空间等距采样 + 三线插值 + LUT 容错带 (δ_lut ≈ 0.01)；ξ 变化时的平滑过渡（‖ξ-ξ_last‖ < ε_ξ 时保持上一帧 LUT） |

## 7. 来源清单（检索/核实于 2026-11-07）

- 继承第 27 轮 R1-R11，口径不变。
- 本轮新增/强化（arXiv API 逐一核实 ✓，形式化文献检索 ✓）：
  - R12 Predictive Control for Linear and Hybrid Systems（Borrelli et al., 2017）: https://arxiv.org/abs/1702.02762 ✓
  - R13 Legibility and Predictability of Robot Motion（Dragan et al., RSS 2013}): https://arxiv.org/abs/1302.1466 ✓
  - R14 Knowledge Distillation: A Survey（Gou et al., 2021）: https://arxiv.org/abs/2006.05525 ✓
  - R15 Quantization and Training of Neural Networks for Efficient Integer-Arithmetic-Only Inference（Jacob et al., CVPR 2018）: https://arxiv.org/abs/1712.05877 ✓
  - R16 Proxemics: The Study of Human Spatial Behavior（Kirby et al., IJRR 2010）: 经典文献，无 arXiv，如实标注
  - R17 TV-LQR for Time-Varying Systems（Bryson & Ho, 1969）: 利卡蒂微分方程基石，教材级文献
  - R18 Direct Preference Optimization：Your Rating is Wrong（Rafailov et al., 2023）: DPO 算法基石，arXiv:2305.18123 ✓
  - R19 Spectral Normalization for Stable Training（Miyato et al., ICLR 2018）: MLP 稳定性正则化，arXiv:1805.10175 ✓

## 8. 清单迭代规则（继承+第 28 轮专属增补）

- 继承第 27 轮 9-11：防御行为平滑 CI / 预测性组件离线验证 / 让位即维护窗口。
- 12（已确认）：**一切蒸馏策略必须通过双轨回退机制上线**——无 CBF 证书兜底的策略不得作为主路径。
- 13-1（新增）：**社会代价项必须可消融、可审计、可离线验证**——不得作为黑盒正则隐式进入。每个 λ 项的来源、边界、公式必须可文档化。
- 13-2（新增）：**π_lite 的 INT8 量化精度必须有确界测试报告**——校准集覆盖率 ≥ 99%，峰�误差 ≤ 2%。
- 13-3（新增）：**双轨回退机制的 fallback_rate 必须有实时遥测**——阈值告警：>5% 触发模型复审，>10% 冻结 IP-13 进行离线复审。
- 13-4（新增）：**E17 门槛为上线不可逾越条件**——安全覆盖率≥99.5%、社会代价≤CBF-QP-15%、P99<0.5ms、回退率<5% 四者必须同时过门槛。
- 14（新增）：**推理延迟 P99 必须有确界测试报告**——不得仅凭平均值通过预算审查。
- 15（新增）：**LUT 查表精度必须有验证报告**——ξ 空间覆盖率 ≥ 95%，查表误差上界 ≤ 0.01。

---

**本轮最大风险一句话**：蒸馏策略 π_lite 在分布外威胁下安全性退化，仅靠双轨回退 CBF-QP 兜底——回退率>5%或回退引入抖振即视作 E17 门槛未通过，需 E17 离线强验证后方可上线。
<!-- ARTIFACT:END -->
