# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 35 轮 · 三灵感落地 v2：VLM 判别器 × CTC 式进度对齐 × 差异化定位

> 承接第 34 轮（v11：LoRA 专家银行 + 进度 critic + 四足先验裁剪）。本轮灵感词「视觉语言模型 / 语音识别 / 差异化定位」的运气极好：一词是旗舰主干（VLM），一词**通道不存在但方法论可整建制迁移**（语音识别 → CTC 对齐），一词同时是技术路线与竞争策略（定位）。且上轮行动项 A16 在本轮直接完成，拿到改变设计重心的一手数据。

## 0. 联网核实（先事实后推理；检索口径 2026-11-08）

- **事实 H（通道诚实复核，github README 全文 grep 2026-11-08）**：全文无 audio/speech/voice/microphone 字样；obs = 4 相机 + 本体 + `observation.language`（str，每 episode 一条，无时序堆叠）。**「语音识别」作为输入通道不成立**——遵守规则 27/31：通道裁剪、方法论保留。
- **事实 I（★★本轮最关键；上轮行动项 A16 完成）**：32 任务的 `meta/tasks.parquet` 全部直取得手（pyarrow 解析），**每任务恰 5 条指令同义变体，共 160 条**（如 HangCup："Hang the cup on the marked spot on the cup rack." ↔ "Hook the cup onto the marked spot of the cup rack."）。两个推论：
  1. **语言鲁棒是官方内置设计目标**——评测指令很可能不总是 canonical 措辞（R75 证实 VLA 对改写敏感），指令增强必须做且要贴官方分布；
  2. **指令文本编码了任务结构**：32 条 canonical 指令显式子句均值 1.66（总 53），**8/32 含顺序/颜色/位置约束**（"from right to left in the order: red, green, yellow" / "the first socket" / "two on the bottom and one on top" / "one by one"）。**指令文本 = rubric 粒度的免费下界**——上轮"步骤分口径未核实（A15 登录墙）"的风险，第一次有了可量化的先验锚点。
- **事实 J（文献，arXiv API 实时检索 2026-11-08）**：立体×VLA 谱系（StereoPolicy 2605.09989、ExStereo 2610.04805、EATR-Stereo 2608.17453 人形双目 token 路由、StereoEngine 2610.12734）；VLM 判别器谱系（VLMs as Success Detectors 2303.07280、**No Free Checker 综述 2609.09250**、D&A 零样本奖励 2611.03622）；指令改写鲁棒（Paraphrase Consistency 2610.19438）；运行期防护（ActFovea 2607.29169、OGAM 2610.05878）。
- 上轮 F24（接口/§6 可信度指标）、F31（定基座）复核不变。

## 1. 研究者直觉（先直觉与动机，后形式化）

**直觉 1（语音识别的"遗产迁移"）**。语音识别被通道事实 H 清零，但 ASR 四件套在本赛道有精确同构物：

| ASR | 本赛道同构物 |
|---|---|
| CTC 单调对齐（输入长、输出短、路径单调、存在空白段） | 示范帧 → rubric 子步骤的对齐（桌面操作的"调整/静止期"天然对应 blank） |
| 流式解码 | 运行期低时延进度估计（IP-25 口） |
| LM beam 重打分 | 卡住时对 System-1 动作块候选做"进度前瞻重打分" |
| 热词偏置 | 语言指令对视觉注意力的偏置（TRI-FUSE cross-attention 已有，不加码） |

上轮 IP-28 v1 的"change-point 点估计 + 单调化"正是 CTC 的**退化版**（Viterbi 硬对齐 + 手工正则）——本轮升级为**边缘化所有对齐路径的软对齐**，对变点噪声鲁棒。这是"迭代不推倒"的教科书场景：v1 的三线索融合保留为**线索提取器**，v2 只替换监督信号的形式。

**直觉 2（VLM 不止是 backbone，还是"考官"）**。上轮 VLM 只当 System-2 主干（IP-21/29）。R72–R74 谱系表明 VLM 判别"子步骤是否达成"是成熟且廉价的能力（共享特征 + 轻头）。与直觉 1 咬合：**CTC 对齐给连续进度，VLM 判别给离散步完成事件，互校出双保险**——两者错误模式相关度低（过/欠分割 vs 视觉歧义/遮挡），不一致样本几乎必是标签错误，进仲裁池集中处理。同一信号服务四处：训练标签去噪、运行期子目标切换（IP-23）、部分分计分器（E37 本地代理）、训练数据清洗（IP-29 专家训练前剔除 bad demo）。

**直觉 3（差异化定位 = 技术路线 + 竞争策略双关）**。技术侧：`head_stereo_left/right` 是一手相机但 v11 只当普通视角用——浪费。F31 定基座 ⇒ 场景几何近乎静态 ⇒ **抓取时刻 ee_pose ≈ 物体位姿**（一手 schema 键）可自监督出 SE(3) 弱定位头，支撑 (a) 指令中 8/32 任务的显式空间/颜色约束 grounding，(b) 插入类任务（PlugCharger/PlugInEthernet/Unlock/DisconnectEthernet）的 mm 级接近校正。战略侧：若"榜首<30%"为真（F34 未核实），全体队伍血点在长程+精细任务；我方错位押四件低竞争高边际差量：**可信度指标**（§6 一手确认被记录、榜旁展示，多数队伍会忽视）、**部分分**（rubric 中间态）、**插入精度**、**语言鲁棒**（160 条官方变体免费送）。

