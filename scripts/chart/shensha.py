"""子平通行神煞求值（文档：rules/94_神煞细节.md）。

纯查表，零命理判断：输入四柱干支、性别、年柱纳音，输出按柱分组的神煞清单。
查法口径与 rules/94_神煞细节.md 各 R-煞 条目一一对应；条目注明出处为
《三命通会》者，查法表见本模块顶部各常量。

本命盘与岁运查询共用同一求值器：
  - 本命：evaluate_natal() → {year/month/day/hour/combo: [条目文字]}
  - 岁运：evaluate_target() → 目标干支（流年/流月/大运/流日）相对本命锚点所逢之神煞
"""
from __future__ import annotations

GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"
YANG_GAN = set("甲丙戊庚壬")

# 六十甲子纳音（ pairwise ），末字即五行
_NAYIN_PAIRS = [
    "海中金", "炉中火", "大林木", "路旁土", "剑锋金",
    "山头火", "涧下水", "城头土", "白蜡金", "杨柳木",
    "泉中水", "屋上土", "霹雳火", "松柏木", "长流水",
    "沙中金", "山下火", "平地木", "壁上土", "金箔金",
    "覆灯火", "天河水", "大驿土", "钗钏金", "桑柘木",
    "大溪水", "沙中土", "天上火", "石榴木", "大海水",
]
_JIAZI = [GAN[i % 10] + ZHI[i % 12] for i in range(60)]
NAYIN = {gz: _NAYIN_PAIRS[i // 2] for i, gz in enumerate(_JIAZI)}

# —— 日干查地支 ——
TIANYI = {"甲": "丑未", "戊": "丑未", "庚": "丑未",
          "乙": "子申", "己": "子申", "丙": "亥酉", "丁": "亥酉",
          "壬": "卯巳", "癸": "卯巳", "辛": "午寅"}                    # 天乙贵人
WENCHANG = {"甲": "巳", "乙": "午", "丙": "申", "戊": "申", "丁": "酉",
            "己": "酉", "庚": "亥", "辛": "子", "壬": "寅", "癸": "卯"}  # 文昌
LU = {"甲": "寅", "乙": "卯", "丙": "巳", "丁": "午", "戊": "巳",
      "己": "午", "庚": "申", "辛": "酉", "壬": "亥", "癸": "子"}      # 禄神
YANGREN = {"甲": "卯", "丙": "午", "戊": "午", "庚": "酉", "壬": "子"}  # 羊刃（五阳干）
JINYU = {"甲": "辰", "乙": "巳", "丙": "未", "丁": "申", "戊": "未",
         "己": "申", "庚": "戌", "辛": "亥", "壬": "丑", "癸": "寅"}   # 金舆（禄前二辰）
TAIJI = {"甲": "子午", "乙": "子午", "丙": "卯酉", "丁": "卯酉",
         "戊": "辰戌丑未", "己": "辰戌丑未", "庚": "寅亥", "辛": "寅亥",
         "壬": "巳申", "癸": "巳申"}                                    # 太极贵人
FUXING = {"甲": "寅子", "乙": "丑卯", "丙": "寅子", "丁": "亥", "戊": "申",
          "己": "未", "庚": "午", "辛": "巳", "壬": "辰", "癸": "丑卯"}  # 福星贵人
HONGYAN = {"甲": "午", "乙": "午", "丙": "寅", "丁": "未", "戊": "子",
           "己": "辰", "庚": "戌", "辛": "酉", "壬": "巳", "癸": "申"}  # 红艳（三命通会）

# —— 月令查 ——
TIANDE = {"寅": "丁", "卯": "申", "辰": "壬", "巳": "辛", "午": "亥", "未": "甲",
          "申": "癸", "酉": "寅", "戌": "丙", "亥": "乙", "子": "巳", "丑": "庚"}  # 天德
YUEDE_GROUPS = {"寅": "丙", "午": "丙", "戌": "丙", "申": "壬", "子": "壬", "辰": "壬",
                "亥": "甲", "卯": "甲", "未": "甲", "巳": "庚", "酉": "庚", "丑": "庚"}  # 月德
STEM_HE = {"甲": "己", "己": "甲", "乙": "庚", "庚": "乙", "丙": "辛", "辛": "丙",
           "丁": "壬", "壬": "丁", "戊": "癸", "癸": "戊"}
BRANCH_HE = {"子": "丑", "丑": "子", "寅": "亥", "亥": "寅", "卯": "戌", "戌": "卯",
             "辰": "酉", "酉": "辰", "巳": "申", "申": "巳", "午": "未", "未": "午"}

# —— 三合局查（以年支或日支）——
def _sanhe(key: str, table: tuple[str, str, str, str]) -> str:
    """key 支所属三合局 → 对应目标支。table 序：申子辰、寅午戌、巳酉丑、亥卯未。"""
    for group, target in zip(("申子辰", "寅午戌", "巳酉丑", "亥卯未"), table):
        if key in group:
            return target
    raise ValueError(key)

YIMA = ("寅", "申", "亥", "巳")      # 驿马
TAOHUA = ("酉", "卯", "午", "子")    # 桃花（咸池）
HUAGAI = ("辰", "戌", "丑", "未")    # 华盖
JIANGXING = ("子", "午", "酉", "卯")  # 将星
JIESHA = ("巳", "亥", "寅", "申")    # 劫煞
WANGSHEN = ("亥", "巳", "申", "寅")  # 亡神
ZAISHA = ("午", "子", "卯", "酉")    # 灾煞

# —— 年支查 ——
GUCHEN = {"亥": "寅", "子": "寅", "丑": "寅", "寅": "巳", "卯": "巳", "辰": "巳",
          "巳": "申", "午": "申", "未": "申", "申": "亥", "酉": "亥", "戌": "亥"}  # 孤辰
GUASU = {"亥": "戌", "子": "戌", "丑": "戌", "寅": "丑", "卯": "丑", "辰": "丑",
         "巳": "辰", "午": "辰", "未": "辰", "申": "未", "酉": "未", "戌": "未"}  # 寡宿
CHONG = {z: ZHI[(ZHI.index(z) + 6) % 12] for z in ZHI}

# —— 年柱纳音查 ——
# 天罗地网：火命见戌亥为天罗，水土命见辰巳为地网，金木命无（三命通会·卷三·论天罗地网）
# 童子煞：春秋寅子贵，冬夏卯未辰；金木马卯合，水火鸡犬多；土命逢辰巳（通行口诀，无书证）
SEASON_OF_MONTH = {**{m: "春" for m in "寅卯辰"}, **{m: "夏" for m in "巳午未"},
                   **{m: "秋" for m in "申酉戌"}, **{m: "冬" for m in "亥子丑"}}
TONGZI_SEASON = {"春": "寅子", "秋": "寅子", "冬": "卯未辰", "夏": "卯未辰"}
TONGZI_NAYIN = {"金": "午卯", "木": "午卯", "水": "酉戌", "火": "酉戌", "土": "辰巳"}

# —— 日柱干支固定组 ——
YINCHA_YANGCUO = {"丙子", "丁丑", "戊寅", "辛卯", "壬辰", "癸巳",
                  "丙午", "丁未", "戊申", "辛酉", "壬戌", "癸亥"}        # 阴差阳错
SHILING = {"甲辰", "乙亥", "丙辰", "丁酉", "戊午",
           "庚戌", "庚寅", "辛亥", "壬寅", "癸未"}                       # 十灵日
KUIGANG = {"庚辰", "庚戌", "壬辰", "戊戌"}                              # 魁罡
SHIE_DABAI = {"甲辰", "乙巳", "丙申", "丁亥", "戊戌",
              "己丑", "庚辰", "辛巳", "壬申", "癸亥"}                    # 十恶大败
TIANSHE = {"春": "戊寅", "夏": "甲午", "秋": "戊申", "冬": "甲子"}       # 天赦日

# —— 三奇（天干顺布相连；三组归属诸书异说，不冠名，只判顺逆）——
SANQI = ("乙丙丁", "甲戊庚", "辛壬癸")

# 输出排序（每柱内部按此序）
STAR_ORDER = [
    "天德", "天德合", "月德", "月德合", "天乙贵人", "太极贵人", "福星贵人",
    "文昌", "禄神", "羊刃", "金舆", "驿马", "桃花", "红艳", "华盖", "将星",
    "劫煞", "灾煞", "亡神", "元辰", "勾煞", "绞煞", "孤辰", "寡宿",
    "天罗", "地网", "童子煞", "天赦", "魁罡", "阴差阳错", "十灵日", "十恶大败",
]

PILLAR_KEYS = ("year", "month", "day", "hour")
PILLAR_LABELS = {"year": "年柱", "month": "月柱", "day": "日柱", "hour": "时柱"}
_PILLAR_SHORT = {"year": "年", "month": "月", "day": "日", "hour": "时"}


def _shift(zhi: str, n: int) -> str:
    return ZHI[(ZHI.index(zhi) + n) % 12]


def _entry(star: str, note: str) -> tuple[str, str]:
    return (star, note)


class ShenShaContext:
    """本命锚点：日干、年支、日支、月令、年柱纳音、阴阳男女。"""

    def __init__(self, pillars: dict[str, str], gender: str):
        """pillars: {year/month/day/hour: 干支两字符}；gender: 「男」/「女」"""
        self.pillars = pillars
        self.gender = gender
        self.day_gan = pillars["day"][0]
        self.year_zhi = pillars["year"][1]
        self.day_zhi = pillars["day"][1]
        self.month_zhi = pillars["month"][1]
        self.year_ganzhi = pillars["year"]
        self.day_ganzhi = pillars["day"]
        self.nayin_wuxing = NAYIN[self.year_ganzhi][-1]
        year_gan = pillars["year"][0]
        yang_year = year_gan in YANG_GAN
        male = gender == "男"
        # 阳男阴女为顺，阴男阳女为逆
        self.shun = (yang_year and male) or (not yang_year and not male)
        self.season = SEASON_OF_MONTH[self.month_zhi]

    def anchor_hits(self, star: str, targets: str, anchor_desc: str,
                    out: dict[str, list]) -> None:
        """targets 为若干目标支；命中某柱地支则在该柱登记。"""
        for key in PILLAR_KEYS:
            zhi = self.pillars[key][1]
            if zhi in targets:
                out[key].append(_entry(
                    star, f"以{anchor_desc}查，见于{_PILLAR_SHORT[key]}支{zhi}"))


def evaluate_natal(pillars: dict[str, str], gender: str) -> dict[str, list]:
    """本命神煞：{year/month/day/hour: [(星名, 注)], combo: [...]}"""
    ctx = ShenShaContext(pillars, gender)
    out: dict[str, list] = {k: [] for k in PILLAR_KEYS}
    out["combo"] = []

    # —— 日干查 ——
    ctx.anchor_hits("天乙贵人", TIANYI[ctx.day_gan], f"日干{ctx.day_gan}", out)
    ctx.anchor_hits("文昌", WENCHANG[ctx.day_gan], f"日干{ctx.day_gan}", out)
    ctx.anchor_hits("禄神", LU[ctx.day_gan], f"日干{ctx.day_gan}", out)
    if ctx.day_gan in YANGREN:
        ctx.anchor_hits("羊刃", YANGREN[ctx.day_gan], f"日干{ctx.day_gan}", out)
    ctx.anchor_hits("金舆", JINYU[ctx.day_gan], f"日干{ctx.day_gan}", out)
    ctx.anchor_hits("太极贵人", TAIJI[ctx.day_gan], f"日干{ctx.day_gan}", out)
    ctx.anchor_hits("福星贵人", FUXING[ctx.day_gan], f"日干{ctx.day_gan}", out)
    ctx.anchor_hits("红艳", HONGYAN[ctx.day_gan], f"日干{ctx.day_gan}", out)

    # —— 月令查（天德、月德及其合，可应天干或地支）——
    for star, target in (("天德", TIANDE[ctx.month_zhi]),
                         ("月德", YUEDE_GROUPS[ctx.month_zhi])):
        he = STEM_HE.get(target) or BRANCH_HE.get(target)
        for key in PILLAR_KEYS:
            gan, zhi = ctx.pillars[key]
            if gan == target:
                out[key].append(_entry(
                    star, f"以月令{ctx.month_zhi}查，见于{_PILLAR_SHORT[key]}干{gan}"))
            elif zhi == target:
                out[key].append(_entry(
                    star, f"以月令{ctx.month_zhi}查，见于{_PILLAR_SHORT[key]}支{zhi}"))
            if gan == he:
                out[key].append(_entry(
                    f"{star}合", f"以月令{ctx.month_zhi}查，见于{_PILLAR_SHORT[key]}干{gan}"))
            elif zhi == he:
                out[key].append(_entry(
                    f"{star}合", f"以月令{ctx.month_zhi}查，见于{_PILLAR_SHORT[key]}支{zhi}"))

    # —— 年支、日支并查（三合局诸煞）——
    for star, table in (("驿马", YIMA), ("桃花", TAOHUA), ("华盖", HUAGAI),
                        ("将星", JIANGXING), ("劫煞", JIESHA),
                        ("灾煞", ZAISHA), ("亡神", WANGSHEN)):
        for anchor_zhi, anchor_desc in ((ctx.year_zhi, f"年支{ctx.year_zhi}"),
                                        (ctx.day_zhi, f"日支{ctx.day_zhi}")):
            ctx.anchor_hits(star, _sanhe(anchor_zhi, table), anchor_desc, out)

    # —— 年支查（孤辰寡宿、元辰、勾绞）——
    ctx.anchor_hits("孤辰", GUCHEN[ctx.year_zhi], f"年支{ctx.year_zhi}", out)
    ctx.anchor_hits("寡宿", GUASU[ctx.year_zhi], f"年支{ctx.year_zhi}", out)
    yz = ctx.year_zhi
    if ctx.shun:  # 阳男阴女
        yuan_chen = _shift(CHONG[yz], 1)   # 冲前一位
        gou, jiao = _shift(yz, 3), _shift(yz, -3)  # 命前三辰为勾，后三辰为绞
    else:          # 阴男阳女
        yuan_chen = _shift(CHONG[yz], -1)  # 冲后一位
        jiao, gou = _shift(yz, 3), _shift(yz, -3)
    ctx.anchor_hits("元辰", yuan_chen, f"年支{yz}", out)
    ctx.anchor_hits("勾煞", gou, f"年支{yz}", out)
    ctx.anchor_hits("绞煞", jiao, f"年支{yz}", out)

    # —— 年柱纳音查 ——
    wx = ctx.nayin_wuxing
    if wx == "火":
        ctx.anchor_hits("天罗", "戌亥", f"年柱纳音{wx}命", out)
    elif wx in "水土":
        ctx.anchor_hits("地网", "辰巳", f"年柱纳音{wx}命", out)
    for key in ("day", "hour"):  # 童子煞查日、时二支
        zhi = ctx.pillars[key][1]
        if zhi in TONGZI_SEASON[ctx.season]:
            out[key].append(_entry(
                "童子煞", f"以月令{ctx.month_zhi}季节查，见于{_PILLAR_SHORT[key]}支{zhi}"))
        elif zhi in TONGZI_NAYIN[wx]:
            out[key].append(_entry(
                "童子煞", f"以年命纳音{wx}查，见于{_PILLAR_SHORT[key]}支{zhi}"))

    # —— 日柱干支固定组 ——
    fixed = (("阴差阳错", YINCHA_YANGCUO), ("十灵日", SHILING),
             ("魁罡", KUIGANG), ("十恶大败", SHIE_DABAI))
    for star, group in fixed:
        if ctx.day_ganzhi in group:
            out["day"].append(_entry(star, "日柱干支直查"))
    if ctx.day_ganzhi == TIANSHE[ctx.season]:
        out["day"].append(_entry("天赦", f"{ctx.season}季生，日柱干支直查"))

    # —— 三奇（天干顺布相连）——
    stems = "".join(ctx.pillars[k][0] for k in PILLAR_KEYS)
    for seq in SANQI:
        if seq in stems:
            i = stems.index(seq)
            span = "年月日" if i == 0 else "月日时"
            out["combo"].append(_entry("三奇贵人", f"{seq}顺布，见于{span}天干"))
        elif seq[::-1] in stems:
            i = stems.index(seq[::-1])
            span = "年月日" if i == 0 else "月日时"
            out["combo"].append(_entry("三奇贵人", f"{seq}逆布，见于{span}天干"))

    return out


def evaluate_target(pillars: dict[str, str], gender: str,
                    target_ganzhi: str) -> dict[str, list]:
    """岁运查询：目标干支（流年/流月/大运/流日）相对本命锚点所逢神煞。

    返回 {anchored: [(星名, 注)], own: [(星名, 注)]}：
      anchored —— 以本命日干/年支/日支/月令/年命纳音查得，目标干支逢之；
      own —— 目标干支自身所属之日柱固定组（阴差阳错等，供流日查询参看）。
    """
    ctx = ShenShaContext(pillars, gender)
    t_gan, t_zhi = target_ganzhi[0], target_ganzhi[1]
    anchored: list[tuple[str, str]] = []
    own: list[tuple[str, str]] = []

    def hit(star: str, targets: str, anchor_desc: str) -> None:
        if t_zhi in targets:
            anchored.append(_entry(star, f"以{anchor_desc}查，见于{target_ganzhi}之支"))

    hit("天乙贵人", TIANYI[ctx.day_gan], f"日干{ctx.day_gan}")
    hit("文昌", WENCHANG[ctx.day_gan], f"日干{ctx.day_gan}")
    hit("禄神", LU[ctx.day_gan], f"日干{ctx.day_gan}")
    if ctx.day_gan in YANGREN:
        hit("羊刃", YANGREN[ctx.day_gan], f"日干{ctx.day_gan}")
    hit("金舆", JINYU[ctx.day_gan], f"日干{ctx.day_gan}")
    hit("太极贵人", TAIJI[ctx.day_gan], f"日干{ctx.day_gan}")
    hit("福星贵人", FUXING[ctx.day_gan], f"日干{ctx.day_gan}")
    hit("红艳", HONGYAN[ctx.day_gan], f"日干{ctx.day_gan}")

    for star, target in (("天德", TIANDE[ctx.month_zhi]),
                         ("月德", YUEDE_GROUPS[ctx.month_zhi])):
        he = STEM_HE.get(target) or BRANCH_HE.get(target)
        if t_gan == target or t_zhi == target:
            anchored.append(_entry(star, f"以月令{ctx.month_zhi}查，逢{target_ganzhi}"))
        if t_gan == he or t_zhi == he:
            anchored.append(_entry(f"{star}合", f"以月令{ctx.month_zhi}查，逢{target_ganzhi}"))

    for star, table in (("驿马", YIMA), ("桃花", TAOHUA), ("华盖", HUAGAI),
                        ("将星", JIANGXING), ("劫煞", JIESHA),
                        ("灾煞", ZAISHA), ("亡神", WANGSHEN)):
        for anchor_zhi, anchor_desc in ((ctx.year_zhi, f"年支{ctx.year_zhi}"),
                                        (ctx.day_zhi, f"日支{ctx.day_zhi}")):
            hit(star, _sanhe(anchor_zhi, table), anchor_desc)

    hit("孤辰", GUCHEN[ctx.year_zhi], f"年支{ctx.year_zhi}")
    hit("寡宿", GUASU[ctx.year_zhi], f"年支{ctx.year_zhi}")
    yz = ctx.year_zhi
    if ctx.shun:
        yuan_chen, gou, jiao = _shift(CHONG[yz], 1), _shift(yz, 3), _shift(yz, -3)
    else:
        yuan_chen, jiao, gou = _shift(CHONG[yz], -1), _shift(yz, 3), _shift(yz, -3)
    hit("元辰", yuan_chen, f"年支{yz}")
    hit("勾煞", gou, f"年支{yz}")
    hit("绞煞", jiao, f"年支{yz}")

    wx = ctx.nayin_wuxing
    if wx == "火":
        hit("天罗", "戌亥", f"年柱纳音{wx}命")
    elif wx in "水土":
        hit("地网", "辰巳", f"年柱纳音{wx}命")
    if t_zhi in TONGZI_SEASON[ctx.season]:
        anchored.append(_entry("童子煞", f"以月令{ctx.month_zhi}季节查，逢{target_ganzhi}"))
    elif t_zhi in TONGZI_NAYIN[wx]:
        anchored.append(_entry("童子煞", f"以年命纳音{wx}查，逢{target_ganzhi}"))

    for star, group in (("阴差阳错", YINCHA_YANGCUO), ("十灵日", SHILING),
                        ("魁罡", KUIGANG), ("十恶大败", SHIE_DABAI)):
        if target_ganzhi in group:
            own.append(_entry(star, "目标干支自身所属"))
    if target_ganzhi == TIANSHE[ctx.season]:
        own.append(_entry("天赦", f"{ctx.season}季之目标干支自身所属"))

    order = {name: i for i, name in enumerate(STAR_ORDER)}
    anchored.sort(key=lambda e: order[e[0]])
    own.sort(key=lambda e: order[e[0]])
    return {"anchored": anchored, "own": own}
