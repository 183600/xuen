# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 28 轮 · 「多机器人协作 × 强化学习训练 × 可解释性」：官方把基座和沙盘都开源了——BIMAN-CREW 双臂仲裁 / 沙盘三介质 RL / CALIB-PROBE 校准验证门

## 0. 轮次编号与信息核实（先严谨，再发散）

**编号说明**：状态文件已保留第 27 轮（灵感词：碰撞避免/夹爪控制/强化学习）；本轮模板仍写"第 1 轮"。按「优先深化与修剪、不推倒重来」元规则，本轮记为**第 28 轮**。注意「强化学习」是第 27 轮已消费过的词，本轮只做**深化**不重开战线。

**本轮检索核实（全部检索于 2026-11-07）**：

- **官方三页重验**：排行榜/运行记录仍"Coming Soon"[R1/R2]；challenges 页口径不变（32 任务/32000 演示/169h/得分点 100 分/七步提交流程）[R1a]。F7/F8 未解除。
- **接口与数据侧**：repo 仍 2 commits（最新 2026-08-21）[R3]；HF 集合 32 项、lastUpdated 2026-09-11 [R4]；HangCup 元数据 2026-10-14 有更新但规模标签不变（100K<n<1M）[R4]。
- **F19（本轮最重要新事实）官方 UnifoLM 家族全栈开源**：
  - **UnifoLM-WLA-1.0-Base**：6B 参数基座（2026-09-28 发布权重），约 2500h 真机数据，单模型协调 64 任务（桌面+全身），支持二指夹爪与多种五指灵巧手；开源含 LoRA 微调代码、动作专家训练、Model Server；**明确把 UniBot-V1 Challenge Dataset 列为配套数据集** [R8c]；
  - **UnifoLM-WMA-0**：世界模型-动作框架（2025-09-15），世界模型两种用法——(a) 交互式仿真引擎生成合成数据，(b) Policy Enhancement（预测未来交互优化决策）；**存在 WMA-0-Dual 双臂权重**；真机 demo 含双臂叠盒/收铅笔 [R8b]；
  - UnifoLM-VLA-0（2026-01-29，12 类操作单策略）[R8a]；
  - **统一动作/状态规范**：54 维动作/60 维状态+有效性掩码、chunk 30 步@30fps≈1s、SE(3) 增量动作、分位归一化 [R8c]——与我们已消化的 F15/F16/F17 观测语义同族，A6 探针结论可复用其规范做交叉验证。
- **F20 官方沙盘与 RL 工具链**：unitree_sim_isaaclab（G1/H1-2 仿真，**与真机同一 DDS 协议**，定位含数据采集/回放/生成/模型验证，需 RTX 3080-4090）[R9]；unitree_rl_lab（IsaacLab 2.3.0 RL 环境，G1-29dof 等）[R10]；unitree_mujoco。→ **第 27 轮"评测无环境→整策略 RL 进拒绝清单"的前提被部分推翻：官方沙盘存在，但与真机评测的相关性未知（新缺口 F8'）**。
- **F22 官方 bimanual 资产**：HF 有 Z1_Dual_Dex1_*（叠盒/倒咖啡/叠衣/收铅笔）、G1_Dex1_DualRobot_Clean_Table、WMA-0-Dual 权重、UnifoLM-WBT 数据集集合 [R4][R8b]——双臂协调先验的免费训练数据。
- **文献锚点（arXiv API 逐一核实，全部命中）**：MAPPO [R7a]、PBT [R7b]、Q-chunking（离线先验+chunk 级 RL）[R7c]、Foresight（动作条件世界模型做长时程失败检测）[R7d]、无失败数据的不确定性运行时失败检测 [R7e]、Conformalized 交互式模仿学习 [R7f]、"Do VLAs Know They Will Fail?"（SAE 表征含结果预测信息，可提前预警失败）[R7g]、BiRoAD（双臂共享+角色自适应表征）[R7h]、PA-BiCoop（主-辅双臂协作分工）[R7i]。

**结论**：无与上轮冲突的事实；F7/F8 仍是最大信息缺口；新增最大缺口 **F8'（SANDBOX-GAP）：两个官方沙盘与真机评测的相关性未知**。F19/F20/F22 三个新事实全部利好本轮三词，且共同指向一个战略判断：**基座与沙盘已成公共物品，竞争重心向"末段细节+扰动泛化+可信交付"迁移——恰是 v3 清单的差异化地带。**

## 1. 三个灵感词拼出的图（直觉先行）

