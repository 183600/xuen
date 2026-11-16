# 第 3 轮产物 · 创新点清单 v10：**MetricVoiceGauge-ACMD-SG**（Metric Voice Gauge with Action-Chunk Certificates, Contract Middleware, Innovation Distillation, **Certificate Residual Sentinel & Gazebo-twin Calibration**）

> 背景：v9 MetricVoiceGauge-ACMD（定义 532–539；引理 82–86；实验 E551–E570）。
> 本轮灵感：「异常检测」×「Gazebo」
> **继承纪律**：MetricVoiceGauge 九不变式（CVC-闭环、SpatialCert、RT-CVC、FaultCert、PrimitiveGraph、严格退化链、OTL、GCT、ER）全部保留；v9 的 AC/MW/ID 三模块与 DA-ML/SPR/Cal 原样继承。新组件一律为**可选增强**：任一环节不可用 ⇒ 注入中立元或取离线最坏常数，严格等价退回 v9 行为（引理 89/93），而非行为漂移。**本轮不新增退化级**。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进（相对 MetricVoiceGauge-ACMD v9） |
|---|---|---|---|
| IP-340–356 | v9 全部模块 | 继承 | 语义不变；AC 的 trust_ok 改由三源证据融合（IP-357/360），K_eff 公式吸收 β_eff（定义 547） |
| IP-354 | ActionChunkCertifier | 语义升级 | 证书余量由固定 β 变为 `β_eff = β_sim + Γ`（定义 547）；β_eff 增大时 K_eff 单调收缩 |
| IP-355 | ContractMiddleware | 集成升级 | 新增契约行 `CRS`（0.05ms）与 `TGA`（周期任务）；哨兵拒绝作为 trust 事件注入同一 trust_ok 门，不新增分支 |
| IP-357 | CertificateResidualSentinel 证书残差哨兵 | 新增核心模块 | 单步特征残差的**快/慢双 e-process**；任意时刻可选停止且虚警 ≤ α（Ville）；拒绝当周期 K_eff←1 并切 p* |
| IP-358 | GazeboAnomalyInjectionBench 异常注入基准 | 新增核心模块 | A1–A6 六类注入 × 房间模板 × 固定种子；标定 μ₀/分位/λ 网格；产出检测延迟-虚警 Pareto 与预注册测试集 |
| IP-359 | AbortPointMCCertifier 中止点蒙特卡洛证书 | 新增核心模块 | 每个候选 p 做 N_mc 次扰动 rollout，Clopper–Pearson 单侧上界 `U(k,N,δ)≤ε_coll` 才纳入 P_t；与 F̂ 无关 |
| IP-360 | TwinGapAuditor 孪生差距审计器 | 新增核心模块 | 双样本 e-process/MMD 给出 D_sim 与 D_real 残差差距上界 Γ；β_eff=β_sim+Γ；Γ 不可认证 ⇒ K_eff≡1 |

**退化链声明（v10 复用 v9 五级，仅替换证据源）：**
- Level-1：AC 证书失效 / trust_ok 破坏。trust_ok 现为 `CRS 快慢哨兵均未拒 ∧ Δ_dom<τ_dom ∧ risk_SLAM<τ_SLAM ∧ Γ 已认证`；破坏 ⇒ K_eff←1，逐步执行，等价 v9 决策粒度；
- Level-2：MW 失效 ⇒ 切换 v9/v8 手写网关代码路径（代码保留），等价 v8 集成方式；
- Level-3：ID 失效 ⇒ 全模块 active、归因冻结，等价 v8 全模块常开；
- Level-4：v9 的 DA/SPR/Cal 任一失效 ⇒ 中立元注入（Δ_dom≡0 / risk_SLAM≡0 / sensor_weight≡1），等价 v7；
- Level-5：全失效 ⇒ 完整退回 v7，再退回 v6。
- **新增证据源的退化**（非新增级）：CRS 失效 ⇒ trust 退回仅用 Δ_dom（v9）；GAIB 失效 ⇒ 取保守静态 μ₀ 与 β_max；AMC 失效 ⇒ P_t 用定义 534；TGA 失效 ⇒ Γ≡Γ_max。

## 1. 符号体系增量（定义 540–548）

