## 0. 版本关系与本轮增量

本轮产物是 **v7.1 QNC-ALC（Quorum-Certified Nogood ALC）**，直接建立在 v6.1 ALC 之上：不改 v6.0 的 SD 割数学，不改 v6.1 的中位数分支规则和 anytime 接口形状，只在状态里增加 Q（clause）、force（强制域）、L（叶子证书）。

编号 v7.1 是为了避开工作区已占用的 `exp/v62`（PSS）与 `exp/v70`（DCS）目录；本轮内容不依赖那两条 proof-tree 线。QNC 的 quorum 层与 proof-tree 层正交：proof tree 决定「怎么切」，quorum 决定「切完之后证书还能证明什么」。

本轮增加四件事：

1. **quorum 引理**：一个叶证书的有效 scope 可以严格小于节点的 forbid 集 F，缩到 E={c∈F: 列松弛<0}；
2. **quorum clause**：E 是一条全局约束「至少一个任务的开始落在 E 里」，可用于剪枝；
3. **强制域（force）**：单任务 E 直接给出 s_i∈E_i，把 D_i 永久收缩（单调）；
4. **零 LP 前检**：D_i=∅ 时 0 次 LP 直接 NO。

另加一个可审计对象：每个叶子记录 (F,E,Φ)，独立重放 `verify(Φ, forbid=E)`；全部叶子通过才算 audited。

推荐接口：

    QNC(inst, h, use_quorum=True, use_empty=True)
    .decide(budget, nodecap, max_rounds, topk) -> (verdict, state)
    .audit() -> bool

## 1. 符号

- n：任务数；m：机器数；p_i：加工时间；pred(i)、succ(i)、elig(i)。
- h：待判定的 makespan 上界（NO 基准 h=OPT−1）。
- est_i、q_i：优先序头/尾；D_i = {est_i, …, h−q_i−p_i}，任务 i 的可行开始时间域。
- T=h；列 c=(i,t)，t∈D_i；异构资格时列是 c=(i,k,t)。
- z_{i,t}∈[0,1]：开始时间分数指示；F_i(t)=Σ_{s≤t} z_{i,s}。
- C：已分离的 SD 割集；LP(S) 表示把列集 S 删掉后的 start-time LP。
- Φ=(α,β,λ,scale)：整数 Farkas 证书；α 是 assignment 等式的自由对偶，β_t、λ_{ij,t} 是容量/SD 不等式的非负对偶。
- A：LP 的约束矩阵（行=assignment/容量/SD，列=z）；b：右端。
- σ_c=(A^T y)_c：列 c 的松弛。
- E(Φ,F)：证书 Φ 在 forbid 集 F 下的 **essential scope**。
- Q：quorum clause 集合（每个是列的集合 E）；F_i^force：任务 i 的强制域。
- L：已认证叶子列表，元素为 (F_j,E_j,Φ_j)。
- B：已用 LP 数；N_nodes：DFS 节点数。

## 2. 形式定义

### 2.1 带删除列的 start-time LP

对 S⊆∪_i D_i，LP(S) 的变量是 {z_c : c∈(∪D_i)∖S}：

    Σ_{t∈D_i∖S} z_{i,t} = 1                         ∀i
    Σ_{i} Σ_{s≤t<s+p_i, (i,s)∉S} z_{i,s} ≤ m          ∀t
    F_i(t) ≥ F_j(t+p_i)                              ∀(i→j),∀t
    0 ≤ z ≤ 1

最后一行是 v6.0 的 SD 行，F 用未删除的列计算。LP(∅) 是根层 LP；LP(F) 是 forbid 集 F 的节点 LP。

### 2.2 证书与 essential scope

Φ=(α,β,λ) 是 LP(S) 的整数 Farkas 证书，若

    (A_S)^T y ≥ 0（对每个未删除列），   b^T y < 0，   β,λ ≥ 0，α 自由。

`verify(Φ, forbid=S)` 就是逐列重放这个条件，并检查 b^T y<0。

对节点 forbid 集 F，定义

    E(Φ,F) = { c∈F : σ_c < 0 }.

σ_c 用全矩阵 A（不删列）算，所以对 c∉F 有 σ_c≥0（Φ 已经证明 LP(F) 不可行）。

### 2.3 quorum clause 与强制域

由 2.2 得到一条比「本节点 NO」更强的话：

> LP(D∖E) 不可行。

对整数调度取逆否：**每个可行调度都存在任务 i，使 s_i∈E_i**。这就是 quorum clause。

