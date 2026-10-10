"""干支派生纯查表：五行、十神、十二长生（星运）、旬空、六十甲子纳音。

本命四柱的同名信息由 chart/tyme_adapter.py 经 tyme4py 求得；本模块为同口径的
纯 Python 实现，供岁运干支（大运/流年/流月）与渲染层复用，保证 HTML 盘面
与排盘正文口径一致。纯查表，零命理判断（P1）。
"""

GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"

WX_GAN = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
          "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}
WX_ZHI = {"子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土",
          "巳": "火", "午": "火", "未": "土", "申": "金", "酉": "金",
          "戌": "土", "亥": "水"}

_YY = {"甲": 1, "丙": 1, "戊": 1, "庚": 1, "壬": 1,
       "乙": -1, "丁": -1, "己": -1, "辛": -1, "癸": -1}
_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}


def ten_god(me: str, other: str) -> str:
    """other 天干相对日干 me 的十神（命名与 tyme4py get_ten_star 一致）。"""
    wx_m, wx_o = WX_GAN[me], WX_GAN[other]
    same = _YY[me] == _YY[other]
    if wx_m == wx_o:
        return "比肩" if same else "劫财"
    if _SHENG[wx_m] == wx_o:
        return "食神" if same else "伤官"
    if _KE[wx_m] == wx_o:
        return "偏财" if same else "正财"
    if _KE[wx_o] == wx_m:
        return "七杀" if same else "正官"
    return "偏印" if same else "正印"


_TERRAIN_ORDER = ["长生", "沐浴", "冠带", "临官", "帝旺", "衰",
                  "病", "死", "墓", "绝", "胎", "养"]
_TERRAIN_START = {"甲": "亥", "乙": "午", "丙": "寅", "戊": "寅", "庚": "巳",
                  "壬": "申", "丁": "酉", "己": "酉", "辛": "子", "癸": "卯"}


def terrain(me: str, zhi: str) -> str:
    """日干 me 对地支 zhi 的十二长生（阳顺阴逆，命名与 tyme4py get_terrain 一致）。"""
    start = ZHI.index(_TERRAIN_START[me])
    zi = ZHI.index(zhi)
    off = (zi - start) % 12 if _YY[me] == 1 else (start - zi) % 12
    return _TERRAIN_ORDER[off]


def gz_void(gz: str) -> str:
    """一柱干支所在旬的空亡两支（与 tyme4py get_extra_earth_branches 同果）。"""
    g, z = GAN.index(gz[0]), ZHI.index(gz[1])
    return ZHI[(z - g + 10) % 12] + ZHI[(z - g + 11) % 12]


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
