# 玄 · 设计一个新的算法

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 想法区 · 第 3 轮（承接 v8.8 SAGE-ALC）：把「指数级」压进一个可测的参数 k

**灵感词**：parameterized algorithm / total correctness / complexity analysis  
**起点**：v8.8 SAGE-ALC 在 252 例上做到 252/252 认证、$Q=0$、LP$_{\rm CHD}=0$、YES 节点 $=0$、9.62 s。它把 APEX 的 105 次 CHD 全部消掉，但代价写在上一轮的最后一句：LP-BRANCH 最坏是 $\prod_i |D_i(h)|$ 个叶子，`nodecap=96`、`depthcap=24` 只是经验阀门；一旦新语料把阀门顶开，$Q=0$ 和墙钟优势会一起消失。本轮不打算再找一个更快的 oracle，而是想把这句话变成一个**参数化定理**：先找到真正控制指数的参数，再给出全正确性（终止 + 可靠 + 完备）的论证，最后用复杂度分析和 252 例实验说明这个参数在当前语料上有多小。

## 一、先看数据：58 个 NO 并没有用满 96 个节点

上一轮把 105 次查询拆成 58 个 NO、46 个 YES 和 1 个尾部。本轮我把这 58 个 NO 在 $h=\mathrm{OPT}-1$ 上重新跑了一遍完整搜索，得到的分支统计非常不「指数」：

| 证明高度 $k$ | 实例数 | 节点数/例 | 叶子数/例 | 读法 |
|---:|---:|---:|---:|---|
| 0 | 194 | 1 | 1 | 根 LP 直接不可行，单张 Farkas 证书 |
| 1 | 50 | 3 | 2 | 根节点切一刀，两个叶子都不可行 |
| 2 | 7 | 5 | 3 | 一侧再切一刀 |
| 4 | 1 | 9 | 5 | 最深的一条「毛毛虫」 |

58 个 $g=1$ 的 NO 证明合计只有 194 个 LP 节点、126 张叶子证书；最深一例 9 个节点，离 `nodecap=96` 很远。换句话说，SAGE 的指数上界是真的，但**这批实例的证明树高度 $k$ 最大只有 4**。如果指数真的由 $k$ 控制，那么最坏情况 $2^{k+1}-1$ 在这一批上最多是 31 个节点，实际最大 9 个。这个观察就是本轮的起点。

## 二、三个灵感词分别落在哪一层

- **parameterized algorithm**：不是把 $n$、$T$、$\delta$ 当参数，而是把「证明树高度 $k$」当参数。先做核化：单点域（$|D_i(h)|=1$）的任务永不分支，零松弛关键路径上的任务自动是单点域；搜索只在一组自由任务上切分。然后做有界搜索：`Search(k)` 只允许高度 $\le k$ 的证明，找到就返回，找不到就报告 UNKNOWN。参数化算法要回答的不是「能不能多项式」，而是「$f(k)\cdot \mathrm{poly}$ 里的 $k$ 是什么、有多大」。
- **total correctness**：SAGE 只证了「每个被接受的证明是可靠的」（soundness），没有证「搜索一定终止并给出答案」（completeness/termination）。本轮补三件事：第一，定义势函数 $\mu(F)=\sum_i |D_i(h,F)|$，证明每次非平凡切分都严格减小 $\mu$，所以完整搜索一定终止；第二，证明叶子规则和分支规则覆盖了所有调度，所以完整搜索是完备的；第三，做一个**总轨迹证书**，把初始上下界、每一次 probe、最终 NO($v-1$) 和 $C_{\max}=v$ 的调度一起重放，而不是只审计最后一张 NO 树。
- **complexity analysis**：把一次 probe 的代价写成 $O(2^k(L+C))$，其中 $L$ 是一次 SDLP 求解、$C$ 是一次证书 LP；把外层写成 $O(2^k\log\Delta(L+C))$；把最坏情况写成 $k\le \mu(\varnothing)\le n(T+1)$；再用 252 例测出 $k$ 的真实分布。复杂度分析在这里不是装饰，它直接解释了为什么 NO 侧可以完整搜索，而 YES 侧不能。

## 三、第一次试错：把「分数支撑 $\delta$」当参数，NO 反而更慢

最自然的参数是根 LP 的分数变量数 $\delta$。工作区里已经有 `exp/v8n/core.py` 的 DCA 原型：它先求根 LP，取分数支撑 $S$，枚举 $S$ 中任务的开始时刻，把剩余任务留给 LP。这个思路听起来很参数化：$|S|$ 小，枚举就小。

实测不是这样。$h=\mathrm{OPT}-1$ 上，stress 的根 LP 分数支撑平均 7.31、最大 13；base 最大 11，pert 最大 11。DCA 在 58 个 $g=1$ 的 NO 上用了 **1586 个 LP 节点、最大 56 个/例、13.41 s**；同一批实例，SAGE 风格的完整分支只用 **194 个节点**。DCA 的 `core_sizes` 常见是 6–10，但每个 core 里的任务有多个开始时刻，组合数很快膨胀；分数支撑描述的是「LP 顶点有多少个分数坐标」，不是「整数冲突需要切几刀」。结论：**$\delta$ 不是好参数，它高估了整数侧的证明复杂度。**

## 四、第二次试错：域熵和核大小也都太松

第二个候选是域熵
\[
k_{\rm ent}=\sum_{i:|D_i|>1}\log_2|D_i(h)|.
\]
它在 base 上最大 89.9，stress 上最大 39.3；即使把单点域和零松弛任务全部核化掉，58 个 $g=1$ 的 NO 里仍有 57 个的自由任务数 $n_f=15$（另一个是 9）。$n_f=15$ 意味着最坏 $2^{15}$ 个叶子，和实际 3–9 个节点差了两个数量级。原因是 LP 在每一层都在剪枝：绝大多数域组合在根或第一层就被 Farkas 证书排除了。结论：**域熵和核大小是「搜索空间的体积」，不是「证明的深度」；它们都不是好参数。**

## 五、第三次成功：$k$ = 证明树高度，NO 浅、YES 深

把证明树的高度 $k$ 作为参数后，252 例的 $h=\mathrm{OPT}-1$（NO）分布是：

```text
k=0: 194 例    k=1: 50 例    k=2: 7 例    k=4: 1 例
```

而 $h=\mathrm{OPT}$（YES）的分布是另一条曲线：

```text
k=0: 55 例   k=1: 44 例   k=2: 54 例   k=3: 30 例
k=4: 23 例   k=5: 18 例   ...           k=29: 1 例
```

这不是「同一个参数在两边都小」，而是一个**不对称性**：

> **NO 证明只需要在 LP 上制造不可行，切一两刀就够；YES 构造需要在 LP 上把分数解变成整数调度，可能要走很深。SAGE 的经验成功，本质上是因为它把 LP-BRANCH 用在了 NO 侧、把 GA 用在了 YES 侧；一个统一的深度参数是错的。**

这也是本轮算法设计的核心：PACT 不再用一个深度上限去卡所有 probe，而是把 NO 侧做成参数化完整搜索，把 YES 侧继续交给 GA/完整搜索的混合；同时用总轨迹证书把整条 bracket 路径固定下来。

## 六、PACT-ALC：参数化证书树 + 全正确性 + 总轨迹

本轮算法叫 **PACT-ALC**（Parameterized Certificate Trees with ALC），是 v8.8 SAGE-ALC 的子类，保留 bracket、LP pin、LP 舍入、LNS、STAB 和 GA，新增：

1. **PACT-SEARCH**：三值、高度参数化的固定 $h$ 判定器
   \[
   \mathrm{Search}(h,d)\in\{\mathrm{NO}(\pi),\mathrm{YES}(s,m),\mathrm{UNKNOWN}\}.
   \]
   每个节点先解 SDLP：不可行 → Farkas 叶子；整数 → `check_schedule` 的 YES；分数 → 按策略切一刀，递归到 $d-1$。只有两个子节点都是 NO 才返回 NO；一个 UNKNOWN 会让父节点 UNKNOWN。这样「洞」是局部的，不会像 SAGE 的 `depthcap` 那样一刀砍掉整个兄弟分支。