> **多机器人协作**回答「系统里谁是"多个智能体"」：赛制锁死"单 G1+单模型+远程 API"，物理多机器人=拒绝清单。但系统里真实存在一组多智能体——**双臂**。32 任务显式含双手协调，双臂在头顶共享工作区的分工/交接/避让是真实的协调问题；把多智能体文献（MAPPO 的合作训练框架 [R7a]、PA-BiCoop 的主-辅分工 [R7i]、BiRoAD 的角色自适应表征 [R7h]）压缩到"双臂仲裁层"，多机器人协作就有了合法落点。第二落点在训练侧：多个虚拟策略（IP-9 委员会）与沙盘里的多个工人（PBT [R7b]）。
> **强化学习训练**回答「沙盘解禁了多少」：第 27 轮把 RL 压缩到窄域的前提是"无环境"。本轮 F19/F20 推翻了半个前提——官方送来两个沙盘：WMA-0（外观真、物理近似、可当 rollout 评估器与合成数据引擎）与 Isaac Lab（物理真、渲染域差、与真机同 DDS 协议）。但两个沙盘与真机评测的相关性都未知（F8'），所以不是"RL 解禁"，而是"**训练介质从 1 种变 3 种、验收通道不变**"：Isaac Lab（物理）→ WMA-0（交互先验）→ 自训结构化 WM（最轻），held-out 真演示回放仍是唯一裁判。Q-chunking [R7c] 给了与 action-chunk 接口同构的 RL 形态：critic 只评 chunk 好坏，不改主干。
> **可解释性**回答「<30% 格局下什么最值钱」：知道为什么失败比多对一个更值钱。三个合法落点：①**表征探针**——VLA 中间层激活含结果预测信息，轻量 probe 即可提前预警失败 [R7g]；②**校准**——无失败数据的运行时失败检测 [R7e] 与 conformal 思路 [R7f] 给 verify/激活阈值提供统计校准，代替手调；③**世界模型偏差监测**——Foresight 式动作条件监控 [R7d] 把 IP-13 的世界模型变成 IP-11/12 的"第六感"。三者合起来既是迭代速度的乘数（IP-3 失败归因），也是提交材料（§6 可信度自证）。

核心类比（本轮灵魂）：**多机器人协作是"两个工人需要一个班组长"；RL 是"官方现在发了沙盘，可以自己出题自己练——但先要验证沙盘和考场像不像"；可解释性是"错题本+评分标准"——每道错题都写得清错在哪一步、凭什么扣分。**

一句话押注：

> **本轮新增 IP-14 BIMAN-CREW（双臂仲裁）/ IP-15 CALIB-PROBE（校准验证门），深化 IP-13 为"沙盘三介质"；最值得押注 IP-15 CALIB-PROBE——把三个词焊在现有押注 IP-12 的 verify 环节上（探针置信度→conformal 校准→世界模型偏差监测→统一触发重抓/让位/仲裁），近零成本、不依赖 F7/F8、直接决定所有"介入式插件"的触发质量。**

## 2. 研究日志：三词各自戳中哪个瓶颈（承接四层分解）

| 瓶颈层 | 多机器人协作的戳点 | 强化学习训练的戳点 | 可解释性的戳点 |
|---|---|---|---|
| 数据层 | 官方 bimanual 资产=免费角色先验（F22） | 沙盘自造经验（Isaac Lab/WMA-0/自训 WM 三介质） | 合成失败样本给探针当免费标签 |
| 表征层 | 双臂共享+角色自适应表征 [R7h] | chunk 级 Q 表征（critic 只评好坏）[R7c] | backbone 中间层=结果预测信息源 [R7g] |
| 目标函数层 | 主-辅分工目标（效率×安全）[R7i] | 奖励自监督不变+Q-critic 稀疏奖励缓解 | conformal 覆盖率=可验证的校准目标 [R7e/R7f] |
| 工程层 | 保守激活：冲突才介入+角色日志 | 沙盘保真度门（A8）先行 | 触发原因全部可读（§6 自证材料） |

观察：上一轮三词焊在"最后一厘米"微管线上；本轮三词焊在"**触发质量**"上——SAFE-FILTER 让位、GRIP-GATE 重抓、BIMAN-CREW 仲裁，全部是"介入式插件"，介入与否、何时介入、介入多深，正是校准与可解释性的主场。本轮创新密度来源=**给所有介入式插件装同一个校准触发器**。

## 3. 灵感词交点（组合即创新）

