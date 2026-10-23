# 想法区 · 第 3 轮：从「块」到「链」——把跨块耦合变成前置条件

**灵感词**：parallel algorithm / 蒙特卡洛方法 / precondition
**起点**：v2.1「X-DUB/PACE-ΠA*」。38 例 38 节点 / 2 表，deep 8 例 8 / 6，held-out 50 例 229 / 128（43 胜 7 平 0 负），easy 60 例 781，planted n=17–24 21 例 21 节点。它的收官风险仍然是一句话：

> MAP 把「数块」升级成「块到机器的匹配」，但它仍然忽略块与块之间的时间耦合：当不可行性来自跨块优先序而不是装填/资格时，MAP 只能说 YES，搜索仍要回到 d!；5 个 held-out 残例就是这条边界。

本轮不推倒 v2.1。我想把这句话再往前推一格：**如果「块到机器的匹配」也走到头了，那么下一个该被用掉的结构是什么？**

## 一、残例的解剖：MAP 的变量表里没有「时间」

MAP 的定义是一个存在句：

```text
∃ 划分 R = S_1 ⊔ … ⊔ S_t，∃ 单射 φ，  f_{φ(j)}[S_j] ≤ h .
```

它有三个变量：块、机器、单射。它没有第四个变量：**块与块之间的时间**。两个块各自在自己的机器上可行，并不等于它们能以正确的先后关系同时存在。5 个 held-out 残例（idx 5/21/32/42/47）在 `h=OPT−1` 上 `MAP=1`、真实不可行，原因正是这个：`i∈S_a`、`j∈S_b`、`i≺j`，但 MAP 把 `S_a` 和 `S_b` 当成两个可以独立安排的黑盒，丢掉了「`i` 什么时候结束、`j` 什么时候开始」。

继续在 MAP 里加「更细的块 / 更多的机器匹配 / 更强的资格检查」不会修好它。这不是划分不够细，而是**被丢掉的变量不是集合，是时间**。

## 二、直觉：一条链就是一组「必须同时成立」的前置条件

取残余 DAG 里的一条链 `P=(i_1≺…≺i_L)`。任何可行排程都给 P 一个起点向量 `s=(s_1,…,s_L)`。**如果我把 `s` 固定住**，那么对每个不在 P 上的任务 `j`，它的可行域立刻被三样东西夹住：

```text
release   r_j = 从固定链和 est 向前传播的最长路；
deadline  d_j = 从固定链和 h−q 向后传播的最晚完成；
capacity  c_s(t) = t 时刻已可用机器数 − P 在 t 时刻的占用（0 或 1）。
```

剩下的问题 `RES(σ,P,s)` 是一个更小的、只含 `R\P` 的调度问题。关键的一句话是：

> 如果**每一个** placement `s` 的 `RES(σ,P,s)` 都不可行，那么 `σ` 一定不可行。

因为任一可行排程都会在 P 上留下某个 placement，并把其余任务留成一个 residual 排程；所以「所有 placement 都失败」是「不存在可行排程」的逆否命题。这不是启发式，是**全称证书**。

这就是本轮想用的「precondition」：链是粗变量，固定它把原来的 m 机耦合问题**预处理**成「窗口 + 容量 profile」的 residual。它和数值计算里的预条件子是同构的：链是刚性、低秩的那一块；residual 是需要修正的细块。关键路径是**最便宜的那个预条件子**：它最小化松弛 `S=h−cp`，因而最小化 placement 数 `C(S+L,L)`；但更长的链会留下更小的 residual，所以不该只取一条链，而该有一个**链的 portfolio**。

## 三、为什么是「链」，不是「块」：全称 vs 存在

这是本轮最想写清楚的一个逻辑点：

- 块是**存在**对象。MAP 问「是否存在一个划分/分配」；找不到反例时它只能说「未知」。
- 链是**全称**对象。每一条链都出现在每一个可行排程里；所以「某一条链的所有 placement 都失败」就足以否定整个状态。

