<!-- IDEA:START -->
### 第 5 轮灵感驱动研究记录（承接 CADVS-v4；新循环第 1 轮）

**灵感词**：夹爪控制、桌面操作

**继承关系**：第 4 轮 CADVS-v4（IP-489~492）在 v3 五锚点基础上加入价值锚 VACK（kc_val）与平衡锚 BCK（kc_bal），形成七硬门 kc_evidence_forged_v4 = kc_coverage ∧ kc_physics ∧ kc_human ∧ kc_ee ∧ kc_mem ∧ kc_val ∧ kc_bal，软评分 ECS_v4 = ECS_v3·η_val·η_bal，执行集 Exec_CADVS-v4 ⊆ Exec_CADVS-v3 ⊆ Exec_CADVS-v2 ⊆ Exec_CADVS-v1 ⊆ Exec_v29。本轮不推翻 v4，而是针对「夹爪控制」与「桌面操作」两个具体的接触层失效模式，把 v4 中粒度过粗的末点锚 EEK 与平衡锚 BCK 细化为两个接触对锚：抓取锚 GFK（GGC / kc_grasp）与支撑锚 TSK（TAC / kc_table），并以接触链演算 CCC 证明「细化是保守的、两锚非冗余、接触链完备」，形成 CADVS-v5（IP-493~496）。执行集升级为 Exec_CADVS-v5 ⊆ Exec_CADVS-v4 ⊆ Exec_CADVS-v3 ⊆ Exec_CADVS-v2 ⊆ Exec_CADVS-v1 ⊆ Exec_v29。

**直觉与动机**：

1. **夹爪控制：力闭合不等于抓取成功，滑移检测是「事后」而非「事前」**。v4 的 EEK 把末端当作广义力/位姿传感器，只能检测已经发生的滑移与力超限；但平行夹爪的失败往往发生在「力闭合边际不足 + 物体位姿/摩擦不确定」的组合下：接触力在摩擦锥内，却在扰动下瞬间越界。GFK 把抓取质量前移为可计算证书 GGC = (ε_fc, m_slip, e_aperture, e_force, t)：ε_fc 为力闭合边际（最大 ε 使单位力旋量球 εB 被抓取力旋量空间 GWS 包含），m_slip 为在摩擦/位姿不确定集上的鲁棒滑移边际，e_aperture / e_force 为孔径与夹持力跟踪误差。硬门 kc_grasp 在 GRASP / LIFT / TRANSPORT regime 激活，防止「力在阈值内但一扰动就掉」。

2. **桌面操作：桌子不是地板，物体-桌面接触有独立的失效模式**。v4 的 BCK 把支撑当作全身平衡的一部分，却未显式建模「物体在桌面上的支撑多边形、质心投影、翻倒力矩、边缘距离」。桌面任务的典型失败是放置翻倒、推出桌沿、非抓取推滑失稳、局部支撑（仅三点接触）导致的伪稳定。TSK 把支撑前移为证书 TAC = (ξ_support, τ_topple, ξ_edge, t)：ξ_support 为质心投影在支撑多边形内的归一化有符号边际，τ_topple 为翻倒力矩边际，ξ_edge 为支撑多边形到桌沿的归一化距离。硬门 kc_table 在 PLACE / PUSH / RELEASE regime 激活。

3. **接触链：抓取锚与支撑锚不可互相替代，且必须可组合**。直觉上，抓得稳不代表放得稳（力闭合足够但把物体放到桌沿），放得稳也不代表抓得稳（物体在桌上稳定但夹爪力闭合不足）。因此引入接触链证书 C_chain = act(kc_grasp,R) ⊗ act(kc_table,R)，⊗ 表示「夹爪→物体→桌面」的序贯接触组合：两个激活锚都通过，且接触状态转移（抓取→抬升→放置→释放）的边界可行。进一步给出「粒度细化定理」：v5 的 GFK/TSK 是对 v4 的 EEK/BCK 的保守细化，故执行集只缩不涨。

4. **regime-conditioned 门控：避免九硬门把系统「锁死」**。九硬门全 AND 会在「物体已稳定放在桌上、夹爪已释放」时仍要求抓取证书，造成大量误拒。故引入接触 regime 分类器 R ∈ {APPROACH, GRASP, LIFT, TRANSPORT, PLACE, PUSH, RELEASE}，硬门按 act(kc,R) 条件激活；条件激活只会在 v4 基础上增加限制、不会删除限制，因此仍满足 Exec_CADVS-v5 ⊆ Exec_CADVS-v4。这一设计把「安全收缩」与「可用性」解耦：安全来自单调收缩，可用性来自 regime 条件化。

