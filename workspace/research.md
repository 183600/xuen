# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。
<!-- IDEA:START -->
# 第 61 轮（承接第 60 轮 SGEC/IP-153~160；新一轮灵感循环第 1 轮；本轮灵感：「最优控制」×「惯性测量单元」）

> 第 60 轮的 SGEC 用 SSM×CIEC×EPIR×SERC 把「场景语义→认知意图→执行约束→证据链」接了起来，但仍有三个结构性缺口：
> 1. **阻抗参数仍是「编译/搜索」而非「最优合成」**：EEIS 的 K_safe 来自约束筛选与场景先验收窄，缺少一个显式代价（能量、接触力方差、跟踪误差）下的最优性保证——「安全」有了，「为什么这组 K_p/K_d 在代价意义下最好」没有。
> 2. **接触瞬态是「高频盲区」**：force/position 遥测是低频、事件驱动的，而落地冲击、滑动起始、抓取微振发生在 100–1000 Hz；第 60 轮的场景识别看到的是「冲击之后」，不是「冲击之中」。
> 3. **证据链在稀疏 EV-exec 之间是「空档」**：EPIR 只保证已产生的 EV-exec 不丢、不乱序，却无法回答「两条 EV-exec 之间机器人到底发生了什么」——消息丢失窗口内的连续状态仍是黑箱。
>
> 本轮引入两个灵感词：**最优控制**（把阻抗增益从「约束可行」提升为「代价最优 + 可证明次优界」）与**惯性测量单元**（用 IMU 的高频惯性信息补上接触瞬态与证据空档，并作为最优控制模型辨识的激励源）。

## 0. 直觉与动机

**灵感 1（最优控制 → 阻抗的参数化最优合成 IOIS）**
直觉：阻抗控制律 F = K_p(x_d−x) + K_d(ẋ_d−ẋ) 本质上就是一个状态反馈 u = −K z，z=(x,ẋ)。既然是反馈，就可以问：在代价 J=∫(zᵀQz+uᵀRu)dt 下，最优的 K 是什么？答案由 Riccati 方程给出 K* = R⁻¹BᵀP，且 K* 直接就是阻抗增益 [K_p*, K_d*]。关键洞见：**不是「先设 K_p/K_d 再论证安全」，而是「先声明代价 Q/R 与约束，再由 CARE 解出唯一的 K*，最后把 K* 投影到 K_safe」**——阻抗从手工参数变成有代价语义的最优反馈。

**灵感 2（IMU → 高频惯性能态与接触模型辨识）**
直觉：接触力遥测像「脉搏」，IMU 像「心电图」——前者告诉你力多大，后者告诉你加速度/角速度如何突变。接触动力学 M ẍ + D ẋ + K x = u + w 里的 ẍ 正是 IMU 直接测量的量。关键洞见：**IMU 把接触模型从「离线标定的先验」变成「在线可辨识的对象」**：用 (u, x̂, ẋ̂, a_m) 做递归最小二乘，实时估计 (M̂, D̂, K̂) 及其协方差，喂给 CARE 得到「当前接触状态下的最优阻抗」。

**灵感 3（IMU → 冲击事件触发的滚动最优控制 ETIOC）**
直觉：最优控制若每毫秒都解一遍 MPC 太贵，但接触瞬态只占很小时间窗。IMU 的加速度残差 ||a_m − â|| 是天然的「事件探测器」：一旦超过 γ_imp 就触发一次短时域 OCP，在 [t_k, t_k+T_h] 上带力/速度约束滚动优化。关键洞见：**「事件触发」把最优控制的算力花在真正需要的瞬态上**，并用最小事件间隔 τ_min 保证 Zeno-free 与实时可调度。

**灵感 4（IMU → 惯性桥证据链 IB-EPIR）**
直觉：两条 EV-exec 之间不是真空——IMU 以 200–1000 Hz 记录了这段惯性轨迹。把这段轨迹降采样后做哈希 H_k，随下一条 EV-exec 一起上链，云端就能在消息丢失时用 H_k 重建「空档里发生了什么」。关键洞见：**证据不只证明「结果」，还要证明「过程」**；惯性桥把 EV-exec 的稀疏点连成连续带，且桥的积分协方差 tr(Σ_gap) 给出「这条桥还能信多久」的硬边界。

**灵感 5（合流 → 惯性最优接地闭环 IOGC）**
直觉：IMU 估计 ξ̂ → 辨识 θ̂ → CARE 合成 K* → 事件触发 MPC 处理冲击 → 执行产生 EV-exec → IMU 桥补空档 → 更新 θ̂ 与不确定性。形成 **「惯性能态→模型→最优增益→事件执行→惯性证据→模型更新」** 的闭环。关键洞见：**最优性不是一次性的，而是随模型辨识与 IMU 置信度在线刷新**；当 IMU 不健康时，最优解必须退化为鲁棒/缓存解。

## 1. 形式化定义（增量：定义 161–168）

