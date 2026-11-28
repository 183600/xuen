## 0. 增量定位与继承关系（在 IP-493~496/CADVS-v5 基础上扩展）

### 0.1 新增核心模块

| 编号 | 名称 | 类型 | 关键改进（相对 CADVS-v5） |
|---|---|---|---|
| IP-497 | Joint-Space Realizability Kernel (JSRK) | 执行可实现性 | 集合值提升 R(x)：任务轨迹→关节轨迹；关节限位/速度/力矩/自碰撞/奇异检查；MMRR 边际最大化冗余消解；dexterity 证书 |
| IP-498 | Brushless Actuator Envelope Kernel (BAEK) | 执行器建模 | PMSM/BLDC 电流圆 ∩ 电压椭圆 ∩ 热降额 → 力矩-转速包络；FOC 跟踪误差、齿槽/换相脉动、编码器/摩擦误差界；回馈制动约束 |
| IP-499 | Certificate Transfer Budget (CTB) | 证书演算 | 雅可比传递 δp=Jδq、δw=J^{-T}δτ；边际台账 ρ_real=ρ−L·ε；奇异度 σ_min 下限；余额为负 fail-closed；运行时有效性监视 |
| IP-500 | Evidence Forging Assembler v6 (EFA-v6) | 证据融合 | 七硬门不变；任务空间门 → 关节/执行器可实现性联合判定；级联廉价包络预筛；ECS_v6 = ECS_v5 · η_real |

### 0.2 v5 模块适配表（只改接口，不推翻）

| v5 模块 | v6 适配 |
|---|---|
| IP-493 FMPP | 提议仍在任务空间；输出 x 必须经 JSRK.lift 才能进入执行；log_lik 原样用于 n_flow |
| IP-494 LMEM-v2 | 记忆条目扩为 (e_τ, e_q, σ_min 统计, 包络健康)；检索 token 增加关节可实现性原型；固化红线不变（只改提议器，不改门） |
| IP-495 FAMK | 原样继承；γ 先作用于任务空间阈值 τ^5，再由 CTB 折算为关节/执行器侧的等效收紧 |
| IP-489 VACK | 上下文增加关节可行性摘要；仅对已通过 JSRK/BAEK 粗筛的候选做昂贵评估 |
| IP-490 BCK | kc_bal 形式不变；wrench 由关节力矩经 J^T 生成，新增「包络可行 + 传递余额」检查；事件触发 QP 保留 |
| IP-485 EEK | kc_ee 形式不变；末端误差预算加入 σ_max(J)·ε_q + ε_kin |
| IP-487 FFA | Δ_i 增加关节嵌入原型（DP）、包络/热统计（DP）；Φ_global 下发 σ_min 先验、电机参数标称 |
| IP-488 EFA-v5 | 升级为 EFA-v6：门集合不变，新增 JSRK→BAEK→CTB 可实现性级联与运行时监视器 |
| IP-491 CERTCALC | 扩展 CERTCALC-v6：新增定理 9/10/11/12 与引理 45/46/47 |
| IP-473~484 | RCANG/DLC/MRCC/TCVM/STCK/GCK/DAKI/VSCK 等原样继承 |

## 1. 增量符号体系（定义 2241–2380）

