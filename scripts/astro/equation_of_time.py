import math
from datetime import datetime


def equation_of_time_minutes(dt_utc: datetime) -> float:
    """
    均时差近似，精度约 ±15 秒（远优于时辰粒度所需）。
    返回：真太阳时 = 平太阳时 + 返回值（分钟）。
    """
    assert dt_utc.tzinfo is not None

    # 一年中的天数序 + 当日小数
    doy = dt_utc.timetuple().tm_yday
    frac = (dt_utc.hour * 3600 + dt_utc.minute * 60 + dt_utc.second) / 86400

    gamma = 2 * math.pi / 365.0 * (doy - 1 + (frac - 0.5))

    # 经典近似式（Spencer / NOAA 系列），单位：分钟
    eot = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    return eot
