# IP-431–436 v22 新增承诺-时序层核心模块

| 编号 | 名称 | 类型 | 关键改进（相对 v21） |
|---|---|---|---|
| IP-431 | Recursive Feasibility Certificate (RFC) | 新增时序证书模块 | H 步递归可行 + 终端不变集 + 可安全停住集；证书悬崖提前预警；失效→低速/停 |
| IP-432 | Robust Tube Certificate (RTC) | 新增鲁棒收紧模块 | 把 CertBox/覆盖/意图/语音惊扰统一为扰动集；tube 约束收紧；包含率可证 |
| IP-433 | Prosody-Timed Commitment Synthesizer (PTCS) | 新增下行承诺模块 | 证书→有限模板话语的确定性编译；韵律编码紧迫度；时长/可懂度硬约束 |
| IP-434 | Say-Do Consistency Monitor (SDCM) | 新增一致性模块 | 执行 vs 承诺计划族的容差监视；偏差→重宣布/撤回/SafeStop；SDCC 可审计 |
| IP-435 | Commitment Negotiation Protocol (CNP) | 新增协商协议 | ANNOUNCED→ACKED?→COMMITTED→EXECUTING；静默≠同意；撤回只向更保守 |
| IP-436 | HPC++ & Explicit Certificate-MPC (EC-MPC) | 准入/实时升级 | HPC+ ∪ RFC ∪ SDCC 五证一体；10Hz 证书 + 50Hz O(1) 查询；超时→SafeStop |

## 0. 核心符号体系（定义 876–930）

| 符号 | 含义 |
|---|---|
| H, x_{0:H}, u_{0:H-1} | 预测时域、状态/输入轨迹 |
| X_k^cert | 由 v21 证书（CertBox/覆盖/规范域）膨胀得到的第 k 步约束集 |
| X_term | 终端不变集（终端控制器 κ_f 下正不变） |
| X_stop | 可安全停住集：存在制动轨迹在 d_min 外停住 |
| RFC_t = (π*, U_t, X_term, ρ_t) | 递归可行证书：计划、管、终端集、可行性裕度 |
| ρ_t | 可行性裕度（到约束边界的最近距离） |
| S_k | 鲁棒正不变管（tube）在第 k 步的截面 |
| W_k = W_det ⊕ W_cov ⊕ W_int ⊕ W_ann | 扰动集：检测/覆盖/意图/语音惊扰 |
| W_ann | 语音诱发扰动（惊扰位移/抢行/后退的标定上界） |
| τ_human | 人从听到承诺到开始反应的最小时间（默认 0.8s，可人群标定） |
| TTC_commit | 到承诺点的时间（承诺点后不再允许静默改模式） |
| τ_retract | 撤回截止：此后只允许 SafeStop |
| τ_warn | 证书悬崖预警提前量 |
| u_t = (txt, prosody, dur, chan) | 承诺话语：文本、韵律、时长、通道 |
| G | 有限承诺模板文法（模式 × 方向 × 紧迫度） |
| dur(u), I(u, noise) | 话语时长、噪声下可懂度 |
| CommCert = (mode, I, dur, chan, hash) | 通信证书：可懂度/时长/通道可审计 |
| Π_ann, Π_exec | 承诺计划族、实际执行计划族（Π_exec ⊆ Π_ann） |
| commit_state | IDLE/ANNOUNCED/ACKED/COMMITTED/EXECUTING/RETRACTED/SAFESTOP |
| SDCC = (announced, executed_prefix, deviations, retractions, hashes) | 说做一致证书 |
| HPC++ = (HPC+, RFC, SDCC) | 五证一体：几何+规范+负信息+时序+说做 |
| Exec_v22 = Exec_v21 ∩ Fil_rfc ∩ Fil_sdcc | v22 可执行计划集合 |

## 1. 关键算法骨架

