# 玄 · 设计一个新的算法

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
## 一、上一轮留下的硬结论

v6.0 SD-ECC 把 v5.0 的「期望开始时间」行换成了随机占优累计行：

  F_i(t) ≥ F_j(t+p_i),  F_i(t)=Σ_{s≤t} z_{i,s}.

这不是再加一条剪枝，而是把优先序从「期望」变成「分布占优」。结果很硬：

- 141/141 NO；根层 139/141；holdout 48/50；只剩 idx 5、47 需要 1 层开始二分（4 个分支节点，总 145 节点）。
- 整数 Farkas 证书 143 个（133 packing + 10 critical path），0 失败；scale 中位数 9，最大 720；β 最大 87，dom 最大 4。
- lazy 版（按需分离 SD 割）只需 35 条割就复现 141/141，总 149 节点、0.83 s；full 版 2.22 s（含证书）。

所以 v6.0 已经把「证书强度」推到了 139/141 根层。它留下的不是强度问题，而是**证书的生命周期问题**：

1. 判定和证书不同步：lazy 先判 NO，证书事后再提取；full 版先建全矩阵，再提取。
2. 没有预算接口：给定 1 ms / 1 次 LP / 1 条割，算法不能回答「现在能证什么」。
3. 证书不可增量复用：换 h、换分支节点，都要重新提取。
4. 2 个残例（5/47）根层未闭合；它们的证书要带分支 forbid 才能提取。

本轮的问题因此不是「再加一条割」，而是：

> 能不能把 v6.0 的 lazy 分离 + 整数证书，改造成一个**任意预算下都单调、且判定与证书同步**的 anytime 认证器？

灵感词是「algorithm engineering / anytime algorithm / 算法框架」。我的解读：

- algorithm engineering：证书提取不是离线后处理，而是判定路径的一部分；它的成本必须可测、可开关。
- anytime：预算增加时，答案只能变强，不能回退；中间答案必须可解释。
- 框架：割束（cut sheaf）+ 认证器状态机 + 预算调度，而不是单一函数。

## 二、第一次尝试：连续对偶上升，失败

我先把 start-time LP 的 Farkas 对偶写成价格形式：

  D(β,γ)=Σ_i min_t [B_i(t)+tσ_i] + Σ_e p_i γ_e − mΣ_t β_t.

β≥0 是时间割价，γ≥0 是优先序割价；D>0 即 NO。D 是凹的、1-齐次的。于是很自然地想用归一化次梯度上升（ADA）来 anytime 地找证书：每步 O(nT)，找到 D>0 就停，找不到就返回当前 D 作为进度。

在 5 个 MPC 残例上跑 2000 步：

- idx 21/32/42（LP 根层不可行）：best D = −0.345 / −0.306 / −0.421；
- idx 5/47（LP 根层可行）：best D = −0.563 / −0.235。

全部为负，连根层不可行的三例都没找到证书。

原因不是实现 bug，而是证书太薄：把 Farkas LP 归一化后，最优目标只有 0.001–0.026（21/32/42）。D 在非光滑的 min 处有大量断点，次梯度在 10^-3 量级的裕度上收敛极慢。这个负结果把 v6.0 的设计解释清楚了：**必须解整数 Farkas LP 并对对偶解做有理舍入，不能靠连续爬山**。它也解释了 `integer_certificate` 为什么要扫 DENS 网格（1..200, ..., 10000）。

## 三、第二次尝试：把证书做成「束」

回到 v6.0 的 lazy 代码，我注意到一个结构性事实：SD 割集 C 只增；LP(C) 的可行域嵌套；并且**旧证书对新割仍然有效**。因为新增的 SD 割行在 Farkas 证书里的对偶系数可以取 0，`A^T y` 不会变小，`b^T y` 不变。

也就是说：

- 一旦在某个割集上提取并验证了证书 Φ，后续无论加多少割，Φ 都仍然证明 NO；
- 判定不会回退，证书可以缓存；
- 这把「证书」从一个输出对象变成了一个**单调状态**。

于是 ALC 的状态就是 `(C, Φ, B, LB)`：割集、证书、已用 LP 次数、已证下界。每一步：

