# 玄 · 设计一个新的算法

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
## 一、上一轮的两问与这一轮的入口

v7.1 QNC 把「判定 + 证书」做成同一个事件，也留下了两个很具体的问题：

- **Q1**：idx 5/47 的根 LP 可行，所以单个无条件 Farkas 证书不可能在根层闭合（v7.1 定理 4.6）。那根层到底缺什么对象？
- **Q2**：证书除了说「这个节点 NO」，能不能反过来约束搜索？

本轮灵感词是「进化算法 / 算法设计 / 优化模型」。我的第一反应不是再加强割，而是把「找矛盾」当成一个进化搜索：

> 种群 = 候选调度（或候选单元文字）；适应度 = 违反硬约束的数目；但候选只是猜测，必须用 LP 证书把文字变成事实。

于是证明对象从「一个节点的 Farkas 证书」变成「被认证的文字集合 + 一条被违反的硬约束」。这直接对应 Q1：根层缺的可能不是更强的割，而是**两个（或更多）单元证书的组合**。

## 二、第一次尝试：把候选调度当种群

我最初的设计是：

- 基因：一个完整开始时间向量 $a=(a_1,\dots,a_n)$，$a_i\in D_i$；
- 适应度：$a$ 违反优先序 / 容量 / 资格约束的加权数；
- 变异：改一个任务的开始时间；交叉：交换两个父代的若干任务；
- 「证明修复」：对候选 $a$ 中造成违反的文字 $(i,a_i)$，逐个用 LP 探测
  $\mathrm{LP}(\{(i,t)\})$ 是否不可行；只有被证书确认的文字才能进入证明。

这个思路的问题是：候选空间是 $\prod_i |D_i|$，而真正能拿到证书的文字极少。但「优化模型」的部分是对的：

> 找一个最小的文字集合 $P$，使 $P$ 中每个文字都可认证，且 $P$ 违反一条硬约束。

这是一个**最小证书覆盖**问题：同任务两个不同开始只需 2 个文字；一条优先序边上的冲突只需 2 个；容量冲突需要 $m+1$ 个。适应度可以写成「每多认证一个文字，能覆盖多少条潜在冲突」。

## 三、方向检查：删 $(i,t)$ 证明的是「强制 $t$」，不是「禁止 $t$」

上一轮犯过一次方向错误：把 essential scope $E$ 当成「禁」。这一轮先把方向写死。

设 $\mathrm{LP}(E)$ 表示把列集 $E$ 删掉后的 start-time LP。若

$$\mathrm{LP}(\{(i,t)\})\ \text{不可行},$$

则任何可行整数调度都不能避开 $(i,t)$，所以

$$s_i=t.$$

注意：$(i,t)$ 是**被删掉的列**，但结论是「必须用它」。这不是 ban，而是 force。两个证书分别给出 $s_i=t$ 和 $s_i=u$（$t\ne u$）时，才是矛盾。

这个方向检查也解释了上一轮的 idx 5：QNC 的叶子给出 $E_1=\{7:22,23\}$、$E_2=\{7:17,\dots,21\}$，两个都是「必须落在」的区域；它们不相交，所以 NO。本轮要找的是更小的 forced 区域，最小就是单点 $\{t\}$。

## 四、支持引理：种群塌缩成 LP support

设 $z$ 是当前割集 $C$ 下根 LP 的任意可行解，$S_i(z)=\{t:z_{i,t}>0\}$。关键观察：

> 若 $\mathrm{LP}(\{(i,t)\})$ 不可行，则 $z_{i,t}>0$。

证明只有一行：若 $z_{i,t}=0$，则删掉 $(i,t)$ 不会删掉 $z$ 的任何正分量，$z$ 仍是 $\mathrm{LP}(\{(i,t)\})$ 的可行解，矛盾。

这条**支持引理**把候选集从整个 $D_i$ 压到 $S_i(z)$。在这批数据上 $|S_i|\le 3$，所以「进化搜索」退化成「扫描 support」；真正的工作量是证书 LP，不是种群搜索。我的第一个在线 EA 设计因此被这个定理推翻了——这是一个很好的负结果：

> 当候选集可以被一个结构定理压到很小时，EA 的价值不在搜索候选，而在**排序测试顺序**。

于是本轮把 EA 放到离线：用 7 个根分数实例的缓存 forced/free 标签，进化一个线性排序策略；在线算法只用一个确定性的 span-first 顺序。EA 是设计工具，不是运行时组件。

## 五、算法草图：根层单元陷阱

主过程：

1. 零 LP 前检：若某个 $D_i=\varnothing$，直接 NO。
2. 解根 LP（带 lazy SD 割）。不可行 → 单证书 NO；整数 → YES。
3. 分数解：算 support $S_i(z)$。按「support 是否覆盖整个 domain 的两端」优先、再按 support 大小、最大质量、任务编号排序。
4. 对每个候选 $(i,t)$ 做一次单列删除 LP。若不可行，提取整数 Farkas 证书，验证
   $\mathrm{verify}(\Phi,\mathrm{forbid}=\{(i,t)\})$。
5. 若同一任务上出现两个不同 $t$ 的 forced 单元 → **单元陷阱**，根层 NO。
6. 若不同任务的 forced 单元违反一条优先序边或容量时刻 → **单元共识**，根层 NO。
7. 若没有陷阱，把已认证的 forced 单元写进 domain，回退到 QNC DFS。

