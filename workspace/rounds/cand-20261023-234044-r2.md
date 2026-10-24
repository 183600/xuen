# 玄 · 设计一个新的算法

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
## 一、上一轮留下的不对称

v7.2 QUC 在 NO 侧已经很强：141 个基准 + 60 个扰动全部在 $h=\mathrm{OPT}-1$ 判 NO，201/201 通过审计；7 个「根 LP 可行但分数」的实例每例只需 2 次单列探针，根层就闭合了。但它留下了一个很不对称的局面：

- NO 侧：根层 2 次探针，知道「必须用哪个开始时间」；
- YES 侧：预算 6 时 93/141 仍是 UNKNOWN，因为 QUC 只会继续做 NO 搜索，不会主动构造一个调度。

本轮灵感词是 **convex optimization / 归约 / fault-tolerant algorithm**。我第一反应不是再加强 SD 割，而是问：同一个 LP，除了给出「删掉某列后不可行」的 Farkas 证书，还能不能给出「怎样排才可行」的信息？

答案是能，但两种信息的方向相反：

- **向下归约（NO）**：删列 → 解 LP → 不可行 → Farkas 证书 → 强制/陷阱；
- **向上归约（YES）**：同一个 LP 的分数解 → 开始时间分布 → 采样优先级 → 串行调度 → 独立重放。

于是本轮算法叫 **BRC-ALC（Bidirectional Reduction-Certified ALC）**：把 NO 的「删」和 YES 的「造」放在同一个 LP 上，用证书和调度分别封口。

## 二、先试错：凸优化不等于构造器

我最初想沿「凸优化」走 cover LP：把单元证书、支持集证书和容量割放进一个混合证书 LP，求一个最小的证书覆盖。v8.0 的原型 `exp/v80/qcm.py` 确实跑通了，但在 252 个 NO 上只触发了 3 次 cover LP，收益几乎为零。原因是 v7.2 的单元陷阱已经把根层矛盾压到 2 个单点，cover LP 没有新的矛盾可组合。

这是一个有用的负结果：**凸优化在这个问题上的价值不在「求更强的界」，而在「给出一个可采样的分布」**。根 LP 的分数解 $z$ 同时是：

- NO 侧 support 引理的载体：可认证的单元必在 $S_i(z)$ 中；
- YES 侧构造器的指南：$z_{i,t}$ 是「任务 $i$ 在 $t$ 开始」的松驰权重。

## 三、向上归约的三次原型

我把 YES 侧当成一个独立的构造问题，先不看 NO 证明，只要求在 $h=\mathrm{OPT}$ 上造出可行调度。三次原型的数字很清楚地指出了方向：

| 构造器 | 141 个 YES 中闭合 | 观察 |
|---|---:|---|
| 期望开始时间排序 + 串行 SGS | 104 | 快，但把分数解「四舍五入」成单一顺序，丢掉了并行的灵活性 |
| 根 LP 分布随机舍入 + SGS | 134 | 采样恢复了多样性，仍有 7 个 hard 实例 |
| 分布采样 + 有界 DFS SGS | 141 | 7 个 hard 实例分别需要 0–16 次重启 |

7 个 hard 实例的分布很说明问题：`large_a` 的 idx 5 需要第 16 次重启；`large_het` 的 0/3/7 在 0/2/8 次重启闭合；`hard3` 的 4 在 0 次闭合；`large_het` 的 2/4 根 LP 本身就是整数，直接返回。也就是说，**LP 分布已经把「可能的开始时间」压得很小，剩下的是在几个等价好顺序之间做有界搜索**。

因此 v8.0 的 YES 构造器是：从根 LP 分布独立采样每个任务的开始时间，得到一个优先级键；用这个键驱动串行 SGS；如果 SGS 走死，就在「当前可开工任务 × 可选机器」上做有界 DFS 回溯。构造器只相信最后的 `check_schedule`，不相信自己的启发式。

## 四、向下归约：不重写 QSP，只加容错

