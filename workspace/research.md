# 玄 · 设计一个新的算法

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 想法区 · 第 2 轮（承接 v8.7 APEX-ALC）：把「谁来证明 NO」变成可执行的分支树

**灵感词**：self-stabilizing algorithm / genetic algorithm / linear programming  
**起点**：v8.7 APEX-ALC 在 252 例上做到 252/252 认证，$Q=105$、LP $=874$、YES 节点 $=60001$、同 runner 复跑 11.82 s。上一轮把「近似比」变成了整数间隙 $g=\mathrm{OPT}-L^*$，并且证明 $g\in\{0,1\}$；但 APEX 仍然把最后的闭合压在 CHD oracle 上：58 个 $g=1$ 实例各要一次 NO，46 个 $g=0$ 实例各要一次 YES 构造，另有一个 $Q=2$ 的尾例。

## 一、先把 105 次查询按「证明义务」重新分类

APEX 的查询分布看起来很干净：148 例 0 次、103 例 1 次、1 例 2 次。但把它按证明义务拆开，问题立刻变了：

1. **58 次是「在 $L^*$ 上证 NO」。** 这些实例的 incumbent 已经是 $\mathrm{OPT}=L^*+1$，下界证明也把 $\mathrm{LB}$ 抬到了 $L^*$。唯一缺的是一张 $\mathrm{NO}(L^*)$。APEX 让 CHD 去做这件事，而 CHD 是一个 YES-first 的约束搜索；它最坏会在 YES 侧烧掉 60k 节点，stress 的那一例就是这样。
2. **46 次是「在 $L^*=\mathrm{OPT}$ 上造 YES」。** 这些实例的 LP 在 $L^*$ 可行，但解是分数的；APEX 的 `lp_schedule` 舍入失败，LNS 在 $\mathrm{UB}-\mathrm{LB}=1$ 时不触发，于是只能问 CHD 要一张 $C_{\max}=L^*$ 的调度。
3. **1 次是尾部扫描。** base 的 `large_het 7` 在二分后还做了一次线性扫描；它说明 $Q\le2$ 只是经验事实，不是定理。

所以本轮的第一句话是：

> **105 次查询不是 105 个「搜索深度」问题，而是 58 个 NO 证明、46 个 YES 构造和 1 个尾部；把这三类义务分开，才能分别用 LP、遗传搜索和证明代数去消掉。**

## 二、三个灵感词分别落在哪一层

- **self-stabilizing algorithm**：自稳定算法从任意初始状态出发，只靠局部修复规则收敛到合法状态，不依赖外部初始化。APEX 的 proof store 其实已经是一个「判断集合」，但它没有闭包算子；APEX 的 bracket 也已经是一个「区间状态」，但它没有稳定化规则。我们可以把两者都写成自稳定系统：LP-BRANCH 从根 LP 的分数状态出发，局部地切分不稳定的叶子，直到每个叶子要么是整数调度、要么是 Farkas 不可行；STAB 从任意证明集合出发，反复应用 subsumption，直到判断集合闭合。两者都有有限的 ranking function，因此终止；判断闭包是单调规则的最小不动点，所以最终判断与插入顺序无关。
- **genetic algorithm**：上界侧不应该只用一个 LNS 邻域。把调度看成「优先级排列 → 串行 SGS 解码」的基因组，用种群、交叉（OX）、变异、精英保留和单调局部修复去搜索；每个接受个体都必须过 `check_schedule`。它不是证明器，但它是上界侧的构造器，正好补 LP-BRANCH 只会证 NO、不会造 YES 的空缺。
- **linear programming**：LP 不再只是「下界机」。固定 $h$ 的 SD LP 如果分数可行，就继续分支；如果不可行，叶子上的 Farkas 对偶就是一张可重放的 $\mathrm{NO}(h)$ 证明。换句话说，**LP 本身可以是一个 proof-producing decision procedure**，而不是只能给出一个数值下界。

## 三、第一次试错：把 `sdecc_no` 当黑箱 oracle，NO 很快，但证明不可重放

工作区里已经有 `exp/v60/sdecc.py` 的 `sdecc_no`：它在固定 $h$ 上做 LP 分支，分数变量按开始时间切成两半。直接拿它当 oracle，stress 的 NO 在 3–7 个 LP 节点内就返回，60k YES 节点瞬间消失。这个实验说明「LP 分支是 NO 侧的强引擎」。

但它不能直接进 APEX：

- `sdecc_no` 只返回 `False/True/None`，没有留下可重放的证明树；把它塞进 `no_states` 会破坏 APEX 的 soundness 叙事。
- 分支用 `bounds` 数组零掉列，和 `verify` 的 `forbid` 语义没有对齐；如果不把「路径上的禁止开始时刻」显式记录下来，检查器无法独立重放。
- 递归实现会在大实例上撞 Python 递归深度；必须显式加 nodecap/depthcap，并在超限时退回 CHD。

结论：**LP 分支是必要的，但「一个 verdict」不是证明；必须把分支路径和叶子 Farkas 一起变成一等证明项。**

## 四、第二次试错：只做遗传上界，YES 能造，但 NO 侧仍是 60 次

第二个实验只做上界：把 4 个启发式顺序和随机排列作为初始种群，用 OX 交叉、交换/插入变异、精英保留，再做「只接受严格改进」的局部交换修复。它在独立的 46 个 $g=0$ 原型上能全部找到 $C_{\max}=L^*$ 的调度；集成到 SAGE 的 `no_bb` 变体后，GA 造出了 45 张 YES，但：

- $Q=60$：58 个 $g=1$ 实例仍然要 CHD 的 NO，另 2 个 $g=0$ 实例 GA 没找到；
- YES 节点回到 $60001$，stress 仍然是 60k；
- 时间反而升到 24.65 s，因为 GA 在 $g=1$ 的不可行 $h$ 上会把预算跑满。

结论：**GA 是必要的上界补件，但不是下界证明器；它不能替代 $\mathrm{NO}(L^*)$。**

## 五、合流：SAGE-ALC

把两次试错接起来，就得到本轮算法 **SAGE-ALC（Self-stabilizing proof Algebra with Genetic upper-side Evolution）**：