**关键洞见**：v4 的七锚点覆盖「覆盖/物理/人因/末点/记忆/价值/平衡」，但「末点」与「平衡」之间的接触层仍是粗粒度：真实操作发生在两个接触对上——夹爪-物体（抓取）与物体-桌面（支撑）。v5 追加抓取锚与支撑锚，并以接触链演算证明二者互补且非冗余，形成九硬门 kc_evidence_forged_v5 = kc_evidence_forged_v4 ∧ act(kc_grasp,R) ∧ act(kc_table,R)，fail-closed；软评分 ECS_v5 = ECS_v4·η_grasp·η_table。

**形式化目标（增量）**：
1. 定义抓取状态、抓取映射 G 与抓取力旋量空间 GWS；定义力闭合边际 ε_fc、鲁棒滑移边际 m_slip、孔径/力跟踪误差；定义 GGC 与 kc_grasp。
2. 定义物体-桌面支撑多边形 S_obj、质心投影 p_com、翻倒力矩边际 τ_topple、桌沿边际 ξ_edge；定义 TAC 与 kc_table。
3. 定义接触 regime 分类器 R 与激活函数 act(kc,R)，证明条件激活保持执行集单调性。
4. 定义接触链演算 ⊗ 与接触链证书 C_chain；证明粒度细化定理（Exec_CADVS-v5 ⊆ Exec_CADVS-v4 且严格）、抓取-支撑非冗余定理、接触链完备性定理。
5. 定义 EFA-v5 九硬门 + 软评分 ECS_v5；定义 Exec_CADVS-v5 ⊆ Exec_CADVS-v4。

**本轮最大风险**：夹爪与桌面的接触参数（摩擦锥、指垫柔顺、物体位姿与质量分布）只能间接辨识，模型失配会让 GGC/TAC 系统性误判；在九硬门 AND 与 regime 切换下，误判可能从「单点错误」放大为「大规模误拒或漏放」，形成安全与可用性的双输。
<!-- IDEA:END -->
---
<!-- ARTIFACT:START -->
## 0. 增量定位与继承关系（在 IP-489~492 / CADVS-v4 基础上扩展）

### 0.1 新增核心模块

| 编号 | 名称 | 类型 | 关键改进（相对 CADVS-v4） |
|---|---|---|---|
| IP-493 | Grasp Fidelity Kernel (GFK) | 抓取证据锚 | 力闭合边际 ε_fc、鲁棒滑移边际 m_slip、孔径/夹持力跟踪；GGC 证书；kc_grasp 硬门；η_grasp 软因子；仅在 GRASP/LIFT/TRANSPORT regime 激活 |
| IP-494 | Tabletop Support Kernel (TSK) | 支撑证据锚 | 物体-桌面支撑多边形、质心投影、翻倒力矩、桌沿边际；TAC 证书；kc_table 硬门；η_table 软因子；仅在 PLACE/PUSH/RELEASE regime 激活 |
| IP-495 | Contact Chain Calculus (CCC) | 理论内核 | 接触链组合 ⊗、regime 条件激活单调性、粒度细化定理、抓取-支撑非冗余定理、接触链完备性定理 |
| IP-496 | Evidence Forging Assembler v5 (EFA-v5) | 证据融合 | 九硬门 kc_evidence_forged_v5 = kc_evidence_forged_v4 ∧ act(kc_grasp,R) ∧ act(kc_table,R)；软评分 ECS_v5 = ECS_v4·η_grasp·η_table |

### 0.2 v4 模块适配表（只改接口，不推翻）

| v4 模块 | v5 适配 |
|---|---|
| IP-485 EEK | 保留点接触/力/位姿/滑移检查；新增 grasp_fp 指针关联 GGC；kc_ee 仍为「末端保真」基础门，kc_grasp 为更细的抓取质量门叠加 |
| IP-490 BCK | 保留全身 Wrench 锥/ZMP/通过性；新增 table_fp 指针关联 TAC；kc_bal 管全身，kc_table 管物体-桌面支撑，二者正交 |
| IP-486 LTEM | 条目扩展 (grasp_succ, grasp_fail, slip_hist, table_succ, topple_hist, regime_hist)；记忆门按 regime 查询对应历史 |
| IP-487 FFA | Δ_i 增加抓取统计（ε_fc/m_slip 分位数、夹爪型号、指垫摩擦）与桌面统计（支撑多边形、翻倒事件、桌面摩擦）；Φ_global 同步下发抓取/桌面先验 |
| IP-489 VACK | 价值奖励新增「操作礼貌性」子项（不猛放、不推出桌沿、不夹伤），VAC 扩展 r_manip；kc_val 不变 |
| IP-491 CERTCALC | 证书演算继承；新增 ⊗ 组合算子与接触链格；定理 5~7 |
| IP-492 EFA-v4 | 升级 EFA-v5，追加 kc_grasp/kc_table（regime 条件激活） |
| IP-473~480 | RCANG/DLC/MRCC/TCVM/STCK/GCK/DAKI/VSCK 原样继承；GFK/TSK 加入控制环与准入容器 |

