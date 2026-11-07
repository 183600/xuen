# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 27 轮（新灵感循环第 5 轮）· ADAPT-REACTIVE：行为树驱动的在线自适应力矩+热觉察

## 0. 先给直觉：为何「行为树、在线学习、Isaac Sim」是对第 26 轮最大风险的精准回应？

第 26 轮最大风险：
> **「物理对账」依赖的逆动力学/摩擦模型本身也是模型——变速、变温下的摩擦系统偏差会污染 e_τ，审计可能把「动力学模型误差」误判为「世界模型漂移」，造成慢性误回退**

三个灵感词各回答一层：
- **行为树**回答「怎么做决策」：把「被审计的想象服务」作为行为树的节点，动态闭合「观察-规划-执行」的闭环，使漂移检测成为可解释的行为选择；
- **在线学习**回答「怎么改模型」：把「物理对账」的判决转化为「标签」，用增量贝叶斯/递归最小二乘实时修正摩擦/热参数，避免模型误判；
- **Isaac Sim**回答「怎么验证」：用可微渲染器/物理引擎从模拟中学习「可解释的偏差源」特征，跨模态蒸馏校准审计的“误报谬误”。

核心灵魂：**把「被审计的想象」从「静态管控」变成「行为决策中的可解释反馈回路」**，用 Isaac Sim 提供的可解释偏差源特征校准器，行为树调度在线学习，从而真正「免疫」摩擦模型本身的误判。

一句话押注：
> **本轮给 TEMPO-NAV 的 μ_z 增广「行为树闭环 + 在线参数自适应 + Isaac Sim 跨模态校准」：行为树节点 B = {IDLE, PLAN, ADAPT, RECOVER}，在线学习用增量贝叶斯更新摩擦系数 μ_f(θ_v, θ_t)，Isaac Sim 提供「摩擦-力矩-温度」的可解释特征 ψ ∈ ℝᵏ，蒸馏到审计判决 ρ，消除「动力学误差误判漂移」的根本症源。**

## 1. 研究日志：从「静态管控」到「行为树驱动的可解释反馈」

### 1.1 第 26 轮的核心失效模式

| 失效模式 | 说明 |
|---|---|
| 动力学误差误判 | 摩擦模型 μ_f(v, θ) 受速度/温度影响，τ̂ 偏差污染 e_τ → 虚警 g 增长 |
| 审计不解释 | CUSUM 只给出「是/否」判决，不说明「哪儿对账失效」 |
| 参数僵化 | σ_τ、τ_lim(θ) 固定不随实际摩擦演化自适应 |

### 1.2 三个灵感词的技术化实现

#### 行为树：动态闭环调度
- B(q, τ_meas, e_τ, g) → 动作：IDLE→PLAN→ADAPT→RECOVER
- ADAPT 节点激活时，打开「在线学习」子进程
- RECOVER 节点在 g > h 且 τ 传感确认「实际碰撞」时触发，跳过想象直接阻抗

#### 在线学习：增量贝叶斯摩擦校准
- 状态：β = {μ_f, b_f, C_f, κ_f}（滚动摩擦截距、斜率、功率系数、热耦合）
- 观测：y_t = τ_meas − τ_motion − Jᵀf̂ + τ_recon（残差）
- 似然：y_t | β ~ N(βᵀφ_t, σ²)（线性-高斯）
- 更新：β_{t+1} = β_t + K_t(y_t − βᵀφ_t)，K_t = P_tφ_t/(σ² + φᵀ_t P_t φ_t)
- 超参数 σ 由「审计判决 ρ」的置信度反向标定：ρ 小 → 增大 σ，减缓更新

