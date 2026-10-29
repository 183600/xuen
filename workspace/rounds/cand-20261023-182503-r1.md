# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
## 0. 本轮结论

这一轮先做了三件“扫雷”：

1. **把官方规则从 Feishu 手册里挖出来**（至少前 2.2 节）：仅通才模型赛道；**单模型完成全部 32 任务，不得混合多个模型**；每任务 **10 次**，5 类泛化各 2 次；单次真机最多 **180 秒**；按 32 任务**总平均成功率**排序，成功率相同才看**总平均步骤分**，再相同看提交日期；模型由选手自部署，平台只远程调用；单任务调试通道不计分。
2. **确认公开榜仍是随机占位**：`leaderboard.html` 的内联脚本自述 “randomly-generated”，`leaderboard_data.json` 的 `generated_from` 是 `gen_leaderboard.py`。榜单上的 MolmoAct2/WALL-OSS/DreamZero 等名字是真的，但分数和排名是假的；只能拿论文分析架构，不能拿分数当证据。用户简报里的“榜首 <30%”与占位分布一致，但它不是真实排名。
3. **把 32 个官方任务页的 `score_steps` 和 `human_1/human_4` 备注抓下来**。人为干扰不是“手挡一下”，而是**撤销已完成子目标**：把叠好的毛巾翻开（T16）、拉上的拉链拉开（T19）、拧开的盖子拧回去（T14）、把锁拿走（T12）、把可乐/薯片放回传送带起点（T24）、把插头拔起（T10）、把第二个碗拿走（T27）、把笔盒合上再手动打开（T17）。这一条直接推翻“进度单调递增”的假设。

因此本轮的主判断是：

> **上一轮的 RUBICON 2.0 方向对，但优化目标错了。** 步骤分/首检查点容易让人去“刷部分分”；官方排序是**成功率优先**，步骤分只是平分后的 tie-breaker。10 次/任务 × 32 任务 = 320 次试验，p≈0.3 时总平均成功率的标准误约 **2.6pp**；1–2pp 的榜单差距基本是噪声。真正该做的是：**用部件级语义分割把“接触最后几毫米 + 撤销式干扰”变成可检测、可修复的状态，再把有限的调试预算押到能显著抬高平均成功率的短板上。**

所以本轮把 RUBICON 2.0 升级为 **RUBICON 3.0**：

- **SPA-VLA（Semantic Part-Affordance VLA）**：把 SAM3/PartSAM 的部件分割离线蒸馏进**单模型 VLA**，用部件 token 统一表示“抓哪里/插哪里/挂哪里/拉哪里/进度到哪”；部署时只有一个 checkpoint，不违反“不得混合多个模型”。这是本轮的技术主押注。
- **RPSM（Reversible Part-State Memory）**：维护部件级状态谓词（在钩上/插入/拧紧/拉链闭合/叠好/堆叠/分拣/锁上），允许状态回退；检测到 `human_1/human_4` 的撤销后，只修复被撤销的子目标，不盲目重跑全程。这是本轮最贴合官方干扰备注的创新。
- **Compliance Compiler（SERB 2.0）**：把单模型、10 trials、180s、自部署、许可证、人机安全、无任务硬编码变成可执行门禁和提交清单；这是“防归零”，不是文档装饰。
- **Endurance Governor**：把“续航”拆成**服务续航**（N 端口、p99 延迟、热/内存、4 小时 soak）和**语义续航**（部件状态记忆跨遮挡/跨干扰保持），而不是猜电池化学。
- **Task Portfolio Optimizer**：用 Beta-Binomial 对 32 任务成功率建模，按“提升平均成功率的边际收益/成本”分配调试预算；先消灭 0% 任务，再攻高杠杆短板。这是最便宜、最直接对准排行榜口径的创新。

一句话：**语义分割不是再加一个感知模型，而是给 VLA 一个可验证的部件接口；伦理合规不是 PPT，而是防归零的运行时门禁；续航不是省电，而是长程状态不丢。**

## 1. 本轮新增/修正的事实

### 1.1 官方规则（已读部分，2026-10-23）

- 单模型、全 32 任务；模型类型不限（World Model、VLA 均可）。
- 每任务 10 次；5 类泛化（位置/干扰物/背景/未见物品/人为干扰）各 2 次。
- 单次最多 180s；超时记失败，但按执行情况给步骤分。
- 排名：总平均成功率 ↓ → 总平均步骤分 ↓ → 提交日期 ↑。
- 选手自部署，平台远程 API 调用；N 台机器人，端口从 `8765` 起连续 N 个（`8765 … 8765+N−1`）；N 由组委会另行公布（README 示例 N=3）。
- 单任务调试通道不计分。
- 外部数据/模型、控制频率、评分公式细节、任务硬编码限制、base/waist 限制：**未核实**，不能写成确定规则。

### 1.2 榜单与竞争分析

- 公开榜是占位；真实排名不可用。命名模型是真实项目，可分析论文，但**不能**说“MolmoAct2 以 29.7% 排第一”。
- 真实强基线更可能是：WALL-OSS-0.5（4B、20+ embodiments；微调后 60.5% task progress、+17.5% over π0.5）、MolmoAct2（open action reasoning）、DreamZero（14B world-action model；跨 embodiment 视频演示 10–20 分钟带来 >42% 未见任务提升）、π0.5、GigaBrain-0.7、GR00T N1.5。
- 它们的共同强项是语义/物理泛化；共同短板是**接触最后几毫米、长程状态推进、撤销式干扰后的恢复**。这三项恰好是官方评分轴里最容易被忽视、又最能拉开成功率的。

### 1.3 官方干扰备注的关键结构

- **撤销（undo）**：T14 拧回盖子、T16 翻开毛巾、T17 合上再打开笔盒、T19 拉开拉链、T27 拿走第二个碗、T10 拔起插头。
- **移除/替换**：T12 把锁拿走、T29 移开外壳盖、T28 移动耳机。
- **重置到起点**：T24 把可乐/薯片放回传送带起点。
- **移动底座/架子**：T11 抓电池前动底座、T25 放第一个后挪底座、T08 抓书后挪架子、T21 把架子向左移。
- **阻塞/占用**：T05 人手握网口、T10 抓插头前移动插头、T26 移开网线/插口。

这意味着：**进度不能是一个单调计数器**。模型必须能观测“当前世界状态”，检测“回到之前的状态”，并只修复被破坏的子目标。这是 RPSM 的直接动机。

## 2. 三条灵感词的落点

### 2.1 语义分割 → SPA-VLA

- 32 个任务几乎都是**部件级交互**：杯把、盘沿、插头、插孔、拉链头、瓶盖、钥匙、毛巾角、试管、碗沿、耳机、手机、便签钉、注射器。
- 物体级 3D 位姿不够：抓杯把和抓杯身是两件事；插头 prong 和插头 body 是两件事；拉链 pull 和齿是两件事。
- 部件表示天然适合**未见物品**：换一个颜色的杯子，杯把还在；换一个形状的插头，prong 还在。它也比物体 ID 更适合**人为干扰**：部件被移动/遮挡后可以重新检测。
- **不是在线跑两个模型**：SAM3/PartSAM 只在离线做教师，生成 mask/centroid/affordance 伪标签；学生是 VLA 内部的 16 个 part queries + 轻量 mask/centroid 头，和动作头在同一个 checkpoint。部署时只有一个模型。
- 部件 token 同时服务四件事：语言 grounding、接触目标选择、进度谓词、状态记忆。

### 2.2 伦理与合规 → Compliance Compiler

- 伦理不是“写一段声明”，而是三类风险：
  1. **归零风险**：多模型混用、任务特定硬编码、外部数据/模型未披露、超时/崩溃、许可证不清。
  2. **人机安全**：人为干扰就在工作区；碰撞可能直接终止评测或损坏机器人。
  3. **评测诚信**：不能针对 32 个任务写死坐标/轨迹，不能只挑容易的 trial 上报。
- 做法：把规则编译成**可执行门禁** + **运行时 monitor** + **提交 manifest**。每条规则都有实现和测试，不通过不放行。
- 特别地：**不把任务 ID 喂给模型**，只用语言 + 图像 + proprio；这既防过拟合，也能在答辩/审计时证明泛化。

### 2.3 续航能力 → Endurance Governor

- **服务续航**：N 个端口共享一个后端，长时并发；p99 延迟、显存、热节流、崩溃恢复、每端口状态隔离。这是自部署 API 的真实约束。
- **语义续航**：部件状态记忆跨遮挡、跨阶段、跨人为干扰保持；人手离开后能重新 grounding，而不是从零开始。
- **物理能量**：减少不必要的 base/waist 运动和抖动，但这不是主战场；不猜电池化学，不把“省电”当核心卖点。
- 指标：4 小时 soak 的成功率漂移、p99 延迟漂移、显存增长、热节流次数、干扰后恢复率、每次成功能耗（能测则测）。

