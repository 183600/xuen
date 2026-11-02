# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 14 轮（研究线累计；本轮灵感循环第 1 轮）· VOI-MAP：把「语音指令」变成语义地图上的目标分布，用「价值信息/成本」决定何时调用 VLA、何时主动看一眼、何时直接伺服

> 检索/复核日期：**2026-11-02（UTC）**。赛事身份不变：宇树 **UniBot 世界挑战赛**（unibot.unitree.com），G1 + Dex1，32 项桌面任务，通才单模型赛道，选手自部署 + 官方远程真机 API。本轮三个词是「语音交互」「成本控制」「语义地图」。**不推倒**第 10 轮 FACT-VLA、第 11 轮 GEO-RESIDUAL、第 12 轮 CHUNK-SERVO、第 13 轮 WAVE-SERVO；VOI-MAP 是它们之上的**元认知层**：它不改变「怎么动」，只决定「动哪个目标、值不值得再花一次计算」。

## 0. 先给直觉：第 13 轮把「手」稳住了，但「眼睛和耳朵」还没有预算

第 13 轮 WAVE-SERVO 解决的是：给定目标位姿，5 步块内的视觉伺服在可变 RTT 下不振荡。它有一个隐含前提：**目标是对的，且值得一直算**。这两个前提在真实评测里都不成立。

1. **抓错物体，伺服再稳也没用。** 32 个桌面任务由语言指令指定目标；一旦把「杯子」听成「帽子」、或把「左边的碗」指到「右边的碗」，TD-PC 只会把你稳定地带到错误的位置。第 10–13 轮一直在优化「最后 3 厘米」，但失败也可能发生在「第 0 厘米」——目标选择。
2. **语言是一个有噪声的信道。** 评测接口给的是语言（很可能是文本）；但赛题面向真实部署，语音才是最终交互形态。即使评测给文本，「口语化、同音词、近音词、改写」的鲁棒性仍是低成本高回报的。用一个精确字符串匹配的解析器，等于假设信道无噪；更糟的是，一旦解析错，系统会自信地执行错。
3. **计算是预算，不是免费资源。** 每次 VLA 调用有延迟、有算力、有 API 风险；每个 5 步块也是一次机会成本。第 12/13 轮把 `H_c=5` 写成常数，第 13 轮把伺服做成常开；这在「目标明确」时是对的，但在「目标不确定」时，把预算花在伺服上可能不如花在「再看一眼」或「重新 grounding」上。**该优化的是每单位成本的成功率，不是单步精度。**

所以本轮的直觉是：**在 WAVE-SERVO 之上加一个「语义地图 + 价值信息」的决策层。** 语义地图是主端与从端共享的工作记忆；语言 grounding 把指令变成地图节点上的一个概率分布；预算调度器在 {直接伺服, 主动看一眼, 调用 VLA, 提交} 之间，按「边际成功增益 / 成本」选动作。

一句话先给押注：

> **把「语音指令」解析成语义地图上的目标分布，而不是一个硬标签；用地图的不确定性和剩余预算共同决定下一次计算买什么——目标清楚就直接伺服，目标含糊就先花小钱看一眼，看一眼还不够才调用昂贵的大模型；每次计算都要能说清楚它买到了多少成功概率。**

三个可验证创新点：

1. **语音鲁棒 grounding**：语音/文本 → 任务 schema → 地图候选分布；用音素编辑距离 + 同音词表处理 ASR 噪声，且**不硬提交**，把歧义传给调度器。用 G10 验证「grounding MAP 准确率 / 校准」。
2. **语义地图作为共享信念**：对象级地图（位姿、协方差、存在置信、颜色/类别）由经典立体视觉 + 数据关联维护，**不引入第二个学习模型**；地图不确定性直接驱动「看一眼」的价值。用 G12 验证「位姿误差 / 关联切换」。
3. **价值信息预算调度**：把每 episode 的 VLA 调用、LOOK、伺服步数建模成带成本的序列决策；用边际增益/成本贪心选择，并在预算紧张时自动退化为 CHUNK-SERVO。用 G11 + 合成实验验证「成功率/成本」。

三个词怎么落地：

| 词 | 落地 | 不做什么 |
|---|---|---|
| **语音交互** | ASR 噪声下的 schema 解析；同音/近音编辑距离；歧义不硬提交；用「主动看一眼」代替向人追问；模块间的符号 backchannel | 不训练 ASR/TTS；不做真人对话；不把 VLA 伪装成语言模型 |
| **成本控制** | VLA 调用、LOOK、伺服步数的统一成本；边际增益/成本；预算紧张自动降级；预注册成本指标 | 不把「省算力」当唯一目标；不在正式评测上做预算 A/B |
| **语义地图** | 对象级地图 + 协方差 + 存在置信；语言→地图节点；地图不确定性驱动计算 | 不引入第二个检测/分割模型；不假设腕部有内参；不假设有深度 |

## 1. 研究日志：为什么是现在、为什么是这一层

### 1.1 第 10–13 轮留下的三个「未付费假设」

```text
A1. 目标位姿是对的：grounding 被当成上游已解决。
A2. 计算预算是无限的：默认每个 5 步块都能算伺服、都能调用 VLA。
A3. 语言是干净文本：没有同音词、没有改写、没有口语省略。
```

A1 是最大的漏洞。WAVE-SERVO 的 TD-PC 能证明「视觉误差回路不振荡」，但证明不了「误差定义在一个正确的目标上」。A2 在单端口、低延迟时可以近似成立；在多端口、跨城、API 限流时不成立。A3 在评测文本上可能成立，但和真实产品形态不一致，而且文本指令也会有人类写的省略和指代。

### 1.2 三个会改变方案的新判断

1. **语义地图不需要第二个学习模型，也可以是「够用的」。** 第 10–13 轮反复担心「第二个模型违规」。但桌面场景是刚体、静态、对象少；用头双目立体 + 颜色/深度不连续分割 + 匈牙利数据关联 + 卡尔曼滤波，就能维护对象级地图。类别标签不用检测器，直接用指令里的名词本体，加上颜色/空间关系消歧。这是确定性几何，不是学习模型。**代价**：它会在透明、反光、遮挡、纯色桌面上退化；所以它必须输出协方差，而不是假装自己很准。
2. **「看一眼」比「问一句」更适合这个评测。** 没有真人在环里，主动问「你说的是哪个杯子」不可行。但机器人可以主动改变视角：左右平移、抬高、倾斜，去获取一个能区分候选目标的新观测。这是**主动感知**，也是「语音交互」在自动评测里的可落地版本：用感知动作回答语言歧义。成本远低于一次 VLA 调用。
3. **固定的 30/5 调度在「歧义」面前是错的。** 如果目标不确定，先执行 5 步伺服可能是在错误的物体上浪费 5 步；如果目标很确定，再调用 VLA 是浪费一次昂贵的规划。正确的调度应该同时看**语义不确定性**和**几何执行不确定性**，而不是只看时间。

### 1.3 为什么是「地图 + 价值信息」而不是「更强的语言模型」