- **剪枝**：节点 forbid 集 F' 若满足 E⊆F'，则该节点是 NO（不用 LP）。
- **强制域**：若 E 只涉及一个任务 i，clause 退化为 s_i∈E_i，于是可把 D_i 永久收缩到 E_i（与已有强制域取交）。
- **空交**：若同一任务 i 有两个已证强制 s_i∈E、s_i∈E' 且 E∩E'=∅，则根层 NO。

### 2.4 anytime 状态

    S = (C, Q, F^force, L, B)

不变式：

- C 只增（SD 割是有效不等式）；
- Q 只增（每条 clause 都有证书）；
- F_i^force 只缩（每次与新的 E_i 取交）；
- L 只增（叶子证书只追加）。

预算 b 增加时，S 是 b 时刻状态的扩展；所以已证的 NO 不回退，已收缩的域不回退。新的进度量是「被强制域删掉的开始时间质量」和「quorum 数」，不是只看 LB。

## 3. 算法

### 3.1 主过程

    function QNC_DECIDE(inst, h, budget):
        C = ∅; Q = ∅; force = {}; L = []
        if ∃i: D_i = ∅: return NO            # 零 LP 前检（CP 界）
        v = DFS(root_bounds())
        return v, state

    function DFS(bounds):
        bounds = apply_force(bounds)
        if ∃i: all columns of i forbidden: return NO      # 空域
        F = forbids(bounds)
        for E in Q:
            if E ⊆ F: return NO                           # clause 剪枝
        res = solve_with_lazy_SD(bounds, C)               # 计 1 次 LP
        if res == INFEASIBLE:
            Φ = integer_farkas(F)                         # DENS + 精确重放
            E = { c∈F : σ_c(Φ) < 0 }
            L.append((F, E, Φ))
            if E != ∅: Q.add(E)
            if |jobs(E)| == 1:
                i = the job;  force[i] = force.get(i, D_i) ∩ E_i
            return NO
        if res has integral z: return YES
        (i, mid) = median_branch(z)                       # v6.1 规则
        a = DFS(bounds with t>mid forbidden for job i)
        if a != NO: return a
        return DFS(bounds with t≤mid forbidden for job i)

### 3.2 证书提取

    function integer_farkas(F):
        A, hi = lp.matrix()                     # base + 当前 SD 割
        present = [c : c ∉ F]
        y* = argmin Σα_i + Σ m·β_t
             s.t. (A^T y)_c ≥ 0  ∀c∈present,  Σ_{ineq} y = 1,  y_ineq ≥ 0
        for D in DENS:
            y = round(D·y*)
            if (A^T y)_c ≥ 0 ∀c∈present and b^T y < 0:
                return y
        return None

与 v6.1 的区别只在 `present`：v6.1 的分支叶会重建完整 SDLP 再解 Farkas LP；这里直接在 lazy LP 的矩阵上删列，省掉重建。DENS 网格与精确重放不变。

### 3.3 审计

    function AUDIT(L):
        for (F,E,Φ) in L:
            if not E ⊆ F: return False
            if not verify(Φ, forbid=E): return False
        return True

注意 `forbid=E` 比 `forbid=F` 更强：它要求证书在 F∖E 这些列上也满足 A^T y≥0。这正好复验了 essential scope 的定义，不需要额外信息。

### 3.4 预算

- `budget` 计 LP 次数；超预算返回 UNKNOWN，保留 C/Q/force/L。
- `nodecap` 计 DFS 节点；同样返回 UNKNOWN。
- 判定只在有证书（或整数解）时给出；UNKNOWN 不产生判决。

## 4. 定理与证明

### 4.1 quorum 引理

设 Φ 证明 LP(F) 不可行，E={c∈F:σ_c<0}。则 Φ 证明 LP(E) 不可行。

**证明**：LP(E) 的列是 (D∖F)∪(F∖E)。对 c∈D∖F，Φ 对 LP(F) 有效 ⇒ σ_c≥0；对 c∈F∖E，由 E 的定义 σ_c≥0。所以 (A_E)^T y≥0。b 没有变化，b^T y<0。∎

### 4.2 最小性

对每个 c∈E 有 σ_c<0，所以把 c 加回 present 会破坏 A^T y≥0。因此 E 是 **对这个 y** 唯一的最小 scope。注意这不等于全局最小：换一个对偶解 y 可能得到更小的 E。

### 4.3 lifting

