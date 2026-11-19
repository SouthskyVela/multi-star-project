#!/usr/bin/env python3
"""One-off restructuring of slides.md requested in review round 2."""
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "slides.md"
t = P.read_text(encoding="utf-8")
log = []


def sub(old: str, new: str, label: str) -> None:
    global t
    if new in t:
        log.append(f"skip {label}")
        return
    if old in t:
        t = t.replace(old, new, 1)
        log.append(f"ok   {label}")
    else:
        log.append(f"MISS {label}")


def insert_before(anchor: str, block: str, label: str) -> None:
    global t
    if block.strip() in t:
        log.append(f"skip {label}")
        return
    if anchor in t:
        t = t.replace(anchor, block + anchor, 1)
        log.append(f"ok   {label}")
    else:
        log.append(f"MISS {label}")


# ---------------------------------------------------------------- cover
sub(
    "汇报人：____________　　学号：____________　　2026 年 11 月",
    "汇报人：李达航　　学号：23009101011　　2026 年 11 月\n\n"
    '<div class="mt-2 text-xs text-slate-400">开源地址：github.com/SouthskyVela/multi-star-project</div>',
    "cover identity",
)

# ---------------------------------------------------------------- slide 3 background
sub(
    '<div class="mt-6 p-4 rounded bg-slate-100 text-sm">\n\n本课题不追求真实的轨道动力学与全链路成像',
    '<div class="mt-4 p-4 border-l-4 border-teal-600 bg-teal-50 text-sm">\n\n'
    "**可拓展性**：多颗卫星组成的卫星群在调度算法上有很大的设计空间——可以把成像采样质量（uv 覆盖、PSF）作为奖励，"
    "用强化学习去优化阵列构型与观测编排。\n\n</div>\n\n"
    '<div class="mt-3 p-4 rounded bg-slate-100 text-sm">\n\n本课题不追求真实的轨道动力学与全链路成像',
    "background extensibility",
)

# ---------------------------------------------------------------- slide 4 scope
old_scope = '''<div class="grid grid-cols-2 gap-6 mt-4 text-sm">

<div>

### 要做的事

- **主控选举与接管**：同一时刻只有一个主控，故障后自动切换
- **任务编排**：巡天、定源、定标三种模式的状态机
- **命令可靠性**：幂等、围栏、重放保护、不可逆变轨不重发
- **阵列评估**：构型、uv 覆盖、dirty beam / PSF
- **可观测性**：实时面板、审计日志、资源全景

</div>

<div>

### 不做什么

- 不做真实轨道摄动、姿态控制与推进建模
- 不做完整射电成像管线（成像仅用于评估阵列）
- 不构成飞行安全证明
- 不覆盖任意非对称网络分区
- 不依赖 GPU 也能完成核心调度（GPU 仅加速批量评估）

</div>

</div>'''
new_scope = '''<div class="mt-4 text-sm">

### 要做的事

- **主控竞选与接管**：同一时刻只有一个主控，故障后自动切换
- **任务编排**：巡天、定源、定标三种模式的状态机
- **命令可靠性**：幂等、围栏、重放保护、不可逆变轨不重发
- **阵列评估**：构型、uv 覆盖、dirty beam / PSF
- **可观测性**：实时面板、审计日志、资源全景
- **可复现**：单机从零创建集群，版本化镜像与脚本

</div>'''
sub(old_scope, new_scope, "slide4 remove out-of-scope column")