NO 侧我没有另起炉灶，而是直接继承 v7.6 QSP：单列探针、支持集探针、force 递归、单元陷阱、跨任务共识、span-first 顺序。原因是 QSP 在 252 个 NO 上已经做到 577 LP / 283 节点，比 QNC 的 585/415 好；再改搜索顺序只会引入新的过拟合。

我真正加的是**容错层**。动机来自两次具体的失败：

1. v7.2 的 `audit_quc` 跨任务字段错位：`self.cross` 是 `('prec', i, t, j, u)`，代码却按 `cross[:4]` 解包，201 个基准没触发，51 个压力集里第 24 例触发。这说明「证书存在」不等于「证书被正确重放」。
2. 两阶段搜索在压力集 idx 47 上从根重启，根 LP 因为已加割而改变，导致重复探针：QSP 20 LP/14 节点，最初的 RDF 38 LP/30 节点。修法是：纯 NO 模式只跑一遍 QSP 等价搜索；YES 模式如果 phase A 没拿到 `root_z`，就对当前有效割集直接解一次 LP 取一个构造器见证，而不是重新走整个 lazy 分离。

容错层的四条规则：

- **证书先验证再使用**：任何 Farkas 证书都过 `verify`；损坏证书被抓住后走恢复，不进入证明。
- **dual row-core 恢复**：对偶 LP 解出来后丢掉零对偶值的行，在剩余行上重解；行核上的证书把丢掉的行补零就得到全 LP 的证书，所以这是归约而不是放松。
- **fail-stop 域分裂**：叶证书提取失败时，不返回无证书的 NO，而是按最大剩余域分裂成两个子问题；只有两个子问题都有证书，父节点才成立；预算耗尽就返回 UNKNOWN。
- **调度独立重放**：YES 只由 `check_schedule` 确认；构造器的任何中间状态都不算证据。

## 五、两阶段决定：把预算花在能闭合的地方

一个统一的 `decide` 如果对每个实例都先跑构造器，NO 侧会被大量无效的 SGS 拖慢。因此 v8.0 用两阶段：

1. **phase A**：小预算 NO 搜索（12 LP / 200 节点）。大多数 NO 在这一步就闭合；如果根 LP 分数且拿到 `root_z`，进入 YES 构造。
2. **phase B1**：8 次采样、每次 500 个 SGS 节点。大多数 YES 在这里闭合。
3. **phase B2**：48 次采样、每次 4000 个 SGS 节点，全局 60k 节点上限。处理 7 个 hard YES。
4. **phase C**：如果仍未决，用剩余全预算回到 QSP 搜索。

实测这个顺序把 NO 的额外成本压得很低：252 个 NO 在统一模式下是 595 LP / 299 节点 / 4.95 s，只比纯 NO 模式多 18 LP / 16 节点；只有压力集的一个实例触发构造器，且被 60k 节点上限截住。YES 侧则从 QUC6 的 48/141 提升到 141/141。

## 六、这一轮学到的东西

1. **同一个 LP 可以同时服务两个方向**：support 引理把 NO 的候选压到 support，分布采样把 YES 的候选压到 support 的权重；两者不是两个算法，而是同一个凸松弛的两种读法。
2. **向上归约的瓶颈不是「采样」而是「回溯」**：纯随机舍入 134/141，剩下 7 个需要的是有界 DFS，而不是更多样本。于是全局节点预算比「更多 trials」更有效。
3. **容错必须可观测**：`corrupt_caught`、`corrupt_missed`、`leaf_missing`、`ft_splits`、`ft_stuck`、`proof_complete` 这些计数器让「算法返回了 NO」和「算法有完整证明」变成两个可分别检查的命题。故障注入中 `corrupt_missed=0`，说明损坏证书没有蒙混过关。
4. **负结果同样重要**：cover LP 只触发 3 次，说明本轮不需要更复杂的凸组合证书；压力集 idx 47 的重复探针说明重启不是免费的，纯 NO 模式必须单遍。
5. **YES 构造器不是完备算法**：它是有界随机搜索，60k 节点之外不保证找到调度；它的价值是把 93 个 QUC6 UNKNOWN 中的 93 个全部闭合，而不是证明「所有 YES 都能被它闭合」。

## 七、一句话最大风险