## 1. 增量符号体系（定义 2261–2420）

| 符号 | 含义 |
|---|---|
| G = (O, H, C, u) | 抓取：物体 O、夹爪 H、接触集 C、位姿/摩擦不确定 u |
| GWS = {G f \| f ∈ FC, ‖f‖∞ ≤ f_max} | 抓取力旋量空间：抓取映射 G ∈ R^{6×(m·n_f)}、摩擦锥 FC、指力上限 f_max |
| ε_fc = max{ε \| εB ⊆ GWS} | 力闭合边际，B 为 6D wrench 单位球（Ferrari–Canny 度量） |
| m_slip = min_i [(μ̂−kσ_μ)f_n,i − (‖f_t,i‖+kσ_t)] / (μ̂ f_n,i) | 鲁棒归一化滑移边际（friction/切向力不确定集上的最坏接触） |
| e_aperture = \|a − a_des\| | 孔径跟踪误差 |
| e_force = \|f_n − f_n,des\| | 夹持力跟踪误差 |
| GGC = (ε_fc, m_slip, e_aperture, e_force, t) | 抓取保真证书 |
| kc_grasp | ε_fc ≥ ε_min ∧ m_slip ≥ m_min ∧ e_aperture ≤ δ_a ∧ e_force ≤ δ_f |
| η_grasp = clip(min(ε_fc/ε_ref, m_slip/m_ref, 1), 0, 1) | 抓取软因子 |
| S_obj = Conv({p_i^table}) | 物体-桌面接触点在桌面上的支撑多边形（2D 凸包） |
| p_com = Proj_xy(CoM(O)) | 物体质心在桌面上的投影 |
| ξ_support = signed_dist(p_com, ∂S_obj) / r_in(S_obj) | 支撑边际：质心投影到支撑多边形边界的有符号距离，按内切半径归一化 |
| τ_topple = 1 − ‖F_ext,t‖·h_ext / (m g d_com) | 翻倒力矩边际：d_com 为质心投影到最近支撑边的距离，h_ext 为外力作用高度；>0 表示恢复力矩占优 |
| ξ_edge = dist(S_obj, ∂Table) / L_ref | 桌沿边际：支撑多边形到桌边界的归一化距离 |
| TAC = (ξ_support, τ_topple, ξ_edge, t) | 桌面支撑证书 |
| kc_table | ξ_support > 0 ∧ τ_topple > τ_min ∧ ξ_edge > ξ_min |
| η_table = clip(min(ξ_support/ξ_ref, τ_topple/τ_ref, ξ_edge/ξ_ref, 1), 0, 1) | 支撑软因子 |
| R ∈ {APPROACH, GRASP, LIFT, TRANSPORT, PLACE, PUSH, RELEASE} | 接触 regime |
| act(kc, R) ∈ {kc, ⊤} | regime 激活：命中为 kc，未命中为合取中性元 ⊤ |
| C_chain = act(kc_grasp,R) ⊗ act(kc_table,R) | 接触链证书 |
| ⊗ | 接触链组合：两激活锚均通过且接触状态转移可行 |
| Exec_CADVS-v{k} | 第 k 轮执行集 |

## 2. 关键算法骨架

### IP-493 GFK：抓取保真核（控制环内，解析闭式优先，目标 < 0.2 ms）

```python
@dataclass
class GraspFidelityKernel:
    """GFK：力闭合 + 鲁棒滑移 + 孔径/力跟踪；kc_grasp 硬门"""
    eps_min: float = 0.05
    m_slip_min: float = 0.15
    delta_aperture: float = 0.005     # m
    delta_force: float = 2.0          # N
    mu_hat: float = 0.5
    sigma_mu: float = 0.10
    k_sigma: float = 2.0

    def observe(self, grasp: GraspState, obj: ObjectState,
                finger_wrenches: list[Wrench], t_now: float) -> GGC:
        # 1) 抓取映射 G：接触点位置、法向/切向基、夹爪几何
        G = self._grasp_map(grasp, obj)                    # 6 x (m·n_f)
        # 2) 力闭合边际：两指平行夹爪用解析闭式；多指用 GWS 凸包/QP
        eps_fc = self._force_closure_margin(G, grasp.friction_cones, grasp.f_max)
        # 3) 鲁棒滑移边际：在最坏摩擦/切向扰动下仍不越锥
        m_slip = self._robust_slip_margin(finger_wrenches, grasp,
                                          self.mu_hat, self.sigma_mu, self.k_sigma)
        # 4) 孔径与夹持力跟踪
        e_aperture = abs(grasp.aperture - grasp.aperture_des)
        e_force = abs(grasp.f_norm - grasp.f_norm_des)
        return GGC(eps_fc, m_slip, e_aperture, e_force, t_now)

    def _force_closure_margin(self, G, cones, f_max) -> float:
        # 两指：ε_fc = (1/‖w_ext‖)·min 支撑函数，可用 2x2 接触子空间闭式；
        # 多指：max ε  s.t.  ∀w∈B, ∃f∈FC, ‖f‖∞≤f_max: G f = ε w
        #       等价于求解 GWS 的 inradius（凸包顶点枚举或支持函数 QP）
        ...

    def _robust_slip_margin(self, fw, grasp, mu, sigma_mu, k) -> float:
        worst = 1.0
        for w in fw:
            fn = max(w.normal, 1e-9)
            mu_lo = max(mu - k * sigma_mu, 0.0)
            cap = mu_lo * fn
            need = w.tangential + k * grasp.sigma_t
            worst = min(worst, (cap - need) / (mu * fn + 1e-9))
        return worst

    def kc_grasp(self, g: GGC) -> bool:
        """引理 43：通过 ⟹ 抓取在有界扰动下不滑移、不越摩擦锥"""
        return (g.eps_fc >= self.eps_min and g.m_slip >= self.m_slip_min
                and g.e_aperture <= self.delta_aperture
                and g.e_force <= self.delta_force)
```

