# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 13 轮 · WAVE-SERVO：把「增益调度」升级为「遥操作波变量 + 能量有界闭环」，并用论文级预注册检验它

> 检索/复核日期：**2026-10-28（UTC）**。赛事身份不变：宇树 **UniBot 世界挑战赛**（unibot.unitree.com），G1 + Dex1，32 项桌面任务，通才单模型赛道，选手自部署 + 官方远程真机 API。本轮是**新一轮灵感循环的第 1 轮**，三个词是「遥操作」「论文发表」「闭环控制」。本轮不推倒第 10 轮 FACT-VLA、第 11 轮 GEO-RESIDUAL、第 12 轮 CHUNK-SERVO，而是给 CHUNK-SERVO 最薄弱的**伺服层**补上理论保证：把「VLA 规划器—远程 API—机器人」显式建模成一个**带可变时延的双边遥操作回路**，用波变量/时域无源性（TD-PC）替代拍脑袋的增益调度；把 33k 条遥操作演示当作「人类操作者的阻抗先验」生成相位相关的增益表；把竞赛评测当成一次**可预注册、可复现、可证伪**的论文实验。

## 0. 先给结论：CHUNK-SERVO 的方向对，但它的伺服层缺一个稳定性证明

第 12 轮已经论证：榜单头部全部卡在「1 秒开环 chunk + 最后 3 厘米接触」。本轮不重复那部分取证，只补三个新判断：

1. **远程评测在控制论上就是双边遥操作**。主端是 VLA（慢、语义、30 步规划），从端是机器人与环境（快、接触、30Hz），通信通道是官方 websocket，带 10–150ms 甚至更抖的 RTT。双边遥操作的核心难题不是「看得更准」，而是**时延下闭环不振荡**。第 12 轮的 `K_eff = K_0/(1+τ/τ_0)` 是启发式，不是保证；可变时延下它仍可能失稳。
2. **可变时延会向视觉伺服环路注入能量**。无延迟时 `v = -ΛF̂` 使功率恒 ≤0；一旦用 `e_{k-d}` 计算速度，功率 `-ΛF̂_{k-d}ᵀF̂_k` 可正可负。正的部分就是能量注入，表现为超调、极限环、接触抖动。**这不是调参能根治的，是结构问题。**
3. **10 trials/任务是发表级统计的陷阱**。单任务 SE 约 0.14，任何 +1–2pp 都不可信。要发表，必须预注册、配对、分层收缩、报告效应量与区间，并公开阴性结果。**「论文发表」在本轮不是修辞，是方法的一部分。**

所以本轮的押注是 **WAVE-SERVO**：

> 保留 CHUNK-SERVO 的「30 步规划 + 5 步执行 + 演示相对目标 + 单模型确定性控制器」；把 5 步块内的修正从「PD + 增益调度」升级为「虚拟力 + 时域无源性 TD-PC + 遥操作演示导出的相位阻抗表」；用波变量作为时延通道的分析语言与高延迟回退模式；用预注册的分层贝叶斯实验协议判定它到底有没有用。

一句话：**把「按 RTT 降增益」改成「监测虚拟端口能量、在能量注入时主动耗散」，从而在任意可变时延下让视觉伺服回路保持无源；再用预注册实验诚实地判断这是不是真涨点。**

三个可验证创新点：

1. **WAVE 层**：虚拟力 `F̂` + Passivity Observer/Controller，替代启发式增益调度；给出离散时延裕度 `a < 2 sin(π/(2(2d+1)))` 与 TD-PC 的耗散推导。用 G2/G8 验证「无源性、无极限环、接触不抖」。
2. **遥操作阻抗先验**：从 33k 演示统计每个任务/相位的接近速度、横向修正幅度、接触驻留时间，生成确定性 `K_p(φ), D(φ)` 查表；不用第二个学习模型。用 G1/G3 验证「相位阻抗 > 固定增益」。
3. **论文级协议**：预注册 H1–H4 与证伪条件；配对 A/B；分层 Beta-Binomial/Logistic 收缩；Holm 多重比较；阴性结果台账；引用卫生审计。用 G9 验证「结论可复现、不靠榜单噪声」。

三个灵感词怎么落到方案里：

| 灵感词 | 落到哪里 | 不做什么 |
|---|---|---|
| **遥操作** | 把 VLA→API→机器人建模为主从遥操作；波变量分析时延通道；TD-PC 保证虚拟端口无源；演示即「人类操作者的阻抗先验」 | 不做真人实时遥操作接管（规则/延迟不允许）；不做物理力反馈（无 F/T） |
| **论文发表** | 预注册假设与证伪条件；配对/分层贝叶斯/效应量；阴性结果台账；引用与复现审计 | 不把预览榜单当 SOTA；不把 +1–2pp 当结论；不编造引用 |
| **闭环控制** | 5 步块内能量有界反馈；虚拟力观测；时延估计与预测；接触段法向耗散 | 不做 30Hz 广域网高增益伺服；不做第二个学习残差 |

## 1. 本轮新增/复核的事实（只列会改变方案的）

### 1.1 结构事实：这就是一个带时延的主从遥操作回路（A 级：官方 API）

- 提交端每次 `get_action` 返回固定 `action_chunk_size` 的动作，evaluator 顺序执行，chunk 内无新观测、无打断（第 12 轮已核实）。
- 观测四路 RGB、EE 位姿、夹爪、下身体、语言；**没有 depth / camera_info / force / tactile**。
- 评测端逐调用记录延迟、波动、动作统计，作为结果可信度的一部分。
- 评测跨 N 台机器人，每端口独立 `reset()`。

**推论**：主端（VLA）与从端（机器人）之间只有「延迟的位置/速度指令 + 延迟的图像」这一个通道，且没有力反馈。这正是**位置-位置（position-position）双边遥操作**的设定。无源性理论可以直接搬，但只能作用在「视觉误差 ↔ 指令速度」这个虚拟端口上。

### 1.2 数据事实：33k 演示是遥操作轨迹，不是纯专家策略（A 级：数据元数据 + 结构推断）

- 32 任务 33,276 episodes / 18.28M frames / 169.28h / 30fps；单任务 969–1,533 episodes。
- 四路视频 480×640；头双目有内参、畸变、R/T、基线 58.2526mm、已校正；腕部相机无内参。
- 每条 episode 的 EE 位姿、夹爪、下身体逐帧可得。

**新用法**：把每条演示看成「人类遥操作者的一条闭环轨迹」，从中提取**相位相关的速度/刚度统计**（接近速度、横向修正幅度、接触驻留、夹爪闭合时序），作为确定性阻抗表。这不是训练第二个模型，是统计先验。

### 1.3 理论事实：时延下无源性是成熟的（A 级：经典结果，非本轮新证）

