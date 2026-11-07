# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 27 轮 · 「预测性维护 × 共享控制 × 手势识别」：GUARD-LOOP——把第 26 轮的"被干扰后补救"升级为"干扰前预判、干扰中仲裁、全程预防性维护"

## 0. 轮次编号与信息核实（先严谨，再发散）

**编号说明**：状态文件已保留第 26 轮（上一轮，灵感词：低成本方案/群体智能/SLAM）记录；用户消息模板写"第 1 轮"。按本循环「优先深化与修剪、不推倒重来」的元规则，本轮记为**第 27 轮**，三个新灵感词作为对第 26 轮清单（IP-1~IP-10）的深化输入，而非新课题。

**本轮检索核实（全部检索于 2026-11-07）**：

- **F7/F13 重验**：排行榜页仍显示"Coming Soon"，页面文案重申榜单"支持按用户、模型、任务筛选"[R1]；运行记录页仍"Coming Soon"，重申"点击详情查看完整评测视频"[R2]。与第 26 轮口径一致，无新事实；F7（榜单未开）与 F8（手册未读）两大信息缺口仍未解除。
- **文献锚点（arXiv API 逐一核实 ✓，2026-11-07）**：Control Barrier Functions 综述（Ames et al.）[R6]、MediaPipe Hands（Zhang et al.）[R7]、HaGRID 手势数据集（WACV 2024）[R8]、Mahalanobis OOD 检测（Lee et al., NeurIPS 2018）[R9]、Hendrycks & Gimpel OOD baseline（ICLR 2017）[R10]。CUSUM/EWMA 为经典 SPC 文献（Page 1954 / Roberts 1959），无 arXiv，如实标注。
- **事实卡**：本轮**零新增**——三词全部落在既有瓶颈的解法侧，没有产生新的"赛事事实"。

**结论**：无与上轮冲突的事实；上轮最大风险 F9（评测相机映射/校正状态）仍未解除，A4 继续挂最高行动项。

## 1. 直觉先行：三个词拼成同一条因果链

> 第 26 轮把"人为干扰"场景的结构性解法押在**重定位**（干扰发生后找回物体）上。本轮三词恰好是这条链的**前三环**：
> - **手势识别**回答"干扰从哪来、往哪去"：评测相机里的人手是"人为干扰"唯一的可观测前兆——手的关键点轨迹比物体位移早 0.5~2s 暴露意图（伸手→接触，先于物体被挪走 5-10cm）。第 26 轮的 SLAM-MAP"只有物体、没有人"，人手是它最盲的一块。
> - **预测性维护**回答"能不能别等坏了再修"：第 26 轮攒了三个事后机制——干扰后重定位（RELOC）、崩溃后故障转移（E11）、chunk 失败后重试。工业预测性维护给这三个事后机制同一个升维方向：**在失效发生前**预测它——地图有"过期度"（staleness）、端口有"健康度"（CUSUM）、chunk 有"失败概率"（p_fail）。
> - **共享控制**回答"干扰正在发生的那 1~2 秒控制权归谁"：继续执行原 chunk（可能与人手相撞）和完全停机（白烧步骤分）之间需要一条连续谱——让位/防御/换目标/加速，权重由意图与失效预测决定，滞回+率限保证平滑，而不是硬阈值开关。

核心类比（本轮灵魂）：**手势识别是"看清考官伸过来的手"；预测性维护是"别等笔被抢走了才找笔——看考官的手就知道他要动哪支笔"；共享控制是"考官改你卷子时先停笔，但眼睛别离开卷子，他一收手立刻接着写"。**

一句话押注：

> **本轮新增 IP-11 INTENT-GUARD（手部感知+意图预测+CBF 式共享控制仲裁）与 IP-12 PREDICT-MAINT（地图/模型/端口三级健康预测+维护窗口+预测性故障转移），并把第 26 轮的固定关键帧升级为"维护窗口"按需调度——最值得押注的单点是「让位停顿即维护窗口」：干扰从纯粹的坏事件变成免费的感知与维护时间片，这是三词交点上唯一零新增成本的结构性收益。**