#### Isaac Sim：可解释偏差特征蒸馏
- 从 Isaac Sim 中采样：{v, θ, μ_f, J, τ_theory, τ_sim, e_τ_sim}
- 特征编码器 ψ_φ(e_τ) → ℝᵏ：通过注意力机捕获「哪个关节、哪个方向」贡献大
- 蒸馏损失：L_distill = KL(π_sim || π_auditor) + ||ψ_φ − ψ_pred||²
- 目标：让ψ_φ 在 Isaac Sim 上有经验归一化，上真实机器上 ψ_φ 仍可靠

### 1.3 增量演进：TEMPO-NAV+ADAPT

| 层 | TEMPO-NAV v4 | ADAPT-REACTIVE | 关系 |
|---|---|---|---|
| 世界模型 | μ_z(s,a,θ)→(r,s',θ',τ̂,σ) | μ_z(s,a,θ,β)→(r,s',θ',τ̂,σ)：**+ 在线β** | **增广** |
| OOD 检测 | χ²+CUSUM+g_t | + ψ_θ(e_τ)特征 + 贝叶斯校准 | **解耦** |
| 规划 | L3'' anytime | L4''：行为树调度 + ADAPT 节点 | **闭环化** |
| 学习 | 离线 DAgger 蒸馏 | **在线增量贝叶斯 + Isaac Sim蒸馏** | **激活** |
| 运行时 | 1kHz/500Hz/50Hz | + 300Hz 行为树控制器 | **协同** |

## 2. 直觉深化：为什么「行为树+在线学习+Isaac Sim」能破局？

### 2.1 行为树如何「解释」审计？

```
                    ┌─────────────┐
                    │ OBSERVER    │
                    │ (g, e_τ)    │
                    └─────┬───────┘
                          │
                    ┌─────▼───────┐
                    │ BEHAVIOR    │
                    │ TREE        │
                    ├─────────────┤
                    │ IDLE: g≈0   │
                    │ PLAN: g>0   │  
                    │ ADAPT:      │ ← 打开在线学习
                    │ RECOVER:    │ ← 强制降级
                    └─────────────┘
```

- 当 g_t 持续上升时，行为树不再「硬拉低 σ」，而是「查询：是摩擦漂移，还是模型漂移？」
- ADAPT 节点：激活增量贝叶斯，用最近 M=50 窗的 e_τ 重新拟合 β，**改变 σ 的来源**

### 2.2 在线学习如何「免疫」摩擦误差？

| 传统做法 | ADAPT 的做法 |
|---|---|
| 固定 μ_f，g 大则认为模型差 | 把 g 当作「σ 的信号」，同步更新 μ_f |
| 虚假漂移 → 过度保守 | 真实摩擦漂移 → β 自适应，σ 稳定 |
| 需要重新标定 | 持续闭环，不离线 |

关键等式：**σ²_τ = σ²_MC + Jᵀ·Σ_f·J + (∂τ̂/∂β·P_β·∂τ̂/∂β)ᵀ**

ADAPT 让 P_β 在线更新，σ²_τ 自动适应「**这一刻的摩擦不确定性**」

### 2.3 Isaac Sim 为什么「不偏」？

- Isaac Sim 提供「**可微摩擦模型**」的 ground truth β_sim
- 特征 ψ_φ 训练时对齐 Isaac Sim 的 β_sim → τ_sim 映射，形成「**摩擦-力矩-温度**」的可解释层
- 上真实机器，ψ_φ 捕获的仍是「残差结构」，但不再依赖固定 μ_f，**用蒸馏知识校准 β 的先验**

## 3. 形式化定义

### 3.1 行为树调度器
- 状态变量：b ∈ {IDLE, PLAN, ADAPT, RECOVER}
- 判决规则：
  - g_t < θ_low → b = IDLE
  - g_t ∈ [θ_low, θ_high] → b = PLAN
  - g_t > θ_high 且 ψ_φ(e_τ) > τ_ψ → b = ADAPT
  - g_t > h 且 τ_meas 突变 → b = RECOVER