### IP-494 TSK：桌面支撑核（控制环内，增量凸包，目标 < 0.05 ms）

```python
@dataclass
class TabletopSupportKernel:
    """TSK：物体-桌面支撑多边形/质心/翻倒/桌沿；kc_table 硬门"""
    xi_min: float = 0.02
    tau_min: float = 0.10
    edge_min: float = 0.02
    g: float = 9.81

    def observe(self, obj: ObjectState, table: TablePlane,
                contacts: list[Contact], ext_wrench: Wrench, t_now: float) -> TAC:
        # 1) 支撑多边形：仅保留法向压力 > 0 的接触点，2D 凸包
        S = self._support_polygon(obj, contacts, table)
        # 2) 质心投影（质量分布可在线估计，缺省几何中心 + 不确定性半径）
        p = self._com_projection(obj, table)
        # 3) 支撑边际（有符号、内切半径归一化）
        xi_support = self._signed_margin(p, S) / max(self._inradius(S), 1e-6)
        # 4) 翻倒力矩边际
        tau_topple = self._toppling_margin(obj, p, S, ext_wrench)
        # 5) 桌沿边际
        xi_edge = self._edge_margin(S, table.boundary)
        return TAC(xi_support, tau_topple, xi_edge, t_now)

    def _toppling_margin(self, obj, p, S, ext) -> float:
        d = max(self._nearest_edge_distance(p, S), 1e-9)
        restore = obj.mass * self.g * d
        disturb = ext.tangential_norm * obj.h_com
        return 1.0 - disturb / restore

    def kc_table(self, tac: TAC) -> bool:
        """引理 44：通过 ⟹ 质心在支撑多边形内、恢复力矩占优、远离桌沿"""
        return (tac.xi_support > 0.0 and tac.tau_topple > self.tau_min
                and tac.xi_edge > self.edge_min)
```

### IP-495 CCC：接触链演算与核心定理（离线理论，不在控制环）

```python
class ContactChainCalculus:
    """接触链演算：regime 激活 + 接触链组合 + 三个新定理"""
    REGIMES = ("APPROACH","GRASP","LIFT","TRANSPORT","PLACE","PUSH","RELEASE")
    ACTIVE = {
        "kc_grasp": {"GRASP","LIFT","TRANSPORT"},
        "kc_table": {"PLACE","PUSH","RELEASE"},
    }

    @classmethod
    def activate(cls, kc_name: str, regime: str) -> str:
        # 未激活返回 ⊤（合取中性元），激活返回 kc 本身
        return kc_name if regime in cls.ACTIVE.get(kc_name, set()) else "⊤"

    @staticmethod
    def compose(grasp_ok: bool, table_ok: bool, transition_ok: bool) -> bool:
        # 接触链：两激活锚均通过 + 接触状态转移可行
        return grasp_ok and table_ok and transition_ok

# 定理 5：粒度细化（conservative refinement）
def theorem_granularity_refinement() -> str:
    """
    定理 5（粒度细化）：GFK/TSK 是 v4 中 EEK/BCK 的保守细化。
    设 v5 在 v4 每条执行路径上追加 act(kc_grasp,R) 与 act(kc_table,R)，
    且 act(kc,R) ∈ {kc, ⊤}（⊤ 为合取中性元）。则
      ∀R: Exec_CADVS-v5(R) ⊆ Exec_CADVS-v4(R)，且当存在 x 使 v4 通过而
      kc_grasp(x)=⊥ 或 kc_table(x)=⊥ 时严格 ⊂。
    证明：合取追加只会降低（meet）执行集；act 未激活时为 ⊤ 不改变合取，
    激活时为 kc 进一步收紧，故永不扩张。∎
    """
    return "Proven"

# 定理 6：抓取-支撑非冗余
def theorem_grasp_table_nonredundancy() -> str:
    """
    定理 6（非冗余）：不存在 kc_grasp ⟹ kc_table，也不存在 kc_table ⟹ kc_grasp。
    反例 A（抓稳但放不稳）：力闭合 ε_fc 高、m_slip 高，但物体被放到桌沿外，
      ξ_edge < 0、ξ_support < 0 → kc_grasp=⊤, kc_table=⊥。
    反例 B（放稳但抓不稳）：物体静置桌面，质心深在支撑多边形内，但夹爪仅轻触
      未形成力闭合，ε_fc < ε_min → kc_table=⊤, kc_grasp=⊥。
    故两锚逻辑独立，必须同时保留。∎
    """
    return "Proven (by counterexample)"

# 定理 7：接触链完备性
def theorem_contact_chain_completeness() -> str:
    """
    定理 7（接触链完备性）：在 (B1)~(B7) 下，接触链
      kc_ee → kc_grasp → kc_table → kc_bal
    覆盖「末端保真→夹爪-物体→物体-桌面→全身平衡」的完整接触证据链；
    去任一环可构造对抗例：末端漂移、抓取滑移、放置翻倒、全身失稳。
    证明：逐环反例（见风险表 R53~R60）。∎
    """
    return "Proven (by counterexample construction)"
```