## 2. 研究日志：三词各自戳中哪个瓶颈（承接第 25/26 轮四层分解）

| 瓶颈层 | 预测性维护的戳点 | 共享控制的戳点 | 手势识别的戳点 |
|---|---|---|---|
| 数据层（每任务 1k、无失败恢复数据、无人手数据） | 失效标签/延迟流全部来自本地回放与探针（免费） | 仲裁权重训练不需要新数据（规则+滞回） | 合成手注入三件套（IP-7 扩容，渲染即标签，近零成本） |
| 表征层（地图"只有物体没有人"） | 三元组轻量健康表征（staleness / p_fail / CUSUM） | 模式-权重连续谱 u 替代离散开关 | 手关键点=新的结构化低维 token（21×3，base 系） |
| 目标函数层（训练-评测错位） | p_fail 失效头=进度预测器第二出口，新增两个消费者 | wait/switch/accelerate 的期望进度比较 | 意图分类标签来自注入器基元（免费监督） |
| 工程层（N 端口/延迟/可信度） | CUSUM 预测性故障转移（E15）；维护窗口按需感知（E16） | 平滑仲裁=能过可信度条款的防御动作 | 中间步手跟踪 ~4ms（复用轻量跟踪通道） |

观察：三词没有一个指向"更大的模型"；与 25/26 轮判断一致——全是结构、纪律与复用层面的杠杆。且三词天然按**感知→预测→行动**排序，拼成一个闭环而非三个孤岛，这是本轮最大的运气。

## 3. 灵感词交点（组合即创新）

- **手势识别 × 共享控制 = 意图驱动仲裁**：u 权重由意图分布与威胁度驱动（滞回+率限），而非硬阈值——防御动作平滑、可解释、可记账（B_def 时长预算）。
- **预测性维护 × 共享控制 = 让位停顿即维护窗口**：DEFEND 期间机器人不动，但感知与重定位照跑——干扰把"停下来的时间"变成"维护的时间"，把干扰的坏处转化为感知机会。
- **手势识别 × 预测性维护 = "哪块地图即将失效"可知**：人手轨迹的目标 slot 预测 → 该 slot 协方差提前放大+列入维护队列——地图的"预防性检修工单"，重定位从"被动触发"变"预约开工"。
- **三词交点 = GUARD-LOOP**：感知（手势）→预测（三级健康）→仲裁（共享控制）→维护（窗口调度），全部复用第 26 轮资产（地图/重定位/进度预测器/注入器/N 端口拓扑），零新增稀缺资源消耗。

## 4. 与第 26 轮清单的深化/修剪决策

| 清单项 | 本轮处置 | 依据 |
|---|---|---|
| IP-1 SLAM-MAP | 微修订：重定位触发源+人手接触事件；"固定关键帧"→"维护窗口"调度（IP-12 执行） | 预测性维护×共享控制 |
| IP-2 SCORE-ALIGN | 微修订：进度预测器增设 p_fail 失效头，新增两个消费者（仲裁调制/换目标决策） | 预测性维护 |
| IP-3 LOCAL-EVAL | 不变（探针体系已覆盖；回放新增可注入手部序列） | — |
| IP-4 SUBMISSION-OPS | 深化：容错从"崩溃后接管"升级为"CUSUM 预警先于崩溃转移"（E15） | 预测性维护 |
| IP-5 DUAL-HEAD | 冻结维持 P2（F8 未解，不投入） | — |
| IP-6 UNSEEN-GRASP | 维持并入 IP-1 腕-头闭环（不变） | — |
| IP-7 DISTURB-AUG | 深化：+合成手注入三件套（手检测集/意图集/前后图像对） | 手势识别 |
| IP-8 STEP-EFF | 微修订：DEFEND 时长计入步骤分效率账，强化 wait-vs-switch 决策价值 | 共享控制 |
| IP-9 SWARM-DECODE | 微修订：DEFEND 期间 K=1+chunk 视界缩短（更快再仲裁）；EXEC 路径不变 | 共享控制 |
| IP-10 COST-LADDER | 记账：新增两 IP 申报算力 ~0.7 GPU·天（一次性），推理账户 <2ms/步 | 纪律 |
| — | **新增 IP-11 INTENT-GUARD** | 手势识别×共享控制 |
| — | **新增 IP-12 PREDICT-MAINT** | 预测性维护 |

