# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 27 轮 · 「模块化设计 × 目标检测 × 工具调用」：给 12 项清单立宪法——模块契约、检测引擎、确定性工具调用运行时

## 0. 轮次编号与信息核实（先严谨，再发散）

**编号说明**：状态文件已保留第 26 轮（灵感词：低成本方案/群体智能/SLAM）记录；用户消息模板写"第 1 轮"。按「优先深化与修剪、不推倒重来」元规则，本轮记为**第 27 轮**，三个新灵感词当作对 v2 清单（10 项）的深化输入。

**本轮检索核实（全部检索于 2026-11-07，与第 26 轮同日重验）**：

- **对象确认**：unibot.unitree.com 官方四页、GitHub repo、HF 数据集/合集全部可达且口径一致——用户所指即宇树 UniBot 世界挑战赛（Unitree G1 人形机器人、32 项桌面任务、5 类泛化场景、通才模型赛道），无歧义，不涉及其他同名项目。
- **排行榜/运行记录**：两页仍 Coming Soon [R1/R2]——F7 未解除；页面文案（按用户/模型/任务筛选、详情附完整评测视频）与上轮一致，无新承诺。
- **挑战赛页**：32 任务 / 32000 演示 / 169h；得分点满分 100 口径；飞书参赛手册链接未变 [R1a]——F8 未解除。
- **接口 README 全文重读（repo 仍 2 commits，规则未变，本轮消化出四个新细节）**[R3]：
  1. **评测观测目录确认含双腕相机** `cam_left_wrist / cam_right_wrist`（[480,640,3] RGB）——上轮 IP-6 腕-头闭环的腕部输入只是从数据集侧推断，本轮升为评测端确认（新事实 F15）。
  2. **`obs_delta_indices` 是双旋钮**：其键集决定"只传声明的观测键"，其值声明每键时间堆叠；另有 `image_resize` 可逐键降分辨率——两者是 msgpack-over-websocket 传输延迟的第一杠杆，比量化更靠前的免费优化（F16）。
  3. **`observation.language` episode 内不变、无时间轴、offset 恒 [0]**：任务指令（如 "move the block to the target position."）是开放词汇检测的免费 prompt 源——检测引擎不必凭空猜类别名（F16 附带）。
  4. **评测器对 N 台机器人乱序评测、每台固定连一个端口（8765 起连续 N 个）**，且接口含 `reset()`（每 episode 一次）与 `action_chunk_size`（chunk 内顺序执行）——运行时状态机的 reset/trace 切分与端口级容错有了官方锚点（F17/F18）。
- **数据集**：HangCup 1.04k episodes / 194,564 行 / 8.8 GB；collection 32 项更新于 Sep 11 [R4]——F14 无变化。
- **文献锚点（arXiv API 逐一核实，含三处 ID 纠错）**：Toolformer、ReAct、SayCan、Code as Policies、VoxPoser、RoboTool（原题 Creative Robot Tool Use with Large Language Models）、RoboOS、GR00T N1（双系统）、RT-H（层级动作）、DETR、RT-DETR、YOLO-World、OWLv2、Grounding DINO、D-FINE、SAM 2 [R6]。**纠错记录：VoxPoser 实为 2307.05973（初记 2301.12411 是黑洞物理论文）；OWLv2 实为 2306.09683（初记 2306.10007 是 GROOT 传感运动预训练）；RoboTool 实为 2310.13065（初记 2403.03149 是联邦学习论文）**——全表见产物区事实卡。

**结论**：无与上轮冲突的事实；F7（榜单未开）/F8（手册未读）仍是最大信息缺口，「榜首 <30%」保持为未核实工作假设；本轮全部增量来自灵感词对 v2 清单的架构性收拢，而非新事实。

## 1. 三个灵感词拼出的图（直觉先行）

