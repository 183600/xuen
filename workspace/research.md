# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 9 轮 · R3-VLA：Regroup / Rephrase / Recover——把泛化拆成三种可训练的不变性

> 检索/复核日期：2026-10-27（UTC）。赛事身份不变：宇树 **UniBot 世界挑战赛**（unibot.unitree.com），G1 + Dex1，32 项桌面任务，通才单模型赛道，选手自部署 + 官方远程真机 API。本轮三个灵感词是「视觉-语言-动作模型」「痛点分析」「评测指标」。状态文件上一轮是第 8 轮 SURE-BT；本轮作为新灵感循环的第 1 轮继续写，但不推倒上一轮，而是把它降为运行时骨架。

## 0. 先给结论：第 8 轮把恢复放在运行时，这一轮要把恢复放回训练分布

第 8 轮的主线是 **SURE-BT**：把官方评分图编译成分块同步行为树，在 chunk 边界做验证/恢复。它解决的是“执行时怎么补救”。但本轮新增的证据说明，只有运行时补救不够：

- 动作块一旦进入系统，误差放大是常态，闭环重规划并不稳定地把误差收缩；作者明确建议用“扰动/树覆盖训练”让策略见过偏差（[S36]）。
- 标准 SFT 数据几乎只有成功轨迹，策略没有见过“失败后怎么回来”；RePO-VLA 用恢复段训练，把对抗成功率从 20% 提到 75%（[S39][S40]）。
- 公开数据的 192 个采集 session 之间存在明显视觉域偏移；随机切分会把同一 session 泄漏到验证集，本地涨点不等于官方 OOD 涨点（本轮统计，[S5][S6]）。
- 官方每任务有 5 条英文复述；VLA 对复述过拟合，LIBERO-Para 报告 22–52pp 下降（[S41]）。
- 官方还记录每步延迟/波动/动作统计规律性，作为结果可信度信号（[S7] §6）。这意味着“高成功率但动作抖动/延迟尖峰”也可能被看见。

所以本轮把主押注从“运行时 BT”升级为 **R3-VLA：Regroup（按 session 分组域泛化）+ Rephrase（复述不变性）+ Recover（扰动恢复训练）**，三者共享同一个 checkpoint；SURE-BT 保留为运行时骨架，并新增“可靠前缀 + 安全端点”把训练成果兑现。

## 1. 六个硬事实

### 1.1 动作块误差：放大常见，闭环重规划不保证收缩

[S36] 在 12 个操作任务、3 个基准上注入小动作误差，测量开环/闭环传播率：稳定状态稀少，误差放大常见；闭环重规划很少把开环放大转成可信收缩。作者建议显式训练恢复，而不是期待它从模仿学习中自发出现。

**对 UniBot 的含义**：第 8 轮的 BT 只能在 chunk 边界补救；如果策略本身不会恢复，BT 的恢复算子只是“再试一次”，不是“学会回来”。训练侧必须补恢复数据/扰动覆盖。

### 1.2 执行视界有峰值；chunk 内动作 attend 固定 VL token

[S37] 显示执行视界先升后降；flow-based VLA 的 chunk 内动作对 vision-language token 的注意力几乎不变，开头/结尾动作 token 是稳定锚点；动作自注意力可作为“可预测极限”的代理，AutoHorizon 在测试时估计每个 chunk 的可执行视界，开销可忽略。

**含义**：固定 `action_chunk_size` 不是“越长越好”；我们可以在不改变 API 的前提下，只执行可靠前缀，把剩余动作填成安全端点。

### 1.3 恢复需要训练；失败轨迹也有价值

[S39] 在 17 种扰动、4 个模态上发现动作是最脆弱的模态，现有视觉鲁棒 VLA 不会自动获得其他模态的鲁棒性；[S40] 用恢复段初始化 + 进度价值函数，把对抗成功率从 20% 提到 75%。[S48] 则证明推理时反事实重对齐也能大幅恢复，但需要“把机器人/场景最小代价地拉回可行流形”，在不可逆任务上有风险。

**含义**：先做便宜的“动作噪声鲁棒优化 + 推理时恢复”，再做“仿真/真机恢复微调”；不要一上来就训世界模型。

### 1.4 复述是独立轴；干净能力已经饱和，鲁棒性才分得开

[S41]：7 个 0.6B–7.5B VLA 在复述下一致下降 22–52pp，主因是物体级词汇替换，说明模型依赖表面匹配。[S42]：6 个系统在 clean LIBERO 上只差 1.58 分，但鲁棒性/复述摘要跨度 14.62/31.08 分。

**含义**：官方每任务 5 条复述不是“数据细节”，而是可训练的语言轴；用复述 dropout + 一致性 + 留一复述验证，成本低、证据强。

### 1.5 评测本身会骗人：shortcut、显著性、过拟合、数据源依赖

[S43] 审计 LIBERO/CALVIN/SimplerEnv/RoboCasa/RoboTwin 2.0，提出四种失效模式：shortcut solvability、lack of statistical significance、creeping overfitting、data-source dependence。LIBERO 上 0.09B 无语言编码器 probe 接近 SOTA；多数报告增益不可证显著。

**含义**：我们不仅要“跑得高”，还要“证明不是 shortcut/不是噪声/不是泄漏”。DGS-32 要把 session、复述、扰动三重留出和配对统计写进协议。

### 1.6 数据里藏着三份免费监督

本轮把 32 个 HF 数据集全量解析后确认：

| 隐藏监督 | 规模 | 用途 |
|---|---:|---|
| 采集 session | 192 个（3–10/任务，2–6 个 robot ID，2026-02-05–06-25） | 域标签；session-grouped 训练/验证 |
| 官方复述 | 每任务 5 条（共 160 条；平均 Jaccard 0.40，最低 0.06） | 复述不变性训练/留一复述验证 |
| 人扰备注 | 30/32 任务有 human_1_note + human_4_note | 扰动剧本；恢复训练/评测 |

同时有三处 spec gap：9 个任务缺 `unseen_object_3`（T08/T09/T15/T16/T19/T29/T30/T31/T32），T31/T32 没有任何 generalization 备注；所有 `score_steps` 总分归一为 100，但步数 2–5 不等（11 个 2 步、14 个 3 步、5 个 4 步、2 个 5 步）。这些不是“数据脏”，而是告诉我们：**不要过拟合备注；缺失轴要有兜底脚本。**

## 2. 痛点分析：按“可训练性”排序

| 痛点 | 证据 | 影响的分数 | 本轮对策 |
|---|---|---|---|
| P1 隐藏域偏移/会话泄漏 | 192 sessions；between/within 图像均值比中位数 2.03，最高 7.46；随机切分泄漏 | 位置/背景/干扰物 60% | Regroup：session-grouped 采样/验证 |
| P2 恢复不在训练分布 | SFT 只有成功；[S36][S39][S40] | 人扰轴 20% + 执行漂移 | Recover：动作噪声鲁棒优化 + 恢复微调 |
| P3 复述过拟合 | 5 条复述；[S41] 22–52pp；[S42] 31.08 分跨度 | 未见物品/语言轴 20% | Rephrase：dropout + 一致性 + 留一复述 |
| P4 固定 chunk 开环 | API 整块执行；[S36][S37][S38] | 接触-rich/长程 | AEH：可靠前缀 + 安全端点 |
| P5 评测噪声/字典序/shortcut | 320 次、SE 2.56pp；[S43] | 排名/结论 | DGS-32：配对/分层/审计/功效 |
| P6 spec gap/数据质量 | 9 缺 unseen 备注；T31/T32 空；2–5 步；`tasks` 字段 schema 不一致 | 任务级判断 | 兜底脚本 + 不把备注当测试泄漏 |

## 3. R3-VLA：三种不变性，一个 checkpoint

### 3.1 Regroup：把 session 当免费域标签

- 从 `task_id` 解析 session/date；每个任务 3–10 个 session，足够做 leave-one-session-out。
- 训练：任务均匀 → session 均匀的两级采样；对最大 session 降权（最大占比平均 32.4%，最高 51.5%）。
- 正则：group DRO / V-REx 作为消融；主路径用“平衡采样 + 最差 session checkpoint 选择”，更稳。
- 增强：只做任务安全的背景/光照/相机小扰动；颜色任务不能改物体颜色。
- 验证：held-out-session；同时报告 in-domain，防止“泛化涨、拟合掉”。

### 3.2 Rephrase：把 5 条官方复述用满

- 每条样本随机抽一条复述（paraphrase dropout）；同一观测-动作对用两条复述做一致性损失（动作分布 KL/L2）。
- 测试时优先 canonicalize 到任务 canonical 描述（零额外延迟）；只有在延迟允许时才对 5 条复述做动作平均。
- 验证：leave-one-paraphrase-out；报告 canonical vs held-out 的 gap。
- 不做外部 LLM 生成复述；用官方 5 条 + 规则化同义替换，避免外部数据/模型合规风险。

### 3.3 Recover：从官方人扰备注到恢复训练

- 解析 30 个任务的 human_1/human_4 备注，归类为目标平移、容器/夹具平移、步骤撤销、动态遮挡。
- L0（最便宜）：动作噪声鲁棒优化——对 flow-matching 目标加最坏情况动作噪声（[S39]），不需要新数据。
- L1：推理时恢复——SURE-BT 算子 + 两样本触发/反事实重对齐（[S44][S48]），不需要训练。
- L2：仿真扰动 rollouts + RePO 式恢复段训练（[S40]）；需要 sim 或 paired real-to-sim。
- L3：真机调试槽收集少量恢复数据，做最后一公里微调。
- 课程：小动作噪声 → 物体平移 → 撤销 → 遮挡；clean:perturbed ≈ 7:3，防止遗忘。
- 验证：held-out perturbation / 官方人扰轴；同时看不可逆失败是否增加。

### 3.4 为什么是一个模型

三者都是同一 WLA-1.0-Base 上的数据/损失/微调策略；AEH 头挂同一 backbone；VFCS 只用同一模型的内部置信；SURE-BT 是确定性代码。没有第二个在线模型，符合单模型规则。

## 4. 推理端：把“可靠前缀”写进 chunk 合同