```python
# IP-431 Recursive Feasibility Certificate
@dataclass
class RFC:
    plan: list
    tube: object
    terminal_set: object
    rho: float
    feasible: bool = True

class RecursiveFeasibilityCertifier:
    def __init__(self, dynamics, horizon=12, margin_warn=0.5):
        self.f = dynamics
        self.H = horizon
        self.margin_warn = margin_warn

    def solve(self, x0, constraint_sets, u_set, terminal_set, stop_set):
        """constraint_sets: [X_0^cert ... X_{H-1}^cert] from v21 HPC+/DCL
           terminal_set ⊆ stop_set; returns RFC or failure reason."""
        # 1. 标准 MPC：滚动时域可行 + 终端不变
        plan = mpc_solve(self.f, x0, constraint_sets, u_set, terminal_set)
        if plan is None:
            return None, "NO_HORIZON_FEASIBLE"
        # 2. 终端集必须落在可安全停住集内（防证书悬崖）
        if not subset(terminal_set, stop_set):
            return None, "TERMINAL_NOT_STOPPABLE"
        # 3. 可行性裕度：到最近约束边界的距离，用于悬崖预警
        rho = min_distance_to_boundary(plan, constraint_sets)
        if rho < self.margin_warn:
            return RFC(plan, None, terminal_set, rho), "CLIFF_WARNING"
        return RFC(plan, None, terminal_set, rho), "OK"

    def shift(self, rfc, constraint_sets_next):
        """移位计划 (u_1..u_{H-1}, κ_f(x_H))；检查递归可行性保持"""
        shifted = rfc.plan[1:] + [terminal_controller(rfc.plan[-1].x_next)]
        ok = all(shifted[k].state in constraint_sets_next[k]
                 for k in range(len(shifted)))
        return shifted, ok


# IP-432 Robust Tube Certificate
class RobustTubeCertifier:
    def __init__(self, dynamics, w_det, w_cov, w_int, w_ann):
        self.f = dynamics
        self.W = w_det + w_cov + w_int + w_ann   # 集合 Minkowski 和

    def tube(self, s0, H):
        """S_{k+1} = A S_k ⊕ W_k（线性）；非线性用可达集过近似"""
        S = [s0]
        for k in range(H):
            S.append(propagate(self.f, S[-1]) + self.W)
        return S

    def tighten(self, constraint_sets, S):
        """z_k ∈ X_k^cert ⊖ S_k；收紧后为空则不可行（不是放宽）"""
        tightened = [erode(X, S[k]) for k, X in enumerate(constraint_sets)]
        return tightened

    def robust_solve(self, x0, constraint_sets, u_set, terminal_set, stop_set):
        S = self.tube(initial_tube(x0), len(constraint_sets))
        tight = self.tighten(constraint_sets, S)
        if any(is_empty(X) for X in tight):
            return None, "TUBE_EMPTY"
        rfc, why = RecursiveFeasibilityCertifier(self.f).solve(
            x0, tight, u_set, terminal_set, stop_set)
        if rfc is not None:
            rfc.tube = S
        return rfc, why


# IP-433 Prosody-Timed Commitment Synthesizer
class ProsodyTimedCommitmentSynthesizer:
    def __init__(self, grammar, tts_cache, intelligibility_model,
                 tau_human=0.8, beta=0.05, startle_cap=0.2):
        self.G = grammar                 # 有限模板：mode × direction × urgency
        self.tts = tts_cache             # 预合成缓存：在线 O(1)
        self.I = intelligibility_model   # (u, noise) -> P(正确识别)
        self.tau_human = tau_human
        self.beta = beta
        self.startle_cap = startle_cap

    def compile(self, cert, plan_family, ttc_commit, noise):
        """确定性编译：语义 = 计划族模式；不自由生成"""
        mode = mode_of(plan_family)
        urgency = urgency_of(ttc_commit)          # 低/中/高
        cands = sorted(self.G[mode][urgency], key=lambda t: t.duration)
        for tmpl in cands:
            u = self.tts.render(tmpl, prosody=prosody_of(urgency, cert.direction))
            if not sem_matches(u, plan_family):
                continue                          # 语义错位：拒绝
            if u.dur + self.tau_human > ttc_commit:
                continue                          # 时长预算：拒绝
            if self.I(u, noise) < 1 - self.beta:
                continue                          # 可懂度：拒绝
            if startle_risk(u) > self.startle_cap:
                continue                          # 惊扰：拒绝
            return u, CommCert(mode, self.I(u, noise), u.dur, u.chan,
                               hash(u))
        # 无可用话语：不是"喊更久"，而是收缩计划
        return None, "NO_UTTERANCE_WITHIN_BUDGET"

    def fallback_channel(self, mode, noise):
        """噪声/听障：切视觉/灯光/振动；仍不满足则减速/停"""
        return visual_or_haptic(mode)


# IP-434 Say-Do Consistency Monitor
class SayDoConsistencyMonitor:
    def __init__(self, tolerance, t_retract):
        self.tol = tolerance
        self.t_retract = t_retract
        self.log = []

    def check(self, executed, announced_family, t):
        """执行是否仍在承诺计划族容差内"""
        if in_family(executed, announced_family, self.tol):
            return "OK"
        self.log.append(("deviation", t, executed.hash))
        if t < self.t_retract:
            return "REANNOUNCE_OR_RETRACT"      # 可向更保守撤回
        return "SAFESTOP"                        # 过截止：只许停

    def issue_sdcc(self, announced, executed_prefix, deviations, retractions):
        return SDCC(announced, executed_prefix, deviations, retractions,
                    merkle(self.log))


# IP-435 Commitment Negotiation Protocol
class CommitmentNegotiationProtocol:
    def __init__(self, ttl_ack=0.5, max_reannounce=2):
        self.state = "IDLE"
        self.ttl_ack = ttl_ack
        self.max_reannounce = max_reannounce
        self.reannounce_count = 0

    def step(self, event, t, ttc_commit):
        if self.state == "IDLE" and event.kind == "PLAN_READY":
            if event.utterance.dur + event.tau_human > ttc_commit:
                return "SLOW_OR_STOP"            # 预算不足：先降速
            self.state = "ANNOUNCED"
            return "SPEAK"
        if self.state == "ANNOUNCED" and event.kind == "ACK":
            self.state = "ACKED"
            return "COMMIT"                      # ack 提高效率，不解锁几何
        if self.state in ("ANNOUNCED", "ACKED") and t >= ttc_commit:
            # 静默≠同意：无 ack 也可按最保守承诺执行，但不得越权
            self.state = "COMMITTED"
            return "COMMIT_CONSERVATIVE"
        if event.kind == "DEVIATION" and t < event.t_retract:
            if self.reannounce_count < self.max_reannounce:
                self.reannounce_count += 1
                self.state = "ANNOUNCED"
                return "REANNOUNCE"              # 只向更保守计划
            return "RETRACT_TO_CONSERVATIVE"
        if event.kind == "DEVIATION" and t >= event.t_retract:
            self.state = "SAFESTOP"
            return "SAFESTOP"
        return "HOLD"


# IP-436 HPC++ 准入 + 显式证书 MPC
@dataclass
class HPCPlusPlus:
    hpc_plus: HPCPlus          # v21：HPC + CC + AbsCert
    rfc: RFC                   # 时序可续期
    sdcc: SDCC                 # 说做一致

    def admits(self, theta_dom):
        return (self.hpc_plus.admits(theta_dom)
                and self.rfc is not None
                and self.rfc.feasible
                and self.rfc.rho >= 0.0
                and self.sdcc.consistent)

class ExplicitCertificateMPC:
    """10Hz 证书更新 + 50Hz O(1) 查询；网格未命中回退 QP，超时→SafeStop"""
    def __init__(self, grid, qp_solver, deadline_ms=8.0):
        self.grid = grid
        self.qp = qp_solver
        self.deadline = deadline_ms

    def update_certificate(self, hpc_plus, rfc, sdcc):
        self.cert_key = discretize(hpc_plus, rfc, sdcc)

    def control(self, x):
        u = self.grid.lookup(self.cert_key, x)
        if u is not None:
            return u, "GRID"
        u = self.qp.solve_with_deadline(self.cert_key, x, self.deadline)
        if u is None:
            return safe_stop(x), "SAFESTOP"
        return u, "QP_FALLBACK"
```