> **模块化设计**回答「系统怎么长大而不失控」：v2 清单已有六个互相咬合的部件（地图、进度预测器、投票裁判、sanitize、N 端口服务、回放探针），再往下长必然变成一坨意大利面。本轮立**模块契约**：每个部件声明输入/输出 schema、延迟预算、失败语义、可替换键、合规折叠开关、成本行——三条好处立刻兑现：①E1-E11（及本轮新增 E12-E15）实验从"改代码"变成"换配置"；②"单模型"合规开关变成配置项——学习型部件可折叠进 VLA 前向作辅助头（字面单模型）也可外挂（最强性能），一键切换，等 A5 澄清，不再需要重构；③N 端口部署=模块复制，与 IP-4 容错天然同构。
> **目标检测**回答「地图的眼睛从哪来」：SLAM-MAP 的一切 slot 都来自检测框——检测器的精度是地图质量的天花板，延迟是实时性的地板。v2 把检测当黑盒 `open_vocab_detect()`，本轮拆开为 **IP-12 DETECT-ENGINE**：头部开放词汇实时检测（YOLO-World/RT-DETR 级）+ 腕部近景快检（蒸馏纳米学生）+ 手部入侵检测（「人为干扰」的事件触发器）+ 中间步轻量跟踪（IoU+KLT，SAM 2 式记忆传播可选）。附带红利：教师在 32k 官方演示帧上的伪标注 = 零成本自监督域内蒸馏（教师→纳米学生），同时喂养重定位外观库（IP-1）、回放评分器（IP-3）、进度预测器（IP-2）。
> **工具调用**回答「谁在什么时候叫醒哪个模块」：Toolformer/ReAct 的教训是"交错显式调用优于端到端硬猜"，桌面遇扰操作恰是典型多步环境。但 <300ms/步的延迟预算和 §6 可信度条款都装不下一个 LLM 路由——**所以调用者是确定性状态机，不是 LLM**：把 IP-1 v2 的 TRACKING/LOST/RELOC/REMAP 状态机升格为运行时核心循环（新增 GRASP_APPROACH/PLACE_APPROACH/DISTURB 态），地图查询/先看后抓/重定位/进度检查/投票裁判/手部事件全部包成带类型 schema 的工具函数，每次调用留痕（trace）——trace 成为赛后失败签名聚类（IP-4/IP-9）的单一事实源，也是 IP-8 效率策略的强制执行者。

核心类比（本轮灵魂）：**模块化设计是"把答题卡分成客观题/主观题/草稿纸三个分区，各区有标准填涂规范——哪区丢分一眼看出"；目标检测是"草稿纸上每个符号都得先用尺子画框——框歪了整张草稿全歪"；工具调用是"考场不许交头接耳（单模型），但桌上有三个服务铃：查地图、找眼镜、看计时器——按铃记录全部留底，赛后复盘一目了然"。**

一句话押注：

> **本轮新增 IP-11 TOOL-RUNTIME（P0）与 IP-12 DETECT-ENGINE（P1），并给全部 12 项立模块契约；最值得押注的单点是 TOOL-RUNTIME——它零算力成本，把已投建的每个模块焊成可审计、可降级、可换件的系统骨架，并把「人为干扰」从感知层升格为状态机的一等公民（DISTURB 态）。**

## 2. 研究日志：三词各自戳中哪个瓶颈（承接第 25 轮四层分解）

| 瓶颈层 | 模块化设计 | 目标检测 | 工具调用 |
|---|---|---|---|
| 数据层（每任务仅 1k、无失败恢复数据） | 契约使伪标注/合成数据源可插拔替换 | 检测器伪标注 32k 演示=零成本数据资产；域内自蒸馏 | 工具结果=结构化数据入 trace，赛后可复用为分析/训练资产 |
| 表征层（无深度、结构扰动靠隐式学习） | 地图/检测/跟踪解耦，各自独立优化 | **全打这一层**：开放词汇+手检+跟踪三路 | — |
| 目标函数层（训练-评测错位） | 学习型部件可折叠为同底座辅助头 | 进度预测器输入由检测框供给 | check_progress/judge 成为显式调用点（错位可见可修） |
| 工程层（N 端口/延迟/可信度） | **全打这一层**：契约/N端口复制/合规开关 | 纳米学生控延迟；事件驱动感知省算力 | 状态机路由+trace+降级语义；声明集=带宽旋钮 |

观察：三个词没有一个指向"更大的模型"——与本循环一贯判断一致；模块化与工具调用是纯工程杠杆（算力≈0），检测是唯一需要选型实验（E13）的词，且在线成本可压到纳米级学生模型。

## 3. 灵感词交点（组合即创新）

- **模块化 × 工具调用 = 契约即工具**：每个模块的对外接口就是它暴露的工具；「状态→工具」路由表是系统唯一的全局知识，改行为=改一张表，不改代码。
- **工具调用 × 目标检测 = 事件驱动感知**：检测不再是每帧必跑的后台进程，而是状态机按需调用的工具（关键帧才全量、抓取前才闭环、手检只在中间步轻量校验）——第 26 轮延迟预算表原封不动。
- **目标检测 × 模块化 = 可替换的眼睛**：教师/学生/开源检测器全部实现同一契约，E13 跑分后配置切换；若 F9 判定评测流未校正，只有 head 路受罪（换单目+平面先验），骨架无损——F9 的爆炸半径从"全链路"缩小为"一个模块"。
- **三词交点 = trace**：每次工具调用的输入/输出摘要+延迟落盘，与 IP-4 遥测、IP-9 赛后失败签名聚类共用同一数据结构。**trace 是本轮把三个词焊在一起的焊点，也是 IP-11 的灵魂。**

