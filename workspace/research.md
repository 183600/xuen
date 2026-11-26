<!-- IDEA:START -->
灵感驱动研究循环·第 1 轮（v24）；本轮灵感：「力矩传感」×「工具调用」

> **基线**：第 3 轮产出 MetricVoiceGauge-NCD-HUTDH-v23 + IP-436–439（云边同步/少样本/IP 认证）。其上承 v22 分层 PGEV（IP-431–435）、v21 语义-规范层（IP-425–430）、v20 联邦感知证书。
> 本轮纪律：**力矩是物理见证而非估计、工具调用是不可信提议者的能力受限接口**。不推倒 v23：CESC/FSVC/IPAM/HDL/ACSC/DCSC/CFC+++ 全部保留。本轮只做一件事：**把 v23「依赖统计感知下界的无碰撞承诺」升级为「统计感知 + 物理见证的双通道、可退化为有界后果（bounded-consequence）承诺」，并让 LLM 代理的工具调用只能通过不可伪造的能力证书进入执行链**。

## 0. 直觉与动机

**灵感 1（力矩传感 → 物理见证层）**
直觉：v23 的最大风险是「合规的缺席幻觉」——检测漏检时 AbsCert 形式成立而事实为假。视觉/检测是**统计通道**；但任何真实接触都会在关节力矩上留下残差，这是独立于视觉的**物理通道**。力矩传感器把 EVC 里「由电流估计的 τ」变成「直接测量的 τ」，并给出动量/扰动观测器残差 `r(t)`，`|r|>ε_r` 即外力/接触。必须诚实：力矩只能**事后**见证接触，不能防止第一次接触。因此它不把承诺升级为「永不碰撞」，而是把承诺**分层**：几何/语义层尽力避免接触；物理层保证**一旦接触，接触力 ≤ F_max 且 τ_reflex 内停止**。这是从 "collision-free under assumption" 到 "bounded-consequence under physics" 的范式补充。副产品：残差可**否决** AbsCert（覆盖区声明无人却出现外力残差 → 立即撤销缺席证书并翻转「有人」），成为最高优先级 veto 通道；测量 τ 也让 `E_arm` 从估计变为测量，模型失配即保守。

**灵感 2（工具调用 → 能力证书层）**
直觉：v23 隐含把 LLM 当「可信规划器」；工具调用时代，LLM 是**不可信提议者**，它会调用任意 API/执行器，且可能被提示注入。安全的关键不是「限制 LLM 说什么」，而是「执行器只认内核签发的、与参数绑定的能力令牌」。核心：工具分三类——**Q 查询**（只读，输出为不可信证据，需再取证）、**E 执行器**（改变物理状态，必须持有 Cap 令牌）、**M 元工具**（只增安全：请求人类确认/第二视角/慢速探触）。**LLM 只能提议，内核才能签发**：`Cap = Sig_kernel(tool_id, args_hash, plan_cert_id, expiry, nonce)`。提示注入最多让 LLM 提议一个危险调用，但拿不到令牌。组合安全：多个 E 调用单独安全、合起来可能不安全（能量/共享区竞争），用**租约 + 可串行化**：每个 E 调用租资源、限时限额；冲突租约串行化，跨租约校验全局不变量，失败回滚。反直觉点：**给代理「更多安全的查询工具」反而提高活性**——代理可主动调用只增证据的工具（第二视角、慢速探触、人类确认）来合法地「挣得」AbsCert 与执行权限，而不必全局保守。

**三者如何统一**
统一为 **v23 之上的「物理-效应器」耦合层**：TWC 回答「是否真的接触了、接触力多大」，FBCG 回答「最坏接触力被什么界住」，CCTC/TCTM 回答「不可信代理的哪个工具调用被允许、以何种事务语义执行」。共享状态 `ζ_phys = ζ_ce ∪ (r_t, b̂_t, F̂_t, Cap_t, Lease_t, ToolTrace_t)`。统一准入门 **HPC-T = HPC-E+ ∧ TWC_valid ∧ CapabilityCert ∧ LeaseOK**，其中 `TWC_valid ≜ (无接触迹象) ∨ (F̂_contact ≤ F_max ∧ t_stop ≤ τ_reflex)`。所有 E 调用必须携带内核令牌，故 `Exec_v24 = Exec_v23 ∩ Fil_twc ∩ Fil_fbcg ∩ Fil_cap ∩ Fil_lease ⊆ Exec_v23`。

## 1. 研究问题（Q12–Q16）

