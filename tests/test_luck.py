"""流年/小运/大运标签单元测试（schema 1.2）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from chart.luck import (  # noqa: E402
    childhood_luck, decade_pillars, flow_years, ganzhi_of_year,
    luck_label_for_year,
)
from chart.model import LuckPillar  # noqa: E402


class FlowYearsTest(unittest.TestCase):
    def test_ganzhi_of_year(self):
        self.assertEqual(ganzhi_of_year(2007), "丁亥")
        self.assertEqual(ganzhi_of_year(2026), "丙午")

    def test_full_range_from_birth_year(self):
        years = flow_years(2007, 2026, 10)
        self.assertEqual(years[0], (2007, "丁亥"))
        self.assertEqual(years[-1], (2035, "乙卯"))
        self.assertEqual(len(years), 29)
        self.assertIn((2013, "癸巳"), years)


class ChildhoodLuckTest(unittest.TestCase):
    def test_forward(self):
        # 阴年女命顺行：时柱辛巳 → 1 岁壬午、2 岁癸未……10 岁辛卯
        rows = childhood_luck("辛", "巳", True, 10.34, 2007)
        self.assertEqual(rows[0], (1, 2007, "壬午"))
        self.assertEqual(rows[1], (2, 2008, "癸未"))
        self.assertEqual(rows[-1], (10, 2016, "辛卯"))
        self.assertEqual(len(rows), 10)

    def test_backward(self):
        rows = childhood_luck("辛", "巳", False, 3.0, 2000)
        self.assertEqual(rows[0], (1, 2000, "庚辰"))
        self.assertEqual(rows[-1], (3, 2002, "戊寅"))

    def test_empty_when_luck_starts_under_one(self):
        self.assertEqual(childhood_luck("辛", "巳", True, 0.34, 2007), [])


class LuckLabelTest(unittest.TestCase):
    def setUp(self):
        self.pillars = [
            LuckPillar(index=1, gan="丙", zhi="午", start_age=10.34, start_year=2017),
            LuckPillar(index=2, gan="丁", zhi="未", start_age=20.34, start_year=2027),
        ]

    def test_childhood(self):
        self.assertEqual(luck_label_for_year(2013, self.pillars), "童限")

    def test_boundary_year(self):
        self.assertEqual(luck_label_for_year(2017, self.pillars), "交运年·入丙午运")

    def test_inside_pillar(self):
        self.assertEqual(luck_label_for_year(2020, self.pillars), "丙午运")
        self.assertEqual(luck_label_for_year(2030, self.pillars), "丁未运")

    def test_no_pillars(self):
        self.assertEqual(luck_label_for_year(2020, []), "童限")


if __name__ == "__main__":
    unittest.main()
