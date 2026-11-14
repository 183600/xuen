# 玄 · 灵感驱动研究循环

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 1 轮（灵感循环第 1 轮；本轮灵感：「迭代验证」×「需求洞察」×「少样本学习」）

> 背景：当前具身智能系统往往依赖海量标注数据进行监督学习，而在真实部署中面对「需求洞察」中暗示的稀缺场景（罕见故障、边缘案例、新环境）时，往往因数据不足而失效或产生灾难性误判。R73 的 MODGAUGE 提供「计量契约代数」框架，将不确定度明确传递，但其前提是「契约可表达」且「模块已认证」。当模块在部署初期只有极少量样本时，MODGAUGE 的「模块热替换」定理无法直接使用——我们没有足够的材质/视角/互扰数据来校准 DPEM、训练 IRL、构架 MReg。
>
> 本轮灵感三位一体，设计 **LeanGauge** 算法：
> - **需求洞察**：系统需要在「故障前哨」层面识别「尚未被需求覆盖的风险区域」——这些区域往往是「数据稀缺」的、且「代价高」的；
> - **迭代验证**：通过「可预测的自助下注」在线生成「伪需求」样本，对每个「需求未覆盖」的子空间进行「最小验证子图」的「闭环修复」；
> - **少样本学习**：在「需求洞察」发现的稀缺子空间内，用「结构化的先验约束」+「贝叶斯不确定度传播」+「迭代验证生成的样本」进行「计量契约的局部校准」；
>
> 核心命题：**把「等待大数据」的被动学习，变为「在少样本下主动发现+迭代修复需求盲区」的主动计量增强**——系统在每次「需求洞察」触发时，自动生成「迭代验证子图」，在子图内就地完成「少样本学习」的「计量契约修复」，从而在「模块热替换」前置条件（材质/视角/互扰覆盖）得到满足。

## 0. 直觉与动机

**灵感 1（需求洞察 → 故障前哨层面的「需求盲区」识别）**
直觉：R73 的 MODGAUGE 追求「契约表达力完备」，但实际部署时往往面临「契约可表达性盲区」——某个材质/视角/干扰组合在训练数据中从未出现，这在「故障前哨」层面表现为：DPEM 对该组合的 u_depth 估计偏低（假确定性），但实际测量 σ 远大于预期，导致下游 BSE 发出错误的「安全」信号。这种盲区往往在「极端边缘」或「罕见组合」——数据稀缺、代价高昂——它们正是需求洞察要发现的：**需求盲区 = 稀疏子空间 + 高风险等价类**。

我们引入**需求盲区检测器 D-Box**，它持有「需求覆盖率矩阵」R ∈ ℝ^(d×m×i)，其中 d=距离维、m=材质维、i=互扰维；每个单元格的值是「该子空间是否被验证过」+「当前 u 的置信区间宽度」。当 R 某格单元的验证次数 < τ_n (例如 ≤1) 且该格属高风险区域（碰撞/失手代价 > τ_cost），即判定该子空间为「需求盲区」。

**灵感 2（迭代验证 → 可预测下注的「自助验证」机制）**
直觉：R73 的最高风险是「契约表达力盲区」——系统自信地组合一个错误世界。我们的「迭代验证」灵感来源于 R73 的 CAS 哨兵，但**不依赖外部标签，而是用「可预测的自助下注」在线生成「伪需求样本」**：
- 选取当前需求盲区所在的「边缘子空间」；
- 构造「最小验证子图」M_ver ⊆ MReg（只包含涉及该子空间的所有关键模块）；
- 在 M_ver 内，对每个候选动作 a，执行「可预测下注」：
  - 假设 a 将进入盲区 → 观测 σ_pred；
  - 若 σ_pred > σ_decl + γ (经验安全裕度) → 下注 a 为「潜在风险信号」；
  - 执行 a，记录真实观测 σ_obs；
- 根据「下注结果」→「真实是否中标」生成「需求样本」+「计量反馈」；
- 更新盲区覆盖矩阵 R。

