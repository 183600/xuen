# 玄 · 灵感驱动研究循环

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 10 轮（新灵感循环；本轮灵感：「基准测试」×「场景泛化」）
> **基线**：第 9 轮 MetricVoiceGauge-ACMD（定义 532–539；引理 82–86；实验 E551–E570）。
> 本轮纪律：**测量科学 + 泛化几何 + 单调收紧**。v9 用三个模块还了算力债、集成债、叙事债，却留下两笔新债：**评估债**（“+10%/+15%”建立在一个静态、未分层、可被在线学习污染的测试清单上）与**泛化债**（DA-ML 只能事后反应域偏移，系统从未陈述“性能在哪个场景区域内有界”）。新模块一律设计为**单调收紧算子**——只许缩短块长、唤醒模块、限制动作集；其失效注入**恒等收紧 ⊥**，故严格退回 v9，不引入新失效模式（引理 90）。

## 0. 直觉与动机

**灵感 1（基准测试 → 把测量仪器做成一等公民）**
直觉：一个堆到 17 个 IP 的系统，最脆弱的往往不是控制器，而是“我们凭什么相信它更好”这句话。现有 E551–E570 是静态清单：难例被易例稀释（未分层）、样本量与效应量未预注册（统计功效未知）、在线学习可能早已看过测试分布（污染）。核心创新：**基准锻造器（BenchmarkForge, BF）**——在因子化场景空间上维护自适应采样分布 q_t，把有限 episode 预算集中到“能力边界”（失败邻近度 × 证书不确定度）；同时用**开发/留出族整族隔离 + 承诺哈希账本 + 序贯 α 消耗**保证报告的泛化差距 Ĝ 不被自适应采样自身夸大。BF 的产出不是分数，而是带分层、置信区间、可复现承诺的测量报告。

**灵感 2（场景泛化 → 场景代数与单元证书）**
直觉：v9 的泛化是“检测到偏移就缩短块”，被动且滞后。可陈述的泛化应当是几何的：把场景分解为因子（光照、杂乱度、材质透明性、物体类别、动力学、传感器退化），在因子空间定义距离；在单元（cell）的**锚点网**上实测，若性能对场景是 L-Lipschitz，则单元内部性能有可计算下界。核心创新：**场景代数（ScenarioAlgebra, SA）**——场景 = 因子向量 + 组合语法（family）；证书 = 单元证书 (L̂, ε, δ, 审计样本)；审计违例即**细分单元**（branch-and-bound），得到**已认证区域 R_cert**。R_cert 之外不是“未知但大概没事”，而是**外推 = 无保证**，必须收紧（定义 543/549）。这把“泛化”从口号变成一张可查询、可反驳的区域图。

**灵感 3（测量与泛化的闭环 → 泛化差距监视器）**
直觉：基准若只离线跑，是论文附录；泛化若只离线证，管不住运行中的机器人。需要一个在线、廉价、只收紧不放宽的桥。核心创新：**泛化差距监视器（GeneralizationGapMonitor, GGM）**——用嵌入执行流的 canary 探针（有已知期望结果的小任务）在线估计性能，与单元证书给出的期望下界比较；差距超阈即触发收紧（K_eff↓、全模块唤醒、请求 BF 重采样）。关键的是，外推指示 E(s) 由**当前因子向量即时几何判定**，不依赖 20 帧滑窗——这正是对 v9 遗留风险“DA 滑窗滞后于真实跳变”的结构性回应（引理 91）。

## 1. 研究问题（轮次升级版）

- **Q1（基准有效性）**：自适应采样如何既把预算压在能力边界，又不让被评系统“对着考试复习”（Goodhart）？留出族整族隔离与序贯 α 消耗能把 Ĝ 的偏差与假阳性压到什么程度？
- **Q2（泛化证书可靠性）**：操作任务的性能在场景因子空间上有多 Lipschitz？抓取/接触这类阈值事件的不连续面能否被审计与细分**定位**，还是会产生“锚点全过、内部塌陷”的假安全？
- **Q3（收紧闭环的安全性）**：SA/BF/GGM 作为单调收紧算子，如何形式化保证“中性元 = 恒等 ⇒ 逐位退回 v9”，并在 E(s)、Ĝ、v9 门控三个信号之间不发生抖振？