**YES 侧是随机化、有界节点的构造器，60k 节点和 48 次采样之外不保证找到调度；NO 侧仍依赖 SD 割的强度，若根 LP 的 lazy 分离本身耗尽预算，BRC 会诚实地返回 UNKNOWN，而不是一个没有证书的 NO。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
## 0. 版本关系与本轮增量

本轮产物是 **v8.0 BRC-ALC（Bidirectional Reduction-Certified ALC）**。它不是对 v7.2 的替代，而是把上一轮的两个半成品接起来：

- **向下归约**直接继承 v7.6 QSP：单列探针、支持集探针、force 递归、单元陷阱、跨任务共识、span-first 顺序；QSP 又包含 v7.2 QUC 的单元证书和 v7.1 QNC 的 DFS/clause/叶子证书层。
- **向上归约**是本轮新增：用同一个根 LP 的分数解做开始时间分布，采样优先级，串行 SGS + 有界 DFS 构造调度，最后独立重放。
- **容错层**是本轮新增：所有证书先验证；提取失败走 dual row-core 恢复；叶证书缺失走 fail-stop 域分裂；YES 只由 `check_schedule` 确认。
- **两阶段预算**是本轮新增：小预算 NO 搜索 → 小构造器 → 大构造器 → 全预算 NO 搜索。若调用者明确只要 NO，可用 `yes_scan=False` 走单遍 QSP 等价路径。

另修正了两个上一轮遗留问题：

1. v7.2 `audit_quc` 的跨任务字段错位（`cross[:4]` 丢掉 kind，导致字段整体移位）；QSP 的 `audit_qsp` 用 `cross[:5]` 修复，BRC 继承该修复。
2. 两阶段搜索从根重启时会因新割改变根 LP，从而重复探针；纯 NO 模式改为单遍，YES 模式在 phase A 未取得 `root_z` 时只对当前有效割集直接解一次 LP 取构造器见证。

推荐接口：

    RDF(inst, h, yes_scan=True, small_budget=12, small_nodes=200,
        yes_trials1=8, yes_nodecap1=500,
        yes_trials2=48, yes_nodecap2=4000,
        yes_node_budget=60000, ft_on=True, recover=True,
        fail_calls=0, corrupt_calls=0, ft_budget=64)
    .decide(budget=100000, nodecap=5000) -> (verdict, state)
    .audit_rdf() -> bool
    .proof_complete() -> bool

`verdict ∈ {True, False, None}`；`True` 必带一个通过 `check_schedule` 的调度，`False` 必带完整 Farkas/clause 证明（`proof_complete=True`），`None` 表示预算耗尽或 fail-stop。

## 1. 符号

- \(n\)：任务数；\(m\)：机器数；\(p_i\)：加工时间；\(\mathrm{pred}(i)\)、\(\mathrm{succ}(i)\)、\(\mathrm{elig}(i)\)。
- \(h\)：待判定的 makespan 上界；NO 基准 \(h=\mathrm{OPT}-1\)，YES 基准 \(h=\mathrm{OPT}\)。
- \(D_i=\{\mathrm{est}_i,\dots,h-q_i-p_i\}\)：任务 \(i\) 的可行开始时间域。
- \(C\)：已分离的 SD 割集；\(\mathrm{LP}(C)\) 是带割集的 start-time LP；\(\mathrm{LP}(C,E)\) 是把列集 \(E\) 删掉后的 LP。
- 列 \(c=(i,t)\)；资格感知时 \(c=(i,k,t)\)。\(z_{i,t}\) 是开始时间分数（资格感知时对机器求和）。
- \(S_i(z)=\{t:z_{i,t}>0\}\)：任务 \(i\) 在可行解 \(z\) 中的 support。
- \(\Phi\)：整数 Farkas 证书；\(\mathrm{verify}(\Phi,\mathrm{forbid}=E)\) 逐列重放 \((A_E)^T y\ge0\)、\(b^T y<0\)。
- \(E\)：证书的 essential scope；\(F\)：当前被禁止的列集合。
- \(d_i(t)=z_{i,t}/\sum_u z_{i,u}\)：构造器用的开始时间分布。
- \(N_{\mathrm{yes}}\)：构造器全局 SGS 节点上限（默认 60,000）。
- \(T_{\mathrm{SGS}}\)：串行调度生成树；\(B_1,B_2\)：两批构造器的 trials/nodecap。