若 E⊆F'，则 Φ 也证明 LP(F') 不可行。因为 LP(F') 的列 ⊆ LP(E) 的列，而 LP(E) 已经不可行。这就是「节点入口 clause 检查」的正确性。

### 4.4 clause 与 force 的可靠性

设 s 是任一可行整数调度。若对所有 i 都有 s_i∉E_i，则 s 的 z 在 LP(E) 上可行（只用 D∖E 的列，且满足容量/SD），与 4.1 矛盾。所以 ∃i: s_i∈E_i。

若 E 只涉及任务 i，则上式就是 s_i∈E_i，故收缩 D_i 可靠。

### 4.5 空交

若同一任务 i 有两条已证强制 s_i∈E、s_i∈E'，且 E∩E'=∅，则不存在可行调度。∎

### 4.6 单证书不可能性

若当前割集 C 下根层 LP(∅) 可行，则任何后代证书的 E 都非空。

**证明**：若 E=∅，由 4.1，Φ 证明 LP(∅) 不可行，与根层可行矛盾。∎

**推论**：idx 5/47 的根 LP 可行，所以它们不可能用单个无条件 Farkas 证书在根层闭合。要闭合，要么加强割使根 LP 不可行，要么给出多证书证明。idx 5 的两条 quorum 空交就是后者。

### 4.7 单调性

C、Q、L 只增，force 只缩，且每一层都是原问题的有效蕴含。设预算 b_2≥b_1，则 b_1 时刻的状态是 b_2 时刻状态的子集（DFS 顺序固定），所以：

- status(b_1)=NO ⇒ status(b_2)=NO；
- force(b_2) ⊆ force(b_1)（每个域更小）；
- Q(b_1) ⊆ Q(b_2)，L(b_1) ⊆ L(b_2)；
- 已审计的叶子仍然审计通过。

### 4.8 复杂度

- LP：变量 O(nmT)，约束 O(mT+n+|C|)，|C|≤|E|T。
- 一次分离 O(nT+|E|T)。
- 一次 essential scope 计算 O(nnz(A))；一次 clause 检查 O(|Q|·|E|)。
- 整数舍入 O(|DENS|·nnz(A))，|DENS|≈215。
- 总 LP ≤ budget，总节点 ≤ nodecap；空间 O(nmT+|C|+|Q|+nT)。

## 5. 实验

### 5.1 设置

- 数据：141 例 NO 基准（holdout 50、synth2_45、large_a 8、large_b 10、large_het 8、hard3 12、deep 8），h=OPT−1。
- 扰动集：对 holdout idx 5/47 随机改一个 p_i（±1），重新求 OPT，得 60 例，其中 5 例在 h=OPT−1 需要分支。
- 环境：Python 3.12、NumPy 2.5.4、SciPy 1.18.1（HiGHS），单线程；实现 `exp/v71/qnc.py`。
- 预算：每节点 max_rounds=60，nodecap=5000；实测远低于上限。
- 判定：141+60 例都应 NO。

### 5.2 主结果（141 例）

| 方法 | NO | LP | DFS 节点 | 墙钟(s) |
|---|---:|---:|---:|---:|
| v6.1 ALC | 141 | 159 | 149 | 1.46 |
| QNC，仅零 LP 前检 | 141 | 149 | 139 | 1.39 |
| QNC 完整（前检+quorum） | 141 | 147 | 137 | 1.39 |

- 前检省 10 LP / 10 节点：10 例的某个 D_i=∅（est_i+p_i+q_i>h），v6.1 要解 1 次不可行 LP，QNC 在 0 LP 判 NO。
- quorum 再省 2 LP / 2 节点，全部来自 idx 5。
- 其余 129 例两者完全一致（1 LP / 1 节点）。
- 证书：131 例有 Farkas 叶子，共 134 个叶子；10 例由空域关闭（无 Farkas 证书）。134/134 在 E 上重放通过，0 次提取失败；scale 中位数 9，最大 2000（large_het idx 7）。202 次提取（含扰动集）0 失败。

### 5.3 分支子集（7 例）

| 实例 | ALC LP/节点 | QNC LP/节点 | 叶子 | 强制域 | 说明 |
|---|---|---:|---:|---|---|
| holdout 5 | 8 / 5 | **6 / 3** | 2 | {7:∅} | 两个 quorum {22,23}、{17..21} 空交 |
| holdout 47 | 7 / 5 | 7 / 5 | 3 | {11:[32]} | quorum 未与兄弟域空交 |
| h5-6 | 8 / 5 | **6 / 3** | 2 | {7:∅} | 同 idx 5 |
| h5-16 | 8 / 5 | **6 / 3** | 2 | {7:∅} | 同 idx 5 |
| h47-6 | 5 / 3 | 5 / 3 | 2 | {3:∅} | 空交，但发现于最后一个叶子，无 LP 收益 |
| h47-18 | 7 / 5 | 7 / 5 | 3 | {11:[31]} | 无收益 |
| h47-26 | 9 / 7 | 9 / 7 | 4 | {} | 4 个叶子，E 均跨任务 |
| **合计** | **52 / 35** | **46 / 29** | 18 | | 3 改善、4 持平、0 退化 |

LP −11.5%，节点 −17.1%。收益全部来自「单任务 force + 兄弟域空交」；跨任务的 E 只进 clause，没有触发过剪枝。

### 5.4 scope 压缩

上表 18 个叶子：

- Σ|F| = 96，Σ|E| = 59，**scope 缩小 38.5%**；
- 18 个叶子里 11 个严格 |E|<|F|（例如 17→7、8→4、7→3、5→2），7 个 E=F（例如 5→5、7→7）；
- 根层叶子 F=E=∅（本来就没有 forbid）。所以压缩只发生在需要分支的实例上。

这不是「证书更小」：β、dom 的系数没变，变的是证书被允许的有效区域更大。同一个 Φ 现在证明 LP(E) 不可行，而 LP(E) 的可行域比 LP(F) 大。

### 5.5 anytime

按 LP 预算 k 重跑（每个 k 从零开始；因为 DFS 顺序固定，k 时刻的状态是 k+1 时刻的前缀）：

201 例（141 基准 + 60 扰动）：

| k | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 已判 NO | 10 | 164 | 186 | 194 | 194 | 195 | 198 | 200 | 200 | 201 |
| 其中 audit 通过 | 10* | 164 | 186 | 194 | 194 | 195 | 198 | 200 | 200 | 201 |
| 已生成叶子 | 0 | 154 | 176 | 184 | 187 | 192 | 198 | 200 | 201 | 202 |
| 强制域事件 | 0 | 0 | 0 | 0 | 3 | 6 | 6 | 6 | 6 | 6 |

\* k=0 的 10 例是空域关闭，`audit()` 为空真；其余行为 Farkas 叶子重放。

141 基准单独看：

| k | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 已判 NO | 10 | 135 | 138 | 139 | 139 | 139 | 140 | 141 | 141 |

与 v6.1 的 135/138/139/139/139/139/140/141 相比：曲线整体左移 1 个 LP（在 k=6 就到 140、k=7 到 141），并多出 k=0 的 10 例。

### 5.6 负结果

1. **clause 剪枝 0 次命中**（201 例）。所有 E⊆F 的检查都没触发；真正起作用的是零 LP 前检（10 例）和单任务 force（6 次）。clause 目前只是一个正确但未兑现的机制。
2. **idx 47 无收益**。E={11:32} 是单任务，force 生效，但兄弟分支的区域与 {32} 不空交；额外只多了 3 个 clause，LP/节点不变。
3. **空交发现太晚**。4 个「force 变空」的实例里，有 3 个是在最后一个叶子才发现空交（h47-6 也是 2 叶子才空交），此时搜索已经结束，省不到 LP。空交是证明对象的收益（2 证书链），不是搜索的收益。
4. **扰动集的 5 个分支例里只有 2 个改善**，样本很小，不能当作统计结论。
5. **零 LP 前检是主要收益，但它不新**：v6.1 的 `integer_certificate` 本来就有 est+p+q>h 的 CP 分支，只是放在 LP 之后；本轮把它提到 LP 之前。

### 5.7 正确性检查

- 201/201 返回 NO（h=OPT−1 已知 NO），无误判 YES。
- 202 个叶子证书全部 `verify(Φ,forbid=E)` 通过；0 次提取失败；10 个空域例不产生 Farkas 证书。
- 6 次强制域事件：4 次收缩到空集（→ NO），2 次收缩到单元集（{11:32}、{11:31}）。
- 强制域只做交集，不会重新放大；`apply_force` 在每个节点入口执行，所以兄弟节点继承。
- 未系统测试 YES 侧：扰动集的 OPT 是用 ALC 扫描得到的（YES 来自整数 LP 解，未用独立调度检查器复验）。这是本轮的一个实验缺口。
- 未测 n>24 的实例；最大规模仍是 holdout/large 系列。

## 6. 风险与下一步

### 6.1 已知风险

1. **数据分布风险（最大）**：139/141 根层 1 LP 闭合，quorum 只在 2/141 上触发。任何「搜索期收益」都会被这个分布压成小数字。换到 LP 更弱、需要大量分支的实例上，收益可能放大，也可能被 force 的重放成本抵消。
2. **主要收益不新**：159→147 的 12 个 LP 里，10 个来自零 LP 前检（一个预处理技巧），2 个来自 quorum。把前检拿掉，quorum 的净收益只有 2 LP / 2 节点。
3. **clause 剪枝未兑现**：0/201 命中。clause 的正确性没问题，但它和「阈值分支」的形状不匹配：分支一次禁掉半个域，很少正好包含一个小 E。
4. **空交发现太晚**：force 变空时搜索往往已经结束；没有「提前预测空交」的机制。
5. **证明覆盖未独立检查**：`audit()` 逐叶重放，但「叶子覆盖整个域」是由 DFS 构造保证的，没有独立的树检查器。要作为可交付证明，还差一个 proof-tree 序列化 + 覆盖检查。
6. **数值**：DENS 上限 10000，本轮最大 scale 2000，余量 5×；更大实例可能舍入失败。
7. **扰动集太小**：5 个分支例、2 个改善，不能支撑统计结论；只能说明机制是通的。
8. **YES 侧未系统测**：分支最坏指数；QNC 的 anytime 只保证 NO 侧单调。

### 6.2 下一步

1. **proof-tree 序列化**：把 DFS 的 split 也记录下来，写一个独立 checker：叶子 `verify(Φ,E)` + split 覆盖 + force 链；这是把 audit 从「逐叶」升级为「整树」的关键。
2. **提前触发 quorum**：不要等 DFS 走到叶子。用可行 LP 的对偶价格预测「哪个任务的域最可能被一张证书压小」，优先分支它；或者在根层对每个任务试一个候选 E（来自分数解的支撑），直接解 LP(E)，把「找 quorum」变成主动搜索。
3. **clause 与分支形状对齐**：当前阈值分支一次禁半个域。若改成「按 E 的形状分支」（先禁 E 的补集），clause 才可能命中。
4. **空交短路**：force 一变成空就立刻终止整棵树，不再探索；本轮 4 个空交里 3 个发生在最后，短路可省掉后续节点（虽然本轮已经是最后）。
5. **弱 LP 家族**：构造 LP 更弱但整数仍 NO 的实例族（例如加长链、减少机器），系统测 quorum 的收益曲线。
6. **与 proof-tree 线合并**：QNC 的 E 可以直接作为 DCS/PSS 的叶子 scope，减少 proof tree 的叶子数；这是正交组合，不是替代。
7. **证书成本**：lazy Farkas + 增量 warmth；目标把 42% 的证书成本压到 20% 以下。

## 7. 复现文件

- `exp/v71/qnc.py`：QNC 状态机、essential scope、clause、force、audit、`farkas_int`。
- `exp/v71/bench_ablation.py`、`ablation.json`：141 基准 + 60 扰动的 ALC / 仅前检 / QNC 三档对比。
- `exp/v71/bench_anytime.py`、`anytime.json`、`anytime_corpus.json`：LP 预算 anytime 曲线。
- `exp/v71/bench_qnc.py`、`qnc_stats.json`：141 例主结果的早期版本（含逐例明细）。
- `exp/v71/perturb60.pkl`：60 个扰动实例（inst, opt, 基线节点数）。
- 依赖：`exp/v61/alc.py`（v6.1 基线）、`exp/v60/lazy.py`（lazy SD）、`exp/v60/cert.py`（DENS/verify/_row_meta）、`exp/v13/po.py`（heads_tails）。
- 数据：`exp/v20/holdout_cases50.pkl`、`exp/v28/synth2_45.pkl`、`exp/v14/{large_a,large_b,large_het}.pkl`、`exp/v13/hard3.pkl`、`exp/v18/deep.pkl`。
- 运行环境：Python 3.12、NumPy 2.5.4、SciPy 1.18.1（HiGHS）；工作目录 `/home/runner/work/xuen/xuen/workspace`。

## 8. 一句话最大风险

**QNC 的收益与「需要分支的节点数」成正比，而这批数据 139/141 根层就闭合；quorum 只在 2/141 上被真正触发，所以本轮测到的加速很小，换到 LP 更弱、分支更深的实例上才可能显现——但也可能被 force 的额外重放成本吃掉。**