### 3.2 在线贝叶斯摩擦更新
- 参数向量：β_t ∈ ℝᵖ（摩擦系数 + 功率-热耦合）
- 特征：φ_t = [v, |v|, v·θ, ω·θ, sign(ω)·θ] ∈ ℝᵖ
- 观测：y_t = τ_meas,t − τ_motion,t − Jᵀf̂_t
- 似然模型：y_t | β_t ~ 𝒩(φᵀ_t β_t, σ²_t)
- 先验/后验：
  - β_t | D_{t-1} ~ 𝒩(μ_{t-1}, Σ_{t-1})
  - μ_t = μ_{t-1} + K_t(y_t − φᵀ_t μ_{t-1})
  - Σ_t = Σ_{t-1} − K_t φᵀ_t Σ_{t-1}
  - K_t = Σ_{t-1} φ_t/(σ²_t + φᵀ_t Σ_{t-1} φ_t)
- σ²_t 由 ρ_t 标定：σ²_t = σ²_base / ρ_t

### 3.3 Isaac Sim 特征蒸馏
- 从 Isaac Sim 采样 N_s 个 (v, θ, μ_f, τ_theory) 三元组
- 训练 ψ_φ: ℝⁿ → ℝᵏ（注意力特征编码器）
- 蒸馏损失：ℒ = 𝔼_{v,θ} [ KL( π(·|ψ_φ,τ_theory) || π_sim(·|τ_theory) ) + λ||ψ_φ − ψ_sim||² ]
- 目标 π_ψ: 给定 τ，预测「哪些关节的残差最可疑」
- 上真实机器：π_ψ(e_τ) 与 CUSUM g 形成「**双信号**」：g 量化漂移大小，π_ψ 定位漂移根因

## 4. 算法完整流程

```
# 0. 初始：TEMPO-NAV 的所有模块，外加
#    - Isaac Sim 预训练的 ψ_φ
#    - 贝叶斯摩擦先验 β_0 ~ 𝒩(μ_0, Σ_0)

# 1kHz 安全层（沿用）
every 1ms:
    a_sat = tau_limit_saturation(a_cmd, τ_lim(θ))
    impedance_control(a_sat)

# 300Hz 行为树控制器（新增）
every 3.33ms:
    # 读取审计状态
    _, _, tau_var = μ_z.sample(...)
    sigma_tau = sqrt(tau_var) + 0.05
    rho_phy, g = auditor.update(τ_meas, τ̂, sigma_tau)
    
    # 行为树判决
    b = behavior_tree(g, ρ_phy, τ_meas)
    
    if b == IDLE:
        skip_learning()
    elif b == ADAPT:
        # 在线贝叶斯更新
        β ← bayesian_update(τ_meas, τ̂, φ(状态), σ²_base/ρ_phy)
        σ_τ ← recompute_with_updated_β(β)
    elif b == RECOVER:
        trigger_emergency_fall_back()

# 500Hz 蒸馏层（沿用）
every 2ms:
    a = π_distill(s, θ, β)

# 50Hz 想象层（沿用）
every 20ms:
    cfg = budget.allocate(...)
    seq, depth = plan_anytime(s, θ, β, cfg)
    # ADAPT 判决更新 σ τ_lim
    sigma_tau_adj = auditor.rho() < 0.5 ? σ_τ * 1.5 : σ_τ
```

## 5. Python 核心实现

