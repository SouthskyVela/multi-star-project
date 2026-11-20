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
    b = [title("系统操作流：四类操作的分支与汇合", "公共入口相同，按操作类型分流；破坏性操作需页面内二次确认，事件与模式切换不需要")]

    common = [
        (90, "① 打开面板", "浏览器访问 18082"),
        (450, "② 选择对象", "主星 / small-sat-0…8 / 表单"),
        (810, "③ 选择操作", "暂停、注入、恢复、事件、模式"),
    ]
    for x, head, sub in common:
        b.append(box(x, 120, 300, 70, WHITE, LINE, 10))
        b.append(text(x + 16, 150, head, 16, INK, "bold"))
        b.append(text(x + 16, 174, sub, 11, MUTED))
    b.append(arrow(392, 155, 446, 155, MUTED, 1.6))
    b.append(arrow(752, 155, 806, 155, MUTED, 1.6))

    b.append(box(1160, 120, 350, 70, SLATE_BG, LINE, 10, 1.2))
    b.append(text(1176, 150, "按操作类型分流", 15, INK, "bold"))
    b.append(text(1176, 174, "A 主控 / B 小星 / C 事件 / D 模式", 11, MUTED))
    b.append(arrow(1112, 155, 1156, 155, MUTED, 1.6))

    branches = [
        ("A 主控故障测试", 60, AMBER, [
            ("点击“暂停当前主控 22 秒”", "仅暂停，不销毁 Pod"),
            ("页面内二次确认（30 s）", "再次点击生效"),
            ("停止续约与命令下发", "旧主控进入静默"),
            ("租约过期，其他主星接管", "epoch + 1，重建计划"),
        ]),
        ("B 小星故障注入 / 恢复", 440, AMBER, [
            ("选择 small-sat 与“注入故障”", "下拉框指定目标"),
            ("页面内二次确认（30 s）", "防止误触"),
            ("执行器置 FAILED，移出健康集合", "健康 9→8，基线 36→28"),
            ("计划重构（plan + 1）", "剩余小星重分配任务"),
            ("点击“恢复故障”", "无需二次确认"),
            ("健康检查通过，重新纳入", "健康 8→9，plan + 1"),
        ]),
        ("C 天文事件提交", 820, TEAL, [
            ("填写事件字段", "频率 / 通量 / 谱指数 / 有效期"),
            ("点击“提交事件”", "单次点击，无需确认"),
            ("event_id 去重", "重复提交不抬版本"),
            ("进入 FIXED_SOURCE", "plan + 1，事件到期回退"),
        ]),
        ("D 运行模式切换", 1200, TEAL, [
            ("点击 SURVEY / FIXED_SOURCE / CALIBRATION", "顶部模式按钮"),
            ("前置校验", "健康 ≥ 2，且无 UNKNOWN 任务"),
            ("切换模式", "plan + 1，任务整体重排"),
        ]),
    ]

    for name, x, color, steps in branches:
        b.append(box(x, 235, 340, 46, AMBER_BG if color == AMBER else TEAL_BG, color, 8, 1.6))
        b.append(text(x + 14, 264, name, 14, INK, "bold"))
        b.append(arrow(x + 170, 193, x + 170, 231, color, 1.6, "arrow-teal" if color == TEAL else "arrow"))
        y = 300
        for head, sub in steps:
            b.append(box(x, y, 340, 52, WHITE, LINE, 8, 1.3))
            b.append(text(x + 12, y + 22, head, 12, INK, "bold"))
            b.append(text(x + 12, y + 42, sub, 10, MUTED))
            y += 64

    b.append(box(60, 745, 460, 60, SLATE_BG, LINE, 10))
    b.append(text(76, 772, "④ 快照刷新（1 s）", 14, INK, "bold"))
    b.append(text(76, 794, "面板读取 /api/snapshot，不读缓存", 10, MUTED))

    b.append(box(560, 745, 460, 60, SLATE_BG, LINE, 10))
    b.append(text(576, 772, "⑤ 结果核对", 14, INK, "bold"))
    b.append(text(576, 794, "主控 / 健康数 / 基线 / 模式", 10, MUTED))

    b.append(box(1060, 745, 460, 60, SLATE_BG, LINE, 10))
    b.append(text(1076, 772, "⑥ 审计与追溯", 14, INK, "bold"))
    b.append(text(1076, 794, "事件流 + 日志 + 版本号", 10, MUTED))

    for x, steps in [(60, branches[0][3]), (440, branches[1][3]), (820, branches[2][3]), (1200, branches[3][3])]:
        y_end = 300 + len(steps) * 64 - 12
        b.append(arrow(x + 170, y_end + 2, x + 170, 741, MUTED, 1.4))
    b.append(arrow(524, 775, 556, 775, MUTED, 1.4))
    b.append(arrow(1024, 775, 1056, 775, MUTED, 1.4))
    return svg(1600, 860, chr(10).join(b))


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