## 3. 创新点排序（本轮修正）

| 顺序 | 创新点 | 价值 | 风险 | 依赖 |
|---|---|---|---|---|
| P0 | **SPA-VLA**：部件可供性蒸馏进单模型 VLA | 高 | 中 | SAM3/PartSAM + WLA/GigaBrain |
| P0 | **RPSM**：可逆部件状态记忆 + 撤销检测/修复 | 高 | 中 | SPA-VLA + 官方干扰备注 |
| P0 | **Task Portfolio Optimizer + LPL**：按成功率口径分配调试预算 | 高 | 低 | 本地 10-trial 评测 |
| P0 | **Compliance Compiler**：单模型/180s/许可证/人机安全门禁 | 高（防归零） | 低 | 规则 + 部署 |
| P1 | 部件感知接触伺服（插/挂/拉链/拧盖） | 高 | 中 | 部件 centroid/normal + 腕部 |
| P1 | Endurance Governor：N 端口/p99/热/内存/语义记忆 | 中高 | 低中 | 部署 + 监控 |
| P1 | Rubric Compiler 2.1：score_steps + 语言约束 + 时间预算 | 高 | 低 | `info.json` + `tasks.parquet` |
| P2 | Waist/Pivot Controller：静态默认 + 安全探针 | 中 | 中高 | pivot 探针 |
| P2 | 语言复述鲁棒性：5 条复述 + 留一法 | 中 | 低 | `tasks.parquet` |
| P3 | 世界模型/仿真增广 | 中 | 高 | 算力/资产 |

**与上一轮相比的关键变化**：

- **Waist/Pivot 从 P0 降到 P2**：成功率优先，腰部运动带来平衡/外参风险；默认静态，只有任务确实需要时才小范围动。
- **“高地板/首点优先”改为“最差任务优先 + 组合优化”**：首点只影响步骤分，不影响成功率；0% 任务的边际收益最大。
- **SERB 升级为 Compliance Compiler**：从四类 checklist 变成“规则→实现→测试”的闭环。
- **EcoPort 升级为 Endurance Governor**：从“省算力”扩展到“服务续航 + 语义续航”。
- **PosePort 保留但降级为 SPA-VLA 的几何底座**：部件 token 需要 3D 点/法向，姿态图仍然有用；不再单独作为最大卖点。
- **新增 RPSM**：这是官方干扰备注直接逼出来的，上一轮没有。

## 4. 修剪/暂缓

- **从零训练大模型**：不划算；WLA-1.0/GigaBrain-0.7 已开源且许可证清晰。
- **真机在线 RL**：样本效率/安全/时间都不允许。
- **运行时 LLM/VLM API**：延迟/网络/规则风险；离线编译。
- **任务特定硬编码轨迹**：泛化差，可能违规；用部件谓词 + 学习进度头。
- **激进 pivot / 大幅 base 运动**：默认静态；先探针，再按任务配置。
- **完整仿真 RL**：P3；规则/资产/时间不确定。
- **大规模 3D 生成增广**：P3；先把真实数据 + 轻量部件增广做好。
- **“再大一点的 VLA”**：不是本轮边际收益所在；本轮比的是状态接口和恢复能力。

## 5. 为什么这版可能赢

- **对准口径**：成功率优先 → 先消灭 0%、再攻短板、用 CI 而不是榜单噪声做决策。
- **对准数据**：32 任务都是部件交互 → 部件表示是比物体中心更合适的归纳偏置。
- **对准干扰**：官方 human 备注是撤销/移除/重置 → RPSM 直接打这个轴。
- **对准部署**：单模型 + 自部署 + N 端口 → 蒸馏而不是级联；Endurance Governor 保证长时稳定。
- **对准风险**：Compliance Compiler 把“可能归零”的项前置，而不是最后一周才发现。

## 6. 8 周执行顺序（压缩版）

| 周 | 目标 | 交付 |
|---|---|---|
| 1 | 规则/接口/基线；LPL 10-trial；Compliance checklist；pivot 探针 | 可跑 baseline、32 任务 LPL、规则 manifest |
| 2 | 部件教师：SAM3/PartSAM 伪标签；标定/姿态校验；数据管线 | 部件标签 v1、质量报告、训练集 |
| 3 | SPA-VLA 微调（多视角 + proprio + 语言 + part head） | 首个可评测 checkpoint |
| 4 | RPSM 谓词/撤销增广；Rubric 2.1；进度头 | 闭环 v1、undo 测试集 |
| 5 | 部件接触伺服；Compliance runtime；Endurance 多端口 | 硬任务增强、4h soak |
| 6 | Portfolio 分配；消融；全 32 任务 LPL | 策略 v2、消融报告 |
| 7 | 全 32 任务正式协议；统计分析；迭代 | 首个可靠成绩 + CI |
| 8 | 最终提交；审计/复现；红队 | 提交包 |

## 7. 一句话押注

**把语义分割蒸馏成单模型 VLA 的部件可供性 token，再用可逆部件状态记忆把官方 `human_1/human_4` 的撤销式干扰变成可检测、可修复的闭环；评分点只做辅助，平均成功率才是主目标。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
## A. 结论

本轮把 RUBICON 2.0 升级为 **RUBICON 3.0**，核心不是“再大一点的 VLA”，而是三个对准比赛口径的接口：

1. **SPA-VLA（Semantic Part-Affordance VLA）**：把 SAM3/PartSAM 的部件分割离线蒸馏进**单模型 VLA**。模型内部用 16 个 part queries 输出部件存在性、affordance、2D mask、3D centroid、描述子；动作头 cross-attend 到这些部件 token。部署时只有一个 checkpoint，不跑第二个分割模型。
2. **RPSM（Reversible Part-State Memory）**：官方 `human_1/human_4` 大量是**撤销已完成子目标**（翻开毛巾、拉开拉链、拧回盖子、拿走锁、把分拣物放回起点、拔起插头）。RPSM 维护可逆的部件状态谓词，检测“进度回退”，只修复被撤销的子目标。
3. **Compliance Compiler + Endurance Governor + Task Portfolio Optimizer**：分别解决“防归零”“长时服务/语义续航”“有限调试预算该压哪 32 个任务”的问题。

**最重要的口径修正**：官方排序是**总平均成功率优先**，步骤分只是平分后的 tie-breaker；10 次/任务 × 32 任务 = 320 次试验，p≈0.3 时总平均成功率的标准误约 **2.6pp**，1–2pp 的榜单差距基本是噪声。策略应从“刷首点/刷步骤分”转为“消灭 0% 任务 + 攻 3–5pp 的真实增益 + 降低方差”。

以下所有事实、表格、架构、实验与风险均以 **2026-10-23** 可访问的公开页面/文件为准；无法核实的地方明确标注“未核实”。

## B. 官方规则与评分数学

### B.1 已读规则

| 维度 | 已读规则 | 来源 | 对策略的影响 |
|---|---|---|---|
| 赛道 | 仅通才模型（Multi-task）赛道；单任务调试通道不计分 | Feishu 手册 1.2 | 不能靠单任务成绩上榜；必须 32 任务整体可用 |
| 模型 | **所有任务须基于同一模型完成，不得混合多个模型一起测试**；模型类型不限（World Model、VLA 均可） | Feishu 手册 1.1 | 不做“分割模型 + VLA”的在线级联；用蒸馏进单模型 |
| 试验 | 每任务 10 次独立运行 | Feishu 手册 1.2 / 2.1 | 每任务成功率只有 10 个 Bernoulli 样本，噪声大 |
| 泛化 | 5 类：位置、干扰物、桌面背景、未见物品、人为干扰；每类 2 次 | Feishu 手册 2.1 | 训练/验证必须按这 5 类分层，不能只做随机留出 |
| 时限 | 单次真机最多 180 秒；超时记失败，但仍按执行情况给步骤分 | Feishu 手册 2.1 | 需要阶段时间预算、watchdog、超时前安全退出 |
| 排名 | 32 任务总平均成功率 ↓；相同则总平均步骤分 ↓；再相同则提交日期 ↑ | Feishu 手册 1.2 | **成功率是第一目标**；步骤分只在平分时有用 |
| 部署 | 选手自行部署推理服务；平台远程 API 调用；平台不提供算力 | Feishu 手册 1.1 | N 端口、并发、p99 延迟、热/内存/崩溃是硬约束 |
| 端口 | N 台机器人；从 `8765` 起连续 N 个端口（`8765 … 8765+N−1`）；端口数必须恰好等于 N；N 由组委会另行公布（README 示例 N=3） | 提交 README §5 | 按 N 做会话隔离/批处理；不能假设单机器人 |
| 交互质量 | 每步延迟、延迟波动、动作统计规律会被记录，并可能与成绩一起展示；要求延迟稳定、动作无异常离群 | 提交 README §6 | 延迟抖动/异常动作会损害可信度；Endurance Governor 是硬需求 |
| 资源 | 32 任务全部真机数据 | Feishu 手册 2.2；HF collection | 可用挑战数据训练；外部数据/模型是否允许未核实 |
| 未核实 | 外部数据/模型、N 的具体值、控制频率、4.2 评分公式细节、4.3 排名/入围/成绩记录细节、任务硬编码限制、base/waist 限制 | Feishu 手册 2.3–5.2 不可读 | 产物中按“假设/风险”处理，不写成确定规则 |