| 符号 | 含义 |
|---|---|
| r_t ∈ [0,B] | 单步特征残差（定义 540），由冻结 F̂ 与实测状态计算 |
| μ₀, q_{1−α_c} | 信任域标定残差均值（含裕度 η）与单侧分位数 |
| E_t^fast, E_b^slow | 单步快 e-process 与 W 步块均值慢 e-process（定义 541） |
| α_fast, α_slow | 快/慢检验显著性预算，独立分配，默认各 1e−3 |
| W | 慢哨兵块长，默认 W=20 周期（与 v9 Δ_dom 窗对齐，便于对比） |
| A = {A1..A6} | 异常注入类：尖峰/卡死/慢漂移/时延/障碍突现/打滑（定义 546） |
| Π_cal, Π_val, Π_test | Gazebo 标定/验证/测试场景集，按房间与种子不相交 |
| N_mc, k_p, U(k,N,δ) | 中止点 p 的蒙特卡洛次数、碰撞数、Clopper–Pearson 单侧上界 |
| ε_coll | 单中止点允许碰撞概率上界，默认 1e−4 |
| Γ_{1−δ_gap} | 仿真-现实残差分布差距的单侧置信上界（定义 544） |
| β_sim, β_max | 仿真标定余量、允许的最大余量（超过即 K_eff≡1） |
| β_eff | 真实侧有效余量：β_sim + Γ（定义 547） |
| st^trust ∈ {TRUSTED, DEGRADED, UNTRUSTED} | 三态信任机（定义 545） |

**新增定义 540（特征残差 FeatureResidual）** 对每个已执行步 (s_t,a_t,s_{t+1})，令 φ 为任务特征映射（间隙、速度、力矩、抓取置信、IMU 角速度）：
```
r_t = ‖ φ(s_{t+1}) − φ(F̂(s_t,a_t)) ‖_Σ / s_φ
```
s_φ 为标定尺度，使信任域内 r_t 量纲归一且经验上界为 B。F̂ 冻结（与 v9 定义 533 同一模型），故 r_t 只是“证书的现场体检”，不训练、不反馈。

**新增定义 541（残差 e-process ResidualEProcess）** 取可预测的固定/网格 bet λ ∈ (0, μ₀/(B−μ₀)]，定义
```
E_t^fast = ∏_{i=1}^t ( 1 + λ·(r_i/μ₀ − 1) )，  E_0 = 1
```
慢哨兵对块均值 \bar r_b = (1/W)Σ_{i∈block_b} r_i 构造 E_b^slow（同式）。原假设 H₀：E₀[r]≤μ₀（标定裕度 η>0 保证严格）。则 {E_t} 为非负超鞅，Ville 不等式给出 `P(∃t: E_t ≥ 1/α) ≤ α`。采用 |Λ| 个候选 λ 时按 Bonferroni 取 α/|Λ|（或在线自适应 bet 的亥姆霍兹机，保持 anytime-valid）。

**新增定义 542（双时间尺度哨兵 TwoScaleSentinel）** 输出 `reject ∈ {none, fast, slow}`：
- fast：E_t^fast ≥ 1/α_fast ⇒ 突发异常，立即拒绝；
- slow：E_b^slow ≥ 1/α_slow 且连续 H_slow=2 个块成立 ⇒ 漂移异常；
- 拒绝后清零对应 e-process（重置），并要求 H_rec=10 周期未拒才可回到 TRUSTED（防抖）。

**新增定义 543（Gazebo 异常注入基准 GAIB）** 场景集 Π = 房间模板 × 动态障碍密度 × 光照/反光；注入类 A 的物理语义：

| 类 | 注入 | Gazebo 实现 | 目标异常 |
|---|---|---|---|
| A1 | 传感器尖峰 | SensorSpikePlugin（高斯/脉冲叠加） | 观测离群 |
| A2 | 卡死/丢帧 | 固定最后值、按概率丢弃 | 观测冻结 |
| A3 | 慢漂移 | 噪声均值/方差线性漂移 | 分布缓变 |
| A4 | 执行时延 | 动作队列延迟 d 步、抖动 | 模型-执行错配 |
| A5 | 障碍突现 | PopInObstaclePlugin（块中插入） | 中块突变 |
| A6 | 打滑 | 轮地摩擦系数阶跃、外力扰动 | 动力学突变 |

标定协议：固定 `physics step=1ms`、固定随机种子、每 episode 记录 rosbag + 残差 CSV；Π_cal 上拟合 μ₀、q、λ 网格；Π_val 选阈值；**Π_test 只在预注册判据冻结后开跑**。