- Anderson & Spong (1989)：时延双边遥操作的无源性与散射变换。
- Niemeyer & Slotine (1991)：波变量，使通信通道在任意常值时延下无源。
- Hannaford & Ryu (2002)：时域无源性控制（TD-PC），用 Passivity Observer/Controller 在线耗散，鲁棒于可变时延与模型误差。
- Smith (1957)：死区预测器，需要精确模型与常值时延，对可变时延脆弱。

**推论**：第 12 轮的 Smith 预测只能做前馈补偿，不能作为稳定性保证；TD-PC 才是在线安全网。两者可叠加：Smith 提性能，TD-PC 保底。

### 1.4 统计事实：10 trials/任务的估计噪声（B 级：本轮计算）

- 若 `p≈0.25`，单任务 10 次的 SE ≈ `sqrt(0.25×0.75/10) ≈ 0.137`（13.7pp）。
- 32 任务合并的 SE ≈ `sqrt(0.25×0.75/320) ≈ 2.42pp`。
- 配对设计可降低方差，但只有在同一初始条件、同一任务内配对时才成立；不能把「不同任务平均」当配对。

**推论**：单任务通道的 5 次 A/B 只能做 go/no-go 方向判断，不能做显著性结论；正式结论必须来自 32×10 或明确的重复实验，并用分层模型借力。

### 1.5 引用卫生（本轮新增的「论文发表」约束）

第 10–12 轮产物中引用了若干 arXiv 编号（如 `2609.xxxxx`）。其中年份前缀 `2609` 不合常理（超过当前年份），**本轮一律不依赖这些编号**，只依赖可核验的官方仓库/文档与经典作者-年份文献。复现包中每条引用必须带「可打开链接或 DOI」，否则标为 `UNVERIFIED` 并排除出论证链。这是发表级工作的最低要求，也是防止「用假引用支撑真结论」的必要措施。

## 2. 诊断：CHUNK-SERVO 的三个未证假设

第 12 轮把「30 步 → 5 步」做对了，但它隐含了三个未证假设：

```text
A1. 增益调度 K_eff = K_0/(1+τ/τ_0) 在 τ 抖动时仍稳定。
A2. 延迟补偿 e_{t+τ} ≈ e_t + J_v v τ 足够准。
A3. 接触段「法向缩幅/低通」不会引入持续抖动或极限环。
```

这三个都不是错的，而是**没有证明**。可变 RTT 下：

- A1：`τ` 从 20ms 跳到 150ms 时，等效离散延迟 `d = τ/Ts` 从 0 跳到 4–5；无源裕度骤降，启发式可能来不及降增益。
- A2：`J_v` 依赖深度与位姿估计；透明/反光时 `J_v` 误差大，预测反而注入能量。
- A3：低通 + 缩幅改变的是增益，不是能量结构；若延迟项本身在注入能量，缩幅只是把振荡频率压低。

**统一诊断**：问题不在「增益大小」，而在「延迟反馈项是否向环路注入能量」。正确的工具是**无源性/能量监测**，不是继续调 `K`。

## 3. 方法：WAVE-SERVO

### 3.1 总架构（在 CHUNK-SERVO 上增量）

```text
                 ┌──────────────────────────────────────────────┐
                 │ Evaluator (N ports 8765..8765+N-1)           │
                 └───────────────┬──────────────────────────────┘
                                 │ websocket: obs / action chunk (delayed)
                                 ▼
                 ┌──────────────────────────────────────────────┐
                 │ Per-port PolicyService (CPU)                  │
                 │ ├─ phase/edit observer (GEO-RESIDUAL)         │
                 │ ├─ goal retrieval (demo library, DG-KEYFRAME) │
                 │ ├─ teleop-impedance table K(φ),D(φ)           │
                 │ ├─ virtual force F̂ + TD-PC (WAVE layer)       │
                 │ ├─ delay estimator τ̂, d̂                       │
                 │ ├─ plan cache (30-step VLA plan)              │
                 │ └─ action adapter (WLA 54D → API 21D)         │
                 └───────────────┬──────────────────────────────┘
                                 │ async, batched
                                 ▼
                 ┌──────────────────────────────────────────────┐
                 │ Shared VLA server (GPU, 唯一学习模型)         │
                 │ UnifoLM-WLA-1.0, 30-step chunk                │
                 └──────────────────────────────────────────────┘
```

唯一学习模型仍是 VLA；WAVE 层、阻抗表、TD-PC 全部是确定性控制器/统计表，**不违反单模型规则**。

### 3.2 双层闭环：主端慢环 + 从端快环

- **主端慢环（VLA，~1Hz）**：产出 30 步语义规划 `a_ff`。它只决定「往哪去、做什么」，不负责毫米级。
- **从端快环（WAVE-SERVO，6Hz 修正）**：每个 5 步块用最新图像算 `e`、`F̂`，经 TD-PC 得到有界修正 `Δ`，叠加到 `a_ff`。
- 两层之间用**相对目标**（第 12 轮 DG-KEYFRAME）连接，避免绝对动作在时延下失配。

### 3.3 虚拟力与无源性（本轮核心）

定义视觉伺服误差 `e ∈ R^6`（EE 系 twist）：

```math
e = \log\!\left(T_{ee}^{-1} T_{ee}^{d}\right),\qquad
T_{ee}^{d} = T_{base,target}\,T_{target,ee}^{*}.
```

定义虚拟力（目标对夹爪的弹簧-阻尼代理）：

```math
\hat F_k = K_e\,e_k + D_e\,\dot e_k .
```

定义指令速度（无延迟理想律）：

```math
v_k^{d} = -\Lambda\,\hat F_k,\qquad \Lambda \succ 0 .
```

功率：

```math
P_k = v_k^{\top}\hat F_k
    = -\hat F_k^{\top}\Lambda \hat F_k \le 0 .
```

**无延迟时回路天然耗散**。有延迟 `d` 时用 `\hat F_{k-d}` 计算速度：

```math
P_k = -\hat F_{k-d}^{\top}\Lambda \hat F_k ,
```

当 `\hat F_{k-d}` 与 `\hat F_k` 反号（目标被扰动/时延错位）时 `P_k > 0`，即**能量注入**。

**TD-PC**：

```math
E_{obs}(k) = E_{obs}(k-1) + T_s\, v_k^{\top}\hat F_k ,
```

若 `E_{obs}(k) < 0`（控制器在产能），加阻尼：

```math
\beta_k = \frac{-E_{obs}(k)}{T_s\,\|\hat F_k\|^2 + \varepsilon},\qquad
v_k \leftarrow v_k - \beta_k \hat F_k,
```

使 `T_s\,\beta_k\|\hat F_k\|^2 = -E_{obs}(k)`，`E_{obs}(k) \to 0`。此后 `E_{obs} \ge 0`，虚拟端口无源。

