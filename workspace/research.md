# 玄 · 灵感驱动研究循环

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 10 轮（新灵感循环第 1 轮；承接 v9；本轮灵感：「避障控制」×「持续学习」）
> **基线**：第 9 轮 MetricVoiceGauge-ACMD（定义 532–539；引理 82–86；实验 E551–E570）。
> 本轮纪律：**运行时避障安全网 + 安全保持的持续适应**。两个灵感对应 v9 的两处结构性软肋：(i) 块证书的安全性以「信任域内前向模型误差 ≤ β」为前提，而域偏移恰使该前提最脆弱；(ii) 前向模型与阈值固定，陌生域只能靠 K_eff 收缩变保守，无法适应变好。新增 SAF/CSL/CTA 均为可选增强，失效时按**保守退化序**（行为集 ⊆ v9 行为集）注入恒等元或安全吸收元，严格退回 v9。

## 0. 直觉与动机

**灵感 1（避障控制 → 运行时屏障安全滤子）**
直觉：v9 把安全压在"预测未来 K 步不碰"上，但预测最不可靠时恰是域偏移。避障控制的核心教训是**别赌长时程，赌闭环不变式**：用只依赖当前测量与保守不确定性界的控制屏障函数（CBF），在**每个执行步**把动作投影进安全集。核心创新：**安全避障滤子（SafeAvoidanceFilter, SAF）**，50Hz 对 AC 的第 k 步动作解一个最小修正 QP，约束为鲁棒离散时间 CBF（含不确定裕度 L_h·ρ）；不可行则急停/退最近中止点。它不新增任何长时程预测，只新增**可证明的逐步闸门**：每步约束成立 ⇒ 安全集前向不变。AC 管"块内计划是否可信"，SAF 管"这一步是否必定安全"——预测失效时 SAF 仍是最后一道可证明的闸门。

**灵感 2（持续学习 → 安全保持的在线适应）**
直觉：v9 的 DA-ML/OTL/Cal 只在固定参数上做门控与校准，遇新障碍动力学（新地面、新行人速度分布）只能变保守、不能变好；但朴素在线微调前向模型会灾难性遗忘并悄悄放松安全裕度。核心创新：**持续安全账本（ContinualSafetyLedger, CSL）**——双账本：可塑性账（新域预测误差下降）与稳定性账（锚集上的保持）；每次更新先写影子权重，经「安全回归套件 + 证书不放松检验」才原子提交，否则回滚。配套**证书保持切线投影（ConstraintTangentAdapter, CTA）**把梯度更新投影到"锚集不确定界不增"的参数流形切空间。于是"适应"被关进安全证书可接受的参数邻域。

**两者合流**：避障提供**运行时可证明净**，持续学习提供**让这个净随经验收紧（更不保守）的适应能力**，CTA 是二者的数学接缝——学习只能在证书保持的切空间里动。v9 的最大风险（域偏移时前向模型误差最大）在这里被正面处理：SAF 不依赖长时程预测兜底，CSL 收紧 ρ 但有锚集与认证检查点回滚。

## 1. 研究问题（轮次升级版）

- **Q1（运行时屏障可靠性）**：在残差估计误差有界 ‖d−d̂_θ‖ ≤ ρ 下，SAF 的鲁棒 DCBF 能否保证逐步前向不变？在相对阶 ≥2 与执行器饱和下，如何用 HOCBF 与松弛变量保持可行性并安全处理不可行？
- **Q2（安全保持的持续学习）**：什么样的接受判据、参数投影与回滚点，能在不放松锚集安全证书的前提下最大化新域可塑性？覆盖（coverage）失效时如何在有限步内退回最近认证检查点？
- **Q3（两环耦合）**：SAF 的保守性由 ρ 决定；CSL 收紧 ρ 是否单调扩张可行动作集、从而降低保守性并提升任务收益？如何避免"学习—保守—低收益"的次优锁定？

## 2. 设计原则（在 P10–P12 基础上新增 P13–P15）

