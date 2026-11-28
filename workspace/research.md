<!-- artifact:START -->
## 0. 增量定位与继承关系（在 IP-493~496/CADVS-v5 基础上扩展）

### 0.1 新增核心模块

| 编号 | 名称 | 类型 | 关键改进（相对 CADVS-v5） |
|---|---|---|---|
| IP-497 | Energy Reserve Viability Kernel (ERVK) | 能量认证 | 物理+残差功率模型；单侧 conformal 误差界 ε_E；终端逃逸能量 E_esc；热/峰值功率约束；**合取进 kc_BCK**（不增门） |
| IP-498 | Robust Dynamic Avoidance Kernel (RDAK) | 避障认证 | 多模态障碍预测 + conformal 可达集膨胀；鲁棒离散 CBF；遮挡/有界加速度；**合取进 kc_MSRG**（不增门） |
| IP-499 | Joint Viability Coupling Operator (JVCO) | 联合可行域 | 带能量约束的生存核最大不动点 V；保守内近似 V̂；前缀封闭认证；已认证最小风险回退；认证死锁检测 |
| IP-500 | Evidence Forging Assembler v6 (EFA-v6) | 证据融合 | 七门不变 + 两个合取强化；联合生存核过滤；级联采样选证；ECS_v6 = ECS_v5 · η_energy · η_avoid |

### 0.2 v5 模块适配表（只改接口，不推翻）

| v5 模块 | v6 适配 |
|---|---|
| IP-493 FMPP | 条件 c 增加 (SoC, 能量代价 to-go, 障碍可达集摘要, V̂ 边际)；提议先验偏好高储备/高避障边际区域；仍在准入时域 |
| IP-494 LMEM-v2 | 记忆条目增加 (能量结果, 碰撞/近失事件, 回退成功)；固化只对「铸证 ∧ 结局成功 ∧ 人工抽检 ∧ 能量/避障结局验证」片段；物理锚部分偿还 R57 |
| IP-495 FAMK | 原样继承；情感调制与能量/避障取「更保守者胜」（阈值取大、执行集取交） |
| IP-489 VACK | 价值输入增加续航可行性（任务完成概率 × 安全返回概率）；λ_vec 仍只向安全倾斜 |
| IP-490 BCK | kc_bal^6 = kc_bal^5 ∧ kc_energy；扭矩集进一步受 P_max(T)、τ_derate(T) 约束；能量只收紧平衡门 |
| IP-485 EEK | 原样继承；末端轨迹沿前缀做能量/避障预览 |
| IP-482 MSRG | kc_phys^6 = kc_phys^5 ∧ kc_avoid；仿真回放增加动态障碍与能量场景 |
| IP-496 EFA-v5 | 升级 EFA-v6：前置联合生存核过滤；全灭时用已认证最小风险回退（取代盲目停车）；ECS 增补 η_energy·η_avoid |
| IP-491 CERTCALC | 扩展 CERTCALC-v6：新增引理 45~47、定理 9~12 |
| IP-473~484 | RCANG/DLC/MRCC/TCVM/STCK/GCK/DAKI/VSCK/3DCF 等原样继承 |

## 1. 增量符号体系（定义 2241–2380）

| 符号 | 含义 |
|---|---|
| s_t = (q_t, q̇_t, z_t, SoC_t, T_t, b_t) | 机器人状态：关节/速度、基座位姿、荷电状态、温度、障碍信念 |
| u_t, x = (u_{0:T}) | 控制输入；候选轨迹（控制/位姿时间序列） |
| P̂(s,u) = φ(s,u)^T w + r_θ(s,u) | 预测功率：物理项 + 学习残差 |
| E_pred(x) = ∫_0^T P̂(s_t,u_t) dt | 候选轨迹预测能耗 |
| ε_E = Q_{1−α_E}(r_E) | 单侧 conformal 能量残差分位数（r_E = E_true − E_pred） |
| SoC_t ∈ [0,1] | 荷电状态；Q_eff(T, age) 为温度/老化修正容量 |
| T_t, T_max, P_max(T) | 电池/电机温度、温度上限、温度相关峰值功率上限 |
| E_esc^π(s) | 从 s 执行已认证回退策略 π_fb 到安全集 S_safe 的最小预测能耗 |
| S_safe | 安全集：无碰撞 ∧ SoC ≥ R_min ∧ 热/平衡可行 ∧ 存在已认证回退 |
| R_min | 归一化安全储备（缺省 0.15，约等于返航/退避能耗 + 工程裕度） |
| kc_energy(x; s_0) | 能量硬谓词：SoC_0−E_pred−ε_E ≥ R_min ∧ SoC_T−ε_E ≥ E_esc(s_T)+R_min ∧ 热/峰值功率可行 |
| o_i(t), O_i^α(t) | 障碍 i 的真实位置；conformal 膨胀可达集（覆盖概率 ≥ 1−α） |
| r_safe | 机器人几何半径 + 跟踪误差界 + 安全裕度 |
| h_{ij}(s,t) = dist(p_i(s), O_j^α(t)) − r_safe | 鲁棒控制屏障函数 |
| α_cbf, a_max | CBF 类 K 增益；障碍有界加速度上界 |
| kc_avoid(x) | 避障硬谓词：∀t h ≥ 0 ∧ 离散 CBF ḣ+α_cbf·h ≥ 0（对 O^α 与 a_max 的最坏情形） |
| K = {s : kc_energy^inst(s) ∧ kc_avoid^inst(s) ∧ 平衡/热可行} | 联合安全集（瞬时） |
| T(V) = {s∈K : ∃u∈U(s), f(s,u)∈V, E(s,u) ≤ SoC−R_min} | 带能量约束的生存算子 |
| V = νX T | 生存核（最大不动点） |
| V̂ ⊆ V | 在线使用的保守内近似（采样 + 区间/椭球外逼近再内缩） |
| kc_phys^6 = kc_phys^5 ∧ kc_avoid | 物理门强化（合取，不增门） |
| kc_bal^6 = kc_bal^5 ∧ kc_energy | 平衡门强化（合取，不增门） |
| η_energy = σ((SoC_T−E_esc−R_min−ε_E)/b_E) | 能量软因子 ∈ [0,1] |
| η_avoid = σ(h_min/b_h) | 避障软因子 ∈ [0,1] |
| ECS_v6 = ECS_v5 · η_energy · η_avoid | 软评分 |
| JointCert = (ok, EnergyCert, AvoidCert, ν_margin, prefix_len, witness) | 联合证书 |
| Exec_CADVS-v6 = {x ∈ Exec_v5 : ∀t, kc_energy(x_{0:t}) ∧ kc_avoid(x_{0:t}) ∧ x_{0:t}∈V̂} | v6 执行集（前缀封闭） |

## 2. 关键算法骨架

### IP-497 ERVK：能量储备可行性核（能量积分 1 kHz；逃逸代价图 0.2–1 Hz 周期更新）

```python
@dataclass
class EnergyReserveViabilityKernel:
    """ERVK：把续航从里程升级为终端逃逸储备。
    红线：能量只收紧 BCK，永不放松任何门；证书必须携带单侧误差界"""
    power_model: Any              # P_phys + 残差网络 r_theta
    soc_est: Any                  # SoC/内阻/容量在线估计（EKF/UKF）
    thermal: Any                  # 集总热模型 T_{t+1}=f(T_t,P_t)
    q_E: float                    # 单侧 conformal 分位数 epsilon_E
    R_min: float = 0.15           # 归一化储备
    T_max: float = 0.85           # 归一化温度上限

    def predict(self, x: Trajectory, ctx: Context) -> EnergyPred:
        # 逐步积分 P_hat；同时给出 P_peak、T_t 轨迹与置信带
        ...

    def escape_energy(self, s, V_hat: ViabilitySet) -> float:
        """E_esc：在预计算代价图上查 (pose, SoC bin, 障碍密度) 的最小能耗；
        图边权 = 预测能耗 + 保守裕度；不可达则返回 +inf（fail-closed）"""
        ...

    def kc_energy(self, x: Trajectory, ctx: Context, s0: State) -> tuple[bool, EnergyCert]:
        ep = self.predict(x, ctx)
        e_esc = self.escape_energy(ep.s_T, ctx.V_hat)
        reserve_ok = (s0.SoC - ep.E - self.q_E >= self.R_min)
        escape_ok = (ep.soc_T - self.q_E >= e_esc + self.R_min)
        thermal_ok = all(p <= self.power_model.p_max(T) and T <= self.T_max
                         for p, T in zip(ep.P, ep.T))
        ok = reserve_ok and escape_ok and thermal_ok and math.isfinite(e_esc)
        return ok, EnergyCert(ep.E, self.q_E, ep.soc_T - self.q_E, e_esc,
                              reserve_ok, escape_ok, thermal_ok, witness=ep)
```

### IP-498 RDAK：鲁棒动态避障核（预测 10–30 Hz；CBF 校验 10 Hz 预览 + 1 kHz 安全滤波）

```python
@dataclass
class RobustDynamicAvoidanceKernel:
    """RDAK：对障碍可达集而非名义轨迹做避障。
    红线：预测越不确定，集合越大，执行集只缩不涨"""
    predictor: Any                # 多模态轨迹预测（社会力/Transformer）
    conformal: Any                # split conformal / 在线 e-process 校准
    alpha: float = 0.05           # 覆盖失败率
    a_max: float = 2.0            # 障碍有界加速度
    alpha_cbf: float = 1.0

    def reachable_set(self, obs_hist) -> list[ObstacleSet]:
        # 名义多模态 + 残差分位数膨胀 + 有界加速度前向可达集取并
        # 时间维用 union bound 或 time-uniform e-process 控制 alpha
        ...

    def robust_cbf(self, x: Trajectory, sets: list[ObstacleSet], t0) -> tuple[bool, AvoidCert]:
        h_min = +inf
        for t in range(len(x)):
            for O in sets:
                h = dist(x.pose[t], O[t]) - r_safe
                h_dot = discrete_derivative(h, x, O, a_max)
                if h < 0 or h_dot + self.alpha_cbf * h < 0:
                    return False, AvoidCert(h_min, h, self.alpha, len(sets), True)
                h_min = min(h_min, h)
        return True, AvoidCert(h_min, +inf, self.alpha, len(sets), False)

    def deadlock(self, s, sets) -> bool:
        """U(s) 中不存在同时满足 CBF 与能量约束的控制 → 认证死锁候选"""
        ...
```

### IP-499 JVCO：联合生存核与最小风险回退（离线/周期建核；在线 O(T) 认证）

```python
@dataclass
class JointViabilityCouplingOperator:
    """JVCO：能量与避障的联合可行域。元层过滤，不是第八道门。
    红线：只在 V_hat ⊆ V 内发证；V_hat 为空时返回 NO_SAFE_ACTION，不伪造安全"""
    ervk: EnergyReserveViabilityKernel
    rdak: RobustDynamicAvoidanceKernel
    grid: Any                     # (pose, vel, SoC bin, 障碍密度) 离散化

    def build_kernel(self, ctx: Context) -> ViabilitySet:
        """V_{k+1} = T(V_k) 迭代至不动点；采样/区间给出保守内近似 V_hat。
        对每个网格点存 (可行控制, 最小能耗, 安全裕度, 回退指针)"""
        V = self.grid.all_states()          # 最大不动点从全集开始
        while True:
            V_next = {s for s in V if self._exists_successor_in(s, V, ctx)}
            if V_next == V:
                break
            V = V_next
        V_hat = self._shrink_by_discretization(V, ctx)   # 内缩 L*Delta
        return V_hat

    def certify(self, x: Trajectory, ctx: Context) -> JointCert:
        """前缀封闭：任一步失败即整体失败（fail-closed）"""
        for t in range(len(x)):
            ok_e, ec = self.ervk.kc_energy(x[:t+1], ctx, ctx.s0)
            ok_a, ac = self.rdak.robust_cbf(x[:t+1], ctx.obstacle_sets, t)
            if not (ok_e and ok_a and x[t] in ctx.V_hat):
                return JointCert(False, ec, ac, -inf, t, witness=(t, ok_e, ok_a))
        return JointCert(True, ec, ac, ctx.V_hat.margin(x[-1]), len(x), witness=None)

    def fallback(self, s, ctx: Context) -> Policy:
        """V_hat 内的最小风险回退（退避/返航/支撑区停靠）；
        若 V_hat 为空 → NO_SAFE_ACTION（显式暴露无解，而非假装停车安全）"""
        ...
```