无删除项：本轮检索未产生否定证据；两新增项均为增量模块、可消融、可回退到 v2 能力。

## 5. 风险与本轮最大风险

**最大风险：合成手→真人手的域差距叠加意图误判，可能让机器人在评测中频繁无谓让位——不丢物体却丢步骤分；若 E12/E13 不过门槛，GUARD-LOOP 立即降级为"仅维护窗口+第 26 轮重定位"，损失上界=上轮能力（不亏但不赚）。** 缓解：手检测双轨（MediaPipe zero-shot 兜底+合成微调头提效）+防御时长预算 B_def（episode 内防御时间 ≤20%）+E12/E13 门槛先行。

其余新增风险：①手部遮挡/盲区（头相机仰角大时近处人手出画）→ 双视角（头+腕）+误差界自适应膨胀；②CBF 投影的手位置假设（外参前向模型误差传导）→ ε_h 自适应 margin+解析 fallback；③防御动作被判定"不规则交互模式"（README §6 可信度条款）→ 率限+滞回+低通，Jerk/熵检查入冒烟 CI；④外部软件栈（手检测/仲裁器）与"单模型"边界 → 与 SLAM-MAP 感知栈同状态，待 A5 澄清；⑤F9 相机映射未解除（继承，高）。

## 6. 下一轮展望（灵感未知）

- 若灵感指向「世界模型/想象」→ p_fail 失效头升级为物体级前向想象：slot 协方差传播预演干扰结果，服务 wait/switch 决策的概率化版本；
- 若灵感指向「多智能体/博弈」→ 干扰者建模从"单步意图"升级为"意图序列/对抗策略"，仲裁器带对手模型；
- 若 F7/F8 解除 → 立即触发清单强制修订（评测视频逐任务拆解+得分点官方定义回填），并优先验证"人为干扰"场景的真实脚本（A6）。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 27 轮产物 · 创新点清单 v3：IP-11 INTENT-GUARD / IP-12 PREDICT-MAINT / GUARD-LOOP 完整算法设计

## 0. 结论

第 26 轮清单 v2（10 项）本轮完成「深化 + 新增」迭代，产出 v3（12 项）：

- **IP-11 新增 INTENT-GUARD（P1）**：手部感知（双轨：MediaPipe zero-shot 兜底 + 合成微调头）→ 意图预测（7 类基元 + 目标 slot + 接触时间）→ CBF 式共享控制仲裁（滞回 + 率限 + 防御时长预算）。服务"人为干扰"场景，叠加在 E10 重定位之上。
- **IP-12 新增 PREDICT-MAINT（P1）**：三级健康预测（地图 staleness / 模型漂移 Mahalanobis 分 / 端口 CUSUM）+ 维护窗口调度 + 预测性故障转移。端口件与模型件完全独立于语义地图路线。
- 四项深化（IP-1/IP-2/IP-4/IP-7），四项微修订（IP-3 不变/IP-8/IP-9/IP-10 记账），IP-5 冻结不变，无删除项。
- **结构性升级**：第 26 轮"固定关键帧"感知调度 → "维护窗口"按需调度（预测性维护思想的直接落地，E16 预期感知算力 −30%）。