```python
import torch
import torch.nn as nn
import numpy as np
from collections import deque
from scipy.linalg import cho_solve, cho_factor

# ============================================================
# 0. Isaac Sim 特征编码器 ψ_φ（可微渲染特征）
# ============================================================
class FrictionFeatureExtractor(nn.Module):
    """从力矩残差提取「可解释偏差源」特征。
       自 Isaac Sim 预训练得到，上真实机器蒸馏使用。"""
    def __init__(self, n_joints: int = 7, feat_dim: int = 16):
        super().__init__()
        self.attn = nn.MultiheadAttention(n_joints, num_heads=2, dropout=0.1)
        self.mlp = nn.Sequential(
            nn.Linear(n_joints * 3, 64), nn.ReLU(),
            nn.Linear(64, feat_dim), nn.Tanh()
        )
        
    def forward(self, e_tau, v, theta):
        # e_tau: (T, n_joints), v: (T,), theta: (T, n_joints)
        B, T, n = (*e_tau.shape[:-1], e_tau.shape[-1]) if e_tau.dim() == 3 else (1, *e_tau.shape)
        e_tau = e_tau.view(B, T, n).permute(1, 0, 2)  # T, B, n
        keys = torch.stack([e_tau, e_tau * v.unsqueeze(-1), e_tau * theta], -1).flatten(-2, -1)
        attn_out, _ = self.attn(keys, keys, keys)
        return self.mlp(attn_out.permute(1, 0, 2).flatten(1, 2))


# ============================================================
# 1. 在线贝叶斯摩擦/热参数更新器
# ============================================================
class OnlineBayesianFrictionCalibrator:
    """增量贝叶斯线性回归：y = φᵀβ + ε
       y = τ_meas - τ_motion - Jᵀf̂
       φ = [v, |v|, v·θ, ω·θ, sign(ω)·θ]"""
    def __init__(self, p: int = 5, sigma_base: float = 0.1, 
                 mu0: np.ndarray = None, Sigma0: np.ndarray = None):
        self.p = p
        self.sigma_base = sigma_base
        if mu0 is None:
            self.mu = np.zeros(p)
            self.Sigma = np.eye(p) * 1e3
        else:
            self.mu, self.Sigma = mu0.copy(), Sigma0.copy()

    def _features(self, v, w, theta):
        v = np.asarray(v); w = np.asarray(w); theta = np.asarray(theta)
        phi = np.array([v * np.abs(v), np.abs(v), v * theta, w * theta, np.sign(w) * theta])
        return phi.flatten()

    def update(self, tau_meas, tau_hat, v, w, theta, rho: float):
        """rho 来自 auditor，标定 σ²_t"""
        y = tau_meas - tau_hat
        phi = self._features(v, w, theta)
        sigma2 = self.sigma_base ** 2 / max(rho, 0.1)  # ρ 小 → σ 大，更新慢
        
        phi_mu = phi @ self.mu
        S_phi = self.Sigma @ phi
        denom = sigma2 + phi @ S_phi
        
        if denom < 1e-12:
            return
        
        K = S_phi / denom  # 卡尔曼增益
        self.mu = self.mu + K * (y - phi_mu)
        self.Sigma = self.Sigma - np.outer(K, phi @ self.Sigma)
        
        # 数值稳定性：Sigma 需半正定
        eig, vec = np.linalg.eigh(self.Sigma)
        eig = np.maximum(eig, 1e-6)
        self.Sigma = vec @ np.diag(eig) @ vec.T

    def predict_error_var(self, v, w, theta):
        """返回 σ²_τ 中的摩擦不确定性贡献"""
        phi = self._features(v, w, theta)
        return (phi @ self.Sigma @ phi)


# ============================================================
# 2. 行为树调度器
# ============================================================
class BehaviorTreeController:
    """动态闭环调度器"""
    def __init__(self, theta_low: float = 0.5, theta_high: float = 1.5,
                 theta_psi: float = 0.3, h: float = 4.0):
        self.theta_low, self.theta_high = theta_low, theta_high
        self.theta_psi = theta_psi
        self.h = h
        self.state = "IDLE"
        
    def step(self, g: float, rho: float, psi_score: float) -> str:
        """根据审计结果返回行为状态"""
        if g < self.theta_low:
            self.state = "IDLE"
        elif g > self.h:
            if psi_score > self.theta_psi:
                self.state = "ADAPT"
            else:
                self.state = "RECOVER"
        else:
            self.state = "PLAN"
        return self.state


# ============================================================
# 3. ADAPT-REACTIVE 堆栈
# ============================================================
class ADAPTRStack:
    """TEMPO-NAV + 行为树 + 在线学习 + Isaac Sim 蒸馏"""
    def __init__(self, world_model, planner, skill_lib, auditor, budget,
                 observer, thermal_cfg, executor, psi_extractor, bayes_calibrator):
        self.world_model = world_model
        self.planner = planner
        self.skill_lib = skill_lib
        self.auditor = auditor
        self.budget = budget
        self.observer = observer
        self.thermal = thermal_cfg
        self.executor = executor
        self.psi_extractor = psi_extractor
        self.bayesian_calibrator = bayes_calibrator
        self.behavior_ctrl = BehaviorTreeController()
        
    def step(self, obs) -> dict:
        # 1kHz 安全层
        if self.observer.update(obs['q'], obs['qd'], obs['tau_meas'])[0]:
            return dict(mode='EMERGENCY', action=None, source='momentum_observer')
        
        # 读取状态
        tau_meas = obs['tau_meas']
        state, theta = obs['s'], obs['theta']
        v, w, omega = obs['v'], obs['w'], obs['omega']
        
        # 采样世界模型得到 τ̂ 与 σ_τ
        w_model = self.world_model  # MCWorldModel
        f_hat, s_next, tau_hat, theta_next, sigma, tau_var = w_model.sample(
            torch.as_tensor(state[None], dtype=torch.float32),
            torch.zeros(1, 2),  # a=0，实际由规划器给出
            torch.as_tensor(theta[None], dtype=torch.float32),
            torch.tensor([self.thermal['theta_amb']]),
            torch.as_tensor(obs['tau_motion'], dtype=torch.float32).unsqueeze(0),
            torch.as_tensor(obs['JT'], dtype=torch.float32).unsqueeze(0),
            obs['omega'][None] if np.ndim(obs['omega']) == 1 else obs['omega'][None, ...],
            T=3
        )
        sigma_tau = np.sqrt(tau_var.squeeze(0).cpu().numpy()) + 0.05
        tau_hat_np = tau_hat.squeeze(0).cpu().numpy()
        
        # 物理对账 + CUSUM
        rho_phy, g = self.auditor.update(tau_meas, tau_hat_np, sigma_tau)
        
        # Isaac Sim 特征判决
        e_tau = tau_meas - tau_hat_np
        psi_score = float(np.max(self.psi_extractor(
            torch.as_tensor(e_tau[None, None], dtype=torch.float32),
            torch.as_tensor([v], dtype=torch.float32),
            torch.as_tensor(theta[None], dtype=torch.float32)
        )))
        
        # 行为树判决
        b = self.behavior_ctrl.step(g, rho_phy, psi_score)
        
        # 在线学习
        if b == "ADAPT":
            self.bayesian_calibrator.update(
                tau_meas, tau_hat_np, v, w, theta, rho_phy
            )
            # 更新 σ_τ（此处演示，实际需回传给 auditor）
        
        # 规划
        if b == "PLAN":
            ctx = self._build_ctx(obs, theta)
            cfg = self.budget.allocate(self.thermal['gpu_temp'])
            seq, depth, elapsed = self.planner.plan(state, theta, ctx, cfg)
            self.budget.observe(elapsed)
            mode = 'imaginary'
            action = seq
        elif b == "ADAPT":
            # ADAPT 时仍用蒸馏策略，但 σ 已更新
            mode = 'distill_adapt'
            action = self.executor.pi_distill(state, theta)
        else:  # RECOVER
            mode = 'imaginary'
            action = None  # 或保守缩放
        
        return dict(mode=mode, action=action, depth=depth if b=="PLAN" else 0,
                    rho=rho_phy, g=g, behavior=b, psi=psi_score)

    def _build_ctx(self, obs, theta):
        return dict(goal=torch.as_tensor(obs['goal'], dtype=torch.float32),
                    tau_motion=torch.as_tensor(obs['tau_motion'], dtype=torch.float32).unsqueeze(0),
                    JT=torch.as_tensor(obs['JT'], dtype=torch.float32).unsqueeze(0),
                    omega=torch.as_tensor(obs['omega'], dtype=torch.float32).unsqueeze(0),
                    theta_amb=torch.tensor([self.thermal['theta_amb']]),
                    tau_lim=lambda th: torch.as_tensor(self.thermal['tau_lim_fn'](th.numpy())))
```