## 2. 向下归约：NO 侧

### 2.1 单列探测与 force 方向

设 \(p=(i,t)\)。若

\[
\mathrm{LP}(C,\{p\})\ \text{不可行},
\]

则由 `verify(Φ_p, forbid={p})` 得到有效证书，并称 \(p\) 是 **forced unit**，结论是

\[
s_i=t.
\]

方向必须写死：\(\{p\}\) 是**被删掉的列**，但结论是「必须用 \(p\)」。两个 forced unit 给出 \(s_i=t\)、\(s_i=u\) 且 \(t\ne u\) 时才是矛盾。

### 2.2 支持引理

设 \(z\) 是 \(\mathrm{LP}(C)\) 的任意可行解。若 \(\mathrm{LP}(C,\{p\})\) 不可行，则

\[
z_p>0.
\]

**证明**：若 \(z_p=0\)，删掉 \(p\) 不会删掉 \(z\) 的任何正分量，\(z\) 仍是 \(\mathrm{LP}(C,\{p\})\) 的可行解，矛盾。∎

**推论**：所有可认证的单元都落在当前解的 support 中，\(U_i\subseteq S_i(z)\)。因此固定 \(z\) 和 \(C\) 时，扫描 \(S_i(z)\) 对同任务单列陷阱是完备的；不会漏掉任何一对可认证的 \(t,u\)。

### 2.3 支持集探测、force 与陷阱

对任务 \(i\) 删除整个 \(S_i(z)\) 后解一次 LP。若不可行，取证书的 essential scope \(E\)：

- 若 \(E\) 只含一个任务 \(j\)，则 \(s_j\in E_j\) 是**集合 force**；
- 若 \(E\) 含两个任务且与已有 force 不相容，则是 **cross** 冲突；
- 若 \(E\) 跨多个任务，则加入 clause \(E\)（禁止同时落在 \(E\) 中）。

同任务出现两个不相交的 force（单元陷阱或集合陷阱）直接 NO；跨任务的 force 违反优先序边或容量时刻也直接 NO。以上规则和 span-first 顺序均继承 QSP。

### 2.4 纯 NO 模式

`yes_scan=False` 时，`decide` 只跑一遍 QSP 等价搜索：

    self.budget = budget
    self.nodecap = nodecap
    v, why = self._search([(0,1)] * N, 0)

这条路径在 252 个 NO 上与 QSP **逐例**给出相同的 LP 数、节点数和 probe 数（聚合 577 LP / 283 节点 / 74 probes），因为 `_farkas` 先走 `farkas_int`，只有失败才进入 row-core 恢复，不改变原来的力/陷阱行为。

## 3. 向上归约：YES 侧

### 3.1 从 LP 分布到优先级

根 LP 的分数解给出

\[
d_i(t)=\frac{z_{i,t}}{\sum_{u\in D_i} z_{i,u}}.
\]

独立采样 \(t_i\sim d_i\)，令

\[
\mathrm{rank}_i=t_i+\varepsilon_i,\qquad \varepsilon_i\sim U(0,10^{-6}),
\]

用 \(\mathrm{rank}\) 排序可开工任务。\(\varepsilon\) 只用于打破相同开始时间的平局，不改变时间语义。

### 3.2 串行 SGS + 有界 DFS

`_sgs_dfs(rank, nodecap)` 的每一步：

1. 取所有前驱已完成的任务（available）；
2. 按 \(\mathrm{rank}\) 升序尝试；
3. 对每个任务、每台 eligible 机器，算最早可行开始 \(t\)（满足优先序、机器空闲、\(t\le \mathrm{latest}_i\)）；
4. 递归；若整棵子树失败则回溯，换下一个任务/机器。