这条区分直接决定了蒙特卡洛该怎么用：

> **只能采样链，不能采样 placement。**

采样 placement 是存在句：抽到几个失败的 placement，不能推出「所有 placement 都失败」；它只能帮你找 YES，不能帮你证 NO。采样链是全称句：抽到一条链，对它做**穷尽**的 placement 枚举；只要这一条链被驳倒，NO 就是可靠的。于是蒙特卡洛的随机性只影响**覆盖率**（能不能抽到一条好链），不影响**可靠性**（绝不会假 NO）。这正是我想要的那种「有原则的随机化」。

## 四、形式化（简版；完整定义、证明与实现见产物区）

**定义 1（链与链松弛）**。`P=(i_1,…,i_L)` 是残余 DAG 中的一条有向路径（相邻两项有优先边，允许传递）。令

```text
S(P) = h − ( est_{i_1} + Σ_t p_{i_t} + q_{i_L} ) .
```

对关键路径，`S(P)=h−cp(σ)`；对任意链，`S(P)≥h−cp(σ)`。

**定义 2（placement）**。`s∈Z^L` 是 P 的 placement，若

```text
s_1 ≥ est_{i_1},   s_{t+1} ≥ s_t+p_{i_t},   s_t+p_{i_t} ≤ h−q_{i_t} .
```

等价地，用 gap 分解

```text
g_0 = s_1−est_{i_1},  g_t = s_{t+1}−(s_t+p_{i_t})  (1≤t<L),
g_L = (h−q_{i_L})−(s_L+p_{i_L}),
```

则 `g_t≥0`、`Σg_t=S(P)`。枚举所有 composition 就是枚举所有整数 placement；`g_L` 是链后剩余松弛，不参与建 `s`，只负责把总和补齐。

**定义 3（residual）**。固定 `P,s` 后，`RES(σ,P,s)` 是给每个 `j∈R\P` 选整数起点 `t_j`，满足

```text
r_j ≤ t_j,   t_j+p_j ≤ d_j,   u≺v ⇒ t_u+p_u ≤ t_v,
|{j : t_j ≤ t < t_j+p_j}| ≤ c_s(t)   对所有 t .
```

**定义 4（CPS 三值语义）**。

```text
CPS(σ) = NO       若 S(σ)<0，或对 P 的每个 placement s，RES(σ,P,s)=0；
         YES      若存在 placement s 使 RES(σ,P,s)=1（仅在全资格+精确 residual 时作为可行性证明）；
         UNKNOWN  若 S(σ)>τ、或 residual 撞 nodecap、或异资格下 RES=1。
```

**定理 1（投影/可靠性）**。任一可行排程都投影到 P 的某个 placement 和一个 residual 排程；所以 `CPS(σ)=NO ⇒ σ` 不可行。

**定理 2（精确性）**。若所有任务全资格、residual 用精确回溯、且没有撞 cap，则 `CPS` 是一个**判决过程**：存在 placement 的 residual 排程 ⇔ `σ` 可行。证明的构造部分是区间图染色：把链区间和 residual 区间放在一起，任意时刻活跃区间数 ≤ 可用机器数，按起点贪心染色即可；链任务不要求在同一台机器上（优先序只约束时间）。

**定理 3（并行正确性）**。把 placement 集合任意划分给 P 个 worker；每个 worker 只对它那一块做穷尽判定；全局用 OR（有 YES → YES/UNKNOWN）与 AND（全 NO → NO）合并。早停只允许发生在 YES 上；NO 必须等所有 worker 都返回 NO。

**定理 4（蒙特卡洛可靠性）**。从任意分布 D 采样 K 条链，每条链穷尽枚举 placement；若某条链被驳倒，返回 NO。假 NO 概率为 0。若 D 下「可驳倒链」的比例为 ρ，则 K 条都漏掉的概率 ≤ `(1−ρ)^K`。

## 五、并行：placement 是天然的任务

placement 之间没有数据依赖：每个 placement 自己算窗口、容量、residual。于是并行算法是「枚举—分块—OR/AND」：