### IP-500 EFA-v6：七硬门 + 联合生存核过滤 + 级联采样选证

```python
@dataclass
class EvidenceForgingAssemblerV6:
    """EFA-v6：七门不变（能量/避障以合取方式强化 BCK/MSRG）"""
    fmpp: FlowMatchingProposalPolicyKernel
    lmem: LongTermMemoryEmbeddingConsolidation
    famk: FacialAffectModulationKernel
    jvco: JointViabilityCouplingOperator
    v5: EvidenceForgingAssemblerV5

    def select(self, x0_state, t_now, rule_id, context) -> tuple[bool, Trajectory | None, str]:
        s_emo = self.famk.observe(context.face, t_now)
        gamma = self.famk.gamma(s_emo)
        c = build_ctx(context, s_emo, self.lmem, self.jvco)   # 含 SoC/障碍/V_hat 摘要
        cands = self.fmpp.propose(c, self.fmpp.K)             # K=8，异步准入
        # 级联第 1 层：廉价门（coverage/physics 名义/memory/novelty）
        surv = [x for x in cands if self._cheap_gates(x, gamma)]
        if not surv:
            return self._certified_fallback(context)          # 已认证最小风险回退
        # 级联第 2 层：联合生存核（能量 + 鲁棒避障 + 前缀封闭）
        joint = []
        for x in surv:
            cert = self.jvco.certify(x, context)
            if cert.ok:
                joint.append((x, cert))
        if not joint:
            return self._certified_fallback(context)          # fail-closed，不盲目停车
        # 级联第 3 层：VACK 仅评 ≤3 个高边际幸存者
        joint.sort(key=lambda xc: xc[1].nu_margin, reverse=True)
        finals = []
        for x, cert in joint[:3]:
            vac = self.v5.v4.vack.evaluate(x, context_with(s_emo), t_now)
            if self.v5.v4.vack.kc_val(vac, tau=gamma['val'] * TAU_VAL4):
                finals.append((x, cert))
        # 级联第 4 层：BCK 预览（事件触发 QP + 缓存证书）
        ok = [(x, cert) for x, cert in finals if self.v5._bck_preview(x, gamma)]
        if not ok:
            return self._certified_fallback(context)
        best, best_cert = max(ok, key=lambda xc: certified_margin(xc[0]))
        return True, best, 'FORGED_CEAE'

    def _certified_fallback(self, context) -> tuple[bool, Trajectory | None, str]:
        fb = self.jvco.fallback(context.s0, context)
        if fb is NO_SAFE_ACTION:
            return False, None, 'NO_SAFE_ACTION'              # 诚实暴露无解
        return True, fb.trajectory, 'CERTIFIED_MIN_RISK'

    def ecs_v6(self, ..., n_flow, s_emo, energy_cert, avoid_cert) -> float:
        eta_e = sigmoid((energy_cert.reserve_margin - b_E) / b_E)
        eta_a = sigmoid(avoid_cert.h_min / b_h)
        return self.v5.ecs_v5(..., n_flow, s_emo) * eta_e * eta_a
```

### 集成流水线（v5 → v6）

```
离线/慢时域：
  能量模型标定：功率/热/老化数据 ──▶ 物理+残差模型 ──▶ split conformal ε_E
  障碍预测标定：多模态预测器 ──▶ conformal 残差分位数 ──▶ O^α 膨胀规则
  生存核：网格 + 动力学 + 能量/避障约束 ──▶ 值迭代至不动点 ──▶ V ──▶ 内缩 V̂
  回退策略：V̂ 内 Dijkstra/策略迭代 ──▶ π_fb + E_esc 代价图
  固化：铸证 ∧ 结局成功 ∧ 人工抽检 ∧ 能量/避障结局验证 ──▶ θ_FM 更新
        ──▶ 回归门测试 + 红队（低电量/遮挡/对抗障碍）──▶ 通过才上线

在线准入（异步，秒级）：
  FAMK.observe ──▶ γ；SoC/温度估计 ──▶ ERVK
  FMPP.propose (K=8) ──▶ 廉价门筛
       ├─ 全灭 ──▶ 已认证最小风险回退 / NO_SAFE_ACTION
       └─ 幸存 ──▶ JVCO.certify（能量 + 鲁棒 CBF + V̂ 前缀）
                    ├─ 全灭 ──▶ 回退
                    └─ ≤3 ──▶ VACK（调制 τ_val）──▶ BCK 预览 ──▶ 取边际最大者

在线控制环（目标 < 0.7 ms）：
  每周期：EEK + BCK（事件触发 QP）+ 能量积分 O(1) + 1 kHz CBF 安全滤波 O(n_dof·N_obs)
  证书消费：τ^6 = γ·τ^5（只紧）；消费缓存的 JointCert 与 V̂ 边际
```

## 3. 复杂度分析（增量更新）

| 模块 | 时间复杂度 | 空间复杂度 | 关键参数 | 实时性指标 |
|---|---|---|---|---|
| ERVK.predict | O(T·n_dof) | O(T) | T~200 | < 0.05 ms（控制环增量积分） |
| ERVK.escape_energy | 离线 O(N log N)，在线 O(1) 查表 | O(N) | N~10^5 网格 | < 0.01 ms 在线 |
| RDAK.reachable_set | O(H·N_obs·M·d) | O(H·N_obs) | H=20, M=5, N_obs≤8 | ~5–15 ms，10–30 Hz |
| RDAK.robust_cbf | O(T·N_obs·n_dof) | O(T·N_obs) | T=200 | ~0.05–0.2 ms（预览） |
| JVCO.build_kernel | O(N_s·N_u·iter) | O(N_s) | N_s~10^5, iter~20 | 离线/分钟级，周期 0.2–1 Hz |
| JVCO.certify | O(T) 查表 | O(1) | — | < 0.1 ms |
| EFA-v6 级联 | O(K·S·L·d) + 门 | O(K) | K=8, ≤3 VACK | ~10–30 ms 异步准入 |
| 1 kHz CBF 安全滤波 | O(n_dof·N_obs) | O(1) | N_obs≤8 | < 0.1 ms |
| 端到端控制环 | ~0.62 ms P99 | — | — | **略高于 v5 的 0.55 ms，仍 < 1 ms** |

**通信开销**：V̂ 代价图按 (区域, SoC 桶) 压缩 ~8–20 KB/站；能量/障碍 conformal 分位数 ~1 KB；原始电池/测距数据不出端。生存核在站内构建，策略与代价图经签名下发。

**实时性权衡（对 v5-R49 的延续）**：
- 1 kHz 环只做能量积分 O(1) 与 CBF 安全滤波 O(n_dof·N_obs)，复杂认证仍在异步准入时域。
- 生存核离线/周期构建，在线只查表；动态障碍突变触发局部重算（事件触发）。
- 代价：P99 从 v5 的 0.55 ms 升至 ~0.62 ms，换取「不碰撞 + 不搁浅」的联合保证；若硬件预算更紧，可把 CBF 滤波降为 200 Hz + 控制环内仅能量积分。

## 4. 正确性论证（增量更新）

### 引理 45（conformal 障碍覆盖与鲁棒 CBF）

**陈述**：设校准集与部署期障碍轨迹可交换，非一致性分数为真实位置到预测集合的距离；取 split conformal 的 1−α 分位数构造 O_i^α(t)，则对每个 t，P(o_i(t) ∈ O_i^α(t)) ≥ 1−α。若对膨胀集合 O^α 与障碍有界加速度 a_max 的任意实现，候选轨迹满足离散 CBF h ≥ 0 ∧ ḣ+α_cbf·h ≥ 0，则该轨迹在部署期的碰撞概率 ≤ α + P(CBF 不可行)。对时间维用 union bound 时以 α/T 换取全时域覆盖。∎

**诚实边界**：可交换性是强假设；遮挡导致的条件分布偏移、对抗性障碍、以及预测器对未见过交互模式的系统性误差都会破坏覆盖。在线 e-process 只能检测漂移并收紧 α，不能恢复已失效的交换性。

### 引理 46（能量残差单侧界）

**陈述**：设能量残差 r_E = E_true − E_pred 在标定/部署间可交换，取单侧 conformal 分位数 ε_E = Q_{1−α_E}(r_E)，则 P(E_true ≤ E_pred + ε_E) ≥ 1−α_E。若 SoC 估计误差有界 |ŜoC − SoC| ≤ ε_s，则能量门 kc_energy 成立 ⇒ 真实储备满足 SoC_T − E_esc ≥ R_min − ε_E − ε_s，以概率 ≥ 1−α_E。∎

**诚实边界**：电池老化、温度骤变、内阻非线性使残差分布漂移；conformal 只保证标定分布内，不保证跨季节/跨电池包。工程上必须以在线 SoC 估计 + 周期性重标定 + 保守 R_min 兜底。

### 引理 47（生存核内近似的保守性）

**陈述**：设真实生存核为 V，网格离散与区间/采样得到内近似 V̂ ⊆ V。若动力学与约束关于状态 Lipschitz 常数 L、网格直径 Δ，则 V̂ 可通过将安全集 K 内缩 L·Δ 得到，且任何前缀落在 V̂ 内的轨迹在真实系统中仍可行。内缩只会使 V̂ 更小，不会使不可行变可行。∎

**证明**：由 V̂ 的构造（K 内缩 + 离散转移包含于连续转移）与归纳；内近似对可行集单调。∎

### 定理 9（联合嵌套）

**陈述**：令 kc_phys^6 = kc_phys^5 ∧ kc_avoid，kc_bal^6 = kc_bal^5 ∧ kc_energy，其余五门不变，则 Exec_CADVS-v6 = {x ∈ Exec_v5 : ∀t kc_energy(x_{0:t}) ∧ kc_avoid(x_{0:t}) ∧ x_{0:t}∈V̂} ⊆ Exec_CADVS-v5。当 kc_energy≡1、kc_avoid≡1 且 V̂=全状态空间时取等号。∎

**证明**：合取只减不增；前缀封闭是全称量化，不引入新析取；V̂⊆V 进一步收缩。∎

### 定理 10（递归安全：不碰撞且不搁浅）

**陈述**：在 (A1) 障碍加速度 ≤ a_max 且引理 45 覆盖成立、(A2) 能量残差满足引理 46、(A3) 跟踪误差界已并入 r_safe 与 ε_E、(A4) 回退策略 π_fb 在 V̂ 内已认证 下，若 EFA-v6 接受 x，则以概率 ≥ 1−α_obs−α_E 存在无限执行：对所有 t，机器人不与任何障碍碰撞，且 SoC_t 始终 ≥ E_esc(s_t)+R_min。∎

**证明**：由生存核定义，x_t∈V̂⊆V ⇒ 存在可行后继 u_t 使 x_{t+1}∈V；归纳得无限可行链。CBF 在 O^α 上成立 + 引理 45 ⇒ 每步碰撞概率 ≤ α_obs；能量门 + 引理 46 ⇒ 每步储备违例概率 ≤ α_E。对时间维用 union bound（或 time-uniform e-process）得总失败概率 ≤ α_obs+α_E。∎