- **多机器人 × RL = 双臂在沙盘里练**：Isaac Lab 双臂环境的合作训练（MAPPO 框架 [R7a] 压缩为双 agent 特例）；PBT 多工人演化 LoRA [R7b]（观察项，不过成本账不启用）。
- **RL × 可解释性 = 沙盘验收可解释**：Q-critic 的 chunk 评分、世界模型偏差分数、CEM 最优解的归因——训练产物自带"可读的失败理由"，直接喂给 E 系列实验的失败归因。
- **多机器人 × 可解释性 = 角色分配日志**：哪只手负责什么、何时交接、为何仲裁——评测视频复盘的天然索引（F7 解除后拆对手双手协调行为的第一把钥匙）。
- **三词交点 = "可解释的沙盘训练"**：BIMAN-CREW 的每个决策带置信度与理由（IP-15），训练在官方沙盘（IP-13 三介质），交付仍是单模型单权重+轻量插件——三者都不动主模型，全部挂在已有资产上，符合 COST-LADDER。

## 4. 与第 27 轮清单的深化/修剪决策

| 清单项 | 本轮处置 | 依据 |
|---|---|---|
| IP-1 SLAM-MAP | 维持；外参前向模型继续服务 IP-14 双臂空间关系与 IP-15 人手缓冲 | — |
| IP-2 SCORE-ALIGN | 深化：进度裁判**第四消费者**=CALIB-PROBE 的失败预警先验 | 灵感词 可解释性 |
| IP-3 LOCAL-EVAL | 深化：失败归因从"看日志"升级为"探针+校准"；A8 沙盘保真度探针挂载于此 | 灵感词 RL×可解释 |
| IP-4 SUBMISSION-OPS | 深化：遥测新增角色分配日志+校准分数（§6 自证材料） | 灵感词 可解释性 |
| IP-5 DUAL-HEAD | 维持 P2（冻结） | F8 未解 |
| IP-6 UNSEEN-GRASP | 维持指针 | — |
| IP-7 DISTURB-AUG | 维持；新增产出类型：**合成失败样本**（探针标签，失败率可控） | 灵感词 可解释性 |
| IP-8 STEP-EFF | 维持 P1 | F8 未解 |
| IP-9 SWARM-DECODE | 深化：明确"多机器人协作"的合法映射=多策略委员会；单权重交付约束重申 | 灵感词 多机器人 |
| IP-10 COST-LADDER | 深化：拒绝清单 +1 条 #9；#8 修订为"可复用官方 WMA-0" | 纪律 |
| IP-11 SAFE-FILTER | 维持 P1；让位激活阈值改由 IP-15 校准分数供给 | 触发质量 |
| IP-12 GRIP-GATE | 深化：verify 的固定阈值→conformal 校准阈值（IP-15 承接） | 触发质量 |
| IP-13 GRIP-RL | **深化**：训练介质三选一→三介质分层；CEM 之外加 Q-chunking 式 chunk critic；PBT 观察项；四道闸+第 5 道沙盘保真度门 | 灵感词 RL |
| — | **新增 IP-14 BIMAN-CREW**（P1） | 多机器人协作 |
| — | **新增 IP-15 CALIB-PROBE**（P1，本轮押注） | 可解释性 |

无删除项；v3 十三项全部保留，本轮净增两项且都挂在已有资产上。

## 5. 风险与本轮最大风险

**最大风险：SANDBOX-GAP——把官方沙盘当真考场。** Isaac Lab 物理保真但渲染/动力学域差，WMA-0 外观保真但物理近似；两者的 rollout 分布与真机评测的相关性完全未知（F8'）。若 RL/协调训练在"像而不真"的沙盘里过拟合，就是第 27 轮 IP-13 最大风险的放大版（离线漂亮、真机拉胯），且这次诱导投入的成本上限更高（仿真基建+双臂环境搭建）。缓解：①**A8 保真度探针先行**——量化沙盘↔真演示回放的分布差异，不过阈不训 RL；②held-out 真演示回放唯一验收通道不变；③训练介质从最便宜的自训结构化 WM 起步，Isaac Lab/WMA-0 只在探针过关后逐级启用；④沉没成本封顶不变。

其余新增风险：⑤IP-14"帮倒忙"——仲裁层推翻主模型的正确分工反而降低成功率（缓解：保守激活，冲突检测触发才介入；conformal 激活阈值；E16 消融验证正常场景零回归）；⑥探针不忠实——saliency/SAE 解释不可靠，且 [R7g] 结论基于 OpenVLA，向 WLA 架构的迁移未验证（缓解：解释只生成调试假设、不自动改动作；多探针交叉验证；E17 验收）；⑦WMA-0-Dual 为 CC BY-NC-SA 许可、竞赛合规需核查（A7 顺带）；⑧官方栈演进快（缓解：锁定 commit 复现，A7 记录版本）。

## 6. 下一轮展望（灵感未知）

