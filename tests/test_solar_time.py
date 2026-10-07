"""真太阳时经度修正黄金样本（设计文档 §4.4 / §6.1）。

数据来源：
  - golden/longitudes.yaml      —— 不同经度城市逐条断言 lon_correction_min
  - golden/time_boundary.yaml   —— 其中带 expect.lon_correction_min 的 A 组样本
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

from astro.solar_time import to_true_solar_time   # noqa: E402
from astro.timezone_resolve import to_utc         # noqa: E402
from geo.cities import resolve_location           # noqa: E402


def load_golden(name):
    with open(GOLDEN_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def true_solar_chain(place, birth):
    """数据流 L0-a ~ L0-d：地名 + 钟表时间 → (真太阳时, solar_audit, loc)。"""
    loc = resolve_location(place)
    clock = datetime.strptime(birth, "%Y-%m-%d %H:%M")
    utc, _tz_audit = to_utc(clock, loc)
    tst, st_audit = to_true_solar_time(utc, loc.lon)
    return tst, st_audit, loc


class LongitudeCorrectionGoldenTest(unittest.TestCase):
    def test_longitudes_yaml(self):
        samples = load_golden("longitudes.yaml")
        self.assertGreaterEqual(len(samples), 5, "longitudes.yaml 至少需要 5 组样本")
        for s in samples:
            with self.subTest(sample=s["name"], place=s["place"]):
                _tst, audit, loc = true_solar_chain(s["place"], s["birth"])
                # 城市表经度 sanity check（0.1° 级即够，见文档 §4.1）
                self.assertAlmostEqual(loc.lon, s["lon"], delta=0.1)
                self.assertAlmostEqual(
                    audit["lon_correction_min"],
                    s["expect_lon_correction_min"],
                    delta=s["tolerance"],
                )


class TimeBoundaryGoldenTest(unittest.TestCase):
    """文档 §6.1 A 组：乌鲁木齐 / 成都 / 上海。"""

    def test_time_boundary_yaml(self):
        samples = [
            s for s in load_golden("time_boundary.yaml")
            if "lon_correction_min" in s.get("expect", {})
        ]
        self.assertGreaterEqual(len(samples), 3, "time_boundary.yaml A 组应有 3 条样本")
        for s in samples:
            with self.subTest(sample=s["name"], place=s["place"]):
                tst, audit, _loc = true_solar_chain(s["place"], s["birth"])
                self.assertAlmostEqual(
                    audit["lon_correction_min"],
                    s["expect"]["lon_correction_min"],
                    delta=s["tolerance"],
                )
                if "true_solar_time" in s["expect"]:
                    want = datetime.strptime(
                        s["expect"]["true_solar_time"], "%Y-%m-%d %H:%M"
                    )
                    tol_min = s["expect"].get("true_solar_time_tolerance_min", 3)
                    self.assertLessEqual(
                        abs((tst - want).total_seconds()),
                        tol_min * 60,
                        f"真太阳时 {tst} 与期望 {want} 差距超过 {tol_min} 分钟",
                    )


if __name__ == "__main__":
    unittest.main()