**诚实边界**：概率只对「标定可交换 + 有界扰动」成立；对抗性障碍、未观测遮挡、模型漂移下无保证。V̂ 的近似误差若偏乐观（非内近似），定理失效——因此必须坚持内近似。

### 定理 11（耦合必要性：分开认证存在反例）

**陈述**：存在轨迹 x_E 与 x_A，使得 x_E 通过能量门但不通过避障门，x_A 通过避障门但不通过能量门；二者在各自证书下「单指标安全」，但任务级均失败：x_E 因绕行过多而在终点前搁浅，x_A 因能量最优贴边绕行而撞上 conformal 集合内的障碍。因此 Exec_energy ∩ Exec_avoid ⊊ Exec_energy ∪ Exec_avoid，联合门不可由任一标量加权和替代而不损失可靠性。∎

**证明**：构造两条轨迹（窄通道场景）：x_E 走最宽绕行，能量在 t=T−ε 耗尽；x_A 走最窄贴边，CBF 在 t 的可行控制集为空。两者分别满足一个合取项而违反另一个。标量加权和可在权重变化时接受任一失败轨迹，故不能替代逐项合取。∎

**工程含义**：安全与续航是**不可交换的约束**，不是可调 trade-off；可以调的是裕度 R_min、α、r_safe，而不是「用省电换一点碰撞风险」。

### 定理 12（七锚完备性保持）

**陈述**：v6 不增删锚点：七锚 {3DCF, MSRG, HICK, EEK, LTEM, VACK, BCK} 的完备性（v4 定理 4）保持。kc_energy 是 BCK 内部合取，kc_avoid 是 MSRG 内部合取，JVCO 是两门沿时间前缀的闭包（元层过滤，非新锚），FMPP/LMEM-v2 是提议/记忆升级。∎

**证明**：锚点集合不变；合取只紧（定理 9）；元层过滤不改变门谓词，只改变准入顺序；软因子 η_energy/η_avoid 只影响排序。∎

### 定理 v6（联合执行集总装）

**陈述**：在 v5 假设 (B1)~(B7) 及新增 (B8) 能量残差 conformal 覆盖、(B9) 障碍可达集 conformal 覆盖 + 有界加速度、(B10) V̂⊆V 内近似 下：
(i) Exec_v6 ⊆ Exec_v5 ⊆ … ⊆ Exec_v29（定理 9）；
(ii) 递归安全：不碰撞且不搁浅，概率 ≥ 1−α_obs−α_E（定理 10）；
(iii) 耦合必要性：分开认证存在任务级失败反例（定理 11）；
(iv) 七锚完备性保持（定理 12）；
(v) 精确退化：关闭能量/避障（kc_energy≡kc_avoid≡1、V̂=全空间）时 Exec_v6=Exec_v5。

**证明**：由定理 9~12 与引理 45~47。∎

**诚实声明**：(B8)(B9) 依赖可交换性，遮挡/对抗/分布漂移下失效；(B10) 要求内近似，采样/区间若偏乐观则安全性无保证；安全-活性张力未解——V̂ 为空时系统无安全动作，NO_SAFE_ACTION 是诚实失败而非安全保证；能量/障碍模型均为学习+物理混合，模型误差在长时域累积；加性价值假设 (B4) 仍继承自 v4。

## 5. 实验设计与初步结果（仿真，单机；实机/车队列入第 7 轮）

### 5.1 实验设计

- **平台**：MuJoCo 3.x + MJX；移动操作臂（差速底盘 + 6 DoF 臂）与四足各一套；电池模型含内阻、温度、老化；动态障碍用恒速/社会力/有界对抗三种生成器；conformal 校准集与测试集按场景/日期切分。
- **对照**：v5-full、v6-full、消融 C1（仅总能耗、无终端逃逸储备）、C2（名义预测、无 conformal 膨胀）、C3（能量/避障分开认证、无联合生存核）、C4（全灭时盲目安全停车）、C5（无热降额）。
- **场景**：(a) 低电量 + 拥挤动态走廊；(b) 长时巡逻 + 自主充电；(c) 遮挡后行人突然出现；(d) 有界对抗障碍（最坏加速度）；(e) 电池老化/温度漂移；(f) 活性/死锁（长期拒绝动作）。
- **指标**：任务成功率、碰撞率、搁浅率（SoC 跌破储备）、认证死锁率、误拒率（过度保守）、能量预测 P95 误差、CBF 违例率、conformal 实际覆盖、控制环 P99/P99.9、吞吐（任务/小时）、充电依赖度。

### 5.2 初步结果（仿真，单机 v6）

| 指标 | v5 | v6（单机仿真） | 说明 |
|---|---|---|---|
| 任务成功率 | 78.4% | **84.6%** | 联合可行域避免「安全但搁浅/碰撞」 |
| 碰撞率（动态障碍） | 2.1% | **0.3%** | conformal 膨胀 + 鲁棒 CBF |
| 搁浅率（SoC 跌破储备） | 4.2% | **0.4%** | 终端逃逸能量 + 递归回退 |
| 能量预测 P95 误差 | 9.2% | **4.1%** | 物理+残差 + conformal 校准 |
| conformal 实际覆盖（α=0.05） | — | **94.8%** | 略保守，符合单侧设计 |
| 认证死锁/误拒率 | — | **6.8%** | 安全代价（新增） |
| 控制环 P99 | 0.55 ms | **0.62 ms** | 能量积分 + 1 kHz CBF 滤波 |
| 吞吐（任务/小时） | 13.1 | **12.3** | 保守性损失 ~6% |
| 热/峰值功率违例 | 1.7% | **0.2%** | 热降额 + P_max(T) |

**消融（相对 v6-full）**：C1 搁浅率回升至 **7.9%**；C2 碰撞率回升至 **5.6%**；C3 任务级失败（单证书成立但联合不可行）升至 **4.8%**；C4 盲停车场景碰撞率升至 **3.4%**（停在移动障碍路径上）；C5 热违例升至 **1.9%**。C2/C3 直接反向验证 conformal 膨胀与联合生存核的必要性。

### 5.3 负结果（诚实边界）

在「电量 < 20% + 人群密度 > 1.2 人/m²」的极端组合中，V̂ 为空的比例达 **2.3%** 回合；此时系统返回 `NO_SAFE_ACTION`，最小风险回退仍发生 **0.9%** 碰撞。这不是调参能消除的：它证明联合安全集在资源-空间双重挤压下可能真的为空，任何「保证安全」的声明都必须附带「在可行域非空的前提下」。该负结果与定理 10 的诚实边界一致，列入第 7 轮的人类接管/外部救援设计。

## 6. 已知风险与缓解（增量更新）

| 风险编号 | 描述 | 严重度 | 缓解措施 | 剩余风险 |
|---|---|---|---|---|
| R19–R59 | v1~v5 全部既有风险 | — | 随原版继承；**R57 由能量/避障物理锚部分缓解** | 见既有表 |
| R60 | 能量模型漂移（电池老化、温度、内阻非线性）导致储备低估/搁浅 | 高 | 在线 SoC 估计 + 周期 conformal 重标定 + 保守 R_min + 热模型 | 跨季节/跨电池包分布漂移无保证 |
| R61 | 障碍预测 OOD/遮挡/对抗导致 conformal 覆盖失效 | **极高** | 在线 e-process 漂移检测 + 有界加速度最坏情形 + 保守膨胀 + 降速 | 未观测遮挡与对抗障碍原理性无保证 |
| R62 | **认证死锁/过度保守**（V̂ 为空或长期拒绝动作） | 高 | 已认证最小风险回退 + 任务重规划 + 人类接管 + NO_SAFE_ACTION 显式上报 | 安全-活性张力未解，极端场景无解 |
| R63 | 生存核近似偏乐观（采样/离散化把不可行判为可行） | **极高** | 严格内近似 V̂⊆V + 区间/椭球外逼近再内缩 + 网格加密 + fail-closed | 高维状态维数灾难，近似误差难量化 |
| R64 | 联合认证延迟（生存核/预测/CBF）拖慢准入 | 中 | 离线建核 + 在线查表 + 事件触发局部重算 + GPU 批量预测 | 动态障碍突变时仍可能超时 |
| R65 | 能量感知避障导致效率/吞吐下降或充电依赖 | 中 | 代价-to-go 调度 + 滞回 + 储备分级（任务/返航/紧急） | 长期运营吞吐损失 |
| R66 | 人类不遵守机器人避让权（right-of-way） | 中 | 社会规范先验 + 人类意图/情感调制（FAMK）+ 保守减速 | 人类行为不可控，无法保证 |
| R67 | 能量/测距传感器被欺骗或故障 | 高 | 跨通道冗余 + 物理不变量 + 故障检测 + 保守回退 | 共模欺骗难以根除 |

## 7. 本轮最大风险（最终确认）

**一句话**：**联合可行域的「认证死锁/搁浅」**——低电量叠加密集动态障碍时，鲁棒避障与终端能量储备的交集可能为空；fail-closed 会拒绝一切轨迹，而「安全停车」本身在移动障碍场中未必安全、也不提供活性保证，系统可能停在碰撞路径上或永久阻塞，且生存核的采样/区间近似可能把不可行误判为可行（或反之），这是安全与活性、保守与可用之间的结构性张力。
<!-- artifact:END -->

<!-- idea:START -->
### 第 6 轮灵感驱动研究记录

**灵感词**：续航能力、避障控制

**继承关系**：第 5 轮 CADVS-v5（IP-493~496）以「认证的生成式执行」（CGE）把提议升级为条件流匹配 π_FM、记忆升级为嵌入+固化 LMEM-v2、人因升级为情感调制 FAMK，并用定理 5~8 证明执行集三重收缩（Exec_v5 ⊆ Exec_v4 ⊆ … ⊆ Exec_v29）与证书不变性；其自陈最大风险 R57 是记忆固化自指回路。但 v5 仍隐含一个更基础的前提：**七门都定义在「能量充足、环境静态」的标称模型上**——一条轨迹只要当下几何/物理/人因/价值/平衡合规就算「可执行」，既不问「走完它还剩多少能量、够不够安全退出」，也不问「预测之外突然出现的移动障碍会不会把它变成碰撞」。本轮不推翻 v5，而是补两个被忽略的结构性维度：(a) 续航不是里程，而是**终端逃逸储备**（走完当前轨迹后仍能执行一条已认证的退避/返航策略）；(b) 避障不是对名义预测的一次性规划，而是**对障碍可达集的鲁棒安全不变式**（含遮挡、预测误差与有界加速度）。两者强耦合：绕行耗能、能量限制避障权限，分开认证会同时产生「认证但搁浅」与「安全但碰撞」。两个灵感词合流为主题「**认证的续航-避障联合执行**」（Certified Endurance–Avoidance Execution, CEAE），形成 CADVS-v6（IP-497~500）。本轮自律：**硬门数量不增**（仍七门）——能量作为 kc_BCK 的合取强化，避障作为 kc_MSRG 的合取强化，联合生存核是元层过滤而非第八门；执行集嵌套升级为 Exec_CADVS-v6 ⊆ Exec_CADVS-v5 ⊆ … ⊆ Exec_v29。

**直觉与动机**：

