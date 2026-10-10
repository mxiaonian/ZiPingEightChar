#!/usr/bin/env python3
"""命主档案检索 —— 按任意组合条件查 memory/archives/。

用法：
    python memory_lookup.py [--name 张三] [--birth "1990-05-14 08:30"] \
        [--place 四川省成都市] [--gender 男] [--pillars "丁亥 乙巳 庚子 辛巳"]

条件可任意组合（至少一项），全部命中才算匹配；比较大小写/空白容错。
输出：每份命中档案的路径与 frontmatter 摘要；无匹配输出「无档案」。

只读档案、不排盘，不经过软锁。档案规范见 memory/README.md。

退出码：0 检索完成（含无匹配）；2 输入不可用；3 内部错误。
"""
import argparse
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _runtime_guard  # noqa: F401  import 即检查：Python < 3.10 时中文报错退出（码 3）
import _memory_store as store


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="memory_lookup.py",
        description="命主档案检索：按姓名/出生时刻/出生地/性别/四柱任意组合查 memory/archives/",
    )
    ap.add_argument("--name", default=None, help="姓名")
    ap.add_argument("--gender", default=None, choices=["男", "女"], help="性别")
    ap.add_argument("--birth", default=None,
                    help='出生时刻（当地钟表时间），格式 "YYYY-MM-DD HH:MM"')
    ap.add_argument("--place", default=None, help="出生地")
    ap.add_argument("--pillars", default=None,
                    help='四柱干支，年月日时顺序，空格分隔，如 "丁亥 乙巳 庚子 辛巳"')
    ap.add_argument("--memory-root", default=None,
                    help=f"档案根目录（默认技能根 memory/；亦可用环境变量 {store.ENV_VAR}）")
    a = ap.parse_args()

    if all(v is None for v in (a.name, a.gender, a.birth, a.place, a.pillars)):
        print("ERROR: 至少给一个检索条件（--name/--birth/--place/--gender/--pillars）。",
              file=sys.stderr)
        return 2
    if a.pillars is not None and len(a.pillars.split()) != 4:
        print("ERROR: --pillars 应为年月日时四组干支，如 \"丁亥 乙巳 庚子 辛巳\"。",
              file=sys.stderr)
        return 2

    try:
        root = store.resolve_root(a.memory_root, __file__)
        hits = []
        for path in store.iter_archives(root):
            meta, _ = store.parse_frontmatter(path.read_text(encoding="utf-8"))
            if not meta:
                continue
            if store.matches(meta, name=a.name, birth=a.birth, place=a.place,
                             gender=a.gender, pillars=a.pillars):
                hits.append((path, meta))

        if not hits:
            print("无档案")
            return 0
        print(f"命中 {len(hits)} 份档案：\n")
        for path, meta in hits:
            print(path)
            for k in store.FIELDS:
                v = meta.get(k, "")
                if isinstance(v, list):
                    v = " ".join(str(x) for x in v)
                print(f"  {k}: {v}")
            print()
        return 0
    except Exception:
        print("ERROR: 检索内部错误。", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
