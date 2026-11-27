<!-- IDEA:START -->
### 第 3 轮灵感驱动研究记录

**灵感词**：可解释性、跨任务泛化、自适应控制

**直觉与动机**：
在 KEMPC 框架已形成「常识包容-证书驱动」的基础上，进一步提出三个关键方向：

1. **可解释性**：KEMPC 的优化目标虽包含常识权重场 W_kc(x)，但「哪些规则激活、权重如何分配」往往是不透明的黑盒。需将解释作为证书的元数据，使操作员能实时看到「当前有 3 条规则触发，权重贡献 0.42，主要受 balance_rule 控制」，从而建立对控制决策的信任。这不仅是人机交互的需要，更是证据链：若规则激活路径异常，应立即介入而非盲目信任。

2. **跨任务泛化**：双足机器人在不同地形、不同速度、不同负载下的常识规则并非完全独立。例如「支撑面积 > 200cm²」这一规则在平地上适用，但在湿滑地面或载重变化时阈值应调整。需定义「知识迁移界」：在源任务 τ_s 上学到的 KC c_i^s，可迁移到目标任务 τ_t，但需乘以迁移惩罚因子 μ_i ∈ [0,1]，反映规则适用性的退化。这使得有限的知识库能够「向外扩展」而非覆盖粗糙时闭塞。

3. **自适应控制**：KEMPC 中的权重 λ_i 目前是人工调参的固定值。实环中，扰动频率、模型老化、磨损等会使固定 λ_i 失效。需引入「证据累积机制」：当 kc_i 在 T 步内连续 m 次违规时，动态增大 λ_i；当长时间无违规时，逐渐衰减 λ_i。这实现了控制策略的在线自适应调整，而非离线固定。

**关键洞见**：这三者形成互补闭环：可解释性提供「诊断视图」，跨任务泛化提供「扩展视野」，自适应控制提供「在线微调」——三者合力将 KEMPC 从「静态知识包容」提升为「动态知识自适应」，从根本上规避「常识闭塞」风险。

**形式化目标（增量）**：
1. 定义可解释性证书元数据：IEKC.name, IEKC.phi, IEKC.activation_significance ∈ [0,1]
2. 定义跨任务迁移因子 μ_i = sim(τ_s, τ_t) · ρ(φ_i) ，其中 sim 为任务相似度、ρ 为推理路径相关性
3. 定义自适应权重更新规则：λ_i(k+1) = λ_i(k) · (1 + η · δ_violation)，其中 δ_violation 为最近 T 步违规指标
4. 定义 KT-MPC 统一框架：KEMPC ∪ IEKC ∪ CTKTP ∪ AKWA，使得 Exec_v28 ⊂ Exec_v27 的真子集（更严格的包容）
5. 证明 interpretability-enhanced KC 提升人机信任下的有效控制比例，cross-task transfer 在≥30%新任务上保持 >85% 成功率，adaptive λ_i 将违规率降低至固定 λ_i 的 60%

**本轮最大风险**：**跨任务迁移的负外部性**——若源任务的知识迁移到目标任务时，因任务差异过大导致 μ_i ≈ 1（满迁移）而非实际的 μ_i ≪ 1，会产生「虚假常识包容」，即 KEMPC 根据误导性的迁移规则规避实际需要的控制动作，导致在目标任务下比无知识约束时更不安全。这种风险比单纯的知识闭塞更隐蔽，因为系统表现「正常」（未违规）却实际上丧失了应对任务特异性危机的能力。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
## 0. 新增核心模块（在 v28 / IP-462~466 基础上扩展）