- **AEH**：用动作自注意力/两样本方差估可靠前缀 L*；执行前 L* 步，剩余 T_a−L* 步填保持/回撤/预放置安全端点；下一块边界重观测。API 仍然收到完整 T_a，不违反接口。
- **VFCS**：只在关键状态（接触、插入、放置、人扰后）采样 K=2，用 MG-Select 的 KL 或两样本方差选块；优先选“分数接近但更平滑”的块，照顾官方动作规律性指标。K=2 是延迟上限；p99 不达标就退回 K=1。
- **SURE-BT**：保留第 8 轮的 chunk 边界 tick、谓词迟滞、护理级别、恢复算子；AEH/VFCS 作为 chunk policy 插件，不改变 BT 的决策周期。
- **延迟/规律性预算**：T_a=8 → 267ms，T_a=16 → 533ms；记录 p50/p95/p99、latency IQR、动作 jerk、离群率；官方 §6 明确会看这些。

## 5. 评测：DGS-32（Domain-Grouped Split for 32 tasks）

- **三重留出**：held-out-session（域泛化）、held-out-paraphrase（语言泛化）、held-out-perturbation（恢复）；再加 in-domain 作对照。
- **矩阵**：32×10 = 320；5 轴×2；配对条件；官方人扰备注优先，缺失任务用兜底脚本并标注 inferred。
- **指标**：success（主）、step score（tie-break/诊断）、axis success、recovery rate、time-to-recovery、intervention rate、predicate F1、timeout、p99 latency、latency variability、action jitter、domain gap、paraphrase gap、shortcut probe gap。
- **统计**：Wilson CI；按 task/session 分层的配对 bootstrap；McNemar；预注册 +5pp；单任务 +10pp 不当真；序列检验控制早停。
- **审计**：四种失效模式各做一个诊断；尤其 shortcut probe（无语言/场景-only 小模型）和 data-source dependence（按 robot/date 留出）。
- **tie-break**：11 个 2 步任务（50/50）、14 个 3 步（30/30/40）、5 个 4 步（25×4）、2 个 5 步（20×5）；步骤分分辨率 0.06–0.16pp/单 episode。成功率完全相同时，步骤分可能以极小差距决定名次；只在“几乎成功”区域做步骤分保险，绝不牺牲成功率。

## 6. 与第 8 轮的关系

| 关系 | 内容 |
|---|---|
| 保留 | SURE-BT、WLA-1.0-Base、放置锚点、恢复算子库、护理级别、几乎成功前沿、调试槽 |
| 升级 | SMB-320 → DGS-32；恢复算子 → PRT + 运行时；步骤分诊断 → tie-aware portfolio |
| 新增 | SGDG、PIT、PRT、AEH、VFCS、benchmark audit、动作规律性指标 |
| 降级 | 双手角色图（P1，R3 之后）；风险头（可选）；放置锚点（叶子） |
| 砍 | ICR、L2L、全孪生、自由仿真、运行时 MPC/RL、布料/拉链/透明全物理、每任务 LoRA、WMA 主路径 |

## 7. 风险与合规

- **单模型**：R3 全部是同一 checkpoint 的训练策略；AEH 头同 backbone；VFCS 无外部 verifier；默认不用外部 LLM/VLM/检测器。
- **外部数据**：默认 OFF；只用官方 33k；复述增广用规则模板。
- **备注泄漏**：官方人扰备注是训练先验，不是测试脚本；训练时混随机扰动，评测时留出。
- **sim-to-real**：PRT 的 L2 需要 sim；没有 sim 就停在 L0/L1，不要硬上。
- **统计**：320 次、SE 2.56pp；+3pp 只当信号，+5pp 才下结论；配对/分层/CI。
- **榜单占位**：29.7% 不是真实头部；不用它做模型选择。
- **延迟/规律性**：VFCS 只在关键状态用；p99 不达标或 jitter 增加 >10% 就砍。

## 8. 一句话押注

**把 192 个采集 session 当免费域标签、30 个任务的 60 条官方人扰备注当恢复剧本、5 条官方复述当语言增广，在同一个 WLA-1.0-Base 上做 R3-VLA（Regroup/Rephrase/Recover）训练；推理端用可靠前缀+安全端点兑现，评测端用 DGS-32 的 session/复述/扰动三重留出验证——这是本轮最值得押注的方向。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 9 轮产物区 · R3-VLA + DGS-32 技术报告（Regroup / Rephrase / Recover）

> 目标赛事：宇树 **UniBot 世界挑战赛**（unibot.unitree.com），G1 + Dex1，32 项桌面任务，通才单模型赛道，选手自部署 + 官方远程真机 API。检索/复核日期：**2026-10-27（UTC）**。本报告在第 8 轮 SURE-BT 基础上，把主火力从“运行时恢复”扩展到“训练分布 + 推理前缀 + 评测协议”。核心判断：**运行时 BT 是必要的，但不是充分的；策略必须在训练中见过域偏移、复述变化和扰动恢复，评测必须按 session/复述/扰动留出，才能把本地涨点转成官方 OOD 涨点。**

## 0. 产物摘要

### 0.1 一句话

**把 192 个采集 session 当免费域标签、30 个任务的 60 条官方人扰备注当恢复剧本、5 条官方复述当语言增广，在同一个 WLA-1.0-Base 上做 R3-VLA（Regroup/Rephrase/Recover）训练；推理端用可靠前缀 + 安全端点兑现，评测端用 DGS-32 的 session/复述/扰动三重留出验证。**

### 0.2 组件与是否进推理

| 组件 | 作用 | 进推理？ |
|---|---|---|
| WLA-1.0-Base | 唯一学习 checkpoint | 是（唯一模型） |
| Regroup：session 平衡采样 | 降低采集域过拟合 | 否（训练） |
| Rephrase：复述 dropout/一致性 | 语言不变性 | 否（训练） |
| Recover：动作噪声鲁棒优化 | 动作级抗扰 | 否（训练） |
| Recover：恢复段微调 | 学会从偏差回来 | 否（训练） |
| AEH：可靠前缀 + 安全端点 | 固定 chunk 内只信前 L* 步 | 是（同一模型 + 轻量头） |
| VFCS：verifier-free 选块 | 关键状态 K=2 选更稳的块 | 是（同一模型，无外部 verifier） |
| SURE-BT | chunk 边界验证/恢复 | 是（确定性代码） |
| 谓词/风险头（可选） | 条件可靠性 | 是（同 checkpoint 辅助头） |
| DGS-32 | 三重留出评测 + 审计 | 否（评测） |
| 动作规律性监控 | 延迟/抖动/离群 | 否（评测/部署） |

### 0.3 预期收益（可证伪）

| 杠杆 | 目标增益 | 证据/假设 | 停止条件 |
|---|---:|---|---|
| Regroup（held-out session） | +2–4pp | between/within 比中位数 2.03；随机切分泄漏 | 若 held-out session 不涨或 in-domain 回归 >1pp，退回普通采样 |
| Rephrase（held-out paraphrase） | +1–3pp | 5 条复述；[S41] 22–52pp；[S42] 31.08 分跨度 | 若 canonical 回归 >1pp 或 held-out 不涨，只保留 canonicalization |
| Recover（人扰/扰动） | +3–5pp | [S36][S39][S40]；人扰轴 20% | 若不可逆失败增加或人扰轴不涨，停在 L0/L1 |
| AEH（接触-rich） | +1–3pp | [S37][S38]；固定 chunk 开环 | 若 time-to-success 恶化 >10%，关 |
| VFCS（关键状态） | +1–3pp | [S44][S45]；K=2 | 若 p99 超 chunk 或 jitter >10%，砍 |
| 合计（保守） | **+5pp** | 320 次、SE 2.56pp；配对设计更稳 | 95% CI 跨 0 不上线 |

### 0.4 与第 8 轮的关系

| 关系 | 内容 |
|---|---|
| 保留 | SURE-BT、WLA-1.0-Base、放置锚点、恢复算子库、护理级别、几乎成功前沿、调试槽 |
| 升级 | SMB-320 → DGS-32；恢复算子 → PRT + 运行时；步骤分诊断 → tie-aware portfolio |
| 新增 | SGDG、PIT、PRT、AEH、VFCS、benchmark audit、动作规律性指标 |
| 降级 | 双手角色图（P1，R3 之后）；风险头（可选）；放置锚点（叶子） |
| 砍 | ICR、L2L、全孪生、自由仿真、运行时 MPC/RL、布料/拉链/透明全物理、每任务 LoRA、WMA 主路径 |

---

## 1. 事实核对（2026-10-27）

### 1.1 赛事身份与规则

| 事项 | 事实 | 来源 |
|---|---|---|
| 赛事 | UniBot 世界挑战赛，G1 + Dex1，32 桌面任务 | [S1] |
| 赛道 | 仅通才多任务；单任务调试不计分 | [S2][S3] |
| 每任务 | 10 次；5 类泛化各 2 次（位置/干扰物/背景/未见物品/人扰） | [S2][S3] |
| 排名 | 总平均成功率 → 总平均步骤分 → 提交日期 | [S2][S3] |
| 时限 | 单次 180s，超时失败 | [S2][S3] |
| 模型 | 单模型，不得混用；类型不限 | [S2][S3] |
| 部署 | 选手自部署，官方远程 API | [S2][S3] |
| 提交 | `metadata` + `get_action` + `reset`；token 双校验 | [S7] |

**评分算术**：

```text
总 episode = 32 × 10 = 320
单任务权重 = 1/32 = 3.125pp
单轴权重 = 2/10 = 20% = 64 episodes
单任务内分辨率 = 1/10 = 10%（任务内）
全局单 episode 分辨率 = 1/320 = 0.3125pp

S = (1/32) Σ_t (1/10) Σ_r 1[all steps completed]
P = (1/32) Σ_t (1/10) Σ_r Σ_i w_{t,i} 1[step i completed]
rank = lexicographic(S, P, submission_date)
```

### 1.2 数据规模与隐藏监督