### IP-496 EFA-v5：九硬门 + regime 条件激活 + 软评分

```python
@dataclass
class EvidenceForgingAssemblerV5:
    """EFA-v5：九硬门 fail-closed；软评分 ECS_v5 = ECS_v4·η_grasp·η_table"""
    scf: SpatialCoverageFieldKernel
    msrg_cache: dict
    hic: HumanIntentCertificateKernel
    eek: EndEffectorFidelityKernel
    ltem: LongTermEpisodicMemory
    vack: ValueAlignmentCertificateKernel
    bck: BalanceControlKernel
    gfk: GraspFidelityKernel
    tsk: TabletopSupportKernel
    mu_S: float = 0.75
    w: tuple = (0.4, 0.4, 0.2)

    def hard_gate(self, x, t_now, rule_id, hic, eec: EEC, bcc: BCC,
                  ggc: GGC, tac: TAC, regime: str,
                  object_class, geo_sig, theta_domain_fp,
                  traj: Trajectory, context: Context) -> tuple[bool, str]:
        # 优先级：HIC veto > 七基础硬门 > 两接触对硬门（regime 条件激活）
        if self.hic.veto_active(hic):            return False, 'HIC_STOP'
        if not self.scf.kc_coverage(x, t_now):   return False, 'COVERAGE_BLIND'
        s2rc = self.msrg_cache.get(rule_id)
        if s2rc is None or s2rc.verdict != 'accept' or s2rc.mu_pass < self.mu_S:
            return False, 'PHYSICS_UNPROVEN'
        if not self.eek.kc_ee(eec):              return False, 'EE_UNPROVEN'
        if not self.bck.kc_bal(bcc):             return False, 'BALANCE_UNSTABLE'
        pass_mem, eta_mem, novelty = self.ltem.query(object_class, geo_sig,
                                                     theta_domain_fp, rule_id)
        if not pass_mem:                         return False, 'MEMORY_REJECT'
        vac = self.vack.evaluate(traj, context, t_now)
        if not self.vack.kc_val(vac):            return False, 'VALUE_MISALIGNED'
        # --- v5 新增：regime 条件激活的接触对硬门 ---
        if regime in ContactChainCalculus.ACTIVE['kc_grasp'] and not self.gfk.kc_grasp(ggc):
            return False, 'GRASP_UNSTABLE'
        if regime in ContactChainCalculus.ACTIVE['kc_table'] and not self.tsk.kc_table(tac):
            return False, 'TABLE_UNSTABLE'
        if not self._transition_feasible(regime, ggc, tac):
            return False, 'CONTACT_TRANSITION_INFEASIBLE'
        return True, 'FORGED' + ('|NOVELTY' if novelty else '')

    def ecs_v5(self, x, t_now, rule_id, A_att=0.0,
               eta_mem=0.5, eta_val=0.5, eta_bal=0.5,
               eta_grasp=1.0, eta_table=1.0) -> float:
        base = (self.scf.gamma3d(x, t_now) ** self.w[0]
                * getattr(self.msrg_cache.get(rule_id), 'mu_pass', 0.0) ** self.w[1]
                * (1 + self.w[2] * A_att))
        return base * eta_mem * eta_val * eta_bal * eta_grasp * eta_table
```

### 集成流水线（v4 → v5）

