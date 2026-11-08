# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 35 轮 · 三灵感落地：开源基座雷达 × 跨 episode 记忆检索 × 门禁式路线图

> 承接第 34 轮（v11：四足先验 × 步骤分 × LoRA 专家银行）。本轮灵感词「开源软件 / 记忆检索 / 技术路线图」。
> **先联网核实，再谈创新**——本轮拿到四项改变「资源账」的一手事实（宇树自家开源 VLA 家族、72 仓 G1-Dex1 开放数据集、第三方全量 UniBot LoRA 参考配方、32 任务×5 指令改写），据此对 v11 的"重算力旗舰"假设做**诚实下修**，并把主攻方向转向**记忆检索**。

## 0. 联网核实（先事实后推理；检索口径 2026-11-08）

复核与新增事实（来源见产物区 §8；编号续接 v11）：

- **S2 复核（github unitreerobotics/unibot_submission）**：仓库自 2026-08-21 后**无新提交**（2 commits：version 2 → 帧跳过堆叠/图像缩放/序列化修改）。接口契约与 v11 记录的 F24 完全一致：4 相机 + 双臂 7 + ee_pose 6×2 + 夹爪 2 + lower_body 15 + language；动作 joint/ee 二选一 + 共享夹爪 + `pivot[7]`；`obs_delta_indices` 兼具选键与时序堆叠；§6 时延/波动/动作统计=可信度指标。**无变化，F24 继续有效**。
- **S1 复核（unibot.unitree.com）**：`/leaderboard` 与首页同为 7351B 静态占位页（无 JS bundle、无 API、无 fetch）。**排行榜仍不可得**；"榜首<30%""5 类泛化场景""步骤分口径"仍为**待验假设**（诚实标注，A15 继续开放）。
- **F36（★新：指令改写，HF `meta/tasks.parquet` 直取）**：32 个任务仓**每个恰有 5 条英文改写指令**，以 `@` 连接（如 HangCup："Hang the cup on the marked spot on the cup rack." + 4 变体）。**A16 已解决**。含义重大：配合 arXiv 2610.19438（LIBERO 上改写指令使 OpenVLA 成功率 **-38 分**，prompt 集成无法恢复，paraphrase consensus 反掉 16.8 分）——**指令改写鲁棒性是被低估的排名变量**；我们手里恰好有 5 改写，可做 5× 增广 + 改写鲁棒评测 +  paraphrase-invariant 的路由/检索键。
- **F37（★新：宇树自家开源 VLA 家族，HF + github）**：`unitreerobotics/UnifoLM-VLA-Base`——**在 G1-Dex1 开放数据集上继续预训练的 VLA**（Qwen2.5-VLM 骨干 + 流匹配 DiT 动作头，代码 `github.com/unitreerobotics/unifolm-vla`，基于 LeRobot；含 `deployment/model_server/run_real_eval_server.py` 真机评测服务端），license **CC BY-NC-SA 4.0**；同门 `UnifoLM-ER-Flow`（**apache-2.0**：交互中心世界模型 + RVQ 离散动作 token）、`UnifoLM-WLA-1.0-Base`（apache-2.0）、`UnifoLM-WMA-0-Base`（**gated**，不可得）。**与官方同平台、同数据家族的开源基座真实存在**。
- **F38（★新：72 仓 G1-Dex1 开放集）**：`unitreerobotics/g1-dex1-datasets-68bae98bf0a26d617f9983ab` 集合共 **72 个数据集**（2026-10-14 新增约 28 个：Wipe_Table、Erase_Board、Bag_Insert、Connect_The_Network_Port、Put_Food_In_Oven、Tableware_Storage…）。即：**32 挑战任务之外还有约 40 个同平台开放任务**可做预训练/域扩展。
- **F39（★新：第三方全量参考配方）**：`ezhoureal/lingbot-vla-v2-unibot-lora`（apache-2.0）：LingBot-VLA-V2（6.3B=Qwen3-VL-4B 骨干 + Qwen2 MoE 动作专家，自身 apache-2.0、60k 小时预训练）上做 LoRA r64/α32（q/v/o，65M 可训练），**全量 UniBot G1_Dex1 = 32 任务 / 33,276 episodes**，10K 步、bf16、**单张 RTX 4090**，val loss 0.085，**合并为单一完整 checkpoint**（恰好符合"单模型"通才赛道）；并公开 `norm_stats/unibot_full.json`（全量 meanstd 归一化统计，可复用/交叉校验）。LingBot-VLA-V2 另有 Dual-Query 蒸馏（DINO-Video/LingBot-Depth）与 MoE 动作专家。
- **F40（新：无公开 UniBot 榜单复现）**：GitHub 搜 `unibot` 691 仓皆无关（校园助手/聊天机器人）；Unitree 其他挑战（IKEA、luckyrobots/g1-manipulation-challenge）与 UniBot 无关。**没有任何公开提交代码/榜单可供对标**——本地闭环（IP-3）+ F39 参考配方就是我们唯一的基准刻度。
- **S9 数据许可（复核）**：G1_Dex1_HangCup = **apache-2.0**、194,564 帧（与 F25 一致）。**数据可自由商用**，但 F37 的模型权重是 NC-SA——**"数据自由" ≠ "基座自由"**，基座选型必须先过许可审计。
- **文献（arXiv API 实时检索，2026-11-08）**：记忆/检索/改写鲁棒性集群 R65–R82（HeLM 2611.02660、PREM 2611.00634、IMPRINT 2610.14406、MemBodied 2609.28256、CogMemory 2610.34251、Robocasa-Mem 2611.06475、Paraphrase 2610.19438、Retrieve-to-Act 2610.37215、Externalise-the-Memory 2610.30478、FastHarness 2610.31427、VoI 检索 2610.40030、P² 进度探针 2610.31613、VeriVLA 2610.21985、OCC4M 2609.28798、IOM 2607.23702、FLORA 2610.31779、VLA-HWBench 2610.34717、Async Policies 2611.05155）。均为标题+摘要级核实，未逐篇读全文。