## 2. 符号体系增量（定义 876–930）

| 编号段 | 新增符号（本轮） | 继承符号（v21，保持不变） |
|---|---|---|
| 876–885 | H, X_k^cert, X_term, X_stop, RFC_t, ρ_t | D_t, CertBox_k, ε_loc(s), Prior_c |
| 886–895 | S_k, W_k, W_det/W_cov/W_int/W_ann, τ_human | Obs_t, Cov_t, AbsCert, κ_c, δ_abs |
| 896–905 | TTC_commit, τ_retract, τ_warn, u_t, G, dur, I, CommCert | R, Θ_F/Θ_O/Θ_P, YieldSet, τ_rule |
| 906–915 | Π_ann, Π_exec, commit_state, SDCC, HPC++ | σ_dcl, SafeStop, CC(n), proofs |
| 916–925 | Exec_v22, Fil_rfc, Fil_sdcc, EC-MPC 网格键 | g_t, î, q, Γ(q), q_low/q_high, TTL_intent |
| 926–930 | 承诺链 merkle 锚、重宣布预算 | Mod(v), Quorum+, HPC+, ζ_sem, Exec_v21 |

## 3. 推导

**引理 163（RFC 的递归可行性）**
设 `X_term` 在终端控制器 `κ_f` 下正不变（`κ_f(x) ∈ U` 且 `f(x,κ_f(x)) ∈ X_term`，∀x∈X_term），且 t 时刻存在满足约束的 H 步计划 `π_t`。若 t+1 时刻约束满足 `X_k^cert(t+1) ⊇ X_{k+1}^cert(t)`（约束收紧不快于计划移位），则移位计划 `(u_1,...,u_{H-1}, κ_f(x_H))` 在 t+1 时刻可行；归纳得 ∀t 存在可行计划。若该包含不成立（人或覆盖突变），则由 RTC 的管吸收或触发撤回/SafeStop，而不是假定归纳继续。∎

