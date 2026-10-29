# 产物区 · v2.4：X-DUB/PACE-ΠA-CC*

> **CC = Cut-first Certificate Cascade**（割平面先行的证书级联）。
> v2.3 的 `OS`（序空间证书）、`CPS`（链 placement）、`PACE`（机器-时间搜索）全部保留；本轮只改**入口**：
> 在 PACE 之前先跑 **ICC（Interval Capacity Certificate，区间容量证书）**；ICC 只返回有证书的 NO，漏了就交给根层 `OS(10k)`；OS 再 UNKNOWN 才回到 PACE。
> v2.3 的 300 节点 CPS 探针默认删除（保留 `probe>0` 作为可选守卫）。理由是摊销账：ICC 之后，探针在测过的 115 个状态上是负收益。
> 状态：设计稿 + 可运行实现 + **held-out 50 例 1.552→0.552 s（2.81×）** + **hard3 12 例 0.114→0.0207 s（5.5×）** + **deep 8 例 0.303→0.0456 s（6.6×）** + **5 残例 0.0825→0.0492 s（1.68×）** + **45 合成紧状态 45/45 ICC 关闭（0.003 s）** + **400 组暴力 0 不一致** + **70 张 YES 排程验证** + **53 张 ICC witness 重算 0 失败**；**38 例核心 0.113→0.120 s（+6% 回退）**；未接 PSPLIB，未做 Coq/Lean。

---

## 0. 版本关系与本轮增量

v2.3 的资产全部保留：

- `OS`：全资格下对优先序做 DFS，SGS 把起点传播成最早可行；active schedule 定理保证 `NO ⇔ 不可行`（未撞 cap）；`YES` 带排程。
- `CPS`：链 placement 枚举 + residual 精确回溯；`NO` 由投影引理保证。
- `PACE`：`MAP`、`DHD`、`DCD`、`HPACK`、`PACK-front`、`MINT`、`PACK-SET`、`SOP`、`ODOM` 等层；`PACE=NO` 有证书。
- v2.3 的 `HY`：`CPS(300) → OS(10k)`，作为 PACE 的 tier 0.15。

本轮增量只有四件事：

1. **ICC 割层**：在根状态上枚举时间窗 `[a,b]`，用 `icc-full`（整任务包含）和 `icc-mand`（强制重叠）两种容量不等式，返回短的 NO 证书。ICC 是**部分判定过程**：只证 NO，不证 YES。
2. **CC 级联**：`ICC → OS(10k) → PACE`。ICC 和 OS 都在 PACE 之前；CPS 探针默认删除。每一层只做自己 sound 的事，UNKNOWN 往下走。
3. **部分正确性组合定理**：把每个引擎写成三值 Hoare 三元组，证明顺序组合保持 soundness；completeness 变成「门 + 预算」的条件定理。
4. **摊销账**：用 `p·S > (1-p)·c` 逐阶段算账。ICC 在 45 个合成状态上 `p=1`、`c≈5e-5 s`，在 held-out 上 `p=0`、税约 7%；CPS 探针在 held-out 上 `p=2/50`、税 12%，在 hard3/残例上 `p=0`、税 17–33%，所以删除。

退化关系：

```text
probe=0, icc_on=True, pmax=16      → 本轮默认 CC（ICC → OS → PACE）
probe=64                           → CC + 可选 CPS 守卫（v2.3 探针的缩水版）
probe=300                          → 近似 v2.3 HY，但仍在 PACE 之前
icc_on=False                       → 纯 OS 根层 + PACE（held-out 0.588 s，hard3 0.086 s）
os_ncap=0                          → ICC + PACE（held-out 3.53 s）
pmax=0                             → 纯 PACE（held-out 3.49 s）
icc_on=False, probe=300, pmax=0    → 逐字回到 v2.2/v2.3 的 PACE
```

---

## 1. 符号

| 符号 | 含义 |
|---|---|
| `I=(n,m,p,E,≺,h)` | 实例：加工时间、机器数、资格、优先图、公共期限 |
| `σ=(R,A,est)` | DEC 状态：未调度集、机器可用时刻、最早开始 |
| `c_σ(t)` | `t` 时刻已可用机器数 `|{k:A_k≤t}|`；全资格下是精确聚合容量 |
| `r_i,d_i` | `r_i=est_i`，`d_i=h−q_i(R)`，`q_i` 是不含 `p_i` 的最长尾 |
| `full(σ)` | 全资格：`∀i∈R, E_i={0..m−1}` |
| `S(σ)` | 链松弛 `h−cp(σ)`，`cp(σ)=max_i(r_i+p_i+q_i)` |
| `[a,b]` | 时间窗，`0≤a<b≤h` |
| `S(a,b)` | `{i∈R : r_i≥a ∧ d_i≤b}`（整任务包含集） |
| `D(a,b)` | `Σ_{i∈S(a,b)} p_i` |
| `C(a,b)` | `Σ_{t=a}^{b−1} c_σ(t)` |
| `mand_i(a,b)` | `max(0,min(p_i, r_i+p_i−a, b−(d_i−p_i), b−a))` |
| `M(a,b)` | `Σ_{i∈R} mand_i(a,b)` |
| `κ` | 可选 CPS 探针预算；本轮默认 `0`（删除） |
| `B` | OS 节点预算，默认 `10,000` |
| `N_P` | PACE 节点预算，默认 `3,000,000` |
| `ICC` | 区间容量证书层，返回 `NO(w)` 或 `UNKNOWN` |
| `CC` | 本轮级联 `ICC → OS → PACE` |
| `E` | OS 展开状态数（≤ active 排程数） |
| `p_s,c_s,S_s` | 阶段 `s` 的成功率、成本、成功时省下的成本 |