这与 CAS 的「赌局哨兵」不同：**我们不是监控契约偏离，而是主动发起「哨兵式的探测行动」来发现盲区本身**。

**灵感 3（少样本学习 → 计量契约的「局部校准」）**
直觉：一旦迭代验证生成了「需求盲区样本」，我们需要在「数据稀缺」的前提下完成「计量契约的局部校准」。方案：
- **结构化先验**：对 DPEM 的每个分量 u_range, u_material, u_edge 等，都有已知的物理尺度（σ ∝ d²/B、材质反射率指数等）；
- **贝叶斯不确定度传播**：在需求盲区样本 N_bl 上，构建高斯过程（或变分推断），对 u 进行后验更新。先验由物理尺度给出，数据不足时靠先验，充足时数据主导；
- **局部修复**：只修复盲区子图的「契约声明」——更新 EC 中的 χ_R, D, τ_merge 等。其余子图保持原有证书，实现「局部热替换」。

这把「需求盲区」从「黑 桶」变成「可验证的、可修复的子问题」。

## 1. 形式化定义（增量：定义 398–415）

**定义 398（需求覆盖矩阵与需求盲区）** 需求覆盖矩阵 R ∈ ℝ^(d×m×i)：
- R[d,m,i] = (n_verify, σ_conf_lo, σ_conf_hi, cost_risk)；
- n_verify：子空间 (d,m,i) 的验证次数；
- σ_conf : 该子空间当前 u 的置信区间；
- cost_risk：该子空间的风险等价类（碰撞/失手代价）。

**定义 399（需求盲区）** 子空间 s = (d,m,i) 为需求盲区 ⇔ n_verify(s) ≤ τ_n ∧ cost_risk(s) ≥ τ_cost。

**定义 400（可预测自助下注）** 给定需求盲区 s，候选动作集合 A_s。下注函数 λ: A_s → ℝ，λ(a) = σ_pred(a|s) - σ_decl(a)。若 λ(a) ≥ γ，则判 a 为「潜在风险信号」。

**定义 401（最小验证子图 M_ver）** M_ver = (V_ver, E_ver) ⊆ MReg，其中 V_ver 包含所有涉及盲区 s 的模块，E_ver 是其诱导子图。

**定义 402（迭代验证采样）** 对 a ∈ A_s：
1. 执行下注：假设 a 进入 s → 计算 σ_pred = χ_viewpoint(a) + χ_material(a) + ...；
2. 若 σ_pred > σ_decl + γ：执行 a → 记录 σ_obs；
3. 生成「需求样本」(a, σ_obs, u_bl)；
4. 更新 R[s].n_verify += 1, σ_conf 更新。

**定义 403（少样本局部校准）** 在 N_bl = {(a_j, σ_j)}_J^j=1 个需求盲区样本上，对 DPEM 的每个分量 u_k 进行贝叶斯更新：
- 高斯过程先验：u_k ~ GP(μ_0(d,m,i), K_0(·,·))；
- 观测似然：σ_j | u_k ~ 𝒩(u_k(a_j), σ_obs²)；
- 后验：u_k | N_bl ~ GP(μ_N, K_N)；
- 局部修复：更新 EC 中 u_fields, χ_R, D 的声明。

**定义 404（迭代修复闭环 I-Box）** 给定需求盲区 s：
```
循环：
  1. M_ver ← MINIMAL_VALIDATION_SUBGRAPH(s)
  2. A_s ← ACTIONS_ENTERING(s)
  3. for each a ∈ A_s:
        λ ← PREDICTABLE_BET(a, s)
        if λ ≥ γ: EXECUTE(a), SAMPLE ← OBSERVE(a)
  4. N_bl ← COLLECT_SAMPLES(s)
  5. if N_bl 达标：
        (R, EC) ← LOCAL_CALIBRATE(N_bl)
        if CONTRACT_VALID(EC) and BUDGET_OK: BREAK
```

**定义 405（检测-纠正-验证-更新 4CV）**
- **检测 D**：D-Box 发现需求盲区；
- **纠正 C**：I-Box 执行迭代验证采样；
- **验证 V**：局部校准得到新契约 EC'；
- **更新 U**：MReg 中盲区子图热替换为 EC'，R 更新。

