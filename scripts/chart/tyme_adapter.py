# -*- coding: utf-8 -*-
"""tyme4py 唯一接触面：输入真太阳时时刻，返回四柱及派生信息（纯计算，无命理判断）。"""
from datetime import datetime

import tyme4py
from tyme4py.solar import SolarTime, SolarTerm

LIBRARY_VERSION = tyme4py.__version__

_PILLARS = ("year", "month", "day", "hour")


def _solar_time_to_dt(t: SolarTime) -> datetime:
    return datetime(t.get_year(), t.get_month(), t.get_day(),
                    t.get_hour(), t.get_minute(), t.get_second())


def _jie_bounds(cast_dt: datetime) -> tuple:
    """出生时刻前后最近的两个节令（is_jie()），以出生年为中心 ±1 年遍历。"""
    prev_jie = next_jie = None
    for y in (cast_dt.year - 1, cast_dt.year, cast_dt.year + 1):
        for i in range(24):
            term = SolarTerm.from_index(y, i)
            if not term.is_jie():
                continue
            t = _solar_time_to_dt(term.get_julian_day().get_solar_time())
            if t < cast_dt and (prev_jie is None or t > prev_jie[1]):
                prev_jie = (term, t)
            elif t > cast_dt and (next_jie is None or t < next_jie[1]):
                next_jie = (term, t)
    return prev_jie, next_jie


def _hidden(me, earth_branch) -> list:
    items = []
    for getter in ("get_hide_heaven_stem_main",
                   "get_hide_heaven_stem_middle",
                   "get_hide_heaven_stem_residual"):
        hs = getattr(earth_branch, getter)()
        if hs is not None:
            items.append([hs.get_name(), me.get_ten_star(hs).get_name()])
    return items


def _shen_sha(ganzhi: dict, gender: str) -> dict:
    """子平通行神煞（查法见 chart/shensha.py 与 rules/94_神煞细节.md）。"""
    from chart.shensha import evaluate_natal, STAR_ORDER

    raw = evaluate_natal(ganzhi, gender)
    order = {name: i for i, name in enumerate(STAR_ORDER)}
    return {
        key: [f"{star}（{note}）"
              for star, note in sorted(entries, key=lambda e: order[e[0]])]
        for key, entries in raw.items()
    }


def cast(cast_dt: datetime, gender: str) -> dict:
    """cast_dt：已完成子初换日调整的真太阳时（naive，北京时间语义）。"""
    solar = SolarTime.from_ymd_hms(cast_dt.year, cast_dt.month, cast_dt.day,
                                   cast_dt.hour, cast_dt.minute, cast_dt.second)
    ec = solar.get_lunar_hour().get_eight_char()
    pillars = {k: getattr(ec, f"get_{k}")() for k in _PILLARS}
    me = ec.get_day().get_heaven_stem()

    prev_jie, next_jie = _jie_bounds(cast_dt)

    base = {k: {"gan": p.get_heaven_stem().get_name(),
                "zhi": p.get_earth_branch().get_name()} for k, p in pillars.items()}
    ganzhi = {k: v["gan"] + v["zhi"] for k, v in base.items()}

    return {
        **base,
        "day_master": me.get_name(),
        "ten_god": {k: me.get_ten_star(pillars[k].get_heaven_stem()).get_name()
                    for k in ("year", "month", "hour")},
        "hidden": {k: _hidden(me, pillars[k].get_earth_branch()) for k in _PILLARS},
        "terrain": {k: me.get_terrain(pillars[k].get_earth_branch()).get_name()
                    for k in _PILLARS},
        "na_yin": {k: pillars[k].get_sound().get_name() for k in _PILLARS},
        "void": {k: "".join(b.get_name() for b in pillars[k].get_extra_earth_branches())
                 for k in ("day", "hour")},
        "shen_sha": _shen_sha(ganzhi, gender),
        "prev_jie": {"name": prev_jie[0].get_name(), "time": prev_jie[1]},
        "next_jie": {"name": next_jie[0].get_name(), "time": next_jie[1]},
        "tai_yuan": ec.get_fetal_origin().get_name(),
        "ming_gong": ec.get_own_sign().get_name(),
        "library_version": LIBRARY_VERSION,
        "raw": ec,
    }