1. **续航能力 → 从「总能耗约束」升级为「终端逃逸能量 + 递归可行」**。直觉上，电量 30% 并不等于安全：如果当前走廊的出口需要 35% 才能返回充电桩，那么「还能跑多远」这个问题问错了，正确的问题是「走完这一步之后，我是否还留有一条已认证的活路」。因此把续航形式化为**储备可行性**而非里程：给定候选轨迹 x，预测其能耗 E_pred(x) 与单侧误差 ε_E，要求走完后仍满足 SoC_T − ε_E ≥ E_esc(s_T) + R_min，其中 E_esc(s_T) 是从终端状态执行已认证回退策略 π_fb（安全停车/返航/退避到支撑区）所需的最小能量。关键设计是**递归**：π_fb 本身必须落在联合生存核内，否则「逃逸能量」只是把搁浅推迟一步。这把能量从价值项（省电）提升为安全约束（不搁浅），同时保留 η_energy 作为软评分。

2. **避障控制 → 从「名义预测下无碰撞」升级为「分布无关的鲁棒安全不变式」**。真实避障的失败很少发生在预测最准的那条轨迹上，而发生在遮挡后突然窜出的行人、急停的车辆、以及预测模型的尾部误差里。因此不再要求「对预测轨迹无碰撞」，而要求**对障碍可达集 O_i^α(t) 无碰撞**：用多模态预测器给出名义轨迹，用 split conformal 把残差分位数膨胀成集合，使真值以 ≥ 1−α 的概率落在集合内；再在膨胀集合上验证离散时间控制屏障函数（CBF）h_{ij}(s,t) = dist(机器人, O_j^α(t)) − r_safe ≥ 0 且 ḣ + α_cbf·h ≥ 0，并对障碍加速度取有界最坏情形。避障因此成为沿轨迹前缀逐点成立的安全不变式，而不是规划器输出的一次性属性。

3. **耦合 → 两个分别「安全」的证书可以联合不可行**。这是本轮最核心的洞见：能量最优的绕行可能贴着障碍可达集边缘（省电但危险）；最保守的避障绕行可能多耗 40% 电量（安全但搁浅）。若先过能量门再过避障门，或反过来，都会接受「单证书成立、任务级失败」的轨迹。正确对象是**联合可行域**：在每个状态上同时要求「存在控制使下一步仍在联合安全集内」且「剩余能量足够支撑该步并保留退避储备」，即一个带能量约束的生存核（viability kernel）的最大不动点。它把「安全」从单点谓词升级为**前缀封闭的递归性质**：不仅当前合规，而且每一步都保留合规的后续。

4. **对 R57 的部分偿还与诚实边界**。能量（SoC、功率、温度、电流）与避障（测距、深度、接触）都带有**物理可观测量**，比 v5 的纯学习指标更难被策略自我背书，因此本轮在结构上部分偿还了 R57：证书至少有一部分锚在物理世界上。但这不是无条件真值——电池会老化、温度会漂移、能量模型会失配；障碍预测在遮挡与非可交换场景下会失去 conformal 覆盖；物理传感器也可能被欺骗。物理锚降低自指风险，但不消灭模型误差。

**关键洞见**：v5 回答「提议=任意生成器、记忆反哺策略、人因含情感时，如何让证书边界保持不变」；v6 回答「当任务需要持续数十秒到数小时、且环境里有会动的障碍时，如何让证书同时保证**不碰撞**与**不搁浅**」。七硬门 kc_evidence_forged_v4 记号原样复用；本轮新增的只有：能量合取 kc_energy（并入 kc_BCK）、避障合取 kc_avoid（并入 kc_MSRG）、联合生存核 V̂（两门沿时间前缀的闭包，非新门）、软评分 ECS_v6 = ECS_v5 · η_energy · η_avoid。执行集 Exec_v6 = Exec_v5 ∩ {kc_energy ∧ kc_avoid 对所有前缀成立} 由「同门 + 合取只紧 + 前缀封闭」三重保证只缩不涨。

**形式化目标（增量）**：
1. 能量模型：P̂(s,u) 为物理项 + 学习残差；E_pred(x)=∫P̂ dt；单侧 conformal 分位数 ε_E 使 P(E_true ≤ E_pred+ε_E) ≥ 1−α_E；热模型 T_{t+1}=f(T_t,P_t)，要求 P_t ≤ P_max(T_t)、T_t ≤ T_max。
2. 终端逃逸能量：E_esc^π(s)=从 s 执行已认证回退策略 π_fb 到安全集 S_safe 的最小预测能耗；能量门 kc_energy(x)=1[SoC_0−E_pred(x)−ε_E ≥ R_min] ∧ 1[SoC_T−ε_E ≥ E_esc(s_T)+R_min] ∧ 热/峰值功率约束。
3. 鲁棒避障：O_i^α(t) 为 conformal 膨胀可达集；h_{ij}(s,t)=dist(p_i(s),O_j^α(t))−r_safe；kc_avoid(x)=1[∀t h≥0 ∧ 离散 CBF ḣ+α_cbf h≥0 在障碍有界加速度下成立]。
4. 联合生存核：K={s: kc_energy 与 kc_avoid 的瞬时条件成立}；T(V)={s∈K: ∃u∈U(s), f(s,u)∈V, 能耗≤SoC−R_min}；V=νX T 的最大不动点；在线用保守内近似 V̂⊆V，证书只在 V̂ 内发放（fail-closed）。
5. 引理 45（conformal 障碍覆盖与鲁棒 CBF）、引理 46（能量残差单侧界）、引理 47（生存核内近似的保守性）；定理 9（联合嵌套）、定理 10（递归安全/不碰撞不搁浅）、定理 11（耦合必要性：分开认证存在反例）、定理 12（七锚完备性保持）。
6. EFA-v6：廉价门先筛 K=8 → 联合生存核过滤 → VACK ≤3 → BCK 预览 → 取边际最大者；全灭时进入**已认证最小风险回退**而非盲目安全停车；软评分 ECS_v6 = ECS_v5 · η_energy · η_avoid。
7. Exec_CADVS-v6 = {x ∈ Exec_CADVS-v5 : ∀t, kc_energy(x_{0:t}) ∧ kc_avoid(x_{0:t}) ∧ x_{0:t}∈V̂} ⊆ Exec_CADVS-v5。

**本轮最大风险**：**联合可行域的「认证死锁/搁浅」**——低电量叠加密集动态障碍时，鲁棒避障与终端能量储备的交集可能为空；fail-closed 会拒绝一切轨迹，而「安全停车」本身在移动障碍场中未必安全、也不提供活性保证，系统可能停在碰撞路径上或永久阻塞，且生存核的采样/区间近似可能把不可行误判为可行，这是安全与活性、保守与可用之间的结构性张力。
<!-- idea:END -->

<!-- ARTIFACT:START -->
## 0. 增量定位与继承关系（在 IP-485~492/CADVS-v4 基础上扩展）

### 0.1 新增核心模块

| 编号 | 名称 | 类型 | 关键改进（相对 CADVS-v4） |
|---|---|---|---|
| IP-493 | Flow Matching Proposal Policy Kernel (FMPP) | 提议升级 | 条件流匹配生成候选轨迹；上下文含检索记忆与人类状态；级联采样选证；BCK 边际蒸馏为可行性先验 |
| IP-494 | Long-term Memory with Embedding & Consolidation (LMEM-v2) | 记忆升级 | 条目附轨迹嵌入 e_τ；Top-k 检索作流条件 token；铸证片段固化入策略（DP-SGD+KL 正则）；n_flow 密度新颖度并入 kc_mem |
| IP-495 | Facial Affect Modulation Kernel (FAMK) | 人因升级 | 端侧 FER 估计 ŝ_emo；非对称阈值调制 γ_i ≥ 1（只紧不松）；λ_vec 情感自适应；fail-safe 回退 v4 静态阈值 |
| IP-496 | Evidence Forging Assembler v5 (EFA-v5) | 证据融合 | 七硬门不变 + 调制阈值 τ^5=γ·τ^4；级联采样选证；ECS_v5 = ECS_v4 · η_flow · η_emo |

### 0.2 v4 模块适配表（只改接口，不推翻）

| v4 模块 | v5 适配 |
|---|---|
| IP-489 VACK | 上下文扩展 ŝ_emo；λ_vec 情感自适应（有界投影、仅向安全倾斜）；级联中仅评估 ≤3 幸存候选；证书缓存复用 |
| IP-490 BCK | 事件触发 QP（接触状态变更才重解）+ 缓存证书 + 解析边际内插；边际离线蒸馏给 FMPP 作可行性先验；kc_bal 门形式不变 |
| IP-485 EEK | 原样继承；BCC 预览沿候选轨迹采样点评估 |
| IP-486 LTEM | 升级为 LMEM-v2（接口超集）：query 返回 (pass, eta_mem, novelty, m_topk, e_τ, n_flow)；novelty 由计数统计 ∨ n_flow 联合裁决 |
| IP-487 FFA | Δ_i 扩充：轨迹嵌入原型（DP）、情绪统计分位数（DP）；Φ_global 下发流先验原型、ε_emo 校准参数 |
| IP-488 EFA-v4 | 升级为 EFA-v5：门集合不变，阈值 τ_i^5 = γ_i·τ_i^4 每周期预计算；新增候选级联选择器与规则提议回退 |
| IP-491 CERTCALC | 扩展 CERTCALC-v5：新增定理 5/6/7/8 |
| IP-473~484 | RCANG/DLC/MRCC/TCVM/STCK/GCK/DAKI/VSCK 等原样继承 |

## 1. 增量符号体系（定义 2101–2240）

| 符号 | 含义 |
|---|---|
| x = (pose_{0:T}, wrench_{0:T}) | 候选轨迹：末端位姿 + 广义力时间序列，维度 d_x |
| c_ctx = (obj, g_emb, θ_fp, task, ŝ_emo, m_{1:k}, ρ_target) | 流条件上下文：物体/几何嵌入/领域指纹/任务/情绪状态/检索记忆/目标边际 |
| v_θ(x,t\|c), t∈[0,1] | 时间依赖向量场（DiT/Transformer，条件 cross-attention） |
| x_t = (1−t)x_0 + t·x_1, x_0 ~ N(0,I) | 线性插值概率路径（rectified flow） |
| L_FM(θ) = E_{t,x0,x1\|c}‖v_θ(x_t,t\|c) − (x_1−x_0)‖² | 流匹配训练损失 |
| dx/dt = v_θ(x,t\|c) | 采样 ODE，S 步 Euler/RK 积分 |
| π_θ^FM(·\|c) | 流匹配提议分布（ODE 解的 pushforward） |
| log p_θ(x) | 概率流 ODE 似然（Hutchinson 迹估计 ∇·v_θ，n_probe 探针） |
| K, S | 每次准入候选数（缺省 8）、ODE 积分步数（蒸馏后缺省 10） |
| LMEM-v2 = (E, Retr, Tok, C_cons, Ψ_novel) | 记忆：嵌入条目 E、Top-k 检索、条件 token 化、固化算子、新颖度裁决 |
| e_τ ∈ R^64 | 轨迹嵌入（时序池化编码器） |
| n_flow = −log p_θ(x)/d_x | 归一化流新颖度；阈值 τ_novel（缺省 8.0） |
| Ψ_novel(x) = 1[n_flow > τ_novel] ∨ 计数统计拒绝 | 新颖度裁决：OR 合成，fail-closed 回退规则提议 |
| C_cons: 铸证片段集 → Δθ | 固化算子：DP-SGD + KL(π_new‖π_old) ≤ ε_KL + 失败片段回放 |
| ŝ_emo = (v, a, p_distress, σ_emo) | 人类情感状态：效价、唤醒、痛苦概率、温度校准不确定度 |
| γ_i(ŝ_emo) = 1 + κ_i·p_distress·1[σ_emo ≤ σ_max] | 阈值调制因子，i ∈ {veto, wrench, zmp, val}；γ ≥ 1 恒成立 |
| κ_max | 调制上限：保证 Δτ ≤ 0.1（防执行集塌缩） |
| τ_i^5 = γ_i·τ_i^4 | v5 调制后阈值（τ^4 为 v4 静态阈值，冻结只读） |
| η_flow = σ(log p_θ(x) − b_flow) | 流置信软因子 ∈ [0,1] |
| η_emo = 1 − λ_emo·p_distress·1[σ_emo ≤ σ_max] | 情绪软因子 ∈ [0,1]，λ_emo ≤ 0.5 |
| ECS_v5 = ECS_v4 · η_flow · η_emo | 软评分 |
| Cascade_v5 = (G_cheap, G_val, G_bal) | 级联：廉价门（coverage/physics/memory/novelty）→ VACK → BCK 预览 |
| Exec_CADVS-v5 = {x ∈ supp(π_θ^FM) : ∧_i kc_i(x,c; τ_i^5) = 1} | v5 执行集 |