一个自然的反应是：上一个更大的 VLM，把指令理解得更好。但这有三个问题：

- **单模型规则**：引入第二个学习模型做 grounding，直接踩线。
- **成本**：每次不确定都调用大模型，延迟和算力都不可接受；而很多歧义用一次「看一眼」就能解决。
- **可解释性/可证伪性**：地图上的目标分布是一个显式的概率对象，可以检查、可以校准、可以在仿真里复现；黑盒 VLM 的 grounding 很难做因果消融。

所以 VOI-MAP 的立场是：**语言理解不一定要更大的模型，可以用「地图 + 主动感知 + 预算」把一个小模型的歧义消化掉。** 这也是「成本控制」真正的含义：不是省钱，是把计算花在信息增益最大的地方。

### 1.4 与第 13 轮的关系

| 层 | 第 13 轮 | 第 14 轮 VOI-MAP |
|---|---|---|
| 语义/目标 | 假设给定 | 输出目标分布 `p(o|u,M)`；歧义显式化 |
| 地图 | 单目标相对位姿 | 对象级地图 + 协方差 + 存在置信 |
| 调度 | 固定 30 步规划 / 5 步伺服 | 按 `Δsuccess/Δcost` 选 SERVO / LOOK / VLA / COMMIT |
| 语言 | 文本条件 | 音素编辑距离 + 同音词 + 不硬提交 |
| 安全 | TD-PC + 限幅 | 继承；新层不新增执行通路 |
| 统计 | 预注册 A/B | 继承；新增「成功率/成本」主端点 |

**保留**：FACT-VLA 的相位化 BC、GEO-RESIDUAL 的几何残差与编辑检测、CHUNK-SERVO 的 30/5 双频、WAVE-SERVO 的 TD-PC 与相位阻抗表、单模型合规、预注册统计纪律。
**升级**：目标从「一个位姿」升级为「地图上的分布」；调度从「固定频率」升级为「预算感知」；语言从「精确匹配」升级为「噪声信道下的分布」。
**剪枝**：不做第二个检测/分割/语言模型；不做真人对话；不把「省算力」当成唯一目标；不在正式 320 trials 上做未验证的预算 A/B。

## 2. 机制草图（先给直觉，形式化见产物区）

### 2.1 语义地图：不是重建，是「够用的对象账本」

```text
M_t = { o_i = (id_i, label_i, μ_i, Σ_i, ν_i) } ∪ F_t
```

- `μ_i, Σ_i`：对象在桌面坐标系的位置与协方差（头双目三角化 + 卡尔曼）；
- `label_i`：来自指令名词本体 + 颜色/关系属性，不是检测器；
- `ν_i`：存在/可见置信，用于出生/死亡与「要不要再看一眼」；
- `F_t`：自由空间栅格，用于碰撞与可达性检查。

关键设计：**地图必须输出不确定性**。如果地图假装 `Σ=0`，调度器就永远不会选择 LOOK，整个预算层退化成固定调度。

### 2.2 语音 grounding：从字符串到分布

```text
u (ASR 文本) → 规范化 → schema σ(u) = (verb, target, reference, relation, constraints)
            → 候选集 C = {o_i : label_i ≈ target}
            → 打分 s_i = w_l·sim(label_i,target) + w_c·color + w_g·geometry + w_p·phonetic
            → p(o_i|u,M) = softmax(s_i / T)
```

三个细节：

1. **音素编辑距离**：`cup→cub` 能被纠正，`cup→cap` 不能（真同音）。所以不能承诺「语音鲁棒」，只能承诺「近音鲁棒 + 同音交给地图/主动感知」。
2. **不硬提交**：如果 top-2 的后验差小于阈值，保留分布，交给调度器。硬 argmax 会把一个可恢复的歧义变成一个不可恢复的错误。
3. **几何先验**：`left of the bowl` 不是字符串匹配，是地图上的一个区域势函数；这比纯语言模型更准，也更便宜。

### 2.3 预算调度：买信息，不买「更多计算」

每个决策点，候选动作：

| 动作 | 成本 | 作用 |
|---|---|---|
| `SERVO` | 1 个 5 步块 | 降低几何误差，不改变目标信念 |
| `LOOK` | ≈1–2 个块（小幅视角移动） | 降低目标熵；对近音/遮挡有效，对真同音可能无效 |
| `VLA` | 5 个块（含延迟） | 重新规划/重新 grounding；对长程和多阶段任务价值更大 |
| `COMMIT` | 0 | 停止收集信息，执行当前 MAP 目标 |

规则：`a* = argmax_a ΔE[success|a] / cost(a)`，只有当边际收益超过机会成本时才买。预算紧张时，`SERVO` 自然占优；目标很清楚时，`COMMIT` 自然占优；目标含糊且看一眼便宜时，`LOOK` 自然占优。**这不是一个固定的状态机，是一个可解释的分配器。**

### 2.4 「对话」在哪里

- **外部对话**：人说一句 → 系统解析成分布 → 系统用「看一眼」来问场景，而不是向人追问；
- **内部对话**：VLA 的计划被抽象成符号子目标（`approach(target)`、`grasp(target)`、`place(target, ref)`），执行器回传状态符号（`APPROACHED`、`CONTACT`、`SLIP`、`OCCLUDED`）。这些符号是确定性地从几何/夹爪状态派生的，不是第二个模型。它们让「慢规划器」和「快伺服」有一个低带宽、可解释的接口。

这个「符号 backchannel」是「语音交互」在系统内部的类比：**用离散符号交换意图和状态，而不是每步都传高维动作。**

## 3. 可证伪的假设

| 编号 | 假设 | 证伪条件 | 级别 |
|---|---|---|---|
| H1 | 音素编辑距离 + 不硬提交，在高 ASR 噪声下提升 grounding MAP 准确率 | 相对精确匹配无提升，或校准更差 | 主 |
| H2 | 预算调度在相同成功率下降低平均成本（或相同成本下提升成功率） | 相对固定 5 步无成本/成功率优势 | 主 |
| H3 | 预算紧张时调度器自动退化为 SERVO，不出现「为了消歧把预算花光」 | 紧预算下显著差于纯 SERVO | 主（安全性） |
| H4 | 完整 VoI 贪心显著优于「置信度门控的 LOOK」这一简单启发式 | 两者差值的 CI 跨 0 | 次（证伪性） |

H4 是刻意写成「可能失败」的：如果完整 VoI 不比一个简单门控好，就应该砍掉复杂度，只保留门控。**一个不能证伪自己复杂度的方案，不值得工程化。**

## 4. 什么情况下放弃这条线

- 语义地图在真实桌面上的位姿误差 > 2cm，且 LOOK 不能降低关联歧义 → 地图不可用，退回「任务级固定目标 + WAVE-SERVO」。
- 语言指令在评测中几乎无歧义（每个任务只有唯一目标且措辞固定）→ VOI-MAP 的 grounding 部分价值下降，只保留预算调度。
- 预算调度的收益 < 5% 成本节省，且 H4 失败 → 砍掉调度器，保留「置信度门控」。
- 真实延迟下 LOOK 的移动本身触发超时 → LOOK 只在 APPROACH 早期允许，CONTACT 段禁用。