**P13 运行时屏障律（Runtime Barrier, SAF）**
执行步而非块边界上做安全决策：a_safe = Π_C(a^k)，Π_C 为带鲁棒 DCBF 约束的最小修正投影。约束用**当前测量状态 + 学习残差模型 + 不确定半径**，不用 K 步预测。不可行 ⇒ 急停/最近中止点；SAF 为 φ^elig=false 的安全关键模块，失效注入**安全吸收元**（急停），而非恒等元。

**P14 安全保持适应律（Safety-Preserving Adaptation, CSL）**
任何参数更新 θ→θ′ 必须同时满足：可塑性增益 G_new ≥ τ_gain、锚集稳定性损失 L_anchor(θ′)−L_anchor(θ) ≤ τ_stab、锚集不确定界不放松 Δρ_A ≤ 0、安全回归套件全通过。四项全过才原子提交；否则回滚。退化时冻结 θ 于最近认证检查点。

**P15 证书保持投影律（Certificate-Preserving Projection, CTA）**
把 SGD 更新 Δθ 投影到线性化的证书可行域 {δ : ρ_θ(A)+J_Aδ ≤ ρ_max} 的切空间；约束不活跃时 Δθ_CTA=Δθ_SGD，故 CTA 失效可注入恒等投影、退回「CSL 账本 + 全空间更新」而不破坏账本的原子性。

## 3. 与基线的接口（如何退化）

- SAF 失效（超时/证书异常）⇒ 注入安全吸收元 a_stop（急停/最近中止点），行为集 ⊆ v9，安全由 v9 AC 证书级兜底；显式关闭 SAF ⇒ 恒等投影，逐位退回 v9 决策；
- CSL 失效 ⇒ 冻结 θ 于最近认证检查点 θ*，退回 v9 固定模型（ρ 取检查点值），安全等价 v9；
- CTA 失效 ⇒ 恒等投影，更新仍受 CSL 四项判据与回滚保护，等价「无投影的 CSL」；
- v9 的 AC/MW/ID 任一失效 ⇒ 按 v9 五级链退回；
- 全部失效 ⇒ 完整退回 v9 → v8 → v7 → v6。

## 4. 预期贡献

1. **运行时鲁棒避障滤子**：把安全从"块级预测"下移到"逐步闭环不变式"，与 AC 形成「计划可信 + 执行必安全」两级分工；
2. **安全保持的持续学习**：双账本 + 证书保持切线投影，使在线适应不能突破锚集安全证书，同时用认证检查点回滚兜住覆盖失效；
3. **保守性—可塑性桥接**：证明 ρ 收紧 ⇒ SAF 可行集单调扩张 ⇒ 保守性单调下降，首次把"学得更好"翻译成"避障更不保守且仍可证明安全"；
4. **实验 E571–E590**：静态/动态障碍、可行性、覆盖标定、适应增益、遗忘、证书保持、对抗投毒、长跑、仿真到实物与端到端任务。

## 5. 本轮最大风险

**一句话**：SAF 的鲁棒屏障以不确定半径 ρ 为有效性前提，而持续学习恰在最陌生的障碍分布上更新残差模型；若 conformal 半径在该分布外过度自信（覆盖失效），屏障裕度会被低估，最激进的适应场景正是安全保证最脆弱的场景。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 10 轮产物 · 创新点清单 v10：**MetricVoiceGauge-SCAF**（Safe Continual Avoidance Filter）

> 背景：第 9 轮 MetricVoiceGauge-ACMD（定义 532–539；引理 82–86；实验 E551–E570）。
> 本轮灵感：「避障控制」×「持续学习」
> **继承纪律**：MetricVoiceGauge 九不变式（CVC-闭环、SpatialCert、RT-CVC、FaultCert、PrimitiveGraph、严格退化链、OTL、GCT、ER）与 v9 的 AC/MW/ID 全部原样继承。新增 SAF/CSL/CTA 一律为**可选增强**，且遵循**保守退化序** B(v10) ⊆ B(v9)：失效时注入恒等元或安全吸收元，任意时刻的可观测行为集不超出 v9，故 v9 的安全性引理原样传递（引理 93）。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进（相对 v9 ACMD） |
|---|---|---|---|
| IP-340–356 | v9 全部模块 | 继承 | 语义不变；AC 的动作输出改经 SAF 投影后再执行（IP-357） |
| IP-354 | ActionChunkCertifier | 接口升级 | 其候选块在生成期额外接受 SAF 可行性预检；中止点集 P_t 与 SAF 急停轨迹统一由定义 534/542 给出 |
| IP-357 | SafeAvoidanceFilter 安全避障滤子 | 新增核心模块 | 50Hz 逐步鲁棒 DCBF 最小修正 QP；HOCBF 处理相对阶 2；不可行即安全吸收元；φ^elig=false |
| IP-358 | ContinualSafetyLedger 持续安全账本 | 新增核心模块 | 双账本 + 影子权重 + 四项接受判据 + 原子提交/回滚；认证检查点与 ACI 覆盖监控 |
| IP-359 | ConstraintTangentAdapter 证书保持切线投影 | 新增核心模块 | 把更新投影到锚集不确定界不增的切空间；不活跃时退化为恒等，兼容 CSL 原子性 |