2. **核化**：$|D_i(h)|=1$ 的任务和零松弛关键路径任务不参与分支；搜索只在 $n_f$ 个自由任务上切。核化是可靠的：零松弛任务满足 $est_i+p_i+q_i=h$，任何 $C_{\max}\le h$ 的调度都有 $s_i=est_i$；单点域更直接。
3. **完整模式**：把 $d$ 设为 $\infty$，用势函数 $\mu(F)$ 保证终止；这就是全正确性的搜索侧。完整模式在 252 例上只用 450 个搜索 LP + 138 个证书 LP，10.59 s，$Q=0$，总审计 252/252。
4. **快速模式（closing）**：bracketing probe 仍用 SAGE 的 caps + GA，只有 $ub-lb=1$ 的 closing probe 用完整搜索。它在 252 例上 11.43 s、总 LP 852（和 SAGE 完全一样，只是从 BB 重新分配到了 complete），总审计 252/252，$Q=0$。
5. **TOTAL-TRACE**：一个新的总证书对象，重放初始 LB/UB、每次 probe 的 NO 证明或 YES 调度、最终 NO($v-1$) 和 $C_{\max}=v$ 的调度；它不信任 `certified` 标志，只信 `audit_rdf` 和 `check_schedule`。

复杂度上，一次高度为 $k$ 的完整搜索最多 $2^{k+1}-1$ 个节点，时间 $O(2^k(L+C))$；外层最多 $O(\log\Delta)$ 次 probe，总计 $O(2^k\log\Delta(L+C))$。最坏情况 $k\le n(T+1)$，所以它不是多项式算法；但在 252 例上，NO 侧 $k\le4$，实际最大 9 个节点，参数化上界是 31，证明这个指数在当前语料上被 $k$ 压住了。

## 七、当前方案最大的风险

**$k\le4$ 只是这 252 例的经验事实：如果新语料上 NO 证明高度变大，完整搜索会指数爆炸；而退回 SAGE 的 caps 又会把 $Q=0$ 和总证书一起丢掉——所以 PACT 的全正确性和它的性能保证，仍然绑在同一个未经证明的小参数上。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 产物区 · v8.9 PACT-ALC：参数化证书树、全正确性与总轨迹

## 0. 本轮产物与一句话结论

**PACT-ALC**（Parameterized Certificate Trees with ALC）是 v8.8 SAGE-ALC 的子类：保留 APEX 的 bracket、LP pin、LP 舍入、LNS、STAB 和 GENETIC-UB，新增

1. **PACT-SEARCH**：固定 $h$ 的三值、高度参数化判定器
   \[
   \mathrm{Search}(h,d)\in\{\mathrm{NO}(\pi),\mathrm{YES}(s,m),\mathrm{UNKNOWN}\}.
   \]
   只有两个子节点都返回 NO 才生成一个 NO 节点；一个 UNKNOWN 会让父节点 UNKNOWN，但不会像 SAGE 的 `depthcap` 那样直接砍掉兄弟分支。洞是局部的。
2. **KERNEL-1**：单点域任务和零松弛关键路径任务不参与分支；搜索只在自由任务集 $K=\{i:|D_i(h)|>1\}$ 上切分。零松弛规则是可靠的：$est_i+p_i+q_i=h$ 时任何 $C_{\max}\le h$ 的调度都满足 $s_i=est_i$。
3. **COMPLETE 模式**：令 $d=\infty$，用势函数 $\mu(F)=\sum_i|D_i(h,F)|$ 保证终止。它是全正确性的搜索侧。
4. **TOTAL-TRACE**：一个总证书，重放初始 LB/UB、每次 probe 的 NO 证明或 YES 调度、最终 $\mathrm{NO}(v-1)$ 与 $C_{\max}=v$ 的调度；检查器不信任生成器的 `certified` 标志。

在 252 例上：

- **PACT-C（complete，默认）**：252/252 认证，$Q=0$，273 次 pin LP + 450 次搜索 LP + 138 次证书 LP，总审计 252/252，10.59 s。
- **PACT-F（closing，快速）**：252/252 认证，$Q=0$，总 LP 852（与 SAGE 完全相同，只是从 BB 重新分配到 complete），总审计 252/252，11.43 s。
- **SAGE v8.8（同 runner 复跑）**：252/252 认证，$Q=0$，442 次 BB LP + 137 次证书 LP，11.62 s，但没有总轨迹审计。
- **参数**：58 个 $g=1$ 的 NO 证明高度分布为 $50\times k=1$、$7\times k=2$、$1\times k=4$；252 个 NO probe 中 194 个在 $k=0$ 就由根 LP 的 Farkas 证书闭合。YES 侧的高度重尾，最大 $k=29$，这正是 GA 仍然必要的原因。

结论：PACT 把 SAGE 的「capped 分支」升级为「按证书高度 $k$ 参数化的完整搜索」，并在 252 例上给出了 252 张可重放的总证书；但它没有把 $k$ 变成定理，$k\le4$ 仍然只是当前语料的经验事实。

---

## 1. 产物清单

| 路径 | 内容 |
|---|---|
| `exp/v8o/pact.py` | PACT-ALC 实现：`pact_decide`、`TotalTrace`、`PACT(SAGE)`、`run_pact` |
| `exp/v8o/bench_pact.py` | 252 例主实验与 8 组消融 |
| `exp/v8o/bench_pact_complete.json` | PACT-C 原始结果，252 行 |
| `exp/v8o/bench_pact_closing.json` | PACT-F（closing）原始结果 |
| `exp/v8o/bench_pact_single3.json` | 单次深度 3 + GA + complete 的结果 |
| `exp/v8o/bench_pact_single1.json` | 单次深度 1 + GA + complete 的结果 |
| `exp/v8o/bench_pact_d1.json` | 迭代加深到 1 的结果 |
| `exp/v8o/bench_pact_d0.json` | 只允许 $k=0$ 的结果 |
| `exp/v8o/bench_pact_no_complete.json` | 关闭 complete fallback、保留 CHD 的结果 |
| `exp/v8o/bench_pact_no_ga.json` | 关闭 GA、complete 负责所有 YES 的结果 |
| `exp/v8o/pact_depth.json` | 252 例在 $h=\mathrm{OPT}-1$ 与 $h=\mathrm{OPT}$ 上的完整搜索参数（504 行） |
| `exp/v8o/param_rows.json` | 252 例在 $h=\mathrm{OPT}-1$ 上的域、分数支撑、自由任务数诊断 |
| `exp/v8i/sage.py` | v8.8 SAGE 基类；PACT 直接继承 |
| `exp/v8i/bench_sage_full.json` | SAGE 基线（本轮同 runner 复跑） |
| `exp/v60/sdecc.py` | `SDLP`，固定 $h$ 的 SD 线性规划 |
| `exp/v60/cert.py` | `integer_certificate`、`verify`，叶子 Farkas 证书 |
| `exp/v8a/rdf.py` | `check_schedule` 与 CHD/RDF 接口 |

---

## 2. 与 v8.8 SAGE-ALC 的版本关系

| 层 | v8.8 SAGE-ALC | v8.9 PACT-ALC | 关系 |
|---|---|---|---|
| 初始 bracket | LP pin + chip bound + LP 舍入 + LNS | 原样继承 | 不变 |
| 下界 | LP pin；NO 由 LP-BRANCH 给 | LP pin + PACT-SEARCH | 新增高度参数化 |
| 上界 | LP 舍入 + LNS + CHD YES | 继承 + GENETIC-UB | 不变 |
| NO 搜索 | 单次 DFS，`nodecap=96`、`depthcap=24` | `Search(h,d)`，洞局部化，完整模式无 cap | 语义升级 |
| 证明代数 | 判断集合 + subsumption | STAB 原样复用 | 不变 |
| 最终闭合 | `MEET`，NO($v-1$) 来自 BranchProof | `MEET`，NO($v-1$) 来自 PACT 树 | 不变 |
| 审计 | 只审计最后一张 NO 树 | `TotalTrace` 重放整条 bracket | 新增 |
| fallback | CHD | CHD，仍保留 | 不变 |