## 5. 一句话押注

**第 13 轮证明了「给定目标时手是稳的」；本轮押注「目标本身是一个分布，计算是一种预算」：用语义地图承载这个分布，用音素编辑距离消化语音噪声，用边际信息增益/成本决定下一次计算买什么——目标清楚就伺服，含糊就先看一眼，看一眼不够才调用大模型。**

## 6. 本轮最大的风险

**语义地图的观测前端（无第二个学习模型、腕部无内参、无主动深度，头双目在透明/反光/弱纹理上不可靠）可能太弱，导致目标后验本身就是错的；此时再精细的 VoI 调度也只是在一个错误的后验上做最优分配，整个元认知层会变成「用更聪明的方式分配预算去执行错误的目标」。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 14 轮产物 · VOI-MAP 技术报告

> 检索/复核日期：**2026-11-02（UTC）**。对象：宇树 **UniBot 世界挑战赛**（G1 + Dex1，32 项桌面任务，通才单模型赛道，选手自部署 + 官方远程真机 API）。本报告是研究线累计第 14 轮、也是新一轮灵感循环第 1 轮「语音交互 / 成本控制 / 语义地图」的工程化产物。它在第 13 轮 **WAVE-SERVO** 之上加一个**元认知层**，不替换第 10 轮 FACT-VLA、第 11 轮 GEO-RESIDUAL、第 12 轮 CHUNK-SERVO。

## 0. 结论与边界

### 0.1 一句话结论

第 13 轮证明了「给定目标时，5 步块内的视觉伺服在可变时延下可以保持虚拟端口无源」；本轮把问题往前推一步：**目标本身不是给定的，而是一个由语言和语义地图产生的分布；计算也不是免费的，而是一个有限预算。** VOI-MAP 用语义地图承载目标分布，用音素编辑距离消化语音噪声，用「边际成功增益 / 成本」在 `SERVO / LOOK / VLA / COMMIT` 之间分配预算。它不改变执行层，只决定「动哪个目标、值不值得再花一次计算」。

### 0.2 证据等级

| 等级 | 含义 | 本报告中的例子 |
|---|---|---|
| A | 官方文档、提交模板、数据集元数据、经典文献直接核实 | 规则/API、32 任务、33,276 eps、WLA `chunk_size=30`、无 depth/force |
| B | 本轮在公开数据/公式/合成实验上做的分析，可复现 | 合成预算实验、grounding 准确率、复杂度估算 |
| C | 设计假设，需 G0–G12 验证 | 真实桌面上的地图精度、LOOK 的信息增益、VoI 在真机上的收益 |
| U | 未核验，不得进入论证链 | 第 10–13 轮中形如 `2609.xxxxx` 的异常 arXiv 编号 |

### 0.3 本轮不做什么

- 不训练第二个检测/分割/语言/ASR 模型；语义地图用经典立体视觉 + 数据关联，标签来自指令名词本体。
- 不做真人实时对话/追问；评测是自动 `get_action`，没有人在环里。
- 不假设腕部相机有内参、不假设有深度图、不假设有 F/T 或触觉。
- 不把合成实验当作真机证据；不把 5 次 A/B 当显著性结论。
- 不依赖不可核验的 arXiv 编号。

## 1. 承接：第 13 轮解决了什么、没解决什么

### 1.1 已解决

- 第 12 轮：30 步开环 → 5 步闭环，降低反馈周期；DG-KEYFRAME 相对目标。
- 第 13 轮：把 5 步块内的修正从「PD + 增益调度」升级为「虚拟力 + TD-PC」；给出离散时延裕度 `a < 2 sin(π/(2(2d+1)))`，并证明虚拟端口的累计能量 `E_obs ≥ 0`。
- 结论：**在执行层，给定目标位姿，系统有稳定性论证和确定性回退。**

### 1.2 未解决

| 问题 | 第 13 轮的隐含假设 | 本轮的处理 |
|---|---|---|
| 目标选错 | 目标位姿由上游给定且正确 | 目标变成地图上的分布 `p(o|u,M)`；歧义显式化 |
| 语言噪声 | 文本干净、精确匹配 | 音素编辑距离 + 同音词表 + 不硬提交 |
| 计算预算 | 每个 5 步块都算伺服/可调 VLA | 统一成本模型 + 边际增益/成本调度 |
| 地图 | 单目标相对位姿 | 对象级地图 + 协方差 + 存在置信 |
| 主动感知 | 无 | `LOOK`：用视角移动换取信息增益 |

### 1.3 本轮的三个新判断

1. **Grounding 错误是不可伺服的。** 抓错物体时，TD-PC 的稳定性反而会让错误执行得更稳、更彻底。目标选择必须在执行前/执行中被显式建模为不确定性。
2. **语言鲁棒性有上限，必须承认。** 音素编辑距离能修 `cup→cub`，修不了 `cup→cap` 这种真同音；真同音要靠地图几何、颜色、或主动看一眼。**不承诺「语音鲁棒」，只承诺「近音鲁棒 + 同音可检测 + 歧义可行动」。**
3. **固定调度在歧义面前是错的。** 「总是 5 步伺服」在目标明确时最优，在目标含糊时会把预算花在错误物体上；「不确定就调用 VLA」在长程任务上可能对，但成本高、延迟大。正确对象是**边际信息增益/成本**。

## 2. 符号与形式化

### 2.1 语义地图

设桌面坐标系为 `W`。时刻 `t` 的语义地图：

```math
M_t = \bigl(\{o_i\}_{i=1}^{N_t},\; F_t\bigr),\qquad
o_i = (\mathrm{id}_i,\ \ell_i,\ \mu_i,\ \Sigma_i,\ \nu_i)
```

- `\mu_i \in \mathbb R^3`：对象位置（本方案先做位置，姿态按任务需要再做）；
- `\Sigma_i \in \mathbb R^{3\times3}`：位置协方差；
- `\ell_i`：标签（来自指令名词本体 + 颜色/关系属性）；
- `\nu_i \in [0,1]`：存在/可见置信；
- `F_t`：桌面自由空间栅格（用于碰撞/可达性检查）。

**观测前端（无第二个学习模型）**：

```text
头双目校正图像 → 视差 → 桌面点云 P_t（下采样到 ~2k 点）
              → 深度/颜色不连续分割 → 区域 R_t = {r_j}
              → 区域质心 z_j、协方差 R_j、颜色直方图
```

不使用的：腕部相机做米制（无内参）、任何学习型检测/分割器、任何深度网络。

### 2.2 地图更新：门控 + 匈牙利 + 卡尔曼

对每个已有对象 `i`，预测：

```math
\mu_i^- = \mu_i^{t-1},\qquad \Sigma_i^- = \Sigma_i^{t-1} + Q
```

对每个观测区域 `j`，马氏距离：

