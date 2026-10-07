"""子初换日（设计文档 §4.5 / §6.1 B 组）。

- 纯函数边界：真太阳时 22:59→当日 False，23:00→次日 True，
  23:59→次日 True，00:00→当日 False
- 黄金样本：golden/time_boundary.yaml 中带 expect.is_late_zi 的条目，
  走全链条 L0-a ~ L0-e（日界判定必须用真太阳时，不能用钟表时间）
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

from astro.day_boundary import resolve_calendar_day   # noqa: E402
from astro.solar_time import to_true_solar_time       # noqa: E402
from astro.timezone_resolve import to_utc             # noqa: E402
from geo.cities import resolve_location               # noqa: E402

# (真太阳时, 期望日历日, 期望 is_late_zi)
BOUNDARY_CASES = [
    ("1990-06-15 22:59", "1990-06-15", False),
    ("1990-06-15 23:00", "1990-06-16", True),
    ("1990-06-15 23:59", "1990-06-16", True),
    ("1990-06-16 00:00", "1990-06-16", False),
]


class DayBoundaryUnitTest(unittest.TestCase):
    def test_boundary_cases(self):
        for tst_str, day_str, expect_late in BOUNDARY_CASES:
            with self.subTest(tst=tst_str):
                tst = datetime.strptime(tst_str, "%Y-%m-%d %H:%M")
                day, flag = resolve_calendar_day(tst)
                self.assertEqual(day, datetime.strptime(day_str, "%Y-%m-%d"))
                self.assertIs(flag["is_late_zi"], expect_late)

    def test_day_is_midnight(self):
        # 返回的日历日必须是 00:00:00
        day, _flag = resolve_calendar_day(datetime(1990, 6, 15, 23, 30))
        self.assertEqual((day.hour, day.minute, day.second), (0, 0, 0))


class LateZiGoldenTest(unittest.TestCase):
    def test_late_zi_samples(self):
        with open(GOLDEN_DIR / "time_boundary.yaml", encoding="utf-8") as f:
            samples = [
                s for s in yaml.safe_load(f)
                if "is_late_zi" in s.get("expect", {})
            ]
        self.assertGreaterEqual(len(samples), 2, "time_boundary.yaml B 组应有 2 条样本")
        for s in samples:
            with self.subTest(sample=s["name"], place=s["place"]):
                loc = resolve_location(s["place"])
                clock = datetime.strptime(s["birth"], "%Y-%m-%d %H:%M")
                utc, _tz_audit = to_utc(clock, loc)
                tst, _st_audit = to_true_solar_time(utc, loc.lon)
                _day, flag = resolve_calendar_day(tst)
                self.assertIs(flag["is_late_zi"], s["expect"]["is_late_zi"])


if __name__ == "__main__":
    unittest.main()