**三线汇合点 = 指令文本**。tasks.parquet 是本轮枢纽：它是 (a) 语言增强的官方分布样本（IP-32），(b) rubric 粒度先验（IP-28 v2 互校），(c) 空间约束清单（IP-31 grounding 目标），(d) System-2 语义路由的输入（IP-29）。一个数据文件同时喂四条线——这种"元数据被新灵感词重新照亮"的现象本身登记为新规则 36。

## 2. 灵感词 → 落地线（继承 + 裁剪登记）

- 「**视觉语言模型**」→ **IP-30 VLM-VERIFIER（P0，新增）**：共享 backbone 的子步骤/成功判别头；与 IP-28 互校；只用于**决策**（切步/重试/降级/数据清洗），不用于上报（合规）。
- 「**语音识别**」→ 通道裁剪（事实 H）+ 方法论遗产两条：**(a) IP-28 v2 CTC-PROGRESS（P0，升级）**——上轮 change-point 融合升级为 CTC 软对齐 + 指令先验互校 + 流式解码 + 卡住 beam 重打分；**(b) IP-32 LANG-ROBUST（P1，新增，并入 IP-26 语言轴）**——官方 5 变体 + 槽位化组合 + 字符噪声增强。
- 「**差异化定位**」→ **IP-31 STEREO-LOCATE（P0，新增）**：双目伪深度 + 抓取弱标签的 SE(3) 物体定位，支撑空间 grounding 与插入精度；同时产出**差异化算力矩阵**（四差量优先级）。
- 继承不变：IP-21/22/23/24/25/26/29（主链）、IP-27（P2，跨形态数据仍未确认可得，继续挂起不投算力）、IP-2/3/4/9/10。

## 3. 形式化定义（严谨版；完整展开见产物区 §3.1）

**定义 1（示范与对齐设定）**：示范 ξ=(o_1..o_T)，编码器给帧特征 f_t。v1 三线索（夹爪 0↔4.5 事件、腕部速度/曲率变点、物体位移/光流变点）给候选边界 B={b_1<…<b_K}，分 S=K+1 段；子步骤标签序列 y=(1..S)；引入 blank 符号 ∅。

**定义 2（CTC 软对齐）**：路径 π=(π_1..π_T)，π_t∈{∅}∪[S]，单调不减，折叠算子 B(π)（去 ∅、并相邻重复）满足 B(π)=y。进度头给帧后验 P_φ(π_t|f_t)，损失 L_CTC=−log Σ_{π∈Π(y)} ∏_t P_φ(π_t|f_t)，前向后向递推 O(T·S)。

**定义 3（软进度与运行期流式估计）**：γ_t(s)=α_t(s)β_t(s)/Σ_s′ α_t(s′)β_t(s′)；离线标签 ē_t=Σ_s (s/S)γ_t(s)。运行期只用左上下文滑窗 W：ŝ_t=max_{τ≤t} E_{γ̂_τ}[s]（累计最大保证单调），p_t=ŝ_t/S。

**定义 4（指令先验互校，方向性下界）**：S_lang=|指令子句|（连接词分割，32 条 canonical 人工校验）。一致性条件 **S_lang ≤ S ≤ S_lang + m**（m=2 容差）。方向依据：官方指令由任务设计者撰写，S_lang 是 rubric 步数的**下界**（指令可能省略隐含步），故 S < S_lang 必须合并段、绝不丢弃指令信息；过分割由变点数上界控制。违反者进仲裁池（IP-30 复判 + 人工抽检标定）。

**定义 5（VLM 判别头与互校）**：V_ψ(f_{t−w..t}, z_s)→P(c_s 达成)；正例=Viterbi 边界 b_s 后 δ 帧，负例=b_s 前 δ 帧 + 跨 episode 同场景干扰帧（难负例）。互校量 IoU(CTC 边界, V 切换点) < θ 的样本进仲裁池。

**定义 6（立体弱定位）**：抓取事件 E_c={t*: gripper 0↔4.5 跳变 ∧ 持物≥τ_hold}；弱标签 ŝ_c=ee_pose_gripper_base(t*)（base 系，一手 schema 键）；先验 N(μ_c,Σ_c) 按任务-物体聚合；在线 ŝ_c(t)=μ_c+Δ_θ(左目特征 × 伪深度图)；子目标空间参数化 z_t=(k, c, ŝ_c^goal, τ)。

## 4. 三线耦合与关键决断

耦合（继承 v11 架构，增量标注）：语言（5 变体鲁棒训练，IP-32）+ 双目（伪深度+弱定位，IP-31）+ 本体 → TRI-FUSE → 共享 backbone → IP-29 低频路由 → System-2 子目标 z_t（现在含 IP-31 空间参数化）→ System-1 流匹配 → **IP-28 v2 流式进度 + IP-30 判别双通道互校** → 卡住 beam 重打分 / IP-24 恢复 LoRA / 部分分降级 → IP-25 SLO。

关键决断：
1. **CTC 取代硬阶梯标签**：v1 的 p̂_t 阶梯函数保留为线索提取器（产生边界候选），监督信号改为边缘化对齐（依据：CTC 对对齐噪声的经典鲁棒性；blank 吸收调整期）。
2. **指令先验只当下界**：S_lang ≤ S，不上确等号（指令可能省略隐含步，如姿态/容差要求——诚实登记为 P4 的失败模式）。
3. **VLM 判别只做决策不做上报**：阈值保守（FPR≤5% 优先），假"完成"提前切步的代价大于假"未完成"多试一次；与 CTC 线索、夹爪事件构成三票制。
4. **beam 重打分条件触发**：仅卡住时 N≤2–4；正常路径 N=1 时延增量 <3%；实测超 IP-25 SLO 预算 20% 则 N 降 1 或只在 PlanStep 边界启用。
5. **语言增强贴官方分布**：官方 5 变体全用 + 槽位组合（Hang/Hook × spot/position/place）+ 字符噪声；评测时训练/留出口径分离（规则 37）。