在本轮 7 个根分数实例上，span-first 顺序让每一步都恰好命中被 forced 的端点，所以每个实例只需要 **2 次探针**。idx 5 用 job 6 的 $12/17$，idx 47 用 job 3 的 $6/8$。两个证书都是独立的单列 Farkas 证书，合起来就是「$s_6=12$ 且 $s_6=17$」的矛盾。

## 六、实验结果

141 个基准 + 60 个扰动，全部 $h=\mathrm{OPT}-1$，全部 NO：

| 方法 | NO | LP | 节点 | 墙钟 |
|---|---:|---:|---:|---:|
| ALC v6.1 | 201 | 284 | 229 | — |
| QNC v7.1 | 201 | 268 | 213 | 2.177 s |
| QUC v7.2 | 201 | 260 | 191 | 2.156 s |

- 7 个根分数实例全部根层闭合：QNC 46 LP / 29 节点 → QUC 38 LP / 7 节点；
- 单看 141 基准：QNC 147/137 → QUC 145/131；
- 单看 60 扰动：QNC 121/76 → QUC 115/60；
- 14 个单元证书全部重放通过，0 次提取失败；201/201 audit 通过；
- anytime：201 例在预算 6 就全部判 NO，QNC 要到预算 9；141 例在预算 6 到 141，QNC 要到 7。

收益的来源很集中：194/201 是空域、根 LP 不可行或整数，算法完全不变；真正被触发的是 7 个根分数实例。idx 5/h5 的 LP 数没有下降（6→6），但节点 3→1；idx 47/h47 既降 LP 又降节点。整体墙钟几乎不变（2.156 s vs 2.177 s），因为省下的分支被两次证书提取抵消。

## 七、这一轮学到的东西与负结果

1. **支持引理是这一轮真正的“算法设计”**：它把「猜哪些单元值得认证」变成「扫描当前 LP 解的正分量」。这不是启发式，而是完备性陈述（对单列陷阱而言）。
2. **单元陷阱不是新证明规则**：它只是 QNC v7.1 的「同任务两个 quorum 不相交」在单点 quorum 上的特例。新的是**检测方式**：根层 2 次探针，而不是等 DFS 走到叶子。
3. **跨任务单元共识没有触发**：7 个实例全是同任务陷阱；跨任务的优先序冲突规则实现了，但 0 次命中。它在理论上更强，在本数据上没有兑现。
4. **span-first 有过拟合风险**：这个顺序是看了 7 个实例后选的；离线 EA 也能找到每例 2 次探针的策略，但样本只有 7 个，不能当统计结论。
5. **回退成本没有测到**：所有根分数实例都命中了陷阱；如果某个根分数实例没有陷阱，QUC 会先花最多 6 次探针再重启 QNC，这是真实的 overhead。
6. **YES 侧仍未系统测**：所有 201 例都是 $h=\mathrm{OPT}-1$ 的 NO；单元陷阱只影响 NO 侧。

## 八、一句话最大风险

**收益完全条件于「根 LP 可行但分数」这一小撮实例（本轮 7/201）；换到根 LP 直接不可行的大多数实例算法不变，换到 support 很大、或矛盾需要多列 quorum / 更强割的实例，2 次探针的窗口会消失，探针预算反而变成额外成本。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
## 0. 版本关系与本轮增量

本轮产物是 **v7.2 QUC-ALC（Quorum Unit-Certificate ALC）**，直接建立在 v7.1 QNC-ALC 之上：不改 v6.0 的 SD 割数学，不改 v6.1 的中位数分支规则和 anytime 接口形状，只在根层增加一个**单元证书扫描**，并保留 QNC 的 clause、force、叶子证书层作为回退。

本轮增加五件事：

1. **单元探测**：对单个任务-时间文字 $p=(i,t)$，删掉该列后解一次 LP；不可行则证明 $s_i=t$，而不是禁止 $t$；
2. **支持引理**：若 $(i,t)$ 可被单元证书强制，则任意根 LP 可行解都有 $z_{i,t}>0$。所以所有可认证的单元都在当前解的 support 里，根层扫描 support 对单列陷阱是完备的；
3. **单元陷阱**：同一任务的两个不同 forced 单元 $s_i=t$、$s_i=u$（$t\ne u$）直接 NO；
4. **跨任务单元共识**：不同任务的 forced 单元若违反优先序边或容量时刻，也直接 NO；
5. **span-first 扫描顺序**：support 覆盖整个 domain 两端的任务优先，端点的开始时间先测；这是控制 probe 预算的排序启发式，不参与正确性。

另加一个可审计对象：每个单元探测记录 $(p,\Phi_p)$，独立重放 `verify(Φ_p, forbid={p})`；同任务陷阱额外检查 $t\ne u$。QUC 的 `audit_quc()` 先调用 QNC 的 `audit()`，再检查所有单元证书和陷阱。

推荐接口：

    QUC(inst, h, use_quorum=True, use_empty=True,
        unit_budget=6, unit_scan=True)
    .decide(budget, nodecap, max_rounds, topk) -> (verdict, state)
    .audit_quc() -> bool

