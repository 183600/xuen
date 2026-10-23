# 产物区 · v7.2 UCP-ALC（Unit-Core Probing ALC）

本轮产物是 **v7.2 UCP-ALC**，直接建立在 v7.1 QNC-ALC 之上。v6.0 的 SD 割数学、v6.1 的 ALC 证书管线、v7.1 的 quorum/force/median 分支全部保留；本轮只增加一个新阶段：

> **根层反事实探测**：在 LP 仍可行时，主动禁掉一个 start，问 LP 是否还可行；若不可行，这个 start 就是 unit core，禁掉它得到的 Farkas 证书是一条全局 unit clause。同一任务上两个不同 unit core 构成 pair refutation，直接 NO。

一句话概括与 v7.1 的关系：v7.1 把证书当作「不可行节点的副产品」，并研究它能证明多大的区域；v7.2 改变证书的**产地**，在可行节点上主动制造它，并把证明对象从「一棵 DFS 树 + 多个 quorum」压缩成「两条 unit clause + 一条逻辑规则」。

## 0. 本轮增量

1. **unit core**：`Probe(i,t)` 定义为 `P(C, B∖col(i,t))` 不可行；它等价于 v7.1 的 quorum 在 `|E|=1` 时的特例，但 v7.1 只能从不可行叶子得到，v7.2 可以在根层可行 LP 上得到。
2. **pair refutation**：同一任务的两个不同 unit core 直接矛盾，返回 NO；不需要 DFS 覆盖，也不需要多证书混合。
3. **确定性探测调度**：job 按紧割度 `deg_C(i)` 排序，atom 按 LP 质量排序；没有 RNG。它是随机探测分布 π 的众数版本（MoCE 的贪心去随机化）。
4. **root-only 的 soundness 边界**：非根 probe 的 unit clause 只在分支内成立，不能提升为全局 clause；本轮把 probe 硬限制在 depth 0，并把这个限制写成定理而不是工程约定。
5. **pair-only + gate**：只接受「两张 unit 证书」的 pair refutation；单个 unit core 默认不 force，避免改变 v7.1 的搜索路径。gate 在第一个 probe 可行时立刻放弃，把失败开销限制在 1 LP。

推荐接口：

    UCP(inst, h, probe_on=True, probe_jobs=1, probe_cap=8,
        probe_gate=True, use_force=False)
    .decide(budget, nodecap, max_rounds, topk) -> (verdict, state)
    .audit_full() -> bool

## 1. 符号

| 符号 | 含义 |
|---|---|
| `n, m, h` | 任务数、机器数、待判定的 makespan 上界（NO 基准 `h=OPT-1`） |
| `p_i, pred(i), succ(i), elig(i)` | 加工时间、前驱、后继、可选机器集 |
| `est_i, q_i` | 优先序头/尾 |
| `D_i = {est_i,…,h-q_i-p_i}` | 任务 i 的可行开始时间域 |
| `D = ∪_i D_i` | 全 start 集 |
| `c = (i,t)` 或 `(i,k,t)` | LP 列：start `(i,t)` 在机器 k 上；`col(i,t)` 是它的所有机器副本 |
| `z_c ∈ [0,1]` | 分数开始指示 |
| `F_i(t) = Σ_{s≤t} z_{i,s}` | 开始时间累积分布 |
| `C` | 已分离的 SD 割集，只增 |
| `B ⊆ D` | 当前允许的列（bounds）；`B_i = B ∩ D_i` |
| `P(C,B)` | 带割集 C、列集 B 的 start-time LP |
| `Φ = (α,β,λ,scale)` | 整数 Farkas 证书 |
| `σ_c = (A^T y)_c` | 列 c 的松弛 |
| `Probe(i,t)` | `P(C, B∖col(i,t))` 是否可行 |
| `κ(i,t)` | unit clause：每个满足 B 的可行调度都有 `s_i=t` |
| `Atoms_i(z)` | 任务 i 的分数 start 集合：`0 < Σ_k z_{i,k,t} < 1` |
| `deg_C(i)` | 割集 C 中碰到 job i 的割数：`|{(a,b,s)∈C : a=i 或 b=i}|` |
| `Q, force, L` | clause 集、全局强制域、已认证叶子 |
| `B_lp, Π` | 已用 LP 数、probe 计数 |
| `Λ` | pair witness：`(i,t1,t2,Φ1,Φ2)` |