### B.2 排序公式与统计功效

设任务 `i` 的第 `j` 次试验成功为 `y_ij ∈ {0,1}`，步骤分为 `q_ij ∈ [0,100]`：

```text
S = (1/32) * Σ_i (1/10) * Σ_j y_ij          # 总平均成功率
Q = (1/32) * Σ_i (1/10) * Σ_j q_ij          # 总平均步骤分
rank: S desc, then Q desc, then submission_date asc
```

总平均成功率的近似标准误：

```text
SE(S) ≈ sqrt( (1/32^2) * Σ_i p_i(1-p_i)/10 )
```

当所有 `p_i≈0.3` 时：

```text
SE(S) ≈ sqrt(0.3*0.7/320) ≈ 0.0256 = 2.56pp
95% CI ≈ ±5.0pp
```

**真实优势与“排名更高”的概率**（正态近似，320 次试验）：

| 真实成功率优势 Δ | P(观测排名更高) |
|---:|---:|
| 0.5pp | 55.5% |
| 1.0pp | 60.8% |
| 1.5pp | 66.0% |
| 2.0pp | 70.8% |
| 2.5pp | 75.3% |
| 3.0pp | 79.3% |
| 4.0pp | 86.1% |
| 5.0pp | 91.2% |

**含义**：

- 公开榜/单次评测里 1–2pp 的差距不能当真实优势；不要为榜单波动改架构。
- 想把“排名更高”的概率做到 ~80%，需要约 **3pp** 的真实优势；做到 ~90% 需要约 **5pp**。
- 320 次试验下，检测 3pp 差异（80% power）需要约 3,700 次/组；本赛不可能靠增加 trials 解决，只能靠**更大的真实增益**和**降方差**。

**边际价值**：

```text
一个任务 +10pp  → 总平均 +0.10/32 = +0.31pp
全部 32 任务 +2pp → 总平均 +2.0pp
一个任务 +30pp  → 总平均 +0.94pp
```

所以：**先消灭 0%（一个 0% 任务相对 100% 损失 3.1pp、相对 30% 损失 0.94pp），再在 3–5 个短板上各拿 20–30pp，比在强任务上抠 1–2pp 更划算。**

### B.3 任务组合优化

对每个任务维护 Beta 后验：

```text
p_i ~ Beta(α_i, β_i)
α_i = α0 + k_i
β_i = β0 + (n_i - k_i)
```

- 先验：Easy `Beta(3,3)`（均值 0.5）、Medium `Beta(2,4)`（0.33）、Hard `Beta(1.5,5)`（0.23）；也可统一 `Beta(2,2)`。
- 目标 1：最大化 `E[S] = (1/32) Σ E[p_i]`。
- 目标 2：最大化 `P(S > S*)`，用 Monte Carlo 从后验采样。
- 目标 3：降低 `Var(S)`，提高“单次评测抽到好成绩”的概率。
- 选择下一个调试任务：`score_i = (E[p_i] - current_i) / cost_i`，或 `UCB_i / cost_i`；对 `P(p_i < 0.05) > 0.5` 的任务加“no-zero”优先级。
- 成本 `cost_i` 可用历史调试时长、接触密度、任务时长、失败模式数估计。

**示例**：5 个 0% 任务各提到 30% → `5×0.30/32 = +4.7pp`；5 个 70% 任务各提到 80% → `5×0.10/32 = +1.6pp`。前者是后者的 3 倍，且通常更容易，因为 0% 往往有明确的系统性失败（抓错部件、没插进去、超时）。

**步骤分的位置**：先保证 `S`，再在 `S` 不下降的前提下最大化 `Q`。不要为了首点 50 分而牺牲完整成功；首点只在 `S` 打平时有用。

### B.4 对上一轮的修正

| 上一轮 | 本轮修正 | 原因 |
|---|---|---|
| “成功率 + 步骤分综合排序” | **成功率优先，步骤分 tie-breaker** | Feishu 1.2 原文 |
| “高地板任务优先，先稳首点” | **最差任务优先 + 组合优化** | 首点不影响成功率；0% 任务边际损失最大 |
| SERB 四类 checklist | **Compliance Compiler：规则→实现→测试** | 需要防归零，不只是文档 |
| EcoPort 省算力/省电 | **Endurance Governor：服务续航 + 语义续航** | 自部署 + N 端口 + 长时干扰 |
| PosePort 独立 P0 | **SPA-VLA 的几何底座** | 部件 token 需要 3D 点/法向；不再单独当最大卖点 |
| Waist/Pivot P0 | **P2：静态默认 + 安全探针** | 成功率优先；腰部运动带来平衡/外参风险 |
| 用公开榜分析头部 | **公开榜是随机占位，只能用论文** | HTML 自述 + `gen_leaderboard.py` |

## C. 32 任务与官方干扰备注

### C.1 评分表（官方 `tasks_v2/<slug>/info.json`）

| ID | 官方 slug | 任务（中/英） | 难度 | 评分点 | 检查点 |
|---|---|---|---|---|---|
| T01 | `hang_the_cup` | 挂杯子 / HangCup | Easy | 50+50 | 2 |
| T02 | `fruit_basket_collection` | 水果收集 / FruitCollection | Easy | 50+50 | 2 |
| T03 | `pack_the_doll` | 装娃娃 / PackDoll | Easy | 50+50 | 2 |
| T04 | `sort_fruit` | 水果分类 / FruitSorting | Easy | 30+30+40 | 3 |
| T05 | `disconnect_ethernet` | 拔网线 / DisconnectEthernet | Hard | 50+50 | 2 |
| T06 | `color_arrangement` | 颜色排列 / ColorArrangement | Easy | 30+30+40 | 3 |
| T07 | `place_photo_frames` | 摆放相框 / PlacePhotoFrame | Medium | 30+30+40 | 3 |
| T08 | `organize_bookshelf` | 整理书架 / OrganizeBookshelf | Easy | 50+50 | 2 |
| T09 | `toolbox_storage` | 工具箱收纳 / ToolboxStorage | Hard | 25×4 | 4 |
| T10 | `plug_charger` | 插插头 / PlugCharger | Hard | 30+30+40 | 3 |
| T11 | `pick_out_battery` | 挑出电池 / PickOutBatteries | Medium | 30+30+40 | 3 |
| T12 | `unlock` | 开锁 / Unlock | Hard | 30+30+40 | 3 |
| T13 | `organize_test_cube` | 整理试管 / ArrangeTestTubes | Easy | 30+30+40 | 3 |
| T14 | `open_pill_bottle` | 倒出药品 / PourOutMedicine | Hard | 50+50 | 2 |
| T15 | `organize_tools` | 整理工具 / OrganizeTools | Medium | 25×4 | 4 |
| T16 | `fold_towel` | 叠毛巾 / FoldTowel | Hard | 20×5 | 5 |
| T17 | `organize_stationery` | 整理文具 / OrganizeStationery | Easy | 20×5 | 5 |
| T18 | `pack_bag` | 收拾书包 / PackBag | Medium | 25×4 | 4 |
| T19 | `zip_up` | 拉上拉链 / ZipUp | Medium | 50+50 | 2 |
| T20 | `paper_cup_stacking` | 纸杯堆叠 / PaperCupStacking | Easy | 30+30+40 | 3 |
| T21 | `clear_plates` | 餐盘排列 / ArrangePlates | Easy | 30+30+40 | 3 |
| T22 | `spell_robot` | 字母拼写 / SpellRobot | Medium | 25×4 | 4 |
| T23 | `store_racket` | 球拍收纳 / StorePaddle | Medium | 50+50 | 2 |
| T24 | `sort_food_conveyor` | 传送带分拣 / ConveyorSorting | Medium | 50+50 | 2 |
| T25 | `stack_cups` | 整理纸杯 / StoreCups | Easy | 30+30+40 | 3 |
| T26 | `plug_in_ethernet` | 插网线 / PlugInEthernet | Medium | 30+30+40 | 3 |
| T27 | `stack_bowls_three` | 碗具堆叠 / StackBowls | Easy | 30+30+40 | 3 |
| T28 | `store_earphones` | 装耳机 / StoreEarphones | Hard | 25×4 | 4 |
| T29 | `pack_iphone` | 装手机 / PackPhone | Hard | 30+30+40 | 3 |
| T30 | `remove_pinned_note` | 移除固定便签 / RemovePinnedNote | Medium | 50+50 | 2 |
| T31 | `pencil_case` | 整理文具袋 / OrganizePencilCase | Medium | 30+30+40 | 3 |
| T32 | `syring_water` | 针管转移液体 / SyringeWaterTransfer | Medium | 50+50 | 2 |