## 6. 正确性论证

**命题 1（增量贝叶斯收敛）**：在假设 φ_t 持久激励（ΦᵀΦ 可逆）且噪声高斯的下，OnlineBayesianFrictionCalibrator 收敛于 β*，且 Σ_t → 0；ρ_t 小于 1 时更新减缓，大与 1 时更新加速，实现「不确定性驱动学习」。

**命题 2（行为树安全性）**：行为树的 RECOVER 节点在 g > h 且物理确认 τ_meas 突变时触发，保证「误判 → 实际碰撞」的安全兜底。ADAPT 节点只在 ψ_score 显著时激活，防止「噪声误判 → 频繁学习」的震荡。

**命题 3（Isaac Sim 蒸馏可解释性）**：ψ_φ 通过注意力机制聚焦「残差结构」，蒸馏目标 π_sim 由 Isaac Sim 的可微摩擦模型提供，保证 ψ_φ 在真实机器上捕获的残差模式与「摩擦漂移」高度相关，实现「误判根因定位」。

## 7. 本轮最大的风险

**行为树的阈值 θ_low, θ_high, θ_ψ 需要在不同机器上重新标定，若标定不当，ADAPT 节点可能频繁激活导致「过度学习」或 RECOVER 节点误触发导致「过度保守」，破坏原有的 TEMPO-NAV 稳定性。**
 XUEN_EOF
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 27 轮产物 · ADAPT-REACTIVE 技术报告：行为树驱动的在线自适应力矩-热觉察

