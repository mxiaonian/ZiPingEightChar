"""神煞求值单元测试（chart/shensha.py）。

对拍基准：rules/94_神煞细节.md 各条目查法 + 《三命通会》卷三诸神煞篇。
整盘向量取「丁亥/乙巳/庚子/辛巳（女）」，与人工按 94 篇逐条手推的结果一致。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from chart.ganzhi import GAN, ZHI  # noqa: E402
from chart.shensha import STAR_ORDER, evaluate_natal, evaluate_target  # noqa: E402

_VENDOR = Path(__file__).resolve().parents[1] / "vendor"
if _VENDOR.is_dir():
    sys.path.insert(0, str(_VENDOR))
try:  # 排盘适配层（含排序逻辑）；无 tyme4py 的环境跳过其回归测试
    from chart.tyme_adapter import _shen_sha
except ImportError:  # pragma: no cover
    _shen_sha = None


def natal(year, month, day, hour, gender="男"):
    return evaluate_natal(
        {"year": year, "month": month, "day": day, "hour": hour}, gender)


def stars(result, key):
    return {s for s, _ in result[key]}


class WholeChartVectorTest(unittest.TestCase):
    """丁亥/乙巳/庚子/辛巳（女）整盘对拍。"""

    @classmethod
    def setUpClass(cls):
        cls.r = natal("丁亥", "乙巳", "庚子", "辛巳", gender="女")

    def test_year(self):
        self.assertEqual(stars(self.r, "year"), {"文昌", "太极贵人", "亡神"})

    def test_month(self):
        self.assertEqual(stars(self.r, "month"),
                         {"月德合", "驿马", "劫煞", "地网"})

    def test_day(self):
        self.assertEqual(stars(self.r, "day"), {"月德", "桃花", "将星"})

    def test_hour(self):
        self.assertEqual(stars(self.r, "hour"),
                         {"天德", "驿马", "劫煞", "地网", "童子煞"})

    def test_combo_empty(self):
        self.assertEqual(self.r["combo"], [])


class GanLookupTest(unittest.TestCase):
    """日干查支诸星。"""

    def test_tianyi(self):
        r = natal("甲子", "丙寅", "甲午", "辛未")  # 甲日 → 丑未
        self.assertIn("天乙贵人", stars(r, "hour"))
        self.assertNotIn("天乙贵人", stars(r, "year"))

    def test_lu_ren_jinyu(self):
        r = natal("丙子", "庚寅", "甲申", "己巳")  # 甲禄在寅
        self.assertIn("禄神", stars(r, "month"))
        all_stars = stars(r, "month") | stars(r, "day") | stars(r, "year") | stars(r, "hour")
        self.assertNotIn("羊刃", all_stars)  # 盘无卯，甲日亦无刃可取
        r2 = natal("丙子", "庚寅", "甲辰", "己巳")  # 甲日金舆在辰
        self.assertIn("金舆", stars(r2, "day"))

    def test_yangren_yang_gan(self):
        r = natal("丙子", "辛卯", "甲戌", "己巳")  # 甲刃在卯
        self.assertIn("羊刃", stars(r, "month"))

    def test_yangren_yin_gan_none(self):
        """阴干无刃：乙日见卯只取禄，不取刃。"""
        r = natal("丙子", "庚寅", "乙卯", "己巳")
        self.assertNotIn("羊刃", stars(r, "day"))
        self.assertIn("禄神", stars(r, "day"))

    def test_taiji_fuxing_hongyan(self):
        r = natal("丙子", "庚寅", "庚午", "丁亥")  # 庚日：太极寅亥、福星午、红艳戌
        self.assertIn("太极贵人", stars(r, "hour"))
        self.assertIn("福星贵人", stars(r, "day"))
        self.assertNotIn("红艳", stars(r, "day") | stars(r, "hour"))

    def test_wenchang(self):
        r = natal("丙子", "庚寅", "乙巳", "丁午")  # 乙日文昌在午
        self.assertIn("文昌", stars(r, "hour"))


class MonthLingTest(unittest.TestCase):
    """月令查天德、月德及其合（可应天干或地支）。"""

    def test_tiande_stem_and_branch(self):
        r = natal("辛亥", "庚寅", "丁子", "辛巳")  # 寅月天德丁（日干）、天德合壬
        self.assertIn("天德", stars(r, "day"))
        r2 = natal("辛亥", "庚寅", "壬子", "辛巳")
        self.assertIn("天德合", stars(r2, "day"))

    def test_tiande_branch_hit(self):
        r = natal("甲子", "庚午", "丙子", "己亥")  # 午月天德亥（时支）、月德丙（日干）
        self.assertIn("天德", stars(r, "hour"))
        self.assertIn("月德", stars(r, "day"))

    def test_yuede(self):
        r = natal("戊申", "壬子", "甲子", "丙寅")  # 子月（申子辰）月德壬、月德合丁
        self.assertIn("月德", stars(r, "month"))
        r2 = natal("戊申", "丁丑", "甲子", "丙寅")  # 丑月（巳酉丑）月德庚
        self.assertNotIn("月德", stars(r2, "month"))


class SanheLookupTest(unittest.TestCase):
    """三合局诸煞：年支、日支并查。"""

    def test_yima_double_anchor(self):
        # 年支巳（巳酉丑→亥）、日支午（寅午戌→申）
        r = natal("辛巳", "庚寅", "戊午", "壬申")
        self.assertIn("驿马", stars(r, "hour"))   # 以日支午查
        r2 = natal("辛巳", "庚寅", "戊午", "乙亥")
        self.assertIn("驿马", stars(r2, "hour"))  # 以年支巳查

    def test_taohua_huagai_jiangxing(self):
        # 日支辰（申子辰）：桃花酉、华盖辰、将星子
        r = natal("甲子", "辛酉", "丙辰", "戊子")
        self.assertIn("桃花", stars(r, "month"))
        self.assertIn("华盖", stars(r, "day"))
        self.assertIn("将星", stars(r, "year"))
        self.assertIn("将星", stars(r, "hour"))

    def test_jiesha_wangshen_zaisha(self):
        # 年支卯（亥卯未）：劫煞申、亡神寅、灾煞酉
        r = natal("丁卯", "壬寅", "甲午", "壬申")
        self.assertIn("亡神", stars(r, "month"))
        self.assertIn("劫煞", stars(r, "hour"))
        r2 = natal("丁卯", "己酉", "甲午", "壬申")
        self.assertIn("灾煞", stars(r2, "month"))


class YearBranchAndGenderTest(unittest.TestCase):
    """孤辰寡宿、元辰、勾绞——与阴阳男女有关。"""

    def test_guchen_guasu(self):
        r = natal("戊寅", "乙巳", "甲午", "戊辰")  # 年支寅（寅卯辰）：孤辰巳、寡宿丑
        self.assertIn("孤辰", stars(r, "month"))
        self.assertNotIn("寡宿", stars(r, "month"))

    def test_yuanchen_shun(self):
        """阳男：冲前一位。子年冲午，午前一位 = 未。"""
        r = natal("甲子", "辛未", "丙午", "戊子", gender="男")
        self.assertIn("元辰", stars(r, "month"))

    def test_yuanchen_ni(self):
        """阴女同阳男顺查；阴男阳女逆查。子年阴男：冲后一位 = 巳。"""
        r_male = natal("乙丑", "辛巳", "丙午", "戊子", gender="男")
        # 乙丑年支丑，阴男：冲后一位。丑冲未，未后一位 = 午
        self.assertIn("元辰", stars(r_male, "day") | stars(r_male, "hour"))
        r_female = natal("乙丑", "辛巳", "丙午", "戊子", gender="女")
        # 阴女顺查：冲前一位 = 申，盘无申 → 无元辰
        self.assertNotIn("元辰", stars(r_female, "month") | stars(r_female, "day") |
                           stars(r_female, "year") | stars(r_female, "hour"))

    def test_goujiao(self):
        """甲子阳男：命前三辰卯为勾、后三辰酉为绞。"""
        r = natal("甲子", "丁卯", "辛酉", "戊子", gender="男")
        self.assertIn("勾煞", stars(r, "month"))
        self.assertIn("绞煞", stars(r, "day"))
        r2 = natal("甲子", "丁卯", "辛酉", "戊子", gender="女")
        self.assertIn("绞煞", stars(r2, "month"))
        self.assertIn("勾煞", stars(r2, "day"))


class NayinTest(unittest.TestCase):
    """年柱纳音查：天罗地网、童子煞。"""

    def test_tianluo_fire(self):
        r = natal("丙寅", "壬辰", "甲戌", "乙亥")  # 炉中火 → 天罗戌亥
        self.assertIn("天罗", stars(r, "day"))
        self.assertIn("天罗", stars(r, "hour"))

    def test_diwang_water_earth(self):
        r = natal("丙子", "壬辰", "甲辰", "己巳")  # 涧下水 → 地网辰巳
        self.assertIn("地网", stars(r, "month"))
        self.assertIn("地网", stars(r, "day"))
        self.assertIn("地网", stars(r, "hour"))

    def test_luowang_metal_wood_none(self):
        r = natal("甲子", "壬辰", "甲戌", "乙亥")  # 海中金 → 无罗网
        for k in ("year", "month", "day", "hour"):
            self.assertNotIn("天罗", stars(r, k))
            self.assertNotIn("地网", stars(r, k))

    def test_tongzi_season(self):
        r = natal("甲子", "丙寅", "戊寅", "甲寅")  # 春生见寅（日支、时支皆中）
        self.assertIn("童子煞", stars(r, "day"))
        self.assertIn("童子煞", stars(r, "hour"))

    def test_tongzi_nayin(self):
        # 庚午路旁土 → 辰巳；秋月生（寅子），日时支午卯两不涉 → 须无
        r = natal("庚午", "甲申", "甲午", "丁卯")
        self.assertNotIn("童子煞", stars(r, "day") | stars(r, "hour"))
        # 甲子海中金 → 午卯；秋月生不涉季节组，纯验纳音组
        r2 = natal("甲子", "壬申", "甲午", "丁卯")
        self.assertIn("童子煞", stars(r2, "day"))
        self.assertIn("童子煞", stars(r2, "hour"))


class FixedDayGroupTest(unittest.TestCase):
    """日柱干支固定组。"""

    def test_yincha_yangcuo(self):
        r = natal("甲子", "丙寅", "丙子", "戊子")
        self.assertIn("阴差阳错", stars(r, "day"))
        r2 = natal("甲子", "丙寅", "丙戌", "戊子")
        self.assertNotIn("阴差阳错", stars(r2, "day"))

    def test_shiling_kuigang(self):
        r = natal("甲子", "丙寅", "庚戌", "戊子")
        self.assertIn("十灵日", stars(r, "day"))
        self.assertIn("魁罡", stars(r, "day"))

    def test_shie_dabai_jichou(self):
        """己丑为十恶大败（甲申旬空午未、己禄在午）；epub 作乙丑系讹字。"""
        r = natal("甲子", "丙寅", "己丑", "戊子")
        self.assertIn("十恶大败", stars(r, "day"))
        r2 = natal("甲子", "丙寅", "乙丑", "戊子")
        self.assertNotIn("十恶大败", stars(r2, "day"))

    def test_tianshe(self):
        r = natal("甲子", "丙寅", "戊寅", "戊午")  # 春月戊寅日
        self.assertIn("天赦", stars(r, "day"))
        r2 = natal("甲子", "壬申", "戊寅", "戊午")  # 秋月戊寅日 → 非
        self.assertNotIn("天赦", stars(r2, "day"))


class SanqiTest(unittest.TestCase):
    def test_shunbu(self):
        r = natal("乙巳", "丙戌", "丁亥", "辛丑")
        self.assertEqual(len(r["combo"]), 1)
        star, note = r["combo"][0]
        self.assertEqual(star, "三奇贵人")
        self.assertIn("顺布", note)

    def test_nibu(self):
        r = natal("丁巳", "丙戌", "乙亥", "辛丑")
        self.assertEqual(len(r["combo"]), 1)
        self.assertIn("逆布", r["combo"][0][1])

    def test_not_adjacent_no_sanqi(self):
        r = natal("乙巳", "甲戌", "丙子", "丁丑")  # 乙丙丁不相连
        self.assertEqual(r["combo"], [])


class TargetQueryTest(unittest.TestCase):
    """岁运查询（evaluate_target）。"""

    P = {"year": "丁亥", "month": "乙巳", "day": "庚子", "hour": "辛巳"}

    def test_anchored(self):
        """丙午 对 丁亥/乙巳/庚子/辛巳（女）：福星（庚见午）、天德合（丙）、
        灾煞（日支子见午）、元辰（阴女顺查，亥冲巳前一位为午）；丙午自身属阴差阳错。"""
        r = evaluate_target(self.P, "女", "丙午")
        names = {s for s, _ in r["anchored"]}
        self.assertEqual(names, {"福星贵人", "天德合", "灾煞", "元辰"})
        own = {s for s, _ in r["own"]}
        self.assertEqual(own, {"阴差阳错"})

    def test_anchored_yisi(self):
        r = evaluate_target(self.P, "女", "乙巳")
        names = {s for s, _ in r["anchored"]}
        self.assertEqual(names, {"月德合", "驿马", "劫煞", "地网", "童子煞"})
        own = {s for s, _ in r["own"]}
        self.assertEqual(own, {"十恶大败"})


def _jiazi60() -> list[str]:
    return [GAN[i % 10] + ZHI[i % 12] for i in range(60)]


# 甲子…乙亥：12 个干支覆盖全部 10 天干与 12 地支（月、时柱扫面用）
_SPREAD12 = _jiazi60()[:12]


class StarOrderExhaustiveTest(unittest.TestCase):
    """根治校验：求值器一切可能产出的神煞名都必须落在 STAR_ORDER 键集内。

    3.6.0 事故：三奇贵人漏录排序表，排盘排序 KeyError。此处穷举求值器
    全部输入维度（年柱 60 × 月柱 12 全干支行 × 日柱 60 × 时柱 12 全干支行
    × 男女），收集实际产出的星名集合，断言与 STAR_ORDER 完全一致——
    新增神煞忘补排序表、或排序表残留死项，都会被本测试当场抓住。
    """

    def test_star_order_no_duplicates(self):
        self.assertEqual(len(STAR_ORDER), len(set(STAR_ORDER)))

    def test_natal_outputs_exactly_star_order(self):
        produced: set[str] = set()
        for year in _jiazi60():
            for month in _SPREAD12:
                for day in _jiazi60():
                    for hour in _SPREAD12:
                        for gender in ("男", "女"):
                            r = evaluate_natal(
                                {"year": year, "month": month,
                                 "day": day, "hour": hour}, gender)
                            for entries in r.values():
                                produced.update(s for s, _ in entries)
        self.assertEqual(produced, set(STAR_ORDER))

    def test_target_outputs_subset_of_star_order(self):
        """岁运查询同理：年 60 × 月 4（四季各一）× 日 60 × 目标干支 60。"""
        produced: set[str] = set()
        for year in _jiazi60():
            for month in ("甲寅", "乙巳", "丙申", "丁亥"):
                for day in _jiazi60():
                    p = {"year": year, "month": month, "day": day, "hour": "甲子"}
                    for target in _jiazi60():
                        r = evaluate_target(p, "男", target)
                        produced.update(s for s, _ in r["anchored"])
                        produced.update(s for s, _ in r["own"])
        missing = produced - set(STAR_ORDER)
        self.assertEqual(missing, set())

    @unittest.skipIf(_shen_sha is None, "tyme4py 不可用")
    def test_sanqi_combo_survives_adapter_sort(self):
        """回归：combo 组三奇贵人经 tyme_adapter._shen_sha 排序不再 KeyError。"""
        out = _shen_sha({"year": "甲辰", "month": "戊辰",
                         "day": "庚子", "hour": "辛巳"}, "男")
        self.assertTrue(any(s.startswith("三奇贵人") for s in out["combo"]))


if __name__ == "__main__":
    unittest.main()