**定义 406（LeanGauge 总览）** LeanGauge = (MODGAUGE, D-Box, I-Box, 4CV)。

**定义 407（迭代验证时序契约 IV-Contract）** 与 REG 类比，IV-Contract = (A_s, τ_iter, B_iter, recovery_condition)：
- A_s：允许进入盲区的动作集合；
- τ_iter：每次迭代验证的最长时延；
- B_iter：迭代预算总量；
- recovery: 迭代收敛/失败的恢复条件。

**定义 408（采样效率下界）** 为保证盲区 s 的 σ_conf 缩小至 ≤ ε，所需最小样本数：
n_min(s) ≥ (σ_prior² - ε²) / (KL(U_prior || U_post) ≥ δ) 

其中 KL 由贝叶斯后验控制，δ 为目标信息增益。

## 2. 关键算法骨架

```python
# IP-310 LeanGauge：需求盲区检测器 D-Box
class DBox:
    def __init__(self, subspace_dims=(DIST_BINS, MATTERIAL_CAT, INTF_LEVEL)):
        self.R = np.zeros(subspace_dims + (4,))  # (n_verify, σ_lo, σ_hi, cost_risk)
        self.tau_n = 2
        self.tau_cost = 0.3  # normalized risk

    def detect_blind_spot(self):
        blind_spots = []
        for idx in np.argwhere(self.R[..., 0] <= self.tau_n):
            if self.R[tuple(idx) + (3,)] >= self.tau_cost:
                blind_spots.append((idx, self.R[tuple(idx)]))
        return blind_spots  # [(subspace_idx, (n, σ_lo, σ_hi, cost))]

    def update(self, subspace, n_verify, sigma_conf, cost):
        self.R[subspace] = [n_verify, sigma_conf[0], sigma_conf[1], cost]


# IP-311 I-Box：可预测自助下注与迭代验证采样
class IBox:
    def __init__(self, dpem, budget_cycle, gamma=0.15):
        self.dpem = dpem
        self.budget = budget_cycle
        self.gamma = gamma  # 预测-声明差阈值

    def predictable_bet(self, action, subspace):
        v = action.viewpoint
        m = subspace[1]  # material category
        sigma_pred = self.dpem.predict_uncertainty(v=v, m=m)
        sigma_decl = self.dpem.declared_uncertainty(v=v, m=m)
        return sigma_pred - sigma_decl

    def execute_validation(self, blind_spot):
        s = blind_spot[0]  # subspace index
        actions = self._actions_entering(s)
        samples = []
        for a in actions:
            if self.predictable_bet(a, s) >= self.gamma:
                sigma_obs = self.dpem.observe(action=a)  # 实际执行
                samples.append((a, sigma_obs))
                DBox.update(s, n_verify+1, ...)  # update coverage
        return samples


# IP-312 BP-Cal：贝叶斯先验驱动的局部校准
class BayesianLocalCalibrator:
    def __init__(self, prior_mean, prior_cov):
        self.prior_mean = prior_mean  # 物理尺度给出的 GP 均值
        self.prior_cov = prior_cov    # 物理尺度给出的 GP 协方差

    def calibrate(self, samples, subspace):
        """贝叶斯线性高斯过程更新"""
        X = np.array([s[0].viewpoint for s in samples])
        y = np.array([s[1] for s in samples])
        K = self.prior_cov(X, X) + 1e-6 * np.eye(len(X))
        L = np.linalg.cholesky(K)
        alpha = np.linalg.solve(L.T, np.linalg.solve(L, y))
        # 预测均值/协方差（标准BFGS优化版）
        mu_post = self.prior_mean(X) @ alpha  # 简化
        # 更新契约声明
        return mu_post, K  # 新的 u_k, Σ_k

    def update_contract(self, module, new_u, subspace):
        old_ec = module.ec
        new_fields = old_ec.u_fields.copy()
        new_fields[subspace] = new_u
        new_chi = lambda a: compute_chi_from_physical(u=new_u, v=a.viewpoint)
        new_ec = old_ec._replace(u_fields=new_fields, chi_R=new_chi)
        return new_ec


# IP-313 LeanGauge-4CV：一次完整的迭代修复闭环
def lean_gauge_4cv(M, blind_spot):
    """一次 I-Box 迭代"""
    if blind_spot.n_verify < 3:  # 初始探测
        samples = IBox.execute_validation(M, blind_spot)
        if len(samples) < 2:
            return False, "探测样本不足"
        new_u, _ = BayesianLocalCalibrator.calibrate(samples, blind_spot.subspace)
        new_ec = BayesianLocalCalibrator.update_contract(M.dpe, new_u, blind_spot.subspace)
        M.mreg.hot_replace(M.dpe, new_ec)  # 局部热替换
        DBox.update(blind_spot.subspace, len(samples), ...)
        return True, "迭代完成"
    else:  # 验证收敛
        return True, "子图已验证通过"


# IP-314 LeanGauge 主闭环（嵌入 MODGAUGE）
def LeanGauge_round(M, obs, audio, tac_frame, depth_img, det_set):
    """MODGAUGE-RAS + I-Box 迭代修复闭环"""
    blind_spots = DBox.detect_blind_spot()
    for spot in blind_spots:
        success, msg = lean_gauge_4cv(M, spot)
        if success:
            break  # 局部修复成功，继续主循环
    return MODGAUGE_round(M, obs, audio, tac_frame, depth_img, det_set)
```

