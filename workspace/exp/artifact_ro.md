# 产物区 · v0.6：X-DUB/RO*

> **R**ollout-first **O**nline exact search  
> 中文名：推演优先的在线精确搜索  
> 状态：完整设计稿；45 个 n=8–10、m=2 实例上验证了 ROLLOUT 的 45/45 命中、总扩展 1226→994（−18.9%）、困难 17 例 854→632（−26.0%）、`t=0` 平均 gap 1.588→0.000；24/24 个 n≤9 实例由独立穷举 DFS 复核；PNS/null-window/beam 的负结果与 SCALE 的 Last-Δ 定理已记录。证明 DAG checker、m≥3、PSPLIB 留到下一轮。

---

## 0. 版本关系与本轮增量

v0.5「X-DUB/AG*」已经建立：

- `P|prec|Cmax` 的 `(任务,机器)` 动作空间与最优性覆盖；
- 一致 A* 层：`F(child)=max(F(parent),L_loc(child))`，`f=max(C,F)`，`h=f-C` 一致，不需要 reopening；
- 贪心焦点 `FOCAL-GREEDY`，guide 只排序、不剪枝；
- 证书泛化：`THRESH-CERT`、`CERT-INHERIT`、`CERT-REGION`、`DOM-GEN`；
- 证明 DAG 的 `INHERIT / THRESH-CORE / DOMINATED-BY` 规则。

v0.6 **不推翻** 上述任何结论。它只做四处增量：

1. **ROLLOUT-PV**：用"1 层前瞻 + 贪心 playout"的 rollout 替代 CP 贪心作为初始上界；返回一条 PV 和一个可独立检查的可行调度。附 **policy-improvement 定理**：rollout 不劣于基策略族中的任何一条。
2. **ONLINE-LST**：playout 的内层规则用 `LST = p_i+q_i 最大`，即"含自身的剩余关键路径"，也是带截止期的在线表调度；给出内层规则的消融。
3. **SCALE-CERT + Last-Δ**：把 FPTAS 的 scaling 拆成两个**方向**——round-up 只能造解，round-down 只能反驳；并证明**任何严格松弛都不能认证最后一单位**。这解释了 v0.5 的 THRESH 为什么在 precedence-heavy 实例上无效。
4. **CR-BOUND**：把 online 的 Graham 竞争比 `ρ=2-1/m` 转成一个免费、可检查的下界 `L_CR=ceil(U/ρ)`；实验上被 L0 支配，只作兜底。

关系：

```text
关闭 ROLLOUT/CR/SCALE  → v0.5 的 AG*（多一条 LST 规则）
只开 ROLLOUT            → 更好的 U0 与 anytime，剪枝不变
只开 SCALE/CR           → 多两个可采纳下界
全部打开                → v0.6 完整算法
```

搜索主体（`FOCAL/DOM/INHERIT/THRESH/证明 DAG`）完全保留。组合下界：

```text
L(σ) = max( L0(σ), L_D(σ), L_AV(σ;U-1), L_TH(σ), L_CR, L_SCALE(Δ) )
F(σ) = 路径上所有 L 的最大值
f(σ) = max( C(σ), F(σ) )
```

`L_CR` 与 `L_SCALE` 可关闭；关闭后逐字退回 v0.5。

---

## 1. 问题、符号与复用的旧结论

### 1.1 形式化问题

```text
P | prec | Cmax
```

给定任务集 `V={1,...,n}`、工时 `p_i∈Z_{≥1}`、优先约束 `E⊆V×V`（DAG）、同构机器数 `m`。调度由开始时间 `s_i` 和机器 `μ_i` 组成，满足：

```text
(i,j) ∈ E  ⇒  s_j ≥ s_i + p_i
μ_i = μ_j  ⇒  [s_i, s_i+p_i) 与 [s_j, s_j+p_j) 不重叠
```

目标 `Cmax=max_i(s_i+p_i)` 最小，最优值记 `OPT`。

### 1.2 符号表（v0.6 新增/重定义）

| 符号 | 含义 |
|---|---|
| `σ=(S,A,c)` | 状态：已调度集、机器可用时间（升序元组）、完成时间 |
| `R=V\S` | 未调度集 |
| `C(σ)=max_k A_k` | 状态已完成的 makespan |
| `OPT(σ)` | 从 `σ` 出发完成所有剩余任务的最小绝对 makespan |
| `lo_i(σ)` / `q_i(σ)` | 动态 head / tail |
| `L0(σ)` | `max(C, max_i(lo_i+p_i+q_i), ceil(P(R)/m))` |
| `L_D, L_AV, L_TH` | v0.4/v0.5 的对偶、AVAIL、阈值下界 |
| `L_CR` | `ceil(U_R/ρ)`，Graham 竞争比下界 |
| `L_SCALE(Δ)` | round-down 松弛证书给出的下界（可选） |
| `L(σ)` | `max(L0,L_D,L_AV,L_TH,L_CR,L_SCALE)` |
| `F(σ)` | 路径最大下界（v0.5） |
| `f(σ)` | `max(C(σ),F(σ))` |
| `Π` | 基策略族 `{CP, LST, LPT, MWKR}` |
| `U_Π(σ)` | `min_{π∈Π} Cmax(Greedy(σ,π))` |
| `V_π(σ,a)` | playout 值：先做动作 `a`，再按 `π` 完成的 makespan |
| `U_R^π(σ)` | 内层策略为 `π` 的 rollout makespan |
| `U_R(σ)` | `min_{π∈Π} U_R^π(σ)` |
| `ρ` | `2-1/m`（Graham 比） |
| `Δ` | scaling 粒度 |
| `p^↓(Δ), p^↑(Δ)` | 向下/向上取整的工时向量 |
| `PV` | rollout 返回的主变元（一条完整调度） |