与 v7.1 的关系：QUC 的单元陷阱是 QNC v7.1 的「同一任务两个 quorum 空交」在单点 quorum 上的特例；本轮的新东西不是证明规则，而是**在根层用 support 引理把这两个单点 quorum 找出来**。若扫描没有找到陷阱，QUC 回退到 QNC 的 DFS。

## 1. 符号

- $n$：任务数；$m$：机器数；$p_i$：加工时间；$\mathrm{pred}(i)$、$\mathrm{succ}(i)$、$\mathrm{elig}(i)$。
- $h$：待判定的 makespan 上界（NO 基准 $h=\mathrm{OPT}-1$）。
- $\mathrm{est}_i$、$q_i$：优先序头/尾；$D_i=\{\mathrm{est}_i,\dots,h-q_i-p_i\}$。
- $T=h$；非资格列 $c=(i,t)$，资格列 $c=(i,k,t)$。
- $z_{i,t}\in[0,1]$：开始时间分数指示；资格感知时 $z_{i,t}=\sum_k z_{i,k,t}$。
- $C$：已分离的 SD 割集；$\mathrm{LP}(C,E)$ 表示在割集 $C$ 下把列集 $E$ 删掉后的 start-time LP。
- $\Phi=(\alpha,\beta,\lambda,\mathrm{scale})$：整数 Farkas 证书；$\mathrm{verify}(\Phi,\mathrm{forbid}=E)$ 逐列重放 $(A_E)^T y\ge0$、$b^T y<0$。
- 单元文字 $p=(i,t)$；$\mathrm{forbid}(p)=\{(i,t)\}$。资格感知时它删除任务 $i$ 在时间 $t$ 的所有机器列 $(i,k,t)$。
- 单元证书 $\Phi_p$：$\mathrm{LP}(C,\{p\})$ 的 Farkas 证书；它证明 $s_i=t$。
- $S_i(z)=\{t:z_{i,t}>0\}$：任务 $i$ 在可行解 $z$ 中的 support；$\mu_i(t)=z_{i,t}$ 是 support 质量。
- $U\subseteq\cup_i D_i$：已认证单元集合；$U_i=\{t:(i,t)\in U\}$。
- $k_{\mathrm{unit}}$：单元 probe 预算；$B$：总 LP 数；$B_{\mathrm{unit}}$：probe 数。
- $Q$、$F^{\mathrm{force}}$、$L$：沿用 v7.1 的 clause、强制域、叶子证书；$L_{\mathrm{unit}}$：单元证书列表。
- $\mathrm{span}(i)$：$\min S_i(z)=\min D_i$ 且 $\max S_i(z)=\max D_i$。

## 2. 形式定义

### 2.1 单元探测与 force 方向

设 $C$ 是当前割集，$p=(i,t)$。若

$$\mathrm{LP}(C,\{p\})\ \text{不可行},$$

则由 `verify(Φ_p, forbid={p})` 得到一个有效证书，并称 $p$ 是 **forced unit**，记为 $s_i=t$。

方向必须写清楚：$\{p\}$ 是**被删掉的列**，但结论是「必须用 $p$」。这不是禁止 $t$，而是强制 $t$。证明：若存在可行整数调度使 $s_i\ne t$，它的指示向量在 $p$ 上为 0，删掉 $p$ 后仍可行，矛盾。两个 forced unit 给出 $s_i=t$ 与 $s_i=u$ 且 $t\ne u$ 时，才是矛盾。

单元证书对整个原问题有效，而不只对当前 LP 有效：$C$ 中每条割都是整数调度的有效不等式，所以 $\mathrm{LP}(C,\{p\})$ 是原问题在删除 $p$ 后的松弛；它不可行，原问题也不能避开 $p$。

### 2.2 支持引理

设 $z$ 是 $\mathrm{LP}(C)$ 的任意可行解。若 $\mathrm{LP}(C,\{p\})$ 不可行，则

$$z_p>0.$$

**证明**：若 $z_p=0$，删掉 $p$ 不会删掉 $z$ 的任何正分量；$z$ 仍满足所有约束，从而是 $\mathrm{LP}(C,\{p\})$ 的可行解，矛盾。∎

**推论**：所有可认证的单元都落在当前解的 support 中，即 $U_i\subseteq S_i(z)$。因此，固定一个可行 $z$、固定割集 $C$，扫描 $S_i(z)$ 对**同任务单列陷阱**是完备的：不会漏掉任何一对可认证的 $t,u$。

注意：这条引理对任意可行 $z$ 成立，不要求 $z$ 最优；也不要求 support 很小。它只说明「候选集可以压到 support」，不说明 support 一定小。本数据上 $|S_i|\le3$，所以 2 次 probe 就够；一般情况仍由 budget 控制。

### 2.3 单元陷阱

若 $U_i$ 中存在 $t\ne u$，则不存在可行调度，返回 NO。

**证明**：2.1 给出 $s_i=t$ 与 $s_i=u$，矛盾。∎

这是 QNC v7.1 定理 4.5 在 $E=\{t\}$、$E'=\{u\}$ 上的特例：两个单点 quorum 不相交。它没有增强证明强度；增强的是**发现方式**——在根层用 2 次 probe 发现，而不是等 DFS 到叶子。

### 2.4 跨任务单元共识