这是**活动调度**（active schedule）生成器。经典串行 SGS 定理：若存在可行调度，则存在一个活动可行调度，且每个活动调度都可由某个优先级表生成。因此固定优先级表时，DFS 对「任务 × 机器」的离散选择是完备的；不确定性只来自优先级表。构造器用随机采样生成不同的表，用有界 DFS 在表附近做修正。

### 3.3 调度重放

`_schedule_from_z` 处理 LP 顶点已经整数的情况：从 \(z\) 读出每个任务的开始时间；非资格感知时按开始时间贪心分配机器；最后调用

    check_schedule(inst, h, start, mach)

逐项检查：

- 每个任务只开始一次，\(0\le s_i\)，\(s_i+p_i\le h\)；
- 机器在 \(\mathrm{elig}(i)\) 中；
- 每条优先序边 \(s_j\ge s_i+p_i\)；
- 每台机器上的任务区间不重叠。

**YES 只由重放确认**；构造器的中间状态、LP 的整性、采样分布都不算证据。

## 4. 容错层

### 4.1 证书先验证

`_farkas(lp, forbid)` 的顺序：

1. 若注入了 `fail_calls`，直接走恢复；
2. 先调 `farkas_int`（v7.x 路径）；
3. 失败则调 `farkas_core`（dual row-core）；
4. 若注入了 `corrupt_calls`，故意改坏证书的第一个 \(\alpha\) 系数；`verify` 必须抓住；
5. 只有通过验证的证书才返回。

`corrupt_missed` 统计「改坏后仍通过验证」的次数，故障注入实验中为 0。

### 4.2 dual row-core 恢复

对偶 LP 是

\[
\max\ 0\quad\text{s.t.}\quad A_E^T y\ge0,\quad b^T y=-1.
\]

解出 \(y\) 后丢掉 \(y_r=0\) 的行，在剩余行上重解；行核上的证书把丢掉的行补零，就得到全 LP 的证书。因此这是**归约**（把对偶行数变小），不是放松。它只改变证书的表示，不改变「不可行」这一事实。

### 4.3 fail-stop 域分裂

叶 LP 不可行但证书提取失败时，不返回无证书的 NO。`_ft_split`：

1. 找当前 live 域最大的任务 \(i\)；
2. 取其中位时间 \(m\)；
3. 分成 \(D_i^{\le m}\) 和 \(D_i^{>m}\) 两支；
4. 分别递归证明；两支都 NO 才返回 NO；
5. 若分裂预算 `ft_budget` 耗尽，返回 `(None, 'ft-budget')`，即 UNKNOWN。

`proof_complete()` 的条件：

    ft_stuck == 0 and leaf_missing <= ft_splits

即每个缺失证书要么被恢复、要么被一个已证明的分裂替代；如果有 stuck/budget/FT-off 的缺失，证明不完整。`audit_rdf()` 在 `audit_qsp()` 之上再检查：

- 所有单元/force 证书逐条 `verify`；
- 若 `yes_ok=True`，必须有 `schedule` 且通过 `check_schedule`。

## 5. 决定过程

    def decide(budget, nodecap):
        if not yes_scan:
            return qsp_search(budget, nodecap)          # 单遍 NO
        # phase A: 小预算 NO
        budget = min(budget, 12); nodecap = min(nodecap, 200)
        v, why = search(root)
        # 根 lazy 分离可能先耗尽小预算；直接解当前割集取见证
        if v is None and root_z is None:
            res = LP(C).solve()
            if res.status == infeasible: return NO, 'root-core'
            if res.status == feasible:  root_z = res.x
        # phase B1: 小构造器
        if v is None and root_z is not None:
            v = construct(root_z, trials=8, nodecap=500)
        # phase B2: 大构造器（全局 60k 节点）
        if v is None and root_z is not None and yes_nodes < 60000:
            v = construct(root_z, trials=48, nodecap=4000)
        # phase C: 全预算 NO
        if v is None:
            budget = budget_full; nodecap = nodes + nodecap_full
            v, why = search(root)
        return v, stats(why)

预算语义：