## 5. 本轮最大风险（一句话）

**整个 v2 进度-判别链押注"指令文本 = rubric 下界 + 自监督对齐质量"——若官方步骤分含有指令未提及的隐含步或与子句粒度严重背离，IP-28/30 的监督将系统性偏移**；必须先以 E40（100 episode 人工抽检边界 F1）+ E37（截断部分分代理）证伪，再投入全量训练。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 35 轮产物 · 创新点清单 v12：VLM 判别器 × CTC 式进度对齐 × 差异化定位

> 承接 v11（第 34 轮）。本轮**新增 3 项（IP-30/31/32）、升级 1 项（IP-28→v2，语音识别方法论注入）、其余继承**；上轮行动项 **A16 完成**（32 任务指令全表），A15（rubric 手册）仍登录墙。

## 0. 结论

- 旗舰 **IP-21 UNIBOT-RFM 不变**；System-2（IP-29 LoRA 银行）不变。本轮把**监督与验证层**升级为「**CTC 软对齐进度（IP-28 v2）× VLM 判别（IP-30）双通道互校**」，把**感知层**加装「**双目弱定位（IP-31）**」，把**语言轴**升级为「**官方 5 变体鲁棒训练（IP-32）**」。
- 战略层（差异化定位）：四差量优先——**可信度指标**（§6 被官方记录、榜旁展示）+ **部分分**（rubric 中间态）+ **插入精度**（双目定位）+ **语言鲁棒**（160 条官方变体），错位于"纯成功率"竞争。
- 路线无关原则（继承）+ 通道诚实：事实 H 证明**无音频通道**，语音识别只以方法论遗产进入（CTC/流式/重打分/热词偏置），不造幽灵通道。
- 上轮行动项状态：**A16 ✅（本轮完成，32 任务 × 5 变体全表）**；A15 ❌（登录墙）；A9/A11/A13/A14 沿用。

## 1. 事实卡（新增 F36–F39，检索口径 2026-11-08）

- **F36（通道无音频，github README 全文 grep）**：无 audio/speech/voice/microphone；`observation.language`（str，episode 级，无时序堆叠）是唯一语言输入。§6 可信度指标（时延/波动/动作统计规律）复核不变。
- **F37（★★tasks.parquet 全表，32 仓直取 + pyarrow 解析，上轮 A16 完成）**：每任务 `meta/tasks.parquet` 恰 1 行、`task` 字段内**5 条 @ 分隔指令变体，共 160 条**。canonical 指令显式子句均值 1.66（总 53）；**8/32 含顺序/颜色/位置约束**（ArrangePlates、ColorArrangement、OrganizeTools、PackDoll、PlugCharger、PickOutBatteries、StackBowls、StoreCups）。变体差异呈**槽位模式**：动词（Hang/Hook）× 名词（spot/position/place）× 介词（on/onto/at）。全表见 §3.6。
- **F38（文献谱系，arXiv API）**：R65–R78（§6）；关键三条——No Free Checker（2609.09250，verifier 综述：VLM 判别可行但有成本，"没有免费的检查器"）；Paraphrase Consistency（2610.19438，改写一致性 ≠ 自洽，VLA 对措辞敏感，必须显式训练）；EATR-Stereo（2608.17453，人形双目证据的 token 路由——官方平台同为双目人形，直接可比）。
- **F39（复核不变）**：F24（接口/§6）、F25（数据结构）、F26（32 任务）、F30（动作 schema：`ee_pose_gripper_base[6]` 一手存在）、F31（定基座）、F32（夹爪 0–4.5、非对称）、F33（repo 结构）、F34（榜单/手册不可得，"榜首<30%"待验）。

## 2. 创新点清单 v12 一览

