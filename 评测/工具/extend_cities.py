#!/usr/bin/env python3
"""评测用地点扩展：给技能副本的 data/cities.json 追加境外/模糊地名的代理城市条目。

条目与首次评测（fate_benchmark 工作区）所用完全一致，原样搬来：
- 境外城市按真实 IANA 时区（台北/吉隆坡/新加坡/宫崎/香港/澳门）；
- 模糊地名（美国/中国/中国大陆）代理到杭州 120.16E Asia/Shanghai，
  对齐官方 UTC+8 简化口径；港澳条目对齐母版修复口径（tzdata 自带
  1949–1979 夏令时、无 1986–1991 大陆夏令时）。

用法：
    python extend_cities.py [--cities <技能副本 data/cities.json>]
                            [--scripts <技能副本 scripts 目录>]
                            [--questions <盲版题目目录>]

追加后批跑校验：--questions 所指各届所有命主的 place 字符串逐一过
resolve_location，全部命中才算通过。默认指向母版自身（scripts/、data/），
评测复测时通常先复制一份技能再对副本执行本脚本，避免改动母版。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # 评测/
SKILL = Path(__file__).resolve().parents[2]         # 技能母版根
DEFAULT_QUESTIONS = ROOT / "试题" / "BaziQA-全球算命师大赛" / "questions"

TAIPEI = {"lon": 121.56, "lat": 25.03, "tz": "Asia/Taipei"}
KL = {"lon": 101.69, "lat": 3.14, "tz": "Asia/Kuala_Lumpur"}
SG = {"lon": 103.85, "lat": 1.29, "tz": "Asia/Singapore"}
MIYAZAKI = {"lon": 131.42, "lat": 31.91, "tz": "Asia/Tokyo"}
# 官方口径统一按 UTC+8 处理，美国/中国等模糊地名代理到杭州（120.16E）
HANGZHOU_PROXY = {"lon": 120.16, "lat": 30.29, "tz": "Asia/Shanghai"}
# 港澳对齐母版修复口径：港澳 tzdata 自带 1949–1979 夏令时、无 1986–1991 大陆夏令时
HK = {"lon": 114.17, "lat": 22.32, "tz": "Asia/Hong_Kong"}
MO = {"lon": 113.54, "lat": 22.2, "tz": "Asia/Macau"}
GZ = {"lon": 113.26, "lat": 23.13, "tz": "Asia/Shanghai"}
ST = {"lon": 116.68, "lat": 23.35, "tz": "Asia/Shanghai"}
BJ = {"lon": 116.41, "lat": 39.9, "tz": "Asia/Shanghai"}

EXTRA = {
    "台北": TAIPEI, "台湾": TAIPEI, "中国台湾": TAIPEI, "台湾，中国": TAIPEI,
    "吉隆坡": KL, "马来西亚": KL,
    "新加坡": SG,
    "宫崎": MIYAZAKI, "日本": MIYAZAKI, "日本宫崎": MIYAZAKI, "日本宫崎县": MIYAZAKI,
    "美国": HANGZHOU_PROXY, "中国": HANGZHOU_PROXY, "中国大陆": HANGZHOU_PROXY,
    "中国香港": HK, "香港，中国": HK,
    "中国澳门": MO, "澳门，中国": MO,
    "广东": GZ, "广东，中国": GZ,
    "潮汕": ST, "广东潮汕，中国": ST,
    "北京，中国": BJ,
}


def main() -> int:
    ap = argparse.ArgumentParser(description="评测用地点扩展（境外/模糊地名 → 代理城市）")
    ap.add_argument("--cities", type=Path, default=SKILL / "data" / "cities.json")
    ap.add_argument("--scripts", type=Path, default=SKILL / "scripts")
    ap.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    a = ap.parse_args()

    table = json.loads(a.cities.read_text(encoding="utf-8"))
    added = 0
    for k, v in EXTRA.items():
        if k not in table:
            table[k] = v
            added += 1
    a.cities.write_text(json.dumps(table, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    print(f"追加 {added} 条（目标 {len(EXTRA)} 条），总条目 {len(table)}")

    # 批跑校验：各届全部命主的 place 逐一解析
    sys.path.insert(0, str(a.scripts))
    from geo.cities import resolve_location  # noqa: E402

    ok = fail = 0
    for f in sorted(a.questions.glob("contest8_*.json")):
        for p in json.loads(f.read_text(encoding="utf-8"))[1:]:
            place = p["profile"]["birth"]["place"]
            try:
                loc = resolve_location(place)
                ok += 1
                print(f"  OK  {f.name} {p['person_id']:<40} {place!r} -> "
                      f"{loc.name} {loc.lon}E {loc.tz}")
            except Exception as e:  # noqa: BLE001
                fail += 1
                print(f"  FAIL {f.name} {p['person_id']:<40} {place!r}: {e}")
    print(f"地点解析: {ok} 成功 / {fail} 失败")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