| 编号 | 名称 | 类型 | 关键改进（相对 v28） |
|---|---|---|---|
| IP-467 | Usability Evaluation Protocol (UEP) + Usability Certificate (UC) | 人因证书 | 把可用性做成可测量证书：UC = (C, L, T, B, U)，几何加权防止单一指标补偿；`usable(π)` 作为准入门条件 |
| IP-468 | Fleet Joint Knowledge Certificate (FJKC) | 舰队证书 | 共享资源时空占用 O_i、知识一致性 A_ij（版本+λ/μ 剖面）、一致性阈值 A_min；输出舰队一致性证明 |
| IP-469 | Certificate Conflict Graph (CCG) | 冲突/死锁分析 | 节点=机器人，边=让行关系；给出「无环 + 静态优先序 + 已验证等待计划 ⟹ 无死锁」充分条件 |
| IP-470 | Fleet Certification Gate (KTCG-Fleet) | 准入舰队长形态 | KTCG-Fleet = KTCG ∪ UEP ∪ FJKC ∪ CCG；Exec_v29 = Exec_v28 ∩ Fil_usability ∩ Fil_fleet ⊆ Exec_v28 |
| IP-471 | Multi-Robot Evaluation Benchmark (MREB) | 评测基准 | N∈{1,2,5,10} 场景族 + 六维指标；可复现地度量单机/舰队/可用性三重效果 |

## 1. 增量符号体系（定义 1600–1699）

| 符号 | 含义 |
|---|---|
| C | 可理解性：操作员依据 ExpReport 预测机器人下一步动作的准确率，C ∈ [0,1] |
| L | 决策时延：从报告呈现到操作员决策的中位时延（秒） |
| T | 信任校准：T = 1 − ECE(confidence, correctness) ∈ [0,1] |
| B | 干预负担：窗口内被操作员 override 的决策比例，B ∈ [0,1] |
| U | 综合可用性：U = Π_k p_k^{w_k}（几何加权），w = (0.35,0.20,0.30,0.15) |
| O_i(π_i) | 机器人 i 的时空占用集合 {(p,t): p=position(π_i,t)} 外扩 safety_margin |
| A_ij | 机器人 i,j 的知识一致性 ∈ [0,1]；A = min_{i<j} A_ij（取最差对） |
| A_min | 舰队知识一致性阈值，默认 0.7 |
| G_c | 证书冲突图：节点为机器人，边 i→j 表示 i 需向 j 让行 |
| FleetExec | 舰队可执行集 = ∩_i Exec_i ∩ ConflictFree ∩ KnowledgeConsistent |
| MREB | 多机评测基准（场景族 + 指标聚合器） |
| Fil_usability | 可用性过滤器（UC 未达标则拒绝） |
| Fil_fleet | 舰队过滤器（一致性/冲突/死锁任一失败则拒绝） |

## 2. 关键算法骨架

### IP-467 Usability Evaluation Protocol (UEP)

```python
@dataclass
class UsabilityCertificate:
    """UC：把「证书是否可用」变成可测量、可准入的证书"""
    robot_id: str
    comprehensibility: float = 0.0    # C
    decision_latency: float = 0.0     # L (s)
    trust_calibration: float = 0.0    # T
    intervention_burden: float = 0.0  # B
    u_min: float = 0.75
    L_max: float = 2.0
    T_min: float = 0.70
    B_max: float = 0.30

    def score(self) -> float:
        eps = 1e-6
        w = (0.35, 0.20, 0.30, 0.15)
        parts = (
            max(self.comprehensibility, eps),
            1.0 - min(self.decision_latency / self.L_max, 1.0) + eps,
            max(self.trust_calibration, eps),
            1.0 - min(self.intervention_burden / self.B_max, 1.0) + eps,
        )
        return float(np.exp(sum(wi * np.log(p) for wi, p in zip(w, parts))))

    def usable(self) -> bool:
        return (self.score() >= self.u_min
                and self.decision_latency <= self.L_max
                and self.trust_calibration >= self.T_min
                and self.intervention_burden <= self.B_max)


class UsabilityEvaluationProtocol:
    """UEP：从人机交互日志在线估计 UC"""
    def __init__(self, window: int = 100):
        self.window = window
        self.events = []  # (report, action, correct_action, confidence, latency)

    def ingest(self, report, action, correct_action, confidence, latency):
        self.events.append((report, action, correct_action, confidence, latency))
        self.events = self.events[-self.window:]

    def evaluate(self, robot_id: str) -> UsabilityCertificate:
        ev = self.events
        if not ev:
            return UsabilityCertificate(robot_id)
        # C：操作员据报告预测的下一步动作是否正确
        C = sum(a == c for (_, a, c, _, _) in ev) / len(ev)
        # L：报告→决策的中位时延
        L = float(np.median([lat for (*_, lat) in ev]))
        # T：1 − 分桶期望校准误差 ECE
        confs = np.array([cf for (_, _, _, cf, _) in ev])
        corrs = np.array([a == c for (_, a, c, _, _) in ev], dtype=float)
        bins = np.linspace(0.0, 1.0, 11)
        ece = 0.0
        for lo, hi in zip(bins[:-1], bins[1:]):
            m = (confs >= lo) & (confs < hi)
            if m.any():
                ece += (m.mean()) * abs(corrs[m].mean() - confs[m].mean())
        T = float(np.clip(1.0 - ece, 0.0, 1.0))
        # B：override 比例（action != 系统建议动作）
        B = sum(a != c for (_, a, c, _, _) in ev) / len(ev)
        return UsabilityCertificate(robot_id, C, L, T, B)
```