**新增定义 544（孪生差距 TwinGap）** 在重叠工况集 Π∩ 上取仿真残差样本 D_sim 与真实残差样本 D_real，定义
```
Γ_{1−δ} = sup_{u∈[0,1]} ( Q_real(u) − Q_sim(u) )_+  的单侧置信上界
```
以双样本 e-process（或 MMD 置换检验 + 自助上界）给出，置信 1−δ_gap。Γ 是“仿真证书在真实世界需要补的余量”。

**新增定义 545（信任状态机 TrustFSM）**
- TRUSTED：快/慢均未拒 ∧ Δ_dom<τ_dom ∧ risk_SLAM<τ_SLAM ∧ Γ 已认证；
- DEGRADED：fast 拒绝 ∨ Δ_dom≥τ_dom ∨ Γ∈(Γ_soft,Γ_hard] ⇒ K_eff 按定义 547 收缩；
- UNTRUSTED：slow 拒绝持续 ∨ β_eff≥β_max ⇒ K_eff≡1，立即以 p* 停驻并走 v9 单步路径；
- 回迁：UNTRUSTED→DEGRADED→TRUSTED 需连续 H_rec 周期无拒且 Δ_dom<τ_dom/2。

**新增定义 546（异常类谱 AnomalyTaxonomy）** A1–A6 及其可观测签名（均值移、方差胀、自相关升、残差偏置、残差突发）。每类给出最小可检测幅度 δ_min(α,β)，作为 GAIB 的覆盖指标。

**新增定义 547（有效证书余量与块长 EffectiveBeta）**
```
β_eff = min(β_max, β_sim + Γ_{1−δ_gap})
K_eff(t) = 1                                          若 UNTRUSTED
         = max(1, ⌊K_max·(1−Δ_dom/τ_dom)·(1−(β_eff−β_sim)/ (β_max−β_sim))⌋)   否则
```
第二条在 Γ=0 时退化为 v9 定义 539；Γ→β_max−β_sim 时 K_eff→1。**β 与 K 的耦合使“证据不足”自动变成“块更短”，无需新分支。**

**新增定义 548（场景覆盖证书 ScenarioCoverage）** C(Π_test) = 异常类 × 幅度 × 房间的覆盖矩阵；每个实验必须报告覆盖格与空置格，空置格视为该结论的未验证域，禁止外推。

## 2. 形式化定义（要点与升级）

**定义 532/533/534（动作块/块证书/中止点）** 继承 v9；定义 533 中 β 统一替换为 β_eff（定义 547）。
**定义 535（中间件契约）** 新增两行，其余不变：

| 模块 | D_m (ms) | Ŵ_m (ms) | v_m^⊥ | φ^elig |
|---|---|---|---|---|
| CRS 快哨兵（50Hz） | 0.05 | 0.05 | 不拒绝（恒等证据） | ✗ |
| CRS 慢哨兵（1/W Hz） | 0.02 | 0.02 | 不拒绝 | ✗ |
| TGA 审计（周期 10min） | 50 | 50 | Γ←Γ_max | ✗ |

**升级定义 496（软证书，v10）**
```
δ_trigger = {σ<τ_safe ∧ γ_grasp valid ∧ Δ_dom<τ_dom ∧ risk_SLAM<τ_SLAM ∧ Ĉ_t valid ∧ ¬CRS.reject}
```
六个条件同尺度；CRS 拒绝与 Δ_dom 越阈**同样**触发 M₀ 硬检查。引理 82+87+89 联合保证“块内软通过、硬失败”的空洞被哨兵堵住。

**升级定义 531（软硬约束衔接）** 中块守卫除证书/停车不变式外增加一条：CRS fast 拒绝 ⇒ 立即 abort 到 p*，不等块边界。

## 3. 关键算法骨架