- `lp_solves` 统计所有 LP，包括 phase A、probe、恢复和 root_z fallback；
- 构造器的 SGS 节点单独计入 `yes_nodes`，不占 LP 预算；
- phase C 重置为完整 `budget`（不是剩余预算），所以总 LP 可能比单遍 QSP 多出 phase A 的至多 12 次；这是 anytime 的取舍。
- `yes_scan=False` 不做 phase A/B，因此没有这个额外开销。

## 6. 正确性

### 6.1 向下可靠性

**定理 1（NO 可靠性）**：若 `_search` 返回 `False`，则不存在满足 \(h\) 的可行调度。

证明沿用 v7.1/v7.2 的归纳：每个返回 NO 的节点是以下之一：

- LP 不可行，且有 `verify` 通过的 Farkas 证书；
- 空域/空任务，由 `_empty_job` 检测；
- 某个 clause \(E\subseteq F\)，而 \(E\) 是之前叶证书的 essential scope；
- 同任务两个不相交 force，或跨任务 force 违反硬约束；
- FT 分裂的两个子节点都返回 NO。

这些情况覆盖了当前节点的整个域；每个分支要么有证书，要么被已证明的 clause/force 排除。归纳到根，所有可行调度都被排除。∎

### 6.2 向上可靠性

**定理 2（YES 可靠性）**：若 `_search`/`_yes_construct` 返回 `True`，则 `check_schedule` 通过，因此调度可行且 makespan \(\le h\)。

证明是直接的：YES 只在两种情况下产生：

1. LP 顶点整数，`_schedule_from_z` 读出调度并通过 `check_schedule`；
2. 构造器 `_sgs_dfs` 返回一个完整调度，并通过同一个 `check_schedule`。

`check_schedule` 独立于构造过程，逐项检查域、优先序、资格和机器不重叠。∎

### 6.3 容错保证

**定理 3（容错）**：

- 损坏证书若不能通过 `verify`，不会被用于证明；`corrupt_missed=0` 是这一条的可观测证据。
- 证书提取失败时，`_farkas` 先尝试 row-core 恢复；恢复失败且 `ft_on=True` 时，`_ft_split` 把该叶替换成两个子问题；只有两个子问题都 NO 才向上返回 NO。
- 若分裂预算耗尽，返回 UNKNOWN；不会出现「无证书的 NO」。
- `audit_rdf=True` 且 `proof_complete=True` 时，所有 NO 证书和 YES 调度都可独立重放。

### 6.4 相对完备性

**定理 4（不丢 NO）**：在相同 LP 割集和相同预算下，BRC 的 phase A/C 搜索树与 QSP 的搜索树相同；构造器只增加 YES 出口，不删除任何 NO 分支。因此：

- 若 QSP 在预算内证明 NO，BRC 也证明 NO（除非构造器先找到一个通过重放的 YES；但若 QSP 的 NO 证明正确，这种情况不可能发生）；
- 若 BRC 返回 UNKNOWN，可能是 phase A 小预算、构造器节点上限或 FT 分裂上限导致的；`yes_scan=False` 可消除 phase A/B 的影响。

注意：phase C 重置完整预算，所以「相同预算」应理解为「单遍 QSP 的预算」；BRC 的总 LP 可能多出 phase A 的至多 12 次。

## 7. 复杂度

- **NO 搜索**：每个节点 1 次 LP，加至多 `topk` 次分离 LP；每个 probe 1 次 LP。最坏情况仍是指数级（NP-hard 问题的必然），实测 252 个 NO 共 577 LP / 283 节点。
- **YES 构造**：最多 56 次采样；每次 SGS DFS 至多 `nodecap` 个节点；全局 60k 节点。每个 SGS 节点做一次 available 排序和至多 \(n\cdot m\) 个机器选择；回溯要恢复 `busy`、`predfin`、`rem`。实测 84 trials / 35,711 节点。
- **空间**：LP 列数 \(O(n\cdot T\cdot|\mathrm{elig}|)\)；证书规模与 LP 行数同阶；SGS 状态 \(O(n+m)\)。

## 8. 实验结果

数据：