## 1. 灵感词 → 三条落地线

- 「**开源软件**」→ **IP-30 OPEN-STACK-RADAR**：整个竞技环境（提交模板、32 挑战仓+72 开放仓、宇树自家 VLA 代码、LingBot-VLA-V2、第三方参考 LoRA）都是开源的。**差异化不在"有没有模型"，而在"基座选型 + 一键复适 + 许可合规 + 持续吸收新发布"**。含一个**现实修正**：F39 证明全量微调在**单卡 4090** 上可行——v11 给 IP-21 记的"算力(重,一次性)"**降级为(中)**；竞争瓶颈从算力转移到**决策纪律**（这正是第三条线的入口）。
- 「**记忆检索**」→ **IP-31 MEMORY-RETRIEVAL（本轮技术主攻）**：F36 的指令文本暴露 32 任务中大量**长程/多物/非马尔可夫**任务（OrganizePencilCase：开拉链→收全部→拉拉链；ToolboxStorage：收纳→上锁；StoreEarphones：进充电仓→进收纳盒；PackDoll：全部装包→竖放；StoreCups：one by one；ConveyorSorting：传送带动态分拣）。马尔可夫策略在这些任务上结构性吃亏（R65/R68/R70/R78）。记忆检索同时命中三个排名杠杆：**长程成功率、未见物泛化（跨 episode 近邻先验）、失败恢复（失败经验检索）**。
- 「**技术路线图**」→ **IP-32 ROADMAP-GATES**：当基座与参考配方都开源后，真正的稀缺品是**什么时候做什么、什么时候止损**。做一份带**量化 go/no-go + 预登记止损线 + 三账户预算分配**的分阶段路线图（P0 复现 → P1 旗舰 → P2 记忆栈 → P3 泛化/部署加固 → P4 冻结），并把"开源雷达纳入 slot"（新发布只有在本门槛优于现役且时延不劣才切换）。

## 2. 三线耦合与关键决断

- **耦合**：IP-30 供基座+数据+B0 参照 → IP-29 专家银行在其上挂载（路由器键改为**5 改写平均嵌入**，R71 驱动）→ IP-31 记忆栈给 System-2 提供检索先验与物体账本、给 IP-28 进度头提供历史条件、给 IP-24 提供失败经验 → IP-25 用异步/VoI 门禁保证检索不伤时延 SLO → IP-32 用门禁决定每层的去留。
- **关键决断**：
  1. **默认基座 = LingBot-VLA-V2（apache-2.0）**，挑战者臂 = 宇树 `UnifoLM-VLA-Base`（G1-Dex1 原生，但 **CC BY-NC-SA 4.0，先过许可审计**，A17）；对照臂 = F39 公开 LoRA 配方即 B0。**禁止**在无许可结论前把 NC-SA 权重用于正式提交。
  2. **动作空间转换精确性优先于一切**：LingBot 规范空间是「arms(14)+grippers(2)+waist(4)+base(3)、state-relative deltas、meanstd 归一化」，与官方 joint schema（双臂 7+7、夹爪、`pivot[7]`）**不是同一套**；必须有显式转换器 + 用 F39 的 `norm_stats/unibot_full.json` 交叉校验（A18）。
  3. **记忆默认外置**：提交是远程服务（合法持有内存状态），故 M1 工作记忆与 M2 检索库**放服务端**，不进权重；仅当时延证明可行才蒸馏（R73 显示蒸馏进 LoRA 可行但仅 +1pp n.s.，不急于做）。
  4. **检索必须在关键路径之外**：ANN 预索引（亚毫秒级）+ 异步预取（R82）+ VoI 门禁（R75：只检索"信息价值"高于阈值的观测）——直接呼应 §6 时延/可信度指标。
  5. **指令 5× 增广作为一等公民**：所有语言条件模块用 5 改写训练，并以跨改写评测（E41）验证（R71：改写可 -38 分，不可儿戏）。

## 3. 诚实标注（未解决项，不假装解决）

- 排行榜、参赛手册/步骤分口径、5 类泛化赛制的官方定义**仍不可得**（S1 占位页、S4 登录墙、F40 无公开复现）。"榜首<30%"是用户口径，**不是已核实事实**。
- 因此 IP-28/IP-31 的"步骤分最大化"仍按**更保守的解释 A（rubric 部分分）**实现，且保持 rubric 无关的自监督设计（继承规则 33/34）。
- 文献均为标题/摘要级引用。