1. 解 LP(C)；
2. 不可行 → 立即用当前 C 提取整数证书 Φ，验证，返回 NO；
3. 可行 → 分离违反的 SD 割，按预算加 k 条，重复；
4. 预算耗尽 → 返回 UNKNOWN，但保留 C/Φ/LB。

外层再从 EPC 下界开始逐 h 探测：证一个 h，LB 加一；证书和割集跨 h 复用（SD 割与 h 无关）。

这就是 ALC（Anytime Lazy Certificate）。它没有改 SD 割的数学，只改了证书的生命周期。

## 四、实验结果

141 例 NO（h=OPT−1）：

- 141/141 NO，141/141 证书验证通过（145 次提取，含 4 次分支重复）。
- 135/141 在**第 1 次 LP** 就闭合；k=1/2/3/7/8 的累计闭合数是 135/138/139/140/141。
- 总 159 次 LP、149 个 DFS 节点、35 条割（全在 holdout 的 6 例）。
- 判定-only 0.632 s；带证书 1.099 s；证书提取 0.465 s（42%）。
- v6.0 full：判定 1.089 s + 证书 1.135 s = 2.224 s；lazy：0.829 s（无证书）。
- holdout 下界剖面：从 EPC LB 逐 h 探测，55 次调用 / 73 LP / 0.233 s，LB=OPT 50/50；ECC 的 root 二分要 147 个 LP。

有一个负结果必须写下来：我原本以为 lazy 证书会更稀疏。逐例对比 139 个根层 NO 证书：ALC 更小 20 例、相同 102 例、更大 17 例；中位数 7 vs 8，最大 91 vs 89。**稀疏性不是 lazy 的必然收益**；容量-only 的对偶可能更分散。ALC 的真正收益是同步性和成本，不是证书尺寸。

还有两个成本/风险数据：

- 证书 scale 中位数 9，最大 2000（holdout idx 7，β=91），而 DENS 上限是 10000；离上限只差 5×。
- 2 个分支例（5/47）仍需 5 个节点、7–8 次 LP；根层没有闭合。

## 五、这一轮学到的东西

不是「更强的割」，而是「证书的状态管理」。v6.0 已经证明 SD 割够强；本轮证明的是：

- 证书一旦存在就永久有效，所以 anytime 的核心是**单调状态**，不是更快的单次求解；
- 证书不是免费的：v6.0 里证书占 51% 的时间，ALC 里占 42%；应该做成可选输出；
- lazy 不保证证书更小；不要用「稀疏性」作为 lazy 的卖点。

## 六、一句话最大风险

**ALC 的 1-LP 闭合率（135/141）主要来自 capacity-only start-time LP 的强度，而不是 dominance 割；如果新实例需要大量 SD 割，anytime 曲线会迅速变平，42% 的证书成本会吞掉判定优势。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
## 0. 版本关系与本轮增量

本轮产物是 **v6.1 ALC（Anytime Lazy Certificate）**，建立在 v6.0 SD-ECC 的三件既有产物上：

- `sdecc.py`：带随机占优（SD）割的 start-time LP；
- `lazy.py`：按需分离 SD 割的 lazy 版；
- `cert.py`：整数 Farkas 证书的提取与精确重放。

v6.1 不改 SD 割的数学，也不改 v5/v6 的开始时间分支规则；它增加的是四件事：

1. **证书束（cut sheaf）**：割集单调增长，旧证书对新割永久有效；
2. **判定与证书同步的 anytime 状态机**；
3. **两档输出**：verdict-only（只要判定）与 audit（判定 + 可审计证书）；
4. **下界剖面**：从 EPC 下界开始逐 h 探测，割集和证书跨 h 复用。

推荐用法：

    ALC_ANYTIME(inst, budget) -> (LB, UB, verdict, certificate, cutset)

预算可以是 LP 次数、割数或墙钟；超预算返回 UNKNOWN，但已证的 NO 与证书不回退。

## 1. 符号