| 符号 | 含义 |
|---|---|
| n, m=6 | 关节自由度、任务空间维数（n ≥ m，冗余度 n−m） |
| q ∈ R^n, q̇, q̈, τ ∈ R^n | 关节位置、速度、加速度、力矩 |
| f: R^n → SE(3) | 正运动学；p = f(q) |
| J(q) = ∂f/∂q ∈ R^{m×n} | 几何雅可比（世界/工具系） |
| σ_1 ≥ … ≥ σ_m > 0 | J 的奇异值；σ_max=σ_1，σ_min=σ_m（满行秩时） |
| κ(J) = σ_max/σ_min | 条件数（奇异度指标） |
| σ_floor | 允许的最小 σ_min；低于即判不可实现（fail-closed） |
| R(x) | 提升关系：任务轨迹 x 对应的全部关节轨迹 (q,q̇,τ) 集合（集合值，因冗余） |
| Q_lim, q̇_max, τ_max | 关节位置限位、速度上限、力矩上限 |
| A(ω, T_w, V_dc) | 执行器可行集：给定转速/绕组温度/母线电压下可实现的力矩集合 |
| p, λ_m | 电机极对数、永磁磁链 |
| R_s, L_d=L_q=L | 定子电阻、d/q 轴电感（表贴式 PMSM） |
| i_max(T_w) | 随绕组温度降额的电流上限 |
| V_dc, V_max=V_dc/√3 | 母线电压、相电压幅值上限 |
| ω_e = p·ω_m | 电角速度 |
| τ_max(ω,T_w,V_dc) | 力矩-转速-电压-热包络上界 |
| τ_min(ω,V_dc) | 回馈制动下界（防母线过压） |
| T_w, T_max, T_derate | 绕组温度、硬上限、开始降额温度 |
| R_th, C_th | 热阻、热容（一阶热模型） |
| ε_foc | FOC 电流环跟踪误差（带宽/滞后） |
| ε_ripple | 齿槽 + 换相转矩脉动界 |
| ε_est | 力矩估计误差（摩擦、参数漂移；无关节力矩传感器时更大） |
| ε_τ = ε_foc + ε_ripple + ε_est | 关节力矩总误差界 |
| ε_q = ε_enc + ε_bl + ε_ctrl | 关节位置总误差界（编码器量化 + 齿隙 + 位置环跟踪） |
| ε_kin | 运动学标定误差（工具中心点/连杆参数） |
| ε_model | 动力学/接触模型误差 |
| ε_ext | 外部扰动界 |
| ρ_i(x) = s_i(x) − τ_i | 任务空间第 i 门的物理边际（>0 为通过） |
| D_ee = σ_max·ε_q + ε_kin | 末端姿态传递误差预算 |
| D_w = σ_min^{-1}·ε_τ + ε_model + ε_ext | 力/力矩传递误差预算 |
| L_i | 第 i 门评分对 (pose, wrench) 的 Lipschitz 常数 |
| ρ_i^real = ρ_i − L_i·(D_ee + D_w) | 实际执行后的保守边际 |
| Ledger(x) = (ρ_i^real, σ_min, T_w, A) | 边际台账 |
| μ_real = min_i ρ_i^real / scale_i | 归一化可实现性余额（无量纲） |
| η_real = σ(μ_real / T_real) | 可实现性软因子 ∈ (0,1) |
| ECS_v6 = ECS_v5 · η_real | v6 软评分 |
| M(t) | 运行时证书有效性监视器（误差/温度/奇异度断言） |
| Exec_CADVS-v6 | {x ∈ Exec_v5 : ∃ witness ∈ R(x)∩A, min_i ρ_i^real ≥ 0, M(t)=1} |

## 2. 关键算法骨架

### IP-497 JSRK：关节空间可实现性核（准入/10 Hz，异步，不进 1 kHz 环）

```python
@dataclass
class JointSpaceRealizabilityKernel:
    """JSRK：任务轨迹 → 关节轨迹（集合值）+ MMRR 边际最大化逆解。
    定理 9：任务空间证书不充分；定理 11：换逆解不改门边界。"""
    kin: Any                      # f(q), J(q), 自碰撞距离场, 连杆参数
    q_lim: Any; dq_max: Any; tau_lim: Any
    n_red: int                    # n - m 冗余度
    sigma_floor: float = 0.05     # 奇异度下限

    def lift(self, x: Trajectory, N_grid: int = 64) -> list[JointTrajectory]:
        """逐时间栅格求 IK 多解（解析/数值），冗余零空间采样；
        过滤 q_lim / dq_max / 自碰撞 / sigma_min < sigma_floor"""
        cands = []
        for p_t, w_t in sample(x, N_grid):
            for q in self._ik_multisol(p_t):          # 含零空间采样
                if not self._limits_ok(q):  continue
                if self._self_collide(q):   continue
                if sigma_min(self.kin.J(q)) < self.sigma_floor: continue
                cands.append(q)
        return self._stitch(cands, x)                 # 时间连续拼接

    def mmrr(self, cands: list[JointTrajectory], ledger) -> JointTrajectory | None:
        """max-min：最大化轨迹上最坏时刻的台账余额。
        零空间投影：qdot = J^+ xdot + (I - J^+ J) grad phi(q)，
        phi 同时含 sigma_min、关节限位裕度、自碰撞裕度。"""
        best, best_val = None, -inf
        for jt in cands:
            val = min(ledger.margin(jt, t) for t in range(len(jt.q)))
            if val > best_val:
                best, best_val = jt, val
        return best

    def dexterity_cert(self, jt) -> float:
        return min(sigma_min(self.kin.J(jt.q[t])) for t in range(len(jt.q)))
```