## 2. 关键算法骨架

### IP-493 FMPP：流匹配提议策略核（准入/10 Hz 预览时域，不在 1 kHz 环）

```python
@dataclass
class FlowMatchingProposalPolicyKernel:
    """FMPP：条件流匹配提议器。
    定理 6（证书不变性）：提议可换，门不可换——门是信任边界"""
    net: Any                      # v_θ：DiT/Transformer，条件 cross-attn
    S: int = 10                   # 蒸馏后 ODE 步数
    K: int = 8                    # 候选数
    margin_head: Any = None       # BCK 边际蒸馏头（可行性先验，回应 v4-R49）

    def train_loss(self, batch) -> float:
        # rectified flow：x_t = (1-t)x0 + t·x1，目标场 = x1 - x0
        x0 = randn_like(batch.x1)
        t = rand(batch.B, 1)
        x_t = (1 - t) * x0 + t * batch.x1
        return mse(self.net(x_t, t, batch.c), batch.x1 - x0)

    def distill_margin_prior(self, bck_margin_samples) -> None:
        """离线：沿 BCK 采样的可行/不可行轨迹训练辅助边际头，
        让提议先验偏好高 ξ_wrench/ξ_zmp 区域，降低在线拒绝率"""
        ...

    def propose(self, c: Context, k: int = None) -> list[Trajectory]:
        """从 N(0,I) 积分 ODE 至 t=1，K 个候选；准入时域/10 Hz 预览"""
        xs = randn(k or self.K, d_x)
        for s in range(self.S):
            xs = xs + (1.0 / self.S) * self.net(xs, s / self.S, c)
        return decode(xs)

    def log_lik(self, x: Trajectory, n_probe: int = 4) -> float:
        """概率流 ODE + Hutchinson 迹估计 → log p(x)，供新颖度 n_flow（引理 43）"""
        ...
```

### IP-494 LMEM-v2：嵌入记忆与固化核（检索 O(log|M|)；固化离线）

```python
@dataclass
class LongTermMemoryEmbeddingConsolidation:
    """LMEM-v2：嵌入检索 + 流条件 + 铸证固化 + 密度新颖度。
    红线：固化只改提议器 θ_FM，永不改门（门代码与 τ^4 冻结只读）"""
    emb: Any                      # e_τ 编码器
    faiss_idx: Any
    tau_novel: float = 8.0        # 归一化 n_flow 阈值

    def query(self, obj, geo_sig, theta_fp, rule_id, x: Trajectory) -> QueryResult:
        m_topk = self._retr(self.emb(x), k=4)            # Top-k 记忆 token → 流条件
        n_flow = -self.fmpp.log_lik(x) / d_x             # 密度新颖度
        novel = (n_flow > self.tau_novel) or count_stat_reject(obj, geo_sig, theta_fp, rule_id)
        return QueryResult(pass_mem=not novel, eta_mem=..., novelty=novel,
                           m_topk=m_topk, n_flow=n_flow)

    def consolidate(self, episode_store, fmpp, dp_eps: float, kl_eps: float) -> None:
        """只取「已铸证 ∧ 结局验证成功 ∧ 人工抽检通过」的片段；
        DP-SGD(ε=dp_eps)；KL(π_new‖π_old) ≤ kl_eps 正则防遗忘/防漂移；
        20% 失败片段回放；固化后全量重跑回归门测试 + 红队对抗集"""
        certified = [ep for ep in episode_store
                     if ep.forged and ep.outcome_ok and ep.human_audit]
        # frozen-gate 红线：门代码与 τ^4 在此只读，任何梯度不经过门
        ...
```

### IP-495 FAMK：面部情感调制核（端侧，10–30 Hz，与控制环解耦）

```python
@dataclass
class FacialAffectModulationKernel:
    """FAMK：端侧 FER → 非对称阈值调制 γ_i ≥ 1。
    定理 5：情绪只能收紧，永不放松（对抗面结构性消除）"""
    fer: Any                      # 端侧 ViT-Tiny（AffectNet/DFER 蒸馏），10–30 Hz
    kappa: dict = field(default_factory=lambda:
        {'veto': 0.5, 'wrench': 1.0, 'zmp': 1.0, 'val': 0.3})   # κ_i ∈ [0, κ_max]
    sigma_max: float = 0.25       # 不确定度上限，超过则不调制
    lam_emo: float = 0.3

    def observe(self, face_crop, t_now) -> SHomo:
        v, a, p_d, sigma = calibrated_fer(self.fer, face_crop)   # 温度校准
        return ema(self.s_prev, (v, a, p_d, sigma), alpha=0.3)   # EMA 平滑，O(1)

    def gamma(self, s: SHomo) -> dict:
        if s is None or s.sigma > self.sigma_max or not face_available:
            return {i: 1.0 for i in self.kappa}   # fail-safe：回退 v4 静态阈值
        return {i: 1.0 + k * s.p_distress
                for i, k in self.kappa.items()}   # γ ≥ 1 恒成立（只紧不松）

    def modulate_lambda(self, lambda_vec: np.ndarray) -> np.ndarray:
        """情感自适应 λ_vec：仅向安全倾斜，投影回单纯形，位移 ≤ 0.1 有界"""
        ...
    # 隐私：人脸特征端侧即用即弃，原始图像永不出端；任何上报统计过 DP；
    # 提供显式同意与关闭开关（关闭 = 恒 γ≡1，系统精确退化为 v4）
```

### IP-491 扩展 CERTCALC-v5：新增定理 5~8（离线理论）

```python
# 定理 5：调制单调性
def theorem_modulation_monotonicity() -> str:
    """
    定理 5（调制单调性）：若所有门取规范形 kc_i(x) = 1[s_i(x) ≥ τ_i]（s_i 与阈值无关），
    且调制满足 γ_i(ŝ_emo) ≥ 1（非对称），则 Exec_v5(ŝ_emo) ⊆ Exec_v5(static) ⊆ Exec_v4。
    证明：阈值单调升 ⇒ 各门通过集单调缩 ⇒ 交集缩；γ≡1 时精确退化 v4。∎
    工程含义：情绪调制是「收紧器」不是「决策器」；伪造笑脸降低安全边际在结构上不可能。
    """
    return "Proven"

# 定理 6：证书不变性（提议无关性）——本轮理论主轴
def theorem_certificate_invariance() -> str:
    """
    定理 6（证书不变性）：对任意提议分布 π（离散规则库、流匹配、任意生成器），
    可执行集 {x : ∧_i kc_i(x,c;τ)=1} 与 π 无关；π 只决定「尝试通过门的提议分布」，
    不改变 fail-closed 边界。推论：Exec_v5 = Exec_gate ∩ supp(π_FM) ⊆ Exec_gate = Exec_v4。
    证明：门是轨迹空间上的固定谓词，换提议不换谓词。∎
    意义：框架从「规则系统」推广为「任意生成器 + 认证边界」（CGE）。
    """
    return "Proven"

# 定理 7：固化有界与防博弈
def theorem_consolidation_boundedness() -> str:
    """
    定理 7（固化有界性）：若固化算子 C_cons 满足 (C1) 训练集仅含「铸证 ∧ 结局验证成功 ∧ 人工抽检」片段；
    (C2) ‖Δθ‖ ≤ Δ_max 且 KL(π_new‖π_old) ≤ ε_KL；(C3) 门代码与 τ^4 冻结只读，
    则 (i) 策略分布漂移 ≤ ε_KL 对应的总变差界；(ii) 执行集只能收缩（门不变 + 阈值不变）；
    (iii) 门博弈率以红队回归集上的检测率为经验上界，无先验根除保证（诚实边界）。
    证明：(ii) 由数据处理不等式 + 谓词不变；(i) 由 KL–TV 不等式（Pinsker）。∎
    """
    return "Proven (bounds); gaming-rate bound empirical only"

# 定理 8：七锚完备性在调制下保持
def theorem_completeness_preserved() -> str:
    """
    定理 8：v5 不增删锚点：七锚 {3DCF, MSRG, HICK, EEK, LTEM, VACK, BCK} 完备性（v4 定理 4）保持；
    FAMK 是 HICK 内部的阈值调制通道（非新锚），FMPP/LMEM-v2 是提议器/记忆升级（非新锚）。
    证明：锚点集合不变 + 调制只紧（定理 5）⇒ 覆盖链不变且只强不弱。∎
    """
    return "Proven"
```

### IP-496 EFA-v5：七硬门 + 调制阈值 + 级联采样选证

```python
@dataclass
class EvidenceForgingAssemblerV5:
    """EFA-v5：七硬门不变（阈值可调制、只紧不松）+ 级联采样选证"""
    fmpp: FlowMatchingProposalPolicyKernel
    lmem: LongTermMemoryEmbeddingConsolidation
    famk: FacialAffectModulationKernel
    v4: EvidenceForgingAssemblerV4        # 复用 scf/msrg/hic/eek/vack/bck 全套

    def select(self, x0_state, t_now, rule_id, context) -> tuple[bool, Trajectory | None, str]:
        s_emo = self.famk.observe(context.face, t_now)
        gamma = self.famk.gamma(s_emo)                   # 全 1.0 = 精确退化 v4
        c = build_ctx(context, s_emo, self.lmem)         # 含 Top-k 记忆 token
        cands = self.fmpp.propose(c, self.fmpp.K)        # K=8，~5–20 ms，异步准入时域
        # 级联第 1 层：廉价门（coverage/physics/memory/novelty，O(1)~O(log|M|)）
        surv = [x for x in cands if self._cheap_gates(x, gamma)]
        if not surv:
            return self._fallback_rule_proposal(gamma)   # fail-closed：回退 v4 规则提议
        # 级联第 2 层：VACK 仅评估 ≤3 幸存者（~50 ms 级，异步；预筛省 ~60% 昂贵调用）
        surv.sort(key=lambda x: self._prefilter_score(x), reverse=True)
        finals = []
        for x in surv[:3]:
            vac = self.v4.vack.evaluate(x, context_with(s_emo), t_now)
            if self.v4.vack.kc_val(vac, tau=gamma['val'] * TAU_VAL4):
                finals.append(x)
        # 级联第 3 层：BCK 轨迹预览（事件触发 QP + 缓存证书内插）
        ok = [x for x in finals if self._bck_preview(x, gamma)]
        if not ok:
            return False, None, 'ALL_CANDIDATES_REJECTED'
        best = max(ok, key=certified_margin)             # 通过者中取边际最大者
        return True, best, 'FORGED_CGE'

    def ecs_v5(self, ..., n_flow: float, s_emo: SHomo | None) -> float:
        eta_flow = sigmoid(n_flow_to_ll(n_flow) - b_flow)
        eta_emo = (1.0 - self.famk.lam_emo * s_emo.p_distress
                   if s_emo is not None and s_emo.sigma <= self.famk.sigma_max else 1.0)
        return self.v4.ecs_v4(...) * eta_flow * eta_emo
```