**定义 161（惯性能态与接触动力学 ICD）** 任务空间接触模型与 IMU 观测模型：
- **接触动力学**：M(x)ẍ + D(x,ẋ)ẋ + K(x)x = u + w，其中 u 为阻抗/力矩控制量，w 为外部扰动与未建模力。
- **线性化状态空间**：z = [x; ẋ]，ż = A z + B u + B_w w，A = [[0, I], [−M⁻¹K, −M⁻¹D]]，B = [0; M⁻¹]。
- **IMU 观测**：a_m = Rᵀ(ẍ − g) + b_a + n_a，ω_m = ω + b_g + n_g，其中 b_a、b_g 为加速度/角速度偏置。
- **EKF 状态**：ξ = (p, v, q, b_a, b_g)，输出估计 (x̂, ẋ̂) 与协方差 Σ_z；惯性信息矩阵 I_imu = Σ_z⁻¹。
- **IMU 健康度**：h_imu = 1[‖b̂_a‖ ≤ β_a ∧ ‖b̂_g‖ ≤ β_g ∧ tr(Σ_z) ≤ σ̄] ∈ {0,1}。

**定义 162（逆最优阻抗合成 IOIS）** 给定辨识模型 θ̂ = (M̂, D̂, K̂)、代价 (Q, R) 与安全集 K_safe：
- **最优反馈**：求解连续代数 Riccati 方程 AᵀP + PA − PBR⁻¹BᵀP + Q = 0，得 K* = R⁻¹BᵀP ∈ R^{m×2n}。
- **阻抗分解**：K* = [K_p*, K_d*]，即最优刚度与阻尼增益。
- **安全投影**：K^proj = Π_{K_safe}(K*) = argmin_{K∈K_safe} ‖K − K*‖_{Σ_z}，其中 Σ_z 为惯性能态协方差加权。
- **逆最优残差**：ε_inv(K) = ‖R K − BᵀP‖_F / (‖R K‖_F + 1)，用于判定「某增益是否等价于某个 (Q,R) 下的最优反馈」。
- **最优性保证**：若 ε_inv ≤ τ_inv、Riccati 残差 ε_ric ≤ τ_ric、模型失配 ε_mod ≤ τ_mod，则 K^proj 是 (Q,R,θ̂) 意义下的 ε_opt-次优增益。

**定义 163（惯性扰动观测器 IDOB）** 由 IMU 高频测量构造力残差：
- **残差**：r(t) = M̂ a_m(t) + D̂ ẋ̂(t) + K̂ x̂(t) − u(t)。
- **扰动估计**：d̂ = LPF_λ(r)，即一阶低通滤波，截止频率 λ 由接触带宽决定。
- **前馈补偿**：u_ff = −d̂，用于抵消外部扰动与未建模力。
- **冲击事件**：E_imp(t) = 1[‖r(t)‖ > γ_imp]，作为 ETIOC 的事件触发源之一。
- **误差界**：在偏置有界 ‖b_a‖ ≤ β_a、噪声有界前提下，‖d − d̂‖ ≤ ε_dob(β_a, λ, Σ_z)。

**定义 164（事件触发惯性最优控制 ETIOC）** 触发函数与滚动优化：
- **触发条件**：e(t) = ‖z(t) − z(t_k)‖_W；当 e(t) ≥ σ‖z(t_k)‖ + η 或 E_imp(t)=1 时触发事件。
- **有限时域 OCP**：
  ```
  min_{u(·)} ∫_{t_k}^{t_k+T_h} (zᵀQz + uᵀRu) dτ + z(t_k+T_h)ᵀP z(t_k+T_h)
  s.t.  ż = A z + B u,  u ∈ [u_min, u_max],  |ẋ| ≤ v_max,  z(t_k) = ẑ(t_k)
  ```
- **Zeno 防护**：最小事件间隔 τ_min > 0，且 τ_min ≥ T_solve（CARE/QP 最坏求解时间）。
- **稳定性**：当 (σ, η) 满足 Lyapunov 触发条件时，闭环对触发误差 ISS，且存在正的不变集。

**定义 165（惯性桥证据链 IB-EPIR）** 在第 60 轮 EPIR 上增加惯性段：
- **惯性签名段**：s_k = {(t, a_m, ω_m)}，t ∈ [t_k^{ev}, t_{k+1}^{ev}]，降采样后量化为 H_k = H(quantize(downsample(s_k)))。
- **惯性桥**：B_k = (seq_id, t_start, t_end, H_k, anchor=x̂(t_start), Σ_gap)。
- **协方差传播**：Σ_gap(t) = Σ_z(t_start) + ∫_{t_start}^{t} Q_imu dτ + drift_term(t)，用于量化积分漂移。
- **桥有效性**：bridge_valid(B_k) = 1[tr(Σ_gap) ≤ δ_bridge ∧ H_k 与重叠段重放哈希一致]。
- **因果检验扩展**：云端在原 S_check 的「时间戳顺序 + 内容哈希」之外，增加「相邻桥哈希连续」检验；若断裂则判定为「惯性-证据分歧」，请求 S_shadow 重放。