- **Q12（力矩残差的可靠性与盲区）**：如何在模型不确定性 δ_model 与传感器噪声 ε_n 下用 conformal/极值标定检测阈值 ε_r，使残差见证的漏检率与虚警率均有界？软/慢/遮挡接触（信号低于 ε_r 却高于致伤力）这一**共同盲区**如何被系统性识别与降级处理？
- **Q13（有界后果的力界）**：给定期望接触力上界 F_max、反射延迟 τ_reflex、执行器带宽与接触刚度上界 K_max，如何解析导出接近速度上界 v_max 与刚度上界，使最坏接触力 ≤ F_max？力矩测量误差 δτ 与 m_eff 估计区间如何保守进入该界？
- **Q14（能力证书的不可伪造与防重放）**：Cap 令牌如何与 plan_cert、args_hash、nonce、租约绑定，使被注入的 LLM 无法伪造/重放/混淆代理？工具描述与工具输出如何被标记为「数据而非指令」？
- **Q15（工具调用组合的事务性）**：多 E 调用如何用租约实现可串行化与无死锁？能量/共享区/F_max 等全局不变量如何跨租约原子校验？失败回滚如何不破坏已签发的安全证书链？
- **Q16（单调安全查询与活性）**：哪些工具可证明是**单调安全**的（只收缩可行域/只增证据）？reduced-speed torque probe 如何在 FBCG 界内为 AbsCert 取证，把「统计不可知」转成「物理可证」，同时不引入假自由空间？

## 2. 设计原则（在 P41–P42 基础上新增 P43–P46）

**P43 物理见证独立律（Physical Witness Independence）**
接触判定以测量力矩残差 `r = filter(τ_meas − τ_model)`（动量/扰动观测器）为准，独立于视觉证据；`|r| > ε_r` 即触发最高优先级 veto：撤销覆盖区内 AbsCert、状态翻转为「有人/有接触」、进入反射停止。力矩通道只可**加严**不可放宽；其失效（传感器故障/标定丢失）使 ε_r→∞ 并回退到更保守估计上界。

**P44 有界后果律（Bounded-Consequence）**
若几何/语义层无法保证无接触，则执行必须满足 `v ≤ v_max ∧ K ≤ K_max ∧ t_stop ≤ τ_reflex`，使接触力 `F ≤ F_max`；该界由测量 τ 与已知/保守估计的 m_eff 导出。几何上采用柔顺接触近似 `F ≈ v·√(m_eff·K)`，故 `v_max = (F_max − F_static)/√(m_eff·K_max)`。任何失效只允许降速、降刚度、增反射裕度（只降不升）。

**P45 能力证书律（Capability-Certified Invocation）**
任何 E 工具调用必须携带 `Cap = Sign_kernel(tool_id, args_hash, plan_cert_id, expiry, nonce)` 且 `args_hash` 匹配、`plan_cert` 有效、未过期、未重放；LLM 文本、工具描述、工具输出永不持有能力。Q 工具只读且输出标记为不可信证据；M 工具必须可证单调安全。令牌由内核对**已被准入计划中的具体调用**签发，代理无权自签。

**P46 工具事务律（Tool-Call Transaction）**
E 调用在租约内执行，冲突租约串行化（按资源全序获取或超时升级）；全局不变量（能量、共享区占用、F_max）跨租约原子校验，违反即回滚；不可满足 → SafeStop 升级而非静默等待。故 `Exec_v24 = Exec_v23 ∩ Fil_twc ∩ Fil_fbcg ∩ Fil_cap ∩ Fil_lease ⊆ Exec_v23`。

## 3. 与基线的接口（如何退化）

- 力矩传感器故障/标定丢失 ⇒ ε_r→∞，TWC 退化为「不可见证」，FBCG 仍以估计 τ 的保守上界生效 ⇒ 比 v23 更保守；
- 残差模型失配超界 ⇒ 判为「可能接触」，撤销 AbsCert，进入速度/刚度收缩；
- 能力内核故障 ⇒ 所有 E 调用默认拒绝，只留 Q/M，机器人停在安全态 ⇒ 子集；
- 租约管理器故障 ⇒ E 调用退化为单调用全局锁或全拒 ⇒ 子集；
- 查询/探触工具故障 ⇒ 只是失去合法挣得活性的手段，回落 v23 保守默认 ⇒ 子集；
- 全部失效 ⇒ 回退 v23 ⇒ `Exec_v24 ⊆ Exec_v23 ⊆ Exec_v22 ⊆ … ⊆ Exec_v18`。
- **安全继承**：TWC 只加 vetos、FBCG 只收紧 v/K、Cap 只做合取门、Lease 只串行化并回滚；任意失效都向更保守方向退化。

## 4. 预期贡献

