"""地理模块：出生地字符串 → 经纬度与时区。"""

from .cities import Location, LocationError, resolve_location

__all__ = ["Location", "LocationError", "resolve_location"]