设 $U$ 是已认证单元集合。若以下任一条件成立，则 NO：

- **优先序**：$i\to j$，$(i,t)\in U$，$(j,u)\in U$，且 $t+p_i>u$；
- **容量**：存在 $\tau$，使 $|\{(i,t)\in U:t\le\tau<t+p_i\}|>m$；
- **同任务**：2.3。

**证明**：任一可行调度必须实现 $U$ 中每个单元；上述条件分别违反优先序约束或容量约束。∎

容量条件只数「任务数」，不区分机器；因此对资格感知实例也是 sound 的（每个任务在 $\tau$ 最多贡献 1 个单位的负载）。资格匹配导致的「无机器可放」冲突不在单元层检查；它需要额外的 matching 检查，见 6.2。

### 2.5 最小单元证书覆盖（优化模型）

把「找矛盾」写成：

    min |P|
    s.t. P ⊆ ∪_i S_i(z),
         ∀p∈P: LP(C,{p}) 不可行（有证书 Φ_p）,
         P 违反一条硬约束（2.3 或 2.4）.

- 同任务陷阱：$|P|=2$；
- 优先序冲突：$|P|=2$；
- 容量冲突：$|P|>m$。

支持引理给出候选全集；单元探测负责认证；扫描顺序是这个模型的一个贪心策略。它不是精确算法：预算 $k_{\mathrm{unit}}$ 可能截断，容量冲突需要多于 2 个单元，跨任务冲突需要不同任务的 support 同时命中。

### 2.6 anytime 状态

    S = (C, Q, F^force, L, U, B, B_unit)

不变式：

- $C$、$Q$、$L$、$U$ 只增；
- $F_i^{\mathrm{force}}$ 只缩（单元与已有强制域取交）；
- $B$、$B_{\mathrm{unit}}$ 只增；
- 预算增加时，已证的 NO 不回退，已认证的单元不回退。

当前实现的根层扫描在 `_root_phase` 内完成；如果扫描没有陷阱，`_apply_units` 把单元写进 force，再回退到 QNC 的 `_branch`。因此 QUC 的 anytime 曲线在根层之后与 QNC 相同，只是根层多了最多 $k_{\mathrm{unit}}$ 次 probe。

## 3. 算法

### 3.1 主过程

    function QUC_DECIDE(inst, h, budget):
        C = ∅; Q = ∅; force = {}; L = []; U = []
        if ∃i: D_i = ∅: return NO                 # 零 LP 前检
        res, z = solve_root_with_lazy_SD(C)       # 计 1 次 LP
        if res == INFEASIBLE:
            learn QNC leaf; return NO
        if z integral:
            return YES
        if unit_scan:
            con = SCAN_UNITS(z)
            if con is trap: return NO             # 2.3
            if con is cross: return NO            # 2.4
            apply_units_to_force()
        return QNC_BRANCH()                       # v7.1 回退

    function SCAN_UNITS(z):
        S = support(z)
        order jobs by (not span(i), |S_i|, -max μ_i(t), i)
        for i in ordered jobs with |S_i| >= 2:
            times = sorted(S_i)
            if span(i): times = [min, max] + interior by -μ
            else:       times = sorted by -μ, tie t
            for t in times:
                if B_unit >= k_unit: return None
                if (i,t) in U: continue
                ok, Φ = PROBE_UNIT(i,t)
                B += 1; B_unit += 1
                if not ok: continue
                U.append((i,t)); L_unit.append((i,t,Φ))
                L.append(({p},{p},Φ))
                con = UNIT_CONFLICT(U)
                if con != None: return con
        return None

    function PROBE_UNIT(i,t):
        # 用当前割集 C，只删列，不加新割；一次 LP
        res = LP(C, forbid={(i,t)})
        if res feasible: return False, None
        Φ = integer_farkas(forbid={(i,t)})
        if Φ is None or not verify(Φ, forbid={(i,t)}):
            unit_fail += 1; return False, None
        return True, Φ

关键点：

- probe 只解一次 LP，不做 lazy separation；它用的是根 LP 已经学到的割集 $C$。若 probe 可行，不产生任何结论；若不可行，提取 Farkas 证书。
- 单元证书同时追加到 `L`，所以 QNC 的 `audit()` 也会重放它；`audit_quc()` 再检查单元集合与陷阱。
- 若某个 probe 的证书提取失败，`unit_fail` 加 1，扫描继续；不把「提取失败」当成「未 forced」，也不产生错误判决。
- 若扫描没有陷阱，`_apply_units` 只把已认证的单元写进 force；未认证的候选不写。
- 根 LP 不可行或整数时，扫描不运行；这两类实例的行为与 QNC 完全一致。

### 3.2 扫描顺序

- **span-first**：若 support 覆盖当前 domain 的两端，先测低端点和高端点，再测内部；否则按 support 质量从大到小。
- 任务排序：`span` 优先，然后 `|S_i|` 小者优先，再按最大 support 质量降序，最后任务编号升序。
- 这个顺序只影响 probe 预算的命中率，不影响正确性；任何顺序下，找到的陷阱都是有效的。
- 7 个根分数实例的 support 都恰好是 domain 两端（如 job 6 的 $\{12,17\}$、job 3 的 $\{6,8\}$），所以 span-first 每例只用 2 次 probe。