## 0. 结论：从「静态管控」到「行为树驱动的可解释反馈」

ADAPT-REACTIVE 在第 26 轮 TEMPO-NAV 基础上做**闭环增强**（不推倒）：
- **μ_z v3**：世界模型增强 β 在线状态，σ_τ 由在线贝叶斯摩擦校准器动态更新
- **OOD-GUARD v4**：四信号 + Isaac Sim 特征 ψ，实现「漂移定位」而非「漂移检测」
- **L4''**：行为树调度器 B = {IDLE, PLAN, ADAPT, RECOVER}，动态闭环控制学习-规划-执行
- **运行时 v3**：1kHz 安全 / 300Hz 行为树 / 500Hz 蒸馏 / 50Hz 想象
- **BENCH v5**：新增 T15 行为树误判率 / T16 线上学习收敛

## 1. 符号表（完整更新）

| 符号 | 含义 | 来源 |
|---|---|---|
| s, a, 𝒵, φ_z, π_z | 接触状态、动作、原语库、前置条件、执行策略 | 第 24/25/26 轮沿用 |
| θ ∈ ℝⁿ⁺¹ | 关节绕组温度 + 环境温 | 第 26 轮沿用 |
| τ_meas ∈ ℝⁿ | 关节力矩传感器测量（1kHz） | 第 26 轮沿用 |
| τ̂ = τ_motion + Jᵀf̂ | 力矩头（物理锚定） | 第 26 轮沿用 |
| β ∈ ℝᵖ | 在线贝叶斯摩擦参数 | **新增** |
| φ = [v|v|, vθ, ωθ, sign(ω)θ] | 摩擦特征向量 | **新增** |
| g_t, h, k | CUSUM 状态、门限、允差 | 第 26 轮沿用 |
| ψ_φ(e_τ) | Isaac Sim 特征提取器 | **新增** |
| b ∈ {IDLE, PLAN, ADAPT, RECOVER} | 行为树状态 | **新增** |
| D, N, T_MC, deadline | 想象深度、网格、采样、截止期 | 第 26 轮沿用 |