实现上 `PACT` 只覆盖三处：

- `_probe(h)`：先做参数化搜索，再 GA，再完整搜索，最后 CHD；
- `optimize()`：沿用 APEX/SAGE 的 bracket，但记录每一步到 `self.steps`；
- `_build_total()`：在最终 `lb=ub` 后构造 `TotalTrace` 并审计。

其余 `initial_bounds`、`_decide`、`_absorb`、`_record`、`_result`、`_final_proof` 全部继承。

---

## 3. 问题、符号与判断

### 3.1 实例与调度

一个实例为
\[
I=(J,M,E,p,q,\mathrm{elig}),
\]
其中 $J$ 是任务集，$|J|=n$；$M$ 是机器集，$|M|=m$；$E\subseteq J\times J$ 是先后约束；$p_i$ 是加工时间；$q_i$ 是尾延迟；$\mathrm{elig}_i\subseteq M$ 是允许机器集。调度 $s:J\to\mathbb Z_{\ge0}$ 可行当且仅当：

1. 每个 $s_i$ 落在 $\mathrm{elig}_i$ 对应的机器可用时间上；
2. 对每条 $i\to j$，$s_j\ge s_i+p_i$；
3. 每台机器上的任务区间 $[s_i,s_i+p_i)$ 不重叠。

令
\[
C_{\max}(s)=\max_{i\in J}(s_i+p_i).
\]

### 3.2 固定 horizon、域与禁止集

固定 $h$。用 `heads_tails` 计算最长头 $est_i$ 与最长尾 $q_i$：
\[
est_i=\max_{P\leadsto i}\sum_{k\in P}p_k,\qquad
q_i=\max_{i\leadsto P}\sum_{k\in P\setminus\{i\}}p_k.
\]
任务 $i$ 的域为
\[
D_i(h)=[est_i,\;h-q_i-p_i]\cap\mathbb Z_{\ge0}.
\]
禁止集 $F\subseteq J\times\mathbb Z_{\ge0}$ 表示「任务 $i$ 不允许在 $t$ 开始」。记
\[
D_i(h,F)=D_i(h)\setminus\{t:(i,t)\in F\}.
\]
判断
\[
\mathrm{NO}(h\mid F):=\text{不存在 }F\text{-允许的可行调度 }s\text{ 使 }C_{\max}(s)\le h.
\]
当 $F=\varnothing$ 时简写为 $\mathrm{NO}(h)$。

### 3.3 证明树

PACT 的证明树为
\[
\pi ::= \mathrm{Leaf}(F,\Phi)\mid \mathrm{Empty}(F,i)\mid
\mathrm{Yes}(s,m)\mid \mathrm{Node}(i,t,F,\pi_L,\pi_R).
\]
语义：

- $\mathrm{Leaf}(F,\Phi)$：$\mathtt{verify}(I,h,\Phi,\mathrm{forbid}=F)=1$，证明 $\mathrm{NO}(h\mid F)$；
- $\mathrm{Empty}(F,i)$：$D_i(h,F)=\varnothing$，证明 $\mathrm{NO}(h\mid F)$；
- $\mathrm{Yes}(s,m)$：$\mathtt{check\_schedule}(I,h,s,m)=1$，给出 YES；
- $\mathrm{Node}(i,t,F,\pi_L,\pi_R)$：令
  \[
  F_L=F\cup\{(i,u):u>t\},\qquad
  F_R=F\cup\{(i,u):u\le t\},
  \]
  两个子域都非空，$\pi_L$ 证明 $\mathrm{NO}(h\mid F_L)$，$\pi_R$ 证明 $\mathrm{NO}(h\mid F_R)$，则节点证明 $\mathrm{NO}(h\mid F)$。

### 3.4 高度、大小与势函数

定义高度
\[
\mathrm{ht}(\mathrm{Leaf})=\mathrm{ht}(\mathrm{Empty})=\mathrm{ht}(\mathrm{Yes})=0,
\]
\[
\mathrm{ht}(\mathrm{Node}(i,t,F,\pi_L,\pi_R))
=1+\max(\mathrm{ht}(\pi_L),\mathrm{ht}(\pi_R)).
\]
定义大小
\[
|\mathrm{Leaf}|=|\mathrm{Empty}|=|\mathrm{Yes}|=1,\qquad
|\mathrm{Node}|=1+|\pi_L|+|\pi_R|.
\]
定义势函数
\[
\mu(F)=\sum_{i\in J}|D_i(h,F)|.
\]
一次非平凡切分 $(i,t)$ 满足两侧都非空，因此
\[
\mu(F_L)<\mu(F),\qquad \mu(F_R)<\mu(F).
\]

### 3.5 核化

**单点域规则**：若 $|D_i(h)|=1$，则任务 $i$ 的开始时刻在根盒中唯一，不需要分支。

**零松弛规则**：若 $est_i+p_i+q_i=h$，则
\[
D_i(h)=\{est_i\},
\]
因为 $h-q_i-p_i=est_i$。更强地，对任意可行 $s$ 且 $C_{\max}(s)\le h$，
\[
est_i\le s_i,\qquad s_i+p_i+q_i\le C_{\max}(s)\le h=est_i+p_i+q_i,
\]
所以 $s_i=est_i$。这类任务在搜索中不参与分支。

定义自由核
\[
K=\{i\in J:|D_i(h)|>1\}.
\]
搜索只在 $K$ 上切分。核化不改变可行调度集：单点域和零松弛任务只是把「必须取的值」从搜索变量里去掉。实现中 LP 仍保留这些任务的单列（便于证书直接重放），但 `choose` 不会选它们。

### 3.6 proof store 与查询 $Q$

proof store $\mathcal P$ 保存
\[
\mathrm{NO}(h),\quad \mathrm{LB}(v),\quad \mathrm{UB}(s),\quad \mathrm{EXACT}(v).
\]
$Q$ 只统计 **CHD oracle 调用次数**；PACT 的 LP、证书 LP、GA 的 SGS 次数都不计入 $Q$。因此 $Q=0$ 的准确含义是：没有再向 CHD 问任何一次 YES/NO，而不是零计算。

---

## 4. 形式化规则

### 4.1 叶子规则

**(L1) Farkas 叶子。** 若固定 $h,F$ 的 SDLP 不可行，且
\[
\mathtt{verify}(I,h,\Phi,\mathrm{forbid}=F)=1,
\]
则
\[
\frac{\mathtt{verify}(I,h,\Phi,\mathrm{forbid}=F)=1}
{\mathrm{NO}(h\mid F)}.
\tag{Farkas}
\]

**(L2) 空域叶子。** 若存在 $i$ 使 $D_i(h,F)=\varnothing$，则
\[
\frac{D_i(h,F)=\varnothing}{\mathrm{NO}(h\mid F)}.
\tag{Empty}
\]

**(L3) 整数叶子。** 若 LP 解 $z$ 是整数，解码得到 $(s,m)$，且
\[
\mathtt{check\_schedule}(I,h,s,m)=1,
\]
则返回 YES。它不是 NO 证明，但会缩小上界。

**(L4) 匹配叶子（规格）。** 若所有开始时刻都已固定，`_assign_machines` 做精确的机器分配回溯；若失败，该叶子是 NO。当前实现把这种情况标为 UNKNOWN 并交给 CHD；252 例中未触发。全正确性定理把这一条列为假设 C3。

### 4.2 分支规则