### 3.3 审计

    function AUDIT_QUC():
        if not QNC_AUDIT(L): return False
        for (i,t,Φ) in L_unit:
            if not verify(Φ, forbid={(i,t)}): return False
        if trap (i,t,u):
            if t == u: return False
            if (i,t) not in U or (i,u) not in U: return False
        if cross:
            if cap: recount units at tau; check count == c and c > m
            if prec: check edge and u < t + p_i
        return True

- 同任务陷阱检查两个单元证书都在 $U$ 中，且 $t\ne u$。
- 跨任务优先序检查边存在且确实违反；容量检查重新数 $\tau$ 处的单元数，且 $>m$。
- 本轮 7 个陷阱全是同任务；跨任务路径没有实验命中，只有实现与定理。

### 3.4 预算

- `unit_budget` 默认 6，只计单元 probe；根 LP 的 lazy 分离和回退 DFS 计 `budget`。
- 若 `B_unit` 达到 `unit_budget`，停止扫描；若没有陷阱，回退 QNC。
- 若全局 `budget` 耗尽，返回 UNKNOWN；不产生判决。
- `nodecap` 计 DFS 节点；根层陷阱的 NO 是 1 个节点。
- 本轮 7 个陷阱都在 2 次 probe 内命中；`unit_budget=6` 留了 3 倍余量。

## 4. 定理与证明

### 4.1 单元引理

设 $C$ 是有效割集，$p=(i,t)$。若 $\mathrm{LP}(C,\{p\})$ 不可行，则每个可行整数调度都有 $s_i=t$。

**证明**：若 $s_i\ne t$，其指示向量在 $p$ 上为 0（资格感知时所有 $(i,k,t)$ 都为 0），删掉 $p$ 后仍满足 $C$ 和全部约束，与不可行矛盾。∎

### 4.2 支持引理

设 $z$ 是 $\mathrm{LP}(C)$ 的任意可行解。若 $\mathrm{LP}(C,\{p\})$ 不可行，则 $z_p>0$。

**证明**：若 $z_p=0$，删除 $p$ 不删除任何正分量，$z$ 仍是 $\mathrm{LP}(C,\{p\})$ 的可行解，矛盾。∎

**推论**：$U_i\subseteq S_i(z)$；对固定 $z$ 和 $C$，扫描 $S_i(z)$ 对同任务单列陷阱完备。

### 4.3 单元陷阱定理

若 $U$ 中有 $(i,t)$、$(i,u)$ 且 $t\ne u$，则 NO。

**证明**：由 4.1，$s_i=t$ 且 $s_i=u$，矛盾。∎

### 4.4 跨任务单元共识

若 $U$ 违反一条优先序边或某个时刻的容量上界，则 NO。

**证明**：4.1 强制每个单元；可行调度必须满足优先序与容量，与违反条件矛盾。∎

### 4.5 支持扫描的完备性

固定根 LP 可行解 $z$ 与割集 $C$。若存在同任务单列陷阱 $t,u$，且两个单元都可认证，则 $t,u\in S_i(z)$；若扫描按任意顺序遍历 $S_i$ 且预算足够，必能找到该陷阱。

**证明**：由 4.2 得 $t,u\in S_i(z)$；扫描遍历 support；两个 probe 都不可行时，4.3 返回 NO。∎

注意：这是**同任务单列陷阱**的完备性，不是所有 NO 的完备性。跨任务冲突、容量冲突、多列 quorum 不在这个陈述内；预算截断也会破坏「必能找到」。

### 4.6 回退可靠性

若扫描没有找到陷阱，QUC 回退到 QNC；QNC 的 NO 证书与 YES 整数解都是 sound 的。若扫描找到陷阱，4.3/4.4 给出 NO。因此 QUC 的 NO 判决 sound；YES 判决来自根 LP 的整数解，也是 sound；预算耗尽返回 UNKNOWN。

### 4.7 单调性

$C,Q,L,U$ 只增，force 只缩；新增割只会加强 LP，已认证的单元仍然有效，陷阱仍然是陷阱。预算增加时，扫描顺序固定，状态是前一时刻的扩展，所以已证 NO 不回退。当前实现的 anytime 曲线是「固定顺序 + 预算前缀」，不是在线重排。

### 4.8 复杂度

- 根 LP：与 QNC 相同，变量 $O(nmT)$，约束 $O(mT+n+|C|)$。
- 每次 probe：一次 LP（无 lazy 分离）+ 一次整数 Farkas 提取；提取 $O(|\mathrm{DENS}|\cdot\mathrm{nnz}(A))$。
- support 计算 $O(\mathrm{nnz}(z))$；排序 $O(n\log n+|S|\log|S|)$。
- 总 LP $\le B$；总 probe $\le k_{\mathrm{unit}}$；总节点 $\le$ `nodecap`。
- 额外成本上界：$k_{\mathrm{unit}}$ 次 LP + $k_{\mathrm{unit}}$ 次证书提取；本轮 7 例共 14 次 probe、14 个证书。

## 5. 实验

### 5.1 设置