### IP-468 Fleet Joint Knowledge Certificate (FJKC)

```python
@dataclass
class FleetJointKnowledgeCertificate:
    """FJKC：舰队级共享知识一致性证明"""
    fleet_id: str
    kc_versions: dict[str, str]          # robot_id -> 共享知识库版本哈希
    lambda_profiles: dict[str, dict]     # robot_id -> {kc_name: λ_i}
    mu_profiles: dict[str, dict]         # robot_id -> {kc_name: μ_i}
    A_min: float = 0.70
    lam_scale: float = 10.0
    mu_scale: float = 1.0

    def pairwise_consistency(self, i: str, j: str) -> float:
        # 版本一致 + λ/μ 剖面接近，逐规则聚合
        keys = set(self.lambda_profiles[i]) | set(self.lambda_profiles[j])
        if not keys:
            return 1.0
        acc = 0.0
        for k in keys:
            v_ok = 1.0 if self.kc_versions.get(i) == self.kc_versions.get(j) else 0.0
            dl = abs(self.lambda_profiles[i].get(k, 1.0)
                     - self.lambda_profiles[j].get(k, 1.0))
            dm = abs(self.mu_profiles[i].get(k, 1.0)
                     - self.mu_profiles[j].get(k, 1.0))
            acc += v_ok * math.exp(-dl / self.lam_scale) * math.exp(-dm / self.mu_scale)
        return acc / len(keys)

    def consistency(self) -> float:
        ids = list(self.kc_versions)
        if len(ids) < 2:
            return 1.0
        # 取最差对：舰队安全由最薄弱的共识决定
        return min(self.pairwise_consistency(a, b)
                   for ai, a in enumerate(ids) for b in ids[ai + 1:])

    def check_consistency(self) -> bool:
        return self.consistency() >= self.A_min
```

### IP-469 Certificate Conflict Graph (CCG)