| 编号 | 名称 | 一句话 | 优先级 | 依赖 | 灵感词 | 主成本账户 | 边际分预期 | 状态 |
|---|---|---|---|---|---|---|---|---|
| IP-21 | **UNIBOT-RFM** | 单模型双系统 VLA 覆盖 32 任务 | **P0** | A9,A13 | 机器人基础模型 | 算力(重,一次性) | 主成功率 | 旗舰（继承） |
| IP-29 | LoRA-EXPERT-BANK | K 个能力 LoRA + 语言/首帧低频路由 + 恢复 LoRA | **P0** | IP-21 | LoRA | 算力(中) | 全域成功率+省显存 | 继承 |
| IP-28 | **CTC-PROGRESS (v2)** | 自监督进度升级为 **CTC 软对齐 + 指令先验互校 + 流式解码 + 卡住 beam 重打分** | **P0** | F37,IP-3 | **步骤分 × 语音识别(遗产)** | 数据(标注轻) | 步骤分+长程成功率 | **升级** |
| **IP-30** | **VLM-VERIFIER** | 共享 backbone 的子步骤/成功判别头，与 IP-28 互校；服务切步/重试/降级/数据清洗 | **P0** | IP-28,IP-21 | **视觉语言模型** | 算力(轻) | 步骤分+鲁棒性 | **新增** |
| **IP-31** | **STEREO-LOCATE** | 双目伪深度 + 抓取弱标签 SE(3) 物体定位；支撑空间 grounding 与插入精度；附差异化算力矩阵 | **P0** | IP-22,F31 | **差异化定位** | 算力(轻) | 插入类成功率+grounding | **新增** |
| **IP-32** | **LANG-ROBUST** | 官方 5 变体 + 槽位组合 + 字符噪声指令增强（并入 IP-26 语言轴） | **P1** | F37 | **语音识别(遗产)** | 数据(近零) | 语言泛化 | **新增** |
| IP-22 | TRI-FUSE | 多视图×本体×语言 token 级融合 + 立体伪深度（IP-31 消费方） | P0 | IP-21 | 技术融合 | 算力(中) | 未见物/位置泛化 | 继承 |
| IP-23 | TASK-DAG | 子目标分段（本轮升级：z_t=(k,c,ŝ_c,τ) 空间参数化） | P1 | IP-28,IP-31 | 任务分解 | 数据(轻) | 步骤分+长程 | 继承 |
| IP-24 | FAILURE-MONITOR | 失败预警 + 恢复 LoRA + 部分分降级触发 | P1 | IP-21,IP-29,IP-30 | 泛化监控×安全 | 算力(轻) | 鲁棒性/可信度 | 继承 |
| IP-25 | LATENCY-SLO | 时延 SLO + 少步动作头 + QAT + N 端口并发 + 平滑 | P0 | IP-4,A11 | 接口工程 | 算力(部署机) | 掉请求→0、可信度 | 继承 |
| IP-26 | GENERALIZE-SUITE | 五轴增广（本轮**新增语言轴** = IP-32） | P1 | IP-2,IP-3 | 泛化能力 | 数据(近零) | 全场景 | 继承 |
| IP-27 | QUAD-PRIOR | 跨形态表征先验（不做运动控制） | P2 | 数据可得性 | 四足机器人 | 算力(低) | 未见物泛化 | 挂起（继承） |
| IP-2/3/4/9/10 | SCORE-ALIGN / LOCAL-EVAL / SUBMISSION-OPS / SWARM-DECODE / COST-LADDER | （同 v11） | P0/P1 | — | — | — | — | 继承 |
| IP-1/8/11/13/16–20 | — | — | — | — | — | — | — | 退役/合并（v10/v11） |

## 3. 重点展开

### 3.1 IP-28 v2 CTC-PROGRESS（完整算法设计）

**符号表**：

| 符号 | 含义 |
|---|---|
| ξ=(o_1..o_T) | 一个示范 episode（T≈410 帧；30fps × 13.7s 均值） |
| f_t | 编码器帧特征（TRI-FUSE 输出） |
| B={b_1<…<b_K} | 变点候选边界（v1 三线索融合） |
| S=K+1 | 段数 = 子步骤数 |
| y=(1..S) | 段 id 标签序列 |
| ∅ | blank token（调整/静止/过渡段） |
| π=(π_1..π_T) | 对齐路径，π_t∈{∅}∪[S]，单调 |
| B(π) | 折叠算子（去 ∅、并相邻重复） |
| P_φ(π_t\|f_t) | 进度头帧后验（轻量分类头） |
| α_t(s), β_t(s) | CTC 前向/后向变量 |
| γ_t(s) | 边际后验 P(π_t=s\|f,y) |
| ē_t | 离线软进度标签 = Σ_s (s/S)γ_t(s) |
| S_lang | 指令子句数（F37：均值 1.66，范围 1–3） |
| m | 互校容差（默认 2） |
| W | 运行期滑窗（默认 30 帧 = 1s） |
| N | beam 候选数（默认 1；卡住时 2–4） |
| ε, τ_hold, δ, θ, TAU_FAIL | 卡住阈值 / 持物时长 / 边界裕量 / 互校 IoU 阈 / 失败阈值 |

**算法步骤**：

离线伪标签（一次性）：
1. **线索提取（继承 v1）**：夹爪 0↔4.5 跳变、腕部速度/曲率变点、物体位移/光流变点 → 融合为候选边界 B。
2. **分段数校验（新增指令先验）**：S=K+1 vs S_lang；若 S < S_lang（指令子句下界被违反）→ 以指令子句为锚合并/拆分段；仍冲突 → 仲裁池。
3. **CTC 前向后向**：计算 γ_t(s)，输出软进度 ē_t 与 Viterbi 硬边界（供 IP-30 训练标签与互校）。
4. **仲裁池**：与 IP-30 判别互校 IoU < θ 的样本 → 人工抽检 100 例标定 θ，其余剔除或降权。

训练：`L = L_flow + λ1·L_CTC + λ2·L_mono + λ3·L_verifier`（互校一致样本）+ λ4·router_lb（IP-29，继承）。

运行期（流式）：
1. 每 chunk（T_a 步）末：滑窗 W 内 γ̂_t(s)，ŝ_t=max_{τ≤t}E_{γ̂_τ}[s]，p_t=ŝ_t/S。
2. 卡住检测（继承 v1）：Δp 窗口 < ε。
3. **卡住 → beam 重打分（ASR LM-rescoring 遗产）**：System-1 采 N≤4 候选动作块，以 Δp 前瞻 + IP-30 判别分重打分选 A*；非卡住 N=1。
4. IP-24 判不可挽回 → 部分分最大化降级（继承 v11）。

**复杂度分析**：
- 离线 CTC：每 episode O(T·S)，T≈410、S≤6 → ~3×10³ 基本运算；32k episodes 总 ~10⁸，单 CPU 分钟级，一次性。
- 训练增量：batch 内 O(B·T·S)，相对 VLM 前向 <1%。
- 运行期：滑窗后向 O(W·S)≈240 ops/chunk（可忽略）；IP-30 判别 1 次轻头前向（共享特征，~1–2ms）；beam N=2 时 flow 采样 ×2（+~10ms 量级，需实测），**N>4 禁用**；正常路径时延增量 <3%。
- 显存：进度头 + 判别头 < backbone 参数 1%。