```math
d_{ij}^2 = (z_j-\mu_i^-)^\top(\Sigma_i^-+R_j)^{-1}(z_j-\mu_i^-)
```

只保留 `d_{ij}^2 \le \gamma^2` 的边，用匈牙利算法最大化总似然。匹配上的做卡尔曼更新：

```math
K_i = \Sigma_i^-(\Sigma_i^-+R_j)^{-1},\quad
\mu_i = \mu_i^- + K_i(z_j-\mu_i^-),\quad
\Sigma_i = (I-K_i)\Sigma_i^-
```

未匹配区域：若点数足够且能对应指令名词，则新建对象（大方差）；未匹配对象：`\nu_i` 衰减，超过 `\tau_{out}` 帧后保留但增大 `\Sigma_i`（不立即删除，避免遮挡导致的身份丢失）。

**关键设计**：`\Sigma_i` 必须真实反映不确定性。若地图假装 `\Sigma_i=0`，调度器永远不会选择 `LOOK`，预算层退化为固定调度。

### 2.3 语言 schema 与 grounding 后验

指令 `u` 先规范化为 schema：

```math
\sigma(u) = (\mathrm{verb},\ \mathrm{target},\ \mathrm{reference},\ \mathrm{relation},\ \mathrm{constraints})
```

候选集：

```math
C_t(\tau) = \{o_i : \ell_i \in \mathrm{syn}(\tau)\ \text{或颜色/关系匹配}\}
```

打分：

```math
s_i = w_\ell\,\mathbb 1[\ell_i\in\mathrm{syn}(\tau)]
    + w_c\,\mathbb 1[\mathrm{color}_i\in C]
    + w_g\,\phi_{\mathrm{rel}}(\mu_i;\rho,r)
    - w_p\,d_{\mathrm{phon}}(\tau_{\mathrm{asr}},\ell_i)
```

其中 `\phi_{\mathrm{rel}}` 是几何关系势函数。例如 `left of the bowl`：

```math
\phi_{\mathrm{left}}(x_i;x_\rho) =
-\frac{1}{2\sigma_x^2}\bigl((x_i-x_\rho)+\delta\bigr)^2
-\lambda\,\mathbb 1[x_i>x_\rho]
```

后验：

```math
p(o_i\mid u,M_t) = \frac{\exp(s_i/T)}{\sum_{j\in C_t}\exp(s_j/T)}
```

**音素距离**（确定性、无学习）：

```math
d_{\mathrm{phon}}(a,b) = \min\bigl(\mathrm{Lev}(a,b),\ \mathrm{Lev}(\mathrm{sk}(a),\mathrm{sk}(b))+0.5\bigr)
```

`Lev` 是 Levenshtein 编辑距离，`sk` 是一个小的确定性音素骨架映射（去元音、合并清浊）。同音词表单独维护，用于标记「真同音」——这类歧义不靠编辑距离解决，交给 `LOOK`/几何。

**不硬提交**：若

```math
\frac{p_{(1)}}{p_{(2)}} < \rho_{\mathrm{amb}}
```

则保留分布，调度器看到高熵，选择 `LOOK` 或 `VLA`，而不是 argmax 后直接执行。

### 2.4 预算化决策过程

状态：

```math
x_t = (b_t,\ p_t,\ \phi_t,\ B_t,\ M_t)
```

- `b_t`：目标后验（由 §2.3 得到，随 LOOK/VLA 更新）；
- `p_t`：执行进度（已执行的伺服步数/块数）；
- `\phi_t`：相位（APPROACH / PRECONTACT / CONTACT / CARRY）；
- `B_t`：剩余预算（归一化成本单位）；
- `M_t`：语义地图。

动作与成本：

| 动作 | 成本 | 对信念/进度的影响 |
|---|---|---|
| `SERVO` | `c_s` | `p \leftarrow p+\delta`；`b` 不变 |
| `LOOK` | `c_l` | 以概率 `q_l` 把 `b` 收敛到真值；否则不变；`p` 不变 |
| `VLA` | `c_v` | 以概率 `q_v` 把 `b` 收敛到真值；并可重规划（长程任务额外收益） |
| `COMMIT` | 0 | 停止收集信息，执行当前 MAP 目标 |

成功模型（MAP 近似）：

```math
P_{\mathrm{succ}}(b,p) \approx \Bigl(\max_i b_i\Bigr)\cdot f(p),\qquad
f(p)=1-e^{-p/p_0}
```

更一般的写法是 `\sum_i b_i f_i(p)`；本报告为可解释性使用 MAP 近似，并在 §5.5 说明它偏向「只抓一个目标」的任务。

**一步边际增益**：

```math
\Delta_{\mathrm{servo}} = c\,[f(p+\delta)-f(p)],\qquad c=\max_i b_i
```

```math
\Delta_{\mathrm{look}} = (c'_l-c)\,f(p),\qquad c'_l = q_l\cdot 1 + (1-q_l)\,c
```

```math
\Delta_{\mathrm{vla}} = (c'_v-c)\,f(p) + \Delta_{\mathrm{plan}},\qquad c'_v = q_v\cdot 1 + (1-q_v)\,c
```

其中 `\Delta_{\mathrm{plan}}` 是 VLA 的重新规划收益（本轮合成实验设为 0，因此实验对 VLA 是**保守的**）。

**调度规则**：

```math
a^\star = \arg\max_{a\in\{\mathrm{SERVO},\mathrm{LOOK},\mathrm{VLA}\}}
\frac{\Delta_a}{c_a}
\quad\text{s.t.}\quad c_a\le B_t
```

若最大比值低于机会成本阈值 `\lambda`，或 `c\ge c_{\mathrm{stop}}` 且 `p\ge p_{\mathrm{stop}}`，则 `COMMIT`。

### 2.5 与 POMDP 的关系

严格的问题是有限时域 POMDP：

```math
\max_\pi\ \mathbb E\Bigl[\sum_t \mathrm{success}_t - \eta\sum_t \mathrm{cost}_t\Bigr]
```

上述规则是**一步贪心**，忽略了「现在买的信息会影响未来动作」的期权价值。它便宜、可解释、可在 CPU 上实时算；但它是近似，不是最优。第 6 节会把这个近似本身作为一个可证伪假设（H4）。

## 3. 算法

### 3.1 分层结构