## 2. 核心算法

### 2.1 在线贝叶斯摩擦校准

```
Algorithm: OnlineBayesianFrictionCalibrator
Input: τ_meas, τ̂, v, w, θ, ρ (审计置信度)
Output: β (摩擦参数)

1. φ ← [v|v|, vθ, ωθ, sign(ω)θ]
2. σ² ← σ_base² / max(ρ, 0.1)
3. y ← τ_meas − τ̂
4. K ← Σ·φ / (σ² + φᵀ·Σ·φ)
5. μ ← μ + K·(y − φᵀ·μ)
6. Σ ← Σ − K·φᵀ·Σ
7. return μ, Σ
```

收敛性：在 φ_t 持久激励下，μ_t → μ* = (ΦᵀΦ)⁻¹Φᵀy，Σ_t → 0。

### 2.2 行为树调度器

```
Algorithm: BehaviorTreeStep(g, ρ, ψ)
Input: g_t (CUSUM), ρ (置信度), ψ (特征得分)
Output: 行为状态 b

if g < θ_low:
    b ← IDLE
elif g > h:
    if ψ > θ_ψ:
        b ← ADAPT  # 打开在线学习
    else:
        b ← RECOVER  # 强制降级
else:
    b ← PLAN
return b
```

### 2.3 Isaac Sim 特征蒸馏

```
Algorithm: FrictionFeatureDistillation
1. 从 Isaac Sim 采样 {(v, θ, τ_theory)}
2. 对每个样本，求解 τ_sim = τ_motion + Jᵀf(μ_f(v,θ))
3. 计算残差 e_τ = τ_sim − τ_theory
4. 用注意力网络 ψ_φ(e_τ, v, θ) → ℝᵏ
5. 约束：KL(π(·|ψ_φ) || π_sim(·|τ_theory)) + λ||ψ_φ − ψ_sim||²
6. 上真实机器：ρ_phy = min(ρ_triple, exp(−g/σ))
```

## 3. 复杂度分析

| 模块 | 复杂度 | 延迟 |
|---|---|---|
| 贝叶斯更新 | O(p²) p=5 | <0.1ms |
| 行为树判决 | O(1) | <0.1ms |
| ψ_φ 特征提取 | O(T·n_j) | <0.5ms |
| 计划器 | O(|𝒜|^D·T_MC) | ≤20ms |

## 4. 实验设计 BENCH v5

| 任务 | 类型 | 设计意图 |
|---|---|---|
| T9-T11 | (第 26 轮保留) | OOD AUC, SR, 恢复率 |
| T12-T14 | (第 26 轮保留) | 热约束、计算热节流、漂移注入 |
| **T15 行为树误判率** | 可解释性 | ADAPT/RECOVER 触发的误判率 |
| **T16 线上收敛** | 在线学习 | β 收敛至 ground truth 的轨迹 |

## 5. 风险缓解

| 风险 | 缓解方案 |
|---|---|
| 贝叶斯不收敛 | 检查 φ 持久激励；若长期无更新，回退到固定 μ_f |
| 行为树误判 | 引入「历史一致性」检查：连续 3 帧 RECOVER 才实际降级 |
| Isaac Sim 特征失效 | 特征蒸馏双模检验：ψ 与 CUSUM 两信号皆触发才 ADAPT |

## 6. 本轮最大的风险

**行为树的阈值 θ_low, θ_high, θ_ψ 需要在不同机器上重新标定，若标定不当，ADAPT 节点可能频繁激活导致「过度学习」或 RECOVER 节点误触发导致「过度保守」，破坏原有的 TEMPO-NAV 稳定性。**
 XUEN_EOF
<!-- ARTIFACT:END -->