**正确性论证**：
- **P1（对齐鲁棒）**：CTC 边缘化所有合法对齐路径，变点扰动 δb 时梯度由邻近路径分担（对比硬阶梯标签在边界处的梯度跳变）；blank 吸收"调整期"，防止静止段被强加进度。
- **P2（单调性）**：路径约束单调 ⇒ γ 质量单调转移；运行期 ŝ_t 取累计最大 ⇒ p_t 单调；L_mono 显式惩罚残余逆行。
- **P3（部分分下界映射）**：若步骤分 = 按 rubric 步的部分分（解释 A，保守口径），完成前 s 步得分 ≥ total·s/S_max；本方法只需边界**相对顺序**正确——S 偏差只影响归一化斜率，不影响"先做哪步"的决策序。
- **P4（指令先验方向性）**：官方指令由任务设计者撰写（一手 F37），S_lang 是 rubric 步数的**下界**；故互校只允许 S ≥ S_lang；S < S_lang 必须合并段，绝不丢弃指令信息。失败模式：rubric 含指令未提及的隐含步（姿态/容差要求）→ S_lang 低估但不误导方向，m 容差 + 变点线索（会给出更细 K）双向兜底。

**已知风险**：CTC"帧内标签恒定"假设在快速过渡段近似破（blank 过渡缓解）；连接词解析规则脆弱（"and" 既连接子步也连接名词）——解析规则已对 32 条 canonical 指令人工校验（本轮统计口径）；过渡帧被 blank 吸收过多时边界系统性后移（用 δ 裕量 + Viterbi 中点对齐缓解）。

### 3.2 IP-30 VLM-VERIFIER（完整算法设计）

**动机**：CTC 给连续进度，"步完成"是离散事件；VLM 判别（R72–R74 谱系）成熟且廉价（共享特征 + 轻头）。二者错误模式相关度低，互校 = 标签质量双保险（"No Free Checker" R73 提醒：verifier 有成本，故只做轻头 + 保守接入）。

**设计**：
- 头结构：`V_ψ(池化视觉特征窗 f_{t−w..t}, 步文本嵌入 z_s) → P(c_s 达成)`；文本编码用 backbone 自身语言分支（不引入新 LM，省部署内存）。
- 训练标签：正例 = Viterbi 边界 b_s 后 δ=15 帧；负例 = b_s 前 15 帧 + 跨 episode 同场景干扰帧（难负例）+ 时间扰动增强。
- 语言输入：官方 5 变体轮换（F37）→ 判别头天然对措辞鲁棒（与 IP-32 协同）。
- **用途四**：① 标签互校（IoU 仲裁池）；② 运行期步完成检测 → IP-23 子目标切换；③ 部分分计分器（E37 本地代理口径）；④ 训练数据清洗（bad demo 剔除，IP-29 专家训练前置）。
- **合规与安全限制**：只用于内部决策，不上报任何官方通道；阈值取验证集 FPR≤5% 对应点（假"完成"提前切步的代价 > 假"未完成"多试一次）；三票制（VLM 判别 + CTC 线索 + 夹爪事件）方可切步；IP-24 全局兜底（继承规则 30 fail-safe）。

**正确性论证**：
- **P5（互校完备性）**：CTC 错误模式（过/欠分割、边界漂移）与 VLM 错误模式（视觉歧义、遮挡、外观相似）相关度低；IoU 双低的样本几乎必是标签错误 → 仲裁池收益集中。
- **P6（保守阈值安全性）**：FPR≤5% 限定了级联失败率上界；漏检（假阴性）只损失重试机会，由 CTC 连续进度补充（进度仍在涨时不过早重试）。

**风险**：判别头把"看起来像完成"误判为完成（杯子挂在架边未卡入）——缓解：难负例挖掘 + 三票制 + E41 达标才接入切步。

### 3.3 IP-31 STEREO-LOCATE（完整算法设计）

**动机**：F31 定基座 ⇒ 场景几何近乎静态；指令含显式空间/颜色约束（8/32 任务，F37）；插入类任务（PlugCharger/PlugInEthernet/Unlock/DisconnectEthernet）的精度是成功率瓶颈假设之一；`head_stereo_left/right` 是一手相机但 v11 只当普通视角用——浪费。文献支点：StereoPolicy（2605.09989）、ExStereo（2610.04805）、EATR-Stereo（2608.17453，同为双目人形）。

**设计**：
- **伪深度**：d(u,v)=f·B/δ(u,v)；立体匹配用轻量预训练模型或 SGBM 离线蒸馏（480×640，一次前向）。
- **弱标签自监督**：抓取事件 t*（gripper 0↔4.5 跳变 ∧ 持物 ≥ τ_hold）时物体位姿 ≈ `ee_pose_gripper_base(t*)`（base 系，一手 schema 键 F30）；跨 episode 聚合 → 先验 N(μ_c,Σ_c)（按任务-物体）。
- **定位头**：残差修正 ŝ_c(t)=μ_c+Δ_θ(左目特征 × 伪深度图)；输出 SE(3) + 协方差。
- **消费方**：① 子目标空间参数化 z_t=(k,c,ŝ_c^goal,τ)（IP-23 升级，goal 取示范终点分布 + 先验）；② 插入任务接近段末端位姿校正（System-1 ee 模式）；③ 颜色/顺序约束 grounding（IP-32 指令解析 → 目标物体 id → ŝ_c）。
- **差异化算力矩阵（战略产出）**：按（指令约束密度 × 夹爪不对称性 × 插入/堆叠族）分配 LoRA 专家训练优先级；四差量（可信度/部分分/插入精度/语言鲁棒）优先于泛化长尾。