**退化链声明（v10 契约化六级）：**
- Level-0（新增最高优先）：SAF QP 不可行或检测到不可避免碰撞 ⇒ 安全吸收元 a_stop（最大减速/最近中止点），并冻结学习；
- Level-1：SAF 模块失效 ⇒ 注入 a_stop（保守），或显式关闭时恒等投影、逐位退回 v9 AC 决策；
- Level-2：CSL 失效 ⇒ 冻结 θ 于最近认证检查点 θ*，退回 v9 固定模型；
- Level-3：CTA 失效 ⇒ 恒等投影，更新仍受 CSL 四项判据与回滚；
- Level-4：AC 证书失效或信任域破坏 ⇒ K_eff←1，逐步执行（v9）；
- Level-5：MW/ID/v8 模块失效 ⇒ 按 v9 五级链退回 v9→v8→v7→v6。

## 1. 符号体系增量（定义 540–551）

| 符号 | 含义 |
|---|---|
| x_t∈X | 增广状态（位姿、速度、关节、与最近障碍关系等） |
| O_t, h(x) | 时刻 t 的障碍集与符号距离屏障：h(x)=dist(p,O_t)−r_robot−m_safe |
| C={x:h(x)≥0} | 安全集；前向不变目标 |
| γ∈(0,1] | DCBF 收缩因子，h(x_{t+1})≥(1−γ)h(x_t) |
| d, d̂_θ | 真实残差动力学与 θ 参数化的学习残差模型 |
| ρ_θ(x,u) | 残差不确定半径（conformal/集成散度），满足 ‖d−d̂_θ‖≤ρ_θ 时称**覆盖** |
| L_h | h 的 Lipschitz 常数 |
| a^k, a_safe | AC 第 k 步名义动作与 SAF 投影后的安全动作 |
| A, ρ_max | 锚集（安全关键场景，版本化冻结）与锚集不确定半径预算 |
| θ*, ρ* | 最近认证检查点及其有效半径 |
| G_new, L_anchor | 可塑性增益与新域相对锚集的稳定性损失 |
| τ_gain, τ_stab | 接受阈值 |
| J_A | 锚集不确定度对 θ 的 Jacobian |
| Cons(θ) | 保守性度量 E‖a_safe−a^k‖ |
| a_stop | 安全吸收元：最大减速度指向最近中止点的停驻序列 |
| α_t | ACI 在线误覆盖目标，随违例自适应 |

**新增定义 540（增广避障状态与安全集）** x_t 含机器人位姿/速度/执行器状态及最近 r 个障碍的几何-运动摘要；静态障碍 O_static 与动态障碍 O_t=O_0⊕(v_obs·t)⊕E_t（E_t 为有界预测误差集）。屏障 h(x)=dist(p,O_t)−r_robot−m_safe，C={x:h(x)≥0}。

**新增定义 541（鲁棒离散时间控制屏障函数 R-DCBF）** 对 x_{t+1}=f_0(x_t,u_t)+d(x_t,u_t)，若存在 u∈U 使
```
h(f_0(x,u)+d̂_θ(x,u)) − L_h·ρ_θ(x,u) ≥ (1−γ)·h(x),   γ∈(0,1]
```
则 h 为 (γ,ρ_θ)-鲁棒 DCBF。相对阶 ≥2 时用 HOCBF：ψ_0=h，ψ_1=ψ_0+α_1ψ_0，对 ψ_1 施加同型条件（定义 541′）；动态障碍通过 O_t 的预测集把其加速度不确定并入 ρ_θ。