### 1.3 复用的 v0.5 结论

以下直接继承，不再证明：

- **动作覆盖性**：动作 `(i,k)` 在 `t=max(A_k,max_{j∈pred(i)}c_j)` 开始；从根出发的某条动作序列可达到一个最优调度。
- **A* 一致性**：`F≤OPT`，`f(child)≥f(parent)`，`h=f-C` 一致；父证书对后代有效。
- **Focal 精确**：guide 只排序，剪枝只用 `f≥U`；无限预算下前沿耗尽即 `U=OPT`。
- **AVAIL/THRESH 可采纳**：见 v0.5 定理 1/3。
- **DOM-GEN 可采纳**：同 `S` 下 `σ⪯τ ⇒ OPT(σ)≤OPT(τ)`。
- **证明 DAG 规则**：`TERMINAL/PRUNED-DUAL/PACK-CORE-AVAIL/THRESH-CORE/INHERIT/DOMINATED-BY/EXACT/EXHAUSTED`。

v0.6 只新增初始上界、内层 playout 规则、两个可选下界和三个证明节点；动作空间与搜索剪枝不变。

---

## 2. 动机：三堵墙与一个重新表述

### 2.1 三堵墙（详见想法区 §1）

- **Null-window / MTD**：把搜索拆成 `H=U-1` 的判定，17 个困难实例总扩展 **3,354**，而 v0.5 是 **913**。原因是判定搜索丢掉了"未反驳状态的支配"这把 optimization 的刀。
- **PNS**：纯 AND 树的 `pn=Σ` 在 17 个实例上总扩展 **1,231,417**，约 913 的 1,348 倍。
- **Beam**：宽度 4、静态 `max(A)` 评估的上界平均超出 OPT **4.76**；宽度 16 仍差 **3.94**。而宽度 1、playout 评估的 rollout 平均超出 **0.00**。

### 2.2 重新表述：找解与证明分居

17 个困难实例上：

- `L0 < OPT` 的有 **17/17**，gap 1–6；
- CP 贪心 `U0=OPT` 的只有 **2/17**；
- 但 302 步的实例 `U0=OPT=46`，302 步全部用于反驳 45。

因此：

```text
找解：把 U0 降到 OPT        ← rollout 负责，成本 ~5 ms
证明：证明不存在 ≤ U-1 的完成 ← 精确搜索负责，成本指数
```

v0.5 的 focal 在"选点"上并不差（25 次扩展内 29/30 找到 OPT），差的是**起点**。RO 只换起点，把搜索从"边找边证"变成"先找后证"。

---

## 3. 博弈树层：ROLLOUT-PV

### 3.1 基策略与 playout 值

`Π={CP,LST,LPT,MWKR}`，其中（`est_i` 为当前状态下 `i` 的最早开始）：

```text
CP  : 选 q_i 最大的就绪任务
LST : 选 p_i + q_i 最大的就绪任务
LPT : 选 p_i 最大的就绪任务
MWKR: 选剩余后代总工时最大的就绪任务
```

四条规则都只依赖当前状态 `(S,A,c)`，因此是**马尔可夫的 list-scheduling 策略**。对状态 `σ`、动作 `a=(i,k)`、策略 `π`：

```text
σ·a            = 在机器 k 上以最早可行时间调度 i 的后继状态
Greedy(σ,π)    = 从 σ 出发按 π 生成的完整调度
V_π(σ,a)       = Cmax( Greedy(σ·a, π) )
```

### 3.2 ROLLOUT 算法

```text
ROLLOUT(σ, π):
1  σ' ← σ;  PV ← ∅
2  while R(σ') ≠ ∅:
3      A(σ') ← 所有就绪任务 × 所有机器
4      a* ← argmin_{a∈A(σ')} V_π(σ', a)        # 每个 a 跑一次 playout
5      把 a* 的最早可行调度提交到 σ';  PV ← PV ∪ {a*}
6  return Cmax(σ'), PV
```

`U_R^π(σ)=Cmax(σ')`，`U_R(σ)=min_{π∈Π} U_R^π(σ)`。这正是**宽度 1、评估函数为 playout 的 beam**；§10.7 的对比说明"评估质量"比"宽度"重要一个数量级。整个 rollout 是确定性的：tie-break 固定为任务索引、机器索引，不使用随机数。

### 3.3 定理 1（policy improvement）

**定理 1**：对任意 `π∈Π` 和任意状态 `σ`，

```text
U_R^π(σ) ≤ Cmax(Greedy(σ,π)).
```

因此 `U_R(σ) ≤ U_Π(σ) = min_{π∈Π} Cmax(Greedy(σ,π))`。