```text
                    ┌─────────────────────────────────────────────┐
                    │ Evaluator (N ports, delayed websocket)      │
                    └──────────────────┬──────────────────────────┘
                                       │ obs / action chunk
                                       ▼
        ┌──────────────────────────────────────────────────────────┐
        │ Per-port PolicyService (CPU)                             │
        │                                                          │
        │  ┌────────────────────────────────────────────────────┐  │
        │  │ L3  VOI-MAP 元认知层（本轮新增）                    │  │
        │  │  semantic map M_t                                   │  │
        │  │  grounding p(o|u,M_t)                               │  │
        │  │  budget scheduler: SERVO / LOOK / VLA / COMMIT      │  │
        │  └───────────────────────┬────────────────────────────┘  │
        │                          │ selected action              │
        │  ┌───────────────────────▼────────────────────────────┐  │
        │  │ L2  WAVE-SERVO（第 13 轮）                          │  │
        │  │  virtual force F̂, TD-PC, phase impedance table      │  │
        │  │  5-step correction, delay estimate, clamps          │  │
        │  └───────────────────────┬────────────────────────────┘  │
        │                          │ 30/5 chunk                 │
        │  ┌───────────────────────▼────────────────────────────┐  │
        │  │ L1  VLA server（唯一学习模型，GPU，~1Hz）            │  │
        │  │  UnifoLM-WLA-1.0, 30-step plan                      │  │
        │  └────────────────────────────────────────────────────┘  │
        └──────────────────────────────────────────────────────────┘
```

VOI-MAP 只决定「调用哪一层、什么时候调用、目标是谁」；它不直接产生关节/末端动作；所有执行仍经过 L2 的 TD-PC 和限幅。

### 3.2 地图更新伪代码

```python
def update_map(M, stereo_rgb, instruction, dt):
    P = stereo_pointcloud(stereo_rgb)          # head stereo, table frame
    regions = segment_depth_color(P, stereo_rgb)
    preds = [predict(o, dt) for o in M.objects]  # static: mu^- = mu, Sigma^- = Sigma + Q
    edges = []
    for i, o in enumerate(preds):
        for j, r in enumerate(regions):
            d2 = mahalanobis(r.centroid, o.mu, o.Sigma + r.cov)
            if d2 <= GATE2:
                edges.append((i, j, d2))
    matches = hungarian_max_likelihood(edges)
    for i, j in matches:
        M.objects[i] = kalman_update(preds[i], regions[j])
    for j in unmatched(regions):
        if region_is_object(regions[j]) and label_compatible(instruction, regions[j]):
            M.objects.append(birth(regions[j]))   # large Sigma
    for o in unmatched(M.objects):
        o.nu *= DECAY
        o.Sigma += Q_LOST                      # keep identity, inflate uncertainty
    M.free_space = update_occupancy(M.free_space, P)
    return M
```

### 3.3 Grounding 伪代码

```python
def ground(instruction, M):
    schema = canonicalize(instruction)          # verb/target/reference/relation/constraints
    cands = [o for o in M.objects if label_match(o.label, schema.target)]
    if not cands:
        return None, 1.0                    # high entropy -> scheduler will LOOK/VLA
    scores = []
    for o in cands:
        s = W_L * label_score(o.label, schema.target)
        s += W_C * color_score(o.color, schema.constraints)
        s += W_G * relation_potential(o.mu, schema)
        s -= W_P * phonetic_distance(schema.target_asr, o.label)
        scores.append(s)
    p = softmax(scores, T)
    return p, entropy(p)

def should_commit(p, ratio_thresh):
    p_sorted = sorted(p, reverse=True)
    return len(p) == 1 or (p_sorted[0] / max(p_sorted[1], 1e-9) >= ratio_thresh)
```

### 3.4 LOOK：用视角换信息

`LOOK` 不是任意移动。候选是有限个**小幅、可逆、限速**的视角动作：

```text
{left 3cm, right 3cm, up 3cm, tilt_left 5°, tilt_right 5°}
```

选择规则：对每个候选视角 `v`，用当前地图与分割模型预测「哪些候选对象会变得可区分」，得到期望熵减 `\Delta H(v)`；选

```math
v^\star = \arg\max_v \frac{\Delta H(v)}{c_{\mathrm{look}}(v)}
```

实现上不训练新模型：用几何遮挡关系 + 颜色直方图 + 当前 `\Sigma_i` 做一个确定性的代理。若 `\Delta H(v^\star) < \epsilon`（看一眼也分不清），则不浪费预算，转而选择 `VLA` 或按几何先验 `COMMIT`。

**相位约束**：`LOOK` 只在 APPROACH/PRECONTACT 允许；CONTACT/CARRY 禁止（会破坏接触/抓取）。

### 3.5 预算调度伪代码

```python
def schedule(belief, progress, phase, budget, M, cfg):
    c = max(belief)
    f = lambda p: 1.0 - math.exp(-p / cfg.p0)

    # COMMIT if confident enough and execution far enough
    if c >= cfg.c_stop and progress >= cfg.p_stop:
        return COMMIT

    opts = []
    if budget >= cfg.c_servo:
        opts.append((SERVO, c * (f(progress + cfg.delta) - f(progress)), cfg.c_servo))
    if phase in (APPROACH, PRECONTACT) and budget >= cfg.c_look and cfg.looks < cfg.max_looks:
        c_after = cfg.q_look + (1 - cfg.q_look) * c
        opts.append((LOOK, (c_after - c) * f(progress), cfg.c_look))
    if budget >= cfg.c_vla and cfg.vlas < cfg.max_vla:
        c_after = cfg.q_vla + (1 - cfg.q_vla) * c
        opts.append((VLA, (c_after - c) * f(progress) + cfg.delta_plan, cfg.c_vla))
    if not opts:
        return COMMIT

    act, gain, cost = max(opts, key=lambda o: o[1] / o[2])
    if gain / cost < cfg.lambda_opportunity:
        return COMMIT
    return act
```

### 3.6 与 WAVE-SERVO 的接口

- `SERVO`：调用第 13 轮的 5 步块；虚拟力、TD-PC、相位阻抗表、限幅全部不变。
- `VLA`：异步请求 30 步计划；拿到后缓存，按 5 步切片；不阻塞当前伺服。
- `LOOK`：小幅视角动作，不经过 VLA；动作本身仍受关节限位/速度限幅。
- `COMMIT`：停止收集信息，执行当前 MAP 目标；若执行中编辑检测触发（第 11 轮），回到 `LOOK`/`VLA`。
- **安全继承**：VOI-MAP 不新增执行通路；所有动作仍是第 13 轮安全集的子集。

### 3.7 `get_action` 伪代码

```python
class VoiMapPolicy:
    def __init__(self):
        self.M = SemanticMap()
        self.plan = None
        self.belief = None
        self.progress = 0
        self.phase = "APPROACH"
        self.budget = BUDGET0
        self.looks = 0
        self.vlas = 0

    def get_action(self, obs):
        self.M = update_map(self.M, obs.stereo, obs.instruction, obs.dt)
        self.phase = observe_phase(self.M, obs)          # round 11/12
        if edit_detected(obs):
            self.phase = "RECOVER"

        belief, H = ground(obs.instruction, self.M)
        if belief is None or H > H_MAX:
            act = LOOK if self._look_worth_it() else VLA
        else:
            act = schedule(belief, self.progress, self.phase, self.budget, self.M, CFG)

        if act == SERVO:
            self.progress += 1
            self.budget -= CFG.c_servo
            return self._wave_servo_chunk(obs, self._map_target(belief))
        if act == LOOK:
            self.looks += 1
            self.budget -= CFG.c_look
            return self._look_action(obs)
        if act == VLA:
            self.vlas += 1
            self.budget -= CFG.c_vla
            self._request_plan_async(obs)
            return self._safe_hold_or_last_chunk()
        return self._commit_action(obs, belief)          # COMMIT
```