- 32 个 HF 数据集，2026-10-14 最后更新；合计 **33,276 episodes / 18,282,246 frames / 169.28h / 30fps**（[S5][S6][S11]）。
- 每任务 969–1,533 episodes；四路相机 `head_stereo_left/right` + `wrist_left/right`，640×480；状态含双臂关节、EE base/torso 位姿、夹爪、下身、torso、D435；动作含 joint/EE；LeRobot v3.0。
- **192 个采集 session**：3–10 个/任务，2–6 个 robot ID，日期跨 **2026-02-05–2026-06-25**；最大 session 占比平均 **32.35%**，中位数 30.4%，最高 **51.5%**（T20 PaperCupStacking）。
- **5 条官方复述/任务**（共 160 条）：平均 pairwise Jaccard **0.404**；最低平均 0.246（T04 FruitSorting），最高 0.544（T01 HangCup）；最低单对 0.056（T23 StorePaddle）、0.062（T04）。
- **30/32 任务有 `human_1_note` + `human_4_note`**；T31 OrganizePencilCase、T32 SyringeWaterTransfer 为空；9 个任务缺 `unseen_object_3`（T08/T09/T15/T16/T19/T29/T30/T31/T32）。
- **步骤分布**：11 个 2 步（50/50）、14 个 3 步（30/30/40）、5 个 4 步（25×4）、2 个 5 步（20×5）；所有 `score_steps` 总分归一为 100。
- **session 视觉偏移代理**：以 `head_stereo_left` 图像均值为特征，between-session / within-session std 比值中位数 **2.03**，均值 2.23；高偏移 T05 7.46、T28 4.48、T01 4.00、T17 3.72、T11 3.54、T14 3.48；低偏移 T09 0.46、T30 0.64、T16 0.72、T25 0.83、T12 0.92。**注意：这是粗代理，不是正式 domain distance；高比值可能来自光照/背景/相机/日期，不能直接等同于官方轴。**

**数据质量注意**：

- `meta/episodes/*.parquet` 的 `tasks` 字段在 31 个数据集是 `list<string>`，在 `PlugCharger` 是单个 `string`；naive loader 会取到首字符。必须做 schema 兼容。
- `meta/episodes` 没有 axis 标签；5 轴只能从 `info.json` 的 `generalization` 备注和官方规则推断。
- `task_id` 形如 `G1_Dex1_HangCup_8520_20260506_episode_0002`，编码任务/session/日期；这是本轮最关键的免费标签。

### 1.3 接口与 chunk 合同

| 项 | 事实 | 设计含义 |
|---|---|---|
| 观测 | 4×RGB、双臂关节/EE、夹爪、下身、language | 可用腕部相机做接触/位姿验证 |
| 叠帧 | `obs_delta_indices` 自定义 | 谓词可用短历史；BT 状态可维护 |
| 缩放 | `image_resize` 自定义 | 降延迟的关键 |
| 动作 | joint 或 ee 互斥 | 推荐 ee（放置/恢复）或 joint（平滑）；二选一 |
| chunk | 固定 `action_chunk_size`；整块执行 | BT tick = chunk 边界；AEH 只能改“块内执行哪些动作” |
| reset | 每 episode 一次 | BT/AEH 状态必须清空；per-connection 隔离 |
| language | 单字符串、全程不变 | 任务识别一次；5 复述匹配 |
| token | `metadata.token` + `meta.token` | 双处校验 |
| 端口 | N 个连续 8765..8765+N−1；每端口独立状态 | 多进程或共享后端 + 分发；不能全局单例 |

**README §6 的隐性指标（原文要点）**：评测期间逐步调用策略，记录每次 `get_action` 的延迟和内容；建议保持交互延迟平滑稳定、返回结果没有不必要的异常；组委会在评估结果可信度时可能结合每步延迟及其波动性、返回动作的统计规律性，并可能随结果展示（[S7] §6）。

**含义**：成功率和步骤分之外，还有“延迟稳定性 + 动作规律性”的可信度维度。任何测试时采样/自适应计算都必须控制 p99 和抖动，否则可能赢了成功率、输了可信度。

### 1.4 榜单/运行记录仍是占位

- `leaderboard_data.json`：`generated_from: "gen_leaderboard.py"`；8 模型 ×32 任务 = 256 条；`generated_at` 为 None（[S8]）。
- 8 个占位模型：MolmoAct2 29.7/39.0、WALL-OSS-0.5 28.5/38.9、DreamZero 27.9/37.9、Spirit-v1.5 25.9/34.4、DM0 23.5/31.7、PI-0.5 22.8/30.6、GigaBrain-0 22.6/29.5、GR00T N1.5 20.5/28.1。
- 榜单页/首页仍“即将发布”；详情页“测试视频占位”；`runs.html` 256/256（[S8][S9]）。
- 结论：**29.7% 是 seeded demo，不是真实头部**；只能当难度先验，不能用来推断哪个轴最弱/哪队最强。

### 1.5 本轮新增的十四条外部证据

| 证据 | 关键结论 | 对 UniBot 的含义 | 来源 |
|---|---|---|---|
| 动作块稳定性 | 12 任务/3 基准；稳定状态稀少，误差放大常见；闭环重规划很少把开环放大转成可信收缩；建议扰动/树覆盖训练 | 运行时 BT 不够；训练侧要补恢复覆盖 | [S36] |
| 自适应执行视界 | 视界先升后降；chunk 内动作 attend 固定 VL token；首尾动作 token 是锚点；动作自注意力可估可预测极限；AutoHorizon 测试时、开销可忽略 | 固定 chunk 内只执行可靠前缀 | [S37] |
| VLA-Corrector | latent-space vision monitor 检测视觉动态偏差；事件触发截断 + online gradient guidance；不改 backbone 权重 | 与 AEH 互补；可做“漂移触发重规划” | [S38] |
| RobustVLA | 17 种扰动/4 模态；动作最脆弱；视觉鲁棒不自动迁移；对最坏动作噪声做离线鲁棒优化 | 动作噪声鲁棒优化不需要新数据 | [S39] |
| RePO-VLA | 成功-only 模仿缺少恢复监督；恢复段初始化 + 进度价值；对抗成功率 20→75% | 恢复可以训练，不必只靠运行时 | [S40] |
| LIBERO-Para | 7 个 0.6B–7.5B VLA；复述下降 22–52pp；物体级词汇替换是主因 | 5 条复述是独立可训练轴 | [S41] |
| IndustrialVLA-Bench | 6 系统 clean 只差 1.58 分；鲁棒性/复述摘要跨度 14.62/31.08 分 | 干净能力饱和，鲁棒性区分模型 | [S42] |
| 基准审计 | 四种失效模式：shortcut、显著性、渐进过拟合、数据源依赖；0.09B 无语言 probe 接近 LIBERO SOTA；多数增益不显著 | 评测必须配对/留出/审计 | [S43] |
| VeriVLA | 两样本触发（chunk 内时序变化 + 跨样本方差）+ JEPA latent WM 排序；完成 50.8→65.5%；+326ms/4090 | 验证有效，但延迟重；只取触发/排序思想 | [S44] |
| MG-Select | 用 masked reference 的 KL 选动作；无需额外训练/模块 | VFCS 的最便宜实现 | [S45] |
| RoboDojo | 42 sim + 18 real；5 个能力维度；sim-and-real 统一评测 | 评测维度化，不只看平均 | [S46] |
| ManipArena | 20 任务、10,812 轨迹、13.5M 帧、约 188h；in-domain/visual-shift/semantic-OOD 分层；子任务部分分；三级语言标注 | DGS-32 的分层/部分分/语言轴参考 | [S47] |
| CoRe | 推理时反事实重对齐；无需失败数据/微调；最高 +85pp；需物理/场景最小重对齐 | 不可逆任务慎用；可做可逆子集 L1 | [S48] |
| PACT-VLA | 用 pre-commit observation 选 chunk；FlowRes；4-step 延迟下 +15pp（vs RTC）；真机 60→82%；无独立 verifier | 若评测端有 pre-commit 观测，可替代 VFCS | [S49] |

### 1.6 事实/推断分界

| 事项 | 状态 |
|---|---|
| 32×10、5 轴×2、字典序、180s、单模型、API、N 端口、token | 已核实（手册/README） |
| 33,276 episodes / 169.28h / 4 相机 / 30fps / 192 sessions | 已核实（HF metadata 全量解析） |
| 5 条复述 / 60 条人扰备注（30 任务）/ 9 缺 unseen 备注 / 2–5 步 | 已核实（info.json + tasks.parquet） |
| 榜单 29.7% | 占位，非真实 |
| session 视觉偏移比值 | 粗代理，非正式 distance |
| 人扰轴更弱、恢复增益最大 | 假设，需调试槽证伪 |
| 官方 §6 可信度是否进入排名 | 未核实；只说“可能展示” |
| WLA-1.0-Base 是否已见 33k | 未核实；若已见，session 留出是弱 OOD |
| 评测端是否逐字使用 5 条复述 | 未核实 |
| `unseen_object_3` 是“缺失”还是“替换” | 未核实；备注多为“缺少 X” |
| N 的具体值、调试槽配额、320 条件是否固定 | 未核实 |

---

## 2. 痛点分析

### 2.1 P1 隐藏域偏移：192 个 session + 随机切分泄漏

**事实**：

- 32 任务共 192 个 session，3–10 个/任务；2–6 个 robot ID；日期跨 5 个月。
- 最大 session 占比平均 32.35%，T20 高达 51.5%——随机切分会让同一 session 的 episode 同时出现在 train/val，验证集与训练集同分布；T20 这种大 session 的泄漏尤其严重。
- 以图像均值为代理，between-session / within-session std 比值中位数 2.03，最高 7.46；说明采集域（光照/背景/相机/日期）确实有可见差异。

**为什么是痛点**：

- 官方 5 轴中的位置/背景/干扰物占 60%（3/5 轴），而随机 episode 切分几乎不制造这些 shift；本地验证会高估 OOD 能力。
- 12 个任务只有 4–5 个 session（2 个 4 session、10 个 5 session），T20 只有 3 个；随机切分尤其容易泄漏。
- 若底座 WLA-1.0-Base 已见过 33k，session 留出也不是“真 OOD”；但至少能测“微调是否记住采集域”。

**对策**：Regroup（§3.2）+ DGS-32 held-out-session（§5.2）。

### 2.2 P2 恢复不在训练分布

**事实**：

