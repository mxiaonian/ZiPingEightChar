"""L1→L2 数据契约（文档 4.7 节）。

改动本文件等于改契约版本（schema_version）。
本模块只做数据定义与组装，不含任何命理判断（P1）。
"""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Pillar:
    gan: str
    zhi: str
    gan_ten_god: str | None = None      # 该柱天干相对日干的十神
    hidden_stems: list[str] = field(default_factory=list)     # 藏干
    hidden_ten_gods: list[str] = field(default_factory=list)
    na_yin: str | None = None


@dataclass
class LuckPillar:
    index: int
    gan: str
    zhi: str
    start_age: float
    start_year: int


@dataclass
class ChartData:
    # —— 输入 ——
    name: str
    gender: str
    birthplace: str
    birth_clock: str             # 用户原始输入

    # —— 时间归算审计（P3）——
    tz_used: str
    is_dst: bool
    lon_correction_min: float
    eot_minutes: float
    true_solar_time: str
    is_late_zi: bool

    # —— 四柱 ——
    year: Pillar
    month: Pillar
    day: Pillar
    hour: Pillar

    # —— 派生 ——
    day_master: str              # 日干
    month_ling: str              # 月令地支（取格之锚）
    solar_term_before: str       # 出生前一个节气
    solar_term_after: str        # 出生后一个节气
    luck_pillars: list[LuckPillar] = field(default_factory=list)

    # —— 派生（渲染层补充字段）——
    luck_is_forward: bool = False        # 大运顺排/逆排
    start_age_text: str = ""             # 起运年龄，如「7 岁 7 个月 19 天」
    terrain: dict[str, str] = field(default_factory=dict)   # 四柱键 → 十二长生
    void: dict[str, str] = field(default_factory=dict)      # {"day": .., "hour": ..}
    shen_sha: list[str] = field(default_factory=list)       # 神煞
    flow_years: list[tuple[int, str]] = field(default_factory=list)   # 流年 (年份, 干支)
    flow_months: list[tuple[str, str]] = field(default_factory=list)  # 流月 (标签, 干支)
    tai_yuan: str = ""                   # 胎元
    ming_gong: str = ""                  # 命宫

    # —— 溯源 ——
    library_version: str = ""    # tyme4py 版本，写入输出
    schema_version: str = "1.0"


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def _fmt_term(term: dict) -> str:
    """{"name", "time"} → 「节气名 YYYY-MM-DD HH:MM」"""
    return f"{term['name']} {_fmt_dt(term['time'])}"


def _build_pillar(key: str, raw: dict) -> Pillar:
    gz = raw[key]
    hidden_pairs = raw.get("hidden", {}).get(key, [])
    return Pillar(
        gan=gz["gan"],
        zhi=gz["zhi"],
        gan_ten_god=raw.get("ten_god", {}).get(key),
        hidden_stems=[pair[0] for pair in hidden_pairs],
        hidden_ten_gods=[pair[1] for pair in hidden_pairs],
        na_yin=raw.get("na_yin", {}).get(key),
    )


def build_chart_data(
    name: str,
    gender: str,
    place: str,
    clock: str,
    loc,
    tz_audit: dict,
    st_audit: dict,
    bd_audit: dict,
    raw: dict,
    luck: dict,
    luck_pillars: list[LuckPillar],
    flow_years: list[tuple[int, str]],
    flow_months: list[tuple[str, str]],
) -> ChartData:
    """把 tyme_adapter 的原始 dict、各层 audit 与 luck 结果组装成 ChartData。

    纯组装，零命理判断。
    """
    return ChartData(
        # 输入
        name=name,
        gender=gender,
        birthplace=place,
        birth_clock=clock,
        # 时间归算审计
        tz_used=tz_audit["tz_used"],
        is_dst=tz_audit["is_dst"],
        lon_correction_min=st_audit["lon_correction_min"],
        eot_minutes=st_audit["eot_minutes"],
        true_solar_time=_fmt_dt(st_audit["tst"]),
        is_late_zi=bd_audit["is_late_zi"],
        # 四柱
        year=_build_pillar("year", raw),
        month=_build_pillar("month", raw),
        day=_build_pillar("day", raw),
        hour=_build_pillar("hour", raw),
        # 派生
        day_master=raw["day_master"],
        month_ling=raw["month"]["zhi"],
        solar_term_before=_fmt_term(raw["prev_jie"]),
        solar_term_after=_fmt_term(raw["next_jie"]),
        luck_pillars=luck_pillars,
        # 派生（补充字段）
        luck_is_forward=luck["is_forward"],
        start_age_text=luck["start_age_text"],
        terrain=raw.get("terrain", {}),
        void=raw.get("void", {}),
        shen_sha=raw.get("shen_sha", []),
        flow_years=flow_years,
        flow_months=flow_months,
        tai_yuan=raw.get("tai_yuan", ""),
        ming_gong=raw.get("ming_gong", ""),
        # 溯源
        library_version=raw.get("library_version", ""),
    )