## 4. 与第 26 轮清单的深化/修剪决策

| 清单项 | 本轮处置 | 依据 |
|---|---|---|
| IP-1 SLAM-MAP | **深化 → v3**：地图服务工具化（get_map/locate/look_closer/relocate 四工具），检测黑盒拆出移交 IP-12 | 工具调用+目标检测 |
| IP-2 SCORE-ALIGN | 微修订：进度预测器=check_progress 工具；监督输入来自 IP-12 伪标注 | 工具调用+检测 |
| IP-3 LOCAL-EVAL | 深化：契约驱动的消融矩阵（E15 载体），实验=换配置 | 模块化 |
| IP-4 SUBMISSION-OPS | 深化：声明最小键集+image_resize=带宽双旋钮（F16）；trace 遥测统一（F17/F18） | 工具调用 |
| IP-5 DUAL-HEAD | 冻结维持（P2），但解冻条件从"合规未知"精确为"A5 两问的答复"；fold_in 即其合规形态 | 模块化 |
| IP-6 UNSEEN-GRASP | 指针维持；F15 把腕路输入从推断变为确认，与 IP-12 wrist 路对接 | 目标检测 |
| IP-7 DISTURB-AUG | 深化：新增产出手事件序列（帧对+事件标签），喂 E14 与 DISTURB 态 | 目标检测 |
| IP-8 STEP-EFF | 微修订：关键帧/降频策略由路由表强制执行（从"建议"变"机制"） | 工具调用 |
| IP-9 SWARM-DECODE | 微修订：judge 工具化；trace 成为其赛后聚类输入 | 工具调用 |
| IP-10 COST-LADDER | 深化：契约新增 cost_row 字段；拒绝清单新增第 7 条（不上 LLM 路由器） | 低成本+模块化 |
| — | **新增 IP-11 TOOL-RUNTIME（P0）** | 工具调用×模块化 |
| — | **新增 IP-12 DETECT-ENGINE（P1）** | 目标检测 |

无删除项；v2 十项全部存活。

## 5. 风险与本轮最大风险

**最大风险仍是 F9（评测相机映射/校正未确认），但本轮后其爆炸半径从「全链路」缩小为「head 检测路」**——腕部路、手检路、状态机骨架、trace、工具协议全部与 F9 无关。缓解不变：A4 最高优先+单目桌面平面先验备份路（现已成为 DetectEngine 契约下的一个 swap 选项）。

其余新增风险：①「工具调用=运行时外挂」的合规疑虑（[R3] §6+拒绝清单第 6 条）——缓解：确定性工具=算法非模型；学习型工具默认 fold_in；A5 升级为两问（见产物区行动项）；②静态路由表覆盖不了长尾状态迁移——缓解：trace 记录未覆盖迁移，赛后按聚类补表；REMAP 兜底态常在；③手事件误报打断正常抓取——缓解：双帧确认+E14 误报率门槛 <2%；④纳米学生域内精度不足——缓解：教师 int8 兜底（契约 swap_key 一键回退）。

## 6. 下一轮展望（灵感未知）

- 若灵感指向「世界模型/想象」→ 工具表新增 `simulate`：slot 协方差传播的物体级前向想象（第 26 轮已预留），执行前预演 chunk 结果，与进度裁判联合门控；
- 若灵感指向「记忆/案例」→ 工具 `retrieve_similar_episode`：以 trace+失败签名为索引的案例库检索，LOST/DISTURB 态的恢复策略从案例取而非从零猜；
- 若灵感指向「人因/注意力」→ hand 路升级为手部意图预测（伸向哪个 slot→让位/遮挡预判），与 DISTURB 态串成完整干扰响应链；
- 若 F7/F8 解除 → 强制修订：对手评测视频×我方 trace 双证据逐任务拆解；手册得分点定义回填 IP-2。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 27 轮产物 · 创新点清单 v3：TOOL-RUNTIME / DETECT-ENGINE / 模块契约（12 项）

## 0. 结论

第 26 轮清单 v2（10 项）本轮完成一次「架构性收拢」，产出 v3（12 项）：