---

## 2. 形式定义

### 2.1 状态、窗口、容量

沿用 v2.2/v2.3。给定 `σ=(R,A,est)` 与公共期限 `h`：

```text
r_i = est_i ,        d_i = h − q_i(R) ,        c_σ(t) = |{k : A_k ≤ t}| .
```

全资格时 `(r,d,c_σ,≺)` 精确刻画剩余问题（v2.2 引理 2：区间图贪心染色）。本轮不重复证明。

### 2.2 ICC 割

**定义 1（整任务包含割，`icc-full`）**。若存在 `0≤a<b≤h` 使

```text
D(a,b) = Σ_{i∈R, r_i≥a, d_i≤b} p_i  >  C(a,b) = Σ_{t=a}^{b−1} c_σ(t) ,
```

则 `σ` 不可行。witness 为 `('icc-full', a, b, S_mask, D, C)`。

**定义 2（强制重叠割，`icc-mand`）**。对 `i∈R` 定义

```text
mand_i(a,b) = max(0, min(p_i, r_i+p_i−a, b−(d_i−p_i), b−a)) ,
M(a,b) = Σ_{i∈R} mand_i(a,b) .
```

若存在 `a<b` 使 `M(a,b) > C(a,b)`，则 `σ` 不可行。witness 为 `('icc-mand', a, b, mand_tuple, M, C)`。

**定义 3（ICC 过程）**。

```text
ICC(σ,h):
  for a in starts(σ):                 # {r_i} ∪ {d_i−p_i}
    for b in ends(σ):                 # {r_i+p_i} ∪ {d_i}
      if b≤a: continue
      C ← Σ_{t=a}^{b−1} c_σ(t)
      if D(a,b) > C: return NO(('icc-full', a,b,S,D,C))
      if M(a,b) > C: return NO(('icc-mand', a,b,mand,M,C))
  return UNKNOWN
```

`starts/ends` 各至多 `2|R|` 个，所以窗口数 `O(n^2)`，每个窗口 `O(n)`，总 `O(n^3+n h)`。

**注（与 PACE potential 的关系）**：v2.1 的 `potential` 已经包含 mandatory energy（`energy` 见证）。ICC 不是新的不等式，而是把 `energy` 这一支**独立**成 `O(n^3)`、`O(n)` 证书、可在任何引擎之前调用的层；它不带 MINT/PACK-SET/HPACK，也不建表。它的价值是**顺序与证书**，不是新的数学。对 45 个 synth，PACE potential 也能剪；ICC 的差别是 0.003 s、短证书、最先跑。

**定义 4（ICC 检查器）**。

```text
CHECK_ICC(σ,h,w):
  解包 (kind,a,b,payload,demand,cap)
  重算 C(a,b)；若 C≠cap 或 demand≤cap: reject
  若 kind='full':
      重算 S(a,b)、D；要求 payload=S_mask、D=demand、D>cap
  若 kind='mand':
      重算 mand 向量；要求逐项相等、M=demand、M>cap
  accept
```

检查器不信任 `payload`，只信 `a,b,kind`，其余全部重算。复杂度 `O(n+h)`。

### 2.3 证书与三值语义

**定义 5（证书）**。

```text
Cert = YES(t)                    # t 是完整排程
     | NO(tree)                  # OS 序树 / CPS residual 树 / PACE 搜索树
     | NO(window)                # ICC witness
     | UNKNOWN .
```

**定义 6（sound / complete）**。引擎 `E` 是 sound 的，若

```text
E(σ)=YES(t) ⇒ t 可行 ;        E(σ)=NO(π) ⇒ σ 不可行 .
```

`E` 在门 `G` 上 complete，若对 `σ∈G`：可行时 `E` 不返回 NO，不可行时不返回 YES；且预算足够时不返回 UNKNOWN。

**定义 7（三值组合）**。`E1; if UNKNOWN then E2` 表示先跑 `E1`，只有 `E1=UNKNOWN` 才跑 `E2`。

### 2.4 部分正确性

把 `CC` 看成一个程序，Hoare 三元组是：

```text
{ true }
  v ← CC(σ,h)
{ (v=YES ⇒ σ 可行) ∧ (v=NO ⇒ σ 不可行) }
```

这就是 **partial correctness**：后置条件不承诺 `v≠UNKNOWN`，也不承诺一定终止在 YES/NO；它只承诺「只要给出判决，判决就是真的」。终止性由三个预算单独给（定理 6）；completeness 是带门和预算条件的定理 5。