路线无关原则不变：IP-11/IP-12 均以可消融模块接入；去掉两者系统回退到 v2 能力，无负收益。

## 1. 事实卡（继承与核实状态）

F1-F14 继承第 26 轮（2026-11-07 检索口径）；本轮重验 F7/F13：两页仍 Coming Soon，承诺文案不变 [R1/R2]。**本轮零新增事实卡**（结构迭代轮）。行动项：A1-A5 不变；**A6（新增，P2）**：评测访问后采集/请求含人手入镜的帧，验证手检测双轨的真实域差距（E12 前置）。

## 2. 创新点清单 v3 一览

| 编号 | 名称 | 一句话 | 优先级 | 依赖 | 灵感词 | 主成本账户 | 边际分预期 | 状态 |
|---|---|---|---|---|---|---|---|---|
| IP-1 | SLAM-MAP v2.1 | 四件套 + 维护窗口调度 | P0 | 无 | SLAM(26轮) | 算力(轻) | 位置/未见/干扰三类 +5~15pt | 微修订 |
| IP-2 | SCORE-ALIGN v2 | +p_fail 失效头（三消费者） | P0 | 无 | 25/27轮 | 数据(近零) | 步骤分 + 仲裁质量 | 微修订 |
| IP-3 | LOCAL-EVAL | 零真机迭代闭环 + 群体探针 | P0 | IP-2 | 26轮 | 算力(1 GPU) | 迭代速度=生命线 | 维持 |
| IP-4 | SUBMISSION-OPS v2 | +CUSUM 预测性故障转移 | P1 | 无 | 竞赛×预测维护 | 算力(部署机) | 掉请求→0 | 深化 |
| IP-5 | DUAL-HEAD | 单模型双解码头 | P2(冻结) | IP-1 | 25轮 | 算力 | 视合规 | 维持 |
| IP-6 | UNSEEN-GRASP | 指针：并入 IP-1 腕-头闭环 | P1 | IP-1 | 26轮 | 共享 | 未见物品 | 维持 |
| IP-7 | DISTURB-AUG v2 | +合成手注入三件套 | P1 | 无 | 25轮×手势 | 数据(近零) | 人为干扰场景 | 深化 |
| IP-8 | STEP-EFF | 步骤分效率工程（含防御时长记账） | P1 | A1 | 25/27轮 | 零额外 | 步骤分 | 微修订 |
| IP-9 | SWARM-DECODE | population/蒸馏+自洽投票；DEFEND 降 K | P1 | IP-2 | 26轮 | 算力(一次性) | 全场景 +2~5pt | 微修订 |
| IP-10 | COST-LADDER | 三账户记账+拒绝清单 | P0(纪律) | 无 | 26轮 | 全账户 | 防负 ROI | 维持 |
| IP-11 | INTENT-GUARD | 手势感知+意图预测+共享控制仲裁 | P1 | IP-1,IP-7 | 手势×共享控制 | 算力(0.7 GPU·天，一次性) | 干扰场景 +5~10pt（叠加 E10） | **新增** |
| IP-12 | PREDICT-MAINT | 三级健康+维护窗口+预测性故障转移 | P1 | IP-4(端口件) | 预测性维护 | 线上 <2ms/步 | 掉请求→0；感知算力 −30% | **新增** |

## 3. 重点展开一：GUARD-LOOP 完整算法设计（IP-11 × IP-12 联合，接第 26 轮地图服务骨架）

### 3.1 符号定义

继承第 26 轮：语义工作区地图 M={s_j}_{j=1..n}，s_j=(p_j, Σ_j, e_j, src_j)；重定位状态机 TRACKING/LOST/RELOC/REMAP；关键帧间隔 T_KF。

**v3 新增符号**：