- **IP-11 TOOL-RUNTIME（P0，新增）**：确定性状态机作路由器（非 LLM），把地图/检测/进度/投票/sanitize 包成带类型 schema 的工具，chunk 边界按静态路由表调用；每次调用留 trace——零算力成本，是其余 11 项的公共骨架（模块契约由 IP-11 承载架构、IP-10 承载成本记账，不单设编号）。
- **IP-12 DETECT-ENGINE（P1，新增）**：头部开放词汇+腕部快检+手部入侵+中间步跟踪四路统一契约；教师在 32k 官方帧上伪标注→纳米学生域内蒸馏；检测从黑盒变可替换的眼睛。
- **模块契约（横切纪律）**：schema/延迟预算/失败语义/swap_key/fold_in/cost_row 六字段——实验矩阵、合规开关、N 端口部署、成本记账共用同一套机制。
- 其余十项微修订（§6）；无删除项；F9 爆炸半径从全链路缩小为一个模块。

路线无关原则不变：IP-2/IP-3/IP-4/IP-10/IP-11 不依赖语义地图路线成立。

## 1. 事实卡更新（检索日期 2026-11-07，同日重验）

F1-F14 与第 25/26 轮一致（F7 榜单 Coming Soon 重验 [R1/R2]；repo 仍 2 commits [R3]）。新增：

| # | 事实 | 来源 |
|---|---|---|
| F15 | 评测观测目录含双腕相机 `cam_left_wrist/cam_right_wrist`（[480,640,3] RGB）→ IP-6 腕路输入由数据集推断升为评测端确认 | [R3] |
| F16 | `obs_delta_indices` 键集决定只传声明的键（带宽旋钮#1）；`image_resize` 逐键降分辨率（旋钮#2）；`observation.language` 无时间轴、episode 内不变（offset 恒 [0]）→ 语言指令=开放词汇检测免费 prompt 源 | [R3] |
| F17 | N 台评测机器人乱序评测，每台固定连一个端口（8765 起 N 个连续端口），每端口须独立可靠完成完整交互 → 端口=状态隔离物理单元、容错粒度 | [R3] |
| F18 | 接口含 `reset()`（每 episode 一次）与 `action_chunk_size`（chunk 内顺序执行）→ 运行时状态机 reset 挂 reset()；trace 按 episode 切分；关键帧策略与 T_a 对齐 | [R3] |

**行动项更新**：A1（手册）/A2（注册）/A3（榜单监控）/A4（相机极线验证，P0）不变；**A5 升级为两问**：①N 的确切数量（F10）；②「单模型」边界——运行时确定性感知模块（检测/跟踪/匈牙利匹配）与同底座学习型辅助头（进度/重排）是否计入模型？（直接决定 IP-11 学习型工具的外挂/fold_in 配置与 IP-5 解冻）。

**文献锚点核实表（arXiv API，2026-11-07；含三处 ID 纠错）**：

| 锚点 | ID | 用途 | 备注 |
|---|---|---|---|
| Toolformer | 2302.04761 | 工具调用 | |
| ReAct | 2210.03629 | 交错推理-行动 | |
| SayCan | 2204.01691 | 技能库=工具前身 | |
| Code as Policies | 2209.07753 | 代码即策略 | |
| VoxPoser | 2307.05973 | LLM 组合 3D 值地图 | **纠错**：初记 2301.12411（实为黑洞论文） |
| RoboTool | 2310.13065 | LLM 创造性调用工具 | 原题 Creative Robot Tool Use with LLMs；**纠错**：初记 2403.03149（联邦学习论文） |
| RoboOS | 2505.03673 | 分层具身框架/工具编排 | |
| GR00T N1 | 2503.14734 | 双系统（S1 快/S2 慢） | 模块化锚点 |
| RT-H | 2403.01823 | 语言作中间层的层级动作 | 模块化锚点 |
| DETR | 2005.12872 | 检测范式 | |
| RT-DETR | 2304.08069 | 实时检测基线 | |
| YOLO-World | 2401.17270 | 实时开放词汇 | |
| OWLv2 | 2306.09683 | 开放词汇教师候选 | **纠错**：初记 2306.10007（实为 GROOT） |
| Grounding DINO | 2303.05499 | 开放词汇教师候选 | |
| D-FINE | 2410.13842 | 实时检测学生候选 | |
| SAM 2 | 2408.00714 | 记忆式视频跟踪 | track 路可选实现 |

## 2. 创新点清单 v3 一览