- 若灵感指向「课程学习/自动课程」→ 沙盘三介质天然支持难度课程（Isaac Lab 物理扰动递增→WMA-0 外观变化→真机回放验收），与 IP-7 注入器合并成课程化训练——第 27 轮展望的这条预告本轮已部分落地；
- 若灵感指向「人机交互/信任」→ 可解释性报告升级为"提交自证包"（delta 遥测+角色日志+校准曲线），人手避让（IP-11/E15）与校准预警（IP-15）串联成完整的干扰响应链；
- 若 F7/F8 解除 → 立即用运行记录+完整评测视频验证两件事：头部方案是否直接用官方 WLA-1.0 栈（若不是，其基座选择即情报）；末段失败分布是否与 IP-11/12/14 的假设一致——IP-14 的收益届时首次可量化。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 28 轮产物 · 创新点清单 v4：BIMAN-CREW / CALIB-PROBE——官方开源栈时代的"差异化插件"策略

## 0. 结论

第 27 轮清单 v3（13 项）本轮完成「深化 + 净增两项」迭代，产出 v4（15 项）：

- **IP-14 新增 BIMAN-CREW（P1）**：双臂仲裁层——冲突检测器（保守激活）+ 主-辅角色仲裁头 + 交接门控；多机器人协作在"单机器人赛制"下的合法落点=双臂即多智能体。
- **IP-15 新增 CALIB-PROBE（P1，本轮押注）**：失败探针 + conformal 校准 + 世界模型偏差监测，统一驱动所有介入式插件（重抓/让位/仲裁）的触发质量；近零成本、不依赖 F7/F8。
- **IP-13 深化**：训练介质三选一→三介质分层（自训结构化 WM → WMA-0 → Isaac Lab），新增 Q-chunking 式 chunk critic 与第 5 道闸（沙盘保真度门）；PBT 观察项不启用。
- IP-2 加第四消费者、IP-3 失败归因升级、IP-4 遥测加角色日志与校准分数、IP-7 加合成失败样本、IP-9 明确映射、IP-10 拒绝清单 +1 且 #8 修订、IP-11/12 触发阈值改由 IP-15 供给；无删除项。

**战略层判断（本轮最重要）**：官方已开源 UnifoLM-WLA-1.0-Base（6B，配套 UniBot-V1 数据）+ WMA-0 世界模型（含 Dual 双臂权重）+ Isaac Lab 仿真（同 DDS 协议）+ RL 工具链——**"基座+沙盘"已成所有参赛队的公共物品**。榜单 <30% 的瓶颈因此更可能落在末段细节与扰动泛化，恰是 IP-11/12/13/14/15 的差异化地带。基座选型从开放问题收敛为：**默认主干=官方栈（A7 跑通基线），插件即护城河**。路线无关原则不变：所有 IP 仍以可消融插件接入。

## 1. 事实卡更新（检索日期 2026-11-07）

F1-F18 与第 27 轮一致（本轮重验：官方三页仍 Coming Soon [R1/R1a/R2]；repo 仍 2 commits [R3]；HF 集合 32 项、lastUpdated 2026-09-11 [R4]）。新增：

| # | 事实 | 来源 |
|---|---|---|
| F19 | 官方 UnifoLM 家族全栈开源：WLA-1.0-Base（6B/2500h 真机数据/64 任务/LoRA 微调代码/Model Server，明确配套 UniBot-V1 数据集）；WMA-0 世界模型（仿真引擎+Policy Enhancement，**有 Dual 双臂权重**，CC BY-NC-SA）；VLA-0；统一规范 54 维动作/60 维状态+掩码、chunk 30@30fps、SE(3) 增量、分位归一化 | [R8a/R8b/R8c] |
| F20 | 官方沙盘与 RL 工具链：unitree_sim_isaaclab（G1/H1-2，**与真机同一 DDS 协议**，用途含采集/回放/生成/模型验证，需 RTX 3080-4090）；unitree_rl_lab（IsaacLab RL 环境，G1-29dof）；unitree_mujoco → 第 27 轮"无环境"前提被部分推翻 | [R9][R10] |
| F21 | 官方公开 bimanual 资产：Z1_Dual_Dex1_*（叠盒/倒咖啡/叠衣/收铅笔）、G1_Dex1_DualRobot_Clean_Table、WMA-0-Dual 权重、UnifoLM-WBT 集合 | [R4][R8b] |
| F8' | **SANDBOX-GAP（新缺口）**：两个官方沙盘的 rollout 分布与真机评测的相关性未知；沙盘指标≠官方得分 | 本轮判定 |

行动项：A1-A6 不变；**A7（新增，P0）**：跑通 UnifoLM-WLA-1.0-Base + 32k 演示 LoRA 微调基线（锁定 commit、记录版本；顺带核查 CC BY-NC-SA 许可对竞赛提交的约束）；**A8（新增，P1）**：沙盘保真度探针——held-out 真演示在三介质中的回放分布差异量化（见 E18），不过阈不训 RL。