**证明**：设 `π` 从 `σ` 出发的第一个动作是 `a_0`。由策略的马尔可夫性，`π` 从 `σ·a_0` 出发的续成与原调度完全一致，故

```text
V_π(σ,a_0) = Cmax(Greedy(σ·a_0,π)) = Cmax(Greedy(σ,π)).
```

rollout 在第一步取 `min_{a∈A(σ)} V_π(σ,a)`，而 `a_0∈A(σ)`，所以

```text
U_R^π(σ) ≤ V_π(σ,a_0) = Cmax(Greedy(σ,π)).
```

对 `π` 取 min 得 `U_R(σ) ≤ U_Π(σ)`。证毕。

**推论 1.1（可行性）**：`U_R^π(σ)` 是一条合法完成的 makespan，故 `OPT(σ) ≤ U_R(σ)`。

**推论 1.2（Graham 继承）**：`U_R(σ) ≤ U_Π(σ) ≤ ρ·OPT(σ)`，`ρ=2-1/m`。

**备注**：定理 1 只保证"不劣于基策略"，不保证最优。实验上 45/45 命中 OPT，但这是经验事实，不是定理。

**推论 1.3（Bellman 误差界）**：设

```text
ε = max_{a∈A(σ)} | V_π(σ,a) - OPT(σ·a) |.
```

则 `|U_R^π(σ) - OPT(σ)| ≤ ε`。

**证明**：`min` 是 1-Lipschitz：

```text
| min_a V(a) - min_a OPT(σ·a) | ≤ max_a |V(a)-OPT(σ·a)| = ε.
```

而 Bellman 最优性给出 `min_{a∈A(σ)} OPT(σ·a) = OPT(σ)`。证毕。

这个推论把"rollout 好不好"归因到**单步 playout 的误差 ε**，而不是搜索宽度：宽度 B 不改变 ε，只改变常数；playout 的规则才改变 ε。这正好解释了 §10.7 的 beam 对比。

**推论 1.4（零搜索证书）**：若 `U_R(σ) = L(σ)` 对某个可靠下界 `L` 成立，则 `OPT(σ)=U_R(σ)`，且 `ROLLOUT-WITNESS(PV)` 单独就构成最优性证书，不需要展开任何节点。

**证明**：`L≤OPT≤U_R` 且 `L=U_R`，夹逼得 `OPT=U_R`。证毕。

### 3.4 PV 的作用

`PV` 是 rollout 实际提交的动作序列，也就是一条完整调度的"主变元"。它有三个用途：

1. **即时 anytime**：`t=0` 就返回 `PV` 和 `U_R`，不需要任何搜索；
2. **证明见证**：`ROLLOUT-WITNESS(PV)` 是可独立检查的可行调度；
3. **诊断**：若 `U_R>OPT`，说明 rollout 的评估在某个状态上选错了动作；可把该状态作为下一轮的特征研究对象。

v0.6 不把 PV 用于剪枝，也不把 PV 当作下界。

---

## 4. 在线层：ONLINE-LST 与 CR-BOUND

### 4.1 为什么是 LST

`CP` 只看 `q_i`（i 之后的最长路），会低估"i 本身很长"的任务；`LST` 看 `p_i+q_i`，即**经过 i 的最长剩余路径**。它仍然是纯在线的：每一步只用当前的 `est,q,A`，不预设未来。

45 个实例的内层消融（§10.4）：

```text
CP 32/45, LPT 35/45, MWKR 31/45, LST 42/45, min-of-4 45/45.
```

LST 不是"另一个 magic priority"：它是带截止期的表调度里"最晚开始时间最小"的等价形式（在固定 H 下，`lst_i=H-q_i-p_i`，最大化 `p_i+q_i` 即最小化 `lst_i`）。

### 4.2 定理 2（Graham 比与 CR 下界）

**定理 2**：对任意 list schedule（非延迟、最早开始），

```text
Cmax ≤ (2 - 1/m)·OPT.
```

因此对任意可行 `U`，`L_CR=ceil(U/ρ) ≤ OPT`，`ρ=2-1/m`。

**证明**：Graham 1969 的标准结果；这里只用到"同构机器 + 优先约束 + list schedule"三个假设。由 `U ≤ ρOPT` 得 `OPT ≥ U/ρ`；`OPT` 为整数，故 `OPT ≥ ceil(U/ρ)`。证毕。

**使用规则**：

```text
L_CR = ceil(U_R/ρ)
L    = max(L0, L_CR, ...)
```

`L_CR` 可采纳、可检查、零成本，但在 17 个实例上 **0/17** 超过 L0（平均低 12.2），所以默认只在 `L0` 失效的极端不平衡实例上启用。

---

## 5. FPTAS 层：SCALE-CERT 与 Last-Δ 定理

### 5.1 两个方向

对 `Δ≥1` 定义

```text
p^↓_i(Δ) = max(1, p_i - Δ)      （乐观松弛：任务变短）
p^↑_i(Δ) = p_i + Δ              （悲观收紧：任务变长）
```

注意它们不是"取整到网格"，而是**单调平移**；下面的方向性对任意 `p^↓≤p≤p^↑` 都成立。