## 2. 形式定义

### 2.1 带列限制的 start-time LP

对 `B⊆D`，`P(C,B)` 的变量是 `{z_c : c∈B}`：

    Σ_{t : (i,t)∈B} z_{i,t} = 1                         ∀i
    Σ_{i} Σ_{s≤t<s+p_i, (i,s)∈B} z_{i,s} ≤ m            ∀t
    F_i(t) ≥ F_j(t+p_i)                                  ∀(i→j), ∀t
    0 ≤ z ≤ 1

异构资格时把 `(i,t)` 换成 `(i,k,t)`，assignment 对 k 求和。`P(C,D)` 是根层 LP，`P(C,B)` 是节点 LP。`C` 的每一行都是原整数问题的有效不等式（SD 割），所以 `P(C,B)` 不可行 ⇒ 该子问题无整数解。

### 2.2 probe 与 unit core

对 `(i,t)`，定义

    Probe_C,B(i,t) = INFEASIBLE   iff   P(C, B∖col(i,t)) 不可行.

若 `Probe` 不可行，称 `(i,t)` 是（相对于 `C,B` 的）**unit core**。用 `farkas_int` 提取整数证书 `Φ`，并要求

    verify(Φ, forbid={(i,t)}) = True,
    E(Φ) = {(i,t)},

即证书在除 `(i,t)` 外的所有列上 `A^T y ≥ 0`，且 `b^T y < 0`。由于根层 `P(C,D)` 可行，`E=∅` 不可能，所以 `E={(i,t)}` 是唯一可能。

**与 v7.1 quorum 的关系**：v7.1 的 `E(Φ,F)={c∈F:σ_c<0}` 是一个不可行列集的 essential scope；`|E|=1` 时它就是 unit core。区别在产地：v7.1 需要 `F` 已经不可行，v7.2 只需要 `F∖{c}` 不可行。

### 2.3 unit clause 与 pair refutation

**unit clause**：

    κ(i,t):  每个满足 B 的可行调度 s 都有 s_i = t.

**pair refutation**：

    κ(i,t1) ∧ κ(i,t2) ∧ t1≠t2  ⇒  ⊥.

根层 `B` 只含全局 force，所以根层的 `κ` 是全局 clause。非根 `B` 含分支限制，`κ` 只在分支内成立；见 4.6。

### 2.4 确定性探测调度

给定收敛 LP 的分数解 `z`：

    Atoms_i(z) = { t : 0 < Σ_{k} z_{i,k,t} < 1 }
    mass_i(t)  = Σ_{k} z_{i,k,t}
    Eligible   = { i : |Atoms_i(z)| ≥ 2 }
    key(i)     = ( 1[|Atoms_i(z)| ≠ 2],  -deg_C(i),  i )
    i*         = argmin_{i∈Eligible} key(i)
    (t1,t2)    = mass_i(t) 最大的两个 start

排序键的第一项把「恰好两个分数 atom」的 job 放在前面：两次 probe 覆盖该 job 的全部分数支撑，若两次都不可行，pair 是对这个 job 的完整反驳。第二项是紧割度；第三项是固定 tie-break。

**去随机化解释**：定义代理分布

    π(i) ∝ deg_C(i)   (i∈Eligible)
    π(t | i) ∝ mass_i(t)

随机探测从 π 抽 `(i,{t1,t2})`。`i*` 最大化 `π(i)`；`(t1,t2)` 最大化 `π(t1|i)π(t2|i)`。所以 UCP 的调度是代理分布的**众数**，也就是 MoCE 的贪心确定性版本。注意：代理分布不等于真实成功率；真实精度是实验量（7/7）。

### 2.5 状态与 anytime

    S = (C, Q, force, L, B_lp, Π)

不变式与 v7.1 相同：`C,Q,L` 只增，`force` 只缩。新增 `Π` 只记录 probe 次数与 pair witness，不影响单调性。`budget` 计所有 LP（包括 probe）；`nodecap` 计 DFS 节点。超预算返回 UNKNOWN，保留状态。

## 3. 算法