## 2. 创新点清单 v4 一览

| 编号 | 名称 | 一句话 | 优先级 | 依赖 | 灵感词 | 主成本账户 | 边际分预期 | 状态 |
|---|---|---|---|---|---|---|---|---|
| IP-1 | SLAM-MAP v3 | 四件套+碰撞层 | P0 | 无 | SLAM×碰撞 | 算力(轻)+伪标注 | 位置/未见/人为干扰 +5~15pt | 维持 |
| IP-2 | SCORE-ALIGN | 过程奖励+进度裁判（四消费者） | P0 | 无 | 评测指标 | 重标注近零 | 步骤分+部分分 | 深化 |
| IP-3 | LOCAL-EVAL | 零真机闭环+探针归因+沙盘保真度探针 | P0 | IP-2 | 低成本×可解释 | 算力(1 GPU) | 迭代速度=生命线 | 深化 |
| IP-4 | SUBMISSION-OPS | N端口/延迟/容错+安全挂载点+角色日志 | P1 | 无 | 竞赛×群体 | 部署机 | 免费工程分层 | 深化 |
| IP-5 | DUAL-HEAD | 单模型双解码头 | P2(冻结) | IP-1 | 25轮 | 算力 | 视合规 | 维持 |
| IP-6 | UNSEEN-GRASP | 先看后抓 | 指针 | IP-1/12 | SLAM | 共享 | 未见物品 | 维持 |
| IP-7 | DISTURB-AUG | 扰动合成+失败邻近状态+**合成失败样本（探针标签）** | P1 | 无 | 25轮×RL | 数据(合成) | 人为干扰 | 深化 |
| IP-8 | STEP-EFF | 步骤分效率工程 | P1 | A1 | 25轮 | 零 | 步骤分 | 维持 |
| IP-9 | SWARM-DECODE | soup/蒸馏+自洽投票（多策略委员会，单权重交付） | P1 | IP-2 | 群体×多机器人 | LoRA×K 一次性 | +2~5pt | 深化 |
| IP-10 | COST-LADDER | 三账户+拒绝清单（#8 修订、+1 条 #9） | P0(纪律) | 无 | 低成本 | 全账户 | 防负 ROI | 深化 |
| IP-11 | SAFE-FILTER | CBF-lite 动作护盾（让位激活改由 IP-15 校准） | P1 | IP-4(+IP-1) | 碰撞避免 | CPU <5ms | 尾部风险保护 | 维持 |
| IP-12 | GRIP-GATE | 何时合/合多拢/失败重抓（verify→conformal 校准） | P0 | A6 | 夹爪控制 | 1-2 GPU·天 | 抓取族 +3~8pt | 深化 |
| IP-13 | GRIP-RL | **沙盘三介质**+chunk critic→蒸馏回门控 | P2(门控) | IP-2/7/12+A8 | 强化学习 | 2-4 GPU·天(封顶) | 扰动场景 +2~5pt | 深化 |
| IP-14 | BIMAN-CREW | 双臂冲突检测+主辅仲裁+交接门控 | P1 | IP-12/15 | 多机器人协作 | 1-2 GPU·天 | 双手协调 +2~6pt | **新增** |
| IP-15 | CALIB-PROBE | 失败探针+conformal 校准+WM 偏差监测 | P1 | IP-2/7/13(可选) | 可解释性 | <1 GPU·天 | 全局触发质量+迭代速度 | **新增（押注）** |

## 3. 重点展开一：IP-14 BIMAN-CREW（多机器人协作）

### 3.1 设计——双臂=两个智能体，三组件

1. **冲突检测器（保底信号，决定是否激活）**：双臂目标 slot 相同 / 双臂轨迹胶囊最小间距 < d_min（复用 IP-11 的 FK 胶囊，F15 关节角） / 同 chunk 内双臂同时计划接近同一空间点——任一触发才激活仲裁；否则完全不介入（**保守激活原则**，防"帮倒忙"）。
2. **主-辅角色仲裁头**：轻量 aux head 输出 {left_lead, right_lead, sync_delay}——主-辅分工思想锚定 PA-BiCoop [R7i]；表征锚定 BiRoAD 的角色自适应先验 [R7h]。训练数据：32k 演示的双手协调子集 + 官方 bimanual 资产（F22：Z1_Dual 系列/G1_DualRobot/WMA-0-Dual，跨体态角色先验迁移，零采集成本）。
3. **交接门控**：物体交接瞬间（一手递一手接）用 GRIP-GATE 的连续开度信号（F16：指令开度 vs 实测开度）+ IP-15 校准分数决定接手时机与确认条件——交接是双臂任务最典型的失败点。