- 141 个 NO 基准：`exp/v20/holdout_cases50.pkl`、`exp/v28/synth2_45.pkl`、`exp/v14/{large_a,large_b,large_het}.pkl`、`exp/v13/hard3.pkl`、`exp/v18/deep.pkl`，均取 \(h=\mathrm{OPT}-1\)；
- 60 个扰动：`exp/v71/perturb60.pkl`，\(h=\mathrm{OPT}-1\)；
- 51 个压力集：`exp/v81/h5h47_branch.pkl`，全部 NO；
- 141 个 YES：同一批基准文件取 \(h=\mathrm{OPT}\)。
- 规模：\(n=11\ldots21\)，\(m\) 随实例；本机 Python 3.12 / SciPy 1.18.1 HiGHS。

### 8.1 NO：252 例

| 方法 | NO | LP | 节点 | probes | audit | proof | 墙钟 |
|---|---:|---:|---:|---:|---:|---:|---:|
| QNC v7.1 | 252 | 585 | 415 | 0 | 252 | — | 4.03 s |
| QUC v7.2 | 252 | 636 | 286 | 0 | 252 | — | 4.30 s |
| QSP v7.6 | 252 | 577 | 283 | 74 | 252 | — | 3.97 s |
| **BRC 纯 NO** | **252** | **577** | **283** | **74** | **252** | **252** | **4.05 s** |
| BRC 统一模式 | 252 | 595 | 299 | — | 252 | 252 | 4.89 s |

- 纯 NO 模式与 QSP **逐例**相同（LP、节点、probes 全部一致），但额外提供 `proof_complete` 和容错层；墙钟多约 0.08 s，来自证书验证。
- 统一模式只多 18 LP / 16 节点 / 0.84 s；252 例中只有压力集的一个实例触发构造器，且被 60k 节点上限截住。
- 分族：141 基准 QSP/BRC 145 LP / 131 节点；60 扰动 115/60；51 压力 317/92。QNC 为 147/137、121/76、317/202；QUC 为 145/131、115/60、376/95。
- 7 个「根 LP 可行但分数」的实例仍由 QSP 的单元/支持探针在根层闭合，每例 2 次 probe；BRC 没有破坏这一性质。

### 8.2 YES：141 例

| 方法 | YES | UNKNOWN | NO | LP | 节点 | 构造调用/trials | SGS 节点 | 验证调度 | 墙钟 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| QUC6 v7.2 | 48 | 93 | 0 | 712 | 141 | — | — | — | 3.96 s |
| **BRC** | **141** | **0** | **0** | **1102** | **326** | **45 / 84** | **35,711** | **141** | **7.30 s** |

- 97 例在 phase A 的 12 LP 内直接由整数 LP 顶点闭合（`_schedule_from_z` + `check_schedule`）；
- 43 例由 phase B1（8 trials / 500 nodes）闭合；
- 1 例（holdout 35）phase B1 失败，phase B2 用 5 次额外 trial 闭合；该例总计 2 次调用、13 trials、20,029 SGS 节点、0.209 s；
- 141/141 `audit_rdf` 通过，141/141 调度通过独立重放；
- 相对 QUC6：YES 覆盖 48→141，LP 712→1102（+55%），墙钟 3.96→7.30 s（+84%）。这就是「把 93 个 UNKNOWN 全部闭合」的代价。

### 8.3 故障注入：7 个 hard NO

对象：`holdout:5,47`、`large_a:5`、`large_het:0,3,7`、`hard3:4`，均 \(h=\mathrm{OPT}-1\)。

| 模式 | NO | UNKNOWN | recovered | forced_fail | caught | missed | missing | splits | stuck | audit | proof |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| clean | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 7 | 7 |
| corrupt1 | 7 | 0 | 7 | 0 | 7 | 0 | 0 | 0 | 0 | 7 | 7 |
| fail1 | 7 | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 7 | 7 |
| corrupt1 + no-recover | 7 | 0 | 0 | 0 | 7 | 0 | 6 | 6 | 0 | 7 | 7 |
| fail1 + no-recover | 7 | 0 | 0 | 7 | 0 | 0 | 6 | 6 | 0 | 7 | 7 |
| fail-all + no-recover | 0 | 7 | 0 | 459 | 0 | 0 | 455 | 448 | 7 | 7 | 0 |