- 公开数据是成功演示；没有失败/恢复/状态重置片段（这与 [S39] 的观察一致）。
- [S36]：动作误差进入系统后放大常见，稳定状态稀少；闭环重规划很少把开环放大转成可信收缩；建议显式训练恢复。
- [S40]：成功-only 模仿缺少恢复监督；恢复段训练把对抗成功率从 20% 提到 75%。
- [S48]：推理时反事实重对齐可大幅恢复，但需要把机器人/场景拉回可行流形；不可逆任务风险高。

**为什么是痛点**：

- 官方人扰轴 20%，且是唯一动态轴；人扰发生在 chunk 中间时，BT 只能到边界才知道。
- 即使 BT 检测到失败，策略本身没有“回来”的技能；`Regrasp/Redo` 只是重复，不是恢复策略。
- 不可逆失败（倒药/插头/水/锁）一次就归零；恢复必须“先安全、再正确”。

**对策**：Recover（§3.4）的 L0→L3 阶梯；运行时 SURE-BT 保留。

### 2.3 P3 复述过拟合

**事实**：

- 每任务 5 条官方复述；平均 Jaccard 0.404，最低单对 0.056——不是简单同义替换。
- [S41]：7 个 VLA 在复述下一致下降 22–52pp；物体级词汇替换是主因，说明模型依赖表面匹配。
- [S42]：clean 只差 1.58 分，复述摘要跨度 31.08 分——复述是区分模型的强轴。

**为什么是痛点**：

- 官方未见物品轴可能改变物体指称/属性；语言 grounding 不是“附属能力”。
- 单条指令训练会让模型记住固定句式；测试换一种说法就掉。
- 但 5 条复述都在公开数据里，若不利用，等于把免费监督扔掉。

**对策**：Rephrase（§3.3）+ held-out-paraphrase（§5.2）。

### 2.4 P4 固定 chunk 开环

**事实**：

- API 的 `action_chunk_size` 固定；评测端顺序执行完整 chunk 才再次调用。
- [S36]：动作误差放大常见；[S37]：执行视界先升后降，chunk 内动作 attend 固定 VL token；[S38]：VLA-Corrector 用 latent monitor 检测漂移并截断。
- 官方 §6 还记录每步延迟/波动/动作规律性。

**为什么是痛点**：

- 人类干扰/物体滑落/接触误差发生在 chunk 中间时，机器人会继续执行过期动作。
- 单纯减小 chunk 会增加推理频率和延迟；单纯增大 chunk 会放大开环误差。
- 测试时采样（K>1）会提高延迟和抖动，可能触发可信度问题。

**对策**：AEH（§4.2）+ VFCS（§4.3）+ 安全端点；只在关键状态采样。

### 2.5 P5 评测噪声/字典序/shortcut

**事实**：

- 320 episodes；p≈0.3 时 SE=2.56pp；单任务 10 次 SE=14.5pp；单轴 64 次 SE=5.73pp。
- 排名字典序：成功率第一，步骤分只在并列时用；提交日期再 tie-break。
- [S43]：四种失效模式；0.09B 无语言 probe 接近 LIBERO SOTA；多数报告增益不显著。
- 榜单仍是占位。

**为什么是痛点**：

- +3pp 可能只是噪声；单任务 +10pp 完全不可信。
- 头部若落在 1–2 SE 内，成功率可能完全并列；步骤分以 0.06–0.16pp/单 episode 的粒度决定名次。
- 如果基准可被 scene-only shortcut 解，语言/复述的投入可能打水漂；如果数据源泄漏，本地涨点不代表官方涨点。

**对策**：DGS-32 的配对/分层/功效/审计（§5）；tie-aware portfolio（§5.7）。

### 2.6 P6 spec gap/数据质量

**事实**：

- 9 个任务缺 `unseen_object_3`；T31/T32 没有任何 generalization 备注。
- 步骤 2–5 不等；2 步任务每步 50 分，5 步任务每步 20 分。
- `tasks` 字段 schema 在 PlugCharger 是 string，其余是 list。
- `meta/episodes` 无 axis 标签；官方 5 轴只能推断。

**为什么是痛点**：

- 缺失备注的任务无法直接构造人扰/未见物品脚本；若硬套相似任务，可能过拟合。
- 步骤分 tie-break 的杠杆因任务而异；2 步任务粗，4/5 步任务细。
- schema 不一致会让数据管线静默出错（例如只取到 “P”）。

**对策**：兜底脚本 + inferred 标记；schema 兼容层；不把备注当测试泄漏；DGS-32 只对“有备注”的任务做严格人扰验证，其余用随机扰动。

### 2.7 痛点优先级矩阵

| 痛点 | 分数影响 | 训练可解 | 推理可解 | 评测可解 | 本轮优先级 |
|---|---:|---|---|---|---|
| P1 域偏移 | 高（60%） | 是（Regroup） | 部分（增强） | 是（session 留出） | P0 |
| P2 恢复 | 高（20%+） | 是（Recover） | 是（BT/CoRe） | 是（扰动留出） | P0 |
| P3 复述 | 中（20%） | 是（Rephrase） | 是（canonical） | 是（复述留出） | P0 |
| P4 开环 chunk | 中高 | 部分（鲁棒训练） | 是（AEH/VFCS） | 是（延迟/抖动） | P1 |
| P5 评测噪声 | 高（结论） | 否 | 否 | 是（DGS-32） | P0（元） |
| P6 spec gap | 中 | 部分 | 部分 | 是（兜底） | P1 |

---

## 3. R3-VLA：方法

### 3.1 总览

```text
官方 33k episodes
  ├─ task_id → session/date ──► Regroup：两级平衡采样 + held-out session
  ├─ tasks 字段 → 5 复述 ─────► Rephrase：dropout + 一致性 + 留一复述
  └─ info.json → 人扰备注 ────► Recover：L0 动作噪声 → L1 推理时 → L2 sim → L3 真机
                                      │
                                      ▼
                          WLA-1.0-Base（唯一 checkpoint）
                                      │
                     ┌────────────────┴────────────────┐
                     ▼                                 ▼
              AEH + VFCS + SURE-BT                 DGS-32 评测
              （chunk 合同/恢复）                  （session/复述/扰动留出）
```

### 3.2 Regroup：session-grouped 域泛化

**数据解析**：

- `task_id = G1_Dex1_<Task>_<session>_<YYYYMMDD>_episode_<idx>`；session key 用 `<Task>_<session>_<date>`。
- 每个任务 3–10 个 session；不需要额外标注。
- 兼容 `tasks` 字段的 list/string 两种 schema。

**切分**：

- 主协议：`GroupKFold` by session，按任务分层；每个任务 5 折（≥5 sessions）或 leave-one-session-out（3–4 sessions）。
- 保证：同一 session 不跨 train/val；每个 held-out fold 至少覆盖所有任务的一个 session。
- 对照：随机 episode 切分（Round 8 的 SMB-320 方式）作为 in-domain 参考；报告 `held-out-session gap = in-domain - held-out`。

**采样**：

- 两级采样：任务均匀 → session 均匀 → episode 均匀。
- 对最大 session 降权：权重 ∝ `1/sqrt(n_session)` 或温度采样；避免 T20 的 51.5% 主导。
- 消融：uniform / inverse-frequency / sqrt-inverse / group DRO。

**正则**：

- 主路径：平衡采样 + 最差 session checkpoint 选择（max mean, tie-break worst-session）。
- 消融：Group DRO（softmax 权重，温度 τ）、V-REx（方差惩罚）、IRM（可能不稳定）。
- 不对任务分类头做 domain adversarial（6B 模型 + 小数据，风险高）。

**增强**：

- 背景/光照/相机小扰动、随机裁剪/缩放、色彩 jitter。
- **任务安全**：颜色排序/颜色匹配任务（T04/T06/T21/T27 等）不能改物体颜色；透明/反光物体不做极端亮度。
- 一致性：同一观测的 clean/augmented 版本，动作分布 KL/L2 惩罚（权重小，0.05–0.1）。

**验证**：

- held-out-session success（主）、worst-session success、in-domain success。
- 训练曲线按 session 分组记录，避免被大 session 掩盖。

### 3.3 Rephrase：复述不变性

**数据**：

- `meta/tasks.parquet` / episodes 的 `tasks` 字段含 5 条英文复述（`@` 分隔）。
- 每条样本随机抽一条复述；同一 epoch 内不重复使用同一复述（可选）。
- 任务 canonical 文本用 `en_desc`；5 条复述作为增广。

**训练**：

- **Paraphrase dropout**：以概率 p（0.3–0.5）把指令替换为同任务另一条复述或 canonical 描述。
- **一致性损失**：对同一 `(o, a)`，用两条复述 `l_i, l_j` 前向，惩罚动作分布差异：
  - flow 模型：同一 noise/time 的预测速度 L2；
  - 离散动作 token：对称 KL。
  - 权重 λ_p=0.1–0.3；只对动作头，不对视觉 backbone。
- **规则增广**：从 5 条复述挖同义词/句式模板（place↔put、cup↔mug、insert↔plug 等），做替换/重排；不改变物体身份/颜色/数量；不用外部 LLM。
- **不要**用外部复述数据或在线 LLM；单模型合规 + 外部数据规则不明。

**推理**：

- **Canonicalization**（默认）：把输入指令与 160 条复述/32 条 canonical 描述做规范化 token 匹配，命中则用 canonical 文本；零额外延迟。
- **Marginalization**（可选）：对 top-2 匹配复述各前向一次，动作平均；延迟 2×，只在 p99 允许时用。
- **Fallback**：匹配失败则用原指令；不要强行映射到错误任务。

**验证**：

- Leave-one-paraphrase-out：每任务训练 4 条、测试 1 条；5 折；报告 average/worst。
- 同时报告 canonical success，防止“复述涨、canonical 掉”。

### 3.4 Recover：扰动恢复训练

**3.4.1 官方备注解析**

30 个任务有 `human_1_note`（某步前扰动）和 `human_4_note`（某步后撤销/再扰动）。人工建表（30×2）：

| 字段 | 示例（T10 PlugCharger） | 用途 |
|---|---|---|
| phase | 抓插头前 / 插入后 | 决定注入时机 |
| target | 插头 / 插排 | 决定扰动对象 |
| type | 平移 / 撤销 / 遮挡 | 决定恢复算子 |
| recovery goal | 重新对准 / 重抓 / 重插 | 训练标签 |

归类：

