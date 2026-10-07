from datetime import datetime, timedelta

from .equation_of_time import equation_of_time_minutes

STANDARD_MERIDIAN = 120.0   # 北京时间基准经线


def to_true_solar_time(utc: datetime, lon: float) -> tuple[datetime, dict]:
    """
    完整真太阳时归算。

    链条：UTC → 120°E 平太阳时 → 经度修正 → 均时差 → 真太阳时

    参数
      utc : 带时区的 UTC datetime
      lon : 出生地经度（东经为正）

    返回
      (真太阳时 datetime, audit)
    """
    assert utc.tzinfo is not None, "必须传入带时区的 UTC 时间"

    # 剥掉 tzinfo 是刻意的：后续全是 120°E 平太阳时域内的算术
    base_naive = (utc + timedelta(hours=8)).replace(tzinfo=None)

    # 经度修正：每偏离 1° 差 4 分钟
    lon_corr = (lon - STANDARD_MERIDIAN) * 4.0

    eot = equation_of_time_minutes(utc)

    tst = base_naive + timedelta(minutes=lon_corr + eot)

    return tst, {
        "longitude": lon,
        "lon_correction_min": round(lon_corr, 2),
        "eot_minutes": round(eot, 2),
        "total_correction_min": round(lon_corr + eot, 2),
        "tst": tst,
    }