- `corrupt1`：7 个损坏证书全部被 `verify` 抓住，7 个都由 row-core 恢复；`missed=0`。
- `fail1`：7 个强制失败全部由 row-core 恢复，判决不变。
- 关闭恢复后，6 个叶证书缺失触发 6 次域分裂，两个子问题都成功证明，判决仍为 7/7 NO；第 7 个损坏发生在 probe 而非叶子，所以没有 `leaf_missing`。
- 全部失败且关闭恢复：7 个实例都 fail-stop 成 UNKNOWN，`ft_stuck=7`、`proof_complete=False`；没有任何无证书的 NO。这正是容错层想要的行为。

## 9. 复现文件

- `exp/v8a/rdf.py`：BRC-ALC 实现（`RDF` 类，含 `_farkas`、`farkas_core`、`_ft_split`、`_schedule_from_z`、`_sgs_dfs`、`decide`、`audit_rdf`、`proof_complete`）。
- `exp/v8a/bench_rdf.py`：NO 252（QNC/QUC/QSP/BRC 纯 NO）+ YES 141（QUC6/BRC）；输出 `exp/v8a/bench_rdf.json`。
- `exp/v8a/bench_ft.py`：故障注入；输出 `exp/v8a/bench_ft.json`。
- `exp/v8a/bench_unified.py`：BRC 统一模式在 252 个 NO 上的开销；输出 `exp/v8a/bench_unified_no.json`。
- 依赖：`exp/v76/qsp.py`（向下引擎）、`exp/v76/smc.py`（`farkas_obj`）、`exp/v72/quc.py`、`exp/v71/qnc.py`、`exp/v60/cert.py`、`exp/v90/grsc.py`（`check_schedule` 参考）。

复现命令（工作目录 `/home/runner/work/xuen/xuen/workspace`）：

    .venv/bin/python exp/v8a/bench_rdf.py
    .venv/bin/python exp/v8a/bench_ft.py
    .venv/bin/python exp/v8a/bench_unified.py

## 10. 已知风险与边界

1. **YES 构造器是随机化、有界节点的**：60k SGS 节点和 48 次采样之外不保证找到调度；在本数据上 141/141，但不能外推成「所有 YES 都能闭合」。更大的实例可能需要提高 `yes_node_budget`，或换确定性 DFS/CP。
2. **采样只用一个根 LP 解**：\(d_i(t)\) 来自一个可行 \(z\)，不是所有可行解的凸组合；它可能错过只在另一个等价 LP 顶点才显现的好顺序。这是启发式，不是完备性来源。
3. **NO 侧仍依赖 SD 割**：若根 LP 的 lazy 分离本身在预算内无法收敛，BRC 会返回 UNKNOWN（`roundcap`）而不是 NO；phase A 的 root_z fallback 只帮助 YES 构造器，不帮助 NO 证明。
4. **容错注入是合成的**：只模拟证书提取失败/损坏，不模拟 LP 求解器数值失败、内存不足或对抗性割。`farkas_core` 在严重数值问题下也可能失败，此时只能 fail-stop 成 UNKNOWN。
5. **统一模式在少数 NO 上有构造器开销**：压力集 idx 47 的 60k SGS 节点是实测最坏情况；若已知目标为 NO，应使用 `yes_scan=False`。
6. **规模与基线**：\(n\le21\)，未与 CP/SAT 或商业调度器对比；墙钟受 Python/HiGHS 影响，LP 数比墙钟更可移植。
7. **审计修复的边界**：`audit_qsp` 修了 v7.2 的 cross 字段错位，但审计只覆盖已记录的对象；未触发的规则（例如跨任务共识在本数据上 0 次命中）仍缺少数据验证。

## 11. 一句话最大风险

**YES 侧是随机化、有界节点的构造器，60k 节点和 48 次采样之外不保证找到调度；NO 侧仍依赖 SD 割的强度，若根 LP 的 lazy 分离本身耗尽预算，BRC 会诚实地返回 UNKNOWN，而不是一个没有证书的 NO。**
<!-- ARTIFACT:END -->