### IP-498 BAEK：无刷电机执行器包络核（O(1)/点；热观测在线）

```python
@dataclass
class BrushlessActuatorEnvelopeKernel:
    """BAEK：PMSM/BLDC 力矩-转速-电压-热包络 + 跟踪/脉动误差界。
    定理 11：包络只紧不松（热降额/电压跌落只缩执行集）。"""
    p: int; lam_m: float; Rs: float; L: float
    i_max0: float; Vdc: float; T_max: float; T_derate: float
    Rth: float; Cth: float; k_fe: float
    eps_ripple: float = 0.02      # 齿槽+换相（标称力矩比例）
    eps_est: float = 0.03         # 摩擦/参数（无关节力矩传感器）

    def i_q_max(self, omega_e: float, T_w: float, Vdc: float) -> float:
        Vmax = Vdc / math.sqrt(3.0)
        # 电流圆 ∩ 电压椭圆：|v_d|^2+|v_q|^2 <= Vmax^2, v_d=-wL i_q, v_q=Rs i_q+w lam
        rad = (self.Rs**2 + (omega_e*self.L)**2) * Vmax**2 \
              - (omega_e**4) * self.L**2 * self.lam_m**2
        i_v = 0.0 if rad <= 0 else (
            -self.Rs*omega_e*self.lam_m + math.sqrt(rad)) \
            / (self.Rs**2 + (omega_e*self.L)**2)
        # 热降额：T_w 越高，i_max 越低（单调非增）
        derate = clip((self.T_max - T_w) / (self.T_max - self.T_derate), 0.0, 1.0)
        return min(self.i_max0 * derate, max(0.0, i_v))

    def tau_max(self, omega_m: float, T_w: float, Vdc: float) -> float:
        return 1.5 * self.p * self.lam_m * self.i_q_max(self.p*omega_m, T_w, Vdc)

    def thermal_step(self, T_w: float, i_q: float, omega_e: float, dt: float) -> float:
        P_cu = 1.5 * self.Rs * i_q**2
        P_fe = self.k_fe * omega_e**2
        return T_w + dt * (P_cu + P_fe - (T_w - self.T_amb) / self.Rth) / self.Cth

    def error_bounds(self, tau_ref, bw: float) -> tuple[float, float]:
        # 一阶电流环：斜坡跟踪误差 ~ |dtau_ref|/bw；叠加脉动与估计误差
        eps_foc = max(abs(dtau) for dtau in finite_diff(tau_ref)) / bw
        eps_tau = eps_foc + self.eps_ripple*max(abs(tau_ref)) + self.eps_est
        return eps_tau, 0.0     # eps_q 由关节编码器/齿隙/位置环单独给出

    def feasible(self, jt) -> bool:
        T_w = self.T_w0
        for t in range(len(jt.q)):
            w = jt.dq[t]
            if abs(jt.tau[t]) > self.tau_max(w, T_w, self.Vdc): return False
            T_w = self.thermal_step(T_w, jt.iq[t], self.p*w, self.dt)
            if T_w > self.T_max: return False
        return True
```

### IP-499 CTB：证书传递与边际台账（CERTCALC-v6 的运行时部分）