**定理 3（SCALE 双向可靠性）**：

```text
(a) 若 p^↓ 在截止期 H 上不可行，则 p 在 H 上也不可行。   （round-down 反驳）
(b) 若 p^↑ 存在 makespan ≤ H 的调度，则 p 也存在。        （round-up 造解）
```

**证明**：

(a) `p^↓≤p`，故 `p` 的任意可行调度对 `p^↓` 也可行且 makespan 不增。若 `p` 在 `H` 上可行，则 `p^↓` 也可行，矛盾。

(b) `p^↑≥p`，同一调度在 `p` 上的 makespan 不超过在 `p^↑` 上的 makespan；后者 `≤H`，故前者 `≤H`。证毕。

**反方向不成立**（各给一个反例）：

- `p^↑` 在 `H` 上不可行 **不** 推出 `p` 不可行：把任务变长会让原本可行的实例不可行。
- `p^↓` 在 `H` 上可行 **不** 推出 `p` 可行：把任务变短会让原本不可行的实例可行。

因此实现里必须把方向写死；这是 FPTAS 式 scaling 在精确 B&B 里最容易犯的错。

### 5.2 定理 4（Last-Δ）

**定理 4**：设 `R` 是原问题的一个松弛，满足 `OPT(R) ≤ OPT`（例如 `p^↓`、丢约束、丢机器）。若 `R` 的某个可靠证书反驳了 `H=OPT-1`，则必有 `OPT(R)=OPT`。

**证明**：证书反驳 `H` 意味着 `OPT(R) ≥ H+1 = OPT`。结合 `OPT(R) ≤ OPT`，得 `OPT(R)=OPT`。证毕。

**推论 4.1**：任何**严格**松弛（`OPT(R)<OPT`）都不可能认证最后一单位。它只能反驳严格低于 `OPT` 的阈值，即只能"跳过早期的 rung"，不能闭合端局。

这解释了 v0.5 的 THRESH 负结果：THRESH 的窗口装箱也是一个松弛，若它在 `OPT-1` 上不可行，等价于说该松弛在 `OPT-1` 上恰好紧；precedence-heavy 实例的端局不在它的射程内。

### 5.3 实验：Δ=1 就已经掉了 4.3

17 个困难实例，`p^↓=max(1,p-Δ)`，用 AG 重算 `OPT(↓)`：

| Δ | `OPT(↓)=OPT` 的实例 | 平均 `OPT-OPT(↓)` |
|---:|---:|---:|
| 1 | 0/17 | 4.29 |
| 2 | 0/17 | 7.47 |
| 3 | 0/17 | 7.24 |
| 4 | 0/17 | 10.47 |

Δ=1 就把每个任务减 1，等于总工时减 `n`；`OPT` 平均掉 4.3。**0/17 保持最优**，与推论 4.1 一致：round-down 在端局上没有射程。

### 5.4 `L_SCALE` 的定位

`L_SCALE(Δ)` 只用于"早期 rung"：在 `H≪OPT` 时，round-down 松弛可能仍然不可行，从而一次性反驳一批阈值。它**不**用于 `H=U-1` 的端局；默认关闭，避免付出无用的装箱测试。

---

## 6. 主循环 X-DUB/RO*

```text
算法 X-DUB/RO*(G,p,m,B,Δ)
────────────────────────────────────────────────
1  (lo,q,L0) ← PRECOMPUTE(G,p,m)
2  for π∈Π: (U_π,PV_π) ← GREEDY(σ0,π)
3  U ← min_π U_π;  PV ← argmin_π
4  for π∈Π:
5      (U_R^π,PV_R^π) ← ROLLOUT(σ0,π)          # §3.2，四次独立
6  π* ← argmin_π U_R^π
7  if U_R^{π*} < U:  U ← U_R^{π*};  PV ← PV_R^{π*}
8  L ← max(L0, L_CR, L_SCALE(Δ))               # 后两者可关
9  if L ≥ U: return (U,PV,L,PROOF)
10 root ← NEW-NODE(σ0=(∅,0^m,⊥))
11 root.L ← L0;  root.F ← L0;  root.f ← max(C(σ0),L0)
12 Open ← {root};  DomTable ← {(S=∅):[(sort(A0),c0,root.id)]}
13 F_global ← L0;  t ← 0
14 while Open ≠ ∅ and t < B:
15     purge Open 中 f≥U 的节点
16     if Open=∅: break
17     f_min ← min_{v∈Open} f(v)
18     if f_min≥U: break
19     Φ ← {v∈Open : f(v) ≤ f_min+ω}
20     v ← argmin_{v∈Φ, |Φ|≤B_focal} U_Π(v)     # guide 只排序
21     t ← t+1
22     for each child w of v:
23         if w is complete:
24             U ← min(U,C(w));  continue
25         L_w ← L_LOC(w,U)                      # L0+AVAIL(U-1)+可选 THRESH
26         F_w ← max(v.F,L_w);  f_w ← max(C(w),F_w)
27         if f_w≥U: prune;  continue
28         if Cert(w,U-1): prune;  continue       # AVAIL/THRESH/ENERGETIC/CONFLICT
29         if DOMINATED(w):
30             U ← min(U,U_Π(w))                 # 可选：保留其贪心上界
31             record DOMINATED-BY(witness);  continue
32         insert w into Open;  update DomTable
33     if t mod T_scan = 0:
34         L_root ← THRESH(root,U)
35         F_global ← max(F_global,L_root)
36         for v∈Open: F(v)←max(F(v),F_global); f(v)←max(C(v),F(v))
37     L ← max(F_global, min_{v∈Open} f(v), L_CR, L_SCALE)
38 end while
39 if Open=∅ or L≥U:
40     PROOF ← BUILD-PROOF-DAG(root,U,PV)
41 return (U,L,PV,PROOF)
```