- 数据：141 例 NO 基准（holdout 50、synth2_45、large_a 8、large_b 10、large_het 8、hard3 12、deep 8），$h=\mathrm{OPT}-1$。
- 扰动集：对 holdout idx 5/47 随机改一个 $p_i$（±1），重新求 OPT，得 60 例；其中 5 例在 $h=\mathrm{OPT}-1$ 需要分支，且根 LP 分数。
- 环境：Python 3.12、NumPy 2.5.4、SciPy 1.18.1（HiGHS），单线程；实现 `exp/v72/quc.py`。
- 预算：`unit_budget=6`，每节点 `max_rounds=60`、`topk=100`、`nodecap=5000`；实测远低于上限。
- 基线：QNC v7.1（`exp/v71/qnc.py`）、ALC v6.1（`exp/v61/alc.py`）。
- 公平墙钟：`exp/v72/bench_time.py`，QNC 与 QUC 在同一批 201 例上顺序运行。

### 5.2 主结果（201 例）

| 方法 | NO | LP | 节点 | 墙钟(s) |
|---|---:|---:|---:|---:|
| v6.1 ALC | 201 | 284 | 229 | — |
| v7.1 QNC | 201 | 268 | 213 | 2.177 |
| **v7.2 QUC** | **201** | **260** | **191** | **2.156** |

相对 QNC：LP −3.0%，节点 −10.3%，墙钟 −0.02 s（基本持平）。ALC 的 LP/节点复用 v7.1 基线，墙钟未在 201 例上重测（—）；QNC/QUC 的 2.177/2.156 s 是同一 `bench_time.py` 的顺序计时。

分拆：

| 子集 | ALC LP/节点 | QNC LP/节点 | QUC LP/节点 |
|---|---:|---:|---:|
| 141 基准 | 159 / 149 | 147 / 137 | 145 / 131 |
| 60 扰动 | 125 / 80 | 121 / 76 | 115 / 60 |
| 合计 | 284 / 229 | 268 / 213 | 260 / 191 |

- 141 基准的 −2 LP / −6 节点来自 holdout idx 5/47 两个根分数实例；
- 60 扰动的 −6 LP / −16 节点来自 5 个根分数实例；
- 其余 194 例是空域、根 LP 不可行或整数，QUC 与 QNC 完全相同；
- 墙钟：QUC 在深分支例（idx 47、h47-18、h47-26）更快，在 idx 5、h5 与 h47-6 上略慢（多 2 次证书提取），总体几乎持平。

### 5.3 7 个根分数实例

| 实例 | 根 LP | 陷阱任务 | support | QNC LP/节点 | QUC LP/节点 | probe |
|---|---:|---|---|---:|---:|---:|
| holdout 5 | 4 | 6 | {12,17}=D_6 | 6 / 3 | 6 / 1 | 2 |
| holdout 47 | 3 | 3 | {6,8}=D_3 | 7 / 5 | 5 / 1 | 2 |
| h5-6 | 4 | 6 | {13,18}=D_6 | 6 / 3 | 6 / 1 | 2 |
| h5-16 | 4 | 6 | {13,18}=D_6 | 6 / 3 | 6 / 1 | 2 |
| h47-6 | 3 | 3 | {6,8}=D_3 | 5 / 3 | 5 / 1 | 2 |
| h47-18 | 3 | 3 | {5,7}=D_3 | 7 / 5 | 5 / 1 | 2 |
| h47-26 | 3 | 3 | {6,8}=D_3 | 9 / 7 | 5 / 1 | 2 |
| **合计** | **24** | | | **46 / 29** | **38 / 7** | **14** |

- 7 个陷阱任务全部是 span：support 恰好是 domain 的两端；
- 每个实例的 2 个单元都是不同开始时间，构成 2.3 的陷阱；
- 14 个单元证书全部重放通过，0 次提取失败；`scale` 11–73，中位数约 35；`dom` 行 0–4，`beta` 行 8–23；
- 根 LP + probe = QUC 总 LP：idx 5 是 4+2=6，idx 47 是 3+2=5，其余同理；
- QUC 在这些实例上把 29 个 DFS 节点压成 7 个，LP 从 46 压到 38。

### 5.4 排序 ablation

在同样的 7 个实例上，只改 probe 顺序：

| 顺序 | 总 LP | 节点 | probe |
|---|---:|---:|---:|
| 按 support 大小/质量 | 44 | 7 | 20 |
| **span-first + job-index tie-break** | **38** | **7** | **14** |
| 理论下界（每例 2 probe） | 38 | 7 | 14 |

- 理论下界 = 7 个根 LP（24）+ 14 个 probe = 38；span-first 达到下界。
- 离线 EA：用 7 个实例的 forced/free 缓存标签，population 30 × 40 代，在线性排序特征上搜索；最优策略也是 14 个 probe（每例 2 个）。
- 排序 ablation 的脚本 `exp/v72/order_ablation.py` 与结果 `order_ablation.json`：span 38/7/14，support 44/7/20；两档都 7/7 NO、7/7 audit。
- 一个缺少 job-index tie-break 的手写 span 策略在同一组上要 23 个 probe（h47-26 的并列 support 处理失败），说明排序细节会影响预算命中；但正确性不受影响。
- EA 是**离线设计工具**，不是在线算法的一部分；样本只有 7 个，不能当作泛化结论。

### 5.5 anytime

