from datetime import datetime, timedelta

ZI_HOUR_START = 23  # 真太阳时 23:00 换日


def resolve_calendar_day(tst: datetime, rule: str = "子初") -> tuple[datetime, dict]:
    """
    日界归算：rule="子初"（默认）真太阳时 23:00–24:00 归入次日；
    rule="子正" 以 0:00 为日界，晚子时不换日。

    返回
      (日历日 00:00 的 datetime, flag)
    """
    is_late_zi = tst.hour == ZI_HOUR_START

    day = tst.replace(hour=0, minute=0, second=0, microsecond=0)
    if is_late_zi and rule != "子正":
        day += timedelta(days=1)

    return day, {
        "rule": ("子正换日@真太阳时00:00" if rule == "子正"
                 else "子初换日@真太阳时23:00"),
        "is_late_zi": is_late_zi,
        "tst_time": tst.strftime("%Y-%m-%d %H:%M:%S"),
    }