- n：任务数；m：机器数；p_i：任务 i 的加工时间。
- pred(i)、succ(i)、elig(i)：前驱、后继、可用机器。
- h：待判定的 makespan 上界（NO 基准取 h = OPT−1）。
- est_i、q_i：优先序头部/尾部；d_i = h − q_i 是最晚完成时间。
- T = h：时间索引上界。
- z_{i,t} ∈ [0,1]：全资格时任务 i 在 t 开始的分数指示；异构资格时 z_{i,k,t}。
- F_i(t) = Σ_{s≤t} z_{i,s}：任务 i 在 t 前开始的累计概率/质量。
- E：优先序边集；e = (i→j)。
- C ⊆ E × {t}：已分离的 SD 割集；C_k 表示第 k 轮后的割集。
- LP(C)：在割集 C 下的 start-time LP。
- y = (α, β, λ)：LP(C) 的 Farkas 对偶；β_t 是时间容量价格，λ_{ij,t} 是 SD 割价格，α_i 是任务价格。
- Φ = (α, β, λ, scale)：整数化后的 Farkas 证书；`verify(Φ)=true` 表示精确重放通过。
- δ(C)：归一化 Farkas 目标，δ(C) > 0 ⇔ LP(C) 不可行 ⇔ NO。
- B：已用 LP 次数；K：已用割数；N_nodes：DFS 节点数。
- LB、UB：已证 makespan 下界与已构造可行调度的上界。

## 2. 形式定义

### 2.1 SD start-time LP

全资格时变量 z_{i,t}，t ∈ [est_i, h−q_i−p_i]：

    Σ_t z_{i,t} = 1                                   ∀i
    Σ_i Σ_{s≤t<s+p_i} z_{i,s} ≤ m                     ∀t
    F_i(t) ≥ F_j(t+p_i)                               ∀(i→j), ∀t
    0 ≤ z_{i,t} ≤ 1

最后一行是 v6.0 的 SD 割；它比 v5.0 的期望行 E[s_i]+p_i ≤ E[s_j] 强，因为它是整个开始时间分布的随机占优：

    若 s_j ≤ t+p_i，则 s_i+p_i ≤ s_j ≤ t+p_i ⇒ s_i ≤ t,

所以事件 {s_j ≤ t+p_i} 蕴含 {s_i ≤ t}，累计质量满足 F_i(t) ≥ F_j(t+p_i)。

异构资格时把 z_{i,t} 细化为 z_{i,k,t}，容量行变成每台机器每时刻 ≤1；SD 行对每个任务对成立（对机器求和）。

**lazy 版本**：先只建分配行 + 容量行，得到 LP(∅)；解出 z 后，对每条边 i→j 扫描 t，若 F_j(t+p_i) − F_i(t) > tol，则割 (i,j,t) 违反；按违反量排序，加入 top-k 条。每个加入的割都是有效不等式，所以 LP(C) 不可行时，原问题不可行。

### 2.2 整数 Farkas 证书

对 LP(C) 的矩阵 A、右端 b，Farkas 证书是 y 满足：

    A^T y ≥ 0,   b^T y < 0,   y 在不等式行上 ≥ 0.

证书的整数化：解归一化 Farkas LP 得到分数 y*，对密度 D ∈ DENS 取 y = round(D·y*)，然后精确重放：

    A^T y ≥ 0 且 b^T y < 0.

第一个重放通过的 D 就是证书的 scale。v6.0 的 DENS 是 1..200 加上 240, 300, ..., 10000。当前 141/141 成功，scale 中位数 9，最大 2000。

`verify` 逐任务、逐可能开始时间检查 α_i + B_i(t) + 割的势差 ≥ 0，并检查目标 < 0；它不依赖浮点 LP 的可行性状态。

### 2.3 证书束与单调性

定义割束为嵌套序列：

    C_1 ⊆ C_2 ⊆ ... ⊆ C_k ⊆ E × [0,T).

每个 C_k 对应 LP(C_k)。若 LP(C_k) 不可行，则存在整数 Farkas 证书 Φ_k。关键性质是：