| 编号 | 名称 | 一句话 | 优先级 | 依赖 | 灵感词 | 主成本账户 | 边际分预期 | 状态 |
|---|---|---|---|---|---|---|---|---|
| IP-1 | SLAM-MAP v3 | 地图服务=四工具（get_map/locate/look_closer/relocate），检测移交 IP-12 | P0 | IP-11,IP-12 | SLAM(26轮) | 算力(轻)+伪标注(近零) | 位置/未见/人为干扰 +5~15pt | 深化 |
| IP-2 | SCORE-ALIGN | 进度裁判=check_progress/judge；监督来自检测伪标注 | P0 | IP-11,IP-12 | 评测指标(25轮) | 数据(近零) | 步骤分+部分分 | 微修 |
| IP-3 | LOCAL-EVAL | 回放闭环+契约驱动消融矩阵（E15 载体） | P0 | IP-2,IP-11 | 低成本(26轮) | 算力(1 GPU) | 迭代速度=生命线 | 深化 |
| IP-4 | SUBMISSION-OPS | N端口容错+trace 遥测+带宽双旋钮（F16/F17） | P1 | IP-11 | 竞赛(25轮) | 部署机 | 免费工程分 | 深化 |
| IP-5 | DUAL-HEAD | 学习型工具 fold_in=同底座辅助头 | P2(冻结) | A5 | 25轮+模块化 | 算力 | 视合规 | 冻结维持 |
| IP-6 | UNSEEN-GRASP | =look_closer+IP-12 wrist 路（F15 确认输入） | P1 | IP-1,IP-12 | 检测(本轮) | 共享 | 未见物品 | 指针 |
| IP-7 | DISTURB-AUG | 干扰合成+手事件序列喂 E14/DISTURB 态 | P1 | IP-12 | 25轮 | 数据(合成近零) | 人为干扰 | 深化 |
| IP-8 | STEP-EFF | 效率策略由路由表强制执行 | P1 | IP-11 | 25轮 | 零额外 | 步骤分 | 微修 |
| IP-9 | SWARM-DECODE | judge 工具化；trace 喂赛后聚类 | P1 | IP-2,IP-11 | 群体(26轮) | 算力(一次性) | 全场景 +2~5pt | 微修 |
| IP-10 | COST-LADDER | 三账户+模块级 cost_row+拒绝清单第 7 条 | P0(纪律) | 无 | 低成本(26轮) | 全账户 | 防负 ROI | 深化 |
| IP-11 | TOOL-RUNTIME | 确定性状态机+typed 工具+trace 单一事实源 | **P0 新增** | 无 | 工具调用×模块化 | 算力(≈0) | 其余 11 项的骨架 | 新增 |
| IP-12 | DETECT-ENGINE | 三路检测+跟踪+教师→学生伪标注自蒸馏 | **P1 新增** | 腕路无；头路 F9 | 目标检测 | 算力(E13 一次性) | 地图质量天花板+事件触发 | 新增 |

## 3. 重点展开一：IP-11 TOOL-RUNTIME（工具调用运行时）

### 3.1 定位与合规设计

- **不是新模型**：VLA 是唯一策略模型；工具分两类——确定性算法工具（匈牙利/EMA/反投影/阈值/KLT，合规无虞）与学习型小头（check_progress、locate 重排器），后者带 **fold_in 开关**：外挂运行（最强性能）↔ 折叠进 VLA 前向作同底座辅助头（字面单模型）。A5 答复前默认 fold_in 或冻结。
- **路由器是确定性状态机，不是 LLM**：①<300ms/步装不下；②§6 可信度条款偏好确定性交互；③静态表可被 trace 审计。IP-10 拒绝清单第 7 条：本轮循环不上 LLM 路由（留 P2 观察位）。
- **降级语义**：每个工具声明失败返回（None→路由表给默认动作），运行时永不因工具失败停机。

### 3.2 工具注册表（typed schema）

```python
# 工具 = (输入, 输出, 延迟预算, 失败语义, fold_in)
TOOLS = {
  "get_map":        (MapQuery,   SlotList,    "<1",  "return_None", False),  # 地图快照查询（O(n_slots) 内存读）
  "locate":         (Desc,       SlotRef,     "5",   "return_None", True ),  # 开放词汇定位（指令名词短语 prompt，F16）
  "look_closer":    (SlotRef,    SlotRef,     "15",  "return_None", False),  # 腕-头闭环（仅抓取前一步）
  "relocate":       (None,       RelocStatus, "20",  "return_None", False),  # LOST 后重关联（IP-1 v2）
  "check_progress": (ChunkCtx,   ProgScore,   "3",   "return_None", True ),  # 进度裁判（IP-2）
  "judge":          (CandList,   Cand,        "2",   "argmax_c0",   False),  # K 路投票破平（IP-9）
  "sanity":         (Action,     Action,      "1",   "passthrough", False),  # 动作 sanitize（IP-4）
  "hand_watch":     (None,       HandEvent,   "10",  "return_None", False),  # 手部入侵事件（关键帧+校验步）
  "log_event":      (Event,      None,        "<1",  "passthrough", False),  # trace 落盘
}
# 关键帧全量感知成本记在 DetectEngine.head（40ms/关键帧），不占 get_map 预算
```