```python
# IP-357 CertificateResidualSentinel：双时间尺度 anytime-valid 残差哨兵
class CertificateResidualSentinel:
    def __init__(self, mu0, B, alpha_fast=1e-3, alpha_slow=1e-3,
                 W=20, H_slow=2, H_rec=10, lam=None):
        assert 0 < mu0 < B
        self.mu0, self.B, self.W = mu0, B, W
        self.lam = lam or 0.5 * mu0 / (B - mu0)      # 非负因子 ⇒ 超鞅
        self.a_f, self.a_s, self.H_slow, self.H_rec = alpha_fast, alpha_slow, H_slow, H_rec
        self.E_fast = 1.0
        self.block_sum, self.block_n = 0.0, 0
        self.E_slow, self.slow_hits, self.clear = 1.0, 0, 0
        self.reject = 'none'

    def _bet(self, r):
        return 1.0 + self.lam * (r / self.mu0 - 1.0)  # ∈ [1-lam, 1+lam(B/mu0-1)]

    def observe(self, s, a, s_next):
        r = feature_residual(s, a, s_next)            # 定义 540
        self.E_fast *= self._bet(r)
        if self.E_fast >= 1.0 / self.a_f:
            self.reject = 'fast'
            self.E_fast = 1.0                          # 重置，防历史污染
            self.clear = 0
            return self.reject

        self.block_sum += r; self.block_n += 1
        if self.block_n == self.W:                     # 慢哨兵：块均值
            rbar = self.block_sum / self.W
            self.E_slow *= 1.0 + self.lam * (rbar / self.mu0 - 1.0)
            self.slow_hits = self.slow_hits + 1 if self.E_slow >= 1.0 / self.a_s else 0
            self.block_sum, self.block_n = 0.0, 0
            if self.slow_hits >= self.H_slow:
                self.reject = 'slow'
                self.E_slow, self.slow_hits = 1.0, 0
                self.clear = 0
                return self.reject

        self.reject = 'none'
        self.clear += 1
        return self.reject

    def trusted(self):
        return self.reject == 'none' and self.clear >= self.H_rec


# IP-358 GazeboAnomalyInjectionBench：异常注入与标定
class GazeboAnomalyInjectionBench:
    INJECTIONS = ['A1_spike', 'A2_stuck', 'A3_drift',
                  'A4_latency', 'A5_popin', 'A6_slip']
    def __init__(self, gazebo_runner, rooms, seeds, physics_step_ms=1):
        self.g, self.rooms, self.seeds = gazebo_runner, rooms, seeds
        self.step = physics_step_ms

    def calibrate(self):
        residuals, delays, far = [], [], []
        for room in self.rooms['cal']:
            for inj in self.INJECTIONS:
                for seed in self.seeds['cal']:
                    log = self.g.run(room, inj, seed, step_ms=self.step)
                    residuals += log.residuals              # 干净段
                    delays.append(log.first_cross_after_onset)
                    far.append(log.false_rejects)
        mu0 = quantile(residuals, 0.5) * (1 + ETA)       # 裕度 η
        B = max(residuals) * B_SCALE
        return {'mu0': mu0, 'B': B, 'residuals': residuals,
                'delay_pareto': (delays, far)}

    def evaluate_heldout(self, sentinel_factory):
        return {room: self.g.run(room, inj, seed)
                for room in self.rooms['test']
                for inj in self.INJECTIONS for seed in self.seeds['test']}


# IP-359 AbortPointMCCertifier：中止点的分布无关置信证书
class AbortPointMCCertifier:
    def __init__(self, gazebo_runner, N_mc=10000, delta=1e-3, eps_coll=1e-4):
        self.g, self.N, self.delta, self.eps = gazebo_runner, N_mc, delta, eps_coll

    def certify(self, state, chunk, p):
        k = 0
        for i in range(self.N):
            world = self.g.sample_disturbance(seed=i)     # 域随机化扰动
            traj = self.g.rollout_brake(state, chunk.actions[:p], world)
            k += int(traj.collides)
        return (k, clopper_pearson_upper(k, self.N, self.delta))

    def filter_points(self, state, chunk):
        pts = []
        for p in chunk.candidate_abort_indices:
            k, U = self.certify(state, chunk, p)
            if U <= self.eps:                              # 引理 90 才纳入
                pts.append(p)
        return pts


# IP-360 TwinGapAuditor：仿真-现实差距上界 Γ
class TwinGapAuditor:
    def __init__(self, delta_gap=1e-2):
        self.delta = delta_gap
    def gap_upper(self, sim_residuals, real_residuals):
        # 双样本 e-process / MMD 置换检验 + 自助上界（单侧）
        test = two_sample_e_process(sim_residuals, real_residuals)
        return test.quantile_gap_upper(conf=1 - self.delta)


# 主闭环：trust_ok 三源融合（不新增分支，只替换证据）
def metricvoicegauge_round_3(M, s, obs, audio_stream=None, ell=None, ...):
    ctx = mw_default_ctx()
    results = middleware.run_cycle(runners={
        'DA_ML':  lambda c: domain_adapter.update_and_measure(obs),
        'SPR':    lambda c: slam_risk.compute(M.slam_backend.get_latest_state()),
        'CAL_FI': lambda c: calib_fi.get_weights_kappa(),
        'CRS':    lambda c: sentinel.observe(prev_s, prev_a, obs.state),
        'OTL':    lambda c: online_learner.update_and_thresholds(c),
    }, ctx=ctx)
    ctx.delta_dom, ctx.tau_dom = results['DA_ML'], M.tau_dom

    # 证据融合：Γ 每 10min 审计一次；β_eff 随 Γ 诚实膨胀
    gamma = twin_gap.gap_upper(sim_buffer, real_buffer)     # 定义 544
    beta_eff = min(BETA_MAX, BETA_SIM + gamma)              # 定义 547
    trust = not (results['CRS'] == 'fast'
                 or ctx.delta_dom >= ctx.tau_dom
                 or ctx.risk_slam >= M.tau_slam
                 or gamma is None)

    if current_chunk is None or current_chunk.exhausted:
        current_chunk = chunker.generate_chunk(
            ctx.state, ctx.delta_dom, ctx.tau_dom,
            trust_ok=trust, beta=beta_eff)                  # 定义 533+547

    verdict, k_next = chunker.midchunk_guard(current_chunk, k_exec, live_obs)
    if results['CRS'] == 'fast' or verdict == 'abort':      # 引理 89 同 Level-1
        current_chunk.execute_safe_stop_at(k_next)
        current_chunk = None
    else:
        execute(current_chunk.actions[k_next])

    C, spatial_cert, claims, metrics, rewards = M.inherited_v8_path(ctx)
    distiller.step(cycle_idx, ctx)
    return C, spatial_cert, claims, metrics, rewards
```