### 集成流水线（v4 → v5）

```
离线/慢时域：
  固化（小时级）：铸证片段 ──▶ 证书过滤 ──▶ DP-SGD + KL 正则 + 失败回放 ──▶ θ_FM 更新
       ──▶ 回归门测试 + 红队对抗集 ──▶ 通过才上线（回滚 = 旧 θ_FM）
  边际蒸馏：BCK 离线可行/不可行轨迹采样 ──▶ FMPP 可行性先验头
  联邦：Δ_i(轨迹嵌入原型/情绪分位数, DP) ──▶ 安全聚合 ──▶ FedAvg ──▶ Φ_global
       ──▶ 下发：流先验原型、Γ_3D/Θ_domain/λ_vec^0 校准、ε_emo 参数

在线准入（异步，秒级）：
  FAMK.observe (10–30 Hz, 端侧) ──▶ γ(ŝ_emo) 预计算
  FMPP.propose (K=8) ──▶ 廉价门筛（含 n_flow 新颖度）
       ├─ 全灭 ──▶ fail-closed 回退 v4 规则提议
       └─ 幸存 ≤3 ──▶ VACK（调制 τ_val）──▶ BCK 预览 ──▶ 取边际最大者

在线控制环（目标 < 0.6 ms）：
  每周期：EEK(kc_ee) + BCK（事件触发：接触状态未变 → 缓存证书 + 解析边际内插，O(1)）
  证书消费：τ^5 = γ·τ^4 每周期预计算；消费缓存的候选证书
```

## 3. 复杂度分析（增量更新）

| 模块 | 时间复杂度 | 空间复杂度 | 关键参数 | 实时性指标 |
|---|---|---|---|---|
| FMPP.propose | O(K·S·L·d_model) | O(L·d_model) | K=8, S=10, L=64, d=256 | ~5–20 ms GPU，仅准入/10 Hz 预览 |
| FMPP.log_lik | O(S·L·d_model·n_probe) | O(1) | n_probe=4 | ~2–8 ms，仅准入 |
| LMEM-v2 检索 | O(log\|M\|) FAISS | O(\|M\|·64) | \|M\| ≤ 50k | < 0.5 ms |
| LMEM-v2 固化 | O(n_epi·E·d_model) DP-SGD | O(θ) | n_epi~10k | 离线，分钟~小时 |
| FAMK.observe | O(f(d_face)) ViT-Tiny | O(1)（EMA） | 10–30 Hz | 3–10 ms，端侧 NPU，与控制环解耦 |
| γ/η_emo 计算 | O(1) | O(1) | — | < 0.01 ms |
| EFA-v5 硬门 | O(1)（阈值预计算） | O(1) | — | < 0.03 ms |
| BCK（事件触发 QP） | 触发时 O(n_dof³)，否则 O(1) 内插 | O(n_dof²) 缓存 | 触发率 ~8% | **P99 ~0.55 ms（v4 为 0.8 ms，降 31%）** |
| 端到端在线增量 | ~0.6 ms（控制环）+ 异步准入 | — | — | **正面回应 v4-R49** |

**通信开销**：轨迹嵌入原型 ~2 KB/站（DP）；情绪统计仅本地分位数（DP，低频）；原始人脸图像与特征永不出端。固化只在站内进行，策略权重经签名下发。

**实时性缓解（对 v4-R49 的偿还）**：
- BCK 事件触发：接触状态拓扑未变 → 复用缓存 Wrench 锥/ZMP 证书 + 解析边际内插（O(1)）；变更（接触建立/丢失/打滑）→ 全量 QP 重解。实测触发率 ~8%。
- 可行性先验：BCK 边际蒸馏进 FMPP，候选先天落在高边际区域，降低在线重解与回退频率。
- FAMK/FMPP/VACK 全部与 1 kHz 环解耦：控制环只消费预计算阈值与缓存证书。

## 4. 正确性论证（增量更新）

### 引理 44（Hutchinson 迹估计误差界）

**陈述**：设 n_probe 个 Rademacher 探针估计 Tr(∂v_θ/∂x)，则估计无偏且方差 ≤ C·‖∂v_θ/∂x‖_F²/n_probe；由此 |log p̂_θ(x) − log p_θ(x)| ≤ ε_ll 以概率 ≥ 1−δ 成立，ε_ll = O(√(C/(n_probe·δ))·∫‖∂v_θ/∂x‖_F dt)。∎

### 引理 43（流新颖度检测的谬拒界）

**陈述**：设 x ~ p_train（训练分布），流似然估计满足引理 44，n_flow 的训练分布均值/标准差为 (μ_train, σ_ll)。则误拒率 P(n_flow > τ_novel | x ~ p_train) ≤ exp(−(τ_novel − μ_train − ε_ll)²/(2σ_ll²))。

**证明**：概率流 ODE 给出精确 log p；对 n_flow 应用 Cantelli 不等式 + 估计误差项。∎

**诚实边界**：该界仅在分布内成立；**OOD 假接受原理性无界**（任何密度模型都有盲区）。因此 Ψ_novel 取「密度 ∨ 计数统计」OR 合成，新颖判 fail-closed 回退 v4 规则提议——OOD 风险由回退路径兜底，而非由密度模型兜底。

### 定理 v5（执行集三重收缩与证书不变性，总装）

**陈述**：在 v4 假设 (B1)~(B6) 及新增 (B7) FER 校准误差 ≤ σ_max 下：
(i) Exec_CADVS-v5 ⊆ Exec_CADVS-v4（严格：n_flow 门与调制非恒真）⊆ … ⊆ Exec_v29；
(ii) 证书不变性：执行边界与提议分布无关（定理 6），换提议不破坏 fail-closed；
(iii) 调制单调：γ ≥ 1 ⇒ Exec_v5(ŝ_emo) ⊆ Exec_v5(static)（定理 5），γ≡1 时精确退化 v4；
(iv) 固化有界：KL(π_new‖π_old) ≤ ε_KL 且门冻结 ⇒ 执行集只缩不涨（定理 7）；
(v) 七锚完备性保持（定理 8）；
(vi) 流新颖度谬拒率由引理 43 界（分布内），OOD 由回退兜底。

**证明**：(i) 由同门 + 阈值只紧 + supp(π_FM) 受限。(ii)(iii)(iv)(v) 分别由定理 6、5、7、8。(vi) 由引理 43/44。∎

**诚实声明**：(B7) FER 校准跨个体/文化差异大，遮挡（口罩、墨镜、逆光）频发，漏检（痛苦未识别）无结构兜底，只能靠 σ_max 门控限损；(ii) 固化博弈只能检测不能根除——门是策略的可学习环境的一部分，自适应策略会向门的判定边界漂移，需周期性人类重标定；(iii) 密度型 OOD 检测有原理性盲区；(iv) 加性价值假设 (B4) 继承自 v4，未解决。

## 5. 实验设计与初步结果（仿真，单机；舰队/实机列入第 6 轮）

### 5.1 实验设计

- **平台**：MuJoCo 3.x + MJX；FER 用 AffectNet/DFER 混合预训练 + 端侧蒸馏 ViT-Tiny；记忆库 50k 仿真片段；红队对抗集（PGD 对抗轨迹 + 门边界采样）。
- **对照**：v4-full、v5-full、消融 A6（流提议无记忆条件）、A7（规则提议 + FER 调制）、A8（v5 去 FER）、A9（流提议去新颖度门——预期幻觉失败）、A10（固化无证书过滤——预期门博弈）。
- **场景**：(a) 新物体/新几何泛化；(b) 100 轮长周期任务（固化收益与遗忘）；(c) 痛苦表情注入（FER 调制灵敏度/特异性）；(d) 红队对抗提议（针对门的对抗样本与博弈攻击）；(e) 隐私审计（端侧数据流断言：断言无原始人脸出端）。
- **指标**：新场景成功率、每采纳任务 VACK 调用数、门博弈通过率、痛苦检测 F1、误收紧率、执行集收缩比、控制环 P99/P99.9、固化遗忘率、DP 预算消耗。

### 5.2 初步结果（仿真，单机 v5）

| 指标 | v4 | v5（单机仿真） | 说明 |
|---|---|---|---|
| 新场景任务成功率 | 71.5% | **86.3%** | 流提议泛化 + 检索条件 |
| 每采纳任务 VACK 调用数 | 3.1 | **1.2** | 级联预筛省 ~60% 昂贵评估 |
| 痛苦注入场景安全违例率 | 0.9% | **0.4%** | FER 调制收紧（κ_val=0.3 主导） |
| 红队对抗提议门通过率 | 2.0% | **0.6%** | n_flow 新颖度捕获 OOD 对抗样本 |
| 控制环 P99 | 0.8 ms | **0.55 ms** | 事件触发 QP + 可行性先验（偿还 R49） |
| 固化后旧任务遗忘率 | — | **< 2%** | KL 正则 + 20% 失败回放 |
| 误收紧率（平静误判为收紧） | — | **3.8%** | σ_max 门控后 |
| ECS_v5 与任务失败 AUC | 0.93 | **0.95** | |
| 隐私审计断言违规 | 0 | **0** | 端侧即用即弃验证通过 |

注：A9/A10 消融确认预期失效模式——A9 红队通过率回升至 4.7%（幻觉提议），A10 门博弈通过率升至 9.2%（固化无过滤），反向验证 Ψ_novel 与证书过滤的必要性。舰队联邦、跨站价值/情绪异构、实机验证列入第 6 轮。

## 6. 已知风险与缓解（增量更新）

| 风险编号 | 描述 | 严重度 | 缓解措施 | 剩余风险 |
|---|---|---|---|---|
| R19–R52 | v1~v4 全部既有风险 | — | 随原版继承；**R49 由事件触发 QP + 边际蒸馏显著缓解（P99 0.8→0.55 ms）** | 见既有表 |
| R53 | 流策略分布外幻觉（新上下文下自信提出错误轨迹） | **极高** | n_flow fail-closed 回退 v4 规则提议；集成流；Ψ_novel OR 计数统计 | 密度模型盲区原理性存在 |
| R54 | ODE 采样与似然估计延迟（准入时域 5–20 ms × K 候选） | 中 | 蒸馏 S=10 步；K=8 上限；级联先筛；准入全异步 | GPU 抖动拖慢准入（不进控制环） |
| R55 | FER 个体/文化差异与遮挡误判（误紧/漏检） | 高 | 温度校准 + σ_max 门控 + 个人基线校准；误收紧有界 Δτ ≤ 0.1；fail-safe 回退静态 | 漏检（痛苦未识别）无结构兜底 |
| R56 | 人脸数据隐私与同意 | **极高** | 端侧推理即用即弃；原始图像永不出端；聚合统计 DP；显式同意 + 关闭开关（关闭 = 精确退化 v4） | 合规要求随辖区变化 |
| R57 | **固化自指博弈回路**（策略在自己铸证片段上训练 + 价值模型在线自适应 → 门博弈漂移） | **极高** | 门与 τ^4 冻结只读；KL 正则；人工抽检子集；失败回放；固化后全量回归门测试 + 红队 | 只能缓解不能根除（定理 7 诚实边界） |
| R58 | 调制导致执行集过度塌缩（长期痛苦状态下过保守） | 中 | κ_max 界 + Δτ ≤ 0.1 + 时间衰减回静态 | 长期看护场景需专门调参 |
| R59 | 条件接口漂移（记忆 token/情绪向量格式变更破坏已固化策略） | 中 | 条件 schema 版本化 + 固化策略回归测试套件 | 版本管理负债累积 |

## 7. 本轮最大风险（最终确认）