### 3.3 状态机路由表（IP-1 v2 状态机升格）

```
每 chunk 边界执行；reset() 时归 TRACKING（F18）
TRACKING        : [关键帧?] DetectEngine.head → get_map → hand_watch → sanity(get_action(obs))
GRASP_APPROACH  : look_closer(target) → sanity(get_action(obs))          # 先看后抓（IP-6）
PLACE_APPROACH  : check_progress → sanity(get_action(obs))               # 放置确认/完成判定
LOST            : relocate() → 成功→TRACKING / 超时→REMAP                # 人为干扰后（IP-1 v2）
DISTURB         : log_event(hand_event) → relocate() → 让位动作           # 手事件双帧确认后（IP-7 联动）
REMAP           : get_map(full_scan) → 重建 slots → TRACKING              # 兜底态
```

与 v2 差异：v2 状态机只管地图跟踪；v3 把「抓取前看一眼」「放置前查进度」「手进来先让位再重找」三类时序决策从模型隐式猜测升为显式调用——**每类恰好对应一个泛化场景**（未见物品/背景+干扰物/人为干扰）。

### 3.4 trace：单一事实源

```python
@dataclass
class ToolTrace:
    t: float; episode: int; port: int; state: str; tool: str
    args_digest: str; result_digest: str; latency_ms: float
# 失败签名 = (task, state@fail, last_tool, result_delta_hash)
# trace 与 IP-4 遥测、IP-9 赛后聚类共用同一结构；按 episode 切分（F18）
# 未覆盖状态迁移也记为 trace 事件 → 赛后补路由表
```

锚点：Toolformer/ReAct（交错调用优于硬猜）[R6a/R6b]、SayCan（技能库）[R6c]、Code as Policies/VoxPoser/RoboTool（LLM 生成式调用——我方取其"显式化"思想、弃其 LLM 路由）[R6d/R6e/R6f]、RoboOS（分层具身编排）[R6g]、GR00T N1 双系统/RT-H 层级动作（模块化先例）[R6h/R6i]。

### 3.5 延迟预算增量（接第 26 轮 §3.5 表）

| 环节 | 增量 | 说明 |
|---|---|---|
| 工具簿记+路由 | <1ms/chunk | 纯函数调用+dataclass 填表 |
| hand_watch | 10ms/关键帧 | 学生模型；中间步只做轻量校验 |
| look_closer / relocate | 15ms / 20ms | 仅特定状态触发（第 26 轮已有） |
| 其余 | 不变 | 关键帧降频与 T_a 对齐（F18） |

## 4. 重点展开二：IP-12 DETECT-ENGINE（目标检测引擎）

### 4.1 三路检测+一路跟踪，统一契约

```python
class DetectEngine(ModuleContract):
    def head(rgb_l, rgb_r, prompts) -> Dets     # 开放词汇+实例化；关键帧 40ms
    def wrist(rgb, bank)            -> Dets     # 近景快检（纳米学生）+开放词汇兜底；抓取前 15ms
    def hand(rgb)                   -> HandDets # 手/前臂入侵事件；关键帧+校验步 10ms
    def track(dets_prev, rgb)       -> Dets     # IoU+KLT 轻量传播（SAM 2 记忆式可选）；中间步 8ms
```

四路对应五类泛化场景：head 路（位置变化/背景/干扰物：开放词汇+crop embedding 判别相似干扰物）；head 路 locate（未见物品：F16 语言指令=免费 prompt）；hand 路（人为干扰：事件触发 DISTURB 态）；wrist 路（未见物品+抓取精度：近景小目标，F15）；track 路（全部：中间步低成本延续）。

### 4.2 伪标注自蒸馏闭环（零真机成本）