1. **物理见证层 TWC**：首次把直接力矩残差作为独立于视觉的接触见证与缺席证书 veto，给出漏检率/虚警率的可标定界（conformal 阈值 + 极值尾界）；
2. **有界后果证书 FBCG**：把安全承诺从「无碰撞」扩展为「无碰撞或接触力 ≤ F_max 且快速停止」，给出 v_max/K_max/τ_reflex 的解析界；
3. **能力证书化工具调用 CCTC**：把 LLM 工具调用降格为「提议」，执行器只认内核令牌，抗提示注入/重放/混淆代理；
4. **工具调用事务 TCTM**：租约化可串行化与跨租约全局不变量，防「每个调用都合法但组合不安全」；
5. **单调安全查询 + 主动取证**：代理可主动调用只增证据工具合法「挣得」活性，缓解全局保守导致的活性坍缩；
6. **五证一体 HPC-T**：HPC-E+ ∪ TWC ∪ Capability ∪ Lease 统一门，`Exec_v24 ⊆ Exec_v23` 闭环。

## 5. 本轮最大风险

**一句话**：力矩残差与视觉缺席共享同一个「软、慢、遮挡」盲区——低于 ε_r 的轻接触与低于检测底限的漏检可能同时发生，使两条本应独立的通道在最需要冗余的边界情形上**共同失明**，defense-in-depth 退化为单点；且「有界后果」在颈部/儿童等脆弱部位即使 F ≤ F_max 仍可能致伤，我们可能误把「有界」当成「安全」。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
## 0. 新增核心模块（在 IP-436–439 基础上扩展）

| 编号 | 名称 | 类型 | 关键改进（相对 MetricVoiceGauge-NCD-HUTDH-v23） |
|---|---|---|---|
| IP-440 | TorqueWitness Certificate (TWC) | 物理见证证书 | 动量/扰动观测器残差 `r` 作为独立接触见证；conformal 阈值 ε_r；AbsCert veto；τ_meas 替换 τ_est |
| IP-441 | ForceBounded Compliance Guarantee (FBCG) | 有界后果保证 | 解析导出 v_max/K_max/τ_reflex 使接触力 ≤ F_max；失效只降不升 |
| IP-442 | Capability-Certified Tool Calling (CCTC) | 工具调用安全 | 工具类型 Q/E/M；Cap 令牌内核签发；args_hash/plan_cert/nonce 绑定；防重放/混淆代理 |
| IP-443 | Tool-Call Transaction Manager (TCTM) | 工具事务管理 | 租约、可串行化、跨租约全局不变量原子校验、回滚、死锁→SafeStop |
| IP-444 | Monotone-Safe Query Toolkit (MSQT) | 主动取证 | 只增证据工具集；reduced-speed torque probe；人类确认；第二视角 |
| IP-445 | HPC-T (Physical-Effector Unified Gate) | 统一准入门升级 | HPC-E+ ∪ TWC ∪ Capability ∪ Lease 五证一体；`Exec_v24 = Exec_v23 ∩ Fil_twc ∩ Fil_fbcg ∩ Fil_cap ∩ Fil_lease` |
| IP-446 | Residual Blind-Spot Monitor (RBSM) | 共同盲区监控 | 视觉缺席 × 力矩残差交叉审计；多增益观测器/主动抖动；盲区降级策略 |

## 0+. 增量符号体系（定义 1000–1049）

| 符号 | 含义 |
|---|---|
| τ_meas,i, τ_model,i | 关节 i 的测量力矩 / 模型预测力矩（逆动力学+摩擦） |
| r(t) | 力矩残差（扰动观测器状态），一阶滤波后的外部力矩估计 |
| K_O | 观测器增益（决定残差带宽与延迟 τ_d ≈ 1/K_O 量级） |
| ε_r | 接触检测阈值（conformal 分位数 + 模型不确定度裕度） |
| δ_model, ε_n | 模型不确定性上界 / 传感器噪声上界 |
| F_max, F_static | 允许接触力上界 / 静摩擦-预紧导致的静态接触力 |
| F̂_contact | 由 `r` 与 `m_eff` 估计的接触力上界 |
| v_max, K_max | 有界后果导出的接近速度上界 / 接触刚度上界 |
| τ_reflex | 从检测到接触至执行器进入安全态的最大反射延迟 |
| m_eff, e | 等效质量 / 恢复系数（冲量模型备用） |
| ToolType ∈ {Q, E, M} | 查询（只读）/ 执行器（改物理状态）/ 元工具（只增安全） |
| Cap | 能力令牌 `(tool_id, args_hash, plan_cert_id, expiry, nonce, sig)` |
| Lease | 资源租约 `(resource, holder, t_start, t_end, budget)` |
| ToolTrace | 本轮工具调用轨迹（供审计与回放检测） |
| TWC_valid | `(\|r\| ≤ ε_r) ∨ (F̂_contact ≤ F_max ∧ t_stop ≤ τ_reflex)` |
| MonotoneSafe(t) | 工具 t 的效果只增证据或只收缩可行域（不新增自由空间/权限） |
| CapabilityCert(call, plan) | 调用 call 的 Cap 验签通过 ∧ args_hash 匹配 ∧ plan_cert 有效 ∧ 未过期未重放 |
| LeaseOK(plan) | plan 涉及的全部 E 调用均持有有效租约且全局不变量满足 |
| E_arm^meas | `∫ Σ\|τ_meas,i·q̇_i\| dt`，测量力矩版机械臂能耗 |
| ζ_phys | `ζ_ce ∪ (r_t, b̂_t, F̂_t, Cap_t, Lease_t, ToolTrace_t)` |
| Exec_v24 | `Exec_v23 ∩ {π : TWC_valid ∧ FBCG(π) ∧ CapabilityCert(Tools(π)) ∧ LeaseOK(π)}` |
| Fil_twc, Fil_fbcg, Fil_cap, Fil_lease | 物理见证/有界后果/能力/租约过滤器 |