## 3. 推导

**引理 42（自助下注可预测性）** 若动作 a 的观测 σ(a) 服从亚强稳健条件（A115 类），则 σ_pred(a|s) 为在子空间 s 上的可预测下注 λ(a)。系：利用 χ_v 等反作用通道，对每个 (v,m) 组合给出闭式 σ_pred；亚强稳健保证 λ(a) ≥ γ 时实际 σ(a) 的上界可控。

**引理 43（局部贝叶斯校准可收敛）** 设先验 u ~ GP(μ_0, K_0)，样本数 N ≥ n_min(s)，则后验 σ_post ≤ ε ⇒ P(σ_post > ε) ≤ exp(-N·δ)。系：标准 GP 回归的后验方差收敛率。

**引理 44（迭代修复的局部热替换）** M_ver 子图的模块 EC 更新为 EC' ⇔ EC' 满足定义 367 契约完整性 + 定义 370 组合单调性 + 引理 35 热替换定理 ⇒ 子图系统级性质保持。因 M_ver 只是 MReg 的子图，整体安全由 4CV 保持。

**引理 45（全流程时序预算）** IV-Contract 保证每次迭代 ≤ τ_iter，总预算 ≤ Σ B_iter ≤ B_total；且 τ_iter 由 REG 时序契约界定，硬实时不变。

## 4. 复杂度分析