### 3.2 伪代码

```python
def biman_crew(chunk_l, chunk_r, obs, calib):
    conflict = detect_conflict(chunk_l, chunk_r, obs, d_min=0.06)   # F15 FK 胶囊
    if not conflict:
        return chunk_l, chunk_r, None                # 保守激活：不触发不介入
    roles = self.arbiter(obs, calib.p_fail)          # {left_lead, right_lead, sync}
    chunk_l, chunk_r = enforce_roles(chunk_l, chunk_r, roles)
    if handover_detected(chunk_l, chunk_r, obs):     # 交接段
        t_take = calib.gated_release(obs, gripper_state)  # IP-15 校准分数
        chunk_give, chunk_take = sync_handover(chunk_give, chunk_take, t_take)
    telemetry.log_roles(roles, conflict)             # 角色分配日志（IP-4/§6）
    return chunk_l, chunk_r, roles
```

### 3.3 成本账与合规

- 算力：训练 1-2 GPU·天（LoRA/aux head）；推理 <5ms；数据 0（官方 bimanual 资产免费，F22）。
- 边际分预期：双手协调类任务 +2~6pt（F7/F8 未知，取保守区间）；碰撞场景与 IP-11 共享收益。
- 合规：仲裁只改双臂动作序列的时序/角色指派，不改任务语义；触发原因与角色日志全量遥测（IP-4），满足 §6 可信度自证；E16 消融必须证明"正常场景零回归"。

## 4. 重点展开二：IP-15 CALIB-PROBE（可解释性，本轮押注）

### 4.1 三组件

1. **失败探针**：backbone 中间层特征（冻结）+ 线性/SAE 轻量头 → 预测 chunk 级/整局失败概率。标签自监督：演示全为成功 → 用 IP-7 合成扰动 rollout 生成可控比例的失败样本（免人工标注）。锚点：VLA 激活含结果预测信息、可提前预警失败 [R7g]。
2. **conformal 校准**：在 held-out 真演示+合成失败样本上校准非一致性分数，输出带覆盖率保证的阈值/预测集 [R7e/R7f]，代替所有手调阈值。**校准分数是唯一触发货币**，统一消费于：GRIP-GATE 重抓触发（IP-12 verify 阈值）、SAFE-FILTER 让位激活（IP-11 人手缓冲）、BIMAN-CREW 仲裁激活（IP-14 冲突判定复核）。
3. **世界模型偏差监测**：动作条件 rollout（自训结构化 WM 为主，A8 过关后可选 WMA-0）与真实下一帧观测比对，偏差超校准分位 → 失败预警。锚点：Foresight 用动作条件世界模型监控长时程操作失败 [R7d]；无失败数据的不确定性失败检测 [R7e]。这是介入式插件的"第六感"，与 IP-11 的几何护盾互补（几何管硬约束，偏差管柔性异常）。

### 4.2 伪代码

```python
class CalibProbe:
    def calibrate(self, heldout_demos, synthetic_failures, alpha=0.1):
        scores = [self.nc_score(d) for d in heldout_demos + synthetic_failures]
        self.q_hat = np.quantile(scores, 1 - alpha)   # conformal 分位
    def watch(self, obs_t, obs_pred=None):
        p_fail = self.probe(self.backbone_feat(obs_t))          # 探针
        dev = self.wm_deviation(obs_t, obs_pred) if obs_pred else None  # WM 偏差
        s = combine(p_fail, dev)                       # 非一致性分数
        return s > self.q_hat, {"p_fail": p_fail, "dev": dev}   # 触发+可读理由
```

### 4.3 成本账与边界

- 算力：探针 <1 GPU·天；校准是后处理（0）；推理 <2ms；数据 0（复用 IP-7 合成失败样本）。
- 边际分预期：不直接加分，而是**全局触发质量**——减少误重抓（步骤分保护，联动 IP-8）、减少漏重抓（成功率）、减少误让位/误仲裁（E15/E16 的误报率指标）；同时是 IP-3 失败归因的主工具（迭代速度乘数）。
- 边界与合规：解释只用于调试假设生成与置信度输出，**不自动改动作**（防不忠实解释造成新风险）；[R7g] 的 SAE 结论基于 OpenVLA，向 WLA 架构迁移需 E17 验收后才进触发链；校准集分布漂移（扰动场景）触发重校准。

## 5. 重点展开三：IP-13 深化——沙盘三介质 + chunk 级 RL

### 5.1 训练介质分层（v3 的"自训 WM"→三介质，验收通道不变）

