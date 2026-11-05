# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 25 轮（研究线累计；本轮灵感循环第 7 轮）· ROS-VGDN 演示方案：从「语音交互」「ROS」「演示方案」出发，在 VGDN 算法上构建可部署的 ROS2 演示系统

## 0. 先给直觉：演示方案需要什么？

演示是 science 与 engineering 的桥梁**：

> **science** 给出模型（VGDN 的 H 推断、Q 值函数）；
> **engineering** 要把模型装进「机器人真能跑」的黑盒。

ROS2 提供「节点、话题、服务、行为树」的模块化框架；VGDN 提供「声-态-反馈」的决策逻辑。**演示方案的核心问题是：怎么把「数学公式」包装成「能被机器人拿去跑」的可执行文件？**

一句话先给押注：

> **本轮把 VGDN 的理论层搬进 ROS2 的「BehaviorTree执行器」里，设计「DemoServer」Action Server、「语音-动作」映射表、以及「可视化热力图」RViz 插件。**

三个可验证创新点：

1. **DemoServer Action Server**：接收语音指令 → 调用 LLM 消歧 → 生成 DemoMap → 返回目标位姿 + 解释文本；支持「暂停/中止/恢复」的生命周期，符合 ROS2 Action 模型。

2. **语音-动作映射表**：离线编译「语言模式 → 约束参数」的查表，避免在实时路径规划中调用 LLM；表中记录「左/右边》→「约束 sign = -1/+1」等规则。

3. **热力图 RViz 插件**：DemoMap 的 H(s) 以「半透明色谱」形式叠加在点云上，用户可点击「校正」点 → 触发 DemoMap 增量更新。

## 1. ROS2 架构设计

### 1.1 节点划分

| 节点 | 负责 | 订阅 | 发布 |
|---|---|---|---|
| `demo_server` | 主控制器，ActionServer | `/speech_recognition`, `/demo/feedback` | `/demo/action`, `/demo/explain`, `/demo/heatmap` |
| `speech_node` | 语音识别 | `/audio` | `/speech_recognition` |
| `heatmap_visual` | RViz 插件 | `/demo/heatmap` | `/rviz/interactive_point` |
| `feedback_listener` | 用户反馈 | `/demo/feedback` | - |

### 1.2 BehaviorTree 结构

```xml
<!-- demo_tree.xml -->
<Root>
  <Fallback>
    <Sequence name="DemoActive">
      <ForceSuccess key="WaitInput"/>
      <Action name="ComputeMap" port="intent"/>
      <Action name="SelectTarget"/>
      <Parallel name="Execute">
        <Action name="FastMove"/>
        <Action name="SlowAdjust">
          <BackToBack>
            <Action name="ComputeCorrection"/>
            <SetBlackboard key="blended_action" value="{correction}*α"/>
          </BackToBack>
        </Action>
      </Parallel>
      <Action name="Explain"/>
    </Sequence>
    <Sequence name="WaitForVoice">
      <Action name="Listen"/>
    </Sequence>
  </Fallback>
</Root>
```

## 2. DemoServer Action Server 实现

### 2.1 接口定义

```
Goal:
  string speech_text   # 识别后的文本
  string language      # 语言代码
  float32 max_latency  # 最大响应时间

Result:
  geometry_msgs/PoseStamped target_pose
  string explanation
  demo_msgs/DemoMap heatmap

Feedback:
  uint8 status          # 0=INIT, 1=PROCESSING, 2=EXECUTING, 3=COMPLETE
  string progress_msg
```

### 2.2 Python 实现

```python
#!/usr/bin/env python3
import rclpy
from rclpy.action import ActionServer
from rclpy.node import Node
from demo_msgs.action import DemoAction

class DemoServer(Node):
    def __init__(self):
        super().__init__('demo_server')
        self._as = ActionServer(
            self, DemoAction, 'demo_task',
            execute_callback=self.execute_callback)
        
        # 订阅反馈
        self.fb_sub = self.create_subscription(
            DemoFeedback, '/demo/feedback', self.fb_cb, 10)
        
        # DemoMap 缓存
        self.demo_map = None
        self.intent_dist = None
        
    async def execute_callback(self, goal_handle):
        self.get_logger().info('收到演示指令')
        feedback = DemoAction.Feedback()
        feedback.status = 1
        goal_handle.publish_feedback(feedback)
        
        # 1. 语义消歧
        intent = self.parse_intent(goal_handle.request.speech_text)
        
        # 2. 生成 DemoMap
        self.demo_map, expl = self.build_demo_map(intent)
        
        # 3. 选目标
        target = self.select_target(self.demo_map)
        
        # 4. 返回结果
        result = DemoAction.Result()
        result.target_pose = target
        result.explanation = expl
        result.heatmap = self.demo_map_to_msg()
        goal_handle.succeed()
        return result
```

## 3. 语音-动作映射表（离线编译）

```python
# voice_action_maps.py
VOICE_ACTION_MAP = {
    # 简单放置
    "put.*on.*table": {
        'action': 'place',
        'plane': 'table',
        'confidence_boost': 1.0
    },
    # 侧向约束
    "left.*side|左侧": {
        'constraint': {'sign': -1, 'axis': 'x'}
    },
    "right.*side|右侧": {
        'constraint': {'sign': 1, 'axis': 'x'}
    },
    "near.*the": {
        'distance_factor': 0.5
    },
    # 复合指令
    "near.*left|left.*near": {
        'constraint': {'sign': -1, 'axis': 'x'},
        'distance_factor': 0.5
    }
}
```

## 4. 热力图 RViz 插件（Python）