> 注意：官方 `en_name` 与上一轮表有个别差异（T13/T14/T21/T23/T24/T25/T27/T29/T31/T32）。上表以 2026-10-23 的 `info.json` 为准。T31/T32 的 `generalization` 备注为空，需要按同类任务补测试。

### C.2 官方人为干扰备注（`human_1` / `human_4`）与未见物品

| ID | `human_1_note` | `human_4_note` | `unseen_object_3` |
|---|---|---|---|
| T01 | 杯子向后 | 杯子向右 | 缺少红色杯子和塑料架子 |
| T02 | 水果向前 | 水果向右 | 缺少不同果篮 |
| T03 | 娃娃向前 | 娃娃向右 | 缺少绿色和紫色娃娃 |
| T04 | 橘色盘子向左移动移动 | 把梨往右移动 | 缺少其他款式的盘子 |
| T05 | 把网线另一头也插上 | 移动道具手握网口 | 缺少其他颜色的短网线 |
| T06 | 绿色积木向右移动 | 红色积木向前移动 | 没有其他积木 只有塑料积木 |
| T07 | 相框向上移动 | 相框向上移动 | 只有一种相框 |
| T08 | 抓到书后挪动架子 | 书向右 | — |
| T09 | 胶带向后移动 | 胶带向右移动 | — |
| T10 | 抓插头前进行移动 | 将插头拔起 | 缺少其他颜色的插排 |
| T11 | 抓取电池之前动底座 | 抓电池之后动绿色盒子 | 缺少黑色电池 |
| T12 | 锁向左移动 | 中途把锁拿走 | 缺少一把绿色锁 |
| T13 | 试管向右移动 | 试管向左移动 | 不同类型的试管 |
| T14 | 拧开盖子之后拧动回来 | 把瓶子向左移动 | 缺少不同颜色的药品收纳盒 |
| T15 | 钳子向左移动 | 螺丝刀向右移动 | — |
| T16 | 将叠完的毛巾翻开 | 将叠完的毛巾翻开 | — |
| T17 | 荧光笔向后 | 笔盒合上之后手动打开 | 缺少黑色的文件盒 |
| T18 | 把文具盒向上移动 | 把书包向左移动 | 缺少其他颜色的文具盒 |
| T19 | 把包向左边移动 | 拉上拉链之后拉开 | — |
| T20 | 把左边的纸杯向上移动 | 把右上角的纸杯向右移动 | 缺少不同类型纸杯 |
| T21 | 把盘子向前移动 | 把架子向左边移动 | 缺少不同类型的盘子 |
| T22 | 字母上移动 | 字母向左边移动 | 缺少不同颜色的字母 |
| T23 | 球拍向前移动 | 球拍向左移动 | 缺少不同的球拍套装 |
| T24 | 可乐快到了然后放回传送带起点 | 薯片快到了然后放回传送带起点 | 缺少不同的零食 |
| T25 | 把纸杯向左移动 | 放了第一个马上放第二个挪一下底座 | 缺少不同颜色的纸杯 |
| T26 | 把网线移开 | 把插口移开 | 不同的网线跟端口 |
| T27 | 把粉色碗向下移动 | 叠了第二个之后拿下第二个 | 除了塑料类型 |
| T28 | 把黄色盒子的耳机向前移动 | 把红盒子的耳机向右移动 | 缺少不同的收纳盒以及耳机托盘 |
| T29 | 手机向上移动 | 外壳盖移开 | — |
| T30 | 把把黄色钉子移到中间 | 把绿色钉子向下移动 | — |
| T31 | — | — | — |
| T32 | — | — | — |

> 备注：官方原文存在个别重复字/空格（如 T04 “移动移动”、T30 “把把”），上表保留原样；阅读时按语义理解。

### C.3 干扰类型与 RPSM 映射

| 干扰类型 | 代表任务 | 对模型的含义 |
|---|---|---|
| **撤销已完成子目标** | T14 拧回盖子、T16 翻开毛巾、T17 合上再打开、T19 拉开拉链、T27 拿走第二个碗、T10 拔起插头 | 进度不能单调；需要状态谓词 + 回退检测 + 定向修复 |
| **移除物体** | T12 拿走锁、T29 移开外壳盖、T28 移动耳机 | 重新扫描；找不到则安全停止，不能幻觉继续 |
| **重置到起点** | T24 把可乐/薯片放回传送带起点 | 需要重新分拣；不能假设“已经放好” |
| **移动底座/架子** | T11 动底座、T25 挪底座、T08 挪架子、T21 移架子 | 相机外参/场景记忆失效；需要重定位/重投影 |
| **阻塞/占用** | T05 手握网口、T10 抓插头前移动、T26 移开网线/插口 | 目标不可达；需要等待/换目标/重试 |
| **普通位移** | 大多数任务的 `human_1` | 部件重新检测 + 相对位姿更新 |

> 这比“人手挡一下”难得多：官方干扰是**语义状态改变**。纯 BC 的单调进度头会把“毛巾被翻开”当成仍在“已叠好”阶段，继续去拿下一个物体；RPSM 必须显式检测回退。

### C.4 数据集与姿态事实（沿用上一轮，2026-10-23 复核）

| 事实 | 数值/结论 | 对 SPA-VLA 的影响 |
|---|---|---|
| 规模 | 32 任务；约 **33,276 episodes / 169.3h**（官方页称 32k/169h；ColorArrangement 1533 是 outlier） | 足够微调 3.5B–6B；部件标签只需采样 |
| 传感器 | 4 路 RGB：头部双目 `head_stereo_left/right` + 左右腕 `wrist_left/right`；480×640×3，30fps，AV1 | 头部双目可做粗 3D；腕部做接触近景 |
| 状态/动作 | 双臂 7+7、grippers、`lower_body[15]`、`pivot[7]`、`state_torso[6]`、`state_d435[6]`、`waist_state_joint[3]`；EE pose base/torso | part head 输入 proprio；pivot 只做低维控制 |
| 语言 | `meta/tasks.parquet` 每任务 **5 条英文复述**（`@` 分隔） | 语言-部件对比学习；留一法验证 |
| 时长 | 6.2s（HangCup）–37.6s（ToolboxStorage）；另有 StorePaddle 34.1s、SpellRobot 31.2s、PackPhone 29.2s、FoldTowel 25.8s、OrganizeTools 25.0s | 阶段时间预算；长任务需要 RPSM |
| 标定 | 32 任务至少 **10 组**头部双目标定；`fx` 186.03–296.15，baseline norm(T) 46.72–64.86mm，`cx` 左 302.45–365.43 / 右 315.98–384.27 | 不能全局硬套外参；按任务读 `camera_params` |
| 深度误差 | G1 `fB≈16.45 m·px`：1m 处 0.1px≈6.1mm；G5/G7 `fB≈10.2/11.2`：1m 处≈9–10mm；0.5m 处≈1.5–2.5mm | 头部 stereo 只做粗定位；接触必须腕部/相对位姿 |
| pivot 语义 | `pivot_3≈waist yaw`（r≈0.73，slope 0.307，R²=0.532）；`pivot_4≈waist pitch`（r≈0.86，slope 0.6497，R²=0.737）；`pivot_5=0` | 部件 3D 要随 waist 更新；默认静态 |
| pivot 使用 | OrganizeTools 连续用 waist（p3∈[-0.516,0.569]，p4∈[0,0.627]）；StorePaddle/FoldTowel p4 回合级偏移；PickOutBatteries/Unlock/PaperCupStacking height 偏移；ZipUp/OrganizeBookshelf 偶发 base；其余近静态 | 按任务配置；不要为“用上 pivot”而乱动 |
| 头部运动 | OrganizeTools D435 pitch std≈0.093、yaw≈0.081；HangCup 也有 0.014–0.019 | 外参动态；PoseGraph 需 neck/head 节点 |

> 结论：**部件 3D 不能只靠头部双目**。头部双目给厘米级粗定位；接触最后几毫米必须用腕部近景 + 部件 centroid/normal + 相对位姿。腰部/头部一动，part token 的 3D 点就要用 `waist_state_joint`/`state_torso`/`state_d435` 重投影。

## D. 竞争分析

### D.1 榜单审计