**诚实边界**：无源性是对**虚拟端口** `(v, F̂)` 的，不是对真实物理接触力的。它保证「视觉误差回路不产生能量」，不保证「物理上不撞坏」。真实接触的安全性仍靠限幅/限速/最大重试。

### 3.4 波变量作为分析语言与高延迟回退

对虚拟端口定义波变量（`b>0` 为波阻抗）：

```math
u_k = \frac{1}{\sqrt{2b}}\left(\hat F_k + b\,v_k\right),\qquad
w_k = \frac{1}{\sqrt{2b}}\left(\hat F_k - b\,v_k\right).
```

功率分解：

```math
\hat F_k^{\top} v_k = \tfrac12\left(u_k^{\top}u_k - w_k^{\top}w_k\right).
```

通道对 `u` 延迟 `T_f`、对 `w` 延迟 `T_b`；延迟线存储能量有界，故常值时延下通道无源。**可变时延下波变量不保证无源**，因此：

- 主模式：TD-PC（对可变时延鲁棒）；
- 高延迟/高抖动回退：波变量编码 + 更低带宽，牺牲响应换稳定。

### 3.5 从遥操作演示导出相位阻抗表

对每个任务 `t`、每个相位 `φ`（接近/预接触/接触/搬运）：

```text
从成功演示统计：
  ṽ(φ)   = 接近速度中位数
  σ⊥(φ) = 横向修正幅度（垂直于接近轴）
  τc(φ) = 接触驻留时间
  g(φ)   = 夹爪闭合时序
阻抗表：
  K_p(φ) = K_0 · (1 + α·z_speed(φ)) / (1 + α·z_lateral(φ))
  D(φ)   = D_0 · (1 + β·z_lateral(φ))
```

只用中位数/分位数/z-score，**无学习权重**。物理直觉：人类遥操作者在接近段快、在接触段慢且硬；把这种「相位相关的柔顺」抄进控制器。

### 3.6 时延估计与预测

```text
τ̂_k = median(last W RTT samples)          # 抗抖动
d̂_k = round(τ̂_k / T_s)
jitter_k = IQR(last W RTT samples)
若 jitter_k 大：提高基础阻尼、降低 K_p；TD-PC 自动兜底
Smith 前馈：e_{k+d̂} ≈ e_k + J_v v_k τ̂_k   # 只提性能，不做保证
```

### 3.7 状态机（在 CHUNK-SERVO 上加密）

```text
INIT → PLAN → APPROACH(PBVS) → PRECONTACT(PBVS+IBVS)
     → CONTACT(TD-PC + 法向耗散) → CARRY → DONE
                     │
                     └─ edit_score>θ_e → RECOVER（停/重定位/重规划）
```

`CONTACT` 态强制启用 TD-PC；`APPROACH` 态可只用 Smith 前馈以保响应。

## 4. 与第 10/11/12 轮的关系：保留、升级、剪枝

**保留**：

- FACT-VLA 相位化 BC、CAC 柔顺、EGP 门控；
- GEO-RESIDUAL 动作条件化残差、米制表面距离、编辑检测；
- CHUNK-SERVO 的 30/5 双频、DG-KEYFRAME 相对目标、单模型合规、竞赛组合；
- 官方 WLA 基座、33k 演示、单任务通道。

**升级**：

- 增益调度 → **TD-PC 能量有界闭环**（本轮核心）；
- 固定相位置信 → **遥操作统计阻抗表**；
- Smith 预测从「稳定手段」降级为「性能前馈」；
- 评测从「跑分」升级为「预注册论文实验」。

**剪枝**：

- 不再把「调 `K`/`H_c`」当稳定性方案；
- 不做物理力反馈（API 没有）；
- 不做第二个学习残差/阻抗网络；
- 不依赖任何不可核验的 arXiv 编号；
- 不把 5 次 A/B 当显著性结论。

## 5. 实验门 G0–G9（新增 G8 无源、G9 可复现）

| 门 | 问题 | 通过标准 | 失败动作 |
|---|---|---|---|
| G0 | 腕部相机能否标定？ | 重投影 ≤5px；头双目 ROI 有效 ≥70% | 只用头双目 PBVS |
| G1 | 演示检索/阻抗表是否可信？ | top-5 几何有效 ≥80%；相对位姿 ≤5mm/2°；阻抗表分相位可分 | 改用任务级固定目标/固定增益 |
| G2 | 仿真伺服是否收敛？ | 横向 ≤2mm、深度 ≤3mm、2s ≥95%；RTT 0–150ms 稳定 | 降增益/加 chunk；只做 PBVS |
| G3 | 真机单任务是否涨点？ | 3/5 任务 +10pp；FoldTowel 不回归 | 不提交 servo 版本 |
| G4 | 人为干扰能否恢复？ | 检测 ≤200ms；仿真恢复 ≥70% | 只做离线标注 |
| G5 | 延迟是否可接受？ | p99 ≤150ms；timeout 不升 | 加 chunk/降分辨率/关伺服 |
| G6 | 32 任务干跑是否稳定？ | N 端口隔离、reset 干净、内存不涨 | 回退基线 |
| G7 | 消融是否支持因果？ | 相对目标>绝对；5 步>30 步；伺服>无伺服 | 保留有效部分，砍无效部分 |
| **G8** | **无源性/无极限环？** | `E_obs≥0`；仿真无持续极限环；接触抖动 RMS 不升 | 关 TD-PC，回退纯 PD + 限幅 |
| **G9** | **论文级可复现？** | 预注册先写；代码/种子/配置/区间齐全；每条引用可打开 | 论文主张降级为工程报告 |

## 6. 风险（本轮更新）

| 风险 | 影响 | 缓解 |
|---|---|---|
| **虚拟力≠物理力** | 无源只保证视觉回路，不保证接触安全 | 限幅/限速/最大重试；接触段额外电流/位置滞止代理 |
| 过度保守 | TD-PC 耗散过多，伺服变慢，任务超时 | 只在 `E_obs<0` 时耗散；APPROACH 态旁路；G3 判收益 |
| 增益表过拟合演示分布 | 新物体/新位置失效 | 只用中位数/z-score；按 session 分组验证；置信度低回退 |
| 可变时延被低估 | `d̂` 错，预测反注能 | TD-PC 兜底；jitter 大时降带宽；G5 |
| 单模型解释 | 被判第二个模型 | 确定性控制器 + 统计表；写清无学习权重 |
| 统计假阳性 | 把噪声当涨点 | 预注册、配对、分层、Holm、阴性台账；G9 |
| 引用污染 | 用假文献支撑真结论 | 引用审计；`UNVERIFIED` 排除出论证链 |

