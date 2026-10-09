# scripts/render/html.py
"""ChartData → 单文件 HTML 盘面（模板 render/templates/paipan.html）。

与 Markdown 输出同为纯计算渲染：十神/藏干/空亡/纳音/十二长生/月令旺衰
均为固定查表，不含任何命理判断（P1）。
"""
from datetime import datetime
from pathlib import Path

from chart.luck import luck_label_for_year

GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"

_WX_GAN = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
           "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}
_WX_ZHI = {"子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土",
           "巳": "火", "午": "火", "未": "土", "申": "金", "酉": "金",
           "戌": "土", "亥": "水"}
_YY = {"甲": 1, "丙": 1, "戊": 1, "庚": 1, "壬": 1,
       "乙": -1, "丁": -1, "己": -1, "辛": -1, "癸": -1}
_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

_HIDDEN = {"子": ["癸"], "丑": ["己", "癸", "辛"], "寅": ["甲", "丙", "戊"],
           "卯": ["乙"], "辰": ["戊", "乙", "癸"], "巳": ["丙", "戊", "庚"],
           "午": ["丁", "己"], "未": ["己", "丁", "乙"],
           "申": ["庚", "壬", "戊"], "酉": ["辛"], "戌": ["戊", "辛", "丁"],
           "亥": ["壬", "甲"]}

_NAYIN = {"甲子": "海中金", "乙丑": "海中金", "丙寅": "炉中火", "丁卯": "炉中火",
          "戊辰": "大林木", "己巳": "大林木", "庚午": "路旁土", "辛未": "路旁土",
          "壬申": "剑锋金", "癸酉": "剑锋金", "甲戌": "山头火", "乙亥": "山头火",
          "丙子": "涧下水", "丁丑": "涧下水", "戊寅": "城头土", "己卯": "城头土",
          "庚辰": "白蜡金", "辛巳": "白蜡金", "壬午": "杨柳木", "癸未": "杨柳木",
          "甲申": "泉中水", "乙酉": "泉中水", "丙戌": "屋上土", "丁亥": "屋上土",
          "戊子": "霹雳火", "己丑": "霹雳火", "庚寅": "松柏木", "辛卯": "松柏木",
          "壬辰": "长流水", "癸巳": "长流水", "甲午": "沙中金", "乙未": "沙中金",
          "丙申": "山下火", "丁酉": "山下火", "戊戌": "平地木", "己亥": "平地木",
          "庚子": "壁上土", "辛丑": "壁上土", "壬寅": "金箔金", "癸卯": "金箔金",
          "甲辰": "覆灯火", "乙巳": "覆灯火", "丙午": "天河水", "丁未": "天河水",
          "戊申": "大驿土", "己酉": "大驿土", "庚戌": "钗钏金", "辛亥": "钗钏金",
          "壬子": "桑柘木", "癸丑": "桑柘木", "甲寅": "大溪水", "乙卯": "大溪水",
          "丙辰": "沙中土", "丁巳": "沙中土", "戊午": "天上火", "己未": "天上火",
          "庚申": "石榴木", "辛酉": "石榴木", "壬戌": "大海水", "癸亥": "大海水"}

_TERRAIN_ORDER = ["长生", "沐浴", "冠带", "临官", "帝旺", "衰",
                  "病", "死", "墓", "绝", "胎", "养"]
_TERRAIN_START = {"甲": "亥", "乙": "午", "丙": "寅", "戊": "寅", "庚": "巳",
                  "壬": "申", "丁": "酉", "己": "酉", "辛": "子", "癸": "卯"}

_SEASON = {"寅": ("木", "火", "水", "金", "土"), "卯": ("木", "火", "水", "金", "土"),
           "巳": ("火", "土", "木", "水", "金"), "午": ("火", "土", "木", "水", "金"),
           "申": ("金", "水", "土", "火", "木"), "酉": ("金", "水", "土", "火", "木"),
           "亥": ("水", "木", "金", "土", "火"), "子": ("水", "木", "金", "土", "火"),
           "辰": ("土", "金", "火", "木", "水"), "戌": ("土", "金", "火", "木", "水"),
           "丑": ("土", "金", "火", "木", "水"), "未": ("土", "金", "火", "木", "水")}
_SEASON_LABEL = ("旺", "相", "休", "囚", "死")


def _wx(ch: str) -> str:
    wx = _WX_GAN.get(ch) or _WX_ZHI.get(ch)
    return {"木": "wx-mu", "火": "wx-huo", "土": "wx-tu",
            "金": "wx-jin", "水": "wx-shui"}.get(wx, "")


def _ten_god(me: str, other: str) -> str:
    wx_m, wx_o = _WX_GAN[me], _WX_GAN[other]
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