- `https://unibot.unitree.com/leaderboard.html`（2026-10-23）仍显示 “排行榜即将公开 / Coming Soon”。
- 页面内联脚本原文：*“The real, randomly-generated leaderboard is rendered here purely to sit (blurred) behind the '排行榜即将公开' overlay. … this script only fills it in; it never unmasks anything.”*
- `leaderboard_data.json` 的 `generated_from` 为 `gen_leaderboard.py`；8 个模型的分数/排名是随机生成，不是真实提交。
- 结论：**可以分析命名模型的论文，不能引用榜单分数**。用户简报里的“榜首 <30%”与占位分布一致，但只能当“难度直觉”，不能当证据。

### D.2 真实强基线（论文主张，不是榜单）

| 模型/论文 | 真实主张（来自论文/模型卡） | 强项 | 对本赛的短板 |
|---|---|---|---|
| **WALL-OSS-0.5**（4B） | 20+ embodiments、1M+ trajectories；微调后 15 任务平均 **60.5% task progress**、比 π0.5 高 **17.5%** | 强通用 VLA、数据规模大、跨 embodiment | 4B 推理成本；“progress”不等于 full success；无显式部件状态/回退检测 |
| **MolmoAct2** | open action reasoning model；**MolmoER** backbone；**OpenFAST** action tokenizer；flow-matching action expert；per-layer KV-cache conditioning；**MolmoThink** adaptive-depth reasoning | 语义/空间推理强；开放权重/数据 | 推理链延迟；接触最后几毫米；无显式可逆状态记忆 |
| **DreamZero**（14B） | World Action Model；视频扩散联合预测未来视频+动作；**7Hz** 实时闭环（约 **150ms/chunk** 量级）；AgiBot G1（论文实验平台）；跨 embodiment 视频演示 10–20 分钟带来 **>42%** 未见任务提升 | 物理动态/泛化强；world model 路线 | 14B 算力/延迟；扩散精度；长程状态验证弱 |
| **π0.5** | 强通用 VLA；开放世界泛化；高层推理 + 低层动作 | 语义泛化、数据覆盖 | 非 G1 专用；腰部/pivot/接触精度需适配 |
| **GigaBrain-0.7-3.5B** | world-model 数据、RGBD、CoT；Apache-2.0 | 数据引擎、3.5B 可部署 | 与本赛动作接口/域差异；需微调 |
| **GR00T N1.5** | NVIDIA 跨 embodiment 基础模型 | 工具链/生态 | 非 G1 专用；微调成本 |
| **Spirit-v1.5 / DM0** | 出现在占位榜的名字；公开论文/模型卡信息不足 | — | 不做架构判断，避免用假排名反推能力 |

### D.3 共同短板与本轮切入点

1. **接触最后几毫米**：插头 prong、网线水晶头、钥匙、瓶盖、拉链、试管。纯 RGB 端到端在 1m 处双目只有厘米级精度；需要腕部近景 + 部件 centroid/normal + 相对位姿伺服。
2. **可逆状态**：官方 human 干扰会撤销已完成子目标；大多数 VLA/进度头假设单调推进，缺少“回退检测 + 定向修复”。
3. **长程状态**：4–5 检查点任务（T09/T15/T16/T17/T18/T22/T28）容易漏点、premature stop、失败不重试。
4. **部署稳定性**：4 路视频、N 端口、长时并发；p99 延迟/热/内存会直接吃掉成功率。
5. **合规风险**：单模型、外部数据/模型、任务硬编码、许可证；一项不清可能归零。

> 表中的“短板”是按公开论文/模型卡做的推断，不是官方评测结论；真实排名不可见，不能据此断言谁强谁弱。
>
> 本轮不跟它们比“更大的 VLA”，而是比**部件接口 + 可逆状态 + 组合优化 + 合规/部署**。这四项目前不是论文的主赛道，但对本赛评分口径的边际收益更高。

## E. SPA-VLA：部件可供性蒸馏

### E.1 动机

32 个任务几乎都是部件级交互：

- 抓**杯把**（T01），不是抓杯身；
- 抓**盘沿**（T21），不是抓盘面；
- 抓**插头 prong**（T10/T26），不是抓线；
- 抓**拉链头**（T19），不是抓齿；
- 抓**瓶盖**（T14），不是抓瓶身；
- 抓**钥匙**（T12）、**毛巾角**（T16）、**碗沿**（T27）、**耳机**（T28）、**手机**（T29）、**便签钉**（T30）、**注射器**（T32）。

物体级 3D 位姿不够；部件级表示才能同时解决：

- **未见物品**：换颜色/形状/材质，部件语义仍在；
- **人为干扰**：部件被移动/遮挡后可重新检测；
- **进度验证**：谓词作用在部件状态上（在钩上/插入/拧紧/闭合）；
- **语言 grounding**：语言里的“handle/rim/prong/zipper/cap”直接对应部件。

### E.2 架构

```text
4 views (head L/R, wrist L/R) + proprio + language
        │
        ▼
VLM backbone（WLA-1.0 / GigaBrain-0.7 / 其他允许的底座）
        │
        ├─ 16 part queries（cross-attend 到 4 视图 token）
        │     ├─ existence / affordance（grasp, insert, hang, pull, push, rotate, fold, pour, place, open, close）
        │     ├─ 2D mask（1/4 分辨率）
        │     ├─ 2D centroid（soft-argmax）
        │     ├─ 3D point（camera ray + depth；无 depth 时用学习头）
        │     └─ descriptor（用于跨帧/跨视角跟踪）
        │
        ├─ language tokens ──► part-language contrastive
        │
        ▼
action expert（cross-attend 到 part tokens + language + proprio）
        │
        ▼
action chunk（双臂关节/EE + grippers + pivot）
```

关键点：

- **part queries 是共享的**，不是每个任务一组；任务差异由语言和观测决定，模型**不接收 task id**。
- `K=16` 足够覆盖大多数任务（最多同时 4–6 个相关部件）；用 Hungarian matching 与教师部件对齐。
- mask 头只在需要时输出；centroid/3D 头始终输出，接触伺服和记忆主要用 centroid/3D。
- 动作头把 part tokens 当作结构化 object slots；这比纯全局 token 更容易学“抓哪里”。

### E.3 教师管线（离线）

1. **文本提示**：为每个任务定义 3–8 个部件短语，例如 `cup handle`, `cup rim`, `plate rim`, `plug prong`, `socket slot`, `zipper pull`, `bottle cap`, `key`, `towel corner`, `bowl rim`, `earphone`, `phone`, `pin`, `syringe plunger`。
2. **分割**：SAM3（文本/概念提示）出 2D mask；PartSAM 出 3D part；GroundingDINO 出 box 做兜底；深度来自头部双目 + 腕部（如果可用）。
3. **多视角关联**：把 3D centroid 投影到其他视角，检查 mask/深度一致性；小部件优先用腕部视角。
4. **时序跟踪**：SAM3 video 或轻量 mask tracker；光流/一致性检查；低置信帧丢弃。
5. **质量控制**：mask 面积、深度有效像素、重投影误差、时序 IoU；低置信帧不参与监督；人工标注 1–2k 帧做验证集。
6. **标签预算**：每任务 100–200 episodes 的关键帧（每 5 帧取 1），约 10–30 万帧；8 卡 2–4 天可完成；其余帧用跟踪/伪标签。

### E.4 学生损失

```text
L = L_action
  + λ_mask * L_mask          # BCE + Dice，仅高置信帧
  + λ_cent * L_cent          # soft-argmax centroid L1
  + λ_aff  * L_aff           # affordance CE（Hungarian matching）
  + λ_3d   * L_3d            # 3D point L1（depth 有效时）
  + λ_temp * L_temp          # 跨帧/跨视角跟踪一致性
  + λ_lang * L_lang          # 语言-部件对比学习
```

- `L_action`：按底座选择 flow matching / diffusion / CE；不改底座的动作头结构，只加 cross-attention。
- `L_lang`：同一任务的部件 descriptor 与语言 embedding 拉近，与其他任务的部件推远；hard negatives 用同任务的其他部件。
- **不使用 task id**；只使用 `tasks.parquet` 的 5 条复述。留一条复述做验证，检查语言泛化。
- 训练时对 part head 使用 confidence weighting；教师不确定的帧不强制 mask loss。

### E.5 运行时

- 每 `k=2` 个 action chunk 计算一次 part tokens；中间 chunk 复用，并用 proprio/光流更新 centroid。
- 置信度下降、遮挡、人手进入、或进入接触阶段时，立即重算。
- part tokens 的四个用途：
  1. **接触目标**：选当前 affordance 对应的部件 centroid/normal；
  2. **进度谓词**：输入 RPSM；
  3. **状态记忆**：descriptor + 3D + last seen；
  4. **安全**：part head 可加一个 `human hand` query 或复用深度做近距离检测（规则式，不另起模型）。
- 若 part head 不确定：回退到 VLA 的隐式 attention；**不切换模型**。

### E.6 单模型合规