## 4. 本轮最大风险

1. **基座-动作空间错配**（F39 的 deltas/分组 ≠ 官方 schema）：转换错一格 = 全盘皆输。缓解：A18 转换器单测 + 本地回放闭环（IP-3）先证伪再上真机。
2. **记忆检索反噬**：错误先验会主动带偏策略（R72 指出 OOD 视觉偏移下检索自身训练 kinematic 先验才是正道——我们的库正来自训练分布，这点有利；但未见物 embedding 距离不可靠）。缓解：E42 消融 + 检索置信门限 + 回退纯基座。
3. **路线图变成"规划戏剧"**：缓解：每个门禁必须绑定一个可执行实验 + 一个三账户数字（规则 38）。

## 5. 一句话结论

本轮最值得押注：把 **IP-31 跨 episode 记忆检索**（工作记忆物体账本 + 5-改写鲁棒检索键 + 失败经验检索）立为技术主攻，用 **IP-30 开源基座雷达**（默认 apache-2.0 的 LingBot-VLA-V2、B0 参考配方锚定、许可审计）把算力账降下来，以 **IP-32 门禁式路线图**保证每一步可证伪、可止损。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 35 轮产物 · 创新点清单 v12：开源基座雷达 × 跨 episode 记忆检索 × 门禁式路线图

> 承接 v11（第 34 轮）。本轮**新增 IP-30/31/32（均 P0）**，**下修 IP-21 算力账户**（F39：单卡 4090 可全量微调），解决行动项 A16（F36），新开 A17（许可审计）/A18（动作空间转换）。灵感词：开源软件 / 记忆检索 / 技术路线图。

## 0. 结论

- **旗舰 IP-21 UNIBOT-RFM 保留**，但补一条**基座纪律**：默认基座 `LingBot-VLA-V2`（apache-2.0），挑战臂 `UnifoLM-VLA-Base`（G1-Dex1 原生、CC BY-NC-SA 4.0 → A17 审计），对照臂 B0 = F39 公开 LoRA 配方（单卡 4090 / 10K 步 / 33,276 episodes / 单一 checkpoint）。**IP-21 算力账户从"重"降为"中"**。
- **新增 IP-31 MEMORY-RETRIEVAL（P0，本轮技术主攻）**：M1 工作记忆（物体账本/过程记忆）+ M2 跨 episode 检索银行（5 改写鲁棒键）+ M3 失败经验检索（驱动 IP-29 恢复 LoRA 选择）+ M4 异步/VoI 检索门禁 + M5 蒸馏可选。
- **新增 IP-30 OPEN-STACK-RADAR（P0，工程主攻）**：开源候选登记册 + 一键复适 + 许可台账 + B0 锚定；把 72 仓 G1-Dex1 开放集纳入预训练池。
- **新增 IP-32 ROADMAP-GATES（P0，纪律主攻）**：P0–P4 分阶段 + 量化 go/no-go + 预登记止损线 + 三账户预算 + 开源纳入 slot。
- **F36（32 任务 × 5 指令改写）升级为一等公民约束**：所有语言条件模块 5× 增广训练 + 跨改写评测（规则 37）。

## 1. 事实卡（联网核实；检索日期 2026-11-08）

- **F24（接口契约，github unibot_submission 复核）**：与 v11 一致（4 相机 480×640 u8、双臂 7×2、ee_pose 6×2、夹爪 2、lower_body 15、language；joint/ee 二选一 + 共享夹爪 + `pivot[7]`；`obs_delta_indices` 选键+时序堆叠；`image_resize`；token；N 端口 8765..；§6 时延/波动/动作统计=可信度指标）。仓库 2026-08-21 后无新提交。
- **F25/F30/F31/F32/F33（数据 schema 与定基座，HF 直取）**：沿用 v11（LeRobot v3.0、30fps、480×640；HangCup 194,564 帧；`pivot`≈常数、height≈0.735–0.740、std≤0.016 → 桌面任务实质定基座；夹爪 0–4.5、左右手强度非对称）。
- **F34（榜单/规则，未核实）**：官网为 7351B 静态占位页；feishu 手册 Login Required；"榜首<30%""5 类泛化""步骤分口径"=待验假设。
- **F35（文献集群 R52–R64）**：沿用 v11。
- **F36（★指令改写，HF `meta/tasks.parquet` 直取全部 32 仓）**：每任务恰 **5 条英文改写**，`@` 连接。举例：HangCup / OrganizePencilCase（开拉链→收全部文具→拉拉链）/ PackBag（书包→拉链）/ ToolboxStorage（收纳→上锁）/ StoreEarphones（充电仓→收纳盒）/ SpellRobot（拼 "robot"）/ ConveyorSorting（传送带动态→按类分拣）。**A16 关闭**。
- **F37（★宇树开源 VLA 家族，HF+github）**：`UnifoLM-VLA-Base`（G1-Dex1 继续预训练；Qwen2.5-VLM + 流匹配 DiT 动作头；代码 unifolm-vla：LeRobot 数据栈 + `run_real_eval_server.py`；**CC BY-NC-SA 4.0**）；`UnifoLM-ER-Flow`（**apache-2.0**：动态区域预测 + RVQ 离散动作 token）；`UnifoLM-WLA-1.0-Base`（apache-2.0）；`UnifoLM-WMA-0-Base`（**gated**）。
- **F38（★72 仓 G1-Dex1 开放集）**：`g1-dex1-datasets` 集合 72 仓（2026-10-14 新增约 28 仓：Wipe_Table、Erase_Board、Bag_Insert、Connect_The_Network_Port、Put_Food_In_Oven、Tableware_Storage 等）→ 预训练池 ≈ 4×挑战集。
- **F39（★第三方全量参考配方，`ezhoureal/lingbot-vla-v2-unibot-lora`，apache-2.0）**：LingBot-VLA-V2 6.3B（Qwen3-VL-4B 骨干 + Qwen2 MoE 动作专家）上 LoRA r64/α32（q/v/o，65M 可训练）；**全量 32 任务 / 33,276 episodes**；10K 步、bf16、**单 RTX 4090**；val 0.085；**合并为单一 checkpoint**；动作规范 = joint 空间 arms(14)+grippers(2)+waist(4)+base(3)、**state-relative deltas**、meanstd；公开 `norm_stats/unibot_full.json`。LingBot-VLA-V2 本体：apache-2.0、60k 小时（50k 机器人 + 10k 第一人称）、MoE 动作专家、Dual-Query 蒸馏（DINO-Video/LingBot-Depth）。
- **F40（无公开对标）**：GitHub 无 UniBot 挑战提交/榜单复现；其他 Unitree 挑战（IKEA/luckyrobots）无关。→ 唯一刻度 = IP-3 本地闭环 + B0。
- **S9（数据许可）**：挑战仓均 apache-2.0（HangCup 复核）；但 F37 基座权重 NC-SA。**数据自由 ≠ 基座自由**。