```
教师（OWLv2 / Grounding DINO 级，离线，仅本地跑）
  └─ 伪标注 32k 官方演示帧（194,564 行 × head_stereo×2 + wrist×2 裁帧）
       ├─ slot 外观 embedding 库（重定位验证集，IP-1 v2 已用）
       ├─ 本地回放评分器（IP-3）/ 进度预测器监督（IP-2）
       ├─ E13 评测集（500 帧伪标注 + 100 帧人工校验）
       └─ 蒸馏纳米学生（RT-DETR / D-FINE-nano，域内帧上微调蒸馏）
在线：学生跑 head/wrist/hand 路（延迟预算内）；教师 int8 兜底（swap_key 一键回退）
```

选型规则（cost-score）：域内 mAP@0.5 学生 ≥ 教师-2pt → 在线用学生；否则教师量化。检测器=可替换眼睛：候选实现同一契约，E13 跑分后配置切换。

### 4.3 F9 弹性

若 A4 判定评测流未立体校正：head 路换「单目+桌面平面先验」（已知桌面高度反投影 3D，第 26 轮已预研）——只有 head 路一个模块受罪，engine 契约与骨架无损。wrist/hand/track 路与 F9 无关。

## 5. 重点展开三：模块契约规范（MODULAR-CONTRACT，横切纪律产出）

```python
@dataclass
class ModuleContract:
    name: str; inputs: type; outputs: type       # 类型化 schema
    latency_budget_ms: float                     # 超限=违约，冒烟 CI 拦截
    failure_semantics: str                       # raise / return_None / degrade_to:<module>
    swap_key: str                                # 同契约实现互换（E13 换装、F9 备份）
    fold_in: bool                                # 可否折叠进 VLA 前向（合规开关，A5）
    cost_row: tuple                              # IP-10 记账（账户, 边际分预期）
```

三条立刻兑现的好处：①E1-E15 实验矩阵=换配置（E15 的 2^4 消融从工程噩梦变枚举器）；②合规开关=配置项（IP-5 解冻即一键，无重构）；③N 端口部署=模块复制（IP-4 两种官方部署方式映射为复制粒度选择，F17）。示例：DetectEngine（§4.1）与 ProgressHead（inputs=ChunkCtx{检测框序列, gripper 开度, chunk idx}，outputs=ProgScore，budget=3ms，fold_in=True，cost_row=("算力-训练","步骤分+2pt")）。

## 6. 其余 IP 修订摘要（v2→v3 增量）

- **IP-1**：地图服务=四工具（§3.2/§3.3）；检测黑盒移交 IP-12；四件套（外参/重定位/腕头闭环/关键帧协方差）不变，只是获得统一调用协议。
- **IP-2**：进度预测器=check_progress 工具；监督输入新增 IP-12 伪标注的物体级事件序列（"已抓起/已对准/已放入"→过程奖励骨架更细）。
- **IP-3**：新增契约驱动的消融矩阵执行器（E15）；检测评测集构建纳入其职能。
- **IP-4**：新增带宽双旋钮（声明最小键集+image_resize，F16）；trace 遥测格式定稿（F17/F18）；容错粒度=端口不变。
- **IP-5**：冻结维持；解冻条件=A5 两问答复；fold_in 形态已由契约预留。
- **IP-6**：指针维持；F15 确认腕路输入；实现载体=IP-12 wrist 路+look_closer 工具。
- **IP-7**：新增产出手事件序列（干扰前后帧对+事件标签），喂 E14 与 DISTURB 态训练。
- **IP-8**：关键帧/降频/确定性解码策略由路由表强制执行；步骤分公式仍待 A1。
- **IP-9**：judge 工具化（batch 并行不变）；赛后聚类输入从"遥测"统一为 trace。
- **IP-10**：契约 cost_row 字段；拒绝清单第 7 条：不上 LLM 路由器（<300ms 预算+可信度条款）。

## 7. 实验设计（新增 E12-E15，接第 26 轮 E1-E11）

| 实验 | 设置 | 指标 | 预期 |
|---|---|---|---|
| E12 运行时开销与迁移覆盖 | 注入故障：强制 LOST/伪手事件/RELOC 超时/工具返回 None | 簿记延迟、迁移正确率、trace 完整率、不停机率 | <1ms/chunk；100%/100%/100% |
| E13 检测选型 | {OWLv2, Grounding DINO, 蒸馏学生 nano, YOLO-World} × {head, wrist}；500 帧伪标注+100 帧人工校验 | mAP@0.5（未见物品 split 单列）、延迟、换装后本地回放成功率增量 | 学生≥教师-2pt→上学生；head 路延迟 ≤40ms |
| E14 手事件检测 | 注入手部{进入, 移物, 挡视线}三类 | 事件 recall/precision、触发延迟、正常轨迹误报率 | 触发 <200ms；误报 <2% |
| E15 模块消融矩阵 | {map, look_closer, judge, relocate(v1/v2)} 2^4 组合 × 本地回放子集（各 ~200 episodes） | 各组合成功率 | 验证各 IP 边际分预期——IP-10 记账从预期变实证 |