## 7. 一句话押注

**保留 CHUNK-SERVO 的双频执行与演示相对目标，但把它的伺服层从「按 RTT 调增益」升级为「虚拟力 + 时域无源性」：监测视觉伺服虚拟端口的能量，在可变时延注入能量时主动耗散，并用遥操作演示导出的相位阻抗表设置基线增益；最后用预注册的分层贝叶斯实验诚实地判定它是否真涨点——因为一个没有稳定性证明的闭环，和一个没有统计纪律的涨点，都不值得发表。**

**本轮最大风险**：虚拟力不是真实接触力，基于虚拟端口的无源性只能证明「视觉误差回路不振荡」，不能证明「物理接触不撞坏」；若真实接触的摩擦/非线性主导，这套理论可能既保守又不对症。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 13 轮产物 · WAVE-SERVO 技术报告

> 检索/复核日期：**2026-10-28（UTC）**。对象：宇树 **UniBot 世界挑战赛**（G1 + Dex1，32 项桌面任务，通才单模型赛道，选手自部署 + 官方远程真机 API）。本报告是新一轮灵感循环第 1 轮「遥操作 / 论文发表 / 闭环控制」的工程化产物；它在第 12 轮 **CHUNK-SERVO** 之上做控制层增量，不替换第 10 轮 FACT-VLA、第 11 轮 GEO-RESIDUAL。

## 0. 结论与边界

### 0.1 一句话结论

CHUNK-SERVO 的「30 步规划 + 5 步执行」方向正确，但其伺服层是 PD + 启发式增益调度，在**可变 RTT** 下没有稳定性保证。本报告把「VLA—远程 API—机器人」显式建模为**带时延的主从（位置-位置）遥操作回路**，用**虚拟力 + 时域无源性控制（TD-PC）** 在视觉伺服虚拟端口上监测并耗散延迟注入的能量，用**遥操作演示导出的相位阻抗表**设定基线增益，用**预注册分层贝叶斯实验**判定它是否真涨点。唯一学习模型仍是 VLA；其余全部是确定性控制器与统计表。

### 0.2 证据等级

| 等级 | 含义 | 本报告中的例子 |
|---|---|---|
| A | 官方文档、提交模板、数据集元数据、经典文献直接核实 | 规则/API、33,276 eps、WLA `chunk_size=30`、时延裕度公式 |
| B | 我们在公开数据/网页/公式上做的分析，可复现 | 单任务 SE≈13.7pp、延迟裕度表、能量推导 |
| C | 设计假设，需 G0–G9 验证 | TD-PC 在真机接触段的有效性、阻抗表收益 |
| U | 未核验，不得进入论证链 | 第 10–12 轮中形如 `2609.xxxxx` 的 arXiv 编号 |

### 0.3 本轮不做什么

- 不做物理力反馈/触觉闭环（API 没有 F/T、tactile）。
- 不做真人实时遥操作接管（评测是自动 `get_action`，且 RTT 不允许）。
- 不做第二个学习模型/残差网络/阻抗网络；TD-PC 与阻抗表均无学习权重。
- 不依赖不可核验的 arXiv 编号。
- 不把 5 次 A/B 当显著性结论；不把预览榜单当 SOTA。

## 1. 事实核对（只列会改变方案的）

### 1.1 接口时间模型（A）

一次 `get_action` 后，evaluator 顺序执行 `H_c` 个动作，chunk 内无新观测、无打断。设：

- `f_c`：evaluator 控制频率（假设 30Hz，必须实测）；
- `T_s = 1/f_c`；
- `H_c`：提交的 `action_chunk_size`；
- `τ`：RTT + 推理 + 图像传输的等效延迟；
- `d = round(τ/T_s)`：等效离散延迟步数。

反馈周期：

```math
T_{fb} \approx \frac{H_c}{f_c} + \tau .
```

| 场景 | `H_c` | `f_c` | `τ` | `T_fb` |
|---|---:|---:|---:|---:|
| WLA 默认 | 30 | 30 | 50ms | 1050ms |
| 本轮保守 | 5 | 30 | 50ms | 217ms |
| 本轮高延迟 | 5 | 30 | 150ms | 317ms |
| 低控制频率 | 5 | 10 | 50ms | 550ms |

### 1.2 离散时延裕度（A：可推导）

标量误差回路（每轴独立）：

```math
e_{k+1} = e_k - a\,e_{k-d},\qquad a = K T_s .
```

特征方程 `z^{d+1} - z^d + a = 0`。在单位圆 `z=e^{iθ}` 上，由 `e^{idθ}(e^{iθ}-1) = -a` 得：

- 幅值条件 `2|sin(θ/2)| = a`；
- 相位条件 `θ = π/(2d+1)`（取最小正根）。

故稳定域：

```math
\boxed{\,0 < a < a_{\max}(d) = 2\sin\!\left(\frac{\pi}{2(2d+1)}\right)\,}
```

| `d` | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---:|---:|---:|---:|---:|---:|
| `a_max` | 2.000 | 1.000 | 0.618 | 0.445 | 0.347 | 0.284 |
| `K_max` @30Hz (1/s) | 60.0 | 30.0 | 18.5 | 13.3 | 10.4 | 8.5 |

**含义**：τ 从 20ms 跳到 150ms（d≈0→5），允许增益下降约 **7 倍**。启发式 `K_0/(1+τ/τ_0)` 很难在抖动中始终落在域内；这是本轮引入 TD-PC 的直接动机。

### 1.3 数据与遥操作先验（A+C）

- 32 任务 / 33,276 episodes / 18.28M frames / 169.28h / 30fps；单任务 969–1,533 eps。
- 头双目已校正（基线 58.2526mm，fx≈282px）；腕部相机无内参。
- 每条 episode 提供逐帧 EE 位姿、夹爪、下身体，可提取相位速度/刚度统计（C 级用法，需 G1 验证）。

### 1.4 榜单与统计纪律（B）

榜单是赛事方预览，`step~success` 高度线性（`R²>0.999999`），任务级成功率不是 10% 整数倍，跨模型任务相关仅约 0.098。使用它只能当「难度先验」，不能当实测分布。10 trials/任务单任务 SE≈13.7pp；32 任务合并 SE≈2.42pp。

### 1.5 引用卫生（本轮新增）

第 10–12 轮出现的 `2609.xxxxx` 形 arXiv 编号年份异常，本报告标为 `U` 级，不进入论证链。所有引用在复现包中必须可打开；不可打开者标 `UNVERIFIED` 并从论证中移除。

## 2. 问题形式化

### 2.1 主从遥操作模型

把系统写成两端口网络：