关键点：

- **第 4–7 行**是本轮唯一改变搜索轨迹的地方：`U0` 从 `U_Π` 变成 `U_R`。四次 rollout 都从根出发、互相独立；取最小。
- **第 20 行**的 guide 仍是 `U_Π`（4 条贪心），不是 rollout；rollout 太贵，只在根跑。
- **第 28 行**的 `Cert` 是 v0.5 的 AVAIL/THRESH 的扩展；可关闭。
- **第 37 行**的 `L_CR/L_SCALE` 可关闭；关闭后退回 v0.5 的下界。
- **第 40 行**的证明 DAG 新增 `ROLLOUT-WITNESS`、`SCALE-CERT`、`CR-BOUND`。

---

## 7. 正确性论证

### 7.1 定理 1（policy improvement）

已证于 §3.3。

### 7.2 定理 2（Graham / CR）

已证于 §4.2。

### 7.3 定理 3（SCALE 双向）

已证于 §5.1。

### 7.4 定理 4（Last-Δ）

已证于 §5.2。

### 7.5 定理 5（任意时刻区间）

**定理 5**：在 RO 运行的任意时刻，

```text
L ≤ OPT ≤ U.
```

**证明**：

- `U` 来自 `PV`（rollout 的合法调度）、贪心完成或完整状态，均为可行调度，故 `OPT≤U`。
- `L0` 可采纳（v0.5）；`L_CR` 由定理 2 可采纳；`L_SCALE` 由定理 3(a) 可采纳；`L_TH` 由 v0.5 定理 3 可采纳；前沿 `min f` 由 A* 一致性与前沿覆盖性给出 `≤OPT`。取 max 仍 `≤OPT`。证毕。

### 7.6 定理 6（终止即最优）

**定理 6**：若算法因 `Open=∅` 或 `L≥U` 终止，则 `U=OPT`。

**证明**：若存在 `Cmax<U` 的完成，由动作覆盖性和前沿覆盖性，它必须经过某个开节点 `v`，且 `f(v)≤Cmax<U`。这与 `Open=∅` 或 `min f≥U` 矛盾。结合 `U` 可行，`U=OPT`。证毕。

### 7.7 定理 7（ROLLOUT 不破坏精确性）

**定理 7**：把 `U0` 从任意可行值改成 `U_R`，不改变算法返回的 `OPT`。

**证明**：搜索的剪枝只用 `f≥U` 与可采纳证书；`U_R` 是可行上界（推论 1.1），故 `U0≥OPT`。v0.5 的定理 2/6 只要求初始 `U` 可行，不要求它最优。改变 `U0` 只改变展开顺序与剪枝时机，不改变可达解集合。证毕。

### 7.8 定理 8（证明 DAG 可靠）

**定理 8**：若 `CHECK(root)` 通过，则 `U=OPT`。

**证明**：对 DAG 拓扑归纳。v0.5 的节点规则已可靠；新增：

- `ROLLOUT-WITNESS(PV)`：checker 验证 `PV` 是一条合法完成（每任务一次、前驱、机器不重叠），且 `Cmax(PV)=U_R`。故 `OPT≤U_R`。
- `SCALE-CERT(down,H)`：checker 验证 `p^↓≤p`，在 `p^↓` 上重算证书并确认 `H` 不可行；由定理 3(a)，`OPT>H`。
- `SCALE-CERT(up,H)`：checker 验证 `p^↑≥p`，并验证附带调度在 `p^↑` 上 `≤H`；由定理 3(b)，`OPT≤H`。
- `CR-BOUND`：checker 验证 `ρ=2-1/m`、`PV` 可行、`ceil(U_R/ρ)≤L`；由定理 2，`L≤OPT`。

所有规则都只依赖局部证据；`ROLLOUT` 的内部评估、`focal` 的选择、`SCALE` 的方向选择都不在证明 DAG 里。结合 v0.5 的 `TERMINAL/PRUNED/PACK-CORE/INHERIT/DOMINATED/EXACT/EXHAUSTED`，根节点的证明闭合 `U=OPT`。证毕。

### 7.9 与 v0.5 的支配关系

```text
U0^RO = U_R ≤ U_Π = U0^v0.5       （定理 1）
L^RO  ≥ L^v0.5                    （多了 L_CR/L_SCALE，可关）
剪枝集合不变，U 更小 ⇒ 剪枝更强
```

因此 RO 的**剪枝集合**是 v0.5 的超集：任何被 v0.5 的 `f≥U` 剪掉的节点，在 RO 的更小 `U` 下也被剪掉。但实际搜索树不是逐点子树——`U` 下降轨迹不同会改变 focal 的候选集与展开顺序；实验中 7 个平局、0 个失败是经验观察，不是逐点支配定理（见风险 12）。