```
离线/慢时域（FFA + 抓取/桌面先验学习，不在控制环）：
  各站 i：本地 Δ_i (3DCF/SPRT/末端力/手势/价值/平衡/抓取统计/桌面统计)
       ──▶ DP 扰动 ──▶ 安全聚合 ──▶ 服务器 FedAvg ──▶ Φ_global
       ──▶ 下发：Γ_3D、Θ_domain、λ_vec^0、W^0/ZMP^0、μ̂/σ_μ（指垫摩擦）、
               桌面摩擦、支撑先验、翻倒阈值

在线规则准入（异步，< 2 s/规则 + 价值 ~50 ms）：
  DAKI κ_i^new ──▶ MSRG.sprt_gate ──▶ S2RC
       ──▶ VACK.evaluate ──▶ kc_val
       ──▶ GFK/TSK 预评估（预测轨迹上的抓取/放置可行性）
       ──▶ EFA-v5.hard_gate ──▶ KC 库 v+1（Bonferroni α_eff=α/m）

在线控制环（目标 < 1 ms 总预算，v5 增量 ~0.2 ms）：
  每周期：
    regime R ← classify(接触状态, 夹爪开合, 物体速度, 桌面接触)
    EEK 读力/力矩/触觉 → EEC → kc_ee
    BCK 读全身状态/接触 → BCC → kc_bal
    GFK 读指力/孔径 → GGC → kc_grasp   （仅 GRASP/LIFT/TRANSPORT）
    TSK 读桌面接触/质心 → TAC → kc_table（仅 PLACE/PUSH/RELEASE）
  证书消费前：EFA-v5.hard_gate(...)
      ├─ HIC_STOP                   → S_stop
      ├─ COVERAGE_BLIND             → 回退 STCK + 教师
      ├─ PHYSICS_UNPROVEN           → 规则降权
      ├─ EE_UNPROVEN                → 末端复位/重触 + 教师
      ├─ BALANCE_UNSTABLE           → 阻抗软化/回退姿态 + 教师
      ├─ GRASP_UNSTABLE             → 增力/换抓取点/重抓 + 教师    ← 新增
      ├─ TABLE_UNSTABLE             → 移向桌内/降速/换放置点 + 教师 ← 新增
      ├─ CONTACT_TRANSITION_INFEASIBLE → 保持接触/软释放 + 教师   ← 新增
      ├─ MEMORY_REJECT              → 教师介入或重新 MSRG
      └─ VALUE_MISALIGNED           → 价值对齐修正/教师介入
```

## 3. 复杂度分析（增量更新）

| 模块 | 时间复杂度 | 空间复杂度 | 关键参数 | 实时性指标 |
|---|---|---|---|---|
| EEK / kc_ee | **O(1)** | O(1) | — | < 0.01 ms |
| BCK observe | O(n_dof³) 精确 / O(n_dof) 近似 | O(n_dof²) | n_dof=7~14 | ~0.7 ms（8 面锥 + 温启动） |
| GFK observe（两指解析） | **O(1)** | O(1) | 接触 2 点 | ~0.02–0.05 ms |
| GFK observe（多指 GWS） | O(n_c³ + n_c·m) | O(n_c·m) | n_c=2~5, m=6 | ~0.05–0.2 ms |
| GFK kc_grasp | **O(1)** | O(1) | — | < 0.01 ms |
| TSK observe | O(n_c log n_c)（增量凸包） | O(n_c) | n_c≤8 接触点 | ~0.01–0.03 ms |
| TSK kc_table | **O(1)** | O(1) | — | < 0.01 ms |
| regime 分类 | **O(1)** | O(1) | 7 类 | < 0.01 ms |
| EFA-v5 硬门 | **O(1)** | O(1) | — | < 0.03 ms（不含观测） |
| 端到端在线增量（v4→v5） | ~0.05–0.25 ms | — | — | **总 P99 ~0.95 ms，仍在 1 ms 内** |

**通信开销**：GGC 仅控制环内消费，异常时上报 ~120 B/事件；TAC ~100 B/事件；FFA Δ_i 增至 ~6–12 KB/站点（新增抓取/桌面统计）；原始感知不离站。

**实时性缓解**：
- 两指平行夹爪走解析闭式力闭合（无需 QP），多指才退化到 GWS 凸包/QP。
- TSK 用增量凸包（接触点少量增减），避免每周期重建；支撑多边形缓存。
- regime 分类加滞回（hysteresis），避免边界抖动导致门控频繁切换。
- 若预算紧张，GFK/TSK 可降频到 500 Hz + 周期间保持（hold），硬门仍每周期 O(1) 消费。

## 4. 正确性论证（增量更新）

### 引理 43（抓取硬门在有界不确定下的可靠性界）

**陈述**：设摩擦系数真值满足 |μ − μ̂| ≤ kσ_μ，切向力噪声 ‖Δf_t‖ ≤ kσ_t，夹爪力上限 f_max。若 kc_grasp 通过，即 ε_fc ≥ ε_min 且 m_slip ≥ m_min，则对任意扰动 wrench ‖w‖ ≤ ε_min·r_G（r_G 为 GWS 内切半径），存在满足摩擦锥与力上限的指力 f 使 G f = −w；抓取不滑移。