# ---------------------------------------------------------------- new slide: initial sketch
sketch = '''---

# 最初构想：一张草图

<div class="grid grid-cols-5 gap-6 mt-1">

<div class="col-span-2">
<img src="/img/sketch/initial-idea.jpg" class="w-full rounded border border-slate-300" />
<div class="tiny mt-2">课题启动时的原始设想：控制面 / 节点 / 主副星 / 测试项 / 可视化。</div>
</div>

<div class="col-span-3 text-sm">

**草图里的几个要点**

- 天基射电干涉成像：**控制面为主星，节点为子星**
- 子星按 uv 采样最优调整构型与波束；主、副卫星可以互切
- 星间通信依靠激光 / 微波，减少对地面补网的依赖
- 测试三条线：常规功能切换、事件触发、主星与子星故障
- 可视化三件事：调度终端面板、阵列可视、输入输出响应
- 拓展设想：增加子星数量、引入 AI 辅助调度

</div>

</div>

'''
insert_before("# 需求分析", sketch, "insert sketch slide")

# ---------------------------------------------------------------- slide 5 requirements
sub(
    "| 功能 | 三主星租约选主，故障后 30 s 内完成接管 | 暂停主控 22 s，观察 leader 与 epoch |",
    "| 功能 | 三颗主星竞选主控（基于 Kubernetes Lease），同一时刻只有一颗生效；故障后 30 s 内完成接管 | 暂停主控 22 s，观察主控与 epoch 变化 |",
    "requirement wording",
)

# ---------------------------------------------------------------- new slide: why k3d
k3d = '''---

# 为什么选 k3d，而不是 k8s 或 k3s

<div class="text-sm mt-2">

| 方案 | 形态 | 资源占用 | 与本课题的匹配度 |
|---|---|---|---|
| Kubernetes（k8s） | 完整控制平面，面向多机生产集群 | 高 | 功能齐全，但单机演示过重 |
| K3s | 轻量发行版，一个进程即可运行 | 低 | 够轻，但默认只有一个节点 |
| k3d | 用 Docker 容器承载 K3s 节点 | 低–中 | 一条命令起 1 server + 3 agent，最接近真实多节点 |

</div>

<div class="grid grid-cols-3 gap-4 mt-5 text-xs text-slate-600">

<div><b>可复现</b>：集群、镜像、PVC 都落在项目目录，换机器同样能起。</div>

<div><b>可观测</b>：k3d 的节点就是容器，<code>docker ps</code> 与 <code>kubectl</code> 能一一对应，便于讲清 Node 与 Pod。</div>

<div><b>代价</b>：节点是容器而非真机，网络时延与存储都是模拟，不能替代星间链路验证。</div>

</div>

'''
insert_before("# 资源全景：Headlamp 里的真实集群（1/2）", k3d, "insert k3d slide")

# ---------------------------------------------------------------- split resource panorama
old_panorama = '''# 资源全景（2/2）：逐层展开到实例

<div class="grid grid-cols-2 gap-4 mt-2">

<figure>
<img src="/img/headlamp/07-map-small-sat.png" class="w-full rounded border border-slate-300" />
<figcaption>small-sat：StatefulSet → 9 个 Pod → 9 个 PVC，另有一个 Service。</figcaption>
</figure>

<figure>
<img src="/img/headlamp/08-map-main-sat.png" class="w-full rounded border border-slate-300" />
<figcaption>main-sat：3 个 Pod、3 个 PVC，并通过两个 Service 暴露状态与主控入口。</figcaption>
</figure>

</div>

<div class="mt-3 text-sm">

**为什么用 StatefulSet**：卫星需要稳定身份（<code>small-sat-0</code> 永远是同一颗星）、稳定存储（PVC 跟随序号）与有序滚动更新；Deployment 无法保证这三点。

</div>'''
new_panorama = '''# 资源全景（2/3）：small-sat 的九个实例

<img src="/img/headlamp/07-map-small-sat.png" class="w-full max-h-[74vh] object-contain mx-auto rounded border border-slate-300" />

<div class="grid grid-cols-3 gap-4 mt-2 text-xs text-slate-600">

<div><b>StatefulSet</b>：9 个副本，序号即卫星编号。</div>

<div><b>PVC</b>：每颗星一块 64 MiB，随序号重建。</div>

<div><b>Service</b>：headless，供主控按 DNS 发现。</div>

</div>

---

# 资源全景（3/3）：main-sat 的三颗主星

<img src="/img/headlamp/08-map-main-sat.png" class="w-full max-h-[74vh] object-contain mx-auto rounded border border-slate-300" />

<div class="grid grid-cols-3 gap-4 mt-2 text-xs text-slate-600">

<div><b>StatefulSet</b>：3 个副本，稳定身份与存储。</div>

<div><b>Service ×2</b>：一个对内暴露状态，一个提供主控入口。</div>

<div><b>为什么用 StatefulSet</b>：身份、存储随序号固定，Deployment 无法保证。</div>

</div>'''
sub(old_panorama, new_panorama, "split panorama")