**正确性论证**：
- **P7（弱标签有效性）**：持物 ≥ τ_hold 过滤空夹/打滑；过滤后标签误差 ≈ 夹爪指尖到物体位姿的固定标定偏移，跨 episode 系统性 → 可估计、可扣除。
- **P8（先验紧致性）**：F31 基座静止 + 任务物体集合小 ⇒ Σ_c 小；先验只做粗锚，残差头吸收摆放随机性（每 episode 物体初始位姿随机但场景静态）。

**风险**：多物体任务（FruitSorting 按颜色分拣、PickOutBatteries 电池混块）需"物体身份 × 位姿"联合估计——先做任务主物体单物体版（P0），多物体属性绑定依赖 IP-32 指令解析（P1 增强）；立体匹配在弱纹理桌面不可靠（伪深度只做粗锚，残差头兜底）。

### 3.4 IP-32 LANG-ROBUST（并入 IP-26 语言轴）

- **官方变体全集训练**（合法：在训练集元数据内）；**槽位化组合**：对 5 变体做词对齐 → 提取可替换槽（动词 Hang/Hook、名词 spot/position/place、介词 on/onto/at）→ 组合生成新变体；**字符级噪声**（同音替换/丢冠词，模拟 ASR 常见错误——语音识别的第二处方法论遗产）。
- **口径分离（规则 37）**：训练 4 变体 + 留出 1 变体测泛化，双列报告。
- 依据 R75：改写一致性 ≠ 自洽——必须显式训练，不指望 backbone 自带鲁棒。
- 成本：近零（元数据 + 规则生成）；与 IP-29 路由器、IP-30 判别头的语言输入共享同一增强管线。

### 3.5 v12 架构（增量标注）

```
语言指令(5变体, IP-32 鲁棒训练) ─────┐
4×RGB(双目对; IP-31 伪深度+弱定位) ──┤→ TRI-FUSE(IP-22) → 共享 VLM backbone
本体(arms/ee/grip/lower_body) ───────┘        │
        System-2 = LoRA 银行(IP-29, 低频路由) → z_t=(k,c,ŝ_c^goal,τ)  [IP-23×IP-31]
        │
        ├─ IP-28v2 CTC 流式进度 p_t（滑窗后向 + 累计最大单调）
        ├─ IP-30 VLM 判别 P(c_s 达成)（轻头, FPR≤5%, 三票制）
        │       └─ 离线 IoU 仲裁池 / 在线互校
        ▼
System-1 = 少步流匹配（joint/ee 双表示）→ 动作块 T_a×(双臂+夹爪)
        │  卡住 → beam 重打分（N≤4, 条件触发, ASR 遗产）
        │  + pivot 冻结头（IP-27 遗产, 仅 clip height/angle_z）
        ▼
IP-24 失败监测 → 恢复 LoRA / 部分分降级 → IP-25 SLO（时延+平滑+N端口）
```

### 3.6 附表：32 任务 canonical 指令（F37 一手，每任务 5 变体中的变体 1；共 160 条存于各仓 meta/tasks.parquet）

| 任务 | canonical 指令 | 显式约束 |
|---|---|---|
| HangCup | Hang the cup on the marked spot on the cup rack. | marked-spot |
| ArrangePlates | Place the plates on the rack from right to left in the order of red, green, and blue. | 顺序+颜色 |
| ArrangeTestTubes | Place the test tubes neatly back into the test tube rack. | — |
| ZipUp | Straighten the storage pouch and zip it up. | 2 子步 |
| ColorArrangement | Arrange the blocks from right to left in the order: red, green, yellow. | 顺序+颜色 |
| Unlock | Unlock the lock using the key. | — |
| DisconnectEthernet | Unplug the Ethernet cable from the network port. | — |
| ConveyorSorting | Pick up the food items moving on the conveyor belt and sort them onto the rack on the right by category. | 2 子步+方位 |
| FruitCollection | Put all the fruits into the fruit basket. | — |
| FoldTowel | Fold the towel neatly and place it aside. | 2 子步 |
| OrganizeBookshelf | Put the top book onto the bookshelf. | top 属性 |
| FruitSorting | Place each fruit onto the plate with the matching color. | 颜色匹配 |
| SpellRobot | Arrange the letter blocks to spell "robot". | 字符序列 |
| OrganizePencilCase | Open the pencil case zipper, place all stationery items into the pencil case, and close the zipper. | **3 子步** |
| OrganizeStationery | Put the stationery into the pencil case. | — |
| StackBowls | Stack the three bowls in the order: red, green, blue. | 顺序+颜色 |
| StoreCups | Place the paper cups on the table into the cup rack one by one. | one-by-one |
| OrganizeTools | Place the tools onto the tool rack from right to left. | 顺序+方位 |
| PackDoll | Pack all the dolls into the bag, then place the bag upright in front of you. | 2 子步+姿态 |
| PackBag | Put the pencil case into the backpack and zip it up. | 2 子步 |
| PackPhone | Pack the phone into its packaging box. | — |
| StoreEarphones | Place the earphones into the charging case and put the case into the storage box. | 2 子步 |
| StorePaddle | Put the table tennis paddle into its case and zip it up. | 2 子步 |
| PaperCupStacking | Stack the paper cups in front of you with two on the bottom and one on top. | 数量+拓扑 |
| PickOutBatteries | Pick out the batteries from the blocks and place them into the green box. | 2 子步+颜色 |
| ToolboxStorage | Store all the tools on the table in the toolbox and lock the toolbox. | 2 子步 |
| PlugCharger | Position the power strip properly and plug the plug into the first socket. | 2 子步+**first socket** |
| SyringeWaterTransfer | Transfer water from the large cup to the small cup using a syringe. | 2 子步+工具 |
| PlugInEthernet | Plug the Ethernet cable into the network port. | — |
| PlacePhotoFrame | Open the photo frame and place it on the table. | 2 子步 |
| RemovePinnedNote | Remove the note that is pinned to the board with push pins. | — |
| PourOutMedicine | Unscrew the bottle cap and pour the medicine from the bottle into the container. | 2–3 子步 |