---

## 8. 复杂度分析

### 8.1 单次操作

- **预处理**：`O(n+|E|)`。
- **一条贪心**：`O(n(n+|E|))`（每步重算 head/tail；可增量化到 `O(n log n+|E|)`，本轮未做）。
- **一次 playout**：同上，`T_G=O(n(n+|E|))`。
- **一次 ROLLOUT**：`n` 步 × 至多 `n·m` 个动作 × `T_G`，即

```text
T_roll(π) = O(n · n m · T_G) = O(n³ m (n+|E|)).
```

- **四次 ROLLOUT**：`O(4 n³ m (n+|E|))`；`n=10,m=2` 时约 `8×10^4` 次基本操作，Python 实测 **5.4 ms/实例**。
- **focal 选择**：`O(|Open| + B_focal·T_G)`。
- **AVAIL/THRESH**：同 v0.5。
- **支配检查**：`O(|D_S|(n+m))`，受 `K_dom` 限制。

### 8.2 总复杂度

```text
时间: O( 4 n³ m (n+|E|) + N·(T_win + T_AVAIL + T_G)
         + N·K_dom·(n+m) + T_TH(root) )
空间: O( N(n+m) + Σ_S |D_S|(n+m) + N_proof )
```

- `N` 是物化节点数；最坏仍指数（`N=O((m·n)^n)`），v0.6 不改变最坏界。
- rollout 是**根节点一次**的多项式预处理；当 `N≥20` 时它相对于搜索可忽略。
- 当 `n` 很大时 `T_roll=O(n⁴m)` 可能不可忽略；缓解：只跑 LST 一条内层策略（成本 1/4）、或按 `B_actions` 采样动作、或只在 `U_Π-L0 ≥ 2` 时启用。

### 8.3 成本控制

- rollout 只在根跑，搜索内部只用 4 条贪心 guide；
- 若 `U_Π = L0`，直接跳过 rollout（已经最优）；
- `Cert` 的 energetic/conflict 只在 `AVAIL` 失败且深度 ≤ `D_cert` 时跑；
- `L_SCALE` 默认关闭；
- `K_dom` 控制支配表内存。

---

## 9. 证明 DAG 与 checker

### 9.1 新增节点类型

```text
ROLLOUT-WITNESS(PV, U_R)
SCALE-CERT(Δ, dir, H, evidence)
CR-BOUND(ρ, U_R, L)
```

### 9.2 checker 规则

```text
CHECK-NODE(v):
1  if v in memo: return memo[v]
2  case v.type:
3    ROLLOUT-WITNESS:
4        验证 PV 中每个任务恰好一次；
5        验证前驱约束与机器不重叠；
6        验证 Cmax(PV)=U_R；
7        验证 U_R ≥ U（若该节点用于证明 U 可行）
8    SCALE-CERT(down):
9        验证 p^↓_i ≤ p_i 且 p^↓_i ≥ 1；
10       在 p^↓ 上重算所声称的证书，验证 H 不可行；
11       由定理 3(a) 得 OPT>H
12   SCALE-CERT(up):
13       验证 p^↑_i ≥ p_i；
14       验证附带调度在 p^↑ 上合法且 Cmax≤H；
15       由定理 3(b) 得 OPT≤H
16   CR-BOUND:
17       验证 m 台同构机器与优先约束（全局假设）；
18       验证附带调度合法且 Cmax=U_R；
19       验证 ceil(U_R/(2-1/m)) ≤ L；
20       由定理 2 得 L≤OPT
21   TERMINAL/PRUNED-DUAL/PACK-CORE-AVAIL/THRESH-CORE/
22   INHERIT/DOMINATED-BY/EXACT/EXHAUSTED:
23       按 v0.5 规则
24   else: reject
25   memo[v] ← true; return true
```

### 9.3 独立性

- `PV` 由 checker 重新验证，不信任 rollout 的评估；
- `p^↓/p^↑` 由 checker 重算；
- `Cert` 的窗口、强制集、容量由 checker 重算；
- `L_CR` 的 `ρ` 只依赖 `m`；
- focal、guide、rollout 的内部选择都不在证明 DAG 里；
- 递归栈检测环；严格支配是偏序。

---

## 10. 实验

### 10.1 设置

- 随机 DAG：任务按索引拓扑排序；`i<j` 以概率 `ep` 加边；`p_i` 均匀取 `1..pmax`；`m=2`。
- 池子：
  - **hard17**：从 500 个随机实例中筛出 AG 扩展数 ≥12 且已证完（`open=0`）的 17 个；`n=9–10`。
  - **broad28**：90 个随机实例中所有在预算内证完的 28 个；`n=8–10`。
  - **fresh28**：另取 120 个随机实例，只统计"rollout 命中率"，不做搜索对比。
