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

    def test_brand_head_embedded(self):
        """顶部品牌区：logo 与 LogoFont 均 base64 内嵌，口号在。"""
        from render.html import build_html
        html = build_html(_chart())
        self.assertIn("灵爻妙解", html)
        self.assertIn("传承易学智慧", html)
        self.assertIn('class="brand-head"', html)
        self.assertIn("data:image/png;base64,", html)
        self.assertIn("@font-face", html)
        self.assertIn("data:font/ttf;base64,", html)

    def test_qrcode_card(self):
        """尾部交流群卡：二维码 jpeg base64 内嵌，标题与正文文案各出现一次。"""
        from render.html import build_html
        html = build_html(_chart())
        self.assertIn('class="card qrcard"', html)
        self.assertIn("data:image/jpeg;base64,", html)
        self.assertEqual(html.count("灵爻妙解 · 传统文化交流群"), 1)
        self.assertEqual(
            html.count("扫码加入微信群：反馈解读偏差、交流文化心得、"
                       "参与档案共建，版本更新动态第一时间同步。"), 1)

    def test_audit_versions_only_in_comment(self):
        """技术信息并入用户信息卡：展示行删版本段，完整原文留在 HTML 注释。"""
        from render.html import build_html
        html = build_html(_chart())
        self.assertEqual(html.count("tyme4py"), 1)
        self.assertEqual(html.count("schema"), 1)
        m = re.search(r"<!--[^>]*tyme4py[^>]*-->", html)
        self.assertIsNotNone(m, "注释中应保留含 tyme4py/schema 的完整审计原文")
        self.assertIn("schema", m.group(0))
        self.assertIn("时区", m.group(0))
        self.assertIn("月令", html)
        self.assertIn("日界 子初换日（23:00）", html)

    def test_shensha_notes_stripped(self):
        """神煞括号注释在装配层剔除（全角/半角），Markdown 侧不受影响。"""
        from render.html import _strip_sha_note, build_html
        self.assertEqual(_strip_sha_note("将星（以年支子查，见于月支子）"), "将星")
        self.assertEqual(_strip_sha_note("天乙贵人(以日干查)"), "天乙贵人")
        self.assertEqual(_strip_sha_note("驿马"), "驿马")
        html = build_html(_chart())
        self.assertNotIn("（以", html)

    def test_luck_flow_card_removed(self):
        """「大运 · 流年」对照卡已整张删除；排盘卡仍只含四柱。"""
        from render.html import build_html
        html = build_html(_chart())
        self.assertNotIn("大运 · 流年", html)
        self.assertNotIn("当前一步大运与本年流年对照", html)
        self.assertNotIn("LUCK_FLOW_TABLE", html)
        pan_seg = html[html.find("排盘<span"):html.find('class="sect">大运')]
        self.assertIn("年柱", pan_seg)
        self.assertNotIn("大运", pan_seg)
        self.assertNotIn("流年", pan_seg)

    def test_luck_strip_enriched(self):
        """大运格：起运年+干支之外带十神·星运/空亡/纳音/神煞（2018 甲申运对拍）。"""
        from render.html import build_html
        html = build_html(_chart())
        seg = html[html.find('class="sect">大运'):html.find('class="sect">流年')]
        self.assertIn("2018 · 28 岁起", seg)
        self.assertIn("正官 · 沐浴", seg)          # 甲对日干己 / 己对申
        self.assertIn("午未", seg)                  # 甲申旬空
        self.assertIn("泉中水", seg)                # 甲申纳音
        self.assertIn("天乙贵人 · 金舆 · 驿马 · 劫煞 · 孤辰", seg)  # 甲申岁运神煞
        self.assertIn('class="cell cur"', seg)      # 当前一步高亮

    def test_flow_year_strip_enriched(self):
        """流年格：年份+干支之外带主星/星运/空亡/纳音/神煞（2026 丙午对拍）。"""
        from render.html import build_html
        html = build_html(_chart())
        seg = html[html.find('class="sect">流年'):html.find('class="sect">流月')]
        self.assertIn("正印 · 临官", seg)           # 丙对日干己 / 己对午
        self.assertIn("寅卯", seg)                  # 丙午旬空（甲辰旬）
        self.assertIn("天河水", seg)                # 丙午纳音
        self.assertIn("天德合 · 禄神 · 将星", seg)  # 丙午岁运神煞
        self.assertIn('class="cell cur"', seg)      # 本年高亮

    def test_strips_have_no_field_labels(self):
        """条带小卡只排值：不出现「主星/星运/空亡/纳音/神煞」字段标签。"""
        from render.html import build_html
        html = build_html(_chart())
        segs = [html[html.find('class="sect">大运'):html.find('class="sect">流年')],
                html[html.find('class="sect">流年'):html.find('class="sect">流月')]]
        for seg in segs:
            for label in ("主星", "星运", "空亡", "纳音", "神煞"):
                self.assertNotIn(label, seg)

    def test_ten_god_table(self):
        from chart.ganzhi import ten_god
        self.assertEqual(ten_god("庚", "丁"), "正官")
        self.assertEqual(ten_god("庚", "丙"), "七杀")
        self.assertEqual(ten_god("庚", "辛"), "劫财")
        self.assertEqual(ten_god("庚", "壬"), "食神")

    def test_void_and_terrain(self):
        from chart.ganzhi import gz_void, terrain
        self.assertEqual(gz_void("庚子"), "辰巳")
        self.assertEqual(gz_void("甲子"), "戌亥")
        self.assertEqual(terrain("庚", "巳"), "长生")
        self.assertEqual(terrain("庚", "子"), "死")

    def test_nayin_shared_with_shensha_module(self):
        """纳音表集中于 chart/ganzhi.py，chart/shensha.py 复用同一份。"""
        from chart.ganzhi import NAYIN
        from chart.shensha import NAYIN as SHA_NAYIN
        self.assertIs(NAYIN, SHA_NAYIN)
        self.assertEqual(NAYIN["甲辰"], "覆灯火")
        self.assertEqual(NAYIN["丙午"], "天河水")


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