规则：

- 任何异常 → 返回上一合法 chunk 或安全 hold；绝不返回 NaN/错误形状。
- 每个端口独立维护地图、信念、预算、计数。
- `VLA` 除冷启动外不阻塞；plan 过期时用旧 plan + 伺服。

### 3.8 状态机

```text
INIT → GROUND → {SERVO | LOOK | VLA | COMMIT}
                  │        │       │
                  │        │       └─→ PLAN → APPROACH → ...
                  │        └─→ 更新地图/信念 → GROUND
                  └─→ APPROACH → PRECONTACT → CONTACT → CARRY → DONE
                                         │
                                         └─ edit_score>θ_e → RECOVER → GROUND
```

与第 13 轮的状态机相比，新增 `GROUND` 和 `LOOK` 两个节点；`RECOVER` 回到 `GROUND` 而不是直接重规划，这样「目标错了」和「目标对了但执行失败」被区分开。

## 4. 性质、复杂度与正确性

### 4.1 Grounding 的 Bayes 解释

**命题 1（模型内最优）**：把 §2.3 中除音素项以外的打分写成先验能量

```math
p(o_i)\ \propto\ \exp\!\Bigl(\frac{w_\ell \mathbb 1[\ell_i\in\mathrm{syn}]+w_c\mathbb 1[\mathrm{color}_i\in C]+w_g\phi_{\mathrm{rel}}}{T}\Bigr),
```

把音素项写成似然

```math
p(z\mid o_i)\ \propto\ \exp\!\Bigl(-\frac{w_p\,d_{\mathrm{phon}}(z,\ell_i)}{T}\Bigr),
```

则 `p(o_i|z) ∝ p(z|o_i)p(o_i)` 正好是 §2.3 的 softmax；MAP 选择最小化 0-1 损失。

**证明**：由 Bayes 公式，`p(o_i|z) ∝ p(z|o_i)p(o_i)`；指数相加即得 softmax；0-1 损失的贝叶斯最优决策是后验众数。∎

**边界**：这证明的是「在假设的噪声模型下最优」，不是「在真实 ASR 下最优」。若真实噪声不同（例如同音词不是对称替换），后验会 misspecified；必须用 G10 的 ECE 校准来检验，而不是把命题 1 当现实保证。

### 4.2 调度器的一步最优性与多步缺口

**命题 2（一步分数背包）**：在单步决策、成本可加、动作互斥的设定下，`\arg\max_a \Delta_a/c_a` 是「单位成本成功增益」最大的动作。

**证明**：对任意两个动作 `a,b`，比较 `\Delta_a/c_a` 与 `\Delta_b/c_b`；比值大者在固定成本下增益更大，或在固定增益下成本更低。单步可行域是离散的，逐项比较即得。∎

**多步缺口**：真正的目标是有限时域 POMDP；一步贪心忽略了「信息影响未来」的期权价值。若把「购买的信息」看成集合函数，且期望成功对购买集合是单调自适应次模的、成本可加，则自适应贪心有一常数近似（Golovin & Krause, 2011）。**但本方案没有证明自己的成功模型满足自适应次模性**，所以只声明「一步局部最优 + 经验有效」，不声明全局近似比。这是本轮刻意保留的理论缺口。

### 4.3 非退化与安全继承

**命题 3（极限退化）**：

- 若目标唯一（`|C|=1`）且预算充足，则 `c=1`，`LOOK/VLA` 的边际增益为 0，调度器选择 `SERVO` 直到 `p≥p_stop`，再 `COMMIT`；行为退化为 WAVE-SERVO。
- 若预算只够 `SERVO`（`B<c_l` 且 `B<c_v`），动作集只剩 `SERVO/COMMIT`；行为退化为 CHUNK-SERVO。
- 若预算为 0，返回安全 hold/上一 chunk；行为退化为开环 VLA。

**证明**：逐条检查动作集与 `\Delta/c` 的符号即可。∎

**命题 4（安全继承）**：VOI-MAP 的输出是 `{SERVO, LOOK, VLA, COMMIT}` 之一；`SERVO`/`VLA` 产生的动作经过第 13 轮的 TD-PC 与限幅；`LOOK` 是头部/躯干限速、限位、可逆的小幅视角动作；`COMMIT` 是保持/停止。故 VOI-MAP 的可达动作集是第 13 轮安全集的子集，虚拟端口的无源性保证不被破坏。

**证明**：由构造，VOI-MAP 不直接写关节/末端指令，只选择已有安全动作；安全集对子集封闭。∎

**边界**：这仍然只保证「虚拟端口无源」和「动作在限幅内」，**不保证物理接触不撞坏**——这是第 13 轮的最大风险，本轮没有消除。

### 4.4 复杂度

| 模块 | 复杂度 | 典型值（N≤20, P≤2k, |u|≤20） |
|---|---|---|
| 点云/分割 | `O(P)` | ~0.5 ms |
| 数据关联 | `O(N^3)`（匈牙利） | N=20 → <0.2 ms |
| 卡尔曼 | `O(N)` | <0.05 ms |
| Grounding | `O(|C|\cdot|u|\cdot L)` | <0.1 ms |
| 调度 | `O(|A|)=4` | <0.01 ms |
| **总计（CPU 开销）** | — | **<2 ms / get_action** |

总延迟仍由 VLA 推理与网络主导；VOI-MAP 的 CPU 开销相对可忽略。内存 `O(N + |F_t|)`，单端口 <50 MB。

### 4.5 为什么不是「总是调用 VLA」或「总是伺服」

- **总是 VLA**：每次 `c_v` 高；在 32×10 的评测里，延迟和限流会直接变成 timeout；而且 VLA 对「最后 3 厘米」的几何精度不如 5 步伺服（第 12 轮已论证）。合成实验里 `always_vla` 在所有预算档都被支配（§5.3）。
- **总是伺服**：目标错时，伺服越稳越糟；没有机制去获取新信息。
- **固定 LOOK-first**：在简单任务上浪费一次 LOOK；在预算紧张时挤掉执行步。合成实验里 `look_first` 的平均 succ/cost 低于 `look_gate` 和 VOI（§5.3）。
- **VOI-MAP**：把「要不要买信息」变成显式决策；预算紧时自动退化为伺服，目标清楚时自动跳过 LOOK。

## 5. 本轮合成实验（实跑，B 级证据）

### 5.1 这不是基准证据

这是一个**合成机制检查**，只回答一个问题：在「指令噪声 + 候选歧义 + 硬预算」的玩具模型里，VoI 调度是否比固定调度更省/更准。它不证明真机收益，也不证明地图在真实桌面可用。脚本：`exp/voi_map_sim.py`；结果：`exp/voi_map_results.json`。

### 5.2 生成模型（全部声明，不拟合）

