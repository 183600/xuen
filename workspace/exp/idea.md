# 想法区 · 第 1 轮：从 X-DUB/AG* 到 X-DUB/DA

**灵感词**：dynamic analysis / derandomization / 算法范式  
**起点**：v0.5「X-DUB/AG*」——一致 A\* + 贪心焦点 + 证书/状态泛化  
**本轮性质**：不推翻 v0.5 的任何定理。只补三个它没有闭合的结构性缺口：**搜索不会观测自己的间隙**、**核心循环里仍有采样**、**搜索范式没有理论**。

---

## 一句话直觉

v0.5 的证明 DAG 是一台很强的**静态证书机器**，但它不会**观测自己**：它不知道当前 `U-L` 的间隙来自优先约束还是装箱，不知道 focal 何时在空转，也不知道自己还有哪些选择是"采样"出来的。

本轮让搜索学会三件事：

1. **看见间隙**（GAP-LEDGER）：把 `U-L` 拆成 `G_search + G_cert`，并给每个证书族一个**零装箱测试**的收益上界 `η`；
2. **把采样换成带证明的确定性构造**（DERAND）：窗口扫描变成二级 B&B，focal 截断变成容许带内的确定性选择，MCTS rollout 变成 MCE dive；
3. **把搜索范式变成可切换的自动机**（PARADIGM-AUTOMATON）：DIVE / CLIMB / CERT / MERGE 四态，切换由 ledger 决定，并证明切换只改顺序、不改剪枝。

---

## 1. 三个缺口，不是三个标签

### 缺口 A：证书族是"盲投"的

v0.5 在根上跑 THRESH，在内部节点跑 `AVAIL(U-1)`。但第 7 轮实验已经诚实报告：20 个"贪心上界比 OPT 差 ≥2"的根实例上，THRESH **一次都没有**闭合剩余间隙。原因是这些间隙来自优先约束和机器分配，装箱证书再强也碰不到。

v0.5 知道这个负结果，却没有把它变成算法：它只是把 THRESH 调成"每 `T_scan` 次扩展跑一次"。

> **dynamic analysis 的启发**：不要问"这个证书族平均好不好"，要问"在当前这个状态上，它**可能**改变 `L_loc` 吗？"

这个问题的答案可以是一个**零装箱测试**的算术判据。见 §3 的 `η` 与 `slack`。

### 缺口 B：focal 与 best-first 的取舍没有理论

v0.5 证明了 `f(child) ≥ f(parent)`，但只用它来说"不需要 reopening"。它没有用这个性质解释 anytime 与节点数的分裂：

- focal 在 25 次扩展时已 29/30 找到 OPT，但最终节点数不一定最少；
- best-first 最终节点数不错，anytime 却差。

> **算法范式的启发**：这不是两个启发式的竞争，而是 **gap 的两端**。把"搜索"拆成 `DIVE`（降 `U`）与 `CLIMB`（抬 `f_min`），让切换由 ledger 决定，并证明切换不影响精确性。

### 缺口 C：核心循环里仍有采样

窗口扫描顺序、`B_focal` 截断、MCTS rollout、bandit 选择——它们不影响正确性，但让实验不可复现，也没有最坏保证。v0.4 的 bandit 负结果（只匹配最佳固定顺序）已经说明：**在廉价特征下，统计泛化不是出路**。

> **derandomization 的启发**：不是"固定随机种子"，而是换成**带精确性/支配性证明的确定性构造**。

---

## 2. 关键观察：一致性把 gap 劈成两个单调驱动

### 引理（`f_min` 单调）

若每步展开一个 `f` 最小的节点，则

```text
f_min = min_{v∈Open} f(v)
```

单调不减。

**证明**：被展开的节点 `v` 满足 `f(v)=f_min`。v0.5 的一致性定理给出每个子节点 `w` 的 `f(w) ≥ f(v) = f_min`。移除 `v` 后，`Open` 中剩余节点仍有 `f ≥ f_min`，新子节点也满足 `f ≥ f_min`，故新的最小值不小于旧的。证毕。

这个引理 v0.5 没有显式写出，但它是本轮全部搜索调度的基础。定义

```text
G_search = U - f_min          # 前沿还差多少才够到 U
G_cert   = f_min - L_global   # 前沿最小值与全局根证书的差
G        = U - L = G_search + (L_global 与 f_min 的较大者关系)
```

更准确地说，`L = max(L_global, f_min)`，所以真正的闭合条件是 `f_min ≥ U`。两个单调驱动是：