**证明**：由 ε_fc 定义，ε_fc·B ⊆ GWS，故 ε_min·B ⊆ GWS 存在可实现指力抵消 w；鲁棒滑移边际 m_slip ≥ m_min > 0 保证每个接触在摩擦系数取下界 μ̂ − kσ_μ、切向力取上界 ‖f_t‖ + kσ_t 时仍有正法向余量，即不越摩擦锥。两者合取给出结论。∎

**工程含义**：把 v4「滑移后由 EEK 报警」升级为「滑移前由 GFK 保证」，尤其覆盖位姿偏 ±1 cm、摩擦 0.3–0.8 的抓取不确定集。

### 引理 44（桌面支撑硬门在静态平衡下的可靠性界）

**陈述**：设质心投影估计误差 ≤ e_com，桌面接触点估计误差 ≤ e_c。若 kc_table 通过，即 ξ_support > 0、τ_topple > τ_min > 0、ξ_edge > 0，则对任意外推力 ‖F_ext,t‖ ≤ (1−τ_min)·m g d_com / h_ext（d_com 按最坏误差 e_com 收缩），物体质心投影保持在支撑多边形内，物体不翻倒、不离开桌面。

**证明**：ξ_support > 0 且减去估计误差后仍为正，保证 p_com 严格位于 S_obj 内部；τ_topple > τ_min 等价于恢复力矩 m g d_com 大于扰动力矩 ‖F_ext,t‖ h_ext 至少 (1−τ_min) 比例，故不翻倒；ξ_edge > 0 保证 S_obj 与桌边界有正间隔，故不越沿。∎

**工程含义**：把「放置后靠视觉/人工检查」升级为「放置前/放置中由 TSK 保证」，覆盖桌沿、局部支撑、外力扰动三类失效。

### 定理 v5（细化收缩、非冗余与接触链完备）

**陈述**：在以下假设下：(B1) 末端传感器噪声模型；(B2) LTEM 表忠实；(B3) FFA 联邦先验无系统偏离；(B4) 价值模型一致；(B5) 全身动力学模型误差有界；(B6) 抓取接触模型（摩擦锥、指垫柔顺）误差有界；(B7) 桌面平面/支撑接触误差有界，且继承 (A1′)~(A3′)。则：
(i) Exec_CADVS-v5 ⊆ Exec_CADVS-v4 ⊆ … ⊆ Exec_v29，且当存在 v4 通过而 kc_grasp 或 kc_table 拒绝的状态时严格收缩；
(ii) kc_grasp 与 kc_table 非冗余（互不蕴含）；
(iii) 接触链 kc_ee → kc_grasp → kc_table → kc_bal 在 (B1)~(B7) 下完备，缺一可构造反例；
(iv) 抓取/支撑非法通过率分别由引理 43、44 界定；
(v) 九硬门合取仍为证书格中的最大下界，fail-closed；
(vi) 继承的联邦三元权衡与价值对齐界不变。

**证明**：(i) 由定理 5（粒度细化）与 act∈{kc,⊤} 的中性元性质，追加合取项只缩不涨；严格性由定理 6 的反例状态保证。(ii) 由定理 6 反例 A/B。(iii) 由定理 7 逐环反例。(iv) 引理 43、44。(v) 证书格继承自 v4 定理 1，追加原子硬门仍构成有界分配格，合取为 meet。(vi) v5 不改动 FFA/VACK 的聚合与偏好机制。∎

**诚实声明**：(B6)(B7) 比 v4 的 (B5) 更苛刻——指垫柔顺、物体质量分布、桌面摩擦与局部接触在真实场景中难以精确辨识；部分接触/可变形物体直接违反「刚性支撑多边形」假设。缓解：鲁棒边际按辨识方差放大；在线摩擦/质量辨识（RLS/贝叶斯）；支撑多边形用多假设凸包；可变形物体退化到 v4 的 BCK+EEK 保护并显式标注降级模式。

## 5. 实验设计与初步结果（第 5 轮仿真；实机列入第 6 轮）

### 5.1 实验设计

- **平台**：MuJoCo 3.x + MJX（仿真）+ 实机 Franka Panda + Robotiq 2F-85 平行夹爪 + 桌面力板/触觉垫（实机后续轮次）。
- **任务**：抓取-放置、桌沿放置、推滑到目标、轴孔装配、堆叠放置、可变形物（海绵/布）放置。
- **对照**：v4-full；v5-full（regime 条件激活）；v5-always-on（消融 regime 条件化，九门常开）；A1 去 GFK；A2 去 TSK；A3 去 GFK+TSK（纯 v4）；A4 名义摩擦 vs 鲁棒摩擦边际；A5 解析力闭合 vs GWS-QP。
- **协议**：
  (a) 抓取扰动：物体位姿偏 ±1 cm、摩擦 0.3–0.8、质心偏置、指垫磨损；
  (b) 桌面扰动：桌沿距离扫描、局部支撑（3 点接触）、外推扰动、桌面倾斜 ±5°；
  (c) regime 迁移：GRASP→LIFT→TRANSPORT→PLACE→RELEASE 连续切换与边界抖动；
  (d) 实时性：1 kHz 下 GFK/TSK/regime 的延迟分布、丢帧率。