```text
- episode 为 50/50 混合：
    simple:    k=1，无歧义；
    ambiguous: k∈{2,3,4}，ASR 错误率 e。
- ASR：以概率 e 污染标签；其中一半是真同音（音素编辑距离修不了），
  一半是近音（编辑距离能修）。
- grounding 前端：exact-match vs 音素编辑距离。
- 动作成本：SERVO=1（+1 执行进度），LOOK=2（q=0.8 解决目标，最多 2 次），
  VLA=5（q=0.95，最多 1 次）。
- 成功 = 提交目标正确 且 Bernoulli(1-exp(-progress/2.5))。
- 预算 B ∈ {5,8,11,14}；每个格子 5000 episodes；固定种子。
```

**重要简化**：VLA 在玩具里只是一个「消歧器」，没有建模它的重规划/长程价值；因此实验**对 VLA 保守**，不能据此否定 VLA 在长程任务上的作用。

### 5.3 结果

**Grounding MAP 准确率**（混合 simple/ambiguous）：

| ASR 错误率 `e` | exact-match | 音素编辑距离 + 不硬提交 |
|---:|---:|---:|
| 0.10 | 0.969 | **0.994** |
| 0.25 | 0.919 | **0.986** |
| 0.40 | 0.872 | **0.980** |

**预算调度**（对 `e∈{0.10,0.25,0.40}`、`k∈{2,4}` 取平均；格式：成功率 / 平均成本 / 成功率每成本）：

| 预算 B | SERVO | LOOK-first | LOOK-gate | Always-VLA | VOI-MAP |
|---:|---|---|---|---|---|
| 5 | **.852 / 5.00 / .170** | .700 / 5.00 / .140 | .812 / 5.00 / .163 | .000 / 5.00 / .000 | .842 / 5.00 / .168 |
| 8 | **.946 / 8.00 / .118** | .905 / 8.00 / .113 | .939 / 8.00 / .117 | .702 / 8.00 / .088 | .936 / 8.00 / .117 |
| 11 | .956 / 9.16 / .104 | .957 / 10.08 / .095 | .958 / 8.90 / **.108** | .908 / 11.00 / .083 | .957 / 8.85 / **.108** |
| 14 | .960 / 10.32 / .093 | .957 / 10.31 / .093 | .961 / 9.29 / .103 | .958 / 13.02 / .074 | .959 / 8.96 / **.107** |

**高歧义代表行**（`B=11, e=0.40, k=4`）：

| 策略 | 成功率 | 平均成本 | 成功率/成本 |
|---|---:|---:|---:|
| SERVO | .943 | 9.5 | .099 |
| LOOK-first | .957 | 10.1 | .095 |
| LOOK-gate | .953 | 9.1 | .105 |
| Always-VLA | .901 | 11.0 | .082 |
| VOI-MAP | **.959** | 9.1 | **.106** |

### 5.4 读法：哪些假设被支持，哪些没有

**被支持**：

- **F1（H1）**：音素编辑距离在高噪声下显著提升 grounding MAP；`e=0.40` 时 .872→.980。近音错误是主要可修部分；真同音仍会失败，这符合预期。
- **F3（H3）**：预算 `B=5` 时，VOI-MAP 自动退化为近似 SERVO（.842 vs .852，差距 ≤1pp，本轮未做显著性检验），没有出现「为了消歧把预算花光」。这是安全性/鲁棒性证据。
- **F2（H2，弱）**：`B≥11` 时，VOI/LOOK-gate 的成功率每成本高于 SERVO 和 LOOK-first；VOI 在成功率与 SERVO 持平的情况下把平均成本从 9.16 降到 8.85（约 3.4%）。收益是**成本效率**，不是大幅涨点。

**没有被支持**：

- **F4（H4 失败）**：完整 VoI 贪心并没有显著优于「置信度门控的 LOOK」。`VOI - LOOK-gate` 的成功率/成本均值 `+0.0025`，范围 `[-0.001, +0.010]`，跨 0。**结论：在这个玩具里，收益主要来自「门控 + 成本感知」，而不是 VoI 公式本身。** 下一轮应把 LOOK-gate 作为强基线；若真机也不能显著超过它，就砍掉完整 VoI。
- **Always-VLA 被支配**：所有预算档的成功率/成本都最低；`B=14` 时成功率追平 SERVO（.958 vs .960），但平均成本高约 26%。把大模型当万能修复在成本上不成立。
- **低预算下不能靠消歧**：`B=5` 时 SERVO 最好；这提醒我们，VOI-MAP 的价值区间是「预算中等以上 + 歧义非平凡」，不是所有场景。

### 5.5 效度威胁

| 威胁 | 影响 | 下一轮怎么补 |
|---|---|---|
| 地图被假设为完美 | **没有测试最大风险**（地图前端误差/关联错误） | G12：真实/半真实桌面，注入位姿噪声与遮挡 |
| VLA 只建模为消歧器 | 低估 VLA 的长程价值 | 加入多阶段任务与 `Δ_plan` |
| ASR 噪声是合成的 | 真实同音/改写分布未知 | 用任务指令做人工同音/改写集，测 ECE |
| 候选数 ≤4 | 真实桌面可能更多 | 扩到 8–10 个对象 |
| 成本是归一化的 | 真实延迟/限流不同 | 用单任务通道实测 `c_v,c_l,c_s` |
| 无真机 | 不能证明物理接触安全 | 保留第 13 轮的限幅/重试；真机 A/B |

## 6. 实验设计与门

### 6.1 继承第 13 轮的门

G0–G9 继续有效（标定、检索、仿真收敛、真机涨点、干扰恢复、延迟、32 任务稳定、消融、无源、可复现）。本报告只列新增/修改的门。

### 6.2 新增门 G10–G12

| 门 | 问题 | 通过标准 | 失败动作 |
|---|---|---|---|
| **G10** | 语音/文本 grounding 是否鲁棒且校准？ | `e=0.25` 时 MAP ≥0.90；ECE ≤0.10；top-2 歧义不硬提交率 ≥95% | 回退精确匹配 + 任务级固定目标；砍掉语音层 |
| **G11** | 预算调度是否真的省成本？ | `B=11` 时在成功率不低 0.5pp 的前提下平均成本 ≤ SERVO 的 0.97×；`B=14` 时成功率/成本 ≥ SERVO 的 1.10×；`B≤8` 时成功率不低 2pp；LOOK-gate 作为强基线 | 若不能超过 LOOK-gate，砍掉完整 VoI，只保留门控 |
| **G12** | 语义地图是否够用？ | 中位位置误差 ≤1.5cm；关联切换 ≤1 次/episode；归一化 NEES（除以 3）∈ [0.5,1.5] | 只用头双目 PBVS；或退回任务级固定目标 |

### 6.3 预注册假设