| 介质 | 保真度 | 成本 | 启用条件 |
|---|---|---|---|
| 自训结构化 WM（v3 原案：slot 特征+ee/夹爪运动学+任务嵌入 → P_grasp/Δprogress/collide） | 物理近似、任务贴合 | 2-4 GPU·天 | 默认第一级（已过记账） |
| WMA-0 官方世界模型（含 Dual 双臂权重） | 外观真、物理近似；**复用不自训** | 推理算力（过账后） | A8 过关 + 许可核查（CC BY-NC-SA，F19） |
| Isaac Lab 仿真（同 DDS 协议，F20） | 物理真、渲染域差 | GPU 3080-4090 + 环境搭建 | A8 过关且前两级不敷使用 |

### 5.2 Q-chunking 式 chunk critic（与 CEM 并列的第二条优化路径）

```
离线先验: 32k 演示 → 行为克隆 chunk 策略（已有）
沙盘在线: 在第一/二级介质中, critic 只输出 chunk 级 Q 值（1 维, 不改主干）
          探索: chunk 级噪声(时序一致, 优于逐步噪声) [R7c]
蒸馏:     最优 chunk 决策回归进 GRIP-GATE 头（与 CEM 路径同出口）
选择:     CEM(3 维动作空间) vs Q-chunking(chunk 评分) —— E14 双路径对比, 取一
```

锚点：Q-chunking 面向 offline-to-online、以 chunk 为探索/评估单元，与评测接口的 action chunk 天然同构 [R7c]。

### 5.3 PBT 观察项与第 5 道闸

- PBT（多工人演化 LoRA、定期淘汰/杂交）[R7b]：与"多机器人协作"的隐喻映射（沙盘里的多工人）。**本轮不启用**——只在 A8 过关且 IP-13 主线出效果后评估，成本账不过即永久观察。
- 四道闸（v3 §5.4）不变，**新增第 5 道**：沙盘保真度门（A8）——任何在沙盘里的训练，先证明沙盘↔真演示的分布差异在阈内。

## 6. 其余 IP 修订摘要（v3→v4 增量）

- **IP-2**：进度裁判第四消费者=CALIB-PROBE 的失败预警先验（p_fail 的进度条件化）。
- **IP-3**：失败归因从"看日志"升级为"探针+校准分数+WM 偏差"三维定位；A8 沙盘保真度探针挂载于此。
- **IP-4**：遥测新增角色分配日志（哪只手负责什么/何时交接/为何仲裁）与校准分数序列——§6 可信度自证材料再扩容。
- **IP-7**：注入器新增产出类型：合成失败样本（探针标签，失败率可控、类型可控——比真实失败更均衡）。
- **IP-9**：明确"多机器人协作"的合法映射=多策略委员会；重申单权重交付约束（通才赛道）。
- **IP-10**：拒绝清单 **#9 不做物理多机器人/多模型在线 ensemble——一切"多"（多策略/多工人/多角色）必须收敛为单权重单机器人交付**；**#8 修订**：不自训像素级世界模型，但**可复用官方 WMA-0 权重**做评估器（过 A8 与许可账后）。

## 7. 实验设计（新增 E16-E18，接第 27 轮 E1-E15）

| 实验 | 设置 | 指标 | 预期 |
|---|---|---|---|
| E16 双臂仲裁 | 演示回放+合成双臂冲突注入（同 slot/轨迹交叠/交接失败三类）；仲裁 vs 不仲裁 | 协调任务代理成功率 / 误仲裁率 / 正常场景成功率降幅 / 角色日志完整度 | 冲突场景失败 -20%；正常场景降幅 <0.5pt |
| E17 校准验证门 | held-out 真演示+IP-7 合成失败样本；conformal 校准 vs 固定阈值 verify | ECE/reliability 曲线 / 失败预警提前量（步数）/ 误报率 / 下游重抓正确率 | ECE <5%；预警提前 ≥3 步；误报 <8% |
| E18 沙盘保真度（A8） | held-out 真演示在自训 WM / WMA-0 / Isaac Lab 中回放 rollout | 状态轨迹分布距离（MMD）/ 视觉距离（FVD）/ 接触事件率差 | 至少一级过阈；据此决定 IP-13 介质阶梯 |

提交纪律不变：冒烟 CI + 单变量 + 48h 校准报告；E16 的误仲裁率与 E17 的校准曲线纳入 CI 检查项。

## 8. 风险登记簿（增量；第 27 轮其余行继续有效）

