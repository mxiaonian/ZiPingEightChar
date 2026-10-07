"""均时差单测：四个已知极值点（设计文档 §4.2 / §6.2）。

采样方式：UTC 正午（12:00Z），容差 ±0.5 分。
"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from astro.equation_of_time import equation_of_time_minutes  # noqa: E402

# (月, 日, 已知均时差/分) —— 文档 §4.2 给出的全年极值
EXTREMA = [
    (2, 11, -14.2),   # 全年最小
    (5, 14, 3.7),
    (7, 26, -6.5),
    (11, 3, 16.4),    # 全年最大
]


class EquationOfTimeExtremumTest(unittest.TestCase):
    def test_extremum_points(self):
        for month, day, expected in EXTREMA:
            with self.subTest(date=f"1990-{month:02d}-{day:02d}"):
                dt_utc = datetime(1990, month, day, 12, 0, tzinfo=timezone.utc)
                eot = equation_of_time_minutes(dt_utc)
                self.assertAlmostEqual(eot, expected, delta=0.5)

    def test_year_round_within_physical_bounds(self):
        # 每月 15 日 UTC 正午采样，均时差物理范围应落在约 −14.3 ~ +16.5 分内
        for month in range(1, 13):
            with self.subTest(month=month):
                dt_utc = datetime(1990, month, 15, 12, 0, tzinfo=timezone.utc)
                eot = equation_of_time_minutes(dt_utc)
                self.assertGreaterEqual(eot, -14.7)
                self.assertLessEqual(eot, 16.9)

    def test_naive_datetime_rejected(self):
        # 文档 §4.2 契约：必须传入带时区的 UTC datetime
        with self.assertRaises(AssertionError):
            equation_of_time_minutes(datetime(1990, 1, 1, 12, 0))


if __name__ == "__main__":
    unittest.main()