- 一个 checkpoint 包含：backbone、part head、action head、progress/predicate head。
- 运行时**不加载 SAM3/PartSAM**；它们只在离线当教师。
- 不按任务切换模型；不按任务加载不同权重；不把 task id 喂给模型。
- 如果规则对“辅助头”有疑问：在 model card 中说明它们是同一计算图的一部分；所有输出由同一 checkpoint 产生。
- 安全 monitor 用规则式深度/几何过滤，不引入第二个学习模型；若必须用人检测器，明确标注为 safety monitor，不参与任务决策。

### E.7 消融

| 实验 | 变量 | 目的 |
|---|---|---|
| A0 | 原 VLA | 基线 |
| A1 | + part head（无语言对比） | 部件监督本身是否有用 |
| A2 | + language-part contrastive | 语言 grounding 是否提升未见物品 |
| A3 | + 3D/temporal | 3D/跟踪是否提升接触 |
| A4 | 推理时 oracle mask | 上限；判断 part head 是否值得继续投入 |
| A5 | + RPSM | 撤销干扰恢复 |
| A6 | + contact servo | 最后几毫米 |
| A7 | 无 task id vs 有 task id | 证明不是靠任务 ID 过拟合 |

**关键指标**：full success（主）、step score（次）、unseen-object success、human-recovery success、mask IoU、centroid error、p99 latency。**不要只看 mask IoU**；如果 mask 很准但 full success 不涨，说明 part token 没被动作头用起来，需要检查 cross-attention/损失权重。

### E.8 资源与风险

- 数据：32 任务约 33k episodes / 169h；教师标注 10–30 万关键帧。
- 训练：优先 LoRA/部分微调 3.5B–6B 底座；8×A100/H100，1–2 周；推理 1×H100/L40S 只能服务少量端口，6B/4 视图需实测，可能需要更大 GPU 或降频/量化。
- 风险：透明/反光/小部件分割噪声；part query 坍塌；教师误差进动作头；算力不足；单模型解释。
- 缓解：多视角 + 腕部近景 + 置信度门控 + 人工验证集 + oracle-mask 上限 + 先小规模验证再放大。

## F. RPSM：可逆部件状态记忆

### F.1 谓词库（示例）

| 任务组 | 谓词 | 观测来源 |
|---|---|---|
| 挂杯 T01 | `cup_handle_grasped`, `cup_on_hook` | 杯把 mask + 钩子 3D + 相对位姿 |
| 插头 T10 | `plug_grasped`, `prong_aligned`, `plug_inserted`, `charger_on` | prong mask + socket slot + 深度/接触 |
| 网线 T05/T26 | `connector_grasped`, `connector_aligned`, `inserted`, `disconnected` | 水晶头 mask + 端口 + 相对位姿 |
| 开锁 T12 | `key_grasped`, `key_in_lock`, `unlocked` | 钥匙/锁孔 + 旋转状态 |
| 倒药 T14 | `cap_grasped`, `cap_off`, `pills_out` | 瓶盖/瓶身 + 药片 mask |
| 叠毛巾 T16 | `corner_grasped`, `fold_1`, `fold_2`, `folded` | 毛巾角/边 + 层数/对齐 |
| 拉链 T19 | `pull_grasped`, `zipper_closed` | 拉链头 + 齿闭合 |
| 堆叠 T20/T25/T27 | `cup_grasped`, `cup_stacked(k)`, `bowl_stacked(k)` | 杯/碗 + 堆叠高度/顺序 |
| 分拣 T04/T24 | `item_grasped`, `item_in_bin(category)` | 物品 + 料盒/传送带 |
| 工具箱 T09 | `tool_grasped`, `tool_in_box`, `lid_closed`, `locked` | 工具 + 箱格 + 锁 |
| 书架 T08 | `book_grasped`, `book_on_shelf(slot)` | 书 + 书架槽位 |
| 文具 T17/T31 | `pen_in_case`, `case_closed` | 笔/笔盒 + 盖子 |

### F.2 观测与更新

- 输入：part tokens（mask/centroid/3D/descriptor）、深度、proprio、夹爪开合、语言约束。
- 关系分类器：小 MLP/Transformer 在部件特征和相对几何上预测谓词；时序用 GRU/HMM 平滑，避免单帧抖动。
- 维护 belief `b_t`：每个谓词一个概率；允许 `true → false`（撤销）和 `false → true`（完成）。
- 进度不是标量：`progress = Σ w_k * 1[b_k = true]`，但修复决策用**最低成本未完成/被撤销谓词**，不是简单看总分。

### F.3 撤销增广

- **反向播放**成功 episode 的最后 2–5 秒，标为“进度回退”。
- **对象瞬移/移除**：把已完成子目标的物体移走或放回起点（对应 T12/T24/T27）。
- **人手插入/遮挡**：合成手部 mask 或真实人手视频，标为“不可观测/需等待”。
- **状态翻转**：拉链拉开、盖子拧回、毛巾翻开、笔盒打开（对应 T14/T16/T17/T19）。
- 训练一个 `progress_delta` 头（+1/0/−1）或对比损失：正向片段 vs 反向片段；让模型学会“这不是新的子目标，而是回退”。

### F.4 修复策略

```text
if predicate true -> false:
    mark subgoal k as undone
    choose repair action = argmin cost(restore k)
    prompt VLA: "redo <subgoal k>" or call part-aware skill
    re-check predicate; if still false, retry / safe stop
if object missing:
    re-scan workspace (head + wrist)
    if not found: stop safely, log; do not hallucinate
```

- **定向修复**优先于全程重跑：180s 预算下，重跑全程通常不够。
- 修复顺序：先修被撤销的子目标，再继续后续；如果后续依赖被破坏，回退到最早受影响的谓词。
- 与 portfolio 结合：如果某任务的撤销恢复率很低，把它列为高杠杆调试项。

### F.5 评测

- **官方备注脚本化**：按 C.2 的 `human_1/human_4` 在真机/仿真中执行；每任务 10 trials，记录检测延迟、修复成功率、总时间、false positive。
- **合成 undo**：对成功 episode 做反向/移除/翻转；离线测 progress_delta 的 AUC。
- **消融**：单调进度头 vs RPSM；无 part 状态 vs 有 part 状态；无修复 vs 有修复。
- **指标**：undo detection rate、repair success、time-to-recover、false alarm rate、full success under human disturbance。

### F.6 风险

- 谓词设计过细 → 标注/观测困难；先做 8–12 个跨任务通用谓词（grasped/in_hand/inserted/on_hook/closed/stacked/sorted/in_box）。
- 遮挡/透明物体 → 多视角 + 腕部 + 置信度；不可观测时保持 belief，不要强行翻转。
- 人手遮挡 → 等待/降速；安全优先。
- 规则是否允许“主动暂停”未核实；先做被动检测 + 短停，不做长时间等待。

## G. Compliance Compiler（SERB 2.0）

### G.1 规则 → 实现 → 测试

| 规则 | 来源 | 实现 | 测试 |
|---|---|---|---|
| 单模型全 32 任务 | Feishu 1.1/1.2 | 一个 checkpoint；所有头在同一计算图；运行时不 reload/不切换 | 静态 manifest；运行时模型 hash 不变；任务切换日志 |
| 不得混合多个模型 | Feishu 1.1 | 不在线程内跑 SAM3/PartSAM/其他 policy；教师仅离线 | 进程/依赖扫描；网络请求白名单 |
| 10 trials/task；5 类 ×2 | Feishu 1.2/2.1 | LPL 评测器固定协议；分层抽样 | 协议配置 + 日志审计 |
| 180s | Feishu 2.1 | 阶段时间预算；watchdog；超时前 safe retreat | 注入超时；检查失败但步骤分记录 |
| 自部署 API | Feishu 1.1 | Docker/conda；N 个连续端口（8765…8765+N−1，数量恰好等于 N）；健康检查；会话隔离 | 4h soak；端口并发；崩溃恢复；端口数核对 |
| 人机安全 | 伦理 + human 干扰 | 深度/部件 human query → 降速/暂停；速度/工作空间限幅；watchdog | 人手接近红队；急停；NaN/超限注入 |
| 许可证 | 数据/模型卡 | 只使用 Apache-2.0/明确许可；SPDX 清单；NOTICE | license scan；缺失即阻断 |
| 无任务硬编码 | 规则未明示，但高风险 | 不喂 task id；语言 + 观测；坐标由部件检测产生 | task-id ablation；代码审计 |
| 可复现 | 最佳实践 | seed/config/git hash/data version/model card | 重放一次完整评测 |
| 不刷榜/不挑 trial | 评测诚信 | 固定协议；所有 trial 落日志；不手工挑成功样本 | 日志完整性检查 |
| 交互质量 | README §6 | 延迟预热/批处理/p99 守门；动作限幅/平滑/异常检测 | 延迟抖动统计；动作离群检查；4h soak |