- **主端（leader）**：VLA 规划器，输出 30 步前馈 `a_ff`；
- **从端（follower）**：机器人 + 环境，状态 `x = (T_{ee}, v, gripper)`；
- **通道**：延迟 `τ_k`（可变、未知、上界 `τ_max`），传输「指令」与「图像/状态」。

位置-位置架构：主端发期望位姿，从端回观测位姿；无力反馈。控制目标是：

```math
\min\ \|e_k\|^2 \quad \text{s.t.}\quad \text{闭环在 } \tau_k \in [0,\tau_{\max}] \text{ 下有界、无持续振荡}.
```

### 2.2 视觉伺服误差与相对目标

```math
e_k = \log\!\left(T_{ee,k}^{-1}\,T_{ee,k}^{d}\right) \in \mathbb R^6,\qquad
T_{ee,k}^{d} = T_{base,target}(t_k)\,T_{target,ee}^{*}.
```

`T_{target,ee}^{*}` 来自第 12 轮演示检索（DG-KEYFRAME）；`T_{base,target}(t)` 在线用头双目 + 第 11 轮几何估计。

### 2.3 虚拟端口

真实功率端口需要力，API 没有。定义**虚拟力**：

```math
\hat F_k = K_e(\phi_k)\,e_k + D_e(\phi_k)\,\dot e_k \in \mathbb R^6,
```

其中 `φ_k` 是相位（接近/预接触/接触/搬运），`K_e(\phi), D_e(\phi)` 来自遥操作演示统计（§4）。定义指令速度与虚拟端口功率：

```math
v_k^{d} = -\Lambda\,\hat F_k,\qquad
P_k = v_k^{\top}\hat F_k = -\hat F_k^{\top}\Lambda\hat F_k \le 0 \quad(\tau=0).
```

**边界声明**：`\hat F` 是视觉误差的弹簧-阻尼代理，不是物理接触力。下文的「无源」均指**虚拟端口无源**。

### 2.4 可辨识性条件（沿用第 12 轮）

伺服仅在以下同时满足时启用：目标在视野内；深度/视差有效（双目 ROI≥70% 或腕部 inlier≥15）；标定误差在门限内（重投影≤5px）；目标位姿协方差低于阈值；任务属刚体接触类。任一不满足 → 回退 VLA 开环/PBVS 粗对齐。

## 3. WAVE-SERVO 设计

### 3.1 分层结构

```text
Leader (VLA, GPU, ~1Hz):
    a_ff[0:30] = VLA(obs)                  # 语义规划，不含毫米级
                 │  async, plan cache
                 ▼
Follower (CPU, 6Hz correction):
    phase φ, goal retrieval
    e_k, ė_k
    F̂_k = K_e(φ)e_k + D_e(φ)ė_k
    v_k = -Λ F̂_{k-d̂}                      # 延迟反馈
    TD-PC: E_obs, β_k  (仅在 E_obs<0 时耗散)
    Δ_k = clip(T_s v_k, ±δ_p, ±δ_r)
    a_cmd = a_ff[chunk] ∘ exp(Δ_k)
                 │  5-step chunk
                 ▼
Evaluator (remote, delayed)
```

### 3.2 TD-PC 精确步骤

记 `Ts` 为控制周期，`F̂_k` 为当前虚拟力，`v_k` 为当前指令速度（由延迟力 `F̂_{k-d̂}` 计算）。

```text
1. E_obs(k) = E_obs(k-1) + Ts * (v_k · F̂_k)
2. if E_obs(k) < 0:
       β_k = -E_obs(k) / (Ts * ||F̂_k||^2 + ε)
       v_k = v_k - β_k * F̂_k
       E_obs(k) = 0
3. Δ_k = clip(Ts * v_k, ±δ_p, ±δ_r)      # δ_p=1cm, δ_r=0.05rad
```

性质：

- `E_obs(k) ≥ 0` 对所有权 `k`（归纳：负则归零，正则不减）。
- 耗散量恰好抵消累计产能：`Ts β_k ‖F̂_k‖² = -E_obs_old(k)`。
- 当 `τ=0` 时 `E_obs` 单调不增（因为 `P_k≤0`），TD-PC 不触发，**不影响无延迟性能**。
- `β_k` 只在能量注入时非零，故是「按需耗散」而非全局降增益。

### 3.3 波变量（分析 + 高延迟回退）

```math
u_k = \frac{1}{\sqrt{2b}}(\hat F_k + b v_k),\qquad
w_k = \frac{1}{\sqrt{2b}}(\hat F_k - b v_k),
```

```math
\hat F_k^{\top} v_k = \tfrac12\left(u_k^{\top}u_k - w_k^{\top}w_k\right).
```

- 常值时延：延迟线储能 `\int (u^2+w^2)` 有界 ⇒ 通道无源 ⇒ 与无源主/从端互联稳定。
- 可变时延：波变量本身不保证无源；因此只作为**分析语言**和 `τ_max` 很大时的**低带宽回退**，主模式仍是 TD-PC。
- 与 Smith 预测的关系：Smith 需要精确模型与常值时延，作为**性能前馈**保留；TD-PC 作为**稳定性安全网**，两者不冲突。

### 3.4 时延估计

```text
τ̂_k = median(RTT[k-W+1 : k])          # 抗抖动
d̂_k = round(τ̂_k / Ts)
jitter_k = IQR(RTT[k-W+1 : k])
if jitter_k > J0:  基线下调 K_e, 上调 D_e
Smith 前馈: e_{k+d̂} ≈ e_k + J_v v_k τ̂_k
```

`W` 取 10–20；`J0` 由单任务通道标定。所有量逐端口独立。

### 3.5 相位阻抗表（遥操作演示先验）

对任务 `t`、相位 `φ`，从成功演示统计：

```text
ṽ(φ)   = median approach speed
σ⊥(φ) = median lateral correction magnitude
τc(φ) = contact dwell time
```

构造：

```math
K_e(\phi) = K_0\,\frac{1+\alpha\,z_{v}(\phi)}{1+\alpha\,z_{\perp}(\phi)},\qquad
D_e(\phi) = D_0\,\bigl(1+\beta\,z_{\perp}(\phi)\bigr),
```

`z` 为按任务归一化的 z-score，`α,β` 由 G1/G2 标定。物理直觉：人类遥操作者接近快、接触慢且刚；把「相位相关柔顺」编码进增益表，而不是全局常数。

### 3.6 `get_action` 伪代码