| 风险 | 等级 | 缓解 |
|---|---|---|
| SANDBOX-GAP：把官方沙盘当真考场（离线漂亮、真机拉胯） | **高（本轮最大）** | A8 保真度探针先行+介质阶梯（最便宜自训 WM 起步）+真演示回放唯一验收+沉没成本封顶 |
| IP-14 仲裁"帮倒忙"（推翻正确分工） | 中 | 保守激活（冲突触发才介入）+conformal 激活阈值+E16 正常场景零回归验收 |
| 探针解释不忠实/跨架构不迁移（[R7g] 基于 OpenVLA） | 中 | 解释不自动改动作；多探针交叉验证；E17 验收后才进触发链 |
| WMA-0-Dual CC BY-NC-SA 许可与提交合规 | 中 | A7 顺带核查竞赛条款；不过关则 WMA-0 仅用于离线实验 |
| 校准集分布漂移（扰动场景下 q_hat 失效） | 中 | 分场景校准+漂移监控+触发重校准 |
| 官方栈演进快（基座/沙盘版本变动） | 低 | A7 锁定 commit 记录版本；插件式架构天然解耦 |

## 9. 来源清单（全部检索于 2026-11-07）

- R1 排行榜页（重验仍 Coming Soon）：https://unibot.unitree.com/leaderboard.html
- R1a 挑战赛页（32 任务/32000 演示/169h；七步提交流程）：https://unibot.unitree.com/challenges.html
- R2 运行记录页（重验仍 Coming Soon）：https://unibot.unitree.com/runs.html
- R3 提交接口规范（重验：仍 2 commits，最新 2026-08-21）：https://github.com/unitreerobotics/unibot_submission
- R4 数据集：HangCup 卡片（lastModified 2026-10-14，规模标签不变）：https://huggingface.co/datasets/unitreerobotics/G1_Dex1_HangCup ；集合（32 项，lastUpdated 2026-09-11）：https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset
- R8 UnifoLM 家族（本轮新核）：
  - R8a UnifoLM-VLA-0：https://github.com/unitreerobotics/unifolm-vla
  - R8b UnifoLM-WMA-0（世界模型=仿真引擎+Policy Enhancement；Dual 双臂权重 CC BY-NC-SA）：https://github.com/unitreerobotics/unifolm-world-model-action ；模型卡 https://huggingface.co/unitreerobotics/UnifoLM-WMA-0-Dual
  - R8c UnifoLM-WLA-1.0（6B/2500h/64 任务/LoRA/Model Server；配套 UniBot-V1 数据集；动作/状态规范 54 维/60 维）：https://github.com/unitreerobotics/unifolm-wla ；规范 https://github.com/unitreerobotics/unifolm-wla/blob/main/docs/robot_action_state_processing_en.md ；ER-1 卡片 https://huggingface.co/unitreerobotics/UnifoLM-ER-1
- R9 unitree_sim_isaaclab（G1/H1-2，同 DDS 协议，数据采集/回放/生成/验证）：https://github.com/unitreerobotics/unitree_sim_isaaclab
- R10 unitree_rl_lab（IsaacLab RL 环境，G1-29dof）：https://github.com/unitreerobotics/unitree_rl_lab
- R7 文献锚点（arXiv API 逐一核实，2026-11-07）：
  - R7a MAPPO: https://arxiv.org/abs/2103.01955
  - R7b Population Based Training: https://arxiv.org/abs/1711.09846
  - R7c Q-chunking（RL with Action Chunking）: https://arxiv.org/abs/2507.07969
  - R7d Foresight（动作条件世界模型失败检测）: https://arxiv.org/abs/2606.23085
  - R7e 无失败数据的不确定性运行时失败检测: https://arxiv.org/abs/2503.08558
  - R7f Conformalized Interactive Imitation Learning: https://arxiv.org/abs/2410.08852
  - R7g Do VLAs Know They Will Fail?（SAE 结果预测表征）: https://arxiv.org/abs/2610.32208
  - R7h BiRoAD（双臂共享+角色自适应表征）: https://arxiv.org/abs/2609.23445
  - R7i PA-BiCoop（主-辅双臂协作）: https://arxiv.org/abs/2606.28192
- 第 25/26/27 轮来源（R5/R6 系列等）本轮未逐一重抓，口径以对应轮记录为准。

## 10. 清单迭代规则（增补，继承第 25/26/27 轮 §10）

0-10.（继承）事实卡核对 / COST-LADDER 记账 / 对手视频锚定 / 接口事实依赖校验 / 窄域原则等全部有效；
11.（新增）**沙盘保真度门**：任何"在沙盘里训练"的 IP 必须先过 A8 探针（沙盘↔真演示回放分布差异量化），不过阈不得投入训练算力——沙盘分数只能排定优先级，不能当验收；
12.（新增）**公共物品原则**：官方开源资产（基座/世界模型/仿真/RL 工具链）默认优先复用；自训/自建仅当复用不可行或构成差异化需要时立项，且立项书必须包含"为何不用官方对应物"一节。
<!-- ARTIFACT:END -->