**定义 166（惯性最优接地闭环 IOGC）** 算子 IOGC(M, task, scene, intent, δ_f_req)：
```
① ISE:   (ξ̂, Σ_z, h_imu) ← IMU_EKF.step(a_m, ω_m, dt)
② ID:    θ̂ = (M̂, D̂, K̂), Σ_θ ← RLS.update(u, x̂, ẋ̂, a_m)
③ IOIS:  K* ← CARE(A(θ̂), B(θ̂), Q, R)；K^proj ← Π_{K_safe}(K*)
④ IDOB:  d̂ ← LPF(M̂a_m + D̂ẋ̂ + K̂x̂ − u)；E_imp ← 1[‖r‖ > γ_imp]
⑤ ETIOC: if 触发: u* ← solve_finite_horizon_OCP(z=ẑ, P, K^proj, 约束)
⑥ SERC:  复用第 60 轮场景/意图约束，更新 K_safe（场景先验 + 意图锁定）
⑦ Execute: 下发 K^proj 与 u*；采集力/位遥测
⑧ EV-exec: build_exec_evidence(...) → 生成 seq_id 对应的执行证据
⑨ IB-EPIR: B_k ← build_inertial_bridge(IMU 段)；S_shadow.append(EV-exec ⊕ B_k)
⑩ IOC:   Cert_io ← build_inertial_optimality_certificate(K^proj, P, ε_ric, ε_mod, ε_inv, h_imu)
⑪ Return: (K^proj, u*, EV-exec, B_k, Cert_io, θ̂, Σ_θ)
```

**定义 167（惯性最优性证书 IOC）** 证书结构：
- **Cert_io** = (K^proj, P, ε_ric, ε_mod, ε_inv, ε_opt, safety_margin, h_imu, bridge_valid)。
- **次优界**：存在常数 c₁,c₂,c₃，使 J(u) − J* ≤ c₁ε_ric + c₂ε_mod + c₃ε_inv，其中 J* 为理想模型/理想 IMU 下的最优代价。
- **有效性判定**：Cert_valid = 1[ε_ric ≤ τ_ric ∧ ε_mod ≤ τ_mod ∧ ε_inv ≤ τ_inv ∧ K^proj ∈ K_safe ∧ h_imu=1 ∧ bridge_valid=1]。
- **失效动作**：任一不满足即撤销「最优」标签，降级为鲁棒增益 K_rob 或第 60 轮缓存增益 K_cache。

**定义 168（惯性-最优预算 B_io 与 PCE+++++）** B_io = (B_oc, B_imu, B_cog)：
- **B_oc** = (CARE_solve_budget, MPC_horizon_budget, QP_iterations)：最优控制算力预算。
- **B_imu** = (Sample_rate, Bias_drift_budget, Calibration_health, Bridge_horizon)：惯性测量预算。
- **B_cog** = 第 60 轮的 (B_scene, B_intent, B_ros, B_exec)。
- **VOI 扩展**：
  ```
  voi_io(π) = VOI_meta_pessimistic(π) − cost_cog(π) − cost_exec(π) − cost_oc(π) − cost_imu(π)
  cost_oc  = λ_care·T_care + λ_mpc·T_mpc + λ_qp·N_qp
  cost_imu = λ_rate·(1/Sample_rate) + λ_bias·‖b̂_a,b̂_g‖ + λ_bridge·tr(Σ_gap)
  ```
- **降级策略**：B_oc 耗尽 ⇒ 使用上一周期缓存 K_cache；B_imu 不健康 ⇒ 使用鲁棒增益 K_rob = argmin_{K∈K_safe} max_{θ∈Θ} J(K;θ)；桥时域超限 ⇒ 停止惯性重建，回退到 EPIR 纯序列校验。

## 2. 关键算法伪代码

### IP-161 ISE（惯性能态估计）

```python
class InertialStateEstimator:
    def __init__(self, cfg):
        self.ekf = ErrorStateKalmanFilter(cfg)
        self.beta_a, self.beta_g, self.sigma_bar = cfg.beta_a, cfg.beta_g, cfg.sigma_bar

    def step(self, a_m, omega_m, dt):
        self.ekf.predict(a_m, omega_m, dt)
        self.ekf.correct_contact(self.contact_model)
        xi, Sigma = self.ekf.state, self.ekf.cov
        healthy = (norm(xi.ba) <= self.beta_a and
                   norm(xi.bg) <= self.beta_g and
                   trace(Sigma) <= self.sigma_bar)
        return xi, Sigma, healthy
```

### IP-162 IOIS（逆最优阻抗合成）

```python
def synthesize_optimal_impedance(theta_hat, Q, R, K_safe, Sigma_z):
    M, D, K = theta_hat
    n = M.shape[0]
    A = np.block([[np.zeros((n, n)), np.eye(n)],
                  [-np.linalg.inv(M) @ K, -np.linalg.inv(M) @ D]])
    B = np.vstack([np.zeros((n, n)), np.linalg.inv(M)])
    P = scipy.linalg.solve_continuous_are(A, B, Q, R)
    K_lqr = np.linalg.inv(R) @ B.T @ P
    Kp, Kd = K_lqr[:, :n], K_lqr[:, n:]
    eps_ric = norm(A.T @ P + P @ A - P @ B @ np.linalg.inv(R) @ B.T @ P + Q)
    K_proj = project_to_safe(K_lqr, K_safe, weight=np.linalg.inv(Sigma_z))
    eps_inv = norm(R @ K_lqr - B.T @ P) / (norm(R @ K_lqr) + 1.0)
    return K_proj, P, eps_ric, eps_inv
```

### IP-163 IDOB（惯性扰动观测器）

```python
class InertialDisturbanceObserver:
    def __init__(self, theta_hat, lam=0.9, gamma_imp=2.0):
        self.theta_hat, self.lam, self.gamma_imp = theta_hat, lam, gamma_imp
        self.d_hat = np.zeros(3)

    def update(self, a_m, x_hat, v_hat, u):
        M, D, K = self.theta_hat
        r = M @ a_m + D @ v_hat + K @ x_hat - u
        self.d_hat = self.lam * self.d_hat + (1 - self.lam) * r
        impact = np.linalg.norm(r) > self.gamma_imp
        return self.d_hat, impact, r
```