## 4. 推导

**引理 87（哨兵随时有效性 / 虚警上界）** 设信任域内 E₀[r_t] ≤ μ₀ 且 r_t∈[0,B]，λ∈(0,μ₀/(B−μ₀)]。则 (E_t^fast) 为非负超鞅，`P(sup_t E_t^fast ≥ 1/α_fast) ≤ α_fast`；慢哨兵对块均值同理给出 `P(sup_b E_b^slow ≥ 1/α_slow) ≤ α_slow`。两检验独立分配预算，联合虚警 ≤ α_fast+α_slow。因结论对任意停时成立，50Hz 每周期检验无需多重比较校正。∎

**引理 88（检测延迟上界）** 若异常使 E[r_t] = μ₀+δ（δ>0），单步期望对数增量 `ℓ(δ)=log(1+λδ/μ₀)>0`，则快哨兵检测延迟 `T_fast ≤ log(1/α_fast)/ℓ(δ)`（期望意义，Wald）；慢哨兵对块均值偏移 δ̄ 的延迟 `T_slow ≤ W·log(1/α_slow)/log(1+λδ̄/μ₀)`。故 A1/A5/A6 类突变在 1–3 步内可检，A3 类缓变在 1–2 个 W 块内可检。∎

**引理 89（哨兵退化与 v9 Level-1 逐位等价）** CRS fast 拒绝 ⇒ trust=False ⇒ K_eff=1 且以 p* 停驻，与 v9 定义 539「U_t 不成立」分支的状态、动作、日志字段逐一相同（仅日志多一条 `evidence=CRS_fast`）；CRS 失效 ⇒ 关闭哨兵，trust 退化为 v9 的 `Δ_dom<τ_dom ∧ risk_SLAM<τ_SLAM`。故由 v9 引理 83，可观测行为等价 v9 对应退化级。∎

**引理 90（中止点证书覆盖）** 若 p 的碰撞指示在 N_mc 次独立扰动下为 Bernoulli(p_coll)，Clopper–Pearson 单侧上界 U(k,N,δ) 满足 `P(p_coll ≤ U(k,N,δ)) ≥ 1−δ`。仅当 U≤ε_coll 才把 p 纳入 P_t，故每个被接受中止点的真实碰撞概率 ≤ε_coll（置信 1−δ），与 F̂ 无关。对 |P_t| 个点做 Bonferroni，δ'=δ/|P_t| 保持族覆盖。∎