| 符号 | 定义 |
|---|---|
| H(t)={h_i} | t 时刻可见人手集合；h_i=(K_i∈R^{21×3} 关键点（base 系，经 IP-1 外参前向模型）, v_i∈R^3 速度, c_i∈Δ^{|G|-1} 意图分布, ĵ_i∈{1..n,∅} 预测目标 slot, τ_i∈R_{\ge0} 估计接触时间) |
| G={reach, take, place, push, point, wave, idle} | 意图标签集（与第 25 轮 G5 注入器基元对齐，训练标签免费） |
| threat_j | slot j 威胁度：EMA( Σ_i P(c_i∈{reach,take,place,push})·g(dist(h_i, s_j)) )，g 为单调衰减核 |
| p_fail∈[0,1] | 当前 chunk 失效概率（IP-2 失效头输出） |
| staleness_j = age_j / τ_task(phase) | slot 过期度；age_j=距上次观测帧数，τ_task=任务阶段感知周期 |
| S_k | 端口健康 CUSUM 统计量（§3.5） |
| drift_t | 模型漂移分：感知特征对训练统计的 Mahalanobis 距离滑动窗（§3.6） |
| u∈[0,1]，m∈{EXEC, DEFEND} | 防御权重与模式（滞回切换：on=0.6 / off=0.3） |
| a_pol / a_def / a_cmd | 策略动作 / 防御动作∈{hold, backoff(v), wait} / 输出动作 |
| h_sec(x)=‖p_ee−p_hand‖−d_min | 安全裕度（CBF）；膨胀裕度 d_min'=d_min+ε_h+v_max·T_react（ε_h=手定位误差界，T_react=仲裁延迟上界） |
| B_def | 单 episode 防御时长预算（默认 20% episode 长度） |

### 3.2 算法步骤（主循环伪代码，接第 26 轮 relocate/REMAP 机制）

```python
def guard_loop_step(self, obs, t):
    # ---- 0. 基线（继承第 26 轮）：地图 token + 策略解码 ----
    K = 1 if self.mode == "DEFEND" else self.K_exec   # DEFEND 时 K=1，batch 让给仲裁
    a_pol, chunk = self.policy.decode(obs, self.map.tokens(), K=K)

    # ---- 1. PERCEIVE 人手（IP-11；外参前向模型是 IP-1 资产）----
    hands = (self.hand_detect(obs)        if t % T_KF == 0   # 全量：检测+21关键点，~12ms
             else self.hand_track_light(obs))                # 轻量：模板跟踪，~4ms

    # ---- 2. PREDICT（IP-12；训练信号全部来自本地资产）----
    for h in hands:
        h.c     = self.intent_mlp(feat(h))                   # <1ms，G 上 7 类分布
        h.j_hat = hungarian(self.map.slots, extrapolate(h))  # 手轨迹外推 × 马氏距离
        h.tau   = time_to_contact(h.v, h.p)
    d = threat_update(self.map.slots, hands)                 # slot 级威胁 + EMA 平滑
    p_fail = self.progress_head.p_fail(obs, chunk)           # IP-2 失效头
    self.map.health.enqueue(staleness=ages(self.map), threat=d)   # 维护工单（§3.5）
    self.port_health.tick(self.last_latency)                 # CUSUM（§3.5）

    # ---- 3. ARBITRATE（IP-11 共享控制核心）----
    d_max = max(d, default=0.0)
    self.mode = hysteresis(self.mode, d_max, on=0.6, off=0.3)     # 防模式抖振
    u_target = 1.0 if self.mode == "DEFEND" else 0.0
    u = clip(self.u + RATE * sign(u_target - self.u), 0, 1)       # 率限
    if self.def_time_used(t) > B_def:
        self.mode, u_target = "EXEC", 0.0                        # 有界让位：不许死等
    a_def = self.defensive_action(hands, self.ee_pose, self.gripper_state)
    a_cmd = cbf_filter((1 - u) * a_pol + u * a_def, hands,
                       d_min=d_min_adaptive(), v_max=V_MAX)      # CBF-QP / 解析 fallback

    # ---- 4. TASK-LEVEL：目标 slot 被威胁时 wait / switch / accelerate ----
    if threatened(self.map.goal_slot, d):
        self.map.goal_slot = argmax_E_progress(
            [wait, switch_to([s for s in self.map.slots if d[s] < 0.3]), accel],
            scorer=self.progress_head, p_fail=p_fail)            # IP-2 期望进度比较

    # ---- 5. MAINTAIN：让位停顿 = 免费维护窗口（IP-12 × IP-1）----
    if self.mode == "DEFEND" or self.map.health.due(t):
        self.map.relocate_or_perceive(obs)                       # 第 26 轮 E10 机制

    # ---- 6. SYS：预测性故障转移（IP-4 升级，独立于地图）----
    if self.port_health.alarm():
        self.router.preemptive_failover()

    return sanitize(low_pass(a_cmd))                             # 平滑输出（可信度条款）
```