**引理 164（鲁棒管的约束收紧）**
若名义计划 `z_{0:H}` 满足 `z_k ∈ X_k^cert ⊖ S_k`，实际状态 `x_0 ∈ z_0 ⊕ S_0`，扰动 `w_k ∈ W_k`，且 `S_{k+1}=A S_k ⊕ W_k`（线性；非线性用可达集过近似），则 `x_k ∈ z_k ⊕ S_k ⊆ X_k^cert`，∀k。故 CertBox 定位误差、覆盖/意图不确定性、语音惊扰 `W_ann` 均被 `S_k` 吸收；若收紧后可行域非空，则鲁棒可行，否则 `TUBE_EMPTY` → 不执行。∎

**引理 165（承诺时长预算）**
若 `dur(u_t) + τ_human ≤ TTC_commit` 且 `I(u_t, noise) ≥ 1-β`，则人在承诺点前至少拥有 `τ_human` 的反应时间，且以 ≥1-β 正确理解承诺模式。若不存在满足该式的 `u_t ∈ G`，则计划必须收缩（减速/等待）或 SafeStop；故承诺不会在"人还没听清"时生效。∎

**引理 166（说做一致性）**
若执行轨迹 `ξ` 始终落在承诺计划族 `Π_ann` 的容差内，且 SDCM 在偏差超出容差时于 `τ_retract` 前触发重宣布/撤回，则不存在"未宣布的模式切换"被执行；人基于承诺的预测与实际执行在容差内一致。监视器失效时按 P39 冻结最保守前缀或 SafeStop，故一致性不被静默破坏。∎

**引理 167（撤回的安全性）**
撤回仅在 `τ_retract` 前允许，且撤回目标 `Π_retract ⊆ Π_ann ∩ Exec_v21`（更保守）；`τ_retract` 后只允许 SafeStop。故撤回不会扩大可执行集，也不会产生"先承诺 A 后偷偷执行 B"的语义缺口；重宣布预算耗尽时强制保守模式，避免"狼来了"。∎

**引理 168（v22 整体安全继承）**
RFC 只对计划集做过滤（存在性 + 终端集），RTC 只收紧约束，PTCS 只添加时长/可懂度/惊扰约束，SDCM/CNP 只添加一致性义务与撤回限制，语音输出不改变几何可执行集。故 `Exec_v22 = Exec_v21 ∩ Fil_rfc ∩ Fil_sdcc ⊆ Exec_v21 ⊆ Exec_v20 ⊆ Exec_v19 ⊆ Exec_v18`。∎

## 4. 复杂度分析