\[
\frac{
  \mathrm{NO}(h\mid F_L)
  \qquad
  \mathrm{NO}(h\mid F_R)
}{
  \mathrm{NO}(h\mid F)
}
\tag{Branch}
\]
其中
\[
F_L=F\cup\{(i,u):u>t\},\qquad
F_R=F\cup\{(i,u):u\le t\},
\]
且两个子域都非空。穷尽性：任何 $F$-允许的调度，$s_i$ 要么 $\le t$，要么 $>t$，二者必居其一；两个子域都不可行，则父域不可行。

### 4.3 `Search(h,d)` 的三值语义

```text
Search(bounds, F, d):
    if d < 0: return UNKNOWN
    solve SDLP(bounds)
    if infeasible:
        cert = integer_certificate(..., forbid=F)
        if verify(cert): return Leaf(F, cert)
        if exists i with D_i(h,F)=empty: return Empty(F, i)
        return UNKNOWN
    if integral:
        (s, m) = decode(z)
        if check_schedule(s, m): return Yes(s, m)
        if singleton_leaf finds (s, m): return Yes(s, m)
        choose a job with multiple allowed times; if none: return UNKNOWN
    else:
        (i, t) = choose_fractional_job(z, bounds)
    left  = Search(bounds_L, F_L, d-1)
    if left is Yes: return left
    right = Search(bounds_R, F_R, d-1)
    if right is Yes: return right
    if left is NO and right is NO:
        return Node(i, t, F, left, right)
    return UNKNOWN
```

关键点：

- 一个 UNKNOWN 子节点不会阻止另一个子节点的探索；这与 SAGE 的 `depthcap` 不同，后者在深度超限时直接返回 None，可能丢掉另一侧的 YES。
- 只有两个子节点都 NO 才生成 NO 节点；否则父节点是 UNKNOWN。
- `d=\infty` 时没有深度检查，完整搜索由 $\mu$ 保证终止。

### 4.4 核化规则的形式化

**引理 1（零松弛钉死）**：若 $est_i+p_i+q_i=h$，则任意可行 $s$ 且 $C_{\max}(s)\le h$ 都有 $s_i=est_i$。

**证明**：$s_i\ge est_i$，且 $s_i+p_i+q_i\le C_{\max}(s)\le h=est_i+p_i+q_i$，故 $s_i\le est_i$，于是 $s_i=est_i$。$\square$

**引理 2（核化保持可行集）**：把单点域和零松弛任务从分支变量中移除，不改变根盒内可行调度的集合。

**证明**：这些任务的开始时刻在根盒中唯一；移除它们只是去掉没有选择的分支，不会删除任何可行调度。$\square$

### 4.5 总轨迹

一个总轨迹为
\[
T=(lb_0,ub_0,\pi_0,s_0,m_0,\;
[(h_j,v_j,\pi_j,s_j,m_j)]_{j=1}^q,\;
\pi^*,s^*,m^*).
\]
审计条件：

1. $\pi_0$ 证明 $\mathrm{LB}(lb_0)$，或 `bound_lb(I)=lb0`；$s_0$ 是 $C_{\max}\le ub_0$ 的调度。
2. 对每个 step $j$：$lb_{j-1}\le h_j<ub_{j-1}$。
   - 若 $v_j=\mathrm{NO}$，$\pi_j$ 证明 $\mathrm{NO}(h_j)$，$lb_j=h_j+1$，$ub_j=ub_{j-1}$；
   - 若 $v_j=\mathrm{YES}$，$s_j$ 满足 $C_{\max}\le h_j$，$ub_j=\min(ub_{j-1},C_{\max}(s_j))$，$lb_j=lb_{j-1}$。
3. 最终 $lb_q=ub_q=v$，$\pi^*$ 证明 $\mathrm{NO}(v-1)$，$s^*$ 满足 $C_{\max}=v$。
4. 结论：$\mathrm{OPT}=v$。

实现中的 `TotalTrace.audit_rdf()` 逐条检查上述条件；它不读取生成器的 `certified`、`proof` 或 `ok`。

### 4.6 STAB 复用