## 1. 关键算法骨架

```python
# ============================================================
# IP-440 TorqueWitness Certificate (TWC) — 物理见证证书
# ============================================================
@dataclass
class TorqueWitnessCertificate:
    r: np.ndarray                    # 关节残差向量（外部力矩估计）
    eps_r: float                     # 接触阈值（conformal 标定）
    contact: bool                    # 是否判为接触
    F_hat: float                     # 接触力上界估计
    t_stamp: float

class TorqueWitness:
    """扰动/动量观测器：r 为外部力矩 τ_ext 的一阶滤波。
       连续形式（模型精确时）：r_dot = K_O (τ_ext - r)；
       实现上用测量力矩与模型力矩的差驱动残差滤波。"""
    def __init__(self, K_O: float, alpha_r: float, model):
        self.K_O = K_O
        self.alpha_r = alpha_r          # 虚警率上界，用于 conformal 阈值
        self.model = model
        self.r = np.zeros(model.n_joints)
        self.calib_residuals: list[float] = []   # 无接触校准集 |r|
        self.eps_r = float('inf')       # 未标定前默认不可见证（保守）

    def calibrate_threshold(self, contact_free_stream):
        """无接触条件下收集 |r|，取 conformal (1-alpha_r) 分位数 + 模型裕度。"""
        for q, dq, tau_meas in contact_free_stream:
            self.step(q, dq, tau_meas)
            self.calib_residuals.append(float(np.linalg.norm(self.r)))
            if len(self.calib_residuals) > 5000:
                self.calib_residuals.pop(0)
        if len(self.calib_residuals) < 30:
            self.eps_r = float('inf')
            return
        q_hat = np.quantile(self.calib_residuals, 1.0 - self.alpha_r)
        self.eps_r = q_hat + self.model.delta_model_bound() + 1e-9

    def step(self, q, dq, tau_meas) -> TorqueWitnessCertificate:
        tau_model = self.model.inverse_dynamics(q, dq)   # 含摩擦/负载补偿
        # 一阶残差滤波（离散）；r -> τ_ext，时间常数 ≈ 1/K_O
        self.r = self.r + (tau_meas - tau_model - self.r) * self.K_O
        mag = float(np.linalg.norm(self.r))
        contact = mag > self.eps_r
        # 由残差反推接触力上界：F ≈ ||r|| / J^T 力臂映射（保守取最小力臂）
        self.F_hat = self.model.residual_to_force_upper(self.r) if contact else 0.0
        return TorqueWitnessCertificate(
            r=self.r.copy(), eps_r=self.eps_r, contact=contact,
            F_hat=self.F_hat, t_stamp=time.now())

    def veto_absence(self, cert: TorqueWitnessCertificate) -> bool:
        """AbsCert veto：若覆盖区内声明无人却出现接触，撤销缺席证书。"""
        return cert.contact   # True => 必须撤销 AbsCert 并翻转“有人/有接触”

# ============================================================
# IP-441 ForceBounded Compliance Guarantee (FBCG) — 有界后果
# ============================================================
class ForceBoundedCompliance:
    """柔顺接触模型 F ≈ v·sqrt(m_eff·K)，解出 v_max 使 F ≤ F_max。"""
    def __init__(self, F_max, F_static, m_eff_upper, K_max,
                 tau_reflex, delta_tau_ratio=0.05):
        self.F_max = F_max
        self.F_static = F_static
        self.m_eff_upper = m_eff_upper * (1.0 + delta_tau_ratio)  # τ 误差 -> 质量上界
        self.K_max = K_max
        self.tau_reflex = tau_reflex
        # v_max = (F_max - F_static) / sqrt(m_eff_upper * K_max)
        self.v_max = max(0.0, (F_max - F_static)) / math.sqrt(
            self.m_eff_upper * self.K_max + 1e-12)

    def within_bounds(self, v_cmd: float, K_cmd: float) -> bool:
        return (v_cmd <= self.v_max + 1e-9) and (K_cmd <= self.K_max + 1e-9)

    def project(self, v_cmd: float, K_cmd: float) -> tuple[float, float]:
        """只降不升：把命令投影到安全域内。"""
        return min(v_cmd, self.v_max), min(K_cmd, self.K_max)

    def guarantee(self, v_cmd, K_cmd) -> float:
        """返回在 FBCG 下最坏接触力上界（供证书写入）。"""
        return self.F_static + v_cmd * math.sqrt(self.m_eff_upper * K_cmd)

# ============================================================
# IP-442 Capability-Certified Tool Calling (CCTC) — 能力证书化
# ============================================================
from enum import Enum
class ToolType(Enum):
    Q = "query"       # 只读，输出为不可信证据
    E = "effector"    # 改物理状态，必须持 Cap
    M = "meta"        # 只增安全（请求人类/第二视角/慢速探触）

@dataclass
class Capability:
    tool_id: str
    args_hash: bytes
    plan_cert_id: bytes
    expiry: float
    nonce: bytes
    sig: bytes

    def verify(self, pk_kernel, tool_id, args, plan_cert, now, used_nonces) -> bool:
        if tool_id != self.tool_id:
            return False
        if hashlib.sha256(canonical_json(args)).digest() != self.args_hash:
            return False
        if not plan_cert.valid(self.plan_cert_id):
            return False
        if now >= self.expiry:
            return False
        if self.nonce in used_nonces:           # 防重放
            return False
        return verify_signature(pk_kernel, self._message(), self.sig)

    def _message(self) -> bytes:
        return self.tool_id.encode() + self.args_hash + self.plan_cert_id \
               + struct.pack("<d", self.expiry) + self.nonce

class ToolRegistry:
    def __init__(self):
        self.tools: dict[str, dict] = {}
    def register(self, name, fn, ttype: ToolType, resource=None,
                 monotone_safe=False):
        self.tools[name] = dict(fn=fn, type=ttype, resource=resource,
                                monotone_safe=monotone_safe)

class ToolCallGate:
    """LLM 只能提议；内核在计划被 HPC-T 准入后，为“具体调用”签发 Cap。
       代理永远接触不到内核私钥，故注入无法伪造/扩大能力。"""
    def __init__(self, kernel_sk, registry: ToolRegistry, tctm,
                 fbcg: ForceBoundedCompliance, plan_certs):
        self.kernel_sk = kernel_sk
        self.registry = registry
        self.tctm = tctm
        self.fbcg = fbcg
        self.plan_certs = plan_certs
        self.used_nonces: set[bytes] = set()

    def propose_and_execute(self, call: dict, plan_cert):
        tool = self.registry.tools[call["tool_id"]]
        args = call["args"]
        if tool["type"] is ToolType.Q:
            return self._run_query(tool, args)          # 只读，结果标记不可信
        if tool["type"] is ToolType.M:
            assert tool["monotone_safe"], "M 工具必须可证单调安全"
            return tool["fn"](args)                     # 只增安全
        # ---- E 执行器：必须由内核为本次调用铸造能力令牌 ----
        if not self._plan_admits_this_call(call, plan_cert):
            raise SecurityError("call not in admitted plan")
        # FBCG 先行投影，确保即使调用合法也满足力界
        v, K = args.get("v", 0.0), args.get("K", 0.0)
        args["v"], args["K"] = self.fbcg.project(v, K)
        cap = self._mint_cap(call, plan_cert)
        if not cap.verify(self._kernel_pk, call["tool_id"], args,
                          plan_cert, time.now(), self.used_nonces):
            raise SecurityError("capability verify failed")
        self.used_nonces.add(cap.nonce)
        lease = self.tctm.acquire(tool["resource"], call["budget"])
        try:
            return tool["fn"](args)
        finally:
            self.tctm.release(lease)

    def _mint_cap(self, call, plan_cert) -> Capability:
        msg = (call["tool_id"].encode()
               + hashlib.sha256(canonical_json(call["args"])).digest()
               + plan_cert.id
               + struct.pack("<d", time.now() + 0.5)
               + os.urandom(16))
        return Capability(..., sig=sign(self.kernel_sk, msg))

    def _run_query(self, tool, args):
        out = tool["fn"](args)
        return {"data": out, "trusted": False,   # 数据非指令，需再取证
                "type": "untrusted_observation"}

# ============================================================
# IP-443 Tool-Call Transaction Manager (TCTM) — 事务/租约
# ============================================================
class ToolCallTransactionManager:
    def __init__(self, invariant_check, timeout=0.5):
        self.leases: dict[str, Lease] = {}
        self.invariant_check = invariant_check   # 全局：能量/共享区/F_max
        self.timeout = timeout

    def acquire(self, resource, budget) -> Lease:
        if resource in self.leases:
            # 按资源全序获取以避免环形等待；超时即升级 SafeStop
            if not self._wait_or_ordered(resource):
                raise ResourceDeadlock(resource)
        candidate = Lease(resource, holder=current_agent(), t_start=time.now(),
                          t_end=time.now() + budget, budget=budget)
        trial = dict(self.leases); trial[resource] = candidate
        if not self.invariant_check(trial):       # 跨租约原子校验
            raise InvariantViolation(resource)
        self.leases[resource] = candidate
        return candidate

    def release(self, lease: Lease):
        self.leases.pop(lease.resource, None)

    def leases_ok(self, plan) -> bool:
        return self.invariant_check(self.leases)

# ============================================================
# IP-444 Monotone-Safe Query Toolkit (MSQT) — 主动取证
# ============================================================
class MonotoneSafeQueryToolkit:
    """所有工具只增证据或只收缩可行域，不新增自由空间/权限。"""
    def __init__(self, twc: TorqueWitness, fbcg: ForceBoundedCompliance):
        self.twc = twc
        self.fbcg = fbcg

    def torque_probe(self, region, probe_v: float):
        """慢速探触：在 FBCG 界内运动，用残差确认/排除接触。
           成功（全程 |r|≤ε_r）只产生“该区无接触”的正面证据，
           绝不直接签发 AbsCert（AbsCert 仍需 CAC 的召回下界与手势翻转检查）。"""
        v = min(probe_v, self.fbcg.v_max)         # 只降不升
        trace = []
        for pose in sweep(region):
            cert = self.twc.step(*sense(pose, dq=v))
            trace.append(cert)
            if cert.contact:
                return {"contact": True, "region": region,
                        "F_hat": cert.F_hat}       # 只增“有接触”证据
        return {"contact": False, "region": region,
                "evidence": "probe_clean", "trace": trace}

    def request_human(self, question):
        return {"evidence": "human_ack", "question": question}

    def request_second_view(self, other_robot_id):
        return {"evidence": "second_view", "from": other_robot_id}

# ============================================================
# IP-445 HPC-T — 五证一体统一准入门
# ============================================================
@dataclass
class HPCT:
    hpc_e_plus: 'HPCEPlus'          # 几何∧规范∧负信息∧能量∧云边∧少样本∧IP
    twc: TorqueWitness
    fbcg: ForceBoundedCompliance
    tool_gate: ToolCallGate
    tctm: ToolCallTransactionManager
    rbsm: 'ResidualBlindSpotMonitor'

    def admits(self, plan, twc_cert: TorqueWitnessCertificate,
               tool_calls: list[dict], plan_cert) -> bool:
        # 1) v23 及以下的全部证书
        if not self.hpc_e_plus.admits(plan, plan.x, plan.v, plan.z,
                                      plan.E_res, plan.margin_req,
                                      plan.modules):
            return False
        # 2) 物理见证：要么无接触，要么有界后果成立
        twc_ok = (not twc_cert.contact) or (
            twc_cert.F_hat <= self.fbcg.F_max
            and plan.t_stop <= self.fbcg.tau_reflex)
        if not twc_ok:
            return False
        if twc_cert.contact and self.hpc_e_plus.abs_cert_claims_free(plan.region):
            # 覆盖区声明无人却检测到接触 -> 撤销 AbsCert（veto）
            self.hpc_e_plus.revoke_absence(plan.region)
            return False
        # 3) 有界后果
        if not self.fbcg.within_bounds(plan.v, plan.K):
            return False
        # 4) 能力证书（逐调用）
        for call in tool_calls:
            if call["type"] == ToolType.E:
                if not self.tool_gate.verify_call(call, plan_cert):
                    return False
        # 5) 租约与全局不变量
        if not self.tctm.leases_ok(plan):
            return False
        # 6) 共同盲区监控：审计视觉缺席与力矩见证是否同时“沉默”
        if self.rbsm.common_blind_risk(plan) > plan.blind_risk_budget:
            return False
        return True

# ============================================================
# IP-446 Residual Blind-Spot Monitor (RBSM) — 共同盲区监控
# ============================================================
class ResidualBlindSpotMonitor:
    """当视觉声称“无接触/无人”且力矩残差也长期低于 ε_r 时，
       不能证明安全——这两个‘沉默’可能共享软/慢/遮挡盲区。
       用多增益观测器 + 主动抖动/探触制造可观测性，估算共同盲区风险。"""
    def __init__(self, twc: TorqueWitness, k_gains=(1.0, 3.0, 10.0)):
        self.observers = [TorqueWitness(k, twc.alpha_r, twc.model) for k in k_gains]
        self.history: deque = deque(maxlen=200)

    def common_blind_risk(self, plan) -> float:
        # 多增益：轻接触在不同带宽下残差响应不同；若所有增益都沉默，
        # 与“无接触”在统计上不可区分 -> 返回的风险不应为 0。
        silent = all(o.r_norm < o.eps_r for o in self.observers)
        vision_silent = self._vision_claims_free(plan)
        if silent and vision_silent:
            # 用模型不确定度与最小可检测力反推“可能被漏掉的力”占比
            return self._unobservable_force_fraction()
        return 0.0
```