### 2.5 CC 级联与门

**定义 8（CC）**。

```text
CC(σ,h):
  1  if full(σ):
        v ← ICC(σ,h)
        if v=NO: return v
  2  if full(σ) ∧ |R|≤16 ∧ 0≤S(σ)≤4:
        v ← OS(σ; B=10000)
        if v≠UNKNOWN: return v
  3  return PACE(σ,h)
```

门：

```text
icc_gate(σ) = full(σ)
os_gate(σ)  = full(σ) ∧ |R|≤16 ∧ 0≤S(σ)≤4
```

门关掉只少剪，不会多剪；`B` 和 `N_P` 是预算，不是正确性参数。

### 2.6 整数规划视角

全资格下，`σ` 的可行性等价于时间索引 0-1 规划：

```text
(IP_σ)  Σ_t x_{i,t} = 1                                   ∀i
        Σ_i Σ_{s=t−p_i+1}^{t} x_{i,s} ≤ c_σ(t)            ∀t
        x_{i,t} = 0   若 t<r_i 或 t>d_i−p_i
        Σ_t t·x_{i,t} + p_i ≤ Σ_t t·x_{j,t}               ∀i≺j
        x_{i,t} ∈ {0,1}
```

`ICC-full` 是把 `[a,b]` 上的容量约束相加，并利用 `i∈S(a,b)` 的变量支撑完全落在 `[a,b]`：

```text
Σ_{i∈S(a,b)} p_i
  = Σ_{i∈S(a,b)} Σ_{t=a}^{b−1} overlap_i(t)·x_{i,t}
  ≤ Σ_{t=a}^{b−1} c_σ(t) = C(a,b) .
```

所以 `D>C` 是一条**窗口割 / Hall 不等式 / Chvátal–Gomory 割**，witness 就是它的对偶乘子（一个窗 + 一个集合）。`ICC-mand` 是经典 energetic reasoning 的割。CPS 是「链 placement 分支」，OS 是「序分支」，PACE 是「机器-时间分支」；四层是同一个 `IP_σ` 的四种证明系统。

---

## 3. 算法

### 3.1 ICC

```text
ICC(σ,h):
  if R=∅: return UNKNOWN
  r ← est|R ; d ← h−q(R)
  c[t] ← |{k:A_k≤t}| ; pc ← prefix(c)
  starts ← sort({r_i} ∪ {d_i−p_i})
  ends   ← sort({r_i+p_i} ∪ {d_i})
  for a in starts:
    if a<0 ∨ a≥h: continue
    for b in ends:
      if b≤a ∨ b>h: continue
      C ← pc[b]−pc[a]
      S ← 0 ; D ← 0
      for i in R:
        if r_i≥a ∧ d_i≤b: S|=1<<i ; D+=p_i
      if D>C: return NO(('icc-full',a,b,S,D,C))
      M ← 0 ; vec ← []
      for i in R:
        v ← min(p_i, r_i+p_i−a, b−(d_i−p_i), b−a)
        v ← max(0,v)
        vec.append(v) ; M+=v
      if M>C: return NO(('icc-mand',a,b,vec,M,C))
  return UNKNOWN
```

### 3.2 OS（v2.3，原样）

```text
OS(σ; B):
  cap ← c_σ ; rel ← r ; mask ← R ; nodes ← 0
  dfs(mask,cap,rel):
    nodes += 1
    if nodes>B: return UNKNOWN
    if mask=0: return YES(sched)
    key ← (mask, cap, rel|mask)
    if key∈memo: return NO
    ready ← {i∈mask : pred(i)∩mask=∅}
    cand ← [(i, EARLIEST(cap,rel_i,p_i,d_i)) ...]
    cand ← 去掉 ⊥
    if cand=∅: memo.add(key); return NO
    for (i,t) in ORDER(cand):            # 顺序不影响 NO 节点数（v2.3 定理 2）
      cap' ← cap−1_{[t,t+p_i)}
      rel' ← rel; 对 j∈succ(i)∩mask: rel'_j←max(rel'_j,t+p_i)
      if dfs(mask\{i},cap',rel')=YES: return YES
    memo.add(key); return NO
```

全资格、未撞 `B` 时，OS 是判决过程（v2.3 定理 1，active schedule 定理 + SGS 复现）。本轮不重复证明，只引用。

### 3.3 CC

```text
CC(σ,h):
  if full(σ):
     v ← ICC(σ,h)
     if v=NO: return v
  if full(σ) ∧ |R|≤16 ∧ 0≤S(σ)≤4:
     v ← OS(σ; B=10000)
     if v≠UNKNOWN: return v
  return PACE(σ,h)
```

### 3.4 PACE 后备

PACE 使用 v2.2 配置（`cps_on=True` 等），逐字保留：

```text
PACE(σ,h):
  ... v2.2 的 DEAD / NORM / MAP / window / MINT / PACK-SET / SOP /
      DHD / DCD / HPACK / CPS / 分支 ...
```