1. **LP-BRANCH（下界 / NO 侧）**：在 $h$ 上建 SD LP；分数可行就选一个分数任务，在它的允许开始时间上做二分；LP 不可行的叶子用 `integer_certificate(..., forbid=F)` 生成 Farkas 证书；整数叶子直接给出调度。所有叶子按 $F$ 分区，内部节点记录 $(i,m)$，整棵树就是 $\mathrm{NO}(h)$ 的证明。nodecap $=96$、depthcap $=24$，超限返回 UNKNOWN 并退回 GA/CHD。
2. **GENETIC-UB（上界 / YES 侧）**：种群 $40$、代数 $60$、预算 $4000$ 次 SGS 评估；基因组是任务排列，解码器是 `_greedy_rank`，适应度是 $(\text{makespan},\sum C_i)$；OX 交叉、交换/插入变异、精英保留、局部交换修复；只有过 `check_schedule` 的调度才被接受。
3. **STAB（证明代数）**：把 $\mathrm{NO}(h)$、$\mathrm{LB}(v)$、$\mathrm{UB}(s)$、$\mathrm{EXACT}(v)$ 写成单调规则；从任意 proof store 出发反复应用
   \[
   \mathrm{NO}(h)\Rightarrow \mathrm{LB}(h+1),\qquad
   \mathrm{LB}(v)\land h<v\Rightarrow \mathrm{NO}(h),
   \]
   直到不动点。最终 $\mathrm{LB}=\mathrm{UB}=v$ 时，只要 proof store 里有 $\mathrm{LB}(v)$（等价地，有 $v-1$ 的 NO），就直接 `MEET`，不再补问 $v-1$。
4. **外层**：仍是 APEX 的 bracket + LP pin + LP 舍入 + LNS + CHD fallback；只是每个 probe 先问 LP-BRANCH，再问 GENETIC-UB，最后才问 CHD。CHD 调用才计入 $Q$。

252 例的结果是：

| 语料 | $n$ | $Q$ | LP$_{\rm CHD}$ | LP$_{\rm pin}$ | LP$_{\rm BB}$ | LP$_{\rm cert}$ | YES 节点 | 时间 | 认证 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 141 | 0 | 0 | 120 | 191 | 15 | 0 | 5.51 s | 141 |
| pert | 60 | 0 | 0 | 81 | 78 | 10 | 0 | 1.03 s | 60 |
| stress | 51 | 0 | 0 | 72 | 173 | 112 | 0 | 3.08 s | 51 |
| **合计** | **252** | **0** | **0** | **273** | **442** | **137** | **0** | **9.62 s** | **252** |

对照同 runner 的 APEX：$Q=105\to0$，LP$_{\rm CHD}=874\to0$，YES $=60001\to0$，时间 $11.82\to9.62$ s；总计数 LP（pin + CHD + BB + cert）从 $1147$ 降到 $852$。最终证明分布是：58 张 `branch`（正好替换 APEX 的 58 张 `oracle`）、110 张 Farkas、60 张 bound、24 张 energy；$g=0$ 的 194 例最终证明与 APEX 完全一致，$g=1$ 的 58 例从 `oracle` 变成 `branch`。

消融把三件东西的贡献分得很清楚：

| 变体 | $Q$ | LP$_{\rm CHD}$ | YES 节点 | 时间 | 读法 |
|---|---:|---:|---:|---:|---|
| **SAGE full** | **0** | **0** | **0** | **9.62 s** | 58 NO + 46 YES + 1 UNKNOWN→GA |
| `no_ga` | 1 | 13 | 0 | 9.71 s | B&B 的 1 个 UNKNOWN 退回 CHD |
| `bb_no_only` | 2 | 24 | 0 | 13.21 s | B&B 只证 NO；GA 造 45 个 YES，漏 2 个 |
| `no_bb` | 60 | 412 | 60001 | 24.65 s | GA 造 45 个 YES，但 58 个 NO 仍靠 CHD |

这不是「APEX 加了一个更快的 oracle」：`branch` 是一等判断，`STAB` 是它的闭合算子，`GENETIC-UB` 是上界补件。三者缺一不可，但贡献最大的是 LP-BRANCH：它把「NO 证明」从 CHD 的 YES 搜索里独立出来，60k YES 节点因此归零。

## 六、当前方案最大的风险

**$Q=0$ 不是免费的：它把 CHD 换成了最坏指数级的 LP-BRANCH；如果新语料上分支树或叶子 Farkas 证书爆炸，SAGE 会同时失去 APEX 的查询数优势和墙钟优势。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 产物区 · v8.8 SAGE-ALC：自稳定证明代数 + 遗传上界 + LP 分支证明

## 0. 本轮产物与一句话结论

**SAGE-ALC**（Self-stabilizing proof Algebra with Genetic upper-side Evolution）是 v8.7 APEX-ALC 的子类：保留 bracket、LP pin、LP 舍入、LNS 与 CHD fallback，新增

1. **LP-BRANCH**：固定 $h$ 的 SD LP 分支，分数叶子继续分裂，不可行叶子给出可重放的 Farkas 证书，整数叶子给出调度；整棵树是 $\mathrm{NO}(h)$ 的一等证明。
2. **GENETIC-UB**：排列基因组 + 串行 SGS + OX 交叉 + 变异 + 精英保留 + 单调局部修复，专门补上界侧的 YES 构造。
3. **STAB**：把 $\mathrm{NO}$、$\mathrm{LB}$、$\mathrm{UB}$、$\mathrm{EXACT}$ 写成单调判断，按需做 subsumption 闭包，最终用 $\mathrm{MEET}$ 消除 $\mathrm{OPT}-1$ 的 oracle。

在 252 例上：**252/252 认证，$Q=0$，LP$_{\rm CHD}=0$，YES 节点 $=0$，9.62 s**；同 runner 的 v8.7 APEX 为 $Q=105$、LP$_{\rm CHD}=874$、YES 节点 $=60001$、11.82 s。58 个原本要 CHD 证 NO 的实例全部换成 58 张 `branch` 证明，60k YES 节点归零。

但这不是免费的：LP-BRANCH 最坏是指数级，$Q=0$ 只是当前语料上的结果，不是定理。

---

## 1. 产物清单

| 路径 | 内容 |
|---|---|
| `exp/v8i/sage.py` | SAGE-ALC 实现：`BranchProof`、`SubsumptionProof`、`lp_branch_decide`、`ga_schedule`、`SAGE(APEX)` |
| `exp/v8i/bench_sage.py` | 252 例主实验与 `no_ga`、`no_bb`、`bb_no_only` 三组消融 |
| `exp/v8i/bench_sage_full.json` | full 原始结果，252 行 |
| `exp/v8i/bench_sage_no_ga.json` | 关闭 GA 的结果 |
| `exp/v8i/bench_sage_no_bb.json` | 关闭 LP-BRANCH 的结果 |
| `exp/v8i/bench_sage_bb_no_only.json` | 只用 LP-BRANCH 证 NO、禁用 B&B YES 的结果 |
| `exp/v8h/apex.py` | v8.7 APEX 基类；SAGE 直接继承 |
| `exp/v8h/bench_apex_full.json` | APEX 基线（本轮同 runner 复跑） |
| `exp/v60/sdecc.py` | `SDLP` 与 `sdecc_no`，LP-BRANCH 的底层 |
| `exp/v60/cert.py` | `verify`、`integer_certificate`，叶子 Farkas 证书 |
| `exp/v8a/rdf.py` | `check_schedule` 与 CHD/RDF 接口 |