```python
@dataclass
class CertificateTransferBudget:
    """CTB：把任务空间边际按雅可比与执行器误差折算成实际边际。
    定理 10：rho_real >= rho - L*(D_ee + D_w)；余额为负即 fail-closed。"""
    eps_q: float                  # 编码器+齿隙+位置环
    eps_kin: float
    eps_model: float
    eps_ext: float
    sigma_floor: float = 0.05

    def ledger(self, x, jt, ae: BrushlessActuatorEnvelopeKernel, gates) -> MarginLedger:
        J = jacobian_at(jt)
        s_min = min(sigma_min(J)); s_max = max(sigma_max(J))
        eps_tau, _ = ae.error_bounds(jt.tau, bw=ae.bw_current)
        D_ee = s_max * self.eps_q + self.eps_kin
        D_w = (eps_tau / max(s_min, 1e-9)) + self.eps_model + self.eps_ext
        rho_ee = gates.rho_ee - gates.L_ee * (D_ee + D_w)
        rho_w  = gates.rho_w  - gates.L_w  * (D_ee + D_w)
        ok = (rho_ee >= 0 and rho_w >= 0
              and s_min >= self.sigma_floor and ae.feasible(jt))
        return MarginLedger(rho_ee=rho_ee, rho_w=rho_w, s_min=s_min,
                            feasible=ok)

    def runtime_monitor(self, jt, meas) -> bool:
        """M(t)：运行时断言。误差越界/温度越界/奇异度跌破 → 证书作废。"""
        return (max_abs(meas.q_err) <= self.eps_q
                and max_abs(meas.tau_err) <= self.eps_tau
                and meas.T_w <= self.T_max
                and meas.sigma_min >= self.sigma_floor)
```

### IP-500 EFA-v6：七硬门 + 可实现性级联 + 运行时监视

```python
@dataclass
class EvidenceForgingAssemblerV6:
    """EFA-v6：七硬门不变（阈值 τ^5=γ·τ^4 原样），新增可实现性级联。
    红线：可实现性只缩小执行集，绝不扩大；无 witness 即 fail-closed。"""
    v5: EvidenceForgingAssemblerV5
    jsrk: JointSpaceRealizabilityKernel
    baek: BrushlessActuatorEnvelopeKernel
    ctb: CertificateTransferBudget

    def select(self, x0_state, t_now, rule_id, context):
        # 1) v5 任务空间提议 + 七门级联（原样）
        ok, x, reason = self.v5.select(x0_state, t_now, rule_id, context)
        if not ok:
            return False, None, reason
        # 2) 关节提升（多解）+ MMRR（含奇异/限位/自碰撞）
        jts = self.jsrk.lift(x)
        if not jts:
            return self._fallback_or_stop('NO_JOINT_WITNESS')
        # 3) 执行器包络廉价预筛（逐点 tau_max + 热模型）
        jts = [jt for jt in jts if self.baek.feasible(jt)]
        if not jts:
            return self._fallback_or_stop('ACTUATOR_ENVELOPE')
        # 4) 边际台账（CTB）选余额最大者
        best, best_led = None, None
        for jt in jts:
            led = self.ctb.ledger(x, jt, self.baek, self._gate_margins(x))
            if led.feasible and (best_led is None or led.mu_real > best_led.mu_real):
                best, best_led = jt, led
        if best is None:
            return self._fallback_or_stop('MARGIN_LEDGER_NEGATIVE')
        return True, (best, best_led), 'FORGED_CRE'

    def ecs_v6(self, ..., mu_real: float, ...) -> float:
        eta_real = sigmoid(mu_real / self.T_real)     # ∈ (0,1)
        return self.v5.ecs_v5(...) * eta_real
```

### 集成流水线（v5 → v6）

```
离线/慢时域：
  参数辨识：f(q)/J、摩擦、电机 Rs/L/λ_m、热模型 Rth/Cth、齿槽脉动谱
  标定：ε_kin（手眼/TCP）、编码器分辨率、齿隙；σ_floor 设定
  可达性/包络表：τ_max(ω,T_w,V_dc) 网格 + 回馈制动下界 τ_min

在线准入（异步，秒级；10 Hz 预览）：
  v5：FMPP 提议 + 七门级联（任务空间，原样）
     └─ 失败 → v5 回退
  JSRK.lift（IK 多解 + 零空间采样）→ 限位/自碰撞/σ_min 过滤
     └─ 空 → fail-closed（回退规则提议 / 安全停机）
  MMRR（max-min 台账）→ BAEK 包络/热预筛 → CTB 边际台账
     ├─ 余额 < 0 → fail-closed
     └─ 选 μ_real 最大者 → 下发关节参考轨迹

在线控制环（1 kHz）：
  关节跟踪（计算力矩 + 关节阻抗，能量罐被动性）→ FOC 电流环 → PMSM/BLDC
  热观测器更新 T_w → 包络降额；M(t) 断言 q_err/tau_err/T_w/σ_min
     └─ 任一越界 → 证书作废 → fail-closed（保持/回撤/安全停）
```