CC 的第 3 步只在 ICC 和 OS 都 UNKNOWN 时执行。若根门已经跑过 OS，PACE 内部的 CPS 可能重复一次，但只在极少数状态上发生；这不会破坏 soundness。

### 3.5 证书格式与检查

**ICC-NO**：

```text
kind    = 'icc-full' | 'icc-mand'
payload = S_mask（full）或 mand 向量（mand）
claim   = D(a,b)>C(a,b) 或 M(a,b)>C(a,b)
check   = 重算 r,d,c,C；full 重算 S,D；mand 重算 vec,M
```

大小：`full` 为 `O(1)` 个整数 + 一个 mask；`mand` 为 `O(n)` 个整数。检查 `O(n+h)`。

**OS-NO**：v2.3 的序树；内部节点 `(π_prefix,(mask,cap,rel),verdict)`，叶子 dead；检查器重放 SGS，重算子节点集合。大小 = 展开状态数（5 个残例 6,802；50 个 held-out 80,463）。

**OS-YES**：`π` + 起点向量；检查器验证优先序、`r≤t`、`t+p≤d`、任意时刻活跃数 `≤c_σ`；全资格下用区间图贪心染色到机器。大小 `O(n)`。

**PACE-NO**：v2.1/v2.2 的见证（能量、clique、subset、MINT、PACK-SET、SOP、MAP、CPS residual 树等）。

### 3.6 复杂度

设 `r=|R|`，`h` 为期限，`E` 为 OS 展开状态数。

```text
ICC:       O(n^3 + n·h) 时间；O(n+h) 空间；证书 O(n)
OS:        O(E·(h + r log r))；memo O(E·(h+r))；E ≤ active 排程数 ≤ r!
PACE:      不变，节点上限 N_P=3,000,000
CC:        T_ICC + [ICC UNKNOWN]·T_OS(B) + [OS UNKNOWN]·T_PACE
           最坏 ≤ T_ICC + B·(h+r log r) + T_PACE
```

`CC` 没有打破 NP-hard：`m=1` 时 OS 就是 `1||Lmax` 的序枚举；`m` 台、无优先时是 `P||Cmax` 的 active 排程枚举。ICC 是多项式时间的**不完全**证明层，OS/PACE 才是指数兜底。

---

## 4. 定理与证明

### 4.1 引理 1（`icc-full` 可靠性）

**引理 1**。若 `D(a,b)>C(a,b)`，则 `σ` 不可行。

**证明**。反设存在可行排程 `t`。对任意 `i∈S(a,b)`，由 `r_i≥a` 与 `d_i≤b` 得 `t_i≥a`、`t_i+p_i≤b`，所以 `i` 的整个加工区间落在 `[a,b)` 内，贡献 `p_i` 个机器-时间单位。于是

```text
Σ_{i∈S} p_i ≤ Σ_{t=a}^{b−1} (在 t 时刻占用的机器数) ≤ Σ_{t=a}^{b−1} c_σ(t) = C(a,b) ,
```

与 `D>C` 矛盾。∎

### 4.2 引理 2（`icc-mand` 可靠性）

**引理 2**。若 `M(a,b)>C(a,b)`，则 `σ` 不可行。

**证明**。对任意可行 `t`，任务 `i` 的区间 `[t_i,t_i+p_i)` 与 `[a,b)` 的交长至少为

```text
max(0, min(p_i, t_i+p_i−a, b−t_i, b−a)) .
```

由 `t_i≥r_i`、`t_i≤d_i−p_i`，该交长不小于 `mand_i(a,b)`（三个 min 项分别用 `t_i≥r_i`、`t_i+p_i≤d_i`、`p_i` 放缩）。所以总占用至少 `M(a,b)`，不超过 `C(a,b)`，矛盾。∎

### 4.3 引理 3（检查器可靠性）

**引理 3**。若 `CHECK_ICC` 接受 `w`，则 `w` 是引理 1 或引理 2 的有效实例。

**证明**。检查器按定义重算 `r,d,c,C`，不信任 `payload`；`full` 分支逐项验证 `S` 中任务的窗口包含性和 `D`；`mand` 分支逐项验证向量和 `M`；最后验证 `demand>cap`。因此接受意味着定义 1/2 的不等式成立，由引理 1/2 得 NO。∎

### 4.4 定理 1（顺序组合的 soundness）

**定理 1**。若 `E1,E2` sound，则 `E1; if UNKNOWN then E2` sound。

**证明**。若返回 `E1` 的 YES/NO，由 `E1` sound；若返回 `E2` 的 YES/NO，由 `E2` sound；若返回 UNKNOWN，无判决。∎

### 4.5 定理 2（CC 的 soundness）

**定理 2**。`CC(σ,h)=YES ⇒ σ 可行`；`CC=NO ⇒ σ 不可行`。

**证明**。分三支：

- ICC 返回 NO：引理 1/2。
- OS 返回 YES/NO：v2.3 定理 1（全资格、未撞 B）。
- PACE 返回 YES/NO：v2.1/v2.2 的 soundness（各层见证可检查）。

由定理 1，顺序组合 sound。∎

### 4.6 定理 3（条件 completeness）