提交纪律不变：冒烟 CI+单变量+48h 校准报告；契约 latency_budget 纳入 CI。

## 8. 风险登记簿（增量；第 25/26 轮其余行继续有效）

| 风险 | 等级 | 缓解 |
|---|---|---|
| F9 相机映射/校正未确认 | 高（维持最大，但爆炸半径缩小为 head 路） | A4 不变；单目+平面先验=契约内 swap 选项 |
| 工具调用被认定"运行时外挂"（A5 未决） | 中高 | 确定性工具=算法；学习型默认 fold_in；A5 两问 |
| 静态路由表漏长尾迁移 | 中 | trace 记未覆盖事件；赛后补表；REMAP 兜底 |
| 手事件误报打断正常操作 | 中 | 双帧确认；E14 误报门槛 <2% |
| 学生检测器精度不足 | 低 | 教师 int8 兜底（swap_key 回退） |
| 契约纪律流于形式 | 低 | E15 消融与 CI 超限拦截强制契约"真用" |

## 9. 来源清单（全部检索于 2026-11-07）

- R1 排行榜页（Coming Soon 重验）：https://unibot.unitree.com/leaderboard.html
- R1a 挑战赛页（32 任务/32000 演示/169h；七步参赛流程；得分点 100 分口径）：https://unibot.unitree.com/challenges.html
- R2 运行记录页（Coming Soon 重验；"完整评测视频"承诺）：https://unibot.unitree.com/runs.html
- R3 提交接口规范（README §1 接口/reset/chunk / §2 观测目录含双腕相机+obs_delta_indices+image_resize / §3 动作目录 / §4 token / §5 N 端口与两种部署 / §6 可信度条款；repo 仍 2 commits）：https://github.com/unitreerobotics/unibot_submission
- R4 数据集卡片（1.04k episodes / 194,564 行 / 8.8 GB；head_stereo rectified；state_torso/state_d435）：https://huggingface.co/datasets/unitreerobotics/G1_Dex1_HangCup ；collection（32 项，Sep 11）：https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset
- R6 文献锚点（arXiv API 核实，2026-11-07；三处 ID 纠错见 §1 表）：
  - R6a Toolformer: https://arxiv.org/abs/2302.04761
  - R6b ReAct: https://arxiv.org/abs/2210.03629
  - R6c SayCan (Do As I Can, Not As I Say): https://arxiv.org/abs/2204.01691
  - R6d Code as Policies: https://arxiv.org/abs/2209.07753
  - R6e VoxPoser: https://arxiv.org/abs/2307.05973
  - R6f RoboTool (Creative Robot Tool Use with Large Language Models): https://arxiv.org/abs/2310.13065
  - R6g RoboOS: https://arxiv.org/abs/2505.03673
  - R6h GR00T N1: https://arxiv.org/abs/2503.14734
  - R6i RT-H: https://arxiv.org/abs/2403.01823
  - R6j DETR: https://arxiv.org/abs/2005.12872
  - R6k RT-DETR: https://arxiv.org/abs/2304.08069
  - R6l YOLO-World: https://arxiv.org/abs/2401.17270
  - R6m OWLv2: https://arxiv.org/abs/2306.09683
  - R6n Grounding DINO: https://arxiv.org/abs/2303.05499
  - R6o D-FINE: https://arxiv.org/abs/2410.13842
  - R6p SAM 2: https://arxiv.org/abs/2408.00714
- 第 25/26 轮来源（含 R5a-R5g）本轮未逐一重抓，口径以第 26 轮记录为准；官方页面重验见 R1/R1a/R2/R3/R4。

## 10. 清单迭代规则（增补，继承第 26 轮 §10）

0-8.（继承）事实卡先行；COST-LADDER 记账；榜单上线后对手锚定以评测视频为第一证据源；
9.（新增）**无契约不立项**：新 IP/模块必须先过模块契约六字段（schema/延迟预算/失败语义/swap_key/fold_in/cost_row）；契约缺失连续两轮的清单项降级或合并；
10.（新增）**trace 单一事实源**：赛后清单修订必须引用运行时 trace 聚类（失败签名），不得只引用分数；榜单上线后 trace+评测视频（F13）为双证据源。
<!-- ARTIFACT:END -->