## 2. 复杂度分析

| 模块 | 时间复杂度 | 空间复杂度 | 关键参数 |
|---|---|---|---|
| TWC 残差更新 | O(n_j²)（逆动力学）/ 步 | O(n_j + |calib|) | n_j≤7, |calib|≤5000, K_O≈50Hz |
| TWC 阈值标定 | O(N_calib·n_j²) 离线 | O(|calib|) | α_r≈1e-3 |
| FBCG 投影/判定 | O(1) | O(1) | ρ=√(m_eff K), F_max |
| CCTC 验签+哈希 | O(|args|) | O(1) 增量 | Ed25519 验签 ~50µs |
| TCTM 租约 | O(|leases|) 不变式 + O(1) 锁 | O(|leases|) | |leases|≤N_e |
| MSQT 探触 | O(|region|/v_probe)（物理时间） | O(|trace|) | v_probe ≤ v_max |
| HPC-T 准入 | O(1) + O(|tool_calls|) 验签 | O(1) 增量 | ≤20 calls |
| RBSM 风险审计 | O(G·n_j²)/步（G=增益数） | O(G·n_j) | G=3 |

**实时性**：TWC 在 50Hz 内 O(n_j²)（n_j≤7 可忽略），Cap 验签 ~50µs，TCTM O(1) 锁；RBSM 三增益可降频到 10Hz 审计。关键路径无阻塞 I/O，云端仍完全异步。