**行动项更新**：A16 **关闭**（F36）；**A17 新增**：NC-SA 基座的竞赛用途许可审计（IP-30 前置，最高优先）；**A18 新增**：官方 joint schema ↔ 基座规范空间（deltas/分组）转换器 + norm_stats 交叉校验；A14（全 32 任务 pivot 扫描）、A15（rubric）、A9/A11/A13 沿用。

## 2. 创新点清单 v12 一览

| 编号 | 名称 | 一句话 | 优先级 | 依赖 | 灵感词 | 主成本账户 | 边际分预期 | 状态 |
|---|---|---|---|---|---|---|---|---|
| IP-21 | UNIBOT-RFM | 单模型双系统 VLA 覆盖 32 任务（System-2 规划 + System-1 少步流匹配动作头） | P0 | A9,A13,A18 | 机器人基础模型 | **算力(中)** ← F39 下修 | 主成功率 | 旗舰（账户修正） |
| **IP-31** | **MEMORY-RETRIEVAL** | 工作记忆物体账本 + 跨 episode 检索银行（5 改写鲁棒键）+ 失败经验检索 + 异步/VoI 门禁 | **P0** | IP-3,IP-28,IP-29,A18 | **记忆检索** | 算力(轻)+工程(中) | 长程成功率/未见物/恢复 | **新增** |
| **IP-30** | **OPEN-STACK-RADAR** | 开源基座登记册 + 一键复适 + 许可台账 + B0 锚定 + 72 仓预训练池 | **P0** | A17,A18,IP-3 | **开源软件** | 工程(中) | 基座选型正确率 + 迭代速度 | **新增** |
| **IP-32** | **ROADMAP-GATES** | P0–P4 分阶段 + 量化 go/no-go + 预登记止损 + 三账户预算 + 开源纳入 slot | **P0** | IP-10 | **技术路线图** | 近零 | 防负 ROI + 决策速度 | **新增** |
| IP-29 | LoRA-EXPERT-BANK | 共享 VLM + K 个能力 LoRA 专家 + 语言/首帧路由器 + 恢复 LoRA（键→5 改写平均嵌入） | P0 | IP-21 | LoRA | 算力(中) | 全域成功率 + 省显存 | 继承（键升级） |
| IP-28 | PROGRESS-CRITIC | 自监督进度/子步骤：稠密监督 + 卡住重试 + 部分分最大化 | P0 | A15,IP-3 | 步骤分 | 数据(标注轻) | 步骤分 + 长程 | 继承（+P² 探针 R76） |
| IP-25 | LATENCY-SLO | 时延 SLO + 少步动作头 + QAT + N 端口并发 + 动作平滑 | P0 | IP-4,A11 | 接口工程 | 部署机 | 可信度 + 不掉请求 | 继承（+R81/R82） |
| IP-22 | TRI-FUSE | 多视图×本体×语言融合 + 立体伪深度 +（可选）世界模型辅助 | P0 | IP-21 | 技术融合 | 算力(中) | 未见物/位置泛化 | 继承（+F37 ER-Flow 选项） |
| IP-24 | FAILURE-MONITOR | 可观测失败预警 + 触发恢复（恢复 LoRA 由 M3 检索选择） | P1 | IP-21,IP-29,IP-31 | 泛化×安全 | 算力(轻) | 鲁棒性/可信度 | 继承（+M3/R77） |
| IP-23 | TASK-DAG | 得分点驱动子目标分段 + 分层 | P1 | IP-28,IP-21 | 任务分解 | 数据(轻) | 步骤分 + 长程 | 继承 |
| IP-26 | GENERALIZE-SUITE | 五轴增广与评测 | P1 | IP-2,IP-3 | 泛化 | 数据(近零) | 全场景 | 继承 |
| IP-2/IP-3/IP-4/IP-10 | SCORE-ALIGN / LOCAL-EVAL / SUBMISSION-OPS / COST-LADDER | 沿用 | P0 | — | — | — | — | 继承 |
| IP-9 | SWARM-DECODE | 开源候选池内集成→蒸馏单模型（与 IP-30 登记册共享池） | P1 | IP-2,IP-30 | 泛化 | 算力(一次性) | +2~5pt | 继承（挂 IP-30） |
| IP-27 | QUAD-PRIOR | 跨形态表征先验，**不做运动控制** | P2 | IP-22 | 四足 | 算力(低) | 未见物 | 继承（保持裁剪） |
| IP-8 | STEP-EFF | 并入 IP-28/IP-25 | — | — | — | — | — | 合并（v11 起） |
| IP-1/11/13/16/17/18/19/20 | SLAM/社交/力觉/触觉/对话 | 接口不可达或赛道无需求 | — | — | — | — | — | 退役 |