- **DIVE（focal）**：直接降 `U`；
- **CLIMB（min-f 层）**：直接抬 `f_min`。

两者都让 `U - f_min` 单调下降。v0.5 的 anytime 表正好是这句话的实验版。

**一个反直觉的推论**：focal 展开的若是 `f > f_min` 的节点，它在**降低 U 的同时不抬 f_min**；best-first 展开 `f_min` 节点，它在**抬 f_min 的同时不降 U**。所以"哪个更好"没有全局答案，只有"当前 gap 的哪一端更松"。

---

## 3. dynamic analysis：GAP-LEDGER

### 3.1 绑定族与 margin

对状态 `σ=(S,A,c)` 和当前上界 `U`，令

```text
L_loc(σ;U) = max( L0(σ), L_AV(σ;U-1), L_TH(σ;U), L_D(σ) )
```

按固定次序 tie-break（本轮用 `L_TH ≻ L_AV ≻ L_D ≻ L0`），定义

```text
β(σ) = argmax_f L_f(σ)
μ(σ) = L_loc(σ) - max_{f≠β(σ)} L_f(σ)      （单族时 μ=+∞）
slack(σ) = L_loc(σ) - L0(σ) ≥ 0
```

`β` 是"当前是谁在托底"，`μ` 是"第二名的差距"，`slack` 是"除 L0 之外的证书已经贡献了多少"。

### 3.2 headroom：一个零装箱测试的上界

固定窗口 `(a,b)`，令

```text
qmax(a) = max { q_i : i∈R, est_i ≥ a }
ub(a,b) = min( U-1, b + qmax(a) )
```

**引理（ub 可采纳）**：若窗口 `(a,b)` 在截止期 `H` 上不可行，则 `H ≤ ub(a,b)`。

**证明**：若强制集 `X_H(a,b)` 为空，装箱问题为空集，必然可行，矛盾。故存在 `i∈R` 满足 `est_i ≥ a` 且 `H - q_i ≤ b`，即 `H ≤ b + q_i ≤ b + qmax(a)`；又 `H ≤ U-1`。证毕。

定义

```text
η(σ) = max( 0, max_{(a,b)∈W(σ,U)} (ub(a,b)+1) - L0(σ) )
```

其中 `W(σ,U)` 是固定窗口族（与 `H` 无关，见产物区 §3）。

**引理（η 上界）**：

```text
L_TH(σ;U) ≤ L0(σ) + η(σ).
```

**证明**：对任意窗口，`H*(a,b)+1 ≤ ub(a,b)+1 ≤ L0+η`；对窗口取 max、再与 `L0` 取 max，仍不超过 `L0+η`。证毕。

**推论（零测试跳过）**：令

```text
η_eff(σ) = max( 0, η(σ) - slack(σ) ).
```

则 `L_loc` 因 THRESH 而增加的量不超过 `η_eff(σ)`。特别地，

```text
η_eff(σ) = 0  ⇒  跑 THRESH 不可能改变 L_loc(σ)。
```

**证明**：

```text
L_loc' = max(L_loc, L_TH) ≤ max(L_loc, L0+η)
       = L_loc + max(0, L0+η-L_loc)
       = L_loc + max(0, η-slack).
```

证毕。

这是本轮最实用的一个观察：**在跑任何一次装箱测试之前，就能知道 THRESH 最多能带来多少收益**。`η=0` 时直接跳过；`η_eff` 很小时把预算留给别的节点。

### 3.3 前沿 ledger 与确定性路由

维护

```text
f_min,  G_search = U - f_min,  G_cert = f_min - L_global
W_f = Σ_{v:β(v)=f} (U - f(v))          # 每个族的可攻击 slack
N_f = |{v:β(v)=f}|
```

路由函数 `ROUTE(ledger)` 是确定性的：

```text
if 存在 v∈Open 且 η_eff(v) ≥ 1:
    优先对 (U-f(v)) 最大的 K_cert 个节点跑 DERAND-THRESH
elif steps - last_progress ≥ W_U:
    CLIMB
else:
    DIVE
```

### 3.4 成本

`η` 只需要枚举 `O(n²)` 个窗口并做 `O(1)` 算术，**不需要装箱**；`β/μ` 需要 `L_TH` 的数值，只在 actually 跑证书时更新。因此 ledger 的边际成本远低于一次 `AVAIL` 测试。

---

## 4. derandomization：三类确定性替换