### IP-164 ETIOC（事件触发惯性最优控制）

```python
class EventTriggeredInertialOCP:
    def __init__(self, Q, R, P, W, sigma, eta, tau_min, horizon):
        self.Q, self.R, self.P, self.W = Q, R, P, W
        self.sigma, self.eta = sigma, eta
        self.tau_min, self.horizon = tau_min, horizon
        self.t_last, self.u_seq = -np.inf, None
        self.z_k = None

    def maybe_solve(self, t, z_hat, impact, K_proj, constraints):
        if self.z_k is None:
            self.z_k, self.t_last = z_hat.copy(), t
            self.u_seq = solve_finite_horizon_ocp(
                z_hat, K_proj, self.Q, self.R, self.P, self.horizon, constraints)
            return self.u_seq
        e = np.linalg.norm(self.W @ (z_hat - self.z_k))
        trigger = impact or (e >= self.sigma * np.linalg.norm(self.z_k) + self.eta)
        if trigger and (t - self.t_last) >= self.tau_min:
            self.z_k, self.t_last = z_hat.copy(), t
            self.u_seq = solve_finite_horizon_ocp(
                z_hat, K_proj, self.Q, self.R, self.P, self.horizon, constraints)
        return self.u_seq
```

### IP-165 IB-EPIR（惯性桥证据链）

```python
class InertialBridgeEPIR(ExecutionPerceptionIsolationRegion):
    def __init__(self, window=100, delta_bridge=1e-3):
        super().__init__(window)
        self.delta_bridge = delta_bridge

    def build_bridge(self, seq_id, imu_segment, anchor, Sigma_anchor):
        Hk = hash_quantized(downsample(imu_segment))
        Sigma_gap = propagate_covariance(Sigma_anchor, imu_segment)
        return InertialBridge(seq_id, imu_segment.t0, imu_segment.t1,
                              Hk, anchor, Sigma_gap)

    def append_with_bridge(self, ev_exec, imu_segment, anchor, Sigma_anchor):
        bridge = self.build_bridge(self.last_received + 1, imu_segment, anchor, Sigma_anchor)
        msg = super().append({**ev_exec, 'bridge': bridge})
        return msg, bridge

    def verify_bridge(self, bridge, imu_replay):
        hash_ok = (hash_quantized(downsample(imu_replay)) == bridge.H)
        drift_ok = trace(bridge.Sigma_gap) <= self.delta_bridge
        return hash_ok and drift_ok
```

### IP-166 IOGC（惯性最优接地闭环）

```python
def inertial_optimal_grounding_loop(M, task, scene, intent, delta_f_req):
    xi, Sigma_z, h_imu = M.ise.step(M.a_m, M.omega_m, M.dt)
    theta_hat, Sigma_theta = M.id.update(M.u_prev, xi.x, xi.v, M.a_m)

    K_safe = M.serc.update_constraints(scene, intent, delta_f_req)
    K_proj, P, eps_ric, eps_inv = synthesize_optimal_impedance(
        theta_hat, M.Q, M.R, K_safe, Sigma_z)

    d_hat, impact, r = M.idob.update(M.a_m, xi.x, xi.v, M.u_prev)
    u_seq = M.etioc.maybe_solve(M.t, np.hstack([xi.x, xi.v]),
                                impact, K_proj, M.constraints)

    result = execute_impedance(K_proj, u_seq, d_hat)
    ev_exec = build_exec_evidence(result, xi, theta_hat, K_proj)
    msg, bridge = M.epir.append_with_bridge(ev_exec, M.imu_buffer, xi.x, Sigma_z)

    cert = build_inertial_optimality_certificate(
        K_proj, P, eps_ric, Sigma_theta, eps_inv, h_imu, bridge)
    if not cert.valid:
        K_proj = M.fallback_gain(K_rob=M.K_rob, K_cache=M.K_cache)

    return K_proj, u_seq, ev_exec, bridge, cert, theta_hat, Sigma_theta
```

### IP-167 IOC（惯性最优性证书）

```python
def build_inertial_optimality_certificate(K_proj, P, eps_ric, Sigma_theta,
                                          eps_inv, h_imu, bridge):
    eps_mod = sqrt(trace(Sigma_theta))
    eps_opt = C1 * eps_ric + C2 * eps_mod + C3 * eps_inv
    valid = (eps_ric <= TAU_RIC and eps_mod <= TAU_MOD and
             eps_inv <= TAU_INV and h_imu and bridge.valid)
    return InertialOptimalityCertificate(
        K=K_proj, P=P, eps_ric=eps_ric, eps_mod=eps_mod,
        eps_inv=eps_inv, eps_opt=eps_opt, h_imu=h_imu,
        bridge_valid=bridge.valid, valid=valid)
```

### IP-168 PCE+++++（惯性-最优预算耦合）