## 3. 正确性论证

### 引理 1（残差见证的检测底限与延迟）
**陈述**：设模型不确定度上界 δ_model、噪声上界 ε_n、阈值 ε_r。若持续外力 `\|τ_ext\| > ε_r + δ_model`，则残差在 `τ_d = O(1/K_O·ln(...))` 内越过阈值；若 `\|τ_ext\| ≤ ε_r − δ_model`，则残差**永不**越过阈值（检测底限），此即与视觉共同盲区的来源。
**证明**：模型精确时 `ṙ = K_O(τ_ext − r)`，故 r 以时间常数 1/K_O 指数逼近 τ_ext；加入有界模型误差与噪声后，稳态判据为 |τ_ext| 与 ε_r 的比较。小于底限的外力在稳态下无法与噪声/模型误差区分。∎

### 引理 2（有界后果的力界）
**陈述**：柔顺接触下最坏接触力 `F ≈ F_static + v·√(m_eff·K)`。若 `v ≤ v_max = (F_max−F_static)/√(m_eff^U·K_max)` 且 `K ≤ K_max`，则对任意 K≤K_max 有 `F ≤ F_max`。
**证明**：F 关于 v、K 均单调递增；在 v_max、K_max 处取最大；m_eff^U 为含 τ 误差的质量上界，故对所有真实 m_eff≤m_eff^U 成立。∎