# ---------------------------------------------------------------- imaging slides
imaging = '''---

# 前期工作：六星编队的成像仿真

<div class="grid grid-cols-2 gap-4 mt-1">

<figure>
<img src="/img/imaging/fig_uv_coverage.png" class="w-full rounded border border-slate-300" />
<figcaption>10 个轨道周期的 uv 覆盖：左 10 MHz，右 40 MHz，轨迹自然填充成环带。</figcaption>
</figure>

<figure>
<img src="/img/imaging/fig_rime_image.png" class="w-full rounded border border-slate-300" />
<figcaption>RIME 可见度仿真与脏图：四个输入源都回到正确位置。</figcaption>
</figure>

</div>

<div class="grid grid-cols-3 gap-4 mt-2 text-xs text-slate-600">

<div><b>构型</b>：6 星（1 主 5 从），Callisto 500 km 极轨，10 轨内基线 109–1982 km。</div>

<div><b>分辨率</b>：10 MHz 约 2.48″，40 MHz 约 0.62″。</div>

<div><b>结果</b>：峰值恢复约 80%，损失主要来自 uv 中心空洞的短基线缺失。</div>

</div>

---

# 前期工作：多工具交叉验证

<img src="/img/imaging/fig_4tool_compare.png" class="w-full max-h-[68vh] object-contain mx-auto mt-1 rounded border border-slate-200" />

<div class="grid grid-cols-3 gap-4 mt-2 text-xs text-slate-600">

<div><b>RIME</b>：4 个源位置正确，峰值恢复约 80%。</div>

<div><b>OSKAR</b>：120 个随机快照联合成像，恢复率 75%，与短基线缺失一致。</div>

<div><b>pyuvsim / OmniUV</b>：归一化通过并保持相位闭合；OmniUV 用真实开普勒轨道生成 FITS-IDI。</div>

</div>

<div class="tiny mt-2">附带结论：均匀快照会产生规则栅瓣，随机化观测时刻后消除——这条已写回阵列设计约束。</div>

---

# 前期工作：CASA 端到端成像

<div class="grid grid-cols-5 gap-5 mt-1">

<div class="col-span-3">
<img src="/img/imaging/fig_casa_image.png" class="w-full rounded border border-slate-300" />
<div class="tiny mt-2">左：脏图；右：Högbom 清洗后。红圈为注入源的真值位置。</div>
</div>

<div class="col-span-2 text-sm">

**定量结果**

- 四个源位置误差 ≤ 0.6″（约四分之一合成波束）
- 流量恢复率 99.3%–99.9%
- 角域动态范围约 1490

**与本课题的关系**

前期工作验证了“阵列几何 → 可见度 → 成像”的正向链路；本课题补上调度、故障与重构这一层，让阵列在运行中始终可成像。

</div>

</div>

'''
insert_before("# 测试体系与总览", imaging, "insert imaging slides")