```python
class WaveServoPolicy:
    Ts = 1.0 / 30.0
    Hc = 5

    def __init__(self):
        self.E_obs = 0.0
        self.F_hist = deque(maxlen=32)   # 延迟力环形缓冲
        self.plan = None
        self.plan_idx = 0
        self.phase = "APPROACH"

    def get_action(self, obs):
        self._tick(obs)                       # 相位/编辑检测（第 11/12 轮）
        tau = self._estimate_delay(obs)       # median RTT
        d = max(0, round(tau / self.Ts))
        self._maybe_request_plan(obs)         # 异步 VLA，不阻塞

        goal = self._retrieve_goal(obs)       # DG-KEYFRAME，可返回 None
        if self.plan is None or goal is None:
            return self._safe_chunk(obs)      # 合法 hold / 上一 chunk

        e = self._servo_error(obs, goal)      # 6D twist
        de = (e - self._e_prev) / self.Ts
        F = self._impedance(self.phase) * e + self._damping(self.phase) * de
        self.F_hist.append(F)

        F_delayed = self.F_hist[-1 - d] if len(self.F_hist) > d else F
        v = -self.Lambda @ F_delayed          # 延迟反馈

        # ---- TD-PC ----
        self.E_obs += self.Ts * float(v @ F)
        if self.E_obs < 0.0:
            beta = -self.E_obs / (self.Ts * float(F @ F) + 1e-9)
            v = v - beta * F
            self.E_obs = 0.0

        delta = self._clip(v * self.Ts, dp=0.01, dr=0.05)
        a_ff = self._plan_slice(self.Hc)      # 30 步计划切 5 步
        a_cmd = compose_relative(a_ff, delta) # EE 局部系右乘
        return self._adapter(a_cmd, obs)      # WLA 54D -> API 21D
```

规则：

- VLA 除冷启动外不阻塞；plan 过期用旧 plan + 伺服。
- 伺服任何异常 → 返回上一组合法 chunk 或安全 hold；绝不返回 NaN/错误形状。
- 每端口独立 `E_obs`、`F_hist`、`phase`、`plan`、`goal`。

### 3.7 动作适配（沿用第 12 轮，保留关键风险）

WLA 54D → API 21D：`left/right EE 相对 → 绝对`（先整体 compose 再切 5 步，避免锚点错位）；gripper 直通；`pivot` 从 base/waist/height 组合。`pivot` 7 维语义未逐维定义，第一验证项是 `example_env.py` + 单任务通道；不匹配时先返回零 pivot，只验证双臂。

### 3.8 状态机

```text
INIT → PLAN → APPROACH(PBVS) → PRECONTACT(PBVS+IBVS)
     → CONTACT(TD-PC + 法向耗散) → CARRY → DONE
                     │
                     └─ edit_score>θ_e → RECOVER（停/重定位/重规划）
```

- `APPROACH`：可旁路 TD-PC，只用 Smith 前馈，保响应。
- `CONTACT`：强制 TD-PC；法向分量额外乘 0.3–0.5 并低通；切向保留。
- `RECOVER`：编辑检测触发；先停，再重定位；目标不可见则 VLA 重规划。

## 4. 推导与性质

### 4.1 为什么启发式增益调度不够

带宽/稳定裕度随时延下降（§1.2）。若 `d` 在 0–5 间抖动，固定 `K` 必须满足最坏 `d=5`，即 `K<K_max(5)≈8.5/s`。但这会让 `d=0` 时过慢。启发式在线调 `K` 需要准确知道 `d` 且切换平滑；一旦估计滞后或抖动，可能瞬时越界。TD-PC 不依赖精确 `d`：它只看「实际能量流」，越界时自动耗散。

### 4.2 能量有界性

定义累计虚拟能量：

```math
E_{obs}(k) = T_s \sum_{i=1}^{k} v_i^{\top}\hat F_i .
```

TD-PC 步骤保证 `E_obs(k) ≥ 0`。当 `E_obs(k) < 0` 时，`β_k` 使本次耗散恰为 `-E_obs(k)`，故新值归零。于是对所有 `k`：

```math
T_s \sum_{i=1}^{k} v_i^{\top}\hat F_i \ge 0 .
```

即虚拟端口从控制器角度看是「耗散/无源」的。对无源系统，负反馈互联的 `L_2` 稳定性由无源性定理给出（在虚拟端口意义下）。

### 4.3 无延迟不退化

`τ=0 ⇒ d=0 ⇒ v_k = -ΛF̂_k ⇒ P_k = -F̂_k^TΛF̂_k ≤ 0 ⇒ E_obs` 单调不增，TD-PC 不触发。故 TD-PC 是「只在需要时介入」的安全层，不牺牲标称性能。

### 4.4 接触段的法向/切向分解

令接触法向 `n_k`，投影 `P_n = n n^T`，`P_t = I - P_n`：

```math
\Delta_k = P_n \Delta_k^{n} + P_t \Delta_k^{t},\qquad
\Delta_k^{n} \leftarrow \gamma_n\,\mathrm{LPF}(\Delta_k^{n}),\quad \gamma_n\in[0.3,0.5].
```

TD-PC 作用在整体 `Δ_k` 上；法向额外缩幅用于防止硬接触冲击。滑移检测（`r_grasp` 突变）时冻结切向、加大夹持。

### 4.5 与波变量的关系

波变量把通道功率分解为前向/后向行波，延迟线储能 `E_delay = 1/2∫(u²+w²)` 有界，故常值时延通道无源。TD-PC 可看作「在端口处直接观测能量并耗散」，对可变时延更直接。两者数学上可统一到「端口哈密顿/无源性」框架：波变量是坐标变换，TD-PC 是端口耗散注入。

## 5. 预注册实验协议（论文发表层）

### 5.1 先写假设，再做实验

| 编号 | 假设 | 证伪条件 | 主/次 |
|---|---|---|---|
| H1 | 高时延（τ≥100ms）下，TD-PC 降低成功率方差与接触抖动 | 方差不变或变大；抖动 RMS 上升 | 主 |
| H2 | 相位阻抗表在 A 档接触任务优于固定增益 | 配对差值 CI 跨 0 且方向为负 | 主 |
| H3 | 5 步 chunk 优于 30 步（复现第 12 轮） | 5 步 ≤ 30 步 | 次 |
| H4 | 低时延（τ<30ms）下 TD-PC 无平均收益 | 低时延下反而显著更差 → 应旁路 | 次（证伪性） |

**预注册内容**：上述假设、主/次端点、分析计划、停止规则、排除标准，必须在正式评测前写入仓库并打时间戳。

### 5.2 分层贝叶斯模型

对任务 `t`、trial `j`、处理臂 `c∈{off,on}`：

```math
y_{t,j} \sim \mathrm{Bernoulli}(p_{t,c(j)}),
```

```math
\mathrm{logit}(p_{t,c}) = \alpha_t + \delta\,\mathbb 1[c=\text{on}] + \gamma\,\mathbb 1[\text{human}] + \eta\,\mathbb 1[c=\text{on}]\mathbb 1[\text{human}],
```