STAB 的单调规则原样保留：
\[
\frac{\mathrm{NO}(h)}{\mathrm{LB}(h+1)},\qquad
\frac{\mathrm{LB}(v)\qquad h<v}{\mathrm{NO}(h)},\qquad
\frac{\mathrm{LB}(v)\qquad \mathrm{UB}(s)\qquad C_{\max}(s)=v}{\mathrm{EXACT}(v)}.
\]
PACT 只在 `_ensure_lb_proof(value)` 里按需闭包：先找精确的 $\mathrm{NO}(value-1)$，找不到就从更强的 $\mathrm{NO}(h')$ 做 `SubsumptionProof`。这与 SAGE 完全一致。

---

## 5. 算法

### 5.1 外层 `optimize`

```text
lb, ub, s, mach = initial_bounds()
if ub is None: return unknown
steps = []
while lb < ub:
    if ub - lb <= scan_cap:
        h = lb
    else:
        h = floor((lb + ub) / 2)
    v, payload = probe(h)
    if v == YES:
        if Cmax(payload) < ub and check_schedule(...):
            ub, s, mach = Cmax(payload), payload.schedule, payload.machine
            steps.append((h, YES, payload))
    elif v == NO:
        lb = max(lb, h + 1)
        record_proof(payload)
        steps.append((h, NO, payload))
    else:
        recover_unknown(h)
if lb == ub:
    final_proof()          # NO(lb-1)
    build_total_trace()    # 初始界 + steps + final NO + schedule
return result()
```

与 SAGE 的差别只在 `probe`、`final_proof` 的证明来源和 `build_total_trace`；bracket 本身不变。

### 5.2 `probe(h)`

```text
# PACT-C: complete first
if mode == 'complete':
    r = pact_decide(inst, h, depthcap=None, nodecap=None)
    if r.verdict == NO: return NO, r.proof
    if r.verdict == YES: return YES, (r.schedule, r.machine, Cmax)
    return CHD(h)

# PACT-F: closing hybrid
if mode == 'closing' and ub - lb > 1:
    return SAGE._probe(h)          # capped BB + GA + CHD
if mode == 'closing' and ub - lb == 1:
    r = pact_decide(inst, h, depthcap=None, nodecap=None)
    if r.verdict == NO: return NO, r.proof
    if r.verdict == YES: return YES, (r.schedule, r.machine, Cmax)

# PACT-P: parameterized NO-first
for d in 0..pact_depth:
    r = pact_decide(inst, h, depthcap=d, nodecap=pact_nodecap)
    if r.verdict == NO: return NO, r.proof
    if r.verdict == YES: return YES, (r.schedule, r.machine, Cmax)
got = ga_schedule(inst, h, ...)
if got is not None and check_schedule(...): return YES, got
r = pact_decide(inst, h, depthcap=None, nodecap=None)
if r.verdict == NO: return NO, r.proof
if r.verdict == YES: return YES, ...
return CHD(h)
```

关键点：

- PACT-C 不调用 GA、不调用 CHD；所有 probe 由完整搜索解决。
- PACT-F 的 bracketing probe 仍用 SAGE 的 capped BB；只有 closing probe 用完整搜索。
- PACT-P 的深度循环是「参数化 NO-first」：它先找浅证明，找不到再让 GA 和完整搜索接手。252 例上 PACT-P 比 PACT-C 慢，因为它在 YES probe 上重复做了完整搜索；它的价值是给出「$k\le3$ 时全部 58 个 NO 都能闭合」的证据。

### 5.3 `pact_decide` 的细节

```text
root = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig)
dfs(bounds, F, d):
    if d < 0: return UNKNOWN
    res = lp.solve(bounds)
    if res infeasible:
        cert = integer_certificate(inst, h, forbid=F)
        if verify(cert): return Leaf(F, cert)
        if empty domain: return Empty(F, i)
        return UNKNOWN
    if res integral:
        s, m = decode(res.x)
        if check_schedule(s, m): return Yes(s, m)
        s, m = singleton_leaf(...)
        if s is not None: return Yes(s, m)
        pick any job with >1 allowed time; if none: return UNKNOWN
    else:
        i, mid = choose_fractional_job(res.x, bounds)
        if i is None: return UNKNOWN
    F_L = F ∪ {(i, u): u > mid}
    F_R = F ∪ {(i, u): u ≤ mid}
    left = dfs(bounds_L, F_L, d-1)
    if left is Yes: return left
    right = dfs(bounds_R, F_R, d-1)
    if right is Yes: return right
    if left is NO and right is NO:
        return Node(i, mid, F, left, right)
    return UNKNOWN
```

`choose_fractional_job` 的选择与 SAGE 一致：按任务质量、尾延迟、后继数、下标排序，取累计质量首次超过 50% 的时间点作为 `mid`；退化时取中位时间。这个策略只影响树的形状，不影响分区性质。

### 5.4 `TotalTrace`

```text
TotalTrace(inst, opt, lb0, ub0, init_lb_proof, init_bound,
           init_schedule, init_machine, steps, final_lb_proof,
           final_schedule, final_machine):
    audit:
        check final_lb_proof.h == opt-1 and final_lb_proof.audit_rdf()
        check final_schedule is feasible with Cmax == opt
        check init_schedule is feasible with Cmax <= ub0
        check init_lb_proof (or bound_lb == lb0)
        lb, ub = lb0, ub0
        for (h, v, payload) in steps:
            assert lb <= h < ub
            if v == NO:
                assert payload.h == h and payload.audit_rdf()
                lb = max(lb, h+1)
            elif v == YES:
                assert check_schedule(payload, h)
                ub = min(ub, Cmax(payload))
            else:
                return False
        return lb == ub == opt
```

### 5.5 GENETIC-UB

GA 原样继承 SAGE：基因组是任务排列，解码器是串行 SGS，适应度是 $(\text{makespan},\sum C_i)$，OX 交叉、交换/插入变异、精英保留、单调局部修复；只有通过 `check_schedule` 的调度才被接受。PACT-C 不用 GA；PACT-F 只在 bracketing probe 的 BB 返回 UNKNOWN 时用一次 GA。

---

## 6. 正确性论证

### 6.1 叶子可靠性

- **Farkas 叶子**：`verify` 独立重放整数证书；若 SDLP 不可行，则不存在 $F$-允许的整数调度，故 $\mathrm{NO}(h\mid F)$。
- **空域叶子**：若 $D_i(h,F)=\varnothing$，任务 $i$ 没有允许开始时刻，故不存在完整调度。
- **整数叶子**：`check_schedule` 检查优先、机器、容量、eligibility 与 $C_{\max}\le h$；通过则给出真实 YES。
- **匹配叶子**：`_assign_machines` 是固定开始时刻上的精确回溯；失败则不存在机器分配。当前实现把失败标为 UNKNOWN，交给 CHD；这是全正确性定理的假设 C3。

### 6.2 分支可靠性

设节点 $\mathrm{Node}(i,t,F,\pi_L,\pi_R)$ 的两个子节点分别证明了
\[
\mathrm{NO}(h\mid F_L),\qquad \mathrm{NO}(h\mid F_R).
\]
任取一个 $F$-允许的调度 $s$。由于 $s_i\le t$ 或 $s_i>t$ 必居其一：

- 若 $s_i\le t$，则 $s$ 是 $F_R$-允许的，与右子判断矛盾；
- 若 $s_i>t$，则 $s$ 是 $F_L$-允许的，与左子判断矛盾。

故不存在这样的 $s$，即 $\mathrm{NO}(h\mid F)$。对树高归纳，所有 `BranchProof` 的根判断可靠。

### 6.3 终止性

**引理 3（势函数严格下降）**：若切分 $(i,t)$ 把当前允许域分成两个非空部分，则
\[
\mu(F_L)<\mu(F),\qquad \mu(F_R)<\mu(F).
\]

**证明**：$F_L$ 和 $F_R$ 都是 $F$ 的真超集，且各自至少禁止了当前允许域中的一个时刻；只有任务 $i$ 的域发生变化，其他任务的域不变，故 $\mu$ 至少减少 1。$\square$

**定理 1（完整搜索终止）**：`Search(h,\infty)` 在有限步内终止，且递归深度不超过 $\mu(\varnothing)\le n(T+1)$。

**证明**：每次递归调用都在严格更小的 $\mu$ 上进行；$\mu$ 是非负整数，故良基。$\square$

### 6.4 完备性

**引理 4（分区覆盖）**：固定策略 $\pi$ 的搜索树是一棵二叉分区树：每个内部节点把当前盒按任务 $i$ 的开始时刻切成 $s_i\le t$ 与 $s_i>t$ 两半，两个子盒不交且并集为父盒。

**证明**：切分只修改任务 $i$ 的允许域，且两个子域互补；其他任务域不变。$\square$

**引理 5（完整搜索的判定正确性）**：若匹配叶子被正确关闭，则 `Search(h,\infty)` 返回 YES 当且仅当存在可行调度 $s$ 使 $C_{\max}(s)\le h$；否则返回 NO。

**证明**：

- 若存在可行 $s$，由引理 4，$s$ 落入某个叶子。该叶子的 LP 可行；若 LP 整数，`check_schedule` 接受；若 LP 分数，搜索继续切分；若所有开始时刻已固定，`_assign_machines` 找到机器分配。故不会返回 NO。
- 若不存在可行 $s$，每个叶子的 LP 不可行或空域，Farkas/Empty 叶子闭合；所有叶子闭合后，根返回 NO。
- 若某个叶子既不能闭合也不能给出 YES，`Search` 返回 UNKNOWN，而不是错误的 NO/YES。

因此，在证书原语完备的前提下，完整搜索是可靠且完备的。$\square$

### 6.5 全正确性定理

**定理 2（PACT-C 的全正确性）**：假设

- **C1**：`verify` 对 Farkas 证书是可靠的；
- **C2**：`check_schedule` 对调度是可靠的；
- **C3**：每个不可行叶子都能由整数/有理 Farkas 证书或匹配叶子关闭；
- **C4**：`initial_bounds` 返回的 $lb_0,ub_0$ 满足 $lb_0\le\mathrm{OPT}\le ub_0$，且附带有效的下界证明或组合界、以及通过检查的上界调度。

则 PACT-C 终止，返回 $\mathrm{OPT}$，且 `TotalTrace.audit_rdf()` 为真。

**证明**：

1. **终止**：外层每轮要么把 $lb$ 抬高（NO），要么把 $ub$ 压低（YES）；$ub-lb$ 是有限非负整数，故外层最多 $ub_0-lb_0+1$ 轮。每轮 `Search(h,\infty)` 由定理 1 终止；`_ensure_lb_proof` 只在有限 proof store 上扫描。故总终止。
2. **不变式**：初始 $lb_0\le\mathrm{OPT}\le ub_0$ 由 C4。NO 步把 $lb$ 抬到 $h+1\le\mathrm{OPT}$；YES 步把 $ub$ 压到 $C_{\max}(s)\ge\mathrm{OPT}$。故每步后不变式成立。
3. **闭合**：循环退出时 $lb=ub=v$。由不变式 $\mathrm{OPT}=v$。
4. **证书**：`_ensure_lb_proof(v)` 给出 $\mathrm{NO}(v-1)$（或等价 subsumption），最终调度 $s^*$ 满足 $C_{\max}=v$。`TotalTrace` 逐条重放初始界、每个 step、最终 NO 和调度；由 C1、C2、引理 5，审计通过。

$\square$

### 6.6 总轨迹的可靠性

`TotalTrace.audit_rdf()` 不信任生成器；它独立检查：

- 初始下界证明（或 `bound_lb` 等式）和初始调度；
- 每个 step 的 $h$ 在当前 bracket 内；
- 每个 NO 证明的 $h$ 匹配且 `audit_rdf` 通过；
- 每个 YES 调度的 $C_{\max}\le h$ 且 `check_schedule` 通过；
- 最终 $\mathrm{NO}(v-1)$ 和 $C_{\max}=v$ 的调度。

因此，`total_audit=True` 蕴含 $\mathrm{OPT}=v$，且整条 bracket 路径可重放。篡改测试见第 11 节。

### 6.7 快速模式

PACT-F 在 bracketing probe 上仍用 SAGE 的 capped BB/GA/CHD。若某个 bracketing probe 返回 UNKNOWN，CHD 会被调用，$Q>0$；此时总轨迹仍可审计（CHD 的 RDF 被包成 `OracleProof`），但 $Q=0$ 不再是定理。252 例上 PACT-F 的 bracketing probe 只有 2 个：一个 BB YES，一个 BB UNKNOWN 被 GA 接住；因此 $Q=0$ 且总审计 252/252。

### 6.8 为什么没有多项式核

`SCHED(I,h)` 是 NP 完全的：取 $m=2$、无优先约束、全 eligibility，判定是否存在 $C_{\max}\le h$ 的调度就是 PARTITION。若 PACT 对某个由 $n$ 多项式界定的参数给出多项式核，就会推出 P$\ne$NP 下的矛盾。因此本轮**不声称**多项式核；$k$ 是证书高度参数，最坏 $k\le n(T+1)$，可能是线性于 $nT$ 的。$k\le4$ 只是 252 例的经验事实，不是结构性定理。

---

## 7. 复杂度

### 7.1 LP 规模

固定 $h$ 的 SDLP 有
\[
O(nT)\ \text{个变量},\qquad
O(mT+|E|T+n)\ \text{条约束},
\]
其中 $T=h+1$ 是 horizon 长度。单次 LP 的代价记为 $L(n,m,T)$；证书 LP 的代价记为 $C(n,m,T)$。在 252 例上单次是毫秒级。

### 7.2 搜索树

高度为 $k$ 的完整二叉搜索树最多有
\[
2^{k+1}-1\ \text{个节点},\qquad 2^k\ \text{个叶子}.
\]
每个内部节点一次 LP；每个 NO 叶子一次证书 LP。因此
\[
T_{\rm probe}(k)=O\bigl(2^k(L+C)\bigr).
\]
完整模式 $k\le\mu(\varnothing)\le n(T+1)$，最坏
\[
O\bigl(2^{n(T+1)}(L+C)\bigr),
\]
是有限但指数的。这个上界是诚实的：PACT 不是多项式算法。

### 7.3 外层

外层最多
\[
O(\log(ub_0-lb_0)+\mathrm{scan\_cap})
\]
次 probe；总时间
\[
O\bigl(2^k\log\Delta\,(L+C)+T_{\rm init}\bigr),
\]
其中 $\Delta=ub_0-lb_0$。在 252 例上 $\Delta$ 很小，scan_cap=4，实际 probe 总数 105。

### 7.4 空间

当前实现把每个节点的 $F$ 存成 `frozenset`，所以最坏空间
\[
O(2^k\cdot nT)
\]
（证明树）或 $O(k\cdot nT)$（DFS 栈）。252 例的最大证明只有 9 个节点，空间可忽略。若未来要支持大 $k$，应把 $F$ 换成区间盒（每个任务一个 $[lo_i,hi_i]$），空间降到 $O(2^k n)$；这是 PRISM 方向的改进，本轮未实现。

### 7.5 实测参数 $k$

**NO 侧（$h=\mathrm{OPT}-1$）**：

| 语料 | $n$ | $k=0$ | $k=1$ | $k=2$ | $k=4$ | 最大 $k$ | 节点 | 证书 LP | 时间 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 141 | 139 | 2 | 0 | 0 | 1 | 145 | 143 | 2.41 s |
| pert | 60 | 55 | 5 | 0 | 0 | 1 | 70 | 65 | 0.81 s |
| stress | 51 | 0 | 43 | 7 | 1 | 4 | 173 | 112 | 1.67 s |
| **合计** | **252** | **194** | **50** | **7** | **1** | **4** | **388** | **320** | **4.89 s** |

**YES 侧（$h=\mathrm{OPT}$）**：

| 语料 | $n$ | $k=0$ | $k=1$ | $k=2$ | $k\ge3$ | 最大 $k$ | 节点 | 时间 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 141 | 45 | 19 | 21 | 56 | 29 | 597 | 5.99 s |
| pert | 60 | 4 | 21 | 22 | 13 | 9 | 178 | 0.87 s |
| stress | 51 | 6 | 4 | 11 | 30 | 7 | 206 | 1.05 s |
| **合计** | **252** | **55** | **44** | **54** | **99** | **29** | **981** | **7.90 s** |

58 个 $g=1$ 的 NO 证明子集：

| 高度 $k$ | 实例数 | 节点/例 | 叶子/例 | 总节点 | 总证书 |
|---:|---:|---:|---:|---:|---:|
| 1 | 50 | 3 | 2 | 150 | 100 |
| 2 | 7 | 5 | 3 | 35 | 21 |
| 4 | 1 | 9 | 5 | 9 | 5 |
| **合计** | **58** | — | — | **194** | **126** |

这张表是本轮最重要的实验结果：**NO 侧的高度被压到 4，实际节点数 9；而 YES 侧的高度可以到 29。** 同一个深度参数不能同时服务两边。

### 7.6 YES 侧与 GA

YES 侧的完整搜索在 252 例上用 981 个 LP 节点，最大高度 29；如果用一个固定的深度上限，会漏掉大量 YES。GENETIC-UB 的代价是一次 SGS 解码 $O(n^2)$，预算 $B=4000$，一次 GA 调用上界 $O(Bn^2)$。PACT-C 完全不用 GA；PACT-F 只用 1 次；PACT-P（深度 3）用 7 次成功 + 3 次失败，说明 GA 是 YES 侧的性能补件，而不是 NO 侧的证明器。

---

## 8. 实验设计

### 8.1 语料

沿用 v8.1 的三组语料，共 252 例：

| 语料 | $n$ | 说明 |
|---|---:|---|
| base | 141 | 基础族，覆盖多种结构；8 例有 eligibility 限制（`large_het`） |
| pert | 60 | 扰动族，LP 分数/舍入边界更多 |
| stress | 51 | 压力族，根 LP 在 $\mathrm{OPT}-1$ 上仍然可行 |

约束规模为 $n\le21$、$m\le4$、$T\le68$；每例都有已知最优值 `known`，仅用于离线验收，不参与算法。

### 8.2 指标

- `certified`：算法是否给出精确认证；
- `ok`：`certified` + `opt=known` + `audit` + `proof` + `cert_h=known-1`；PACT 还要求 `total_audit`；
- `Q`：CHD 调用次数；
- `pin_lp`：LP pin 次数；
- `bb_lp`：SAGE LP-BRANCH 节点 LP 次数；
- `cert_lp`：SAGE 叶子证书 LP 次数；
- `pact_lp`：PACT 搜索 LP 次数；
- `pact_cert_lp`：PACT 叶子证书 LP 次数；
- `pact_nodes`：PACT 搜索树节点数；
- `total_audit`：`TotalTrace.audit_rdf()` 是否通过；
- `time`：单例墙钟，包含 LP、GA、证书、总审计。

### 8.3 变体

- **SAGE v8.8**：同 runner 复跑，作为基线；
- **PACT-C**：complete first，所有 probe 由完整搜索解决，不用 GA/CHD；
- **PACT-F**：closing hybrid，bracketing 用 SAGE，closing 用完整搜索；
- **PACT-P（single3）**：单次深度 3 + GA + complete；
- **PACT-d1**：迭代加深到 1；
- **PACT-d0**：只允许 $k=0$；
- **PACT-no-complete**：关闭 complete fallback，保留 CHD；
- **PACT-no-ga**：关闭 GA，complete 负责所有 YES。

### 8.4 复现

```bash
cd /home/runner/work/xuen/xuen/workspace
.venv/bin/python exp/v8o/bench_pact.py      # PACT 全部变体
.venv/bin/python exp/v8i/bench_sage.py      # SAGE 基线
```

`bench_pact.py` 会写入 `exp/v8o/bench_pact_*.json`；`bench_sage.py` 会写入 `exp/v8i/bench_sage_full.json`。所有变体在同一 Python 进程、同一 runner、无并行；时间是单次运行，不含置信区间。

---

## 9. 主实验结果

### 9.1 SAGE vs PACT

| 指标 | SAGE v8.8 | PACT-C | PACT-F |
|---|---:|---:|---:|
| 认证 | 252/252 | 252/252 | 252/252 |
| $Q$ | 0 | **0** | **0** |
| LP pin | 273 | 273 | 273 |
| 搜索 LP | 442（BB） | **450（complete）** | 30（BB）+ 412（complete） |
| 证书 LP | 137 | **138** | 6 + 131 |
| LP 总计 | 852 | **861** | **852** |
| YES 节点 | 0 | 0 | 0 |
| 总审计 | 无 | **252/252** | **252/252** |
| 时间 | 11.62 s | **10.59 s** | 11.43 s |

PACT-C 的总 LP 比 SAGE 多 9 次，但墙钟反而略低；这是单次运行，不应解读为稳定的速度优势。真正的差别是：PACT-C 没有 caps、没有 GA、没有 CHD，并且 252 张总证书全部通过独立重放。

### 9.2 分语料

| 语料 | $n$ | SAGE 时间 | PACT-C 时间 | PACT-C 搜索 LP | PACT-C 证书 LP | PACT-C 总审计 |
|---|---:|---:|---:|---:|---:|---:|
| base | 141 | 6.64 s | 6.08 s | 199 | 16 | 141 |
| pert | 60 | 1.31 s | 1.15 s | 78 | 0 | 60 |
| stress | 51 | 3.67 s | 3.36 s | 173 | 122 | 51 |
| **合计** | **252** | **11.62 s** | **10.59 s** | **450** | **138** | **252** |

stress 的证书 LP 是 122，占 138 的绝大多数；这与 stress 的根 LP 在 $\mathrm{OPT}-1$ 上仍然可行一致：NO 证明必须切到 Farkas 叶子，而 base/pert 的 194 个 NO 里大多数在根就不可行。

### 9.3 引擎归因

| 变体 | complete NO | complete YES | GA YES | BB YES | CHD | 未决 |
|---|---:|---:|---:|---:|---:|---:|
| PACT-C | 58 | 47 | 0 | 0 | 0 | 0 |
| PACT-F | 58 | 45 | 1 | 1 | 0 | 0 |
| PACT-single3 | 58 | 40 | 7 | 0 | 0 | 10 个 probe 进入 GA/complete |
| PACT-d1 | 58 | 26 | 21 | 0 | 0 | 31 个 probe 进入 GA/complete |
| PACT-d0 | 58 | 6 | 41 | 0 | 0 | 60 个 probe 进入 GA/complete |
| PACT-no-complete | 57 | 38 | 7 | 0 | 3 | 0 |
| PACT-no-ga | 58 | 47 | 0 | 0 | 0 | 10 个 probe 进入 complete |

PACT-single3 是一个关键对照：深度 3 足以闭合全部 58 个 NO（与参数表一致），但只闭合 40/47 个 YES；剩下的 7 个由 GA 接住，3 个由完整搜索接住。**NO 侧浅、YES 侧深**，这不是调参问题，而是两侧证明义务不同。

### 9.4 证明类型

| 类型 | SAGE | PACT-C | PACT-F | PACT-no-complete |
|---|---:|---:|---:|---:|
| `branch` | 58 | 58 | 58 | 57 |
| `farkas` | 110 | 110 | 110 | 110 |
| `bound` | 60 | 60 | 60 | 60 |
| `energy` | 24 | 24 | 24 | 24 |
| `oracle` | 0 | 0 | 0 | 1 |
| **合计** | **252** | **252** | **252** | **252** |

PACT-C/F 的最终证明形态与 SAGE 完全一致：58 张 `branch`、110 张 Farkas、60 张 bound、24 张 energy；区别在 `branch` 的搜索过程和总轨迹。PACT-no-complete 把 1 张 `branch` 退回 `oracle`，同时 $Q=3$，这说明完整 fallback 是消除最后一个 oracle 的关键。

### 9.5 时间与 LP 分解

PACT-C 的 10.59 s 包含：

- LP pin：273 次；
- 完整搜索：450 次；
- 叶子证书：138 次；
- 总轨迹审计：252 次（每次重放该例的证明与调度）；
- GA/CHD：0 次。

PACT-F 的 11.43 s 包含：

- LP pin：273 次；
- BB：30 次；
- complete closing：412 次；
- 证书：6 + 131 次；
- GA：1 次；
- 总轨迹审计：252 次。

两者的 LP 总量都是 852，但 PACT-F 多了一次 GA 和 bracketing BB 的开销；PACT-C 把所有 probe 统一成 complete，代码路径更简单，审计也更容易解释。

---

## 10. 消融

| 变体 | $Q$ | 搜索 LP | 证书 LP | LP 总计 | 总审计 | 时间 | 读法 |
|---|---:|---:|---:|---:|---:|---:|---|
| **PACT-C** | **0** | **450** | **138** | **861** | **252** | **10.59 s** | 完整搜索，无 GA/CHD |
| **PACT-F** | **0** | 30 + 412 | 6 + 131 | **852** | **252** | 11.43 s | closing 完整，bracketing 用 SAGE |
| PACT-single3 | 0 | 484 | 140 | 897 | 252 | 14.18 s | 深度 3 后 GA/complete |
| PACT-d1 | 0 | 471 | 139 | 883 | 252 | 14.89 s | 深度 1 后 GA/complete |
| PACT-d0 | 0 | 334 | 129 | 736 | 252 | 27.54 s | 只允许根节点切分 |
| PACT-no-complete | **3** | 719 | 148 | 1140 | 252 | 16.71 s | 关闭 complete，CHD 回来 |
| PACT-no-ga | 0 | 868 | 165 | 1306 | 252 | 17.07 s | 关闭 GA，complete 负责 YES |

### 10.1 深度消融

- **d0**：只允许根节点切分。58 个 NO 仍然全部闭合（因为多数 NO 在根或一刀内闭合），但 41 个 YES 要 GA、60 个要 complete；时间 27.54 s，说明 YES 侧不能被深度 0 卡住。
- **d1**：26 个 YES 在深度 1 内闭合，21 个靠 GA，10 个靠 complete；14.89 s。
- **single3**：58 个 NO 全部闭合，40 个 YES 在深度 3 内闭合，7 个靠 GA，3 个靠 complete；14.18 s。它比 PACT-C 慢，因为它在 YES probe 上先做了一次注定失败的深度 3 搜索。
- **PACT-C**：不做深度尝试，直接完整搜索；10.59 s。这说明在 252 例上，**参数化深度优先不是运行时策略，而是证明复杂度的度量**。

### 10.2 关闭 complete

`PACT-no-complete` 把最后 3 个 probe 退回 CHD：

- $Q=3$，LP$_{\rm CHD}$ 不在本表（CHD 内部 LP 另计）；
- 时间 16.71 s，比 PACT-C 多 6.12 s；
- 最终证明出现 1 张 `oracle`；
- 总审计仍然 252/252，因为 CHD 的 RDF 被包成 `OracleProof`，`TotalTrace` 可以重放它。

这说明：**总正确性不要求 $Q=0$；$Q=0$ 是 PACT-C 把 CHD 完全替换掉之后的额外结果。**

### 10.3 关闭 GA

`PACT-no-ga` 用完整搜索负责所有 YES：

- $Q=0$，总审计 252/252；
- 搜索 LP 868，证书 LP 165，总计 1306，时间 17.07 s；
- 比 PACT-C 多 6.48 s。

GA 不是正确性必需，但它是 YES 侧的性能补件；在 PACT-C 中，完整搜索已经足够快，所以 GA 可以被完全省掉。这是一个有趣的结论：**当完整搜索的 YES 高度在 29 以内时，GA 的边际收益是负的（至少在这批语料上）；但 PACT-C 的成功依赖于完整搜索能承受 981 个 YES 节点。**

---

## 11. 证明审计与篡改测试

### 11.1 独立重放

`TotalTrace.audit_rdf()` 从初始界开始，按步骤重放：

- 初始下界：`init_lb_proof.audit_rdf()` 或 `bound_lb(I)=lb0`；
- 初始上界：`check_schedule(init_schedule, ub0)`；
- 每个 step：$h$ 在当前 bracket 内，NO 证明的 $h$ 匹配且 `audit_rdf` 通过，YES 调度的 $C_{\max}\le h$ 且 `check_schedule` 通过；
- 最终：`final_lb_proof.h=opt-1` 且 `audit_rdf` 通过，`final_schedule` 的 $C_{\max}=opt$。

它不读取生成时的 LP 状态、bounds、`certified` 或 `ok`。

### 11.2 篡改测试

在 `stress 47`（$h=34$，OPT=35）上手工修改 `TotalTrace`：

| 篡改 | `audit_rdf()` |
|---|---|
| 删除最后一个 step | False |
| 把某个 step 的 $h$ 改成 $ub_0+1$ | False |
| 把最终调度的某个开始时刻 +1 | False |
| 把最终 NO 证明的 $h$ +1 | False |
| 原始对象 | True |

这些测试只针对证书对象，不针对 LP 求解器；它们说明 `TotalTrace` 在做结构性校验，而不是只查一个布尔标志。

### 11.3 证明对象

PACT-C/F 的最终证明对象与 SAGE 相同：

- `BranchProof`：逐层检查 $F$ 分区、子 $F$ 恰好是父 $F$ 加对应半区、叶子 `verify` 或空域；
- `SubsumptionProof`：检查 `source.h >= self.h` 且 source 自身 audit；
- `TotalTrace`：检查整条 bracket。

`pact_decide` 在返回 NO 前会先 `proof.audit_rdf()`；如果失败，返回 UNKNOWN，不会把坏证明交给外层。

---

## 12. 讨论

### 12.1 为什么 NO 浅、YES 深

NO 证明只需要展示「不存在」：LP 在根或切一刀后不可行，Farkas 证书就闭合了。YES 证明需要构造一个整数调度：LP 的分数解可能在很多任务上都有质量，搜索要逐层把分数质量挤到整数点；每层只切一个任务，所以高度可能很大。252 例的分布正是这样：NO 最大高度 4，YES 最大高度 29。

这不是 PACT 的缺陷，而是问题结构：**不可行性证明可以是局部的，可行性构造可以是全局的。** SAGE 把 LP-BRANCH 用在 NO 侧、把 GA 用在 YES 侧，正好对应这个不对称性。

### 12.2 为什么参数化深度优先不是运行时策略

PACT-single3 在 252 例上比 PACT-C 慢 3.59 s：它在每个 YES probe 上先做一次深度 3 的搜索，失败后再 GA/complete。深度 3 对 NO 足够，对 YES 不够；重复的根 LP 和失败的搜索是纯开销。因此本轮的结论不是「用深度 3 替换 SAGE」，而是：

> **用 $k$ 解释 SAGE 的 NO 侧为什么便宜，用完整搜索替换 NO 侧的 caps；运行时仍然让 YES 侧走它擅长的引擎。**

PACT-C 选择「完整搜索统一处理两侧」，是因为在这批语料上完整搜索的 YES 代价可以接受（981 个节点、7.90 s）；如果新语料的 YES 更深，PACT-F/PACT-P 的混合模式更合适。

### 12.3 为什么不是「APEX + 更快的 oracle」

PACT 的 `branch` 是一等证明：它携带完整的 $F$ 分区，能在不运行 LP 的情况下被 `audit_rdf` 重放，能被 `SubsumptionProof` 接到最终下界，能被 `TotalTrace` 纳入整条 bracket。$Q=0$ 不是「oracle 变快了」，而是「NO 从搜索副产品变成了证明对象」。

### 12.4 与 SAGE 的关系

PACT-C 不是 SAGE 的替代品，而是它的「证明侧升级」：

- 搜索策略相同（LP 引导的分数任务切分）；
- 叶子规则相同（Farkas/Empty/YES）；
- 外层 bracket 相同；
- 新增的是三值语义、完整模式、总轨迹和参数分析。

在 252 例上，PACT-C 的 LP 总数只比 SAGE 多 9 次，但总审计从「最后一张 NO 树」升级为「整条 bracket + 上下界 + 最终调度」。这是本轮的主要收益。

---

## 13. 已知风险与限制

1. **$k$ 是经验参数，不是定理**：252 例上 NO 侧 $k\le4$，但最坏 $k\le n(T+1)$；新语料可能完全不同。完整搜索的 $2^k$ 上界仍然是指数。
2. **没有多项式核**：`SCHED` 是 NP 完全的；本轮不声称多项式核，也不声称 FPT 于 $n$ 或 $T$。$k$ 是证书高度参数，依赖具体实例和切分策略。
3. **YES 侧重尾**：YES 高度最大 29；完整搜索在 YES 侧用 981 个节点。如果新语料的 YES 更深，PACT-C 会变慢，GA 仍然是必要的性能补件。
4. **Farkas 证书的数值稳定性**：实现使用 `integer_certificate` 的整数缩放；252 例的 138 张证书全部通过 `verify`，但没有实现精确有理 Farkas 的完整回退。若新语料出现病态 LP，`pact_decide` 会返回 UNKNOWN，退回 CHD。
5. **匹配叶子未完全证书化**：8 个 `large_het` 实例有 eligibility 限制；`_assign_machines` 是精确回溯，但失败时当前实现返回 UNKNOWN 而不是 NO 证明。全正确性定理把这一点列为假设 C3；252 例未触发。
6. **总轨迹的成本**：`TotalTrace` 会重新审计每个 step 的证明和调度；时间已计入 10.59 s，但证明规模增大时，审计成本会线性增长。
7. **单次运行**：时间是同一 runner 的单次墙钟，没有置信区间；SAGE 与 PACT 的 1 s 差异不应被过度解读。
8. **语料小**：$n\le21$、$m\le4$、$T\le68$；没有 PSPLIB、没有更大规模、没有多峰分布。$k\le4$ 不能外推。
9. **切分策略未针对高度优化**：`choose_fractional_job` 沿用 SAGE 的质量/尾延迟/后继数排序；不同的切分顺序可能得到更矮的证明树。本轮没有做策略搜索。
10. **`known` 的使用**：`ok` 用 `known` 做离线验收；生产环境应看 `certified`、`audit`、`proof`、`total_audit`。
11. **快速模式仍用 caps**：PACT-F 的 bracketing probe 仍可能返回 UNKNOWN；$Q=0$ 是 252 例的结果，不是定理。
12. **总轨迹的 CHD 包装**：如果某个 step 由 CHD 给出，`TotalTrace` 用 `OracleProof` 包装 RDF；它的可靠性依赖 RDF 的 `audit_rdf`，而不是 PACT 自己的检查器。

---

## 14. 最大风险（一句话）

**PACT 的全正确性只在 $k$ 小的时候便宜：如果新语料上 NO 证明高度 $k$ 变大，完整搜索会指数爆炸；而退回 SAGE 的 caps 又会把 $Q=0$ 和总证书一起丢掉——所以本轮最大的风险是「$k\le4$ 只是这 252 例的经验事实，不是定理」。**

---

## 15. 本轮结论（一句话）

**PACT-ALC 把 SAGE 的 NO 证明从「capped 搜索」变成「按证书高度 $k$ 参数化的完整搜索」：在 252 例上 252/252 认证、$Q=0$、总审计 252/252、10.59 s，58 个 $g=1$ 的 NO 证明高度分布为 $50\times1$、$7\times2$、$1\times4$；代价是 $k$ 的最坏情况仍是 $n(T+1)$，全正确性不能自动变成多项式时间。**
<!-- ARTIFACT:END -->