### 3.1 主过程

    function UCP_DECIDE(inst, h, budget, nodecap):
        C = ∅; Q = ∅; force = {}; L = []; probes = 0
        if ∃i: D_i = ∅: return NO                 # 零 LP 前检
        return DFS(D, depth=0)

    function DFS(B, depth):
        B = apply_force(B)
        if ∃i: B_i = ∅: return NO                  # 空域
        F = forbids(B)
        for E in Q:
            if E ⊆ F: return NO                    # v7.1 clause 剪枝
        res, z, converged = solve_lazy_SD(B, C)    # 计 1..r 次 LP
        if res == INFEASIBLE:
            Φ = farkas_int(C, B)                   # v7.1 叶子证书
            E = { c∈F : σ_c(Φ) < 0 }
            L.append((F,E,Φ))
            if E ≠ ∅: Q.add(E)
            if |jobs(E)| == 1:
                force[i] = force.get(i,D_i) ∩ E_i
            return NO
        if z is integral: return YES

        # ---------- 根层反事实探测（本轮新增） ----------
        if depth == 0 and converged and probes < probe_cap and not gate_off:
            acted = False
            for i in rank_jobs(z)[:probe_jobs]:
                units = []
                for t in top2_atoms(i, z):
                    if probes >= probe_cap: break
                    probes += 1
                    if Probe(i,t) == INFEASIBLE:
                        Φ = farkas_int(C, B∖col(i,t))
                        if verify(Φ, forbid={(i,t)}):
                            units.append((t, Φ))
                    elif units == [] and probe_gate:
                        gate_off = True            # 第一个 probe 可行，放弃
                        break
                if len(units) == 2:
                    L += [({(i,t)}, {(i,t)}, Φ) for (t,Φ) in units]
                    Q += [{(i,t)} for (t,Φ) in units]
                    pair_witness = (i, units[0][0], units[1][0])
                    return NO                      # pair refutation
                if len(units) == 1 and use_force:
                    st = learn_unit(units[0])
                    if st == empty: return NO
                    acted = True
                    break
            if acted:
                continue                            # 重新解 LP

        # ---------- v7.1 median 分支回退 ----------
        (i, mid) = median_branch(z)
        a = DFS(B with t>mid forbidden for i, depth+1)
        if a != NO: return a
        return DFS(B with t≤mid forbidden for i, depth+1)