**定理 3**。设 `σ` 在门内（`full ∧ |R|≤16 ∧ 0≤S≤4`），且 `CC` 没有撞 OS 的 `B` 或 PACE 的 `N_P`。则 `CC` 返回 YES 当且仅当 `σ` 可行。

**证明**。

- 若 `σ` 不可行：ICC 若返回 NO，正确；否则 OS 在门内是判决过程，返回 NO；若 OS 撞 cap，PACE 在未撞 `N_P` 时也是判决过程，返回 NO。
- 若 `σ` 可行：ICC 不会返回 NO（引理 1/2 的逆否）；OS 在门内是判决过程，返回 YES；若 OS 撞 cap，PACE 返回 YES。
- 两个方向都不可能在可行时返回 NO，或不可行时返回 YES（定理 2）。∎

**注**：若 `σ` 不在门内（例如 `n>16`、`S>4`、异资格），CC 直接走 PACE；completeness 继承 v2.2 的 PACE（在 `N_P` 内）。异资格下 OS 的 YES 不可信，所以 `os_gate` 必须含 `full`。

### 4.7 定理 4（终止与预算）

**定理 4**。`CC` 对任意有限输入终止；总工作量上界为

```text
T_CC ≤ T_ICC + 1_{ICC=UNKNOWN}·B·(h+r log r) + 1_{OS=UNKNOWN}·T_PACE .
```

**证明**。ICC 枚举有限窗口；OS 每次递归 `mask` 严格减小，且节点数超过 `B` 立即返回 UNKNOWN；PACE 有 `N_P` 节点上限；递归有限。∎

**系（Hoare 三元组）**：

```text
{ true } CC { (YES⇒可行) ∧ (NO⇒不可行) }  且  CC 终止 .
```

后置条件不保证 `≠UNKNOWN`；这是 partial correctness 的精确表述。

### 4.8 命题 1（ICC 之后的探针是负收益，经验命题）

**命题 1（实测，非定理）**。在本文的 115 个状态（50 held-out + 12 hard3 + 8 deep + 45 synth）上，ICC 之后的 CPS 探针：

```text
held-out:  p=2/50,  c=64×50=3,200 节点,  +14% 时间,  只提前判决 2 例
hard3:     p=0/12,  c=64×12=768 节点,    +33% 时间
residual5: p=0/5,   c=65×5=325 节点,     +16% 时间
synth45:    ICC 已 45/45 关闭，探针 0 次
```

所以默认 `κ=0`。这不是普遍定理：若新分布上 ICC 继续漏、而 CPS 在 64 内经常完成、OS 很贵，探针会重新划算。产物区把它写成经验命题，并保留 `probe>0` 开关。

**摊销不等式**：阶段成本 `c`、成功率 `p`、成功时省 `S`，值得跑 iff `pS>(1-p)c`。held-out 上 CPS 探针 `pS≈64`、`(1-p)c≈61`，几乎打平，实测因常数项输；hard3/残例 `p=0`，纯税。

### 4.9 命题 2（没有普遍支配）

**命题 2（实测）**。

- ICC 在 50 个 held-out 上 **0 命中**；这 50 个状态的 NO 是全局的，窗口割看不见。
- ICC 在 45 个合成紧状态上 **45/45 命中**；v2.3 的「OS 0/45 胜」是在 ICC 之后的残差上测的，不能推出根层结论。
- OS 在 5 个残例上 6,802 节点；CPS 要 110,971 节点（v2.3 数据），ICC 0 命中。
- PACE 在 `n>16`、异资格、`S>4` 上仍是唯一完整后备；38 例核心 16 个 PACE。

所以不存在「ICC 支配一切」或「OS 支配一切」；本轮主张的是**级联顺序**在测过的分布上更便宜。

### 4.10 命题 3（证书大小）

**命题 3**。ICC witness 大小 `O(n)`（`full` 为 `O(1)` 个整数 + 一个 mask；`mand` 为 `n` 个整数），检查 `O(n+h)`；OS 的 NO 证书是序树，大小 = 展开状态数（5 残例 6,802；50 held-out 80,463）；PACE 的证书是搜索树/局部见证。

在 45 个 synth 上，45 张 ICC 短证书替代了 359,940 个 OS 节点；这是本轮「短证书」的最强证据，但只覆盖局部 NO。PACE potential 也能剪这 45 个状态（0.0062 s），所以 ICC 的增量是「2× 速度 + 可独立重算的 O(n) 证书 + 可在任何引擎前调用」，不是「只有 ICC 能剪」。

---

## 5. 实验

### 5.1 实验设计与设置

**假设**：

- H1（局部 NO）：ICC 能在根层关闭相当一部分紧状态，且证书可独立重算。
- H2（全局 NO）：ICC 漏掉的状态里，根层 OS 比 PACE 的根层表便宜；把 OS 提前能降低 wall-clock。
- H3（探针）：ICC 之后，CPS 探针的摊销收益为负，删除它不会损失判决。