### 3.7 训练/服务伪代码（增量）

```python
def build_pseudo_labels(demos):                      # 一次性离线
    for xi in demos:
        B = changepoints(xi)                         # v1 三线索保留为线索提取器
        S = len(B) + 1
        s_lang = parse_clauses(xi.lang)              # F37 规则(32 条人工校验)
        if S < s_lang:                               # 指令下界(P4): 只合并不丢弃
            B, S = merge_segments(B, s_lang)
        gamma, vit = ctc_forward_backward(feat(xi), S)   # O(T·S)
        xi.e_bar, xi.vit_bounds = soft_progress(gamma, S), vit
        if iou(vit, verifier_switchpoints(xi)) < THETA:
            arbitrate(xi)                            # 仲裁池: IP-30 复判 + 人工抽检
    return demos

def train_v12(demos):
    base, fuse = load_pretrained_vlm(), TriFuseEncoder(...)
    bank   = LoRABank(base, K=6)                     # IP-29 继承
    s1     = FlowActionExpert(steps=4, chunk=T_a, dual=("joint","ee"))
    prog   = ProgressHead()                          # IP-28 v2: 帧后验 + blank
    ver    = VerifyHead(base.lang_dim)               # IP-30: 轻头
    loc    = StereoLocator()                         # IP-31: 残差定位
    for batch in demos:
        f  = fuse(batch.images_stereo, batch.proprio, batch.lang_variant)
        z  = subgoal(batch.lang, loc.locate(batch), bank.route(batch, low_freq=True))
        a  = s1(f, batch.proprio, z)
        L  = flow_loss(a, batch.action) \
           + LAM1 * ctc_loss(prog, f, batch.S) \
           + LAM2 * mono_penalty(prog.p, batch.e_bar) \
           + LAM3 * bce(ver(f, z), batch.reach_labels) \
           + LAM4 * router_lb(bank)
        update(fuse, bank, s1, prog, ver, loc, L)
    bank.recovery = train_recovery(bank, interventions(demos))   # IP-24 遗产
    return base, fuse, bank, s1, prog, ver, loc

def act(obs, state):                                 # 运行期
    f = fuse(obs)
    z = subgoal(obs.lang, loc.locate(obs), state.k)  # 路由低频, IP-31 空间参数
    if state.stuck and state.n_beam > 1:             # 条件触发(ASR LM-rescoring 遗产)
        cands = [s1.sample(f, obs.proprio, z) for _ in range(state.n_beam)]
        A = argmax(cands, key=lambda A: dprog(prog, f, A) + ver.score(f, z, A))
    else:
        A = s1.sample(f, obs.proprio, z)             # 正常路径: 增量 <3%
    p = stream_progress(prog, f, state.W)            # 滑窗后向 + 累计最大 → 单调
    if stuck(p, state.win):        state.mode = "beam_or_replan"
    if failure_monitor(obs) > TAU_FAIL and p < P_DONE:
        state.mode = "partial_credit"                # IP-24 × IP-28 遗产
    return A
```

## 4. 实验设计（新增 E40–E43）

| 实验 | 设置 | 指标 | 门槛/预期 |
|---|---|---|---|
| E40 对齐质量 | CTC v2 vs v1 硬阶梯：100 episode 人工抽检边界 F1；下游任务成功率 | 边界 F1、成功率 | F1(v2) > F1(v1) + 5pt |
| E41 VLM 判别 | AUROC / FPR@90TPR；截断部分分代理 vs 实际；与 CTC 互校 IoU 分布 | AUROC≥0.85、FPR≤5% | 达标才接入切步决策 |
| E42 立体定位 | 插入族（PlugCharger/PlugInEthernet/Unlock/DisconnectEthernet）成功率；定位误差（ee 弱标签 GT 代理） | 成功率、mm 误差 | 插入族 +5pt 或关闭 |
| E43 语言鲁棒 | 训练 4 变体留出 1 变体 vs 单变体训练；字符噪声扰动 | 留出成功率、噪声鲁棒 | 留出 ≥ 单变体 +8pt |
| E36–E39 | 沿用（LoRA 银行 / 部分分 / 跨形态 / pivot） | — | — |
| E30–E35 | 沿用（数据统一 / 闭环 / 泛化 / 时延 / 失败预警 / 消融） | — | — |

**降级机制**：指令解析误判子句 → 退回 v1 纯变点线索 + 人工抽检；VLM 判别不达 E41 门槛 → 只做遥测不接入决策；立体匹配不可用 → 单目残差头（先验锚定）；beam 超 SLO → N=1；A15 rubric 手册到手 → S_lang 升级为 rubric 直读（先验变硬约束）；槽位组合生成劣质变体 → 仅用官方 5 变体。

## 5. 风险登记簿（新增/更新）