> **注意**：上表中“无任务硬编码”“外部数据/模型”不是已读手册的明确条款，属于**风险控制**；在正式提交前必须读 5.1/5.2 确认。若规则允许外部预训练模型，按 Apache-2.0 清单使用；若不允许，则只用挑战数据微调，SPA-VLA 仍成立。

### G.2 人机安全

- **安全壳**：工作空间包围盒、最大末端速度、最大关节速度、waist/base 限幅、夹爪力上限（若可设）。
- **人机分离**：头部/腕部深度 + 部件 human query → 人手/人臂最小距离；低于阈值降速，低于停止距离暂停。
- **暂停-恢复**：暂停时保持姿态、记录 belief；人离开后重观测、重定位、继续；不盲目重跑。
- **watchdog**：推理超时、NaN、动作超限、端口断连 → 清零动作/保持/安全退出。
- **审计**：每 trial 记录时间、动作统计、延迟、安全事件、恢复事件；提交前回放。

### G.3 提交 manifest

- 模型卡：底座、参数量、许可证、训练数据、外部依赖、已知限制。
- 数据卡：挑战数据版本、派生标签（部件 mask/谓词）的生成方法、是否含外部数据。
- 配置：seed、chunk size、control space、image resize、obs_delta_indices、token 处理。
- 部署：N 端口、并发、p99 延迟、显存、热设计、健康检查、降级策略。
- 合规：SPDX/NOTICE、单模型声明、无 task-id/无硬编码声明、红队报告。
- 复现：git hash、环境 lockfile、评测脚本、日志格式。

### G.4 未核实项的处理

- **外部数据/模型**：默认只用挑战数据 + Apache-2.0 底座；在 manifest 中列明；若规则禁止，切换到“挑战数据微调小模型 + SPA-VLA”的 fallback。
- **N/控制频率**：按 N=3 的示例先做并发/隔离；用配置注入，不写死；实际 N 公布后只改部署参数。
- **评分公式/tie-break 细节**：按 1.2 的排序顺序实现；4.2 未读，不假设每任务权重；Q 只做 tie-break。
- **单模型定义**：所有任务决策由一个 checkpoint 产生；辅助头在同一图；安全 monitor 规则式；不跑第二个 policy。
- **base/waist**：默认静态；只有在探针确认允许且任务需要时小范围动；否则退回双臂 + 相对位姿。

## H. Endurance Governor

### H.1 服务架构

```text
N ports 8765..8765+N-1
   │
   ├─ per-session state（episode、belief、chunk cache；互不共享可变状态）
   ├─ request queue / dynamic batcher（按 deadline 聚合）
   ├─ one model server（SPA-VLA；part head + action head）
   ├─ watchdog / health / metrics
   └─ safe fallback（hold / retreat / wait；不切换模型）
```

- 一个共享模型服务，N 个轻量会话；每个端口独立 reset，避免跨机器人污染。
- 动态 batching 以 p99 deadline 为约束，不无限等 batch。
- 预热：启动时跑 dummy 前向，分配显存/CUDA graph；避免首个 trial 超时。
- 量化：FP8/INT8（若精度允许）；优先量化视觉 backbone，动作头保持高精度。
- 缓存：action chunk 缓存、part token 缓存、视觉 token 缓存（静态场景）；缓存失效用置信度/人手/大位移触发。

### H.2 延迟预算

```text
T_chunk = action_chunk_size / control_frequency
target: p99_inference < 0.8 * T_chunk
```

- 控制频率未知；**假设控制 30Hz**（数据集 30fps），先做 `chunk=8`（约 267ms）与 `chunk=16`（约 533ms）两档；实际频率公布后只改预算参数。
- p99 超过预算 → 增大 chunk（更少调用）或复用 part token/缓存；不要切到另一个模型。
- 记录 p50/p95/p99、jitter、超时率、每端口 QPS。

### H.3 降级阶梯

1. **Normal**：全量 SPA-VLA，chunk=8，part tokens 每 chunk 更新。
2. **High load**：chunk=12–16；part tokens 每 2 chunk 更新；mask 头降频，只用 centroid。
3. **Thermal/memory**：图像分辨率降一档；FP8/INT8；early-exit 视觉层（同一模型）；保持动作头精度。
4. **Critical**：hold/retreat/wait；记录；恢复后从 belief 继续；**不加载第二个模型**。

### H.4 语义续航

- **Part-State Memory**：每个部件存 descriptor、3D centroid、last seen、confidence、谓词状态；TTL/置信度衰减。
- **遮挡**：人手/物体遮挡时保持 belief；人离开后重检测 + 重投影；不把“看不见”当成“消失”。
- **干扰**：检测到状态回退 → RPSM 修复；检测到物体移除 → 重扫描/安全停止。
- **跨阶段**：阶段切换不重置记忆；只重置 episode 级状态。
- **指标**：30s+ 遮挡后的重定位成功率、干扰后恢复率、belief 漂移、false forget rate。

### H.5 指标与 soak

- 4 小时 soak：N 个并发会话，固定脚本化任务；记录成功率漂移、p99 延迟漂移、显存增长、热节流次数、崩溃/重启。
- 成功率漂移：前 25% vs 后 25% 的 trial 成功率；目标 <5pp。
- 内存：RSS/显存增长 <5%；无泄漏。
- 热：GPU 温度/clock；节流时是否能维持降级策略。
- 能量：能测则记录 GPU 能耗/每次成功；不能测则用调用次数/动作能量代理；不夸大。
- 物理能量：减少不必要的 base/waist 运动、jerk；但这不是主卖点。

## I. Task Portfolio Optimizer

### I.1 模型

- 每个任务 `p_i` 用 Beta 后验；先验按难度或统一。
- 观测：LPL 的 10 trials/task（5 类 ×2）。
- 派生：
  - `E[S] = (1/32) Σ E[p_i]`
  - `Var(S) = (1/32^2) Σ Var(p_i)`
  - `P(S > S*)`：Monte Carlo 采样。
- 目标：最大化 `E[S]`，并在接近目标时最大化 `P(S > S*)`；同时惩罚高方差任务。

### I.2 算法

```text
for each weekly cycle:
    update posterior from LPL
    flag tasks with P(p_i < 0.05) > 0.5       # no-zero
    for each task:
        gain_i = target_i - E[p_i]
        score_i = gain_i / cost_i             # or UCB_i / cost_i
    allocate debug/training budget to top tasks
    re-run LPL; repeat
```

- `target_i`：同类任务 75th percentile，或 `min(0.8, E[p_i] + 0.2)`。
- `cost_i`：历史调试时长、接触密度、任务时长、失败模式数；没有历史时用难度/时长代理。
- 对高方差任务：优先做“保守化”（固定 seed/温度 0/更短 chunk/更稳恢复），而不是追高均值。

### I.3 LPL 协议

- 每任务 10 trials；5 类泛化各 2（位置/干扰物/背景/未见物品/人为干扰）。
- 离线：留出 episode（每任务 10–20%）；按任务/难度/时长分层。
- 半离线：用 C.2 的 human 备注构造扰动；仿真/真机调试。
- 真机：优先 T01/T04/T10/T15/T16/T24/T30；每任务 5–10 trials。
- 统计：每任务 Wilson 95% CI；总体 bootstrap CI；报告 `E[S]`、`P(S>S*)`、`Var(S)`。
- 不做“挑成功 trial 上报”；所有 trial 落日志。

### I.4 分配示例

| 场景 | 计算 | 总平均增益 |
|---|---|---:|
| 5 个 0% → 30% | 5×0.30/32 | +4.7pp |
| 5 个 70% → 80% | 5×0.10/32 | +1.6pp |
| 1 个 0% → 50% | 0.50/32 | +1.6pp |
| 10 个 30% → 40% | 10×0.10/32 | +3.1pp |
| 全部 32 个 +2pp | 0.02 | +2.0pp |

> 结论：先修 0%，再修“低均值、低成本、可观测”的任务；不要平均用力。

### I.5 与训练的关系

- Portfolio 决定“下一个调试/标注/训练重点”，不直接改模型结构。
- 如果某任务连续两周无提升，标记为“低弹性”，把预算转到其他任务；不要沉没成本。
- 如果某任务提升来自“任务特定硬编码”，拒绝；必须是可泛化的部件/状态能力。

## J. 实验计划

### J.1 B0–B9

