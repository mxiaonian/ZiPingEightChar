"""HTML 盘面渲染测试（render/html.py + cast_chart --html）。"""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))


def _chart():
    """用真实排盘管线造一份 ChartData（成都 1990 男盘）。"""
    from datetime import datetime
    from astro.solar_time import to_true_solar_time
    from astro.timezone_resolve import to_utc
    from astro.day_boundary import resolve_calendar_day
    from chart.tyme_adapter import cast
    from chart.luck import (childhood_luck, compute_luck, decade_pillars,
                            flow_months, flow_years, is_forward,
                            luck_label_for_year)
    from chart.model import build_chart_data
    from geo.cities import resolve_location

    loc = resolve_location("四川省成都市")
    clock = datetime(1990, 5, 14, 8, 30)
    utc, tz_audit = to_utc(clock, loc)
    tst, st_audit = to_true_solar_time(utc, loc.lon)
    day, bd_audit = resolve_calendar_day(tst)
    cast_dt = day.replace(hour=tst.hour, minute=tst.minute, second=tst.second)
    raw = cast(cast_dt, "男")
    forward = is_forward("男", raw["year"]["gan"])
    luck = compute_luck(birth_tst=tst, prev_jie_time=raw["prev_jie"]["time"],
                        next_jie_time=raw["next_jie"]["time"], forward=forward)
    this_year = datetime.now().year
    decade = decade_pillars(raw["month"]["gan"], raw["month"]["zhi"], forward,
                            luck["start_age_years"], cast_dt.year)
    years = [(y, gz, luck_label_for_year(y, decade))
             for y, gz in flow_years(cast_dt.year, this_year, 10)]
    return build_chart_data(
        name="张三", gender="男", place="四川省成都市",
        clock="1990-05-14 08:30", loc=loc, tz_audit=tz_audit,
        st_audit=st_audit, bd_audit=bd_audit, raw=raw, luck=luck,
        luck_pillars=decade, flow_years=years,
        flow_months=flow_months(this_year),
        childhood_luck=childhood_luck(raw["hour"]["gan"], raw["hour"]["zhi"],
                                      forward, luck["start_age_years"],
                                      cast_dt.year),
    )


class HtmlRenderTest(unittest.TestCase):
    def test_render_complete(self):
        from render.html import build_html
        html = build_html(_chart())
        self.assertFalse(re.findall(r"\{\{[A-Z_]+\}\}", html), "存在未填充占位符")
        for ch in ("庚", "午", "辛", "巳", "己", "卯", "丁"):
            self.assertIn(ch, html)
        for sect in ("排盘", "大运", "流年", "流月", "空亡", "神煞", "纳音"):
            self.assertIn(sect, html)

    def test_ten_god_table(self):
        from render.html import _ten_god
        self.assertEqual(_ten_god("庚", "丁"), "正官")
        self.assertEqual(_ten_god("庚", "丙"), "七杀")
        self.assertEqual(_ten_god("庚", "辛"), "劫财")
        self.assertEqual(_ten_god("庚", "壬"), "食神")

    def test_void_and_terrain(self):
        from render.html import _gz_void, _terrain
        self.assertEqual(_gz_void("庚子"), "辰巳")
        self.assertEqual(_gz_void("甲子"), "戌亥")
        self.assertEqual(_terrain("庚", "巳"), "长生")
        self.assertEqual(_terrain("庚", "子"), "死")


class CastHtmlE2ETest(unittest.TestCase):
    def test_html_flag_writes_file(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "p.html"
            r = subprocess.run(
                [sys.executable, str(SKILL_ROOT / "scripts" / "cast_chart.py"),
                 "--name", "张三", "--gender", "男", "--birth", "1990-05-14 08:30",
                 "--place", "四川省成都市", "--html", str(out)],
                capture_output=True, text=True, timeout=120,
                cwd=str(SKILL_ROOT / "scripts"))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(r.stdout.startswith("# 命盘：张三"))
            self.assertIn("HTML 盘面：", r.stderr)
            html = out.read_text(encoding="utf-8")
            self.assertIn("<table", html)


if __name__ == "__main__":
    unittest.main()