**新增定义 542（安全避障滤子 SAF）** 每 20ms 对 a^k 求解
```
a_safe = argmin_{u∈U} ½‖u−a^k‖²_W
s.t.  h(f_0(x,u)+d̂_θ(x,u)) − L_h·ρ_θ(x,u) ≥ (1−γ)h(x)
      u_min ≤ u ≤ u_max,   ‖u−u_prev‖ ≤ Δu_max
```
可行则输出 a_safe；不可行则输出 a_stop=紧急减速至最近中止点 p*（定义 534），并置 Level-0。显式中立元为恒等投影 Π_id(a^k)=a^k（仅用于显式关闭 SAF）。

**新增定义 543（持续学习双账本）** 锚集 A 固定且版本化。对更新 θ→θ′：
```
G_new    = err_{D_new}(θ) − err_{D_new}(θ′)
L_anchor = max_{a∈A∪D_replay} [err_a(θ′) − err_a(θ)]_+
Δρ_A     = max_{a∈A} ρ_{θ′}(a) − ρ_max
accept ⇔ G_new ≥ τ_gain ∧ L_anchor ≤ τ_stab ∧ Δρ_A ≤ 0 ∧ suite_pass(θ′)
```
四项全过才提交；任一失败即回滚。

**新增定义 544（影子权重与原子提交）** 更新只写 θ_shadow；接受判据在影子模型上离线评估；提交为双缓冲指针切换（版本号 +1），SAF 永远读到一致快照，杜绝半更新可见。

**新增定义 545（证书保持切线投影 CTA）** 设 SGD 更新 Δθ_SGD。解
```
Δθ_CTA = argmin_δ ½‖δ−Δθ_SGD‖²
         s.t.  ρ_θ(A) + J_A·δ ≤ ρ_max      （线性化锚集证书）
Δθ = Π_{T_M}(Δθ_SGD)  若约束活跃；否则 Δθ = Δθ_SGD
```
约束不活跃时 CTA 恒等，故可安全降级。

**新增定义 546（认证检查点与 ACI 覆盖监控）** 采用自适应 conformal：α_{t+1}=α_t+η(α−1{‖d_t−d̂‖>ρ_t})；ρ_t 取残差 1−α_t 分位。当滑窗违例率 > ν_max 时：冻结 θ←θ*、ρ←κ_ρ·ρ*（κ_ρ>1 安全系数），并在 Level-2 恢复前禁止提交。

**新增定义 547（持续避障任务序列与度量）** 任务序列 T_1,…,T_n（障碍几何/动力学/地面摩擦渐变），安全锚集 A 跨任务不变。度量：
```
FWT = mean_i [R_i(θ_after_i) − R_i(θ_0)]
BWT = mean_i [R_i(θ_final) − R_i(θ_after_i)]
Forget = max_i [R_i(θ_after_i) − R_i(θ_final)]
```

**新增定义 548（安全回归套件）** suite_pass 包含：锚集前向不变数值检查、急停可行性、SAF 投影有界性、动态障碍最小间隙、对抗扰动下的屏障残余。套件固定、不可被学习更新修改。

**新增定义 549（保守性度量）** Cons(θ)=E_{x∼D}[‖a_safe(x;θ)−a^k(x)‖]。用于验证"ρ 收紧 ⇒ 可行集扩张 ⇒ 保守性下降"。

**新增定义 550（安全契约与吸收元）** κ_SAF=(In,Out,D=1.0ms,Ŵ=1.0ms,v^⊥=a_stop,π=0,φ^elig=false)；κ_CSL=(…,v^⊥=freeze θ,φ^elig=true 但仅可压缩更新预算)；κ_CTA=(…,v^⊥=Π_id,φ^elig=true)。安全模块的失效值取**吸收元**（急停/冻结）而非恒等元，且吸收元使行为集单调收缩，故仍满足保守退化序。