def _terrain(me: str, zhi: str) -> str:
    """日干对支的十二长生（阳顺阴逆）。"""
    start = _ZHI_IDX(_TERRAIN_START[me])
    zi = _ZHI_IDX(zhi)
    off = (zi - start) % 12 if _YY[me] == 1 else (start - zi) % 12
    return _TERRAIN_ORDER[off]


def _ZHI_IDX(z: str) -> int:
    return ZHI.index(z)


def _gz_void(gz: str) -> str:
    """一柱干支的旬空两支。"""
    g, z = GAN.index(gz[0]), ZHI.index(gz[1])
    return ZHI[(z - g + 10) % 12] + ZHI[(z - g + 11) % 12]


def _z(zhi: str, voids: str) -> str:
    cls = "voidz" if zhi in voids else ""
    return f'<span class="{_wx(zhi)} {cls}">{zhi}</span>'


def _pillar_col(chart, key: str, label: str, cur: bool = False) -> dict:
    """四柱之一 → 各行的 HTML 单元格内容。"""
    p = getattr(chart, key)
    voids = chart.void.get("day", "") + chart.void.get("hour", "")
    return {
        "label": label, "cur": cur,
        "god": p.gan_ten_god or ("日主" if key == "day" else ""),
        "gan": p.gan, "zhi": p.zhi,
        "hidden": list(zip(p.hidden_stems, p.hidden_ten_gods)),
        "terrain": chart.terrain.get(key, ""),
        "void": _gz_void(p.gan + p.zhi),
        "nayin": p.na_yin or "",
        "shensha": chart.shen_sha.get(key, []),
        "voids": voids,
    }


def _extra_col(chart, gz: str, label: str, cur: bool) -> dict:
    """流年/大运列（仅干支行星级信息，神煞留空）。"""
    me = chart.day_master
    voids = chart.void.get("day", "") + chart.void.get("hour", "")
    return {
        "label": label, "cur": cur,
        "god": _ten_god(me, gz[0]),
        "gan": gz[0], "zhi": gz[1],
        "hidden": [(h, _ten_god(me, h)) for h in _HIDDEN[gz[1]]],
        "terrain": _terrain(me, gz[1]),
        "void": _gz_void(gz),
        "nayin": _NAYIN[gz],
        "shensha": [],
        "voids": voids,
    }


def _main_table(chart) -> str:
    this_year = datetime.now().year
    ly = next(((y, gz) for y, gz, _ in chart.flow_years if y == this_year), None)
    cur_luck = None
    for lp in chart.luck_pillars:
        if lp.start_year <= this_year:
            cur_luck = lp
    cols = []
    if ly:
        cols.append(_extra_col(chart, ly[1], f"流年 {ly[0]}", cur=True))
    if cur_luck:
        cols.append(_extra_col(chart, cur_luck.gan + cur_luck.zhi, "大运", cur=True))
    for key, label in (("year", "年柱"), ("month", "月柱"),
                       ("day", "日柱"), ("hour", "时柱")):
        cols.append(_pillar_col(chart, key, label, cur=(key == "day")))

    def th(c):
        tag = '<span class="curtag">当前</span>' if c["cur"] else ""
        return f'<th class="{"cur" if c["cur"] else ""}">{c["label"]}{tag}</th>'

    def row(label, fn, cls=""):
        tds = "".join(
            f'<td class="{"cur" if c["cur"] else ""}">{fn(c)}</td>' for c in cols)
        return f'<tr><td class="rowlabel">{label}</td>{tds}</tr>'

    rows = [
        "<tr>" + '<td class="rowlabel"></td>'
        + "".join(th(c) for c in cols) + "</tr>",
        row("主星", lambda c: f'<span class="god{" day" if c["god"] == "日主" else ""}">{c["god"]}</span>'),
        row("天干", lambda c: f'<span class="gz {_wx(c["gan"])}">{c["gan"]}</span>'),
        row("地支", lambda c: f'<span class="gz">{_z(c["zhi"], c["voids"])}</span>'),
        row("藏干", lambda c: '<div class="hidden">'
            + "<br>".join(f'<span class="hg {_wx(h)}">{h}</span> <span class="god">{g}</span>'
                          for h, g in c["hidden"]) + "</div>"),
        row("星运", lambda c: f'<span class="small">{c["terrain"]}</span>'),
        row("空亡", lambda c: f'<span class="small">{c["void"]}</span>'),
        row("纳音", lambda c: f'<span class="small">{c["nayin"]}</span>'),
        row("神煞", lambda c: '<div class="small">'
            + ("<br>".join(c["shensha"]) if c["shensha"] else "—") + "</div>"),
    ]
    return '<table class="pan">' + "".join(rows) + "</table>"