```math
\alpha_t \sim \mathcal N(\mu_\alpha, \sigma_\alpha^2),\quad
\delta \sim \mathcal N(0, 0.5^2),\quad
\mu_\alpha,\sigma_\alpha \text{ 用弱信息先验}.
```

- `δ` 是伺服的平均对数几率效应；`η` 是人为干扰轴的额外效应。
- 分层结构对 32 个任务做部分池化，缓解单任务 10 次的高方差。
- 全局效应：

```math
\Delta S = \frac{1}{32}\sum_{t=1}^{32}\left(p_{t,\text{on}} - p_{t,\text{off}}\right).
```

报告 `ΔS` 的后验均值、95% 可信区间、`P(ΔS>0)`。**不报单一 p 值作为唯一证据**。

### 5.3 功效与停止规则

- 正式评测 32×10：合并 SE≈2.42pp；配对可降方差，但不要假设降到 0。
- 单任务通道 5×5 仅用于 go/no-go，**不做显著性结论**；预注册中明确写「pilot not powered」。
- 停止规则：若 G3 的 3/5 任务未达 +10pp，停止，不烧正式提交。

### 5.4 多重比较

主端点族预注册为「5 个 A 档任务 + human 轴」，用 Holm–Bonferroni 控制族错误率；其余 27 个任务为探索性，报告时明确标注，不作确证性主张。

### 5.5 阴性结果台账

每个门（G0–G9）记录：通过/失败、样本量、点估计、区间、失败原因。**失败的门必须保留在论文/报告中**，不得只报通过项。这是「论文发表」灵感在本轮的硬约束。

### 5.6 引用与复现审计

- 每条引用：标题、作者、年份、可打开链接/DOI；打不开 → `UNVERIFIED`，移出论证链。
- 复现包：代码、随机种子、配置文件、标定参数、硬件型号、软件版本。
- 不包含：评测端私有数据、官方 token。
- 明确区分「A 级官方事实」「B 级自算」「C 级设计假设」。

## 6. 实验设计与门

### 6.1 离线

| 实验 | 数据 | 指标 | 门 |
|---|---|---|---|
| 目标检索 | 32 任务演示，按 session 分组 | top-5 几何有效 ≥80%；相对位姿 ≤5mm/2° | G1 |
| 阻抗表可分性 | 相位标注子集 | 相间速度/横向幅度差异显著（效应量） | G1 |
| 编辑检测 | 合成编辑 + 正常 | AUROC ≥0.85；误报 ≤5% | G4 |

### 6.2 仿真

| 实验 | 变量 | 指标 | 门 |
|---|---|---|---|
| 收敛 | `H_c`/`K`/`τ` | 横向 ≤2mm、深度 ≤3mm、2s ≥95% | G2 |
| 时延 | τ ∈ {0,30,60,100,150}ms，含抖动 | 超调、极限环、稳定域 | G2/G8 |
| 无源性 | TD-PC on/off | `E_obs≥0`；接触抖动 RMS | G8 |
| 扰动 | 位置/遮挡/背景/目标移动/人手 | 恢复率、检测延迟 | G4 |
| 消融 | 相对/绝对；5/30；PD/TD-PC；阻抗表/固定 | 成功率、误差、方差 | G7 |

### 6.3 真机单任务

| 项 | 设计 |
|---|---|
| 任务 | PlugInEthernet、HangCup、ZipUp、StackBowls、FoldTowel |
| 次数 | 每任务 5 次 A/B（servo off/on），同初始条件 |
| 指标 | 成功、步骤分、耗时、p99、恢复、抖动 |
| 统计 | 配对差值 + bootstrap 95% CI；pilot 不宣称显著性 |
| 门 | ≥3/5 +10pp；FoldTowel 不回归 >5pp |

### 6.4 全量

| 项 | 设计 |
|---|---|
| 任务 | 32×10 |
| 端口 | N 个连续端口，独立 reset |
| 指标 | 总平均成功率、步骤分、p99、timeout、内存 |
| 门 | 无端口串扰；reset 干净；内存不涨；p99 ≤150ms |

### 6.5 门 G0–G9

| 门 | 问题 | 通过标准 | 失败动作 |
|---|---|---|---|
| G0 | 腕部标定？ | 重投影 ≤5px；双目 ROI ≥70% | 只用头双目 PBVS |
| G1 | 检索/阻抗表可信？ | top-5 ≥80%；相对位姿 ≤5mm/2°；相位可分 | 任务级固定目标/固定增益 |
| G2 | 仿真收敛？ | 横向 ≤2mm、深度 ≤3mm、2s ≥95%；τ 0–150ms 稳定 | 降增益/加 chunk；只做 PBVS |
| G3 | 真机涨点？ | 3/5 任务 +10pp；FoldTowel 不回归 | 不提交 servo 版本 |
| G4 | 人为干扰恢复？ | 检测 ≤200ms；仿真恢复 ≥70% | 只做离线标注 |
| G5 | 延迟可接受？ | p99 ≤150ms；timeout 不升 | 加 chunk/降分辨率/关伺服 |
| G6 | 32 任务稳定？ | N 端口隔离、reset 干净、内存不涨 | 回退基线 |
| G7 | 消融支持因果？ | 相对>绝对；5>30；伺服>无伺服 | 保留有效部分，砍无效部分 |
| G8 | 无源/无极限环？ | `E_obs≥0`；无持续极限环；接触抖动 RMS 不升 | 关 TD-PC，回退 PD + 限幅 |
| G9 | 可复现？ | 预注册先写；代码/种子/配置/区间齐全；引用可打开 | 降级为工程报告 |

## 7. 竞赛策略（沿用第 12 轮，加时延分层）

### 7.1 时延分层

| 时延档 | 判定 | 策略 |
|---|---|---|
| 低（τ<30ms） | 本地/同城 | TD-PC 旁路，Smith 前馈 + 正常增益；保响应 |
| 中（30–100ms） | 常规远程 | TD-PC 启用；5 步 chunk |
| 高（>100ms） | 跨城/抖动 | TD-PC + 降带宽；必要时波变量回退；chunk 5–8 |

### 7.2 任务组合

沿用第 12 轮 A/B/C 分档（A 档 19 个伺服优先，B 档 13 个 VLA 优先，C 档观察），优先级：

```text
priority_t = q_t * Δ_t / cost_t
```

`q_t` 为「失败发生在最后 3 厘米」的先验比例，`Δ_t` 由单任务通道更新，`cost_t` 为工程/评测成本。先做 A 档中 `q_t` 高、`cost_t` 低的 3–5 个。

### 7.3 提交节奏

1. W0：WLA + adapter + chunk 30 基线，单任务通道验证 token/`pivot`。
2. W1：安全基线提交（若允许多次），锁 tie-break。
3. W2–W4：标定、目标库、阻抗表、TD-PC、仿真。
4. W5：单任务 A/B、延迟/增益扫描、全量干跑。
5. W6：最终提交，保留回滚开关。