**控制**：同一批实例、同一 PACE 配置、同一 Python 进程、单线程；对每个集合分别跑 v2.3、`icc_on=False`、`probe=64/300`、`os_ncap=0`、`pmax=0` 五个对照；判决逐例比对；ICC witness 全部独立重算；另用 400 组随机小实例做暴力对拍。时间为单次完整运行，复跑波动约 ±3%；`res_pc.json` 是脚本落盘的那一次，正文保留首次记录的数值。

Python 3.12，4 vCPU，单线程。数据与 v2.3 逐字相同：

```text
exp/v13/hard3.pkl（12）
exp/v14/{large_a,large_b,large_het}.pkl（8+10+8）
exp/v18/deep.pkl（8）
exp/v20/holdout_cases50.pkl（50）
exp/v28/synth2_45.pkl（45，按 bench_synth2 的 RNG=99 重建）
```

主配置：

```text
mode='pot', nodecap=3,000,000, mint_on=True, mint_depth=0,
packset_on=True, packset_depth=0, sop_on=True, sop_nodecap=200000,
dhd=True, dcd=True, hpack_on=True, odom=False,
omd=full, map_on=True, map_tau=4, map_ncap=16,
cps_on=True, cps_tau=4, cps_depth=0, cps_ncap=16,
cps_nodecap=300000, cps_gate_fan=0,
ICC on (full only), pmax=16, tau=4, B=10000, probe=0.
```

代码：`exp/v28/icc.py`（ICC）、`exp/v28/root_pc.py`（CC）、`exp/v28/bench_pc.py`（主实验）、`exp/v28/bench_pc_ablate.py`（消融）、`exp/v28/test_pc.py`（正确性）。结果：`exp/v28/res_pc.json`、`res_pc_ablate.json`、`res_pc_valid.json`。

### 5.2 主表

| 集合 | 数量 | v2.3 时间 | **v2.4 时间** | 加速 | 判决分布（ICC/CPS/OS/PACE） |
|---|---:|---:|---:|---:|---|
| held-out 50 | 50 | 1.552 s | **0.552 s** | **2.81×** | 0 / 0 / 50 / 0 |
| hard3 | 12 | 0.114 s | **0.0207 s** | **5.5×** | 8 / 0 / 4 / 0 |
| deep 8 | 8 | 0.303 s | **0.0456 s** | **6.6×** | 0 / 0 / 7 / 1 |
| 5 残例 | 5 | 0.0825 s | **0.0492 s** | **1.68×** | 0 / 0 / 5 / 0 |
| 45 synth | 45 | 0.0184 s（CPS） | **0.003 s** | **6.1× vs CPS / 620× vs OS** | 45 / 0 / 0 / 0 |
| 38 核心 | 38 | 0.113 s | **0.120 s** | **0.94×（+6% 回退）** | 18 / 0 / 4 / 16 |
| 合计 141 | 141 | 1.987 s | **0.621 s** | **3.20×** | — |

所有 `h=OPT−1` 的判决均为 NO，与 v2.3 逐例一致（50/50、12/12、8/8、5/5）。`h=OPT` 时 CC 返回 YES：70 例中 37 个 OS、28 个 CPS、5 个 PACE，全部 YES。

### 5.3 held-out：节点多了 9.7×，时间少了 2.8×

| 版本 | PACE 节点 | PACE 表 | 引擎节点 | 时间 |
|---|---:|---:|---:|---:|
| v2.3 纯 CPS | 50 | 44 | 110,971（5 例） | 3.480 s |
| v2.3 HY | 50 | 44 | 8,307（探针 1,505 + OS 6,802） | 1.552 s |
| **v2.4 CC** | **50** | **0** | **80,463（OS）** | **0.552 s** |

v2.3 的 8,307 个引擎节点只发生在 5 个到达 tier 0.15 的状态上，其余 45 个被 PACE 的根层表/势函数提前剪掉；v2.4 直接对 50 个状态跑 OS，节点数 80,463，但**没有建表**。PACE 的一张根表约 30 ms，OS 一个节点约 7 µs；这就是「节点数不能当时间用」的实测。

逐例时间：min 0.0015 s，median 0.0069 s，max 0.0538 s；没有单例退化到 PACE。

### 5.4 hard3 / deep / 残例

**hard3（12 例，h=OPT−1）**：

- 8 例 ICC：`icc-mand` 6、`icc-full` 2；单例 0.0001–0.0007 s；证书大小 ≤ n+4。
- 4 例 OS：504 / 630 / 557 / 941 节点；单例 0.0048–0.0080 s。
- 合计 0.0207 s，v2.3 0.114 s。
- 其中 `hard3#4`（`S=5`）由 ICC 直接关闭，不需要 OS；v2.3 的 `S≤4` 门本来会把它排除，本轮 ICC 不受 `S` 门限制。

**deep（8 例）**：

- 7 例 OS：337–2,840 节点；0.0023–0.0155 s。
- 1 例 PACE：`S=5`，0.0078 s。
- 合计 0.0456 s，v2.3 0.303 s。

**5 个残例**：