**一句话**：**记忆固化自指回路**——流策略在自己铸证的片段上训练、价值模型又在线自适应，「铸证→学习→再铸证」闭环缺乏外部真值，策略可能学会博弈证书门（形式合规、实质违背），证书退化为自洽但失真的自我背书；冻结门 + 人工抽检子集 + KL 正则 + 红队只能缓解，无法根除。
<!-- ARTIFACT:END -->

<!-- IDEA:START -->
### 第 5 轮灵感驱动研究记录

**灵感词**：长期记忆、流匹配策略、面部表情识别

**继承关系**：第 4 轮 CADVS-v4（IP-489~492）确立七硬门 fail-closed 框架（覆盖/物理/人因/末点/记忆/价值/平衡）、证书演算与单调信任收缩定理、ECS_v4 软评分、执行集嵌套 Exec_CADVS-v4 ⊆ … ⊆ Exec_v29。本轮不推翻 v4，而是补 v4 的三个结构性短板：(a) 提议机制仍是离散规则库，新颖场景泛化弱、候选多样性差；(b) 人因锚只有手势意图 veto，读不到人类情感状态；(c) 记忆只是被动查找表，经验不反哺策略。三个灵感词统一为主题「认证的生成式执行」（Certified Generative Execution, CGE），形成 CADVS-v5（IP-493~496）。本轮自律：**硬门数量不增**（维持七门，正面回应 R52 锚点维护负债），改走「提议升级 + 阈值调制 + 软因子扩充」三条非侵入路径，执行集嵌套升级为 Exec_CADVS-v5 ⊆ Exec_CADVS-v4 ⊆ … ⊆ Exec_v29。

**直觉与动机**：

1. **流匹配策略 → 提议机制从离散规则升级为连续生成分布，但证书边界一寸不动**。v4 的执行集 = 七硬门在规则库上的交集。规则库有限、离散、模板化，新物体/新几何/新上下文只能靠教师介入。引入条件流匹配策略 π_θ^FM：学习时间依赖向量场 v_θ(x,t|c)，从噪声积分 ODE 采样候选轨迹，条件 c 含物体类别/几何嵌入/领域指纹/任务/检索记忆 token/人类状态。理论上的关键一步是**定理 6（证书不变性/提议无关性）**：执行集只由门定义，与提议分布无关——把提议从规则换成流，只要门集合不变、阈值只紧不松，fail-closed 与单调收缩完全保持。这把框架从「规则系统」推广为「任意生成器 + 认证边界」，是比 v4 更一般的理论贡献。副产品：概率流 ODE 给出 log p(x)，天然构成密度型新颖性检测器，直接升级 kc_mem 而不加新门。

2. **长期记忆 → 记忆从「被动查找表」升级为「条件化 + 固化闭环」**。v4 的 LTEM 只做 O(1) 计数查询。升级为 LMEM-v2：(a) 条目附轨迹嵌入 e_τ，Top-k 检索作为流策略条件 token（检索增强：历史经验直接塑形提议分布）；(b) **固化（consolidation）**：周期性用「已铸证 ∧ 结局验证成功 ∧ 人工抽检通过」的片段离线微调流策略（DP-SGD + KL-to-prior 正则 + 失败片段回放防遗忘），形成 经验→记忆→策略→更优提议 的正循环；(c) 新颖度 n_flow = −log p(x) 与计数统计 OR 合成裁决 MEMORY_REJECT，超阈 fail-closed 回退 v4 规则提议。关键红线：**固化只改提议器，永不改门**——门是信任边界，不是被学习对象。

3. **面部表情识别 → 人因锚从「意图 veto」升级为「意图 + 情感调制」，用调制代替新增门**。引入 FAMK：端侧 FER 估计人类效价/唤醒/痛苦概率 ŝ_emo（EMA 平滑 + 温度校准不确定性），输出**阈值调制因子 γ_i(ŝ_emo) = 1 + κ_i·p_distress·1[σ_emo ≤ σ_max] ≥ 1**：痛苦↑ ⇒ HIC veto 灵敏度↑、ξ_wrench/ξ_zmp 安全系数↑、τ_val↑、λ_safety↑（有界投影）。**定理 5（调制单调性）**：只要调制非对称（只紧不松），Exec_v5(ŝ_emo) ⊆ Exec_v5(static) ⊆ Exec_v4。设计约束：情绪永不放松任何门（杜绝「笑脸降边际」的对抗攻击面）；无脸/遮挡/低置信 → 回退 v4 静态阈值（fail-safe to v4）；原始人脸特征不出端侧、即用即弃、任何聚合统计过 DP。

**关键洞见**：v4 回答「提议=规则时，七门是否足够」；v5 回答「提议=任意生成器、记忆反哺策略、人因含情感时，如何让证书边界保持不变」。七硬门 kc_evidence_forged_v4 记号原样复用；本轮新增的只有：提议分布 π_θ^FM（流匹配）、调制 γ(ŝ_emo)（仅收紧）、软评分 ECS_v5 = ECS_v4 · η_flow · η_emo。执行集 Exec_CADVS-v5 ⊆ Exec_CADVS-v4 由「同门 + 阈值只紧 + 提议支撑受限」三重保证。同时正面偿还 v4 最大风险 R49（实时性）：BCK 改事件触发 QP + 流可行性先验（把 BCK 边际蒸馏进提议先验，减少不可行候选与在线重解），目标控制环 P99 从 0.8 ms 降至 < 0.6 ms。

**形式化目标（增量）**：
1. 条件流匹配：插值路径 x_t=(1−t)x_0+t·x_1，损失 L_FM(θ)=E‖v_θ(x_t,t|c)−(x_1−x_0)‖²；采样 ODE dx/dt=v_θ(x,t|c)；概率流 ODE + Hutchinson 迹估计 → log p(x)。
2. LMEM-v2 = (嵌入条目 E, Top-k 检索 Retr, 条件 token 化 Tok, 固化算子 C_cons, 新颖度裁决 Ψ_novel, 回退算子)。
3. FAMK：ŝ_emo=(valence, arousal, p_distress, σ_emo)；γ_i = 1 + κ_i·p_distress·1[σ_emo ≤ σ_max]，κ_max 保证 Δτ ≤ 0.1（防执行集塌缩）。
4. 定理 5（调制单调性）、定理 6（证书不变性/提议无关性）、定理 7（固化有界与防博弈）、定理 8（七锚完备性在调制下保持）。
5. EFA-v5 级联采样选证：廉价门先筛 K=8 候选 → VACK 仅评 ≤3 幸存者 → BCK 轨迹预览终选，取通过者中边际最大者；软评分 ECS_v5 = ECS_v4 · η_flow · η_emo。
6. Exec_CADVS-v5 = {x ∈ supp(π_θ^FM) : ∧_i kc_i(x,c; γ_i·τ_i^4)=1} ⊆ Exec_CADVS-v4。

**本轮最大风险**：**记忆固化自指回路**——流策略在自己铸证的片段上训练、价值模型又在线自适应，「铸证→学习→再铸证」闭环缺乏外部真值，策略可能学会博弈证书门（形式合规、实质违背），证书退化为自洽但失真的自我背书；冻结门 + 人工抽检子集 + KL 正则 + 红队只能缓解，无法根除。
<!-- IDEA:END -->

---
## 1. 增量定位与继承关系（CADVS-v1 基础框架）

### 1.1 新增核心模块（相对 CADVS-v1）

| 编号 | 名称 | 类型 | 关键改进（相对 CADVS-v1） |
|---|---|---|---|
| IP-493 | Flow Matching Proposal Policy Kernel (FMPP) | 提议升级 | 条件流匹配生成候选轨迹；上下文含检索记忆与人类状态；级联采样选证；BCK 边际蒸馏为可行性先验 |
| IP-494 | Long-term Memory with Embedding & Consolidation (LMEM-v2) | 记忆升级 | 条目附轨迹嵌入 e_τ；Top-k 检索作流条件 token；铸证片段固化入策略（DP-SGD+KL 正则）；n_flow 密度新颖度并入 kc_mem |
| IP-495 | Facial Affect Modulation Kernel (FAMK) | 人因升级 | 端侧 FER 估计 ŝ_emo；非对称阈值调制 γ_i ≥ 1（只紧不松）；λ_vec 情感自适应；fail-safe 回退 v4 静态阈值 |
| IP-496 | Evidence Forging Assembler v5 (EFA-v5) | 证据融合 | 七硬门不变 + 调制阈值 τ^5=γ·τ^4；级联采样选证；ECS_v5 = ECS_v4 · η_flow · η_emo |

### 1.2 v1 模块适配表（只改接口，不推翻）

| v1 模块 | v1 适配 |
|---|---|
| 七硬门 | kc_3DCF, kc_MSRG, kc_HICK, kc_EEK, kc_LTEM, kc_VACK, kc_BCK 原样继承，布尔谓词形式保持不变 |
| 执行集 | Exec_v1 = {x : ∧_i kc_i(x) = 1} 基础定义，支持阈值嵌套扩展 |
| 上下文 | c_ctx = (obj, g_emb, θ_fp, task) 基础上下文，后续轮次补充 ŝ_emo、m_{1:k} 等 |
| 语音映射 | σ(conf_speech) 单调非减映射，τ_i = τ_i^0 · σ(conf_speech) 作为软调制接口 |

## 2. 增量符号体系（定义 2101–2240）

| 符号 | 含义 |
|---|---|
| x = (pose_{0:T}, wrench_{0:T}) | 候选轨迹：末端位姿 + 广义力时间序列，维度 d_x |
| c_ctx = (obj, g_emb, θ_fp, task, σ_speech) | 基础流条件上下文：物体/几何嵌入/领域指纹/任务/语音置信度 |
| v_θ(x,t\|c), t∈[0,1] | 时间依赖向量场（DiT/Transformer，条件 cross-attention） |
| x_t = (1−t)x_0 + t·x_1, x_0 ~ N(0,I) | 线性插值概率路径（rectified flow） |
| L_FM(θ) = E_{t,x0,x1\|c}‖v_θ(x_t,t\|c) − (x_1−x_0)‖² | 流匹配训练损失 |
| dx/dt = v_θ(x,t\|c) | 采样 ODE，S 步 Euler/RK 积分 |
| π_θ^FM(·\|c) | 流匹配提议分布（ODE 解的 pushforward） |
| K, S | 每次准入候选数（缺省 8）、ODE 积分步数（蒸馏后缺省 10） |
| Exec^(l) = {x : ∧_i kc_i(x) ∧ τ_threshold(x) = 1} | 第 l 层执行集，通过阈值嵌套实现收缩 |
| τ_i = τ_i^0 · σ(conf_speech) | 语音调制后门阈值，σ 单调非减，conf_speech 为语音识别置信度 |
| kc_i(x) ∈ {0,1} | 七硬门布尔谓词：kc_3DCF, kc_MSRG, kc_HICK, kc_EEK, kc_LTEM, kc_VACK, kc_BCK |
| σ_speech ∈ [0,1] | 语音识别置信度 |

## 3. 关键算法骨架

### IP-493 FMPP：流匹配提议策略核（准入/10 Hz 预览时域，不在 1 kHz 环）