### 引理 3（能力令牌不可伪造与防重放）
**陈述**：在签名 EUF-CMA 安全下，不掌握内核私钥的对手（含被完全注入的 LLM）无法产出被接受的 E 调用，除非重放一个未过期且参数完全匹配的旧令牌；重放被 nonce 集合拒绝，参数篡改被 args_hash 拒绝，跨计划调用被 plan_cert_id 拒绝。
**证明**：Cap 绑定 `(tool_id, args_hash, plan_cert_id, expiry, nonce)` 并由内核签名；验签要求逐项匹配。工具描述/输出不含密钥且被标记为不可信数据，不能提升权限。∎（混淆代理被 plan_cert_id 绑定主体所阻断。）

### 引理 4（工具事务的可串行化与无死锁升级）
**陈述**：TCTM 对冲突资源按全序获取 + 超时升级，保证所有成功提交的 E 调用可串行化且满足全局不变量；无法满足时进入 SafeStop 而非静默等待。
**证明**：资源全序排除环形等待（无死锁）；acquire 对候选租约集合做原子不变式校验，故提交顺序等价于串行顺序；超时路径显式升级，不悬挂。∎

### 引理 5（物理-效应器层的单调退化链）
**陈述**：`Exec_v24 ⊆ Exec_v23 ⊆ Exec_v22 ⊆ … ⊆ Exec_v18`。
**证明**：`Exec_v24` 由若干**合取**过滤器定义（TWC、FBCG、Cap、Lease），任一失败仅减少可行计划；各失效模式（传感器坏/内核坏/租约坏）均回退到更保守默认而非放宽。归纳即得全链。∎