- 搜索：动作 `(i,k)`，最早开始，机器结果去重；`L0+AVAIL(U-1)`；`ω=2`，`B_focal=32`，`K_dom=60`；`inherit=True`；未启用对偶与 THRESH（隔离本轮变量）。
- 基线：`U0=min` 四条贪心（CP/LST/LPT/MWKR），guide 同四条；这是"v0.5 + LST"的强基线。
- RO：`U0=min` 四次 rollout（内层分别为 CP/LST/LPT/MWKR），其余完全相同。
- 精确性：24 个 `n≤9` 实例由独立穷举 DFS 复核（无下界、无支配、无 rollout），24/24 与搜索一致；`n=10` 由池子构造时的前沿耗尽（`open=0`）确认；所有变体返回同一 `OPT`。
- 时间：纯 Python，单线程，单次测量，仅作相对 sanity check。

### 10.2 主结果：节点数

| 池子 | 基线 | RO | 降幅 | 胜/平/负 | rollout 命中 OPT |
|---|---:|---:|---:|---:|---:|
| hard17 | 854 | **632** | **−26.0%** | 10 / 7 / 0 | 17/17 |
| broad28 | 372 | **362** | **−2.7%** | 5 / 23 / 0 | 28/28 |
| 合并 45 | 1226 | **994** | **−18.9%** | 15 / 30 / 0 | 45/45 |

- hard17 的 302 步实例两边都是 302（纯证明，rollout 不改变它）；132→1、32→1、12→1、11→1、5→1、14→1、12→1 来自"U0 直接等于 OPT，根一步闭合"。
- broad28 的收益小，因为 19/28 的基线上界本来就等于 OPT；rollout 在这些实例上是纯开销，但不改变节点数（0 失败）。
- 合并降幅 −18.9%，主要来自 hard17 的 7 个"1 步闭合"。

### 10.3 Anytime：t=0 的 gap

hard17 上，按扩展预算截取的平均剩余 gap（`U-OPT`）：

| 预算 | 基线 | RO |
|---:|---:|---:|
| 0 | 1.588 | **0.000** |
| 1 | 1.588 | **0.000** |
| 2 | 1.176 | **0.000** |
| 5 | 0.765 | **0.000** |
| 10 | 0.235 | **0.000** |
| 20 | 0.235 | **0.000** |

broad28 上，基线在 0/1/2 步是 `0.321/0.321/0.143`，RO 全为 `0.000`；第 5 步起两者都为 0。

**解读**：RO 的 anytime 优势是**结构性**的：它在任何搜索之前就返回 OPT，搜索只负责证书。这不是"更快地找到 OPT"，而是"找解与证明解耦"。

### 10.4 内层策略消融

45 个实例（hard17+broad28），只改 playout 的内层规则：

| 内层规则 | 命中 OPT | 平均超出 | 45 次 rollout 总时间 |
|---|---:|---:|---:|
| CP | 32/45 | 0.422 | 0.054 s |
| LPT | 35/45 | 0.600 | 0.057 s |
| MWKR | 31/45 | 0.467 | 0.064 s |
| **LST** | **42/45** | **0.067** | 0.057 s |
| **min-of-4** | **45/45** | **0.000** | 0.241 s |

- LST 单条就比 CP 多命中 10 个实例，平均超出从 0.422 降到 0.067。
- min-of-4 是四次独立 rollout 取最小，成本 4×（约 5.4 ms/实例），命中 45/45。
- 这说明 **online 的"看 `p_i+q_i`"是 playout 质量的关键**；portfolio 只是把剩下的 3 个补上。

### 10.5 未筛选的新样本

另取 120 个随机实例（同样 n=8–10、m=2，未按难度筛选），其中 28 个在 AG 预算内证完，统计这 28 个：

```text
min-of-4 rollout 命中 OPT：27/28（96.4%）
平均超出：0.036
本节只统计命中率；rollout 的绝对时间随实例密度上升，未单独计时。
```

这用来抵消"45/45 是筛选出来的"的质疑；命中率仍高，但不是 100%。

### 10.6 Scaling / Last-Δ

见 §5.3 表：Δ=1..4 下 `OPT(↓)=OPT` 均为 **0/17**，平均掉 4.29/7.47/7.24/10.47。结论：round-down 只能反驳严格低于 OPT 的阈值，不能认证 `OPT-1`。

### 10.7 负结果（本轮真正花时间的部分）

| 方法 | 指标 | 数值 |
|---|---|---:|
| v0.5 AG（CP 初始上界） | 17 例总扩展 | 913 |
| Null-window / MTD（DFS+refutation memo+fail-DOM） | 17 例总扩展 | 3,354（3.7×） |
| PNS（pn=Σ，无图级 transposition；只做 `H=OPT-1` 的反驳） | 17 例总扩展 | 1,231,417（≈1,348×） |
| Beam B=2 / 4 / 8 / 16（静态 `max(A)` 评估） | 17 例 UB 平均超出 OPT | 5.00 / 4.76 / 4.24 / 3.94 |
| ROLLOUT（B=1，playout 评估） | 17 例 UB 平均超出 OPT | **0.00** |
| Energetic 区间证书 | 17 例节点数 | 854→818（−4.2%） |
| Conflict-graph（m=2 奇环）证书 | 17 例节点数 | 854→847（−0.8%） |
| CR-BOUND | 优于 L0 的实例 | 0/17（平均低 12.2） |

**解读**：

