"""历史时区 / 夏令时黄金样本（设计文档 §4.3 / §6.1 C 组）。

逐条读 golden/history_tz.yaml，断言 to_utc 返回的 (utc, audit)：
  - tz_used / is_dst / dst_offset_min / source：audit 字段逐项相等
  - utc_offset_min：钟表时间 − UTC（分钟），验证 UTC 解算本身
"""
import sys
import unittest
from datetime import datetime
from pathlib import Path

import yaml

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from astro.timezone_resolve import to_utc   # noqa: E402
from geo.cities import resolve_location     # noqa: E402

AUDIT_KEYS = ("tz_used", "is_dst", "dst_offset_min", "source")


class HistoryTzGoldenTest(unittest.TestCase):
    def test_history_tz_yaml(self):
        with open(GOLDEN_DIR / "history_tz.yaml", encoding="utf-8") as f:
            samples = yaml.safe_load(f)
        self.assertGreaterEqual(len(samples), 4, "history_tz.yaml 应有 4 条样本")
        for s in samples:
            with self.subTest(sample=s["name"], place=s["place"]):
                loc = resolve_location(s["place"])
                clock = datetime.strptime(s["birth"], "%Y-%m-%d %H:%M")
                utc, audit = to_utc(clock, loc)
                expect = s["expect"]
                for key in AUDIT_KEYS:
                    if key in expect:
                        self.assertEqual(
                            audit[key], expect[key], f"audit[{key!r}] 不符"
                        )
                if "utc_offset_min" in expect:
                    offset_min = (
                        clock - utc.replace(tzinfo=None)
                    ).total_seconds() / 60
                    self.assertAlmostEqual(
                        offset_min, expect["utc_offset_min"], delta=0.5,
                        msg=f"UTC 偏移 {offset_min} 分 ≠ 期望 "
                            f"{expect['utc_offset_min']} 分",
                    )


class HkMoDstTest(unittest.TestCase):
    """香港/澳门时区回归：1986–1991 中国大陆实行夏令时，港澳 1979 年后无；
    cities.json 港澳条目必须为 Asia/Hong_Kong / Asia/Macau，不得随大陆拨快。"""

    def test_hongkong_1987_no_dst(self):
        loc = resolve_location("香港")
        _utc, audit = to_utc(datetime(1987, 7, 5, 5, 0), loc)
        self.assertEqual(loc.tz, "Asia/Hong_Kong")
        self.assertIs(audit["is_dst"], False)

    def test_macau_1987_no_dst(self):
        loc = resolve_location("澳门")
        _utc, audit = to_utc(datetime(1987, 7, 5, 5, 0), loc)
        self.assertEqual(loc.tz, "Asia/Macau")
        self.assertIs(audit["is_dst"], False)

    def test_mainland_1987_dst_kept(self):
        # 回归保护：大陆 1987 年夏令时仍应拨快
        loc = resolve_location("北京")
        _utc, audit = to_utc(datetime(1987, 7, 5, 5, 0), loc)
        self.assertIs(audit["is_dst"], True)

    def test_hongkong_1970_historical_dst(self):
        # 香港 1949 后的历史夏令时（如 1970 年）应被 IANA 库正确处理
        # （1949 前走民国五时区历史表分支，不在此断言范围）
        loc = resolve_location("香港")
        _utc, audit = to_utc(datetime(1970, 7, 15, 12, 0), loc)
        self.assertEqual(audit["tz_used"], "Asia/Hong_Kong")
        self.assertIs(audit["is_dst"], True)


if __name__ == "__main__":
    unittest.main()