```python
class InertialOptimalBudget:
    def __init__(self, care_ops=20, mpc_ops=10, imu_rate=500,
                 bias_budget=0.05, bridge_horizon=2.0):
        self.B_oc = {'care': care_ops, 'mpc': mpc_ops}
        self.B_imu = {'rate': imu_rate, 'bias': bias_budget,
                      'horizon': bridge_horizon}
        self.used_oc = {'care': 0, 'mpc': 0}

    def degrade_mode(self, h_imu, bridge_trace):
        if self.used_oc['care'] >= self.B_oc['care']:
            return 'cache_gain'
        if not h_imu or bridge_trace > self.B_imu['horizon']:
            return 'robust_gain'
        return 'optimal'

def inertial_optimal_cost(pi):
    return (LAMBDA_CARE * pi.t_care + LAMBDA_MPC * pi.t_mpc +
            LAMBDA_RATE / pi.imu_rate + LAMBDA_BRIDGE * pi.bridge_trace)
```

## 3. 复杂度与正确性

| 组件 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|
| ISE | O(n_ξ²) EKF 更新/步 | O(n_ξ²) | 有界偏置下状态误差 ≤ δ_ξ，h_imu 正确判定 |
| IOIS | O(n³) CARE（n=2 dim） | O(n²) | K^proj ∈ K_safe，ε_opt 次优界成立 |
| IDOB | O(n²) / 步 | O(n) | ‖d−d̂‖ ≤ ε_dob(β_a, λ) |
| ETIOC | O(H·n³) / 事件 | O(H·n) | τ_min > 0 无 Zeno，闭环 ISS |
| IB-EPIR | O(L) 桥构造/段 | O(window + L) | 桥有效概率 ≥ 1−δ，因果哈希连续 |
| IOGC | O(单闭环) | 复用 | 端到端场景适应 + 最优性 + 证据连续 |
| IOC | O(n³) 证书 | O(n²) | 证书有效性 ⇒ 次优界与安全裕度可验证 |

**正确性定理（IOG）**：
假设 A66–A70 成立：
- **(A66)** ISE：IMU + 接触零速/几何更新使系统可观测，EKF 在偏置有界下收敛，‖ξ̂−ξ‖ ≤ δ_ξ。
- **(A67)** 辨识：递归最小二乘在持续激励下 θ̂ → θ，协方差收敛，模型失配 ε_mod ≤ τ_mod。
- **(A68)** 最优性：θ̂ 下 (A,B) 可稳、(A,Q^{1/2}) 可检测，CARE 有唯一稳定解，K* 稳定且 K^proj ∈ K_safe。
- **(A69)** 事件触发：τ_min ≥ T_solve > 0，且 (σ,η) 满足 Lyapunov 触发条件，闭环 ISS。
- **(A70)** 惯性桥：桥时域内积分协方差有界，tr(Σ_gap) ≤ δ_bridge。

则：
1. **ε-最优性**：J(K^proj) − J* ≤ c₁ε_ric + c₂ε_mod + c₃ε_inv，且 Cert_io.valid=1 时该界可验证。
2. **安全性**：K^proj ∈ K_safe，事件间由 ISS 不变集保证力/速度约束不越界，事件时刻由 OCP 约束保证。
3. **证据连续性**：在丢包率低于桥容量时，IB-EPIR 以概率 ≥ 1−δ 重建 EV-exec 之间的连续惯性轨迹，且哈希连续可验。
4. **预算安全性**：B_oc / B_imu / B_cog 任一耗尽或不健康，IOGC 退化为 cache_gain / robust_gain / 第 60 轮降级策略，绝不下发未验证的「最优」增益。

## 4. 实验设计 E192–E196

| 实验 | 指标 | 目标 |
|---|---|---|
| E192 ISE | 姿态/速度 RMSE；偏置收敛时间；冲击检测延迟 | RMSE ≤ 0.5° / 0.01 m/s；≤ 1 s；≤ 5 ms |
| E193 IOIS | 力跟踪误差；ε_inv；K_safe 约束满足率 | 误差 −25% vs EEIS；ε_inv ≤ 0.1；100% |
| E194 ETIOC | 冲击峰值力；事件间隔；约束违反次数 | 峰值力 −30%；τ_min 稳定；0 违反 |
| E195 IB-EPIR | 丢包下证据链完整率；桥漂移 tr(Σ_gap) | ≥ 99.5%；≤ δ_bridge |
| E196 端到端 | vs 第 60 轮：接触建立时间、能量、ΔECE、证书有效率 | 建立 −35%；能量 −15%；ΔECE ≥ 15%；证书 ≥ 99% |

## 5. 本轮最大风险

**一句话**：若 IMU 偏置/积分漂移与接触模型误辨识同时发生，CARE 会基于错误动力学解出「对错误模型可证明最优、对真实接触却可能失稳」的增益——最优性证书反而放大了虚假确定性；必须以「h_imu 健康门槛 + Σ_θ 模型失配门控 + K^proj 安全投影 + cache/robust 双回退」四重护栏，确保最优控制永远只在可验证的模型与惯性置信域内生效。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 61 轮产物 · 创新点清单 v1：IOG（惯性最优接地：最优控制×惯性测量单元，ISExIOIS×IDOB×ETIOC×IB-EPIR×IOGC×IOC×PCE+++++）

> 承接第 60 轮 SGEC（IP-153~160，SSM×CIEC×EPIR×SERC×PCE++++）。本轮把「阻抗安全编译」升级为**「代价最优 + 可证明次优界」的阻抗合成**，并用 IMU 同时解决**接触瞬态高频盲区**与**EV-exec 之间的证据空档**。核心叙事：阻抗就是状态反馈 `u=−Kz`，最优控制给出 `K*=R⁻¹BᵀP`（其分块即 `[K_p*,K_d*]`）；IMU 提供 `ẍ` 与高频段，使接触模型在线可辨识、冲击可事件触发、证据可惯性桥接。

