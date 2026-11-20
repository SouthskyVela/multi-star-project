#!/usr/bin/env python3
"""Operation flow and fault-response flow diagrams, reusing the shared style."""
from __future__ import annotations

from make_diagrams import AMBER, AMBER_BG, INK, LINE, MUTED, SLATE_BG, TEAL, TEAL_BG, WHITE, arrow, box, svg, text, title


def diamond(cx, cy, w, h, fill=WHITE, stroke=AMBER, label=""):
    pts = f"{cx},{cy - h // 2} {cx + w // 2},{cy} {cx},{cy + h // 2} {cx - w // 2},{cy}"
    out = f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="1.8"/>'
    out += text(cx, cy + 6, label, 15, INK, "bold", "middle")
    return out


def operation_flow() -> str:
    b = [title("系统操作流：从用户点击到状态回读", "破坏性操作在页面内二次确认，窗口 15 s；请求经主控校验后下发")]

    steps = [
        (120, 200, "① 打开面板", "浏览器访问 18082，1 s 轮询快照"),
        (120, 320, "② 选择目标", "主星或 small-sat-0 … 8"),
        (120, 440, "③ 选择操作", "暂停主控 / 注入 / 恢复 / 提交事件 / 切模式"),
    ]
    for x, y, head, sub in steps:
        b.append(box(x, y, 420, 86, WHITE, LINE, 10))
        b.append(text(x + 16, y + 34, head, 17, INK, "bold"))
        b.append(text(x + 16, y + 62, sub, 12, MUTED))
    for y in (286, 406):
        b.append(arrow(330, y, 330, y + 32, MUTED, 1.6))

    b.append(diamond(330, 620, 300, 110, AMBER_BG, AMBER, "④ 二次确认？"))
    b.append(arrow(330, 526, 330, 565, MUTED, 1.6))
    b.append(text(344, 552, "点击一次进入确认态", 11, MUTED))

    b.append(f'<path d="M180,620 L90,620 L90,483" fill="none" stroke="{AMBER}" '
             f'stroke-width="1.6" stroke-dasharray="5 4" marker-end="url(#arrow)"/>')
    b.append(text(96, 600, "超时 15 s / 再点取消", 11, AMBER))

    b.append(box(600, 580, 300, 80, TEAL_BG, TEAL, 10, 1.6))
    b.append(text(616, 612, "⑤ 主控校验", 16, INK, "bold"))
    b.append(text(616, 638, "健康数 / UNKNOWN / epoch", 11, MUTED))
    b.append(arrow(432, 620, 596, 620, TEAL, 2, "arrow-teal"))
    b.append(text(470, 606, "是", 12, TEAL))

    b.append(box(960, 580, 280, 80, WHITE, LINE, 10))
    b.append(text(976, 612, "⑥ 下发命令", 16, INK, "bold"))
    b.append(text(976, 638, "command_id + epoch + expires_at", 11, MUTED))
    b.append(arrow(902, 620, 956, 620, TEAL, 1.8, "arrow-teal"))

    b.append(box(1300, 580, 250, 80, WHITE, LINE, 10))
    b.append(text(1316, 612, "⑦ 快照刷新", 16, INK, "bold"))
    b.append(text(1316, 638, "面板 1 s / Headlamp 4 s", 11, MUTED))
    b.append(arrow(1242, 620, 1296, 620, TEAL, 1.8, "arrow-teal"))

    b.append(box(1300, 380, 250, 80, WHITE, LINE, 10))
    b.append(text(1316, 412, "⑧ 反馈与审计", 16, INK, "bold"))
    b.append(text(1316, 438, "状态区 + 事件流 + 日志", 11, MUTED))
    b.append(arrow(1425, 578, 1425, 464, TEAL, 1.8, "arrow-teal"))

    b.append(box(600, 760, 950, 90, SLATE_BG, LINE, 10))
    b.append(text(618, 792, "一致性保证", 14, INK, "bold"))
    b.append(text(618, 818, "同一 command_id 只生效一次；epoch 低于本地最高值直接拒绝；计划版本只增不减；不可逆变轨不重发。", 12, MUTED))
    return svg(1600, 900, "\n".join(b))