| 组件 | 域 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|---|
| D-Box 盲区检测 | 计量域 50Hz | O(|subspace|) < 1ms | O(|subspace|) | 定义 398、399 |
| I-Box 迭代采样 | 计量域（事件触发） | O(|A_s|·T_obs) < 10ms | O(N_bl) | 定义 401、402 |
| BP-Cal 局部校准 | 计量域 1Hz | O(N²_bl) < 50ms | O(N_bl²) | 定义 403、引理 43 |
| 局部热替换 | 计量域 | < 1ms | O(1) | 引理 44 |
| 4CV 主闭环 | 计量域 | O(#blinds × 采样) < 50ms | O(blinds) | 定义 405 |

**总增开销**：相对于 MODGAUGE-RAS 的 3.5ms/周期，LeanGauge 最坏情况（每次都触发盲区）额外 ≤ 100ms/周期，但这是「稀疏事件」，平均开销 ≈ 10ms/分钟。

## 5. 实验设计 E411–E425（RAS-Baselines v4 协议）

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E411 D-Box 盲区探测 | 稀疏矩阵中盲区检出率 | 检出率 ≥90%，误检 ≤10% |
| E412 自助下注可预测性 | σ_pred - σ_obs 偏差 | 偏差 ≤15%（亚强稳健验证） |
| E413 迭代采样有效性 | N_bl=3 时 σ_conf 收敛 | σ_conf ≤ 1.5σ_decl |
| E414 局部贝叶斯校准 | 先验 vs 后验 KL 增益 | KL ≥ 0.5 nats / 样本 |
| E415 局部热替换等价性 | 替换后 diff = 0 | 逐指令等价，系统属性保持 |
| E416 4CV 闭环收敛 | 迭代次数上界 | ≤ 5 次收敛 |
| E417 总时序保全 | 100 周期实时性 | 99% 周期 < 50ms |
| E418 少样本抗鲁棒 | 5% 离群点干扰 | σ_conf 增益 ≥ 0.8×理想 |

## 6. 本轮最大风险

**一句话**：LeanGauge 的核心假设是「需求盲区可以通过「可预测自助下注」在有限预算内探测并校准」——但这依赖「σ_pred 与 σ_obs 高度相关」且「采样点足够信息论充分」；若实际噪声受**不可预测的环境突变**（如骤降气温导致标定瞬间失效、意外的反射材质使深度模型完全失效）或**攻击者精心设计的「盲区注入」**（故意进入模型训练分布外、且不触发下注阈值的区域），那么 I-Box 的「迭代采样」会被错误地当作「需求已覆盖」，系统在盲区上产生**自信的错误判断**——这相当于 R73 的「自信地组合错误世界」在「数据稀缺」的子空间中被「主动放大」。

次级风险与缓解：
1. **σ_pred 与 σ_obs 相关性不足** → 增设「模型-agnostic 观测回执」（如 RGB-深度残差），用以校验 σ_pred；
2. **迭代采样不充分** → 预注册 n_min = 2×引理 48 样本；采样后做「盲区敏感性扫描」；
3. **盲区注入攻击** → 第 0 层物理包络（力/温/时序）兜底；若盲区采样后 u 不降则 RED；
4. **先验驱动的局部校准偏执** → 校准后做「契约回归测试」，若回归不通过则 stub 盲区模块；
5. **4CV 循环死锁** → IV-Contract 中的 recovery_condition：迭代 N > N_max ⇒ 全系统降级（R68 样式）；
6. **D-Box 误检** → cost_risk 阈值 τ_cost 随任务风险动态调节；
7. **贝叶斯校准数值不稳** → 使用稳健 GP（高斯似然 + 学生 t 协方差）+ 数值断点保护。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 1 轮产物 · 创新点清单 v1：**LeanGauge**（Iterative Blind-spot Evidence Metrology with GAUGE audits for RAS）

> 背景：R73 的 MODGAUGE 提供「计量契约代数」框架，将不确定度明确传递。但在部署初期，面对「需求洞察」中暗示的稀缺场景（罕见故障、边缘案例、新环境），模组认证往往缺乏足够样本。LeanGauge 通过「迭代验证」机制，主动发现「需求盲区」并在「少样本」条件下完成「局部计量契约修复」，实现「需求先行」的计量增强。
>
> IP 编号：IP-310~314（共 5 个）。理论姿态：**在 MODGAUGE 基础上，增加「需求盲区检测-迭代修复闭环」层**——不改变 R73 的五不变式（契约完整性、组合单调性、反作用通道完备、主张绑定、严格退化链），而是为「模块热替换」前置条件提供「数据稀缺情形下的自动发现+校准」路径。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进（相对 MODGAUGE） |
|---|---|---|---|
| IP-310 | D-Box 需求盲区检测器 | 核心模块 | 稀疏子空间覆盖矩阵 + 代价感知盲区判定 |
| IP-311 | I-Box 可预测自助下注 | 核心模块 | 基于 χ_R 的闭式 σ_pred + 迭代采样生成需求样本 |
| IP-312 | BP-Cal 局部贝叶斯校准 | 核心模块 | 物理先验 + 少样本后验更新 → 局部契约修复 |
| IP-313 | LeanGauge-4CV | 设计模式 | 检测-纠正-验证-更新 四阶段闭环 |
| IP-314 | LeanGauge 主闭环 | 集成 | MODGAUGE + 4CV 迭代修复 → 稀疏场景自适应 |

## 1. 符号体系增量（定义 398–415）

| 符号 | 含义 |
|---|---|
| `DBox` | 需求盲区检测器 |
| `R ∈ ℝ^(d×m×i×4)` | 需求覆盖矩阵 (n_verify, σ_lo, σ_hi, cost_risk) |
| `s = (d,m,i)` | 子空间索引 |
| `τ_n, τ_cost` | 盲区判定阈值 |
| `IBox` | 迭代验证子系统 |
| `λ(a,s)` | 可预测下注函数 σ_pred - σ_decl |
| `γ` | 下注阈值 |
| `M_ver ⊆ MReg` | 最小验证子图 |
| `N_bl = {(a_j, σ_j)}_J` | 需求盲区样本集 |
| `BP-Cal` | 贝叶斯局部校准器 |
| `U_prior ~ GP(μ_0, K_0)` | 先验高斯过程 |
| `U_post ~ GP(μ_N, K_N)` | 后验高斯过程 |
| `n_min(s) ≥ (σ_prior² - ε²)/δ` | 理论最小样本数 |
| `4CV` | 检测-纠正-验证-更新 四阶段闭环 |

## 2. 形式化定义（要点）

**定义 398（需求覆盖矩阵与需求盲区）** 详见上文。

**定义 400（可预测自助下注）** λ(a,s) = σ_pred(a|s) - σ_decl(a)，其中 σ_pred 由 χ_R 解析计算。

**定义 401（最小验证子图）** M_ver = (V_ver, E_ver) ⊆ MReg，其中 V_ver 包含所有涉及盲区 s 的模块。

**定义 404（迭代修复闭环 I-Box）** 循环更新：
```
循环：
  1. M_ver ← MINIMAL_VALIDATION_SUBGRAPH(s)
  2. A_s ← ACTIONS_ENTERING(s)
  3. for each a ∈ A_s:
        λ ← PREDICTABLE_BET(a, s)
        if λ ≥ γ: EXECUTE(a), SAMPLE ← OBSERVE(a)
  4. N_bl ← COLLECT_SAMPLES(s)
  5. if N_bl 达标：
        (R, EC) ← LOCAL_CALIBRATE(N_bl)
        if CONTRACT_VALID(EC) and BUDGET_OK: BREAK
```

**定义 407（迭代验证时序契约 IV-Contract）** IV-Contract = (A_s, τ_iter, B_iter, recovery_condition)。

**定义 408（采样效率下界）** n_min(s) ≥ (σ_prior² - ε²) / KL(U_prior || U_post) ≥ δ。

## 3. 关键算法骨架

```python
# IP-310 D-Box：需求盲区检测器
class DBox:
    def detect_blind_spot(self):
        blind_spots = []
        for idx in np.argwhere(self.R[..., 0] <= self.tau_n):
            if self.R[tuple(idx) + (3,)] >= self.tau_cost:
                blind_spots.append((idx, self.R[tuple(idx)]))
        return blind_spots  # [(subspace_idx, (n, σ_lo, σ_hi, cost))]

# IP-311 I-Box：可预测自助下注
class IBox:
    def predictable_bet(self, action, subspace):
        v = action.viewpoint
        m = subspace[1]
        sigma_pred = self.dpem.predict_uncertainty(v=v, m=m)
        sigma_decl = self.dpem.declared_uncertainty(v=v, m=m)
        return sigma_pred - sigma_decl

    def execute_validation(self, blind_spot):
        samples = []
        for a in self._actions_entering(blind_spot.subspace):
            if self.predictable_bet(a, blind_spot.subspace) >= self.gamma:
                sigma_obs = self.dpem.observe(action=a)
                samples.append((a, sigma_obs))
        return samples

# IP-312 BP-Cal：局部贝叶斯校准
class BayesianLocalCalibrator:
    def calibrate(self, samples, subspace):
        X = np.array([s[0].viewpoint for s in samples])
        y = np.array([s[1] for s in samples])
        K = self.prior_cov(X, X) + 1e-6 * np.eye(len(X))
        L = np.linalg.cholesky(K)
        alpha = np.linalg.solve(L.T, np.linalg.solve(L, y))
        mu_post = self.prior_mean(X) @ alpha
        return mu_post, K

    def update_contract(self, module, new_u, subspace):
        new_ec = module.ec._replace(u_fields=..., chi_R=...)
        return new_ec

# IP-314 LeanGauge 主闭环
def LeanGauge_round(M, obs, audio, tac_frame, depth_img, det_set):
    blind_spots = DBox.detect_blind_spot()
    for spot in blind_spots:
        success, msg = lean_gauge_4cv(M, spot)
        if success: break
    return MODGAUGE_round(M, obs, audio, tac_frame, depth_img, det_set)
```

## 4. 推导

**引理 42（自助下注可预测性）** 由 χ_R 解析表达式及亚强稳健条件 (A115) 保证。

**引理 43（局部贝叶斯校准可收敛）** 标准 GP 回归后验方差收敛率。

**引理 44（迭代修复的局部热替换）** M_ver 子图的模块 EC 更新后，局部子系统性质保持。

**引理 45（全流程时序预算）** IV-Contract 保证每次迭代 ≤ τ_iter。

## 5. 复杂度分析

| 组件 | 域 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|---|
| D-Box 盲区检测 | 计量域 50Hz | O(\|subspace\|) < 1ms | O(\|subspace\|) | 定义 398、399 |
| I-Box 迭代采样 | 计量域（事件触发） | O(\|A_s\|·T_obs) < 10ms | O(N_bl) | 定义 401、402 |
| BP-Cal 局部校准 | 计量域 1Hz | O(N²_bl) < 50ms | O(N_bl²) | 定义 403、引理 43 |
| 局部热替换 | 计量域 | < 1ms | O(1) | 引理 44 |
| 4CV 主闭环 | 计量域 | O(#blinds × 采样) < 50ms | O(blinds) | 定义 405 |

**总增开销**：相对于 MODGAUGE-RAS，LeanGauge 最坏情况额外 ≤ 100ms/周期，但稀疏事件驱动，平均开销 ≈ 10ms/分钟。

## 6. 实验设计 E411–E425（RAS-Baselines v4 协议）

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E411 D-Box 盲区探测 | 稀疏矩阵中盲区检出率 | 检出率 ≥90%，误检 ≤10% |
| E412 自助下注可预测性 | σ_pred - σ_obs 偏差 | 偏差 ≤15% |
| E413 迭代采样有效性 | N_bl=3 时 σ_conf 收敛 | σ_conf ≤ 1.5σ_decl |
| E414 局部贝叶斯校准 | 先验 vs 后验 KL 增益 | KL ≥ 0.5 nats / 样本 |
| E415 局部热替换等价性 | 替换后 diff = 0 | 逐指令等价，系统属性保持 |
| E416 4CV 闭环收敛 | 迭代次数上界 | ≤ 5 次收敛 |
| E417 总时序保全 | 100 周期实时性 | 99% 周期 < 50ms |
| E418 少样本抗鲁棒 | 5% 离群点干扰 | σ_conf 增益 ≥ 0.8×理想 |

## 7. 本轮最大风险

**一句话**：LeanGauge 核心假设「需求盲区可通过可预测下注在有限预算内探测并校准」，但若实际噪声受**不可预测的环境突变**（骤降气温、意外反射材质）或**精心设计的盲区注入攻击**（进入模型训练分布外、且不触发下注阈值的区域），I-Box 的迭代采样会被错误地当作「需求已覆盖」，系统在盲区上产生**自信的错误判断**——这相当于 R73 的「自信地组合错误世界」在「数据稀缺」的子空间中被「主动放大」。
<!-- ARTIFACT:END -->