1. **目标平移**：抓取前把目标/水果/积木/杯子平移。
2. **容器/夹具平移**：移动盘子、架子、底座、网口、插排、盒子。
3. **步骤撤销**：完成后再撤销（盖回瓶盖、拉开拉链、翻开毛巾、拿走第二个碗、拔起插头）。
4. **动态遮挡/追加**：手进入工作区、把网线另一头也插上、传送带物品临近。
5. **姿态/旋转**：把物体转一个角度/放倒。

**3.4.2 四级恢复阶梯**

| 级别 | 方法 | 需要 | 成本 | 适用 |
|---|---|---|---|---|
| L0 | 动作噪声鲁棒优化（[S39]） | 官方 33k | 低 | 所有任务；先做 |
| L1 | 推理时恢复（SURE-BT + 两样本触发/CoRe） | 无训练 | 低 | 可逆失败；人扰 |
| L2 | 仿真扰动 rollouts + RePO 式恢复段训练（[S40]） | sim/paired real-to-sim | 中 | 选 5–8 个任务 |
| L3 | 真机调试槽恢复数据 | 调试槽 | 高 | 最后一公里 |

**L0 细节**：

- 对每个 clean trajectory 的 action target 加最坏情况噪声 `δ`（最大化 flow-matching loss）或课程高斯噪声；训练模型去噪。
- 噪声尺度：动作范围的 1%→5%；不要一开始就大噪声，避免破坏 clean 能力。
- 数据混合：clean:noisy = 7:3；每 epoch 重新采样噪声。
- 这是最便宜的“见过偏差”方式，不需要新状态/新数据。

**L1 细节**：

- SURE-BT 的 `Relocalize/Regrasp/Reanchor/Redo/Rewind/WaitClear/Nudge/Abort` 保留。
- 两样本触发：同一观测采两个 chunk，测 within-chunk temporal variation + cross-sample variance；高方差 → `verify/careful` 或 VFCS。
- CoRe 式反事实重对齐只用于可逆状态（物体可被安全推回/机器人可回撤）；不可逆任务（倒药/注射/锁）禁用。

**L2 细节**：

- 选 5–8 个任务：T10 插头、T19 拉链、T27 堆碗、T01 挂杯、T23 收纳球拍、T05 拔网线、T31 铅笔盒、T32 注射器。
- 用 paired real-to-sim 或简单 tabletop sim；按官方备注的 phase/target 注入扰动。
- 用当前策略 + 脚本恢复采集 recovery rollouts；标注成功/恢复/失败。
- RePO 式：切恢复段、重置历史、进度价值；或简化成 `(adverse state, instruction) -> recovery action` 的监督。
- 课程：小噪声 → 平移 → 撤销 → 遮挡；每一步 gate 在 in-domain 回归 <1pp。

**L3 细节**：

- 调试槽每周 1 次；选 2–3 个任务，每次 20–30 episodes，采集恢复数据。
- 只做“可逆 + 高价值”任务；不可逆任务用 L0/L1，不冒险。
- 数据量小，用 LoRA/低学习率；不要覆盖 clean 能力。

**3.4.3 恢复评估**

- Held-out perturbation：训练用 human_1，测试 human_4（再交换）；或训练用随机平移，测试官方备注。
- 指标：recovery rate、time-to-recovery、irreversible failure rate、in-domain success。
- 门控：人扰轴 +5–10pp；不可逆失败不增加；in-domain 回归 <1pp。

### 3.5 训练配方与损失

```text
L = L_flow
  + λ_s * L_session      # 可选：group DRO/V-REx；主路径用采样，λ_s=0
  + λ_p * L_para         # 复述一致性，0.1–0.3
  + λ_r * L_recover      # 扰动/恢复，0.1–0.3
  + λ_smooth * L_smooth  # 动作平滑/规律性，0.01–0.05
```

**阶段**：

| 阶段 | 数据 | 目标 | 产出 | Gate |
|---|---|---|---|---|
| Stage 0 | 官方 33k，随机切分 | 复现 baseline | B0 | 无 NaN；p99 达标 |
| Stage 1 | session-grouped | Regroup | R1 | held-out session +2pp，in-domain 回归 <1pp |
| Stage 2 | + 5 复述 | Rephrase | R2 | held-out paraphrase +2pp，canonical 回归 <1pp |
| Stage 3 | + 动作噪声 | Recover L0 | R3 | 扰动条件 +2pp，clean 回归 <1pp |
| Stage 4 | + sim/真机恢复 | Recover L2/L3 | R4 | 人扰轴 +5pp，不可逆失败不增 |
| Stage 5 | + AEH/VFCS | 推理插件 | R5 | 成功率 +2pp，p99/jitter 达标 |

**资源估算**：

- 6B 模型；全参微调 8×H100/H200，约 1–2 周；LoRA/QLoRA 1–2×A100 80GB，约 3–5 天。
- 33k episodes × 4 相机；建议预解码/缩放缓存（240×320 或 256×256），bf16，gradient checkpointing。
- 数据管线：兼容 `tasks` list/string；按 session 分组；避免随机 shuffle 打散 session 统计。
- 最小可行：1 人 ×6 周，LoRA + 1×A100 + 1 个调试槽/周；完整：2 人 ×6 周，8×H100 + 2 个调试槽。

### 3.6 单模型合规矩阵

| 组件 | 类型 | 是否学习 | 合规说明 |
|---|---|---|---|
| WLA-1.0-Base | 唯一 checkpoint | 是 | 主体 |
| Regroup 采样 | 数据代码 | 否 | 离线 |
| Rephrase 一致性 | 训练损失 | 是（同 checkpoint） | 离线 |
| Recover L0/L2/L3 | 训练/微调 | 是（同 checkpoint） | 离线 |
| AEH 头 | 同 backbone 辅助头 | 是 | 共享 backbone |
| VFCS | 同模型内部置信/采样 | 否（无新模型） | 无外部 verifier |
| SURE-BT | 确定性代码 | 否 | 可审计 |
| DGS-32 | 评测 | 否 | 离线 |
| 外部 LLM/VLM/检测器 | 默认不用 | — | 需披露/询问 |
| 外部数据 | 默认 OFF | — | 只用官方 33k |

---

## 4. 推理端：SURE-BT + AEH + VFCS

### 4.1 SURE-BT 保留

第 8 轮的 Chunk-Synchronous BT 继续作为运行时骨架：

- tick 周期 = `action_chunk_size / 30` 秒；
- 谓词连续 N 帧 + 几何/接触校验才推进；
- 每个 chunk 末步是安全端点；
- BT 在边界选择 `continue / verify / recover / replan / abort`；
- 恢复算子库、双手角色图、护理级别保留；
- per-connection/per-episode 状态隔离。

本轮新增的是 **chunk policy**：AEH 决定“块内信多少步”，VFCS 决定“关键状态选哪个块”，BT 决定“边界怎么处理”。

### 4.2 AEH：可靠前缀 + 安全端点

**问题**：API 要求返回固定 T_a 个动作，评测端整块执行；但模型对 chunk 后段的预测可能不可靠（[S37]：视界先升后降；chunk 内动作 attend 固定 VL token）。

**方法**：

1. 取动作自注意力/动作 token 的 entropy 或 terminal-anchor 注意力质量；没有 attention 时，用两样本方差/轻量 horizon head。
2. 估计可靠前缀 `L*`：`L* = argmax_t (h_t - h_{t-1})` 或阈值截断；用 held-out session/扰动校准。
3. 执行 `a_1..a_{L*}`；剩余 `T_a - L*` 步填安全端点：
   - 保持当前 joint/EE 目标（repeat last safe action）；
   - 或回撤到预放置/retreat pose；
   - 用插值避免从 `a_{L*}` 到安全端点的跳变。
4. 下一个 chunk 边界重观测、重规划。
5. BT 若看到 `L*` 很短/置信低，标记 `verify` 或 `careful`。

**安全端点选择**：

- 自由空间运输：保持/减速；
- 接近接触：回撤 1–2cm；
- 抓取中：保持夹爪闭合 + 当前位姿；
- 放置/插入前：预放置姿态；
- 不可逆动作（倒/插/锁）：不要用“继续推”作为安全端点；用保持/回撤。

**代价**：最多 `(T_a - L*)/30` 秒的保持/回撤；T_a=8 时最多 267ms，180s 预算可吸收。若 time-to-success 恶化 >10%，降低 AEH 使用频率或增大 T_a。

### 4.3 VFCS：verifier-free 选块

**触发**（只在关键状态）：

- 接近接触/插入/放置；
- 人扰后备；
- AEH 的 `L*` 很短；
- 两样本方差高；
- 谓词置信低/接近阈值。

**候选**：

- K=2 个 chunk（不同 noise seed）；可选 1 个 deterministic/mean chunk。
- 同一 forward 里 batch 两个候选，降低延迟。

**评分**：

- **MG-Select**：用 masked state/language 的 reference 分布，算每个候选的 KL；选低 KL（更自信）。无需额外训练/模块。
- **两样本方差**：选与另一样本更一致/更低方差的块；或高方差时触发更多候选。
- **PACT/FlowRes**：仅当评测端有 pre-commit observation（能在 chunk commit 前拿到更新观测）；否则不用。
- **Regularity-aware tie-break**：分数差在 ε 内时，选 jerk/高频能量更低、与上一块更连续的候选。

**延迟/规律性**：

- K=2 约 2× 推理；p99 必须 < chunk 时长；否则 K=1。
- 只在关键状态触发；不要每步采样。
- 记录 p50/p95/p99、latency IQR、动作 jerk、离群率；jitter 增加 >10% 就砍。
- 官方 §6 可能展示这些指标；不要让 VFCS 把动作变得“更随机”。

### 4.4 延迟/规律性预算

| T_a | 块时长 @30Hz | 建议 | 备注 |
|---:|---:|---|---|
| 4 | 133ms | 只在模型很快时 | p99<133ms 很难 |
| 8 | 267ms | 默认 | AEH 最多保持 267ms |
| 16 | 533ms | 延迟不达标时 | 开环盲区更大，AEH 更重要 |

**监控指标**：

- p50/p95/p99 latency；
- latency std/IQR；
- 动作 jerk（mean squared jerk）和高频能量；
- 动作离群率（>3σ）、NaN/Inf；
- chunk 间不连续（第一帧与上一块末帧的差）；
- timeout rate。