**新增定义 551（SCAF 联合闭环）** 每 20ms：AC 提议 a^k → SAF 投影得 a_safe → 执行 → 采集 (x,u,x′) → 块边界处 CSL 评估影子更新 → CTA 投影 → 接受则原子提交，否则回滚或冻结。安全不变式由 SAF 运行时保证，学习只改变 ρ 的紧致度，不改变安全集的定义。

## 2. 形式化定义（要点与升级）

**升级定义 496（软证书，v10）** δ_trigger 增加两项：`SAF_QPAvailable ∧ ρ_θ ≤ ρ_max`。块证书 Ĉ_t 仅在 SAF 预检通过的候选上生成，故"块内软通过、执行硬失败"的空洞进一步缩小；M₀ 硬检查直接读取 SAF 的 DCBF 残余，而非仅读预测值。

**升级定义 531（软硬约束衔接）** M₀ 判据新增：任一执行步 SAF 约束不成立或 QP 不可行 ⇒ 立即 Level-0 安全停驻 + 冻结学习，不等块边界。停驻轨迹与 AC 中止点 p* 共用同一 d_stop 构造，保证两套安全机制不互相矛盾。

**升级定义 538（提炼状态机）** ID 对 CSL 只可压缩其更新预算（学习频率），不可将其转为 dormant（φ^elig=false 的核心闸门）；对 SAF/CTA 永不消融。

## 3. 关键算法骨架

```python
# IP-357 SafeAvoidanceFilter：运行时鲁棒避障滤子
class SafeAvoidanceFilter:
    def __init__(self, f0, residual, gamma=0.2, L_h=1.0,
                 m_safe=0.12, u_bounds=None, du_max=None):
        self.f0, self.res = f0, residual
        self.gamma, self.L_h, self.m_safe = gamma, L_h, m_safe
        self.u_bounds, self.du_max = u_bounds, du_max

    def barrier(self, x, u):
        x_next = self.f0(x, u)
        dh = self.res.predict(x, u)                 # d̂_θ
        rho = self.res.radius(x, u)                 # ρ_θ（conformal）
        return self.h(x_next + dh) - self.L_h * rho, rho

    def h(self, x):
        return dist(x.p, x.obstacles) - x.r_robot - self.m_safe

    def filter(self, x, a_nom, u_prev):
        def obj(u):  return 0.5 * (u - a_nom) @ self.W @ (u - a_nom)
        cons = [{'type': 'ineq',
                 'fun': lambda u: self.barrier(x, u)[0]
                                  - (1 - self.gamma) * self.h(x)}]
        cons.append({'type': 'ineq',
                     'fun': lambda u: self.du_max - norm(u - u_prev)})
        sol = solve_qp(obj, cons, self.u_bounds, warm_start=u_prev)
        if sol.success:
            return sol.u, 'safe'
        return self.emergency_stop(x), 'infeasible'   # 安全吸收元

    def emergency_stop(self, x):
        p = nearest_abort_point(x)                     # 定义 534
        return max_deceleration_toward(x, p)


# IP-359 ConstraintTangentAdapter：证书保持切线投影
class ConstraintTangentAdapter:
    def __init__(self, anchors, rho_max, eps=1e-6):
        self.A, self.rho_max, self.eps = anchors, rho_max, eps

    def anchor_uncertainty(self, theta):
        return np.array([radius_model(theta, a) for a in self.A])

    def project(self, theta, dtheta, residual):
        rho_A = self.anchor_uncertainty(theta)
        slack = self.rho_max - rho_A
        if slack.min() > self.eps:                     # 约束不活跃 → 恒等
            return dtheta
        J = jacobian(lambda th: self.anchor_uncertainty(th), theta)
        d = solve_qp_min_norm(dtheta, J, slack)        # 线性化切空间投影
        return d


# IP-358 ContinualSafetyLedger：双账本 + 影子权重 + 原子提交
class ContinualSafetyLedger:
    def __init__(self, cta, anchors, rho_max,
                 tau_gain=1e-3, tau_stab=2e-2):
        self.cta, self.A, self.rho_max = cta, anchors, rho_max
        self.tau_gain, self.tau_stab = tau_gain, tau_stab
        self.theta = None; self.theta_star = None; self.version = 0

    def propose_and_commit(self, theta, dtheta_sgd, D_new, suite_pass):
        dtheta = self.cta.project(theta, dtheta_sgd, None)
        theta_s = theta + dtheta                        # 影子权重
        G_new = self.err(D_new, theta) - self.err(D_new, theta_s)
        L_anc = max(0.0, max(self.err(a, theta_s) - self.err(a, theta)
                             for a in self.A + self.replay))
        rho_ok = max(self.radius(a, theta_s) for a in self.A) <= self.rho_max
        if G_new >= self.tau_gain and L_anc <= self.tau_stab \
                and rho_ok and suite_pass(theta_s):
            self.theta = theta_s                        # 双缓冲原子切换
            self.theta_star = theta_s
            self.version += 1
            return True
        return False                                    # 回滚（不提交影子）


# 主闭环集成：MetricVoiceGauge-SCAF
def metricvoicegauge_round_10(M, s, obs, ...):
    ctx = mw_default_ctx()
    results = middleware.run_cycle(runners={          # v9 契约中间件
        'DA_ML': ..., 'SPR': ..., 'CAL_FI': ..., 'OTL': ...}, ctx=ctx)

    if current_chunk is None or current_chunk.exhausted:
        current_chunk = chunker.generate_chunk(...)   # v9 AC（含 SAF 预检）

    verdict, k_next = chunker.midchunk_guard(current_chunk, k_exec, live_obs)
    if verdict == 'abort':
        current_chunk.execute_safe_stop_at(k_next)
        current_chunk = None
        a_nom = None
    else:
        a_nom = current_chunk.actions[k_next]

    if a_nom is not None:
        a_safe, status = saf.filter(ctx.state, a_nom, ctx.u_prev)  # P13
        if status == 'infeasible':
            freeze_learning()                          # Level-0
        execute(a_safe)

    # ---- 块边界：持续学习（低频，摊销进预算）----
    if cycle_idx % UPDATE_PERIOD == 0 and not learning_frozen:
        ledger.propose_and_commit(ledger.theta, grad(D_new, ledger.theta),
                                  D_new, suite_pass)

    # ---- 覆盖监控：ACI 违例 ⇒ 回滚认证检查点并膨胀 ρ ----
    if aci_violation_rate() > NU_MAX:
        rollback_to(ledger.theta_star, rho=KAPPA * ledger.rho_star)

    C, spatial_cert, claims, metrics, rewards = M.inherited_v9_path(ctx)
    return C, spatial_cert, claims, metrics, rewards
```