> Φ_k 对所有 LP(C_{k'})，k' ≥ k，仍然有效。

理由：LP(C_{k'}) 的约束矩阵 A' 是在 A 上追加 SD 割行；这些新行在证书里的对偶系数取 0，所以 (A')^T y = A^T y ≥ 0，而 b' 的新增分量是 0，b'^T y = b^T y < 0。

因此 anytime 状态可以写成：

    S = (C, Φ, B, LB, UB)

其中 C 只增，Φ 一旦非空就永久有效，LB 只在 NO 后增加。预算增加时，S 只会变强。

### 2.4 anytime 接口

一个 anytime 认证器在预算 b 下返回：

    ALC(inst, b) = (status, LB, UB, Φ, C, effort)

- status ∈ {NO, YES, UNKNOWN}；
- 若 status=NO，则 Φ 非空且 verify(Φ)=true，LB ≥ h+1；
- 若 status=YES，则存在整数开始时间赋值，UB ≤ h；
- 若 status=UNKNOWN，则 LB/UB/Φ/C 是当前已证的部分结果；
- 单调性：b_2 ≥ b_1 ⇒ LB(b_2) ≥ LB(b_1)，UB(b_2) ≤ UB(b_1)，且若 status(b_1)=NO 则 status(b_2)=NO；
- soundness：NO 只在有验证证书时返回；YES 只在有整数解时返回。

## 3. 算法

### 3.1 ALC 状态机

    function ALC_CERTIFY(inst, h, budget, C):
        while lp_solves < budget:
            res = solve(LP(C))
            if res == INFEASIBLE:
                Φ = integer_farkas(C)          # DENS grid + exact replay
                if verify(Φ): return (NO, Φ, C)
                return (NO, NULL, C)           # sound, unaudited
            if res != OPTIMAL: return (UNKNOWN, NULL, C)
            V = separate(res.z)                # violated SD cuts, sorted
            if V == empty: return (UNKNOWN, NULL, C)
            C = C ∪ top_k(V)
        return (UNKNOWN, NULL, C)

    function ALC_DECIDE(inst, h, budget, nodecap):
        C = ∅; Φ = NULL
        v, Φ, C = ALC_CERTIFY(inst, h, budget, C)
        if v == NO: return (NO, Φ, C)
        if v == UNKNOWN and LP(C) is feasible and has fractional z:
            (i, mid) = pick_fractional_start(z)   # same rule as v6.0
            left  = bounds with z[i,t]=0 for t > mid
            right = bounds with z[i,t]=0 for t ≤ mid
            # C is shared by both children; cuts are global valid inequalities
            a = ALC_DECIDE(inst, h, budget, nodecap, C, left)
            if a != NO: return a
            return ALC_DECIDE(inst, h, budget, nodecap, C, right)
        return (v, Φ, C)

分支的 mid 规则沿用 v6.0：取分数质量中位数；若 mid 落在最后一个可能开始时间，则 mid 减一，保证左右两支都真正删除正质量，避免 v5.0 在可行 h 上出现「左支无进展」的深递归。

### 3.2 分离与割预算

`separate(z)` 一次扫描所有边和 t：

    F_i(t) = Σ_{s≤t} z_{i,s}                     # 前缀和，O(nT)
    viol(i,j,t) = F_j(t+p_i) − F_i(t)            # 正数即违反
    按 viol 降序取 top-k

每轮加 top-k 条割；top-k 是 anytime 的粒度旋钮：

- top-k 大：LP 次数少，但单次 LP 更大，证书可能更稠密；
- top-k 小：LP 次数多，但每步更细，证书可能更稀疏。

### 3.3 证书提取

    function integer_farkas(C):
        y* = solve_normalized_farkas_lp(C)        # 变量 α,β,λ
        for D in DENS:
            y = round(D * y*)
            if A_C^T y ≥ 0 and b_C^T y < 0:
                return (α, β, λ, D)
        return NULL

分支节点的证书额外带 forbid 集：把在该节点被置 0 的开始时间从 LP 列中删除，再做 Farkas；`verify` 重放时跳过 forbid 中的 (i,t)。这正是 v6.0 处理 idx 5/47 的方式，ALC 把它纳入同一状态机。

### 3.4 下界剖面

    function ALC_ANYTIME(inst, budget):
        LB = EPC_LB(inst); UB = heuristic_UB(inst)
        C = ∅; Φ = NULL
        while budget > 0 and LB < UB:
            v, Φ, C = ALC_CERTIFY(inst, LB, budget, C)
            if v == NO: LB = LB + 1
            elif v == UNKNOWN: break
        return (LB, UB, Φ, C)

- EPC_LB 用 v3.0 的区间能量检查；它通常比 OPT 小 0–2。
- 每证一个 h，LB 加一；不需要对 h 二分，因为 ALC 的 1-LP 闭合率很高。
- SD 割与 h 无关，C 可以跨 h 复用；β 行与 h 有关，证书跨 h 需要重新提取。

### 3.5 两档输出

- **verdict-only**：`cert_on=False`，不可行时直接返回 NO，不提取证书；成本最低。
- **audit**：`cert_on=True`，每个不可行节点提取并验证证书；成本增加，但输出可独立审计。

## 4. 定理与证明

### 4.1 引理 1（SD 割有效）

设 s 是任意满足优先序的非抢占调度。对边 i→j 和任意 t，若 s_j ≤ t+p_i，则

    s_i + p_i ≤ s_j ≤ t + p_i  ⇒  s_i ≤ t.

所以 {s_j ≤ t+p_i} ⊆ {s_i ≤ t}；对指示变量求和得到 F_i(t) ≥ F_j(t+p_i)。∎

**推论**：LP(C) 是原问题的松弛；LP(C) 不可行 ⇒ 原问题不可行。

### 4.2 引理 2（证书跨割单调）

设 C ⊆ C'，y 是 LP(C) 的 Farkas 证书：A_C^T y ≥ 0，b_C^T y < 0，且 y 在不等式行上 ≥ 0。LP(C') 的矩阵 A_{C'} 在 A_C 上追加 SD 行 g_e(z) ≤ 0。把这些新行的对偶系数取 0，得到 y'。则

    A_{C'}^T y' = A_C^T y ≥ 0,
    b_{C'}^T y' = b_C^T y + 0 < 0.

所以 Φ 对 LP(C') 仍然有效。∎

### 4.3 引理 3（δ 单调）

定义 δ(C) = max { b_C^T y : A_C^T y ≥ 0, y 在不等式行 ≥ 0, ||y||_1 ≤ 1 }。若 C ⊆ C'，LP(C') 的对偶可行域包含 LP(C) 的对偶可行域（新行对偶取 0），所以 δ(C') ≥ δ(C)。∎

**用途**：δ 是一个单调的「证书进度」。当前实现不显式算 δ（那需要每次解 Farkas LP）；用整数证书的 scale 和 |b^T y| 作为代理。

### 4.4 定理 1（ALC soundness）

- ALC 返回 NO 时，LP(C) 不可行，且 `integer_farkas` 返回并 `verify` 通过的整数 Farkas 证书满足 A_C^T y ≥ 0、b_C^T y < 0；由 Farkas 引理，LP(C) 不可行；由引理 1，原问题不可行。
- ALC 返回 YES 时，LP(C) 有整数解：每个任务恰好一个开始（分配行），每时刻容量 ≤m（容量行）。对整数解取 t=s_j−p_i，由 SD 行 F_i(t) ≥ F_j(s_j)=1 得 s_i ≤ s_j−p_i，即优先序成立，所以是一个合法非抢占调度。
- UNKNOWN 不产生判决。
∎

### 4.5 定理 2（anytime 单调）

ALC 的 cutset 只增（`cutset` 去重）；证书一旦验证，由引理 2 永久有效；LB 只在 NO 后加一。因此对 b_2 ≥ b_1：

- status(b_1)=NO ⇒ status(b_2)=NO；
- LB(b_2) ≥ LB(b_1)，UB(b_2) ≤ UB(b_1)；
- 已提取的 Φ 仍满足 verify。

∎

### 4.6 命题（复杂度与预算终止）

- LP(C) 变量 O(nmT)，约束 O(mT + n + |C|)；|C| ≤ |E|T。
- 分离一次 O(nT + |E|T)。
- 整数舍入 O(|DENS|·(n + |C|))，|DENS| ≈ 215；最坏 O(215·|E|T)。
- 每个 DFS 节点最多 max_rounds 次 LP；总 LP ≤ budget，总节点 ≤ nodecap；超预算返回 UNKNOWN。
- 空间 O(nmT + |C|)。

∎

## 5. 实验

### 5.1 设置

- 数据：141 例 NO 基准，h = OPT−1；holdout 50、synth2_45、large_a 8、large_b 10、large_het 8、hard3 12、deep 8。
- 实现：Python 3.12 + SciPy 1.18.1（HiGHS），单线程；`exp/v61/alc.py`。
- 预算：每节点 max_rounds=60，总 nodecap=5000；实测远低于上限。
- 证书：DENS 网格，scale 最大 10000；每例提取一次，分支重复提取。
- 判定：h=OPT−1，141 例应全部 NO。

### 5.2 主结果

| 数据集 | N | NO | 证书验证 | LP 次数 | DFS 节点 | 割 | 1-LP 闭合 | 时间(s) | 证书时间(s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| holdout 50 | 50 | 50 | 50 | 68 | 58 | 35 | 44 | 0.394 | 0.175 |
| synth2_45 | 45 | 45 | 45 | 45 | 45 | 0 | 45 | 0.218 | 0.109 |
| large_a | 8 | 8 | 8 | 8 | 8 | 0 | 8 | 0.067 | 0.024 |
| large_b | 10 | 10 | 10 | 10 | 10 | 0 | 10 | 0.121 | 0.040 |
| large_het | 8 | 8 | 8 | 8 | 8 | 0 | 8 | 0.169 | 0.058 |
| hard3 | 12 | 12 | 12 | 12 | 12 | 0 | 12 | 0.082 | 0.037 |
| deep | 8 | 8 | 8 | 8 | 8 | 0 | 8 | 0.048 | 0.021 |
| **总计** | **141** | **141** | **141** | **159** | **149** | **35** | **135** | **1.099** | **0.465** |

关键点：

- 141/141 NO，141/141 证书验证；145 次提取（141 例 + 4 次分支重复），0 失败。
- 135/141 在第 1 次 LP 就闭合；只有 holdout 的 6 例需要割，2 例需要分支。
- 35 条割全部在 holdout；其他 91 例一条割都不需要。

### 5.3 anytime 曲线

预算 = 完成判定所需的 LP 次数；`lp <= k` 表示在 k 次 LP 内闭合。

| k | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 已判 NO | 135 | 138 | 139 | 139 | 139 | 139 | 140 | 141 |

用时分布：135 例 1 LP；3 例 2 LP；1 例 3 LP；1 例 7 LP；1 例 8 LP。曲线在 k=1 就到 95.7%，k=8 到 100%。

### 5.4 与 v6.0 对比

| 方法 | 判定(s) | 证书(s) | 总(s) | DFS 节点 | 割 | 证书数 |
|---|---:|---:|---:|---:|---:|---:|
| v6.0 full SDLP | 1.089 | 1.135 | 2.224 | 145 | 全量 SD 行 | 143 |
| v6.0 lazy | 0.829 | — | 0.829 | 149 | 35 | — |
| v6.1 ALC verdict-only | 0.632 | — | 0.632 | 149 | 35 | — |
| v6.1 ALC audit | 0.632 | 0.465 | 1.099 | 149 | 35 | 141 |

解读：

- ALC 的 audit 模式比 v6.0 full 快 2.0×（1.10 s vs 2.22 s），证书提取成本从 1.135 s 降到 0.465 s（因为 lazy 的 Farkas LP 更小）。
- ALC 的 verdict-only 与 v6.0 lazy 同量级甚至略快；差异部分来自实现/测量，不作为主结论。
- ALC 的节点数与 lazy 相同（149）；代价是每节点多轮 LP（159 次）。

### 5.5 证书统计与成本

- 131 个 packing 证书 + 10 个 critical-path 证书；145 次提取，0 失败。
- β 中位数 8，最大 91；dom 中位数 0，最大 3；scale 中位数 9，最大 2000。
- 证书提取总时间 0.465 s，平均 3.2 ms/次；v6.0 full 的证书提取 1.135 s，平均约 7.9 ms/次。
- 最大 scale 出现在 holdout idx 7（capacity-only 证书，β=91，scale=2000）；DENS 上限 10000，余量只有 5×。

### 5.6 证书规模对比（负结果）

对 139 个根层 NO 实例，逐例比较 ALC 的 lazy 证书与 v6.0 full SDLP 证书（cuts = |β| + |dom|）：

| 关系 | 例数 |
|---|---:|
| ALC 更小 | 20 |
| 相等 | 102 |
| ALC 更大 | 17 |

- 中位数：ALC 7，full 8；最大：ALC 91，full 89；scale 中位数都是 8。
- full 证书提取时间中位数 4 ms，均值 5.9 ms。

结论：**lazy 不保证证书更稀疏**。ALC 的优势是同步性、成本、预算接口，不是证书尺寸。

### 5.7 top-k 消融

对 holdout 的 6 个需要割的实例，改变每轮加入的割数：

| idx | topk=1 | topk=2 | topk=4 | topk=8 | topk=100 |
|---|---|---|---|---|---|
| 5 | 12 LP / 5 节点 / 7 割 / 0.044 s | **6 / 3 / 5 / 0.024** | 8 / 5 / 7 / 0.032 | 8 / 5 / 7 / 0.035 | 8 / 5 / 7 / 0.033 |
| 47 | **7 / 3 / 4 / 0.035** | 16 / 11 / 7 / 0.079 | 8 / 5 / 7 / 0.043 | 7 / 5 / 7 / 0.038 | 7 / 5 / 7 / 0.038 |
| 21 | 2 / 1 / 1 / 0.010 | 2 / 1 / 2 / 0.010 | 2 / 1 / 4 / 0.010 | 2 / 1 / 5 / 0.011 | 2 / 1 / 5 / 0.011 |
| 32 | 3 / 1 / 2 / 0.013 | 3 / 1 / 4 / 0.014 | 3 / 1 / 7 / 0.013 | 3 / 1 / 8 / 0.013 | 3 / 1 / 8 / 0.013 |
| 39 | 3 / 1 / 2 / 0.015 | 3 / 1 / 3 / 0.016 | **2 / 1 / 3 / 0.012** | 2 / 1 / 3 / 0.012 | 2 / 1 / 3 / 0.013 |
| 42 | 3 / 1 / 2 / 0.014 | 3 / 1 / 4 / 0.014 | **2 / 1 / 4 / 0.011** | 2 / 1 / 5 / 0.011 | 2 / 1 / 5 / 0.011 |

观察：

- idx 5 的甜蜜点是 topk=2（6 LP / 3 节点），比 topk=100 少 2 次 LP；但证书从 5β+1dom/scale 7 变成 9β+4dom/scale 22。
- idx 47 的 topk=1 节点最少（3），但证书 18β+0dom/scale 35；topk=8 是 15β+3dom/scale 39。
- 细粒度不总是更快：topk=1 在 idx 5 上反而 12 LP。
- 证书规模和判定速度之间存在 trade-off，没有一个 topk 全面占优。

### 5.8 下界剖面

holdout 50，从 EPC LB 逐 h 探测到 OPT−1（verdict-only）：

- 55 次 ALC 调用，73 次 LP，63 个 DFS 节点，0.233 s；
- LB = OPT 50/50，平均 gap 0；
- 对比 ECC：root 二分 147 个 LP，root LB 精确 47/50；full ECC 自身再用 157 个 LP 节点才到 50/50。本实验把 root 与 full 分开跑，合计约 1.49 s。
- ALC 的 LP 是 capacity-only/少量割，单次规模更小；73 个 LP 的成本低于 ECC 的 147 个 start-time LP。

这是本轮 anytime 性质的直接收益：预算从 0 增加时，LB 逐 h 上升；每次调用都有证书（verdict-only 模式下无证书，但判定 sound）。

### 5.9 负结果：连续对偶上升

对 5 个残例跑 ADA 2000 步（归一化次梯度，步长 1/√k）：

| idx | 21 | 32 | 42 | 5 | 47 |
|---|---:|---:|---:|---:|---:|
| best D | −0.345 | −0.306 | −0.421 | −0.563 | −0.235 |

全部 < 0。即使 LP 根层不可行的 21/32/42，连续上升也没有找到 Farkas 证书。修正后的归一化 Farkas LP 目标只有 0.001–0.026，说明证书裕度极薄；这解释了为什么必须做整数舍入，而不是连续爬山。

### 5.10 正确性检查

- 141 例都是已知 NO（h=OPT−1），ALC 全部返回 NO，无误判 YES。
- 141/141 证书 `verify` 通过；分支例的证书带 forbid，重放通过。
- 下界剖面 LB=OPT 50/50，没有出现 LB > OPT 的越界。
- 未系统测试 YES 侧；ALC 的 YES 判定依赖整数 LP 解或分支，分支规则沿用 v6.0 的 mid 修正（mid 落在最后一个时间时减一），避免 v5.0 的深递归。
- 证书提取失败时 ALC 仍可返回 NO（sound，但 unaudited）；本轮没有出现这种情况。

## 6. 风险与下一步

### 6.1 风险

1. **收益来源**：135/141 的 1-LP 闭合率主要来自 capacity-only start-time LP，而不是 SD 割。若新实例需要大量 SD 割，anytime 曲线会变平，ALC 退化为 lazy 的逐割搜索。
2. **证书成本**：audit 模式比 verdict-only 慢 74%（1.099 s vs 0.632 s）；证书占总时间 42%。在大规模实例上，Farkas LP + 舍入可能成为瓶颈。
3. **数值薄度**：证书 scale 中位数 9，最大 2000，DENS 上限 10000；更大实例可能需要 >10000 的分母，导致舍入失败（当前 141/141 成功，但没有压力测试）。
4. **根层残例**：idx 5/47 仍需 5 个节点、7–8 次 LP；SD 割没有在根层闭合它们。
5. **YES 侧**：没有系统测试；分支最坏指数；ALC 的 anytime 只保证 NO 侧单调。
6. **下界剖面**：成本与 EPC gap 线性相关；如果 EPC 下界很松（gap 很大），逐 h 探测会退化。
7. **证书尺寸**：lazy 证书不一定更小（20 更小 / 102 相等 / 17 更大）；不要用稀疏性作为卖点。

### 6.2 下一步

1. **增量证书**：用可行 LP 的对偶边际预测 δ(C)，只在 δ 接近 0 时解 Farkas LP；目标是把证书成本从 42% 降到 <15%。
2. **证书引导的割选择**：当前 top-k 按违反量排序；可以按对偶价格/证书势差加权，减少 idx 5/47 的节点数。
3. **跨 h 复用**：当前接口保留 C，但 141 例上没有系统测；在 EPC gap 大的实例上测复用率。
4. **更大规模**：n>20、h>80 的舍入失败率、DENS 上限、LP 时间。
5. **端到端级联**：把 ALC 接到 v6.0 的 root 级联（ICC → SD root → ALC branch），用同一套 141 例测中位数。
6. **YES 侧 anytime**：把 ALC 与可行调度构造器（列表调度/WOS）结合，维护 [LB, UB] 双界。

## 7. 复现文件

- `exp/v60/sdecc.py`：SD start-time LP + `sdecc_no`。
- `exp/v60/lazy.py`：lazy SD 分离 + `lazy_no`。
- `exp/v60/cert.py`：整数 Farkas 证书提取、DENS 舍入、`verify`。
- `exp/v60/final_stats.py`、`final_stats.json`：v6.0 full 基线。
- `exp/v60/bench_lazy.py`、`lazy_bench.json`：v6.0 lazy 基线。
- `exp/v61/alc.py`：ALC 状态机、证书同步、两档输出。
- `exp/v61/bench_alc.py`、`alc_stats.json`：141 例主结果与 anytime 分布。
- `exp/v61/lb_alc.py`、`lb_alc_holdout.json`：holdout 下界剖面。
- `exp/v61/topk_ablation.json`：top-k 消融。
- `exp/v61/cert_compare.json`：ALC vs full 证书规模对比。
- `exp/v61/ada.py`、`farkas_lp.py`：连续对偶上升与归一化 Farkas LP 的诊断实现（负结果）。
- `exp/v61/anytime_lb.py`、`exp/v60/lb_*.json`：ECC 下界剖面基线。
- 数据：`exp/v20/holdout_cases50.pkl`、`exp/v28/synth2_45.pkl`、`exp/v14/{large_a,large_b,large_het}.pkl`、`exp/v13/hard3.pkl`、`exp/v18/deep.pkl`。
- 运行环境：Python 3.12、SciPy 1.18.1（HiGHS）；工作目录 `/home/runner/work/xuen/xuen/workspace`。
<!-- ARTIFACT:END -->