### 4.5 与 API chunk 的兼容性

- API 仍然收到完整 `(T_a, ...)`；AEH 只是把后段填成安全动作，不改变形状。
- 评测端仍然整块执行；BT 仍然只在边界 tick。
- VFCS 只改“选哪个块”，不改执行协议。
- `reset()` 清空 AEH 的 horizon 状态、VFCS 的缓存、BT 的信念/角色/计时。
- N 端口并发：每个连接独立 policy 实例/状态；共享后端时注意批处理不能改变单连接动作（避免跨连接污染）。

---

## 5. DGS-32：评测协议

### 5.1 设计原则

1. **三重留出**：session（域）、paraphrase（语言）、perturbation（恢复）。
2. **配对**：同一组 320 条件跑所有变体，报告配对差值。
3. **分层**：按任务/轴/难度分层报告，不只报平均。
4. **审计**：四种失效模式各一个诊断（[S43]）。
5. **可证伪**：预注册 +5pp；CI 跨 0 不上线。
6. **不冒充官方**：DGS-32 是本地代理，不是官方榜单。

### 5.2 三重留出

| 留出 | 构造 | 度量 | 对应官方轴 |
|---|---|---|---|
| Held-out-session | 按 session 分组 5 折/留一 | in-domain vs held-out gap | 背景/位置/干扰物（代理） |
| Held-out-paraphrase | 每任务留 1 条复述 | canonical vs held-out gap | 未见物品/语言（代理） |
| Held-out-perturbation | 留 human_1 或 human_4 一条 | clean vs perturbed gap | 人扰 |
| In-domain | 随机 episode 切分 | 拟合上限 | 对照 |

**注意**：

- Session 不是官方 axis 标签；它只是免费域代理。用视觉偏移统计/调试槽验证相关性。
- 若底座已见 33k，held-out-session 是“弱 OOD”；官方真机仍是唯一真 OOD。
- 复述留出只测语言；视觉/动作不变，隔离性好。
- 扰动留出只对有备注的 30 个任务严格；T31/T32 用推断脚本，标 `inferred`。

### 5.3 32×10 矩阵

| 轴 | 条件数 | 构造 | 备注 |
|---|---:|---|---|
| 位置 | 2/任务 | 目标/容器平移 ±5–15cm；从演示分布采样 | 与 session 留出配合 |
| 干扰物 | 2/任务 | 插入 1–3 个其他任务物体；不遮目标 | 不要引入未见过类别 |
| 背景 | 2/任务 | 桌布颜色/纹理/光照；held-out session 优先 | 颜色任务避免改物体色 |
| 未见物品 | 2/任务 | 同类不同颜色/形状/材质；从其他任务/资产借 | 9 个任务缺备注，用兜底 |
| 人扰 | 2/任务 | 按官方 human_1/human_4 回放；T31/T32 推断 | 不把备注当测试泄漏 |

- 总 320 条件；同一组条件跑所有变体；配对种子。
- 离线用 2.5D 图像编辑/回放；物理接触（拉链/倾倒/插入）用少量真机调试槽验证。
- 不把 DGS-32 当真实榜单；它只用于相对比较和失败挖掘。

### 5.4 指标套件

| 指标 | 定义 | 用途 |
|---|---|---|
| Success | 全步骤完成率 | 主指标 |
| Step score | 官方加权部分分 | tie-break/诊断 |
| Axis success | 每轴 64 次 | 分轴诊断 |
| Recovery rate | 扰动后恢复并完成的比例 | 恢复能力 |
| Time-to-recovery | 扰动到恢复完成的时长 | 恢复效率 |
| Intervention rate | BT 干预/恢复次数 per episode | 过约束检测 |
| Predicate F1 | 谓词 vs 人工/演示标签 | BT 可靠性 |
| Timeout rate | 超时比例 | 失败模式 |
| p99 latency | `get_action` 延迟 | chunk 合同/可信度 |
| Latency variability | std/IQR | 官方 §6 |
| Action jitter | mean squared jerk/高频能量 | 官方 §6 |
| Outlier rate | >3σ、NaN/Inf | 官方 §6 |
| Domain gap | in-domain - held-out-session | 域泛化 |
| Paraphrase gap | canonical - held-out-paraphrase | 语言泛化 |
| Shortcut probe gap | 场景-only vs 语言条件 | 基准审计 |

### 5.5 统计协议

- **二项 CI**：Wilson 95%；320 次、p≈0.3 时 ±5.0pp。
- **配对**：同一条件跑 A/B；McNemar；差值 SE ≈ sqrt(d/320)；d=0.15 → 2.17pp。
- **分层 bootstrap**：按 task/session 重采样；报告 95% CI。
- **预注册**：目标 +5pp；MDE 计算；不要事后改目标。
- **多重比较**：Holm/BH；轴级/任务级分开。
- **序列检验**：若早停，用 alpha spending；不要偷看多次。
- **任务级**：10 次/任务，分辨率 10%；用分层贝叶斯平滑，不因单任务 +10pp 下结论。
- **报告**：均值 + CI + 配对差值 + 失败模式分布；不只报一个数。

### 5.6 基准审计

| 失效模式 | 诊断 | 在 UniBot 上的做法 | 如果失败 |
|---|---|---|---|
| Shortcut solvability | 场景-only 小模型 vs 语言条件模型 | 0.09B/ResNet-18 probe，无语言；held-out session | 若 gap 小，语言投入降级，转向场景/任务多样性 |
| Lack of statistical significance | 配对检验/CI | 320 次配对；McNemar；预注册 +5pp | 不显著 → 不上线 |
| Creeping overfitting | 留出 session/复述/扰动 | 不调 held-out；限制提交次数 | 若 held-out 掉，回退 |
| Data-source dependence | 按 robot/date 留出 | 用 2–6 个 robot ID/5 个月日期做 leave-one-robot/date-out | 若 gap 大，Regroup 加权 |

**Shortcut probe 细节**：

- 训练一个小模型（如 ResNet-18/0.09B）只用场景图像、不用语言；同一 session-grouped 切分。
- 若其 held-out session 成功率接近语言条件模型，说明任务可由场景 shortcut 解；语言/复述的边际收益低，应把预算转向场景多样性/恢复。
- 这不是“负面结果”，而是**评测贡献**：告诉社区 UniBot 的 32 任务是否真的需要语言。

### 5.7 tie-break 分析

**步骤分杠杆**：

| 步数 | 任务数 | 权重 | 全任务一步（10 次）对总分 | 单 episode 对总分 |
|---:|---:|---|---:|---:|
| 2 | 11 | 50/50 | 1.5625pp | 0.15625pp |
| 3 | 14 | 30/30/40 | 0.9375/0.9375/1.25pp | 0.09375/0.09375/0.125pp |
| 4 | 5 | 25×4 | 0.78125pp | 0.078125pp |
| 5 | 2 | 20×5 | 0.625pp | 0.0625pp |

**tie 概率**：

- 二项模型、n=320、p=0.3：两队成功率完全相同的概率约 **3.44%**；p=0.2 约 3.94%；p=0.5 约 3.15%。
- 头部 5–8 队若落在 1–2 SE 内，至少一对 tie 的概率不可忽略（粗略 10–30%，取决于相关性）。
- 结论：**步骤分不是主目标，但在头部拥挤时是真实 tie-break；保留“步骤分保险”，不要为它牺牲成功率。**

**tie-aware portfolio**：

- 用几乎成功前沿 `flip_{t,k}` 找“差一步”的任务；
- 优先修 `flip` 大、`r_i`（可恢复性）高、步骤分杠杆高的任务；
- 2 步任务一步 50 分，适合“最后一步保险”；4/5 步任务分辨率细，适合逐步优化；
- 只在成功率 plateau 后做；任何导致成功率下降的步骤分优化都砍。

---

## 6. 实验设计

### 6.1 主实验

| ID | 配置 | 目的 |
|---|---|---|
| E0 | WLA-1.0-Base，随机切分，L=16 | 基线 |
| E1 | E0 + Regroup（session 平衡） | 域泛化 |
| E2 | E1 + Rephrase（dropout/一致性） | 语言泛化 |
| E3 | E2 + Recover L0（动作噪声） | 动作抗扰 |
| E4 | E3 + AEH | 可靠前缀 |
| E5 | E4 + VFCS（关键状态 K=2） | 测试时选块 |
| E6 | E5 + Recover L2/L3（sim/真机） | 恢复能力 |
| E7 | E6 + SURE-BT + DGS-32 | 完整系统 |
| E8 | Shortcut probe / 审计 | 评测有效性 |

### 6.2 消融

- 切分：随机 vs session-grouped；5 折 vs leave-one-session-out。
- 采样：uniform vs inverse-frequency vs sqrt-inverse vs group DRO。
- 复述：无 vs dropout vs 一致性 vs canonicalization vs marginalization。
- 恢复：无 vs L0 vs L0+L1 vs L0+L1+L2 vs +L3。
- 噪声：1%/3%/5%；clean:noisy 比例。
- AEH：无 vs attention heuristic vs horizon head；阈值。
- 安全端点：保持 vs 回撤 vs 预放置；插值 on/off。
- VFCS：K=1/2/4；触发条件；regularity tie-break on/off。
- 护理级别：uniform vs irreversibility-weighted。
- BT：on/off；谓词迟滞 on/off；角色图 on/off。
- 损失权重：λ_p/λ_r/λ_smooth。

### 6.3 判定规则

| 门槛 | 条件 | 失败动作 |
|---|---|---|
| G1 | 基线复现；无 NaN；p99 < chunk | 先修工程 |
| G2 | held-out session +2–3pp；in-domain 回归 <1pp | 退回普通采样 |
| G3 | held-out paraphrase +2–3pp；canonical 回归 <1pp | 只保留 canonicalization |
| G4 | 人扰/扰动 +5pp；不可逆失败不增 | 停在 L0/L1 |
| G5 | AEH 接触/过冲失败 -20% 相对；time-to-success 不恶化 >10% | 关 AEH 或增大 T_a |
| G6 | VFCS +3pp；jitter <10%；p99 < chunk | 砍 VFCS |
| G7 | 总体 +5pp，95% CI >0；无轴回归 >3pp | 不上线 |
| G8 | 单模型/外部数据合规审计通过 | 移除风险项 |