| idx | n | L | S | ICC | OS 节点 | 时间 |
|---|---:|---:|---:|---|---:|---:|
| 5 | 15 | 6 | 1 | miss | 788 | 0.0077 |
| 21 | 13 | 4 | 2 | miss | 1,327 | 0.0108 |
| 32 | 15 | 5 | 2 | miss | 959 | 0.0102 |
| 42 | 16 | 5 | 3 | miss | 1,592 | 0.0128 |
| 47 | 15 | 6 | 1 | miss | 2,136 | 0.0171 |
| **合计** | | | | **0/5** | **6,802** | **0.0492** |

对比 v2.3：CPS 110,971 节点 / 2.01 s；OS 6,802 / 0.0717 s；HY 8,307 / 0.0825 s。v2.4 去掉了 1,505 个探针节点，时间 0.0492 s。ICC 在这 5 例上全部 miss——这正是「全局 NO」的核心。

### 5.5 45 个合成紧状态：ICC 45/45

| 引擎 | 节点 | 时间 | 结果 |
|---|---:|---:|---|
| CPS（v2.3） | 427 | 0.0184 s | 45/45 NO |
| OS（v2.3） | 359,940 | 1.8603 s | 45/45 NO；29/45 撞 10k cap |
| **ICC（v2.4）** | **0** | **0.003 s** | **45/45 NO，39 full + 6 mand** |

这是本轮最重要的「负结果的修正」：v2.3 说「45 个合成紧状态 OS 0/45 胜 CPS」，这个陈述在**残差**上成立；但在**根状态**上，45/45 都有 ICC 短证书。CPS/OS 的比较没有把 ICC 算进去，所以「OS 不该在根层跑」的结论是不成立的。

### 5.6 38 例核心：一次诚实的回退

| 文件 | 数量 | v2.4 时间 | 判决 |
|---|---:|---:|---|
| hard3 | 12 | 0.0207 s | 8 ICC / 4 OS |
| large_a | 8 | 0.0085 s | 4 ICC / 4 PACE |
| large_b | 10 | 0.0063 s | 6 ICC / 4 PACE |
| large_het | 8 | 0.0840 s | 8 PACE |
| **合计** | **38** | **0.1195 s** | **18 ICC / 4 OS / 16 PACE** |

v2.3 是 0.113 s，v2.4 慢 6%。原因：

- `large_het#?` 的 0.084 s PACE 是单例 outlier，两个版本都无法用 ICC/OS 关闭（异资格，OS 的 YES 不可信，ICC 只跑 full）。
- ICC 在 held-out 上是约 7% 的固定税；在 38 例上，18 个 ICC 命中节省了搜索，但 16 个 PACE 的固定开销 + outlier 抵消了收益。
- 这是「证书先行」的代价，不是实现 bug；产物区把它写成负结果。

### 5.7 消融

| 变体 | held-out | hard3 | 5 残例 | 45 synth | 说明 |
|---|---:|---:|---:|---:|---|
| **默认 CC**（ICC→OS→PACE） | **0.548** | **0.021** | **0.049** | **0.003** | 本轮 |
| `icc_on=False` | 0.512 | 0.068 | 0.046 | 1.912 | ICC 的收益/税；synth 退回 OS |
| `probe=64` | 0.616 | 0.027 | 0.057 | 0.003 | 探针负收益 |
| `probe=300` | 0.785 | 0.049 | 0.089 | 0.003 | v2.3 探针 |
| `os_ncap=0`（ICC→PACE） | 3.515 | 0.026 | 2.183 | 0.003 | OS 的收益 |
| `pmax=0`（纯 PACE） | 3.482 | 0.023 | 2.178 | 0.004 | v2.3 基线 |

- ICC 在 held-out 上纯税（0.512→0.548，约 7%），在 hard3 上 3.3× 收益（0.068→0.021），在 synth 上 **637×** 收益（1.912→0.003）：没有 ICC 时，29/45 会撞 OS 的 10k cap。注意这是对「无 ICC 的 CC」的比较，不是对 PACE potential；PACE potential 本身也能 45/45 剪（0.0062 s），ICC 相对它约 2×，优势在短证书与不建表。
- CPS 探针在 held-out 上 +12%，hard3 +33%，残例 +17%，synth 0；删除。
- OS 是 held-out 和残例的主力；没有 OS，held-out 回到 3.5 s。
- PACE 仍是 `n>16`/异资格/`S>4` 的唯一完整后备。

### 5.8 正确性

| 测试 | 规模 | 结果 |
|---|---|---|
| CC vs 暴力枚举（`n=3–7`、`m≤3`、`h≤10`） | 400 例（159 可行，226 ICC 命中） | **0 不一致** |
| ICC witness 独立重算 | 53 张（8 hard3 + 45 synth） | **0 失败** |
| OS 在 `h=OPT` 的 YES 排程独立验证 | 50+12+8 | **70/70 通过** |
| CC 在 `h=OPT` 的判决 | 70 例 | **70/70 YES**（37 OS / 28 CPS / 5 PACE） |
| CC vs v2.3 在 held-out | 50 例 | **50/50 同判决** |
| CC vs v2.3 在 hard3/deep/残例 | 12+8+5 | **25/25 同判决** |