def _luck_strip(chart) -> str:
    this_year = datetime.now().year
    cells = []
    for lp in chart.luck_pillars:
        gz = lp.gan + lp.zhi
        cur = lp.start_year <= this_year < lp.start_year + 10
        cells.append(
            f'<div class="cell{" cur" if cur else ""}">'
            f'<div class="cy">{lp.start_year} · {lp.start_age:.0f} 岁起</div>'
            f'<div class="cg"><span class="{_wx(lp.gan)}">{lp.gan}</span>'
            f'<span class="{_wx(lp.zhi)}">{lp.zhi}</span></div>'
            f'<div class="cy">{_ten_god(chart.day_master, lp.gan)}'
            f' · {_terrain(chart.day_master, lp.zhi)}</div></div>')
    return '<div class="strip">' + "".join(cells) + "</div>"


def _childhood_block(chart) -> str:
    if not chart.childhood_luck:
        return ""
    cells = "".join(
        f'<div class="cell"><div class="cy">{age} 岁 · {year}</div>'
        f'<div class="cg"><span class="{_wx(gz[0])}">{gz[0]}</span>'
        f'<span class="{_wx(gz[1])}">{gz[1]}</span></div></div>'
        for age, year, gz in chart.childhood_luck)
    return ('<div class="sect" style="margin-top:14px">小运'
            '<span class="note">童限（未交大运）各虚岁</span></div>'
            f'<div class="strip">{cells}</div>')


def _flow_years(chart) -> str:
    this_year = datetime.now().year
    cells = []
    for year, gz, label in chart.flow_years:
        cls = "cell"
        if year == this_year:
            cls += " cur"
        if label.startswith("交运年"):
            cls += " jiao"
        cells.append(f'<div class="{cls}"><div class="cy">{year}</div>'
                     f'<div class="cg"><span class="{_wx(gz[0])}">{gz[0]}</span>'
                     f'<span class="{_wx(gz[1])}">{gz[1]}</span></div></div>')
    return '<div class="strip">' + "".join(cells) + "</div>"


def _flow_months(chart) -> str:
    cells = []
    for label, gz in chart.flow_months:
        cells.append(f'<div class="cell"><div class="cy">{label}</div>'
                     f'<div class="cg"><span class="{_wx(gz[0])}">{gz[0]}</span>'
                     f'<span class="{_wx(gz[1])}">{gz[1]}</span></div></div>')
    return '<div class="strip">' + "".join(cells) + "</div>"


def _season_bar(chart) -> str:
    seq = _SEASON.get(chart.month_ling)
    if not seq:
        return ""
    parts = "　".join(f"{wx}{lab}" for wx, lab in zip(seq, _SEASON_LABEL))
    return f"月令 {chart.month_ling}：{parts}"


def build_html(chart) -> str:
    """ChartData → 完整 HTML 文档。"""
    tpl = (Path(__file__).resolve().parent
           / "templates" / "paipan.html").read_text(encoding="utf-8")

    warns = []
    if chart.is_late_zi:
        warns.append("⚠️ 晚子时：本造按子初换日归入次日；子正换日一派日柱、时柱不同。")
    if chart.jie_gap_warning:
        warns.append(chart.jie_gap_warning)
    warnings = "".join(f'<div class="warn">{w}</div>' for w in warns)

    qiyun = ""
    if chart.luck_pillars:
        qiyun = (f"起运：{chart.start_age_text}"
                 f"（{'顺行' if chart.luck_is_forward else '逆行'}）")

    audit = (f"时区 {chart.tz_used}（夏令时：{'是' if chart.is_dst else '否'}）· "
             f"经度修正 {chart.lon_correction_min:+.2f} 分 · 均时差 {chart.eot_minutes:+.2f} 分 · "
             f"日界 子初换日（23:00）· tyme4py {chart.library_version} · "
             f"schema {chart.schema_version}")

    mapping = {
        "TITLE": f"命盘：{chart.name}",
        "NAME": chart.name,
        "GENDER_LABEL": "乾造" if chart.gender == "男" else "坤造",
        "DAY_MASTER": f"{chart.day_master}{_WX_GAN[chart.day_master]}",
        "BIRTHPLACE": chart.birthplace,
        "BIRTH_CLOCK": chart.birth_clock,
        "TRUE_SOLAR": chart.true_solar_time,
        "MONTH_LING": chart.month_ling,
        "TAI_YUAN": chart.tai_yuan,
        "MING_GONG": chart.ming_gong,
        "QIYUN": qiyun,
        "WARNINGS": warnings,
        "MAIN_TABLE": _main_table(chart),
        "LUCK_NOTE": f"{chart.start_age_text}起运，当前一步高亮",
        "LUCK_STRIP": _luck_strip(chart),
        "CHILDHOOD_BLOCK": _childhood_block(chart),
        "FLOW_YEARS": _flow_years(chart),
        "FLOW_MONTHS": _flow_months(chart),
        "SEASON_BAR": _season_bar(chart),
        "AUDIT": audit,
    }
    out = tpl
    for k, v in mapping.items():
        out = out.replace("{{" + k + "}}", str(v))
    return out