### 6.4 六周计划

| 周 | 目标 | 交付 | Gate |
|---|---|---|---|
| W1 | 数据解析、session/复述切分、DGS-32 harness、E0 | 切分 + 基线 + 指标 | G1 |
| W2 | Regroup + Rephrase；E1/E2 | R2 checkpoint | G2/G3 |
| W3 | Recover L0 + AEH；E3/E4 | R3 + AEH | G4/G5 |
| W4 | VFCS + SURE-BT 集成；调试槽 #1；E5 | 运行时 v2 | G6 |
| W5 | Recover L2/L3 + DGS-32 全矩阵 + 审计；调试槽 #2；E6/E7/E8 | 评测报告 + 候选 | G7 |
| W6 | 修复/终版/合规/soak/提交 | 最终版 | G8/冻结 |

### 6.5 资源估算

| 配置 | GPU | 时间 | 人 |
|---|---|---|---|
| 最小可行（LoRA） | 1–2×A100 80GB | 3–5 天/阶段 | 1–2 |
| 完整（全参） | 8×H100/H200 | 1–2 周 | 2 |
| DGS-32 离线评测 | 1×A100/4090 | 2–3 天 | 1 |
| 真机调试 | — | 1 槽/周 | 1–2 |

---

## 7. 创新点清单

> 状态：押注=主线；高优先=强烈建议；试验=可选；支撑=评测/工程；降级=保留但非主回路；砍=不做。

### I1 R3-VLA：Regroup + Rephrase + Recover（押注｜新）

- **动机**：官方 5 轴里 60% 是视觉/场景 shift（位置/干扰物/背景），20% 是人扰，20% 是未见物品/语言；公开数据没有轴标签，但有 192 个 session、5 条复述、30 个任务的 60 条人扰备注。第 8 轮的运行时 BT 不能替代训练分布。
- **差异**：不是“再训一个更大的 VLA”，而是用官方数据自带的三种免费监督做**训练侧不变性**；不是“随机增强”，而是 session-grouped + 复述留出 + 官方扰动剧本；一个 checkpoint，无外部数据/模型。
- **可行性**：数据已在本地；解析脚本 1–2 天；LoRA 1–2×A100；6 周可完成最小闭环。
- **资源**：1–2 人 ×6 周；1–8 GPU；1 个调试槽/周。
- **步骤**：解析 session/复述/备注 → 三重切分 → baseline → SGDG → PIT → PRT → 评估。
- **风险**：session 混杂任务/物体；无 sim；复述只覆盖 5 条；备注过拟合。
- **状态**：主线。

#### I1a SGDG：Session-Grouped Domain Generalization（押注｜新）

- **动机**：192 sessions；最大 session 占比 51.5%；随机切分泄漏；官方位置/干扰物/背景轴 60%。
- **差异**：用真实采集 session 作域标签，而非合成域；两级平衡采样 + 最差 session checkpoint；group DRO 只作消融。
- **可行性**：`task_id` 直接解析；无需额外标注；1 人 ×1 周。
- **资源**：1 人 ×1 周；本地数据；无额外 GPU。
- **步骤**：解析 → GroupKFold → 平衡采样 → 训练 → held-out session/worst-session 评估。
- **风险**：session 与任务/物体混淆；group DRO 可能伤 in-domain。
- **状态**：主线。

#### I1b PIT：Paraphrase-Invariant Training（押注｜新）

- **动机**：5 条复述；平均 Jaccard 0.404；[S41] 22–52pp；[S42] 31.08 分跨度。
- **差异**：用官方 5 条 + 规则增广；paraphrase dropout + 一致性；测试时 canonicalization；不用外部 LLM。
- **可行性**：数据字段现成；1 人 ×3–5 天；一致性损失只加动作头。
- **资源**：1 人 ×3–5 天；1×A100/LoRA；无额外数据。
- **步骤**：解析 5 条 → dropout/一致性 → 留一复述 → canonicalization。
- **风险**：评测复述可能不在 5 条内；marginalization 延迟 5×；一致性可能伤 canonical。
- **状态**：主线。

#### I1c PRT：Perturbation-Recovery Training（押注｜升级 NRB）

- **动机**：SFT 只有成功；[S36][S39][S40]；人扰轴 20%。
- **差异**：官方人扰备注 → 扰动剧本；L0 动作噪声 → L1 推理时 → L2 sim → L3 真机；不是只做运行时 BT。
- **可行性**：L0 不需要新数据；L1 不需要训练；L2 需要 sim（gate）；L3 需要调试槽。
- **资源**：L0 1 人 ×1 周；L2 需 sim + 1–2 GPU；L3 需调试槽。
- **步骤**：备注建表 → L0 → L1 → L2/L3 → held-out perturbation。
- **风险**：无 sim；备注≠测试；不可逆失败；真机数据少。
- **状态**：主线（L0/L1 先做，L2/L3 门控）。

### I2 SURE-BT + AEH + VFCS（押注｜升级）

- **动机**：固定 chunk 开环；[S36][S37][S38]；官方 §6 延迟/规律性。
- **差异**：AEH 不截断 API，只把 chunk 后段填安全端点；VFCS 只用同一模型、K=2、关键状态、regularity-aware；无外部 verifier。
- **可行性**：推理插件；1–2 人 ×2 周；需要 attention 或轻量 head。
- **资源**：1–2 人 ×2 周；推理 GPU；attention/轻量 head。
- **步骤**：AEH heuristic → 校准 → VFCS → SURE-BT 集成 → 延迟/抖动 profiling。
- **风险**：horizon 误判；安全端点浪费时间；VFCS 延迟/抖动。
- **状态**：主线（运行时）。

### I3 DGS-32：三重留出评测 + 审计（支撑｜升级 SMB-320）

- **动机**：官方轴隐藏；随机切分泄漏；[S43] 四种失效模式；榜单占位。
- **差异**：session/复述/扰动三重留出；真实 session；配对/分层/CI；shortcut probe/data-source dependence。
- **可行性**：1 人 ×2 周；本地数据；无额外硬件。
- **资源**：1 人 ×2 周；本地数据；无额外硬件。
- **步骤**：切分 → 320 矩阵 → runner → 指标 → 统计 → 审计。
- **风险**：代理效度；sim-to-real；小样本。
- **状态**：支撑（但可作为对外贡献）。

### I4 双手角色图 + 支撑手稳定器（高优先｜保留第 8 轮）

- **动机**：约 14–16 任务双手；支撑手漂移是共性失败。
- **差异**：从演示挖 support/act 标签；BT `Parallel(Support, Act)` + 稳定器；角色可交换。
- **可行性**：演示统计；无需新数据；1 人 ×2 周。
- **资源**：1 人 ×2 周；演示统计；无额外 GPU。
- **步骤**：角色挖掘 → 角色图 → BT `Parallel(Support, Act)` → 支撑手稳定器 → T10/T19/T31 验证。
- **风险**：标签噪声；覆盖策略冲突；单模型合规。
- **状态**：高优先（R3 之后）。

### I5 几乎成功前沿 + tie-aware portfolio（高优先｜升级）

- **动机**：单任务 3.125pp；10 次/任务；步骤分 tie-break 分辨率 0.06–0.16pp。
- **差异**：步骤分当故障定位器；`drop/flip` 分配工程/调试槽；加入 tie 概率和步骤分杠杆。
- **可行性**：BT/评测日志即可；1 人 ×1 周。
- **资源**：1 人 ×1 周；BT/评测日志。
- **步骤**：日志 → `S_{t,k}/drop/flip` → tie 概率/步骤分杠杆 → 背包分配 → 调试槽验证。
- **风险**：小样本；过拟合调试条件；为步骤分牺牲成功率。
- **状态**：高优先（流程）。

### I6 谓词头 + 风险头（试验｜保留第 8 轮）

- **动机**：BT 的瓶颈是条件可靠性；失败检测可提前触发恢复。
- **差异**：辅助头共享 backbone；高精度/低误报；风险只触发 verify/careful，不直接 abort。
- **可行性**：演示相位标签；轻量头；1 ML 人 ×2–3 周。
- **资源**：1 ML 人 ×2–3 周；GPU；演示相位标签。
- **步骤**：标签 → 头 → 校准 → 接线 → 消融。
- **风险**：标签噪声；校准漂移；审计。
- **状态**：试验（G1/G5 门控）。

### I7 放置锚点/位姿迁移（保留｜降级为叶子）

- **动机**：终局放置仍是成功闸门；锚点/相对位姿提精度。
- **差异**：不再当主架构；作为 BT `Act(place)` 叶子/目标提供器。
- **可行性**：沿用第 7 轮；几何/锚点；无需新模型。
- **资源**：1 人 ×1 周维护；沿用第 7 轮代码。
- **步骤**：锚点提供器 → BT `Act(place)` 叶子 → 终局验证。
- **风险**：锚点误差；透明/反光；与恢复冲突。
- **状态**：保留，降级。

### I8 WLA-1.0-Base（保留）

- **动机**：官方 6B、Apache-2.0、约 2,500h、64 任务；单模型合规。
- **差异**：不改底座；LoRA/辅助头。
- **可行性**：官方权重可用；LoRA/辅助头；单模型合规。
- **资源**：1–8 GPU；见 §6.5。
- **步骤**：下载/复现 → LoRA → R3 训练 → 评测。
- **风险**：底座已见 33k；许可证/权重可用性；推理成本。
- **状态**：保留。

### I9 部署检查单（工程｜保留）

- **动机**：N 端口/状态隔离/延迟/token 是硬门槛。
- **差异**：不是研究点；是部署检查单。
- **可行性**：工程；1 人 ×1 周。
- **资源**：N 端口/4h soak；无额外 GPU。
- **步骤**：端口 → 状态隔离 → token → 图像缩放 → 4h soak → 日志。
- **风险**：并发/内存泄漏/断线；p99。
- **状态**：工程，不是研究点。

### I10 动作规律性/延迟感知推理（支撑｜新）

- **动机**：官方 §6 记录每步延迟/波动/动作统计规律性；可能随结果展示。
- **差异**：把 p99/latency IQR/jerk/离群率纳入 DGS-32 和部署门控；VFCS 只选平滑候选；避免每步采样。
- **可行性**：日志 + 轻量监控；1 人 ×3 天。
- **资源**：1 人 ×3 天；日志/监控。
- **步骤**：指标 → 监控 → VFCS tie-break → 门控。
- **风险**：过度平滑伤接触-rich；指标未进排名。
- **状态**：支撑。