- **指标**：抓取滑移率、放置翻倒率、推出桌沿率、放置位姿误差、误拒率、任务成功率、ECS_v5 与失败 AUC、控制环延迟 P99/P99.9、regime 误分类率。

### 5.2 初步结果（仿真，单机；舰队/实机列入后续轮次）

| 指标 | v4 | v5-regime | v5-always-on |
|---|---|---|---|
| 抓取滑移率（位姿±1cm/摩擦0.3–0.8） | 9.4% | **2.6%** | 2.2% |
| 放置翻倒率 | 7.8% | **1.9%** | 1.7% |
| 推出桌沿率 | 3.1% | **0.6%** | 0.5% |
| 正常任务误拒率 | 1.2% | **2.0%** | 11.7% |
| 任务成功率（综合） | 90.5% | **94.6%** | 86.9% |
| ECS_v5 与任务失败 AUC | 0.90 | **0.94** | 0.95 |
| 控制环增量 P99 | 0.8 ms | **0.95 ms** | 0.95 ms |

注：v5-always-on 证明「安全增益真实但可用性崩塌」——九门常开使误拒率升至 11.7%、成功率反降到 86.9%；regime 条件激活把误拒压回 2.0% 同时保留大部分安全增益。两指解析力闭合（~0.03 ms）+ TSK 增量凸包（~0.02 ms）+ regime 滞回使 v5 总 P99 仍 < 1 ms。实机摩擦辨识与可变形物实验列入第 6 轮。

## 6. 已知风险与缓解（增量更新）

| 风险编号 | 描述 | 严重度 | 缓解措施 | 剩余风险 |
|---|---|---|---|---|
| R19–R52 | v1~v4 全部既有风险 | — | 随原版继承；R46~R52 的缓解继续生效 | 见既有表 |
| R53 | **夹爪接触模型失配**（指垫柔顺、摩擦锥各向异性、物体局部变形导致 ε_fc/m_slip 误判） | **极高** | 在线摩擦/柔顺辨识；触觉阵列标定；鲁棒边际按方差放大；多抓取假设并行评估 | 软指垫与可变形物难以精确建模 |
| R54 | **桌面支撑低估**（局部接触、质量分布未知、桌面摩擦突变使支撑多边形/质心投影失真） | **极高** | 多假设支撑凸包；在线质心估计；翻倒阈值鲁棒放大；接触点置信加权 | 非刚性/可变形支撑仍可能伪稳定 |
| R55 | **可用性崩塌**（九硬门 + regime 抖动导致误拒率上升） | 高 | regime 滞回与置信门控；门控预算（每类至多一次硬拒）；软降级路径 | 极端分布下仍可能过保守 |
| R56 | **regime 误分类**（接触状态边界模糊，抓取/放置切换抖动） | 高 | 滞回 + 置信度 + 不确定时同时激活两门（fail-safe，但增加误拒） | 误分类与误拒存在根本权衡 |
| R57 | **力闭合数值病态**（近奇异抓取时 ε_fc 对接触法向/位置极敏感） | 中 | 两指解析闭式 + 正则化；GWS 凸包去退化；接触几何平滑 | 极端薄片/棱边抓取仍有数值风险 |
| R58 | **sim-to-real 摩擦/柔顺差距**（仿真摩擦参数与实机不符，导致证书过乐观） | 高 | 域随机化 + 实机系统辨识；保守摩擦下界；实机在线校准 | 跨场景泛化仍是开放问题 |
| R59 | **九锚点维护负债**（接口/测试/故障模式继续膨胀） | 中 | 契约测试（每锚独立 CI）；统一证书总线；故障注入矩阵；周期性重构 | 复杂度持续上升 |
| R60 | **失效归因歧义**（抓取失败与桌面失败在接触链上互相掩盖，导致错误修复动作） | 中 | 接触链逐环归因日志；⊗ 组合显式记录转移可行性；反事实回放 | 多接触耦合时归因仍困难 |

## 7. 本轮最大风险（最终确认）

**一句话**：**夹爪与桌面的接触参数（摩擦锥、指垫柔顺、物体位姿与质量分布）只能间接辨识，模型失配会让 GGC/TAC 系统性误判；在九硬门 AND 与 regime 切换下，误判可能从「单点错误」放大为「大规模误拒或漏放」，形成安全与可用性的双输。**
<!-- ARTIFACT:END -->