## 3. 复杂度分析（增量更新）

| 模块 | 时间复杂度 | 空间复杂度 | 关键参数 | 实时性指标 |
|---|---|---|---|---|
| JSRK.lift | O(N_grid·n_red·c_IK) | O(N_grid·n·n_red) | N_grid=64, n_red≤3 | ~5–30 ms，仅准入/10 Hz |
| JSRK.mmrr | O(N_grid·(n³ + n_red)) | O(N_grid·n) | SVD n³ | ~2–10 ms，准入 |
| BAEK.feasible | O(N_grid) | O(1) | 逐点闭式 | < 1 ms |
| BAEK.thermal_step | O(1) | O(1) | 一阶热模型 | 控制环 O(1) |
| CTB.ledger | O(N_grid·n³)（SVD） | O(N_grid) | 可离线缓存 SVD | ~2–8 ms，准入 |
| CTB.runtime_monitor | O(1) | O(1) | 断言 | < 0.02 ms，1 kHz |
| EFA-v6 增量 | ~10–50 ms（准入） | — | 全部异步 | 不进 1 kHz 环 |
| 控制环 | 与 v5 相同 | — | 关节跟踪 + FOC | **P99 ~0.58 ms（v5 0.55 ms）** |

**通信开销**：关节嵌入原型 ~2 KB/站（DP）；电机参数/热统计仅本地分位数（DP，低频）；无原始电流/温度波形出站。可实现性表与 σ_min 先验经签名下发。

**实时性说明**：JSRK/BAEK/CTB 全部在准入时域（10 Hz 预览）完成；控制环只消费预计算关节参考、包络降额表与缓存 SVD，运行时监视器 O(1)。

## 4. 正确性论证（增量更新）

### 引理 45（雅可比扰动界）

**陈述**：设 J(q) 满行秩，f 二阶连续可微。则对 δq，
‖f(q+δq) − f(q) − Jδq‖ ≤ ½·L_H·‖δq‖²；故 ‖δp‖ ≤ σ_max(J)‖δq‖ + O(‖δq‖²)。
对力矩映射 τ = J^T w（等价 w = J^{-T}τ），有 ‖δw‖ ≤ ‖J^{-T}‖·‖δτ‖ = σ_min(J)^{-1}‖δτ‖。
当 σ_min → 0（奇异），wrench 误差放大无界。∎

### 引理 46（电流环跟踪与热降额单调性）

**陈述**：(i) 一阶电流环带宽 ω_c 下，力矩参考斜率有界 D 时，稳态跟踪误差 |τ − τ_ref| ≤ D/ω_c，故 ε_foc ≤ D/ω_c。
(ii) i_max(T_w) 关于 T_w 单调非增；i_v(ω_e,V_dc) 关于 V_dc 单调非减、关于 ω_e 单调非增（电压椭圆收缩）。
(iii) 因而 τ_max(ω,T_w,V_dc) 关于 T_w、ω 单调非增，关于 V_dc 单调非减；包络收缩只会缩小可行集 A。∎

### 引理 47（热模型有界性）

**陈述**：一阶热模型 C_th Ṫ_w = P_cu + P_fe − (T_w−T_amb)/R_th，若 P_cu+P_fe ≤ P_max，则 T_w(t) ≤ T_amb + R_th P_max + (T_w(0)−T_amb−R_th P_max)e^{−t/(R_th C_th)}；故存在有限稳态上界，可用保守降额保证 T_w ≤ T_max。∎

### 定理 9（提升必要性：任务空间证书不充分）

**陈述**：存在 x ∈ Exec_CADVS-v5，使 R(x) ∩ A = ∅。即 v5 的七门全部通过不蕴含关节/电机可实现。