## 4. 推导

**引理 87（鲁棒 DCBF 前向不变性）** 设 ∀t 有 ‖d−d̂_θ‖≤ρ_θ 且 h 为 L_h-Lipschitz，SAF 每步输出满足定义 541 约束。则 x_0∈C ⇒ ∀t, h(x_t)≥0。证明：由 Lipschitz 性 h(x_{t+1}^{true}) ≥ h(f_0(x,u)+d̂_θ) − L_hρ_θ ≥ (1−γ)h(x_t)。归纳得 h(x_t) ≥ (1−γ)^t h(x_0) ≥ 0。∎

**引理 88（SAF 无碰撞与不可行处置）** 若每个执行步 SAF 可行，则 ∀t x_t∈C，机器人半径与 m_safe 已计入 h，故无碰撞。若某步不可行，则 a_stop 的刹停距离 ≤ dist(p,O_t)−m_safe 由定义 534 的 d_stop 保证（与 AC 中止点同一构造），停驻后 h≥0；若连停驻都不可行则触发 Level-0 并记录"不可避免"事件，这是唯一允许的安全违背路径，且其概率被 E573 单独度量。∎

**引理 89（安全保持的持续学习 SPCL）** 在覆盖成立（∀a∈A, ‖d−d̂_θ‖≤ρ_θ）且每次更新满足定义 543 四项判据时，任意长度的更新序列 T_1…T_n 中，SAF 每步约束仍成立，故由引理 87 得全序列前向不变。证明：CSL 的 Δρ_A≤0 保证锚集半径不增；CTA 保证 θ′ 不越出 ρ_max 可行域；suite_pass 保证锚集不变式数值成立；SAF 运行时对任意 θ′ 仍执行定义 542 约束。覆盖在锚集上由判据维持；新域覆盖仅被监控（定义 546），故本引理对锚集无条件、对新域条件于覆盖。∎