### D1 DERAND-WINDOW（本轮已实现）

把"遍历所有窗口、每个窗口在 `[L0,U-1]` 上二分"改成：

1. 按 `ub` 降序排序；
2. 维护当前最优 `best`；
3. 若 `ub ≤ best`，后面的窗口都不可能更好，直接停；
4. 否则在 `[max(L0,best+1), min(U-1,ub)]` 上二分。

**定理**：返回与全扫描相同的 `L_TH`。证明见产物区 §4.1。

### D2 DERAND-DIVE（本轮已证明，未实现）

随机优先级表调度：每步在就绪集中均匀随机选一个任务。设 `D` 是该分布，`M(π)` 是优先级序 `π` 的 makespan。MCE 逐个固定任务：

```text
π*_0 = ∅
π*_{t+1} = π*_t + argmin_{i∈Ready} E_D[ M | π*_t + i ]
```

**定理**：`M(π*) ≤ E_D[M]`。证明见产物区 §4.2。这把 v0.4 的 MCTS rollout 换成了一个**有支配性保证**的确定性构造。

### D3 DERAND-FOCAL / TIE（本轮已实现）

- `B_focal` 截断取 `(f,id)` 最小的 `B_focal` 个候选；它们仍落在 `Φ_ω` 内，所以 focal 精确性定理不受影响；
- 所有 tie-break 用规范键 `(f, Ĝ, id)`，其中 `id` 是确定的生成序号；
- 不用 bandit、不用随机数。

---

## 5. 算法范式：PARADIGM-AUTOMATON

四态：

| 状态 | 工作 | 选点规则 |
|---|---|---|
| `DIVE` | 降 `U` | `Φ_ω` 内按 `Ĝ` 最小 |
| `CLIMB` | 抬 `f_min` | 精确 `f=f_min` 层内按 `Ĝ` 最小（ω=0 focal） |
| `CERT` | 抬 `L` | 对 `η_eff≥1` 的前 `K_cert` 个节点跑 DERAND-THRESH |
| `MERGE` | 去重/支配 | 扫描支配表，清理被支配节点 |

`CLIMB` 不是朴素 best-first：它在 `f_min` 层内仍用 guide 破平。这样既不浪费 guide 信息，又保证每步移除一个 `f_min` 节点。

**Progress 定理**：连续 `W_U` 次扩展无进展（`U` 不降且 `f_min` 不升）后进入 `CLIMB`；`CLIMB` 只展开 `f_min` 层，该层有限，故最终要么 `U` 下降、要么 `f_min` 严格上升。这是终止/进展保证，不是多项式界。

**Safety 定理**：自动机只改"先展开谁"，不改任何剪枝条件；因此任意切换都保持 v0.5 的精确性。

---

## 6. 本轮要验证的命题

1. **`f_min` 单调**：代码中每步检查 `f_min` 不下降（一致性实现正确性的 sanity check）。
2. **η 上界**：16 个中段状态上 `gain ≤ headroom` 应为 16/16；`η=0` 时 `gain=0`。
3. **DERAND-WINDOW 精确性**：40 个根状态 + 16 个中段状态上，`full` 与 `derand` 的 `L_TH` 必须完全一致；装箱测试数应显著下降。
4. **自动机**：在简单实例上应"休眠"（与纯 focal 相同）；在困难实例上应不输，最好有节点收益。
5. **正确性**：所有变体返回同一 `U`；THRESH 必须满足 `L_TH ≤ OPT(σ)`，用独立状态 DFS 验证。

---

## 7. 预判的负结果

- 在 n≤10 的简单实例上，`L0+AVAIL(U-1)+focal+DOM` 已经很强，自动机可能**完全休眠**；
- 在 precedence-heavy 实例上，`qmax(a)` 很大，`η` 可能接近 `U-L0`，ledger 无法跳过任何证书；
- MCE dive 的精确 DP 在 n>15 时状态爆炸，只能用 pessimistic estimator，届时"支配性保证"会变弱；
- `η` 的收益只对 THRESH 成立，对 `L_D`/`L_AV` 需要各自的 headroom。

---

## 8. 一句话最大风险

**当前方案最大的风险是：自动机的节点收益集中在 12–14 个任务的随机 DAG 上（9 个实例里 1 个贡献了 129→60 的大部分），而 `η` 在 precedence-heavy 实例上可能因 `qmax` 很大而变得空洞；MCE dive 的 DP 成本也尚未验证。**