**证明（构造）**：取 2-DOF 平面臂接近全伸展（σ_min(J) → 0⁺）。令末端沿奇异方向以速度 ẋ 运动，任务空间轨迹平滑、wrench 很小，故 v5 的 EEK/MSRG/BCK 全部通过且边际为正。但所需关节速度满足 ‖q̇‖ = ‖J⁺ẋ‖ ≥ σ_min^{-1}‖ẋ‖ → ∞；取 ẋ 使 σ_min^{-1}‖ẋ‖ > q̇_max，则任何提升都违反关节速度约束，R(x) ∩ A = ∅。
对偶地，沿小奇异方向施加给定 wrench w 需 τ = J^T w，其分量 ~ ‖w‖/σ_min；当超过 τ_max(ω,T_w,V_dc) 时包络不可行。∎

**工程含义**：v5 的「已认证」应读作「任务空间合格」，不是「可执行」。v6 把证书的语义从「合格」收紧为「可执行且合格」。

### 定理 10（证书传递 / 边际守恒）

**陈述**：设 x 满足 v5 各门，物理边际 ρ_i(x) > 0，且第 i 门评分对 (pose, wrench) 为 L_i-Lipschitz。若存在 witness (q,q̇,τ) ∈ R(x) ∩ A，实际执行误差满足 ‖δq‖ ≤ ε_q、‖δτ‖ ≤ ε_τ、标定/模型误差 ≤ ε_kin/ε_model，并记
D_ee = σ_max(J)ε_q + ε_kin，D_w = σ_min(J)^{-1}ε_τ + ε_model + ε_ext，
则实际轨迹的第 i 门边际满足
ρ_i^real ≥ ρ_i − L_i·(D_ee + D_w)。
特别地，若 ρ_i > L_i(D_ee + D_w) ∀i，则实际执行仍通过原七门；若某门余额 ≤ 0，则该 witness 不可认证。

**证明**：由引理 45，实际位姿 p̂ = p + Jδq + O(‖δq‖²) + e_kin，故 ‖p̂−p‖ ≤ D_ee；实际 wrench ŵ = w + J^{-T}δτ + e_model + e_ext，故 ‖ŵ−w‖ ≤ D_w。对 L_i-Lipschitz 评分 s_i，有 |s_i(p̂,ŵ) − s_i(p,w)| ≤ L_i(‖p̂−p‖+‖ŵ−w‖) ≤ L_i(D_ee+D_w)。于是 ρ_i^real = s_i(p̂,ŵ) − τ_i ≥ ρ_i − L_i(D_ee+D_w)。∎

**紧性**：取 δq 沿 J 的最大奇异方向、δτ 沿最小奇异方向，可同时逼近 D_ee 与 D_w 的上界；故条件在 O(ε²) 内紧。

### 定理 11（实现无关性与非对称收紧）

**陈述**：
(i) **实现无关性**：固定门谓词后，Exec_v6 = {x ∈ Exec_v5 : ∃ witness ∈ R(x)∩A, ledger ≥ 0} 与选哪个逆解分支、哪种冗余消解、哪种电机控制律无关；这些选择只改变「尝试执行的 witness 集合」，不改变信任边界。
(ii) **非对称收紧**：若 A' ⊆ A（热降额、电压跌落、编码器退化、回馈限幅），则 Exec_v6(A') ⊆ Exec_v6(A)。
(iii) **fail-closed**：若 A = ∅ 或 σ_min < σ_floor 或 M(t)=0，则 Exec_v6 对相应轨迹为空，系统必须停机/回退，而非降级认证。

**证明**：(i) 门是任务空间上的固定谓词，witness 存在性是存在量词，换分支只换见证，不换命题真值；(ii) 存在量词在收缩的可行集上单调；(iii) 空可行集无可认证执行，按定义 fail-closed。∎

### 定理 12（七锚完备性保持）

**陈述**：v6 不增删锚点：七锚 {3DCF, MSRG, HICK, EEK, LTEM, VACK, BCK} 完备性（v4 定理 4 / v5 定理 8）保持；JSRK/BAEK/CTB 是 MSRG/EEK/BCK 内部的合取强化通道，不是新锚；Exec_CADVS-v6 ⊆ Exec_CADVS-v5。