## 2. 设计原则（在 P10–P12 基础上新增 P13–P15）

**P13 测量隔离律（Benchmark Isolation, BF）**
留出场景族 H 在 t0 承诺哈希入只追加账本；H 永不被 BF 采样、永不被任何在线更新/标定读取（由执行沙箱强制）。任何用于调参/标定/在线学习的场景永久打标 dev。报告必须同时给出 dev 与 held-out 的 Ĝ 及配对置信区间；污染一旦被审计发现，整族作废并公开重承诺。

**P14 场景单元证书律（Cell-Certificate Generalization, SA）**
场景空间带因子距离 d_S；单元 C 以覆盖半径 ε 的锚点网采样；若 J 在 C 上 L-Lipschitz 且估计 L̂ ≥ L，则 ∀s∈C: J(s) ≥ min_{a∈A}J(a) − L̂ε − δ。审计样本违例 ⇒ 细分；无法认证的区域标记未认证，并映射为**外推指示 E(s)=1**（无保证，而非乐观）。

**P15 单调收紧律（Monotone Tightening, GGM/SA）**
新模块只允许收缩可行动作集、缩短 K_eff、唤醒模块、请求重采样；绝不放宽 v9 的任何门控。失效时注入恒等收紧 ⊥（不做任何额外收紧），故 v10 的有效动作集 ⊆ v9 的，安全性由 v9 传递（引理 90）。

## 3. 与基线的接口（如何退化）

- BF 失效 ⇒ 退回 v9 的静态 E551–E570 套件与既定预注册判据（测量退化为清单，结论口径回 v9）；
- SA 失效 ⇒ E(s)≡0、单元证书退化为单个全局未认证单元，不覆盖也不放松 v9 门控，行为 = v9；
- GGM 失效 ⇒ 无在线差距信号，门控完全交回 v9 的 DA/SPR/Cal；
- SA/BF/GGM 与 v9 组件同时失效 ⇒ 先退 v9，再按 v9 五级链退 v7、v6；
- 全部失效 ⇒ 完整退回 MetricVoiceGauge-OTL-GC-ER v7，再退回 v6。

## 4. 预期贡献

1. **基准锻造**：自适应、分层、隔离、序贯有效的评测框架，把“更好”从点估计升级为带承诺与 CI 的可复现命题；
2. **场景代数与单元证书**：用因子几何 + Lipschitz 把泛化变成可查询的已认证区域 R_cert，并诚实标注外推区；
3. **单调收紧闭环**：GGM 把在线性能与证书下界对齐，E(s) 提供不依赖滑窗的外推先导信号，正面回应 v9 遗留风险；
4. **测量—泛化—控制三环**：E571–E590 覆盖分层、污染审计、统计功效、证书健全性、不连续定位、外推先导、Goodhart 轨迹与端到端任务。

## 5. 本轮最大风险

**一句话**：单元证书的健全性以“任务性能在场景因子空间上 Lipschitz 连续”为前提，而抓取/接触成功本质是阈值事件，其不连续面可能藏在透明材质、反光光照或特定抓取角度的孤立面上；若该面恰好落在单元内部而审计样本未命中，锚点全过、证书被判有效，系统就会在“已认证”单元里以 K_eff>1 运行——泛化保证恰在最罕见的灾难样本处失效。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 10 轮产物 · 创新点清单 v10：**MetricVoiceGauge-BSG**（Metric Voice Gauge with Benchmark Science & Scenario Generalization）

