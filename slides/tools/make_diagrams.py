#!/usr/bin/env python3
"""Generate the deck diagrams as SVG with a single visual system."""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parents[1] / "public" / "img" / "diagrams"
OUT.mkdir(parents=True, exist_ok=True)

INK = "#1f2937"
MUTED = "#5b6776"
LINE = "#b9c3ce"
TEAL = "#0f766e"
TEAL_BG = "#e6f4f1"
AMBER = "#b45309"
AMBER_BG = "#fdf1e3"
SLATE_BG = "#f1f5f9"
WHITE = "#ffffff"
FONT = "Microsoft YaHei, Noto Sans CJK SC, sans-serif"


def svg(width: int, height: int, body: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L0,6 L9,3 z" fill="{MUTED}"/>
    </marker>
    <marker id="arrow-teal" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L0,6 L9,3 z" fill="{TEAL}"/>
    </marker>
  </defs>
  <rect width="{width}" height="{height}" fill="{WHITE}"/>
{body}
</svg>
'''


def text(x, y, value, size=16, color=INK, weight="normal", anchor="start", opacity=1.0):
    return (f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" fill="{color}" '
            f'font-weight="{weight}" text-anchor="{anchor}" opacity="{opacity}">{escape(value)}</text>')


def box(x, y, w, h, fill=WHITE, stroke=LINE, radius=12, width=1.5, dash=None):
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" ry="{radius}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{width}"{dash_attr}/>')


def arrow(x1, y1, x2, y2, color=MUTED, width=1.6, marker="arrow", dash=None):
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
            f'stroke-width="{width}" marker-end="url(#{marker})"{dash_attr}/>')


def title(value, subtitle=""):
    out = text(60, 62, value, 30, INK, "bold")
    if subtitle:
        out += text(60, 94, subtitle, 15, MUTED)
    return out


# ---------------------------------------------------------------- 1. architecture
def architecture() -> str:
    b = [title("系统总体架构", "展示层、控制面、数据面与基础设施分层；控制面只允许一个主控生效")]

    layers = [
        (120, 200, "展示层", SLATE_BG),
        (300, 260, "控制面 · 主星", SLATE_BG),
        (580, 260, "数据面 · 小卫星", SLATE_BG),
        (860, 120, "基础设施", SLATE_BG),
    ]
    for y, h, name, fill in layers:
        b.append(box(40, y, 1520, h, fill, LINE, 14, 1.2))
        b.append(text(58, y + 26, name, 15, MUTED, "bold"))

    # presentation layer
    b.append(box(90, 150, 360, 54, WHITE, TEAL, 10))
    b.append(text(110, 184, "浏览器态势面板 · 18082", 17, INK, "bold"))
    b.append(box(480, 150, 360, 54, WHITE, TEAL, 10))
    b.append(text(500, 184, "Headlamp · 4466（资源视图）", 17, INK, "bold"))
    b.append(text(880, 184, "只读取快照与资源状态，不参与调度决策", 15, MUTED))

    # control plane
    for index in range(3):
        x = 90 + index * 430
        leader = index == 1
        stroke = TEAL if leader else LINE
        fill = TEAL_BG if leader else WHITE
        b.append(box(x, 340, 390, 180, fill, stroke, 12, 2.2 if leader else 1.5))
        b.append(text(x + 20, 372, f"main-sat-{index}", 20, INK, "bold"))
        b.append(text(x + 300, 372, "LEADER" if leader else "FOLLOWER", 13, TEAL if leader else MUTED, "bold"))
        b.append(text(x + 20, 404, "主控竞选 / 计划生成", 15, INK))
        b.append(text(x + 20, 430, "命令下发 / 状态持久化", 15, INK))
        b.append(text(x + 20, 456, "阵列引擎（uv / PSF）", 15, INK))
        b.append(text(x + 20, 490, "epoch 17 · plan 168", 13, MUTED))
    b.append(box(1390, 340, 150, 84, WHITE, AMBER, 10, 1.5))
    b.append(text(1408, 368, "Lease", 16, INK, "bold"))
    b.append(text(1408, 392, "唯一主控", 13, MUTED))
    b.append(box(1390, 436, 150, 84, WHITE, AMBER, 10, 1.5))
    b.append(text(1408, 464, "ConfigMap", 16, INK, "bold"))
    b.append(text(1408, 488, "共享状态", 13, MUTED))

    # data plane
    for index in range(9):
        x = 70 + index * 165
        stroke = LINE
        b.append(box(x, 640, 145, 170, WHITE, stroke, 10, 1.3))
        b.append(text(x + 12, 668, f"small-sat-{index}", 15, INK, "bold"))
        b.append(text(x + 12, 696, "执行器 8080", 12, MUTED))
        b.append(text(x + 12, 718, "PVC 64 MiB", 12, MUTED))
        b.append(text(x + 12, 740, "分块上传", 12, MUTED))
        b.append(text(x + 12, 780, "×9 副本", 12, TEAL))

    # infrastructure chain
    chain = [("Windows 11", 90), ("WSL2 发行版", 330), ("Docker Engine", 610), ("k3d", 890), ("K3s 1+3", 1110)]
    for name, x in chain:
        b.append(box(x, 900, 190, 62, WHITE, LINE, 10))
        b.append(text(x + 95, 938, name, 16, INK, "bold", "middle"))
    for _, x in chain[:-1]:
        b.append(arrow(x + 192, 931, x + 232, 931))

    # cross-layer arrows
    b.append(arrow(520, 206, 520, 336, TEAL, 2, "arrow-teal"))
    b.append(text(532, 282, "查询 / 转发", 13, TEAL))
    b.append(arrow(600, 336, 600, 206, TEAL, 2, "arrow-teal"))
    b.append(text(612, 282, "快照回传", 13, TEAL))
    b.append(arrow(300, 524, 300, 636, TEAL, 2, "arrow-teal"))
    b.append(text(312, 590, "命令 / 参数", 13, TEAL))
    b.append(arrow(760, 636, 760, 528, TEAL, 2, "arrow-teal"))
    b.append(text(772, 592, "遥测 / 分块", 13, TEAL))
    return svg(1600, 1000, "\n".join(b))


# ---------------------------------------------------------------- 2. cluster
def cluster() -> str:
    b = [title("集群架构：从一台笔记本到一个 K3s 集群", "面向没有 Kubernetes 基础的听众，按“宿主 → 虚拟磁盘 → 容器 → 集群 → 工作负载”逐层展开")]

    b.append(box(40, 120, 1520, 780, SLATE_BG, LINE, 16, 1.2))
    b.append(text(60, 152, "Windows 11 主机", 17, MUTED, "bold"))

    b.append(box(80, 175, 1440, 690, WHITE, LINE, 14, 1.4))
    b.append(text(100, 207, "WSL2 · multi-star-sim（独立发行版，VHDX 位于项目 runtime/wsl）", 16, INK, "bold"))

    b.append(box(120, 230, 1360, 610, SLATE_BG, LINE, 12, 1.2))
    b.append(text(140, 262, "Docker Engine（仅该发行版内，不触碰宿主其他环境）", 15, INK))

    b.append(box(160, 285, 1280, 520, WHITE, LINE, 12, 1.2))
    b.append(text(180, 317, "k3d → K3s 集群 multi-star-sim：1 个 server + 3 个 agent", 15, INK, "bold"))

    # nodes
    nodes = [
        ("server", "控制平面\napiserver / SQLite", 200, 350, 250),
        ("agent-0", "承载 Pod", 480, 350, 250),
        ("agent-1", "承载 Pod", 760, 350, 250),
        ("agent-2", "承载 Pod", 1040, 350, 250),
    ]
    for name, desc, x, y, w in nodes:
        b.append(box(x, y, w, 150, WHITE, TEAL if name == "server" else LINE, 10, 1.6))
        b.append(text(x + 16, y + 30, name, 17, INK, "bold"))
        for i, line in enumerate(desc.split("\n")):
            b.append(text(x + 16, y + 58 + i * 22, line, 13, MUTED))
    b.append(text(200, 476, "172.45.0.2", 11, MUTED))
    b.append(text(480, 476, "172.45.0.3", 11, MUTED))
    b.append(text(760, 476, "172.45.0.4", 11, MUTED))
    b.append(text(1040, 476, "172.45.0.5", 11, MUTED))

    # namespace and workloads
    b.append(box(200, 520, 1090, 260, AMBER_BG, AMBER, 10, 1.4, "6 4"))
    b.append(text(218, 550, "Namespace multi-star", 16, INK, "bold"))
    loads = [
        ("StatefulSet small-sat", "9 个 Pod + 9 个 PVC", 230),
        ("StatefulSet main-sat", "3 个 Pod + 3 个 PVC", 560),
        ("Deployment dashboard", "1 个 Pod（可滚动更新）", 890),
    ]
    for name, desc, x in loads:
        b.append(box(x, 570, 290, 96, WHITE, LINE, 8))
        b.append(text(x + 14, 600, name, 14, INK, "bold"))
        b.append(text(x + 14, 626, desc, 12, MUTED))
    b.append(text(218, 700, "Pod = 最小调度单元（一个或多个容器）；Node = 承载 Pod 的虚拟主机，也就是上面的 server / agent 容器。", 13, MUTED))
    b.append(text(218, 726, "同一 Pod 内的容器共享网络命名空间；每个小星、主星各自一个 Pod，并挂载独立 PVC 保存状态。", 13, MUTED))

    # registry
    b.append(box(1330, 520, 150, 120, WHITE, LINE, 10))
    b.append(text(1348, 550, "镜像仓库", 14, INK, "bold"))
    b.append(text(1348, 576, "registry.localhost", 11, MUTED))
    b.append(text(1348, 598, ":5001", 11, MUTED))
    b.append(arrow(1330, 580, 1292, 580, MUTED, 1.4))
    b.append(text(1150, 545, "拉取镜像", 11, MUTED))
    return svg(1600, 940, "\n".join(b))


# ---------------------------------------------------------------- 3. scheduling
def scheduling() -> str:
    b = [title("调度时序：主控竞选、命令围栏与接管", "同一条命令只在特定 epoch 与 plan 版本内有效，旧主控恢复后无法重新生效")]

    actors = [("main-sat-0", 170), ("main-sat-1", 560), ("main-sat-2", 950), ("Lease", 1240), ("small-sat-*", 1470)]
    for name, x in actors:
        b.append(box(x - 90, 130, 180, 52, TEAL_BG if name.startswith("main") else WHITE, LINE, 10))
        b.append(text(x, 163, name, 15, INK, "bold", "middle"))
        b.append(f'<line x1="{x}" y1="182" x2="{x}" y2="820" stroke="{LINE}" stroke-width="1.2" stroke-dasharray="5 5"/>')

    steps = [
        (220, 170, 1240, "① 申请 / 续约 Lease", TEAL),
        (270, 1240, 170, "② 授予 epoch 17", TEAL),
        (330, 170, 1470, "③ 下发命令（epoch/plan/command_id）", TEAL),
        (390, 1470, 170, "④ 回执：accepted / verified", MUTED),
        (520, 1240, 560, "⑥ 租约过期，main-sat-1 接管", TEAL),
        (580, 560, 1470, "⑦ 新计划 plan + 1，重新下发", TEAL),
        (640, 170, 1470, "⑧ 旧主恢复：epoch 16 命令被拒绝", AMBER),
        (700, 1470, 170, "⑨ 仅接受 epoch 17 命令", MUTED),
    ]
    y = 220
    for dy, x1, x2, label, color in steps:
        direction = 1 if x2 > x1 else -1
        b.append(arrow(x1 + direction * 6, dy, x2 - direction * 6, dy, color, 2, "arrow-teal" if color == TEAL else "arrow"))
        b.append(text((x1 + x2) / 2, dy - 10, label, 13, color, "normal", "middle"))
        y += 60

    b.append(f'<rect x="164" y="440" width="12" height="86" fill="{AMBER}" opacity="0.25" rx="6"/>')
    b.append(text(186, 478, "⑤ 主控暂停 22 s", 13, AMBER))
    b.append(text(186, 500, "停止续约、停止下发", 12, AMBER))
    b.append(box(120, 760, 1360, 60, SLATE_BG, LINE, 10))
    b.append(text(140, 796, "幂等保证：command_id 去重；epoch 围栏拒绝旧主控；plan_version 只增不减；UNKNOWN 任务不重发不可逆变轨。", 13, MUTED))
    return svg(1600, 880, "\n".join(b))


# ---------------------------------------------------------------- 4. modes
def modes() -> str:
    b = [title("运行模式与任务流程", "三种模式共享同一套计划版本与命令通道，切换必须先通过前置校验")]

    b.append(box(120, 240, 300, 130, TEAL_BG, TEAL, 16, 2))
    b.append(text(270, 285, "SURVEY", 24, INK, "bold", "middle"))
    b.append(text(270, 318, "巡天：按健康小星维持阵列", 13, MUTED, "normal", "middle"))
    b.append(text(270, 344, "持续生成观测与上传任务", 13, MUTED, "normal", "middle"))

    b.append(box(640, 240, 300, 130, WHITE, LINE, 16, 1.6))
    b.append(text(790, 285, "FIXED_SOURCE", 24, INK, "bold", "middle"))
    b.append(text(790, 318, "定源：锁定单个天文事件", 13, MUTED, "normal", "middle"))
    b.append(text(790, 344, "事件到期自动回退 SURVEY", 13, MUTED, "normal", "middle"))

    b.append(box(1160, 240, 300, 130, WHITE, LINE, 16, 1.6))
    b.append(text(1310, 285, "CALIBRATION", 24, INK, "bold", "middle"))
    b.append(text(1310, 318, "标定：验证复增益与相位", 13, MUTED, "normal", "middle"))
    b.append(text(1310, 344, "不产生科学观测计划", 13, MUTED, "normal", "middle"))

    b.append(arrow(420, 288, 636, 288, TEAL, 2, "arrow-teal"))
    b.append(text(528, 272, "event accepted", 12, TEAL, "normal", "middle"))
    b.append(arrow(636, 330, 420, 330, AMBER, 2, "arrow"))
    b.append(text(528, 352, "事件到期 / 无有效事件", 12, AMBER, "normal", "middle"))

    b.append(arrow(940, 300, 1156, 300, MUTED, 1.8))
    b.append(text(1048, 284, "手动切换", 12, MUTED, "normal", "middle"))
    b.append(arrow(1156, 332, 940, 332, MUTED, 1.8))
    b.append(text(1048, 354, "手动切回", 12, MUTED, "normal", "middle"))

    b.append(arrow(180, 378, 180, 470, MUTED, 1.6))
    b.append(text(192, 430, "前置校验", 12, MUTED))
    guards = [
        "健康小星 ≥ 2",
        "没有 UNKNOWN 在途任务",
        "FIXED_SOURCE 需要未过期事件",
        "切换生成新的 plan_version",
    ]
    for i, guard in enumerate(guards):
        b.append(text(200, 490 + i * 26, f"• {guard}", 13, MUTED))

    b.append(box(760, 470, 700, 250, SLATE_BG, LINE, 12))
    b.append(text(780, 502, "单次计划内的任务编排", 15, INK, "bold"))
    flow = ["生成目标构型", "下发 transfer", "执行 observation", "分块 upload", "verify 归档"]
    for i, step in enumerate(flow):
        x = 790 + i * 135
        b.append(box(x, 530, 120, 56, WHITE, LINE, 8))
        b.append(text(x + 60, 564, step, 11, INK, "normal", "middle"))
        if i < len(flow) - 1:
            b.append(arrow(x + 122, 558, x + 132, 558, MUTED, 1.4))
    b.append(text(780, 620, "每个任务带 plan_version 与 expires_at；超时未执行则作废，不阻塞下一版计划。", 12, MUTED))
    b.append(text(780, 650, "故障时只重构受影响小星，其余任务保持；恢复后重新纳入阵列。", 12, MUTED))
    return svg(1600, 800, "\n".join(b))


# ---------------------------------------------------------------- 5. dataflow
def dataflow() -> str:
    b = [title("系统信息流与通信拓扑", "小星只与主控通信；主控之间通过 Lease 与共享状态协调；面板只读快照")]

    # small sats column
    b.append(box(50, 170, 300, 560, SLATE_BG, LINE, 12))
    b.append(text(70, 200, "小卫星 ×9（Pod）", 15, INK, "bold"))
    for index in range(9):
        y = 220 + index * 56
        b.append(box(70, y, 260, 44, WHITE, LINE, 8))
        b.append(text(84, y + 28, f"small-sat-{index}", 12, INK))
        b.append(text(250, y + 28, "8080", 11, MUTED, "normal", "end"))

    # leader
    b.append(box(470, 300, 320, 300, TEAL_BG, TEAL, 14, 2))
    b.append(text(490, 336, "当前主控 main-sat-1", 18, INK, "bold"))
    b.append(text(490, 368, "调度器 / 计划生成", 14, INK))
    b.append(text(490, 396, "命令围栏与去重", 14, INK))
    b.append(text(490, 424, "状态机与审计", 14, INK))
    b.append(text(490, 452, "阵列引擎 uv / PSF", 14, INK))
    b.append(text(490, 500, "POST /command", 12, MUTED))
    b.append(text(490, 524, "GET /status", 12, MUTED))

    # followers
    b.append(box(470, 640, 150, 80, WHITE, LINE, 10))
    b.append(text(545, 672, "main-sat-0", 13, INK, "bold", "middle"))
    b.append(text(545, 696, "follower", 12, MUTED, "normal", "middle"))
    b.append(box(640, 640, 150, 80, WHITE, LINE, 10))
    b.append(text(715, 672, "main-sat-2", 13, INK, "bold", "middle"))
    b.append(text(715, 696, "follower", 12, MUTED, "normal", "middle"))

    # panel
    b.append(box(920, 240, 300, 180, WHITE, LINE, 12))
    b.append(text(940, 272, "dashboard 代理", 16, INK, "bold"))
    b.append(text(940, 302, "发现 leader → 转发", 13, MUTED))
    b.append(text(940, 326, "无唯一 leader 时返回 503", 13, MUTED))
    b.append(text(940, 360, "浏览器 · 1 s 轮询", 12, TEAL))
    b.append(text(940, 384, "Headlamp · 4 s 刷新", 12, TEAL))

    # state objects
    b.append(box(920, 460, 300, 70, AMBER_BG, AMBER, 10))
    b.append(text(940, 490, "Lease multi-star-control", 13, INK, "bold"))
    b.append(text(940, 514, "holder / epoch / 续约时间", 11, MUTED))
    b.append(box(920, 550, 300, 70, AMBER_BG, AMBER, 10))
    b.append(text(940, 580, "ConfigMap 共享状态", 13, INK, "bold"))
    b.append(text(940, 604, "计划 / 事件 / 审计日志", 11, MUTED))

    # registry + pvc
    b.append(box(920, 650, 300, 70, WHITE, LINE, 10))
    b.append(text(940, 680, "PVC ×12 / 镜像仓库", 13, INK, "bold"))
    b.append(text(940, 704, "状态快照 64 MiB / 镜像 5001", 11, MUTED))

    # arrows
    b.append(arrow(350, 380, 466, 380, TEAL, 1.8, "arrow-teal"))
    b.append(text(360, 368, "命令", 12, TEAL))
    b.append(arrow(466, 430, 350, 430, MUTED, 1.6))
    b.append(text(360, 452, "状态 / 上传", 12, MUTED))

    b.append(arrow(790, 352, 912, 352, TEAL, 1.8, "arrow-teal"))
    b.append(text(846, 340, "快照", 12, TEAL))
    b.append(arrow(912, 392, 790, 392, MUTED, 1.6))
    b.append(text(846, 414, "查询", 12, MUTED))

    b.append(arrow(640, 520, 916, 495, MUTED, 1.4))
    b.append(text(700, 486, "续约 / 竞选", 12, MUTED))
    b.append(arrow(640, 590, 916, 585, MUTED, 1.4))
    b.append(text(716, 574, "持久化", 12, MUTED))

    b.append(arrow(545, 640, 545, 604, MUTED, 1.2))
    b.append(arrow(715, 640, 715, 604, MUTED, 1.2))
    b.append(text(470, 780, "所有小星仅有 HTTPS 出站到主控；主控之间不直接互连，靠 Lease 决定唯一写者。", 13, MUTED))
    return svg(1600, 820, "\n".join(b))


def main() -> None:
    items = {
        "01-architecture.svg": architecture(),
        "02-cluster.svg": cluster(),
        "03-scheduling.svg": scheduling(),
        "04-modes.svg": modes(),
        "05-dataflow.svg": dataflow(),
    }
    for name, content in items.items():
        (OUT / name).write_text(content, encoding="utf-8")
        print("wrote", name, len(content))


if __name__ == "__main__":
    main()