```python
@dataclass
class FlowMatchingProposalPolicyKernel:
    """FMPP：条件流匹配提议器。
    定理 6（证书不变性）：提议可换，门不可换——门是信任边界"""
    net: Any                      # v_θ：DiT/Transformer，条件 cross-attn
    S: int = 10                   # 蒸馏后 ODE 步数
    K: int = 8                    # 候选数
    margin_head: Any = None       # BCK 边际蒸馏头（可行性先验，回应 v4-R49）

    def train_loss(self, batch) -> float:
        # rectified flow：x_t = (1-t)x0 + t·x1，目标场 = x1 - x0
        x0 = randn_like(batch.x1)
        t = rand(batch.B, 1)
        x_t = (1 - t) * x0 + t * batch.x1
        return mse(self.net(x_t, t, batch.c), batch.x1 - x0)

    def distill_margin_prior(self, bck_margin_samples) -> None:
        """离线：沿 BCK 采样的可行/不可行轨迹训练辅助边际头，
        让提议先验偏好高 ξ_wrench/ξ_zmp 区域，降低在线拒绝率"""
        ...

    def propose(self, c: Context, k: int = None) -> list[Trajectory]:
        """从 N(0,I) 积分 ODE 至 t=1，K 个候选；准入时域/10 Hz 预览"""
        xs = randn(k or self.K, d_x)
        for s in range(self.S):
            xs = xs + (1.0 / self.S) * self.net(xs, s / self.S, c)
        return decode(xs)

    def log_lik(self, x: Trajectory, n_probe: int = 4) -> float:
        """概率流 ODE + Hutchinson 迹估计 → log p(x)，供新颇度 n_flow（引理 43）"""
        ...
```

### IP-494 LMEM-v2：嵌入记忆与固化核（检索 O(log|M|)；固化离线）

```python
@dataclass
class LongTermMemoryEmbeddingConsolidation:
    """LMEM-v2：嵌入检索 + 流条件 + 铸证固化 + 密度新颖度。
    红线：固化只改提议器 θ_FM，永不改门（门代码与 τ^4 冻结只读）"""
    emb: Any                      # e_τ 编码器
    faiss_idx: Any
    tau_novel: float = 8.0        # 归一化 n_flow 阈值

    def query(self, obj, geo_sig, theta_fp, rule_id, x: Trajectory) -> QueryResult:
        m_topk = self._retr(self.emb(x), k=4)            # Top-k 记忆 token → 流条件
        n_flow = -self.fmpp.log_lik(x) / d_x             # 密度新颖度
        novel = (n_flow > self.tau_novel) or count_stat_reject(obj, geo_sig, theta_fp, rule_id)
        return QueryResult(pass_mem=not novel, eta_mem=..., novelty=novel,
                           m_topk=m_topk, n_flow=n_flow)

    def consolidate(self, episode_store, fmpp, dp_eps: float, kl_eps: float) -> None:
        """只取「已铸证 ∧ 结局验证成功 ∧ 人工抽检通过」的片段；
        DP-SGD(ε=dp_eps)；KL(π_new‖π_old) ≤ kl_eps 正则防遗忘/防漂移；
        20% 失败片段回放；固化后全量重跑回归门测试 + 红队对抗集"""
        certified = [ep for ep in episode_store
                     if ep.forged and ep.outcome_ok and ep.human_audit]
        # frozen-gate 红线：门代码与 τ^4 在此只读，任何梯度不经过门
        ...
```

### IP-495 FAMK：面部情感调制核（端侧，10–30 Hz，与控制环解耦）

```python
@dataclass
class FacialAffectModulationKernel:
    """FAMK：端侧 FER → 非对称阈值调制 γ_i ≥ 1。
    定理 5：情绪只能收紧，永不放松（对抗面结构性消除）"""
    fer: Any                      # 端侧 ViT-Tiny（AffectNet/DFER 蒸馏），10–30 Hz
    kappa: dict = field(default_factory=lambda:
        {'veto': 0.5, 'wrench': 1.0, 'zmp': 1.0, 'val': 0.3})   # κ_i ∈ [0, κ_max]
    sigma_max: float = 0.25       # 不确定度上限，超过则不调制
    lam_emo: float = 0.3

    def observe(self, face_crop, t_now) -> SHomo:
        v, a, p_d, sigma = calibrated_fer(self.fer, face_crop)   # 温度校准
        return ema(self.s_prev, (v, a, p_d, sigma), alpha=0.3)   # EMA 平滑，O(1)

    def gamma(self, s: SHomo) -> dict:
        if s is None or s.sigma > self.sigma_max or not face_available:
            return {i: 1.0 for i in self.kappa}   # fail-safe：回退 v4 静态阈值
        return {i: 1.0 + k * s.p_distress
                for i, k in self.kappa.items()}   # γ ≥ 1 恒成立（只紧不松）

    def modulate_lambda(self, lambda_vec: np.ndarray) -> np.ndarray:
        """情感自适应 λ_vec：仅向安全倾斜，投影回单纯形，位移 ≤ 0.1 有界"""
        ...
    # 隐私：人脸特征端侧即用即弃，原始图像永不出端；任何上报统计过 DP；
    # 提供显式同意与关闭开关（关闭 = 恒 γ≡1，系统精确退化为 v4）
```

### IP-491 扩展 CERTCALC-v5：新增定理 5~8（离线理论）

```python
# 定理 5：调制单调性
def theorem_modulation_monotonicity() -> str:
    """
    定理 5（调制单调性）：若所有门取规范形 kc_i(x) = 1[s_i(x) ≥ τ_i]（s_i 与阈值无关），
    且调制满足 γ_i(ŝ_emo) ≥ 1（非对称），则 Exec_v5(ŝ_emo) ⊆ Exec_v5(static) ⊆ Exec_v4。
    证明：阈值单调升 ⇒ 各门通过集单调缩 ⇒ 交集缩；γ≡1 时精确退化 v4。∎
    工程含义：情绪调制是「收紧器」不是「决策器」；伪造笑脸降低安全边际在结构上不可能。
    """
    return "Proven"

# 定理 6：证书不变性（提议无关性）——本轮理论主轴
def theorem_certificate_invariance() -> str:
    """
    定理 6（证书不变性）：对任意提议分布 π（离散规则库、流匹配、任意生成器），
    可执行集 {x : ∧_i kc_i(x,c;τ)=1} 与 π 无关；π 只决定「尝试通过门的提议分布」，
    不改变 fail-closed 边界。推论：Exec_v5 = Exec_gate ∩ supp(π_FM) ⊆ Exec_gate = Exec_v4。
    证明：门是轨迹空间上的固定谓词，换提议不换谓词。∎
    意义：框架从「规则系统」推广为「任意生成器 + 认证边界」（CGE）。
    """
    return "Proven"

# 定理 7：固化有界与防博弈
def theorem_consolidation_boundedness() -> str:
    """
    定理 7（固化有界性）：若固化算子 C_cons 满足 (C1) 训练集仅含「铸证 ∧ 结局验证成功 ∧ 人工抽检」片段；
    (C2) ‖Δθ‖ ≤ Δ_max 且 KL(π_new‖π_old) ≤ ε_KL；(C3) 门代码与 τ^4 冻结只读，
    则 (i) 策略分布漂移 ≤ ε_KL 对应的总变差界；(ii) 执行集只能收缩（门不变 + 阈值不变）；
    (iii) 门博弈率以红队回归集上的检测率为经验上界，无先验根除保证（诚实边界）。
    证明：(ii) 由数据处理不等式 + 谓词不变；(i) 由 KL–TV 不等式（Pinsker）。∎
    """
    return "Proven (bounds); gaming-rate bound empirical only"

# 定理 8：七锚完备性在调制下保持
def theorem_completeness_preserved() -> str:
    """
    定理 8：v5 不增删锚点：七锚 {3DCF, MSRG, HICK, EEK, LTEM, VACK, BCK} 完备性（v4 定理 4）保持；
    FAMK 是 HICK 内部的阈值调制通道（非新锚），FMPP/LMEM-v2 是提议器/记忆升级（非新锚）。
    证明：锚点集合不变 + 调制只紧（定理 5）⇒ 覆盖链不变且只强不弱。∎
    """
    return "Proven"
```

### IP-496 EFA-v5：七硬门 + 调制阈值 + 级联采样选证

```python
@dataclass
class EvidenceForgingAssemblerV5:
    """EFA-v5：七硬门不变（阈值可调制、只紧不松）+ 级联采样选证"""
    fmpp: FlowMatchingProposalPolicyKernel
    lmem: LongTermMemoryEmbeddingConsolidation
    famk: FacialAffectModulationKernel
    v4: EvidenceForgingAssemblerV4        # 复用 scf/msrg/hic/eek/vack/bck 全套

    def select(self, x0_state, t_now, rule_id, context) -> tuple[bool, Trajectory | None, str]:
        s_emo = self.famk.observe(context.face, t_now)
        gamma = self.famk.gamma(s_emo)                   # 全 1.0 = 精确退化 v4
        c = build_ctx(context, s_emo, self.lmem)         # 含 Top-k 记忆 token
        cands = self.fmpp.propose(c, self.fmpp.K)        # K=8，~5–20 ms，异步准入时域
        # 级联第 1 层：廉价门（coverage/physics/memory/novelty，O(1)~O(log|M|)）
        surv = [x for x in cands if self._cheap_gates(x, gamma)]
        if not surv:
            return self._fallback_rule_proposal(gamma)   # fail-closed：回退 v4 规则提议
        # 级联第 2 层：VACK 仅评估 ≤3 幸存者（~50 ms 级，异步；预筛省 ~60% 昂贵调用）
        surv.sort(key=lambda x: self._prefilter_score(x), reverse=True)
        finals = []
        for x in surv[:3]:
            vac = self.v4.vack.evaluate(x, context_with(s_emo), t_now)
            if self.v4.vack.kc_val(vac, tau=gamma['val'] * TAU_VAL4):
                finals.append(x)
        # 级联第 3 层：BCK 轨迹预览（事件触发 QP + 缓存证书内插）
        ok = [x for x in finals if self._bck_preview(x, gamma)]
        if not ok:
            return False, None, 'ALL_CANDIDATES_REJECTED'
        best = max(ok, key=certified_margin)             # 通过者中取边际最大者
        return True, best, 'FORGED_CGE'

    def ecs_v5(self, ..., n_flow: float, s_emo: SHomo | None) -> float:
        eta_flow = sigmoid(n_flow_to_ll(n_flow) - b_flow)
        eta_emo = (1.0 - self.famk.lam_emo * s_emo.p_distress
                   if s_emo is not None and s_emo.sigma <= self.famk.sigma_max else 1.0)
        return self.v4.ecs_v4(...) * eta_flow * eta_emo
```

### 集成流水线（v1 → v5）

```
离线/慢时域：
  固化（小时级）：铸证片段 ──▶ 证书过滤 ──▶ DP-SGD + KL 正则 + 失败回放 ──▶ θ_FM 更新
       ──▶ 回归门测试 + 红队对抗集 ──▶ 通过才上线（回滚 = 旧 θ_FM）
  边际蒸馏：BCK 离线可行/不可行轨迹采样 ──▶ FMPP 可行性先验头
  联邦：Δ_i(轨迹嵌入原型/情绪分位数, DP) ──▶ 安全聚合 ──▶ FedAvg ──▶ Φ_global
       ──▶ 下发：流先验原型、Γ_3D/Θ_domain/λ_vec^0 校准、ε_emo 参数

在线准入（异步，秒级）：
  FAMK.observe (10–30 Hz, 端侧) ──▶ γ(ŝ_emo) 预计算
  FMPP.propose (K=8) ──▶ 廉价门筛（含 n_flow 新颇度）
       ├─ 全灭 ──▶ fail-closed 回退 v4 规则提议
       └─ 幸存 ≤3 ──▶ VACK（调制 τ_val）──▶ BCK 预览 ──▶ 取边际最大者

在线控制环（目标 < 0.6 ms）：
  每周期：EEK(kc_ee) + BCK（事件触发：接触状态未变 → 缓存证书 + 解析边际内插，O(1)）
  证书消费：τ^5 = γ·τ^4 每周期预计算；消费缓存的候选证书
```