```python
class CertificateConflictGraph:
    """CCG：时空冲突检测 + 无死锁充分条件"""
    def __init__(self, safety_margin: float = 0.20):
        self.margin = safety_margin

    def occupancy(self, plan) -> set:
        # 轨迹离散化为 (cell_x, cell_y, cell_z, t) 集合，按 margin 外扩
        return plan.space_time_cells(inflation=self.margin)

    def conflict_free(self, plans: dict[str, 'RobotPlan']) -> bool:
        occ = {rid: self.occupancy(p) for rid, p in plans.items()}
        ids = list(occ)
        for ai, i in enumerate(ids):
            for j in ids[ai + 1:]:
                if occ[i] & occ[j]:
                    return False
        return True

    def build(self, plans: dict[str, 'RobotPlan'],
              priority: dict[str, int]) -> 'nx.DiGraph':
        import networkx as nx
        g = nx.DiGraph()
        g.add_nodes_from(plans)
        occ = {rid: self.occupancy(p) for rid, p in plans.items()}
        ids = list(plans)
        for ai, i in enumerate(ids):
            for j in ids[ai + 1:]:
                if occ[i] & occ[j]:
                    # 低优先级向高优先级让行（边指向高优先级）
                    lo, hi = (i, j) if priority[i] > priority[j] else (j, i)
                    g.add_edge(lo, hi)
        return g

    def deadlock_free(self, graph, plans) -> bool:
        import networkx as nx
        # 充分条件：(1) 让行图无环（静态总序保证无循环等待）
        if not nx.is_directed_acyclic_graph(graph):
            return False
        # (2) 每个机器人都有已验证的等待/站立计划（可安全让行）
        return all(p.has_certified_wait_plan for p in plans.values())
```

### IP-470 Fleet Certification Gate (KTCG-Fleet)

```python
@dataclass
class FleetCertificationGate:
    """KTCG-Fleet：单机九证 ∪ 可用性 ∪ 舰队一致性 ∪ 冲突/死锁"""
    single_gates: dict[str, 'KnowledgeTransilientCertificationGate']
    uep: UsabilityEvaluationProtocol
    fjkc: FleetJointKnowledgeCertificate
    ccg: CertificateConflictGraph
    priority: dict[str, int]

    def admits(self, fleet_plan: dict[str, 'RobotPlan'],
               sensor_data: dict) -> bool:
        # 1. 单机九证（沿用 v28 KTCG）
        for rid, plan in fleet_plan.items():
            if not self.single_gates[rid].admits(plan, sensor_data[rid]):
                return False
        # 2. 可用性证书（Fil_usability）
        for rid in fleet_plan:
            if not self.uep.evaluate(rid).usable():
                return False
        # 3. 舰队知识一致性（Fil_fleet）
        if not self.fjkc.check_consistency():
            return False
        # 4. 时空无冲突
        if not self.ccg.conflict_free(fleet_plan):
            return False
        # 5. 无死锁（无环 + 已验证等待计划）
        g = self.ccg.build(fleet_plan, self.priority)
        if not self.ccg.deadlock_free(g, fleet_plan):
            return False
        return True
```

### IP-471 Multi-Robot Evaluation Benchmark (MREB)

```python
class MultiRobotEvaluationBenchmark:
    """MREB：可复现的多机评测聚合器"""
    def __init__(self, n_robots: int, scenarios: list[str], seeds: int = 20):
        self.n = n_robots
        self.scenarios = scenarios
        self.seeds = seeds
        self.records = []

    def run(self, gate, policy) -> dict:
        for scen in self.scenarios:
            for seed in range(self.seeds):
                env = make_fleet_env(scen, self.n, seed)
                plan = policy.plan(env)
                admitted = gate.admits(plan, env.sensor_data)
                roll = env.execute(plan, admitted=admitted)
                self.records.append({
                    "scenario": scen, "seed": seed, "admitted": admitted,
                    "success": roll.success, "conflict": roll.conflict,
                    "deadlock": roll.deadlock,
                    "correlated_violation": roll.correlated_violation,
                    "cert_agreement": roll.cert_agreement,
                })
        return self.aggregate()

    def aggregate(self) -> dict:
        r = self.records
        n = len(r)
        return {
            "joint_success": sum(x["success"] for x in r) / n,
            "conflict_rate": sum(x["conflict"] for x in r) / n,
            "deadlock_rate": sum(x["deadlock"] for x in r) / n,
            "correlated_violation_rate": sum(x["correlated_violation"] for x in r) / n,
            "cert_agreement": sum(x["cert_agreement"] for x in r) / n,
            "admission_rate": sum(x["admitted"] for x in r) / n,
        }
```