| 编号 | 假设 | 主/次 | 证伪条件 |
|---|---|---|---|
| H1 | 音素编辑距离 + 不硬提交提升 grounding MAP | 主 | 相对精确匹配无提升或校准更差 |
| H2 | 预算调度在同等成功率下降低平均成本 | 主 | 相对固定 5 步无成本优势 |
| H3 | 紧预算下自动退化为 SERVO，不出现预算耗尽 | 主（安全） | 紧预算下显著差于纯 SERVO |
| H4 | 完整 VoI 显著优于置信度门控 LOOK | 次（证伪性） | 差值 CI 跨 0 → 砍复杂度 |

**预注册内容**：假设、主/次端点、分析计划、停止规则、排除标准，必须在正式评测前写入仓库并打时间戳。

### 6.4 真机单任务 A/B

| 项 | 设计 |
|---|---|
| 任务 | PlugInEthernet、HangCup、ZipUp、StackBowls、FoldTowel |
| 次数 | 每任务 5 次，配对：SERVO-only vs VOI-MAP，同初始条件 |
| 主端点 | 成功率/成本（成本 = VLA 调用 + LOOK + 伺服步的加权和，权重由实测延迟定） |
| 次端点 | 成功率、p99、timeout、恢复率、grounding 错误率 |
| 统计 | 配对差值 + bootstrap 95% CI；pilot 不宣称显著性 |
| 门 | G3：≥3/5 任务 +10pp；FoldTowel 不回归 >5pp |

### 6.5 全量

| 项 | 设计 |
|---|---|
| 任务 | 32×10 |
| 端口 | N 个连续端口，独立 reset |
| 指标 | 总成功率、步骤分、p99、timeout、平均 VLA 调用数、平均 LOOK 次数 |
| 门 | G6：无端口串扰；reset 干净；内存不涨；p99 ≤150ms |

## 7. 风险与合规

### 7.1 单模型合规

| 模式 | 做法 | 风险 | 建议 |
|---|---|---|---|
| C1 确定性几何 | 地图用立体视觉 + 分割 + 匈牙利 + 卡尔曼 | 最低 | 主推 |
| C2 符号 backchannel | 状态符号由几何/夹爪派生 | 低 | 主推 |
| C3 同 checkpoint 特征 | 若关联需要强描述子，用 VLA encoder | 低–中 | 需要时用，写清 |
| 禁止 | 第二个学习检测/分割/语言模型；在线学习残差 | 高 | 不做 |

### 7.2 风险表

| 风险 | 影响 | 缓解 |
|---|---|---|
| **地图前端太弱** | 目标后验本身错；VoI 在错误后验上做最优分配 | G12；输出协方差；低置信回退固定目标/PBVS；透明/反光只用头双目 |
| 真同音无法消歧 | `cup/cap` 被听错且看一眼也分不清 | 同音词表 + 颜色/几何先验；必要时 VLA；不承诺语音全鲁棒 |
| LOOK 触发超时/遮挡 | 预算反而更紧 | 只在 APPROACH/PRECONTACT；限速限位；`ΔH` 不够就不看 |
| VoI 成功模型 misspecified | 调度选错动作 | 用 LOOK-gate 强基线；G11 直接比较；失败就砍复杂度 |
| VLA 成本被低估 | 调度过度调用 | 用实测延迟/限流更新 `c_v`；预算硬上限 |
| 地图关联切换 | 目标身份跳变 | 马氏门控 + 匈牙利 + `ν` 衰减；`Σ` 膨胀触发 LOOK |
| 统计假阳性 | 把噪声当涨点 | 预注册、配对、分层、Holm、阴性台账 |
| 引用污染 | 假文献支撑真结论 | 引用审计；`UNVERIFIED` 排除 |
| 单模型解释 | 被判第二个模型 | 写清地图/调度无学习权重；C1/C2 为主 |

## 8. 来源

官方/数据（检索日期 2026-11-02，沿用第 13 轮已核实）：

- UniBot 世界挑战赛官网：<https://unibot.unitree.com/>
- 赛事页：<https://unibot.unitree.com/challenges.html>
- 排行榜 JSON：<https://unibot.unitree.com/leaderboard_data.json>
- 提交模板：<https://github.com/unitreerobotics/unibot_submission>
- 提交 README：<https://raw.githubusercontent.com/unitreerobotics/unibot_submission/main/README.md>
- 数据集集合：<https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset>
- WLA 仓库：<https://github.com/unitreerobotics/unifolm-wla>
- WLA 动作/状态规范：<https://github.com/unitreerobotics/unifolm-wla/blob/main/docs/robot_action_state_processing_en.md>
- 官方仿真：<https://github.com/unitreerobotics/unitree_sim_isaaclab>、<https://github.com/unitreerobotics/unitree_mujoco>
- 提交示例：<https://github.com/unitreerobotics/unibot_submission/blob/main/example/example_policy.py>、<https://github.com/unitreerobotics/unibot_submission/blob/main/example/example_env.py>

经典/方法（作者-年份，未在本轮逐篇复核；复现包需补 DOI）：

- Horvitz, E. (1988). Reasoning under varying and uncertain resource constraints. *AAAI*.
- Russell, S., & Wefald, E. (1991). Principles of metareasoning. *Artificial Intelligence*.
- Golovin, D., & Krause, A. (2011). Adaptive submodularity: Theory and applications in active learning and stochastic optimization. *Journal of Artificial Intelligence Research*.
- Bajcsy, R. (1988). Active perception. *Proceedings of the IEEE*.
- Kaelbling, L. P., Littman, M. L., & Cassandra, A. R. (1998). Planning and acting in partially observable stochastic domains. *Artificial Intelligence*.
- Levenshtein, V. I. (1966). Binary codes capable of correcting deletions, insertions, and reversals. *Soviet Physics Doklady*.
- Thrun, S., Burgard, W., & Fox, D. (2005). *Probabilistic Robotics*. MIT Press.
- Chaumette, F., & Hutchinson, S. (2006/2007). Visual servo control, Parts I–II. *IEEE Robotics & Automation Magazine*.
- Jurafsky, D., & Martin, J. H. *Speech and Language Processing*（ASR 混淆/编辑距离背景）.

**UNVERIFIED（不得进入论证链）**：第 10–13 轮中形如 `2609.xxxxx`、`2608.xxxxx` 的 arXiv 编号，年份前缀异常，本轮不采用。

## 9. 一句话押注

**第 13 轮证明了「给定目标时手是稳的」；本轮押注「目标本身是一个分布，计算是一种预算」：用语义地图承载这个分布，用音素编辑距离消化语音噪声，用边际信息增益/成本决定下一次计算买什么——目标清楚就伺服，含糊就先看一眼，看一眼不够才调用大模型。**

## 10. 本轮最大的风险

**语义地图的观测前端（无第二个学习模型、腕部无内参、无主动深度，头双目在透明/反光/弱纹理上不可靠）可能太弱，导致目标后验本身就是错的；此时再精细的 VoI 调度也只是在一个错误的后验上做最优分配，整个元认知层会变成「用更聪明的方式分配预算去执行错误的目标」。** 本轮合成实验刻意假设地图完美，因此这个最大风险还没有被数据触碰。
<!-- ARTIFACT:END -->