> 背景：第 9 轮 MetricVoiceGauge-ACMD（定义 532–539；引理 82–86；实验 E551–E570）。
> 本轮灵感：「基准测试」×「场景泛化」
> **继承纪律**：MetricVoiceGauge 九不变式 + v9 的 AC/MW/ID 三模块原样继承（定义 532–539、引理 82–86）。新增 BF/SA/GGM 一律为**可选增强**且是**单调收紧算子**：失效 ⇒ 注入恒等收紧 ⊥ ⇒ 逐位退回 v9（引理 90），而非行为漂移。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进（相对 MetricVoiceGauge-ACMD v9） |
|---|---|---|---|
| IP-340–356 | v9 全部模块 | 继承 | 语义不变；AC/MW/ID 原样保留 |
| IP-357 | BenchmarkForge 基准锻造器 | 新增核心模块 | 因子化场景空间上的自适应采样 q_t（失败邻近度×证书不确定度）；开发/留出族整族隔离；承诺哈希只追加账本；序贯 α 消耗与配对 CI；输出分层测量报告与 Ĝ |
| IP-358 | ScenarioAlgebra 场景代数与单元证书 | 新增核心模块 | 因子距离 d_S、单元 C 与 ε-锚点网、Lipschitz 单元证书 (L̂,ε,δ,j_min,m)、审计违例细分、已认证区域 R_cert 与外推指示 E(s) |
| IP-359 | GeneralizationGapMonitor 泛化差距监视器 | 新增核心模块 | canary 探针在线性能估计 Ĵ_canary；与证书下界比较得 Ĝ(t)；超阈触发**单调收紧** T（K_eff←1、全模块唤醒、动作集限制） |

**退化链声明（v10 契约化六级）：**
- Level-0（新增，最外层收紧）：E(s)=1 ∨ Ĝ>τ_gap ∨ 审计违例率>τ_audit ⇒ 强制 K_eff←1、全模块唤醒、动作集限制到已认证邻域；只能收紧，先于 v9 门控生效；
- Level-1：AC 证书失效或信任域破坏（Δ_dom ≥ τ_dom ∨ risk_SLAM ≥ τ_SLAM）⇒ K_eff ← 1，等价 v8 决策粒度（v9 继承）；
- Level-2：MW 失效 ⇒ 切换 v8 手写网关代码路径，等价 v8 集成方式；
- Level-3：ID 失效 ⇒ 全模块 active、归因冻结，等价 v8 全模块常开；
- Level-4：v8 的 DA/SPR/Cal 任一失效 ⇒ 中立元注入（Δ_dom≡0 / risk_SLAM≡0 / sensor_weight≡1），等价 v7；
- Level-5：全失效 ⇒ 完整退回 MetricVoiceGauge-OTL-GC-ER v7，再退回 v6。

## 1. 符号体系增量（定义 540–549）