### 3.3 复杂度与延迟预算（接第 26 轮 3.5 表，新增行）

| 环节 | v3 增量 | 手段 |
|---|---|---|
| 手检测+关键点 | ~12ms/关键帧 | 轻量检测头；MediaPipe zero-shot 兜底 [R7] |
| 手跟踪（中间步） | ~4ms/中间步 | 模板/光流轻量通道（复用第 26 轮 8ms 跟踪通道并扩一路） |
| 意图 MLP+威胁 | <1ms | 7 类小 MLP；威胁 EMA O(n·|H|)，n≤10 |
| CBF 过滤 | <1ms | ≤7 维小 QP 或解析夹取 fallback [R6] |
| CUSUM/staleness/漂移分 | ≈0 | 标量递推 O(1)/请求 |
| **合计** | **关键帧 +~16ms，中间步 +~4ms** | 第 26 轮预算表余量 >100ms，IP-10 推理账户通过 |

训练成本记账（IP-10）：合成手渲染+检测头微调 ~0.5 GPU·天；意图分类 ~0.2 GPU·天；一次性，总预算 40 GPU·天内，数据账户零真机红线不触。

### 3.4 正确性论证（设计命题+失效模式，诚实版；最终由 E12-E16 离线验证，非全系统定理）

- **命题 1（安全性）**：若手部定位误差 ≤ε_h 且 |v_ee|≤v_max，则经 cbf_filter 投影的 a_cmd 满足 ḣ_sec ≥ −α·h_sec（标准 CBF 条件 [R6]），即 EE-手距离不越过 d_min'；膨胀项 v_max·T_react 覆盖仲裁延迟（T_react ≤ 2×关键帧间隔）。*失效模式*：ε_h 低估（运动模糊/遮挡）→ 漂移分触发 margin 自适应放大；完全遮挡 → H(t)=∅，退化为第 26 轮纯重定位路径。
- **命题 2（有界让位）**：滞回（on=0.6/off=0.3）+ B_def 上限保证：episode 防御总时长 ≤B_def，超限强制 resume EXEC 并记遥测事件——系统不会"死等"。*失效模式*：威胁抖振 → 滞回+EMA 平滑（已内建）。
- **命题 3（平滑性/可信度）**：u 率限 + a_cmd 低通 ⇒ ‖a_cmd(t)−a_cmd(t−1)‖≤Δa_max，输出轨迹 Lipschitz 连续；滞回消除模式抖振 → 不触发 README §6 "不规则交互模式"疑虑；E14 的动作熵+Jerk 检查纳入冒烟 CI。*失效模式*：QP 无可行解 → 解析夹取 fallback（沿 h_sec 梯度方向收缩+速度截断）。
- **命题 4（可复活）**：DEFEND 期间动作目标冻结但跟踪与重定位照跑（维护窗口）；人手离开 → mode 回 EXEC → 已刷新的地图直接供 chunk 重解码——让位后 O(1) 个关键帧内恢复目标。*失效模式*：RELOC 超时失败 → REMAP（第 26 轮状态机兜底）。

