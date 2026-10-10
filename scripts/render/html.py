# scripts/render/html.py
"""ChartData → 单文件 HTML 盘面（模板 render/templates/paipan.html）。

与 Markdown 输出同为纯计算渲染：十神/藏干/空亡/纳音/十二长生/月令旺衰
均为固定查表，不含任何命理判断（P1）。岁运干支（大运/流年格）的十神/
星运/空亡/纳音复用 chart/ganzhi.py，神煞复用 chart/shensha.py 的岁运
求值器 evaluate_target（与 query_shensha.py 同一口径），不在渲染层
另造规则。

logo 与品牌字体（render/assets/）以 base64 内嵌，保证 HTML 单文件便携；
神煞条目的查法注释（全角/半角括号）仅在本装配层剔除，Markdown 输出保持原样。
"""
import base64
import re
from datetime import datetime
from pathlib import Path

from chart.ganzhi import NAYIN, WX_GAN, WX_ZHI, gz_void, ten_god, terrain
from chart.shensha import evaluate_target

_WX_CLASS = {"木": "wx-mu", "火": "wx-huo", "土": "wx-tu",
             "金": "wx-jin", "水": "wx-shui"}

_SEASON = {"寅": ("木", "火", "水", "金", "土"), "卯": ("木", "火", "水", "金", "土"),
           "巳": ("火", "土", "木", "水", "金"), "午": ("火", "土", "木", "水", "金"),
           "申": ("金", "水", "土", "火", "木"), "酉": ("金", "水", "土", "火", "木"),
           "亥": ("水", "木", "金", "土", "火"), "子": ("水", "木", "金", "土", "火"),
           "辰": ("土", "金", "火", "木", "水"), "戌": ("土", "金", "火", "木", "水"),
           "丑": ("土", "金", "火", "木", "水"), "未": ("土", "金", "火", "木", "水")}
_SEASON_LABEL = ("旺", "相", "休", "囚", "死")

_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
_SHA_NOTE_RE = re.compile(r"[（(][^）)]*[）)]")


def _strip_sha_note(entry: str) -> str:
    """神煞条目剔除查法括号注释：`将星（以年支子查，见于月支子）` → `将星`。"""
    return _SHA_NOTE_RE.sub("", entry).strip()


def _asset_b64(name: str) -> str:
    return base64.b64encode((_ASSETS_DIR / name).read_bytes()).decode("ascii")


def _wx(ch: str) -> str:
    wx = WX_GAN.get(ch) or WX_ZHI.get(ch)
    return _WX_CLASS.get(wx, "")


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
        "void": gz_void(p.gan + p.zhi),
        "nayin": p.na_yin or "",
        "shensha": [_strip_sha_note(s) for s in chart.shen_sha.get(key, [])],
        "voids": voids,
    }


def _render_table(cols: list) -> str:
    """干支列列表 → 排盘表格（主星/天干/地支/藏干/星运/空亡/纳音/神煞）。"""

    def th(c):
        tag = '<span class="curtag">当前</span>' if c["cur"] else ""
        return f'<th class="{"cur" if c["cur"] else ""}">{c["label"]}{tag}</th>'

    def row(label, fn):
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


def _main_table(chart) -> str:
    """排盘卡：仅年月日时四柱。"""
    cols = [_pillar_col(chart, key, label, cur=(key == "day"))
            for key, label in (("year", "年柱"), ("month", "月柱"),
                               ("day", "日柱"), ("hour", "时柱"))]
    return _render_table(cols)


def _target_shensha(chart, gz: str) -> list[str]:
    """岁运干支相对本命锚点所逢的神煞（与 query_shensha.py 同一求值器）。"""
    pillars = {k: getattr(chart, k).gan + getattr(chart, k).zhi
               for k in ("year", "month", "day", "hour")}
    return [star for star, _ in evaluate_target(pillars, chart.gender, gz)["anchored"]]


def _gz_sub(chart, gz: str) -> str:
    """岁运小卡的干支附属行：十神·星运 / 空亡 / 纳音 / 神煞（无标签，值本身说话）。"""
    lines = [
        f"{ten_god(chart.day_master, gz[0])} · {terrain(chart.day_master, gz[1])}",
        gz_void(gz),
        NAYIN[gz],
    ]
    sha = _target_shensha(chart, gz)
    if sha:
        lines.append(" · ".join(sha))
    return "".join(f'<div class="cs">{line}</div>' for line in lines)


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
            f'{_gz_sub(chart, gz)}</div>')
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
                     f'<span class="{_wx(gz[1])}">{gz[1]}</span></div>'
                     f'{_gz_sub(chart, gz)}</div>')
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
             f"日界 子初换日（23:00）")
    audit_full = (f"{audit}· tyme4py {chart.library_version} · "
                  f"schema {chart.schema_version}")

    mapping = {
        "TITLE": f"命盘：{chart.name}",
        "LOGO_B64": _asset_b64("lingyao-logo.png"),
        "FONT_B64": _asset_b64("logo-font.ttf"),
        "QRCODE_B64": _asset_b64("qun-qrcode.jpg"),
        "NAME": chart.name,
        "GENDER_LABEL": "乾造" if chart.gender == "男" else "坤造",
        "DAY_MASTER": f"{chart.day_master}{WX_GAN[chart.day_master]}",
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
        "AUDIT_FULL": audit_full,
    }
    out = tpl
    for k, v in mapping.items():
        out = out.replace("{{" + k + "}}", str(v))
    return out