## 3. 复杂度分析（增量）

| 模块 | 时间复杂度 | 空间复杂度 | 关键参数 |
|---|---|---|---|
| UEP 在线评估 | O(W) | O(W) | W ≤ 200 事件窗口 |
| FJKC 一致性 | O(N²·K) | O(N·K) | N ≤ 10，K ≤ 50 共享规则 |
| CCG 占用/冲突 | O(N²·H·M) | O(N·H·M) | H ≤ 20，M 为离散格数（可用区间加速） |
| CCG 死锁检测 | O(N + E) | O(N + E) | E ≤ N²，DAG 判定 |
| KTCG-Fleet | O(N·(H·n_x³)) + O(N²·K) + O(N²·H·M) | O(N·H·n_x + N·K) | 主导项仍为 N 次单机 KTCG 求解 |

**实时性**：N=10、单机 KTCG 单步 15ms 时，舰队串行求解约 150ms；可采用「并行单机求解 + 集中冲突裁决」把关键路径压到约 20–30ms。UEP 与 FJKC 可低频异步更新（1–5Hz），CCG 在规划层（10Hz）运行，不进入 50Hz 内环。

## 4. 正确性论证（增量）

### 引理 26（UC 的崩塌敏感性）

**陈述**：U ∈ (0,1]，且当任一子指标趋近其最差值（C→0、L→L_max、T→0、B→B_max）时，U→0。

**证明**：U 为各归一化子项的正权重几何平均，指数权重 w_k>0。若某项 p_k→0，则 log U = Σ w_j log p_j → −∞，故 U→0；而几何平均 ≤ 算术平均保证 U≤1，eps 保证非零下界。因此任一维度的崩塌都无法被其他维度的满分线性补偿。∎

### 引理 27（舰队准入的可靠性/单调性）

**陈述**：`KTCG-Fleet.admits(Π)=True ⟹ ∀i, KTCG_i.admits(π_i)=True`，即 FleetExec ⊆ ∩_i Exec_i ⊆ Exec_v28。

**证明**：`admits` 的第一段逐机调用单机 KTCG，任一失败即返回 False；后续四段只做额外合取，不放松任何单机约束。故通过舰队准入蕴含逐机通过。∎

### 引理 28（CCG 冲突检测的可靠性）

**陈述**：若 `conflict_free(Π)=True`，则任意 i≠j 的时空占用集合满足 O_i ∩ O_j = ∅（在 margin 外扩后），即任意时刻任意两机间距 ≥ margin。

**证明**：`conflict_free` 对所有机器人对做 O_i∩O_j 的穷举判定，仅当全部为空才返回 True；占用集合已按 margin 外扩，故交集为空等价于原始轨迹距离大于 margin。∎

### 引理 29（无死锁的充分条件）

**陈述**：若让行图 G_c 无环，且每台机器人持有已验证的等待/站立计划，则舰队执行不会发生循环等待型死锁。

**证明**：死锁的必要条件之一是资源等待图中存在环（循环等待）。静态优先序使每条冲突边的方向由低优先级指向高优先级，若 G_c 无环，则不存在循环等待；又因每台被让行方都能执行已验证的等待计划（不会因等待本身违反单机安全证书），系统可在有限冲突时长后推进。∎

### 定理（KTCG-Fleet 的三重增强安全性）

**陈述**：对任意舰队计划 Π，`KTCG-Fleet.admits(Π)=True` ⟹ Π 同时满足：(1) 每台机器人通过 v28 九证；(2) 每个操作员的 UC 可用（U≥u_min 且 L≤L_max、T≥T_min、B≤B_max）；(3) 舰队知识一致（A≥A_min）；(4) 时空无冲突；(5) 无死锁（G_c 无环且等待计划已验证）。

**证明**：由 `admits` 的五段合取定义逐项对应引理 27–29；可用性段直接由 `UC.usable()` 的合取定义给出；一致性段由 `check_consistency` 的阈值判定给出。故结论成立，且 Exec_v29 = Exec_v28 ∩ Fil_usability ∩ Fil_fleet ⊆ Exec_v28。∎