```text
PAR-CPS(σ,P,W):
    Π ← ENUM_PLACEMENTS(σ,P)
    split Π into W chunks
    parallel for w:  for s in chunk[w]:
                         if RES(σ,P,s)=1: return FEASIBLE
                         if RES(σ,P,s)=UNKNOWN: mark unknown
    return NO if all chunks NO; UNKNOWN if any unknown; FEASIBLE otherwise
```

设 `W=Σ_s T(s)`、`D=max_s T(s)`。P 个 worker 的 list-scheduling 上界是

```text
C_max ≤ W/P + (1−1/P)·D ,
speedup ≤ P / (1 + P·D/W) .
```

这个式子解释了实测：5 个残例里最长的单个 placement 占总量约 20%，所以 4 核理论上限只有约 2.1×，实测 1.98×；不是并行没写好，而是**证书的关键路径就是那一个最难的 residual**。要继续快，只能并行化 residual 的 DFS 本身，而不是 placement。

## 六、蒙特卡洛：只采样链

在默认 cap（300k）下，关键链已经 5/5 根闭，portfolio 没有额外收益；这说明「链的随机化」不是万能的。但把每个 placement 的 residual 预算收紧到 4k 节点时，情况变了：

- 关键链：case 21 的单个 placement 需要 8098 节点，case 47 超过 8000；两者变成 UNKNOWN；关键链只闭 3/5。
- 换一条**更长/不同**的链：residual 更小、单 placement 的尾部更低；case 21/47 都能在 4k 内被驳倒；portfolio 5/5。
- 随机链（30 条，max-weight 随机路径）：case 21 命中 12/30，case 47 命中 10/30；`ρ≈0.4`，K=8 的漏检估计 `(0.6)^8≈1.7%`。

这就是蒙特卡洛的正确用法：**不是随机化 placement，而是随机化链，把「哪条链的 residual 尾部更短」变成一个可重复的采样问题**。它只在「预算受限 / 关键链撞 cap / 异资格」时有用；默认 cap 下它是纯开销。

一个负结果也要写下来：随机化 residual 的变量/值顺序非常糟。case 42 的确定性顺序是 19,208 节点；随机顺序的 4 个种子是 54.7 万–158 万节点，`maxp` 顺序是 242 万。原因是最小可选起点数（minopts）本身就是一个强 MRV 启发式，随机化把它破坏了。所以本轮只用「链的随机化」，不用「residual 的随机化」。

## 七、本轮要交付什么

- **v2.2 = v2.1 + CPS（tier 0.15）**：5 个 held-out 残例从 184 节点降到 5（全部根闭为 1）；held-out 229→50（4.58×，50/50 根闭）；38/deep/easy/planted 不变。
- **PAR-CPS 原型**：4 vCPU、fork 分块；5 个残例 2.00 s→1.01 s（1.98×）；case 21 0.76→0.37 s，case 5 0.34→0.17 s。
- **MC-CPS 原型**：4k 预算下关键链 3/5、链 portfolio 5/5；随机链命中率 12/30、10/30；默认 cap 下 0 额外收益（诚实负结果）。
- **正确性**：1,430 个 A=0 全资格状态、1,977 个随机 A 状态、1,977 个异资格状态，CPS-vs-精确引擎 0 不一致；异资格 150 个 NO，0 假 NO；50 个 h=OPT 状态 0 假 NO；50 个 YES 排程独立验证。
- **边界**：`S≤4`、`n≤16`、全资格、精确 residual；异资格只保证 NO 可靠，YES 只是 unknown；没有短证书；没有 Coq/Lean。

## 八、一句话最大风险

**CPS 的完备性是拿「枚举一条链的所有 placement + 精确 residual 回溯」换来的：它只在 `S≤4`、`n≤16`、全资格且 residual 未撞 cap 的紧状态上是判决过程；一旦 residual 变大或资格异构，它只能退回 unknown，最坏情况仍是 d!。**