> IP 编号：IP-161~IP-168（共 8 个）。本轮不推翻第 60 轮，而是在其 `K_safe`、`EPIR`、`SERC`、`PCE++++` 之上做「最优合成 + 惯性增强」。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进 |
|---|---|---|---|
| IP-161 | ISE Inertial State Estimation | 新增 | EKF 状态 ξ=(p,v,q,b_a,b_g)、惯性能态协方差 Σ_z、健康度 h_imu、信息矩阵 I_imu |
| IP-162 | IOIS Inverse Optimal Impedance Synthesis | 新增 | CARE 解 K*=R⁻¹BᵀP、阻抗分解 [K_p*,K_d*]、安全投影 Π_{K_safe}、逆最优残差 ε_inv |
| IP-163 | IDOB Inertial Disturbance Observer | 新增 | 惯性力残差 r=M̂a_m+D̂ẋ̂+K̂x̂−u、低通扰动估计 d̂、冲击事件 E_imp、前馈 u_ff |
| IP-164 | ETIOC Event-Triggered Inertial Optimal Control | 新增 | 触发函数 e(t)、有限时域 OCP、Zeno 防护 τ_min、ISS 稳定性 |
| IP-165 | IB-EPIR Inertial-Bridge Evidence chain | 升级 IP-155 | 惯性签名段 H_k、惯性桥 B_k、协方差传播 Σ_gap、桥有效性、因果哈希连续 |
| IP-166 | IOGC Inertial-Optimal Grounding Closed loop | 新增 | 惯性能态→辨识→最优增益→事件执行→惯性证据→模型更新闭环算子 |
| IP-167 | IOC Inertial Optimality Certificate | 新增 | 次优界 J−J* ≤ c₁ε_ric+c₂ε_mod+c₃ε_inv、证书有效性、失效降级 |
| IP-168 | PCE+++++ Inertial-Optimal Budget | 升级 IP-157 | 新增 B_oc/B_imu 预算、cost_oc/cost_imu、cache/robust/optimal 三态降级 |

## 1. 符号体系增量（定义 161–168）

| 符号 | 含义 |
|---|---|
| `M(x)ẍ + D(x,ẋ)ẋ + K(x)x = u + w` | 任务空间接触动力学 |
| `z = [x; ẋ]`，`ż = Az+Bu+B_ww` | 线性化接触状态空间 |
| `a_m = Rᵀ(ẍ−g)+b_a+n_a`，`ω_m = ω+b_g+n_g` | IMU 观测模型 |
| `ξ = (p,v,q,b_a,b_g)`，`Σ_z` | EKF 惯性能态与协方差 |
| `h_imu ∈ {0,1}` | IMU 健康度（偏置/协方差门控） |
| `AᵀP+PA−PBR⁻¹BᵀP+Q=0` | 连续 Riccati 方程（CARE） |
| `K* = R⁻¹BᵀP = [K_p*, K_d*]` | 最优阻抗增益 |
| `K^proj = Π_{K_safe}(K*)` | 安全投影后的最优增益 |
| `ε_ric, ε_mod, ε_inv` | Riccati 残差 / 模型失配 / 逆最优残差 |
| `ε_opt ≤ c₁ε_ric+c₂ε_mod+c₃ε_inv` | 次优界 |
| `r = M̂a_m+D̂ẋ̂+K̂x̂−u`，`d̂ = LPF_λ(r)` | 扰动残差与估计 |
| `E_imp = 1[‖r‖>γ_imp]` | IMU 冲击事件 |
| `e(t)=‖z(t)−z(t_k)‖_W ≥ σ‖z(t_k)‖+η` | ETIOC 触发条件 |
| `τ_min ≥ T_solve` | 最小事件间隔（Zeno 防护） |
| `H_k = H(quantize(downsample(s_k)))` | 惯性签名哈希 |
| `B_k = (seq_id,t_start,t_end,H_k,anchor,Σ_gap)` | 惯性桥 |
| `tr(Σ_gap) ≤ δ_bridge` | 桥有效性（漂移边界） |
| `B_io=(B_oc,B_imu,B_cog)` | 惯性-最优预算 |
| `cost_oc=λ_care·T_care+λ_mpc·T_mpc+λ_qp·N_qp` | 最优控制成本 |
| `cost_imu=λ_rate/Sample_rate+λ_bias·‖b̂‖+λ_bridge·tr(Σ_gap)` | 惯性测量成本 |

## 2. 关键算法伪代码

### IP-161 ISE（惯性能态估计）

```python
class InertialStateEstimator:
    def __init__(self, cfg):
        self.ekf = ErrorStateKalmanFilter(cfg)
        self.beta_a, self.beta_g, self.sigma_bar = cfg.beta_a, cfg.beta_g, cfg.sigma_bar

    def step(self, a_m, omega_m, dt):
        self.ekf.predict(a_m, omega_m, dt)
        self.ekf.correct_contact(self.contact_model)
        xi, Sigma = self.ekf.state, self.ekf.cov
        healthy = (norm(xi.ba) <= self.beta_a and
                   norm(xi.bg) <= self.beta_g and
                   trace(Sigma) <= self.sigma_bar)
        return xi, Sigma, healthy
```