201 例（141 基准 + 60 扰动），按 LP 预算 $k$ 重跑；顺序固定，所以 $k$ 时刻的状态是 $k+1$ 的前缀：

| k | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| QNC 已判 NO | 10 | 164 | 186 | 194 | 194 | 195 | 198 | 200 | 200 | 201 |
| **QUC 已判 NO** | **10** | **164** | **186** | **194** | **194** | **198** | **201** | **201** | **201** | **201** |

141 基准单独看：

| k | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| QNC 已判 NO | 10 | 135 | 138 | 139 | 139 | 139 | 140 | 141 |
| **QUC 已判 NO** | **10** | **135** | **138** | **139** | **139** | **140** | **141** | **141** |

- 201 例：QUC 在预算 6 全部判 NO，QNC 要到 9；QUC 在 $k=5,6,7,8$ 严格占优，其余持平。
- 141 例：QUC 在预算 6 到 141，QNC 要到 7；QUC 在 $k=5,6$ 严格占优。
- $k=0$ 的 10 例是空域关闭，两者相同；其余是 Farkas 叶子重放。

### 5.6 证书与审计

- 14 个单元证书：7 个陷阱 × 2；全部 `verify(Φ, forbid={(i,t)})` 通过；0 次提取失败。
- 201/201 返回 NO，且 `audit_quc()` 通过；无误判 YES。
- 7/7 陷阱是同任务；0 次跨任务共识命中；0 次 clause 剪枝（QUC 的陷阱在根层返回，未进入 QNC DFS；非陷阱实例沿用 v7.1 的 0 次）。
- 194/201 不受益：其中 10 例空域在 0 LP 关闭，其余根 LP 不可行或整数。
- 资格感知压力测试：对 7 个根分数实例随机限制资格（每个任务随机去掉一台机器，$h$ 仍取原 OPT−1），得 35 个变体；35/35 NO，2 个仍根分数且都被 2 探针陷阱闭合，35/35 audit 通过。这个小测只验证资格路径不崩，不进入主表；脚本 `exp/v72/elig_stress.py`，结果 `elig_stress.json`。

### 5.7 负结果与限制

1. **收益高度条件化**：只有 7/201 是「根 LP 可行但分数」；194/201 算法完全不变。QUC 不是通用加速，而是根分数实例的专用闭合器。
2. **单元陷阱不是新证明规则**：它是 QNC v7.1 的空交规则在单点上的特例；新的是 support 引理 + 根层主动探测。若审稿人问「证明强度增加了什么」，答案是「没有，增加的是发现方式」。
3. **跨任务共识 0 次命中**：7 个实例全是同任务冲突；优先序/容量规则实现了，但没有数据兑现。容量审计路径也只做了实现级检查，未在本轮实验中触发。
4. **idx 5/h5 的 LP 数不降**：6→6；收益是节点 3→1 和证明形状，不是 LP。墙钟在这些例上略慢（+0.003 s），因为多了 2 次证书提取。
5. **span-first 有过拟合风险**：顺序是看了 7 个实例后选的；离线 EA 也找到 14 probe，但样本只有 7 个，不能证明泛化。
6. **回退成本未测到**：所有根分数实例都命中了陷阱；如果某个根分数实例没有陷阱，QUC 会先花最多 6 次 probe，再重启 QNC 的根 LP，这是真实的 overhead。
7. **support 大小风险**：本轮 $|S_i|\le3$，2 probe 够用；support 很大时，预算 6 可能截断，需要排序/EA 或更大预算。
8. **证书依赖割集**：probe 不加大割，只用当前 $C$；更强的割可能认证更多单元，也可能改变 support。当前设计牺牲了「用 probe 学新割」的机会，换取 1 次 LP/probe 的成本。
9. **数值**：support 阈值 $10^{-7}$；极小正质量可能被当成 0。`scale` 远低于 DENS 上限，本轮没有舍入失败，但更大实例仍有风险。
10. **YES 侧未系统测**：201 例全是 NO；单元陷阱只影响 NO 侧。回退后的 YES 仍来自整数 LP 解，未用独立调度检查器复验。
11. **根层 only**：当前只在根层扫描；内部节点的分数解没有扫描。内部节点可能也有单列陷阱，未测。
12. **单单元回退未触发**：7 个根分数实例都直接 trap；没有出现「只认证一个单元、无 trap，写 force 后回退 QNC」的路径。该路径的正确性由 QNC 保证，但性能没有实验数据。
13. **无统计结论**：7 个根分数实例、5 个扰动分支例；只能说明机制是通的。

## 6. 风险与下一步

### 6.1 已知风险