### 3.5 端口预测性维护（IP-12 系统件，独立于地图路线）

```
每请求 k 记录延迟 l_k；z_k = (l_k − EWMA_mean) / EWMA_std
CUSUM:  S_k = max(0, S_{k-1} + z_k − δ)
S_k > h → 抢在崩溃前把请求切到副本（preemptive_failover）
心跳丢失 >2 周期 → 立即转移（保留 E11 反应式接管兜底）
(δ, h) 按平均运行长度 ARL 校准：目标误警 ARL ≥ 500 请求（E15）
```

复杂度 O(1)/请求；与第 26 轮 E11（kill 后 <2s 接管）叠加为「预警 → 转移 →（若仍崩）接管」三层容错。

### 3.6 模型健康（漂移监测，IP-12 第三件）

感知特征（检测置信度、深度残差、VLA 隐层统计）对训练统计做 Mahalanobis 距离滑动窗（锚点 [R9][R10]）→ drift_t 持续超阈 → ①地图协方差放大降权；②维护窗口频率上调；③遥测打标（赛后分析）。**只调感知置信，不直接改策略输出**——规避可信度条款，零动作侧风险。

### 3.7 与其他 IP 的接口

- IP-1：重定位触发源 +1（人手接触事件/威胁 EMA）；维护窗口的执行者；
- IP-2：p_fail 失效头三消费者（第 26 轮投票破平 → +仲裁调制 → +wait/switch 期望比较）；
- IP-4：三层容错（预警/转移/接管）；赛后遥测新增防御事件字段（mode 切换、B_def 使用率）；
- IP-7：合成手三件套是 IP-11 唯一训练数据源；
- IP-8：DEFEND 时长=步骤分效率账的显式成本项（强化 switch 决策价值）；
- IP-9：DEFEND 期间 K=1 + chunk 视界 20→8 步（更快回到仲裁点，延迟反而降）。

## 4. 重点展开二：IP-7 合成手注入（IP-11 的数据资产）

- **渲染**：3D 手模型（MANO 级网格）/真人手分割贴图 + 基元运动库 {reach, take, place, push, point, wave, idle}（与意图标签集一一对应）+ 域随机化{肤色、尺度、速度、遮挡率、入镜路径}，贴入双目帧（左右目一致性由 3D 渲染保证）。
- **自动标签**（渲染即标签，零人工）：手框 + 21 关键点 + 意图类别 + 目标 slot id + 接触时刻 τ——同时产出：手检测训练集、意图分类训练集、干扰前后图像对（第 26 轮资产扩容）。手势预训练语料可选用 HaGRID [R8]（18 类静态/动态手势，37,583 名被试），仅作检测器初始化，意图分类仍以注入器基元标签为准。
- **成本**：渲染+微调 ~0.5 GPU·天（IP-10 数据账户红线不触：合成近零）。
- **诚实风险**：合成→真域差距是本轮最大风险，双轨兜底与降级机制见 §5/§6。

## 5. 实验设计（新增 E12-E16，接第 26 轮 E7-E11）

| 实验 | 设置 | 指标 | 门槛/预期 |
|---|---|---|---|
| E12 手检测 | 合成验证集 + 真帧抽检（A6） | AP@50、真域掉点 | 合成集 AP≥0.85；真帧掉点 ≤15pt（双轨兜底） |
| E13 意图分类 | 注入器基元标签回放 | 7 类 F1、TTC 误差 | F1≥0.8；TTC 误差 <0.3s |
| E14 干扰整集 | 回放基线（仅 E10 重定位）vs +GUARD-LOOP | 成功率/完成时间/防御时长占比/Jerk/动作熵 | 干扰场景 +5~10pt；完成时间代价 <10%；防御 ≤20%；熵与 Jerk 不劣化（CI 纳入） |
| E15 预测性故障转移 | CUSUM 预警 vs 纯反应式（E11） | 掉请求数、误警 ARL、接管时间 | 掉请求=0；误警 ARL≥500 请求 |
| E16 维护窗口 vs 固定关键帧 | 感知调用次数 / 地图 3D 误差 | 次数、误差 | 调用 −30%、误差持平 |