### IP-162 IOIS（逆最优阻抗合成）

```python
def synthesize_optimal_impedance(theta_hat, Q, R, K_safe, Sigma_z):
    M, D, K = theta_hat
    n = M.shape[0]
    A = np.block([[np.zeros((n, n)), np.eye(n)],
                  [-np.linalg.inv(M) @ K, -np.linalg.inv(M) @ D]])
    B = np.vstack([np.zeros((n, n)), np.linalg.inv(M)])
    P = scipy.linalg.solve_continuous_are(A, B, Q, R)
    K_lqr = np.linalg.inv(R) @ B.T @ P
    Kp, Kd = K_lqr[:, :n], K_lqr[:, n:]
    eps_ric = norm(A.T @ P + P @ A - P @ B @ np.linalg.inv(R) @ B.T @ P + Q)
    K_proj = project_to_safe(K_lqr, K_safe, weight=np.linalg.inv(Sigma_z))
    eps_inv = norm(R @ K_lqr - B.T @ P) / (norm(R @ K_lqr) + 1.0)
    return K_proj, P, eps_ric, eps_inv
```

### IP-163 IDOB（惯性扰动观测器）

```python
class InertialDisturbanceObserver:
    def __init__(self, theta_hat, lam=0.9, gamma_imp=2.0):
        self.theta_hat, self.lam, self.gamma_imp = theta_hat, lam, gamma_imp
        self.d_hat = np.zeros(3)

    def update(self, a_m, x_hat, v_hat, u):
        M, D, K = self.theta_hat
        r = M @ a_m + D @ v_hat + K @ x_hat - u
        self.d_hat = self.lam * self.d_hat + (1 - self.lam) * r
        impact = np.linalg.norm(r) > self.gamma_imp
        return self.d_hat, impact, r
```

### IP-164 ETIOC（事件触发惯性最优控制）

```python
class EventTriggeredInertialOCP:
    def __init__(self, Q, R, P, W, sigma, eta, tau_min, horizon):
        self.Q, self.R, self.P, self.W = Q, R, P, W
        self.sigma, self.eta = sigma, eta
        self.tau_min, self.horizon = tau_min, horizon
        self.t_last, self.u_seq, self.z_k = -np.inf, None, None

    def maybe_solve(self, t, z_hat, impact, K_proj, constraints):
        if self.z_k is None:
            self.z_k, self.t_last = z_hat.copy(), t
            self.u_seq = solve_finite_horizon_ocp(
                z_hat, K_proj, self.Q, self.R, self.P, self.horizon, constraints)
            return self.u_seq
        e = np.linalg.norm(self.W @ (z_hat - self.z_k))
        trigger = impact or (e >= self.sigma * np.linalg.norm(self.z_k) + self.eta)
        if trigger and (t - self.t_last) >= self.tau_min:
            self.z_k, self.t_last = z_hat.copy(), t
            self.u_seq = solve_finite_horizon_ocp(
                z_hat, K_proj, self.Q, self.R, self.P, self.horizon, constraints)
        return self.u_seq
```

### IP-165 IB-EPIR（惯性桥证据链）

```python
class InertialBridgeEPIR(ExecutionPerceptionIsolationRegion):
    def __init__(self, window=100, delta_bridge=1e-3):
        super().__init__(window)
        self.delta_bridge = delta_bridge

    def build_bridge(self, seq_id, imu_segment, anchor, Sigma_anchor):
        Hk = hash_quantized(downsample(imu_segment))
        Sigma_gap = propagate_covariance(Sigma_anchor, imu_segment)
        return InertialBridge(seq_id, imu_segment.t0, imu_segment.t1,
                              Hk, anchor, Sigma_gap)

    def append_with_bridge(self, ev_exec, imu_segment, anchor, Sigma_anchor):
        bridge = self.build_bridge(self.last_received + 1, imu_segment, anchor, Sigma_anchor)
        msg = super().append({**ev_exec, 'bridge': bridge})
        return msg, bridge

    def verify_bridge(self, bridge, imu_replay):
        hash_ok = (hash_quantized(downsample(imu_replay)) == bridge.H)
        drift_ok = trace(bridge.Sigma_gap) <= self.delta_bridge
        return hash_ok and drift_ok
```

### IP-166 IOGC（惯性最优接地闭环）

```python
def inertial_optimal_grounding_loop(M, task, scene, intent, delta_f_req):
    xi, Sigma_z, h_imu = M.ise.step(M.a_m, M.omega_m, M.dt)
    theta_hat, Sigma_theta = M.id.update(M.u_prev, xi.x, xi.v, M.a_m)

    K_safe = M.serc.update_constraints(scene, intent, delta_f_req)
    K_proj, P, eps_ric, eps_inv = synthesize_optimal_impedance(
        theta_hat, M.Q, M.R, K_safe, Sigma_z)

    d_hat, impact, r = M.idob.update(M.a_m, xi.x, xi.v, M.u_prev)
    u_seq = M.etioc.maybe_solve(M.t, np.hstack([xi.x, xi.v]),
                                impact, K_proj, M.constraints)

    result = execute_impedance(K_proj, u_seq, d_hat)
    ev_exec = build_exec_evidence(result, xi, theta_hat, K_proj)
    msg, bridge = M.epir.append_with_bridge(ev_exec, M.imu_buffer, xi.x, Sigma_z)

    cert = build_inertial_optimality_certificate(
        K_proj, P, eps_ric, Sigma_theta, eps_inv, h_imu, bridge)
    if not cert.valid:
        K_proj = M.fallback_gain(K_rob=M.K_rob, K_cache=M.K_cache)

    return K_proj, u_seq, ev_exec, bridge, cert, theta_hat, Sigma_theta
```