**引理 90（遗忘上界与回滚）** 每次提交锚集损失增量 ≤ τ_stab，故 N 次提交后锚集性能退化 ≤ N·τ_stab；一旦套件或 ACI 越过阈值即回滚至 θ*，退化被截断为最近检查点以来的有限和。结合 v9 引理 85 的迟滞，提交事件有限、无抖振。∎

**引理 91（可塑性 ⇒ 保守性单调下降）** 若某次接受更新使新域上 ρ_θ′≤ρ_θ 逐点成立，则定义 542 的可行域 F(θ′) ⊇ F(θ)；最小范数投影到更大凸集上使 ‖a_safe−a^k‖ 不增，故 Cons(θ′)≤Cons(θ)。因此 CSL 收紧 ρ 等价于"更不保守且仍可证明安全"，直到 ρ 触及 ρ_max 下界或任务收益饱和。∎

**引理 92（原子提交与快照一致性）** 定义 544 的双缓冲指针切换使任一 SAF 周期读到的 θ 属于某个完整版本，不存在半更新；影子评估失败不改变可见 θ，故学习失败不引入行为抖动。∎

**引理 93（保守退化序与 v9 严格等价）** SAF 显式关闭 ⇒ Π_id，逐位复现 v9 AC 决策路径；SAF 超时 ⇒ a_stop，其动作集 ⊆ v9 AC 中止点集，故 B(v10)⊆B(v9)；CSL 冻结 ⇒ θ 固定，等价 v9 固定模型；CTA 恒等 ⇒ 无投影更新但仍受账本约束，B ⊆ B(CSL)。由包含关系，v9 的引理 82–86 与九不变式在 v10 全部活动时仍成立（安全性是行为集的下闭性质）。∎

## 5. 复杂度分析

| 组件 | 域 | 时间 | 空间 | 正确性锚 |
|---|---|---|---|---|
| SAF DCBF-QP（50Hz） | 在线 | ≤1.0ms（≤6 约束，热启动） | O(d_u²) | 定义 541/542 |
| SAF HOCBF 扩展 | 在线 | ≤0.2ms 附加 | O(1) | 定义 541′ |
| AC 块生成（5Hz，v9） | 在线 | ≤12ms/次，摊销 ≤1.2ms/cycle | O(n·K·d_a) | v9 |
| CSL 影子评估（块边界，~1Hz） | 在线 | ≤6ms/次，摊销 ≤0.12ms/cycle | O(|A|+|D_new|) | 定义 543/544 |
| CTA 投影 QP | 在线 | ≤0.5ms/次（仅提交时） | O(|A|·d_θ) | 定义 545 |
| ACI 覆盖监控 | 在线 | O(1)/cycle | O(W_window) | 定义 546 |
| v9 继承路径 | 在线 | ≤8ms 典型 / ≤20ms p99 | 不变 | 引理 86 |
| 决策侧合计 | 在线 | 典型 ≤9ms，p99 ≤20ms（SAF≤1ms，CSL 摊销） | — | 引理 86/93 |
| 感知侧合计 | 在线 | ≤2ms（v8 不变） | — | v8 |