### 定理（HPC-T 五证准入门）
**陈述**：`HPCT.admits(π)=True` ⟺ π 同时满足 (1) v23 全部证书，(2) 物理见证有效或无接触，(3) 接触力在 F_max 内且 τ_reflex 内停止，(4) 每个 E 调用持有合法能力令牌，(5) 租约与全局不变量满足且共同盲区风险在预算内。
**证明**：由 `admits` 的六个合取条件与引理 1–5 直接可得；必要性为任一条件缺失即拒证，充分性由单调链与统计/物理界的叠加保证。∎

## 4. 已知风险与缓解

| 编号 | 描述 | 严重度 | 缓解措施 | 剩余风险 |
|---|---|---|---|---|
| R1 | 力矩残差与视觉缺席的**共同盲区**（软/慢/遮挡轻接触同时低于两通道底限） | 最高 | 1) RBSM 多增益观测器 + 主动抖动/慢速探触制造可观测性；2) 融合力敏皮肤/电流高频分量；3) 把承诺诚实标注为 bounded-consequence | 真实轻接触仍可能同时逃过两通道，冗余退化为单点 |
| R2 | 脆弱部位（颈/儿童）即便 F≤F_max 仍可能致伤 | 最高 | 1) 按部位分层 F_max（人形/头部更低）；2) 距离越近 v_max 越小（人距自适应）；3) 接触即停 + 主动退让 | F_max 的下调压低活性；极端姿态仍无绝对保证 |
| R3 | 提示注入/混淆代理使 LLM 提议危险 E 调用 | 高 | 内核签发 Cap + args_hash/plan_cert/nonce 绑定；工具输出标记不可信；默认拒绝 | 合法计划内的参数微调仍可能有害，需 FBCG 兜底 |
| R4 | 租约死锁/饥饿或全局不变量跨租约竞态 | 中 | 资源全序 + 超时 SafeStop；不变式原子校验；回滚日志 | 高并发下活性下降，可能频繁进入 SafeStop |
| R5 | 力矩传感器偏置/温漂导致 ε_r 标定失效（漏检或虚警） | 中 | 在线偏置辨识 + conformal 滑动窗口重标定；虚警则只损失活性 | 温度突变 + 无接触校准集不足时，阈值暂不可信 |

## 5. 实验设计（验证指标）

| 指标 | 基线 (v23) | 目标 (v24) | 测试协议 |
|---|---|---|---|
| 接触检测底限 / 延迟 | 无物理通道 | 底限 ≤ 5N@关节，延迟 ≤ 20ms (K_O=50Hz) | 已知力脉冲注入，扫幅值/频率 |
| 最坏接触力 | 未界定 | ≤ F_max（含 10% 裕度） | 以 v_max、K_max 撞软/硬目标，测峰值力 |
| 缺席幻觉对抗（视觉致盲+软接触） | 可能碰撞 | 接触被 TWC 捕获率 ≥ 90%，或明确报告“共同盲区风险” | 儿童/轮椅/蹲姿/逆光/软质衣物数据集 + 力台 |
| 提示注入红队 | N/A | 0 次越权 E 调用成功 | 注入 200 条恶意工具描述/输出，审计 ToolTrace |
| 工具事务可串行化 | N/A | 0 次不变量违反，死锁 100% 升级 SafeStop | 多代理争用共享区/能量预算，注入延迟 |
| 主动探触取证效率 | N/A | 探触后 AbsCert 可签发率提升 ≥ 30%，且 0 假自由空间 | 未知区域对照：无探触 vs torque_probe |
| 端到端单步延迟 (P99) | <20ms | <25ms（含 TWC+Cap 验签，不破坏 50Hz） | 50Hz 实测，3 增益 RBSM 降频 10Hz |
| 安全单调性违反 | 0 | 0 | 组合故障注入：传感器坏/内核坏/租约坏/注入 |

## 6. 本轮最大风险（最终确认）

**一句话**：TWC 的检测底限与视觉缺席在「软、慢、遮挡」接触上高度相关——一旦轻接触同时低于 ε_r 与视觉召回下界，两条通道便**共同沉默**，系统会在「形式上有界、事实上致伤」的情形下合规执行；因此 v24 的真正确认目标是：把这一共同盲区显式量化并纳入准入门预算，而不是宣称它已被冗余消除。
<!-- ARTIFACT:END -->