## 3. 重点展开

### 3.1 IP-31 MEMORY-RETRIEVAL（灵感：记忆检索）

**动机**：(a) F36 指令文本证实 32 任务含大量长程/多物/非马尔可夫任务；(b) 马尔可夫 VLA 在"已处理哪些物体/收纳关系/子步骤"上结构性失明（R65/R68/R70/R78）；(c) 33,276 episodes 本身就是一座**可检索的经验库**（F39），跨 episode 近邻先验是无需训练的泛化机制；(d) 改写是排名暗礁（R71：-38 分）。

**设计（五模块，默认全部外置于服务端）**：
- **M1 工作记忆（物体账本 + 过程记忆）**：固定容量记忆（MemBodied 式：associative state + episode anchor），**事件触发更新**（HeLM 式：夹爪开合事件、物体计数变化、子步骤完成）。账本字段：`(物体槽位, 类别, 位置, 状态:原位/已抓/已放/已收纳于 X)`；关系含 **containment**（OCC4M：进包/进盒/进仓）。查询接口给 System-2（子目标）与 IP-28 进度头。
- **M2 跨 episode 检索银行（RAG）**：预嵌入全部 33,276 episodes：**键 = 5 改写指令的平均嵌入（paraphrase-invariant）+ 首帧视觉嵌入 + 技能标签**，ANN 索引（亚毫秒）。运行时：检索 top-k 相似 episode → (i) 作为 System-2 的上下文示范（记忆增强教师，R73）；(ii) 提取其末段/子目标序列作**检索先验**注入 System-1（R2A：策略自身训练经验里的 kinematic 先验最干净）。
- **M3 失败经验检索**：IP-24 触发时，从"失败-恢复"配对库检索最相似失败 → 选择/加权 **IP-29 恢复 LoRA**，并复用其成功恢复子轨迹（FastHarness 式"审后再恢复、恢复后回归常规"）。
- **M4 检索调度（不伤时延）**：R75 VoI 门禁——只有"信息价值"高于阈值的观测才触发检索；ANN 查询异步预取（R82 异步策略），不进控制回路；失败事件为最高优先级同步检索。
- **M5 蒸馏开关（P2）**：仅当 E42 证明外置检索增益 ≥ 阈值且时延有余，才把记忆行为蒸馏进权重（R73 预注册结论：+1pp n.s.，不急于做）。

**与现有方案差异**：v11 无任何记忆组件；IP-28 仅是 episode 内进度。IP-31 首次引入**跨 episode 检索 + 物体账本 + 失败经验**，且**键的构造被 F36 直接约束**（改写平均嵌入）。

**可行性/资源**：33k episodes 嵌入预计算（1 GPU·天级）；ANN（faiss 级）；账本更新是轻量规则/小头。数据零新增标注。风险：检索噪声、库与评测场景错配、时延。

```python
class MemoryStack:
    def __init__(self, bank_episodes, embed, ann):
        self.bank_keys = embed_mean_over_5_paraphrases(bank_episodes)  # F36
        self.ann = ann.index(self.bank_keys)                           # 亚毫秒
        self.ledger = ObjectLedger()          # M1: (slot,class,pos,state)
    def on_event(self, ev):                   # 夹爪跳变/计数变化/子步完成
        self.ledger.update(ev)
    def retrieve(self, lang_or_variants, frame, voi_ok):
        if not voi_ok: return None            # M4: 节流，保 §6 时延
        k = concatenate([mean(embed(v) for v in variants), embed(frame)])
        ids, scores = self.ann.search(k, top_k=5)
        return band_filter(ids, scores)       # 阈值过滤，否则回退纯基座
    def on_failure(self, f):                  # M3
        return self.retrieve_similar_failure(f)   # → IP-29 恢复 LoRA 选择
```

### 3.2 IP-30 OPEN-STACK-RADAR（灵感：开源软件）