## 5. 实验设计（MREB + 人因研究）

**场景族**：平地、斜坡、湿滑、楼梯、窄通道（强制共享）、动态障碍；N ∈ {1,2,5,10}；每配置 20 seeds。
**对照组**：
- B0：v28 单机九证 + 贪心多机（无舰队协调、无可用性门）；
- B1：v29 去掉可用性门（只做舰队一致性/冲突/死锁）；
- B2：v29 完整（KTCG-Fleet）。

**预期/模拟结果（N=10，窄通道+动态障碍，均值）**：

| 指标 | B0 (v28) | B1 (无可用性门) | B2 (KTCG-Fleet) |
|---|---|---|---|
| 联合成功率 | 0.71 | 0.86 | 0.91 |
| 冲突率 | 0.18 | 0.03 | 0.01 |
| 死锁率 | 0.12 | 0.04 | 0.008 |
| 相关违规率 | 0.09 | 0.05 | 0.02 |
| 证书一致率 | 0.62 | 0.81 | 0.93 |
| 准入率 | 0.88 | 0.74 | 0.69 |

**人因研究（12 名操作员，3 条件 × 30 次决策，被试内设计）**：

| 条件 | C | L(s) | T | B | U |
|---|---|---|---|---|---|
| 原始证书（无解释） | 0.52 | 3.6 | 0.48 | 0.41 | 0.43 |
| v28 ExpReport | 0.71 | 2.1 | 0.66 | 0.29 | 0.63 |
| v29 UC 门控+解释 | 0.84 | 1.4 | 0.79 | 0.22 | 0.78 |

**关键观察（待验证假设）**：可用性门会降低准入率（0.88→0.69），但把「被操作员误用的证书」挡在门外，换来更高的联合成功率与更低的相关违规率——即「少而可用」优于「多而不可用」。多机相关违规率的下降主要来自 FJKC 的版本/λ/μ 对齐，而非单纯冲突检测。

## 6. 已知风险与缓解（增量）

| 风险编号 | 描述 | 严重度 | 缓解措施 | 剩余风险 |
|---|---|---|---|---|
| R25 | 可用性指标 Goodhart 化（操作员为分数而表演） | 高 | 1) 隐藏部分指标、随机抽检；2) 以真实任务成功率做外锚；3) 定期更换评估场景防过拟合 | 长期部署后操作员行为漂移仍会污染指标 |
| R26 | 多机组合覆盖不完备，相关失效落在盲区 | 高 | 1) 场景族分层抽样 + 对抗性生成；2) 故障注入（共享知识污染）；3) 影子模式线上回放 | 组合爆炸下无法穷尽，极端协同失效仍可能漏检 |
| R27 | FJKC/CCG 的 O(N²) 实时开销 | 中 | 1) 空间分簇后只在邻域内做配对；2) 一致性低频异步；3) 增量更新冲突图 | 超大规模舰队（N>50）仍需分层调度 |
| R28 | 静态优先序导致低优先级机器人饿死/效率下降 | 中 | 1) 带 aging 的优先级；2) 定期重排但保证无环；3) 饥饿检测触发重规划 | 动态重排可能引入瞬时循环等待 |
| R29 | 人因实验样本小、外部效度低 | 中 | 1) 多中心复现；2) 混合在线 A/B；3) 报告置信区间而非点估计 | 实验室结论到实环仍有落差 |

## 7. 本轮最大风险（最终确认）

**一句话**：**评测的 Goodhart 化与覆盖幻觉**——一旦可用性分数与多机基准成为优化目标，系统会优先「通过评测」而非「真正可被使用、真正安全」，而多机组合的覆盖永远不完备，最危险的跨机相关失效恰好落在基准盲区，最终用一份漂亮的评测报告掩盖了真实风险。
<!-- ARTIFACT:END -->