# ---------------------------------------------------------------- merge 24 + 25
old_tail = '''# 工程化实践

<div class="grid grid-cols-2 gap-6 mt-3 text-sm">

<div>

**可移植**

- 30 余个脚本由自身位置推导仓库根目录
- <code>config/runtime.json</code> 只保存相对路径
- <code>start.cmd</code> / <code>stop.cmd</code> 用 <code>wslpath</code> 解析当前检出位置
- 公开仓库不含任何主机绝对路径

</div>

<div>

**可运维**

- 面板暴露 read-only 快照接口，Headlamp 观察资源
- 审计日志连续去重，500 条环形缓冲不再被刷屏
- 状态区只显示关键字段，避免整段 JSON 撑开页面
- 部署脚本幂等，失败停在上一步并打印真实原因

</div>

</div>

<div class="mt-6 p-3 rounded bg-slate-100 text-sm">

**版本与交付**：0.3.2 为本次汇报版本；镜像 <code>multi-star-main:0.3.2</code> 与小星镜像 <code>multi-star-satellite:0.2.0</code> 分离，避免小星无谓重启。

</div>

---

# 局限与后续工作

<div class="grid grid-cols-2 gap-8 mt-4 text-sm">

<div>

### 当前局限

- 阵列几何为简化远场模型，未含近场与电离层扰动
- 调度策略以轮询与固定优先级为主，未做能耗/可见性优化
- 单机 K3s 无法验证真实星间链路时延与丢包
- 镜像与 PVC 规模受限，尚未做百星级压测

</div>

<div>

### 后续计划

- 引入可见性与能量约束，做多目标调度
- 对接 OSKAR 做高保真成像复核
- 增加网络分区与时钟漂移的注入测试
- 将面板与调度器拆分，支持多集群联邦

</div>

</div>'''
new_tail = '''# 工程化实践、局限与后续

<div class="grid grid-cols-2 gap-8 mt-2 text-sm">

<div>

### 工程化

- 30 余个脚本由自身位置推导仓库根目录，配置只存相对路径
- 面板只读快照，Headlamp 观察资源；审计日志连续去重
- 部署脚本幂等，失败停在上一步并打印真实原因
- 镜像分离：<code>main:0.3.2</code> 与 <code>satellite:0.2.0</code>，避免小星无谓重启

</div>

<div>

### 局限与后续

- 阵列几何为简化远场模型，未含近场与电离层扰动
- 调度以轮询与固定优先级为主，未做能耗 / 可见性优化
- 单机 K3s 无法验证真实星间链路时延与丢包
- 后续：可见性约束、OSKAR 复核、网络分区注入、多集群联邦

</div>

</div>

<div class="mt-6 p-3 rounded bg-slate-100 text-xs text-slate-600">

版本与交付：0.3.2 为本次汇报版本；小星镜像仍为 0.2.0，主星与面板按需升级。

</div>'''
sub(old_tail, new_tail, "merge engineering + limits")

# ---------------------------------------------------------------- conclusion wording
sub(
    "1. 用**真实容器编排**承载虚拟卫星，把选主、幂等、故障恢复做成可验证机制，而不是纸面流程。",
    "1. 用**真实容器编排**承载虚拟卫星，把主控竞选、幂等、故障恢复做成可验证机制，而不是纸面流程。",
    "conclusion item1",
)
sub(
    "2. 通过 **Lease + epoch + plan_version** 形成一套简单但有效的围栏体系：同一时刻只有一个写者，旧主控无法“复活”。",
    "2. 通过 **主控竞选（Lease）+ epoch + plan_version** 形成一套简单但有效的围栏体系：同一时刻只有一个写者，旧主控无法“复活”。",
    "conclusion item2",
)

# ---------------------------------------------------------------- final slide URL
sub(
    '<div class="text-2xl font-mono text-teal-700">github.com/SouthskyVela/multi-star-project</div>',
    '<div class="text-2xl font-mono text-teal-700"><a href="https://github.com/SouthskyVela/multi-star-project" target="_blank">github.com/SouthskyVela/multi-star-project</a></div>',
    "final url link",
)

# ---------------------------------------------------------------- formatting fix
sub("-->\n---\n\n# 资源全景", "-->\n\n---\n\n# 资源全景", "blank line before separator")

P.write_text(t, encoding="utf-8", newline="")
print("\n".join(log))