**动机**：提交模板、数据（apache-2.0）、宇树自家代码与权重、LingBot-VLA-V2、第三方全量 LoRA 配方全部公开（F24/F37/F38/F39）。**差异化 = 基座选型 + 一键复适 + 许可合规 + 持续吸收**。且 F39 把"能不能练得起"变成"敢不敢选错"。

**设计**：
- **候选登记册**（字段：license、参数量、动作空间、chunking、embodiment 覆盖、G1/Dex1 匹配度、本地硬件时延、IP-3 本地榜成绩、迁移成本）。基线三臂：B0=F39 配方（LingBot+官方 LoRA）、B1=UnifoLM-VLA-Base（待 A17）、B2=域预训练（72 仓）→ 微调。
- **一键复适**：A9 统一 schema 数据加载 → 同一微调配方（LoRA r64/α32 q/v/o，bf16，10K 步量级）→ IP-3 本地回放榜 → 自动出报告；换基座 < 1 天。
- **许可台账**：apache-2.0 优先（LingBot-VLA-V2、UnifoLM-ER-Flow、数据）；**CC BY-NC-SA 4.0（UnifoLM-VLA-Base）在 A17 结论前只作对照臂**；WMA-0 gated 不可得 → 不排期。
- **开源雷达 slot（挂 IP-32）**：新发布进入"优于现役 ≥2pt 且时延不劣"才切换；雷达本身零算力（API 轮询）。
- **数据池**：72 仓 G1-Dex1（F38）做域预训练（FLORA 式数据引擎概念作参照 R80；InternW0-Δ/ Open-HumanWAM 作外推选项、非关键路径）。

**差异**：v11 假设"自建重算力预训练"；本项改为**选型+复适+合规**的工程纪律，并把 B0 设为一切创新的诚实地平线。

**风险**：追新主义（雷达 slot 有门槛）、NC-SA 合规、生态碎片化（迁移成本已单列）。

### 3.3 IP-32 ROADMAP-GATES（灵感：技术路线图）

**动机**：基座与配方开源后，稀缺品是**决策纪律**：何时做什么、何时止损、何时换基座。路线图即"把风险排进日历"。

**设计（P0–P4，每阶段量化 go/no-go + 预登记止损线）**：
- **P0 复现期（W1–2）**：B0 三臂在 IP-3 上跑通；验证 A18 转换器、A14 pivot 冻结、相机映射 A9。Gate：本地 32 任务成功率复现 B0 ±3pt；否则回查 schema/转换（止损：≤2 周）。
- **P1 旗舰期（W3–5）**：IP-21+IP-29（LoRA 银行）+双表示动作头；5 改写增广。Gate：本地 ≥ B0 +5pt 且路由准确 ≥90%；否则退单 LoRA。
- **P2 记忆期（W6–9）**：IP-31 M1–M3 + IP-28 进度头。Gate：长程子集（≥5 任务）+10pt 且部分分（E37）↑；否则只留 M1。
- **P3 泛化/部署期（W10–12）**：IP-26 五轴 + IP-24 + M4 门禁 + IP-25 时延压测 + IP-4 多端口。Gate：p99 时延 ≤SLO、动作统计无离群。
- **P4 冻结期（W13+）**：可信度预演、官方通道演练、版本冻结；雷达 slot 保留至截止。
- **三账户预算**：训练/服务/工程按阶段配额 + 每阶段止损线（超支即降级该阶段范围，不动其他阶段）。

**差异**：v11 有实验表但无门禁/止损/预算分配；本项把"何时停"变成可执行判据（规则 38：无门禁不上马）。

**风险**：规划戏剧 → 每个 Gate 必须绑定一个实验编号 + 一个数字。

## 4. v12 整合架构

```
输入: 4×RGB ─┐  本体(arms/ee/grip/lower_body) ┤→ TRI-FUSE (IP-22)
     语言指令 ×5 改写 (F36) ──────────────────┘
        │
 System-2 = 开源基座(默认 LingBot-VLA-V2 apache-2.0 / 臂 UnifoLM-VLA-Base 待 A17)
          + LoRA-EXPERT-BANK (IP-29, 路由键=5改写平均嵌入)
          + 检索先验(M2) + 物体账本查询(M1) ──→ 子目标 z_t (IP-23)
        ▲                         │
 失败经验检索(M3) ◄── FAILURE-MONITOR(IP-24)   PROGRESS-CRITIC(IP-28) + P²探针(R76)
        │
 System-1 = 少步流匹配动作头(joint/ee 双表示) → 动作块 T_a×(双臂+夹爪) + pivot 冻结头
        │
 LATENCY-SLO (IP-25): 少步 + QAT + 平滑/限幅 + N 端口并发；检索异步/VoI 门禁(M4)
 A18 转换器（基座规范空间 deltas/waist-base 分组 ↔ 官方 schema）在所有输入/输出边界
 ROADMAP-GATES (IP-32): P0–P4 门禁决定每层去留；OPEN-STACK-RADAR (IP-30) 供基座与数据
```

## 5. 训练/服务伪代码（增量）