### 已砍/降级

- ICR（重、延迟、增益不确定）→ 降级/移出主路径
- L2L 外部数据（规则不明）→ 暂停
- 全 32 任务高保真孪生 → 砍
- 自由仿真/运行时 MPC/仿真 RL → 砍
- 布料/拉链/透明全物理 → 砍
- 步骤分主目标 → 砍（只留 tie-break 保险）
- 每任务 LoRA/模型合并 → 砍
- WMA-0 主路径 → 砍（只在 L2 可选世界模型）

---

## 8. 风险、合规与开关

| 风险 | 概率 | 影响 | 缓解 | 停止条件 |
|---|---|---|---|---|
| session 混杂任务/物体 | 中 | 高 | 分层切分；最差 session；调试槽验证 | held-out 不涨 → 退回普通采样 |
| 底座已见 33k | 中 | 中 | 把 held-out 当“弱 OOD”；真机为准 | 若 gap 全为 0 → 只用调试槽 |
| 无 sim 做 PRT | 高 | 中 | L0/L1 先做；L2 门控 | 无 sim → 停在 L0/L1 |
| 备注过拟合 | 中 | 高 | 随机扰动混采；held-out 备注 | 随机扰动下降 → 调权重 |
| 复述覆盖不足 | 中 | 中 | 规则增广；canonicalization；held-out | held-out 不涨 → 只 canonicalize |
| AEH 误判 | 中 | 中 | 保守阈值；校准；time-to-success 门控 | 恶化 >10% → 关 |
| VFCS 延迟/抖动 | 高 | 高 | K=2；关键状态；regularity tie-break | p99 超 chunk 或 jitter >10% → 砍 |
| 单模型审计 | 中 | 高 | 同 checkpoint；无外部模型；披露 | 审计不过 → 去辅助头 |
| 统计噪声 | 高 | 中 | 配对/分层/CI/预注册 | CI 跨 0 → 不上线 |
| 榜单占位误导 | 高 | 中 | 不用 29.7% 做选择 | 真榜发布 → 重跑 |
| 数据 schema 不一致 | 中 | 低 | 兼容 list/string；校验 | 解析失败 → 修管线 |
| 外部数据违规 | 低 | 高 | 默认 OFF | 禁止 → 停 |
| 不可逆失败 | 中 | 高 | 护理级别；Abort；不激进恢复 | 事故增加 → 关 L1/L2 |

```yaml
policy:
  single_model: true
  auxiliary_heads: same_checkpoint
  planner: compiled_bt
  external_perception_models: false
  external_language_models: false
  external_lab_data: false
  session_grouped_training: true
  paraphrase_augmentation: official_plus_rules
  recovery_training: offline_noise_then_sim_then_real
  chunk_contract: fixed_Ta_safe_tail
  test_time_sampling: critical_states_only_K2
  action_regularity: monitored
  debug_slots_per_release: 1
```

---

## 9. 开放问题

1. 真实榜单何时发布？29.7% 是否只是 seeded demo？
2. WLA-1.0-Base 是否已见过这 33k？若已见，session 留出是弱 OOD。
3. 评测端是否逐字使用 5 条复述？还是新生成复述？
4. 人扰是真人还是机械臂？发生在固定相位还是随机？
5. `human_1_note`/`human_4_note` 的编号语义？是否就是测试脚本？
6. `unseen_object_3` 是“缺少”还是“替换”？9 个缺失任务官方怎么测？
7. 320 个测试条件是固定还是每次随机？能否拿到脚本？
8. 所有模型是否面对同一组 320 条件（可否配对）？
9. 步骤分是人工还是自动判定？失败步骤是否清零后续？
10. 官方 §6 的延迟/规律性是否进入排名，还是只展示？
11. 单模型边界：经典 CV/检测器/辅助头是否允许？
12. 外部数据/预训练权重是否允许？
13. 调试槽配额/成本？是否用同样的 10 次矩阵？
14. 计分跑次数/提交频率？早提交 tie-break 如何利用？
15. N 台机器人/N 端口？并发/延迟上限？
16. 截止日期/赛程？
17. `tasks` 字段 schema 不一致是 bug 还是有意？
18. AEH 的“保持/回撤”安全端点是否会被官方视为有效动作？会不会浪费时间？
19. VFCS 的采样抖动是否会影响官方可信度评价？
20. 官方是否允许在 chunk 内做“安全端点”而不是继续执行模型动作？

---

## 10. 来源（检索/核对日期 2026-10-27）

| 编号 | 来源 | URL | 用途 |
|---|---|---|---|
| S1 | UniBot 挑战赛任务页 | https://unibot.unitree.com/challenges.html | 32 任务、数据规模 |
| S2 | 参赛手册（中） | https://scnhkkqlu12w.feishu.cn/docx/Uz7OdFBcDoqP1dxgH62cHW1CnMh | 10 次/任务、5 轴×2、字典序、180s、单模型 |
| S3 | 参赛手册（英） | https://scnhkkqlu12w.feishu.cn/docx/ZNHIdaGx0oPOlBxNVxkcswqqnnh | 同上（英文核对） |
| S4 | 任务 info.json 示例 | https://unibot.unitree.com/tasks_v2/stack_bowls_three/info.json；https://unibot.unitree.com/tasks_v2/plug_charger/info.json；https://unibot.unitree.com/tasks_v2/disconnect_ethernet/info.json；https://unibot.unitree.com/tasks_v2/zip_up/info.json | 评分步骤、人扰备注 |
| S5 | HF collection | https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset | 32 数据集、更新时间 |
| S6 | HangCup 数据集 | https://huggingface.co/datasets/unitreerobotics/G1_Dex1_HangCup | 1,043 episodes/194,564 frames/30fps/4 相机 |
| S7 | 提交模板 | https://github.com/unitreerobotics/unibot_submission | 接口、chunk、token、reset、§6 可信度 |
| S8 | 排行榜 | https://unibot.unitree.com/leaderboard.html；https://unibot.unitree.com/leaderboard_data.json | 占位证据、29.7% |
| S9 | 运行记录 | https://unibot.unitree.com/runs.html | 256/256 占位 |
| S10 | 我的主页 | https://unibot.unitree.com/profile.html | 计分/不计分调试 |
| S11 | Kinetic Blocks 数据摘要 | https://www.kineticblocks.com/open-data/unitree-unibot-v1-challenge | 33,276 episodes/169h/811GB |
| S12 | WLA-1.0-Base | https://huggingface.co/unitreerobotics/UnifoLM-WLA-1.0-Base；https://github.com/unitreerobotics/unifolm-wla | 6B/Apache-2.0/2,500h/64 任务 |
| S36 | Measuring the Stability Assumption Behind Action Chunking | https://arxiv.org/abs/2610.01626 | 动作误差放大/闭环不收缩/扰动训练 |
| S37 | VLA Knows Its Limits: Adaptive Execution Horizons | https://arxiv.org/abs/2602.21445 | 执行视界峰值/动作自注意力/AutoHorizon |
| S38 | VLA-Corrector | https://arxiv.org/abs/2607.01804 | latent monitor/事件触发截断/自适应视界 |
| S39 | RobustVLA | https://arxiv.org/abs/2510.00037 | 17 扰动/动作最脆弱/动作噪声鲁棒优化 |
| S40 | RePO-VLA | https://arxiv.org/abs/2605.09410 | 恢复段训练/对抗成功率 20→75% |
| S41 | LIBERO-Para | https://arxiv.org/abs/2603.28301 | 复述 22–52pp/物体词汇替换/PRIDE |
| S42 | IndustrialVLA-Bench | https://arxiv.org/abs/2609.25562 | clean 1.58/鲁棒 14.62/复述 31.08 |
| S43 | What Are We Actually Benchmarking in Robot Manipulation? | https://arxiv.org/abs/2606.04233 | 四种失效模式/0.09B probe/显著性 |
| S44 | VeriVLA | https://arxiv.org/abs/2610.21985 | 两样本触发/JEPA latent WM/50.8→65.5%/+326ms |
| S45 | Verifier-free Test-Time Sampling (MG-Select) | https://arxiv.org/abs/2510.05681 | masked reference KL/无额外训练 |
| S46 | RoboDojo | https://arxiv.org/abs/2607.04434 | 42 sim + 18 real/5 能力维度 |
| S47 | ManipArena | https://arxiv.org/abs/2603.28545 | 20 任务/10,812 轨迹/188h/分层 OOD/子任务分 |
| S48 | Imagining Recovery (CoRe) | https://arxiv.org/abs/2608.14822 | 推理时反事实重对齐/最高 +85pp |
| S49 | PACT-VLA | https://arxiv.org/abs/2610.28019 | pre-commit observation/FlowRes/+15pp |

> S13–S35 为第 8 轮已核对来源（MolmoAct2、WALL-OSS、DreamZero、AgentChord、FLARE、HELM、ANCHOR、LIBERO-Recover、SO-101、Behavior-Skill、BTGenBot-2、Multimodal BT、Planning under Uncertainty、PA-BiCoop、BiRoAD、Co-VLA、MA-VLA、VLBiMan++、Foresight、Robust-TAMP、TCoT、宇树世界物理 AI 大赛、社区 N 端口观察），本轮不重复。`unibot.unitree.com` 直连 JSON 会间歇触发风控；本轮通过 `r.jina.ai` 与带浏览器 UA 的 curl 双通道抓取；榜单/运行记录均为占位，数字不作排名依据。

---

## 11. 一句话押注

**在字典序排名下，成功率先行；但成功率的主战场已经从“运行时补救”转向“训练分布里的域偏移、复述变化和扰动恢复”。把 192 个采集 session 当免费域标签、30 个任务的 60 条官方人扰备注当恢复剧本、5 条官方复述当语言增广，在同一个 WLA-1.0-Base 上做 R3-VLA 训练；推理端用可靠前缀 + 安全端点兑现，评测端用 DGS-32 的 session/复述/扰动三重留出验证——这是本轮最值得押注的方向。**
<!-- ARTIFACT:END -->