| 风险 | 等级 | 缓解 |
|---|---|---|
| **步骤分口径与指令子句粒度背离（隐含步/姿态要求）→ IP-28/30 系统性偏移** | **高** | 指令只当下界（P4）；E40 人工抽检 + E37 截断代理；A15 手册持续攻坚 |
| VLM 判别假阳性 → 提前切步级联失败 | 中高 | FPR≤5% 保守阈值 + 三票制 + IP-24 全局兜底 |
| beam 重打分超时延 SLO | 中 | 条件触发 + N 上限 4 + 实测回退 N=1 |
| 立体弱标签噪声（空夹/打滑/标定偏移） | 中 | 持物过滤 + 系统偏移扣除 + E42 验证 |
| 指令连接词解析脆弱（"and"歧义） | 中 | 32 条人工校验口径 + 只当下界 + 可退回 v1 |
| blank 吸收过度 → 边界系统性后移 | 中 | δ 裕量 + Viterbi 中点对齐 + E40 抽检 |
| （继承 v11）LoRA 路由干扰、自监督噪声、定基座不普适、跨形态数据不明、恢复 LoRA 异动 | 中/中低 | 见 v11 §5 |
| （继承 v10）相机映射、时延异常、多端口隔离、算力 | 高/中 | 见 v10 §6 |

## 6. 来源清单（引用口径：2026-11-08）

**官方/数据（一手）**
- S1 官网 `unibot.unitree.com`；S2 `github.com/unitreerobotics/unibot_submission`（README 全文 grep 复核 F36）；S3 HF collection 32 仓（F25/F26/F30/F31 复核）；S4 参赛手册（feishu，登录墙未获取）——同 v11。
- **S5（★新增）**：32 任务仓 `meta/tasks.parquet` 直取 + pyarrow 解析（F37 全表 160 条指令；本轮 A16 完成）。

**文献（arXiv API 实时检索，2026-11-08；标题+编号，未逐篇读全文）**
- R65 StereoPolicy: Improving Robotic Manipulation Policies via Stereo Perception, 2605.09989
- R66 ExStereo: Lifting 2D Vision-Language-Action Models to 3D with Explicit Stereo Representations, 2610.04805
- R67 EATR-Stereo: Embodiment-Aware Token Routing of Paired Stereo Evidence for Humanoid VLA Control, 2608.17453
- R68 StereoEngine: Scaling Stereo Bimanual Robot Data without Stereo Cameras, 2610.12734
- R69 ActFovea: Runtime Safeguarding for VLA Policies, 2607.29169
- R70 SADP: Subgoal-Aware Diffusion Policy for Long-Horizon Manipulation, 2605.16871
- R71 FlowVLA: Pluggable 3D Flow Learning, 2610.16160
- R72 D&A: Decoupling Description and Assessment Enables VLMs as Zero-Shot Robotic Reward Models, 2611.03622
- R73 No Free Checker: A Survey of Verifiers for Robot Policies, 2609.09250
- R74 Vision-Language Models as Success Detectors, 2303.07280
- R75 Paraphrase Consensus Is Not Self-Consistency: Instruction Reliance and Robustness in VLA Policies, 2610.19438
- R76 OGAM: Object-Grounded Attention Monitoring for VLA Policies, 2610.05878
- R77 Beyond Appearance Shifts: Task-Semantic Action Calibration for VLA Models, 2609.23650
- R78 Decoupling Vision, Language, and Action for Efficient Multi-Task Robot Policies, 2609.18374
- （R41–R64 沿用 v10/v11）

**诚实记录**：A15 rubric 手册仍登录墙；"榜首<30%""5 类泛化"仍未核实；R65–R78 仅标题/摘要级检索；tasks.parquet 变体的"官方评测实际使用哪些措辞"不可知（故训练全用 + 留出测泛化，双列报告）；"抓取时 ee_pose ≈ 物体位姿"的标定偏移量需实测。

## 7. 清单迭代规则（继承 + 第 35 轮增补）

- 继承规则 27（通道诚实）、28（映射验证）、29（时延-可信度 SLO）、30（fail-safe）、31（灵感-现实校验）、32（单模型合规专家化）、33（步骤分双解释）、34（稠密监督不依赖 rubric）。
- **35（新增）：通道不存在时登记方法论遗产去向**——灵感词对应官方通道不存在（如语音→无音频，F36）时，显式登记"通道不成立 + 方法论迁移去向"（ASR→CTC 对齐/流式/重打分/热词偏置），防止后轮把幽灵通道当真实需求。
- **36（新增）：元数据优先且可被重新照亮**——任务结构信息优先从官方元数据（tasks.parquet/info.json/stats.json）一手提取再设计；新灵感词可能激活旧元数据的增量信息（本轮语言词激活 tasks.parquet），须重扫一遍。
- **37（新增）：语言增强的官方分布优先与口径分离**——指令增强以官方变体为骨架（槽位组合），训练/留出口径分离并双列报告。

**本轮最大风险一句话**：v2 监督链押注"指令文本 = rubric 下界 + 自监督对齐质量"，若官方步骤分含指令未提及的隐含步或粒度远细于子句，IP-28/30 将系统性偏移——先以 E40 人工抽检 + E37 截断代理证伪，再投全量算力。

**当前最值得押注**：IP-28 v2 CTC 软对齐 × IP-30 VLM 判别的**双通道互校监督**（一份信号同时喂稠密训练/切步/降级/数据清洗），配 IP-31 双目弱定位补插入精度与空间 grounding，IP-32 用官方 160 条变体把语言鲁棒做成近乎免费的分。
<!-- ARTIFACT:END -->