| 组件 | 域 | 时间 | 空间 | 正确性锚 |
|---|---|---|---|---|
| RFC 滚动求解 | H≤12 | O(QP(H))，热启动 ≤3ms | O(H·n) | 引理 163 |
| RFC 移位检查 | H | O(H) | O(H) | 引理 163 |
| RTC 管传播 | H | O(H·reach) | O(H·n) | 引理 164 |
| RTC 约束收紧 | H | O(H·grid) | O(grid) | 引理 164 |
| PTCS 编译 | \|G\|≤48 | O(\|G\|) 查缓存 | O(\|G\|) | 引理 165 |
| PTCS 可懂度查询 | 1 | O(1) 查表 | O(calib) | 引理 165 |
| SDCM 一致性 | 1 | O(1) | O(log) | 引理 166 |
| CNP 状态机 | 1 | O(1) | O(1) | 引理 167 |
| HPC++ 组装 | 1 | O(1)（引用五证） | O(1) | 引理 168 |
| EC-MPC 网格查询 | 1 | O(1) | O(grid) | 引理 168 |
| EC-MPC QP 回退 | H | ≤8ms 截止，超时停 | O(H·n) | 引理 163/168 |
| 50Hz 控制路径 | 在线 | ≤12ms（与 v21 不变） | — | 引理 168 |

## 5. 实验设计 E801–E830

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E801 | RFC 递归可行性（静态） | 10^4 随机初态，零不可行后继 |
| E802 | RFC 移动行人 | 有界速度下递归可行保持 ≥99.9% |
| E803 | 证书悬崖预警 | 提前 ≥0.5s 检出，漏报 ≤1% |
| E804 | X_stop 可达性 | 制动距离误差 ≤5%，零越界 |
| E805 | RTC 保守性 | tube 体积/活性损失 ≤8% |
| E806 | RTC 扰动包含 | 注入检测/覆盖/意图扰动，包含率 ≥99% |
| E807 | W_ann 标定 | 惊扰位移 95 分位上界，覆盖 ≥99% |
| E808 | 承诺时长预算 | dur+τ_human≤TTC，违例=0 |
| E809 | 噪声可懂度 | 75 dBA 下模式识别 ≥95% |
| E810 | 多语言/口音 | 可懂度 ≥90% |
| E811 | 听障/视觉回退 | 视觉通道识别 ≥95% |
| E812 | 证书→语音语义 | 1000 模板零语义错位 |
| E813 | TTS 幻觉对照 | 自由生成对照，拦截 100% |
| E814 | 说做偏差检测 | 注入漂移，检出 ≤100ms |
| E815 | 重宣布预算 | ≤2 次/事件，信任评分不降 |
| E816 | 撤回时序 | τ_retract 前成功 ≥99%，之后零撤回 |
| E817 | 静默≠同意 | 无 ack 不获新许可，零违例 |
| E818 | 语音 STOP | ≤150ms 进入最严 |
| E819 | 伪造 ack | 不可解锁，拦截 100% |
| E820 | EC-MPC 实时 | 50Hz p99 ≤12ms |
| E821 | 网格命中/回退 | 命中 ≥95%，超时→停零违例 |
| E822 | 端到端交接 | 语音承诺下成功 ≥90%，零违例 |
| E823 | 人流混行 | 3 机器人 2 行人，让位 ≥95%，零死锁 |
| E824 | 消融：无 RFC | 悬崖场景失败率显著↑（=v21） |
| E825 | 消融：无 RTC | 扰动下违例↑ |
| E826 | 消融：无 PTCS | 人理解率↓，协调时间↑≥30% |
| E827 | 消融：无 SDCM | 未宣布模式切换↑ |
| E828 | 消融：无 CNP | 撤回混乱/信任↓ |
| E829 | 隐私/审计 | 原始音频零出域，承诺链复放 100% |
| E830 | 全栈竞赛 | 共享搬运 ≤1.8s，违例=0 |

## 6. 预注册判据