- 在我们的实现里，PNS/null-window 的失败主要不是常数，而是结构：判定搜索丢掉 optimization 支配；纯 AND 的 `pn=Σ` 在高分支下爆炸。
- beam 的失败说明"宽度"不是瓶颈；**评估函数**才是。B=1 + playout 完胜 B=16 + 静态评估。
- energetic/conflict 在 17 例上只在 `U` 已降到 `OPT` 附近时才偶尔触发；302/60/45 这三个真正的端局上都没有触发。
- CR 下界被 L0 支配；保留它是因为它零成本、可检查，且在极端不平衡实例上可能有用。

### 10.8 复现

- `exp/exp_ro.py`：`rollout`、`search`、池子构造；
- `exp/exp_final.py`：45 例主实验，输出 `exp/final.json`；
- `exp/proto_pns.py`、`exp/proto_mtd.py`、`exp/proto_dl.py`：PNS、null-window、deadline-ladder 的负结果；
- `exp/proto_cert.py`：energetic / conflict-graph 证书；
- `exp/results_ro.json`、`exp/negatives.json`：数值汇总。

随机种子固定：hard17 用 seed 77，broad28 用 seed 2024，fresh28 用 seed 999。所有时间均为纯 Python 单线程单次测量。

### 10.9 本轮不声称

- 不声称 rollout 在 n≥20、m≥3 或 PSPLIB 上仍能命中 OPT；45/45 是 n≤10 的机制验证。
- 不声称节点数优势在 precedence-heavy 大实例上成立；302 步的反例已经说明端局不受益。
- 不声称 Last-Δ 之外还有新的通用下界；`L_CR` 被 L0 支配，`L_SCALE` 默认关闭。
- 不声称证明 DAG checker 已经实现对拍；本轮只给出规则与可靠性证明。
- 不声称 rollout 是"学习"；它是确定性的、可检查的 policy improvement，v0.4 的 bandit 负结果仍然成立。

---

## 11. 已知风险

1. **Rollout 的近最优性是经验事实，不是定理**。定理 1 只保证 `U_R≤U_Π≤ρOPT`；在 n 更大、DAG 更密、`p_i` 分布更偏的实例上，playout 可能系统性低估长尾任务，`U_R` 可能远离 OPT。
2. **Rollout 成本 `O(n³m|Π|(n+|E|))`**。`n=10` 时约 5 ms；`n=100` 时可能到秒级。缓解：只跑 LST 一条内层、按 `B_actions` 采样动作、或 `U_Π=L0` 时跳过。
3. **端局完全没有改善**。302 步的实例仍是 302 步；rollout 只把"找解"拿掉，没有动"最后一单位"的 refutation。这是本轮最大的未解问题。
4. **Last-Δ 定理封死了 scaling 的端局路线**。任何严格松弛（round-down、THRESH、丢约束）都不能认证 `OPT-1`；不要期待用 FPTAS 式舍入做出精确算法的最后一步。
5. **CR 下界被 L0 支配**。0/17 优于 L0；它只是兜底，不是主卖点。
6. **45/45 有选择偏差**。hard17 按 AG 难度筛、broad28 按"预算内证完"筛；fresh28 的 27/28 更可信，但样本仍小。
7. **m=2、n≤10**。没有 m≥3、没有 PSPLIB、没有 n≥20 的 anytime 曲线；rollout 在 m≥3 时的动作空间是 `n·m`，成本线性增，但 playout 的机器选择策略未验证。
8. **证明 DAG checker 未实现**。`ROLLOUT-WITNESS/SCALE-CERT/CR-BOUND` 只有规则，没有独立对拍；支配方向、DAG 共享、环检测都需要工程验证。
9. **实验是纯 Python 单次测量**。时间只用于相对比较，不是 benchmark；没有重复实验与置信区间。
10. **Rollout 的 tie-break 是固定的**（任务索引、机器索引）。不同 tie-break 可能改变命中率；本轮没有做敏感性分析。
11. **4 条内层策略的 portfolio 是在同一族实例上选的**。fresh28 只统计了 min-of-4 的命中率（27/28），没有单独复测 LST；"min-of-4"的 45/45 仍有过拟合风险。
12. **搜索的 `U` 下降轨迹会改变 focal 的候选集**。RO 的剪枝集合是 v0.5 的超集（更小的 `U` 只会多剪），但实际搜索树不是逐点子树；实验中 7 个平局、0 个失败是经验观察，不是逐点支配定理。
13. **没有跨实例学习**。ROLLOUT 是确定性的、可检查的，但它不是"学出来的"；v0.4 的 bandit 负结果仍然成立。
14. **最坏情况没有改善**。B&B 仍指数；ROLLOUT 是多项式预处理，不改变 NP-hard 的最坏界。

---

## 12. 一句话最大风险

**ROLLOUT 把 n≤10 随机 DAG 的"找解"压到零搜索、把 anytime 的 t=0 gap 打到 0，却完全没有动最后的 refutation（302 步的实例仍是 302 步）；而它的 O(n³m|Π|(n+|E|)) 成本，在"基线上界本来就等于 OPT"的大实例上纯属开销——本轮收益集中在中小时延、基线上界差 1–8 的实例，真正的 NP-hard 端局仍在原地。**