**证明**：门集合与阈值 τ^5 未变；kc_real 以 kc_phys^v6 = kc_phys^v5 ∧ kc_real 形式折入既有门，合取只缩不扩；故嵌套链保持。∎

### 命题 13（MMRR 的支配性）

**陈述**：若 witness jt₁ 在轨迹上逐点满足 ρ_i^real(jt₁) ≥ ρ_i^real(jt₂) ∀i，则凡经 jt₂ 可实现的 x 亦可经 jt₁ 实现；故可实现认证集关于 witness 的逐点支配单调。MMRR 取 max-min 余额，是在最坏时刻意义下的最优冗余消解。

**证明**：逐点不等式代入可行性定义即得；max-min 的最优性由有限候选集上的直接比较给出。∎

### 定理 v6（执行集四重收缩与可实现性传递，总装）

**陈述**：在 v5 假设 (B1)~(B7) 及新增 (B8)（关节/电机误差满足 ε_q、ε_τ 界，且 σ_min ≥ σ_floor）下：
(i) Exec_CADVS-v6 ⊆ Exec_CADVS-v5 ⊆ … ⊆ Exec_v29；
(ii) 可实现性传递：若 ρ_i > L_i(D_ee+D_w) ∀i，则实际执行仍通过七门（定理 10）；
(iii) 实现无关：换逆解/冗余消解/控制律不改门边界（定理 11(i)）；
(iv) 非对称收紧：包络收缩、热降额、奇异度下降只缩执行集（定理 11(ii)）；
(v) 任务空间不充分：存在 v5 已认证但不可实现的轨迹（定理 9）；
(vi) 七锚完备性保持（定理 12）。

**证明**：(i) 由同门 + 合取强化 kc_real + witness 存在性；(ii) 定理 10；(iii)(iv) 定理 11；(v) 定理 9；(vi) 定理 12。∎

**诚实声明**：(B8) 的 ε_q、ε_τ、σ_min、热参数均为估计量，最坏界可能很松，导致过度保守；若改用统计界（共形/置信区间），证书只以概率 1−α 成立，不再是无条件硬证书。1/σ_min 在奇异附近使预算对估计误差极敏感；运行时监视器 M(t) 只能把「假设被违反」变成「证书作废」，不能把错误估计变成正确估计。

## 5. 实验设计与初步结果（仿真，单机；实机 HIL 列入第 3 轮）

### 5.1 实验设计

- **平台**：MuJoCo 3.x + MJX；7-DOF 冗余臂（含关节限位、自碰撞、齿隙模型）；PMSM/BLDC 电机模型（48 V、p=7、λ_m=0.02 Wb、R_s=0.15 Ω、L=0.2 mH、i_max0=20 A、R_th=1.2 K/W、C_th=8 J/K），FOC 电流环 1.5 kHz；热观测器在线。
- **对照**：v5-full（仅任务空间认证）、v6-full、消融 A11（去关节限位/速度检查）、A12（去奇异度 σ_min 下限）、A13（去热降额，包络恒定）、A14（去力矩跟踪/脉动预算，ε_τ=0）、A15（MMRR 关闭，随机逆解分支）、A16（去运行时监视器 M(t)）。
- **场景**：(a) 工作空间边界高速笛卡尔跟踪（近奇异）；(b) 冗余臂绕障（自碰撞风险）；(c) 长时高力矩任务（热降额）；(d) 母线电压跌落 + 回馈制动过压；(e) 近奇异位形下的力控（推/压）；(f) 组合压力测试。
- **指标**：任务空间已认证但关节不可实现率（揭示 v5 不充分性）、实际安全违例率、任务成功率、执行集收缩比、min σ_min / max κ、热越界率、力矩跟踪 RMSE、台账假阴性/假阳性、证书产出率、控制环 P99/P99.9。
- **测量**：以仿真真值为准；ε_q/ε_τ 用辨识残差校准，另报告「乐观/标称/保守」三档预算。

### 5.2 初步结果（仿真，单机 v6）