---

## 2. 与 v8.7 APEX-ALC 的版本关系

| 层 | v8.7 APEX-ALC | v8.8 SAGE-ALC | 关系 |
|---|---|---|---|
| 初始 bracket | LP pin + chip bound + LP 舍入 + LNS | 原样继承 | 不变 |
| 下界 | LP pin；NO 由 CHD 给 | LP pin + LP-BRANCH | 新增可证明 NO |
| 上界 | LP 舍入 + LNS + CHD YES | 继承 + GENETIC-UB | 新增遗传构造 |
| 证明代数 | 判断集合 + subsumption | STAB：单调规则按需闭包 | 扩展为分支证明 |
| 最终闭合 | `MEET` | `MEET`，但 $\mathrm{OPT}-1$ 由 `BranchProof` 提供 | 消除 oracle |
| fallback | CHD | CHD，仍保留 | 仅在 B&B/GA 都失败时调用 |

实现上 `SAGE` 只覆盖三处：

- `_probe(h)`：先 LP-BRANCH，再 GA，最后 CHD；
- `optimize()`：沿用 APEX 的 bracket，但记录 B&B/GA 归因；
- `_ensure_lb_proof(value)`：先找精确的 $\mathrm{NO}(value-1)$，找不到再从更强的 $\mathrm{NO}(h')$ 做 subsumption。

其余 `initial_bounds`、`_decide`、`_absorb`、`_record`、`_result`、`_final_proof` 全部继承 APEX。

---

## 3. 问题、符号与判断

### 3.1 实例

一个实例为
\[
I=(J,M,E,p,q,\mathrm{elig}),
\]
其中 $J$ 是任务集，$M$ 是机器集，$E\subseteq J\times J$ 是先后约束，$p_i$ 是加工时间，$q_i$ 是尾延迟，$\mathrm{elig}_i\subseteq M$ 是允许机器集。调度 $s:J\to\mathbb Z_{\ge0}$ 可行当且仅当：

1. $s_i\in\mathrm{elig}_i$ 对应的机器可用；
2. 对每条 $i\to j$，$s_j\ge s_i+p_i$；
3. 每台机器上的任务区间 $[s_i,s_i+p_i)$ 不重叠。

令
\[
C_{\max}(s)=\max_{i\in J}(s_i+p_i).
\]

### 3.2 固定 horizon 与禁止集

固定 $h$，任务 $i$ 的最早/最晚开始时间为
\[
\mathrm{est}_i(h)=\mathrm{head}_i,\qquad
\mathrm{lst}_i(h)=h-q_i-p_i,
\]
其域为
\[
D_i(h)=[\mathrm{est}_i(h),\mathrm{lst}_i(h)]\cap\mathbb Z_{\ge0}.
\]
禁止集 $F\subseteq J\times\mathbb Z_{\ge0}$ 表示「任务 $i$ 不允许在时刻 $t$ 开始」。记
\[
D_i(h,F)=D_i(h)\setminus\{t:(i,t)\in F\}.
\]
若调度 $s$ 满足 $s_i\in D_i(h,F)$ 对所有 $i$ 成立，则称 $s$ 是 $F$-允许的。

**判断**：
\[
\mathrm{NO}(h\mid F):=\text{不存在 }F\text{-允许的可行调度 }s\text{ 使 }C_{\max}(s)\le h.
\]
当 $F=\varnothing$ 时简写为 $\mathrm{NO}(h)$。

### 3.3 proof store 与四个判断

proof store $\mathcal P$ 保存已证明的判断：
\[
\mathrm{NO}(h),\quad \mathrm{LB}(v),\quad \mathrm{UB}(s),\quad \mathrm{EXACT}(v).
\]
语义是：

- $\mathrm{NO}(h)$：$\mathrm{OPT}>h$；
- $\mathrm{LB}(v)$：$\mathrm{OPT}\ge v$；
- $\mathrm{UB}(s)$：$s$ 可行且 $\mathrm{OPT}\le C_{\max}(s)$；
- $\mathrm{EXACT}(v)$：$\mathrm{OPT}=v$ 且附带一张 $C_{\max}=v$ 的调度。

APEX 的整数间隙是
\[
g=\mathrm{OPT}-L^*,
\]
其中 $L^*$ 是 LP pin 得到的最好下界。上一轮已经在这 252 例上验证 $g\in\{0,1\}$。

### 3.4 查询 $Q$ 的精确定义

$Q$ 只统计 **CHD oracle 调用次数**。LP-BRANCH 的 LP 次数、GA 的 SGS 次数、LP pin 的次数都不计入 $Q$，但计入时间与 LP 计数。因此「$Q=0$」的准确含义是：

> **没有再向 CHD 问任何一次 YES/NO；所有判断都由 LP-BRANCH、LP pin、LNS 或 GA 给出。**

这不是「零计算」，也不是「零 LP」。

---

## 4. 形式化规则

### 4.1 LP-BRANCH 的分支规则

设固定 $h$ 和禁止集 $F$，选任务 $i$ 和分割点 $m$。定义
\[
F_{\le m}=F\cup\{(i,t):t>m\},\qquad
F_{>m}=F\cup\{(i,t):t\le m\}.
\]
直观上：

- $F_{\le m}$ 禁止 $i$ 在 $m$ 之后开始，所以 $i$ 只能落在 $\le m$ 一侧；
- $F_{>m}$ 禁止 $i$ 在 $m$ 或之前开始，所以 $i$ 只能落在 $>m$ 一侧。

规则为
\[
\frac{
  \mathrm{NO}(h\mid F_{\le m})
  \qquad
  \mathrm{NO}(h\mid F_{>m})
}{
  \mathrm{NO}(h\mid F)
}
\tag{Branch}
\]
前提是两个子域都非空；若某个子域为空，该子域是平凡 $\mathrm{NO}$，父判断等价于另一子域。当前实现为避免假分支直接返回 UNKNOWN，并交给 GA/CHD。

**穷尽性**：任何 $F$-允许的调度，$s_i$ 要么 $\le m$，要么 $>m$，二者必居其一。因此两个子域覆盖了父域的所有可能；两个子域都不可行，则父域不可行。

### 4.2 叶子规则

LP-BRANCH 的叶子有三类：

**(L1) Farkas 叶子。** 若固定 $h,F$ 的 SD LP 不可行，且 `integer_certificate(inst,h,forbid=F)` 返回证书 $\Phi$，并且
\[
\mathtt{verify}(I,h,\Phi,\mathrm{forbid}=F)=1,
\]
则
\[
\frac{\mathtt{verify}(I,h,\Phi,\mathrm{forbid}=F)=1}
{\mathrm{NO}(h\mid F)}.
\tag{Farkas}
\]
$\Phi$ 是对偶证书；`verify` 独立重放，不信任求解器的 `status`。

**(L2) 空域叶子。** 若存在任务 $i$ 使 $D_i(h,F)=\varnothing$，则不存在 $F$-允许的完整调度，直接得 $\mathrm{NO}(h\mid F)$。

**(L3) 整数叶子。** 若某个 LP 解 $z$ 是整数，且舍入/解码得到调度 $s$，并通过
\[
\mathtt{check\_schedule}(I,h,s,\mathrm{machine})=1,
\]
则得到 $\mathrm{UB}(s)$，同时这条分支以 YES 结束；它不是 NO 证明，但会缩小上界。

### 4.3 `BranchProof` 数据类型

概念上的证明树为
\[
\pi ::= \mathrm{Leaf}(F,\Phi)\mid \mathrm{Empty}(F,i)\mid
\mathrm{Node}(i,m,F,\pi_L,\pi_R).
\]
实现中的元组形式是：

- `('leaf', F, cert)`；
- `('empty', F, i)`；
- `('node', i, m, F, left, right)`。

检查器 `BranchProof._check(node,F)` 做四件事：

1. 父节点记录的 $F$ 必须与当前 $F$ 一致；
2. 分支点 $(i,m)$ 必须真的把当前允许域切成两个非空部分；
3. 左子节点的禁止集必须是 $F\cup\{(i,t):t>m\}$，右子节点必须是 $F\cup\{(i,t):t\le m\}$；
4. 叶子证书必须通过 `verify(..., forbid=F)`，或空域检查成立。

根调用是 `_check(tree, frozenset())`。因此 `BranchProof` 是自包含的：不依赖 APEX 的 `no_states`，也不依赖生成它的 LP 求解器。

### 4.4 STAB：单调判断闭包

STAB 的规则是
\[
\frac{\mathrm{NO}(h)}{\mathrm{LB}(h+1)}
\tag{NO-LB}
\]
\[
\frac{\mathrm{LB}(v)\qquad h<v}{\mathrm{NO}(h)}
\tag{LB-NO}
\]
\[
\frac{\mathrm{LB}(v)\qquad \mathrm{UB}(s)\qquad C_{\max}(s)=v}
{\mathrm{EXACT}(v)}
\tag{MEET}
\]
以及
\[
\frac{\mathrm{LB}(v)\qquad \mathrm{UB}(s)}
{\mathrm{RATIO}(C_{\max}(s)/v)}.
\tag{RATIO}
\]

这些规则都是单调的：前提中的判断一旦进入 proof store，结论就可以加入。对固定实例，可能的 $h$、$v$ 和已构造的调度集合是有限的，因此从任意初始 proof store 出发，反复应用规则必然在有限步到达最小不动点，且到达的判断与规则应用顺序无关。

实现上不做全局全量闭包，而是 **按需闭包**：`_ensure_lb_proof(value)` 先尝试精确的 $\mathrm{NO}(value-1)$；若没有，就在 proof store 中找最小的 $h\ge value-1$，用
\[
\mathrm{NO}(h)\Rightarrow \mathrm{NO}(value-1)
\]
做一次 subsumption，生成 `SubsumptionProof`。这等价于在需要的点上取闭包，避免为所有 $h$ 预生成证明。

### 4.5 `MEET` 的最终闭合

当外层满足 $\mathrm{LB}=\mathrm{UB}=v$ 时，APEX 调用 `_final_proof()`。SAGE 的 `_ensure_lb_proof(v)` 返回：

- 精确的 $\mathrm{NO}(v-1)$（通常就是 `BranchProof`），或
- 从更强的 $\mathrm{NO}(h')$ 得到的 `SubsumptionProof`。

于是最终证明是
\[
\mathrm{LB}(v)\quad+\quad \mathrm{UB}(s)\quad+\quad C_{\max}(s)=v
\quad\Longrightarrow\quad
\mathrm{EXACT}(v).
\]
这里不再需要向 CHD 追问 $v-1$，因为 $v-1$ 的 NO 已经在证明树里。

---

## 5. 算法

### 5.1 外层 `optimize`

```text
lb, ub, s, mach = initial_bounds()
if ub is None: return unknown
while lb < ub and queries < max_queries:
    if ub - lb <= scan_cap:
        h = lb                    # 尾部线性扫描
    else:
        h = floor((lb + ub) / 2)  # 二分
    v, payload = probe(h)
    if v == YES:
        if Cmax(payload) < ub and check_schedule(...):
            ub, s, mach = Cmax(payload), payload.schedule, payload.machine
    elif v == NO:
        lb = max(lb, h + 1)
        record_proof(payload)
    else:
        recover_unknown(h)
if lb == ub:
    final_proof()
return result()
```

与 APEX 的差别只在 `probe` 和 `final_proof` 的证明来源；bracket 本身不变。

### 5.2 `probe(h)`

```text
if use_bb:
    r = lp_branch_decide(inst, h, nodecap=96, depthcap=24)
    if r.verdict == NO:
        bb_no += 1
        record_proof(r.proof)
        return NO, r.proof
    if r.verdict == YES and bb_yes:
        if check_schedule(inst, h, r.schedule, r.machine):
            bb_yes += 1
            return YES, (r.schedule, r.machine, Cmax(r.schedule))
    if r.verdict == YES and not bb_yes:
        bb_yes_ignored += 1
    if r.verdict is None:
        bb_unknown += 1

if use_ga:
    got, st = ga_schedule(inst, h, pop=40, gens=60, budget=4000)
    if got is not None and check_schedule(inst, h, got):
        ga_yes += 1
        return YES, (got.schedule, got.machine, Cmax(got.schedule))
    ga_no += 1

chd_fallback += 1
queries += 1
v, st, rdf = CHD(h)
absorb(st); record(h, v, st)
return v, rdf
```

关键点：

- LP-BRANCH 的 YES 只在 `bb_yes=True` 时立即接受；`bb_no_only` 故意忽略它，用来测 GA 的上界能力。
- GA 的返回必须过 `check_schedule`；不过就当作没有。
- 只有最后的 CHD 分支增加 $Q$。

### 5.3 `lp_branch_decide` 的自稳定细化

```text
root = SDLP(inst, h, est, q, use_dom=True, elig_aware=True)
dfs(bounds, F, depth):
    if depth > depthcap: return UNKNOWN
    solve(bounds)
    if infeasible:
        cert = integer_certificate(inst, h, forbid=F)
        if verify(cert, forbid=F): return Leaf(F, cert)
        if exists empty D_i(h,F): return Empty(F, i)
        return UNKNOWN
    if integral(z):
        s, m = decode(z)
        if check_schedule(inst, h, s, m): return Yes(s, m)
        return UNKNOWN
    i, mid = choose_fractional_job(z, bounds)
    if none: return UNKNOWN
    low  = dfs(bounds with i <= mid, F ∪ {(i,t): t > mid}, depth+1)
    high = dfs(bounds with i > mid, F ∪ {(i,t): t <= mid}, depth+1)
    if low is UNKNOWN: return UNKNOWN
    if low is Yes: return low
    if high is UNKNOWN: return UNKNOWN
    if high is Yes: return high
    return Node(i, mid, F, low, high)
```

`choose_fractional_job` 只在「质量分数且允许时间数 $>1$」的候选里选；默认按任务质量、尾延迟、后继数、下标排序。`mid` 取累计质量首次超过一半的时间点；若退化，取中位时间。`nodecap=96`、`depthcap=24` 是硬上限；超限返回 UNKNOWN，外层退回 GA/CHD。

这里就是「self-stabilizing」的具体落点：每个叶子是一个局部状态，LP 可行且分数就继续细化，LP 不可行或整数就稳定；细化只依赖当前域的局部信息，不需要全局初始化，也不会撤销已经稳定的叶子。

### 5.4 `ga_schedule` 的遗传上界

```text
seeds = 4 个启发式排列（est、latest、-q、est-0.5q）
P = seeds + 36 个随机排列
cache = 评估 P 中每个基因组：SGS 解码 -> (makespan, sum C)
for gen in 1..60:
    if best <= h or evals >= 4000: break
    P = 按 fitness 排序
    new = P[:4]                     # 精英保留
    while len(new) < 40:
        a, b = tournament(P[:20])
        child = OX(a, b)
        if rand < 0.7: child = mutate(child)
        if rand < 0.15: child = local_repair(child, cap=120)
        new.append(child)
    P = new
best = local_repair(best, cap=2000)
return best if check_schedule(inst, h, best) else None
```

- 基因组：任务排列；
- 解码器：串行 SGS，把排列依次塞进最早可用机器；
- 适应度：$(\text{makespan},\sum_i C_i)$，字典序；
- OX 交叉：保序交叉；
- 变异：交换/插入；
- 局部修复：只接受严格改进的交换，每个子代最多 120 次，末轮最多 2000 次；
- 预算：4000 次唯一 SGS 评估，种群 40，代数 60。

GA 不产生 NO、不产生下界；它只产生通过 `check_schedule` 的上界调度。它的正确性门槛是 `check_schedule`，而不是适应度值。

### 5.5 STAB 的实现

```text
_ensure_lb_proof(value):
    p = APEX._ensure_lb_proof(value)      # 精确 NO(value-1)
    if p is not None: return p
    best = min {h : NO(h) in proofs and h >= value-1}
    if best exists:
        return record(SubsumptionProof(inst, value-1, proofs[best]))
    return None
```

`SubsumptionProof` 的检查器要求 `source.h >= self.h` 且 `source` 自身通过 audit；因此它不能把更弱的 NO 伪装成更强的 NO。

---

## 6. 正确性论证

### 6.1 叶子可靠性

- **Farkas 叶子**：`verify` 独立检查证书；若 $P_h(F)$ 不可行，则任何 $F$-允许的整数调度都不存在，故 $\mathrm{NO}(h\mid F)$。
- **空域叶子**：若 $D_i(h,F)=\varnothing$，任务 $i$ 没有任何允许开始时刻，故不存在完整调度。
- **整数叶子**：`check_schedule` 检查优先级、机器、容量、eligibility 与 $C_{\max}\le h$；通过则给出真实 YES 调度。

### 6.2 分支可靠性

设节点 $\mathrm{Node}(i,m,F,\pi_L,\pi_R)$ 的两个子节点分别证明了
\[
\mathrm{NO}(h\mid F_{\le m}),\qquad
\mathrm{NO}(h\mid F_{>m}).
\]
任取一个 $F$-允许的调度 $s$。由于 $s_i\le m$ 或 $s_i>m$ 必居其一：

- 若 $s_i\le m$，则 $s$ 是 $F_{\le m}$-允许的，与左子判断矛盾；
- 若 $s_i>m$，则 $s$ 是 $F_{>m}$-允许的，与右子判断矛盾。

故不存在这样的 $s$，即 $\mathrm{NO}(h\mid F)$。对树高归纳，所有 `BranchProof` 的根判断可靠。

### 6.3 `BranchProof` 检查器的可靠性

`_check` 逐层验证：

1. 父 $F$ 与当前 $F$ 一致，防止跨层偷换禁止集；
2. 分割点确实把当前允许域分成两个非空部分，防止「假分支」；
3. 子 $F$ 恰好是父 $F$ 加上对应半区的禁止，防止遗漏或重复；
4. 叶子证书通过 `verify` 或空域检查。

因此 `audit_rdf()=True` 蕴含根判断 $\mathrm{NO}(h\mid\varnothing)$。篡改 `alpha`/`beta` 会破坏 `verify`；篡改 `mid` 会破坏子 $F$ 的分区检查；两者都被实验拒绝。

### 6.4 GA 的可靠性

`ga_schedule` 只在最后调用 `check_schedule`；只有通过才返回调度。因此 GA 不会制造假 YES。它可能失败（返回 `None`），这不影响可靠性，只影响完整性。

### 6.5 STAB 的可靠性

`NO-LB`、`LB-NO`、`MEET`、`RATIO` 都是语义上显然的单调规则：

- $\mathrm{NO}(h)$ 即 $\mathrm{OPT}>h$，所以 $\mathrm{OPT}\ge h+1$；
- $\mathrm{LB}(v)$ 且 $h<v$ 时，$\mathrm{OPT}\ge v>h$，所以 $\mathrm{NO}(h)$；
- 下界与同值上界相遇即精确最优。

`SubsumptionProof` 额外检查 `source.h >= self.h`，因此 $\mathrm{NO}(h')\Rightarrow\mathrm{NO}(h)$ 只在 $h'\ge h$ 时成立，方向不会反。

### 6.6 最终认证的可靠性

当外层以 $\mathrm{LB}=\mathrm{UB}=v$ 退出时：

- `UB` 附带一张通过 `check_schedule` 的调度 $s$，且 $C_{\max}(s)=v$；
- `LB` 附带一张通过 `BranchProof.audit_rdf()` 的 $\mathrm{NO}(v-1)$（或通过 subsumption 的等价证明）。

于是 $\mathrm{OPT}\ge v$ 且 $\mathrm{OPT}\le v$，故 $\mathrm{OPT}=v$，且 $s$ 达到 $v$。`_result` 的 `certified`、`audit`、`proof`、`cert_h` 都由这些对象产生，不依赖 `known`。

### 6.7 基准中的 `ok`

基准额外用已知最优值 `known` 做校验：
\[
\mathtt{ok}=\mathtt{certified}\land \mathtt{opt}=\mathtt{known}\land
\mathtt{audit}\land\mathtt{proof}\land \mathtt{cert\_h}=\mathtt{known}-1.
\]
`known` 只用于离线验收，不参与算法。生产环境应看 `certified`、`audit`、`proof`。

### 6.8 完备性的边界

SAGE 的完备性依赖两个引擎至少一个成功：

- LP-BRANCH 在 caps 内给出 NO/YES；或
- GA 找到 YES；或
- CHD fallback 给出答案。

如果三者都失败，外层会走 APEX 的 `_recover_unknown`，最终可能 `certified=False`。因此 SAGE 不是「无条件多项式时间精确算法」；它是「在当前语料上把 105 次 CHD 全部消掉」的工程化精确算法。

---

## 7. 复杂度

### 7.1 LP 规模

固定 $h$ 的 SD LP 有 $O(nT)$ 个开始时间变量和 $O(mT+|E|+n)$ 条约束，其中 $T=h+1$ 是 horizon 长度。单次 LP 由 HiGHS 求解；时间对 $(n,m,T)$ 超线性，但在本语料上单次是毫秒级。

### 7.2 LP-BRANCH 的最坏情况

最坏情况下，每个任务都可能被分裂到每个允许开始时刻，叶子数可达
\[
\prod_{i\in J}|D_i(h)|,
\]
因此是指数级。实现的硬上限是 `nodecap=96`、`depthcap=24`；超限返回 UNKNOWN。这个上限是「查询数换时间」的阀门：上限越松，NO 越可能被证明，但最坏时间越大。

### 7.3 本轮实际分支规模

58 张最终 `branch` 证明合计：

| 指标 | 总和 | 单例最大 |
|---|---:|---:|
| LP 节点 | 194 | 9 |
| 叶子 | 126 | 5 |
| 深度（边） | — | 3 |
| 叶子证书 LP | 126 | 5 |

最坏一例是 `stress` 的 idx 47、$h=34$：9 个 LP 节点、5 个叶子、深度 3。也就是说，在这个语料上 LP-BRANCH 远没有接近 96/24 的上限；但这是经验事实，不是最坏情况保证。

全量 `LP_BB=442` 的构成是：58 张最终 branch 的 194 个节点，加上 46 次 YES 探测和 1 次 UNKNOWN 探测的 248 个节点。全量 `LP_cert=137` 中，126 次来自最终 branch 的叶子，11 次来自未成为最终证明的探测。

### 7.4 GA 复杂度

一次 SGS 解码是 $O(n^2)$（每个任务扫描机器和已有区间），一次 GA 调用的上界是 $O(Bn^2)$，$B=4000$。本轮 full 只调用 GA 一次：

- `evals=2248`，`gens=3`，`t=0.14 s`，`best=41`；
- 该实例是 base 的 `large_het 7`，B&B 返回 UNKNOWN，GA 在 3 代内找到 $C_{\max}=41$ 的调度。

`no_bb` 中 GA 成功 45 次、失败 60 次，总 GA 时间约 16.04 s；失败调用在 $g=1$ 的不可行 $h$ 上会跑满预算。

### 7.5 STAB 复杂度

`_record_proof` 是字典插入；`_ensure_lb_proof` 最多扫描当前 proof store 的键，$O(|\mathcal P|)$，而 $|\mathcal P|\le$ 探测次数（本语料 $\le105$）。`SubsumptionProof` 的 audit 只递归一层 source，成本可忽略。

---

## 8. 实验设计

### 8.1 语料

沿用 v8.1 的三组语料，共 252 例：

| 语料 | $n$ | 说明 |
|---|---:|---|
| base | 141 | 基础族，覆盖多种结构 |
| pert | 60 | 扰动族，LP 分数/舍入边界更多 |
| stress | 51 | 压力族，CHD 的 YES 搜索最坏 |

约束规模为 $n\le21$、$m\le4$、$T\le68$；252 例的整数间隙全在 $\{0,1\}$。每例都有已知最优值 `known`，用于离线验收，不参与算法。

### 8.2 指标

- `certified`：算法是否给出精确认证；
- `opt` / `gap` / `ratio`：与 `known` 的差距；
- `Q`：CHD 调用次数；
- `LP_CHD`：CHD 内部 LP 次数；
- `LP_pin`：LP pin 次数；
- `LP_BB`：LP-BRANCH 节点 LP 次数；
- `LP_cert`：叶子 Farkas 证书 LP 次数；
- `YES_nodes`：CHD 的 YES 侧节点数；
- `time`：单例墙钟，包含 LP、GA、CHD、audit；
- `proof_kind`：最终下界证明类型；
- `audit` / `proof`：独立重放与证明完整性。

### 8.3 对照与消融

- **APEX**：v8.7 原算法，同 runner 复跑；
- **SAGE full**：LP-BRANCH + GA + STAB；
- **`no_ga`**：关闭 GA；
- **`no_bb`**：关闭 LP-BRANCH；
- **`bb_no_only`**：LP-BRANCH 只接受 NO，禁用 B&B YES，让 GA 负责所有 YES。

所有变体使用同一语料、同一 Python 进程、无并行；时间是单次运行，不含置信区间。

### 8.4 复现

```bash
cd /home/runner/work/xuen/xuen/workspace
.venv/bin/python exp/v8i/bench_sage.py      # full + 三组消融
.venv/bin/python exp/v8h/bench_apex.py      # APEX full + 三组消融
```

`bench_sage.py` 会把 full / no_ga / no_bb / bb_no_only 写入 `exp/v8i/bench_sage_*.json`；`bench_apex.py` 的第一个块就是 full。

---

## 9. 主实验结果

### 9.1 APEX vs SAGE

| 指标 | v8.7 APEX | v8.8 SAGE | 变化 |
|---|---:|---:|---|
| 认证 | 252/252 | 252/252 | 不变 |
| $Q$ | 105 | **0** | −105 |
| LP$_{\rm CHD}$ | 874 | **0** | −874 |
| LP$_{\rm pin}$ | 273 | 273 | 不变 |
| LP$_{\rm BB}$ | 0 | 442 | +442 |
| LP$_{\rm cert}$ | 0 | 137 | +137 |
| LP 总计 | 1147 | **852** | −295 |
| YES 节点 | 60001 | **0** | −60001 |
| 时间 | 11.82 s | **9.62 s** | −2.20 s |

同 runner 的 APEX 复跑是 11.82 s；仓库里 `bench_apex_full.json` 记录的是先前 11.86 s 的运行，差异来自机器漂移。SAGE 的 9.62 s 是 252 例 `t` 之和，wall 为 9.63 s。

### 9.2 分语料

| 语料 | $n$ | 认证 | $Q$ | LP$_{\rm CHD}$ | LP$_{\rm pin}$ | LP$_{\rm BB}$ | LP$_{\rm cert}$ | YES 节点 | 时间 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 141 | 141 | 0 | 0 | 120 | 191 | 15 | 0 | 5.51 s |
| pert | 60 | 60 | 0 | 0 | 81 | 78 | 10 | 0 | 1.03 s |
| stress | 51 | 51 | 0 | 0 | 72 | 173 | 112 | 0 | 3.08 s |
| **合计** | **252** | **252** | **0** | **0** | **273** | **442** | **137** | **0** | **9.62 s** |

stress 是变化最大的一组：APEX 的 60k YES 节点主要来自这里；SAGE 用 173 个 LP-BRANCH 节点 + 112 次叶子证书替代，YES 节点归零。

### 9.3 证明类型

| 类型 | 数量 | 含义 |
|---|---:|---|
| `branch` | 58 | LP-BRANCH 的 $\mathrm{NO}(L^*)$ 树 |
| `farkas` | 110 | 单张 Farkas 下界证明 |
| `bound` | 60 | 结构/容量下界 |
| `energy` | 24 | 能量/不等式下界 |
| **合计** | **252** | |

APEX 的 58 张 `oracle` 在 SAGE 中全部变成 `branch`；其余 194 张（110 `farkas` + 60 `bound` + 24 `energy`）与 APEX 完全一致。也就是说，SAGE 没有改变 $g=0$ 的证明形态，只替换了 $g=1$ 的 NO 来源。

### 9.4 引擎归因

SAGE full 的 105 次 probe 分布：

| 引擎 | 结果 | 次数 |
|---|---|---:|
| LP-BRANCH | NO（带 `BranchProof`） | 58 |
| LP-BRANCH | YES | 46 |
| LP-BRANCH | UNKNOWN | 1 |
| GA | YES | 1 |
| GA | NO | 0 |
| CHD fallback | 任意 | 0 |

那 1 次 UNKNOWN 是 base 的 `large_het 7`；GA 用 2248 次唯一 SGS 评估、3 代、0.14 s 找到 $C_{\max}=41$。因此 full 的 $Q=0$ 不是「所有 probe 都一次成功」，而是「唯一失败的那次被 GA 接住了」。

---

## 10. 消融

| 变体 | $Q$ | LP$_{\rm CHD}$ | LP$_{\rm pin}$ | LP$_{\rm BB}$ | LP$_{\rm cert}$ | YES 节点 | 时间 | GA yes/no | CHD 调用 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **SAGE full** | **0** | **0** | 273 | 442 | 137 | 0 | **9.62 s** | 1/0 | 0 |
| `no_ga` | 1 | 13 | 273 | 442 | 137 | 0 | 9.71 s | 0/0 | 1 |
| `bb_no_only` | 2 | 24 | 273 | 442 | 137 | 0 | 13.21 s | 45/2 | 2 |
| `no_bb` | 60 | 412 | 273 | 0 | 0 | 60001 | 24.65 s | 45/60 | 60 |

### 10.1 `no_ga`

关闭 GA 后，base `large_het 7` 的 B&B UNKNOWN 没有上界补件，退回 CHD：

- $Q=1$，CHD 内部 13 次 LP；
- 时间 9.71 s（比 full 多 0.09 s）；
- 证明类型不变（58 `branch`），说明 GA 只负责那 1 个 YES。

这是最轻的消融，说明 GA 在当前语料上不是主力，但它是 $Q=0$ 的最后一根钉子。

### 10.2 `bb_no_only`

LP-BRANCH 只证 NO，禁用 B&B 的 YES，让 GA 负责所有 YES：

- $Q=2$，CHD 24 次 LP，时间 13.21 s；
- GA 成功 45 次、失败 2 次；
- 两个失败是 base `large_het 3` 与 `large_het 5`（都是 $g=0$），最终退回 CHD；
- 58 个 $g=1$ 仍然全部由 `branch` 证明，$Q$ 只剩这两个 YES 尾例。

这说明 LP-BRANCH 的 NO 侧可以独立承担 58 个实例；没有 B&B YES 时，GA 的上界能力差两个尾例。

### 10.3 `no_bb`

关闭 LP-BRANCH：

- $Q=60$，CHD 412 次 LP，YES 节点回到 60001，时间 24.65 s；
- GA 成功 45 次、失败 60 次；
- 58 个 $g=1$ 全部退回 CHD（`oracle` 证明），2 个 $g=0$ 也退回 CHD；
- 最终证明类型变为 `oracle=58`、`farkas=110`、`bound=60`、`energy=24`。

这个变体看起来 LP 总数只有 $273+412=685$，比 full 的 852 少，但时间从 9.62 s 涨到 24.65 s，YES 节点从 0 涨到 60001。**LP 计数不是目标函数；CHD 的 YES 搜索才是墙钟杀手。** 这也是为什么 SAGE 用 LP-BRANCH 换掉 CHD，而不是用 GA 换掉 CHD。

### 10.4 贡献排序

1. **LP-BRANCH 是主贡献**：没有它，$Q=60$、YES=60001、时间 24.65 s；有它，58 个 NO 全部变成 3–9 节点的证书树，YES 归零。
2. **GA 是补件**：只消除 1 次 CHD，但它是 full 达到 $Q=0$ 的必要条件；没有它，$Q=1$。
3. **STAB 是闭合器**：它不直接减少查询，但把 $\mathrm{NO}(L^*)$ 接到 $\mathrm{LB}(L^*+1)$，让最终 `MEET` 不再补问；没有它，`branch` 证明无法转成最终下界。

---

## 11. 证明审计与篡改测试

### 11.1 独立重放

`BranchProof.audit_rdf()` 从根开始，用空 $F$ 重放整棵树：

- 每个内部节点检查 $(i,m)$ 是否把当前允许域切成两个非空部分；
- 每个子节点检查 $F$ 是否恰好是父 $F$ 加对应半区；
- 每个叶子调用 `verify(inst, h, cert, forbid=F)` 或检查空域；
- 不读取生成时的 LP 状态、bounds 或 `no_states`。

因此 `audit_rdf()` 是证明对象的自包含检查，不是「信任生成器」。

### 11.2 篡改

手工修改证明对象后：

- 修改叶子 `alpha` 或 `beta` 的某个分量 → `verify` 返回 False → `audit_rdf()` 返回 False；
- 修改内部节点的 `mid` → 子 $F$ 与重新计算的分区不一致 → `audit_rdf()` 返回 False；
- 删除/替换某个叶子证书 → 检查失败或叶子数不匹配。

这些测试只针对证明对象，不针对 LP 求解器；它们说明 `BranchProof` 的检查器确实在做结构性校验，而不是只查一个布尔标志。

### 11.3 `SubsumptionProof`

`SubsumptionProof.audit_rdf()` 检查：

\[
\mathtt{source}\ne\mathtt{None}\quad\land\quad
\mathtt{source.h}\ge\mathtt{self.h}\quad\land\quad
\mathtt{source.audit\_rdf()}.
\]
因此它只能把更强的 NO 传给更弱的 $h$，不能反向。

### 11.4 `ok` 与 `certified`

full 的 252 例全部 `ok=True`、`certified=True`、`audit=True`、`proof=True`，且 `cert_h=known-1`。`ok` 使用 `known` 做离线验收；`certified`/`audit`/`proof` 不依赖 `known`。

---

## 12. 讨论

### 12.1 为什么不是「APEX + 更快的 oracle」

如果只是把 `sdecc_no` 当黑箱 oracle，能消掉 YES 节点，但证明不可重放，且会破坏 APEX 的 soundness 叙事。SAGE 的 `branch` 是一等判断：

- 它携带完整的 $F$ 分区；
- 它能在不运行 LP 的情况下被 `audit_rdf` 重放；
- 它能被 `SubsumptionProof` 接到最终下界；
- 它能被 `STAB` 的 `NO-LB` 规则消费。

因此 $Q=0$ 不是「oracle 变快了」，而是「NO 从搜索副产品变成了证明对象」。

### 12.2 为什么不是「GA 替换 CHD」

`no_bb` 已经给出反例：GA 能造 45 张 YES，但 58 个 $g=1$ 仍要 CHD，$Q=60$、YES=60001、24.65 s。GA 是上界构造器，不是下界证明器；它无法证明「不存在 $C_{\max}\le h$ 的调度」。

### 12.3 为什么 `Q=0` 仍可能变慢

`Q` 只数 CHD 调用。LP-BRANCH 的 LP 次数、GA 的 SGS 次数、证明 audit 都不计入 $Q$。在 full 中这些成本低于 APEX 的 CHD，所以时间也降了；但在更难的实例上，LP-BRANCH 可能指数爆炸，GA 可能跑满预算，`Q=0` 可能伴随更长的时间。**查询数与墙钟不是同一个目标。**

### 12.4 STAB 的边界

STAB 的抽象是单调闭包，但实现是「按需闭包」：只为最终需要的 $v-1$ 找证明，不预生成所有 $h$。这样做省时间，但也意味着 `proof store` 不是全局最小不动点；如果未来要在交互式证明里查询任意 $h$，需要显式跑全量闭包。

---

## 13. 已知风险与限制

1. **最坏指数级**：LP-BRANCH 的叶子数最坏是 $\prod_i|D_i(h)|$。本语料最大只有 9 个节点/5 个叶子，但新语料可能完全不同；caps 触发时 $Q$ 会回来。
2. **Farkas 证书的数值稳定性**：`verify` 用浮点与容差；若 LP 退化或证书系数病态，可能出现 `verify` 失败，LP-BRANCH 返回 UNKNOWN，退回 CHD。
3. **GA 无完备性**：`no_bb` 中 GA 失败 60 次；`bb_no_only` 中 GA 漏 2 个 $g=0$。GA 的成功依赖预算、种子和实例结构。
4. **语料小**：$n\le21$、$m\le4$、$T\le68$，且所有 $g\in\{0,1\}$；没有 PSPLIB、没有更大规模、没有多峰分布。$Q=0$ 不能外推到一般实例。
5. **单次运行**：时间是单次共享 runner 的墙钟，没有置信区间；APEX 与 SAGE 同 runner 复跑只能降低机器漂移，不能消除。
6. **`known` 的使用**：`ok` 用 `known` 验收；生产环境没有 `known`，必须依赖 `certified`/`audit`/`proof`。
7. **STAB 是按需闭包**：不是全局最小不动点；若未来需要任意 $h$ 的查询，要补全量闭包。
8. **LP-BRANCH 的完备性依赖 caps**：caps 越松越完备，但越慢；当前 96/24 是本语料的经验选择，没有理论最优性。
9. **没有形式化验证**：正确性论证是纸面 + 运行时 audit，没有 Coq/Lean/Isabelle 机器证明；`verify` 和 `check_schedule` 本身也是 Python 代码。
10. **GA 预算与时间**：full 只有 1 次 GA（0.14 s），但 `no_bb` 的 GA 总时间约 16.04 s；如果新语料有大量 B&B UNKNOWN，GA 会成为新的墙钟瓶颈。

---

## 14. 最大风险（一句话）

**$Q=0$ 不是免费的：它把 CHD 换成了最坏指数级的 LP-BRANCH；如果新语料上分支树或叶子 Farkas 证书爆炸，SAGE 会同时失去 APEX 的查询数优势和墙钟优势。**

---

## 15. 本轮结论（一句话）

**SAGE-ALC 用「LP-BRANCH 证 NO + GA 造 YES + STAB 闭合」把 APEX 的 105 次 CHD 全部消掉，在 252 例上做到 $Q=0$、YES 节点 0、9.62 s 且 252/252 认证；代价是 NO 侧变成最坏指数级的分支证明，必须用 caps 和 fallback 控制风险。**
<!-- ARTIFACT:END -->