**引理 91（差距诚实性与块证书可靠性）** 若双样本检验给出 `sup_u(Q_real(u)−Q_sim(u))_+ ≤ Γ`（置信 1−δ_gap），且仿真实测 `‖F̂−F‖∞ ≤ β_sim`（引理 82 前提），则真实侧预测误差 ≤ β_sim+Γ=β_eff；于是引理 82 在 β=β_eff 下成立，块证书保守有效、中止安全。若 Γ 不可认证或 β_eff≥β_max，定义 547 令 K_eff≡1，退回 v9 逐步，引理 82 的 K=1 分支仍成立。∎

**引理 92（无虚警风暴 / 无 Zeno）** 由引理 87，每 episode 期望快/慢虚警次数 ≤ α_fast·T + α_slow·T/W；H_rec=10 的滞回使状态翻转最小间隔 ≥H_rec 周期，故有限时域内迁移次数有限，翻转率 ≤1/(H_rec·Δt)。并行 |Π_test| 个场景时按 Bonferroni 取 α'=α/|Π_test|，族虚警仍受控。∎

**引理 93（单调退化）** 定义 547 中 K_eff 关于 Γ 单调不增：Γ=0 时等于 v9 定义 539 的 K_eff；Γ↑(β_max−β_sim) 时因子→0，K_eff→1。且 β_eff≥β_max 时 TrustFSM 进入 UNTRUSTED，K_eff≡1。故“证据质量下降”严格导出“块长不增、最终退回 v9”，不存在证据变差而 K_eff 变大的反例。∎

**推论 94（v9 最大风险的闭环）** 若真实跳变使 r_t 的均值在 D 步内上升 δ 且 δ>δ_min，则由引理 88，快哨兵在 ≤log(1/α_fast)/ℓ(δ) 步内拒绝，早于 Δ_dom 的 20 帧滑窗；当周期 K_eff←1 并 p* 停驻。故 v9 的“20 帧滞后暴露失效证书”在 δ 可检时被消除；残余风险仅在 δ<δ_min 的慢漂移（见第 8 节）。∎

## 5. 复杂度分析

| 组件 | 域 | 时间 | 空间 | 正确性锚 |
|---|---|---|---|---|
| CRS 快哨兵（50Hz） | 在线 | ≤0.05ms（残差 + 2 次乘加） | O(1) | 定义 540/541，引理 87 |
| CRS 慢哨兵（每 W 周期） | 在线 | ≤0.02ms 摊销 | O(W) 环缓冲 | 定义 542 |
| AMC 中止点证书 | 离线/块边界缓存 | O(N_mc·K·d) per candidate；N_mc=1e4、K≤10 约数秒，缓存复用 | O(N_mc) 采样 | 定义 543，引理 90 |
| GAIB 标定 | 离线 | 场景×注入×种子，小时级 | 日志存储 | 定义 543，P14 |
| TGA 差距审计 | 周期（10min） | O(n_sim+n_real) 双样本检验，≤50ms | O(n) 残差样本 | 定义 544，引理 91 |
| v9 继承路径 | 在线 | ≤4ms（不变） | 不变 | 定义 493–539 |
| 决策侧合计 | 在线 | 典型 ≤8.1ms，p99 ≤20ms（新增 ≤0.1ms） | — | 引理 86+87 |

