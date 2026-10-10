#!/usr/bin/env python3
"""岁运神煞实时查询 —— 模型按需调用。

用法：
    python query_shensha.py --gender 女 \
        --pillars "丁亥 乙巳 庚子 辛巳" --target 丙午 [--label "2026 流年"]

输出（stdout）：
  - 以本命锚点（日干、年支、日支、月令、年柱纳音、阴阳男女）查得、目标干支所逢之神煞；
  - 目标干支自身所属之日柱固定组（阴差阳错、十灵日、魁罡、十恶大败、天赦，供流日参看）。
查法口径与排盘输出 `## 神煞` 一致（chart/shensha.py，规则见 rules/94_神煞细节.md）。

退出码：0 成功；2 输入不可用；3 内部错误。
"""
import argparse
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _runtime_guard  # noqa: F401  import 即检查：Python < 3.10 时中文报错退出（码 3）


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="query_shensha.py",
        description="查询某一干支（流年/流月/大运/流日）相对本命四柱所逢的神煞",
    )
    ap.add_argument("--gender", required=True, choices=["男", "女"], help="性别")
    ap.add_argument("--pillars", required=True,
                    help='本命四柱干支，年月日时顺序，空格分隔，如 "丁亥 乙巳 庚子 辛巳"')
    ap.add_argument("--target", required=True,
                    help="目标干支（流年/流月/大运/流日），如 丙午")
    ap.add_argument("--label", default="", help='目标说明，如 "2026 流年"，仅用于输出标题')
    a = ap.parse_args()

    try:
        from chart.shensha import evaluate_target, GAN, ZHI

        parts = a.pillars.split()
        if len(parts) != 4 or any(len(p) != 2 or p[0] not in GAN or p[1] not in ZHI
                                  for p in parts):
            print("ERROR: --pillars 应为年月日时四组干支，如 \"丁亥 乙巳 庚子 辛巳\"。",
                  file=sys.stderr)
            return 2
        target = a.target.strip()
        if len(target) != 2 or target[0] not in GAN or target[1] not in ZHI:
            print("ERROR: --target 应为一组干支，如 丙午。", file=sys.stderr)
            return 2

        pillars = dict(zip(("year", "month", "day", "hour"), parts))
        result = evaluate_target(pillars, a.gender, target)

        title = f"# 神煞查询：{target}"
        if a.label:
            title += f"（{a.label}）"
        title += f"　对　{' / '.join(parts)}（{a.gender}）"
        print(title)
        print()
        print("## 本命锚点查得（岁运逢）")
        print()
        if result["anchored"]:
            for star, note in result["anchored"]:
                print(f"- {star}（{note}）")
        else:
            print("- （无）")
        print()
        print("## 目标干支自身所属")
        print()
        if result["own"]:
            for star, note in result["own"]:
                print(f"- {star}（{note}）")
        else:
            print("- （无）")
        return 0
    except Exception:
        print("ERROR: 查询内部错误。", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