**降级机制**：E12/E13 任一不过门槛 → IP-11 冻结为"仅维护窗口+重定位"（保留 IP-12），系统回退第 26 轮能力，不产生负收益。E14 的熵/Jerk 检查并入冒烟 CI（可信度条款预防，接第 26 轮 E7 做法）。

## 6. 风险登记簿（增量；第 26 轮各行继续有效）

| 风险 | 等级 | 缓解 |
|---|---|---|
| **合成手域差距 + 意图误判 → 无谓让位丢步骤分（本轮最大）** | **高** | 双轨（MediaPipe 兜底）；B_def 时长预算；E12/E13 门槛 + 降级机制 |
| 手部遮挡/头相机盲区 | 中 | 双视角（头+腕）融合；ε_h 自适应膨胀；遮挡时退化重定位路径 |
| 防御动作触发可信度条款疑虑（README §6） | 中 | 率限+滞回+低通；E14 熵+Jerk 入冒烟 CI |
| 外部软件栈（手检测/仲裁器）与"单模型"边界 | 中 | 与 SLAM-MAP 感知栈同状态；A5 澄清 |
| CBF 假设失效（外参前向模型误差传导） | 中 | d_min' 膨胀 + 解析 fallback；E9 外参误差实测回填 ε_h |
| F9 相机映射/校正未确认（继承） | 高 | A4 最高优先不变 |

## 7. 来源清单（检索/核实于 2026-11-07）

- 继承第 26 轮 R1-R5g（赛事页面、接口 README、数据集卡片、Model soups/Self-Consistency/Kimera 系/LiSTA/LT-mapper/ConceptGraphs），口径不变。
- 本轮新增（arXiv API 逐一核实 ✓）：
  - R6 Control Barrier Functions: Theory and Applications（Ames et al.）: https://arxiv.org/abs/1903.11199 ✓
  - R7 MediaPipe Hands: On-device Real-time Hand Tracking（Zhang et al.）: https://arxiv.org/abs/2006.10214 ✓
  - R8 HaGRID – HAnd Gesture Recognition Image Dataset（Kapitanov et al., WACV 2024）: https://arxiv.org/abs/2206.08219 ✓
  - R9 A Simple Unified Framework for Detecting Out-of-Distribution Samples and Adversarial Attacks（Lee et al., NeurIPS 2018）: https://arxiv.org/abs/1807.03888 ✓
  - R10 A Baseline for Detecting Misclassified and Out-of-Distribution Examples（Hendrycks & Gimpel, ICLR 2017）: https://arxiv.org/abs/1610.02136 ✓
  - R11 CUSUM：Page (1954), Biometrika；EWMA：Roberts (1959), Technometrics —— 经典 SPC 文献，无 arXiv，如实标注
- R1/R2 本轮重验：https://unibot.unitree.com/leaderboard.html 、https://unibot.unitree.com/runs.html （仍 Coming Soon，文案不变）

## 8. 清单迭代规则（继承+增补）

- 继承第 26 轮 0（事实卡先行）/ 7（COST-LADDER 记账）/ 8（榜单上线触发对手锚定修订）。
- 9（新增）：一切防御性行为必须通过平滑 CI（E14 熵+Jerk）与 B_def 时长预算才能上真机评测；
- 10（新增）：一切预测性组件（意图/失效/健康）先回放离线验证（F1/AUC/ARL），后在线接入；
- 11（新增）：让位一旦触发，地图必须同步进入维护窗口——防御时间不许白烧。
<!-- ARTIFACT:END -->