| 符号 | 含义 |
|---|---|
| s ∈ S, φ(s) ∈ ∏F_i | 场景与因子映射（光照/杂乱度/透明性/类别/动力学/传感器退化） |
| d_S(s,s') | 加权因子距离，跨组合语法族另加常数下界 w_fam |
| family(s) | 场景语法族标识（组合产生式 id），留出集按整族切分 |
| C = ∏[a_i,b_i] | 因子空间中的单元（超矩形） |
| A_ε(C), ε(C) | 单元 C 的 ε-锚点网与覆盖半径 sup_s min_a d_S(s,a) |
| cert_C = (L̂,ε,δ,j_min,m) | 单元泛化证书：Lipschitz 估计、覆盖半径、样本误差、锚点最小性能、审计样本数 |
| R_cert, E(s) | 已认证区域（有效单元并集）与外推指示 1[s∉R_cert] |
| q_t, u_t, β_B, ρ | 自适应采样分布、边界度、逆温系数、单族质量上限 |
| H, h0, Ledger | 留出族集合、承诺哈希、只追加审计账本 |
| Ĝ, CI, α_k | 泛化差距 J_dev−J_H、置信区间、第 k 次中期分析的 α 消耗 |
| canary, Ĵ_canary, τ_gap, τ_audit | canary 探针、在线性能估计、差距阈、审计违例率阈 |
| T, ⊥ | 单调收紧算子与恒等收紧（不做额外限制） |

**新增定义 540（场景因子空间与距离）** 场景 s 由因子向量 φ(s)=(f_1,…,f_n)∈∏F_i 与族 g(s)∈G 表示。距离：
```
d_S(s,s') = Σ_i w_i·d_i(f_i,f'_i) + w_fam·1[g(s)≠g(s')],   Σ_i w_i + w_fam = 1,  d_i∈[0,1]
```
w_fam 取足够大使任意跨族距离 ≥ d_fam。d_i 对连续因子用归一化差，对类别因子用 0/1 或语义树距离。距离是 SA 全部证书的唯一度量前提。

**新增定义 541（场景单元与锚点网）** 单元 C=∏_i[a_i,b_i]；锚点网 A_ε(C)⊂C 满足覆盖半径 ε(C)=sup_{s∈C} min_{a∈A} d_S(s,a) ≤ ε。构造采用每因子 κ 分位格点 + 对角补充（预算 O(nκ)），对高维用因子重要度剪枝；ε 为理论上界，不依赖采样。

**新增定义 542（单元泛化证书 CellCertificate）** 设性能 J 在 C 上对 d_S 为 L-Lipschitz，L̂_C ≥ L 为经验估计（锚点对差商取最大并加先验下限），δ_C 为有限样本误差（Hoeffding：δ=√(ln(1/α)/(2m))）。则证书声明
```
∀s∈C:  J(s) ≥ j_min(C) − L̂_C·d_S(s, A_ε(C)) − δ_C,   j_min(C)=min_{a∈A} J(a)
```
证书**有效** ⇔ 独立审计集 Audit(C)（不落在锚点网上）中所有 s′ 满足下式；任一违例 ⇒ 沿违例密度最高的因子二分（branch-and-bound），违例子单元标记**未认证**。

**新增定义 543（已认证区域与外推指示）** R_cert = ∪_{cert_C valid} C。外推指示 E(s)=1[s∉R_cert]，由空间索引 O(log N_cell) 查询。关键区别于 DA：E(s) 由当前因子向量**当帧几何判定**，无滑窗滞后；E(s)=1 表示“此处无泛化保证”，不是“此处一定失败”。未认证单元（含违例）同样计入 E=1。

**新增定义 544（自适应基准分布）** 单元权重
```
q_t(C) ∝ exp(β_B·u_t(C))·w_task(C),   u_t(C)=max(近失败度(C), 证书不确定度(C))
```
近失败度由最近观测失败场景的核密度给出（距离越近越大）；证书不确定度取 δ_C 或预测方差。每 T_bf=50 episode 重加权；单族质量上限 ρ=0.3，防止采样退化为“只考一族”。

**新增定义 545（承诺账本与污染隔离）** 留出族 H 在 t0 计算 h0=SHA256(serialize(sorted(H))⊕salt) 写入只追加账本。规则：任何进入在线更新/β 标定/K_max 调参/BF 采样的场景永久打标 dev；H 在最终评估前对系统不可见（执行沙箱强制）。报告 Ĝ=J_dev−J_H 与配对自助 95% CI；审计若发现 H 场景出现在 dev 路径 ⇒ 整族作废、公开重承诺。

**新增定义 546（序贯有效统计）** 自适应采样使固定样本检验失效，故采用 α-spending 的序贯检验：第 k 次中期分析分配 α_k（O’Brien–Fleming 型），Σα_k≤α=0.05；任意时刻报告有效 CI。最小可检测效应 MDE 预注册，n_min 由配对方差与 power=0.8 反解。

**新增定义 547（canary 探针与在线性能估计）** 按泊松过程在执行流中注入有已知正确结果的廉价探针（如“回到已知位姿”“确认抓取点可见性”），期望结果 r* 与场景无关。Ĵ_canary(t) = 最近 T_c 窗口探针成功率；作为当前场景性能下界代理。

**新增定义 548（泛化差距与单调收紧）** Ĝ(t) = Ĵ_cert_lower(t) − Ĵ_canary(t)。触发收紧当
```
E(s)=1  ∨  Ĝ(t) > τ_gap  ∨  audit_viol_rate(t) > τ_audit
```
收紧 T：K_eff←1；ID 全模块唤醒；动作集限制到 R_cert 内最近已认证配置的邻域；向 BF 请求该单元优先采样。T 只收缩可行集；⊥=identity。

**新增定义 549（认证区域与 v9 门控的合成）** v10 的有效块长是 v9 门控与收紧信号的**合取**（只会更保守）：
```
K_eff^v10(t) = 1                         若 E(s_t)=1 ∨ tighten(t)
             = K_eff^v9(t)               否则
```

## 2. 形式化定义（要点与升级）

**定义 493/495/521/532–539** 继承 v9 不变。
**升级定义 496（软证书，v10）** δ_trigger 增至七条件：σ<τ_safe ∧ γ_grasp valid ∧ Δ_dom<τ_dom ∧ risk_SLAM<τ_SLAM ∧ Ĉ_t valid ∧ **E(s)=0** ∧ **Ĝ≤τ_gap**。后两条只增加否决，不增加放行，故保持“软通过必不掩盖硬失”（引理 87+82 联合）。
**升级定义 539（有效块长，v10）** 按定义 549 与 v9 门控取合取；仅当 SA/GGM 均不可用时自动退化为 v9 门控。
**升级定义 531（软硬约束衔接）** 块级入口增加外推入口：E(s)=1 立即触发 M₀ 硬检查与安全停驻，不等块边界。

## 3. 关键算法骨架

```python
# IP-357 BenchmarkForge：基准锻造器（重活离线/异步，主环只读）
class BenchmarkForge:
    def __init__(self, grammar, metric, heldout_families,
                 beta_B=2.0, rho=0.3, T_bf=50, alpha=0.05):
        self.grammar, self.d = grammar, metric
        self.H = frozenset(heldout_families)
        self.h0 = sha256(serialize(sorted(self.H)) + SALT)
        self.ledger = AppendOnlyLedger(); self.ledger.append(('commit', self.h0))
        self.beta_B, self.rho, self.T_bf, self.alpha = beta_B, rho, T_bf, alpha
        self.q = None

    def update_weights(self, cells, failures, cert_uncertainty):
        w = {C: math.exp(self.beta_B * max(near_failure(C, failures, self.d),
                                          cert_uncertainty[C]))
             for C in cells}
        w = cap_family_mass(w, self.rho)          # 单族占比 ≤ ρ
        self.q = normalize(w)

    def sample_batch(self, n):
        out = []
        while len(out) < n:
            C = sample_from(self.q)
            s = self.grammar.sample_in(C)
            if s.family in self.H:                 # 硬隔离：留出族永不被采样
                continue
            s.tag = 'dev'; out.append(s)
        return out

    def report(self, J_dev, J_H):
        G = mean(J_dev) - mean(J_H)
        lo, hi = paired_bootstrap_ci(J_dev, J_H, alpha=self.alpha)
        return Report(G=G, ci=(lo, hi), strata=by_factor_slice(J_dev),
                      commitment=self.h0)
```

```python
# IP-358 ScenarioAlgebra：场景代数与单元证书（离线/异步构建，在线只查 E）
class ScenarioAlgebra:
    def __init__(self, factors, metric, L_prior=1.0, eps=0.1, delta=0.02):
        self.factors, self.d = factors, metric
        self.L_prior, self.eps, self.delta = L_prior, eps, delta
        self.cells = [UnitCell(domain=full_domain(factors))]

    def certify(self, C, J, audit):
        A, eps = lattice_net(C, self.eps, self.d)
        jmin = min(J(a) for a in A)
        Lhat = max(self.L_prior, max_pairwise_slope(J, A, self.d))
        lower = lambda s: jmin - Lhat * self.d(s, nearest(A, s, self.d)) - self.delta
        bad = [s for s in audit if J(s) < lower(s)]
        if not bad:
            return Cert(C, Lhat, eps, self.delta, jmin, len(audit), valid=True)
        return Cert(C, Lhat, eps, self.delta, jmin, len(audit), valid=False), bad

    def refine(self, C, bad):
        f = argmax_factor_violation(bad)           # 违例最集中的因子
        return bisect(C, f)                        # 违例子单元保持未认证

    def E(self, s):
        return 0 if any(c.valid and s in c.C for c in self.cells) else 1

    def certified_lower(self, s):
        c = nearest_valid_cell(s)
        return c.jmin - c.Lhat * self.d(s, nearest(c.A, s, self.d)) - c.delta
```

```python
# IP-359 GeneralizationGapMonitor：在线差距与单调收紧
class GeneralizationGapMonitor:
    def __init__(self, sa, tau_gap=0.10, tau_audit=0.02, T_c=250):
        self.sa, self.tau_gap, self.tau_audit, self.T_c = sa, tau_gap, tau_audit, T_c

    def step(self, t, s, j_canary, audit_viol_rate):
        gap = self.sa.certified_lower(s) - j_canary
        active = (self.sa.E(s) == 1 or gap > self.tau_gap
                  or audit_viol_rate > self.tau_audit)
        return TightenSignal(active=active, gap=gap,
                             reason=('extrapolation' if self.sa.E(s) else
                                     'gap' if gap > self.tau_gap else 'audit'))
```

```python
# 主闭环集成：MetricVoiceGauge-BSG（只增加收紧，不放宽任何 v9 门控）
def metricvoicegauge_round_10(M, s, obs, audio_stream=None, ell=None, ...):
    ctx = mw_default_ctx()
    results = middleware.run_cycle(runners={          # v9 感知侧，原样
        'DA_ML':  lambda c: domain_adapter.update_and_measure(obs),
        'SPR':    lambda c: slam_risk.compute(M.slam_backend.get_latest_state()),
        'CAL_FI': lambda c: calib_fi.get_weights_kappa(),
        'OTL':    lambda c: online_learner.update_and_thresholds(c),
    }, ctx=ctx)

    # ---- 在线收紧查询（≤0.1ms；SA/BF 重活在离线/异步线程）----
    s_now = factorize(obs)                            # 当前因子向量
    E_s = sa.E(s_now)                                 # 定义 543，无滑窗
    tighten = ggm.step(cycle_idx, s_now, j_canary(), audit_viol_rate())
    trust_v9 = (ctx.delta_dom < M.tau_dom and ctx.risk_slam < M.tau_slam)

    # ---- P15：与 v9 门控合取，只能更保守 ----
    if E_s or tighten.active or not trust_v9:
        K = 1
    else:
        K = chunker.effective_K(ctx.delta_dom, M.tau_dom, trust_v9)
    if tighten.active:
        distiller.wake_all()                          # 陌生域强制全唤醒
        action_mask = sa.safe_action_neighborhood(s_now)
    else:
        action_mask = ALL_ACTIONS

    # ---- v9 块生成 / 中块守卫 / 继承路径，均带 action_mask ----
    ...  # 与 v9 metricvoicegauge_round_9 相同，仅动作采样受 mask 限制
    return C, spatial_cert, claims, metrics, rewards
```

## 4. 推导

**引理 87（单元证书的 Lipschitz 下界）** 设 J 在单元 C 上对 d_S 为 L-Lipschitz，A 为 ε-锚点网，δ 为概率 ≥1−α 的有限样本误差上界。则概率 ≥1−α 下 ∀s∈C：J(s) ≥ min_{a∈A}J(a) − L·ε − δ；用 L̂≥L 替换 L 仍成立。证明：取 a*=argmin_{a∈A}d_S(s,a)，则 d_S(s,a*)≤ε，由 Lipschitz 性 J(s) ≥ J(a*)−L d_S(s,a*) ≥ min_A J − Lε；再扣样本误差 δ。L̂≥L 时右侧更小，界仍有效。∎

**引理 88（细分只保证“可认证区域”健全，不保证“不连续面”可检测）** 若 J 在 C 上连续且存在有效 L 界，则对任意 ε′>0，有限次细分后保留单元直径 <ε′，R_cert 上证书健全。但若 C 内含 J 的不连续面 Σ，且锚点与审计样本全落在 Σ 的同一侧，则 cert_C 可被错误判为 valid（假安全）：取 J 在 C\Σ 上为常数、跨 Σ 跳变即可构造。故 SA 的保证是**条件性**的；P14/P15 以“未认证即收紧”把不可证区域转为保守行为，但不能把假安全概率降为 0——这正是本轮最大风险。∎

**引理 89（隔离下的 Ĝ 偏差来源）** 若 H 未进入 BF 采样、在线更新、β 标定与 K_max 调参路径（沙箱 + 账本可审计强制），则 J_H 的样本分布与 dev 自适应采样策略无关；因此 Ĝ 的偏差只来自“声明族分布 vs 真实部署分布”的定义差异，自适应采样只改变 Var(Ĝ)、不改变 E[J_H]。故 Goodhart 被结构性阻断（依赖隔离实现无旁路；E574 用泄漏注入检验）。∎

**引理 90（单调收紧保持 v9 安全域，中性元逐位退回）** T 为收缩算子：Admissible(T(x))⊆Admissible(x)，且 T 只可能令 K_eff 减小、唤醒集合增大、动作集减小。故 v9 引理 80–86 的不变式在 T 的像上保持；⊥=identity ⇒ T(x)=x。因此 SA/BF/GGM 任一失效时系统逐位等价 v9，不新增失效模式。∎

**引理 91（外推指示对渐变边界漂移的先导性）** 设场景沿因子空间连续漂移并在 t* 越过 R_cert 边界。因子向量由单帧观测解析，E(s) 在 t*+δ_φ（δ_φ≤1 控制周期）翻转。v9 的 Δ_dom 为 W_dom=20 帧滑窗统计；对渐变漂移，其越阈确认时刻 t_DA ≥ t*+W_dom·Δt（需滑窗累积）。故 t_DA−(t*+δ_φ) ≥ W_dom·Δt−δ_φ ≈ 380ms。对**突变**，DA 单帧统计量可能同样快，此时两信号为 OR 互补而非替代。∎

## 5. 复杂度分析

| 组件 | 域 | 时间 | 空间 | 正确性锚 |
|---|---|---|---|---|
| BF 自适应采样/报告 | 离线/异步 | 每 T_bf=50 episode 重权 O(\|cells\|)；报告 O(n_boot·n) | O(\|cells\|) | 定义 544–546 |
| SA 证书构建/细分 | 离线/异步 | 锚点 O(nκ) 次 rollout + 细分 O(log(1/ε)) 层 | O(Σ cells) | 定义 541/542, 引理 87/88 |
| E(s) 查询 | 在线 | O(log N_cell)（单元空间索引） | O(N_cell) | 定义 543 |
| GGM 在线 | 在线 | O(1)/cycle；canary 每 T_c=250 周期 | O(1) | 定义 547/548 |
| v10 新增在线开销 | 在线 | ≤0.1ms（查询+比较） | — | 引理 90/91 |
| v9 继承路径 | 在线 | ≤8ms 典型 / ≤20ms p99（不变） | — | v9 引理 86 |
| 50Hz 守恒 | 在线 | 重活全离线/异步，主环预算 20ms 不变 | — | v9 引理 86 + 本轮 |

## 6. 实验设计 E571–E590

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E571 | 基准分层有效性 | 分层难度单调；相邻层成功率差 ≥15pp |
| E572 | 自适应 vs 静态（等预算） | 每 100 episode 发现失败数 ↑≥2× |
| E573 | 留出族整族切分的 Ĝ 稳定性 | 重复切分间 Ĝ 波动 ≤10% |
| E574 | 污染注入审计 | 注入泄漏检出率 ≥95%，Ĝ 被标红而非照报 |
| E575 | 统计功效与 CI 覆盖 | 95% CI 实际覆盖 ≥93%，MDE 达预注册值 |
| E576 | Lipschitz 估计标定 | 信任域内 L̂≥L 的经验比例 ≥99% |
| E577 | 不连续面定位（透明/反光） | 未认证单元召回 ≥90%，假安全 ≤1% |
| E578 | 细分收敛与预算 | ε 减半所需审计样本增长符合理论阶 |
| E579 | 认证区域覆盖率 vs 锚点数 | 达 90% 覆盖所需锚点预算 ≤ 上限 |
| E580 | 外推先导时间 | 渐变漂移下 E 领先 DA ≥300ms（引理 91） |
| E581 | GGM 灵敏度/误报 | 触发召回 ≥95%，误报 ≤5% |
| E582 | Goodhart 轨迹 | 仅 dev 优化时 J_H 不降；若降则审计报警 |
| E583 | 泛化差距-因子距离曲线 | 随距离单调不增，拐点可解释 |
| E584 | 跨族零样本 | 留出族成功率 ≥ dev −15% |
| E585 | SA 失效 → v9 等价 | E(s)≡0，日志逐位等价 |
| E586 | BF 失效 → 静态套件等价 | 报告口径与 v9 E551–E570 一致 |
| E587 | 基准在环端到端 | 无 overfit 迹象且 ≥ v9 |
| E588 | 在线开销 | 新增 ≤0.1ms，50Hz 0 丢拍 |
| E589 | 单元内对抗场景生成 | 找到证书违例样本 ≤N 次查询 |
| E590 | 综合竞赛模拟 | ≥ v9 +10% 且 held-out 不塌 |

## 7. 预注册判据

| 判据 | 门槛（预注册） | 若未达标的处置 |
|---|---|---|
| 分层（E571） | 层间成功率差 ≥15pp | 调整分层因子/难度定义 |
| 自适应效率（E572） | 等预算失败发现 ↑≥2× | 调 β_B、ρ、近失败核宽 |
| Ĝ 稳定（E573） | 波动 ≤10% | 增大留出族数/样本量 |
| 污染审计（E574） | 检出 ≥95% | 强化沙箱、账本哈希链 |
| 统计有效（E575） | CI 覆盖 ≥93% | 修正 α-spending、增大 n |
| Lipschitz 标定（E576） | L̂≥L 比例 ≥99% | 增大先验 L、加密锚点 |
| 不连续定位（E577） | 召回 ≥90%、假安全 ≤1% | 提高审计密度、按敏感因子加密 |
| 细分收敛（E578） | 增长符合理论阶 | 改二分策略/因子排序 |
| 覆盖率（E579） | 90% 覆盖在预算内 | 因子降维/重要度剪枝 |
| 外推先导（E580） | 领先 ≥300ms | 提高因子解析频率、边界缓冲 |
| GGM（E581） | 召回 ≥95%、误报 ≤5% | 调 τ_gap/τ_audit/T_c |
| Goodhart（E582） | J_H 不随 dev 优化下降 | 隔离实现审计、冻结 H |
| 差距曲线（E583） | 单调不增 | 重定义 d_S 权重 |
| 跨族（E584） | ≥ dev−15% | 扩展训练族、改 SA 锚点 |
| SA 等价（E585） | 逐位等价 | 审计 E(s) 与动作 mask 路径 |
| BF 等价（E586） | 口径一致 | 恢复静态套件为默认 |
| 基准在环（E587） | 无 overfit 且 ≥v9 | 冻结 H、缩短 dev 复用 |
| 在线开销（E588） | ≤0.1ms、0 丢拍 | 索引换缓存、异步化 |
| 对抗生成（E589） | 违例样本 ≤N 查询 | 引入梯度/贝叶斯优化 |
| 竞赛（E590） | ≥v9+10% 且 held-out 不塌 | 综合调参、分析失分瓶颈 |

## 8. 本轮最大风险

**一句话**：单元证书的健全性以“任务性能在场景因子空间上 Lipschitz 连续”为前提，而抓取/接触成功本质是阈值事件，其不连续面可能藏在透明材质、反光光照或特定抓取角度的孤立面上；若该面恰好落在单元内部而审计样本未命中，锚点全过、证书被判有效，系统就会在“已认证”单元里以 K_eff>1 运行——泛化保证恰在最罕见的灾难样本处失效。
<!-- ARTIFACT:END -->