def fault_response() -> str:
    b = [title("故障响应方案：从检测到重新纳入阵列", "主控故障与小星故障走两条处理路径，最终都回到健康检查与计划版本递增")]

    b.append(box(620, 130, 360, 70, AMBER_BG, AMBER, 10, 1.8))
    b.append(text(800, 164, "故障事件", 17, INK, "bold", "middle"))
    b.append(text(800, 188, "断链 / 注入 / 暂停 / 探针失败", 11, MUTED, "normal", "middle"))

    # main-satellite lane
    b.append(box(60, 260, 660, 210, SLATE_BG, LINE, 12, 1.2))
    b.append(text(80, 292, "主控故障", 15, AMBER, "bold"))
    for x, head, sub in [
        (80, "① 停止续约", "进程暂停或失联"),
        (280, "② Lease 过期", "按续约周期判定"),
        (480, "③ 其他主星接管", "epoch + 1"),
    ]:
        b.append(box(x, 330, 180, 90, WHITE, AMBER if x == 80 else LINE, 10))
        b.append(text(x + 14, 362, head, 14, INK, "bold"))
        b.append(text(x + 14, 388, sub, 11, MUTED))
    b.append(arrow(800, 202, 800, 250, AMBER, 1.8))
    b.append(arrow(800, 250, 170, 250, AMBER, 1.6))
    b.append(arrow(170, 250, 170, 326, AMBER, 1.6))
    b.append(arrow(262, 375, 276, 375, MUTED, 1.4))
    b.append(arrow(462, 375, 476, 375, MUTED, 1.4))

    # small-satellite lane
    b.append(box(880, 260, 660, 210, SLATE_BG, LINE, 12, 1.2))
    b.append(text(900, 292, "小星故障", 15, AMBER, "bold"))
    for x, head, sub in [
        (900, "① 健康检查失败", "心跳 / 命令回执超时"),
        (1100, "② 标记 FAILED", "从健康集合移除"),
        (1300, "③ 计划重构", "plan_version + 1"),
    ]:
        b.append(box(x, 330, 180, 90, WHITE, AMBER if x == 900 else LINE, 10))
        b.append(text(x + 14, 362, head, 13, INK, "bold"))
        b.append(text(x + 14, 388, sub, 11, MUTED))
    b.append(arrow(800, 202, 800, 250, AMBER, 1.8))
    b.append(arrow(800, 250, 970, 250, AMBER, 1.6))
    b.append(arrow(970, 250, 970, 326, AMBER, 1.6))
    b.append(arrow(1082, 375, 1096, 375, MUTED, 1.4))
    b.append(arrow(1282, 375, 1296, 375, MUTED, 1.4))

    b.append(box(80, 520, 620, 80, WHITE, TEAL, 10, 1.6))
    b.append(text(96, 552, "④ 重建计划并继续观测", 15, INK, "bold"))
    b.append(text(96, 578, "在编小星任务重分配，未完成任务按旧版本作废", 11, MUTED))
    b.append(arrow(170, 472, 170, 516, TEAL, 1.8, "arrow-teal"))
    b.append(arrow(300, 472, 300, 516, TEAL, 1.8, "arrow-teal"))

    b.append(box(880, 520, 620, 80, WHITE, TEAL, 10, 1.6))
    b.append(text(896, 552, "④ 阵列重构", 15, INK, "bold"))
    b.append(text(896, 578, "uv 覆盖与基线数更新，健康数写入快照", 11, MUTED))
    b.append(arrow(1390, 472, 1390, 516, TEAL, 1.8, "arrow-teal"))

    b.append(box(620, 650, 360, 90, AMBER_BG, AMBER, 10, 1.8))
    b.append(text(800, 684, "恢复请求", 16, INK, "bold", "middle"))
    b.append(text(800, 710, "显式恢复 / 主控重新就绪", 11, MUTED, "normal", "middle"))
    b.append(arrow(390, 602, 620, 672, MUTED, 1.6))
    b.append(arrow(1210, 602, 980, 672, MUTED, 1.6))

    b.append(box(600, 790, 400, 70, WHITE, TEAL, 10, 1.6))
    b.append(text(800, 820, "健康检查通过 → 重新纳入 → plan + 1", 14, INK, "bold", "middle"))
    b.append(text(800, 846, "全过程写入审计事件流", 10, MUTED, "normal", "middle"))
    b.append(arrow(800, 742, 800, 786, TEAL, 1.8, "arrow-teal"))
    return svg(1600, 900, "\n".join(b))


if __name__ == "__main__":
    from pathlib import Path

    from make_diagrams import OUT

    for name, content in {
        "06-operation-flow.svg": operation_flow(),
        "07-fault-response.svg": fault_response(),
    }.items():
        (OUT / name).write_text(content, encoding="utf-8")
        print("wrote", name)
