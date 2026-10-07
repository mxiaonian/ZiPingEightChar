from dataclasses import dataclass
from pathlib import Path
import json

@dataclass(frozen=True)
class Location:
    name: str
    lon: float          # 东经为正
    lat: float
    tz: str             # IANA，如 "Asia/Shanghai"

class LocationError(Exception):
    """出生地无法解析 —— 必须向上抛，不得降级。"""

_CACHE: dict[str, Location] | None = None
_ALIASES: dict[str, str] | None = None

# 省级行政区简称/全称前缀，用于「新疆乌鲁木齐市」这类输入的兜底剥离
_PROVINCE_NAMES = (
    "北京", "天津", "上海", "重庆",
    "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江",
    "江苏", "浙江", "安徽", "福建", "江西", "山东",
    "河南", "湖北", "湖南", "广东", "广西", "海南",
    "四川", "贵州", "云南", "西藏", "陕西", "甘肃",
    "青海", "宁夏", "新疆", "香港", "澳门", "台湾",
)

# 行政通名，长的必须排在短的前面（replace 顺序敏感）
_ADMIN_WORDS = (
    "壮族自治区", "回族自治区", "维吾尔自治区", "自治区",
    "特别行政区", "省", "市",
)

def _load() -> dict[str, Location]:
    global _CACHE, _ALIASES
    if _CACHE is None:
        raw = json.loads(
            (Path(__file__).parents[2] / "data" / "cities.json")
            .read_text(encoding="utf-8")
        )
        _ALIASES = dict(raw.get("_aliases", {}))
        _CACHE = {
            k: Location(k, v["lon"], v["lat"], v["tz"])
            for k, v in raw.items()
            if not k.startswith("_")          # 跳过 _meta / _aliases
        }
    return _CACHE

def _alias(key: str) -> str | None:
    # 别名表：乌市、蓉城、羊城……（放在 cities.json 的 _aliases 段）
    _load()
    assert _ALIASES is not None
    return _ALIASES.get(key)

def _strip_admin(text: str) -> str:
    """去掉「省/市/自治区/壮族自治区/回族自治区/维吾尔自治区/特别行政区」等字样。"""
    for word in _ADMIN_WORDS:
        text = text.replace(word, "")
    return text

def resolve_location(text: str) -> Location:
    """
    容错匹配：全称 → 去后缀（市/省/县/区）→ 别名 → 去行政通名（含省名前缀）。
    命中即返回；未命中抛 LocationError（由 Agent 转成追问）。
    """
    table = _load()
    key = text.strip()

    candidates: list[str | None] = [key, key.rstrip("市省县区"), _alias(key)]

    stripped = _strip_admin(key)
    candidates += [stripped, _alias(stripped)]
    for province in _PROVINCE_NAMES:
        if stripped != province and stripped.startswith(province):
            rest = stripped[len(province):]
            candidates += [rest, _alias(rest)]

    for candidate in candidates:
        if candidate and candidate in table:
            return table[candidate]
    raise LocationError(
        f"未能解析出生地：{text!r}。请用户补充到地级市一级，"
        f"如「四川省成都市」「新疆乌鲁木齐市」。"
    )