```python
def build_v12():                       # IP-30: 基座来自登记册（默认 apache-2.0）
    base = load_open_base("lingbot-vla-v2")            # F39；A17 前不用 NC-SA
    fuse = TriFuseEncoder()                            # IP-22
    bank = LoRABank(base, K=6, paraphrase_keys=True)   # IP-29 + F36 键
    mem  = MemoryStack(bank_episodes=ALL_33K)          # IP-31 M1-M3
    system2 = SubgoalPlanner(bank, memory=mem)         # IP-23
    system1 = FlowActionExpert(steps=4, dual=("joint","ee"))
    prog = ProgressHead(p2_probes=True)                # IP-28 + R76
    for batch in D:                                   # 每条样本语言 5× 增广（F36/R71）
        for variant in batch.lang_variants:
            f = fuse(batch.images, batch.proprio, variant)
            demo = mem.retrieve(variant, batch.first_frame)      # M2（训练期暖初始化）
            z = system2(f, variant, demo)
            a = system1.sample_train(f, batch.proprio, z, batch.action)
            loss = flow_loss(a, A18.convert(batch.action)) \
                 + LAM_PROG * prog_loss(prog(f, mem.ledger), batch.pseudo_progress) \
                 + LAM_ROUT * router_lb(bank) + LAM_PAR * para_invariance(bank)
    mem.build_failure_bank()                          # M3: 失败-恢复配对
    return fuse, bank, system2, system1, prog, mem, A18.converter

def get_action(obs):                 # 服务端（外置记忆，M4 门禁）
    if voi_ok(obs) and t_budget_left():
        demo = mem.retrieve(obs.lang_variants, obs.frame)   # 异步预取结果
    else:
        demo = None
    mem.on_event(detect_event(obs))                    # M1 账本更新
    if failure_monitor(obs, prog) > TAU:               # IP-24
        rec = mem.on_failure(obs)                      # M3 → 恢复 LoRA
        return recover_loras(bank, rec), obs            # 只增不减（规则 30）
    return policy(obs, demo, mem.ledger)
```

## 6. 实验设计（新增 E40–E44；E30–E39 沿用）

| 实验 | 设置 | 指标 | 门槛/预期 |
|---|---|---|---|
| E40 基座对照 | B0(F39 配方) vs B1(UnifoLM-VLA-Base) vs B2(72仓预训练→微调) | 32 任务成功率、p99 时延、显存 | B0 复现 ±3pt 为地平线；选优者进 P1 |
| E41 改写鲁棒 | 无增广 vs 5× 改写增广；跨改写评测 | 成功率掉幅 | 掉幅 ≤5pt（R71 基线：无增广可 -38） |
| E42 检索银行 | 无检索 vs M1 vs M1+M2 vs +M3 | 长程子集成功率、部分分、检索 p99、未见物成功率 | 长程 +≥5pt；p99 检索 ≤SLO；错误先验率 <τ |
| E43 失败恢复 | M3 开/关 | 恢复成功率、动作统计离群（可信度） | 恢复成功率↑；离群≈0 |
| E44 门禁演练 | 按 IP-32 跑 P0–P2 流程 | 每 Gate 可判定性、预算超支率 | 每个 Gate 有明确数字裁决 |
| E36–E39 | 沿用（LoRA 银行/进度-部分分/跨形态/pivot 消融） | — | — |
| E30–E35 | 沿用（数据统一/闭环/泛化/时延/失败预警） | — | — |

**降级机制**：A17 不过 → B1 撤出正式提交（仅对照）；E41 不过 → 强制增广重训；E42 不过 → 仅保 M1（账本）关 M2/M3；门禁不过 → 按止损线缩范围；基座切换触发条件 = 新开源发布本地榜 +≥2pt 且时延不劣。

## 7. 风险登记簿（更新）

| 风险 | 等级 | 缓解 |
|---|---|---|
| **A18 基座-动作空间转换错位**（deltas/waist-base 分组 ≠ 官方 schema） | **高** | 转换器单测 + norm_stats 交叉校验（F39 公开统计）+ IP-3 回放先证伪 |
| **A17 基座许可（CC BY-NC-SA 4.0）** | **高** | 默认 apache-2.0 基座；NC-SA 仅对照臂；结论前不用于正式提交 |
| 记忆检索注入错误先验（未见物 embedding 不可靠） | 中高 | 检索置信门限 + 回退纯基座 + E42 消融 |
| 检索/账本拖累时延（§6 可信度指标） | 中高 | M4 VoI 门禁 + 异步预取 + ANN 亚毫秒 + p99 监控 |
| 路线图规划戏剧 | 中 | 规则 38：无门禁不上马；E44 演练 |
| 步骤分口径未核实（A15） | 高 | rubric 无关设计 + 保守阈值 + E37 |
| 路由错误跨任务干扰（IP-29） | 中高 | 软合并 + 熵门限回退 + E36 |
| 定基座假设不普适（A14） | 中 | 全 32 任务扫描 + pivot 小范围微调 |
| （沿用）相机映射、多端口隔离、时延异常、算力 | 高/中 | 见 v10/v11 |

## 8. 来源清单（引用口径：2026-11-08）