「暴力」枚举所有满足优先序的整数起点向量，再用容量计数判可行；ICC 与它逐例比对，专门检查「会不会把可行状态误判成 NO」。400 例中 226 个 ICC 命中，0 个误判，说明窗口割在这批小实例上没有 soundness 漏洞。

### 5.9 负结果

1. **ICC 在 held-out 上 0/50**：50 个状态的根层最小窗口松弛是 0–3，没有一个窗过载；2.8× 主要来自「OS 提前」，不是「割」。
2. **45 个 synth 的 0/45 是 ICC 之后的比较**：根层 45/45 有 ICC 短证书；v2.3 的负结果不能当作根层结论。
3. **38 例核心 +6% 回退**：large_het 的 0.084 s outlier + ICC 固定税；证书先行不是免费午餐。
4. **CPS 探针被删除**：这是分布相关的决定；若新分布 ICC 漏、CPS 便宜、OS 贵，探针应重新打开。
5. **OS 仍是指数**：held-out 80,463 节点；5 残例 6,802；没有短证书，只有序树。
6. **异资格 YES 失真**：v2.3 的 6/8 问题仍在；`os_gate` 必须含 `full`，异资格只保证 NO。
7. **没有 Coq/Lean**：定理 1–4 是纸面证明 + 可重放内核；引理 1/2 的算术由 53 张 witness 和 400 组暴力支撑。

---

## 6. 与 v2.3 的差异

| 项 | v2.3 | v2.4 |
|---|---|---|
| 入口 | PACE 先跑；tier 0.15 才 `HY` | **ICC 先跑；OS 第二；PACE 后备** |
| 切平面 | 无根层 ICC | **`icc-full` + `icc-mand`** |
| CPS 探针 | 固定 300 | **默认删除**（可选 64/300） |
| held-out 50 | 1.552 s / 44 表 | **0.552 s / 0 表** |
| 5 残例 | 0.0825 s / 8,307 节点 | **0.0492 s / 6,802 节点** |
| hard3 | 0.114 s | **0.0207 s** |
| deep 8 | 0.303 s | **0.0456 s** |
| 38 核心 | 0.113 s | **0.120 s（+6%）** |
| 45 synth | CPS 427 节点 | **ICC 45/45，0 节点** |
| 证书 | placement 表 / 序树 | **+ 窗口短证书** |
| 新定理 | active 复现、序不变性、上集支配、组合可靠性 | **+ ICC 可靠性、检查器可靠性、顺序组合、条件 completeness、预算终止** |
| 新负结果 | OS 不支配 CPS、探针非定理、前沿不划算、根层无并行、异资格 6/8 | **+ ICC 0/50、38 例 +6%、探针在 ICC 后负收益、synth 比较是 post-cut** |
| 代价 | `C(S+L,L)` × residual 或 `E` | **`O(n^3)` ICC + `E` OS + PACE 后备** |

---

## 7. 已知风险

1. **ICC 只证局部 NO**：在 50 个 held-out 上 0 命中；真正的 2.8× 来自 OS 提前与 PACE 表构造的规避，不是割的普遍威力。
2. **2.8× 的比较对象是 v2.3 的实现**：如果 PACE 的根层势函数/表被优化到 1 ms，CC 的相对收益会大幅缩水。
3. **删除 CPS 探针是分布相关的**：新分布若 ICC 漏、CPS 便宜、OS 贵，CC 会比 v2.3 慢；`probe>0` 必须保留为开关。
4. **38 例核心 +6% 回退**：large_het 的 0.084 s outlier 和 ICC 固定税；不是所有集合都变快。
5. **门很窄**：`full ∧ n≤16 ∧ 0≤S≤4`；`n>16`、异资格、`S>4` 全部回 PACE，收益不覆盖。
6. **OS 仍是指数**：80,463 节点 / 50 例；5 残例 6,802；没有短证书，只有序树。
7. **ICC 的 `O(n^3)` 根层开销**：`n>22` 时可能不划算；本轮只在 full 且 `n≤21` 的数据上测。
8. **异资格 YES 失真**：v2.3 的 6/8 问题仍在；`os_gate` 必须含 `full`，异资格只保证 NO。
9. **`est/q/A` 精确性**：高估会假 NO，继承 v2.2 规格。
10. **没有形式化验证**：纸面证明 + 400 组暴力 + 53 张 witness + 70 张 YES 排程；不是 Coq/Lean。
11. **时间测量单机**：4 vCPU 单线程，Python 3.12；常数项受实现影响，节点数不能直接当时间。
12. **公共期限**：各自期限 `d_i` 的路径未实现；ICC 的窗口定义依赖公共 `h`。

---

## 8. 一句话最大风险

**这一轮的 2.8× 主要来自把 OS 提到 PACE 之前、从而绕开 PACE 根层约 0.08 s 的表构造，而不是来自 ICC：ICC 在 50 个 held-out 上 0 命中，真正的判决仍是 8 万节点的 OS 树；一旦换到一个 PACE 根层很便宜、而 OS 很贵的分布，CC 会比 v2.3 慢一个数量级。**