## 6. 实验设计 E571–E590

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E571 | 静态障碍避障基线 | 0 碰撞，最小间隙 ≥ d_safe，任务成功率 ≥ v9 |
| E572 | 动态障碍（行人/移动物） | 0 碰撞，紧急制动率 ≤2%，最小间隙 ≥ m_safe |
| E573 | SAF 可行性与执行器饱和 | 可行率 ≥99%；不可行时安全停驻成功 100%，"不可避免"≤0.1% |
| E574 | 不确定半径标定（conformal） | 经验残差落入 ρ 的覆盖率 ≥99% |
| E575 | SAF×AC 联合 | SAF 覆盖后 AC 中止点始终可行，两套 d_stop 一致 |
| E576 | 持续学习适应增益 | 新域残差误差 ↓≥30%，任务指标 ↑≥10% |
| E577 | 灾难性遗忘 | 锚集退化 ≤τ_stab，BWT ≥−2% |
| E578 | 证书保持数值验证 | N=10⁴ 次更新，0 次前向不变式违背 |
| E579 | 安全回归套件 | 漏检 ≤1%，误拒 ≤5% |
| E580 | 可塑性-稳定性 Pareto | 前沿严格优于 EWC/replay 基线 |
| E581 | 对抗/投毒更新 | 恶意更新 100% 被拒或回滚，0 安全违背 |
| E582 | 分布外障碍（未见几何） | ACI 触发膨胀/冻结，0 碰撞，覆盖率监控有效 |
| E583 | 认证检查点回滚 | 覆盖违背检出 ≤2 周期，回滚后安全恢复 ≤1 周期 |
| E584 | 8h 长跑 | 提交次数/回滚率/碰撞=0/算力统计 |
| E585 | 仿真→实物/换机器人 | 适应后性能 ≥80% 仿真水平 |
| E586 | 端到端 RoboCup@Home 仿真 | ≥ v9 + 10% |
| E587 | 消融 SAF/CSL/CTA | 各组件的安全—性能—保守性贡献 |
| E588 | 与 v9 退化等价 | 模块失效日志逐位，行为集 ⊆ v9 |
| E589 | 计算预算 | p99 ≤20ms；SAF ≤1ms；CSL 摊销 ≤0.2ms |
| E590 | 综合竞赛模拟 | ≥ v9 + 15% |

## 7. 预注册判据

| 判据 | 门槛（预注册） | 若未达标的处置 |
|---|---|---|
| 静态避障（E571） | 0 碰撞且间隙达标 | 增大 m_safe、收紧 γ、提高 ρ 安全系数 |
| 动态障碍（E572） | 0 碰撞，急停 ≤2% | 引入速度障碍/HOCBF 相对阶扩展 |
| 可行性（E573） | 可行 ≥99%，停驻 100% | 放宽 Δu_max、增加松弛变量、提前减速 |
| 覆盖标定（E574） | 覆盖 ≥99% | 换 conformal 分位/集成、增大 κ_ρ |
| SAF×AC（E575） | 中止点全可行 | 统一 d_stop 实现、预检候选块 |
| 适应增益（E576） | 残差 ↓≥30% | 增大更新预算、改残差参数化 |
| 遗忘（E577） | BWT ≥−2% | 收紧 τ_stab、扩大 replay/锚集 |
| 证书保持（E578） | 0 违背 | 缩短提交间隔、收紧 CTA 约束 |
| 回归套件（E579） | 漏检 ≤1%，误拒 ≤5% | 重设计套件、增加对抗样本 |
| Pareto（E580） | 优于基线 | 调 τ_gain/τ_stab、改进 CTA 线性化 |
| 投毒（E581） | 0 安全违背 | 加强异常检测、限制更新范数 |
| 分布外（E582） | 0 碰撞 | 增大 ρ 膨胀系数、强制冻结 |
| 回滚（E583） | 检出 ≤2 周期 | 提高 ACI 监测频率、缩短滑窗 |
| 长跑（E584） | 碰撞 0、趋势稳定 | 周期性重标定 ρ、检查漂移 |
| 仿真→实物（E585） | ≥80% 仿真 | 域随机化、增大 m_safe |
| 端到端（E586） | ≥ v9 + 10% | 调 SAF 保守度与学习频率 |
| 消融（E587） | 各组件正贡献 | 归因分析、去掉冗余组件 |
| 退化等价（E588） | 日志逐位且 B⊆v9 | 审计吸收元/恒等元路径 |
| 预算（E589） | p99 ≤20ms | SAF 移独立线程、CSL 降频 |
| 竞赛（E590） | ≥ v9 + 15% | 综合调参、复盘失分 |

## 8. 本轮最大风险

**一句话**：SAF 的鲁棒屏障以不确定半径 ρ 为有效性前提，而持续学习恰在最陌生的障碍分布上更新残差模型；若 conformal 半径在该分布外过度自信（覆盖失效），屏障裕度会被低估，最激进的适应场景正是安全保证最脆弱的场景。
<!-- ARTIFACT:END -->