**官方/开源（一手，本轮直取）**
- S1 `https://unibot.unitree.com`（/、/challenges、/leaderboard）——7351B 静态占位页，榜单未上线。
- S2 `https://github.com/unitreerobotics/unibot_submission`——接口契约（§1–§6）、可信度指标（§6）；2026-08-21 后无新提交。
- S3 `https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset`（32 仓）+ 各仓 `meta/tasks.parquet`（**F36：每任务 5 改写**）+ `meta/info.json` / `stats.json`；G1_Dex1_HangCup = apache-2.0、194,564 帧；数据集服务端 size/first-rows 复核。
- S4 参赛手册（feishu）——**Login Required，未获取**。
- **S5（新）** `https://huggingface.co/unitreerobotics/UnifoLM-VLA-Base`（模型卡：G1-Dex1 继续预训练、CC BY-NC-SA 4.0）+ `github.com/unitreerobotics/unifolm-vla`（Qwen2.5-VLM + 流匹配 DiT、LeRobot 数据栈、run_real_eval_server）+ `UnifoLM-ER-Flow`（apache-2.0，动态区域+RVQ）+ `UnifoLM-WMA-0-Base`（gated）。
- **S6（新）** `https://huggingface.co/collections/unitreerobotics/g1-dex1-datasets-68bae98bf0a26d617f9983ab`——72 仓开放集。
- **S7（新）** `https://huggingface.co/ezhoureal/lingbot-vla-v2-unibot-lora`（33,276 episodes / 4090 / 10K 步 / LoRA r64 / 单一 checkpoint / norm_stats）+ `https://huggingface.co/robbyant/lingbot-vla-v2-6b`（apache-2.0，6.3B，60k 小时，MoE 动作专家，Dual-Query 蒸馏）。
- **S8（新）** GitHub repository search（`unibot`、`unitree challenge`）——无 UniBot 公开提交/榜单。

**文献（arXiv API 实时检索 2026-11-08；标题+编号，摘要级）**
- R65 HeLM: Hierarchical Explicit Language Memory for Non-Markovian Manipulation, 2611.02660。
- R66 PREM: Prediction-Regulated Memory for Robot Manipulation, 2611.00634。
- R67 IMPRINT: Memory Without Curation（多流潜记忆）, 2610.14406。
- R68 MemBodied: Recurrent Associative Memory for VLA, 2609.28256。
- R69 CogMemory: Variational Cognitive Memory Abstraction, 2610.34251。
- R70 Robocasa-Mem: Environment & Process Memory Benchmark, 2611.06475。
- **R71 Paraphrase Consensus Is Not Self-Consistency（改写使 OpenVLA -38 分）, 2610.19438。**
- **R72 Retrieve to Act: Motion Primitive Graph Retrieval for Robust VLA, 2610.37215。**
- R73 Externalise the Memory: Where Experience Should Live（预注册研究）, 2610.30478。
- R74 FastHarness: Experience-Driven Review Scheduling for VLA, 2610.31427。
- **R75 Cheap Retrieval & Observation Credit Assignment from Value of Information, 2610.40030。**
- R76 Progress Probes P²: Lightweight Runtime Monitoring via VLA 内部激活, 2610.31613。
- R77 VeriVLA: Adaptive Test-Time Verification for Flow-Based VLAs, 2610.21985。
- R78 OCC4M: Object-Centric 4D Memory（含 containment 关系）, 2609.28798。
- R79 IOM: Try Once, Then Optimal（实例导向跨 episode 记忆）, 2607.23702。
- R80 FLORA: An Open Model Suite for Scaling Robotics Data Engines, 2610.31779。
- R81 VLA-HWBench: Where the Time Goes on Edge Hardware, 2610.34717。
- R82 Asynchronous Robot Policies, 2611.05155。
- R83 InternW0-Δ: World Action Model, 20K+ 小时开放数据, 2609.31394；R84 Open-HumanWAM, 2611.06817。
- （R41–R64 沿用 v10/v11。）

**诚实记录**：S1 榜单、S4 手册不可得；"榜首<30%""5 类泛化""步骤分=rubric"均待验；文献为摘要级引用；F39 的总 episode 数（33,276）为第三方元数据，与历史"32000/169h"口径并存待官方确认。

## 9. 清单迭代规则（本轮增补 35–38）

- 继承规则 27–34（通道诚实 / 映射验证 / 时延 SLO / fail-safe / 灵感-现实校验 / 单模型专家化 / 步骤分双解释 / 稠密监督不依赖 rubric）。
- **35（基座许可审计）**：任何基座必须登记 license；默认 apache-2.0/MIT；NC/SA 权重在审计结论前只作对照臂。数据许可 ≠ 基座许可。
- **36（记忆外置优先）**：记忆检索默认放服务端内存（合法、可控），权重蒸馏为 P2 可选项；外置记忆必须可解释（物体账本 + 事件日志）。
- **37（指令 5× 一等公民）**：语言条件模块一律 5 改写增广训练 + 跨改写评测；路由/检索键必须 paraphrase-invariant（R71）。
- **38（门禁纪律）**：新 IP 上马前必须绑定路线图门禁的量化 go/no-go 与止损线；无门禁 = 不上马。

**当前最值得押注**：**IP-31 跨 episode 记忆检索**——以"5 改写平均嵌入 + 首帧"为键的检索银行（M2）与物体账本（M1）同时改善长程成功率、未见物泛化与失败恢复，且**零新增参数、复现成本低**；基座纪律（IP-30，默认 apache-2.0）与路线图门禁（IP-32）为其护航。
<!-- ARTIFACT:END -->