### IP-167 IOC（惯性最优性证书）

```python
def build_inertial_optimality_certificate(K_proj, P, eps_ric, Sigma_theta,
                                          eps_inv, h_imu, bridge):
    eps_mod = sqrt(trace(Sigma_theta))
    eps_opt = C1 * eps_ric + C2 * eps_mod + C3 * eps_inv
    valid = (eps_ric <= TAU_RIC and eps_mod <= TAU_MOD and
             eps_inv <= TAU_INV and h_imu and bridge.valid)
    return InertialOptimalityCertificate(
        K=K_proj, P=P, eps_ric=eps_ric, eps_mod=eps_mod,
        eps_inv=eps_inv, eps_opt=eps_opt, h_imu=h_imu,
        bridge_valid=bridge.valid, valid=valid)
```

### IP-168 PCE+++++（惯性-最优预算耦合）

```python
class InertialOptimalBudget:
    def __init__(self, care_ops=20, mpc_ops=10, imu_rate=500,
                 bias_budget=0.05, bridge_horizon=2.0):
        self.B_oc = {'care': care_ops, 'mpc': mpc_ops}
        self.B_imu = {'rate': imu_rate, 'bias': bias_budget,
                      'horizon': bridge_horizon}
        self.used_oc = {'care': 0, 'mpc': 0}

    def degrade_mode(self, h_imu, bridge_trace):
        if self.used_oc['care'] >= self.B_oc['care']:
            return 'cache_gain'
        if not h_imu or bridge_trace > self.B_imu['horizon']:
            return 'robust_gain'
        return 'optimal'

def inertial_optimal_cost(pi):
    return (LAMBDA_CARE * pi.t_care + LAMBDA_MPC * pi.t_mpc +
            LAMBDA_RATE / pi.imu_rate + LAMBDA_BRIDGE * pi.bridge_trace)
```

## 3. 复杂度与正确性

| 组件 | 时间 | 空间 | 正确性 |
|---|---|---|---|
| ISE | O(n_ξ²)/步 | O(n_ξ²) | 有界偏置下 ‖ξ̂−ξ‖ ≤ δ_ξ |
| IOIS | O(n³) CARE | O(n²) | K^proj ∈ K_safe；ε_opt 次优界 |
| IDOB | O(n²)/步 | O(n) | ‖d−d̂‖ ≤ ε_dob(β_a,λ) |
| ETIOC | O(H·n³)/事件 | O(H·n) | τ_min>0 无 Zeno；闭环 ISS |
| IB-EPIR | O(L)/段 | O(window+L) | 桥有效概率 ≥ 1−δ |
| IOGC | O(单闭环) | 复用 | 最优性 + 安全性 + 证据连续 |
| IOC | O(n³) | O(n²) | 证书有效 ⇒ 次优界可验证 |

**正确性定理（IOG）**：若 A66–A70 成立（ISE 可观测收敛、辨识持续激励、CARE 可解且 K^proj∈K_safe、事件触发 τ_min>0 且 ISS、桥协方差有界），则：
1. `J(K^proj) − J* ≤ c₁ε_ric + c₂ε_mod + c₃ε_inv`，且证书有效时可验证；
2. 事件时刻由 OCP 约束保证、事件间由 ISS 不变集保证力/速度不越界；
3. 丢包率低于桥容量时，IB-EPIR 以概率 ≥ 1−δ 重建 EV-exec 间连续惯性与哈希连续；
4. 任一 B_oc/B_imu/B_cog 耗尽或不健康，退化为 cache_gain / robust_gain / 第 60 轮降级，绝不下发未验证「最优」增益。

## 4. 实验设计 E192–E196

| 实验 | 指标 | 目标 |
|---|---|---|
| E192 ISE | 姿态/速度 RMSE；偏置收敛；冲击延迟 | ≤0.5°/0.01 m/s；≤1 s；≤5 ms |
| E193 IOIS | 力跟踪误差；ε_inv；约束满足率 | −25% vs EEIS；≤0.1；100% |
| E194 ETIOC | 冲击峰值力；事件间隔；约束违反 | −30%；τ_min 稳定；0 |
| E195 IB-EPIR | 丢包下链完整率；桥漂移 | ≥99.5%；≤δ_bridge |
| E196 端到端 | 接触建立时间、能量、ΔECE、证书有效率 | −35%；−15%；≥15%；≥99% |

## 5. 本轮最大风险

**一句话**：若 IMU 偏置/积分漂移与接触模型误辨识同时发生，CARE 会基于错误动力学解出「对错误模型可证明最优、对真实接触却可能失稳」的增益——最优性证书反而放大了虚假确定性；必须以「h_imu 健康门槛 + Σ_θ 模型失配门控 + K^proj 安全投影 + cache/robust 双回退」四重护栏，确保最优控制永远只在可验证的模型与惯性置信域内生效。
<!-- ARTIFACT:END -->
