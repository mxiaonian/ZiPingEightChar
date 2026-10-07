"""起运与大运（文档 4.8 节）。

规则（真诠体系）：
- 阳男阴女顺排，阴男阳女逆排
- 起运：顺排取出生时刻到下一节、逆排取到上一节的时间差
- 折算：3 天 = 1 年（1 年 = 12 个月 = 360 天）
- 大运每步 10 年，从月柱干支起顺/逆推

纯 Python 历法推算，不 import tyme4py。
"""
from datetime import datetime

from .model import LuckPillar

GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"

YANG_GAN = frozenset("甲丙戊庚壬")

# 年上起月法（五虎遁）：年干 → 寅月天干
# 甲己之年丙作首，乙庚之年戊为头，丙辛之年寻庚起，丁壬壬寅顺水流，戊癸甲寅
_MONTH_HEAD_GAN = {
    "甲": "丙", "己": "丙",
    "乙": "戊", "庚": "戊",
    "丙": "庚", "辛": "庚",
    "丁": "壬", "壬": "壬",
    "戊": "甲", "癸": "甲",
}

# 节气月：月支从寅起（立春为寅月），(月支, 起始节气)
_SOLAR_MONTHS = (
    ("寅", "立春"), ("卯", "惊蛰"), ("辰", "清明"), ("巳", "立夏"),
    ("午", "芒种"), ("未", "小暑"), ("申", "立秋"), ("酉", "白露"),
    ("戌", "寒露"), ("亥", "立冬"), ("子", "大雪"), ("丑", "小寒"),
)

SECONDS_PER_DAY = 86400
DAYS_PER_LUCK_YEAR = 3.0    # 3 天折 1 年


def ganzhi_of_year(y: int) -> str:
    """公元 4 年为甲子，(y-4)%60 定位。"""
    return GAN[(y - 4) % 10] + ZHI[(y - 4) % 12]


def ganzhi_cycle_next(gan: str, zhi: str, n: int) -> tuple[str, str]:
    """干支同步推进 n 步（n 可为负）。"""
    return GAN[(GAN.index(gan) + n) % 10], ZHI[(ZHI.index(zhi) + n) % 12]


def is_forward(gender: str, year_gan: str) -> bool:
    """阳年干（甲丙戊庚壬）+ 男 → 顺；阴年干 + 女 → 顺。"""
    return (year_gan in YANG_GAN) == (gender == "男")


def compute_luck(
    birth_tst: datetime,
    prev_jie_time: datetime,
    next_jie_time: datetime,
    forward: bool,
) -> dict:
    """起运：顺排取下一节减出生，逆排取出生减上一节；3 天折 1 年。

    返回 {"is_forward", "start_age_years", "start_age_text"}。
    start_age_years 保留 4 位小数；起运年龄精度要到「天」级，否则起运年份会差一年。
    """
    if forward:
        delta = next_jie_time - birth_tst
    else:
        delta = birth_tst - prev_jie_time

    start_age_years = delta.total_seconds() / SECONDS_PER_DAY / DAYS_PER_LUCK_YEAR

    return {
        "is_forward": forward,
        "start_age_years": round(start_age_years, 4),
        "start_age_text": _age_to_text(start_age_years),
    }


def _age_to_text(years: float) -> str:
    """年数 → 「X 岁 Y 个月 Z 天」。

    按 1 年 = 12 个月 = 360 天折算（0.5 年 = 6 个月），四舍五入到天。
    """
    total_days = round(years * 360)
    y = total_days // 360
    m = (total_days % 360) // 30
    d = total_days % 30
    return f"{y} 岁 {m} 个月 {d} 天"


def decade_pillars(
    month_gan: str,
    month_zhi: str,
    forward: bool,
    start_age_years: float,
    birth_year: int,
    n: int = 8,
) -> list[LuckPillar]:
    """从月柱起顺/逆推 n 步大运（第 1 步为月柱 ±1）。"""
    step = 1 if forward else -1
    pillars = []
    for index in range(n):
        gan, zhi = ganzhi_cycle_next(month_gan, month_zhi, step * (index + 1))
        start_age = start_age_years + 10 * index
        pillars.append(LuckPillar(
            index=index + 1,
            gan=gan,
            zhi=zhi,
            start_age=round(start_age, 4),
            start_year=birth_year + round(start_age),
        ))
    return pillars


def flow_years(current_year: int, n: int = 10) -> list[tuple[int, str]]:
    """从今年起 n 个流年干支。"""
    return [(y, ganzhi_of_year(y)) for y in range(current_year, current_year + n)]


def flow_months(year: int) -> list[tuple[str, str]]:
    """该年 12 个节气月，返回 (「X月(节气起)」, 干支)。

    月支从寅起（立春为寅月）；月干按年上起月法（五虎遁）。
    """
    year_gan = GAN[(year - 4) % 10]
    head = GAN.index(_MONTH_HEAD_GAN[year_gan])
    return [
        (f"{zhi}月({jie}起)", GAN[(head + i) % 10] + zhi)
        for i, (zhi, jie) in enumerate(_SOLAR_MONTHS)
    ]