## 6. 实验设计 E571–E590

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E571 | 突变检测延迟（A5 障碍突现） | CRS 中位延迟 ≤3 周期，对比 Δ_dom ≥20 周期 |
| E572 | 标称虚警率 | 干净长跑中快/慢虚警率分别 ≤α_fast/α_slow（95% 置信） |
| E573 | A1–A6 可检测幅度 δ_min | 每类给出 δ_min(α,β)，A3 单独报告慢漂移边界 |
| E574 | Gazebo 注入保真度 | 各类真实日志与仿真残差签名距离 ≤0.1（归一化） |
| E575 | AMC 覆盖正确性 | 100 个中止点，CP 覆盖率 ≥1−δ；实际碰撞率 ≤ε_coll |
| E576 | 孪生差距 Γ 标定 | Γ 对未见房间的覆盖 ≥95%；报告 Γ 随房间的分布 |
| E577 | β_eff 迁移可靠性 | 真实/高保真测试集碰撞 ≤ 引理 91 上界 |
| E578 | v9 风险闭环 | 注入真实跳变，K_eff 在 ≤3 步内塌缩至 1，0 碰撞 |
| E579 | 传感器异常 A1/A2 | 尖峰/卡死下 0 碰撞，误停 ≤5% |
| E580 | 执行异常 A4/A6 | 时延/打滑下证书失效检出 ≥99%，退化无跳变 |
| E581 | 中块障碍突现 A5 | 中止成功 ≥99.5%，0 碰撞，停驻距离合规 |
| E582 | 慢漂移 A3 / 隐蔽异常 | 慢哨兵检测延迟 ≤2 块；识别 δ<δ_min 盲区并量化 |
| E583 | 场景模糊测试 | 10k 随机场景无崩溃、无越界、退化链可达 |
| E584 | 长跑孪生漂移 | 8h 内 Γ 漂移趋势，触发重标定的阈值 |
| E585 | 证据融合虚警 | CRS∧Δ_dom 联合虚警 ≤ α_fast+α_slow+α_dom |
| E586 | 真实日志影子验证 | 离线回放真实 rosbag，CRS 在线可运行、延迟达标 |
| E587 | 端到端全任务 | RoboCup@Home 仿真 ≥ v9 +10% |
| E588 | 哨兵开销 | 50Hz 下 WCET p99 增量 ≤0.1ms，0 丢拍 |
| E589 | 基准可复现性 | 相同种子逐位复现；发布 GAIB 场景清单与残差集 |
| E590 | 综合竞赛模拟 | ≥ v9 +15% |

## 7. 预注册判据

| 判据 | 门槛（预注册） | 若未达标的处置 |
|---|---|---|
| 突变延迟（E571） | 中位 ≤3 周期 | 增大 λ、缩短 W 仅用于慢哨兵、检查特征 φ |
| 虚警（E572） | ≤α（95% CP 上界） | 增大 μ₀ 裕度 η、降低 λ、增加 H_rec |
| 可检测幅度（E573） | A1/A5/A6 δ_min 足够小 | 改 φ（加接触/IMU 特征）、换更强 F̂ |
| 注入保真（E574） | 距离 ≤0.1 | 补注入物理、做域随机化、报告空置格 |
| AMC 覆盖（E575） | CP 覆盖 ≥1−δ | 增大 N_mc、收紧 ε_coll、修扰动模型 |
| Γ 标定（E576） | 未见房间覆盖 ≥95% | 扩 Π_cal、按房间分层 Γ、必要时 β_max |
| β_eff 迁移（E577） | 碰撞 ≤ 引理 91 上界 | 改用更保守 Γ、降低 K_max |
| 风险闭环（E578） | ≤3 步塌缩、0 碰撞 | 调 α_fast、加 A5 专用特征、缩短 K_max |
| 传感器异常（E579） | 0 碰撞、误停 ≤5% | 降 α、加 A2 冻结检测 |
| 执行异常（E580） | 检出 ≥99% | 增动作延迟特征、快哨兵加权 |
| 中块突现（E581） | ≥99.5%、0 碰撞 | 增中止点密度、减小 β_eff |
| 慢漂移（E582） | 延迟 ≤2 块 | 增大 W、加 CUSUM 辅助、明确盲区 |
| 模糊测试（E583） | 0 崩溃/越界 | 修契约中立元、补断言 |
| 长跑（E584） | Γ 趋势可解释、无爆炸 | 周期重标定、按环境切换 Γ 表 |
| 融合虚警（E585） | ≤预算和 | 收紧 Δ_dom、冻结 α 分配 |
| 影子验证（E586） | 可在线、延迟达标 | 离线批处理、特征降维 |
| 端到端（E587） | ≥v9+10% | 回退 K_eff 上限、调 β_sim |
| 开销（E588） | 增量 ≤0.1ms、0 丢拍 | 残差计算移 SIMD、慢哨兵降频 |
| 可复现（E589） | 同种子逐位复现 | 固定物理步长、记录版本与插件哈希 |
| 竞赛（E590） | ≥v9+15% | 综合调参、分析失分瓶颈 |

## 8. 本轮最大风险

**一句话**：双时间尺度哨兵仍以“信任域内残差与标定分布可比（近似可交换/有界）”为数学前提，而最危险的异常恰是**缓慢、协同的分布漂移**——单步残差始终像正常噪声，慢哨兵的 W 步块又可能被标定集中的同类漂移“合理吸收”；此时快、慢哨兵与 Δ_dom 三者可能同时沉默，系统仍会在大 K_eff 块上暴露失效证书。