1. **数据分布风险（最大）**：7/201 触发；194/201 不变。换到根 LP 总是不可行的语料，QUC 等于 QNC 加一段不执行的代码；换到根 LP 分数但 support 很大、或矛盾需要多列 quorum 的语料，2 次 probe 的窗口消失，probe 预算反而成为 overhead。
2. **主要收益不是「更强的证明」**：同任务陷阱是旧规则；真正的贡献是 support 引理和根层检测。若评审只认证明强度，这一轮的增量会被低估；若评审认「同样的证明更早找到」，则成立。
3. **span-first 过拟合**：7 个实例的 support 都恰好是 domain 两端，这是被选中的原因，不是随机样本的性质。离线 EA 的 14 probe 也不能消除样本偏差。
4. **回退 overhead**：无陷阱的根分数实例会先花 probe 再重启 QNC；本轮没有这种实例，成本未实测。
5. **跨任务/资格共识未兑现**：0 次命中；容量审计路径未实验触发；资格匹配冲突还需要 matching 检查。
6. **证书成本**：14 次 probe 带来 14 次 Farkas 提取；整体墙钟持平，但在更大 LP 上提取成本可能超过省下的分支。
7. **support/割集/数值依赖**：support 由当前 LP 解决定；不同割集、不同最优解可能给出不同 support；阈值和 DENS 舍入是数值风险。
8. **YES 侧未测**：所有实验都是 NO；不能声称对 YES 侧同样有效。
9. **根层 only**：内部节点未扫描；若根层陷阱少、内部节点陷阱多，收益会被低估。
10. **无统计功效**：7 个分支例，不能支撑「平均加速」的结论。

### 6.2 下一步

1. **把根层扫描并入 QNC DFS，去掉重启**：当前 `_root_phase` 扫描失败后 `_branch` 会重新解根 LP；应把 `C`、`force`、`U` 直接传给 `_branch`，省掉一次根 LP，也测回退成本。
2. **内部节点扫描**：在每个分数节点的 support 上做单列 probe；与 QNC 的叶子 quorum 合并，观察是否能把「空交发现太晚」变成「内部节点提前闭合」。
3. **多列 quorum 的 support 引理**：把单列 $p=(i,t)$ 推广到列集 $E$；用 IHS/master 在 support 上找最小可认证 $E$。这是从「单元陷阱」走向「集合陷阱」的下一步。
4. **跨任务共识的完整版**：容量 + 资格 matching（二分图/最大流）；优先序传递闭包；把「单元集合违反一条硬约束」做成一个独立的冲突检查器。
5. **proof-tree 序列化**：单元陷阱是 2 叶证明；把它与 QNC 的树合并，写独立 checker：单元证书 + split 覆盖 + force 链。当前 `audit_quc` 仍只逐叶重放，不是整树检查。
6. **弱 LP / 大 $n$ 家族**：构造根 LP 分数且 support 更大的实例，系统测 $|S_i|$、probe 预算、LP 强度三者的关系；本轮只有 7 例，且 support 都小。
7. **anytime 调度**：把 probe 和分支交错，而不是固定根层扫描；用预算感知的策略决定「继续 probe 还是回退」。
8. **证书增量/暖启动**：probe 的 Farkas 提取可以复用根 LP 的对偶；目标是把 14 次提取的成本压到与省下的分支相抵以下。
9. **YES 侧与独立调度检查器**：对 YES 结果做独立的资源/优先序复验，补上本轮缺口。
10. **统计评估**：在更多根分数实例上重复，报告均值/方差，而不是 7 例的个案。

## 7. 复现文件

- `exp/v72/quc.py`：QUC 类、support 扫描、单元证书、`audit_quc`；继承 `exp/v71/qnc.py` 的 QNC。
- `exp/v72/bench_quc.py`、`exp/v72/quc_stats.json`：201 例主实验（逐例 LP/节点/probe/trap/audit）。
- `exp/v72/bench_time.py`、`exp/v72/time.json`：QNC vs QUC 公平墙钟；顶层 `qnc_t`/`quc_t` 含总墙钟。
- `exp/v72/ea_order.py`、`exp/v72/ea_order.json`：离线排序 EA（缓存 forced/free 标签，30×40）。
- `exp/v72/order_ablation.py`、`exp/v72/order_ablation.json`：span-first vs support-size 的确定性排序 ablation。
- `exp/v72/elig_stress.py`、`exp/v72/elig_stress.json`：资格感知压力测试（35 个变体，2 个根分数陷阱）。
- 依赖：`exp/v71/qnc.py`（QNC 状态机/证书/审计）、`exp/v61/alc.py`（v6.1 基线）、`exp/v60/lazy.py`（lazy SD）、`exp/v60/cert.py`（DENS/verify/_row_meta）、`exp/v13/po.py`（heads_tails）。
- 数据：`exp/v20/holdout_cases50.pkl`、`exp/v28/synth2_45.pkl`、`exp/v14/{large_a,large_b,large_het}.pkl`、`exp/v13/hard3.pkl`、`exp/v18/deep.pkl`；扰动集 `exp/v71/perturb60.pkl`。
- 运行环境：Python 3.12、NumPy 2.5.4、SciPy 1.18.1（HiGHS）；工作目录 `/home/runner/work/xuen/xuen/workspace`。
- 复现命令：

      .venv/bin/python exp/v72/bench_quc.py
      .venv/bin/python exp/v72/bench_time.py
      .venv/bin/python exp/v72/ea_order.py
      .venv/bin/python exp/v72/order_ablation.py
      .venv/bin/python exp/v72/elig_stress.py

## 8. 一句话最大风险

**收益完全条件于「根 LP 可行但分数」这一小撮实例（本轮 7/201）；换到根 LP 直接不可行的大多数实例算法不变，换到 support 很大、或矛盾需要多列 quorum / 更强割的实例，2 次探针的窗口会消失，探针预算反而变成额外成本。**
<!-- ARTIFACT:END -->