### 3.2 probe 的实现

    function Probe(i, t):
        B' = B
        for c in col(i,t): B'[c] = (0,0)          # 异构资格时删所有机器副本
        res = lp.solve(B')                        # 不分离新割，只解一次
        return res.status == INFEASIBLE

`lp.solve` 用当前割集 `C`，不新增割。这点很重要：

- 若返回 INFEASIBLE，证书对 `C` 有效，`C` 的每一行都是原问题的有效不等式，所以 unit clause 可靠；
- 若返回 FEASIBLE，可能只是割不够，产生**假阴性**（漏掉一个真正 unit core），但不会产生假阳性；
- probe 不改变 `C`，所以 pair-only 失败时回退的搜索路径与 v7.1 完全一致。

### 3.3 为什么只 probe 根层

`Probe` 得到的 `κ` 是**相对于 B** 的。根层 `B = D ∩ force`，其中 `force` 只来自根层 unit clause 或 v7.1 的 quorum；两者都是全局有效的。所以根层 `κ` 可以全局化。

在深度 `d>0`，`B` 含有分支禁掉的列。此时 `P(C,B∖col(i,t))` 不可行只说明「在这个分支里，s_i=t 是必须的」；分支外可能有 `s_i≠t` 的可行调度。把这种 `κ` 加进全局 `force` 会错误地砍掉分支外的解。因此代码把 probe 硬限制在 `depth == 0`，而不是做成一个可调参数。

### 3.4 gate 与代价

`gate` 是一个顺序假设检验：

- 第一个 probe 可行 → 这个 LP 不「脆」，立刻放弃整个 probe 阶段，代价 1 LP；
- 第一个 probe 不可行 → 继续 probe 第二个；两个都不可行 → NO；第二个可行 → 记下单个 unit core，但默认不 force，回退 DFS，代价 2 LP。

默认 `probe_jobs=1`，所以一次运行最多 2 个 probe；`probe_cap=8` 只是防御性上限。pair-only + gate 的最坏额外开销是 2 LP，而收益是「根层 2 证书闭合」。

### 3.5 与 v7.1 的关系

- 若 `probe_on=False`，UCP 的 `_solve`/`_branch` 与 QNC 等价。实验中 `ucp_np` 必须逐项等于 QNC（147 LP / 137 节点），这是实现 sanity check。
- 若 probe 失败，UCP 回退到 v7.1 的 median 分支、叶子 Farkas、quorum clause、force 和 audit；不改任何一行数学。
- 因此 UCP 是 v7.1 的**严格扩展**：NO 证明要么是 v7.1 的树，要么是新的 2-clause refutation。

### 3.6 审计

    function AUDIT_FULL(L, pair_witness):
        for (F,E,Φ) in L:
            if not E ⊆ F: return False
            if not verify(Φ, forbid=E): return False
        if pair_witness is not None:
            (i,t1,t2) = pair_witness
            if t1 == t2: return False
            if (i,t1) not in L or (i,t2) not in L: return False
        return True

pair refutation 的检查器只需要实现一条规则：

    verify(Φ1, forbid={(i,t1)}) ∧ verify(Φ2, forbid={(i,t2)}) ∧ t1≠t2
    ⇒ NO

不需要 DFS 覆盖检查；这是它比 v7.1 的树证明更简单的地方。回退 DFS 的覆盖仍由构造保证，尚未做独立树检查（见风险）。

### 3.7 预算

- `budget` 计所有 LP，包括 lazy SD 分离轮和 probe；
- `nodecap` 计 DFS 节点；
- probe 超预算 → 抛 `Budget`，返回 UNKNOWN，保留 `C/Q/force/L`；
- probe 失败不产生判决；判决只在「整数解」或「已验证证书」时给出。

## 4. 正确性

### 4.1 unit clause 引理

设 `Probe_C,B(i,t)` 不可行。则每个满足 `B` 的可行调度 `s` 都有 `s_i=t`。

**证明**：反设存在可行 `s`，满足 `B` 且 `s_i≠t`。`s` 的指示向量只使用 `B∖col(i,t)` 的列，且满足 assignment、容量、precedence/SD 约束，所以它是 `P(C,B∖col(i,t))` 的可行点，与 probe 不可行矛盾。∎

### 4.2 根层 lifting

设 `B_root = D ∩ force`，其中 `force` 的每个元素都由根层 unit clause 或 v7.1 的全局 quorum 推出。归纳假设 `force` 全局有效（只删掉不可能的开始），则 `B_root` 全局有效：任何可行调度都满足 `B_root`。由 4.1，根层 probe 的 `κ(i,t)` 对任何可行调度成立，是全局 clause。∎

### 4.3 pair refutation

设 `κ(i,t1)` 与 `κ(i,t2)` 都已由 4.1/4.2 证明，且 `t1≠t2`。任一可行调度同时满足 `s_i=t1` 和 `s_i=t2`，矛盾。所以不存在可行调度，UCP 返回 NO 正确。∎

### 4.4 回退可靠性

若 probe 阶段没有返回 NO，UCP 进入与 v7.1 相同的 DFS。v7.1 的可靠性（SD 割有效、Farkas 证书整数重放、quorum 引理、force 单调）原样继承。若 UCP 返回 YES，则 LP 的整数解 `z` 满足所有 assignment/容量/SD 约束，是一个可行调度；SD 割是有效不等式，不会删掉可行整数解，所以 YES 正确。∎

### 4.5 确定性

- `rank_jobs` 的排序键是全序：`(len≠2, -deg, id)`，最后按 job id；
- atom 排序键 `(-mass, t)`，最后按 start 时间；
- `self.lp.cols` 的顺序由 SDLP 构造固定；`_start_cols` 按该顺序建立；
- `farkas_int` 的 DENS 网格是固定元组，舍入用 `np.rint`（banker's rounding，确定性）；
- 没有 RNG、没有 hash 顺序依赖、没有时间/线程依赖。

因此同一 `(inst,h,config)` 的判决、LP 数、probe 序列、pair witness 逐位可复现。

### 4.6 为什么非根 probe 不能全局化（反例草图）

设某分支在 job i 上取 `B = {s_i ≤ 5}`。在左子问题里，`P(C,B∖{(i,3)})` 可能不可行，于是 `κ(i,3)` 在左分支成立；但右分支 `{s_i>5}` 里可能存在 `s_i=8` 的可行调度。若把 `κ(i,3)` 加进全局 `force`，就会把 `s_i=8` 砍掉，可能把 YES 误判成 NO。v7.1 的 `E` 没有这个问题，因为 `E` 的证书在 `E` 外的所有列上重放通过，是**无条件**的；probe 的 `κ` 带 `B` 条件，所以只能在根层使用。∎

### 4.7 unit core 的最小性

根层 `P(C,D)` 可行。若 `(i,t)` 是 unit core，则 `P(C,D∖{(i,t)})` 不可行，而 `P(C,D)` 可行；所以 `{(i,t)}` 是不可约的（去掉它就没有 forbids，LP 回到可行）。它是大小 1 的最小非空 core。∎

### 4.8 与 v7.1 quorum 的关系

v7.1 的 `E` 可以是多 job 的列集，例如 `{3:8, 11:29, 11:30}`；UCP 的 unit core 是 `|E|=1`。两者不是替代关系：

- v7.1 的 quorum 在叶子不可行时免费得到，能覆盖跨 job 的冲突；
- UCP 的 unit core 在根层可行时主动得到，能给出「单 start 必然性」；
- v7.1 的 `E` 可以进 clause 剪枝/force；UCP 的 `κ` 也可以，但本轮为了避免路径回归，默认只把 pair 用作 NO 证明。

## 5. 复杂度

- 一次 probe 解一个 LP：变量 `O(|B|) = O(nmT)`，约束 `O(mT+n+|C|)`；与一个普通节点 LP 同阶。
- 一次排名：`O(N + |C| + n log n)`，`N = |D|`。
- 根层 probe 最多 `2·probe_jobs` 次 LP；默认 `probe_jobs=1`，即最多 2 次；`probe_cap=8` 是硬上限。
- 总 LP ≤ `budget`，总节点 ≤ `nodecap`。
- 空间：`O(nmT + |C| + |Q| + |L|)`，probe 不增加割，矩阵不增长。
- 证书提取：`farkas_int` 一次 LP + `|DENS|` 次舍入检查，`|DENS|=215`；与 v7.1 相同。
- 最坏情况：probe 失败并回退，额外 1–2 LP；不会改变 DFS 的渐近复杂度。

## 6. 实验

### 6.1 设置

- 数据：141 例 NO 基准（holdout 50、synth2_45、large_a 8、large_b 10、large_het 8、hard3 12、deep 8），`h=OPT-1`；60 个 v7.1 扰动例；13 个 `h=OPT` 的 YES 子集（holdout idx 0,4,…,48）。
- 环境：Python 3.12、NumPy 2.5.4、SciPy 1.18.1（HiGHS），单线程；工作目录 `/home/runner/work/xuen/xuen/workspace`。
- 预算：`max_rounds=60`、`nodecap=5000`；实测远低于上限。
- 审计：`audit_full()` 对每个叶子 `verify(Φ,forbid=E)`，并检查 pair witness。
- 配置：`UCP(probe_on=True, probe_jobs=1, probe_cap=8, probe_gate=True, use_force=False)`；消融时改参数。

### 6.2 主结果（141 例 NO）

| 方法 | NO | LP | DFS 节点 | 叶子 | 墙钟(s) |
|---|---:|---:|---:|---:|---:|
| v6.1 ALC | 141 | 159 | 149 | — | — |
| v7.1 QNC | 141 | 147 | 137 | 134 | 1.09 |
| **v7.2 UCP（pair-only）** | **141** | **145** | **131** | 133 | **1.07** |
| UCP，关闭 probe | 141 | 147 | 137 | 134 | 1.08 |
| UCP，force + 2 jobs | 141 | 145 | 131 | 133 | 1.07 |

ALC 的 159/149 引自 v7.1；墙钟只比较本次同机运行的 QNC/UCP，1.07 vs 1.09 是噪声级差异，不作为主结果。

- 只有 holdout idx 5/47 进入 probe；其余 139 例路径不变。
- idx 5：6 LP / 1 节点（QNC 6 / 3）；idx 47：5 LP / 1 节点（QNC 7 / 5）。
- 主表相对 QNC 只省 2 LP / 6 节点（−1.4% / −4.4%）；相对 ALC 省 14 LP / 18 节点（−8.8% / −12.1%）。
- `ucp_np` 与 QNC 逐项相同（147/137），说明 probe 关闭时实现没有改变 v7.1。

### 6.3 分支子集（7 例：2 原始 + 5 扰动）

| 实例 | QNC LP/节点 | UCP LP/节点 | pair witness `(job,t1,t2)` |
|---|---|---:|---|
| holdout 5 | 6 / 3 | 6 / 1 | (6, 12, 17) |
| holdout 47 | 7 / 5 | 5 / 1 | (3, 6, 8) |
| h5-6 | 6 / 3 | 6 / 1 | (6, 13, 18) |
| h5-16 | 6 / 3 | 6 / 1 | (6, 13, 18) |
| h47-6 | 5 / 3 | 5 / 1 | (4, 11, 13) |
| h47-18 | 7 / 5 | 5 / 1 | (3, 5, 7) |
| h47-26 | 9 / 7 | 5 / 1 | (4, 11, 13) |
| **合计** | **46 / 29** | **38 / 7** | 7/7 |

- 相对 v6.1 ALC 的 52 / 35：LP −26.9%，节点 −80.0%。
- 相对 v7.1 QNC 的 46 / 29：LP −17.4%，节点 −75.9%。
- 7 个实例全部在根层闭合；每个只用 2 张单列 Farkas 证书。
- 平均每个分支例 5.43 LP / 1 节点；QNC 是 6.57 LP / 4.14 节点。

### 6.4 scope 压缩

7 个分支例的叶子统计：

| 方法 | 叶子数 | Σ|F| | Σ|E| | max |E| |
|---|---:|---:|---:|---:|
| v7.1 QNC | 18 | 96 | 59 | 7 |
| v7.2 UCP | 14 | 14 | 14 | 1 |

- UCP 的每个 `E` 都是单列，`Σ|E|` 从 59 降到 14（−76.3%）。
- 这不是「同一个证书变小」，而是证明对象变了：v7.1 证明的是「某个子立方体不可行」，UCP 证明的是「某个 start 必然」。
- 14 个叶子中 7 个来自 7 个 pair 的第一个 unit core，7 个来自第二个；每个 pair 的两条 clause 在同一 job 上。

### 6.5 anytime（201 例：141 + 60 扰动）

| LP 预算 k | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| QNC 已判 NO | 10 | 164 | 186 | 194 | 194 | 195 | 198 | 200 | 200 | 201 |
| UCP 已判 NO | 10 | 164 | 186 | 194 | 194 | **198** | **201** | 201 | 201 | 201 |

- UCP 在 k=5 多判 3 例（198 vs 195），在 k=6 判完全部 201 例（QNC 要 k=9）。
- 每个已判 NO 的实例都通过 `audit_full()`；k=0 的 10 例是零 LP 空域关闭，`audit()` 为空真。
- 141 基准单独看：QNC 在 k=5/6/7 是 139/140/141，UCP 是 140/141/141；UCP 少一个 LP 就锁死 idx 47（7→5），idx 5 仍是 6。

### 6.6 被迫 atom 密度

在 7 个分支例的收敛根 LP 上（只统计 `0<z<1` 的分数 atom）：

| 实例 | cuts | 分数 atom | unit core | 密度 | top job | top-2 都被迫 |
|---|---:|---:|---:|---:|---:|---|
| holdout 5 | 7 | 12 | 8 | 0.667 | 6 | 是 |
| holdout 47 | 7 | 18 | 9 | 0.500 | 3 | 是 |
| h5-6 | 7 | 12 | 8 | 0.667 | 6 | 是 |
| h5-16 | 7 | 12 | 8 | 0.667 | 6 | 是 |
| h47-6 | 2 | 18 | 13 | 0.722 | 4 | 是 |
| h47-18 | 7 | 18 | 9 | 0.500 | 3 | 是 |
| h47-26 | 5 | 14 | 9 | 0.643 | 4 | 是 |

- 密度 50%–72%，top job 的 top-2 精度 7/7。
- 「密度高」是 unit-core probing 能工作的经验前提；它不是定理，见风险 1。

### 6.7 排序消融（7 个分支例）

| 排序策略 | LP | 节点 | 命中 pair |
|---|---:|---:|---:|
| 紧割度 `(-deg, id)`（本轮） | 38 | 7 | 7/7 |
| job id（`id` 升序） | 53 | 29 | 0/7 |
| 最大 LP 质量（top atom mass 降序） | 52 | 27 | 1/7 |
| 固定随机排列（seed=7） | 52 | 27 | 1/7 |

- 紧割度是唯一 7/7 命中的排序；id 排序 0/7，质量排序和固定随机排列各 1/7。
- 这个消融说明收益不是「随便 probe 都能中」，而是「排序信号 + pair 结构」共同作用。
- 但它只有 7 个样本；不能排除「紧割度只是这两个家族的瓶颈结构与 SD 割生成器的相关性」。

### 6.8 YES 侧小测

13 个 `h=OPT` 的 holdout 例（idx 0,4,…,48）：

- UCP 13/13 返回 YES，0 个误判 NO；
- 其中 7 例 probe 开销 0，6 例 probe 开销 1 LP；
- 没有任何一对 unit core 出现在 YES 实例上（否则就会误判 NO，理论上不可能）。

### 6.9 压力集与负结果

用 `gen_stress2.py` 对 holdout/synth 的 p 做 ±1/±2 扰动，重算 OPT，再筛 `h=OPT-1` 且 QNC 需要分支的实例；234 次候选只留下 2 个可用压力例（另一个 590 个去重候选的 `gen_stress.py` 留下 0 个，见 8）：

| 压力例 | QNC LP/节点 | UCP LP/节点 | probe | 结果 |
|---|---|---:|---:|---|---|
| holdout5-p0（p_0=5, h=30） | 6 / 3 | 6 / 1 | 2 | pair (6,10,15)，根层闭合 |
| holdout36-p12（p_12=7, h=31） | 16 / 11 | 17 / 11 | 1 | 第一个 probe 可行，gate 放弃，+1 LP |

负结果：

1. **holdout36 退化 +1 LP**。gate 已经把失败开销压到 1 LP，但「不退化」不成立；只能说「失败开销有界」。
2. **完整 force 版本更差**。在 holdout36 上 `use_force=True` 会 18 LP（pair-only 17，QNC 16）；force 可靠但改变搜索路径，路径变差会吃掉 probe 收益。
3. **根层闭合不总省 LP**。holdout5-p0 的 6 LP 与 QNC 持平，只省节点（3→1）；证书对象变短不等于 LP 变少。
4. **压力集太小**。234 次候选只留 2 例（另有 590 个去重候选留 0 例）；不能支撑「UCP 在一般分支实例上有效」的统计结论。
5. **`probe_jobs=2` 在已知 7 例上没有额外收益**：top job 已经 7/7 命中，第二个 job 只会增加失败开销。默认保持 1。

### 6.10 审计与数值

- 141/141 NO 的 `audit_full()` 通过；60/60 扰动通过；13/13 YES 无证书但返回 YES。
- 14 个 unit 证书全部 `verify(Φ,forbid={(i,t)})` 通过；0 次提取失败（14 次 probe 中 14 次成功提取，其中 7 对是 pair）。
- pair witness 全部满足 `t1≠t2` 且两条 unit clause 在同一 job。
- `E(Φ)={(i,t)}` 对 14 个 unit 证书全部成立；没有出现 `E=∅`（那会与根层可行矛盾）。
- 14 张 unit 证书的 scale 在 13–59 之间（最大 59），远低于 DENS 上限 10000；本轮没有触发舍入失败。

## 7. 风险与下一步

### 7.1 已知风险

1. **排序信号过拟合（最大）**：7/7 精度只来自 7 个实例、两个家族（holdout 5/47 及其扰动）。`deg_C` 与 unit core 的因果关系没有证明；如果它只是这套 SD 割生成器的相关性，换分布后 probe 会花 1–2 LP 却找不到 pair。
2. **主数据集饱和**：139/141 根层闭合，UCP 只省 2 LP；任何「平均加速」都会被这个分布压成噪声。本轮真正的证据是 7 例分支子集的 80% 节点下降，但样本小。
3. **root-only 的盲区**：非根节点上的局部 pair 可以关闭该子树，却不能全局化；本轮完全放弃这类机会。若一个实例只在深分支出现 pair，UCP 不会比 QNC 好。
4. **probe 假阴性**：probe 用冻结的割集，不分离新割；一个真正被迫的 start 可能因为割不够而返回 FEASIBLE，被 gate 放弃。更多割可能让 probe 命中，但也会增加成本。
5. **force 路径回归**：完整局部搜索版本在 holdout36 上 +2 LP；pair-only 是对这个风险的工程回避，不是理论解决。
6. **压力集太小**：只有 2 个额外压力例，且 1 个退化；不能支撑「一般分支实例有效」。
7. **YES 侧只测 13 例**：没有系统测 YES 的 anytime/误差；pair 理论上不会误判 YES，但实验覆盖不足。
8. **数值**：Farkas 舍入依赖 DENS；本轮 14 张 unit 证书的 scale 只有 13–59，余量很大；但更大实例、更多割可能让 scale 上升，仍可能提取失败（本轮 0 次）。
9. **证明对象的检查器**：pair refutation 是「两张证书 + 一条逻辑规则」，不是单张证书；检查器必须实现 `t1≠t2` 和同 job 规则。回退 DFS 的整树覆盖仍未独立检查。
10. **墙钟收益是噪声**：1.07s vs 1.09s 在 141 例上不构成有意义的加速；不要把它当作主结果。

### 7.2 下一步

1. **把 `deg_C` 换成更细的紧度信号**：用割的对偶乘子/活跃度，而不是计数；在更多实例上做 precision@1 曲线。
2. **学习排序但要确定性**：用一个小型决策规则（如 `deg_C/|C|`、job 的 domain 宽度、top-2 mass gap）做离线排序，仍然无 RNG；用 leave-one-family-out 验证。
3. **带 scope 的局部 unit clause**：在非根节点学 `κ(i,t | B)`，只用于该子树的剪枝，不进全局 force；这样可以把 root-only 扩展到「局部 pair 关子树」。
4. **与 QCM 的 mixture 结合**：v8.0 的 cover LP 可以把多条 unit clause 当成一个概率混合来证 NO；UCP 提供单列 clause，QCM 提供多 clause 的组合，两者正交。
5. **更大压力集**：用 OPT 重算 + 多 job 同时扰动，构造 50+ 个分支例；按 n/m/链长分层，测 UCP 的收益曲线。
6. **弱 LP 家族**：减少 m、加长链，让根 LP 更容易可行但整数仍 NO；这是 UCP 最该发挥作用的分布。
7. **证明树序列化**：把回退 DFS 的 split、force 链、unit pair 一起序列化，写独立 checker；把 `audit_full` 从「逐叶 + pair」升级为「整树 + pair」。
8. **probe 缓存**：anytime 下同一 `(C,B,i,t)` 的 probe 结果可缓存；本轮每次预算重跑没有复用，缓存能把 anytime 曲线再左移。

## 8. 复现文件

- `exp/v72/ucp.py`：UCP 状态机、`_solve`（带 converged 标志）、rank、probe、pair refutation、`audit_full`。
- `exp/v72/bench_ucp.py`、`ucp_bench.json`：141 NO + 60 扰动 + anytime + 消融（`ucp_np` / `ucp_f`）。
- `exp/v72/probe_stats.json`：7 个分支例的 cuts / 分数 atom / unit core / top job 精度。
- `exp/v72/rank_ablation.json`：紧割度 / id / 质量 / 固定随机排列的 7 例消融。
- `exp/v72/gen_stress2.py`、`stress2.pkl`、`stress_results.json`：2 个额外压力例（234 次候选筛选）。
- `exp/v72/gen_stress.py`：第一版压力生成器（0 个保留，负结果）。
- 依赖：`exp/v71/qnc.py`（v7.1 基线、`farkas_int`）、`exp/v60/lazy.py`（lazy SD）、`exp/v60/cert.py`（DENS/verify/_row_meta）、`exp/v13/po.py`（heads_tails）。
- 数据：`exp/v20/holdout_cases50.pkl`、`exp/v28/synth2_45.pkl`、`exp/v14/{large_a,large_b,large_het}.pkl`、`exp/v13/hard3.pkl`、`exp/v18/deep.pkl`、`exp/v71/perturb60.pkl`。
- 环境：Python 3.12、NumPy 2.5.4、SciPy 1.18.1（HiGHS）；`PYTHONPATH=.pylibs:.`。

## 9. 一句话最大风险

**紧割度排序的 7/7 精度只来自 7 个实例、两个家族；如果它只是这套 SD 割生成器的相关性而不是可迁移的瓶颈信号，换到别的分布上 root probe 会花 1–2 个 LP 却找不到 pair，本轮的全部收益就归零。**