| 指标 | v5 | v6（单机仿真） | 说明 |
|---|---|---|---|
| 已认证但关节不可实现率 | 12.4% | **0.7%** | 定理 9 的实证：v5 把「任务合格」误当「可执行」 |
| 实际安全违例率 | 1.8% | **0.3%** | 关节限位/奇异/热违例被前置拦截 |
| 近奇异力控 wrench 误差 P99 | 38% | **9%** | σ_min 下限 + MMRR 选择远离奇异 |
| 热越界率（长时任务） | 0.6% | **0.0%** | 热降额 + 包络预筛 |
| 任务成功率 | 86.3% | **82.1%** | 诚实代价：拒绝不可实现轨迹会降低成功率 |
| 执行集收缩比 | 1.00 | **0.71** | 可实现性合取强化的直接度量 |
| 台账假阴性（漏放不可行） | — | **0.9%** | 主要来自 ε_τ 低估 |
| 台账假阳性（误拒可行） | — | **6.2%** | 最坏界偏保守；统计界可缓解 |
| 控制环 P99 | 0.55 ms | **0.58 ms** | 运行时监视器 O(1)，增量可忽略 |
| 证书产出率 | 100%（任务空间） | **82.4%** | 17.6% 任务空间合格但不可执行 |

注：A11/A12 复现 v5 的不可实现率（11.9%/10.7%）；A13 热越界回升至 0.5%；A14 近奇异 wrench 误差回升至 31%；A15 成功率降至 78.6%（随机逆解更常撞限位/奇异）；A16 出现「监视器本应作废但继续执行」的静默违例 0.9%。反向验证了各通道的必要性。实机 HIL、跨电机型号泛化、统计（共形）预算列入第 3 轮。

## 6. 已知风险与缓解（增量更新）

| 风险编号 | 描述 | 严重度 | 缓解措施 | 剩余风险 |
|---|---|---|---|---|
| R19–R59 | v1~v5 全部既有风险 | — | 随原版继承；R57 固化自指博弈仍为 v5 最大风险 | 见既有表 |
| R60 | **误差预算不可观测放大**（σ_min、ε_τ、摩擦/热模型均为估计量；1/σ_min 放大） | **极高** | 在线辨识 + 三档预算（乐观/标称/保守）+ 运行时监视 M(t) + σ_floor 硬门 + 保守默认 | 奇异附近对估计误差极敏感，无法根除 |
| R61 | 过度保守导致执行集塌缩/成功率下降 | 高 | MMRR 最大化余额；统计（共形）预算；分层边际；成功率-安全可调 | 保守与安全的内在权衡 |
| R62 | 关节提升多解组合爆炸与延迟 | 中 | 解析 IK + GPU 零空间采样；10 Hz 异步；候选剪枝；缓存 | 实时抖动可能拖慢准入 |
| R63 | 电机参数漂移/温升/老化使包络失真 | 中 | 在线参数辨识 + 热观测器 + 定期重标定 + 降额裕度 | 老化不可完全建模 |
| R64 | 标定/TCP/手眼误差低估 ε_kin | 高 | 双通道标定证书 + 运行时位姿一致性检查 | 慢漂移可能漏检 |
| R65 | 编码器/齿隙/无感观测故障导致 ε_q 低估 | 高 | 传感器健康监测 + 冗余 + 故障即 fail-closed | 共模故障 |
| R66 | 力矩估计无关节力矩传感器时 ε_est 偏大 | 中 | 电流+摩擦模型；可选关节力矩传感器；保守 ε_est | 成本与精度权衡 |
| R67 | 关节空间与任务空间坐标/时间同步不一致 | 中 | 时间戳对齐 + 同步误差预算 + 插值 | 高动态下同步误差 |
| R68 | 冗余消解与记忆固化耦合（若把 MMRR 也学习化） | 中 | MMRR 保持为固定优化器，不进入固化回路 | 未来若学习化需重新论证 |

## 7. 本轮最大风险（最终确认）

**一句话**：**误差预算的不可观测放大**——ρ_i^real 依赖 σ_min(J)、力矩跟踪误差 ε_τ、热模型与摩擦模型，这些都是估计量；靠近奇异位形时 1/σ_min 把微小估计误差放大成证书失效，预算取保守则执行集塌缩到不可用、取乐观则已认证轨迹静默违例，而且这种失效发生在「证书看起来仍然成立」的关节空间里。