```python
# heatmap_visual.py
from rviz_py import PluginPanel
from visualization_msgs.msg import Marker
import numpy as np

class HeatmapVisualizer(PluginPanel):
    def __init__(self):
        super().__init__("DemoHeatmap")
        self.marker_col = Marker()
        self.marker_col.header.frame_id = "map"
        
    def on_heatmap(self, heatmap_msg):
        # 将 DemoMap 的 H(s) 渲染为彩色点云
        points = []
        colors = []
        for pt in heatmap_msg.points:
            if pt.intensity > 0.1:  # 置信阈值
                points.append([pt.x, pt.y, pt.z])
                colors.append(self.conf_to_color(pt.intensity))
        
        self.visualize_points(points, colors)
    
    def conf_to_color(self, conf):
        # 将 [0,1] → [r,g,b,a]
        r = conf
        g = 1 - conf
        b = 0.5
        return [r, g, b, 0.5]
```

## 5. 部署配置

### 5.1 ROS2 参数文件（demo_params.yaml）

```yaml
demo_server:
  ros__parameters:
    llm_endpoint: "http://localhost:8000/parse"
    heatmap_resolution: 0.04
    max_latency: 5.0
    risk_kappa: 1.0
```

### 5.2 launch 文件（demo_launch.py）

```python
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='demo_pkg',
            executable='speech_node',
            name='speech_node'
        ),
        Node(
            package='demo_pkg',
            executable='demo_server',
            name='demo_server',
            parameters=['demo_params.yaml']
        ),
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            arguments=['-d', 'demo_config.rviz']
        )
    ])
```

## 6. 本轮最大的风险

**ROS2 ActionServer 的「长时任务」风险：演示任务可能长达数秒（语音识别+LLM+路径规划），在此期间用户可能中途说「不对」或「取消」。若不及时响应取消请求，机器人会执行过期的旧动作，导致安全和可用性问题。缓解：在 DemoServer 中实现「目标版本号」机制，每次接收到新指令后检查目标是否仍为最新。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 25 轮产物 · ROS-VGDN 演示方案 技术报告

## 0. 结论：从算法到部署的闭环装配

本轮将第 24 轮的 VGDN 算法装配进 ROS2 生态：

- **DemoServer Action Server**：接收语音指令，完整执行「消歧→热力图→目标→解释」闭环；
- **语音-动作映射表**：离线编译常见指令模式，避免实时 LLM 调用过载；
- **热力图 RViz 插件**：可视化 H(s)，支持用户交互式校正。

## 1. ROS2 架构

### 1.1 节点

| 节点 | 功能 | 话题 |
|---|---|---|
| `demo_server` | 主控制器，ActionServer | `/speech_recognition` → `/demo/action` |
| `speech_node` | 语音 ASR | `/audio` → `/speech_recognition` |
| `heatmap_visual` | RViz 可视化 | `/demo/heatmap` → 点云渲染 |
| `feedback_listener` | 用户反馈 | `/demo/feedback` |

### 1.2 Action 接口

```
Goal: {speech_text, language, max_latency}
Result: {target_pose, explanation, heatmap}
Feedback: {status, progress_msg}
```

## 2. DemoServer 实现

```python
class DemoServer(Node):
    def __init__(self):
        super().__init__('demo_server')
        self._as = ActionServer(self, DemoAction, 'demo_task',
                               execute_callback=self.execute_callback)
    
    async def execute_callback(self, goal_handle):
        intent = self.parse_intent(goal_handle.request.speech_text)
        self.demo_map, expl = self.build_demo_map(intent)
        target = self.select_target(self.demo_map)
        
        result = DemoAction.Result()
        result.target_pose = target
        result.explanation = expl
        result.heatmap = self.demo_map_to_msg()
        
        goal_handle.succeed()
        return result
```

## 3. 语音-动作映射表

```python
VOICE_ACTION_MAP = {
    "put.*on.*table": {'action': 'place', 'plane': 'table'},
    "left.*side|左侧": {'constraint': {'sign': -1, 'axis': 'x'}},
    "right.*side|右侧": {'constraint': {'sign': 1, 'axis': 'x'}},
    "near.*the": {'distance_factor': 0.5}
}
```

## 4. 部署配置

### 4.1 参数文件

```yaml
demo_server:
  ros__parameters:
    llm_endpoint: "http://localhost:8000/parse"
    heatmap_resolution: 0.04
    max_latency: 5.0
    risk_kappa: 1.0
```

### 4.2 Launch 文件

```python
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(package='demo_pkg', executable='speech_node', name='speech_node'),
        Node(package='demo_pkg', executable='demo_server', name='demo_server',
             parameters=['demo_params.yaml']),
        Node(package='rviz2', executable='rviz2', name='rviz2',
             arguments=['-d', 'demo_config.rviz'])
    ])
```

## 5. 测试计划

| 阶段 | 测试内容 | 成功标准 |
|---|---|---|
| 单元测试 | DemoServer 100 条指令解析 | 成功率 ≥ 90% |
| 集成测试 | 完整闭环语音→动作 | 延迟 ≤ 500ms |
| RViz 测试 | 热力图可视化 + 交互 | 校正 → DemoMap 更新 ≤ 2s |

## 6. 本轮最大的风险

**ROS2 ActionServer 的「长时任务」风险：演示任务可能长达数秒，用户可能在执行期间发出中断或纠正指令。若不及时响应取消请求，机器人会执行过期的旧动作，导致安全和可用性问题。缓解：引入目标版本号机制，确保只有最新指令被执行。**
<!-- ARTIFACT:END -->