若只允许一次提交：跳过 W1，W5 后再交；不要用正式 320 trials 做未验证 A/B。

## 8. 资源与时间表

| 阶段 | 时间 | 交付 | 退出条件 |
|---|---:|---|---|
| P0 基线/接口 | 1 周 | WLA + adapter；token/`pivot` 验证；chunk 30 基线 | 单任务通道 1 任务跑通 |
| P1 标定/目标库/阻抗表 | 2 周 | 腕部标定；目标库；相位阻抗表；检索评测 | G0/G1 |
| P2 WAVE/仿真 | 2 周 | 虚拟力；TD-PC；波变量回退；τ 扫描；扰动套件 | G2/G4/G8 |
| P3 集成/单任务 | 2 周 | 双频执行；状态机；5 任务 A/B | G3/G5 |
| P4 全量干跑 | 1 周 | 32×10 干跑；N 端口；p99/内存 | G6 |
| P5 提交/论文 | 1 周 | 提交包、合规说明、预注册报告、复现包 | G7/G9 |

**算力**：1×24GB GPU（WLA 推理/微调）；可选 1×40/80GB 多端口；16–32 CPU 核；存储视频 1–2TB（可只缓存关键帧降至 <100GB）。
**人员**：1 人伺服/几何；1 人 WLA/部署；1 人评测/统计；共 9–11 周。

## 9. 风险与合规

### 9.1 单模型合规

| 模式 | 做法 | 风险 | 建议 |
|---|---|---|---|
| C1 离线标注 | GEO-RESIDUAL 只离线生成相位/接触标签 | 最低 | 保守首选 |
| C2 确定性控制器 | TD-PC/波变量/阻抗表均无学习权重 | 低 | 主推 |
| C3 同 checkpoint 特征 | 目标描述子用同一 VLA encoder | 低–中 | 需要强描述子时用 |

禁止：在线加载第二个学习策略/残差网络/独立视觉编码器做决策。

### 9.2 风险表

| 风险 | 影响 | 缓解 |
|---|---|---|
| **虚拟力≠物理力** | 无源只保证视觉回路，不保证接触安全 | 限幅/限速/最大重试；接触段电流/滞止代理 |
| 过度保守 | TD-PC 耗散过多，超时 | 只在 `E_obs<0` 耗散；APPROACH 旁路；G3 |
| 时延被低估 | 预测反注能 | TD-PC 兜底；jitter 大降带宽；G5 |
| 阻抗表过拟合演示 | 新物体失效 | 中位数/z-score；按 session 分组；置信度低回退 |
| 目标检索 mismatch | 错误目标 | 任务/相位过滤；top-k 重打分；低置信回退 |
| 透明/反光/变形 | 深度/特征失败 | 只对刚体启用；腕部 2D + 滞止兜底 |
| 标定漂移/换机器人 | 残差变大 | 每机器人重投影校准；误差大关伺服 |
| `pivot` 语义不一致 | 动作被拒/不动 | `example_env.py`/单任务通道先验；零 pivot 回退 |
| 统计假阳性 | 噪声当涨点 | 预注册、配对、分层、Holm、阴性台账 |
| 引用污染 | 假文献支撑真结论 | 引用审计；`UNVERIFIED` 排除 |
| 提交次数限制 | 无法多次 A/B | 邮件确认；单任务通道先验；一次则保守 |

## 10. 来源

官方/数据（检索日期 2026-10-28，沿用第 12 轮已核实）：

- UniBot 世界挑战赛官网：<https://unibot.unitree.com/>
- 赛事页：<https://unibot.unitree.com/challenges.html>
- 排行榜 JSON：<https://unibot.unitree.com/leaderboard_data.json>
- 提交模板：<https://github.com/unitreerobotics/unibot_submission>
- 提交 README：<https://raw.githubusercontent.com/unitreerobotics/unibot_submission/main/README.md>
- 数据集集合：<https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset>
- WLA 仓库：<https://github.com/unitreerobotics/unifolm-wla>
- WLA 动作/状态规范：<https://github.com/unitreerobotics/unifolm-wla/blob/main/docs/robot_action_state_processing_en.md>
- WLA 微调文档：<https://github.com/unitreerobotics/unifolm-wla/blob/main/docs/train_action_expert_en.md>
- 官方仿真：<https://github.com/unitreerobotics/unitree_sim_isaaclab>、<https://github.com/unitreerobotics/unitree_mujoco>
- 提交示例：<https://github.com/unitreerobotics/unibot_submission/blob/main/example/example_policy.py>、<https://github.com/unitreerobotics/unibot_submission/blob/main/example/example_env.py>

经典/控制理论（作者-年份，未附链接，复现包需补 DOI）：

- Anderson, R. J., & Spong, M. W. (1989). Bilateral control of teleoperators with time delay. *IEEE Transactions on Automatic Control*.
- Niemeyer, G., & Slotine, J.-J. E. (1991). Stable adaptive teleoperation. *IEEE Journal of Oceanic Engineering*.
- Hannaford, B., & Ryu, J.-H. (2002). Time-domain passivity control of haptic interfaces. *IEEE Transactions on Robotics and Automation*.
- Artigas, J., et al. (2002). A novel theory for sampled data system passivity. *IEEE/RSJ IROS*.
- Smith, O. J. M. (1957). Closer control of loops with dead time. *Chemical Engineering Progress*.
- Chaumette, F., & Hutchinson, S. (2006/2007). Visual servo control, Parts I–II. *IEEE Robotics & Automation Magazine*.
- Siciliano, B., et al. (2009). *Robotics: Modelling, Planning and Control*. Springer.

**UNVERIFIED（不得进入论证链）**：第 10–12 轮中形如 `2609.xxxxx`、`2608.xxxxx` 的 arXiv 编号，年份前缀异常，本轮不采用。

## 11. 一句话押注

**保留 CHUNK-SERVO 的双频执行与演示相对目标，把伺服层从「按 RTT 调增益」升级为「虚拟力 + 时域无源性」：监测视觉伺服虚拟端口的能量，在可变时延注入能量时按需耗散，用遥操作演示导出的相位阻抗表设定基线增益，用预注册的分层贝叶斯实验判定它是否真涨点——因为一个没有稳定性证明的闭环，和一个没有统计纪律的涨点，都不值得发表。**

## 12. 本轮最大的风险

**虚拟力不是真实接触力，基于虚拟端口的无源性只能证明「视觉误差回路不振荡」，不能证明「物理接触不撞坏」；若真实接触的摩擦/非线性主导，这套理论可能既保守又不对症。**
<!-- ARTIFACT:END -->