| 编号 | 周 | 目标 | 交付 | 成功标准 |
|---|---|---|---|---|
| B0 | 1 | 规则/接口/基线 | 可跑 baseline；32 任务 LPL；Compliance manifest | baseline 能跑通至少 20 任务的评测流程（不要求成功）；LPL 可复现 |
| B1 | 1–2 | 部件教师 | SAM3/PartSAM 伪标签；质量报告；可视化 | 关键部件 mask IoU/centroid 达可用；人工验证通过 |
| B2 | 2–3 | SPA-VLA | 首个 checkpoint；part head 消融 | full success 相对 B0 提升 ≥1.5pp（目标 3pp） |
| B3 | 3–4 | RPSM | 谓词/undo 增广；修复策略 | undo detection AUC >0.8；恢复成功率 ≥50% |
| B4 | 4–5 | Contact servo | 插头/网线/拉链/瓶盖技能 | 硬任务成功率提升 ≥10pp（目标） |
| B5 | 5 | Compliance runtime | 人机安全/超时/端口/红队 | 4h soak 无崩溃；安全事件可恢复 |
| B6 | 5–6 | Endurance | N 端口/批处理/降级 | p99 < 0.8×T_chunk；成功率漂移 <5pp |
| B7 | 6 | Portfolio | 后验/分配/LPL 报告 | 预算分配可解释；0% 任务清零 |
| B8 | 7 | 全 32 任务 | 正式协议评测 | 32×10 trials；报告 CI 与失败模式 |
| B9 | 8 | 审计/复现 | 提交包；红队；复现实验 | 规则/manifest 全通过；重放一致 |

### J.2 评价指标

- 主：full success（每任务/总体）、95% CI。
- 次：step score（tie-break）、检查点完成率、超时率。
- 泛化：位置/干扰物/背景/未见物品/人为干扰分桶成功率。
- 状态：undo detection、repair success、time-to-recover、false alarm。
- 感知：mask IoU、centroid error、3D error（有深度时）。
- 部署：p50/p95/p99、jitter、显存、热节流、4h soak 漂移。
- 合规：单模型 hash 不变、无 task id、许可证清单、红队通过。

### J.3 消融矩阵

| 变量 | A0 | A1 | A2 | A3 | A4 | A5 | A6 | A7 |
|---|---|---|---|---|---|---|---|---|
| part head | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| language-part | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 3D/temporal | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ |
| RPSM | — | — | — | — | ✓ | ✓ | ✓ | ✓ |
| contact servo | — | — | — | — | — | ✓ | ✓ | ✓ |
| undo aug | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ |
| no task id | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

## K. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 教师分割噪声（透明/反光/小部件） | 高 | 中 | 多视角 + 腕部 + 置信度门控 + 人工验证集；oracle-mask 上限 |
| part query 坍塌 | 中 | 高 | Hungarian matching + diversity loss + 可视化/熵监控 |
| part head 不提升 full success | 中 | 高 | 先做 oracle-mask 上限；若上限也低，转 contact servo + RPSM |
| 单模型解释争议 | 中 | 高 | 同一 checkpoint；教师离线；manifest 声明；不跑第二 policy |
| 外部数据/模型规则不允许 | 中 | 高 | 默认挑战数据 + Apache-2.0；准备小模型 fallback |
| N/延迟/并发超预算 | 中 | 高 | 动态 batching、chunk、量化、降级；4h soak |
| 人机安全事件 | 低 | 极高 | SSM、速度/空间限幅、watchdog、红队、急停 |
| 180s 超时 | 中 | 中 | 阶段时间预算、watchdog、超时前 safe retreat |
| 撤销检测误报 | 中 | 中 | 时序平滑、置信度、迟滞；只在低风险时暂停 |
| 过拟合占位榜 | 中 | 中 | 只用 LPL/论文；不引用假分数 |
| 为步骤分牺牲成功率 | 中 | 高 | 词法目标：先 S 后 Q；首点只做辅助 |
| base/waist 规则不允许 | 中 | 中 | 默认静态；探针；退回双臂 + 相对位姿 |
| 未见语言/中文 | 中 | 中 | 5 条复述留一法；约束图；翻译增广（若允许） |
| 数据/派生标签许可证 | 低 | 中 | Apache-2.0 源数据；派生标签自有；NOTICE |

**停止条件**：

- 如果 A4（oracle mask 上限）相对 A0 的 full success 提升 <2pp，停止扩大 part head，转向 contact servo + RPSM + portfolio。
- 如果规则明确禁止外部预训练模型，切换到“挑战数据微调小模型 + SPA-VLA”；不放弃部件接口。
- 如果 4h soak 成功率漂移 >10pp，优先修部署，不继续加模型能力。

## L. 来源（检索日期 2026-10-23）

| 编号 | 来源 | URL | 用途/备注 |
|---|---|---|---|
| S1 | UniBot 挑战赛主页 | `https://unibot.unitree.com/challenges.html` | 32 任务、32000 episodes、169h；任务 slug |
| S2 | 官方排行榜 | `https://unibot.unitree.com/leaderboard.html` | 确认 Coming Soon + 随机占位脚本 |
| S3 | 任务信息示例 | `https://unibot.unitree.com/tasks_v2/hang_the_cup/info.json` | `score_steps`/`generalization`；32 任务同模式 |
| S4 | Feishu 参赛手册 | `https://scnhkkqlu12w.feishu.cn/docx/Uz7OdFBcDoqP1dxgH62cHW1CnMh` | 1.1–2.2 可读；2.3–5.2 未读 |
| S5 | 提交接口 README | `https://github.com/unitreerobotics/unibot_submission` | `metadata`、`PolicyService`、端口、§6 检查 |
| S6 | 数据集 collection | `https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge` | 32 任务 LeRobot v3 数据 |
| S7 | WALL-OSS-0.5 | `https://arxiv.org/html/2605.30877v1` | 4B、20+ embodiments；微调后 60.5% progress、+17.5% over π0.5 |
| S8 | MolmoAct2 | `https://arxiv.org/abs/2605.02881` | open action reasoning；OpenFAST/flow matching/MolmoThink |
| S9 | DreamZero | `https://arxiv.org/pdf/2602.15922.pdf` | 14B WAM、7Hz、约 150ms/chunk、+42% unseen（跨 embodiment 视频演示） |
| S10 | SAM 3 | `https://proceedings.iclr.cc/paper_files/paper/2026/hash/e0982cbc81401df3430ee1ff780dc7a2-Abstract-Conference.html` | 概念/文本提示分割；教师候选 |
| S11 | PartSAM | `https://arxiv.org/pdf/2509.21965v3` | 3D part segmentation；教师候选 |
| S12 | ISO 10218-2:2025 | `https://www.iso.org/standard/73934.html` | 安全参考；不声称认证 |
| S13 | GigaBrain-0.7-3.5B | `https://huggingface.co/open-gigaai/GigaBrain-0.7-3.5B-Base` | Apache-2.0 底座候选 |
| S14 | UnifoLM-WLA-1.0 | `https://github.com/unitreerobotics/unifolm-wla`；`https://huggingface.co/unitreerobotics/UnifoLM-WLA-1.0-Base` | Apache-2.0 底座候选；6B/G1/2500h |
| S15 | 32 任务 info 汇总 | 通过 `https://r.jina.ai/https://unibot.unitree.com/tasks_v2/<slug>/info.json` 逐页抓取 | 本文件 C.1/C.2 的原始数据 |

> 说明：S3/S15 的直接 JSON 请求会被 EdgeOne 拦截（HTTP 567）；网页正文通过 `r.jina.ai` 读取。Feishu 手册在 2.2 后被懒加载/登录墙截断，未能读取 2.3–5.2；相关结论均标“未核实”。

## M. 开放问题

1. **外部数据/模型**是否允许？若允许，Apache-2.0 底座（WLA-1.0/GigaBrain-0.7）可用；若不允许，挑战数据微调的小模型 + SPA-VLA 仍是 fallback。
2. **N 台机器人/端口**：README 示例 N=3，具体值由组委会另行公布；并发/批处理/显存按 N 可配置。
3. **控制频率/action chunk**：README 的 `action_chunk_size` 如何映射到控制频率？p99 预算需实测。
4. **4.2 评分公式**：每任务步骤分是 trial 平均还是其他聚合？Q 是否按任务归一化？未读。
5. **4.3 排名/入围/成绩记录**：榜单入围条件、成绩记录方式、提交日期如何记录？未读。
6. **单模型定义**：辅助头/安全 monitor 是否算“多个模型”？当前设计把所有任务决策放进一个 checkpoint，安全 monitor 规则式。
7. **任务 ID**：评测是否把 task id 传给模型？我们主动不用；若官方只给 task id 不给语言，需要适配。
8. **语言**：评测用 5 条复述、未见复述、还是中文？未核实；先做留一法/约束图。
9. **人为干扰协议**：脚本化还是自适应？`human_1/human_4` 的时序/频率未知；先按备注构造测试。
10. **base/waist 限制**：是否允许移动底座/腰部？未核实；默认静态 + 探针。
11. **真实榜单**：公开榜仍是占位；真实排名/强基线不可见；不要用假分数做决策。
12. **派生标签许可证**：部件 mask/谓词标签由我们生成，源数据 Apache-2.0；提交时保留 NOTICE。
<!-- ARTIFACT:END -->