| 判据 | 门槛（预注册） | 若未达标的处置 |
|---|---|---|
| E801 | 零不可行后继 | 加终端集保守度、缩短 H |
| E802 | ≥99.9% | 降低人速上界、加密重规划 |
| E803 | 漏报 ≤1% | 提高 ρ 预警阈值、加可达集过近似 |
| E804 | 误差 ≤5% | 标定制动模型、增大 d_min |
| E805 | 活性损失 ≤8% | 调 W_ann/管保守度、分层收紧 |
| E806 | 包含率 ≥99% | 增大扰动集、加最坏情形项 |
| E807 | 覆盖 ≥99% | 扩大标定人群、在线自适应 |
| E808 | 违例=0 | 缩短模板、减速、换通道 |
| E809 | ≥95% | 提高音量/换通道、加视觉 |
| E810 | ≥90% | 多语言模板扩充、母语者校准 |
| E811 | ≥95% | 视觉/振动通道调优 |
| E812 | 零错位 | 收紧模板文法、加语义验证 |
| E813 | 拦截 100% | 禁用自由生成、强制证书编译 |
| E814 | ≤100ms | 提高监视频率、事件化 |
| E815 | ≤2 次/事件 | 提高重宣布门槛、加滞回 |
| E816 | ≥99% 零越界 | 调 τ_retract、加预撤回 |
| E817 | 零违例 | 协议层强制、审计告警 |
| E818 | ≤150ms | 语音 STOP 优先通道、蒸馏 |
| E819 | 拦截 100% | 挑战-响应、多因子佐证 |
| E820 | p99 ≤12ms | 网格加密、预算重分配 |
| E821 | ≥95% 零违例 | 网格覆盖优化、热启动 |
| E822 | ≥90% 零违例 | 承诺/接近速度联合调优 |
| E823 | ≥95% 零死锁 | 义务调度、区域分区 |
| E824–828 | 各消融显著退化 | 证明各模块必要性 |
| E829 | 零出域/100% | 数据流审计、哈希规范化 |
| E830 | ≤1.8s 违例=0 | 端到端联合调优 |

## 7. 已知风险与失效模式

1. **施行式语音 / 惊扰与语义反应**（最大风险，见第 8 节）：喊话会改变人的行为，`W_ann` 只能标定几何位移，标定不了"误解后抢行/后退/僵住"。缓解：保守 `W_ann` + 在线监控 + 一旦人反应超出管立即 SafeStop；限制音量/韵律；优先短句。
2. **递归可行性的时变约束假设被违反**：人速超界、遮挡突变、覆盖图瞬变使 `X_k^cert(t+1) ⊉ X_{k+1}^cert(t)`。缓解：RTC 管吸收 + 悬崖预警 + 撤回/SafeStop（E802/E803）。
3. **tube 保守性导致活性坍缩**：W 叠加 + v21 保守 + 义务过滤，人流密集区可能趋停。缓解：分层收紧、只在必要方向收紧、用 AbsCert 赎回、E805 监控 ≤8%。
4. **语音不可懂 / 听障 / 多语言 / 噪声**：承诺形式成立而人未接收。缓解：可懂度下界 + 视觉/振动回退 + 多语言模板 + E809–E811；仍不满足则减速/停。
5. **说做监视器漏检/延迟**：偏差未被发现，承诺与执行脱节。缓解：事件化高频监视 + 容差收紧 + 失效冻结最保守前缀（E814/E827）。
6. **重宣布/撤回引发信任崩塌（狼来了）**：频繁改口使人忽略承诺。缓解：重宣布预算 + 滞回 + 只向更保守撤回 + E815。
7. **隐私与声纹**：语音交互涉及录音与说话人识别。缓解：原始音频零出域、只传 CommCert/SDCC、处理最小化（E829）。
8. **实时预算**：RFC+tube+TTS 侵入 12ms。缓解：10Hz 证书更新、50Hz O(1) 查询、预合成缓存、超时 SafeStop（E820/E821）。
9. **模板/规则过时**：新场景/新语言/新规范下模板语义漂移。缓解：模板文法版本化 + merkle 审计 + 语义验证（E812/E829）。

## 8. 本轮最大风险

**一句话**：本方案把"说出口"当作可审计的承诺，但承诺是施行式的——语音会改变人的行为（惊扰、后退、抢行、误解），而 RFC 的鲁棒管只界定几何与标定扰动，界定不了语义反应；机器人可能"递归可行地"撞上一个因它自己喊话而走进路径的人——**"合规的自我实现事故"**。
